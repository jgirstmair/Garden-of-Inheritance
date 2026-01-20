# ==== Mendel Climate v2 (single-file embed) ================================
# Reads CSVs and produces hourly temps + daily events consistent with Mendel's tables.
# Required CSVs (paths relative to this script or absolute):
#   - mendel_monthly_6_14_22.csv
#   - mendel_5day_means_actual.csv
#   - mendel_monthly_cloudiness.csv
#   - mendel_monthly_rain.csv
#   - mendel_monthly_snow_days.csv
#   - mendel_monthly_thunder_days.csv
#   - mendel_monthly_hail_days.csv
#   - mendel_frost_window.csv

import csv
import datetime as dt
import math
import random



CLIMATE_MODE = "historical"
# Global climate mode switch:
#   "stochastic" → legacy behaviour with AR(1) anomaly noise
#   "historical" → no AR(1) noise; temperatures follow CSV climatology smoothly
# Start with historical climate by default

class MendelClimate:
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
        # Mode selection (falls back to global CLIMATE_MODE if not explicitly given)
        self.mode = str(mode or CLIMATE_MODE).lower().strip()

        self.monthly = self._load_monthly(monthly_csv)
        # Optional year-resolved monthly anchors (per-year 06/14/22°C)
        self.yearly_monthly, self.yearly_years = self._load_yearly_monthly("climate/mendel_yearly_monthly_6_14_22.csv")

        self.five = self._load_five(five_day_csv)
        self.cloud = self._load_month_scalar(cloud_csv, "cloud_mean_0_10", default=5.0)
        self.rain = self._load_rain(rain_csv)
        self.snow = self._load_month_scalar(snow_csv, "snow_days", default=0.0)
        self.thunder = self._load_month_scalar(thunder_csv, "thunder_days", default=0.0)
        self.hail = self._load_month_scalar(hail_csv, "hail_days", default=0.0)
        self.frost = self._load_frost(frost_csv)

        # AR(1) anomaly state (used only in stochastic mode)
        self.anom_last = 0.0
        self.phi = 0.6
        self.sigma = 1.8
        self.rng = random.Random(seed)

        self.clear_amp = 1.0
        self.overcast_amp = 0.5
        self.cloud_scale = 10.0

    def _lerp(self, a,b,t): return a + (b-a)*t
    def _clamp(self, x,a,b): return a if x<a else b if x>b else x

    def _load_monthly(self, path):
            out = {}
            with open(path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    m = int(row["month"])
                    def p(x):
                        try: return float(str(x).replace(",", "."))
                        except: return None
                    out[m] = (p(row["T06_C"]), p(row["T14_C"]), p(row["T22_C"]))
            return out



    def _load_yearly_monthly(self, path):
            """Load year-resolved monthly 06/14/22°C anchors, if available.
            Returns (data, years) where data[(year,month)] = (T06,T14,T22)
            and years is a sorted list of unique years.
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
                        def p(x):
                            try:
                                return float(str(x).replace(",", "."))
                            except Exception:
                                return None
                        data[(y, m)] = (p(row.get("T06_C")), p(row.get("T14_C")), p(row.get("T22_C")))
                        years.append(y)
            except FileNotFoundError:
                return {}, []
            years_sorted = sorted(set(years))
            return data, years_sorted

    def _load_five(self, path):
            recs = []
            with open(path, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    def p(x):
                        try: return float(str(x).replace(",", "."))
                        except: return None
                    recs.append((int(row["start_day_of_year"]), int(row["end_day_of_year"]), p(row["mean_temp_C"])))
            # fill missing values forward/backward, default 10°C
            last=None
            for i,(s,e,t) in enumerate(recs):
                if t is None and last is not None: recs[i]=(s,e,last)
                elif t is not None: last=t
            last=None
            for i in range(len(recs)-1,-1,-1):
                s,e,t = recs[i]
                if t is None and last is not None: recs[i]=(s,e,last)
                elif t is not None: last=t
            recs = [(s,e,(t if t is not None else 10.0)) for (s,e,t) in recs]
            return recs


    def _load_month_scalar(self, path, key, default):
            out = {m: default for m in range(1,13)}
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        try: out[int(row["month"])] = float(str(row[key]).replace(",", "."))
                        except: pass
            except FileNotFoundError:
                pass
            return out


    def _load_rain(self, path):
            out = {m:(0.0,0.0) for m in range(1,13)}
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        def p(x):
                            try: return float(str(x).replace(",", "."))
                            except: return 0.0
                        out[int(row["month"])] = (p(row["rain_mm_total"]), p(row["rain_days"]))
            except FileNotFoundError:
                pass
            return out


    def _load_frost(self, path):
            out = {}
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for row in csv.DictReader(f):
                        y = int(row["year"])
                        def p(x):
                            try: return int(x)
                            except: return None
                        out[y] = (p(row["last_spring_frost_day"]), p(row["first_autumn_frost_day"]))
            except FileNotFoundError:
                pass
            return out

        # ----- helpers

    # ----- helpers ----------------------------------------------------------
    def _anchors_for_date(self, date, year_like=None):
        """Return (T06,T14,T22) anchors for this date.

        In historical mode, if year-resolved monthly data is available,
        we use the specific year (year_like or date.year, clamped to the
        available range). Otherwise we fall back to climatological monthly
        means (self.monthly).
        """
        m = date.month
        # Decide which year to use for year-resolved data
        y = year_like if year_like is not None else date.year
        use_yearly = (
            getattr(self, "mode", "stochastic") == "historical"
            and getattr(self, "yearly_monthly", None)
        )
        cur = nxt = None
        if use_yearly and getattr(self, "yearly_years", None):
            years = self.yearly_years
            if years:
                # Clamp requested year into available range
                if y < years[0]:
                    y_eff = years[0]
                elif y > years[-1]:
                    y_eff = years[-1]
                else:
                    y_eff = y
            else:
                y_eff = y
            # Current month
            cur = self.yearly_monthly.get((y_eff, m))
            # Next month (may roll to next year)
            nm = 1 if m == 12 else m + 1
            ny = y_eff + 1 if m == 12 else y_eff
            nxt = self.yearly_monthly.get((ny, nm))
        # Fallback: climatological monthly anchors
        if cur is None:
            cur = self.monthly.get(m, (6.0, 18.0, 12.0))
        if nxt is None:
            nm = 1 if m == 12 else m + 1
            nxt = self.monthly.get(nm, cur)
        dim = (dt.date(date.year + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
               - dt.date(date.year, m, 1)).days
        t = (date.day - 1) / max(1, dim - 1)
        return tuple(self._lerp(cur[i], nxt[i], t) for i in range(3))

    def _daily_mean_from_5day(self, date):
        doy = date.timetuple().tm_yday
        for s, e, t in self.five:
            if s <= doy <= e:
                return t
        return 10.0

    def _piecewise_cosine(self, t0, T0, t1, T1, hours):
        span = (t1 - t0)
        for k, h in enumerate(range(t0, t1)):
            x = k / max(1, span - 1)
            hours[h % 24] = T0 + (T1 - T0) * (1 - math.cos(math.pi * x)) / 2.0

    def _hourly_from_three_anchors(self, T06, T14, T22, next_T06, amp_scale=1.0):
        hours = [0.0] * 24
        self._piecewise_cosine(6, T06, 14, T14, hours)
        self._piecewise_cosine(14, T14, 22, T22, hours)
        seg = [0.0] * 8
        for k in range(8):
            x = k / 7.0
            seg[k] = T22 + (next_T06 - T22) * (1 - math.cos(math.pi * x)) / 2.0
        hours[22], hours[23] = seg[0], seg[1]
        for i in range(0, 6):
            hours[i] = seg[i + 2]
        mean0 = sum(hours) / 24.0
        hours = [mean0 + (h - mean0) * amp_scale for h in hours]
        return hours


    # ----- API --------------------------------------------------------------
    def daily_state(self, date, year_like=None):
        DEBUG_TEMPS = False  # set True to log 24h targets per day

        # Cloudiness → diurnal amplitude scaling
        cloud = self.cloud.get(date.month, 5.0)
        clear_frac = self._clamp(1.0 - cloud/10.0, 0.0, 1.0)
        amp = self.overcast_amp + (self.clear_amp - self.overcast_amp) * clear_frac

        # Base hourly curve from 06/14/22 °C anchors + next-day 06 °C
        T06, T14, T22 = self._anchors_for_date(date, year_like=year_like)
        next_T06 = self._anchors_for_date(date + dt.timedelta(days=1), year_like=year_like)[0]
        hours = self._hourly_from_three_anchors(T06, T14, T22, next_T06, amp_scale=amp)

        # Gently nudge toward Mendel's 5‑day mean climatology
        target = self._daily_mean_from_5day(date)
        meanH = sum(hours) / 24.0
        offset = target - meanH
        # Blend anchors with 5‑day climatology (0 = pure anchors, 1 = pure 5‑day)
        blend = 0.05
        hours = [h + offset * blend for h in hours]

        # Enforce a minimum realistic diurnal amplitude
        meanH = sum(hours) / 24.0
        m = date.month
        if m in (12, 1, 2):
            _min_amp = 2.5
        elif m in (3, 4, 10, 11):
            _min_amp = 4.0
        else:
            _min_amp = 6.0
        amp_now = max(hours) - min(hours)
        if amp_now > 0 and amp_now < _min_amp:
            gain = max(1.25, _min_amp / max(0.001, amp_now))
            hours = [meanH + (h - meanH) * gain for h in hours]

        # Optional AR(1) anomaly only in stochastic mode
        if self.mode != "historical":
            shock = self.rng.gauss(0.0, self.sigma)
            self.anom_last = self.phi * self.anom_last + (1 - self.phi) * shock
            hours = [h + self.anom_last for h in hours]

        # --- Precipitation & discrete events --------------------------------
        m = date.month
        rain_mm_total, rain_days = self.rain.get(m, (0.0, 0.0))
        # days in month
        if m == 12:
            dim = (dt.date(date.year + 1, 1, 1) - dt.date(date.year, m, 1)).days
        else:
            dim = (dt.date(date.year, m + 1, 1) - dt.date(date.year, m, 1)).days

        # Rain days: seeded RNG per (year,month) → deterministic per run
        self.rng.seed((date.year * 100 + m))
        rainy_set = set(self.rng.sample(range(1, dim + 1), k=min(int(round(rain_days)), dim)) if rain_days > 0 else [])
        rainy_today = date.day in rainy_set
        intensity = 0.0
        if rainy_today and rain_days > 0:
            mean_int = rain_mm_total / max(1.0, rain_days)
            intensity = mean_int * (0.5 + self.rng.random())

        # Snow days from monthly counts
        snow_days = int(round(self.snow.get(m, 0.0)))
        self.rng.seed((9999 + date.year * 100 + m))
        snow_set = set(self.rng.sample(range(1, dim + 1), k=min(snow_days, dim)) if snow_days > 0 else [])
        snow_today = date.day in snow_set

        # Thunder & hail
        thunder_days = int(round(self.thunder.get(m, 0.0)))
        hail_days = int(round(self.hail.get(m, 0.0)))
        self.rng.seed((4444 + date.year * 100 + m))
        th_set = set(self.rng.sample(range(1, dim + 1), k=min(thunder_days, dim)) if thunder_days > 0 else [])
        self.rng.seed((5555 + date.year * 100 + m))
        hail_set = set(self.rng.sample(range(1, dim + 1), k=min(hail_days, dim)) if hail_days > 0 else [])
        thunder_today = date.day in th_set
        hail_today = date.day in hail_set

        # --- Temperature‑based physical constraints -------------------------
        t_mean = sum(hours) / 24.0
        t_min = min(hours)

        # Simple snow gate: prevent snow on clearly warm days
        # Allow marginal slushy cases (slightly > 0°C mean / min), but not e.g. 7°C.
        if snow_today and (t_mean > 3.0 and t_min > 0.5):
            snow_today = False

        # Temperature-based sanity for rain at cold temperatures:
        # If it's clearly below freezing (mean < -1°C), plain rain is unlikely.
        # Convert such "rain days" into snow days instead.
        if rainy_today and t_mean < -1.0:
            rainy_today = False
            if not snow_today:
                snow_today = True

        # Frost season flag from precomputed window
        last_spring, first_autumn = self._frost_window(date.year if year_like is None else year_like)
        in_frost_season = not (last_spring < date.timetuple().tm_yday < first_autumn)

        if DEBUG_TEMPS and not hasattr(self, "_logged_dates"):
            self._logged_dates = set()
        if DEBUG_TEMPS and date not in self._logged_dates:
            try:
                print(f"[climate] {date.isoformat()} hours:",
                      ", ".join(f"{x:.1f}" for x in hours),
                      f" t_mean={t_mean:.1f} t_min={t_min:.1f} snow_today={snow_today}")
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
        return self.daily_state(date)["hours"]

    def _frost_window(self, year):
        rec = self.frost.get(year)
        if rec and all(rec):
            return rec
        return (122, 286)

# ==== end Mendel Climate v2 embed =========================================

