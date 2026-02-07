"""
Garden Environment Module

Manages the garden simulation environment including:
- Time progression (hourly/daily cycles)
- Weather simulation using MendelClimate
- Temperature modeling
- Plant lifecycle management
"""

import datetime as dt
import math
import random
from typing import List, Set

from mendelclimate import MendelClimate
from plant import Plant


# ============================================================================
# Constants
# ============================================================================

# Brno, Czech Republic coordinates (Mendel's monastery)
BRNO_LAT = 49.1951
BRNO_LON = 16.6068

# Time phases
PHASES = ("morning", "noon", "afternoon", "evening")
PHASE_DISPLAY = {
    "morning": "🌅 Morning",
    "noon": "🌞 Noon",
    "afternoon": "🌤 Afternoon",
    "evening": "🌆 Evening",
}

# Weather symbols and their base probabilities
WEATHER_SYMBOLS = ("☀️", "⛅", "☁️", "🌧", "⛈")
WEATHER_WEIGHTS = (0.45, 0.25, 0.15, 0.12, 0.03)


# ============================================================================
# Garden Environment
# ============================================================================

class GardenEnvironment:
    """
    Manages the garden simulation environment.
    
    Tracks time, weather, temperature, and registered plants.
    Handles hourly and daily progression of simulation.
    """
    
    def __init__(self, size):
        """
        Initialize the garden environment.
        
        Args:
            size: Garden grid size (not directly used by environment)
        """
        # Plant registry
        self.plants: Set[Plant] = set()
        
        # Time tracking
        self.day = 1
        self.phase_index = 0
        self.phase = PHASES[0]
        self.clock_hour = 6
        
        # Calendar
        self.year = 1856
        self.month = 4
        self.day_of_month = 1
        self._month_lengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        
        # Weather
        self.weather = random.choices(WEATHER_SYMBOLS, weights=WEATHER_WEIGHTS)[0]
        
        # Temperature
        self.temp = 12.0
        self.target_temps = self._generate_day_temperatures()
        self.temp_updates_remaining = 3
        
        # Weather evaluation cache (prevent duplicate work)
        self._last_weather_eval_key = None
    
    # ========================================================================
    # Plant Management
    # ========================================================================
    
    def register_plant(self, plant: Plant):
        """Add a plant to the environment registry."""
        self.plants.add(plant)
    
    def unregister_plant(self, plant: Plant):
        """Remove a plant from the environment registry."""
        self.plants.discard(plant)
    
    # ========================================================================
    # Time Progression
    # ========================================================================
    
    def next_hour(self):
        """
        Advance simulation by one hour.
        
        Handles:
        - Temperature convergence to target
        - Plant hourly updates (water evaporation, health)
        - Clock advancement
        - Weather updates
        - Midnight rollover (day change, growth)
        """
        # Finish temperature convergence for current hour
        try:
            while getattr(self, 'temp_updates_remaining', 0) > 0:
                self.drift_temperature_once()
        except Exception:
            pass
        
        # Update all living plants
        for plant in list(self.plants):
            if plant.alive:
                try:
                    plant.tick_hour(
                        getattr(self, 'weather', '☀️'),
                        float(getattr(self, 'temp', 15.0))
                    )
                except Exception:
                    # Fallback to phase-based update
                    try:
                        plant.tick_phase(getattr(self, 'weather', '☀️'))
                    except Exception:
                        pass
            else:
                self.unregister_plant(plant)
        
        # Advance clock
        try:
            self.clock_hour = (int(getattr(self, 'clock_hour', 6)) + 1) % 24
        except Exception:
            self.clock_hour = 6
        
        # Update weather for new hour
        try:
            sim_date = dt.date(
                int(self.year),
                int(self.month),
                int(self.day_of_month)
            )
            hour = int(getattr(self, 'clock_hour', 6)) % 24
            prev_icon = getattr(self, 'weather', None)
            
            self._recompute_weather_for_date(
                sim_date,
                hour=hour,
                prev_icon=prev_icon,
                stickiness=0.75
            )
        except Exception:
            pass
        
        # Refresh UI (if available)
        try:
            self._refresh_header()
        except Exception:
            try:
                self.update_ui()
            except Exception:
                pass
        
        # Sync phase from clock
        try:
            self._sync_phase()
        except Exception:
            pass
        
        # Midnight rollover
        if int(self.clock_hour) == 0:
            self._handle_midnight_rollover()
        
        # Reset temperature updates and apply first drift
        try:
            self.temp_updates_remaining = 3
            self.drift_temperature_once()
        except Exception:
            pass
    
    def _handle_midnight_rollover(self):
        """Handle day change at midnight."""
        # Advance calendar
        try:
            self._cal_advance_one_day()
        except Exception:
            pass
        
        # Regenerate temperatures and weather for new day
        try:
            temps = self._generate_day_temperatures()
            if isinstance(temps, dict):
                self.target_temps = temps
        except Exception:
            pass
        
        # Update all plants for new day
        for plant in list(self.plants):
            if plant.alive:
                # Age the plant
                plant.days_since_planting = int(plant.days_since_planting) + 1
                
                # Check senescence and lifespan
                try:
                    max_age = int(plant.max_age_days)
                    age = int(plant.days_since_planting)
                    
                    # Senescence starts 10 days before max age
                    if age >= max(0, max_age - 10):
                        plant.senescent = True
                        
                        # Only apply garden.py senescence decline in casual mode
                        # (overlay/enforce modes use pea_season_model.py for senescence)
                        try:
                            app = getattr(self, '_app', None)
                            season_mode = str(getattr(app, '_season_mode', 'off')) if app else 'off'
                        except:
                            season_mode = 'off'
                        
                        if season_mode == 'off':
                            # Gradual health decline with some variation (±10%)
                            import random
                            base_decline = 2
                            variation = random.uniform(0.9, 1.1)
                            decline = int(base_decline * variation)
                            plant.health = max(0, int(plant.health) - decline)
                    
                    # At max age, accelerate health decline instead of instant death
                    if age >= max_age:
                        # Severe health decline for plants that lived too long
                        import random
                        severe_decline = random.randint(8, 15)
                        plant.health = max(0, int(plant.health) - severe_decline)
                        
                        # Only die when health reaches 0 (natural death)
                        if plant.health <= 0:
                            plant.alive = False
                            try:
                                plant.stage = max(int(plant.stage), 7)
                            except Exception:
                                pass
                except Exception:
                    pass
                
                # Advance growth stage (may advance multiple stages if far enough)
                try:
                    # Keep advancing while possible (handles skipped days/fast forward)
                    max_iterations = 10  # Safety limit to prevent infinite loops
                    for _ in range(max_iterations):
                        old_stage = plant.stage
                        plant.advance_growth()
                        if plant.stage == old_stage or plant.stage >= 7:
                            break  # No advancement or reached maturity
                except Exception:
                    pass
            else:
                self.unregister_plant(plant)
    
    def next_phase(self):
        """Legacy method: advance by one hour (same as next_hour)."""
        return self.next_hour()
    
    def _sync_phase(self):
        """Synchronize phase string and index from current clock hour."""
        try:
            phase_name, phase_idx = self._hour_to_phase(int(getattr(self, 'clock_hour', 6)))
            self.phase = phase_name
            self.phase_index = phase_idx
        except Exception:
            try:
                self.phase = getattr(self, 'phase', 'morning')
                self.phase_index = getattr(self, 'phase_index', 0)
            except Exception:
                pass
    
    def _hour_to_phase(self, hour: int):
        """
        Convert hour to phase name and index.
        
        Args:
            hour: Hour of day (0-23)
            
        Returns:
            Tuple of (phase_name, phase_index)
        """
        if 6 <= hour < 11:
            return 'morning', 0
        elif 11 <= hour < 14:
            return 'noon', 1
        elif 14 <= hour < 18:
            return 'afternoon', 2
        elif 18 <= hour <= 22:
            return 'evening', 3
        else:
            return 'night', 0
    
    def _cal_advance_one_day(self):
        """Advance the calendar by one day."""
        try:
            self.day_of_month += 1
            month_length = self._month_lengths[self.month - 1]
            
            if self.day_of_month > month_length:
                self.day_of_month = 1
                self.month += 1
                
                if self.month > 12:
                    self.month = 1
                    self.year += 1
        except Exception:
            pass
    
    # ========================================================================
    # Weather & Climate
    # ========================================================================
    
    def _recompute_weather_for_date(self, sim_date, hour=None, prev_icon=None, stickiness=0.75):
        """
        Compute weather using MendelClimate v2 with temperature-aware bias and persistence.
        
        Args:
            sim_date: Date to compute weather for
            hour: Hour of day (0-23) or None for daily
            prev_icon: Previous weather icon for persistence
            stickiness: Probability of weather persisting (0.0-1.0)
        """
        # Check cache to avoid duplicate evaluation
        try:
            cache_key = (int(sim_date.toordinal()), int(hour) if hour is not None else -1)
            if getattr(self, "_last_weather_eval_key", None) == cache_key:
                return
            self._last_weather_eval_key = cache_key
        except Exception:
            pass
        
        # Get or create climate singleton
        climate = globals().get("_CLIMATE_V2_SINGLETON", None)
        if climate is None:
            climate = self._init_climate_singleton()
        
        # Get daily state from climate model
        state = climate.daily_state(sim_date)
        
        # Determine time slot for hourly evaluation
        time_slot = 0 if hour is None else int(hour) % 24
        
        # Handle precipitation overrides
        try:
            if state.get('rain_today'):
                icon = '⛈' if state.get('thunder_today') else '🌧'
                self.weather = self._night_icon_adjust(icon, sim_date, time_slot)
                return
            
            if state.get('snow_today'):
                icon = '❄️'
                self.weather = self._night_icon_adjust(icon, sim_date, time_slot)
                return
        except Exception:
            pass
        
        # Compute weather from cloudiness and temperature
        cloudiness = state.get('cloud_0_10', 5.0)
        
        # Temperature bias (warmer hours → more sun, cooler → more clouds)
        temp_bias = self._compute_temperature_bias(state, time_slot)
        
        # Base weights from cloudiness
        if cloudiness < 3:
            weights = [0.70, 0.30, 0.00]  # ☀️, ⛅, ☁️
        elif cloudiness < 5:
            weights = [0.30, 0.60, 0.10]
        elif cloudiness < 7:
            weights = [0.15, 0.55, 0.30]
        else:
            weights = [0.05, 0.35, 0.60]
        
        # Apply temperature bias
        try:
            boost = 0.25
            if temp_bias > 0:
                weights[0] += boost * temp_bias
                weights[2] -= boost * temp_bias
            elif temp_bias < 0:
                weights[2] += boost * (-temp_bias)
                weights[0] -= boost * (-temp_bias)
            
            # Normalize weights
            weights = [max(0.0, min(1.0, w)) for w in weights]
            total = sum(weights) or 1.0
            weights = [w / total for w in weights]
        except Exception:
            pass
        
        # Deterministic RNG for this hour
        rng = random.Random((int(sim_date.toordinal()) * 24 + time_slot) ^ 0xA5F17D)
        candidate = rng.choices(['☀️', '⛅', '☁️'], weights=weights)[0]
        
        # Apply weather persistence (stickiness)
        try:
            if prev_icon in ('☀️', '⛅', '☁️', '🌧', '⛈', '❄️'):
                cloudiness_factor = max(0.0, min(1.0, cloudiness / 10.0))
                persistence = max(0.5, min(0.95, stickiness + 0.15 * cloudiness_factor))
                
                if rng.random() < persistence:
                    self.weather = self._night_icon_adjust(prev_icon, sim_date, time_slot)
                    return
        except Exception:
            pass
        
        # Use new candidate
        self.weather = self._night_icon_adjust(candidate, sim_date, time_slot)
    
    def _compute_temperature_bias(self, state, time_slot):
        """
        Compute temperature bias for weather selection.
        
        Warmer than average → bias toward sun
        Cooler than average → bias toward clouds
        
        Args:
            state: Climate state dictionary
            time_slot: Hour of day (0-23)
            
        Returns:
            Bias value (-1.0 to 1.0)
        """
        try:
            hours = state.get('hours') or []
            if isinstance(hours, (list, tuple)) and len(hours) == 24:
                temp_hour = float(hours[time_slot])
                temp_mean = sum(hours) / 24.0
                bias = max(-1.0, min(1.0, (temp_hour - temp_mean) / 6.0))
                return bias
        except Exception:
            pass
        return 0.0
    
    def _init_climate_singleton(self):
        """Initialize the MendelClimate singleton."""
        try:
            climate = MendelClimate(
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
            climate = MendelClimate(mode=globals().get("CLIMATE_MODE", "stochastic"))
        
        globals()["_CLIMATE_V2_SINGLETON"] = climate
        return climate
    
    # ========================================================================
    # Temperature Management
    # ========================================================================
    
    def _generate_day_temperatures(self):
        """
        Compute hourly temperatures and phase means using MendelClimate v2.
        
        Returns:
            Dictionary with keys: 'hours', 'morning', 'noon', 'afternoon', 'evening'
        """
        # Get current date
        year = int(getattr(self, 'year', 1856))
        month = int(getattr(self, 'month', 4))
        day = int(getattr(self, 'day_of_month', 1))
        sim_date = dt.date(year, month, day)
        
        # Get or create climate singleton
        climate = globals().get('_CLIMATE_V2_SINGLETON', None)
        if climate is None:
            climate = self._init_climate_singleton()
        
        # Get hourly temperatures from climate model
        state = climate.daily_state(sim_date)
        hours = state.get('hours') or [15.0] * 24
        
        # Compute phase averages
        result = {
            'hours': hours,
            'morning': sum(hours[6:11]) / 5.0,
            'noon': sum(hours[11:14]) / 3.0,
            'afternoon': sum(hours[14:18]) / 4.0,
            'evening': sum(hours[18:23]) / 5.0,
        }
        
        # Also update weather for the new day
        try:
            prev_icon = getattr(self, 'weather', None)
            self._recompute_weather_for_date(sim_date, hour=0, prev_icon=prev_icon, stickiness=0.75)
        except Exception:
            pass
        
        return result
    
    def current_target_temp(self):
        """
        Get target temperature for current time.
        
        Returns:
            Target temperature in °C
        """
        temps = getattr(self, 'target_temps', {})
        
        # Use hourly targets if available
        if isinstance(temps, dict) and 'hours' in temps:
            hours = temps['hours']
            if isinstance(hours, (list, tuple)) and len(hours) == 24:
                try:
                    return hours[int(getattr(self, 'clock_hour', 6)) % 24]
                except Exception:
                    pass
        
        # Fallback to phase anchors
        try:
            return temps[getattr(self, 'phase', 'morning')]
        except Exception:
            return getattr(self, 'temp', 15.0)
    
    def drift_temperature_once(self):
        """Apply one temperature drift step toward target."""
        if self.temp_updates_remaining <= 0:
            return
        
        target = self.current_target_temp()
        self.temp += (target - self.temp) * 0.3
        self.temp_updates_remaining -= 1
    
    # ========================================================================
    # Day/Night Cycle
    # ========================================================================
    
    def _eu_dst_offset_hours(self, date: dt.date) -> int:
        """
        Approximate EU Daylight Saving Time offset.
        
        DST rules:
        - Starts last Sunday in March
        - Ends last Sunday in October
        
        Args:
            date: Date to check
            
        Returns:
            2 for CEST (summer), 1 for CET (winter)
        """
        def last_sunday(year, month):
            # Find last day of month
            if month == 12:
                last_day = dt.date(year, 12, 31)
            else:
                last_day = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            
            # Find last Sunday (weekday: Monday=0, Sunday=6)
            return last_day - dt.timedelta(days=(last_day.weekday() + 1) % 7)
        
        dst_start = last_sunday(date.year, 3)
        dst_end = last_sunday(date.year, 10)
        
        return 2 if (date >= dst_start and date < dst_end) else 1
    
    def _sunrise_sunset_local_hours(self, date: dt.date, lat=BRNO_LAT, lon=BRNO_LON):
        """
        Calculate sunrise and sunset times using NOAA algorithm.
        
        Args:
            date: Date to calculate for
            lat: Latitude in degrees
            lon: Longitude in degrees
            
        Returns:
            Tuple of (sunrise_hour, sunset_hour) in local time (0-24)
        """
        # Day of year
        day_of_year = date.timetuple().tm_yday
        
        # Fractional year in radians
        gamma = 2.0 * math.pi / 365.0 * (day_of_year - 1)
        
        # Equation of time (minutes)
        eqtime = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )
        
        # Solar declination (radians)
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
        
        # Solar zenith for sunrise/sunset (~90.833°)
        zenith = math.radians(90.833)
        
        # Hour angle
        cos_ha = (math.cos(zenith) - math.sin(lat_rad) * math.sin(decl)) / (
            math.cos(lat_rad) * math.cos(decl)
        )
        # Clamp for polar edge cases
        cos_ha = max(-1.0, min(1.0, cos_ha))
        ha = math.acos(cos_ha)
        
        ha_deg = math.degrees(ha)
        
        # Solar noon (UTC minutes)
        solar_noon_min = 720 - 4.0 * lon - eqtime
        
        sunrise_min_utc = solar_noon_min - 4.0 * ha_deg
        sunset_min_utc = solar_noon_min + 4.0 * ha_deg
        
        # Convert to local time
        tz_offset = self._eu_dst_offset_hours(date)
        sunrise_local = (sunrise_min_utc / 60.0) + tz_offset
        sunset_local = (sunset_min_utc / 60.0) + tz_offset
        
        # Normalize to 0-24
        sunrise_local %= 24.0
        sunset_local %= 24.0
        
        return sunrise_local, sunset_local
    
    def _is_night_in_brno(self, sim_date, hour_float: float) -> bool:
        """
        Check if given hour is nighttime in Brno.
        
        Args:
            sim_date: Date to check
            hour_float: Hour of day (0-24, can be fractional)
            
        Returns:
            True if nighttime, False if daytime
        """
        # Handle date-like objects
        if hasattr(sim_date, "date"):
            date = sim_date.date()
        else:
            date = sim_date
        
        sunrise, sunset = self._sunrise_sunset_local_hours(date)
        hour = float(hour_float) % 24.0
        
        # Normal case: sunrise < sunset
        if sunrise < sunset:
            return not (sunrise <= hour < sunset)
        
        # Rare wrap-around case (polar regions)
        return (sunset <= hour < sunrise)
    
    def _night_icon_adjust(self, icon: str, sim_date, hour_float: float) -> str:
        """
        Adjust weather icon for nighttime display.
        
        Args:
            icon: Weather icon to potentially adjust
            sim_date: Current date
            hour_float: Current hour (0-24)
            
        Returns:
            Adjusted icon (🌙 for sun/partly cloudy at night)
        """
        if self._is_night_in_brno(sim_date, hour_float):
            if icon in ("☀️", "⛅"):
                return "🌙"
        return icon
    
    # ========================================================================
    # Watering Utilities
    # ========================================================================
    
    def water_all(self):
        """
        Water all living plants, respecting safe phases.
        
        - Morning/Evening: safe watering
        - Noon/Afternoon: stress penalty applied per plant
        - Rain: blocks manual watering
        
        Returns:
            Status message
        """
        if self.weather in ("🌧", "⛈"):
            return "It's raining — manual watering not needed."
        
        count = 0
        for plant in list(self.plants) if self.plants else []:
            if plant.alive:
                plant.water_plant(self.phase)
                count += 1
            else:
                self.unregister_plant(plant)
        
        return f"Watered {count} plants."
    
    def water_all_safe(self):
        """
        Water all living plants safely (as if morning), ignoring phase.
        Skips if raining.
        
        Returns:
            Status message
        """
        if getattr(self, 'weather', None) in ("🌧", "⛈"):
            return "It's raining — manual watering not needed."
        
        count = 0
        for plant in list(self.plants) if self.plants else []:
            if plant.alive:
                plant.water = min(100, plant.water + 30)
                count += 1
            else:
                self.unregister_plant(plant)
        
        return f"Watered {count} plants safely."
    
    def water_all_smart(self):
        """
        Smart watering: only water plants below safe threshold.
        
        - Skip when raining
        - Only water plants with water < 55
        - Target 65 (max +30), clamped to ≤70
        
        Returns:
            Status message
        """
        if getattr(self, 'weather', None) in ("🌧", "⛈"):
            return "It's raining — skipping smart watering."
        
        count = 0
        for plant in list(self.plants) if self.plants else []:
            if not getattr(plant, "alive", True):
                self.unregister_plant(plant)
                continue
            
            water_level = int(getattr(plant, "water", 0))
            if water_level < 55:
                target = 65
                amount = min(30, max(0, target - water_level))
                plant.water = min(70, water_level + amount)
                count += 1
        
        return f"Smart-watered {count} plants (to ≤70)."
