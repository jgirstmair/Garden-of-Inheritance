"""
Pea Season Model

Advanced phenological simulation for garden peas based on Growing Degree Days (GDD),
environmental stress, and realistic lifecycle constraints.

Features:
- Soil temperature and moisture simulation
- GDD-based phenology (vegetative → flowering → podding → senescence)
- Frost and heat stress with cumulative damage tracking
- Stage-based stress vulnerability
- Lifespan and senescence caps for realistic plant aging
- April-tuned sowing windows matching Mendel's practices

Version: v1f4 (hardy GDD stress frost13)
Based on historical pea cultivation practices from Mendel's era
"""

from __future__ import annotations
import datetime as dt
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# Utility Functions
# ============================================================================

def _clamp(x, a, b):
    """Clamp value x to range [a, b]."""
    return a if x < a else b if x > b else x


# ============================================================================
# Plant Phenology Data
# ============================================================================

@dataclass
class PlantPheno:
    """
    Tracks individual plant phenological state and stress accumulation.
    
    Attributes:
        sow_date: Date the plant was sown
        gdd: Accumulated growing degree days
        gdd_threshold: GDD needed to reach maturity
        stage: Current growth stage (vegetative/flowering/podding/senescent)
        senescent: Whether plant has entered senescence
        dead: Whether plant is dead
        stress_index: Cumulative stress load
        stress_streak: Consecutive days of stress
        last_date: Last date plant was updated
        lifespan_limit_days: Maximum days the plant can live
        senescence_limit_days: Maximum days in senescence before death
        senescence_start_date: Date senescence began
        senescence_days_remaining: Days remaining in senescence
    """
    sow_date: dt.date
    gdd: float = 0.0
    gdd_threshold: float = 900.0
    stage: str = "vegetative"
    senescent: bool = False
    dead: bool = False
    stress_index: float = 0.0
    stress_streak: int = 0
    last_date: Optional[dt.date] = None
    lifespan_limit_days: int = 100
    senescence_limit_days: int = 30
    senescence_start_date: Optional[dt.date] = None
    senescence_days_remaining: Optional[int] = None


# ============================================================================
# Pea Season Model
# ============================================================================

class PeaSeasonModelV1F4:
    """
    Comprehensive pea lifecycle simulation with environmental stress.
    
    Models:
    - Soil temperature lag and moisture dynamics
    - GDD accumulation (base 2°C)
    - Sowing windows (April-tuned, frost-aware)
    - Growth stages (vegetative → flowering → podding → senescent)
    - Frost and heat stress events
    - Cumulative stress mortality
    - Natural senescence and lifespan limits
    """
    
    # ========================================================================
    # Soil and Sowing Thresholds
    # ========================================================================
    
    SOIL_LAG = 0.18                  # Soil temperature lag coefficient
    SOIL_RAIN_REFRIG = 0.15          # Cooling effect of rain on soil
    SOIL_INIT = -2.0                 # Initial soil temperature (°C)
    SOW_MIN_SOIL = -2.0              # Absolute minimum soil temp for sowing
    SOW_OK_SOIL = -3.8               # Marginal soil temp threshold
    AIR_MEAN_OK = -3.0               # Minimum air temp for sowing
    HOT_AVOID_5D = 25.0              # Max 5-day mean to avoid (summer)
    HEAT_STRESS_NOON = 34.0          # Noon temp triggering heat stress
    AUTUMN_MIN_FROST_FREE_DAYS = 1   # Min runway for autumn sowing
    
    # ========================================================================
    # Soil Moisture Dynamics
    # ========================================================================
    
    BASE_DRY = 0.015                 # Base daily drying rate
    TEMP_DRY_GAIN = 0.0025           # Extra drying per °C above 5°C
    AMP_DRY_GAIN = 0.010             # Extra drying from diurnal amplitude
    CLOUD_DRY_REDUCTION = 0.04       # Reduced drying under clouds
    RAIN_WETTING_PER_MM = 0.010      # Moisture gain per mm of rain
    
    # ========================================================================
    # Seasonal Windows
    # ========================================================================
    
    SOFT_OPEN_SPRING = (3, 1)        # Early spring sowing (March 1)
    AUTUMN_OPEN = (8, 20)            # Autumn sowing window opens
    AUTUMN_CLOSE = (10, 5)           # Autumn sowing window closes
    
    # ========================================================================
    # Phenology and Senescence
    # ========================================================================
    
    GDD_BASE = 2.0                   # Base temperature for GDD (°C)
    GDD_THRESH_RANGE = (820, 980)    # Random GDD threshold range
    GDD_FLOWER_FRAC = 0.45           # GDD fraction for flowering
    GDD_POD_FRAC = 0.75              # GDD fraction for podding
    SENESCENCE_DECAY = (2, 6)        # Daily health loss in senescence
    
    # ========================================================================
    # Recovery Conditions (message-only, no health gain)
    # ========================================================================
    
    RECOVER_MOIST_RANGE = (0.40, 0.80)   # Optimal soil moisture range
    RECOVER_AIR_MEAN_C = (11.0, 22.0)    # Optimal air temperature range
    RECOVER_DELTA_RANGE = (0, 0)         # No actual health gain (message only)
    
    # ========================================================================
    # Cumulative Stress System
    # ========================================================================
    
    STRESS_WEIGHT = {
        "Frost damage": 1.3,         # Frost is more severe (autumn mortality)
        "Heat stress": 0.7,          # Heat is less severe
    }
    STRESS_DECAY_PER_DAY = 0.98      # Daily stress index decay
    STREAK_RELIEF_PER_DAY = 0        # No streak relief (sticky frost)
    STRESS_MORTALITY = 4.0           # Stress index threshold for death
    STREAK_MORTALITY = 4             # Stress streak threshold for death
    CHRONIC_ZONE = 3.0               # Threshold for chronic weakening
    
    # ========================================================================
    # Stage-Based Stress Multipliers
    # ========================================================================
    
    STAGE_STRESS_MULT = {
        "vegetative": 1.0,           # Seedlings are hardy
        "flowering": 1.5,            # Flowers are vulnerable
        "podding": 2.0,              # Pods are very vulnerable
        "senescent": 2.0,            # Senescent plants are fragile
    }
    
    # ========================================================================
    # Stage-Based Lethal Freeze Temperatures
    # ========================================================================
    # Based on real pea plant cold tolerance
    # Most garden peas (Pisum sativum) die between -4°C and -9°C
    
    LETHAL_FREEZE_TEMPS = {
        "vegetative": -7.0,          # Hardy established seedlings
        "flowering": -4.0,           # Vulnerable flowers/reproductive tissue
        "podding": -4.0,             # Vulnerable developing pods
        "senescent": -5.0,           # Weakened aging plants
    }
    LETHAL_FREEZE_GLOBAL = -7.0      # Fallback for unknown stages
    
    # ========================================================================
    # Lifespan and Senescence Limits
    # ========================================================================
    
    LIFESPAN_RANGE_DAYS = (75, 100)      # Total lifespan (days)
    SENESCENCE_RANGE_DAYS = (20, 40)     # Max senescence duration (days)
    
    # ========================================================================
    # Initialization
    # ========================================================================
    
    def __init__(self, climate, seed=1866):
        """
        Initialize the pea season model.
        
        Args:
            climate: MendelClimate instance for weather data
            seed: Random seed for deterministic simulation
        """
        self.climate = climate
        self.rng = random.Random(seed)
        self.soil_temp = self.SOIL_INIT
        self.soil_moisture = 0.5
        self.last_date = None
        self._soil_gdd = 0.0
        self.plants: Dict[Any, PlantPheno] = {}
    
    # ========================================================================
    # Climate Helpers
    # ========================================================================
    
    def _air_hours(self, date: dt.date):
        """Get 24 hourly air temperatures for date."""
        return self.climate.hourly_targets(date)
    
    def _air_means(self, date: dt.date):
        """
        Calculate air temperature statistics for date.
        
        Returns:
            Tuple of (mean, min, max, evening) temperatures
        """
        h = self._air_hours(date)
        mean = sum(h) / 24.0
        hmin = min(h)
        hmax = max(h)
        eve = h[22]
        return mean, hmin, hmax, eve
    
    def _mean_last_n_days(self, date: dt.date, n=5):
        """Calculate mean air temperature over last n days."""
        tot = 0.0
        for i in range(n):
            d = date - dt.timedelta(days=i)
            tot += self._air_means(d)[0]
        return tot / n
    
    def _frost_free_days_remaining(self, date: dt.date, year_like=None):
        """Calculate days until first autumn frost."""
        last_spring, first_autumn = self.climate._frost_window(
            date.year if year_like is None else year_like
        )
        return max(0, first_autumn - date.timetuple().tm_yday)
    
    def _after_autumn_open(self, date: dt.date):
        """Check if date is after autumn sowing window opens."""
        return (date.month, date.day) >= self.AUTUMN_OPEN
    
    def _in_autumn_window(self, date: dt.date):
        """Check if date is within autumn sowing window."""
        md = (date.month, date.day)
        return self.AUTUMN_OPEN <= md <= self.AUTUMN_CLOSE
    
    # ========================================================================
    # Soil Update
    # ========================================================================
    
    def update_soil(self, date: dt.date):
        """
        Update soil temperature and moisture for the given date.
        
        Args:
            date: Date to update for
            
        Returns:
            Dict with soil_temp, soil_moisture, soil_gdd
        """
        day = self.climate.daily_state(date)
        air_mean, air_noon, _, _ = self._air_means(date)
        rain_mm = float(day.get("rain_mm", 0.0))
        cloud = float(day.get("cloud_0_10", 5.0))
        amp = float(day.get("amp_scale", 0.75))
        
        # Soil temperature lags air temperature
        target = air_mean - 0.5
        self.soil_temp += self.SOIL_LAG * (target - self.soil_temp)
        
        # Rain cools the soil
        if rain_mm > 0:
            self.soil_temp -= self.SOIL_RAIN_REFRIG * (0.5 + min(1.5, rain_mm / 10.0))
        
        # Soil moisture dynamics
        dry = (
            self.BASE_DRY
            + max(0.0, air_mean - 5.0) * self.TEMP_DRY_GAIN
            + amp * self.AMP_DRY_GAIN
            - (cloud / 10.0) * self.CLOUD_DRY_REDUCTION
        )
        if air_noon >= self.HEAT_STRESS_NOON:
            dry += 0.01
        
        wet = rain_mm * self.RAIN_WETTING_PER_MM
        self.soil_moisture = _clamp(self.soil_moisture + wet - dry, 0.0, 1.0)
        
        self.last_date = date
        self._soil_gdd += max(0.0, self.soil_temp - self.GDD_BASE)
        
        return {
            "soil_temp": self.soil_temp,
            "soil_moisture": self.soil_moisture,
            "soil_gdd": self._soil_gdd,
        }
    
    # ========================================================================
    # Sowing and Growth Gates
    # ========================================================================
    
    def can_sow(self, date: dt.date, year_like=None):
        """
        Check if sowing is allowed on the given date.
        
        Args:
            date: Date to check
            year_like: Optional year override for frost window
            
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        soil = self.soil_temp
        air5 = self._mean_last_n_days(date, n=5)
        air10 = self._mean_last_n_days(date, n=10)
        
        # March/April bias (Mendel's practices)
        if date.month == 3 and air10 >= 5.5:
            return (True, "March bias: temps okay")
        if date.month == 4 and air10 >= 5.5:
            return (True, "April bias: ideal for sowing (Mendel)")
        if date.month == 5:
            return (True, "May: open sowing")
        
        # Normal frost gate
        if self.climate.daily_state(date, year_like=year_like).get("in_frost_season", False):
            return (False, "Frost window active")
        
        # Hard soil temperature floor
        if soil < self.SOW_MIN_SOIL:
            return (False, f"Soil too cold ({soil:.1f}°C)")
        
        # Marginal soil support
        if soil < self.SOW_OK_SOIL:
            soft_open = (date.month, date.day) >= self.SOFT_OPEN_SPRING
            if not soft_open and not self._in_autumn_window(date):
                return (False, f"Early spring & marginal soil ({soil:.1f}°C)")
            if air5 < self.AIR_MEAN_OK:
                return (False, f"Air still cold (5-day mean {air5:.1f}°C)")
        
        # Summer heat avoidance
        if self._mean_last_n_days(date, n=5) > self.HOT_AVOID_5D and not self._in_autumn_window(date):
            return (False, "Too hot for new sowings")
        
        # Autumn runway check
        if self._after_autumn_open(date):
            if self._frost_free_days_remaining(date, year_like=year_like) < self.AUTUMN_MIN_FROST_FREE_DAYS:
                return (False, "Too close to first autumn frost")
        
        return (True, "OK to sow")
    
    def can_grow(self, date: dt.date):
        """
        Check growth conditions and stress for the given date.
        
        Args:
            date: Date to check
            
        Returns:
            Tuple of (can_grow: bool, status_note: str)
        """
        air_mean, air_min, air_max, _ = self._air_means(date)
        
        # Use daily extrema to catch overnight frost and hot spikes
        # Realistic lethal freeze threshold for pea plants:
        # Most established peas die around -7°C to -9°C
        # Flowering/podding stages are even more vulnerable
        if air_min < -7.0:
            return (False, "Severe freezing – lethal")
        if air_min < 0.0:
            return (True, "Frost damage")
        if air_max > 34.0:
            return (True, "Heat stress")
        
        return (True, "Normal")
    
    def suggested_health_delta(self, note: str) -> int:
        """
        Get suggested health change for a given growth status.
        
        Args:
            note: Status note from can_grow()
            
        Returns:
            Suggested health delta (negative for damage)
        """
        if "lethal" in note:
            return -9999
        if "Frost damage" in note:
            return -self.rng.randint(4, 12)
        if "Heat stress" in note:
            return -self.rng.randint(1, 4)
        return 0
    
    # ========================================================================
    # Plant Registry
    # ========================================================================
    
    def register_plant(
        self,
        plant_id: Any,
        sow_date: dt.date,
        gdd_threshold: Optional[float] = None
    ):
        """
        Register a new plant in the simulation.
        
        Args:
            plant_id: Unique identifier for the plant
            sow_date: Date the plant was sown
            gdd_threshold: Optional custom GDD threshold (random if None)
        """
        if gdd_threshold is None:
            gdd_threshold = self.rng.uniform(*self.GDD_THRESH_RANGE)
        
        plant = PlantPheno(
            sow_date=sow_date,
            gdd=0.0,
            gdd_threshold=gdd_threshold,
            stage="vegetative",
            senescent=False,
            dead=False,
            lifespan_limit_days=self.rng.randint(*self.LIFESPAN_RANGE_DAYS),
            senescence_limit_days=self.rng.randint(*self.SENESCENCE_RANGE_DAYS),
        )
        self.plants[plant_id] = plant
    
    def unregister_plant(self, plant_id: Any):
        """Remove a plant from the simulation."""
        self.plants.pop(plant_id, None)
    
    # ========================================================================
    # Phenology Advancement
    # ========================================================================
    
    def _advance_pheno(self, plant: PlantPheno, date: dt.date):
        """
        Advance plant through growth stages based on GDD.
        
        Args:
            plant: Plant to advance
            date: Current date
            
        Returns:
            List of (event_type, message) tuples
        """
        ev = []
        frac = plant.gdd / max(1.0, plant.gdd_threshold)
        
        # Flowering transition
        if plant.stage == "vegetative" and frac >= self.GDD_FLOWER_FRAC:
            plant.stage = "flowering"
            ev.append(("stage", "Flowering started"))
        
        # Podding transition
        if plant.stage in ("vegetative", "flowering") and frac >= self.GDD_POD_FRAC:
            plant.stage = "podding"
            ev.append(("stage", "Podding started"))
        
        # Senescence onset
        if (not plant.senescent) and plant.gdd >= plant.gdd_threshold:
            plant.senescent = True
            plant.senescence_start_date = date
            plant.senescence_days_remaining = plant.senescence_limit_days
            ev.append(("senescence_start", "Plant entering senescence (maturity reached)"))
        
        return ev
    
    def _check_caps(self, plant: PlantPheno, date: dt.date):
        """
        Check lifespan and senescence duration caps.
        
        Args:
            plant: Plant to check
            date: Current date
            
        Returns:
            Tuple of (event_type, message) or None
        """
        # Death by total lifespan cap
        total_days = (date - plant.sow_date).days
        if total_days > plant.lifespan_limit_days:
            return (
                "wither",
                f"Natural lifespan exceeded ({total_days}d > {plant.lifespan_limit_days}d)"
            )
        
        # Death by senescence duration cap
        if plant.senescence_start_date is not None:
            sen_days = (date - plant.senescence_start_date).days
            if sen_days > plant.senescence_limit_days:
                return (
                    "wither",
                    f"Senescence duration exceeded ({sen_days}d > {plant.senescence_limit_days}d)"
                )
        
        return None
    
    # ========================================================================
    # Daily Update
    # ========================================================================
    
    def update_day(self, date: dt.date, plant_ids: List[Any]):
        """
        Update all plants for a given day.
        
        Args:
            date: Date to update for
            plant_ids: List of plant IDs to update
            
        Returns:
            List of event dictionaries with keys:
            - date: Event date
            - plant_id: Plant identifier
            - type: Event type (stress/recovery/wither/etc)
            - message: Human-readable message
            - suggested_health_delta: Optional health change
        """
        events = []
        soil = self.update_soil(date)
        air_mean, _, _, _ = self._air_means(date)
        alive_ok, note = self.can_grow(date)
        delta = self.suggested_health_delta(note)
        
        for pid in plant_ids:
            plant = self.plants.get(pid)
            if plant is None:
                self.register_plant(pid, sow_date=date)
                plant = self.plants[pid]
            if plant.dead:
                continue
            
            # Check lifespan/senescence caps first
            cap = self._check_caps(plant, date)
            if cap is not None:
                plant.dead = True
                ctype, cmsg = cap
                events.append({
                    "date": date,
                    "plant_id": pid,
                    "type": ctype,
                    "message": cmsg,
                    "suggested_health_delta": -9999,
                })
                continue
            
            # Decay cumulative stress over gaps
            if plant.last_date is not None and date > plant.last_date:
                gap = (date - plant.last_date).days
                plant.stress_index *= (self.STRESS_DECAY_PER_DAY ** gap)
                plant.stress_streak = max(
                    0,
                    plant.stress_streak - gap * self.STREAK_RELIEF_PER_DAY
                )
            plant.last_date = date
            
            # Accumulate GDD
            plant.gdd += max(0.0, soil["soil_temp"] - self.GDD_BASE)
            
            # Stage transitions and senescence start
            for (etype, msg) in self._advance_pheno(plant, date):
                events.append({
                    "date": date,
                    "plant_id": pid,
                    "type": etype,
                    "message": msg,
                })
            
            # ================================================================
            # Stress, Lethal Events, and Cumulative Mortality
            # ================================================================
            
            # Stage-aware lethal freeze check (realistic pea cold tolerance)
            air_mean_today, air_min_today, air_max_today, _ = self._air_means(date)
            stage_key = "senescent" if plant.senescent else plant.stage
            lethal_temp = self.LETHAL_FREEZE_TEMPS.get(stage_key, self.LETHAL_FREEZE_GLOBAL)
            
            if air_min_today < lethal_temp:
                plant.dead = True
                events.append({
                    "date": date,
                    "plant_id": pid,
                    "type": "lethal_freeze",
                    "message": f"Plant killed by severe freeze ({air_min_today:.1f}°C, {plant.stage} stage lethal at {lethal_temp:.1f}°C)",
                    "suggested_health_delta": -9999,
                })
                continue
            
            # Legacy global lethal freeze (kept for compatibility)
            if delta <= -9999:
                plant.dead = True
                events.append({
                    "date": date,
                    "plant_id": pid,
                    "type": "lethal_freeze",
                    "message": "Plant killed by severe freeze",
                })
                continue
            
            # Stress events
            if note != "Normal":
                # Add ±10% variation to health delta for natural variation
                if delta != 0:
                    variation = 1.0 + (self.rng.random() * 0.2 - 0.1)  # 0.9 to 1.1
                    delta = int(delta * variation)
                
                # Immediate stress event
                events.append({
                    "date": date,
                    "plant_id": pid,
                    "type": "stress",
                    "message": note,
                    "suggested_health_delta": delta,
                })
                
                # Cumulative stress with stage-based multiplier
                base_w = self.STRESS_WEIGHT.get(note, 1.0)
                mult = self.STAGE_STRESS_MULT[
                    "senescent" if plant.senescent else plant.stage
                ]
                w = base_w * mult
                plant.stress_index += w
                plant.stress_streak += 1
                
                # Instead of instant death, apply severe health drain based on stress
                # Plants die naturally when health reaches 0
                if plant.stress_index >= self.STRESS_MORTALITY:
                    # Critical stress: severe health drain per day
                    stress_damage = -int(self.rng.randint(15, 25) * (1.0 + (self.rng.random() * 0.2 - 0.1)))
                    events.append({
                        "date": date,
                        "plant_id": pid,
                        "type": "critical_stress",
                        "message": f"Critical stress - plant failing (stress index: {plant.stress_index:.1f})",
                        "suggested_health_delta": stress_damage,
                    })
                elif plant.stress_streak >= self.STREAK_MORTALITY:
                    # Long stress streak: severe health drain
                    streak_damage = -int(self.rng.randint(12, 20) * (1.0 + (self.rng.random() * 0.2 - 0.1)))
                    events.append({
                        "date": date,
                        "plant_id": pid,
                        "type": "chronic_stress",
                        "message": f"Prolonged stress - plant deteriorating ({plant.stress_streak} days)",
                        "suggested_health_delta": streak_damage,
                    })
                elif plant.stress_index >= self.CHRONIC_ZONE:
                    # Chronic weakening (with variation)
                    slow = -int(self.rng.randint(2, 4) * (1.0 + (self.rng.random() * 0.2 - 0.1)))
                    events.append({
                        "date": date,
                        "plant_id": pid,
                        "type": "chronic_stress",
                        "message": "Chronic stress weakening the plant",
                        "suggested_health_delta": slow,
                    })
            else:
                # No active stress (no frost, no heat)
                # Decay stress over time
                plant.stress_streak = max(
                    0,
                    plant.stress_streak - self.STREAK_RELIEF_PER_DAY
                )
                plant.stress_index *= self.STRESS_DECAY_PER_DAY
                
                # Recovery only under truly favorable conditions
                loM, hiM = self.RECOVER_MOIST_RANGE
                loT, hiT = self.RECOVER_AIR_MEAN_C
                
                # Check all conditions for recovery:
                # 1. Optimal soil moisture (not too dry, not too wet)
                # 2. Optimal temperature range (not cold, not hot)
                # 3. Not senescent (old plants can't recover)
                # 4. Low stress index (below chronic threshold)
                moisture_ok = loM <= self.soil_moisture <= hiM
                temp_ok = loT <= air_mean <= hiT
                not_senescent = not plant.senescent
                stress_low = plant.stress_index < self.CHRONIC_ZONE
                
                # Additional checks for marginal conditions
                # Temperatures close to freezing (0-5°C) = too cold to recover
                too_cold = air_mean < 5.0
                # Soil too dry (< 0.3) or too wet (> 0.9) = stress persists
                soil_stress = self.soil_moisture < 0.3 or self.soil_moisture > 0.9
                
                # Recovery only if ALL conditions are good
                if (moisture_ok and temp_ok and not_senescent and stress_low 
                    and not too_cold and not soil_stress):
                    events.append({
                        "date": date,
                        "plant_id": pid,
                        "type": "recovery",
                        "message": "Favorable conditions – plant recovering",
                        "suggested_health_delta": 0,
                    })
            
            # Senescence daily decay (with ±10% variation for natural feel)
            if plant.senescent and not plant.dead:
                base_decay = -self.rng.randint(*self.SENESCENCE_DECAY)
                variation = 1.0 + (self.rng.random() * 0.2 - 0.1)  # 0.9 to 1.1
                sen_decay = int(base_decay * variation)
                events.append({
                    "date": date,
                    "plant_id": pid,
                    "type": "senescent_tick",
                    "message": "Natural senescence",
                    "suggested_health_delta": sen_decay,
                })
        
        return events
