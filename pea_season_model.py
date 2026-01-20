
"""
pea_season_model_v1f4_hardy_gdd_stress_frost13.py
-----------------------------------------
Builds on v1f3 with TWO additions:
1) Stage-based stress weighting (mature plants are more vulnerable).
2) Senescence & lifespan caps so peas can't linger unrealistically.

What's included overall:
- April-tuned sowing (April override may bypass frost-window if temps OK)
- Soil temp/moisture; soil GDD accumulation (base 2 °C)
- Phenology via GDD: vegetative -> flowering (~45%) -> podding (~75%) -> senescent (>=100%)
- Daily senescence decay (small negative)
- Frost/heat stress events
- Recovery: message-only (no +health to avoid double-heal; rely on v41 water healing)
- Cumulative stress mortality: stress_index + stress_streak -> chronic weakening -> wither
- **NEW** Stage-based stress weighting
- **NEW** Lifespan cap (random 75–100 days) AND max senescence duration (random 20–40 days)

Result: Spring peas mature in ~80 days, then die within ~1 month; autumn peas die in late fall.

Patched: Frost damage weight 1.3 (frost13); Added senescence counter; Sticky frost (decay=0.98, streak relief=0); Frost by min-temp.

"""
from __future__ import annotations
import datetime as _dt
import random as _random
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

def _m_clamp(x, a, b):
    return a if x < a else b if x > b else x

@dataclass
class PlantPheno:
    sow_date: _dt.date
    gdd: float = 0.0
    gdd_threshold: float = 900.0
    stage: str = "vegetative"
    senescent: bool = False
    dead: bool = False
    # cumulative stress tracking
    stress_index: float = 0.0
    stress_streak: int = 0
    last_date: Optional[_dt.date] = None
    # NEW: lifespan & senescence caps
    lifespan_limit_days: int = 100
    senescence_limit_days: int = 30
    senescence_start_date: Optional[_dt.date] = None
    # Explicit senescence countdown (lethal when it hits 0)
    senescence_days_remaining: Optional[int] = None

class PeaSeasonModelV1F4:
    # --- thresholds (April-tuned) -------------------------------------------
    SOIL_LAG = 0.18
    SOIL_RAIN_REFRIG = 0.15
    SOIL_INIT = -2.0
    SOW_MIN_SOIL = -2.0
    SOW_OK_SOIL  = -3.8
    AIR_MEAN_OK  = -3.0
    HOT_AVOID_5D = 25.0
    HEAT_STRESS_NOON = 34.0
    AUTUMN_MIN_FROST_FREE_DAYS = 1
    BASE_DRY = 0.015
    TEMP_DRY_GAIN = 0.0025
    AMP_DRY_GAIN = 0.010
    CLOUD_DRY_REDUCTION = 0.04
    RAIN_WETTING_PER_MM = 0.010
    SOFT_OPEN_SPRING = (3, 1)
    AUTUMN_OPEN = (8, 20)
    AUTUMN_CLOSE = (10, 5)

    # --- phenology / senescence knobs ---------------------------------------
    GDD_BASE = 2.0
    GDD_THRESH_RANGE = (820, 980)
    GDD_FLOWER_FRAC = 0.45
    GDD_POD_FRAC    = 0.75
    SENESCENCE_DECAY = (2, 6)

    # --- recovery (message only) --------------------------------------------
    RECOVER_MOIST_RANGE = (0.40, 0.80)
    RECOVER_AIR_MEAN_C  = (11.0, 22.0)
    RECOVER_DELTA_RANGE = (0, 0)  # message-only

    # --- cumulative stress knobs (v1f3 stricter) ----------------------------
    STRESS_WEIGHT = {"Frost damage": 1.3, "Heat stress": 0.7}  # ↑ frost weight for earlier autumn death
    STRESS_DECAY_PER_DAY = 0.98
    STREAK_RELIEF_PER_DAY = 0
    STRESS_MORTALITY = 4.0     # stricter
    STREAK_MORTALITY = 4       # stricter
    CHRONIC_ZONE = 3.0

    # --- stage-based multipliers (NEW) --------------------------------------
    STAGE_STRESS_MULT = {
        "vegetative": 1.0,
        "flowering": 1.5,
        "podding": 2.0,
        "senescent": 2.0
    }

    # --- lifespan / senescence limits (NEW) ---------------------------------
    LIFESPAN_RANGE_DAYS = (75, 100)     # total days after sowing
    SENESCENCE_RANGE_DAYS = (20, 40)    # days allowed AFTER senescence starts

    def __init__(self, climate, seed=1866):
        self.climate = climate
        self.rng = _random.Random(seed)
        self.soil_temp = self.SOIL_INIT
        self.soil_moisture = 0.5
        self.last_date = None
        self._soil_gdd = 0.0
        self.plants: Dict[Any, PlantPheno] = {}

    # --- climate helpers -----------------------------------------------------
    def _air_hours(self, date: _dt.date):
        return self.climate.hourly_targets(date)
    def _air_means(self, date: _dt.date):
        h = self._air_hours(date)
        mean = sum(h)/24.0
        hmin = min(h)
        hmax = max(h)
        eve = h[22]
        return mean, hmin, hmax, eve
    def _mean_last_n_days(self, date: _dt.date, n=5):
        import datetime as dt
        tot = 0.0
        for i in range(n):
            d = date - dt.timedelta(days=i)
            tot += self._air_means(d)[0]
        return tot/n
    def _frost_free_days_remaining(self, date: _dt.date, year_like=None):
        last_spring, first_autumn = self.climate._frost_window(date.year if year_like is None else year_like)
        return max(0, first_autumn - date.timetuple().tm_yday)
    def _after_autumn_open(self, date: _dt.date):
        return (date.month, date.day) >= self.AUTUMN_OPEN
    def _in_autumn_window(self, date: _dt.date):
        md = (date.month, date.day); return self.AUTUMN_OPEN <= md <= self.AUTUMN_CLOSE

    # --- daily soil update ---------------------------------------------------
    def update_soil(self, date: _dt.date):
        day = self.climate.daily_state(date)
        air_mean, air_noon, _, _ = self._air_means(date)
        rain_mm = float(day.get("rain_mm", 0.0))
        cloud = float(day.get("cloud_0_10", 5.0))
        amp = float(day.get("amp_scale", 0.75))
        target = air_mean - 0.5
        self.soil_temp += self.SOIL_LAG * (target - self.soil_temp)
        if rain_mm > 0:
            self.soil_temp -= self.SOIL_RAIN_REFRIG * (0.5 + min(1.5, rain_mm/10.0))
        dry = (self.BASE_DRY +
               max(0.0, air_mean - 5.0)*self.TEMP_DRY_GAIN +
               amp*self.AMP_DRY_GAIN -
               (cloud/10.0)*self.CLOUD_DRY_REDUCTION)
        if air_noon >= self.HEAT_STRESS_NOON:
            dry += 0.01
        wet = rain_mm * self.RAIN_WETTING_PER_MM
        self.soil_moisture = _m_clamp(self.soil_moisture + wet - dry, 0.0, 1.0)
        self.last_date = date
        self._soil_gdd += max(0.0, self.soil_temp - self.GDD_BASE)
        return {"soil_temp": self.soil_temp, "soil_moisture": self.soil_moisture, "soil_gdd": self._soil_gdd}

    # --- sow / grow gates ----------------------------------------------------
    def can_sow(self, date: _dt.date, year_like=None):
        # # April override (Mendel) — allow even during frost window if temps support
        soil = self.soil_temp
        air5  = self._mean_last_n_days(date, n=5)
        air10 = self._mean_last_n_days(date, n=10)
        # if date.month == 4 and soil >= 2.5 and air10 >= 5.5:
        if date.month == 3 and air10 >= 5.5:
            return (True, "March bias: temps okay")
        if date.month == 4 and air10 >= 5.5:
            return (True, "April bias: ideal for sowing (Mendel)")
        if date.month == 5:
            return (True, "May: open sowing")

        # Otherwise normal frost gate
        if self.climate.daily_state(date, year_like=year_like).get("in_frost_season", False):
            return (False, "Frost window active")

        # Hard floor
        if soil < self.SOW_MIN_SOIL:
            return (False, f"Soil too cold ({soil:.1f}°C)")

        # Marginal support
        if soil < self.SOW_OK_SOIL:
            soft_open = (date.month, date.day) >= self.SOFT_OPEN_SPRING
            if not soft_open and not self._in_autumn_window(date):
                return (False, f"Early spring & marginal soil ({soil:.1f}°C)")
            if air5 < self.AIR_MEAN_OK:
                return (False, f"Air still cold (5-day mean {air5:.1f}°C)")

        # Summer heat-avoid
        if self._mean_last_n_days(date, n=5) > self.HOT_AVOID_5D and not self._in_autumn_window(date):
            return (False, "Too hot for new sowings")

        # Autumn runway
        if self._after_autumn_open(date):
            if self._frost_free_days_remaining(date, year_like=year_like) < self.AUTUMN_MIN_FROST_FREE_DAYS:
                return (False, "Too close to first autumn frost")

        return (True, "OK to sow")


    def can_grow(self, date: _dt.date):
            air_mean, air_min, air_max, _ = self._air_means(date)
            # Use daily extrema to catch overnight frost & hot spikes
            if air_min < 15.0:
                return (False, "Severe freezing – lethal")
            if air_min < 0.0:
                return (True, "Frost damage")
            if air_max > 34.0:
                return (True, "Heat stress")
            return (True, "Normal")
    def suggested_health_delta(self, note: str) -> int:
        if "lethal" in note: return -9999
        if "Frost damage" in note: return -self.rng.randint(4,12)
        if "Heat stress" in note: return -self.rng.randint(1,4)
        return 0

    # --- plant registry & daily events --------------------------------------
    def register_plant(self, plant_id: Any, sow_date: _dt.date, gdd_threshold: Optional[float]=None):
        if gdd_threshold is None:
            gdd_threshold = self.rng.uniform(*self.GDD_THRESH_RANGE)
        plant = PlantPheno(
            sow_date=sow_date, gdd=0.0, gdd_threshold=gdd_threshold, stage="vegetative",
            senescent=False, dead=False,
            lifespan_limit_days=self.rng.randint(*self.LIFESPAN_RANGE_DAYS),
            senescence_limit_days=self.rng.randint(*self.SENESCENCE_RANGE_DAYS),
        )
        self.plants[plant_id] = plant

    def unregister_plant(self, plant_id: Any):
        self.plants.pop(plant_id, None)

    def _advance_pheno(self, plant: PlantPheno, date: _dt.date):
        ev = []
        frac = plant.gdd / max(1.0, plant.gdd_threshold)
        if plant.stage == "vegetative" and frac >= self.GDD_FLOWER_FRAC:
            plant.stage = "flowering"; ev.append(("stage","Flowering started"))
        if plant.stage in ("vegetative","flowering") and frac >= self.GDD_POD_FRAC:
            plant.stage = "podding"; ev.append(("stage","Podding started"))
        if (not plant.senescent) and plant.gdd >= plant.gdd_threshold:
            plant.senescent = True
            plant.senescence_start_date = date
            plant.senescence_days_remaining = plant.senescence_limit_days
            ev.append(("senescence_start","Plant entering senescence (maturity reached)"))
        return ev

    def _check_caps(self, plant: PlantPheno, date: _dt.date):
        # Death by total lifespan cap
        total_days = (date - plant.sow_date).days
        if total_days > plant.lifespan_limit_days:
            return ("wither", f"Natural lifespan exceeded ({total_days}d > {plant.lifespan_limit_days}d)")
        # Death by senescence duration cap
        if plant.senescence_start_date is not None:
            sen_days = (date - plant.senescence_start_date).days
            if sen_days > plant.senescence_limit_days:
                return ("wither", f"Senescence duration exceeded ({sen_days}d > {plant.senescence_limit_days}d)")
        return None

    def update_day(self, date: _dt.date, plant_ids: List[Any]):
        events = []
        soil = self.update_soil(date)
        air_mean, _, _, _ = self._air_means(date)
        alive_ok, note = self.can_grow(date)
        delta = self.suggested_health_delta(note)

        for pid in plant_ids:
            plant = self.plants.get(pid)
            if plant is None:
                self.register_plant(pid, sow_date=date); plant = self.plants[pid]
            if plant.dead: continue

            # Lifespan / senescence caps (checked first to avoid lingering)
            cap = self._check_caps(plant, date)
            if cap is not None:
                plant.dead = True
                ctype, cmsg = cap
                events.append({"date": date, "plant_id": pid, "type": ctype,
                               "message": cmsg, "suggested_health_delta": -9999})
                continue

            # Decay cumulative stress over gaps
            if plant.last_date is not None and date > plant.last_date:
                gap = (date - plant.last_date).days
                plant.stress_index *= (self.STRESS_DECAY_PER_DAY ** gap)
                plant.stress_streak = max(0, plant.stress_streak - gap * self.STREAK_RELIEF_PER_DAY)
            plant.last_date = date

            # Accumulate GDD
            plant.gdd += max(0.0, soil["soil_temp"] - self.GDD_BASE)

            # Stage transitions / senescence start
            for (etype,msg) in self._advance_pheno(plant, date):
                events.append({"date": date, "plant_id": pid, "type": etype, "message": msg})

            # --- Stress / lethal / cumulative mortality ----------------------
            if delta <= -9999:
                plant.dead = True
                events.append({"date": date, "plant_id": pid, "type": "lethal_freeze",
                               "message": "Plant killed by severe freeze"})
                continue

            if note != "Normal":
                # immediate stress event
                events.append({"date": date, "plant_id": pid, "type": "stress",
                               "message": note, "suggested_health_delta": delta})
                # cumulative stress with stage-based multiplier
                base_w = self.STRESS_WEIGHT.get(note, 1.0)
                mult = self.STAGE_STRESS_MULT["senescent" if plant.senescent else plant.stage]
                w = base_w * mult
                plant.stress_index += w
                plant.stress_streak += 1

                # mortality checks
                if plant.stress_index >= self.STRESS_MORTALITY or plant.stress_streak >= self.STREAK_MORTALITY:
                    plant.dead = True
                    events.append({"date": date, "plant_id": pid, "type": "wither",
                                   "message": "Plant succumbed to accumulated stress",
                                   "suggested_health_delta": -9999})
                    continue
                elif plant.stress_index >= self.CHRONIC_ZONE:
                    # chronic weakening (small persistent decline)
                    slow = -self.rng.randint(2, 4)
                    events.append({"date": date, "plant_id": pid, "type": "chronic_stress",
                                   "message": "Chronic stress weakening the plant",
                                   "suggested_health_delta": slow})
            else:
                # No stress: relieve streak and decay load; (optional) message-only recovery
                plant.stress_streak = max(0, plant.stress_streak - self.STREAK_RELIEF_PER_DAY)
                plant.stress_index *= self.STRESS_DECAY_PER_DAY

                loM, hiM = self.RECOVER_MOIST_RANGE
                loT, hiT = self.RECOVER_AIR_MEAN_C
                if loM <= self.soil_moisture <= hiM and loT <= air_mean <= hiT and not plant.senescent:
                    events.append({"date": date, "plant_id": pid, "type": "recovery",
                                   "message": "Favorable conditions – plant recovering",
                                   "suggested_health_delta": 0})

            # Senescence daily decay
            if plant.senescent and not plant.dead:
                sen_decay = -self.rng.randint(*self.SENESCENCE_DECAY)
                events.append({"date": date, "plant_id": pid, "type": "senescent_tick",
                               "message": "Natural senescence", "suggested_health_delta": sen_decay})
        return events
