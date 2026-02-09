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
import tkinter as tk
from gameticker import Entity

GAME_START_DATE = datetime(1856, 4, 1, 6, 0)
TICK_MINUTES = 15

class Weather:
    pass

class Meteorology:
    pass

    def get_current_weather(self, time: datetime):
        pass

class MeteorologyPanel(tk.Label, Entity):

    def __init__(self, *args, **kwargs):
        self.label = tk.Label(*args, **kwargs)
        self.label.pack(fill="x", pady=(4, 8))

    
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

    def update(self, tick_count: int):
        t = self.get_game_time(tick_count)

        self.label.configure(text=f'{t.day} {t.month} {t.year} — {t.time().hour}:{t.time().minute} — Weather - Temperature')

    def get_game_time(self, current_ticks) -> datetime:
        """
        Converts the total ticks into a readable datetime object.
        Python's timedelta handles leap years and variable month lengths automatically.
        """
        return GAME_START_DATE + timedelta(minutes=current_ticks * TICK_MINUTES)


    def __hash__(self):
        return 69