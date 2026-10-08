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
WATERING_SHOW_S = 1.5
PLANTING_SHOW_S = 1.0      # ... and the planting image
TICK_MS = 1000


_KNOWN_MOODS = {"looking", "smiling", "noting", "thinking", "thinking2",
                "eyes-closed", "watering", "planting"}
_ACTION_MOODS = ("watering", "planting")
_DARK_ENTER = 0.40         # garden brightness (0-1) below which the portrait goes to night
_DARK_LEAVE = 0.60         # ... and above which it returns to day
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


_NIGHT_STEPS = 8
_night_cache = {}


def _night_image(path, step):
    """Mendel's daylight portrait darkened and tinted blue by `step`
    (1.._NIGHT_STEPS; _NIGHT_STEPS = full night), so he can stand in the
    dark garden too. Cached per (file, step). Returns a PhotoImage, or
    None if anything goes wrong (the plain daylight image is used then)."""
    key = (path, step)
    if key in _night_cache:
        return _night_cache[key]
    try:
        from PIL import Image, ImageEnhance, ImageTk
        d = step / float(_NIGHT_STEPS)
        im = Image.open(path).convert("RGBA")
        r, g, b, a = im.split()
        rgb = Image.merge("RGB", (r, g, b))
        rgb = ImageEnhance.Brightness(rgb).enhance(1.0 - 0.58 * d)
        tint = Image.new("RGB", rgb.size, (28, 44, 96))
        rgb = Image.blend(rgb, tint, 0.22 * d)
        r, g, b = rgb.split()
        photo = ImageTk.PhotoImage(Image.merge("RGBA", (r, g, b, a)))
    except Exception:
        photo = None
    _night_cache[key] = photo
    return photo


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
        self._dark_state = None       # follows the garden's day/night level
        self._garden_level = None
        self._night_step = 0          # 0 = day ... _NIGHT_STEPS = full night

    # ------------------------------------------------------------------
    def start(self):
        try:
            for seq in ("<Motion>", "<Key>", "<Button>"):
                self.app.root.bind_all(seq, self._on_input, add="+")
        except Exception:
            pass
        self._apply()
        self._job = self.app.root.after(TICK_MS, self._tick)

    def _tut_owns(self):
        """True while the tutorial owns the portrait (Cyril, or Mendel on
        the dialogue's own lines). Between lectures the tutorial hands it
        back (app._tutorial_portrait_free) and this class takes over."""
        return (bool(getattr(self.app, "_tutorial_active", False))
                and not getattr(self.app, "_tutorial_portrait_free", False))

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

    def on_light_changed(self, level):
        """Called by the garden every time it works out its day/night
        brightness (0 = night, 1 = full day, before any rain dimming).
        The portrait follows the same value, with a little hysteresis so
        it doesn't flicker around the half-way point, and redraws as soon
        as it flips."""
        try:
            self._garden_level = float(level)
            was = self._dark_state
            if self._garden_level < _DARK_ENTER:
                self._dark_state = True
            elif self._garden_level > _DARK_LEAVE:
                self._dark_state = False
            elif self._dark_state is None:
                self._dark_state = self._garden_level < 0.5
            step = self._current_night_step()
            changed_step = step != self._night_step
            self._night_step = step
            if (self._dark_state != was or changed_step) and not self._tut_owns():
                self._apply()
        except Exception:
            pass

    def _current_night_step(self):
        """How far into the night the garden is, in whole steps, so
        Mendel's portrait darkens in step with the tiles."""
        try:
            if (self._garden_level is None
                    or not getattr(self.app, "enable_daynight", True)):
                return 0
            return max(0, min(_NIGHT_STEPS,
                              int(round((1.0 - self._garden_level) * _NIGHT_STEPS))))
        except Exception:
            return 0

    def _is_dark(self):
        # Same brightness the garden tiles are showing right now.
        if (self._dark_state is not None
                and getattr(self.app, "enable_daynight", True)):
            return bool(self._dark_state)
        try:
            import datetime as dt
            g = self.app.garden
            d = dt.date(int(g.year), int(g.month), int(g.day_of_month))
            light = self.app._compute_light_factor(d, float(g.clock_hour))
            return light < _DARK_BELOW
        except Exception:
            hour = int(getattr(self.app.garden, "clock_hour", 8)) % 24
            return hour >= 21 or hour < 5

    def _garden_only(self):
        return bool(getattr(self.app, "_garden_only_portrait", False))

    def _garden_scene_path(self):
        """The Mendel-less garden image for the current season: the night
        one when it is dark, else the day one (each falls back to the
        other kind); None if there are no scene images at all."""
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
        # While an action image (watering / planting) has priority, only it
        # may be shown.
        if (time.monotonic() < getattr(self.app, "_portrait_locked_until", 0.0)
                and self.mood not in _ACTION_MOODS):
            return
        season = self._season()
        scene = self._garden_scene_path() if self._garden_only() else self._scene_path()
        if scene:
            key = ("scene", scene)
            path = scene
        else:
            key = (self.mood, season)
            path = self._path(self.mood, season)
        step = 0 if scene else self._night_step
        if not scene and not getattr(self.app, "enable_daynight", True):
            step = 0
        key = key + (step,)
        if key == self._shown and not force:
            return
        if not os.path.isfile(path):
            return
        try:
            img = _night_image(path, step) if step > 0 else None
            if img is None:
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
        self._show_action("watering", WATERING_SHOW_S)

    def show_planting(self):
        self._show_action("planting", PLANTING_SHOW_S)

    def _show_action_in_tutorial(self, mood, secs):
        """During the tutorial the portrait belongs to Cyril (or Mendel on
        the "your turn" lines): flash the action image for `secs`, then
        put back whatever the dialogue was showing."""
        if getattr(self, "_tut_action", False):
            return
        path = self._path(mood, self._season())
        if not os.path.isfile(path):
            return
        try:
            self._tut_prev = getattr(self.label, "image", None)
            img = safe_image(path)
            self.label.configure(image=img)
            self.label.image = img
            self._tut_action = True
            # Nothing (Cyril, Mendel's tutorial image...) may overwrite it
            # until it is over (see tutorial._portrait_locked).
            self.app._portrait_locked_until = time.monotonic() + secs
            self.app.root.after(int(secs * 1000), self._end_tutorial_action)
        except Exception:
            self._tut_action = False

    def _end_tutorial_action(self):
        self._tut_action = False
        try:
            if not self._tut_owns():
                self.refresh()          # tutorial ended meanwhile
                return
            dlg = getattr(self.app, "_tutorial_dialogue", None)
            if dlg is not None and getattr(dlg, "_speaker", None):
                if getattr(dlg, "_mendel_shown", False):
                    dlg._show_mendel_portrait()
                else:
                    dlg._caption_speaker = None     # force a redraw
                    dlg._apply_speaker_caption(dlg._speaker)
            elif getattr(self, "_tut_prev", None) is not None:
                self.label.configure(image=self._tut_prev)
                self.label.image = self._tut_prev
        except Exception:
            pass

    def _show_action(self, mood, secs):
        if self._garden_only():
            return          # no Mendel in "garden view only"
        if self._tut_owns():
            self._show_action_in_tutorial(mood, secs)
            return
        # Repeated actions don't extend the display; one exact timer
        # (not the 1 s tick) ends it. An action image that is already
        # showing (watering or planting) is left alone.
        if self.mood in _ACTION_MOODS:
            return
        # Missing image for this season -> leave the portrait as it is.
        if not os.path.isfile(self._path(mood, self._season())):
            return
        self.mood = mood
        self._apply()
        self.app._portrait_locked_until = time.monotonic() + secs
        try:
            self.app.root.after(int(secs * 1000), self._end_action)
        except Exception:
            self._watering_until = time.monotonic() + secs

    def _end_action(self):
        if self.mood not in _ACTION_MOODS:
            return
        self.mood = self._next_mood(IDLE_OR_ACTIVE(self))
        self._next_change = time.monotonic() + CHANGE_EVERY_S
        self._apply()

    _end_watering = _end_action

    def _tick(self):
        self._job = None
        try:
            if self._tut_owns():
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
                if self.mood not in _ACTION_MOODS:
                    # Worry sets in (or passes) right away.
                    self.mood = (_WORRY_MOOD if stressed
                                 else _pick(_IDLE_MOODS if self._idle else _ACTIVE_MOODS))
                    self._next_change = now + CHANGE_EVERY_S
            if self.mood in _ACTION_MOODS:
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
