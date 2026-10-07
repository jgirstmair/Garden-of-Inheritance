"""
Animated Mendel portrait for the left panel.

Replaces the single static mendel.png with the expression images in
icons/mendel/ (mendel_<mood>_<season>.png):

  * the image always matches the current season,
  * watering the plants shows the "watering" image for a few seconds,
  * otherwise the expression changes at random about every 30 seconds,
  * when the player has been idle for a while, thinking / eyes-closed
    expressions are preferred.

When Mendel is away (19:00-05:59, the hours the game's "night gate" blocks
actions), the portrait shows a garden scene without him instead: a night
image once it is dark, or an empty daytime image while it is still light.
Scene files are recognised by name in icons/mendel/ (see _scan_scenes).

While the tutorial owns the portrait (app._tutorial_active), this stays
out of the way; call refresh() when the tutorial hands it back.
"""

import os
import random
import time

from icon_loader import ICONS_DIR, safe_image

MENDEL_DIR = os.path.join(ICONS_DIR, "mendel")

_SEASONS = ("spring", "summer", "autumn", "winter")

# (mood file-name part, weight)
_ACTIVE_MOODS = (("looking", 4), ("noting", 2))  # "smiling" removed for now
_IDLE_MOODS = (("thinking", 3), ("eyes-closed", 4))
# "thinking2" is Mendel's worried look: only used while some plant is
# overwatered or drying out (same water limits as Plant._update_health_from_water).
_WORRY_MOOD = "thinking2"
_WORRY_CHANCE = 0.6         # chance a change picks the worried look while stressed
_DRY_AT_OR_BELOW = 25
_OVERWATERED_ABOVE = 90

CHANGE_EVERY_S = 30.0      # random expression change interval
IDLE_AFTER_S = 45.0        # no input for this long -> idle expressions
WATERING_SHOW_S = 3.5      # how long the watering image stays
TICK_MS = 1000


_KNOWN_MOODS = {"looking", "smiling", "noting", "thinking", "thinking2",
                "eyes-closed", "watering"}
_DARK_BELOW = 0.25         # light factor under which the scene counts as dark


def _scan_scenes():
    """Finds the Mendel-less scene images in icons/mendel/.

    Any <something>_<season>.png whose <something> is not one of Mendel's
    expressions is a scene: if it contains "night" it is a night scene,
    anything else (empty, day, away, ...) is an empty daytime scene.
    Returns {"night": {season: [paths]}, "day": {season: [paths]}}.
    """
    scenes = {"night": {}, "day": {}}
    try:
        names = sorted(os.listdir(MENDEL_DIR))
    except Exception:
        return scenes
    for fn in names:
        stem, ext = os.path.splitext(fn)
        if ext.lower() != ".png":
            continue
        parts = stem.lower().split("_")
        season = parts[-1].split("-")[0] if parts else ""
        if season in _SEASONS:
            mood = "_".join(parts[:-1])
        elif parts and parts[0] in _SEASONS:      # e.g. spring_night.png
            season, mood = parts[0], "_".join(parts[1:])
        else:
            continue
        if mood.startswith("mendel_"):
            mood = mood[len("mendel_"):]
        if mood in _KNOWN_MOODS:
            continue
        kind = "night" if "night" in mood else "day"
        scenes[kind].setdefault(season, []).append(os.path.join(MENDEL_DIR, fn))
    return scenes


def _pick(pool, avoid=None):
    choices = [(m, w) for m, w in pool if m != avoid] or list(pool)
    total = sum(w for _, w in choices)
    r = random.uniform(0, total)
    for mood, w in choices:
        r -= w
        if r <= 0:
            return mood
    return choices[-1][0]


def IDLE_OR_ACTIVE(p):
    return _IDLE_MOODS if p._idle else _ACTIVE_MOODS


class MendelPortrait:
    def __init__(self, app, label):
        self.app = app
        self.label = label
        self.mood = "looking"
        self._shown = None            # (mood, season) currently displayed
        self._next_change = time.monotonic() + CHANGE_EVERY_S
        self._watering_until = 0.0
        self._last_input = time.monotonic()
        self._idle = False
        self._stressed = False
        self._job = None
        self._tutorial_owned = False
        self._scenes = _scan_scenes()
        self._scene_choice = {}       # (kind, season) -> chosen path

    # ------------------------------------------------------------------
    def start(self):
        try:
            for seq in ("<Motion>", "<Key>", "<Button>"):
                self.app.root.bind_all(seq, self._on_input, add="+")
        except Exception:
            pass
        self._apply()
        self._job = self.app.root.after(TICK_MS, self._tick)

    def _on_input(self, event=None):
        self._last_input = time.monotonic()

    # ------------------------------------------------------------------
    def _season(self):
        s = getattr(self.app, "_bg_current_season", None)
        return s if s in _SEASONS else "spring"

    def _path(self, mood, season):
        return os.path.join(MENDEL_DIR, f"mendel_{mood}_{season}.png")

    def _garden_stressed(self):
        """True if any living plant is overwatered or nearly dried out."""
        try:
            for tile in self.app._all_plot_tiles():
                p = tile.plant
                if p is None or not getattr(p, "alive", True):
                    continue
                w = getattr(p, "water", 50)
                if w <= _DRY_AT_OR_BELOW or w > _OVERWATERED_ABOVE:
                    return True
        except Exception:
            pass
        return False

    def _next_mood(self, pool, avoid=None):
        if self._stressed and random.random() < _WORRY_CHANCE:
            return _WORRY_MOOD
        return _pick(pool, avoid)

    def _mendel_away(self):
        """True during the hours Mendel is at dinner, studying or asleep
        (same window as GardenApp._night_gate)."""
        try:
            hour = int(getattr(self.app.garden, "clock_hour", 8)) % 24
        except Exception:
            return False
        return hour >= 19 or hour < 6

    def _is_dark(self):
        try:
            import datetime as dt
            g = self.app.garden
            d = dt.date(int(g.year), int(g.month), int(g.day_of_month))
            light = self.app._compute_light_factor(d, float(g.clock_hour))
            return light < _DARK_BELOW
        except Exception:
            hour = int(getattr(self.app.garden, "clock_hour", 8)) % 24
            return hour >= 21 or hour < 5

    def _scene_path(self):
        """Path of the Mendel-less scene to show right now, or None."""
        if not self._mendel_away():
            return None
        season = self._season()
        order = ("night", "day") if self._is_dark() else ("day", "night")
        for kind in order:
            files = self._scenes.get(kind, {}).get(season)
            if files:
                key = (kind, season)
                if self._scene_choice.get(key) not in files:
                    self._scene_choice[key] = random.choice(files)
                return self._scene_choice[key]
        return None

    def _apply(self, force=False):
        season = self._season()
        scene = self._scene_path()
        if scene:
            key = ("scene", scene)
            path = scene
        else:
            key = (self.mood, season)
            path = self._path(self.mood, season)
        if key == self._shown and not force:
            return
        if not os.path.isfile(path):
            return
        try:
            img = safe_image(path)
            self.label.configure(image=img)
            self.label.image = img
            self._shown = key
        except Exception:
            pass

    def refresh(self):
        """Re-apply the current expression (e.g. after the tutorial ended)."""
        self._tutorial_owned = False
        self._apply(force=True)

    # ------------------------------------------------------------------
    def show_watering(self):
        if getattr(self.app, "_tutorial_active", False):
            return
        # Repeated waterings don't extend the display; one exact timer
        # (not the 1 s tick) ends it.
        if self.mood == "watering":
            return
        self.mood = "watering"
        self._apply()
        try:
            self.app.root.after(int(WATERING_SHOW_S * 1000), self._end_watering)
        except Exception:
            self._watering_until = time.monotonic() + WATERING_SHOW_S

    def _end_watering(self):
        if self.mood != "watering":
            return
        self.mood = self._next_mood(IDLE_OR_ACTIVE(self))
        self._next_change = time.monotonic() + CHANGE_EVERY_S
        self._apply()

    def _tick(self):
        self._job = None
        try:
            if getattr(self.app, "_tutorial_active", False):
                # The tutorial swaps in Cyril's portrait — hands off.
                self._tutorial_owned = True
                self._job = self.app.root.after(TICK_MS, self._tick)
                return
            if self._tutorial_owned:
                self.refresh()

            now = time.monotonic()
            stressed = self._garden_stressed()
            if stressed != self._stressed:
                self._stressed = stressed
                if self.mood != "watering":
                    # Worry sets in (or passes) right away.
                    self.mood = (_WORRY_MOOD if stressed
                                 else _pick(_IDLE_MOODS if self._idle else _ACTIVE_MOODS))
                    self._next_change = now + CHANGE_EVERY_S
            if self.mood == "watering":
                if self._watering_until and now >= self._watering_until:
                    self._watering_until = 0.0
                    self.mood = self._next_mood(_ACTIVE_MOODS)
                    self._next_change = now + CHANGE_EVERY_S
            else:
                idle = (now - self._last_input) >= IDLE_AFTER_S
                if idle != self._idle:
                    # Switched between active and idle: change right away.
                    self._idle = idle
                    self.mood = self._next_mood(_IDLE_MOODS if idle else _ACTIVE_MOODS, self.mood)
                    self._next_change = now + CHANGE_EVERY_S
                elif now >= self._next_change:
                    pool = _IDLE_MOODS if idle else _ACTIVE_MOODS
                    self.mood = self._next_mood(pool, self.mood)
                    self._next_change = now + CHANGE_EVERY_S + random.uniform(-5, 5)
            self._apply()
        except Exception:
            pass
        try:
            self._job = self.app.root.after(TICK_MS, self._tick)
        except Exception:
            pass
