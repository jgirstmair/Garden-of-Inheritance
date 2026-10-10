"""
Tutorial Module

An in-character tutorial sequence ("Lecture" by "Lecture") reached from
the Monastery map's "Friar's quarters" hover region. Unlike an earlier
version of this module, this one does NOT open a separate mini garden
window — it modifies the real, already-running simulator in place: the
player's actual grid, actual GardenEnvironment, actual status/message
bar. Keeping it in its own file still means new lectures can be added
below without touching Garden-of-Inheritance.py — see LECTURES and
start_tutorial().
"""

import json
import math
import os
import random
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

from icon_loader import ICONS_DIR, safe_image

# Fixed filename for the silent "quick save" taken right before the
# tutorial starts, so leaving the tutorial (via the Monastery's "Mendel's
# Garden" region) can restore the player's real garden exactly as it was.
_AUTOSAVE_NAME = "auto-save-for-tutorial"


def _data_dir():
    # icon_loader.py and Garden-of-Inheritance.py both live in the same
    # directory, and both already use os.path.dirname(os.path.abspath(__file__))
    # of that directory as their base — this avoids importing the
    # hyphenated main module just to find "data/".
    return os.path.join(os.path.dirname(ICONS_DIR), "data")


def _autosave_path():
    return os.path.join(_data_dir(), f"garden_{_AUTOSAVE_NAME}.json")


# Tutorial progress save, written once part 1 is over (and refreshed while
# the player waits for their seedlings / when they leave mid-way), so the
# tutorial can be picked up again at part 2 from the Friar's quarters.
_PROGRESS_NAME = "auto-save-tutorial-progress"


def _progress_path():
    return os.path.join(_data_dir(), f"garden_{_PROGRESS_NAME}.json")


def _play_sound_via_app(app, filename):
    """Plays a sound effect using Garden-of-Inheritance.py's own
    _play_sound() (safe to call unconditionally — it no-ops if pygame or
    that specific file isn't available), found through sys.modules
    rather than an "import Garden-of-Inheritance" — same reasoning as
    _data_dir() above: its hyphenated filename isn't importable as a
    normal Python module, but the already-imported module object is
    still reachable this way regardless of its name."""
    try:
        main_mod = sys.modules.get(type(app).__module__)
        play = getattr(main_mod, "_play_sound", None)
        if callable(play):
            play(filename)
    except Exception:
        pass


def _ensure_key_watch(app, sequences):
    """Makes sure each Tk key sequence in `sequences` has a (single,
    permanent) extra root binding that sets app._tutorial_key_pressed —
    but only while app._tutorial_key_watch_active is True, i.e. while a
    line with "wait_for_keys" is showing. Bound once with add="+" so the
    app's own Ctrl+Left/Right speed handlers keep working; deliberately
    never unbound (Tk's unbind(seq, funcid) can strip every binding for
    that sequence on older Pythons, which would kill the real handlers),
    just switched off via the active flag instead."""
    done = getattr(app, "_tutorial_key_watch_seqs", None)
    if done is None:
        done = set()
        app._tutorial_key_watch_seqs = done

    def _on_key(event=None):
        if getattr(app, "_tutorial_key_watch_active", False):
            app._tutorial_key_pressed = True

    for seq in sequences:
        if seq in done:
            continue
        try:
            app.root.bind(seq, _on_key, add="+")
            done.add(seq)
        except Exception:
            pass


def _format_live_readout(app, name):
    """Formats a short, live status string for a "live_readout" line (see
    the LECTURES comment block) — currently just "game_speed", read
    straight off the running app the same way the normal simulator's own
    speed toast does. Added because that toast (GardenApp._toast) writes
    to app.status_var, which the tutorial's rich-text overlay sits
    directly on top of (see _StatusBarDialogue's class docstring) — so
    during the tutorial that toast is rendered but invisible, and the
    player has no way to see the speed they just set with Ctrl+Left/
    Right. Returning this as a short suffix appended to the dialogue
    line itself (see _StatusBarDialogue._set_status) puts that same
    information somewhere it's actually visible."""
    if name == "water_progress":
        targets = [p for p in getattr(app, "_tutorial_dry_targets", None) or []
                   if getattr(p, "alive", True)]
        done = sum(1 for p in targets if int(p.water) >= _water_min(app))
        return f"   [{done}/{len(targets)} watered]"
    if name != "game_speed":
        return ""
    try:
        secs = float(getattr(app, "day_length_s", 0.0))
    except Exception:
        return ""
    try:
        main_mod = sys.modules.get(type(app).__module__)
        real_time_secs = float(getattr(main_mod, "SPEED_REAL_TIME_SECS", 3600.0))
    except Exception:
        real_time_secs = 3600.0
    if abs(secs - real_time_secs) < 1e-6:
        label = "Real Time (1 sec = 1 sec)"
    else:
        label = f"{secs:g}s / simulated hour"
    return f"   [Current pace: {label}]"


# ============================================================================
# Lecture definitions
# ============================================================================
# Add new lectures here. The whole real grid is fresh and open for every
# lecture — no tiles are locked and nothing is fenced off; the player can
# plant wherever they like. starter_seeds are handed to the player as
# actual unplanted seeds (app.available_seeds) rather than already-planted
# plants — the player plants them with the normal "Plant Seed..." flow.
# dialogue is shown one line at a time in the main UI's own status bar.
# Keep each line's text under ~100 characters — split a longer thought
# into two (or more) consecutive entries instead, so a single line never
# needs to wrap.
#
# wait_for (optional): a condition name start_tutorial() checks for AFTER
# the last "dialogue" line is dismissed, before moving on — instead of
# immediately unlocking the sidebar/finishing the lecture, it silently
# waits (no button, no line shown) until the condition holds. Currently
# supported: "all_seeds_planted" (app.available_seeds reaches 0).
# after_wait_dialogue (optional): more (speaker, line) pairs, played once
# wait_for's condition is met — Cyril speaking again once the player has
# actually finished planting. Leave empty for now; add his next lines
# here whenever they're ready.
#
# Each dialogue entry is (speaker, text) or (speaker, text, extra), where
# extra is an optional dict:
#   "highlight_words": substrings of text to render in black instead of
#       the usual red, so they read as "this names something you can
#       click" — the Plant/Plant All actions, a seed count, etc.
#   "highlight_target": one of _HIGHLIGHT_TARGETS below (or omitted) — a
#       real widget to point a large fading arrow at from underneath
#       while this line is showing, so the player's eye actually lands
#       on the thing being described. Cleared (faded out) the moment the
#       player advances past the line.
#   "grant_seeds": adds this many seeds to app.available_seeds the
#       moment this line is shown — used to hand out more starter seeds
#       partway through the dialogue.
#   "pause": True stops this line from auto-advancing to the next one a
#       second after it finishes typing (the default for every line) —
#       use it where it's worth giving the player a moment, such as a
#       line with a "highlight_target" (so they actually have time to
#       look at what the arrow is pointing at) or one right before they
#       need to go and do something, rather than hurrying them along.
#   "wait_for_condition": one of _WAIT_CONDITIONS below — instead of
#       advancing on a timer (or waiting only for a click, if "pause" is
#       also set), the line silently polls this condition once it's
#       finished typing and auto-advances the moment it becomes true.
#       Use this where the next line shouldn't appear until the player
#       has actually done the thing being asked of them, e.g. advancing
#       only once they've planted their first seed rather than after a
#       fixed delay.
#   "mood": 1, 2 or 3 — which portrait Cyril shows for this line
#       (franz_1 explaining [default], franz_2 smiling after a success,
#       franz_3 idle). He also drops to franz_3 by himself after 8s of
#       waiting on a line, and now and then at random.
#   "wait_for_hold_ms": only meaningful alongside "wait_for_condition" —
#       requires the condition to stay continuously true for this many
#       milliseconds (rather than advancing the instant it first becomes
#       true), e.g. making the player actually land on and hold a given
#       game speed for a few seconds rather than just flick past it.
#   "portrait": "mendel" shows Mendel (instead of Cyril) in the portrait
#       slot for this line — used where the player has to act.
#   "unlock_buttons": a list of app button attribute names opened for good
#       from this line on (everything else stays blocked until explained).
#   "enable_buttons": a list of app attribute names of (sidebar) buttons
#       to switch on while this line shows, e.g. ["water_btn"].
#   "set_water": N sets every living plant's water to N % (and clears the
#       sky / moves to working hours) the first time the line is shown.
#       "dry_count": K dries only K random plants instead of all.
#       Pair with "wait_for_condition": "targets_watered" (just the dried
#       ones) or "plants_watered" (every plant), and optionally
#       "live_readout": "water_progress" for an "x/n watered" counter.
#   "auto_advance_ms": overrides how long a (non-paused) line stays up
#       after it finishes typing before advancing by itself (default
#       AUTO_ADVANCE_MS).
#   "no_skip": True hides the "▶" button on this line and ignores any
#       manual attempt to advance it, so the only way past is its
#       "wait_for_condition" being met — use together with that key.
#   "wait_for_keys": a tuple of Tk key sequences (e.g. "<Control-Left>")
#       to watch for while this line is showing; pressing any of them
#       satisfies the "key_pressed" wait condition below. Use together
#       with "wait_for_condition": "key_pressed".
#   "live_readout": one of _format_live_readout's names (currently only
#       "game_speed") — once the line has finished typing, appends a
#       short, continuously-updating suffix to it (e.g. the current
#       simulation speed) so the player can see the effect of something
#       they're doing right now (like tapping Ctrl+Left/Right) without
#       that feedback getting lost — the normal speed toast writes to
#       the same status bar the tutorial's dialogue text covers, so it's
#       rendered but never actually seen while a line is showing.

LECTURES = [
    {
        "id": 1,
        "title": "Arrival",
        "starter_seeds": 9,        # handed out as seeds, not pre-planted
        "dialogue": [
            ("Cyril",
             "Welcome to St. Thomas, young novice. I am Cyril Franz Napp, "
             "abbot of this monastery.",
             {"highlight_words": ["Cyril Franz Napp"]}),
            ("Cyril",
             "Come, I will show you around and guide you through your "
             "first duties here."),
            ("Cyril",
             "I see you have nine pea seeds left from last year.",
             {"highlight_words": ["nine"], "highlight_target": "seed_count",
              "pause": True}),
            ("Cyril",
             "Good! They are quite ready to be planted."),
            ("Cyril",
             "Choose »Plant«, the button at your left, to plant your first seeds.",
             # Waits for the player to actually plant via the Plant
             # button (rather than a fixed delay) before moving on —
             # see "wait_for_condition" above and _WAIT_CONDITIONS below.
             {"highlight_words": ["Plant"], "highlight_target": "plant_button",
              "unlock_buttons": ["plant_seeds_btn"],
              "pause": True, "no_skip": True,
              "wait_for_condition": "first_seed_planted"}),
            ("Cyril",
             "That lets you pick exactly where, and how many, seeds "
             "to plant at once.",
             # Holds here (same "all_seeds_planted" check used again
             # further down — it's really just "available_seeds is back
             # to 0", true at whatever point in the dialogue it's asked)
             # until all nine starter seeds are actually in the ground,
             # so the second batch below isn't handed out while the
             # first one is still only partly planted.
             {"pause": True, "no_skip": True,
              "wait_for_condition": "all_seeds_planted"}),
            ("Cyril",
             "Here, take a few more peas to sow as well.",
             # 13 more on top of the original 9 starter seeds, so
             # "sow everything at once" (next line) actually has a
             # decent number of seeds behind it. Shown BEFORE that next
             # line (rather than after, like it used to be) so the
             # seed count has already gone up by the time "Plant All"
             # is explained — otherwise the explanation would be
             # talking about sowing a pile of seeds the player hasn't
             # actually been given yet. Auto-advances like any other
             # explanatory line — no "pause" here, since (unlike before)
             # it's no longer the last line before the silent
             # wait_for_all_seeds_planted wait begins.
             {"grant_seeds": 13}),
            ("Cyril",
             "You can also right-click anywhere in the garden and select "
             "»Plant All« to sow a group of seeds at once.",
             # No highlight_target here on purpose — "Plant All" only
             # lives in a right-click context menu, not a fixed button,
             # so there's nothing fixed to point the arrow at (yet).
             #
             # "pause" keeps "▶" on screen so the player can re-read this
             # (or move on manually once they're done), but it's ALSO
             # given its own wait_for_condition — "all_seeds_planted",
             # same name/check as the lecture-level "wait_for" below —
             # so finishing the planting (by "Plant", "Plant All", or
             # any mix of the two) advances past this line the instant
             # every starter seed is in the ground, without making the
             # player click "▶" first just to let that check start.
             # The lecture-level "wait_for" below still runs again right
             # after (via _on_dialogue_dismissed → _wait_for_all_seeds_
             # planted) as a harmless no-op fallback: available_seeds is
             # already 0 by then whenever THIS wait is what fired, so it
             # resolves immediately; it only actually has to poll if the
             # player clicked "▶" manually before finishing planting.
             {"highlight_words": ["Plant All"], "pause": True, "no_skip": True,
              "wait_for_condition": "all_seeds_planted"}),
        ],
        "wait_for": "all_seeds_planted",
        "after_wait_dialogue": [
            ("Cyril",
             "Nicely done! You're quite the natural gardener, I must say.",
             {"mood": 2}),
            ("Cyril",
             "I can hardly wait to see something spring from the soil!",
             {"mood": 2}),
            ("Cyril",
             "Now, this may take some time. So let me "
             "share with you a true gardener's secret!"),
            ("Cyril",
             ("Hold Command (⌘) and tap the ← or → arrow key to slow "
              if sys.platform == "darwin" else
              "Hold Ctrl and tap the < or > key to slow ")
             + "down or speed up time.",
             # Waits for the player to actually press Ctrl+Left or
             # Ctrl+Right (see "wait_for_keys" above) before moving on,
             # with no "▶" to skip past it ("no_skip").
             {"highlight_words": (["Command", "⌘", "← or → arrow key"]
                                 if sys.platform == "darwin" else ["Ctrl", "< or >"]),
              "pause": True, "no_skip": True,
              "wait_for_keys": (("<Control-Left>", "<Control-Right>",
                                "<Command-Left>", "<Command-Right>")
                               if sys.platform == "darwin" else
                               ("<Control-Left>", "<Control-Right>")),
              "wait_for_condition": "key_pressed"}),
            ("Cyril",
             "Excellent, now set the pace to 1 sec = one hour.",
             # Waits for the player to actually land on — and hold,
             # for a few seconds, not just pass through on the way to
             # some other speed — the "1 second = 1 simulated hour"
             # preset (SPEED_PRESETS' "1" in Garden-of-Inheritance.py),
             # same Ctrl+Left/Right trick just explained above. "no_skip"
             # hides "▶" so it can't be clicked past until the pace is
             # actually right.
             {"highlight_words": ["1 sec = one hour"],
              "pause": True, "no_skip": True,
              "wait_for_condition": "real_time_speed_set",
              "wait_for_hold_ms": 3000, "live_readout": "game_speed"}),
            ("Cyril",
             "Splendid! Isn’t it magical how time seems to fly?",
             {"mood": 2}),
            ("Cyril",
             "But we all need time to sleep, study, pray, and eat."),
            ("Cyril",
             "So you may only tend to the garden at a reasonable hour."),
            ("Cyril",
             "I shall grant you access from 6 a.m. until 7 p.m.",
             {"highlight_words": ["6 a.m.", "7 p.m."]}),
            ("Cyril",
             "Oh, and should you feel a little overwhelmed by the passing of time,"),
            ("Cyril",
             "simply press Space to pause for a moment.",
             {"highlight_words": ["Space"], "highlight_target": "pause_button"}),
            ("Cyril",
             "That will be all for now. I think you have learned quite a lot!",
             {"mood": 2}),
            ("Cyril",
             "Now, tend to your plants until you see the first little "
             "seedlings emerge from the soil.",
             {"highlight_words": ["seedlings"]}),
            ("Cyril",
             "Once they do, I come and find you, and I shall teach you more.",
             # Last line of lecture 1 — no "▶": it ends by itself 5s
             # after it finishes typing, which hands control back
             # (start_tutorial's _on_finish) and puts up franz_0.
             {"auto_advance_ms": 5000}),
        ],
    },
]

# Part 2 — Cyril returns once every planted seed has become a seedling
# (see _watch_for_seedlings / _play_lecture_2). More lines can follow here.
LECTURE_2_DIALOGUE = [
    # 5 random plants dry out to 20 % (and the sun comes out for the whole
    # watering part) right as the lecture starts, so they are clearly
    # thirsty well before Cyril mentions it.
    ("Cyril", "Ah, there they are! Your first little seedlings.",
     {"mood": 2, "highlight_words": ["seedlings"],
      "set_water": 20, "dry_count": 5}),
    ("Cyril", "Occasionally, these little fellows will need some water.",
     {"pause": True}),
    ("Cyril", "Look, a few of them are already thirsty!",
     {"highlight_words": ["thirsty"]}),
    ("Cyril", "You’ve probably already noticed the little water drop icon beside each plant.",
     {"highlight_words": ["water drop icon"], "auto_advance_ms": 4500}),
    ("Cyril", "Its color tells you whether a plant is thirsty...",
     {"highlight_words": ["color", "thirsty"], "auto_advance_ms": 4000}),
    ("Cyril", "...or has had quite enough for the day!",
     {"highlight_words": ["quite enough"]}),
    # Mendel's turn: waits (no ▶) until all 5 dried plants are watered,
    # with a live "x/5 watered" count.
    ("Cyril", "Now, select a thirsty plant and water it.",
     {"highlight_words": ["Water"], "highlight_target": "water_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["water_btn"], "live_readout": "water_progress",
      "wait_for_condition": "targets_watered"}),
    # Now every plant dries out to 35 %.
    ("Cyril", "What a glorious sunny day!",
     {"set_water": 35, "auto_advance_ms": 3000, "mood": 2}),
    ("Cyril", "Well, I suppose most seedlings could use some watering right now.",
     {"auto_advance_ms": 4000}),
    # Waits for Water All; then time goes back to 1 sec = 1 hour.
    ("Cyril", "Go on, then, tend to them all at once.",
     {"highlight_words": ["all at once"],
      "unlock_buttons": ["water_all_btn"],
      "highlight_target": "water_all_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "live_readout": "water_progress",
      "wait_for_condition": "plants_watered"}),
    ("Cyril", "Very good! Keep the soil moist, but never soaking wet!",
     {"highlight_words": ["moist", "never soaking wet"], "pause": True}),
    ("Cyril", "Naturally, you’ll want to inspect your plants from time to "
     "time...",
     {"highlight_words": ["inspect"]}),
    ("Cyril", "...see how they’re doing and what traits they might have "
     "revealed already!"),
    # Waits until the player has actually inspected a plant.
    ("Cyril", "You can inspect each plant with the button above, or press I.",
     {"highlight_words": ["button", "I"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"],
      "wait_for_condition": "plant_inspected"}),
    ("Cyril", "Didn’t you mention last supper that you were particularly interested in seven traits?",
     {"highlight_words": ["seven traits"], "auto_advance_ms": 4000}),
    ("Cyril", "Anyway, we can talk about that later!",
     {"auto_advance_ms": 4000}),
    ("Cyril", "I’ll be back when your peas have grown a little taller.",
     {"auto_advance_ms": 5000}),
]


# Part 3 — Cyril returns once the first 3 plants are budding (see
# _watch_for_budding / _play_lecture_3). Placeholder lines for now; Fast
# Forward is handed back at the end of this part.
LECTURE_3_DIALOGUE = [
    ("Cyril", "Look at that, Gregor! The first buds are showing.",
     {"mood": 2, "highlight_words": ["buds"]}),
    ("Cyril", "Before long, these will open into beautiful flowers.",
     {"highlight_words": ["flowers"]}),
    ("Cyril", "Waiting for a garden to grow takes patience...",
     {"auto_advance_ms": 4000}),
    ("Cyril", "...so you may hurry the days along even faster with Fast Forward.",
     {"highlight_words": ["Fast Forward"], "highlight_target": "fast_button",
      "unlock_buttons": ["fast_btn"]}),
    ("Cyril", "Try it. I’ll be back when the first flowers open.",
     {"auto_advance_ms": 5000}),
]


# Part 4 — the first 3 plants are flowering. Placeholder lines.
LECTURE_4_DIALOGUE = [
    ("Cyril", "Gregor, come and see — the first flowers have opened!",
     {"mood": 2, "highlight_words": ["flowers"]}),
    ("Cyril", "Remember, a pea flower usually pollinates itself before it even opens.",
     {"highlight_words": ["pollinates itself"]}),
    ("Cyril", "Soon the petals will fall and little pods will form.",
     {"highlight_words": ["pods"]}),
    ("Cyril", "I’ll look in again when the first pods appear.",
     {"auto_advance_ms": 5000}),
]

# Part 5 — the first 3 plants are forming pods (not ripe yet).
LECTURE_5_DIALOGUE = [
    ("Cyril", "Look, the first pods are growing!",
     {"mood": 2, "highlight_words": ["pods"]}),
    ("Cyril", "They are still green and soft — the peas inside are not ripe yet.",
     {"highlight_words": ["not ripe yet"]}),
    # Waits until the player has inspected a plant.
    ("Cyril", "Go on, take a closer look: inspect one of the plants with pods.",
     {"highlight_words": ["inspect"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"],
      "wait_for_condition": "plant_inspected"}),
    ("Cyril", "You can see the pods in there, but they can’t be harvested yet.",
     {"highlight_words": ["can’t be harvested yet"], "pause": True}),
    ("Cyril", "Be patient until the pods have dried and matured.",
     {"highlight_words": ["dried and matured"]}),
    ("Cyril", "I’ll come back when they are ready to harvest.",
     {"auto_advance_ms": 5000}),
]

# Part 6 — the first 3 plants carry mature pods.
LECTURE_6_DIALOGUE = [
    ("Cyril", "Splendid, Gregor! The first pods are ripe, though some plants need a little more time.",
     {"mood": 2, "highlight_words": ["ripe"]}),
    ("Cyril", "Select a plant with ripe pods and press Harvest to gather its seeds.",
     {"highlight_words": ["Harvest"], "highlight_target": "harvest_button",
      "unlock_buttons": ["harvest_btn"], "pause": True}),
    # Waits until another plant has been inspected...
    ("Cyril", "You can also harvest right in the inspection window. Try it!",
     {"highlight_words": ["inspection window"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"],
      "wait_for_condition": "plant_inspected"}),
    # ...and until at least one pod has been harvested there.
    ("Cyril", "Now harvest its pods: click a single pod, or Harvest All.",
     {"highlight_words": ["Harvest All"], "highlight_target": "inspector_harvest_button",
      "highlight_late": True,
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "pod_harvested"}),
    ("Cyril", "Every seed you gather can be sown again next spring.",
     {"highlight_words": ["sown again"], "auto_advance_ms": 5000}),
]


# ============================================================================
# Highlighting: a fading arrow pointing at a real widget, from below
# ============================================================================

# Maps a lecture line's "highlight_target" name to the actual widget on
# the running app it should point at. Looked up lazily (not at import
# time) since these widgets don't exist yet when this module is loaded.
_HIGHLIGHT_TARGETS = {
    "seed_count": lambda app: getattr(app, "seed_label", None),
    "plant_button": lambda app: getattr(app, "plant_seeds_btn", None),
    "water_button": lambda app: getattr(app, "water_btn", None),
    "water_all_button": lambda app: getattr(app, "water_all_btn", None),
    "inspect_button": lambda app: getattr(app, "inspect_btn", None),
    "pause_button": lambda app: getattr(app, "pause_btn", None),
    "fast_button": lambda app: getattr(app, "fast_btn", None),
    "harvest_button": lambda app: getattr(app, "harvest_btn", None),
    # "Harvest All" inside the plant inspector window (only while open).
    "inspector_harvest_button": lambda app: _live_widget(getattr(app, "_inspector_harvest_btn", None)),
}


def _live_widget(w):
    try:
        if w is not None and w.winfo_exists() and w.winfo_ismapped():
            return w
    except Exception:
        pass
    return None


# Targets whose arrow sits to the right of the widget and points left;
# everything else sits below the widget and points up.
_ARROW_SIDES = {"plant_button": "right", "water_all_button": "right",
                "inspect_button": "right"}


# Maps a lecture line's "wait_for_condition" name to a function that
# checks whether it's been satisfied yet. Each function takes (app,
# baseline) — baseline is whatever app.available_seeds was the moment
# the line started showing, captured in _StatusBarDialogue._show_line —
# and returns True once the player has done the thing being asked.
# Polled every 400ms (see _StatusBarDialogue._poll_wait_condition),
# same cadence as _wait_for_all_seeds_planted below.
def _water_min(app):
    return int(getattr(app, "_tutorial_water_min", 51))


def _tutorial_force_sun(app):
    """Clear sky and working hours, so rain or the evening 'night gate'
    can't block (or replace) the watering the player is asked to do."""
    try:
        g = app.garden
        changed = False
        if getattr(g, "weather_lock", None) != "☀️":
            # GardenEnvironment.weather returns this instead of the real
            # (hourly recomputed) weather until the lock is cleared, so
            # rain can't start between our checks.
            g.weather_lock = "☀️"
            changed = True
        try:
            hour = int(g.clock_hour) % 24
        except Exception:
            hour = 9
        if hour >= 17 or hour < 6:
            from garden import PHASES
            g.clock_hour = 9
            g.phase_index = 0
            g.phase = PHASES[0]
            changed = True
        if changed:
            try:
                app.render_all()
            except Exception:
                pass
    except Exception:
        pass


def _lock_sun_weather(app):
    """Clear sky for the planting part (part 1 and the wait for the
    seedlings): only the weather is pinned — the clock and speed are left
    alone. Released again by _release_sun (end of the watering part, or
    when the tutorial is left)."""
    try:
        g = app.garden
        if getattr(g, "weather_lock", None) != "☀️":
            g.weather_lock = "☀️"
            app.render_all()
    except Exception:
        pass


def _tutorial_autowater(app, on):
    """Part 1 (no rain, nothing for the player to water yet): the game
    waters the plants itself (the "Auto-water" setting). Part 2 turns it
    off so the player can do the watering. The player's own setting is
    remembered and put back when the tutorial is left."""
    try:
        var = getattr(app, "auto_water_normal", None)
        if var is None:
            return
        if getattr(app, "_tutorial_autowater_prev", None) is None:
            app._tutorial_autowater_prev = bool(var.get())
        var.set(bool(on))
    except Exception:
        pass


def _tutorial_autowater_restore(app):
    try:
        prev = getattr(app, "_tutorial_autowater_prev", None)
        if prev is not None:
            app.auto_water_normal.set(bool(prev))
        app._tutorial_autowater_prev = None
    except Exception:
        pass


def _release_sun(app):
    """Gives the real weather back (end of the watering part / tutorial)."""
    app._tutorial_keep_sun = False
    try:
        if getattr(app.garden, "weather_lock", None):
            app.garden.weather_lock = None
            app.render_all()
    except Exception:
        pass


def _start_sun_keeper(app):
    """Holds a clear sky (and working hours) every half second for the
    whole watering part of lecture 2, not just while a line is waiting."""
    app._tutorial_keep_sun = True
    if getattr(app, "_tutorial_sun_job", None) is not None:
        return

    def _tick():
        app._tutorial_sun_job = None
        if not getattr(app, "_tutorial_active", False):
            _release_sun(app)
            return
        if not getattr(app, "_tutorial_keep_sun", False):
            return
        _tutorial_force_sun(app)
        # Real time from 9:00 on, so the player isn't rushed; decided
        # here (not only while a line waits) so it can't be missed.
        if getattr(app, "_tutorial_water_speed", None) is None:
            try:
                hour = int(app.garden.clock_hour) % 24
            except Exception:
                hour = 9
            if 9 <= hour < 17:
                _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)
                app._tutorial_water_speed = "slow"
        try:
            app._tutorial_sun_job = app.root.after(500, _tick)
        except Exception:
            pass

    _tick()


def _tutorial_dry_out_plants(app, level, count=None):
    """Sets living plants' water to `level` (and clears the sky): all of
    them, or `count` randomly chosen ones. The affected plants are kept
    in app._tutorial_dry_targets for the 'x/n watered' check."""
    _tutorial_autowater(app, False)    # the player waters these himself
    app._tutorial_water_speed = None   # re-arm the slow-down for this step
    targets = []
    try:
        living = [t.plant for t in app._all_plot_tiles()
                  if t.plant is not None and getattr(t.plant, "alive", True)]
        if count and count < len(living):
            targets = random.sample(living, int(count))
        else:
            targets = living
        for p in targets:
            p.water = int(level)
    except Exception:
        pass
    app._tutorial_dry_targets = targets
    _start_sun_keeper(app)
    # Watered = out of the "dry" band (> 25 %) after a handful of plants
    # were dried hard; 51 %+ (evenly moist) when everything was dried.
    app._tutorial_water_min = 26 if count else 51
    _tutorial_force_sun(app)
    try:
        app.render_all()
    except Exception:
        pass


def _plants_watered(app, baseline=None):
    """True once no living plant is dry any more (water above the
    'slightly moist' band; overwatered plants don't hold it up). Also keeps the sun out while
    the player is being asked to water."""
    plants = [t.plant for t in app._all_plot_tiles()
              if t.plant is not None and getattr(t.plant, "alive", True)]
    ok = all(int(p.water) >= _water_min(app) for p in plants)   # no dry plant left (overwatered ones are fine)
    if ok:
        # Done: back to 1 sec = 1 hour; the dialogue carries on by itself.
        if getattr(app, "_tutorial_water_speed", None) != "fast":
            _tutorial_set_speed(app, 1.0)
            app._tutorial_water_speed = "fast"
            _release_sun(app)   # the weather is free again
    elif getattr(app, "_tutorial_water_speed", None) is None:
        # Time runs at 1 sec = 1 hour until the working day is reached
        # (9:00 or later); then real time, so the player isn't rushed.
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        if 9 <= hour < 17:
            _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)
            app._tutorial_water_speed = "slow"
    return ok


def _targets_watered(app, baseline=None):
    """True once every plant the step dried out has been watered back
    (no speed change here — the pace only speeds up after the last step)."""
    targets = [p for p in getattr(app, "_tutorial_dry_targets", None) or []
               if getattr(p, "alive", True)]
    ok = all(int(p.water) >= _water_min(app) for p in targets)
    if not ok and getattr(app, "_tutorial_water_speed", None) is None:
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        if 9 <= hour < 17:
            _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)
            app._tutorial_water_speed = "slow"
    return ok


def _tutorial_set_speed(app, secs):
    try:
        app._set_day_length(secs)
        app.day_length_s = secs
    except Exception:
        pass


_WAIT_CONDITIONS = {
    "plants_watered": _plants_watered,
    "targets_watered": _targets_watered,
    # Set by GardenApp._on_inspect_unified when a plant was inspected.
    "plant_inspected": lambda app, baseline: bool(getattr(app, "_tutorial_inspected", False)),
    # At least one pod harvested since the line appeared (the seed bag
    # grew; baseline = its size then).
    "pod_harvested": lambda app, baseline: len(getattr(app, "harvest_inventory", []) or []) > int(baseline or 0),
    "first_seed_planted": lambda app, baseline: getattr(app, "available_seeds", baseline) < baseline,
    "all_seeds_planted": lambda app, baseline: getattr(app, "available_seeds", 0) <= 0,
    # Set by the key watcher (see _ensure_key_watch) when the line's
    # "wait_for_keys" combo is pressed.
    "key_pressed": lambda app, baseline: bool(getattr(app, "_tutorial_key_pressed", False)),
    # True while the game is set to "1 second = 1 simulated hour" — the
    # Ctrl+Left/Right default/"1s" preset (see SPEED_PRESETS in
    # Garden-of-Inheritance.py). Paired with "wait_for_hold_ms" on its
    # LECTURES line so the player has to actually land on and hold this
    # speed for a few seconds, not just flick through it on the way to
    # somewhere else.
    "real_time_speed_set": lambda app, baseline: abs(float(getattr(app, "day_length_s", 0.0)) - 1.0) < 1e-6,
}


def _clear_dialogue_arrow(dlg, fade=True):
    """Clears whatever _ArrowHighlight a _StatusBarDialogue (`dlg`) is
    currently showing, if any, and undoes the click-dismiss binding
    _StatusBarDialogue._show_line sets up alongside it. Shared by the
    dialogue's own methods and the module-level teardown helpers below,
    so there's one place that knows how to fully undo an arrow rather
    than each caller repeating the same two steps."""
    cleanup = getattr(dlg, "_arrow_click_cleanup", None)
    if cleanup is not None:
        try:
            cleanup()
        except Exception:
            pass
        dlg._arrow_click_cleanup = None
    arrow = getattr(dlg, "_active_arrow", None)
    if arrow is not None:
        try:
            if fade:
                arrow.fade_out()
            else:
                arrow.destroy()
        except Exception:
            pass
        dlg._active_arrow = None


def _lerp_color(c1, c2, t):
    """Linearly interpolates between two "#RRGGBB" colors at t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


class _ArrowGroup:
    """Several _ArrowHighlight arrows handled as one (a line may point at
    more than one button at the same time)."""

    def __init__(self, arrows):
        self.arrows = list(arrows)

    def fade_out(self, on_done=None):
        for a in self.arrows:
            try:
                a.fade_out()
            except Exception:
                pass
        if callable(on_done):
            on_done()

    def destroy(self):
        for a in self.arrows:
            try:
                a.destroy()
            except Exception:
                pass


class _ArrowHighlight:
    """
    A large "⬆" with a thick black outline, pulsing between crimson red
    and chestnut brown on a continuous loop, just below a real widget
    (the seed count, the Plant button) to draw the player's eye to it,
    until fade_out() ends it for good once the line is dismissed. An
    earlier version faded the glyph in and out against transparency
    instead of cycling between two solid colors — replaced because a
    color pulse reads more clearly than a glyph disappearing entirely.

    Lives in its own small borderless Toplevel positioned with absolute
    screen coordinates, so it's never clipped by a tightly-sized
    toolbar row the target happens to sit in — and, on Windows,
    wm_attributes("-transparentcolor", ...) makes that window's
    background color fully see-through, so only the glyph (plus its
    outline) is visible rather than a solid colored box around it. That
    attribute is Windows-only; elsewhere (macOS/Linux) Tk simply
    ignores or rejects it, and the window falls back to showing as a
    plain rectangle in the key color instead of a transparent one.

    A Canvas (not a Label) draws the glyph here, since a Label's text
    can only ever be one flat color — the outline is faked by drawing
    the glyph several times in black at small offsets all around the
    center, then the actual (color-cycling) glyph on top of those.
    """

    STEPS = 10
    STEP_MS = 120  # 3x slower than the previous fade's 40ms-per-step
    FONT_SIZE = 78
    OUTLINE_THICKNESS = 6  # a thick, clearly-visible black outline
    COLOR_A = "#DC143C"  # crimson
    COLOR_B = "#954535"  # chestnut brown

    def __init__(self, app, target_widget, side="bottom"):
        self.app = app
        self.target = target_widget
        self.side = side      # "bottom" (points up) or "right" (points left)
        self._job = None
        self._alive = True
        self._step = 0
        self._direction = 1

        # An unlikely, very specific color used only as the
        # "-transparentcolor" key — chosen so it's never a color
        # anything else on screen would plausibly use, and never one
        # of the outline/glyph colors above.
        self._key = "#123456"

        self.win = tk.Toplevel(app.root)
        try:
            self.win.overrideredirect(True)
        except Exception:
            pass
        try:
            self.win.configure(bg=self._key)
        except Exception:
            pass
        # Deliberately NOT forced "-topmost" — it used to sit above
        # every other window, including popups/menus the app itself
        # opens (like the Choose Seeds dialog "Plant" opens), burying
        # them under the arrow. Without it, normal window stacking
        # applies: it renders above the main window (being a Toplevel
        # created after it) but a dialog or menu opened afterward still
        # comes to the front over it, same as any other window would.
        bg_color = self._key
        if sys.platform == "darwin":
            # macOS has no -transparentcolor; it uses a real transparent
            # window with the special "systemTransparent" color instead.
            try:
                self.win.wm_attributes("-transparent", True)
                self.win.configure(bg="systemTransparent")
                bg_color = "systemTransparent"
            except Exception:
                pass
        else:
            try:
                self.win.wm_attributes("-transparentcolor", self._key)
            except Exception:
                # Not supported on this platform — falls back to a plain,
                # non-transparent key-colored rectangle behind the arrow.
                pass

        self.canvas = tk.Canvas(
            self.win, bg=bg_color, highlightthickness=0, bd=0,
            cursor="arrow",
        )
        self.canvas.pack()

        self._build_items()
        self._reposition()
        self._build_ring()
        self._start_cycling()

    def _build_items(self):
        # Drawn as a polygon (not a font glyph) so it looks identical on
        # every platform — the "⬆" glyph depended on Segoe UI, which
        # macOS doesn't have, and rendered as an odd fallback shape.
        o = self.OUTLINE_THICKNESS
        pad = o + 4
        aw, ah = 62, 96          # arrow width / height
        head_h = int(ah * 0.45)
        shaft_hw = int(aw * 0.19)
        if self.side == "right":
            # Sits to the right of the target, pointing left (←).
            w, h = ah + pad * 2, aw + pad * 2
            self.canvas.configure(width=w, height=h)
            cy = h // 2
            left, right = pad, pad + ah
            pts = [
                left, cy,                             # tip
                left + head_h, cy - aw // 2,
                left + head_h, cy - shaft_hw,
                right, cy - shaft_hw,
                right, cy + shaft_hw,
                left + head_h, cy + shaft_hw,
                left + head_h, cy + aw // 2,
            ]
        else:
            w, h = aw + pad * 2, ah + pad * 2
            self.canvas.configure(width=w, height=h)
            cx = w // 2
            top, bottom = pad, pad + ah
            pts = [
                cx, top,                              # tip
                cx + aw // 2, top + head_h,           # right head corner
                cx + shaft_hw, top + head_h,
                cx + shaft_hw, bottom,
                cx - shaft_hw, bottom,
                cx - shaft_hw, top + head_h,
                cx - aw // 2, top + head_h,           # left head corner
            ]
        self._main_id = self.canvas.create_polygon(
            *pts, fill=self.COLOR_A, outline="black",
            width=o, joinstyle="round",
        )

    def _reposition(self):
        try:
            self.target.update_idletasks()
            self.win.update_idletasks()
            if self.side == "right":
                x = self.target.winfo_rootx() + self.target.winfo_width() + 8
                h = self.win.winfo_reqheight()
                y = (self.target.winfo_rooty()
                     + self.target.winfo_height() // 2 - h // 2)
                self.win.geometry(f"+{x}+{y}")
                return
            x = self.target.winfo_rootx() + self.target.winfo_width() // 2
            y = self.target.winfo_rooty() + self.target.winfo_height() + 8
            w = self.win.winfo_reqwidth()
            self.win.geometry(f"+{x - w // 2}+{y}")
        except Exception:
            pass

    RING_THICKNESS = 3

    def _build_ring(self):
        """Four thin borderless bars just outside the target, pulsing in
        step with the arrow, so the pointed-at control is outlined too.
        Bars (not one big overlay) so nothing ever covers the widget and
        clicks still reach it."""
        self._ring = []
        try:
            t = self.RING_THICKNESS
            tg = self.target
            tg.update_idletasks()
            x, y = tg.winfo_rootx(), tg.winfo_rooty()
            w, h = tg.winfo_width(), tg.winfo_height()
            rects = [
                (x - t, y - t, w + 2 * t, t),        # top
                (x - t, y + h, w + 2 * t, t),        # bottom
                (x - t, y, t, h),                    # left
                (x + w, y, t, h),                    # right
            ]
            for rx, ry, rw, rh in rects:
                bar = tk.Toplevel(self.app.root)
                try:
                    bar.overrideredirect(True)
                except Exception:
                    pass
                bar.configure(bg=self.COLOR_A)
                bar.geometry(f"{rw}x{rh}+{rx}+{ry}")
                self._ring.append(bar)
        except Exception:
            pass

    def _set_step(self, step):
        self._step = max(0, min(self.STEPS, step))
        try:
            color = _lerp_color(self.COLOR_A, self.COLOR_B, self._step / self.STEPS)
            self.canvas.itemconfigure(self._main_id, fill=color)
            for bar in getattr(self, "_ring", []):
                bar.configure(bg=color)
        except Exception:
            self._alive = False

    def _cancel_job(self):
        if self._job is not None:
            try:
                self.app.root.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _start_cycling(self):
        self._cancel_job()

        def _tick():
            if not self._alive:
                return
            self._set_step(self._step + self._direction)
            if not self._alive:
                return
            if self._step >= self.STEPS:
                self._direction = -1
            elif self._step <= 0:
                self._direction = 1
            self._job = self.app.root.after(self.STEP_MS, _tick)

        _tick()

    def fade_out(self, on_done=None):
        # Nothing left to animate out to (the glyph cycles between two
        # solid colors now, rather than fading to transparent), so this
        # just stops the loop and removes the window outright.
        self.destroy()
        if callable(on_done):
            on_done()

    def destroy(self):
        self._alive = False
        self._cancel_job()
        for bar in getattr(self, "_ring", []):
            try:
                bar.destroy()
            except Exception:
                pass
        self._ring = []
        try:
            self.win.destroy()
        except Exception:
            pass


# ============================================================================
# Rich (multi-color) status text — overlays the real status_msg Label
# ============================================================================
# app.status_msg is a plain tk.Label, which can only show one color for
# its whole text — not enough to pick out "Plant"/"Plant All"/a seed
# count in black against the rest of a line's red. This overlays a small
# read-only Text widget, styled to look identical, directly on top of it
# (same parent, same bounds) only while tutorial dialogue is showing;
# it's hidden the rest of the time so toasts/etc. keep using the plain
# Label underneath exactly as before.

def _ensure_rich_status_widget(app):
    existing = getattr(app, "_tutorial_rich_status", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                return existing
        except Exception:
            pass
    try:
        font = app.status_msg.cget("font")
    except Exception:
        font = ("Segoe UI", 16, "bold")
    try:
        bg = app.status_msg.cget("bg")
    except Exception:
        bg = "#dcdcdc"
    try:
        padx = int(app.status_msg.cget("padx"))
        pady = int(app.status_msg.cget("pady"))
    except Exception:
        padx, pady = 6, 4

    txt = tk.Text(
        app.status_msg_row, font=font, bg=bg, wrap="word",
        relief="groove", bd=1, padx=padx, pady=pady,
        highlightthickness=0, cursor="arrow", takefocus=0,
    )
    txt.tag_configure("base")
    txt.tag_configure("normal", foreground="#c01818")
    txt.tag_configure("highlight", foreground="black")
    txt.configure(state="disabled")

    def _on_click(event=None):
        dlg = getattr(app, "_tutorial_dialogue", None)
        if dlg is not None:
            try:
                dlg._on_text_clicked()
            except Exception:
                pass
        return "break"      # no text selection / cursor games

    txt.bind("<Button-1>", _on_click)
    app._tutorial_rich_status = txt
    return txt


def _show_rich_status_widget(app):
    txt = _ensure_rich_status_widget(app)
    # Stretched to exactly cover status_msg_row (matching the real
    # status_msg Label's own fill="both"/expand=True sizing) rather than
    # a shorter, vertically-centered band — a shorter band left slivers
    # of the real Label (and its own matching groove border) visible
    # above/below it, along its left and right edges, which read as a
    # stray grey margin around the dialogue text. Fully covering it
    # means our own border (see _ensure_rich_status_widget) is the only
    # one ever visible, and _center_text_vertically below recenters the
    # single line of text within that full height instead.
    txt.place(x=0, y=0, relwidth=1, relheight=1)
    try:
        txt.tkraise()
    except Exception:
        pass
    _center_text_vertically(txt)
    return txt


def _center_text_vertically(txt):
    """Vertically centers the (normally single-line) text within the
    overlay's full height by padding above it with the "base" tag's
    spacing1 — Text widgets otherwise always start content flush at the
    top, which looked visibly misaligned against the "next"/"back"
    buttons (positioned at the overlay's vertical center) once the
    overlay was stretched to the full row height rather than a
    shorter, pre-centered band."""
    try:
        txt.update_idletasks()
        font = tkfont.Font(font=txt.cget("font"))
        line_h = font.metrics("linespace")
        pady = int(txt.cget("pady") or 0)
        interior_h = max(0, txt.winfo_height() - 2 * pady)
        extra = max(0, interior_h - line_h)
        txt.tag_configure("base", spacing1=extra // 2)
    except Exception:
        pass


def _hide_rich_status_widget(app):
    txt = getattr(app, "_tutorial_rich_status", None)
    if txt is None:
        return
    try:
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.configure(state="disabled")
    except Exception:
        pass
    try:
        txt.place_forget()
    except Exception:
        pass


def _set_rich_status_text(app, text, highlight_words, left_gutter=0):
    """Renders `text` into the rich status overlay, coloring any of
    highlight_words (matched longest-first so e.g. "Plant All" doesn't
    get swallowed by a shorter "Plant" rule) in black and everything
    else in the usual red.

    left_gutter (pixels, optional) reserves blank space before the
    first character via the "base" tag's lmargin1 — used while the "◀"
    back button is showing, so the text doesn't start underneath it."""
    txt = _show_rich_status_widget(app)
    try:
        txt.tag_configure("base", lmargin1=left_gutter, lmargin2=left_gutter)
    except Exception:
        pass
    words = sorted({w for w in (highlight_words or []) if w}, key=len, reverse=True)
    try:
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        i, n = 0, len(text)
        while i < n:
            matched = next((w for w in words if text.startswith(w, i)), None)
            if matched:
                txt.insert("end", matched, ("base", "highlight"))
                i += len(matched)
            else:
                txt.insert("end", text[i], ("base", "normal"))
                i += 1
    finally:
        txt.configure(state="disabled")


# ============================================================================
# Status-bar dialogue (reuses the real app.status_var / app.status_msg)
# ============================================================================

class _StatusBarDialogue:
    """
    Plays a scripted sequence of (speaker, line) pairs through the main
    UI's existing status/message bar (self.status_var / self.status_msg)
    instead of a separate dialogue box — each line types itself out one
    character at a time, with a small "next" (▶) button overlaid on
    the status bar's right edge. Clicking it while a line is still typing
    instantly completes that line; clicking it once the line is fully
    shown advances to the next one, or finishes the sequence.

    Lines are shown through a small read-only Text overlay (see
    _set_rich_status_text above) rather than app.status_var directly, so
    individual words (button names, a seed count) can render in black
    against the rest of the red line — real multi-color text isn't
    possible on a plain tk.Label. The overlay sits on top of the real
    status_msg Label the rest of the app uses and is hidden again once
    the dialogue ends, so toasts/etc. go right back to using the plain
    Label exactly as before.

    A line auto-advances to the next one by itself, AUTO_ADVANCE_MS
    after it finishes typing, unless its "extra" dict sets "pause":
    True (see the LECTURES comment block) — used for lines worth
    lingering on, like one with a "highlight_target" arrow. The player
    can still click "▶" at any time to skip the wait.
    """

    AUTO_ADVANCE_MS = 2500

    def __init__(self, app, lines, on_finish=None, speed_ms=20):
        self.app = app
        self.lines = lines
        self.on_finish = on_finish
        self.speed_ms = speed_ms

        self._line_idx = -1
        self._char_pos = 0
        self._full_text = ""
        self._typing_job = None
        self._highlight_words = []
        self._active_arrow = None
        self._arrow_click_cleanup = None
        self._caption_speaker = None
        self._granted_lines = set()
        self._auto_advance = True
        self._auto_advance_job = None
        self._wait_condition_name = None
        self._wait_baseline = None
        self._wait_hold_ms = 0
        self._wait_condition_since = None
        self._live_readout_name = None
        self._live_readout_job = None
        self._no_skip = False
        self._auto_advance_ms = self.AUTO_ADVANCE_MS
        self._speaker = None
        self._mood = 1
        self._line_mood = 1
        self._mood_file = _MOOD_FILES[1]
        self._mood_job = None
        self._smile_started_at = None
        self._smile_linger_until = 0.0
        self._line_shown_at = time.monotonic()
        self._next_random_mood_at = time.monotonic() + _RANDOM_MOOD_EVERY_S
        self._random_mood_until = 0.0
        self._next_pulse_job = None
        self._next_pulse_on = False

        # Defense in depth: if a previous dialogue is somehow still
        # around (start_tutorial() guards against this, but just in
        # case), tear its button (and any arrow it left showing) down
        # first so there's never more than one "next" button or arrow
        # visible at once.
        prev = getattr(app, "_tutorial_dialogue", None)
        if prev is not None and prev is not self:
            try:
                if prev._typing_job is not None:
                    app.root.after_cancel(prev._typing_job)
            except Exception:
                pass
            try:
                prev._cancel_auto_advance()
            except Exception:
                pass
            try:
                prev._stop_live_readout()
                prev._stop_mood()
            except Exception:
                pass
            for btn_attr in ("next_btn", "back_btn"):
                try:
                    getattr(prev, btn_attr).destroy()
                except Exception:
                    pass
            _clear_dialogue_arrow(prev, fade=False)
        app._tutorial_dialogue = self

        # Measures the status label's own font so the buttons can be
        # placed right after the end of the currently-typed text,
        # exactly like the very first version of this dialogue did.
        try:
            label_font = self.app.status_msg.cget("font")
        except Exception:
            label_font = ("Segoe UI", 16, "bold")
        self._font = tkfont.Font(font=label_font)
        try:
            self._label_padx = int(self.app.status_msg.cget("padx"))
        except Exception:
            self._label_padx = 6

        self._btn_bg_normal = "#5C2810"
        self._btn_bg_hover = "#8B4226"

        # Both nav buttons are parented directly on app.root — exactly
        # like _ArrowHighlight's arrow label already is — and
        # positioned with place() using absolute, root-relative pixel
        # coordinates translated from the rich-text overlay's own
        # on-screen position (see _reposition_buttons). Two different
        # parents (status_msg_row, then the Text overlay itself) were
        # each tried and still left the buttons invisible, which this
        # mirrors the one approach already proven to work reliably in
        # this file: a widget parented straight on root sits above the
        # whole status-bar hierarchy without depending on any sibling
        # z-order or embedding behavior inside it.
        self.next_btn = self._make_nav_button("▶", self._on_next_clicked)

        # "◀" — goes back to the previous line (re-typed from the
        # start), so a line can be re-read instead of only ever moving
        # forward. Hidden (place_forget()) on the very first line since
        # there's nothing before it.
        self.back_btn = self._make_nav_button("◀", self._on_back_clicked)

        self._show_line(0)
        self._mood_tick()

    def _make_nav_button(self, text, command):
        # A styled Label rather than tk.Button: on macOS (Aqua) a real
        # Button ignores bg/fg and renders as a plain white native
        # button with white (invisible) text. A Label honors the colors
        # on every platform; the click is bound by hand.
        btn = tk.Label(
            self.app.root, text=text, font=("Segoe UI", 11, "bold"),
            width=2, padx=4, pady=2, relief="flat", bd=0,
            bg=self._btn_bg_normal, fg="white", cursor="hand2",
        )
        btn.bind("<Button-1>", lambda e: command())
        # A flat, borderless button like this one doesn't get any
        # hover feedback from Tk by default — bind it explicitly so it's
        # obvious the button is clickable.
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=self._btn_bg_hover))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=self._btn_bg_normal))
        return btn

    def _reposition_buttons(self, text):
        # "▶" mirrors the very first version of this dialogue's button:
        # measures the plain displayed string with a tkfont.Font and
        # places the button immediately after it, rather than reading
        # the rich-text overlay's bbox for the last character (that
        # bbox approach kept landing the button in the wrong place).
        # Text stays left-aligned (flush against the overlay's own
        # left padding), same as always — a center-justified version
        # was tried and reverted, since it both broke this calculation
        # and wasn't what was wanted.
        #
        # "◀" deliberately does NOT track the text at all — it sits in
        # one fixed spot near the left edge the whole time a line is
        # showing, rather than sliding further right with every
        # keystroke the way "▶" (and an earlier version of "◀" too)
        # does; there's nothing about "go back" that relates to where
        # the text currently ends, and constantly repositioning it
        # alongside the typing animation just reads as distracting
        # motion with no purpose.
        #
        # Both buttons are parented on app.root (see __init__) and
        # their coordinates are translated into app.root-relative
        # pixels the same way _ArrowHighlight already does, since that
        # parenting is what keeps them reliably visible on top of the
        # rich-text overlay.
        try:
            txt = self.app._tutorial_rich_status
            txt.update_idletasks()
            self.app.root.update_idletasks()
            root_x = self.app.root.winfo_rootx()
            root_y = self.app.root.winfo_rooty()
            txt_x = txt.winfo_rootx() - root_x
            txt_y = txt.winfo_rooty() - root_y
            txt_h = txt.winfo_height()
            inset = self._label_padx + int(txt.cget("bd") or 0)

            # The text itself is pushed right by this same amount (via
            # _set_status's left_gutter, reflected in the "base" tag's
            # lmargin), so the two line up and the button never sits on
            # top of the first letter.
            gutter = self._gutter_width() if self._line_idx > 0 else 0
            y = txt_y + txt_h // 2

            # "▶" only ever shows on a "paused" line — one that needs a
            # click (or a wait_for_condition) to move on — not on a line
            # that's about to auto-advance by itself a couple seconds
            # after it finishes typing; showing a button that isn't
            # actually needed just invites clicking it mid-sentence.
            if self._auto_advance or self._no_skip:
                self.next_btn.place_forget()
            else:
                text_w = self._font.measure(text)
                gap = 10
                x = txt_x + inset + gutter + text_w + gap
                self.next_btn.place(x=x, y=y, anchor="w")
                self.next_btn.lift()
                self._start_next_pulse()

            if self._line_idx > 0:
                self.back_btn.place(x=txt_x + inset, y=y, anchor="w")
                self.back_btn.lift()
            else:
                self.back_btn.place_forget()
        except Exception:
            pass

    def _start_next_pulse(self):
        """The first time "▶" ever appears, makes it pulse between its
        normal brown and a soft amber so the player notices it is
        something to press. Stops for good (app._tutorial_next_hint_done)
        the first time it is actually clicked."""
        if getattr(self.app, "_tutorial_next_hint_done", False):
            return
        if self._next_pulse_job is not None:
            return

        steps = 32  # one full pulse = 32 * 50ms = 1.6s
        self._next_pulse_k = 0

        def _tick():
            self._next_pulse_k = (self._next_pulse_k + 1) % steps
            t = (1 - math.cos(2 * math.pi * self._next_pulse_k / steps)) / 2
            try:
                self.next_btn.configure(
                    bg=_lerp_color(self._btn_bg_normal, "#D08A3A", t),
                    font=("Segoe UI", 11 + (1 if t > 0.6 else 0), "bold"))
            except Exception:
                return
            self._next_pulse_job = self.app.root.after(50, _tick)

        _tick()

    def _stop_next_pulse(self, mark_done=False):
        if self._next_pulse_job is not None:
            try:
                self.app.root.after_cancel(self._next_pulse_job)
            except Exception:
                pass
            self._next_pulse_job = None
        self._next_pulse_on = False
        try:
            self.next_btn.configure(bg=self._btn_bg_normal, fg="white",
                                    font=("Segoe UI", 11, "bold"))
        except Exception:
            pass
        if mark_done:
            self.app._tutorial_next_hint_done = True

    def _gutter_width(self):
        try:
            return self.back_btn.winfo_reqwidth() + 6
        except Exception:
            return 0

    def _set_status(self, text):
        # Once the line has finished typing, append its live readout (if
        # any) — e.g. the current game speed — so the player gets
        # continuous feedback on something they're doing right now (see
        # "live_readout" in the LECTURES comment block and
        # _format_live_readout). Left off while still typing so it
        # doesn't flicker in and out character-by-character.
        if self._live_readout_name and self._char_pos >= len(self._full_text):
            suffix = _format_live_readout(self.app, self._live_readout_name)
            if suffix:
                text = text + suffix
        try:
            left_gutter = self._gutter_width() if self._line_idx > 0 else 0
            _set_rich_status_text(self.app, text, self._highlight_words, left_gutter)
        except Exception:
            pass
        self._reposition_buttons(text)

    def _start_live_readout(self):
        """Re-renders the current line every 300ms so its "live_readout"
        suffix (if any) stays current — e.g. updating as the player taps
        Ctrl+Left/Right to change speed. Uses its own job slot
        (_live_readout_job), independent of the auto-advance/wait-
        condition polling job, so it keeps running even on a line that
        has no wait_for_condition at all."""
        self._stop_live_readout()
        if not self._live_readout_name:
            return
        line_idx = self._line_idx

        def _tick():
            self._live_readout_job = None
            if self._line_idx != line_idx:
                return
            if not getattr(self.app, "_tutorial_active", False):
                return
            if self._char_pos >= len(self._full_text):
                self._set_status(self._prefix + self._full_text)
            self._live_readout_job = self.app.root.after(300, _tick)

        self._live_readout_job = self.app.root.after(300, _tick)

    def _stop_live_readout(self):
        if self._live_readout_job is not None:
            try:
                self.app.root.after_cancel(self._live_readout_job)
            except Exception:
                pass
            self._live_readout_job = None

    def _apply_speaker_caption(self, speaker):
        """Bakes the speaker's name onto the tutorial portrait itself
        (see _portrait_with_speaker_caption) instead of showing it as
        part of the message box's own text. A no-op once a given
        speaker is already showing, so this isn't re-decoding/re-
        drawing the image on every single typed character — only when
        the speaker for the current line actually changes."""
        if getattr(self, "_mendel_shown", False):
            return    # Mendel's own portrait is up (see "portrait")
        if _portrait_lock_left(self.app) > 0:
            # A watering/planting image has priority; it redraws the
            # dialogue's portrait itself once it is over.
            self._caption_speaker = None
            return
        if speaker == self._caption_speaker:
            return
        try:
            photo = _garden_only_image(self.app)
            if photo is not None:
                self.app.mendel_label.configure(image=photo)
                self.app.mendel_label.image = photo
                self._caption_speaker = speaker
                return
            # Chosen mood first, then franz_1 as a fallback if that
            # particular file isn't there.
            for fname in (self._mood_file, _MOOD_FILES[1]):
                photo = _portrait_with_speaker_caption(
                    os.path.join(ICONS_DIR, fname), speaker)
                if photo is not None:
                    break
            if photo is not None:
                self.app.mendel_label.configure(image=photo)
                self.app.mendel_label.image = photo
        except Exception:
            pass
        self._caption_speaker = speaker

    def _show_mendel_portrait(self):
        """Puts Mendel's expression image for the current season in the
        portrait slot. Returns False (Cyril stays) if no image exists."""
        if _portrait_lock_left(self.app) > 0:
            return True     # shown again by the action image's end handler
        try:
            season = getattr(self.app, "_bg_current_season", "spring")
            scene = _garden_only_image(self.app)
            if scene is not None:
                self.app.mendel_label.configure(image=scene)
                self.app.mendel_label.image = scene
                return True
            for sea in (season, "spring"):
                path = os.path.join(ICONS_DIR, "mendel",
                                    f"mendel_looking_{sea}.png")
                if os.path.isfile(path):
                    img = safe_image(path)
                    if img is not None:
                        self.app.mendel_label.configure(image=img)
                        self.app.mendel_label.image = img
                        return True
        except Exception:
            pass
        return False

    def _set_mood(self, mood):
        """Switches Cyril's portrait to franz_<mood>.png (1 explaining,
        2 smiling, 3 idle) — a no-op if it is already showing."""
        mood = mood if mood in _MOOD_FILES else 1
        if mood == self._mood and self._caption_speaker is not None:
            return
        self._mood = mood
        self._mood_file = _MOOD_FILES[mood]
        self._caption_speaker = None  # force a re-draw with the new file
        if self._speaker is not None:
            self._apply_speaker_caption(self._speaker)

    def _mood_tick(self):
        """Once a second: after _IDLE_MOOD_AFTER_S on a line that is
        waiting for the player (a pause / wait_for_condition line),
        Cyril switches to franz_3; otherwise every
        _RANDOM_MOOD_EVERY_S there is a chance of a brief franz_3 too.
        Showing a new line resets it to that line's own mood."""
        self._mood_job = None
        if not getattr(self.app, "_tutorial_active", False):
            return
        try:
            now = time.monotonic()
            if self._smile_linger_until:
                if now < self._smile_linger_until:
                    self._mood_job = self.app.root.after(250, self._mood_tick)
                    return
                self._smile_linger_until = 0.0
                self._set_mood(self._line_mood)
                self._line_shown_at = now
            waiting = (not self._auto_advance) or bool(self._wait_condition_name)
            if waiting and now - self._line_shown_at >= _IDLE_MOOD_AFTER_S:
                self._set_mood(3)
            elif now >= self._random_mood_until and self._mood == 3 and not waiting:
                self._set_mood(self._line_mood)
            if now >= self._next_random_mood_at:
                self._next_random_mood_at = now + _RANDOM_MOOD_EVERY_S
                if self._line_mood == 1 and random.random() < 0.3:
                    self._random_mood_until = now + 5
                    self._set_mood(3)
        except Exception:
            pass
        self._mood_job = self.app.root.after(1000, self._mood_tick)

    def _stop_mood(self):
        if self._mood_job is not None:
            try:
                self.app.root.after_cancel(self._mood_job)
            except Exception:
                pass
            self._mood_job = None

    def _apply_seed_grant(self, idx, amount):
        """Adds `amount` seeds to app.available_seeds the first time
        line `idx` is shown (see "grant_seeds" in the LECTURES comment
        block) — tracked per line index in self._granted_lines so
        revisiting it later (e.g. "◀" then "▶" again) doesn't hand out
        the same seeds twice."""
        if not amount or idx in self._granted_lines:
            return
        self._granted_lines.add(idx)
        try:
            amount = int(amount)
            self.app.available_seeds = int(getattr(self.app, "available_seeds", 0) or 0) + amount
            try:
                self.app._refresh_seed_counter_var()
            except Exception:
                pass
            try:
                self.app._toast(f"Cyril hands you {amount} more seeds.", level="info")
            except Exception:
                pass
            # Same "harvest all" cue the real Harvest All action uses —
            # a little audible confirmation that seeds actually landed
            # in the inventory, not just the toast.
            _play_sound_via_app(self.app, "harvest_all.ogg")
        except Exception:
            pass

    def _show_line(self, idx):
        if idx >= len(self.lines):
            return
        self._cancel_auto_advance()
        self._line_idx = idx
        entry = self.lines[idx]
        speaker, text = entry[0], entry[1]
        extra = entry[2] if len(entry) > 2 else {}
        self._auto_advance = not bool(extra.get("pause", False))
        self._auto_advance_ms = extra.get("auto_advance_ms") or self.AUTO_ADVANCE_MS
        self._wait_condition_name = extra.get("wait_for_condition")
        self._wait_baseline = (
            getattr(self.app, "available_seeds", 0)
            if self._wait_condition_name else None
        )
        # "first_seed_planted" is measured against the seed count the
        # lecture started with, not whatever it is when this line appears —
        # otherwise a player who plants everything early (before this
        # line shows) leaves the baseline at 0 and the wait never fires.
        if self._wait_condition_name == "pod_harvested":
            self._wait_baseline = len(getattr(self.app, "harvest_inventory", []) or [])
        if self._wait_condition_name == "first_seed_planted":
            start = getattr(self.app, "_tutorial_start_seeds", None)
            if start is not None:
                self._wait_baseline = int(start)
        # Most wait_for_condition lines advance the instant the check
        # first comes back true; a line can instead require it to stay
        # true for a stretch (e.g. "hold this game speed for 3 seconds")
        # by setting "wait_for_hold_ms" — see _poll_wait_condition.
        self._wait_hold_ms = extra.get("wait_for_hold_ms", 0) or 0
        self._wait_condition_since = None
        self._stop_live_readout()
        self._live_readout_name = extra.get("live_readout")
        self._no_skip = bool(extra.get("no_skip", False))
        if self._wait_condition_name == "plant_inspected":
            self.app._tutorial_inspected = False
        watch_keys = extra.get("wait_for_keys")
        self.app._tutorial_key_pressed = False
        self.app._tutorial_key_watch_active = bool(watch_keys)
        if watch_keys:
            _ensure_key_watch(self.app, watch_keys)
        # No longer "(Speaker): " text in the message box itself — the
        # speaker's name is now baked onto their own portrait instead
        # (see _apply_speaker_caption), freeing up the space it used to
        # take at the start of every line.
        self._prefix = ""
        self._speaker = speaker
        self._line_shown_at = time.monotonic()
        self._random_mood_until = 0.0
        self._line_mood = extra.get("mood", 1)
        # Smiles last twice as long: when a run of smiling (mood 2)
        # lines ends, he keeps smiling for as long again as that run
        # lasted (see _mood_tick, which ends the extra time).
        now = time.monotonic()
        if self._line_mood == 2:
            if self._smile_started_at is None:
                self._smile_started_at = now
            self._smile_linger_until = 0.0
            self._set_mood(2)
        else:
            if self._smile_started_at is not None:
                self._smile_linger_until = now + (now - self._smile_started_at)
                self._smile_started_at = None
            if now >= self._smile_linger_until:
                self._set_mood(self._line_mood)
        # "portrait": "mendel" shows Mendel instead of Cyril while the
        # line asks the player to act; any other line brings Cyril back.
        want_mendel = extra.get("portrait") == "mendel"
        if want_mendel:
            self._mendel_shown = self._show_mendel_portrait()
        elif getattr(self, "_mendel_shown", False):
            self._mendel_shown = False
            self._caption_speaker = None      # force Cyril to be redrawn
        self._apply_speaker_caption(speaker)
        self._full_text = text
        self._char_pos = 0
        self._highlight_words = extra.get("highlight_words") or []
        self._apply_seed_grant(idx, extra.get("grant_seeds"))
        # "enable_buttons": sidebar buttons (app attribute names) that are
        # usable while this line is showing; they are locked again as soon
        # as the player moves on to another line.
        for name in getattr(self, "_enabled_btns", []):
            try:
                getattr(self.app, name).configure(state="disabled")
            except Exception:
                pass
        self._enabled_btns = list(extra.get("enable_buttons") or [])
        for name in self._enabled_btns:
            try:
                getattr(self.app, name).configure(state="normal")
            except Exception:
                pass
        # "unlock_buttons": opens these buttons for the rest of the
        # tutorial (they have just been explained).
        if extra.get("unlock_buttons"):
            _unlock_buttons(self.app, extra["unlock_buttons"])
        # "set_water": dry every plant out to this water level, once per
        # line (so ◀ then ▶ doesn't dry them again).
        if extra.get("set_water") and ("water", idx) not in self._granted_lines:
            self._granted_lines.add(("water", idx))
            _tutorial_dry_out_plants(self.app, extra["set_water"],
                                 extra.get("dry_count"))

        # Nothing to go back to from the very first line — _reposition_
        # buttons() simply place_forget()s it there.
        try:
            self.back_btn.configure(state=("normal" if idx > 0 else "disabled"))
        except Exception:
            pass

        target_names = extra.get("highlight_target")
        if isinstance(target_names, str):
            target_names = [target_names]
        widgets = []
        sides = []
        for name in (target_names or []):
            w = _HIGHLIGHT_TARGETS.get(name, lambda app: None)(self.app)
            if w is not None:
                widgets.append(w)
                sides.append(_ARROW_SIDES.get(name, "bottom"))
        if widgets:
            arrows = [_ArrowHighlight(self.app, w, s)
                      for w, s in zip(widgets, sides)]
            self._active_arrow = arrows[0] if len(arrows) == 1 else _ArrowGroup(arrows)
            # Dismiss the arrow(s) the moment the player actually clicks
            # the thing being pointed at (e.g. clicking "Plant" opens
            # the Choose Seeds dialog) — not just when they advance the
            # dialogue text — so it doesn't linger on screen, on top of
            # whatever that click just opened, once its job is done.
            cleanups = [c for c in (self._bind_arrow_dismiss_on_click(w) for w in widgets) if c]

            def _cleanup_all(_cs=cleanups):
                for c in _cs:
                    try:
                        c()
                    except Exception:
                        pass
            self._arrow_click_cleanup = _cleanup_all

        if extra.get("highlight_late"):
            for name in (target_names or []):
                if _HIGHLIGHT_TARGETS.get(name, lambda app: None)(self.app) is None:
                    self._poll_late_highlight(name, idx)
                    break

        self._set_status(self._prefix)
        self._type_started = time.monotonic()
        self._type_next_char()
        self._start_live_readout()

    def _poll_late_highlight(self, name, idx):
        """For a target that only exists once the player opens something
        (e.g. Harvest All inside the inspector): keeps looking for it while
        this line shows, puts the arrow on it as soon as it appears, and
        takes the arrow away again if that window is closed."""
        state = {"arrow": None}

        def _poll():
            if (getattr(self.app, "_tutorial_dialogue", None) is not self
                    or self._line_idx != idx):
                return
            w = _HIGHLIGHT_TARGETS.get(name, lambda app: None)(self.app)
            arrow = state["arrow"]
            if arrow is not None and self._active_arrow is not arrow:
                state["arrow"] = arrow = None       # cleared elsewhere
            if w is not None and arrow is None:
                try:
                    arrow = _ArrowHighlight(self.app, w, _ARROW_SIDES.get(name, "bottom"))
                    state["arrow"] = arrow
                    self._active_arrow = arrow
                except Exception:
                    pass
            elif w is None and arrow is not None:
                try:
                    arrow.destroy()
                except Exception:
                    pass
                state["arrow"] = None
                if self._active_arrow is arrow:
                    self._active_arrow = None
            if state["arrow"] is not None:
                try:
                    state["arrow"].win.lift()       # above the inspector window
                except Exception:
                    pass
            self.app.root.after(300, _poll)

        self.app.root.after(300, _poll)

    def _bind_arrow_dismiss_on_click(self, widget):
        def _on_click(event=None):
            _clear_dialogue_arrow(self)

        try:
            bind_id = widget.bind("<Button-1>", _on_click, add="+")
        except Exception:
            return None

        def _cleanup():
            try:
                widget.unbind("<Button-1>", bind_id)
            except Exception:
                pass

        return _cleanup

    def _type_next_char(self):
        if self._char_pos >= len(self._full_text):
            self._typing_job = None
            self._schedule_auto_advance()
            return
        # Time-based typing: how many characters are shown depends on the
        # elapsed time, not on how many timer callbacks have fired. On
        # macOS each "after" tick plus the rich-text re-render takes much
        # longer than the nominal delay, so counting ticks made the text
        # crawl; this keeps the same speed on every platform.
        elapsed_ms = (time.monotonic() - getattr(self, "_type_started", time.monotonic())) * 1000.0
        target = min(len(self._full_text), int(elapsed_ms / self.speed_ms) + 1)
        if target > self._char_pos:
            self._char_pos = target
            self._set_status(self._prefix + self._full_text[:self._char_pos])
        self._typing_job = self.app.root.after(8, self._type_next_char)

    def _finish_typing_instantly(self):
        if self._typing_job is not None:
            try:
                self.app.root.after_cancel(self._typing_job)
            except Exception:
                pass
            self._typing_job = None
        self._char_pos = len(self._full_text)
        self._set_status(self._prefix + self._full_text)
        self._schedule_auto_advance()

    def _schedule_auto_advance(self):
        """Lines auto-advance by themselves AUTO_ADVANCE_MS after they
        finish typing, unless marked "pause" (see the LECTURES comment
        block and the class docstring) — called once typing completes,
        whether that's by finishing naturally or being force-completed
        by a click. A "wait_for_condition" line overrides the timer
        entirely (even if "pause" is also set) and polls for that
        condition instead, advancing the instant it's met."""
        self._cancel_auto_advance()
        if self._wait_condition_name:
            self._poll_wait_condition()
        elif self._auto_advance:
            self._auto_advance_job = self.app.root.after(self._auto_advance_ms, self._on_auto_advance)

    def _poll_wait_condition(self):
        """Polls _WAIT_CONDITIONS[self._wait_condition_name] every 400ms
        (mirroring _wait_for_all_seeds_planted's own cadence further
        down this file) and auto-advances once it's satisfied. Stored in
        the same self._auto_advance_job slot as the timed auto-advance
        above, so _cancel_auto_advance() (called at the top of every
        _show_line, and on manual next/back clicks) stops this polling
        loop exactly the same way it stops the timer.

        Normally advances the instant the condition first comes back
        true. If this line set "wait_for_hold_ms" (e.g. "hold this game
        speed for 3 seconds" — see LECTURES), it instead requires the
        condition to stay continuously true for that long: each poll
        tracks when the current true-streak started in
        self._wait_condition_since, resetting it back to None the moment
        the condition goes false again, so flicking away and back
        restarts the wait rather than banking partial progress."""
        condition = _WAIT_CONDITIONS.get(self._wait_condition_name)
        if condition is None:
            return
        line_idx = self._line_idx
        # Polling starts the moment the line finishes typing, so this is
        # the start of its reading time. A line is never left earlier
        # than AUTO_ADVANCE_MS after that, even if its condition is
        # already true (e.g. the player planted every seed in one go
        # while the previous line was still showing) — otherwise the
        # line would flash past before it could be read.
        started = time.monotonic()

        def _check():
            self._auto_advance_job = None
            # Bail quietly if the player moved off this line (back/next)
            # or left the tutorial entirely while this was waiting.
            if self._line_idx != line_idx:
                return
            if not getattr(self.app, "_tutorial_active", False):
                return
            try:
                satisfied = bool(condition(self.app, self._wait_baseline))
            except Exception:
                satisfied = False

            if not satisfied:
                self._wait_condition_since = None
                self._auto_advance_job = self.app.root.after(400, _check)
                return

            now = time.monotonic()
            read_done = (now - started) * 1000.0 >= self.AUTO_ADVANCE_MS

            if self._wait_hold_ms <= 0:
                if read_done:
                    self._on_auto_advance()
                else:
                    self._auto_advance_job = self.app.root.after(200, _check)
                return

            if self._wait_condition_since is None:
                self._wait_condition_since = now
            held_ms = (now - self._wait_condition_since) * 1000.0
            if held_ms >= self._wait_hold_ms and read_done:
                self._on_auto_advance()
            else:
                self._auto_advance_job = self.app.root.after(400, _check)

        self._auto_advance_job = self.app.root.after(400, _check)

    def _cancel_auto_advance(self):
        if self._auto_advance_job is not None:
            try:
                self.app.root.after_cancel(self._auto_advance_job)
            except Exception:
                pass
            self._auto_advance_job = None

    def _on_auto_advance(self):
        self._auto_advance_job = None
        self._on_next_clicked(from_auto=True)

    def _on_next_clicked(self, from_auto=False):
        # A "no_skip" line can only be left by its own wait condition
        # firing (from_auto) — ignore manual attempts, BEFORE cancelling
        # the polling job below so the wait keeps running.
        if self._no_skip and not from_auto:
            return
        if not from_auto:
            self._stop_next_pulse(mark_done=True)
        self._cancel_auto_advance()
        if self._typing_job is not None:
            self._finish_typing_instantly()
            return

        # Dismissing this line — fade out whatever arrow it was pointing
        # at (if any) before moving on, whether that's to the next line
        # or to finishing the whole dialogue.
        _clear_dialogue_arrow(self)

        next_idx = self._line_idx + 1
        if next_idx < len(self.lines):
            self._show_line(next_idx)
        else:
            self._stop_live_readout()
            self._stop_next_pulse()
            self._stop_mood()
            self.app._tutorial_key_watch_active = False
            for btn_attr in ("next_btn", "back_btn"):
                try:
                    getattr(self, btn_attr).destroy()
                except Exception:
                    pass
            self._set_status("")
            _hide_rich_status_widget(self.app)
            if getattr(self.app, "_tutorial_dialogue", None) is self:
                self.app._tutorial_dialogue = None
            if callable(self.on_finish):
                self.on_finish()

    def _on_text_clicked(self):
        """Clicking the dialogue text itself: while it is still being
        typed it appears at once (even on lines the player can't skip);
        while a timed line is just waiting out its pause the wait is
        skipped. Lines that wait for ▶ or for the player to do
        something are left alone, so a stray click can't skip them."""
        if self._typing_job is not None:
            self._finish_typing_instantly()
            return
        if (self._auto_advance and not self._no_skip
                and not self._wait_condition_name
                and self._auto_advance_job is not None):
            self._on_next_clicked()

    def _on_back_clicked(self):
        if self._line_idx <= 0:
            return
        if self._typing_job is not None:
            try:
                self.app.root.after_cancel(self._typing_job)
            except Exception:
                pass
            self._typing_job = None
        # Same as advancing forward — whatever arrow the current line
        # was pointing at should fade out before showing a different one.
        _clear_dialogue_arrow(self)
        self._show_line(self._line_idx - 1)


# ============================================================================
# Real-grid scene setup
# ============================================================================

# Buttons that are blocked in the tutorial until they have been explained
# (name -> app attribute). The Monastery, pause and 1-hour-forward buttons
# are never blocked. A line's "unlock_buttons" extra opens buttons for good
# (for the rest of the tutorial); Fast Forward comes back with part 3.
_TUTORIAL_LOCKABLE = (
    "plant_seeds_btn", "water_btn", "water_all_btn", "inspect_btn",
    "harvest_btn", "pollen_btn", "pollinate_btn", "remove_btn",
    "genetics_btn", "tie_btn", "fast_btn", "measure_temp_btn", "observatory_btn",
    "btn_test_laws",
)


def _policy_active(app):
    return (getattr(app, "_tutorial_active", False)
            and not getattr(app, "_tutorial_policy_off", False))


def _apply_button_policy(app, enable=False):
    """Disables every blocked button; with enable=True the unlocked ones
    are switched on as well (otherwise the game's own selection logic keeps
    deciding whether e.g. Water is usable right now)."""
    unlocked = getattr(app, "_tutorial_unlocked", None) or set()
    monastery = getattr(app, "monastery_btn", None)
    seen = set()
    for name in _TUTORIAL_LOCKABLE:
        btn = getattr(app, name, None)
        if btn is None:
            continue
        seen.add(id(btn))
        try:
            if name in unlocked:
                if enable:
                    btn.configure(state="normal")
            else:
                btn.configure(state="disabled")
        except Exception:
            pass
    # Anything else in the left sidebar (added later) stays blocked too.
    try:
        for child in app.left_actions.winfo_children():
            if child is monastery or id(child) in seen:
                continue
            try:
                child.configure(state="disabled")
            except Exception:
                pass
    except Exception:
        pass


def _unlock_buttons(app, names):
    unlocked = getattr(app, "_tutorial_unlocked", None)
    if unlocked is None:
        unlocked = set()
        app._tutorial_unlocked = unlocked
    for name in names:
        unlocked.add(name)
        try:
            getattr(app, name).configure(state="normal")
        except Exception:
            pass


def _start_button_keeper(app):
    """Makes the blocking stick without fighting the game: each locked
    button gets a guard on its configure() so any attempt by the game
    (selection changes, the temperature check on every tick, ...) to
    switch it on is turned into 'disabled' while it is still blocked.
    (An earlier version re-disabled the buttons on a timer, which made
    them flicker whenever the game switched them on again.)"""
    for name in _TUTORIAL_LOCKABLE:
        btn = getattr(app, name, None)
        if btn is None or getattr(btn, "_tutorial_guarded", False):
            continue

        def _make_guard(btn=btn, name=name, original=btn.configure):
            def guarded(cnf=None, **kw):
                if (_policy_active(app)
                        and name not in (getattr(app, "_tutorial_unlocked", None) or ())):
                    if isinstance(cnf, dict) and "state" in cnf:
                        cnf = dict(cnf, state="disabled")
                    if "state" in kw:
                        kw["state"] = "disabled"
                return original(cnf, **kw)
            return guarded

        try:
            guard = _make_guard()
            btn.configure = guard
            btn.config = guard
            btn._tutorial_guarded = True
        except Exception:
            pass


def _reset_button_policy(app, unlocked=()):
    app._tutorial_policy_off = False
    app._tutorial_unlocked = set(unlocked)
    _apply_button_policy(app, enable=True)
    _start_button_keeper(app)


def _lock_down_sidebar(app):
    """Applies the tutorial's button blocking (see _TUTORIAL_LOCKABLE)."""
    _apply_button_policy(app)
    _start_button_keeper(app)


def _unlock_sidebar(app):
    """Inside the tutorial: re-applies the blocking (only explained
    buttons are usable). Outside it: gives every button back."""
    if _policy_active(app):
        _apply_button_policy(app, enable=True)
        return
    try:
        for child in app.left_actions.winfo_children():
            try:
                child.configure(state="normal")
            except Exception:
                pass
        for name in _TUTORIAL_LOCKABLE:
            try:
                getattr(app, name).configure(state="normal")
            except Exception:
                pass
    except Exception:
        pass


# Cyril's portrait set: franz_1 (explaining/teaching — his default while
# a lecture is running), franz_2 (smiling, after a success), franz_3
# (idle, when the player hasn't done much for a while) while he is
# present; franz_0 is shown once a lecture has ended, until he is back
# for the next one. (The old single franz.png no longer exists.)
_TUTOR_PORTRAIT_FILENAME = "franz_1.png"
_PORTRAIT_AWAY_FILENAME = "franz_0.png"
_MOOD_FILES = {1: "franz_1.png", 2: "franz_2.png", 3: "franz_3.png"}
_IDLE_MOOD_AFTER_S = 8        # waiting this long on a line -> franz_3
_RANDOM_MOOD_EVERY_S = 20     # chance of a brief franz_3 now and then

# Speaker captions baked onto a copy of the portrait (see
# _portrait_with_speaker_caption) are cached by (path, caption text),
# since baking means re-decoding and re-drawing the whole image.
_PORTRAIT_CAPTION_CACHE = {}


def _load_caption_font(size):
    """Best-effort bold truetype font for the baked-in speaker caption —
    falls back through a few common filenames (Windows' own Segoe UI
    first, since that's the font the rest of the UI already uses, then
    a couple of names more likely to exist on Linux/macOS) before
    giving up to PIL's tiny built-in bitmap font."""
    try:
        from PIL import ImageFont
    except Exception:
        return None
    for name in ("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf",
                 "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _portrait_with_speaker_caption(path, caption_text, bottom_inset=14):
    """
    Loads the portrait at `path` and bakes caption_text directly into
    its own pixels — in white, a few pixels above the very bottom edge
    and centered horizontally — rather than overlaying a separate
    widget on top of the image, which would need its own matching
    background color to avoid showing as a mismatched box. Returns an
    ImageTk.PhotoImage, or None if the file can't be loaded.
    """
    cache_key = (path, caption_text)
    cached = _PORTRAIT_CAPTION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        from PIL import Image, ImageDraw, ImageTk
    except Exception:
        return None
    if not os.path.isfile(path):
        return None
    try:
        img = Image.open(path).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = _load_caption_font(max(12, img.width // 14))
        try:
            bbox = draw.textbbox((0, 0), caption_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w, text_h = 0, 16
        x = max(0, (img.width - text_w) // 2)
        y = max(0, img.height - bottom_inset - text_h)
        draw.text((x, y), caption_text, fill="white", font=font)
        photo = ImageTk.PhotoImage(img)
    except Exception:
        return None
    _PORTRAIT_CAPTION_CACHE[cache_key] = photo
    return photo


def _garden_only_image(app):
    """In 'garden view only' (Game Settings) the portrait slot shows the
    garden scene — no Cyril, no Mendel. Returns that image, or None when
    the setting is off / there is no scene image."""
    if not getattr(app, "_garden_only_portrait", False):
        return None
    try:
        path = app._mendel_portrait._garden_scene_path()
        return safe_image(path) if path else None
    except Exception:
        return None


def _portrait_lock_left(app):
    """Seconds left of a watering/planting image that has priority over
    every other portrait (0 if none)."""
    return max(0.0, getattr(app, "_portrait_locked_until", 0.0) - time.monotonic())


def _swap_portrait_for_tutorial(app, filename=_TUTOR_PORTRAIT_FILENAME):
    """
    Swaps the left-panel portrait (self.mendel_label, normally
    mendel.png) to the Abbot's own portrait for the tutorial. Falls back
    to leaving the existing portrait alone if the file isn't there yet —
    drop icons/franz.png in whenever it's ready; nothing else needs to
    change here.
    """
    left = _portrait_lock_left(app)
    if left > 0:
        # An action image has priority: swap right after it is over.
        try:
            app.root.after(int(left * 1000) + 40,
                           lambda: _swap_portrait_for_tutorial(app, filename))
        except Exception:
            pass
        return
    try:
        img = _garden_only_image(app)
        if img is None:
            path = os.path.join(ICONS_DIR, filename)
            img = safe_image(path)
        if img is None:
            return
        app.mendel_label.configure(image=img)
        app.mendel_label.image = img  # keep a reference so it isn't garbage-collected
    except Exception:
        pass


def _set_easy_difficulty(app):
    """Casual/"off" mode — fastest growth, easiest lifecycle settings
    (see LIFECYCLE_SETTINGS in plant.py). This is what the rest of the
    app's UI shows as the easiest of the three difficulty levels.
    Stashes the player's previous difficulty first (on the app itself,
    since _deserialize_garden_state never captures _season_mode at all)
    so leaving the tutorial can put it back."""
    try:
        app._pre_tutorial_season_mode = getattr(app, "_season_mode", app.SEASON_MODES[0])
        app._season_mode = app.SEASON_MODES[0]
        if hasattr(app, "_difficulty_var"):
            app._difficulty_var.set(app._season_mode)
    except Exception:
        pass


def _restore_difficulty(app):
    try:
        prev = getattr(app, "_pre_tutorial_season_mode", app.SEASON_MODES[0])
        app._season_mode = prev
        if hasattr(app, "_difficulty_var"):
            app._difficulty_var.set(app._season_mode)
    except Exception:
        pass


# Real time: 1 real second = 1 simulated second, so 60 real seconds pass
# for every simulated minute — day_length_s is "seconds of real time per
# simulated HOUR" (see _set_day_length_patched in Garden-of-Inheritance.py),
# so that's 60 * 60. Same value as Garden-of-Inheritance.py's own
# SPEED_REAL_TIME_SECS constant (the "Real Time (1 sec = 1 sec)" preset
# in the Simulation Speed dialog) — kept as a plain literal here rather
# than importing it, since that module's hyphenated filename isn't
# importable as a normal Python module.
_TUTORIAL_DAY_LENGTH_S = 3600.0


def _set_ff_locked(app, locked):
    """Fast Forward (button and F key) is off during tutorial parts 1 and
    2 — it would skip right over the things the player is asked to do
    (and refill the plants dried out for the watering step). Part 3 is
    meant to call _set_ff_locked(app, False) to hand it back."""
    app._tutorial_ff_locked = bool(locked)
    if not locked:
        _unlock_buttons(app, ["fast_btn"])


def _set_tutorial_speed(app):
    """Slows the simulation down to real time (60 real seconds per
    simulated minute) for the tutorial, so a novice isn't watching the
    day race by while reading Cyril's lines. Stashes the player's
    previous speed first so leaving the tutorial can put it back."""
    try:
        app._pre_tutorial_day_length_s = float(getattr(app, "day_length_s", 1.0))
        app._set_day_length(_TUTORIAL_DAY_LENGTH_S)
        app.day_length_s = _TUTORIAL_DAY_LENGTH_S
    except Exception:
        pass


def _restore_speed(app):
    try:
        prev = getattr(app, "_pre_tutorial_day_length_s", 1.0)
        app._set_day_length(prev)
        app.day_length_s = prev
    except Exception:
        pass
    _set_ff_locked(app, False)


def _flatten_garden_and_reset_time(app):
    """
    Wipes every plant from every plot's tiles (same unregister-then-clear
    steps _deserialize_garden_state uses when a load replaces the whole
    garden) and resets the simulator's calendar/clock/weather back to
    exactly what a brand-new game starts with (see GardenEnvironment.__init__
    in garden.py: day 1, spring, 8am morning, year 1856) — so the
    tutorial always begins from a clean, fresh-start garden instead of
    wherever the player's ongoing game happened to be. Not just a
    cosmetic season override: app._bg_current_season gets recomputed
    from app.garden.month on every sim-hour tick, so the month itself
    has to change too or the override would be silently undone within a
    tick or two.
    """
    try:
        for tile in app._all_plot_tiles():
            if tile.plant is not None:
                try:
                    app.garden.unregister_plant(tile.plant)
                except Exception:
                    pass
                tile.plant = None
        try:
            app.garden.plants.clear()
        except Exception:
            pass
    except Exception:
        pass

    try:
        from garden import PHASES, WEATHER_SYMBOLS, WEATHER_WEIGHTS
        g = app.garden
        g.day = 1
        g.phase_index = 0
        g.phase = PHASES[0]
        g.clock_hour = 8
        g.year = 1856
        g.month = 4
        g.day_of_month = 1
        g.weather = random.choices(WEATHER_SYMBOLS, weights=WEATHER_WEIGHTS)[0]
        g.temp = 12.0
        try:
            g.target_temps = g._generate_day_temperatures()
        except Exception:
            pass
        g.temp_updates_remaining = 3
        app._bg_current_season = "spring"
        app._bg_last_season = "spring"
        app._last_temp_check_hour = 8
    except Exception:
        pass
    try:
        app._update_temp_button_state()
    except Exception:
        pass


def _teardown_active_dialogue(app):
    """Tears down the currently active _StatusBarDialogue, if any —
    cancels its typing-animation callback, destroys its "next"/"back"
    buttons and any arrow it had showing, hides the rich-text overlay,
    and clears the status bar. Used both when leaving the tutorial
    mid-line (exit_tutorial can be clicked at any point, including while
    Cyril is still mid-sentence) and as the other half of the re-entry
    guard in start_tutorial()."""
    dlg = getattr(app, "_tutorial_dialogue", None)
    if dlg is None:
        return
    try:
        if dlg._typing_job is not None:
            app.root.after_cancel(dlg._typing_job)
    except Exception:
        pass
    try:
        dlg._cancel_auto_advance()
    except Exception:
        pass
    try:
        dlg._stop_live_readout()
    except Exception:
        pass
    app._tutorial_key_watch_active = False
    try:
        dlg._stop_next_pulse()
        dlg._stop_mood()
    except Exception:
        pass
    for btn_attr in ("next_btn", "back_btn"):
        try:
            getattr(dlg, btn_attr).destroy()
        except Exception:
            pass
    _clear_dialogue_arrow(dlg, fade=False)
    _hide_rich_status_widget(app)
    try:
        app.status_var.set("")
    except Exception:
        pass
    app._tutorial_dialogue = None


def _clear_working_patch_border(app):
    """Removes any leftover 'tutorial_border_stone' canvas items — a
    no-op now that the tutorial no longer marks out a restricted patch
    with stones at all, kept only so exit_tutorial() still cleans up
    properly for anyone resuming a tutorial that was started on an
    older build that did draw them."""
    try:
        for tile in app._all_plot_tiles():
            try:
                tile.delete("tutorial_border_stone")
            except Exception:
                pass
    except Exception:
        pass
    app._tutorial_border_imgs = []


def _apply_lecture_to_real_grid(app, lecture):
    """
    Modifies the player's actual, already-built grid in place: flattens
    the whole garden (every plant on every plot removed) and resets the
    calendar/clock back to day 1, then hands the player starter_seeds
    actual, unplanted seeds (app.available_seeds) to plant wherever they
    like on the real grid, with the normal "Plant Seed..." flow — no
    tiles are locked and no patch is marked out; it's simply a fresh,
    normal garden.
    """
    tiles = list(getattr(app, "tiles", None) or [])
    if not tiles:
        return

    _flatten_garden_and_reset_time(app)

    # Make sure no tile is left over from an earlier lecture (or an
    # older build of the tutorial) still marked locked/overridden —
    # across every plot, in case the leftover flag is on a plot that
    # isn't the active one right now.
    try:
        for tile in app._all_plot_tiles():
            tile.locked = False
            tile._season_override = None
    except Exception:
        pass

    for tile in tiles:
        tile._render_state = None
        tile.render()

    # Starter seeds are handed out as an actual, unplanted inventory
    # count — set rather than incremented, since this is the start of a
    # fresh tutorial game — for the player to plant themselves, wherever
    # they like, via the normal "Plant Seed..." right-click flow (see
    # _plant_one_from_group in Garden-of-Inheritance.py).
    app.available_seeds = int(lecture["starter_seeds"])
    app._tutorial_start_seeds = int(lecture["starter_seeds"])

    # Also clear out any harvested-seed inventory left over from the
    # player's real game — the toolbar's "Seeds:" counter (seed_counter_var)
    # shows harvest_inventory + available_seeds combined (see
    # _refresh_seed_counter_var in Garden-of-Inheritance.py), so leaving
    # a non-empty harvest_inventory in place would inflate that number
    # above the starter_seeds count Cyril is actually talking about.
    try:
        app.harvest_inventory = []
    except Exception:
        pass

    # Setting available_seeds directly doesn't repaint the toolbar label
    # on its own — without this, "Seeds:" kept showing whatever total was
    # on screen before the tutorial flattened the garden (e.g. a brand
    # new game's default of 22) instead of the freshly-set starter count.
    try:
        app._refresh_seed_counter_var()
    except Exception:
        pass


# ============================================================================
# Pre-tutorial save / restore
# ============================================================================

def _save_pre_tutorial_state(app):
    """
    Silent "quick save" of the player's real garden, taken right before
    the tutorial modifies anything, under a fixed filename — not the
    interactive named-save flow (no dialog, no toast). Mirrors
    _on_save_garden's own serialize-then-write-JSON steps.
    """
    try:
        app._eager_seed_and_backfill()
    except Exception:
        pass
    try:
        data_dir = _data_dir()
        os.makedirs(data_dir, exist_ok=True)
        save_data = app._serialize_garden_state()
        with open(_autosave_path(), "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _restore_pre_tutorial_state(app):
    """
    Silently restores the garden saved by _save_pre_tutorial_state —
    bypassing _load_garden_from_file's interactive confirm dialog, since
    this is an automatic "leave the tutorial" action, not a player-picked
    load. Beyond the normal deserialize, also restores everything the
    save format itself doesn't capture: difficulty, the Abbot/Mendel
    portrait, sidebar button state, and the tiles' own tutorial-only
    `locked`/`_season_override` flags and stone overlay.
    """
    path = _autosave_path()
    if not os.path.isfile(path):
        return False

    # The player can click "Mendel's Garden" at any point, including
    # mid-sentence while Cyril's dialogue is still typing/showing a
    # "next" button — tear that down now so nothing is left orphaned
    # once the garden underneath it is restored.
    _teardown_active_dialogue(app)

    try:
        with open(path, "r", encoding="utf-8") as f:
            save_data = json.load(f)
        app._deserialize_garden_state(save_data)
    except Exception:
        return False

    # Clear tutorial-only runtime flags on every tile across every plot —
    # _deserialize_garden_state reuses the existing tile objects and never
    # touches these, so they'd otherwise still be locked/overridden.
    try:
        for tile in app._all_plot_tiles():
            tile.locked = False
            tile._season_override = None
            tile._render_state = None
    except Exception:
        pass

    _clear_working_patch_border(app)
    _restore_difficulty(app)
    _restore_speed(app)

    try:
        mp = getattr(app, "_mendel_portrait", None)
        if mp is not None:
            app._tutorial_active = False   # hand the portrait back first
            mp.refresh()
        else:
            mendel_img = safe_image(os.path.join(ICONS_DIR, "mendel.png"))
            if mendel_img is not None:
                app.mendel_label.configure(image=mendel_img)
                app.mendel_label.image = mendel_img
    except Exception:
        pass

    _unlock_sidebar(app)

    # The restored save's month may differ from whatever the tutorial
    # pinned it to — force an immediate season recompute rather than
    # waiting for the next periodic tick.
    try:
        app._apply_daynight_to_tiles()
    except Exception:
        pass

    try:
        app.render_all()
    except Exception:
        try:
            for tile in app.tiles:
                tile.render()
        except Exception:
            pass

    try:
        os.remove(path)
    except Exception:
        pass

    return True


def _wait_for_all_seeds_planted(app, lecture, on_done):
    """
    Silently polls (no line shown, no button) until the player has
    planted every starter seed handed out for this lecture —
    app.available_seeds reaching 0 — then either plays the lecture's
    after_wait_dialogue (Cyril speaking again, once it has lines) or
    calls on_done directly if there's nothing more to say yet. Lets the
    tutorial wait on something the player actually does in the garden,
    rather than firing the moment the last line is dismissed.
    """
    session = getattr(app, "_tutorial_session", 0)

    def _check():
        # The player may have left the tutorial entirely (via "Mendel's
        # Garden") or started another part from the map while this was
        # waiting — stop rather than fire against a different state.
        if not getattr(app, "_tutorial_active", False):
            return
        if getattr(app, "_tutorial_session", 0) != session:
            return
        if getattr(app, "available_seeds", 0) > 0:
            app.root.after(400, _check)
            return
        after_lines = lecture.get("after_wait_dialogue") or []
        if after_lines:
            _StatusBarDialogue(app, after_lines, on_finish=on_done)
        else:
            on_done()

    _check()


# ============================================================================
# Tutorial progress (autosave after part 1) and part 2
# ============================================================================

def _save_tutorial_progress(app, part_done, path=None):
    """Silently saves the tutorial garden plus how far the player got
    (part_done: 1 = lecture 1 finished, 2 = lecture 2 finished). Skipped
    when the plants are gone (see _tutorial_plants_lost), so a good save
    is never replaced by a garden the tutorial can't go on from."""
    if _tutorial_plants_lost(app, int(part_done)):
        return
    try:
        try:
            app._eager_seed_and_backfill()
        except Exception:
            pass
        os.makedirs(_data_dir(), exist_ok=True)
        payload = {
            "tutorial_part_done": int(part_done),
            "day_length_s": float(getattr(app, "day_length_s", 1.0)),
            "garden": app._serialize_garden_state(),
        }
        with open(path or _progress_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        if path is None:
            app._tutorial_part_done = int(part_done)
    except Exception:
        pass


def _checkpoint_path():
    """The tutorial's latest checkpoint (end of a part, or just before
    part 2) — what "restart from the last save" goes back to."""
    return os.path.join(_data_dir(), f"garden_{_PROGRESS_NAME}-checkpoint.json")


def _part2_start_path():
    """Saved just before part 2 starts, with the seedlings already grown."""
    return os.path.join(_data_dir(), f"garden_{_PROGRESS_NAME}-part2start.json")


def _part_start_path(n):
    """Saved the moment part n (2-6) is about to start — what that part's
    "Restart" on the tutorial map goes back to."""
    if n == 2:
        return _part2_start_path()
    return os.path.join(_data_dir(), f"garden_{_PROGRESS_NAME}-part{n}start.json")


def _load_part_start(n):
    if n == 2:
        return _load_tutorial_progress(_part2_start_path()) or _load_part1_snapshot()
    return _load_tutorial_progress(_part_start_path(n))


def _save_checkpoint(app, part_done, also=None):
    _save_tutorial_progress(app, part_done, path=_checkpoint_path())
    if also:
        _save_tutorial_progress(app, part_done, path=also)


def _living_plants(app):
    try:
        return sum(1 for t in app._all_plot_tiles()
                   if t.plant is not None and getattr(t.plant, "alive", True))
    except Exception:
        return 0


def _tutorial_plants_lost(app, part_done=None):
    """True when the tutorial can't go on with this garden: after part 1
    every plant has died or been removed, or later on fewer plants are
    left than the next part needs."""
    if not getattr(app, "_tutorial_active", False):
        return False
    pd = int(getattr(app, "_tutorial_part_done", 0) if part_done is None else part_done)
    n = _living_plants(app)
    if pd == 1:
        return n == 0
    if 2 <= pd <= 5:
        return n < _PLANTS_FOR_NEXT_PART
    return False


def _start_loss_watch(app):
    """Every 2 s (between Cyril's lines): if the plants are gone, offer to
    go back to the last tutorial save. Asked once; asked again only after
    the garden has recovered and been lost again."""
    if getattr(app, "_tutorial_loss_job", None) is not None:
        return

    def _check():
        app._tutorial_loss_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        try:
            if (getattr(app, "_tutorial_dialogue", None) is None
                    and not getattr(app, "fast_forward", False)):
                if _tutorial_plants_lost(app):
                    if not getattr(app, "_tutorial_loss_asked", False):
                        app._tutorial_loss_asked = True
                        _offer_restart_after_loss(app)
                else:
                    app._tutorial_loss_asked = False
        except Exception:
            pass
        app._tutorial_loss_job = app.root.after(2000, _check)

    app._tutorial_loss_job = app.root.after(2000, _check)


def _offer_restart_after_loss(app):
    was_running = bool(getattr(app, "running", True))
    app.running = False
    try:
        yes = app._silent_askyesno(
            "Tutorial",
            "Oh dear — your plants didn't make it, so the tutorial can't go on "
            "with this garden.\n\nGo back to the last tutorial save?")
    except Exception:
        yes = False
    app.running = was_running
    if not yes:
        return
    data = (_load_tutorial_progress(_checkpoint_path())
            or _load_tutorial_progress(_part2_start_path())
            or _load_part1_snapshot())
    if data is None:
        try:
            app._toast("No tutorial save found — starting part 1 again.", level="info")
        except Exception:
            pass
        start_tutorial(app, 0, choice="part1")
        return
    app._tutorial_loss_asked = False
    _resume_tutorial(app, data, was_active=True)


def _remember_realm(app, realm):
    try:
        app._remember_realm(realm)
    except Exception:
        pass


def _part1_snapshot_path():
    return os.path.join(_data_dir(), f"garden_{_PROGRESS_NAME}-part1.json")


def _load_part1_snapshot():
    return _load_tutorial_progress(_part1_snapshot_path())


def _stash_real_settings(app, was_active):
    """When the tutorial is already running, difficulty/speed already hold
    tutorial values — remember the REAL ones so re-applying the tutorial
    settings doesn't overwrite what exit_tutorial must restore."""
    if not was_active:
        return None
    return (getattr(app, "_pre_tutorial_season_mode", None),
            getattr(app, "_pre_tutorial_day_length_s", None))


def _stash_real_settings_restore(app, stash):
    if stash is None:
        return
    if stash[0] is not None:
        app._pre_tutorial_season_mode = stash[0]
    if stash[1] is not None:
        app._pre_tutorial_day_length_s = stash[1]


def _load_tutorial_progress(path=None):
    path = path or _progress_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("garden"), dict):
            return data
    except Exception:
        pass
    return None


def _delete_tutorial_progress():
    try:
        os.remove(_progress_path())
    except Exception:
        pass


def _cancel_seedling_watch(app):
    app._ff_stop_check = None
    job = getattr(app, "_tutorial_seedling_job", None)
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass
    app._tutorial_seedling_job = None


def _all_plants_seedlings(app):
    """True once at least one plant is growing, every starter seed is in
    the ground, and every living plant has reached the seedling stage."""
    try:
        if int(getattr(app, "available_seeds", 0) or 0) > 0:
            return False
        plants = [t.plant for t in app._all_plot_tiles()
                  if t.plant is not None and getattr(t.plant, "alive", True)]
        return bool(plants) and all(int(p.stage) >= 2 for p in plants)
    except Exception:
        return False


def _watch_for_seedlings(app):
    """Polls once a second (while the tutorial is active and no dialogue
    is showing) for the moment all plants are seedlings, then plays part 2.
    Also refreshes the progress save every couple of minutes."""
    _cancel_seedling_watch(app)
    state = {"ticks": 0}

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        # While a Fast Forward runs (its loop pumps Tk events, so this
        # callback fires mid-run) Cyril waits: the FF loop waters plants
        # every simulated hour, which would undo the dried-out plants.
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False)):
            if _all_plants_seedlings(app):
                _save_checkpoint(app, 1, also=_part2_start_path())
                _play_lecture_2(app)
                return
            state["ticks"] += 1
            if state["ticks"] % 120 == 0:
                _save_tutorial_progress(app, 1)
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _force_water_drops(app):
    """Shows the water-drop icons for the tutorial without touching the
    player's saved setting (they may normally use the fill bar)."""
    if getattr(app, "_tutorial_drop_stash", None) is not None:
        return
    app._tutorial_drop_stash = bool(getattr(app, "_water_drop_enabled", False))
    _apply_water_drops(app, True)


def _restore_water_drops(app):
    stash = getattr(app, "_tutorial_drop_stash", None)
    if stash is None:
        return
    app._tutorial_drop_stash = None
    _apply_water_drops(app, stash)


def _apply_water_drops(app, enabled):
    try:
        app._water_drop_enabled = enabled
        try:
            app._water_drop_var.set(enabled)
        except Exception:
            pass
        for tile in app._all_plot_tiles():
            tile._render_state = None
            tile.render()
    except Exception:
        pass


_CYRIL_LEAVES_S = 2


def _cyril_leaves(app):
    """Cyril's 'away' portrait for a few seconds after a lecture, then
    Mendel's own (season-aware) portraits take over again until the next
    lecture starts."""
    _swap_portrait_for_tutorial(app, _PORTRAIT_AWAY_FILENAME)
    session = getattr(app, "_tutorial_session", 0)

    def _hand_back():
        if (not getattr(app, "_tutorial_active", False)
                or getattr(app, "_tutorial_session", 0) != session
                or getattr(app, "_tutorial_dialogue", None) is not None):
            return
        app._tutorial_portrait_free = True
        try:
            app._mendel_portrait.refresh()
        except Exception:
            pass

    try:
        app.root.after(int(_CYRIL_LEAVES_S * 1000), _hand_back)
    except Exception:
        pass


def _play_lecture_2(app):
    app._tutorial_portrait_free = False      # Cyril is back
    _swap_portrait_for_tutorial(app)
    _lock_down_sidebar(app)
    _force_water_drops(app)
    _tutorial_autowater(app, False)      # from here the player waters
    _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)   # real time while Cyril talks

    def _done():
        _tutorial_set_speed(app, 1.0)    # back to 1 sec = 1 hour
        _unlock_sidebar(app)
        _cyril_leaves(app)
        _save_tutorial_progress(app, 2)
        _save_checkpoint(app, 2)
        _watch_for_budding(app)

    _StatusBarDialogue(app, LECTURE_2_DIALOGUE, on_finish=_done)


_PLANTS_FOR_NEXT_PART = 3     # this many plants at a stage bring Cyril back

# After part N is done: (growth stage the plants must reach, next part).
# 4 budding, 5 flowering, 6 pods forming, 7 mature pods (see plant.STAGE_NAMES).
_STAGE_PARTS = {
    2: (4, 3),
    3: (5, 4),
    4: (6, 5),
    5: (7, 6),
}


def _enough_at_stage(app, stage):
    """True once at least _PLANTS_FOR_NEXT_PART living plants have reached
    `stage` (or further)."""
    try:
        n = sum(1 for t in app._all_plot_tiles()
                if t.plant is not None and getattr(t.plant, "alive", True)
                and int(t.plant.stage) >= stage)
        return n >= _PLANTS_FOR_NEXT_PART
    except Exception:
        return False


def _watch_for_next_part(app, part_done):
    """After part `part_done` (2-5): polls once a second for the growth
    stage that brings Cyril back (see _STAGE_PARTS), then plays the next
    part. Also refreshes the progress save every couple of minutes. Shares
    the seedling watch's job slot, so the same cancel stops it."""
    _cancel_seedling_watch(app)
    if part_done not in _STAGE_PARTS:
        return
    stage, nxt = _STAGE_PARTS[part_done]
    state = {"ticks": 0}

    def _ready():
        # Cyril only comes by in the morning (7:00-11:59), even if the
        # plants got there earlier.
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        return 7 <= hour < 12 and _enough_at_stage(app, stage)

    # A long Fast Forward stops right when the plants get there.
    app._ff_stop_check = _ready

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False)):
            if _ready():
                app._ff_stop_check = None
                _save_tutorial_progress(app, part_done, path=_part_start_path(nxt))
                _play_stage_lecture(app, nxt)
                return
            state["ticks"] += 1
            if state["ticks"] % 120 == 0:
                _save_tutorial_progress(app, part_done)
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _watch_for_budding(app):
    _watch_for_next_part(app, 2)


def _play_stage_lecture(app, part):
    """Plays part 3-6 (Cyril comes back, says his lines, leaves again)."""
    dialogue = {3: LECTURE_3_DIALOGUE, 4: LECTURE_4_DIALOGUE,
                5: LECTURE_5_DIALOGUE, 6: LECTURE_6_DIALOGUE}[part]
    app._tutorial_portrait_free = False      # Cyril is back
    _swap_portrait_for_tutorial(app)
    _lock_down_sidebar(app)
    if part >= 3:
        _set_ff_locked(app, False)           # Fast Forward is offered in part 3
    _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)   # real time while Cyril talks
    _lock_sun_weather(app)                   # no rain or storm while he is here

    def _done():
        _tutorial_set_speed(app, 1.0)        # back to 1 sec = 1 hour
        _release_sun(app)                    # the weather is free again
        _unlock_sidebar(app)
        _cyril_leaves(app)
        _save_tutorial_progress(app, part)
        _save_checkpoint(app, part)
        _watch_for_next_part(app, part)

    _StatusBarDialogue(app, dialogue, on_finish=_done)


def _play_lecture_3(app):
    _play_stage_lecture(app, 3)


def _resume_tutorial(app, progress, was_active=False):
    """Picks the tutorial up again after part 1: the player's real garden
    is backed up first (as for a fresh start), then the saved tutorial
    garden is loaded and the seedling watch resumes."""
    _cancel_seedling_watch(app)
    _teardown_active_dialogue(app)
    app._tutorial_session = getattr(app, "_tutorial_session", 0) + 1
    app._tutorial_active = True
    _remember_realm(app, "tutorial")
    if not was_active:
        _save_pre_tutorial_state(app)
    _cyril_leaves(app)
    _stash = _stash_real_settings(app, was_active)
    _set_easy_difficulty(app)
    if not was_active:
        try:
            app._pre_tutorial_day_length_s = float(getattr(app, "day_length_s", 1.0))
        except Exception:
            pass
    _stash_real_settings_restore(app, _stash)
    try:
        app._deserialize_garden_state(progress["garden"])
    except Exception:
        # Corrupt save — fall back to a fresh start.
        start_tutorial(app, 0, choice="part1")
        return
    try:
        speed = float(progress.get("day_length_s", _TUTORIAL_DAY_LENGTH_S))
        app._set_day_length(speed)
        app.day_length_s = speed
        _set_ff_locked(app, True)
    except Exception:
        pass
    _done = int(progress.get("tutorial_part_done", 1))
    # Still waiting for the seedlings: the game keeps watering; once the
    # watering lesson (part 2) has been reached, the player does it.
    _tutorial_autowater(app, _done < 2)
    _reset_button_policy(
        app,
        ("plant_seeds_btn",) if _done < 2 else
        ("plant_seeds_btn", "water_btn", "water_all_btn", "inspect_btn"))
    try:
        for tile in app._all_plot_tiles():
            tile.locked = False
            tile._season_override = None
            tile._render_state = None
    except Exception:
        pass
    _unlock_sidebar(app)
    try:
        app._refresh_seed_counter_var()
    except Exception:
        pass
    try:
        app._apply_daynight_to_tiles()
    except Exception:
        pass
    try:
        app.render_all()
    except Exception:
        pass
    app._tutorial_part_done = int(progress.get("tutorial_part_done", 1))
    try:
        app._toast("Tutorial progress restored.", level="info")
    except Exception:
        pass
    _start_loss_watch(app)
    if app._tutorial_part_done == 1:
        _watch_for_seedlings(app)
    elif app._tutorial_part_done >= 2:
        if app._tutorial_part_done >= 3:
            _set_ff_locked(app, False)
        _watch_for_next_part(app, app._tutorial_part_done)


def exit_tutorial(app):
    """
    Leaves the tutorial and returns to the normal simulator. Bound to the
    Monastery map's "Mendel's Garden" region (replacing what used to open
    the Load Garden dialog there) — clicking it now always takes the
    player back to their real garden exactly as it was before the
    tutorial started, rather than opening a file picker.
    """
    # Leaving between parts 1 and 2: keep the tutorial garden's progress
    # so it can be resumed from the Friar's quarters.
    if (getattr(app, "_tutorial_active", False)
            and 1 <= getattr(app, "_tutorial_part_done", 0) <= 6
            and getattr(app, "_tutorial_dialogue", None) is None):
        _save_tutorial_progress(app, int(app._tutorial_part_done))
    _cancel_seedling_watch(app)
    app._tutorial_policy_off = True     # all buttons come back
    app._tutorial_portrait_free = False
    _release_sun(app)
    _restore_water_drops(app)
    app._tutorial_session = getattr(app, "_tutorial_session", 0) + 1
    try:
        restored = _restore_pre_tutorial_state(app)
    except Exception:
        restored = False
    app._tutorial_active = False
    _remember_realm(app, "garden")
    _tutorial_autowater_restore(app)
    try:
        if restored:
            app._toast("Back in the garden.", level="info")
        else:
            app._toast("You're already in your own garden.", level="info")
    except Exception:
        pass


# ============================================================================
# Entry point
# ============================================================================

# ============================================================================
# Tutorial map — pick which part to play (shown when saves exist)
# ============================================================================

# (title, subtitle, plant growth stage shown as the node icon) per part, left
# to right — the path follows the life of a pea plant, from seedling to a
# mature plant. Add parts by replacing the "Coming soon" entries.
_TUTORIAL_PARTS = [
    ("Part 1", "The First Seeds", 2),          # seedling
    ("Part 2", "The Seedlings", 3),            # leafy young plant
    ("Part 3", "Buds, Flowers & Pods", "budding_terminal_purple"),  # budding, purple, terminal
    ("Part 4", "Coming soon", 6),
    ("Part 5", "Coming soon", 7),
]

# Map part -> (first, last) internal step it covers. Part 3 on the map is
# Cyril's four visits (buds, flowers, pods, harvest = steps 3-6); each
# visit still saves its own point, so "Continue" picks up where you were.
_MAP_PART_STEPS = {1: (1, 1), 2: (2, 2), 3: (3, 6)}


def _stage_node_image(stage, size, locked):
    """Plant-stage icon for a map node, scaled to `size`; greyed out and
    faded when the part is still locked. None if the icon is unavailable."""
    try:
        from PIL import Image, ImageTk
        from icon_loader import stage_icon_path, budding_icon_path_hi, ICONS_DIR as _ID
        if isinstance(stage, str) and stage.startswith("budding_"):
            # A specific budding plant, e.g. "budding_terminal_purple".
            _, pos, col = stage.split("_", 2)
            path = budding_icon_path_hi(pos, col)
            if not path:
                p2 = os.path.join(_ID, f"budding_{pos}_{col}.png")
                path = p2 if os.path.isfile(p2) else stage_icon_path(4)
        else:
            path = stage_icon_path(stage)
        if not path:
            return None
        im = Image.open(path).convert("RGBA")
        im.thumbnail((size, size), Image.LANCZOS)
        if locked:
            r, g, b, al = im.split()
            grey = Image.merge("RGB", (r, g, b)).convert("L").convert("RGB")
            al = al.point(lambda v: int(v * 0.45))
            im = Image.merge("RGBA", (*grey.split(), al))
        return ImageTk.PhotoImage(im)
    except Exception:
        return None


def _map_button(parent, text, command, bg="#8B4226", fg="white", hover="#5C2810"):
    # Label-based so colors work on macOS (tk.Button ignores them there).
    lbl = tk.Label(parent, text=text, font=("Segoe UI", 10, "bold"), bg=bg, fg=fg,
                   padx=12, pady=5, cursor="hand2")
    lbl.bind("<Enter>", lambda e: lbl.configure(bg=hover))
    lbl.bind("<Leave>", lambda e: lbl.configure(bg=bg))
    lbl.bind("<Button-1>", lambda e: command())
    return lbl


def show_tutorial_map(app):
    """Popup with the tutorial parts laid out left to right as a map:
    Part 1 (replay), Part 2 (restart from the end of part 1, or continue
    from the autosave) and locked placeholders for parts still to come."""
    try:
        old = getattr(app, "_tutorial_map_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
    except Exception:
        pass

    BG, PANEL, FG = "#f6efe0", "#fbf7ee", "#3b2a1a"
    win = tk.Toplevel(app.root)
    app._tutorial_map_win = win
    win.title("Tutorial")
    win.configure(bg=BG)
    win.resizable(False, False)
    try:
        win.transient(app.root)
    except Exception:
        pass

    tk.Label(win, text="Friar Cyril's Lessons", font=("Segoe UI", 16, "bold"),
             bg=BG, fg=FG).pack(pady=(14, 2))
    tk.Label(win, text="Choose where to continue your training.",
             font=("Segoe UI", 10, "italic"), bg=BG, fg="#7a6a55").pack(pady=(0, 8))

    col_w = 150
    n = len(_TUTORIAL_PARTS)
    has_snapshot = _load_part1_snapshot() is not None
    has_progress = _load_tutorial_progress() is not None
    progress = _load_tutorial_progress() if has_progress else None
    part_done = int(progress.get("tutorial_part_done", 0)) if progress else 0
    def _map_done(n):
        first, last = _MAP_PART_STEPS.get(n, (99, 99))
        return part_done >= last or (n == 1 and has_snapshot)

    # Parts available: every finished one plus the one being worked on.
    unlocked = 1
    for _n in sorted(_MAP_PART_STEPS):
        if _map_done(_n):
            unlocked = min(len(_TUTORIAL_PARTS), _n + 1)
    unlocked = min(unlocked, max(_MAP_PART_STEPS))

    # The path: a line through one plant-stage icon per part, growing from
    # seedling (left) to a mature plant (right).
    node_r = 34
    path = tk.Canvas(win, width=col_w * n, height=node_r * 2 + 14, bg=BG,
                     highlightthickness=0)
    path.pack(padx=14)
    path._images = []
    cy = node_r + 7
    path.create_line(col_w // 2, cy, col_w * n - col_w // 2, cy,
                     fill="#b59b73", width=5, capstyle="round")
    # the stretch of path already open is drawn darker
    if unlocked > 1:
        path.create_line(col_w // 2, cy, col_w * (unlocked - 1) + col_w // 2, cy,
                         fill="#8B4226", width=5, capstyle="round")
    for i, (_t, _s, stage) in enumerate(_TUTORIAL_PARTS):
        cx = col_w * i + col_w // 2
        ok = (i < unlocked)
        path.create_oval(cx - node_r, cy - node_r, cx + node_r, cy + node_r,
                         fill=("#fbf7ee" if ok else "#e6dfcf"),
                         outline=("#8B4226" if ok else "#b5ab95"), width=3)
        img = _stage_node_image(stage, node_r * 2 - 14, locked=not ok)
        if img is not None:
            path._images.append(img)
            path.create_image(cx, cy, image=img)
        else:
            path.create_text(cx, cy, text=str(i + 1),
                             fill=("#8B4226" if ok else "#aaa090"),
                             font=("Segoe UI", 15, "bold"))

    cards = tk.Frame(win, bg=BG)
    cards.pack(padx=14, pady=(4, 6))

    def _pick(choice):
        try:
            win.destroy()
        except Exception:
            pass
        app.root.after(10, lambda: start_tutorial(app, 0, choice=choice))

    for i, (title, sub, _stage) in enumerate(_TUTORIAL_PARTS):
        ok = (i < unlocked)
        col = tk.Frame(cards, bg=(PANEL if ok else BG), width=col_w - 10, height=168,
                       highlightbackground="#d9cdb4", highlightthickness=1)
        col.grid(row=0, column=i, padx=5, sticky="n")
        col.grid_propagate(False)
        col.pack_propagate(False)
        tk.Label(col, text=title, font=("Segoe UI", 12, "bold"),
                 bg=(PANEL if ok else BG), fg=(FG if ok else "#aaa090")).pack(pady=(10, 0))
        tk.Label(col, text=sub, font=("Segoe UI", 10, "italic"),
                 bg=(PANEL if ok else BG), fg=("#7a6a55" if ok else "#b5ab95"),
                 wraplength=col_w - 30).pack(pady=(0, 8))
        n = i + 1
        done = _map_done(n)
        first = _MAP_PART_STEPS.get(n, (n, n))[0]
        can_restart = (n == 1) or (_load_part_start(first) is not None)
        if ok and done:
            # Finished: ticked, and can be played again from its start.
            tk.Label(col, text="✓", font=("Segoe UI", 14, "bold"),
                     bg=PANEL, fg="#7A9A3C").pack(pady=(0, 2))
            if can_restart:
                _map_button(col, "Restart", lambda f=first: _pick(f"restart:{f}")).pack(pady=2)
        elif ok:
            # The part the saved garden is heading for.
            _map_button(col, "Continue", lambda: _pick("continue"),
                        bg="#7A9A3C", hover="#5f7a2e").pack(pady=(4, 2))
            if n >= 2 and can_restart:
                _map_button(col, "Restart", lambda f=first: _pick(f"restart:{f}")).pack(pady=2)
        else:
            tk.Label(col, text="🔒", font=("Segoe UI", 14), bg=BG,
                     fg="#aaa090").pack(pady=4)

    _map_button(win, "Close", win.destroy, bg="#e0dccf", fg="#333333",
                hover="#d0cbb8").pack(pady=(4, 14))

    try:
        win.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - win.winfo_width()) // 2
        y = app.root.winfo_rooty() + 120
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
    except Exception:
        pass


def start_tutorial(app, lecture_index=0, choice=None):
    """
    Starts the tutorial on the real, running simulator: takes a silent
    save of the player's real garden first (so it can be restored later),
    sets the difficulty to easy, locks down the grid and sidebar to a
    guided 3x3 starter patch, and plays Cyril's lines in the main UI's
    own status bar. Called from the Monastery map's "Friar's quarters"
    hover region (see GardenApp._start_tutorial in
    Garden-of-Inheritance.py).
    """
    # The Monastery button stays clickable throughout the tutorial (so
    # the player can always leave via "Mendel's Garden"), which also
    # means they can reopen the Monastery popup and click "Friar's
    # quarters" again while a tutorial is already running. Without this
    # guard that silently re-entered start_tutorial(): it flattened the
    # (already-flattened) garden again and created a second dialogue
    # with its own "next" button on top of the first one's — the
    # leftover, never-disappearing button plus a duplicate reported.
    was_active = bool(getattr(app, "_tutorial_active", False))
    if lecture_index == 0 and choice is None:
        has_saves = _load_tutorial_progress() is not None or _load_part1_snapshot() is not None
        if was_active and not has_saves:
            try:
                app._toast("Already in the tutorial.", level="info")
            except Exception:
                pass
            return
        if has_saves:
            show_tutorial_map(app)
            return

    lecture = LECTURES[lecture_index]

    if lecture_index == 0:
        if isinstance(choice, str) and choice.startswith("restart:"):
            try:
                n = int(choice.split(":", 1)[1])
            except Exception:
                n = 1
            if n <= 1:
                choice = "part1"
            else:
                data = _load_part_start(n)
                if data is not None:
                    _resume_tutorial(app, data, was_active)
                    return
                choice = "continue"
        if choice in ("restart2", "continue"):
            data = (((_load_tutorial_progress(_part2_start_path()) or _load_part1_snapshot())
                     if choice == "restart2" else _load_tutorial_progress()))
            if data is not None:
                _resume_tutorial(app, data, was_active)
                return
        # Fresh run (part 1). Saved progress is kept until part 1 is
        # finished again and overwrites it.
        _cancel_seedling_watch(app)
        _teardown_active_dialogue(app)
        app._tutorial_session = getattr(app, "_tutorial_session", 0) + 1
        app._tutorial_part_done = 0
        app._tutorial_active = True
        _remember_realm(app, "tutorial")
        if not was_active:
            _save_pre_tutorial_state(app)

    app._tutorial_portrait_free = False
    _swap_portrait_for_tutorial(app)
    _stash = _stash_real_settings(app, was_active)
    _set_easy_difficulty(app)
    _set_tutorial_speed(app)
    _set_ff_locked(app, True)
    _stash_real_settings_restore(app, _stash)
    _reset_button_policy(app)          # everything blocked until explained
    _lock_down_sidebar(app)
    _apply_lecture_to_real_grid(app, lecture)
    if lecture_index == 0:
        _lock_sun_weather(app)         # planting day is a sunny day
        _tutorial_autowater(app, True)     # the plants water themselves in part 1
    else:
        _tutorial_autowater(app, False)    # from part 2 on the player waters

    def _on_finish():
        # Lecture 1 ends by handing control back to the player. Lecture
        # 2+ would chain here instead (e.g. re-lock a different patch
        # and call start_tutorial(app, lecture_index + 1)). The player
        # can also leave early at any point via the Monastery map's
        # "Mendel's Garden" region, which calls exit_tutorial() above.
        _unlock_sidebar(app)
        # Cyril leaves once the lecture is over (franz_0 for 5 s), then
        # Mendel's portraits are back until the next lecture.
        _cyril_leaves(app)
        # Part 1 is over: autosave the tutorial garden, then wait for the
        # seedlings that trigger part 2.
        _save_tutorial_progress(app, 1, path=_part1_snapshot_path())
        _save_tutorial_progress(app, 1)
        _save_checkpoint(app, 1)
        _watch_for_seedlings(app)
        _start_loss_watch(app)

    def _on_dialogue_dismissed():
        wait_for = lecture.get("wait_for")
        if wait_for == "all_seeds_planted":
            _wait_for_all_seeds_planted(app, lecture, _on_finish)
        else:
            _on_finish()

    _StatusBarDialogue(app, lecture["dialogue"], on_finish=_on_dialogue_dismissed)
