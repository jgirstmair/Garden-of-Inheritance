"""
Mendel Climate Module

Generates historically-accurate weather and temperature data based on Gregor Mendel's
meteorological observations from Brno, Czech Republic (1850s-1860s).

Features:
- Hourly temperature interpolation from daily anchors (06:00, 14:00, 22:00)
- Year-resolved and climatological temperature data
- Precipitation events (rain, snow, thunder, hail)
- Frost season windows
- Two modes: historical (smooth) and stochastic (with AR(1) noise)

Required CSV files:
- mendel_monthly_6_14_22.csv: Monthly temperature anchors
- mendel_5day_means_actual.csv: 5-day rolling mean temperatures
- mendel_monthly_cloudiness.csv: Monthly cloudiness averages
- mendel_monthly_rain.csv: Monthly rainfall totals and days
- mendel_monthly_snow_days.csv: Monthly snow day counts
- mendel_monthly_thunder_days.csv: Monthly thunder day counts
- mendel_monthly_hail_days.csv: Monthly hail day counts
- mendel_frost_window.csv: Annual frost season boundaries
"""

import csv
import datetime as dt
import math
import random


# ============================================================================
# Configuration
# ============================================================================

CLIMATE_MODE = "historical"
"""
Global climate mode switch:
- "historical": Smooth temperatures following CSV climatology (no noise)
- "stochastic": Legacy behavior with AR(1) anomaly noise
"""


# ============================================================================
# Mendel Climate System
# ============================================================================

class MendelClimate:
    """
    Historical weather simulation based on Mendel's meteorological data.
    
    Provides:
    - Hourly temperature curves
    - Daily precipitation events
    - Seasonal frost windows
    - Cloudiness and amplitude scaling
    """
    
    def __init__(
        self,
        monthly_csv="climate/mendel_monthly_6_14_22.csv",
        five_day_csv="climate/mendel_5day_means_actual.csv",
        cloud_csv="climate/mendel_monthly_cloudiness.csv",
        rain_csv="climate/mendel_monthly_rain.csv",
        snow_csv="climate/mendel_monthly_snow_days.csv",
        thunder_csv="climate/mendel_monthly_thunder_days.csv",
        hail_csv="climate/mendel_monthly_hail_days.csv",
        frost_csv="climate/mendel_frost_window.csv",
        seed=1865,
        mode=None,
    ):
        """
        Initialize the climate system.
        
        Args:
            monthly_csv: Path to monthly temperature anchors
            five_day_csv: Path to 5-day mean temperatures
            cloud_csv: Path to monthly cloudiness data
            rain_csv: Path to monthly rainfall data
            snow_csv: Path to monthly snow day counts
            thunder_csv: Path to monthly thunder day counts
            hail_csv: Path to monthly hail day counts
            frost_csv: Path to frost window boundaries
            seed: Random seed for deterministic generation
            mode: Climate mode ("historical" or "stochastic")
        """
        # Mode selection
        self.mode = str(mode or CLIMATE_MODE).lower().strip()
        
        # Load climate data
        self.monthly = self._load_monthly(monthly_csv)
        self.yearly_monthly, self.yearly_years = self._load_yearly_monthly(
            "climate/mendel_yearly_monthly_6_14_22.csv"
        )
        self.five = self._load_five(five_day_csv)
        self.cloud = self._load_month_scalar(cloud_csv, "cloud_mean_0_10", default=5.0)
        self.rain = self._load_rain(rain_csv)
        self.snow = self._load_month_scalar(snow_csv, "snow_days", default=0.0)
        self.thunder = self._load_month_scalar(thunder_csv, "thunder_days", default=0.0)
        self.hail = self._load_month_scalar(hail_csv, "hail_days", default=0.0)
        self.frost = self._load_frost(frost_csv)
        
        # AR(1) anomaly state (stochastic mode only)
        self.anom_last = 0.0
        self.phi = 0.6
        self.sigma = 1.8  # Original working value
        self.rng = random.Random(seed)
        
        # Amplitude scaling parameters
        self.clear_amp = 1.0
        self.overcast_amp = 0.5
        self.cloud_scale = 10.0
    
    # ========================================================================
    # Utility Methods
    # ========================================================================
    
    def _lerp(self, a, b, t):
        """Linear interpolation between a and b."""
        return a + (b - a) * t
    
    def _clamp(self, x, a, b):
        """Clamp x to range [a, b]."""
        return a if x < a else b if x > b else x
    
    # ========================================================================
    # CSV Data Loading
    # ========================================================================
    
    def _load_monthly(self, path):
        """
        Load monthly temperature anchors (06:00, 14:00, 22:00).
        
        Args:
            path: Path to CSV file
            
        Returns:
            Dict mapping month (1-12) to (T06, T14, T22) tuple
        """
        out = {}
        with open(path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                m = int(row["month"])
                
                def parse_float(x):
                    try:
                        return float(str(x).replace(",", "."))
                    except Exception:
                        return None
                
                out[m] = (
                    parse_float(row["T06_C"]),
                    parse_float(row["T14_C"]),
                    parse_float(row["T22_C"])
                )
        return out
    
    def _load_yearly_monthly(self, path):
        """
        Load year-resolved monthly temperature anchors.
        
        Args:
            path: Path to CSV file
            
        Returns:
            Tuple of (data dict, sorted years list)
            data[(year, month)] = (T06, T14, T22)
        """
        data = {}
        years = []
        
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    try:
                        y = int(row.get("year"))
                        m = int(row.get("month"))
                    except Exception:
                        continue
                    
                    def parse_float(x):
                        try:
                            return float(str(x).replace(",", "."))
                        except Exception:
                            return None
                    
                    data[(y, m)] = (
                        parse_float(row.get("T06_C")),
                        parse_float(row.get("T14_C")),
                        parse_float(row.get("T22_C"))
                    )
                    years.append(y)
        except FileNotFoundError:
            return {}, []
        
        years_sorted = sorted(set(years))
        return data, years_sorted
    
    def _load_five(self, path):
        """
        Load 5-day mean temperature climatology.
        
        Args:
            path: Path to CSV file
            
        Returns:
            List of (start_day, end_day, mean_temp) tuples
        """
        recs = []
        with open(path, "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                def parse_float(x):
                    try:
                        return float(str(x).replace(",", "."))
                    except Exception:
                        return None
                
                recs.append((
                    int(row["start_day_of_year"]),
                    int(row["end_day_of_year"]),
                    parse_float(row["mean_temp_C"])
                ))
        
        # Fill missing values with forward/backward propagation
        last = None
        for i, (s, e, t) in enumerate(recs):
            if t is None and last is not None:
                recs[i] = (s, e, last)
            elif t is not None:
                last = t
        
        last = None
        for i in range(len(recs) - 1, -1, -1):
            s, e, t = recs[i]
            if t is None and last is not None:
                recs[i] = (s, e, last)
            elif t is not None:
                last = t
        
        # Default to 10°C if still missing
        recs = [(s, e, (t if t is not None else 10.0)) for (s, e, t) in recs]
        return recs
    
    def _load_month_scalar(self, path, key, default):
        """
        Load a single scalar value per month.
        
        Args:
            path: Path to CSV file
            key: Column name to extract
            default: Default value if missing
            
        Returns:
            Dict mapping month (1-12) to scalar value
        """
        out = {m: default for m in range(1, 13)}
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    try:
                        out[int(row["month"])] = float(str(row[key]).replace(",", "."))
                    except Exception:
                        pass
        except FileNotFoundError:
            pass
        return out
    
    def _load_rain(self, path):
        """
        Load monthly rainfall data.
        
        Args:
            path: Path to CSV file
            
        Returns:
            Dict mapping month to (total_mm, rain_days) tuple
        """
        out = {m: (0.0, 0.0) for m in range(1, 13)}
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    def parse_float(x):
                        try:
                            return float(str(x).replace(",", "."))
                        except Exception:
                            return 0.0
                    
                    out[int(row["month"])] = (
                        parse_float(row["rain_mm_total"]),
                        parse_float(row["rain_days"])
                    )
        except FileNotFoundError:
            pass
        return out
    
    def _load_frost(self, path):
        """
        Load frost window boundaries.
        
        Args:
            path: Path to CSV file
            
        Returns:
            Dict mapping year to (last_spring_frost_day, first_autumn_frost_day)
        """
        out = {}
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    y = int(row["year"])
                    
                    def parse_int(x):
                        try:
                            return int(x)
                        except Exception:
                            return None
                    
                    out[y] = (
                        parse_int(row["last_spring_frost_day"]),
                        parse_int(row["first_autumn_frost_day"])
                    )
        except FileNotFoundError:
            pass
        return out
    
    # ========================================================================
    # Temperature Calculation Helpers
    # ========================================================================
    
    def _anchors_for_date(self, date, year_like=None):
        """
        Get temperature anchors (06:00, 14:00, 22:00) for a given date.
        
        In historical mode with year-resolved data available, uses the specific
        year's anchors. Otherwise falls back to climatological monthly means.
        
        Args:
            date: Date to get anchors for
            year_like: Optional year override for climatology
            
        Returns:
            Tuple of (T06, T14, T22) in °C
        """
        m = date.month
        y = year_like if year_like is not None else date.year
        
        # Check if we should use year-resolved data
        use_yearly = (
            getattr(self, "mode", "stochastic") == "historical"
            and getattr(self, "yearly_monthly", None)
        )
        
        # Initialize y_eff (effective year for lookups)
        y_eff = y
        
        cur = nxt = None
        if use_yearly and getattr(self, "yearly_years", None):
            years = self.yearly_years
            if years:
                # Clamp requested year to available range
                if y < years[0]:
                    y_eff = years[0]
                elif y > years[-1]:
                    y_eff = years[-1]
                else:
                    y_eff = y
            
            # Current month
            cur = self.yearly_monthly.get((y_eff, m))
            
            # Next month (may roll to next year)
            nm = 1 if m == 12 else m + 1
            ny = y_eff + 1 if m == 12 else y_eff
            nxt = self.yearly_monthly.get((ny, nm))
        
        # Fallback to climatological monthly anchors
        if cur is None:
            cur = self.monthly.get(m, (6.0, 18.0, 12.0))
        if nxt is None:
            nm = 1 if m == 12 else m + 1
            nxt = self.monthly.get(nm, cur)
        
        # Interpolate linearly through the month from current to next month
        # This creates smooth seasonal transitions
        if m == 12:
            dim = (dt.date(date.year + 1, 1, 1) - dt.date(date.year, m, 1)).days
        else:
            dim = (dt.date(date.year, m + 1, 1) - dt.date(date.year, m, 1)).days
        
        t = (date.day - 1) / max(1, dim - 1)
        return tuple(self._lerp(cur[i], nxt[i], t) for i in range(3))
    
    def _daily_mean_from_5day(self, date):
        """
        Get the 5-day climatological mean for a given date.
        
        Args:
            date: Date to lookup
            
        Returns:
            Mean temperature in °C (default 10.0)
        """
        doy = date.timetuple().tm_yday
        for s, e, t in self.five:
            if s <= doy <= e:
                return t
        return 10.0
    
    def _piecewise_cosine(self, t0, T0, t1, T1, hours):
        """
        Interpolate temperatures between two time points using cosine curve.
        
        Modifies hours list in-place.
        
        Args:
            t0: Start hour
            T0: Start temperature
            t1: End hour
            T1: End temperature
            hours: List to modify (24 elements)
        """
        span = t1 - t0
        for k, h in enumerate(range(t0, t1)):
            x = k / max(1, span - 1)
            hours[h % 24] = T0 + (T1 - T0) * (1 - math.cos(math.pi * x)) / 2.0
    
    def _hourly_from_three_anchors(self, T06, T14, T22, next_T06, amp_scale=1.0):
        """
        Generate 24 hourly temperatures from three daily anchors.
        
        Args:
            T06: Temperature at 06:00
            T14: Temperature at 14:00
            T22: Temperature at 22:00
            next_T06: Temperature at 06:00 next day
            amp_scale: Diurnal amplitude scaling factor
            
        Returns:
            List of 24 hourly temperatures (0-23)
        """
        hours = [0.0] * 24
        
        # Daytime: 06:00 -> 14:00 -> 22:00
        self._piecewise_cosine(6, T06, 14, T14, hours)
        self._piecewise_cosine(14, T14, 22, T22, hours)
        
        # Nighttime: 22:00 -> next 06:00
        seg = [0.0] * 8
        for k in range(8):
            x = k / 7.0
            seg[k] = T22 + (next_T06 - T22) * (1 - math.cos(math.pi * x)) / 2.0
        
        hours[22], hours[23] = seg[0], seg[1]
        for i in range(0, 6):
            hours[i] = seg[i + 2]
        
        # Apply amplitude scaling around the mean
        mean0 = sum(hours) / 24.0
        hours = [mean0 + (h - mean0) * amp_scale for h in hours]
        
        return hours
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    def daily_state(self, date, year_like=None):
        """
        Get complete weather state for a given date.
        
        Args:
            date: Date to generate weather for
            year_like: Optional year override for climatology
            
        Returns:
            Dict containing:
            - hours: List of 24 hourly temperatures
            - rain_mm: Rainfall intensity (mm)
            - rain_today: Whether it's raining
            - snow_today: Whether it's snowing
            - thunder_today: Whether there's thunder
            - hail_today: Whether there's hail
            - in_frost_season: Whether in frost season
            - amp_scale: Diurnal amplitude scale factor
            - cloud_0_10: Cloudiness (0-10 scale)
        """
        DEBUG_TEMPS = False  # Set True to log 24h targets per day
        
        # Cloudiness affects diurnal amplitude
        cloud = self.cloud.get(date.month, 5.0)
        clear_frac = self._clamp(1.0 - cloud / 10.0, 0.0, 1.0)
        amp = self.overcast_amp + (self.clear_amp - self.overcast_amp) * clear_frac
        
        # Generate base hourly curve from anchors
        T06, T14, T22 = self._anchors_for_date(date, year_like=year_like)
        next_date = date + dt.timedelta(days=1)
        next_T06 = self._anchors_for_date(next_date, year_like=year_like)[0]
        hours = self._hourly_from_three_anchors(T06, T14, T22, next_T06, amp_scale=amp)
        
        # No climatology nudging needed - we use Mendel's actual measurements
        # The natural variation comes from interpolation alone
        
        
        # Enforce minimum realistic diurnal amplitude
        meanH = sum(hours) / 24.0
        m = date.month
        if m in (12, 1, 2):
            min_amp = 2.5
        elif m in (3, 4, 10, 11):
            min_amp = 4.0
        else:
            min_amp = 6.0
        
        amp_now = max(hours) - min(hours)
        if amp_now > 0 and amp_now < min_amp:
            gain = max(1.25, min_amp / max(0.001, amp_now))
            hours = [meanH + (h - meanH) * gain for h in hours]
        
        # No stochastic anomaly needed - Mendel's data provides the baseline
        # Natural variation comes from smooth interpolation
        # if self.mode != "historical":
        #     shock = self.rng.gauss(0.0, self.sigma)
        #     self.anom_last = self.phi * self.anom_last + (1 - self.phi) * shock
        #     hours = [h + self.anom_last for h in hours]
        
        # ====================================================================
        # Precipitation and Discrete Events
        # ====================================================================
        
        m = date.month
        rain_mm_total, rain_days = self.rain.get(m, (0.0, 0.0))
        
        # Days in month
        if m == 12:
            dim = (dt.date(date.year + 1, 1, 1) - dt.date(date.year, m, 1)).days
        else:
            dim = (dt.date(date.year, m + 1, 1) - dt.date(date.year, m, 1)).days
        
        # Rain days (deterministic per run via seeded RNG)
        self.rng.seed((date.year * 100 + m))
        rainy_set = set(
            self.rng.sample(range(1, dim + 1), k=min(int(round(rain_days)), dim))
            if rain_days > 0 else []
        )
        rainy_today = date.day in rainy_set
        intensity = 0.0
        if rainy_today and rain_days > 0:
            mean_int = rain_mm_total / max(1.0, rain_days)
            intensity = mean_int * (0.5 + self.rng.random())
        
        # Snow days
        snow_days = int(round(self.snow.get(m, 0.0)))
        self.rng.seed((9999 + date.year * 100 + m))
        snow_set = set(
            self.rng.sample(range(1, dim + 1), k=min(snow_days, dim))
            if snow_days > 0 else []
        )
        snow_today = date.day in snow_set
        
        # Thunder and hail
        thunder_days = int(round(self.thunder.get(m, 0.0)))
        hail_days = int(round(self.hail.get(m, 0.0)))
        self.rng.seed((4444 + date.year * 100 + m))
        th_set = set(
            self.rng.sample(range(1, dim + 1), k=min(thunder_days, dim))
            if thunder_days > 0 else []
        )
        self.rng.seed((5555 + date.year * 100 + m))
        hail_set = set(
            self.rng.sample(range(1, dim + 1), k=min(hail_days, dim))
            if hail_days > 0 else []
        )
        thunder_today = date.day in th_set
        hail_today = date.day in hail_set
        
        # ====================================================================
        # Temperature-Based Physical Constraints
        # ====================================================================
        
        t_mean = sum(hours) / 24.0
        t_min = min(hours)
        
        # Prevent snow on clearly warm days
        if snow_today and (t_mean > 3.0 and t_min > 0.5):
            snow_today = False
        
        # Convert rain to snow at freezing temperatures
        if rainy_today and t_mean < -1.0:
            rainy_today = False
            if not snow_today:
                snow_today = True
        
        # Frost season flag
        last_spring, first_autumn = self._frost_window(
            date.year if year_like is None else year_like
        )
        in_frost_season = not (last_spring < date.timetuple().tm_yday < first_autumn)
        
        # Debug logging
        if DEBUG_TEMPS and not hasattr(self, "_logged_dates"):
            self._logged_dates = set()
        if DEBUG_TEMPS and date not in self._logged_dates:
            try:
                print(
                    f"[climate] {date.isoformat()} hours:",
                    ", ".join(f"{x:.1f}" for x in hours),
                    f" t_mean={t_mean:.1f} t_min={t_min:.1f} snow_today={snow_today}"
                )
            except Exception:
                pass
            self._logged_dates.add(date)
        
        return {
            "hours": hours,
            "rain_mm": intensity,
            "rain_today": rainy_today,
            "snow_today": snow_today,
            "thunder_today": thunder_today,
            "hail_today": hail_today,
            "in_frost_season": in_frost_season,
            "amp_scale": amp,
            "cloud_0_10": cloud,
        }
    
    def hourly_targets(self, date):
        """
        Get 24 hourly temperature targets for a given date.
        
        Args:
            date: Date to get temperatures for
            
        Returns:
            List of 24 hourly temperatures (0-23)
        """
        return self.daily_state(date)["hours"]
    
    def _frost_window(self, year):
        """
        Get frost season boundaries for a given year.
        
        Args:
            year: Year to lookup
            
        Returns:
            Tuple of (last_spring_frost_day, first_autumn_frost_day)
            Default: (122, 286) if not in data
        """
        rec = self.frost.get(year)
        if rec and all(rec):
            return rec
        return (122, 286)
