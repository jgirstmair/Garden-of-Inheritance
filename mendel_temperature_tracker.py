"""
Mendel Temperature Measurement - Classic Style (OPTIMIZED)

This version ensures reliable data saving and plotting for both simulation and modern measurements.

KEY FIXES:
1. All measurements now include 'month' and 'year' fields (required for plotting)
2. Data validation on load prevents malformed entries
3. Both simulation AND modern measurements appear on plot
4. Clear visual distinction: simulation (black borders), modern (red borders)
5. Console logging for debugging data flow

FONT SIZE ADJUSTMENT GUIDE:
Modify these constants to change all fonts at once:
"""

import tkinter as tk
from tkinter import ttk, messagebox, StringVar
import datetime as dt
import json
import os
from pathlib import Path
import csv

# === FONT SIZES - ADJUST THESE TO CHANGE ALL FONTS ===
FONT_TITLE = 14          # Main titles
FONT_HEADING = 12        # Section headings  
FONT_BODY = 11           # Regular text
FONT_SMALL = 10          # Secondary text
FONT_TEMP_DISPLAY = 20   # Large temperature display

# === COLOR SCHEME (from plot) ===
COLOR_MORNING = '#4A5F7A'        # Blue-gray
COLOR_AFTERNOON = '#8B4513'      # Saddle brown
COLOR_EVENING = '#2F4F4F'        # Dark slate gray
COLOR_BG_PARCHMENT = '#F5F3E8'   # Parchment background
COLOR_BG_LIGHT = '#FDFCF5'       # Light cream
COLOR_TEXT_PRIMARY = '#333333'   # Dark text
COLOR_TEXT_SECONDARY = '#666666' # Gray text
COLOR_BORDER = '#5D4E37'         # Dark brown
COLOR_SEPARATOR = '#DDDDDD'      # Light gray

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    Figure = None
    FigureCanvasTkAgg = None
    MATPLOTLIB_AVAILABLE = False

# Try to import scipy for smooth curves (optional)
try:
    from scipy.interpolate import make_interp_spline
    import numpy as np
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

class TemperatureTracker:
    """Temperature tracking following Mendel's schedule."""
    
    VALID_HOURS = [6, 14, 22]
    HOUR_NAMES = {6: "Morning", 14: "Afternoon", 22: "Evening"}
    
    def __init__(self, garden_env, data_dir="data", climate_csv="climate/mendel_yearly_monthly_6_14_22.csv"):
        self.garden_env = garden_env
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.measurements = []
        self.measurements_file = self.data_dir / "temperature_measurements.json"
        self.modern_measurements = []
        self.modern_measurements_file = self.data_dir / "modern_temperature_measurements.json"
        self.mendel_averages = self._load_averages(climate_csv)
        self._load_measurements()
        self._load_modern_measurements()
        self.window = None
    
    def _load_averages(self, path):
        """Load Mendel's 15-year averages."""
        if not os.path.exists(path):
            return {1:{6:-3.9,14:-0.5,22:-2.8},2:{6:-2.5,14:2.5,22:-0.9},3:{6:0.2,14:7.1,22:2.3},
                   4:{6:5.0,14:14.1,22:7.7},5:{6:9.9,14:19.1,22:12.2},6:{6:14.4,14:23.5,22:16.2},
                   7:{6:15.3,14:25.1,22:17.7},8:{6:14.9,14:24.0,22:17.3},9:{6:10.6,14:20.2,22:13.2},
                   10:{6:6.8,14:14.5,22:8.8},11:{6:1.7,14:5.4,22:2.7},12:{6:-2.4,14:0.5,22:-1.9}}
        
        try:
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                monthly_data = {}
                for row in reader:
                    m = int(row['month'])
                    if m not in monthly_data:
                        monthly_data[m] = {6:[],14:[],22:[]}
                    monthly_data[m][6].append(float(row['T06_C']))
                    monthly_data[m][14].append(float(row['T14_C']))
                    monthly_data[m][22].append(float(row['T22_C']))
                return {m: {h: sum(monthly_data[m][h])/len(monthly_data[m][h]) for h in [6,14,22]} 
                       for m in monthly_data}
        except:
            return {1:{6:-3.9,14:-0.5,22:-2.8},2:{6:-2.5,14:2.5,22:-0.9},3:{6:0.2,14:7.1,22:2.3},
                   4:{6:5.0,14:14.1,22:7.7},5:{6:9.9,14:19.1,22:12.2},6:{6:14.4,14:23.5,22:16.2},
                   7:{6:15.3,14:25.1,22:17.7},8:{6:14.9,14:24.0,22:17.3},9:{6:10.6,14:20.2,22:13.2},
                   10:{6:6.8,14:14.5,22:8.8},11:{6:1.7,14:5.4,22:2.7},12:{6:-2.4,14:0.5,22:-1.9}}
    
    def _load_measurements(self):
        """Load simulation measurements with data validation."""
        if self.measurements_file.exists():
            try:
                with open(self.measurements_file, 'r') as f:
                    loaded = json.load(f)
                    # Validate and fix each measurement
                    self.measurements = []
                    fixed_count = 0
                    for m in loaded:
                        # Ensure all required fields exist
                        if 'temperature' not in m or 'hour' not in m:
                            continue
                        
                        # Add month and year if missing (CRITICAL FIX)
                        if 'month' not in m or 'year' not in m:
                            try:
                                if 'date' in m:
                                    date_obj = dt.datetime.strptime(m['date'], "%Y-%m-%d")
                                    m['month'] = date_obj.month
                                    m['year'] = date_obj.year
                                    fixed_count += 1
                                else:
                                    continue  # Skip if we can't determine date
                            except:
                                continue
                        
                        self.measurements.append(m)
                    
                    # Save the validated data back if we fixed anything
                    if fixed_count > 0:
                        print(f"[VALIDATION] Fixed {fixed_count} simulation measurements missing month/year fields")
                        self._save_measurements()
                    
                    print(f"[LOAD] Loaded {len(self.measurements)} simulation measurements")
            except Exception as e:
                print(f"[ERROR] Failed to load measurements: {e}")
                self.measurements = []
        else:
            print("[LOAD] No existing simulation measurements file")
    
    def _save_measurements(self):
        """Save simulation measurements."""
        try:
            with open(self.measurements_file, 'w') as f:
                json.dump(self.measurements, f, indent=2)
            print(f"[SAVE] Saved {len(self.measurements)} simulation measurements")
        except Exception as e:
            print(f"[ERROR] Save error: {e}")
    
    def _load_modern_measurements(self):
        """Load modern-day measurements with data validation."""
        if self.modern_measurements_file.exists():
            try:
                with open(self.modern_measurements_file, 'r') as f:
                    loaded = json.load(f)
                    # Validate and fix each measurement
                    self.modern_measurements = []
                    fixed_count = 0
                    for m in loaded:
                        # Ensure all required fields exist
                        if 'temperature' not in m or 'hour' not in m:
                            continue
                        
                        # Add month and year if missing (CRITICAL FIX)
                        if 'month' not in m or 'year' not in m:
                            try:
                                if 'date' in m:
                                    date_obj = dt.datetime.strptime(m['date'], "%Y-%m-%d")
                                    m['month'] = date_obj.month
                                    m['year'] = date_obj.year
                                    fixed_count += 1
                                else:
                                    continue
                            except:
                                continue
                        
                        self.modern_measurements.append(m)
                    
                    # Save the validated data back if we fixed anything
                    if fixed_count > 0:
                        print(f"[VALIDATION] Fixed {fixed_count} modern measurements missing month/year fields")
                        self._save_modern_measurements()
                    
                    print(f"[LOAD] Loaded {len(self.modern_measurements)} modern measurements")
            except Exception as e:
                print(f"[ERROR] Failed to load modern measurements: {e}")
                self.modern_measurements = []
        else:
            print("[LOAD] No existing modern measurements file")
    
    def _save_modern_measurements(self):
        """Save modern-day measurements."""
        try:
            with open(self.modern_measurements_file, 'w') as f:
                json.dump(self.modern_measurements, f, indent=2)
            print(f"[SAVE] Saved {len(self.modern_measurements)} modern measurements")
        except Exception as e:
            print(f"[ERROR] Save error: {e}")
    
    def _get_datetime(self):
        try:
            if hasattr(self.garden_env, '_get_datetime'):
                return self.garden_env._get_datetime()
            return dt.datetime(
                getattr(self.garden_env, 'year', 1856),
                getattr(self.garden_env, 'month', 4),
                getattr(self.garden_env, 'day_of_month', 1),
                int(getattr(self.garden_env, 'clock_hour', 6)), 0)
        except:
            return dt.datetime(1856, 4, 1, 6, 0)
    
    def can_measure_now(self):
        if not self.garden_env:
            return False, None, "No environment"
        current_time = self._get_datetime()
        hour = current_time.hour
        if hour not in self.VALID_HOURS:
            next_h = min([h for h in self.VALID_HOURS if h > hour] + [self.VALID_HOURS[0]+24])
            if next_h >= 24: next_h -= 24
            return False, None, f"Next: {next_h:02d}:00"
        date_str = current_time.strftime("%Y-%m-%d")
        for m in self.measurements:
            if m['date'] == date_str and m['hour'] == hour:
                return False, hour, "Already measured"
        return True, hour, "Ready"
    
    def get_current_temperature(self):
        if not self.garden_env:
            return None
        try:
            if hasattr(self.garden_env, 'climate'):
                return round(self.garden_env.climate.get_temperature(self._get_datetime()), 1)
        except:
            pass
        try:
            temp = getattr(self.garden_env, 'temp', None)
            if temp: return round(float(temp), 1)
        except:
            pass
        return None
    
    def take_measurement(self):
        """Quick measurement - returns (success, message). ALWAYS includes month and year for plotting."""
        can, hour, reason = self.can_measure_now()
        if not can:
            return False, reason
        temp = self.get_current_temperature()
        if temp is None:
            return False, "No temperature"
        ct = self._get_datetime()
        exp = self.mendel_averages.get(ct.month, {}).get(hour)
        
        # Create measurement with ALL required fields for plotting
        measurement = {
            'date': ct.strftime("%Y-%m-%d"),
            'datetime': ct.strftime("%Y-%m-%d %H:%M"),
            'hour': hour,
            'temperature': temp,
            'month': ct.month,  # CRITICAL for plotting
            'year': ct.year,    # CRITICAL for plotting
            'is_simulation': True
        }
        
        self.measurements.append(measurement)
        self._save_measurements()
        
        print(f"[MEASUREMENT] Saved simulation: date={measurement['date']}, hour={hour}, temp={temp}°C, month={ct.month}")
        
        msg = f"Recorded: {temp}°C"
        if exp:
            dev = temp - exp
            msg += f" (avg: {exp:.1f}°C, {'+' if dev>0 else ''}{dev:.1f}°C)"
        return True, msg
    
    def open_observatory(self):
        """Open full window."""
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return
        
        self.window = tk.Toplevel()
        self.window.title("Meteorological Observatory")
        self.window.geometry("950x700")
        self.window.configure(bg=COLOR_BG_PARCHMENT)
        
        nb = ttk.Notebook(self.window)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Create tabs
        tab_record = tk.Frame(nb, bg="white")
        tab_history = tk.Frame(nb, bg="white")
        tab_plot = tk.Frame(nb, bg="white")
        tab_about = tk.Frame(nb, bg="white")
        
        nb.add(tab_record, text=" 📝 Record ")
        nb.add(tab_history, text=" 📊 History ")
        nb.add(tab_plot, text=" 📈 Plot ")
        nb.add(tab_about, text=" ℹ️ About ")
        
        self._tab_record_merged(tab_record)
        self._tab_history(tab_history)
        self._tab_plot(tab_plot)
        self._tab_about(tab_about)
        
        # Bind tab change event to refresh plot
        def on_tab_change(event):
            current_tab = event.widget.index("current")
            if current_tab == 2:  # Plot tab (0-indexed)
                self._tab_plot(tab_plot)
        
        nb.bind("<<NotebookTabChanged>>", on_tab_change)
    
    def _tab_measure(self, parent):
        c = tk.Canvas(parent, bg="white")
        sb = tk.Scrollbar(parent, orient="vertical", command=c.yview)
        s = tk.Frame(c, bg="white")
        s.bind("<Configure>", lambda e: c.configure(scrollregion=c.bbox("all")))
        c.create_window((0, 0), window=s, anchor="nw")
        c.configure(yscrollcommand=sb.set)
        
        tk.Label(s, text="Current Conditions", font=("Segoe UI",FONT_TITLE,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(20,15))
        
        info = tk.Frame(s, bg=COLOR_BG_LIGHT, highlightbackground=COLOR_BORDER, 
                       highlightthickness=2)
        info.pack(fill="x", padx=20, pady=(0,20))
        
        temp = self.get_current_temperature()
        ct = self._get_datetime()
        can, hour, reason = self.can_measure_now()
        
        tk.Label(info, text=f"{temp}°C" if temp else "—", 
                font=("Segoe UI",FONT_TEMP_DISPLAY,"bold"), bg=COLOR_BG_LIGHT, 
                fg=COLOR_TEXT_PRIMARY).pack(pady=(15,5))
        tk.Label(info, text=ct.strftime("%Y-%m-%d %H:%M"), 
                font=("Segoe UI",FONT_BODY), bg=COLOR_BG_LIGHT, 
                fg=COLOR_TEXT_SECONDARY).pack(pady=(0,15))
        
        tk.Label(s, text="Measurement Schedule", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(0,10))
        
        sched = tk.Frame(s, bg="white")
        sched.pack(fill="x", padx=20)
        for h in self.VALID_HOURS:
            f = tk.Frame(sched, bg=COLOR_BG_LIGHT, highlightbackground=COLOR_SEPARATOR, 
                        highlightthickness=1)
            f.pack(side="left", expand=True, fill="both", padx=5, pady=5)
            tk.Label(f, text=f"{h:02d}:00", font=("Segoe UI",FONT_BODY,"bold"), 
                    bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_PRIMARY).pack(pady=(8,2))
            tk.Label(f, text=self.HOUR_NAMES[h], font=("Segoe UI",FONT_SMALL), 
                    bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_SECONDARY).pack(pady=(0,8))
        
        tk.Label(s, text="Take Measurement", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(20,10))
        
        status = tk.Label(s, text="", font=("Segoe UI",FONT_BODY), bg="white")
        status.pack(padx=20, pady=(0,10))
        
        def do_measure():
            success, msg = self.take_measurement()
            status.config(text=msg, fg=COLOR_MORNING if success else "red")
            if success:
                self.window.after(2000, lambda: status.config(text=""))
        
        btn = tk.Button(s, text="📝 Take Measurement", font=("Segoe UI",FONT_BODY,"bold"), 
                       bg=COLOR_MORNING, fg="white", activebackground="#3A4F6A", 
                       command=do_measure, cursor="hand2", bd=0, padx=20, pady=10)
        btn.pack(pady=(0,20))
        
        if not can:
            tk.Label(s, text=f"Status: {reason}", font=("Segoe UI",FONT_BODY), 
                    bg="white", fg=COLOR_TEXT_SECONDARY).pack(pady=(0,20))
        
        c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
    
    def _tab_record_merged(self, parent):
        """Merged tab with simulation measurement on left and modern recording on right."""
        # Main container with two columns
        main_frame = tk.Frame(parent, bg="white")
        main_frame.pack(fill="both", expand=True)
        
        # Left column: Simulation measurement (from old Measure tab)
        left_col = tk.Frame(main_frame, bg="white", highlightbackground=COLOR_SEPARATOR, 
                           highlightthickness=1)
        left_col.pack(side="left", fill="both", expand=True, padx=(10,5), pady=10)
        
        # Right column: Modern recording (from old Record tab)
        right_col = tk.Frame(main_frame, bg="white", highlightbackground=COLOR_SEPARATOR, 
                            highlightthickness=1)
        right_col.pack(side="left", fill="both", expand=True, padx=(5,10), pady=10)
        
        # === LEFT: SIMULATION MEASUREMENT ===
        left_scroll = tk.Canvas(left_col, bg="white")
        left_sb = tk.Scrollbar(left_col, orient="vertical", command=left_scroll.yview)
        left_content = tk.Frame(left_scroll, bg="white")
        left_content.bind("<Configure>", lambda e: left_scroll.configure(scrollregion=left_scroll.bbox("all")))
        left_scroll.create_window((0, 0), window=left_content, anchor="nw")
        left_scroll.configure(yscrollcommand=left_sb.set)
        
        tk.Label(left_content, text="Simulation Recording", font=("Segoe UI",FONT_TITLE,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(15,10))
        
        tk.Label(left_content, text="Current Conditions", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(10,8))
        
        info = tk.Frame(left_content, bg=COLOR_BG_LIGHT, highlightbackground=COLOR_BORDER, 
                       highlightthickness=2)
        info.pack(fill="x", padx=15, pady=(0,15))
        
        temp = self.get_current_temperature()
        ct = self._get_datetime()
        can, hour, reason = self.can_measure_now()
        
        tk.Label(info, text=f"{temp}°C" if temp else "—", 
                font=("Segoe UI",FONT_TEMP_DISPLAY,"bold"), bg=COLOR_BG_LIGHT, 
                fg=COLOR_TEXT_PRIMARY).pack(pady=(12,4))
        tk.Label(info, text=ct.strftime("%Y-%m-%d %H:%M"), 
                font=("Segoe UI",FONT_BODY), bg=COLOR_BG_LIGHT, 
                fg=COLOR_TEXT_SECONDARY).pack(pady=(0,12))
        
        tk.Label(left_content, text="Measurement Schedule", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(5,8))
        
        sched = tk.Frame(left_content, bg="white")
        sched.pack(fill="x", padx=15)
        for h in self.VALID_HOURS:
            f = tk.Frame(sched, bg=COLOR_BG_LIGHT, highlightbackground=COLOR_SEPARATOR, 
                        highlightthickness=1)
            f.pack(side="left", expand=True, fill="both", padx=3, pady=3)
            tk.Label(f, text=f"{h:02d}:00", font=("Segoe UI",FONT_BODY,"bold"), 
                    bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_PRIMARY).pack(pady=(6,2))
            tk.Label(f, text=self.HOUR_NAMES[h], font=("Segoe UI",FONT_SMALL), 
                    bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_SECONDARY).pack(pady=(0,6))
        
        tk.Label(left_content, text="Record Measurement", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(15,8))
        
        status_sim = tk.Label(left_content, text="", font=("Segoe UI",FONT_BODY), bg="white")
        status_sim.pack(padx=15, pady=(0,8))
        
        def do_measure():
            success, msg = self.take_measurement()
            status_sim.config(text=msg, fg=COLOR_MORNING if success else "red")
            if success:
                left_content.after(2000, lambda: status_sim.config(text=""))
        
        btn_sim = tk.Button(left_content, text="📝 Take Measurement", font=("Segoe UI",FONT_BODY,"bold"), 
                           bg=COLOR_MORNING, fg="white", activebackground="#3A4F6A", 
                           command=do_measure, cursor="hand2", bd=0, padx=20, pady=10)
        btn_sim.pack(pady=(0,15))
        
        if not can:
            tk.Label(left_content, text=f"Status: {reason}", font=("Segoe UI",FONT_SMALL), 
                    bg="white", fg=COLOR_TEXT_SECONDARY).pack(pady=(0,15))
        
        left_scroll.pack(side="left", fill="both", expand=True)
        left_sb.pack(side="right", fill="y")
        
        # === RIGHT: MODERN RECORDING ===
        right_scroll = tk.Canvas(right_col, bg="white")
        right_sb = tk.Scrollbar(right_col, orient="vertical", command=right_scroll.yview)
        right_content = tk.Frame(right_scroll, bg="white")
        right_content.bind("<Configure>", lambda e: right_scroll.configure(scrollregion=right_scroll.bbox("all")))
        right_scroll.create_window((0, 0), window=right_content, anchor="nw")
        right_scroll.configure(yscrollcommand=right_sb.set)
        
        tk.Label(right_content, text="Modern Day Recording", font=("Segoe UI",FONT_TITLE,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(15,10))
        
        tk.Label(right_content, text="Record today's actual temperature to compare with Mendel's 1850s data.", 
                font=("Segoe UI",FONT_BODY), bg="white", fg=COLOR_TEXT_SECONDARY, 
                wraplength=350, justify="left").pack(anchor="w", padx=15, pady=(0,15))
        
        # Date
        tk.Label(right_content, text="Date", font=("Segoe UI",FONT_BODY,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(5,3))
        date_var = StringVar(value=dt.date.today().strftime("%Y-%m-%d"))
        date_entry = tk.Entry(right_content, textvariable=date_var, font=("Segoe UI",FONT_BODY), 
                             width=25, bd=2, relief="solid")
        date_entry.pack(anchor="w", padx=15, pady=(0,10))
        
        # Hour
        tk.Label(right_content, text="Hour (6, 14, or 22)", font=("Segoe UI",FONT_BODY,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(5,3))
        hour_var = StringVar()
        hour_frame = tk.Frame(right_content, bg="white")
        hour_frame.pack(anchor="w", padx=15, pady=(0,10))
        for h in self.VALID_HOURS:
            tk.Radiobutton(hour_frame, text=f"{h:02d}:00", variable=hour_var, value=str(h),
                          font=("Segoe UI",FONT_BODY), bg="white", 
                          selectcolor=COLOR_BG_LIGHT).pack(side="left", padx=(0,10))
        
        # Temperature
        tk.Label(right_content, text="Temperature (°C)", font=("Segoe UI",FONT_BODY,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(5,3))
        temp_var = StringVar()
        temp_entry = tk.Entry(right_content, textvariable=temp_var, font=("Segoe UI",FONT_BODY), 
                             width=25, bd=2, relief="solid")
        temp_entry.pack(anchor="w", padx=15, pady=(0,10))
        temp_entry.focus_set()
        
        status_modern = tk.Label(right_content, text="", font=("Segoe UI",FONT_BODY), bg="white")
        status_modern.pack(padx=15, pady=(5,10))
        
        def record_modern():
            try:
                date_str = date_var.get().strip()
                hour_str = hour_var.get().strip()
                temp_str = temp_var.get().strip()
                
                if not date_str or not hour_str or not temp_str:
                    status_modern.config(text="⚠ Please fill all fields", fg="red")
                    return
                
                date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
                hour = int(hour_str)
                temp = float(temp_str)
                
                if hour not in self.VALID_HOURS:
                    status_modern.config(text="⚠ Hour must be 6, 14, or 22", fg="red")
                    return
                
                # Check for duplicate
                for m in self.modern_measurements:
                    if m['date'] == date_str and m['hour'] == hour:
                        status_modern.config(text="⚠ Already recorded for this date/hour", fg="orange")
                        return
                
                mendel_avg = self.mendel_averages.get(date_obj.month, {}).get(hour)
                
                measurement = {
                    'date': date_str,
                    'datetime': f"{date_str} {hour:02d}:00",
                    'hour': hour,
                    'temperature': temp,
                    'month': date_obj.month,
                    'year': date_obj.year,
                    'is_modern': True
                }
                
                self.modern_measurements.append(measurement)
                self._save_modern_measurements()
                
                msg = f"✓ Recorded: {temp}°C"
                if mendel_avg:
                    dev = temp - mendel_avg
                    msg += f" (Mendel: {mendel_avg:.1f}°C, {'+' if dev>0 else ''}{dev:.1f}°C)"
                status_modern.config(text=msg, fg=COLOR_AFTERNOON)
                
                temp_var.set("")
                temp_entry.focus_set()
                
            except ValueError:
                status_modern.config(text="⚠ Enter valid values", fg="red")
        
        btn_modern = tk.Button(right_content, text="💾 Record Measurement", font=("Segoe UI",FONT_BODY,"bold"), 
                              bg=COLOR_AFTERNOON, fg="white", activebackground="#7A3A0F", 
                              command=record_modern, cursor="hand2", bd=0, padx=20, pady=10)
        btn_modern.pack(pady=(5,15), anchor="w", padx=15)
        
        temp_entry.bind('<Return>', lambda e: record_modern())
        
        # Tips
        tk.Frame(right_content, height=2, bg=COLOR_SEPARATOR).pack(fill="x", padx=15, pady=15)
        
        tk.Label(right_content, text="Tips", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=15, pady=(0,8))
        
        tips = """• Record at Mendel's times: 6:00, 14:00, 22:00
• Modern data appears with RED borders on Plot
• Press Enter to record quickly
• Compare today's climate with 1850s"""
        
        tk.Label(right_content, text=tips, font=("Segoe UI",FONT_SMALL), bg="white", 
                fg=COLOR_TEXT_SECONDARY, justify="left").pack(anchor="w", padx=15, pady=(0,15))
        
        right_scroll.pack(side="left", fill="both", expand=True)
        right_sb.pack(side="right", fill="y")
    
    def _tab_history(self, parent):
        """Display both simulation and modern measurements side-by-side with delete buttons."""
        # Clear any existing widgets (for refresh after delete)
        for widget in parent.winfo_children():
            widget.destroy()
        
        # Title with totals and refresh button at top center
        title_frame = tk.Frame(parent, bg="white")
        title_frame.pack(pady=(10,5), padx=10)
        
        header_row = tk.Frame(title_frame, bg="white")
        header_row.pack()
        
        tk.Label(header_row, text="Measurement History", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0,10))
        
        # Refresh button
        refresh_btn = tk.Button(header_row, text="🔄 Refresh", font=("Segoe UI",FONT_SMALL,"bold"),
                               bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_PRIMARY, 
                               command=lambda: self._tab_history(parent),
                               cursor="hand2", bd=1, relief="solid", padx=8, pady=3)
        refresh_btn.pack(side="left")
        
        totals_text = f"Recorded: {len(self.measurements)}  |  Modern: {len(self.modern_measurements)}"
        tk.Label(title_frame, text=totals_text, font=("Segoe UI",FONT_SMALL), 
                bg="white", fg=COLOR_TEXT_SECONDARY).pack()
        
        # Two columns frame
        cols = tk.Frame(parent, bg="white")
        cols.pack(fill="both", expand=True, padx=10, pady=(0,10))
        
        # LEFT: Simulation
        left = tk.Frame(cols, bg="white")
        left.pack(side="left", fill="both", expand=True, padx=(0,5))
        
        # Header with delete button
        hdr1 = tk.Frame(left, bg=COLOR_BG_PARCHMENT)
        hdr1.pack(fill="x", pady=(0,5))
        tk.Label(hdr1, text="Recorded Measurements", font=("Segoe UI",FONT_BODY,"bold"),
                bg=COLOR_BG_PARCHMENT, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=10, pady=5)
        
        def del_sim():
            self.measurements = []
            self._save_measurements()
            self._tab_history(parent)  # Refresh
        
        tk.Button(hdr1, text="🗑️ Delete All", command=del_sim, font=("Segoe UI",FONT_SMALL),
                 bg="#dc3545", fg="white", padx=10, pady=2).pack(side="right", padx=10, pady=5)
        
        # Scrollable canvas for simulation
        c1 = tk.Canvas(left, bg="white", highlightthickness=1, highlightbackground=COLOR_SEPARATOR)
        sb1 = tk.Scrollbar(left, orient="vertical", command=c1.yview)
        s1 = tk.Frame(c1, bg="white")
        s1.bind("<Configure>", lambda e: c1.configure(scrollregion=c1.bbox("all")))
        c1.create_window((0, 0), window=s1, anchor="nw")
        c1.configure(yscrollcommand=sb1.set)
        
        if not self.measurements:
            tk.Label(s1, text="No data yet", font=("Segoe UI",FONT_BODY),
                    bg="white", fg=COLOR_TEXT_SECONDARY).pack(padx=20, pady=20)
        else:
            for m in sorted(self.measurements, key=lambda x: x.get('datetime',''), reverse=True):
                i = tk.Frame(s1, bg="#E8F4F8", padx=10, pady=6)
                i.pack(fill="x", padx=10, pady=2)
                tk.Label(i, text=m.get('datetime','N/A'), font=("Segoe UI",FONT_SMALL,"bold"),
                        bg="#E8F4F8", fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
                txt = f"{m.get('temperature','N/A')}°C"
                if 'month' in m and 'hour' in m:
                    exp = self.mendel_averages.get(m['month'],{}).get(m['hour'])
                    if exp:
                        dev = m['temperature'] - exp
                        txt += f" • Avg: {exp:.1f}°C • Diff: {'+' if dev>0 else ''}{dev:.1f}°C"
                tk.Label(i, text=txt, font=("Segoe UI",FONT_SMALL-1),
                        bg="#E8F4F8", fg=COLOR_TEXT_SECONDARY).pack(anchor="w")
        
        c1.pack(side="left", fill="both", expand=True)
        sb1.pack(side="right", fill="y")
        
        # RIGHT: Modern
        right = tk.Frame(cols, bg="white")
        right.pack(side="left", fill="both", expand=True, padx=(5,0))
        
        # Header with delete button
        hdr2 = tk.Frame(right, bg=COLOR_BG_PARCHMENT)
        hdr2.pack(fill="x", pady=(0,5))
        tk.Label(hdr2, text="Modern Measurements", font=("Segoe UI",FONT_BODY,"bold"),
                bg=COLOR_BG_PARCHMENT, fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=10, pady=5)
        
        def del_mod():
            self.modern_measurements = []
            self._save_modern_measurements()
            self._tab_history(parent)  # Refresh
        
        tk.Button(hdr2, text="🗑️ Delete All", command=del_mod, font=("Segoe UI",FONT_SMALL),
                 bg="#dc3545", fg="white", padx=10, pady=2).pack(side="right", padx=10, pady=5)
        
        # Scrollable canvas for modern
        c2 = tk.Canvas(right, bg="white", highlightthickness=1, highlightbackground=COLOR_SEPARATOR)
        sb2 = tk.Scrollbar(right, orient="vertical", command=c2.yview)
        s2 = tk.Frame(c2, bg="white")
        s2.bind("<Configure>", lambda e: c2.configure(scrollregion=c2.bbox("all")))
        c2.create_window((0, 0), window=s2, anchor="nw")
        c2.configure(yscrollcommand=sb2.set)
        
        if not self.modern_measurements:
            tk.Label(s2, text="No data yet\n\nUse 'Record' tab", font=("Segoe UI",FONT_BODY),
                    bg="white", fg=COLOR_TEXT_SECONDARY, justify="center").pack(padx=20, pady=20)
        else:
            for m in sorted(self.modern_measurements, key=lambda x: x.get('datetime',''), reverse=True):
                i = tk.Frame(s2, bg="#FFE4E1", padx=10, pady=6)
                i.pack(fill="x", padx=10, pady=2)
                tk.Label(i, text=m.get('datetime','N/A'), font=("Segoe UI",FONT_SMALL,"bold"),
                        bg="#FFE4E1", fg=COLOR_TEXT_PRIMARY).pack(anchor="w")
                txt = f"{m.get('temperature','N/A')}°C"
                if 'month' in m and 'hour' in m:
                    exp = self.mendel_averages.get(m['month'],{}).get(m['hour'])
                    if exp:
                        dev = m['temperature'] - exp
                        txt += f" • Avg: {exp:.1f}°C • Change: {'+' if dev>0 else ''}{dev:.1f}°C"
                tk.Label(i, text=txt, font=("Segoe UI",FONT_SMALL-1),
                        bg="#FFE4E1", fg=COLOR_TEXT_SECONDARY).pack(anchor="w")
        
        c2.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")
    
    def _tab_record(self, parent):
        """Manual data entry for modern measurements."""
        c = tk.Canvas(parent, bg="white")
        sb = tk.Scrollbar(parent, orient="vertical", command=c.yview)
        s = tk.Frame(c, bg="white")
        s.bind("<Configure>", lambda e: c.configure(scrollregion=c.bbox("all")))
        c.create_window((0, 0), window=s, anchor="nw")
        c.configure(yscrollcommand=sb.set)
        
        tk.Label(s, text="Record Modern Temperature", font=("Segoe UI",FONT_TITLE,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(20,10))
        
        tk.Label(s, text="Enter today's actual temperature (e.g., from weather report) to compare with Mendel's historical data.", 
                font=("Segoe UI",FONT_BODY), bg="white", fg=COLOR_TEXT_SECONDARY, 
                wraplength=600).pack(anchor="w", padx=20, pady=(0,20))
        
        # Date entry
        date_frame = tk.Frame(s, bg="white")
        date_frame.pack(anchor="w", padx=20, pady=(0,10))
        
        tk.Label(date_frame, text="Date:", font=("Segoe UI",FONT_BODY,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0,8))
        now = dt.datetime.now()
        date_var = StringVar(value=now.strftime("%Y-%m-%d"))
        tk.Entry(date_frame, textvariable=date_var, font=("Segoe UI",FONT_BODY), 
                width=12).pack(side="left")
        
        # Hour selection and temperature entry on same line
        input_frame = tk.Frame(s, bg="white")
        input_frame.pack(anchor="w", padx=20, pady=(0,10))
        
        tk.Label(input_frame, text="Hour:", font=("Segoe UI",FONT_BODY,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0,8))
        hour_var = StringVar(value="14")
        hour_dropdown = ttk.Combobox(input_frame, textvariable=hour_var, 
                                     values=["6", "14", "22"], width=5, 
                                     font=("Segoe UI",FONT_BODY), state="readonly")
        hour_dropdown.pack(side="left", padx=(0,20))
        
        tk.Label(input_frame, text="Temperature:", font=("Segoe UI",FONT_BODY,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(side="left", padx=(0,8))
        temp_var = StringVar()
        temp_entry = tk.Entry(input_frame, textvariable=temp_var, font=("Segoe UI",FONT_BODY), 
                width=10)
        temp_entry.pack(side="left", padx=(0,6))
        tk.Label(input_frame, text="°C", font=("Segoe UI",FONT_BODY), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(side="left")
        
        # Status label for feedback
        status_label = tk.Label(s, text="", font=("Segoe UI",FONT_SMALL), 
                               bg="white", fg=COLOR_MORNING)
        status_label.pack(anchor="w", padx=20, pady=(5,0))
        
        def record_modern():
            try:
                date_str = date_var.get()
                hour = int(hour_var.get())
                temp = float(temp_var.get())
                
                if temp < -50 or temp > 60:
                    status_label.config(text="⚠ Temperature must be -50 to 60°C", fg="red")
                    return
                
                # Parse date
                try:
                    date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    status_label.config(text="⚠ Invalid date format (use YYYY-MM-DD)", fg="red")
                    return
                
                # Check for duplicate
                for m in self.modern_measurements:
                    if m['date'] == date_str and m['hour'] == hour:
                        status_label.config(text="⚠ Already recorded for this date and hour", fg="orange")
                        return
                
                # Get Mendel's average for comparison
                mendel_avg = self.mendel_averages.get(date_obj.month, {}).get(hour)
                
                # Create measurement with ALL required fields for plotting
                measurement = {
                    'date': date_str,
                    'datetime': f"{date_str} {hour:02d}:00",
                    'hour': hour,
                    'temperature': temp,
                    'month': date_obj.month,  # CRITICAL for plotting
                    'year': date_obj.year,    # CRITICAL for plotting
                    'is_modern': True
                }
                
                self.modern_measurements.append(measurement)
                self._save_modern_measurements()
                
                print(f"[MEASUREMENT] Saved modern: date={date_str}, hour={hour}, temp={temp}°C, month={date_obj.month}")
                
                # Show feedback
                msg = f"✓ Recorded: {temp}°C"
                if mendel_avg:
                    dev = temp - mendel_avg
                    msg += f" (Mendel avg: {mendel_avg:.1f}°C, {'+' if dev>0 else ''}{dev:.1f}°C)"
                status_label.config(text=msg, fg=COLOR_MORNING)
                
                # Clear temperature for next entry
                temp_var.set("")
                temp_entry.focus_set()
                
            except ValueError:
                status_label.config(text="⚠ Enter a valid temperature number", fg="red")
        
        # Record button
        btn = tk.Button(s, text="💾 Record Measurement", font=("Segoe UI",FONT_BODY,"bold"), 
                       bg=COLOR_AFTERNOON, fg="white", activebackground="#7A3A0F", 
                       command=record_modern, cursor="hand2", bd=0, padx=20, pady=10)
        btn.pack(pady=(10,20), anchor="w", padx=20)
        
        # Enable Enter key to record
        temp_entry.bind('<Return>', lambda e: record_modern())
        
        # Tips section
        tk.Frame(s, height=2, bg=COLOR_SEPARATOR).pack(fill="x", padx=20, pady=20)
        
        tk.Label(s, text="Tips", font=("Segoe UI",FONT_HEADING,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(0,10))
        
        tips = """• Use this to record actual temperatures from your location
• Compare modern climate with Mendel's 1850s measurements
• Record at the same hours as Mendel: 6:00, 14:00, or 22:00
• Data appears with RED borders on the Plot tab
• Press Enter after typing temperature to record quickly"""
        
        tk.Label(s, text=tips, font=("Segoe UI",FONT_BODY), bg="white", 
                fg=COLOR_TEXT_SECONDARY, justify="left").pack(anchor="w", padx=20, pady=(0,20))
        
        c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
    
    def _tab_plot(self, parent):
        """Plot with RELIABLE data display - shows BOTH simulation and modern measurements."""
        # Clear previous plot widgets
        for w in parent.winfo_children():
            w.destroy()

        global Figure, FigureCanvasTkAgg, MATPLOTLIB_AVAILABLE

        print(f"\n[PLOT] Refreshing plot...")
        print(f"[PLOT] Simulation measurements: {len(self.measurements)}")
        print(f"[PLOT] Modern measurements: {len(self.modern_measurements)}")

        if not self.measurements and not self.modern_measurements:
            tk.Label(
                parent,
                text="No data to plot yet\n\nTake some measurements first!",
                font=("Segoe UI", FONT_BODY),
                fg=COLOR_TEXT_SECONDARY,
                bg="white",
                justify="center"
            ).pack(expand=True)
            return

        # Lazy import matplotlib
        if not MATPLOTLIB_AVAILABLE or Figure is None or FigureCanvasTkAgg is None:
            try:
                import matplotlib
                matplotlib.use("TkAgg")
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _FCTK
                from matplotlib.figure import Figure as _Figure
                FigureCanvasTkAgg = _FCTK
                Figure = _Figure
                MATPLOTLIB_AVAILABLE = True
            except ImportError:
                tk.Label(
                    parent,
                    text="Matplotlib not available\n\nInstall with: pip install matplotlib",
                    font=("Segoe UI", FONT_BODY),
                    fg=COLOR_TEXT_SECONDARY,
                    bg="white",
                    justify="center"
                ).pack(expand=True)
                return

        # Create figure
        fig = Figure(figsize=(8.5, 5.5), dpi=80, facecolor=COLOR_BG_PARCHMENT)
        ax = fig.add_subplot(111, facecolor=COLOR_BG_LIGHT)

        months = list(range(1, 13))
        
        # Colorblind-friendly colors (Wong palette)
        COLOR_MORNING_CB = '#0173B2'    # Blue
        COLOR_AFTERNOON_CB = '#DE8F05'  # Orange  
        COLOR_EVENING_CB = '#029E73'    # Teal
        
        # Plot Mendel's historical averages WITHOUT LABELS (no legend entries)
        a6  = [self.mendel_averages[m][6]  for m in months]
        a14 = [self.mendel_averages[m][14] for m in months]
        a22 = [self.mendel_averages[m][22] for m in months]
        
        # Smooth curves if scipy available
        if SCIPY_AVAILABLE:
            try:
                months_smooth = np.linspace(1, 12, 300)
                spl6 = make_interp_spline(months, a6, k=3)
                spl14 = make_interp_spline(months, a14, k=3)
                spl22 = make_interp_spline(months, a22, k=3)
                a6_smooth = spl6(months_smooth)
                a14_smooth = spl14(months_smooth)
                a22_smooth = spl22(months_smooth)
                
                # NO LABELS - baseline curves don't appear in legend
                ax.plot(months_smooth, a6_smooth, '-',
                        color=COLOR_MORNING_CB, linewidth=2.5, alpha=0.8, zorder=1)
                ax.plot(months_smooth, a14_smooth, '-',
                        color=COLOR_AFTERNOON_CB, linewidth=2.5, alpha=0.8, zorder=1)
                ax.plot(months_smooth, a22_smooth, '-',
                        color=COLOR_EVENING_CB, linewidth=2.5, alpha=0.8, zorder=1)
            except:
                # Fallback if spline fails
                ax.plot(months, a6, '-',
                        color=COLOR_MORNING_CB, linewidth=2.5, alpha=0.8, zorder=1)
                ax.plot(months, a14, '-',
                        color=COLOR_AFTERNOON_CB, linewidth=2.5, alpha=0.8, zorder=1)
                ax.plot(months, a22, '-',
                        color=COLOR_EVENING_CB, linewidth=2.5, alpha=0.8, zorder=1)
        else:
            # No scipy - just lines without markers or labels
            ax.plot(months, a6, '-',
                    color=COLOR_MORNING_CB, linewidth=2.5, alpha=0.8, zorder=1)
            ax.plot(months, a14, '-',
                    color=COLOR_AFTERNOON_CB, linewidth=2.5, alpha=0.8, zorder=1)
            ax.plot(months, a22, '-',
                    color=COLOR_EVENING_CB, linewidth=2.5, alpha=0.8, zorder=1)
        
        # Calculate and plot yearly averages (dotted lines) from simulation data
        from collections import defaultdict
        yearly_averages = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        
        for m in self.measurements:
            year = m.get('year')
            month = m.get('month')
            hour = m.get('hour')
            temp = m.get('temperature')
            
            if year and month and hour and temp is not None:
                yearly_averages[year][month][hour].append(temp)
        
        # Plot dotted line for each year's monthly averages
        for year in sorted(yearly_averages.keys()):
            year_data = yearly_averages[year]
            
            # Calculate monthly averages for each hour
            months_with_data = sorted(year_data.keys())
            if len(months_with_data) >= 2:  # Only plot if we have data for at least 2 months
                y6_avg, y14_avg, y22_avg = [], [], []
                valid_months = []
                
                for month in months_with_data:
                    if 6 in year_data[month] and year_data[month][6]:
                        y6_avg.append(sum(year_data[month][6]) / len(year_data[month][6]))
                    else:
                        y6_avg.append(None)
                    
                    if 14 in year_data[month] and year_data[month][14]:
                        y14_avg.append(sum(year_data[month][14]) / len(year_data[month][14]))
                    else:
                        y14_avg.append(None)
                    
                    if 22 in year_data[month] and year_data[month][22]:
                        y22_avg.append(sum(year_data[month][22]) / len(year_data[month][22]))
                    else:
                        y22_avg.append(None)
                    
                    valid_months.append(month)
                
                # Plot dotted lines (subtle, not dominant)
                if any(v is not None for v in y6_avg):
                    ax.plot(valid_months, y6_avg, ':',
                            color=COLOR_MORNING_CB, linewidth=1.5, alpha=0.4, zorder=2)
                if any(v is not None for v in y14_avg):
                    ax.plot(valid_months, y14_avg, ':',
                            color=COLOR_AFTERNOON_CB, linewidth=1.5, alpha=0.4, zorder=2)
                if any(v is not None for v in y22_avg):
                    ax.plot(valid_months, y22_avg, ':',
                            color=COLOR_EVENING_CB, linewidth=1.5, alpha=0.4, zorder=2)
        
        # SIMULATION measurements (black borders) - plot by day of year
        sim6_days, sim6_temps = [], []
        sim14_days, sim14_temps = [], []
        sim22_days, sim22_temps = [], []
        
        for m in self.measurements:
            hour = m.get('hour')
            temp = m.get('temperature')
            date_str = m.get('date')
            
            if hour is None or temp is None or date_str is None:
                print(f"[WARNING] Skipping malformed simulation measurement: {m}")
                continue
            
            try:
                date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
                # Convert to day of year as a fraction of month using actual days in month
                if date_obj.month == 12:
                    days_in_month = 31
                else:
                    days_in_month = (dt.date(date_obj.year, date_obj.month + 1, 1) - dt.date(date_obj.year, date_obj.month, 1)).days
                day_of_year = date_obj.month + (date_obj.day - 1) / days_in_month
                
                if hour == 6:
                    sim6_days.append(day_of_year)
                    sim6_temps.append(temp)
                elif hour == 14:
                    sim14_days.append(day_of_year)
                    sim14_temps.append(temp)
                elif hour == 22:
                    sim22_days.append(day_of_year)
                    sim22_temps.append(temp)
            except Exception as e:
                print(f"[WARNING] Error parsing date {date_str}: {e}")
                continue
        
        has_simulation = len(sim6_days) > 0 or len(sim14_days) > 0 or len(sim22_days) > 0
        
        if has_simulation:
            sim_count = len(sim6_days) + len(sim14_days) + len(sim22_days)
            print(f"[PLOT] Plotting {sim_count} simulation measurements")
        
        if sim6_days:
            ax.scatter(sim6_days, sim6_temps, color=COLOR_MORNING_CB, s=50, 
                      marker='o', edgecolors='black', linewidths=1.5, zorder=5)
        if sim14_days:
            ax.scatter(sim14_days, sim14_temps, color=COLOR_AFTERNOON_CB, s=50, 
                      marker='s', edgecolors='black', linewidths=1.5, zorder=5)
        if sim22_days:
            ax.scatter(sim22_days, sim22_temps, color=COLOR_EVENING_CB, s=50, 
                      marker='^', edgecolors='black', linewidths=1.5, zorder=5)
        
        # MODERN measurements (red borders) - plot by day of year
        mod6_days, mod6_temps = [], []
        mod14_days, mod14_temps = [], []
        mod22_days, mod22_temps = [], []
        
        for m in self.modern_measurements:
            hour = m.get('hour')
            temp = m.get('temperature')
            date_str = m.get('date')
            
            if hour is None or temp is None or date_str is None:
                print(f"[WARNING] Skipping malformed modern measurement: {m}")
                continue
            
            try:
                date_obj = dt.datetime.strptime(date_str, "%Y-%m-%d")
                # Convert to day of year as a fraction of month using actual days in month
                if date_obj.month == 12:
                    days_in_month = 31
                else:
                    days_in_month = (dt.date(date_obj.year, date_obj.month + 1, 1) - dt.date(date_obj.year, date_obj.month, 1)).days
                day_of_year = date_obj.month + (date_obj.day - 1) / days_in_month
                
                if hour == 6:
                    mod6_days.append(day_of_year)
                    mod6_temps.append(temp)
                elif hour == 14:
                    mod14_days.append(day_of_year)
                    mod14_temps.append(temp)
                elif hour == 22:
                    mod22_days.append(day_of_year)
                    mod22_temps.append(temp)
            except Exception as e:
                print(f"[WARNING] Error parsing date {date_str}: {e}")
                continue
        
        has_modern = len(mod6_days) > 0 or len(mod14_days) > 0 or len(mod22_days) > 0
        
        if has_modern:
            mod_count = len(mod6_days) + len(mod14_days) + len(mod22_days)
            print(f"[PLOT] Plotting {mod_count} modern measurements")
        
        if mod6_days:
            ax.scatter(mod6_days, mod6_temps, color=COLOR_MORNING_CB, s=60, 
                      marker='o', edgecolors='red', linewidths=2, zorder=6)
        if mod14_days:
            ax.scatter(mod14_days, mod14_temps, color=COLOR_AFTERNOON_CB, s=60, 
                      marker='s', edgecolors='red', linewidths=2, zorder=6)
        if mod22_days:
            ax.scatter(mod22_days, mod22_temps, color=COLOR_EVENING_CB, s=60, 
                      marker='^', edgecolors='red', linewidths=2, zorder=6)
        
        # Labels and title
        ax.set_xlabel('Month', fontsize=12, fontfamily='serif', fontweight='bold')
        ax.set_ylabel('Temperature (°C)', fontsize=12, fontfamily='serif', fontweight='bold')
        
        title = 'Meteorological Observatory — Temperature Observations'
        if has_simulation and has_modern:
            title += '\n(Recorded + Modern Data vs. Mendel\'s 1848-1863 Averages)'
        elif has_simulation:
            title += '\n(Recorded Data vs. Mendel\'s 1848-1863 Averages)'
        elif has_modern:
            title += '\n(Modern Data vs. Mendel\'s 1848-1863 Averages)'
        else:
            title += '\n(Mendel\'s 1848-1863 Averages)'
        
        ax.set_title(title, fontsize=13, fontfamily='serif', fontweight='bold', pad=15)
        
        ax.set_xticks(months)
        ax.set_xticklabels(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], 
                          fontfamily='serif', fontsize=10)
        ax.tick_params(axis='y', labelsize=10)
        ax.set_ylim(-15, 35)  # Extended range from -15°C to 35°C
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5, color='#8B7355')
        
        # Custom legend order: baseline (Morning/Afternoon/Evening), then Recorded, then Modern
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        
        legend_elements = [
            # Mendel baseline (lines only)
            Line2D([0], [0], color=COLOR_MORNING_CB, linewidth=2.5, label='Morning (6:00) — Mendel 1848-1863'),
            Line2D([0], [0], color=COLOR_AFTERNOON_CB, linewidth=2.5, label='Afternoon (14:00) — Mendel 1848-1863'),
            Line2D([0], [0], color=COLOR_EVENING_CB, linewidth=2.5, label='Evening (22:00) — Mendel 1848-1863'),
        ]
        
        # Add Recorded data if present (only times that have data)
        if has_simulation:
            if len(sim6_days) > 0:
                legend_elements.append(Line2D([0], [0], marker='o', color='w', 
                                             markerfacecolor=COLOR_MORNING_CB, markeredgecolor='black',
                                             markeredgewidth=1.5, markersize=7, label='Morning (6:00) — Recorded'))
            if len(sim14_days) > 0:
                legend_elements.append(Line2D([0], [0], marker='s', color='w',
                                             markerfacecolor=COLOR_AFTERNOON_CB, markeredgecolor='black',
                                             markeredgewidth=1.5, markersize=7, label='Afternoon (14:00) — Recorded'))
            if len(sim22_days) > 0:
                legend_elements.append(Line2D([0], [0], marker='^', color='w',
                                             markerfacecolor=COLOR_EVENING_CB, markeredgecolor='black',
                                             markeredgewidth=1.5, markersize=7, label='Evening (22:00) — Recorded'))
        
        # Add Modern data if present (only times that have data)
        if has_modern:
            if len(mod6_days) > 0:
                legend_elements.append(Line2D([0], [0], marker='o', color='w',
                                             markerfacecolor=COLOR_MORNING_CB, markeredgecolor='red',
                                             markeredgewidth=2, markersize=8, label='Morning (6:00) — Modern'))
            if len(mod14_days) > 0:
                legend_elements.append(Line2D([0], [0], marker='s', color='w',
                                             markerfacecolor=COLOR_AFTERNOON_CB, markeredgecolor='red',
                                             markeredgewidth=2, markersize=8, label='Afternoon (14:00) — Modern'))
            if len(mod22_days) > 0:
                legend_elements.append(Line2D([0], [0], marker='^', color='w',
                                             markerfacecolor=COLOR_EVENING_CB, markeredgecolor='red',
                                             markeredgewidth=2, markersize=8, label='Evening (22:00) — Modern'))
        
        legend = ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.08), 
                          ncol=3, fontsize=9, framealpha=0.98, 
                          fancybox=False, edgecolor='black')
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_linewidth(1.5)
        
        # Styling
        for sp in ax.spines.values():
            sp.set_edgecolor(COLOR_BORDER)
            sp.set_linewidth(1.5)
        
        fig.tight_layout(pad=2)
        
        # Display
        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        print("[PLOT] Plot rendered successfully\n")
    
    def _tab_about(self, parent):
        c = tk.Canvas(parent, bg="white")
        sb = tk.Scrollbar(parent, orient="vertical", command=c.yview)
        s = tk.Frame(c, bg="white")
        s.bind("<Configure>", lambda e: c.configure(scrollregion=c.bbox("all")))
        c.create_window((0, 0), window=s, anchor="nw")
        c.configure(yscrollcommand=sb.set)
        
        tk.Label(s, text="About Mendel's Meteorological Work", font=("Segoe UI",FONT_TITLE,"bold"), 
                bg="white", fg=COLOR_TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(20,15))
        
        txt = """Gregor Mendel: The Meticulous Meteorologist

While Gregor Mendel is famous for his groundbreaking work on heredity and genetics through pea plant experiments, he was also an accomplished meteorologist who made daily weather observations for decades.

Daily Measurement Routine:
Mendel measured temperature three times daily:
  • 6:00 AM (Morning) - Capturing the cool morning temperatures
  • 14:00 (2:00 PM) - Peak afternoon warmth
  • 22:00 (10:00 PM) - Evening cooldown

This disciplined routine continued throughout his life at the Augustinian Abbey of St. Thomas in Brno (modern-day Czech Republic).

The Data:
The temperature data in this simulation is derived from Mendel's actual meteorological records spanning 15 years (1848-1863). These measurements provide a climatological baseline representing the typical temperature patterns in Brno during Mendel's era.

Historical Context:
Mendel's meteorological observations were as meticulous as his genetic experiments. He recorded not just temperature, but also:
  • Atmospheric pressure
  • Cloud coverage
  • Precipitation
  • Wind direction and strength
  • Thunder and hail events

His weather data contributed to the broader scientific understanding of Central European climate patterns in the 19th century.

Your Role:
In this simulation, you follow in Mendel's footsteps by taking measurements at the same times he did. Your observations are compared against his 15-year averages, allowing you to see how each day's weather compares to the historical baseline.

Modern Measurements:
The "Record" tab allows you to record today's actual temperatures. You can compare them directly with Mendel's 19th century observations, revealing how climate has changed over the past 160+ years.

Will your measurements match the historical averages, or will you observe unusual weather patterns? Just as Mendel's patient observation revealed the laws of heredity, your careful measurements may reveal patterns in the simulated climate!"""
        
        tk.Label(s, text=txt, font=("Segoe UI",FONT_BODY), bg="white", fg=COLOR_TEXT_PRIMARY, 
                justify="left", wraplength=660).pack(anchor="w", padx=20, pady=(0,20))
        
        c.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
