import datetime as dt
import math
import random
from typing import List

from mendelclimate import MendelClimate
from plant import Plant

BRNO_LAT = 49.1951
BRNO_LON = 16.6068

PHASES = ("morning", "noon", "afternoon", "evening")
PHASE_DISPLAY = {
    "morning":  "🌅 Morning",
    "noon":     "🌞 Noon",
    "afternoon":"🌤 Afternoon",
    "evening":  "🌆 Evening",
}
WEATHER_SYMBOLS = ("☀️", "⛅", "☁️", "🌧", "⛈")
WEATHER_WEIGHTS  = (0.45, 0.25, 0.15, 0.12, 0.03)

class GardenEnvironment:
    def __init__(self, size):
            self.plants: set[Plant] = set()
            self.day = 1
            self.phase_index = 0
            self.weather = random.choices(WEATHER_SYMBOLS, weights=WEATHER_WEIGHTS)[0]

            # Temperature model
            self.temp = 12.0
            self.target_temps = self._generate_day_temperatures()
            self.temp_updates_remaining = 3
            # Calendar & Clock
            self.year = 1856
            self.month = 4
            self.day_of_month = 1
            self._month_lengths = [31,28,31,30,31,30,31,31,30,31,30,31]
            self.clock_hour = 6

    def _recompute_weather_for_date(self, sim_date, hour=None, prev_icon=None, stickiness=0.75):
        """Hourly MendelClimate v2 weather with temp-aware bias and persistence. Precip overrides apply."""
        try:
            _key = (int(sim_date.toordinal()), int(hour) if hour is not None else -1)
            if getattr(self, "_last_weather_eval_key", None) == _key:
                return
            self._last_weather_eval_key = _key
        except Exception:
            pass

        # Climate singleton
        clim = globals().get("_CLIMATE_V2_SINGLETON", None)
        if clim is None:
            try:
                globals()["_CLIMATE_V2_SINGLETON"] = MendelClimate(
                    monthly_csv='climate/mendel_monthly_6_14_22.csv',
                    five_day_csv='climate/mendel_5day_means_actual.csv',
                    cloud_csv='climate/mendel_monthly_cloudiness.csv',
                    rain_csv='climate/mendel_monthly_rain.csv',
                    snow_csv='climate/mendel_monthly_snow_days.csv',
                    thunder_csv='climate/mendel_monthly_thunder_days.csv',
                    hail_csv='climate/mendel_monthly_hail_days.csv',
                    frost_csv='climate/mendel_frost_window.csv',
                    mode=globals().get("CLIMATE_MODE", "stochastic"),
                )
            except Exception:
                globals()["_CLIMATE_V2_SINGLETON"] = MendelClimate(mode=globals().get("CLIMATE_MODE", "stochastic"))
            clim = globals()["_CLIMATE_V2_SINGLETON"]

        st = clim.daily_state(sim_date)

        # ✅ define _slot BEFORE any use
        _slot = 0 if hour is None else int(hour) % 24

        # Precip overrides
        try:
            if st.get('rain_today'):
                self.weather = '⛈' if st.get('thunder_today') else '🌧'
                # optional: keep as-is; night adjust won’t change rain anyway
                self.weather = self._night_icon_adjust(self.weather, sim_date, _slot)
                return
            if st.get('snow_today'):
                self.weather = '❄️'
                self.weather = self._night_icon_adjust(self.weather, sim_date, _slot)
                return
        except Exception:
            pass

        # Cloud + temp bias
        try:
            c = st.get('cloud_0_10', 5.0)
        except Exception:
            c = 5.0
        _slot = 0 if hour is None else int(hour) % 24
        _rng = random.Random((int(sim_date.toordinal()) * 24 + _slot) ^ 0xA5F17D)
        try:
            hrs = st.get('hours') or []
            if isinstance(hrs, (list, tuple)) and len(hrs) == 24:
                t_hour = float(hrs[_slot]); t_mean = sum(hrs)/24.0
                bias = max(-1.0, min(1.0, (t_hour - t_mean) / 6.0))
            else:
                bias = 0.0
        except Exception:
            bias = 0.0
        if c < 3:
            w = [0.70, 0.30, 0.00]  # ☀️, ⛅, ☁️
        elif c < 5:
            w = [0.30, 0.60, 0.10]
        elif c < 7:
            w = [0.15, 0.55, 0.30]
        else:
            w = [0.05, 0.35, 0.60]
        try:
            boost = 0.25
            if bias > 0:
                w[0] += boost*bias; w[2] -= boost*bias
            elif bias < 0:
                w[2] += boost*(-bias); w[0] -= boost*(-bias)
            w = [max(0.0, min(1.0, x)) for x in w]
            ssum = sum(w) or 1.0
            w = [x/ssum for x in w]
        except Exception:
            pass
        cand = _rng.choices(['☀️','⛅','☁️'], weights=w)[0]

        try:
            if prev_icon in ('☀️','⛅','☁️','🌧','⛈','❄️'):
                c_adj = max(0.0, min(1.0, (c if isinstance(c,(int,float)) else 5.0)/10.0))
                p_stick = max(0.5, min(0.95, stickiness + 0.15*c_adj))
                if _rng.random() < p_stick:
                    self.weather = prev_icon
                    self.weather = self._night_icon_adjust(self.weather, sim_date, _slot)
                    return
        except Exception:
            pass

        self.weather = cand
        self.weather = self._night_icon_adjust(self.weather, sim_date, _slot)

    def _sync_phase(self):
        """Sync string phase & index from current clock_hour."""
        try:
            ph, idx = self._hour_to_phase(int(getattr(self, 'clock_hour', 6)))
            self.phase = ph
            self.phase_index = idx
        except Exception:
            try:
                self.phase = getattr(self, 'phase', 'morning')
                self.phase_index = getattr(self, 'phase_index', 0)
            except Exception:
                pass

    def _cal_advance_one_day(self):
        try:
            self.day_of_month += 1
            ml = self._month_lengths[self.month-1]
            if self.day_of_month > ml:
                self.day_of_month = 1
                self.month += 1
                if self.month > 12:
                    self.month = 1
                    self.year += 1
        except Exception:
            pass
        # Regenerate daily temperatures for the new date (v2 climate)
        try:
            tt = self._generate_day_temperatures()
            # If the method returns a dict, set target_temps and reset updates
            if isinstance(tt, dict):
                self.target_temps = tt
                self.temp_updates_remaining = 3
        except Exception:
            pass


    def _hour_to_phase(self, h):
        if 6 <= h < 11:
            return 'morning', 0
        if 11 <= h < 14:
            return 'noon', 1
        if 14 <= h < 18:
            return 'afternoon', 2
        if 18 <= h <= 22:
            return 'evening', 3
        return 'night', 0

    def next_hour(self):
        # Finish remaining temperature sub-updates so current hour reaches its target
        try:
            while getattr(self, 'temp_updates_remaining', 0) > 0:
                self.drift_temperature_once()
        except Exception:
            pass

        # Apply hourly updates to plants (water/health) using current weather & temperature
        for p in list(self.plants):
            if p.alive:
                try:
                    p.tick_hour(getattr(self, 'weather', '☀️'), float(getattr(self, 'temp', 15.0)))
                except Exception:
                    try:
                        p.tick_phase(getattr(self, 'weather', '☀️'))
                    except Exception:
                        pass
            else:
                self.unregister_plant(p)

        # Advance the clock by one hour
        try:
            self.clock_hour = (int(getattr(self, 'clock_hour', 6)) + 1) % 24
        except Exception:
            self.clock_hour = 6


        # Hourly weather recompute
        try:
            sim_date = dt.date(int(self.year), int(self.month), int(self.day_of_month))
            hh = int(getattr(self, 'clock_hour', 6)) % 24
            prev_icon = getattr(self, 'weather', None)
            self._recompute_weather_for_date(sim_date, hour=hh, prev_icon=prev_icon, stickiness=0.75)
            try:
                self._refresh_header()
            except Exception:
                try:
                    self.update_ui()
                except Exception:
                    pass
        except Exception:
            self.clock_hour = 6
        # Keep phase string/index in sync with the clock
        try:
            self._sync_phase()
        except Exception:
            pass

        # Midnight rollover: advance calendar, regenerate daily targets (which sets weather), and advance growth
        try:
            if int(self.clock_hour) == 0:
                # Advance calendar date
                try:
                    self._cal_advance_one_day()
                except Exception:
                    pass
                # Regenerate temperatures AND WEATHER for the new day
                try:
                    tt = self._generate_day_temperatures()
                    if isinstance(tt, dict):
                        self.target_temps = tt
                except Exception:
                    pass

                # Increment plant age and run growth progression
                for p in list(self.plants):
                    if p.alive:
                        p.days_since_planting = int(p.days_since_planting) + 1

                        # Lifespan & senescence checks
                        try:
                            max_age = int(p.max_age_days)
                            if int(p.days_since_planting) >= max(0, max_age - 10):
                                p.senescent = True
                                p.health = max(0, int(p.health) - 2)
                            if int(p.days_since_planting) >= max_age:
                                p.alive = False
                                p.health = 0
                                try:
                                    p.stage = max(int(p.stage), 7)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        try:
                            p.advance_growth()
                        except Exception:
                            pass
                    else:
                        self.unregister_plant(p)
        except Exception:
            pass

        # Reset sub-updates for the new hour and drift once for immediate visual feedback
        try:
            self.temp_updates_remaining = 3
        except Exception:
            pass
        try:
            self.drift_temperature_once()
        except Exception:
            pass

    def phase(self) -> str:
        return PHASES[self.phase_index]

    def _generate_day_temperatures(self):
        """
        Compute hourly temperatures and quick phase means using MendelClimate v2.
        Returns a dict with keys: 'hours', 'morning', 'noon', 'afternoon', 'evening'.
        """
        _year  = int(getattr(self, 'year', 1856))
        _month = int(getattr(self, 'month', 4))
        _dom   = int(getattr(self, 'day_of_month', 1))
        sim_date = dt.date(_year, _month, _dom)

        clim = globals().get('_CLIMATE_V2_SINGLETON', None)
        if clim is None:
            try:
                globals()['_CLIMATE_V2_SINGLETON'] = MendelClimate(
                    monthly_csv='climate/mendel_monthly_6_14_22.csv',
                    five_day_csv='climate/mendel_5day_means_actual.csv',
                    cloud_csv='climate/mendel_monthly_cloudiness.csv',
                    rain_csv='climate/mendel_monthly_rain.csv',
                    snow_csv='climate/mendel_monthly_snow_days.csv',
                    thunder_csv='climate/mendel_monthly_thunder_days.csv',
                    hail_csv='climate/mendel_monthly_hail_days.csv',
                    frost_csv='climate/mendel_frost_window.csv',
                    mode=globals().get("CLIMATE_MODE", "stochastic"),
                )
            except Exception:
                globals()['_CLIMATE_V2_SINGLETON'] = MendelClimate(mode=globals().get("CLIMATE_MODE", "stochastic"))
            clim = globals()['_CLIMATE_V2_SINGLETON']

        st = clim.daily_state(sim_date)
        hours = st.get('hours') or [15.0]*24

        out = {
            'hours': hours,
            'morning':   sum(hours[6:11]) / 5.0,
            'noon':      sum(hours[11:14]) / 3.0,
            'afternoon': sum(hours[14:18]) / 4.0,
            'evening':   sum(hours[18:23]) / 5.0,
        }

        try:
            prev_icon = getattr(self, 'weather', None)
            self._recompute_weather_for_date(sim_date, hour=0, prev_icon=prev_icon, stickiness=0.75)
        except Exception:
            pass

        return out
    def current_target_temp(self):
        tt = getattr(self, 'target_temps', {})
        # Use 24h targets when present
        if isinstance(tt, dict) and 'hours' in tt and isinstance(tt['hours'], (list, tuple)) and len(tt['hours']) == 24:
            try:
                return tt['hours'][int(getattr(self, 'clock_hour', 6)) % 24]
            except Exception:
                pass
        # Fallback to phase anchors
        try:
            return tt[getattr(self, 'phase', 'morning')]
        except Exception:
            return getattr(self, 'temp', 15.0)


    def drift_temperature_once(self):
        if self.temp_updates_remaining <= 0:
            return
        target = self.current_target_temp()
        self.temp += (target - self.temp) * 0.3
        self.temp_updates_remaining -= 1

    def water_all(self):
        """Water all living plants. Respects safe phases and rain.
        - Morning/Evening: safe watering
        - Noon/Afternoon: stress penalty applied per plant (via water_plant)
        - Rain: blocks manual watering (UI should message this)"""
        if self.weather in ("🌧", "⛈"):
            return "It's raining — manual watering not needed."
        count = 0
        for p in list(self.plants) if self.plants else []:
            if p.alive:
                p.water_plant(self.phase)
                count += 1
            else:
                self.unregister_plant(p)
        return f"Watered {count} plants."

    def water_all_safe(self):
        """Water all living plants safely (as if morning), even if current phase differs.
        Skips if it's raining.
        """
        if getattr(self, 'weather', None) in ("🌧", "⛈"):
            return "It's raining — manual watering not needed."
        count = 0
        for p in list(self.plants) if self.plants else []:
            if p.alive:
                p.water = min(100, p.water + 30)
                count += 1
            else:
                self.unregister_plant(p)
        return f"Watered {count} plants safely."

    def water_all_smart(self):
        """Top up plants to a safe target without entering stress bands.
        - Skip when raining.
        - Only water plants with water < 55.
        - Target 65 (max +30), and clamp to ≤70.
        Safe against set mutation when dead plants are removed.
        """
        if getattr(self, 'weather', None) in ("🌧", "⛈"):
            return "It's raining — skipping smart watering."

        count = 0
        # iterate over a snapshot so we can safely unregister plants during the loop
        for p in list(self.plants) if self.plants else []:
            if not getattr(p, "alive", True):
                self.unregister_plant(p)
                continue

            w = int(getattr(p, "water", 0))
            if w < 55:
                target = 65
                add = min(30, max(0, target - w))
                p.water = min(70, w + add)
                count += 1

        return f"Smart-watered {count} plants (to ≤70)."

    def next_phase(self):
        return self.next_hour()

    def _eu_dst_offset_hours(self, d: dt.date) -> int:
        """
        Approx EU DST rule:
        - DST starts last Sunday in March
        - DST ends last Sunday in October
        Returns 2 for CEST, 1 for CET.
        """
        def last_sunday(year, month):
            # last day of month
            if month == 12:
                last = dt.date(year, 12, 31)
            else:
                last = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            # weekday: Monday=0 ... Sunday=6
            return last - dt.timedelta(days=(last.weekday() + 1) % 7)

        start = last_sunday(d.year, 3)
        end = last_sunday(d.year, 10)
        return 2 if (d >= start and d < end) else 1

    def _sunrise_sunset_local_hours(self, date_: dt.date, lat=BRNO_LAT, lon=BRNO_LON) -> tuple[float, float]:
        """
        NOAA-style approximation.
        Returns (sunrise_hour_local, sunset_hour_local) in *local clock hours* (0..24).
        """
        # day of year
        n = date_.timetuple().tm_yday
        # fractional year (radians)
        gamma = 2.0 * math.pi / 365.0 * (n - 1)

        # equation of time (minutes)
        eqtime = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )

        # solar declination (radians)
        decl = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma)
            + 0.00148 * math.sin(3 * gamma)
        )

        lat_rad = math.radians(lat)

        # solar zenith for sunrise/sunset ~90.833°
        zenith = math.radians(90.833)

        # hour angle
        cos_ha = (math.cos(zenith) - math.sin(lat_rad) * math.sin(decl)) / (math.cos(lat_rad) * math.cos(decl))
        # clamp for polar-ish edge cases
        cos_ha = max(-1.0, min(1.0, cos_ha))
        ha = math.acos(cos_ha)  # radians

        ha_deg = math.degrees(ha)
        # solar noon in minutes (UTC-based)
        solar_noon_min = 720 - 4.0 * lon - eqtime

        sunrise_min_utc = solar_noon_min - 4.0 * ha_deg
        sunset_min_utc  = solar_noon_min + 4.0 * ha_deg

        # convert to local time
        tz = self._eu_dst_offset_hours(date_)
        sunrise_local = (sunrise_min_utc / 60.0) + tz
        sunset_local  = (sunset_min_utc / 60.0) + tz

        # normalize into 0..24
        sunrise_local %= 24.0
        sunset_local  %= 24.0
        return sunrise_local, sunset_local

    def _is_night_in_brno(self, sim_date, hour_float: float) -> bool:
        # sim_date might be dt.date already, or something date-like
        if hasattr(sim_date, "date"):
            d = sim_date.date()
        else:
            d = sim_date
        sr, ss = self._sunrise_sunset_local_hours(d)
        h = float(hour_float) % 24.0

        # Normal case: sunrise < sunset
        if sr < ss:
            return not (sr <= h < ss)
        # rare wrap-around case
        return (ss <= h < sr)

    def _night_icon_adjust(self, icon: str, sim_date, hour_float: float) -> str:
        if self._is_night_in_brno(sim_date, hour_float):
            if icon in ("☀️", "⛅"):
                return "🌙"
        return icon
    # Now there are two of them, this is getting out of hand...
    # def _night_icon_adjust(icon, sim_date, hour):
    #     hour = int(hour) % 24
    #     is_night = (hour < 6) or (hour >= 21)
    #     if is_night and icon in ("☀️","⛅"):
    #         return "🌙"
    #     return icon

    def register_plant(self, plant: Plant):
        self.plants.add(plant)

    def unregister_plant(self, plant: Plant):
        self.plants.discard(plant)