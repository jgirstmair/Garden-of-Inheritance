"""
Some thoughts:

Need 2 things: 
    - A clock that keeps track of time, which is basically only for the user to have a 
    nice display, and maybe for the logs. Basically done already in MeteorologyPanel.
    - A meteorology station, that returns current weather, temperature, precipitation etc for the 
    current tick (maybe also hour, idk). Possibly used to update water level in the soil,
    and also plant growth. PERFORMANCE CRITICAL!

Weather needs to be updated either once per hour, or every tick. Preferrably use the existing
MendelClimate, allthough its unclear to me atm what this class actually does...
"""


from datetime import datetime, timedelta
from dataclasses import dataclass
import tkinter as tk
from gameticker import Entity

GAME_START_DATE = datetime(1856, 4, 1, 6, 0)
TICK_MINUTES = 15

@dataclass
class Weather:

    temperature: float
    precipitation: float
    clouds: float

class Meteorology(Entity):

    def __init__(self, mendelclimate):
        self.datetime = GAME_START_DATE
        self.mendelclimate = mendelclimate

        self.weather = self._get_current_weather()
        

    def _get_current_weather(self):
        temps = self.mendelclimate.hourly_targets(self.datetime.date())

        return Weather(temps[self.datetime.hour], 420, 0)

    def update(self, tick_count: int):
        self.datetime = GAME_START_DATE + timedelta(minutes=tick_count * TICK_MINUTES)
        self.weather = self._get_current_weather()

    def __hash__(self):
        return hash('Meteorology_Entity')

class MeteorologyPanel(tk.Label, Entity):

    def __init__(self, meteorology: Meteorology, *args, **kwargs):

        self.label = tk.Label(*args, **kwargs)
        self.label.pack(fill="x", pady=(4, 8))
        self.meteorology = meteorology

    
    def update(self, tick_count: int):
        # self._update_header()
        t = self.meteorology.datetime
        weather = self.meteorology.weather
        temp = weather.temperature
        self.label.configure(text=f'{t.day:02d}.{t.month:02d}.{t.year:04d}' + 
                             f' — {t.time().hour:02d}:{t.time().minute:02d} — Weather - {temp:.1f}°C')


    def _update_header(self):

        mon_names = ['January','February','March','April','May','June','July','August','September','October','November','December']
        mon = mon_names[getattr(self.garden, 'month', 4)-1] if 1 <= getattr(self.garden, 'month', 4) <= 12 else str(getattr(self.garden, 'month', 4))
        dom = getattr(self.garden, 'day_of_month', getattr(self.garden, 'day', 1))
        yr  = getattr(self.garden, 'year', 1856)
        hh  = getattr(self.garden, 'clock_hour', 6)
        mm  = getattr(self.garden, 'clock_minute', 0)
        wx  = getattr(self.garden, 'weather', '')
        tmp = f"{getattr(self.garden, 'temp', 0.0):.1f}°C" if hasattr(self.garden, 'temp') else ''
        clock = f"{int(hh):02d}:{int(mm):02d}"
        self.label.configure(text=f"{dom} {mon} {yr} — {clock} — {wx} {tmp}")
        # Season overlay info suppressed from status bar to avoid permanent message
        # (kept available via self._season_mode for other UI components if needed)
        mode = getattr(self, '_season_mode', 'off')
        # intentionally not writing to self.status_var here

    def __hash__(self):
        return hash('MeteorologyPanel_Entity')
