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
import logging
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


def _click_sound():
    """The app's normal button click (click.ogg), for the tutorial's own
    Label-based buttons, which don't get it automatically."""
    try:
        for mod in list(sys.modules.values()):
            play = getattr(mod, "_play_sound", None)
            if callable(play) and hasattr(mod, "GardenApp"):
                play("click.ogg")
                return
    except Exception:
        pass


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


# Cyril's short words after each watered plant (Part 2) — a little
# old-fashioned, as befits an abbot of the 1850s.
_WATER_PRAISE = ("Very good.", "Just so.", "Well done.", "Splendid.",
                 "That is the way.", "Capital!", "Good, good.", "Quite right.")

# Characters in a dialogue line drawn larger (the arrow keys), so they
# read as keys; see _set_rich_status_text.
_BIG_GLYPHS = frozenset({"←", "→"})


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
    if name == "frost_harvest":
        dlg = getattr(app, "_tutorial_dialogue", None)
        base = getattr(dlg, "_wait_baseline", 0) if dlg is not None else 0
        got = len(_plants_harvested_since(app, base))
        need = int(getattr(app, "_tut_frost_need", 2) or 0)
        return f"   [{min(got, need)}/{need} plants]" + (" ✓" if got >= need else "")
    if name == "harvest_plants":
        dlg = getattr(app, "_tutorial_dialogue", None)
        base = getattr(dlg, "_wait_baseline", 0) if dlg is not None else 0
        got, need = _other_plants_status(app, base)
        return f"   [{min(got, need)}/{need} plants]" + (" ✓" if got >= need else "")
    if name in ("water_progress", "water_progress_praise"):
        targets = [p for p in getattr(app, "_tutorial_dry_targets", None) or []
                   if getattr(p, "alive", True)]
        done = sum(1 for p in targets if int(p.water) >= _water_min(app))
        out = f"   [{done}/{len(targets)} watered]"
        if name == "water_progress_praise":
            # A short word from Cyril each time one more plant is watered.
            prev = getattr(app, "_tut_praise", None)
            if prev is None or done < prev[0]:
                prev = (done, "")
            if done > prev[0]:
                last = prev[1]
                pick = random.choice([w for w in _WATER_PRAISE if w != last] or _WATER_PRAISE)
                prev = (done, pick)
            app._tut_praise = prev
            if prev[1]:
                out += "   " + prev[1]
        return out
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
#   "highlight_words": substrings of text to point out. Keyboard
#       shortcuts among them (_SHORTCUT_WORDS: Space, press S, the ← →
#       arrows…) are drawn in black; all other words keep the speaker's
#       colour (Cyril red, Mendel blue).
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
             "Welcome to St. Thomas, young novice. I am Cyril Napp, "
             "abbot of this monastery.",
             {"highlight_words": ["Cyril Napp"]}),
            ("Cyril",
             "Come, let me show you the garden."),
            ("Cyril",
             "Ah, I see you brought nine pea seeds.",
             {"highlight_words": ["nine"], "highlight_target": "seed_count",
              "pause": True}),
            ("Cyril",
             "Good! They are quite ready to be planted."),
            ("Cyril",
             "Choose »Plant«, the button on your left, to plant your first seeds.",
             # Waits for the player to actually plant via the Plant
             # button (rather than a fixed delay) before moving on —
             # see "wait_for_condition" above and _WAIT_CONDITIONS below.
             {"highlight_words": ["Plant"], "highlight_target": "plant_button",
              "unlock_buttons": ["plant_seeds_btn"], "no_plant_all": True,
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
             {"pause": True, "no_skip": True, "no_plant_all": True,
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
             "share with you a little secret of this garden!"),
            ("Cyril",
             ("Hold Command (⌘) and tap the ← or → arrow key to slow "
              if sys.platform == "darwin" else
              "Hold Ctrl and tap the ← or → arrow key to slow ")
             + "down or speed up time.",
             # Waits for the player to actually press Ctrl+Left or
             # Ctrl+Right (see "wait_for_keys" above) before moving on,
             # with no "▶" to skip past it ("no_skip").
             # The arrows are drawn larger and bold (see _BIG_GLYPHS); the
             # "or" between them stays in the normal text colour.
             {"highlight_words": (["Command", "⌘", "←", "→", "arrow key"]
                                 if sys.platform == "darwin" else ["Ctrl", "←", "→", "arrow key"]),
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
             "Splendid! Isn’t it magical how time can fly?",
             {"mood": 2}),
            ("Cyril",
             "But we all need time to sleep, study, pray, and eat."),
            ("Cyril",
             "So you may only tend to the garden at a reasonable hour."),
            ("Cyril",
             "I shall grant you access from 6 a.m. until 7 p.m.",
             {"highlight_words": ["6 a.m.", "7 p.m."]}),
            ("Cyril",
             "Oh, and should you feel a little overwhelmed by the passing of time, "
             "simply press Space to pause for a moment.",
             {"highlight_words": ["Space"], "highlight_target": "pause_button"}),
            ("Cyril",
             "That will be all for now. I think you have learned quite a lot, Gregor!",
             {"mood": 2}),
            ("Cyril",
             "Now, tend to your plants until you see the first little "
             "seedlings emerge from the soil.",
             {"highlight_words": ["seedlings"]}),
            ("Cyril",
             "Once they do, I shall come and find you.",
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
    ("Cyril", "Ah, there they are! Your first seedlings.",
     {"mood": 2, "highlight_words": ["seedlings"],
      "set_water": 20, "dry_count": 5}),
    ("Cyril", "These little fellows will need water now and then.",
     {"pause": True}),
    ("Cyril", "Look, a few of them are already thirsty!",
     {"highlight_words": ["thirsty"]}),
    ("Cyril", "You’ve probably noticed the little water drop icon beside each plant.",
     {"highlight_words": ["water drop icon"], "auto_advance_ms": 4500}),
    ("Cyril", "Its color shows how moist the soil is: yellow means dry and thirsty...",
     {"highlight_words": ["yellow", "dry and thirsty"], "auto_advance_ms": 4000}),
    ("Cyril", "...light or middle blue is just right, and deep dark blue is far too wet!",
     {"highlight_words": ["just right", "far too wet"]}),
    # Mendel's turn: waits (no ▶) until all 5 dried plants are watered,
    # with a live "x/5 watered" count.
    ("Cyril", "Now, select a thirsty plant and water it.",
     {"highlight_words": ["Water"], "highlight_target": "water_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      # "water_progress_praise": a short word from Cyril after each plant
      "unlock_buttons": ["water_btn"], "live_readout": "water_progress_praise",
      "wait_for_condition": "targets_watered"}),
    # Now every plant dries out to 35 %.
    ("Cyril", "Very good! And what a glorious sunny day it is!",
     {"set_water": 35, "auto_advance_ms": 3000, "mood": 2}),
    ("Cyril", "It seems most seedlings could use some watering right now.",
     {"auto_advance_ms": 4000}),
    # Waits for Water All; then time goes back to 1 sec = 1 hour.
    ("Cyril", "Go on, then, tend to them all at once.",
     {"highlight_words": ["all at once"],
      "unlock_buttons": ["water_all_btn"],
      "highlight_target": "water_all_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "live_readout": "water_progress",
      "wait_for_condition": "plants_watered"}),
    ("Cyril", "There, every one of them has had a drink!",
     {"mood": 2, "auto_advance_ms": 3000}),
    ("Cyril", "Remember to keep the soil moist, but never soaking wet!",
     {"highlight_words": ["moist", "never soaking wet"], "pause": True}),
    ("Cyril", "And water in the morning or the evening if you can.",
     {"highlight_words": ["morning or the evening"], "pause": True}),
    ("Cyril", lambda app: _health_line(app),
     {"highlight_words": ["hearts", "health", "green", "red"], "pause": True}),
    ("Cyril", "A plant that loses all of it dies.",
     {"highlight_words": ["dies"], "pause": True}),
    ("Cyril", "Naturally, you’ll want to inspect your plants from time to "
     "time...",
     {"highlight_words": ["inspect"]}),
    ("Cyril", "...see how they’re doing and which traits they’ve revealed!"),
    # Waits until the player has actually inspected a plant.
    # Only shown if no plant is selected yet: the Inspect button needs one.
    ("Cyril", "First, choose one of your plants: click on it to select it.",
     {"highlight_words": ["click on it"], "portrait": "mendel",
      "pause": True, "no_skip": True, "skip_if": "plant_selected",
      "wait_for_condition": "plant_selected"}),
    # The inspection window opens with every section closed, so the next
    # line can show the Traits button.
    ("Cyril", "You can inspect each plant with the button above, or press I.",
     {"highlight_words": ["button", "I"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"], "inspector_closed": True,
      "wait_for_condition": "plant_inspected"}),
    # Waits until the Traits section has been opened.
    ("Cyril", "Now click »Traits« to see what your plant has revealed so far.",
     {"highlight_words": ["Traits"], "highlight_target": "inspector_traits_toggle",
      "highlight_late": True, "glow_targets": ["inspector_traits_toggle"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "traits_section_open"}),
    ("Cyril", "Didn’t you say at supper last night that only seven traits interest you now?",
     {"highlight_words": ["seven traits"], "auto_advance_ms": 4000}),
    ("Cyril", "Anyway, we can talk about that later!",
     {"auto_advance_ms": 4000}),
    # Waits until the inspection window has been closed (goes straight on
    # if it already is).
    ("Cyril", "You may close the inspection window now.",
     {"highlight_words": ["close"], "highlight_target": "inspector_close_button",
      "highlight_late": True, "glow_targets": ["inspector_close_button"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "inspector_window_closed"}),
    ("Cyril", "I’ll be back when your peas have grown a little taller.",
     {"auto_advance_ms": 5000}),
]


# Part 3 ("Buds, Flowers & Pods") is played in four visits, LECTURE_3 to
# LECTURE_6: Cyril returns once the first 3 plants are budding (see
# _watch_for_budding / _play_lecture_3), then flowering, forming pods and
# carrying ripe pods. Fast Forward stays locked until it is handed over
# near the end of the last visit (LECTURE_6_DIALOGUE).
LECTURE_3_DIALOGUE = [
    # (worked out when shown: if a plant flowered meanwhile, they say so)
    ("Mendel", lambda app: ("Look, Cyril, the first buds are showing!" if not _any_at_stage(app, 5)
                            else "Look, Cyril, buds everywhere, and the first flower is already open!"),
     {"portrait": "mendel", "highlight_words": ["buds", "first flower"], "highlight_plants": 4,
      "pause": True}),
    ("Cyril", lambda app: ("Ah, so they are! Before long, they will open into beautiful flowers."
                           if not _any_at_stage(app, 5) else
                           "Ah, so they are! And the first one has opened already. The others "
                           "will soon follow."),
     {"mood": 2, "highlight_words": ["flowers", "opened already"]}),
    # Waits until the player has inspected a plant (one of the budding ones).
    ("Cyril", "Take a closer look: inspect one of the budding plants.",
     {"highlight_words": ["inspect"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"],
      "wait_for_condition": "plant_inspected", "highlight_plants": 4}),
    ("Cyril", "See the little buds? Each one will become a flower, and later a pod.",
     {"highlight_words": ["buds"], "pause": True}),
    ("Cyril", "I’ll be back when the first flowers open.",
     {"auto_advance_ms": 5000}),
]


# Part 4 — the first 3 plants are flowering.
LECTURE_4_DIALOGUE = [
    ("Mendel", "Cyril, come and see, the first flowers have opened!",
     {"portrait": "mendel", "highlight_words": ["flowers"], "highlight_plants": 5, "pause": True}),
    ("Cyril", "How lovely!",
     {"mood": 2}),
    ("Cyril", "Remember, a pea flower usually pollinates itself before it even opens.",
     {"highlight_words": ["pollinates itself"], "pause": True}),
    ("Cyril", "Soon the petals will fall and little pods will form. Such is the way of the pea plant!",
     {"highlight_words": ["pods"]}),
    ("Cyril", "I’ll look in again when the first pods appear.",
     {"auto_advance_ms": 5000}),
]

# Part 5 — the first 3 plants are forming pods (not ripe yet).
LECTURE_5_DIALOGUE = [
    ("Mendel", "Cyril, come and look, the first pods are growing!",
     {"portrait": "mendel", "highlight_words": ["pods"], "highlight_plants": 6, "pause": True}),
    ("Cyril", "Indeed!",
     {"mood": 2}),
    ("Cyril", "But they’re still green and soft. The peas inside aren’t ripe yet.",
     {"highlight_words": ["aren’t ripe yet"]}),
    # Waits until the player has inspected a plant.
    # The inspection window opens with every section closed ("inspector_
    # closed"), so the next line can show where the pods are.
    ("Cyril", "Go on, take a closer look: inspect one of the plants with pods.",
     {"highlight_words": ["inspect"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"], "inspector_closed": True,
      "wait_for_condition": "plant_inspected", "highlight_plants": 6}),
    # Waits until the Harvest section has been opened.
    ("Cyril", "Now click »Harvest« in the inspection window to see the pods.",
     {"highlight_words": ["Harvest"], "highlight_target": "inspector_harvest_toggle",
      "highlight_late": True, "glow_targets": ["inspector_harvest_toggle"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "harvest_section_open"}),
    ("Cyril", "Yes, you can see the pods in there, but they can’t be harvested yet.",
     {"highlight_words": ["can’t be harvested yet"], "pause": True}),
    ("Cyril", "Be patient until the pods have dried and matured.",
     {"highlight_words": ["dried and matured"]}),
    ("Cyril", "I’ll come back when they are ready to harvest.",
     {"auto_advance_ms": 5000}),
]

# Part 6 — the first 3 plants carry mature pods.
LECTURE_6_DIALOGUE = [
    ("Mendel", "Cyril, I think the first pods are ripe!",
     {"portrait": "mendel", "highlight_words": ["ripe"], "highlight_plants": 7, "pause": True}),
    ("Cyril", "Well done, Gregor! Though some plants still need a little more time.",
     {"mood": 2, "highlight_words": ["more time"]}),
    # Waits until the player has harvested at least once.
    ("Cyril", "Select a plant with ripe pods and press »Harvest« to gather its seeds.",
     {"highlight_words": ["Harvest"], "highlight_target": "harvest_button",
      "unlock_buttons": ["harvest_btn"], "highlight_plants": 7,
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "pod_harvested"}),
    # Waits until another plant has been inspected...
    ("Cyril", "You can also harvest right in the inspection window. Try it!",
     {"highlight_words": ["inspection window"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"], "inspector_closed": True,
      "wait_for_condition": "plant_inspected", "highlight_plants": 7}),
    # Waits until the Harvest section has been opened.
    ("Cyril", "Now click »Harvest« to see its ripe pods.",
     {"highlight_words": ["Harvest"], "highlight_target": "inspector_harvest_toggle",
      "highlight_late": True, "glow_targets": ["inspector_harvest_toggle"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "harvest_section_open"}),
    # ...and until at least one pod has been harvested there.
    # The ripe pods and Harvest All glow softly (no arrow).
    ("Cyril", "Now harvest its pods: click a single pod, or Harvest All.",
     {"highlight_words": ["Harvest All"], "glow_harvest": True,
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "pod_harvested"}),
    # Waits until pods have been harvested from three other plants than the
    # one just harvested in the inspection window (fewer if not that many
    # have ripe pods), then 5 s more.
    ("Cyril", "Well done! Why not gather a few more, perhaps from different plants this time?",
     {"mood": 2, "highlight_words": ["different plants"],
      "pause": True, "no_skip": True, "live_readout": "harvest_plants",
      "wait_for_condition": "other_plants_harvested", "wait_for_hold_ms": 5000}),
    ("Cyril", "Every seed you gather can be sown again next spring.",
     {"highlight_words": ["sown again"], "pause": True}),
    # Fast Forward is handed over only now, at the very end of part 3.
    ("Cyril", "But waiting that long for a garden takes patience…",
     {"auto_advance_ms": 3000}),
    # (no arrow here: the arrow comes with "Go on, give Fast Forward a try!")
    ("Cyril", "...so from now on you may hurry the days along with Fast Forward.",
     {"highlight_words": ["Fast Forward"], "auto_advance_ms": 3000}),
    ("Cyril", "Don’t worry about the watering while the days pass. The other friars will see to it.",
     {"highlight_words": ["watering"]}),
    # Part 3 is only complete once Fast Forward has been tried. The Fast
    # Forward button (and the F key) unlocks only now, with this line.
    # The first Fast Forward: 3 days suggested, at most 5 (see "ff_days").
    ("Cyril", "Go on, give Fast Forward a try!",
     {"highlight_words": ["Fast Forward"], "highlight_target": "fast_button",
      "unlock_buttons": ["fast_btn"], "ff_days": (3, 5),
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "ff_used"}),
    ("Cyril", "Wonderful, now you’re fully in control of time!",
     {"mood": 2}),
    ("Cyril", "That will indeed prove most useful for your experiments!",
     {"auto_advance_ms": 5000}),
]


# Part 4 (start) — the plants grow old. Cyril comes back once
# _SENESCENT_FOR_PART_4 plants are senescent (see _watch_for_ageing); a
# running Fast Forward stops for it.
LECTURE_AGEING_DIALOGUE = [
    # Mendel grew up on his family's farm in Heinzendorf — he knows peas are
    # annuals; Cyril talks to him as to a fellow gardener, not a beginner.
    ("Mendel", "Cyril, the first plants are beginning to wither.",
     {"portrait": "mendel", "highlight_words": ["beginning to wither"]}),
    ("Mendel", "Their season is nearly over.",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "So it is. But you know that better than I do, Gregor.",
     {"mood": 2}),
    ("Cyril", "You grew up on a farm.",
     {"highlight_words": ["grew up on a farm"]}),
    ("Cyril", "Their pods are ripe, and their strength is spent.",
     {"pause": True}),
    ("Mendel", "None of them will survive the winter. Only their seeds will.",
     {"portrait": "mendel", "highlight_words": ["Only their seeds"], "pause": True}),
    ("Cyril", "True. Now gather a few more ripe pods. A little advice:",
     {"mood": 2, "highlight_words": ["a few more ripe pods"],
      "unlock_buttons": ["harvest_btn", "inspect_btn"], "pause": True}),
    # The harvest shortcuts, one at a time: waits until a pod has really
    # been picked with S, then with Shift + S (or no ripe pod is left).
    ("Cyril", "Select a plant with ripe pods and press S to quickly pick one pod.",
     {"highlight_words": ["press S"],
      "pause": True, "no_skip": True, "wait_for_condition": "s_key_harvest"}),
    ("Cyril", "And with Shift + S you pick all the pods of a plant at once. Try it!",
     {"highlight_words": ["Shift + S"],
      "pause": True, "no_skip": True, "wait_for_condition": "shift_s_harvest"}),
    # Fast Forward through the winter; Cyril returns on the first day
    # seeds may be sown again, 1 March (see _watch_for_spring). The number of days is worked
    # out when the line is shown, and the Fast Forward window suggests it.
    # Help (H): waits until the help window has been opened.
    ("Cyril", "Oh, and Gregor, should you ever need a little guidance, simply press ‘H’!",
     {"highlight_words": ["H"], "pause": True, "no_skip": True,
      "wait_for_condition": "help_opened"}),
    ("Cyril", "There you’ll find shortcut keys and a handy reminder of all you’ve learned so far.",
     {"highlight_words": ["shortcut keys"], "auto_advance_ms": 3000}),
    ("Cyril", "I shall come back in March, when the sowing can begin again.",
     {"highlight_words": ["in March"], "auto_advance_ms": 2000}),
    # Ends once Fast Forward has been started (it stops by itself on
    # 1 March, see _play_ageing_lecture / _watch_for_spring).
    ("Cyril", lambda app: (f"Now let the winter pass: Fast Forward {_days_until_spring(app)} "
                           f"days, until next spring."),
     {"highlight_words": ["Fast Forward", "next spring"], "highlight_target": "fast_button",
      "pause": True, "no_skip": True, "wait_for_condition": "ff_used", "release_sun": True}),
]

# Part 4 (continued) — the first day of the sowing season (1 March 1857):
# spring is back. A long Fast Forward stops exactly there.
LECTURE_SPRING_DIALOGUE = [
    ("Cyril", "Winter is over, Gregor!",
     {"mood": 2, "highlight_words": ["Winter is over"], "pause": True}),
    ("Cyril", "Spring is here again, the right time to sow the seeds you gathered last summer.",
     {"highlight_words": ["sow the seeds"], "pause": True}),
    ("Cyril", "I wonder what their children will look like?"),
    ("Cyril", "You know what to do, right?",
     {"mood": 2}),
    ("Cyril", "Sow as many seeds as you please.",
     {"highlight_words": ["as many seeds as you please"], "pause": True}),
    # Part 4 crosses a white mother with a purple father: both are needed.
    ("Cyril", "But be sure to sow seeds of your white-flowering and of your purple-flowering "
     "plants: we shall need both colors soon.",
     {"highlight_words": ["white-flowering", "purple-flowering"], "pause": True}),
    # No seeds of one colour left? Cyril hands over a few (true-breeding).
    ("Cyril", lambda app: _missing_colour_line(app),
     {"highlight_words": ["take a few of mine"], "skip_if": "both_colours_available",
      "give_colour_seeds": True, "pause": True}),
    # Garden 2 opens with this line (it stays closed in the tutorial
    # until now — see GardenApp._plot_open).
    ("Cyril", "Oh, and there’s another strip of garden available to you.",
     {"highlight_words": ["another strip of garden"], "highlight_target": "plot2_button",
      "glow_targets": ["plot2_button"],
      # it sits at the far right, easily missed: after 6 s Cyril says where
      "nudge": (6000, "Up there, at the very right, Gregor: click the »2« next to "
                      "»Mendel’s Garden«.", ["»2«"]),
      "open_plot2": True, "pause": True, "no_skip": True,
      "wait_for_condition": "plot2_shown"}),          # the player opens garden 2
    ("Cyril", "Feel free to use it whenever you need to."),
    # Fast Forward to the next sunny morning before sowing: sowing stays
    # blocked from the start of this visit until then (see _watch_for_spring
    # and "allow_sowing").
    # A thunderstorm comes up with this line, so »Skip to next sunny
    # day« really has something to skip (see "force_weather").
    ("Cyril", "But wait for a fine, sunny day before you sow.",
     {"highlight_words": ["sunny day"], "force_weather": "\u26c8", "pause": True}),
    ("Cyril", "Fast Forward can take you straight there.",
     {"highlight_words": ["Fast Forward"]}),
    # The »▶▶ ☀« button is handed over with this line (locked until now).
    ("Cyril", "Click the button with the sun next to it: it skips straight to the next sunny "
     "morning.",
     {"highlight_words": ["button with the sun", "next sunny morning"],
      "highlight_target": "sunny_button", "glow_targets": ["sunny_button"],
      "unlock_buttons": ["sunny_ff_btn"],
      "pause": True, "no_skip": True, "wait_for_condition": "sunny_skip_used",
      "release_sun": True}),
    ("Cyril", "Ah, there you go.",
     {"mood": 2, "allow_sowing": True, "real_time": True}),
    ("Mendel", "A fine sunny morning, just right for sowing and crossing!",
     {"portrait": "mendel", "highlight_words": ["sowing and crossing"], "pause": True}),
    # Waits until plants of both flower colours grow (Cyril hands over
    # seeds of a colour that cannot be sown any more, see _both_colours_sown).
    ("Cyril", "Well done! Sow your seeds now, and remember: white-flowering and purple-flowering ones.",
     {"highlight_words": ["white-flowering", "purple-flowering"], "highlight_target": "plant_button",
      "unlock_buttons": ["plant_seeds_btn"], "pause": True, "no_skip": True,
      "wait_for_condition": "both_colours_sown"}),
    ("Cyril", "Good, both colors are in the ground. Call me when they begin to bud.",
     {"mood": 2, "highlight_words": ["both colors"], "auto_advance_ms": 5000}),
]


# ============================================================================
# Part 5 — Crossing. Three visits of Cyril in the new season:
#   1. the first buds: choosing the parents and emasculating a bud,
#   2. the emasculated flower is open: collecting pollen from the father
#      and pollinating the mother,
#   3. the crossed pod is ripe: harvesting the first crossed seeds.
# Each visit starts by itself (see _watch_for_cross_visit); a running Fast
# Forward stops for it. Cyril only comes by in the morning.
# ============================================================================
LECTURE_CROSS_1_DIALOGUE = [
    ("Mendel", "Cyril, the new plants are budding.",
     {"portrait": "mendel", "highlight_words": ["budding"], "highlight_plants": 4, "pause": True}),
    ("Mendel", "This time I want to do more than just watch them.",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "You wish to cross them, am I right?",
     {"mood": 2, "highlight_words": ["cross them"]}),
    ("Cyril", "And to choose the father yourself instead of leaving it to the flower?"),
    ("Mendel", "Exactly. A pea flower pollinates itself before it opens.",
     {"portrait": "mendel", "pause": True}),
    ("Mendel", "If I want a cross, I must be quicker.",
     {"portrait": "mendel", "highlight_words": ["I must be quicker"], "pause": True}),
    ("Cyril", "Then first choose your two parents.",
     {"highlight_words": ["two parents"]}),
    ("Cyril", "For now, they should differ in one trait you can clearly see.",
     {"pause": True}),
    ("Cyril", "And both must breed true if you truly want to learn anything of value.",
     {"highlight_words": ["breed true"], "pause": True}),
    ("Mendel", "I believe the white one’s seeds always yield white-flowered plants.",
     {"portrait": "mendel", "pause": True}),
    ("Mendel", "But of the purple-flowered plants, I am not so certain.",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "Yours do, Gregor. These lines have bred true in this garden for many years.",
     {"mood": 2, "highlight_words": ["bred true"]}),
    ("Mendel", "Then whatever their children show comes from the cross itself.",
     {"portrait": "mendel", "highlight_words": ["from the cross itself"], "pause": True}),
    # The mother's colour: white if a white plant has a bud, otherwise
    # purple (and the father the other colour), see _choose_mother_colour.
    ("Cyril", lambda app: (f"Let us take a {_choose_mother_colour(app)}-flowering plant as the mother, "
                           f"and a {_other_colour(_choose_mother_colour(app))} one as the father."),
     {"highlight_words": ["white-flowering plant as the mother", "purple one as the father",
                         "purple-flowering plant as the mother", "white one as the father"],
      "pause": True}),
    ("Cyril", "Then we’ll see whose flower color their offspring inherit."),
    ("Cyril", "As you know, the mother must not pollinate herself."),
    ("Cyril", "So you take away her anthers while the flower is still a bud.",
     {"highlight_words": ["take away her anthers", "still a bud"], "pause": True}),
    # Waits until a plant with buds is shown in the inspection window
    # (opened with every section closed).
    ("Cyril", lambda app: f"Now, select a {_tut_mother_colour(app)}-flowering plant as the mother and inspect it.",
     {"highlight_words": ["white-flowering", "purple-flowering", "mother", "inspect"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"], "inspector_closed": True,
      "wait_for_condition": "white_budding_inspected", "highlight_plants": "white_buds"}),
    # Waits until the Crossing section is open.
    ("Cyril", "Open »Crossing«. There you see all its buds and flowers.",
     {"highlight_words": ["Crossing"], "highlight_target": "inspector_crossing_toggle",
      "highlight_late": True, "glow_targets": ["inspector_crossing_toggle"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "crossing_section_open"}),
    # Waits until a bud is selected; the buds glow.
    ("Cyril", "Click a bud to select it. Then take the forceps.",
     {"highlight_words": ["a bud", "forceps"],
      "glow_targets": ["inspector_bud_cells", "inspector_emasc_button"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "bud_selected", "clear_flower_selection": True}),
    # Waits until a flower has been emasculated.
    ("Cyril", "Carefully now: remove all ten anthers, one by one.",
     {"highlight_words": ["all ten anthers"]}),
    ("Cyril", "Not a single one may stay.",
     {"highlight_target": "inspector_emasc_button", "highlight_late": True, "glow_targets": ["inspector_emasc_button"], "portrait": "mendel", "pause": True, "no_skip": True, "wait_for_condition": "flower_emasculated"}),
    ("Cyril", "Well done, Gregor! See the little »E« attached?",
     {"mood": 2, "highlight_words": ["»E«"]}),
    ("Cyril", "It marks the flower you emasculated.",
     {"pause": True}),
    ("Mendel", "Now it can only be fertilized by the pollen I choose.",
     {"portrait": "mendel", "highlight_words": ["the pollen I choose"], "pause": True}),
    ("Cyril", "But not yet.",
     {"highlight_words": ["not yet"]}),
    ("Cyril", "The stigma needs another day or two before it is ready for pollination."),
    ("Cyril", "I shall come back when the flower has opened.",
     {"auto_advance_ms": 4000}),
    ("Cyril", "You may go ahead and emasculate a few more flowers...",
     {"highlight_words": ["emasculate a few more flowers"], "auto_advance_ms": 3000}),
    ("Cyril", "...perhaps on the same plant? Or on different ones.",
     {"auto_advance_ms": 2000}),
    ("Cyril", "Either way, it will be good practice.",
     {"mood": 2, "highlight_words": ["good practice"], "auto_advance_ms": 5000}),
]

LECTURE_CROSS_2_DIALOGUE = [
    ("Mendel", "Cyril, the flower I emasculated has opened!",
     {"portrait": "mendel", "highlight_words": ["has opened"], "pause": True}),
    ("Cyril", "Good! Now you need pollen from the father, and it must be fresh.",
     {"mood": 2, "highlight_words": ["pollen from the father"]}),
    ("Cyril", "One must not wait too long, lest the pollen dry out.",
     {"highlight_words": ["dry out"], "pause": True}),
    # Cyril has chosen the father: a plant whose pollen is ripe right now
    # (see _pick_tutorial_father) — it is marked in the garden.
    ("Cyril", lambda app: (f"I found a {_father_colour(app)}-flowering plant with fresh pollen "
                           f"this morning and marked it for you."),
     {"highlight_words": ["fresh pollen", "marked"], "highlight_plants": "father",
      "pause": True, "real_time": True}),
    # Waits until that plant is shown in the inspection window.
    ("Cyril", "Select it as the father and inspect it.",
     {"highlight_words": ["father", "inspect"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "unlock_buttons": ["inspect_btn"], "inspector_closed": True,
      "wait_for_condition": "father_inspected", "highlight_plants": "father"}),
    ("Cyril", "Open »Crossing« again.",
     {"highlight_words": ["Crossing"], "highlight_target": "inspector_crossing_toggle",
      "highlight_late": True, "glow_targets": ["inspector_crossing_toggle"],
      "highlight_plants": "father",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "crossing_section_open"}),
    # Waits until an open flower of the father is selected.
    ("Cyril", "Remember that the anthers are only ready in the morning.",
     {"highlight_plants": "father", "glow_targets": ["inspector_father_cell"],
      "auto_advance_ms": 1500}),
    # Waits until the flower Cyril marked (ripe anthers) is selected.
    ("Cyril", "Now find an open flower. I shall mark it for you.",
     {"highlight_words": ["open flower"], "glow_targets": ["inspector_father_cell"],
      "highlight_plants": "father",
      "clear_flower_selection": True,
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "open_flower_selected"}),
    # Waits until the brush window is open (or the pollen is already taken).
    ("Cyril", "Now click »Collect«.",
     {"highlight_words": ["Collect"], "highlight_target": "inspector_pollen_button",
      "highlight_late": True, "highlight_plants": "father",
      "glow_targets": ["inspector_pollen_button", "inspector_father_cell"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "brush_window_open"}),
    # Shown once the brush window is open (they go on by themselves: the
    # player's hands are busy in that window).
    ("Cyril", "Yes, that’s it. Here is my camel-hair brush.",
     {"highlight_words": ["camel-hair brush"], "skip_if": "pollen_collected",
      "auto_advance_ms": 3000}),
    ("Cyril", "Stroke its tip lightly over the tips of five anthers. That is where the "
     "yellow pollen sits.",
     {"highlight_words": ["tips of five anthers", "yellow pollen"],
      "skip_if": "pollen_collected", "auto_advance_ms": 4500}),
    ("Cyril", "Gently, Gregor! You need not press: a light touch on each tip is enough.",
     {"highlight_words": ["light touch"], "skip_if": "pollen_collected",
      "auto_advance_ms": 4000}),
    # Shown while the brush window is open; waits until it closes.
    ("Cyril", "Brush over five anther tips, one after the other. Watch the brush turn yellow.",
     {"highlight_words": ["five anther tips", "turn yellow"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "skip_if": "pollen_collected", "wait_for_condition": "brush_window_closed"}),
    # Only when the window was closed without pollen; waits for the pollen.
    ("Cyril", "No pollen yet. Click »Collect« again and brush five anther tips.",
     {"highlight_words": ["Collect", "five anther tips"],
      "highlight_target": "inspector_pollen_button", "highlight_late": True,
      "glow_targets": ["inspector_pollen_button"], "highlight_plants": "father",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "skip_if": "pollen_collected", "wait_for_condition": "pollen_collected"}),
    ("Cyril", "Marvellous! Your brush carries the pollen.",
     {"highlight_words": ["brush"], "pause": True}),
    ("Cyril", "Now let us return to the mother plant.",
     {"highlight_words": ["mother plant"]}),
    # Waits until the mother (emasculated, open flower) is shown.
    ("Cyril", "Alright, now inspect your emasculated mother plant again.",
     {"highlight_words": ["emasculated mother plant"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "mother_inspected", "highlight_plants": "mother"}),
    # Waits until the open, emasculated flower is selected.
    ("Cyril", "Select the open flower marked with »E«.",
     {"highlight_words": ["»E«"], "glow_targets": ["inspector_emasc_open_cells"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "emasc_flower_selected", "clear_flower_selection": True}),
    ("Cyril", "The fresh pollen goes onto her stigma: the green tip of the pistil, inside the keel.",
     {"highlight_words": ["stigma"], "pause": True}),
    ("Cyril", "You have to bring the brush straight to it and dab it on gently.",
     {"highlight_words": ["straight", "dab it on gently"], "pause": True}),
    # Waits until the pollination window is open (or the flower pollinated).
    ("Cyril", "Now click »Pollinate«.",
     {"highlight_words": ["Pollinate"], "highlight_target": "inspector_pollinate_button",
      "highlight_late": True, "glow_targets": ["inspector_pollinate_button"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "pollinate_window_open"}),
    # Shown while the pollination window is open; waits until it closes.
    ("Cyril", "See the stigma? Move the brush tip onto it, slowly.",
     {"highlight_words": ["brush tip onto it"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "skip_if": "flower_pollinated", "wait_for_condition": "pollinate_window_closed"}),
    # Only when the window was closed before the pollen was on the stigma.
    ("Cyril", "Not yet! Click »Pollinate« again and touch the stigma with the brush tip.",
     {"highlight_words": ["Pollinate", "stigma"],
      "highlight_target": "inspector_pollinate_button", "highlight_late": True,
      "glow_targets": ["inspector_pollinate_button"],
      "portrait": "mendel", "pause": True, "no_skip": True,
      "skip_if": "flower_pollinated", "wait_for_condition": "flower_pollinated"}),
    ("Cyril", "Splendid, Gregor, you did it! See the little »P«?",
     {"mood": 2, "highlight_words": ["»P«"]}),
    ("Cyril", "It marks the flower you pollinated by hand.",
     {"pause": True}),
    ("Mendel", "So these seeds will have two parents: this mother, and the father I chose.",
     {"portrait": "mendel", "highlight_words": ["two parents"], "pause": True}),
    ("Cyril", "Yes, if all went well."),
    # (Mendel 1866: the closed keel protects the pea flower; only the pea
    # beetle Bruchus pisi now and then brings foreign pollen)
    ("Cyril", "Bees and butterflies may visit, but the pea keeps its flower closed and pollinates itself.",
     {"highlight_words": ["keeps its flower closed"], "pause": True}),
    ("Cyril", "Only a little beetle sometimes creeps inside, bringing pollen from other "
     "plants, God knows which!",
     {"highlight_words": ["little beetle"], "pause": True}),
    ("Cyril", "Be sure to catch it whenever you spot one.",
     {"highlight_words": ["catch it"], "pause": True}),
    # Points at the inspection window's »Wildlife« tab (if the window is
    # open) without asking the player to go there.
    ("Cyril", "Under »Wildlife« in the inspection window you can see what it looks like.",
     {"highlight_words": ["Wildlife"], "highlight_target": "inspector_wildlife_toggle",
      "highlight_late": True, "glow_targets": ["inspector_wildlife_toggle"], "pause": True}),
    ("Cyril", lambda app: _weevil_line(app),
     {"highlight_words": ["there is one now", "click on it", "click on one"],
      "highlight_plants": "weevil", "pause": True, "no_skip": True,
      "wait_for_condition": "weevil_caught"}),
    ("Cyril", lambda app: _weevil_after_line(app),
     {"mood": 2, "highlight_words": ["Well caught"], "clear_plant_highlight": True}),
    ("Cyril", "All the more reason to pay close attention to our plants.",
     {"highlight_words": ["pay close attention"], "auto_advance_ms": 3000}),
    ("Cyril", "One more thing: write a note on this plant about the cross you made.",
     {"highlight_words": ["write a note"], "pause": True}),
    # Waits until a note has been saved (»Make note« in the inspection
    # window — pointed at while the window is open).
    ("Cyril", lambda app: _note_example_line(app),
     {"highlight_words": ["For example", "useful later"], "highlight_target": "inspector_note_button",
      "highlight_late": True, "glow_targets": ["inspector_note_button"],
      "pause": True, "no_skip": True, "wait_for_condition": "note_saved"}),
    ("Cyril", "That’s all for now. I shall come back when its pod is ripe.",
     {"auto_advance_ms": 5000}),
]

LECTURE_CROSS_3_DIALOGUE = [
    ("Mendel", "Cyril, the pod of my cross is ripe!",
     {"portrait": "mendel", "highlight_words": ["my cross", "ripe"], "pause": True,
      "pod_click_only": True, "cross_pods_only": True}),
    ("Cyril", "Then let us pick it. Its seeds are the first children (F1) of your own cross.",
     {"highlight_words": ["first children (F1)"], "portrait": "mendel", "pause": True,
      "pod_click_only": True, "cross_pods_only": True}),
    ("Cyril", "But careful: the flowers you left alone have pollinated themselves and made pods too.",
     {"highlight_words": ["pollinated themselves"], "pause": True,
      "pod_click_only": True, "cross_pods_only": True}),
    ("Cyril", "The pod of your cross is marked with a »P«, on its plot and in the inspection window.",
     {"highlight_words": ["»P«"], "glow_targets": ["inspector_cross_pod_cells"], "pause": True,
      "pod_click_only": True, "cross_pods_only": True}),
    # Waits until the crossed pod has been harvested; until then only pods
    # marked »P« can be harvested (their seeds stay apart from the selfed ones).
    # Picked by hand in the inspection window: the Harvest button, the S
    # keys and »Harvest All« wait until the »P« pod has been clicked.
    ("Cyril", "Inspect the mother plant and open »Harvest«.",
     {"highlight_words": ["Inspect the mother plant", "Harvest"],
      "highlight_target": "inspect_button", "highlight_plants": "cross_ripe",
      "unlock_buttons": ["inspect_btn"], "inspector_closed": True,
      "glow_targets": ["inspector_harvest_toggle"], "pod_click_only": True,
      "cross_pods_only": True, "portrait": "mendel", "pause": True, "no_skip": True,
      "skip_if": "cross_pod_shown", "wait_for_condition": "cross_pod_shown"}),
    ("Cyril", "Now pick only the pods marked »P« to keep crossed and selfed seeds separate.",
     {"highlight_words": ["the pods marked »P«", "keep crossed and selfed seeds separate"],
      "portrait": "mendel",
      "pause": True, "no_skip": True, "highlight_plants": "cross_ripe",
      "glow_targets": ["inspector_cross_pod_cells"], "pod_click_only": True,
      "cross_pods_only": True, "wait_for_condition": "crossed_pod_harvested"}),
    ("Mendel", "And when they grow, I will see whose flower color they carry.",
     {"portrait": "mendel", "highlight_words": ["whose flower color"], "pause": True}),
    ("Cyril", "Exactly, Gregor. And that is where the real work begins.",
     {"highlight_words": ["the real work"], "pause": True}),
    ("Mendel", "Uncovering how these seven traits are inherited.",
     {"portrait": "mendel", "highlight_words": ["seven traits"], "pause": True}),
    ("Cyril", "Indeed! Sow them, and their flowers will reveal which color they inherited.",
     {"mood": 2, "highlight_words": ["which color they inherited"], "auto_advance_ms": 5000}),
    ("Mendel", "That’s our first discovery already! No one has ever done that before!",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "Don’t we live in a wondrous time?",
     {"mood": 2}),
]


def _encourage_ff_dialogue(days):
    """Cyril's lines when the player agrees to the next lesson but the
    plants aren't old yet: hurry the days along with Fast Forward."""
    d = f"{days} day" + ("" if days == 1 else "s")
    return [
        ("Cyril", "Splendid! For the next lesson, your plants must grow a little older.",
         {"mood": 2, "highlight_words": ["grow a little older"]}),
        ("Cyril", f"Use Fast Forward for about {d} and watch what happens to them.",
         {"highlight_words": ["Fast Forward", d]}),
        ("Cyril", "I shall come back when the time is right.",
         {"highlight_target": "fast_button", "auto_advance_ms": 5000}),
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
    "sunny_button": lambda app: getattr(app, "sunny_ff_btn", None),
    # the "2" of "Mendel's Garden: 1 2" (garden 2 opens in part 4)
    "plot2_button": lambda app: (list(getattr(app, "_plot_switcher_btns", None) or [None, None]) + [None, None])[1],
    "harvest_button": lambda app: getattr(app, "harvest_btn", None),
    "laws_button": lambda app: getattr(app, "btn_test_laws", None),
    "monastery_button": lambda app: getattr(app, "monastery_btn", None),
    "remove_button": lambda app: getattr(app, "remove_btn", None),
    # the »Generation« choices in the Choose Seeds window (glow only)
    "seed_cross_tick": lambda app: _live_widget(getattr(app, "_seed_filter_btn", None)),
    "seed_crossed_cb": lambda app: _live_widget((getattr(app, "_seed_gen_rbs", None) or {}).get("F1")),
    "seed_ofcross_cb": lambda app: _live_widget((getattr(app, "_seed_gen_rbs", None) or {}).get("F2")),
    # "Harvest All" inside the plant inspector window (only while open).
    "inspector_harvest_button": lambda app: _live_widget(getattr(app, "_inspector_harvest_btn", None)),
    # The "Harvest" section button at the top of the inspector.
    "inspector_harvest_toggle": lambda app: _live_widget(
        (getattr(app, "_inspector_section_btns", None) or {}).get("harvest")),
    # Part 5 (crossing): the inspector's Crossing button, forceps,
    # Pollinate, "Collect Pollen", "Make note" and flower cells (the cell
    # targets give a list of widgets — glow only, no arrow).
    "inspector_crossing_toggle": lambda app: _live_widget(
        (getattr(app, "_inspector_section_btns", None) or {}).get("crossing")),
    "inspector_wildlife_toggle": lambda app: _live_widget(
        (getattr(app, "_inspector_section_btns", None) or {}).get("wildlife")),
    "inspector_emasc_button": lambda app: _live_widget(getattr(app, "_inspector_emasc_btn", None)),
    "inspector_pollinate_button": lambda app: _live_widget(getattr(app, "_inspector_pollinate_btn", None)),
    # "Collect Pollen" only while the selected flower really has ripe anthers
    "inspector_pollen_button": lambda app: (
        _live_widget(_flower_panel_part(app, "pollen_btn")) if _ripe_flower_selected(app) else None),
    "inspector_note_button": lambda app: _live_widget(getattr(app, "_inspector_note_btn", None)),
    "inspector_bud_cells": lambda app: _flower_cells(app, lambda st, f: st == "bud" and not _hand_emasc(f)),
    # open flowers whose anthers are ripe right now (pollen can be taken)
    "inspector_open_cells": lambda app: _ripe_flower_cells(app),
    # the flower Cyril chose on the father (crossing visit 2)
    "inspector_father_cell": lambda app: _father_cell(app),
    # pods from hand-pollinated flowers (marked »P«) in the inspector
    "inspector_cross_pod_cells": lambda app: [w for w in list(getattr(app, "_inspector_cross_pod_lbls", None) or [])
                                              if _live_widget(w) is not None],
    "inspector_emasc_open_cells": lambda app: _flower_cells(app, lambda st, f: st == "open" and _hand_emasc(f)),
    # The inspector's "Close" button.
    "inspector_close_button": lambda app: _live_widget(getattr(app, "_inspector_close_btn", None)),
    # ...and its "Traits" section button.
    "inspector_traits_toggle": lambda app: _live_widget(
        (getattr(app, "_inspector_section_btns", None) or {}).get("traits")),
    # Part 5: the Genotype Viewer / TIE buttons and parts of the TIE
    # (glow only — no arrows into other windows)
    "inspector_genotype_button": lambda app: _live_widget(getattr(app, "_inspector_genotype_btn", None)),
    "inspector_tie_button": lambda app: _live_widget(getattr(app, "_inspector_tie_btn", None)),
    # the way back into a window the player closed: its button in the
    # inspection window (only while that window is closed)
    "tie_reopen": lambda app: (None if _tie(app) is not None
                               else _live_widget(getattr(app, "_inspector_tie_btn", None))),
    "gv_reopen": lambda app: (None if _live_widget(getattr(app, "_genotype_viewer_win", None))
                              is not None
                              else _live_widget(getattr(app, "_inspector_genotype_btn", None))),
    "tie_list": lambda app: _live_widget(getattr(_tie(app), "listbox", None)),
    "tie_tree": lambda app: _live_widget(getattr(_tie(app), "canvas", None)),
    "tie_trait_buttons": lambda app: _live_widget(getattr(_tie(app), "_trait_bar", None)),
    "tie_seed_color_btn": lambda app: _live_widget((getattr(_tie(app), "_trait_rbs", None) or {}).get("Seed color")),
    "tie_flower_color_btn": lambda app: _live_widget((getattr(_tie(app), "_trait_rbs", None) or {}).get("Flowers")),
    "tie_pods": lambda app: _live_widget(getattr(_tie(app), "pods_scroll_canvas", None)),
    "tie_total_ratio": lambda app: _live_widget(getattr(getattr(_tie(app), "pods_row", None), "_ratio_inline", None)),
    "tie_tabs": lambda app: _live_widget(getattr(_tie(app), "_section_bar", None)),
    "tie_ratio_btn": lambda app: _live_widget((getattr(_tie(app), "_section_btns", None) or {}).get("ratio")),
    "tie_punnett_btn": lambda app: _live_widget((getattr(_tie(app), "_section_btns", None) or {}).get("punnett")),
    "tie_pods_btn": lambda app: _live_widget((getattr(_tie(app), "_section_btns", None) or {}).get("pods")),
    "tie_best_fit": lambda app: _live_widget(getattr(_tie(app), "_cross_best_btn", None)),
    "tie_reveal_button": lambda app: [w for w in (_live_widget(getattr(_tie(app), "_reveal_btn", None)),
                                                  _live_widget(getattr(app, "_gv_reveal_btn", None)))
                                      if w is not None],
    "tie_show_alleles": lambda app: _live_widget(getattr(_tie(app), "_alleles_cb", None)),
}


def _hand_emasc(f):
    """The flower was emasculated by hand (with the forceps) — not just
    emptied by taking all its anthers for pollen."""
    e = f.get("emasc") if isinstance(f, dict) else None
    return bool(e) and not (isinstance(e, dict) and e.get("by_pollen_collection"))


def _dialog_open(app, cls_name):
    """A window of class `cls_name` (the brush or pollination window) is
    open on the screen."""
    try:
        for w in app.root.winfo_children():
            if type(w).__name__ == cls_name and w.winfo_exists():
                return True
    except Exception:
        pass
    return False


def _has_anthers(f):
    """An open flower that still has anthers to give pollen."""
    return not f.get("emasc") and int(f.get("anthers_removed", 0) or 0) < 10


def _anthers_ripe_now(app, plant, k, st, f):
    """Flower k of `plant` gives pollen right now: open, anthers left and
    ripe today (the same check "Collect Pollen" itself makes)."""
    if st != "open" or not _has_anthers(f):
        return False
    try:
        return bool(app._flower_anthers_ready(plant, k))
    except Exception:
        return False


def _ripe_flower_selected(app):
    p = _selected_living_plant(app)
    if p is None:
        return False
    return any(_anthers_ripe_now(app, p, k, st, f) for k, st, f in _selected_flowers(app))


def _ripe_flower_cells(app):
    """The flower cells of the shown plant whose anthers are ripe now."""
    try:
        pid, st = getattr(app, "_inspector_flower_panel_st", None) or (None, None)
        p = _selected_living_plant(app)
        if not st or p is None or getattr(p, "id", None) != pid:
            return []
        states, fl = st.get("states") or [], st.get("fl") or []
        out = []
        for k, (cell, _ic) in (st.get("cells") or {}).items():
            if (k < len(states) and k < len(fl)
                    and _anthers_ripe_now(app, p, k, states[k], fl[k])
                    and _live_widget(cell) is not None):
                out.append(cell)
        return out
    except Exception:
        return []


def _flower_panel_part(app, key):
    """Something from the inspector's flower panel (see inspector.py
    _build_flower_panel), or None."""
    try:
        _pid, st = getattr(app, "_inspector_flower_panel_st", None) or (None, None)
        return (st or {}).get(key)
    except Exception:
        return None


def _flower_cells(app, want):
    """The flower cells in the inspector's Crossing row whose (state,
    flower record) satisfy `want`."""
    try:
        _pid, st = getattr(app, "_inspector_flower_panel_st", None) or (None, None)
        if not st:
            return []
        out = []
        states, fl = st.get("states") or [], st.get("fl") or []
        for k, (cell, _ic) in (st.get("cells") or {}).items():
            if k < len(states) and k < len(fl) and want(states[k], fl[k]):
                if _live_widget(cell) is not None:
                    out.append(cell)
        return out
    except Exception:
        return []


def _selected_living_plant(app):
    try:
        idx = getattr(app, "selected_index", None)
        p = app.tiles[idx].plant if idx is not None else None
        return p if p is not None and getattr(p, "alive", True) else None
    except Exception:
        return None


def _flower_info(app, plant):
    """[(k, state, flower record)] for every flower of `plant`."""
    try:
        states = app._flower_states(plant)
        fl = plant.ensure_flowers()
        return [(k, states[k], fl[k]) for k in range(min(len(states), len(fl)))]
    except Exception:
        return []


def _selected_flowers(app):
    """[(k, state, flower)] of the flowers selected in the inspector for the
    selected plant."""
    p = _selected_living_plant(app)
    if p is None:
        return []
    sel = (getattr(app, "_flower_sel", None) or {}).get(getattr(p, "id", None)) or ()
    info = dict((k, (st, f)) for k, st, f in _flower_info(app, p))
    return [(k,) + info[k] for k in sel if k in info]


def _inspector_shows(app, want):
    """The inspection window is open and shows a plant with a flower that
    satisfies want(state, flower)."""
    if _live_widget(getattr(app, "_inspector_win", None)) is None:
        return False
    p = _selected_living_plant(app)
    return p is not None and any(want(st, f) for _k, st, f in _flower_info(app, p))


def _all_flowers(app):
    """(plant, k, state, flower) for every flower of every living plant."""
    out = []
    for p in _living_plant_list(app):
        for k, st, f in _flower_info(app, p):
            out.append((p, k, st, f))
    return out


def _flower_colour(p):
    try:
        return str((getattr(p, "traits", {}) or {}).get("flower_color", "")).lower()
    except Exception:
        return ""


def _close_inspector_section(app, key):
    """Folds one section of the inspection window (e.g. the big Wildlife
    table) — rebuilt at once if the window is open."""
    try:
        secs = app._inspector_sections()
        if not secs.get(key):
            return
        secs[key] = False
        try:
            app._save_inspector_sections()
        except Exception:
            pass
        win = _live_widget(getattr(app, "_inspector_win", None))
        idx = getattr(app, "selected_index", None)
        plant = app.tiles[idx].plant if (idx is not None and 0 <= idx < len(app.tiles)) else None
        if win is not None and plant is not None:
            app._open_plant_inspector(plant)
    except Exception:
        pass


def _missing_seed_colours(app):
    """Flower colours ("white" / "purple") the player has no seeds of
    for Part 4's cross: selfed seeds in the bag (they breed true) and
    the anonymous seeds (which come in both colours) count."""
    have = set()
    try:
        if int(getattr(app, "available_seeds", 0) or 0) >= 2:
            have |= {"white", "purple"}
        for c in list(getattr(app, "_tut_starter_colours", None) or []):
            have.add(c)
        for sd in list(getattr(app, "harvest_inventory", []) or []):
            d = sd.get("donor_id")
            if d not in (None, "", sd.get("source_id")):
                continue                      # crossed seed: not true-breeding
            c = str((sd.get("traits") or {}).get("flower_color", "")).lower()
            if c:
                have.add(c)
    except Exception:
        return []
    return [c for c in ("white", "purple") if c not in have]


def _missing_colour_line(app):
    miss = _missing_seed_colours(app) or getattr(app, "_tut_gave_colours", None) or ["white"]
    what = " or ".join(miss) if len(miss) > 1 else miss[0]
    return f"I see you have no {what}-flowering seeds left. Here, take a few of mine."


def _give_colour_seeds(app, per_colour=3, only=None):
    """Abbot Cyril's own seeds for the colours missing (sown like the
    starter seeds; see GardenApp._tut_starter_colours). `only`: just
    these colours (if they are missing)."""
    miss = _missing_seed_colours(app)
    if only is not None:
        miss = [c for c in miss if c in only]
    if not miss:
        return
    app._tut_gave_colours = list(miss)
    q = list(getattr(app, "_tut_starter_colours", None) or [])
    for c in miss:
        q += [c] * per_colour
    app._tut_starter_colours = q
    app.available_seeds = int(getattr(app, "available_seeds", 0) or 0) + per_colour * len(miss)
    try:
        app._refresh_seed_counter_var()
    except Exception:
        pass
    try:
        app._toast("Abbot Cyril hands you " + " and ".join(
            f"{per_colour} {c}-flowering" for c in miss) + " seeds.", level="info")
    except Exception:
        pass
    _play_sound_via_app(app, "harvest_all.ogg")


def _budding_plants(app):
    budding = []
    for p in _living_plant_list(app):
        try:
            if any(st == "bud" and not _hand_emasc(f) for _k, st, f in _flower_info(app, p)):
                budding.append(p)
        except Exception:
            pass
    return budding


def _other_colour(c):
    return "purple" if c == "white" else "white"


def _choose_mother_colour(app):
    """Part 4's mother: white-flowering if a white plant has a bud to
    emasculate, otherwise purple (the father is then white). Chosen once
    when Cyril proposes it; kept in app._tut_mother_colour."""
    c = getattr(app, "_tut_mother_colour", None)
    if c in ("white", "purple"):
        return c
    cols = {_flower_colour(p) for p in _budding_plants(app)}
    c = "white" if ("white" in cols or "purple" not in cols) else "purple"
    app._tut_mother_colour = c
    return c


def _tut_mother_colour(app):
    """The colour of the cross's mother: the one Cyril chose, or (after
    loading a saved garden) that of the mother of the crossed seeds."""
    c = getattr(app, "_tut_mother_colour", None)
    if c in ("white", "purple"):
        return c
    try:
        for p in _living_plant_list(app):
            if _flower_colour(p) and any(_hand_emasc(f) for _k, _st, f in _flower_info(app, p)):
                return _flower_colour(p)
    except Exception:
        pass
    try:
        for sd in list(getattr(app, "harvest_inventory", []) or []):
            d, src = sd.get("donor_id"), sd.get("source_id")
            if d in (None, "") or str(d) == str(src):
                continue
            snap = _archive_snap(app, src) or {}
            c = str((snap.get("traits") or {}).get("flower_color", "")).lower()
            if c in ("white", "purple"):
                return c
    except Exception:
        pass
    try:
        for p in _living_plant_list(app):
            if _is_cross_child(p):
                snap = _archive_snap(app, getattr(p, "mother_id", None)) or {}
                c = str((snap.get("traits") or {}).get("flower_color", "")).lower()
                if c in ("white", "purple"):
                    return c
    except Exception:
        pass
    return "white"


def _father_colour(app):
    fp = _tut_father_plant(app)[0]
    c = _flower_colour(fp) if fp is not None else ""
    return c if c in ("white", "purple") else _other_colour(_tut_mother_colour(app))


def _white_grandparent(app):
    return "grandmother" if _tut_mother_colour(app) == "white" else "grandfather"


def _both_colours_sown(app):
    """Part 4 spring: white- and purple-flowering plants both grow (the
    cross needs one of each). A colour that cannot be sown any more (no
    seeds of it left) is handed over by Cyril."""
    grown = {_flower_colour(p) for p in _living_plant_list(app)
             if not _is_cross_child(p)}
    if {"white", "purple"} <= grown:
        return True
    try:
        need = [c for c in _missing_seed_colours(app) if c not in grown]
        if need and not getattr(app, "_tut_gave_sow_colours", False):
            app._tut_gave_sow_colours = True
            _give_colour_seeds(app, only=need)
    except Exception:
        pass
    return False


def _white_budding_plants(app):
    """Living plants of the mother's colour (see _tut_mother_colour) with
    a bud that can be emasculated — or, if there is none, any such
    budding plant."""
    budding = _budding_plants(app)
    want = _tut_mother_colour(app)
    pref = [p for p in budding if _flower_colour(p) == want]
    return pref or budding


def _cross_mothers(app):
    """Every plant with an open, emasculated flower (possible mothers) —
    white-flowering ones first (the lesson crosses white x purple)."""
    out = []
    for p, _k, st, f in _all_flowers(app):
        if st == "open" and _hand_emasc(f) and p not in out:
            out.append(p)
    want = _tut_mother_colour(app)
    out.sort(key=lambda p: 0 if _flower_colour(p) == want else 1)
    return out


def _cross_mother(app):
    """A plant with an open, emasculated flower (the cross's mother)."""
    for p, _k, st, f in _all_flowers(app):
        if st == "open" and _hand_emasc(f):
            return p
    return None


def _cross_father_ready(app, mother):
    """Another plant with an open flower whose anthers are ripe today."""
    for p in _living_plant_list(app):
        if p is mother:
            continue
        try:
            if not p.can_collect_pollen()[0]:
                continue
        except Exception:
            continue
        for k, st, f in _flower_info(app, p):
            if st == "open" and not _hand_emasc(f):
                try:
                    if app._flower_anthers_ready(p, k):
                        return p
                except Exception:
                    pass
    return None


def _crossed_pod_ripe(app):
    for p, _k, _st, f in _all_flowers(app):
        try:
            if (_hand_emasc(f) and f.get("pollen") and not f.get("harvested")
                    and p.flower_sets_pod(f) and p.pod_is_ripe(f)):
                return True
        except Exception:
            pass
    return False


def _has_ripe_cross_pod(p):
    try:
        return any(_hand_emasc(f) and f.get("pollen") and not f.get("harvested")
                   and p.flower_sets_pod(f) and p.pod_is_ripe(f) for f in p.ensure_flowers())
    except Exception:
        return False


def _cross_pod_shown(app):
    """The inspection window is open on a plant with a ripe »P« pod, at
    its »Harvest« section (or that pod was picked already)."""
    if _crossed_pod_harvested(app):
        return True
    if _live_widget(getattr(app, "_inspector_win", None)) is None:
        return False
    try:
        if not app._inspector_sections().get("harvest"):
            return False
    except Exception:
        return False
    return _has_ripe_cross_pod(_selected_living_plant(app))


def _crossed_pod_harvested(app):
    try:
        plants = [t.plant for t in app._all_plot_tiles() if t.plant is not None]
    except Exception:
        plants = []
    for p in plants:
        try:
            for f in p.ensure_flowers():
                if _hand_emasc(f) and f.get("pollen") and f.get("harvested"):
                    return True
        except Exception:
            pass
    return False


def _click(app, widget, fn):
    """A click on a Label used as a button: acts when the mouse button is
    released over it, after Tk has finished with that release (like the
    game's _bind_click). Closing or rebuilding a window while the button
    is still pressed over it crashed Tk on the Mac."""
    st = {"armed": False}

    def _press(e=None):
        st["armed"] = True

    def _release(e=None):
        if not st["armed"]:
            return
        st["armed"] = False
        try:
            if not (0 <= int(e.x) < widget.winfo_width() and 0 <= int(e.y) < widget.winfo_height()):
                return
        except Exception:
            pass
        try:
            widget._root().after_idle(fn)
        except Exception:
            fn()
    widget.bind("<Button-1>", _press)
    widget.bind("<ButtonRelease-1>", _release)


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
                "monastery_button": "right",
                "inspect_button": "right",
                # beside the »Wildlife« tab (pointing left at it)
                "inspector_wildlife_toggle": "right"}


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
        # (the crossing visits leave the clock alone: putting it back to
        # the morning skipped hours, and the day's pollen with them)
        if (hour >= 17 or hour < 6) and getattr(app, "_tutorial_keep_hours", True):
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


def _fair_weather(app):
    """The real weather is dry (no rain, storm or snow) — Cyril comes for
    a harvest only on such a morning, so rain never gets in the way."""
    try:
        g = app.garden
        if getattr(g, "weather_lock", None):
            return True
        return str(g.weather) not in ("🌧", "⛈", "❄️", "🌨")
    except Exception:
        return True


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


def _hold_morning(app):
    """Crossing visit 2 (pollen and pollination): the clock may not run out
    of the morning on that day — pollen is only collected in working hours
    and put on in the morning or at noon, and a player who sped the clock
    up was stuck at 19:00 (»Mendel is having dinner«). From noon on it is
    put back to 10:00 of the same day (the day's pollen stays good)."""
    if not getattr(app, "_tut_hold_morning", False):
        return
    try:
        g = app.garden
        day = (int(getattr(g, "month", 0)), int(getattr(g, "day_of_month", 0) or 0))
        start = getattr(app, "_tut_hold_morning_day", None)
        if start is None:
            app._tut_hold_morning_day = start = day
        hour = int(g.clock_hour) % 24
        if day == start and hour >= 12:
            from garden import PHASES
            g.clock_hour = 10
            try:
                g.clock_minute = 0
            except Exception:
                pass
            g.phase_index = 0
            g.phase = PHASES[0]
            try:
                app.render_all()
            except Exception:
                pass
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
        _hold_morning(app)
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
    app._tutorial_keep_hours = True           # the watering part keeps working hours
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


def _plants_with_ripe_pods(app):
    n = 0
    for p in _living_plant_list(app):
        try:
            if int(p.ripe_pods()) > 0:
                n += 1
        except Exception:
            pass
    return n


def _key_harvested(app, baseline, key):
    log = list(getattr(app, "_key_harvest_log", []) or [])
    if any(k == key for k, _n in log[int(baseline or 0):]):
        return True
    return _plants_with_ripe_pods(app) == 0


def _plants_harvested_since(app, baseline):
    log = list(getattr(app, "_harvest_log", []) or [])
    return {pid for pid in log[int(baseline or 0):] if pid is not None}


def _other_plant_harvested(app, baseline):
    log = list(getattr(app, "_harvest_log", []) or [])
    b = int(baseline or 0)
    prev = log[b - 1] if 0 < b <= len(log) else None
    return any(pid is not None and pid != prev for pid in log[b:])


OTHER_PLANTS_NEEDED = 3


def _other_plants_status(app, baseline):
    """(plants harvested so far, plants needed) for the "gather from other
    plants" line: plants other than the last one harvested before the line.
    The number needed is lowered when fewer such plants had ripe pods when
    the line began (so the player can never get stuck)."""
    log = list(getattr(app, "_harvest_log", []) or [])
    b = int(baseline or 0)
    prev = log[b - 1] if 0 < b <= len(log) else None
    got = {pid for pid in log[b:] if pid is not None and pid != prev}
    need = getattr(app, "_tut_other_plants_need", OTHER_PLANTS_NEEDED)
    return len(got), need


def _ripe_plants_other_than(app, prev_id):
    n = 0
    for plot in getattr(app, "_plot_tiles", None) or [getattr(app, "tiles", [])]:
        for t in plot:
            p = getattr(t, "plant", None)
            if p is None or not getattr(p, "alive", True) or getattr(p, "id", None) == prev_id:
                continue
            try:
                if int(p.ripe_pods()) > 0:
                    n += 1
            except Exception:
                pass
    return n


def _sticky_harvest(app, baseline):
    if not getattr(app, "_tut_harvest_seen", False):
        if len(getattr(app, "harvest_inventory", []) or []) > int(baseline or 0):
            app._tut_harvest_seen = True
    return bool(getattr(app, "_tut_harvest_seen", False))


def _living_plant_selected(app):
    try:
        idx = getattr(app, "selected_index", None)
        if idx is None:
            return False
        p = app.tiles[idx].plant
        return p is not None and bool(getattr(p, "alive", True))
    except Exception:
        return False


# ============================================================================
# Lines worked out when shown, the weevil lesson and Cyril's questions
# ============================================================================

def _health_line(app):
    """How a plant's health shows: hearts or the bar (Game Settings)."""
    if getattr(app, "_health_hearts_enabled", False):
        return ("Mind your plants’ health, too: the red hearts on each plot. The fewer hearts, "
                "the worse a plant fares.")
    return ("Mind your plants’ health, too: the bar at the bottom of each plot is green when a "
            "plant thrives, and turns red when it suffers.")


def _crossed_mother_plant(app):
    """The plant whose emasculated flower was pollinated by hand."""
    for p, _k, _st, f in _all_flowers(app):
        if _hand_emasc(f) and f.get("pollen"):
            return p
    return _cross_mother(app)


def _tut_weevil_alive(app):
    c = getattr(app, "_tut_weevil", None)
    return c if (c is not None and getattr(c, "_alive", False)) else None


def _weevil_line(app):
    """A pea weevil appears (on the mother plant if it can) for the player
    to catch; the line says where. Without wildlife pictures it only says
    what to do."""
    app._tut_weevil_base = int(getattr(app, "_bruchus_caught", 0) or 0)
    m = _crossed_mother_plant(app)
    c = _tut_weevil_alive(app)
    if c is None:
        tile = None
        for t in list(getattr(app, "tiles", []) or []):
            if m is not None and getattr(t, "plant", None) is m:
                tile = t
        wl = getattr(app, "wildlife", None)
        try:
            c = wl.spawn_tutorial_weevil(tile) if wl is not None else None
        except Exception:
            c = None
        app._tut_weevil = c
        app._tut_weevil_spawned = c is not None
    if c is None:
        return "Whenever you spot one, click on it to catch it."
    if m is not None and getattr(getattr(c, "tile", None), "plant", None) is m:
        return "Look, there is one now, right on your mother plant! Catch it: click on it."
    return "Look, there is one now! Catch it: click on it."


def _weevil_caught(app):
    return int(getattr(app, "_bruchus_caught", 0) or 0) > int(getattr(app, "_tut_weevil_base", 0) or 0)


def _weevil_after_line(app):
    if _weevil_caught(app):
        return "Well caught, Gregor! That one won’t meddle with your cross."
    if not getattr(app, "_tut_weevil_spawned", False):
        return "They come from May to August, so keep your eyes open."
    return "It got away this time. Keep your eyes open."


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")


def _note_example_line(app):
    mc = _tut_mother_colour(app) or "white"
    fc = _other_colour(mc)
    try:
        g = app.garden
        day = int(getattr(g, "day_of_month", getattr(g, "day", 1)) or 1)
        mon = _MONTHS[int(getattr(g, "month", 5)) - 1]
        when = f", {day} {mon}"
    except Exception:
        when = ""
    return f"For example: »♀ {mc} × ♂ {fc}{when}«. It might prove useful later."


def _f1_colour_line(app):
    cols = {_flower_colour(p) for p in _f1_plants(app)
            if int(getattr(p, "stage", 0) or 0) >= 5 and _flower_colour(p)}
    if cols == {"purple"} or not cols:
        return "But look: all of them are purple! Not a single white one."
    if len(cols) == 1:
        return f"But look: all of them {next(iter(cols))}!"
    return "But look at their colors!"


def _white_parent_word(app):
    return "mother" if _tut_mother_colour(app) == "white" else "father"


# --- Cyril's questions -------------------------------------------------------

def _tut_answer(app, key):
    return (getattr(app, "_tut_answers", None) or {}).get(key)


_PREDICT_REPLY = {
    "all_purple": "Like their parents, you think? We shall see.",
    "some_white": "The white back again, you think? We shall see.",
    "half": "Half and half? We shall see.",
    "all_white": "All white? A bold guess, Gregor. We shall see.",
}

_PREDICT_VERDICT = {
    "all_purple": "You expected them all purple, like their parents. Yet the white is back!",
    "some_white": "Just as you guessed, Gregor: the white is back, in a few of them!",
    "half": "You guessed half and half. The white is back indeed.",   # see _predict_verdict
    "all_white": "You expected them all white. Yet most are purple, and only a few white.",
}


def _predict_reply(app):
    return _PREDICT_REPLY.get(_tut_answer(app, "f2_predict"), "We shall see.")


def _predict_verdict(app):
    ans = _tut_answer(app, "f2_predict")
    if ans == "half":
        p, w = _f2_counts(app)
        if w and w * 2 >= p + w - 1:
            return "You guessed half and half. The white is back indeed, in about half of them!"
        return "You guessed half and half. The white is back indeed, but in far fewer than half."
    return _PREDICT_VERDICT.get(ans, "")


def _f2_counts(app):
    """(purple, white): the flowering grandchildren in the garden."""
    p = w = 0
    for q in _f2_plants(app):
        if int(getattr(q, "stage", 0) or 0) < 5:
            continue
        c = _flower_colour(q)
        if c == "purple":
            p += 1
        elif c == "white":
            w += 1
    return p, w


def _tie_family_counts(app):
    """(purple, white) of the family the TIE shows right now — the white
    grandchild's brothers and sisters, counted as the TIE counts them (Pod
    Seeds or Trait Ratio) — or None if the TIE shows no flower colours."""
    t = _tie(app)
    if t is None:
        return None
    fc = getattr(t, "_family_counts", None)
    try:
        pid, key, counts = fc
    except Exception:
        return None
    if key != "flower_color":
        return None
    if str(getattr(t, "current_pid", pid)) != str(pid):
        return None                               # an older plant's count
    p = int(counts.get("purple", 0) or 0)
    w = int(counts.get("white", 0) or 0)
    return (p, w) if p + w > 0 else None


def _ratio_counts(app):
    """What Cyril counts for »how many purple for each white one«: the
    family in the TIE (so his numbers are the ones on screen), else the
    flowering grandchildren in the garden."""
    return _tie_family_counts(app) or _f2_counts(app)


def _ratio_ok(ans, p, w):
    """Is "1", "2", "3" or "4" (4 or more) a fair reading of p purple to w
    white? Near a boundary (e.g. 7 : 2 = 3.5) both neighbours count."""
    if w <= 0:
        return ans == "4"
    r = p / float(w)
    lo, hi = {"1": (0.0, 1.6), "2": (1.4, 2.6), "3": (2.4, 3.6), "4": (3.4, 1e9)}.get(ans, (0, -1))
    return lo <= r < hi


def _ratio_text(r):
    return str(int(round(r))) if abs(r - round(r)) < 0.05 else f"{r:.1f}"


def _ratio_reply(app):
    p, w = getattr(app, "_tut_ratio_counts", None) or _ratio_counts(app)
    if w <= 0:
        return f"{p} purple, and no white one in flower yet."
    rt = _ratio_text(p / float(w))
    if _ratio_ok(_tut_answer(app, "f2_ratio"), p, w):
        return f"Right: {p} purple and {w} white flowers in all."
    return f"Look again: {p} purple and {w} white flowers in all."


def _ratio_mendel(app):
    """Mendel works the ratio out himself after Cyril's count."""
    p, w = getattr(app, "_tut_ratio_counts", None) or _ratio_counts(app)
    if w <= 0:
        return "Not a single white one yet."
    r = p / float(w)
    if 2.5 <= r <= 3.6:
        return "About three to one."
    return f"About {_ratio_text(r)} to one."


def _ratio_moral(app):
    p, w = getattr(app, "_tut_ratio_counts", None) or _ratio_counts(app)
    r = p / float(w) if w else 0.0
    if 2.5 <= r <= 3.6:
        return "Three to one, Gregor. That ratio might be worth remembering."
    return ("With so few plants, a lot is left to chance, Gregor. The more you grow, "
            "the closer your count will come to the real ratio.")


def _close_question(app):
    w = getattr(app, "_tut_question_win", None)
    app._tut_question_win = None
    try:
        if w is not None and w.winfo_exists():
            w.destroy()
    except Exception:
        pass


def _flower_pil(colour, size):
    try:
        import missions as _ms
        return _ms._trait_pil("flower_color", colour, size)
    except Exception:
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        fill = (146, 92, 170, 255) if colour == "purple" else (250, 250, 245, 255)
        ImageDraw.Draw(im).ellipse((2, 2, size - 2, size - 2), fill=fill,
                                   outline=(90, 70, 50, 255))
        return im


def open_question(app, key):
    """Abbot Cyril asks (a window beside the dialogue): what the
    grandchildren will look like ("f2_predict"), or how many purple there
    are for each white one ("f2_predict" / "f2_ratio"). The family tree so
    far is drawn in the window; one click on an answer gives it."""
    if _tut_answer(app, key) is not None:
        return None
    old = getattr(app, "_tut_question_win", None)
    try:
        if old is not None and old.winfo_exists():
            if getattr(old, "_key", None) == key:
                old.lift()
                return old
            old.destroy()
    except Exception:
        pass
    from PIL import ImageTk
    BG = getattr(app, "INSPECTOR_BG", "#f5f0e6")
    CARD, EDGE, INK, MUTED = "#fbf7ee", "#d9cdb4", "#3b2a1a", "#7a6a55"
    HOVER, SEL = "#efe4cc", "#e3d3ad"
    win = tk.Toplevel(app.root)
    win.withdraw()
    win._key = key
    app._tut_question_win = win
    win.title("Abbot Cyril asks")
    win.configure(bg=BG)
    win.resizable(False, False)
    try:
        win.transient(app.root)
        win.attributes("-topmost", True)
    except Exception:
        pass
    win.protocol("WM_DELETE_WINDOW", lambda: None)      # an answer is needed
    imgs = []
    win._imgs = imgs

    def icon(colour, size=30):
        ph = ImageTk.PhotoImage(_flower_pil(colour, size), master=win)
        imgs.append(ph)
        return ph

    outer = tk.Frame(win, bg=BG, padx=20, pady=14)
    outer.pack(fill="both", expand=True)
    top = tk.Frame(outer, bg=BG)
    top.pack(fill="x")
    try:
        from PIL import Image
        pth = os.path.join(ICONS_DIR, "franz_1.png")
        if os.path.isfile(pth):
            pil = Image.open(pth).convert("RGBA")
            pil.thumbnail((84, 120), Image.LANCZOS)
            ph = ImageTk.PhotoImage(pil, master=win)
            imgs.append(ph)
            tk.Label(top, image=ph, bg=BG).pack(side="left", padx=(0, 14), anchor="n")
    except Exception:
        pass
    head = tk.Frame(top, bg=BG)
    head.pack(side="left", fill="x", expand=True)
    tk.Label(head, text="Abbot Cyril asks", font=("Segoe UI", 11, "italic"), bg=BG,
             fg=MUTED).pack(anchor="w")
    if key == "f2_predict":
        question = "How will the grandchildren flower?"
        sub = ("Here is the family so far. The grandchildren are sown, but none of them "
               "has flowered yet.")
    else:
        question = "How many purple flowers are there for each white one?"
        sub = ("Here is the family. Count the grandchildren in flower, all of them, "
               "as the TIE shows them.")
    tk.Label(head, text=question, font=("Segoe UI", 16, "bold"), bg=BG, fg=INK,
             wraplength=470, justify="left").pack(anchor="w")
    tk.Label(head, text=sub, font=("Segoe UI", 12), bg=BG, fg=MUTED, wraplength=470,
             justify="left").pack(anchor="w", pady=(2, 0))

    # --- the family tree so far
    tree = tk.Frame(outer, bg=CARD, highlightbackground=EDGE, highlightthickness=1,
                    padx=14, pady=10)
    tree.pack(fill="x", pady=(12, 10))
    mc = _tut_mother_colour(app) or "white"
    fc = _other_colour(mc)

    def row(caption, build):
        r = tk.Frame(tree, bg=CARD)
        r.pack(fill="x", pady=2)
        tk.Label(r, text=caption, font=("Segoe UI", 11, "bold"), bg=CARD, fg=MUTED,
                 width=24, anchor="w").pack(side="left", anchor="n", pady=6)
        box = tk.Frame(r, bg=CARD)
        box.pack(side="left")
        build(box)

    def arrow():
        a = tk.Frame(tree, bg=CARD)
        a.pack(fill="x")
        tk.Label(a, text="", font=("Segoe UI", 11, "bold"), width=24, bg=CARD).pack(side="left")
        tk.Label(a, text="↓", font=("Segoe UI", 13, "bold"), bg=CARD, fg=MUTED).pack(side="left", padx=8)

    def parents(box):
        tk.Label(box, image=icon(mc, 54), bg=CARD).pack(side="left")
        tk.Label(box, text="♀", font=("Segoe UI", 14, "bold"), bg=CARD, fg=INK).pack(side="left")
        tk.Label(box, text="×", font=("Segoe UI", 16, "bold"), bg=CARD,
                 fg=INK).pack(side="left", padx=12)
        tk.Label(box, image=icon(fc, 54), bg=CARD).pack(side="left")
        tk.Label(box, text="♂", font=("Segoe UI", 14, "bold"), bg=CARD, fg=INK).pack(side="left")

    def icons_grid(box, cols_list, per_row=12):
        for i, c in enumerate(cols_list):
            if c == "?":
                w_ = tk.Label(box, text="?", font=("Segoe UI", 20, "bold"), bg="#e8e0cc",
                              fg=MUTED, width=2)
            else:
                w_ = tk.Label(box, image=icon(c, 44), bg=CARD)
            w_.grid(row=i // per_row, column=i % per_row, padx=2, pady=2)

    f1 = [_flower_colour(p) for p in _f1_plants(app) if _flower_colour(p)] or ["purple"] * 3
    row("The parents you crossed", parents)
    arrow()
    row("Their children (F1)", lambda b: icons_grid(b, f1[:12]))
    arrow()
    if key == "f2_predict":
        n = max(4, min(12, len(_f2_plants(app))))
        row("Their grandchildren (F2)", lambda b: icons_grid(b, ["?"] * n))
    else:
        p, w = _ratio_counts(app)
        app._tut_ratio_counts = (p, w)
        tot = p + w
        k = min(1.0, 24.0 / tot) if tot else 1.0
        npur, nwhi = int(round(p * k)), (max(1, int(round(w * k))) if w else 0)

        def f2(b):
            icons_grid(b, ["purple"] * npur + ["white"] * nwhi)
            tk.Label(b, text=(f"{p} purple · {w} white" if k >= 1.0 else
                              f"{p} purple · {w} white (shown in proportion)"),
                     font=("Segoe UI", 11, "italic"), bg=CARD, fg=MUTED).grid(
                row=99, column=0, columnspan=12, sticky="w", pady=(4, 0))
        row("Their grandchildren (F2)", f2)

    # --- the answers
    if key == "f2_predict":
        answers = [("all_purple", ["purple"] * 4, "All purple, like their parents"),
                   ("some_white", ["purple"] * 3 + ["white"], "Mostly purple, a few white"),
                   ("half", ["purple"] * 2 + ["white"] * 2, "Half purple, half white"),
                   ("all_white", ["white"] * 4, "All white")]
    else:
        answers = [("1", ["purple", ":", "white"], "about 1 to 1"),
                   ("2", ["purple"] * 2 + [":", "white"], "about 2 to 1"),
                   ("3", ["purple"] * 3 + [":", "white"], "about 3 to 1"),
                   ("4", ["purple"] * 4 + ["…", ":", "white"], "4 or more to 1")]
    opts = tk.Frame(outer, bg=BG)
    opts.pack(fill="x")
    cells = []

    def choose(val):
        try:
            _click_sound()
        except Exception:
            pass
        d = dict(getattr(app, "_tut_answers", None) or {})
        d[key] = val
        app._tut_answers = d
        _close_question(app)

    for i, (val, pics, words) in enumerate(answers):
        cell = tk.Frame(opts, bg=CARD, cursor="hand2", padx=8, pady=6,
                        highlightthickness=2, highlightbackground=EDGE)
        cell.grid(row=0, column=i, padx=4, sticky="nsew")
        opts.grid_columnconfigure(i, weight=1)
        strip = tk.Frame(cell, bg=CARD)
        strip.pack()
        parts = [cell, strip]
        for c in pics:
            if c in (":", "…"):
                w_ = tk.Label(strip, text=c, font=("Segoe UI", 16, "bold"), bg=CARD, fg=INK)
            else:
                w_ = tk.Label(strip, image=icon(c, 34), bg=CARD)
            w_.pack(side="left", padx=1)
            parts.append(w_)
        lbl = tk.Label(cell, text=words, font=("Segoe UI", 11), bg=CARD, fg=INK,
                       wraplength=150, justify="center")
        lbl.pack(pady=(4, 0))
        parts.append(lbl)
        cells.append((cell, parts))

        def paint(on, parts=parts):
            for w_ in parts:
                try:
                    w_.configure(bg=(HOVER if on else CARD))
                except Exception:
                    pass
            try:
                parts[0].configure(highlightbackground=(SEL if on else EDGE))
            except Exception:
                pass

        def hover(e, on, cell=cell, paint=paint):
            if not on:
                try:
                    w_ = cell.winfo_containing(e.x_root, e.y_root)
                    while w_ is not None:
                        if w_ is cell:
                            return
                        w_ = w_.master
                except Exception:
                    pass
            paint(on)
        for w_ in parts:
            _click(app, w_, lambda v=val: choose(v))
            w_.bind("<Enter>", lambda e, h=hover: h(e, True), add="+")
            w_.bind("<Leave>", lambda e, h=hover: h(e, False), add="+")
            try:
                w_.configure(cursor="hand2")
            except Exception:
                pass
    tk.Label(outer, text="Click your answer.", font=("Segoe UI", 11, "italic"), bg=BG,
             fg=MUTED).pack(anchor="e", pady=(8, 0))
    try:
        win.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - win.winfo_reqwidth()) // 2
        y = app.root.winfo_rooty() + max(40, (app.root.winfo_height() - win.winfo_reqheight()) // 3)
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
    except Exception:
        pass
    win.deiconify()
    try:
        win.lift()
    except Exception:
        pass
    return win


_WAIT_CONDITIONS = {
    "plants_watered": _plants_watered,
    "targets_watered": _targets_watered,
    # Set by GardenApp._on_inspect_unified when a plant was inspected.
    "plant_inspected": lambda app, baseline: bool(getattr(app, "_tutorial_inspected", False)),
    # A living plant is selected (not an empty plot).
    "plant_selected": lambda app, baseline: _living_plant_selected(app),
    # A Fast Forward has run to its end since the line appeared.
    "ff_used": lambda app, baseline: int(getattr(app, "_ff_run_count", 0) or 0) > int(baseline or 0),
    # At least one pod harvested since the line appeared (the seed bag
    # grew; baseline = its size then).
    "pod_harvested": lambda app, baseline: len(getattr(app, "harvest_inventory", []) or []) > int(baseline or 0),
    # Same, but stays true once it happened (sowing a seed afterwards
    # doesn't undo it) — for lines that wait a while after the harvest.
    "pod_harvested_once": lambda app, baseline: _sticky_harvest(app, baseline),
    # Pods harvested from at least two different plants since the line appeared.
    "two_plants_harvested": lambda app, baseline: len(_plants_harvested_since(app, baseline)) >= 2,
    # Part 4: ripe pods of two different plants (fewer if not that many
    # plants still had ripe pods when the line began).
    # Part 4: a pod picked with the S key / all pods of a plant with
    # Shift + S since the line appeared (or no ripe pod left anywhere).
    "s_key_harvest": lambda app, baseline: _key_harvested(app, baseline, "s"),
    # A plant note was written and saved since the line appeared.
    "note_saved": lambda app, baseline: int(getattr(app, "_notes_saved_count", 0) or 0) > int(baseline or 0),
    # Fast Forward's "Skip to next sunny day" has run since the line appeared.
    "sunny_skip_used": lambda app, baseline: int(getattr(app, "_sunny_skip_count", 0) or 0) > int(baseline or 0),
    "shift_s_harvest": lambda app, baseline: _key_harvested(app, baseline, "S"),
    "frost_harvest": lambda app, baseline: (
        len(_plants_harvested_since(app, baseline))
        >= int(getattr(app, "_tut_frost_need", 2) or 0)),
    # A pod harvested from a different plant than the last one harvested
    # before the line appeared.
    "other_plant_harvested": lambda app, baseline: _other_plant_harvested(app, baseline),
    # Pods from OTHER_PLANTS_NEEDED further plants (see _other_plants_status).
    "other_plants_harvested": lambda app, baseline: _other_plants_status(app, baseline)[0]
                                                      >= _other_plants_status(app, baseline)[1],
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
    # The inspection window is open with its Harvest section showing.
    "harvest_section_open": lambda app, baseline: (
        _live_widget(getattr(app, "_inspector_win", None)) is not None
        and bool(app._inspector_sections().get("harvest"))),
    # Part 5 (crossing)
    # Part 4 spring: garden 2 opened by the player
    "plot2_shown": lambda app, baseline: int(getattr(app, "active_plot_index", 0) or 0) == 1,
    # Part 4 spring: seeds of both flower colours to sow
    "both_colours_available": lambda app, baseline: not _missing_seed_colours(app),
    "budding_plant_inspected": lambda app, baseline: _inspector_shows(
        app, lambda st, f: st == "bud" and not _hand_emasc(f)),
    # Part 4: the mother is white-flowering (any budding plant if none is)
    "white_budding_inspected": lambda app, baseline: (
        _inspector_shows(app, lambda st, f: st == "bud" and not _hand_emasc(f))
        and _selected_living_plant(app) in _white_budding_plants(app)),
    # Part 4 spring: plants of both flower colours are growing
    "both_colours_sown": lambda app, baseline: _both_colours_sown(app),
    "fresh_both_sown": lambda app, baseline: _fresh_both_sown(app),
    "crossing_section_open": lambda app, baseline: (
        _live_widget(getattr(app, "_inspector_win", None)) is not None
        and bool(app._inspector_sections().get("crossing"))),
    "bud_selected": lambda app, baseline: any(
        st == "bud" and not _hand_emasc(f) for _k, st, f in _selected_flowers(app)),
    "flower_emasculated": lambda app, baseline: any(
        _hand_emasc(f) for _p, _k, _st, f in _all_flowers(app)),
    "father_inspected": lambda app, baseline: (
        (_live_widget(getattr(app, "_inspector_win", None)) is not None
         and _selected_living_plant(app) is not None
         and _selected_living_plant(app) is _tut_father_plant(app)[0])
        if _tut_father_plant(app)[0] is not None else
        (_inspector_shows(app, lambda st, f: st == "open" and not _hand_emasc(f))
         and not _inspector_shows(app, lambda st, f: _hand_emasc(f)))),
    "open_flower_selected": lambda app, baseline: _ripe_flower_selected(app),
    "pollen_collected": lambda app, baseline: bool(app._has_viable_pollen_today()),
    "brush_window_open": lambda app, baseline: (
        _dialog_open(app, "BrushDialog") or bool(app._has_viable_pollen_today())),
    "brush_window_closed": lambda app, baseline: not _dialog_open(app, "BrushDialog"),
    "pollinate_window_closed": lambda app, baseline: not _dialog_open(app, "PollinationDialog"),
    "pollinate_window_open": lambda app, baseline: (
        _dialog_open(app, "PollinationDialog") or any(
            _hand_emasc(f) and f.get("pollen") for _p, _k, _st, f in _all_flowers(app))),
    "mother_inspected": lambda app, baseline: _inspector_shows(
        app, lambda st, f: st == "open" and _hand_emasc(f)),
    "emasc_flower_selected": lambda app, baseline: any(
        st == "open" and _hand_emasc(f) for _k, st, f in _selected_flowers(app)),
    "flower_pollinated": lambda app, baseline: any(
        _hand_emasc(f) and f.get("pollen") for _p, _k, _st, f in _all_flowers(app)),
    "crossed_pod_harvested": lambda app, baseline: _crossed_pod_harvested(app),
    # Part 5
    "f1_sown": lambda app, baseline: bool(_f1_plants(app)),
    # (cleared when the line begins, so it must be ticked in the seed window)
    # the »Seeds from crosses« row of the Choose Seeds window: F1 / F2
    "seed_filter_crossed": lambda app, baseline: getattr(app, "_seed_filter_gen", None) == "F1",
    "seed_filter_ofcross": lambda app, baseline: getattr(app, "_seed_filter_gen", None) == "F2",
    "several_removed": lambda app, baseline: any(
        int(n or 0) >= 2 for n in list(getattr(app, "_remove_log", []) or [])[int(baseline or 0):]),
    # any living plant is shown in the inspection window
    "any_inspected": lambda app, baseline: (
        _live_widget(getattr(app, "_inspector_win", None)) is not None
        and _selected_living_plant(app) is not None),
    "f1_inspected": lambda app, baseline: (
        _live_widget(getattr(app, "_inspector_win", None)) is not None
        and _is_cross_child(_selected_living_plant(app))),
    "genotype_viewer_open": lambda app, baseline: _live_widget(
        getattr(app, "_genotype_viewer_win", None)) is not None,
    "genotype_viewer_closed": lambda app, baseline: _live_widget(
        getattr(app, "_genotype_viewer_win", None)) is None,
    "f1_harvested": lambda app, baseline: _f1_harvested(app),
    "tie_open": lambda app, baseline: _tie(app) is not None,
    # the help window (H) has been opened
    "help_opened": lambda app, baseline: _live_widget(getattr(app, "_help_win", None)) is not None,
    "tie_closed": lambda app, baseline: _tie(app) is None,
    "tie_open_f2": lambda app, baseline: _tie(app) is not None and _is_f2(app, _tie_current(app)),
    "tie_open_f2_white": lambda app, baseline: _tie(app) is not None and _is_white_f2(app, _tie_current(app)),
    # Part 5: more F2 plants sown after none of them flowered white
    "f2_more_sown": lambda app, baseline: (not _f2_white_impossible(app)) or _f2_seeds_left(app) == 0,
    "tie_seed_color": lambda app, baseline: _tie_shows(app, lambda t: t.trait_mode.get() == "Seed color"),
    "tie_flower_color": lambda app, baseline: _tie_shows(app, lambda t: t.trait_mode.get() == "Flowers"),
    "tie_tab_pods": lambda app, baseline: _tie_shows(app, lambda t: _tie_tab(t) == 0),
    "tie_tab_ratio": lambda app, baseline: _tie_shows(app, lambda t: _tie_tab(t) == 2),
    "tie_tab_punnett": lambda app, baseline: _tie_shows(app, lambda t: _tie_tab(t) == 1),
    "genotype_revealed": lambda app, baseline: bool(getattr(app, "_genotype_revealed", False)),
    "tie_alleles_hovered": lambda app, baseline: bool(getattr(app, "_tie_alleles_hovered", False)),
    "tie_show_alleles": lambda app, baseline: _tie_shows(app, lambda t: bool(t._show_alleles_var.get())),
    "f2_sown": lambda app, baseline: (len(_f2_plants(app)) >= 8
                                      or (_f2_plants(app) and _f2_seeds_left(app) == 0)),
    "inspector_window_closed": lambda app, baseline: (
        _live_widget(getattr(app, "_inspector_win", None)) is None),
    "cross_pod_shown": lambda app, baseline: _cross_pod_shown(app),
    "weevil_caught": lambda app, baseline: _weevil_caught(app) or _tut_weevil_alive(app) is None,
    "tie_other_plant": lambda app, baseline: _tie_shows(
        app, lambda t: t.preview_pid is not None and str(t.preview_pid) != str(t.current_pid)),
    "tie_back": lambda app, baseline: _tie_shows(
        app, lambda t: t.preview_pid is None or str(t.preview_pid) == str(t.current_pid)),
    "question_answered": lambda app, baseline: _tut_answer(
        app, getattr(app, "_tut_question_key", None)) is not None,
    "no_f2_prediction": lambda app, baseline: _tut_answer(app, "f2_predict") is None,
    "traits_section_open": lambda app, baseline: (
        _live_widget(getattr(app, "_inspector_win", None)) is not None
        and bool(app._inspector_sections().get("traits"))),
}


def _marked_plant_selected(app, stage):
    """The selected plot holds one of the plants marked for this line
    (see "highlight_plants")."""
    try:
        idx = getattr(app, "selected_index", None)
        if idx is None:
            return False
        tile = app.tiles[idx]
        return tile in _plant_highlight_tiles(app, stage)
    except Exception:
        return False


def _plant_highlight_tiles(app, stage):
    """The plots on screen whose living plant is at exactly `stage` (or, if
    none is, at that stage or beyond). Part 5 also uses "father" (plants
    that can give pollen, never the emasculated mother) and "mother" (the
    plant with the emasculated, open flower)."""
    if stage == "father" and _tut_father_plant(app)[0] is not None:
        fp = _tut_father_plant(app)[0]
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) is fp]
    if stage == "cross_ripe":
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) is not None and _has_ripe_cross_pod(t.plant)]
    if stage == "weevil":
        c = _tut_weevil_alive(app)
        return [c.tile] if c is not None and c.tile in list(getattr(app, "tiles", []) or []) else []
    if stage == "white_buds":
        mothers = _white_budding_plants(app)
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) in mothers]
    if stage == "old":
        # plants (alive or dead) on the garden shown, not children of the cross
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) is not None and not _is_cross_child(t.plant)
                and getattr(t, "plot_idx", 0) == getattr(app, "active_plot_index", 0)]
    if stage == "f1_ripe":
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) is not None
                and getattr(t.plant, "alive", True) and _is_cross_child(t.plant)
                and int(t.plant.ripe_pods() or 0) > 0]
    if stage == "f2_white":
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) is not None
                and getattr(t.plant, "alive", True) and _is_white_f2(app, t.plant)]
    if stage in ("f1", "f2"):
        want = _is_cross_child if stage == "f1" else (lambda p: _is_f2(app, p))
        return [t for t in list(getattr(app, "tiles", []) or [])
                if getattr(t, "plant", None) is not None
                and getattr(t.plant, "alive", True) and want(t.plant)]
    if stage in ("father", "mother"):
        out = []
        for t in list(getattr(app, "tiles", []) or []):
            p = getattr(t, "plant", None)
            if p is None or not getattr(p, "alive", True):
                continue
            info = _flower_info(app, p)
            is_mother = any(_hand_emasc(f) for _k, _st, f in info)
            if stage == "mother":
                if any(st == "open" and _hand_emasc(f) for _k, st, f in info):
                    out.append(t)
            elif not is_mother and any(st == "open" and _has_anthers(f) for _k, st, f in info):
                out.append(t)
        return out
    exact, beyond = [], []
    for t in list(getattr(app, "tiles", []) or []):
        p = getattr(t, "plant", None)
        if p is None or not getattr(p, "alive", True):
            continue
        try:
            st = int(getattr(p, "stage", 0))
        except Exception:
            continue
        if st == stage:
            exact.append(t)
        elif st > stage:
            beyond.append(t)
    return exact or beyond


_GLOW_CACHE = {}


def _glow_photo(photo):
    """A soft golden halo shaped like the plant icon `photo` (same centre,
    a few pixels larger), cached per icon."""
    key = str(photo)
    if key in _GLOW_CACHE:
        return _GLOW_CACHE[key]
    glow = None
    try:
        from PIL import Image, ImageFilter, ImageTk
        src = ImageTk.getimage(photo).convert("RGBA")
        pad = 8
        a = Image.new("L", (src.width + 2 * pad, src.height + 2 * pad), 0)
        a.paste(src.getchannel("A").point(lambda v: 255 if v > 40 else 0), (pad, pad))
        a = a.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3.2))
        a = a.point(lambda v: min(255, int(v * 1.3)))
        halo = Image.new("RGBA", a.size, (255, 205, 70, 0))
        halo.putalpha(a)
        glow = ImageTk.PhotoImage(halo)
    except Exception:
        glow = None
    _GLOW_CACHE[key] = glow
    return glow


_RING_GLOW = {}
GLOW_FRAMES = 12           # one pulse = GLOW_FRAMES x GLOW_STEP_MS
GLOW_STEP_MS = 110


def _ring_glow_frames(rx, ry):
    """Golden glow along the ring, as a list of frames from faint to
    bright (one pulse), cached per ring size."""
    key = (int(rx), int(ry))
    if key in _RING_GLOW:
        return _RING_GLOW[key]
    frames = []
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageTk
        pad = 15
        w, h = 2 * key[0] + 2 * pad, 2 * key[1] + 2 * pad
        a = Image.new("L", (w, h), 0)
        ImageDraw.Draw(a).ellipse((pad, pad, w - pad, h - pad), outline=255, width=8)
        a = a.filter(ImageFilter.GaussianBlur(4.5))
        a = a.point(lambda v: min(255, int(v * 1.6)))
        for i in range(GLOW_FRAMES):
            k = 0.25 + 0.75 * (0.5 - 0.5 * math.cos(2 * math.pi * i / GLOW_FRAMES))
            img = Image.new("RGBA", (w, h), (255, 214, 80, 0))
            img.putalpha(a.point(lambda v, k=k: int(v * k)))
            frames.append(ImageTk.PhotoImage(img))
    except Exception:
        frames = []
    _RING_GLOW[key] = frames
    return frames


def _draw_stem_ring(t, bb):
    """A flat golden ring on the ground around the plant's stem, kept
    inside the tile so it is never cut off."""
    x1, y1, x2, y2 = bb
    cx = (x1 + x2) / 2.0
    base = y2 - 7                                   # where the stem meets the soil
    rx, ry = 17, 6
    try:
        cw = int(t.winfo_width()) or int(t.cget("width"))
        ch = int(t.winfo_height()) or int(t.cget("height"))
    except Exception:
        cw = ch = 0
    if cw > 0:
        rx = min(rx, max(8, cw / 2.0 - 3))
        cx = max(rx + 2, min(cw - rx - 2, cx))
    if ch > 0:
        base = max(ry + 2, min(ch - ry - 2, base))
    box = (cx - rx, base - ry, cx + rx, base + ry)
    frames = _ring_glow_frames(rx, ry)
    t._tut_glow_frames = frames
    if frames:
        t.create_image(cx, base, image=frames[0], anchor="center",
                       tags=("tutplants", "tutback", "tutglow"))
    for part, start in (("tutback", 0), ("tutfront", 180)):
        # dark rim under a bright gold line, so it shows on soil and grass
        t.create_arc(*box, start=start, extent=180, style="arc", outline="#7a5200",
                     width=4, tags=("tutplants", part))
        t.create_arc(*box, start=start, extent=180, style="arc", outline="#ffd24a",
                     width=2, tags=("tutplants", part))


# lines that wait for seeds to be sown: no plant highlight may limit the
# selection then (see _show_line)
_SOWING_CONDITIONS = ("f1_sown", "f2_sown", "both_colours_sown")

# highlight sets that change while the line shows (recomputed each second)
_DYNAMIC_HIGHLIGHTS = ("f1_ripe", "old")


def _show_plant_highlight(dlg, stage):
    """A golden ring around the stem of the plants Cyril is talking about — e.g.
    the ones with buds — with a pulsing glow so they are easy to spot.
    It stays until Cyril has finished this part (and follows the icon as
    the plant grows)."""
    _clear_plant_highlight(dlg)
    tiles = _plant_highlight_tiles(dlg.app, stage)
    if not tiles:
        return
    state = {"job": None, "shown": {}, "pulse": None, "frame": 0}
    dlg._plant_hl = (tiles, state)
    # Only these plants can be selected (and so inspected) meanwhile.
    app = dlg.app
    app._tutorial_select_only = set(tiles)
    try:
        cur = set(getattr(app, "multi_selected_indices", set()) or set())
        if getattr(app, "selected_index", None) is not None:
            cur.add(app.selected_index)
        keep = app._tut_filter(cur)
        if keep != cur:
            app._apply_drag_selection(keep)
    except Exception:
        pass

    def _draw():
        state["job"] = None
        if getattr(dlg.app, "_tutorial_dialogue", None) is not dlg:
            _clear_plant_highlight(dlg)            # Cyril is done
            return
        if stage in _DYNAMIC_HIGHLIGHTS:
            # e.g. only plants that still have ripe pods: a plant drops out
            # of the ring (and the selection limit) once it is done
            try:
                now = _plant_highlight_tiles(dlg.app, stage)
                for t in [t for t in tiles if t not in now]:
                    t.delete("tutplants")
                    state["shown"].pop(t, None)
                tiles[:] = list(now)
                dlg.app._tutorial_select_only = set(now)
            except Exception:
                pass
        for t in tiles:
            try:
                photo = getattr(getattr(t, "plant", None), "img_obj", None)
                if photo is None:
                    t.delete("tutplants")
                    continue
                bb = t.bbox(t.img_item)
                if not bb:
                    continue
                if state["shown"].get(t) != (str(photo), bb) or not t.find_withtag("tutplants"):
                    t.delete("tutplants")
                    _draw_stem_ring(t, bb)
                    state["shown"][t] = (str(photo), bb)
                t.tag_lower("tutback", t.img_item)      # far half behind the plant
                t.tag_raise("tutfront", t.img_item)     # near half in front of the stem
            except Exception:
                pass
        try:
            state["job"] = dlg.app.root.after(1000, _draw)   # keep it through redraws
        except Exception:
            state["job"] = None

    def _pulse():
        state["pulse"] = None
        if getattr(dlg, "_plant_hl", None) is None or dlg._plant_hl[1] is not state:
            return
        state["frame"] = (state["frame"] + 1) % GLOW_FRAMES
        for t in tiles:
            try:
                frames = getattr(t, "_tut_glow_frames", None)
                if frames:
                    for it in t.find_withtag("tutglow"):
                        t.itemconfigure(it, image=frames[state["frame"] % len(frames)])
            except Exception:
                pass
        try:
            state["pulse"] = dlg.app.root.after(GLOW_STEP_MS, _pulse)
        except Exception:
            state["pulse"] = None

    _draw()
    _pulse()


def _clear_plant_highlight(dlg):
    hl = getattr(dlg, "_plant_hl", None)
    if not hl:
        return
    tiles, state = hl
    try:
        dlg.app._tutorial_select_only = None
    except Exception:
        pass
    for _k in ("job", "pulse"):
        if state.get(_k) is not None:
            try:
                dlg.app.root.after_cancel(state[_k])
            except Exception:
                pass
            state[_k] = None
    for t in tiles:
        try:
            t.delete("tutplants")
        except Exception:
            pass
    dlg._plant_hl = None


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


def _arrow_pil(pts, w, h, outline, fill):
    """The tutorial arrow as a picture: the polygon filled, with a black
    outline of the given width and round corners — drawn 4x larger and
    scaled down, so its edges are smooth; transparent around."""
    from PIL import Image, ImageDraw
    ss = 4
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    xy = [(pts[i] * ss, pts[i + 1] * ss) for i in range(0, len(pts), 2)]
    d.polygon(xy, fill=fill)
    lw = int(outline * ss)
    for a, b in zip(xy, xy[1:] + xy[:1]):
        d.line([a, b], fill="black", width=lw)
    r = lw / 2.0
    for (x, y) in xy:
        d.ellipse([x - r, y - r, x + r, y + r], fill="black")
    return im.resize((w, h), Image.LANCZOS)


def _arrow_strips(pts, w, h, outline):
    """The arrow cut into solid rectangles (x, y, width, height, kind):
    kind "o" for the black outline, "f" for the coloured inside. Each
    pixel row is split into runs; equal runs in the rows below are
    merged into one taller rectangle (the shaft is just three)."""
    im = _arrow_pil(pts, w, h, outline, "#ff0000").convert("RGBA")
    px = im.load()
    rows = []
    for y in range(h):
        runs, x = [], 0
        while x < w:
            r, g, b, a = px[x, y]
            kind = None if a < 110 else ("f" if r > 110 else "o")
            x0 = x
            while x + 1 < w:
                r2, g2, b2, a2 = px[x + 1, y]
                k2 = None if a2 < 110 else ("f" if r2 > 110 else "o")
                if k2 != kind:
                    break
                x += 1
            if kind:
                runs.append((x0, x - x0 + 1, kind))
            x += 1
        rows.append(runs)
    out, open_ = [], {}
    for y, runs in enumerate(rows):
        nxt = {}
        for x0, wd, kind in runs:
            key = (x0, wd, kind)
            if key in open_:
                nxt[key] = open_[key]
                nxt[key][3] += 1
            else:
                nxt[key] = [x0, y, wd, 1, kind]
        for key, rect in open_.items():
            if key not in nxt:
                out.append(tuple(rect))
        open_ = nxt
    out.extend(tuple(r) for r in open_.values())
    return out


class _SnapshotArrow:
    """The tutorial arrow on a Mac (Tk 9 can't make any window see-through
    there — tested: every variant comes out black or white). One Canvas
    laid with place() into the window the arrow points into; behind the
    arrow it draws a copy of what lies underneath — the colours of the
    panels and buttons, and the very pictures of the garden plots — so
    it looks see-through, as one single widget (quick to show and to
    take away, unlike a hundred little strips). The copy is renewed about
    once a second, so a plant growing underneath stays right.
    Answers the few window calls the arrow makes, like _PlacedArrow."""

    def __init__(self, host, pts, w, h, outline, color):
        self.host = host
        self._w, self._h = w, h
        self._x = self._y = None
        self._shown = False
        self._job = None
        self.cv = tk.Canvas(host, width=w, height=h, highlightthickness=0, bd=0,
                            cursor="arrow", bg=_widget_bg(host) or "#f0f0f0")
        self.cv._goi_arrow = True
        try:
            import __main__ as _m
            self.cv.bind("<Enter>", lambda e: _m._ctrace("mouse ENTERS the arrow"), add="+")
            self.cv.bind("<Leave>", lambda e: _m._ctrace("mouse LEAVES the arrow"), add="+")
        except Exception:
            pass
        self._poly = self.cv.create_polygon(*pts, fill=color, outline="black",
                                            width=outline, joinstyle="round",
                                            tags="arrow")

    # -- the copy of what lies underneath --------------------------------
    def _snapshot(self):
        cv = self.cv
        try:
            cv.delete("under")
            ax0, ay0 = self._x, self._y
            w, h = self._w, self._h
            ax1, ay1 = ax0 + w, ay0 + h

            def visible_part(c):
                x0, y0 = c.winfo_rootx(), c.winfo_rooty()
                x1, y1 = x0 + c.winfo_width(), y0 + c.winfo_height()
                if x1 <= ax0 or y1 <= ay0 or x0 >= ax1 or y0 >= ay1:
                    return None
                return x0, y0, x1, y1

            def walk(widget):
                for c in widget.winfo_children():
                    try:
                        if (c is cv or getattr(c, "_goi_arrow", False)
                                or isinstance(c, (tk.Toplevel, tk.Menu))
                                or not c.winfo_ismapped()):
                            continue
                        box = visible_part(c)
                        if box is None:
                            continue
                        x0, y0, x1, y1 = box
                        ox, oy = x0 - ax0, y0 - ay0
                        bg = _widget_bg(c)
                        if bg:
                            cv.create_rectangle(ox, oy, x1 - ax0, y1 - ay0, fill=bg,
                                                outline="", tags="under")
                        if isinstance(c, tk.Canvas):
                            _copy_canvas_items(c, cv, ox - c.canvasx(0), oy - c.canvasy(0))
                        else:
                            _copy_label_face(c, cv, ox, oy)
                        walk(c)
                    except Exception:
                        continue
            walk(self.host)
            cv.tag_raise("arrow")
        except Exception:
            pass

    def _refresh(self):
        self._job = None
        if not self._shown:
            return
        self._snapshot()
        try:
            self._job = self.cv.after(1000, self._refresh)
        except Exception:
            self._job = None

    # -- the window calls the arrow makes --------------------------------
    def geometry(self, spec=None):
        try:
            parts = str(spec).replace("-", "+-").split("+")
            nums = [int(v) for v in parts if v != ""]
            self._x, self._y = nums[-2], nums[-1]
        except Exception:
            return
        if self._shown:
            self._place()

    def _place(self):
        try:
            hx, hy = self.host.winfo_rootx(), self.host.winfo_rooty()
            self.cv.place(x=self._x - hx, y=self._y - hy, width=self._w, height=self._h)
            # (Canvas.lift raises canvas items: the widget itself is raised so)
            self.cv.tk.call("raise", self.cv._w)
        except Exception:
            return
        self._snapshot()
        if self._job is None:
            try:
                self._job = self.cv.after(1000, self._refresh)
            except Exception:
                pass

    def deiconify(self):
        self._shown = True
        if self._x is not None:
            self._place()

    def withdraw(self):
        self._shown = False
        try:
            self.cv.place_forget()
        except Exception:
            pass

    def state(self):
        return "normal" if self._shown else "withdrawn"

    def set_fill(self, color):
        try:
            self.cv.itemconfigure(self._poly, fill=color)
        except Exception:
            pass

    def lift(self, *a):
        try:
            self.cv.tk.call("raise", self.cv._w)
        except Exception:
            pass

    def attributes(self, *a, **k):
        return 0

    def winfo_reqwidth(self):
        return self._w

    def winfo_reqheight(self):
        return self._h

    def winfo_exists(self):
        return 1

    def update_idletasks(self):
        try:
            self.host.update_idletasks()
        except Exception:
            pass

    def destroy(self):
        self._shown = False
        try:
            if self._job is not None:
                self.cv.after_cancel(self._job)
        except Exception:
            pass
        self._job = None
        try:
            self.cv.destroy()
        except Exception:
            pass


def _widget_bg(w):
    try:
        bg = w.cget("bg")
        return bg if bg and bg != "systemTransparent" else None
    except Exception:
        return None


def _copy_canvas_items(src, dst, dx, dy):
    """Copies what a canvas shows (pictures, shapes, text) onto `dst`,
    shifted by dx, dy — the same picture objects, so nothing is redrawn."""
    for it in src.find_all():
        try:
            kind = src.type(it)
            if kind == "window" or src.itemcget(it, "state") == "hidden":
                continue
            c = src.coords(it)
            if not c:
                continue
            c = [v + (dx if i % 2 == 0 else dy) for i, v in enumerate(c)]
            opts = {}
            for k, v in src.itemconfigure(it).items():
                val = v[-1]
                if k in ("tags", "state") or val is None:
                    continue
                opts[k] = val           # "" counts: no fill / no outline
            opts["tags"] = "under"
            make = getattr(dst, "create_" + kind)
            try:
                make(*c, **opts)
            except Exception:
                # an option Tk won't take back empty — keep the empty
                # colours (an empty fill/outline means "none", while a
                # missing one would be drawn black)
                keep = {k: v for k, v in opts.items()
                        if v != "" or k in ("fill", "outline", "activefill",
                                            "activeoutline", "disabledfill",
                                            "disabledoutline")}
                make(*c, **keep)
        except Exception:
            continue


def _copy_label_face(src, dst, ox, oy):
    """The picture and text of a label/button, laid out the way Tk lays
    them out (compound picture + text, anchor, padding)."""
    try:
        w, h = src.winfo_width(), src.winfo_height()
        try:
            img = src.cget("image")
        except Exception:
            img = ""
        try:
            txt = src.cget("text")
        except Exception:
            txt = ""
        try:
            compound = str(src.cget("compound") or "none")
        except Exception:
            compound = "none"
        if img and compound == "none":
            txt = ""                       # Tk shows only the picture then
        if not img and not txt:
            return

        def _num(opt):
            try:
                return int(float(str(src.cget(opt))))
            except Exception:
                return 0
        edge = _num("bd") + _num("highlightthickness")
        padx, pady = _num("padx"), _num("pady")
        iw = ih = tw = th = 0
        if img:
            iw = int(src.tk.call("image", "width", img))
            ih = int(src.tk.call("image", "height", img))
        if txt:
            f = tkfont.Font(font=src.cget("font"))
            lines = str(txt).split("\n")
            tw = max(f.measure(ln) for ln in lines)
            th = f.metrics("linespace") * len(lines)
        # (Tk puts padx between picture and text side by side, pady
        # between them one above the other)
        if img and txt and compound in ("left", "right"):
            cw, ch = iw + padx + tw, max(ih, th)
        elif img and txt and compound in ("top", "bottom"):
            cw, ch = max(iw, tw), ih + pady + th
        elif img:
            cw, ch = iw, ih
        else:
            cw, ch = tw, th
        x0, x1 = edge + padx, w - edge - padx
        y0, y1 = edge + pady, h - edge - pady
        try:
            anchor = str(src.cget("anchor") or "center")
        except Exception:
            anchor = "center"
        if "w" in anchor:
            cx = x0
        elif "e" in anchor:
            cx = x1 - cw
        else:
            cx = (x0 + x1 - cw) / 2.0
        if "n" in anchor:
            cy = y0
        elif "s" in anchor:
            cy = y1 - ch
        else:
            cy = (y0 + y1 - ch) / 2.0
        cx += ox
        cy += oy
        ix, iy, tx, ty = cx, cy + (ch - ih) / 2.0, cx, cy + (ch - th) / 2.0
        if img and txt:
            if compound == "left":
                tx = cx + iw + padx
            elif compound == "right":
                ix, tx = cx + tw + padx, cx
            elif compound == "top":
                ix, iy = cx + (cw - iw) / 2.0, cy
                tx, ty = cx + (cw - tw) / 2.0, cy + ih + pady
            elif compound == "bottom":
                tx, ty = cx + (cw - tw) / 2.0, cy
                ix, iy = cx + (cw - iw) / 2.0, cy + th + pady
        elif img:
            ix, iy = cx, cy
        if img:
            dst.create_image(ix, iy, image=img, anchor="nw", tags="under")
        if txt:
            try:
                justify = str(src.cget("justify") or "left")
            except Exception:
                justify = "left"
            dst.create_text(tx, ty, text=txt, font=src.cget("font"), fill=src.cget("fg"),
                            anchor="nw", justify=justify, tags="under")
    except Exception:
        pass


class _PlacedArrow:
    """The tutorial arrow on a Mac: solid strips (frames) laid with place()
    into the window the arrow points into — Tk 9 can't make a window of
    its own see-through there. Answers the few window calls the arrow
    makes (geometry "+x+y" in screen coordinates, withdraw/deiconify,
    state, lift, destroy …), so _TutorialArrow uses it like its window."""

    def __init__(self, host, strips, w, h, color):
        self.host = host
        self._w, self._h = w, h
        self._x = self._y = None
        self._shown = False
        self.frames = []
        for x, y, ww, hh, kind in strips:
            f = tk.Frame(host, bg=("black" if kind == "o" else color), bd=0,
                         highlightthickness=0, cursor="arrow")
            self.frames.append((f, kind, x, y, ww, hh))

    def geometry(self, spec=None):
        try:
            parts = str(spec).replace("-", "+-").split("+")
            nums = [int(v) for v in parts if v not in ("", )]
            self._x, self._y = nums[-2], nums[-1]
        except Exception:
            return
        if self._shown:
            self._place()

    def _place(self):
        try:
            hx, hy = self.host.winfo_rootx(), self.host.winfo_rooty()
        except Exception:
            return
        # (no lift(): the strips are made after everything else in the
        # window, so they lie on top anyway — and on a Mac every raise is
        # a costly re-stacking of the whole window)
        for f, kind, x, y, ww, hh in self.frames:
            try:
                f.place(x=self._x - hx + x, y=self._y - hy + y, width=ww, height=hh)
            except Exception:
                pass

    def deiconify(self):
        self._shown = True
        if self._x is not None:
            self._place()

    def withdraw(self):
        self._shown = False
        for f, *_ in self.frames:
            try:
                f.place_forget()
            except Exception:
                pass

    def state(self):
        return "normal" if self._shown else "withdrawn"

    def set_fill(self, color):
        for f, kind, *_ in self.frames:
            if kind == "f":
                try:
                    f.configure(bg=color)
                except Exception:
                    pass

    def lift(self, *a):
        for f, *_ in self.frames:
            try:
                f.lift()
            except Exception:
                pass

    def attributes(self, *a, **k):
        return 0

    def winfo_reqwidth(self):
        return self._w

    def winfo_reqheight(self):
        return self._h

    def winfo_exists(self):
        return 1

    def update_idletasks(self):
        try:
            self.host.update_idletasks()
        except Exception:
            pass

    def destroy(self):
        for f, *_ in self.frames:
            try:
                f.destroy()
            except Exception:
                pass
        self.frames = []


def _ring_rects(x, y, w, h, t):
    """The four bars of a box lying on the edge of x, y, w, h (screen)."""
    return [(x, y, w, t),                    # top
            (x, y + h - t, w, t),            # bottom
            (x, y, t, h),                    # left
            (x + w - t, y, t, h)]            # right


class _EdgeBar:
    """One bar of the box round a pointed-at control: a thin frame laid
    with place() into the control's own window. Answers the window calls
    the arrow makes of its bars; clicks on it go on to the control."""

    def __init__(self, host, target, color):
        self.host = host
        self.target = target
        self._geo = None
        self._shown = False
        self.f = tk.Frame(host, bg=color, bd=0, highlightthickness=0)
        self.f._goi_arrow = True
        for seq in ("<ButtonPress-1>", "<ButtonRelease-1>", "<ButtonPress-3>",
                    "<ButtonRelease-3>"):
            self.f.bind(seq, lambda e, q=seq: self._forward(q, e))

    def _forward(self, seq, e):
        try:
            tg = self.target
            tg.event_generate(seq, x=e.x_root - tg.winfo_rootx(),
                              y=e.y_root - tg.winfo_rooty(),
                              rootx=e.x_root, rooty=e.y_root)
        except Exception:
            pass
        return "break"

    def geometry(self, spec=None):
        try:
            size, _, pos = str(spec).partition("+")
            w, h = (int(v) for v in size.split("x"))
            x, y = (int(v) for v in pos.split("+"))
            self._geo = (w, h, x, y)
        except Exception:
            return
        if self._shown:
            self._place()

    def _place(self):
        if self._geo is None:
            return
        w, h, x, y = self._geo
        try:
            self.f.place(x=x - self.host.winfo_rootx(), y=y - self.host.winfo_rooty(),
                         width=w, height=h)
            self.f.tk.call("raise", self.f._w)
        except Exception:
            pass

    def deiconify(self):
        self._shown = True
        self._place()

    def withdraw(self):
        self._shown = False
        try:
            self.f.place_forget()
        except Exception:
            pass

    def state(self):
        return "normal" if self._shown else "withdrawn"

    def configure(self, **kw):
        try:
            self.f.configure(**{k: v for k, v in kw.items() if k in ("bg", "background")})
        except Exception:
            pass

    def attributes(self, *a, **k):
        return 0

    def lift(self, *a):
        try:
            self.f.tk.call("raise", self.f._w)
        except Exception:
            pass

    def destroy(self):
        try:
            self.f.destroy()
        except Exception:
            pass


def _setup_bar(bar, color):
    """One bar of the ring round the pointed-at control. On a Mac a
    borderless window gets a soft shadow (the bars looked like blurred,
    rounded pills): there the window is made transparent — which turns
    the shadow off — and a coloured frame fills it."""
    if sys.platform == "darwin":
        try:
            bar.wm_attributes("-transparent", True)
            bar.configure(bg="systemTransparent")
            f = tk.Frame(bar, bg=color, bd=0, highlightthickness=0)
            f.place(x=0, y=0, relwidth=1, relheight=1)
            bar._goi_fill = f
            return
        except Exception:
            pass
    bar.configure(bg=color)


def _paint_bar(bar, color):
    f = getattr(bar, "_goi_fill", None)
    if f is not None:
        f.configure(bg=color)
    else:
        bar.configure(bg=color)


def _own_by_target_window(w, target):
    """Makes the not-yet-shown helper window `w` (arrow, outline bar) belong
    to the window `target` sits in, when that is a separate (always-on-top)
    window like the inspection window: Windows keeps an owned window above
    its owner at all times. Must happen before `w` is shown."""
    try:
        top = target.winfo_toplevel()
        if top is not None and str(top) != ".":
            w.transient(top)
            if bool(top.attributes("-topmost")):
                w.attributes("-topmost", True)
    except Exception:
        pass


def _raise_above(w, other, topmost):
    """Shows `w` again above `other` after it was hidden. Deliberately no
    regular lifting (that made the arrows flicker between above and below
    the inspection window on Windows): the owner relation set when `w` was
    created (_own_by_target_window) keeps it on top by itself."""
    try:
        if topmost and not bool(w.attributes("-topmost")):
            w.attributes("-topmost", True)
        if sys.platform == "win32" or other is None:
            return               # Windows: the owner relation does it
        # macOS / Linux may not keep owned windows above their owner: lift
        # only when it really is below (no lifting while it's on top)
        if not other.winfo_viewable():
            return
        above = str(w.tk.call("wm", "stackorder", str(w), "isabove", str(other)))
        if above not in ("1", "true"):
            w.lift()
    except Exception:
        pass


class _GlowRing:
    """A pulsing outline lying ON a widget's own edge: four thin bars placed
    over it inside its own window (place(), so the widget and its window
    never change size). No separate windows: the earlier borderless
    Toplevel bars had to compete with the always-on-top inspection window
    for the front, and on Windows they flickered in and out with every
    pulse. Hides while the widget isn't visible."""
    T = 3

    def __init__(self, app, widget):
        self.app = app
        self.widget = widget
        self.bars = []
        self._geo = None

    def _ensure_bars(self, top):
        if (len(self.bars) == 4 and all(b.winfo_exists() for b in self.bars)
                and self.bars[0].master is top):
            return True
        self.destroy()
        try:
            self.bars = [tk.Frame(top, bd=0, highlightthickness=0, width=1, height=1)
                         for _ in range(4)]
            for b in self.bars:            # a click on the outline is a click on the widget
                b.bind("<Button-1>", lambda e, _w=self.widget: _w.event_generate("<Button-1>"))
                b.bind("<ButtonRelease-1>",
                       lambda e, _w=self.widget: _w.event_generate("<ButtonRelease-1>", x=1, y=1))
        except Exception:
            self.bars = []
        self._geo = None
        return bool(self.bars)

    def update(self, color):
        w = self.widget
        try:
            ok = bool(w.winfo_exists() and w.winfo_viewable())
        except Exception:
            ok = False
        if not ok:
            for b in self.bars:
                try:
                    b.place_forget()
                except Exception:
                    pass
            self._geo = None
            return
        try:
            top = w.winfo_toplevel()
            if not self._ensure_bars(top):
                return
            x = w.winfo_rootx() - top.winfo_rootx()
            y = w.winfo_rooty() - top.winfo_rooty()
            ww, hh = w.winfo_width(), w.winfo_height()
        except Exception:
            return
        t = self.T
        geo = (x, y, ww, hh)
        rects = [(x, y, ww, t), (x, y + hh - t, ww, t),          # top, bottom
                 (x, y, t, hh), (x + ww - t, y, t, hh)]          # left, right
        for b, (rx, ry, rw, rh) in zip(self.bars, rects):
            try:
                b.configure(bg=color)
                if geo != self._geo or not b.winfo_ismapped():
                    b.place(x=rx, y=ry, width=max(1, rw), height=max(1, rh))
                b.lift()                 # above its sibling widgets (no window juggling)
            except Exception:
                pass
        self._geo = geo

    def destroy(self):
        for b in self.bars:
            try:
                b.destroy()
            except Exception:
                pass
        self.bars = []


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
        _t0 = time.perf_counter()
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

        # On a Mac (Tk 9) a window of its own can't be see-through — the
        # arrow sat in a black box. There it is built from solid strips
        # laid into the window it points into (see _PlacedArrow), with
        # nothing around it that could show.
        self._mac = sys.platform == "darwin"
        if self._mac:
            self.win = None              # made in _build_items
            self.canvas = None
        else:
            self.win = tk.Toplevel(app.root)
            try:
                self.win.withdraw()          # shown once owned and placed (below)
            except Exception:
                pass
            try:
                self.win.overrideredirect(True)
            except Exception:
                pass
            # Owned by the window it points into (set before it is shown —
            # changing it later makes Windows re-create the window): an owned
            # window always stays above its owner, so the arrow can't fall
            # behind the inspection window.
            _own_by_target_window(self.win, self.target)
            # ...except when the target is in the always-on-top inspection
            # window: then the arrow must be on top too (set before the window
            # is shown, which is when every system takes it).
            if self._target_on_top():
                try:
                    self.win.attributes("-topmost", True)
                except Exception:
                    pass
            try:
                self.win.configure(bg=self._key)
            except Exception:
                pass
            # Otherwise deliberately NOT forced "-topmost" — it used to sit above
            # every other window, including popups/menus the app itself
            # opens (like the Choose Seeds dialog "Plant" opens), burying
            # them under the arrow. Without it, normal window stacking
            # applies: it renders above the main window (being a Toplevel
            # created after it) but a dialog or menu opened afterward still
            # comes to the front over it, same as any other window would.
            bg_color = self._key
            try:
                self.win.wm_attributes("-transparentcolor", self._key)
            except Exception:
                # Not supported on this platform (Linux) — falls back to a
                # plain key-colored rectangle behind the arrow.
                pass
            self.canvas = tk.Canvas(
                self.win, bg=bg_color, highlightthickness=0, bd=0,
                cursor="arrow",
            )
            self.canvas.pack()

        self._build_items()
        self._reposition()
        try:
            self.win.deiconify()
        except Exception:
            pass
        self._reposition()
        self._build_ring()
        self._keep_above_target_window()
        self._start_cycling()
        _dt = time.perf_counter() - _t0
        try:
            import __main__ as _m
            _m._ctrace(f"arrow at {self.target} built in {_dt:.3f} s")
        except Exception:
            pass

    def _give_focus_back(self):
        """macOS: a little borderless window that appears (a bar of the
        ring) can take over as the active window — the game window then
        only wakes up with the next click, and the click on the marked
        button is lost. Hand the focus straight back to the window the
        target sits in."""
        if sys.platform != "darwin":
            return
        try:
            top = self.target.winfo_toplevel()
            self.app.root.after(1, top.focus_force)
            import __main__ as _m
            _m._ctrace(f"focus handed back to {top}")
        except Exception:
            pass

    def _target_on_top(self):
        """True when the pointed-at widget sits in an always-on-top window
        (the inspection window): then the arrow and its ring have to be
        on top as well, or they end up hidden behind it."""
        try:
            top = self.target.winfo_toplevel()
            if top is not self.app.root and bool(top.attributes("-topmost")):
                return True
        except Exception:
            return False
        # The (always-on-top) inspection window is open: it could cover an
        # arrow pointing at the main window (e.g. at the garden "2" button).
        try:
            iw = getattr(self.app, "_inspector_win", None)
            return bool(iw is not None and iw.winfo_exists() and iw.winfo_viewable())
        except Exception:
            return False

    def _keep_above_target_window(self):
        if not self._target_on_top():
            return
        for w in [self.win] + list(getattr(self, "_ring", []) or []):
            try:
                w.attributes("-topmost", True)
                w.lift()
            except Exception:
                pass

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
            if self.canvas is not None:
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
            if self.canvas is not None:
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
        if getattr(self, "_mac", False):
            host = self.target.winfo_toplevel()
            self.win = _SnapshotArrow(host, pts, w, h, o, self.COLOR_A)
            self._main_id = None
            return
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
            left = x - w // 2
            # stay inside the main window (a target at its right edge, e.g.
            # the garden "2" button, would push half the arrow off screen)
            try:
                top = self.target.winfo_toplevel()
                r = top.winfo_rootx() + top.winfo_width()
                left = max(top.winfo_rootx(), min(left, r - w))
            except Exception:
                pass
            self.win.geometry(f"+{left}+{y}")
        except Exception:
            pass

    RING_THICKNESS = 3

    def _build_ring(self):
        """Four thin bars lying ON the target's own edge, pulsing in step
        with the arrow: the box marks exactly what can be clicked, never
        more (bars outside it reached over the gaps onto the buttons
        next to it). Laid into the target's window (see _EdgeBar), so they
        appear together with the arrow, cast no shadow on a Mac and never
        take the focus; a click on a bar counts as a click on the target."""
        self._ring = []
        try:
            t = self.RING_THICKNESS
            tg = self.target
            tg.update_idletasks()
            x, y = tg.winfo_rootx(), tg.winfo_rooty()
            w, h = tg.winfo_width(), tg.winfo_height()
            host = tg.winfo_toplevel()
            for rx, ry, rw, rh in _ring_rects(x, y, w, h, t):
                bar = _EdgeBar(host, tg, self.COLOR_A)
                bar.geometry(f"{rw}x{rh}+{rx}+{ry}")
                bar.deiconify()
                self._ring.append(bar)
        except Exception:
            pass

    def _set_step(self, step):
        self._step = max(0, min(self.STEPS, step))
        try:
            color = _lerp_color(self.COLOR_A, self.COLOR_B, self._step / self.STEPS)
            if isinstance(self.win, (_PlacedArrow, _SnapshotArrow)):
                self.win.set_fill(color)
            else:
                self.canvas.itemconfigure(self._main_id, fill=color)
            for bar in getattr(self, "_ring", []):
                _paint_bar(bar, color)
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
            self._follow_target()
            self._stay_on_top()
            self._job = self.app.root.after(self.STEP_MS, _tick)

        _tick()

    def _stay_on_top(self):
        """The arrow (and its ring) must never end up behind the window it
        points into — e.g. the inspection window coming to the front again
        after the arrow appeared. About twice a second: while the target is
        visible, everything is lifted above it again; while it isn't (the
        window stepped aside for a dialog), the arrow hides with it."""
        self._top_tick = getattr(self, "_top_tick", 0) + 1
        if self._top_tick % 3:
            return
        wins = [self.win] + list(getattr(self, "_ring", []) or [])
        try:
            visible = bool(self.target.winfo_exists() and self.target.winfo_viewable())
        except Exception:
            visible = False
        on_top = self._target_on_top()
        try:
            tgt_top = self.target.winfo_toplevel()
        except Exception:
            tgt_top = None
        for w in wins:
            try:
                if not visible:
                    if w.state() != "withdrawn":
                        w.withdraw()
                    continue
                if w.state() == "withdrawn":
                    w.deiconify()
                _raise_above(w, tgt_top, on_top)
            except Exception:
                pass

    def _follow_target(self):
        """Keeps the arrow and its ring on the target when the target moves
        (e.g. the inspector's flower row gets wider once a bud is selected,
        which shifts the forceps to the right)."""
        try:
            tg = self.target
            if not tg.winfo_exists() or not tg.winfo_ismapped():
                return
            geo = (tg.winfo_rootx(), tg.winfo_rooty(), tg.winfo_width(), tg.winfo_height())
        except Exception:
            return
        if geo == getattr(self, "_last_geo", None):
            return
        first = getattr(self, "_last_geo", None) is None
        self._last_geo = geo
        if first:
            return                       # just placed by __init__
        self._reposition()
        x, y, w, h = geo
        rects = _ring_rects(x, y, w, h, self.RING_THICKNESS)
        for bar, (rx, ry, rw, rh) in zip(getattr(self, "_ring", []) or [], rects):
            try:
                bar.geometry(f"{rw}x{rh}+{rx}+{ry}")
            except Exception:
                pass

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
    try:
        import tkinter.font as _tkfont
        _f = _tkfont.Font(root=app.root, font=font)
        _sz = int(_f.actual("size") or 16)
        _big = int(round(abs(_sz) * 1.4)) * (1 if _sz > 0 else -1)
        txt._big_font = _tkfont.Font(root=app.root, family=_f.actual("family"), size=_big,
                                     weight="bold")
        # lowered a little: the bigger arrows then sit in the middle of the
        # normal-sized letters instead of above it
        txt._big_drop = max(0, int(round((txt._big_font.metrics("ascent")
                                          - _f.metrics("ascent")) * 0.35)))
        txt.tag_configure("big", font=txt._big_font, foreground="black",
                          offset=-txt._big_drop)
        txt._big_font_default = txt._big_font
    except Exception:
        txt.tag_configure("big", foreground="black")
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
    # Already showing: nothing to do (this runs for every typed letter;
    # placing, raising and re-centring each time cost a lot on a Mac)
    try:
        if getattr(txt, "_placed", False) and txt.winfo_ismapped():
            return txt
    except Exception:
        pass
    txt._shown = None
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
    txt._placed = True
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
        font = getattr(txt, "_line_font", None) or tkfont.Font(font=txt.cget("font"))
        line_h = font.metrics("linespace") * int(getattr(txt, "_lines", 1) or 1)

        pady = int(txt.cget("pady") or 0)
        interior_h = max(0, txt.winfo_height() - 2 * pady)
        extra = max(0, interior_h - line_h)
        sp = extra // 2
        # A line with the big ← → arrows is taller above the baseline: start
        # it that much higher, so its letters sit exactly where they do on
        # every other line (the whole line was pushed down before).
        big = getattr(txt, "_big_font", None)
        if getattr(txt, "_has_big", False) and big is not None:
            rise = big.metrics("ascent") - getattr(txt, "_big_drop", 0) - font.metrics("ascent")
            sp = max(0, sp - max(0, rise))
        txt._centered_big = bool(getattr(txt, "_has_big", False))
        txt.tag_configure("base", spacing1=sp)
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
    txt._shown = None
    txt._placed = False
    try:
        txt.place_forget()
    except Exception:
        pass
    # a bar made taller for a long line on a narrow garden: back to normal
    h0 = getattr(app, "_tut_status_h0", None)
    try:
        if h0 and int(app.status_msg_row.cget("height") or 0) != int(h0):
            app.status_msg_row.configure(height=int(h0))
    except Exception:
        pass


_END_IMAGE_PAD = 8


def _line_end_image(app, name):
    """A small picture shown at the end of a dialogue line ("end_image"
    in the line's extra) — "bruchus": the pea weevil from
    icons/wildlife. None if the picture isn't there."""
    if not name:
        return None
    cache = app.__dict__.setdefault("_tut_end_images", {})
    if name in cache:
        return cache[name]
    img = None
    try:
        import glob
        from PIL import Image, ImageTk
        base = os.path.dirname(ICONS_DIR)
        pats = {"bruchus": ["bruchus*frame1.png", "bruchus*.png"]}.get(name, [name + "*.png"])
        path = None
        for d in (os.path.join(ICONS_DIR, "wildlife"), os.path.join(base, "wildlife"), ICONS_DIR):
            for pat in pats:
                hits = sorted(glob.glob(os.path.join(d, pat)))
                if hits:
                    path = hits[0]
                    break
            if path:
                break
        if path:
            im = Image.open(path).convert("RGBA")
            bb = im.getbbox()
            if bb:
                im = im.crop(bb)
            im.thumbnail((40, 30), Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
    except Exception:
        img = None
    cache[name] = img
    return img


# Text colour per speaker: Abbot Cyril red, Gregor Mendel a deep blue
# (clearly different from Cyril's red and from the black highlighted
# words, and well readable on the light status bar)
_SPEAKER_COLORS = {"cyril": "#c01818", "mendel": "#1f4f99"}

# Of a line's "highlight_words", only keyboard shortcuts are drawn in black;
# every other highlighted word keeps the speaker's own colour, so Cyril's
# lines stay red and Mendel's blue throughout.
_SHORTCUT_WORDS = frozenset({
    "Ctrl", "Command", "⌘", "←", "→", "arrow key", "Space", "I", "H", "X",
    "Ctrl + A", "⌘ + A",
    "press S", "Shift + S", "hold Shift", "Shift", "Esc", "Enter",
})


def _is_shortcut(word):
    return word in _SHORTCUT_WORDS or word in _BIG_GLYPHS


def _char_tags(text, words):
    """The tags of every character of `text` (highlight words matched in
    the whole line, longest first — so a word has its colour from its
    first typed letter on, instead of changing once it is complete)."""
    out = []
    i, n = 0, len(text)
    while i < n:
        matched = next((w for w in words if text.startswith(w, i)), None)
        if matched:
            if matched in _BIG_GLYPHS:
                tags = ("base", "highlight", "big")
            elif _is_shortcut(matched):
                tags = ("base", "highlight")
            else:
                tags = ("base", "normal")       # speaker's colour, not black
            out.extend([tags] * len(matched))
            i += len(matched)
        else:
            out.append(("base", "normal"))
            i += 1
    return out


def _insert_runs(txt, text, tags, start):
    """Inserts text[start:] with its tags, one insert per run of equal tags."""
    i, n = start, len(text)
    while i < n:
        j = i + 1
        while j < n and tags[j] == tags[i]:
            j += 1
        txt.insert("end", text[i:j], tags[i])
        i = j


def _set_rich_status_text(app, text, highlight_words, left_gutter=0, end_image=None,
                          color=None, full_text=None):
    """Renders `text` into the rich status overlay in the speaker's colour.
    Of highlight_words (matched longest-first so e.g. "Plant All" doesn't
    get swallowed by a shorter "Plant" rule) only keyboard shortcuts
    (_SHORTCUT_WORDS, the big arrows) are drawn in black.

    left_gutter (pixels, optional) reserves blank space before the
    first character via the "base" tag's lmargin1 — used while the "◀"
    back button is showing, so the text doesn't start underneath it."""
    txt = _show_rich_status_widget(app)
    words = sorted({w for w in (highlight_words or []) if w}, key=len, reverse=True)
    # Only what changed is touched: while a line types itself, each new
    # letter is just added at the end. (Redoing the whole line, its tags
    # and the buttons for every letter made the frame rate drop, on a
    # Mac most of all.)
    look = (left_gutter, color or _SPEAKER_COLORS["cyril"])
    if getattr(txt, "_look", None) != look:
        try:
            txt.tag_configure("base", lmargin1=left_gutter, lmargin2=left_gutter)
            txt.tag_configure("normal", foreground=look[1])
        except Exception:
            pass
        txt._look = look
        txt._shown = None
    plan_src = full_text if (full_text and full_text.startswith(text)) else text
    plan_key = (plan_src, tuple(words))
    if getattr(txt, "_plan_key", None) != plan_key:
        txt._plan_key = plan_key
        txt._plan = _char_tags(plan_src, words)
        txt._shown = None
    tags = txt._plan
    shown = getattr(txt, "_shown", None)
    try:
        txt.configure(state="normal")
        if (shown is not None and end_image is None and not getattr(txt, "_shown_img", False)
                and text.startswith(shown)):
            if len(text) > len(shown):
                _insert_runs(txt, text, tags, len(shown))
        else:
            txt.delete("1.0", "end")
            _insert_runs(txt, text, tags if len(tags) >= len(text) else _char_tags(text, words), 0)
        txt._shown = text
        txt._shown_img = end_image is not None
        if end_image is not None:
            try:
                txt.image_create("end", image=end_image, padx=_END_IMAGE_PAD, align="center")
            except Exception:
                pass
    finally:
        txt.configure(state="disabled")
    # (decided by the whole line, so it doesn't jump while being typed)
    has_big = any(g in words for g in _BIG_GLYPHS) and not getattr(txt, "_two_lines", False)
    if has_big != bool(getattr(txt, "_centered_big", False)):
        txt._has_big = has_big
        _center_text_vertically(txt)


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
    READ_MS_PER_WORD = 260

    def __init__(self, app, lines, on_finish=None, speed_ms=20):
        self.app = app
        self.lines = lines
        self.on_finish = on_finish
        self.speed_ms = speed_ms

        self._line_idx = -1
        self._end_image = None
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
        _click(self.app, btn, lambda: (_play_sound_via_app(self.app, "click.ogg"), command()))
        # A flat, borderless button like this one doesn't get any
        # hover feedback from Tk by default — bind it explicitly so it's
        # obvious the button is clickable.
        btn._hover = False
        btn.bind("<Enter>", lambda e, b=btn: (setattr(b, "_hover", True),
                                              b.configure(bg=self._btn_bg_hover)))
        btn.bind("<Leave>", lambda e, b=btn: (setattr(b, "_hover", False),
                                              b.configure(bg=self._btn_bg_normal)))
        return btn

    def _reposition_buttons(self, text, end_image=None):
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
                self._stop_next_pulse()
                self.next_btn.place_forget()
            else:
                lf = getattr(txt, "_line_font", None) or self._font
                if getattr(txt, "_two_lines", False):
                    x = (txt_x + self._visible_width(txt) - inset
                         - self.next_btn.winfo_reqwidth() - 4)
                else:
                    text_w = lf.measure(text)
                    big = getattr(txt, "_big_font", None)
                    if big is not None and getattr(txt, "_has_big", False):
                        for g in _BIG_GLYPHS:
                            text_w += text.count(g) * (big.measure(g) - lf.measure(g))
                    if end_image is not None:
                        try:
                            text_w += end_image.width() + 2 * _END_IMAGE_PAD
                        except Exception:
                            pass
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
        """Whenever "▶" shows (a line that waits for a click), it pulses
        between its normal brown and a soft amber, so the player always
        notices there is something to press to go on. (Under the mouse
        it shows its hover colour instead.)"""
        if self._next_pulse_job is not None:
            return

        steps = 32  # one full pulse = 32 * 50ms = 1.6s
        self._next_pulse_k = 0

        def _tick():
            self._next_pulse_k = (self._next_pulse_k + 1) % steps
            t = (1 - math.cos(2 * math.pi * self._next_pulse_k / steps)) / 2
            try:
                hover = getattr(self.next_btn, "_hover", False)
                self.next_btn.configure(
                    bg=(self._btn_bg_hover if hover else
                        _lerp_color(self._btn_bg_normal, "#D08A3A", t)),
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

    MIN_FONT_PT = 11            # smallest type before a line is wrapped onto two

    def _visible_width(self, txt):
        """The message bar's width that is really on screen (a small screen
        can cut off the right end of the window). Taken from the bar's row,
        which is always shown (the text overlay may not be placed yet: its
        width then reads as 1 px, and every line was shrunk and the bar
        made huge)."""
        row = self.app.status_msg_row
        w = row.winfo_width()
        if w < 50:
            try:
                w = int(row.cget("width") or 0)
            except Exception:
                pass
        try:
            right = row.winfo_screenwidth() - max(0, row.winfo_rootx())
            if right > 50:
                w = min(w, right)
        except Exception:
            pass
        return w

    def _fit_line(self):
        """Makes the whole line (with ▶) fit into the visible message bar:
        in smaller type if it is too long for one line at the normal size,
        and on two lines with ▶ at the right end if even the smallest type
        is too wide (a narrow garden, a small screen). Otherwise the end of
        the line, and the ▶ the player has to click, were out of sight."""
        try:
            txt = _show_rich_status_widget(self.app)
            txt.update_idletasks()
            fam = self._font.actual("family")
            size0 = abs(int(self._font.actual("size") or 16))
            full = str(self._full_text or "")
            if self._live_readout_name:
                full += _format_live_readout(self.app, self._live_readout_name) or ""
            bd = int(txt.cget("bd") or 0)
            pady = int(txt.cget("pady") or 0)
            inset = self._label_padx + bd
            gutter = self._gutter_width() if self._line_idx > 0 else 0
            wants_btn = not (self._auto_advance or self._no_skip)
            btn = (self.next_btn.winfo_reqwidth() + 14) if wants_btn else 0
            vis = self._visible_width(txt)
            if vis < 120:                      # not laid out yet: leave the line as it is
                raise ValueError("no width")
            avail = vis - 2 * inset - gutter - btn - 6
            if self._end_image is not None:
                try:
                    avail -= self._end_image.width() + 2 * _END_IMAGE_PAD
                except Exception:
                    pass
            bigs = [g for g in _BIG_GLYPHS if g in (self._highlight_words or [])]

            def width(f, bf):
                w_ = f.measure(full)
                for g in bigs:
                    w_ += full.count(g) * (bf.measure(g) - f.measure(g))
                return w_

            def fonts(sz):
                return (tkfont.Font(root=self.app.root, family=fam, size=sz, weight="bold"),
                        tkfont.Font(root=self.app.root, family=fam, size=int(round(sz * 1.4)),
                                    weight="bold"))
            row = self.app.status_msg_row
            h0 = getattr(self.app, "_tut_status_h0", None)
            if h0 is None:
                h0 = self.app._tut_status_h0 = int(row.cget("height") or row.winfo_height())
            frame_h = 2 * pady + 2 * bd           # the text's own padding and border
            interior_h = h0 - frame_h
            pick = None
            for sz in range(size0, self.MIN_FONT_PT - 1, -1):
                f, bf = fonts(sz)
                if width(f, bf) <= avail:
                    pick = (sz, f, bf, 1)
                    break
            if pick is None:                         # two lines
                for sz in range(size0, 8, -1):
                    f, bf = fonts(sz)
                    if (2 * f.metrics("linespace") <= interior_h
                            and width(f, bf) <= 2 * avail * 0.9):
                        pick = (sz, f, bf, 2)
                        break
            if pick is None:                         # very narrow: one line more, no more
                f, bf = fonts(10)
                pick = (10, f, bf, 3)
            sz, f, bf, lines = pick
            want_h = max(h0, lines * f.metrics("linespace") + frame_h)
            if int(row.cget("height") or 0) != want_h:
                row.configure(height=want_h)
                txt.update_idletasks()
            txt._line_font = f
            txt._lines = lines
            txt._two_lines = lines > 1
            # the widget's own font (the line's last newline uses it too,
            # so a tag font alone left a big empty line height)
            txt.configure(font=f)
            # (several lines: the text keeps clear of ▶ and of a cut-off right end)
            txt.tag_configure("base", rmargin=(max(0, self.app.status_msg_row.winfo_width() - vis)
                                               + btn + 4 if lines > 1 else 0))
            # (on several lines the arrows keep the normal size: a taller
            # first line would push the last one out of the bar)
            big = f if lines > 1 else (bf if sz != size0 else (getattr(txt, "_big_font_default", None) or bf))
            txt._big_font = big
            txt._big_drop = max(0, int(round((big.metrics("ascent") - f.metrics("ascent")) * 0.35)))
            txt.tag_configure("big", font=big, offset=-txt._big_drop)
            txt._has_big = bool(bigs) and lines == 1
            _center_text_vertically(txt)
        except Exception:
            self._reset_line_fit()

    def _reset_line_fit(self):
        """The normal look: normal type, one line, the bar at its own height."""
        try:
            txt = _ensure_rich_status_widget(self.app)
            txt._line_font = None
            txt._lines = 1
            txt._two_lines = False
            txt.configure(font=self._font)
            txt.tag_configure("base", rmargin=0)
            big = getattr(txt, "_big_font_default", None)
            if big is not None:
                txt._big_font = big
                txt._big_drop = max(0, int(round((big.metrics("ascent")
                                                  - self._font.metrics("ascent")) * 0.35)))
                txt.tag_configure("big", font=big, offset=-txt._big_drop)
            h0 = getattr(self.app, "_tut_status_h0", None)
            if h0 and int(self.app.status_msg_row.cget("height") or 0) != int(h0):
                self.app.status_msg_row.configure(height=int(h0))
            _center_text_vertically(txt)
        except Exception:
            pass

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
        img = (self._end_image if self._end_image is not None
               and self._char_pos >= len(self._full_text) else None)
        full = self._prefix + self._full_text
        try:
            left_gutter = self._gutter_width() if self._line_idx > 0 else 0
            _set_rich_status_text(self.app, text, self._highlight_words, left_gutter,
                                  end_image=img,
                                  color=_SPEAKER_COLORS.get(str(self._speaker or "").strip().lower()),
                                  full_text=full)
        except Exception:
            pass
        # ▶ / ◀ are placed once for the line — where the finished line will
        # end — not moved along with every typed letter (each move made Tk
        # lay out the window again: a slow, jerky typing on a Mac).
        typing = self._char_pos < len(self._full_text)
        pos_text = full if typing else text
        pos_img = self._end_image if typing else img
        key = (self._line_idx, pos_text, pos_img is not None,
               getattr(self, "_auto_advance", None), getattr(self, "_no_skip", None),
               typing)
        if key != getattr(self, "_btn_key", None):
            self._btn_key = key
            self._reposition_buttons(pos_text, pos_img)
            if typing:
                # ▶ only once the last letter of the line is there
                try:
                    self._stop_next_pulse()
                    self.next_btn.place_forget()
                except Exception:
                    pass

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
                    os.path.join(ICONS_DIR, fname), _SPEAKER_CAPTIONS.get(speaker, speaker))
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
        # "skip_if": a line that isn't needed when its condition already
        # holds (e.g. "select a plant first" when one is selected) — only
        # skipped on the way forward, so ◀ can still go back past it.
        _prev = getattr(self, "_line_idx", -1)
        _ex = self.lines[idx][2] if len(self.lines[idx]) > 2 else {}
        if (_ex.get("skip_if") and idx > (_prev if _prev is not None else -1)
                and idx + 1 < len(self.lines)):
            try:
                if _WAIT_CONDITIONS[_ex["skip_if"]](self.app, None):
                    self._line_idx = idx
                    self._show_line(idx + 1)
                    return
            except Exception:
                pass
        self._cancel_auto_advance()
        self._line_idx = idx
        entry = self.lines[idx]
        speaker, text = entry[0], entry[1]
        if callable(text):              # worked out when shown (e.g. days to spring)
            try:
                text = str(text(self.app))
            except Exception:
                text = ""
        extra = entry[2] if len(entry) > 2 else {}
        # the pod of the first cross: only pods marked »P« can be harvested
        self.app._tutorial_cross_pods_only = bool(extra.get("cross_pods_only"))
        # ...picked by clicking the »P« pod itself in the inspection window
        self.app._tutorial_pod_click_only = bool(extra.get("pod_click_only"))
        # ...sown only with »Plant«, »Seeds from crosses« ticked at this generation
        self.app._tut_sow_gen = extra.get("sow_gen_only")
        # ...the first seeds one by one: »All« in Choose Seeds (and the
        # right-click »Plant All«) wait until Cyril explains them
        self.app._tut_no_plant_all = bool(extra.get("no_plant_all"))
        # "tie_focus": the TIE is switched to the plant the line talks about
        # (as soon as it is open), so a sibling shown there can't confuse
        if extra.get("tie_focus") == "f2_white":
            def _focus(_i=idx):
                try:
                    if getattr(self, "_line_idx", None) != _i or not self.app.root.winfo_exists():
                        return
                except Exception:
                    return
                if not _tie_focus_white_f2(self.app):
                    self.app.root.after(400, _focus)
            self.app.root.after(250, _focus)
        self._auto_advance = not bool(extra.get("pause", False))
        # Longer lines stay longer: at least READ_MS_PER_WORD per word after
        # the typing has finished (a flat 2.5 s was too short for long lines).
        self._auto_advance_ms = max(extra.get("auto_advance_ms") or self.AUTO_ADVANCE_MS,
                                    self.READ_MS_PER_WORD * len(str(text).split()))
        # "question": Abbot Cyril asks (a window with the family tree so far
        # and the answers), once the line has been typed
        self.app._tut_question_key = extra.get("question")
        if extra.get("question") and _tut_answer(self.app, extra["question"]) is None:
            def _ask(_i=idx, _k=extra["question"]):
                try:
                    if getattr(self, "_line_idx", None) != _i or not self.app.root.winfo_exists():
                        return
                except Exception:
                    return
                if not getattr(self.app, "_tutorial_active", False):
                    return
                open_question(self.app, _k)
            self.app.root.after(len(str(text)) * self.speed_ms + 500, _ask)
        elif not extra.get("question"):
            _close_question(self.app)
        self._wait_condition_name = extra.get("wait_for_condition")
        self._wait_baseline = (
            getattr(self.app, "available_seeds", 0)
            if self._wait_condition_name else None
        )
        # "first_seed_planted" is measured against the seed count the
        # lecture started with, not whatever it is when this line appears —
        # otherwise a player who plants everything early (before this
        # line shows) leaves the baseline at 0 and the wait never fires.
        if self._wait_condition_name == "ff_used":
            self._wait_baseline = int(getattr(self.app, "_ff_run_count", 0) or 0)
        if self._wait_condition_name in ("two_plants_harvested", "other_plant_harvested",
                                         "other_plants_harvested"):
            self._wait_baseline = len(getattr(self.app, "_harvest_log", []) or [])
            _log = list(getattr(self.app, "_harvest_log", []) or [])
            _prev = _log[-1] if _log else None
            self.app._tut_other_plants_need = min(OTHER_PLANTS_NEEDED,
                                                  _ripe_plants_other_than(self.app, _prev))
        if (self._wait_condition_name in ("seed_filter_crossed", "seed_filter_ofcross")
                and ("seedfilter", idx) not in self._granted_lines):
            self._granted_lines.add(("seedfilter", idx))      # once (the line may be shown again)
            # the player ticks it (nothing else filtered away meanwhile)
            for _a in ("_seed_filter_gen", "_seed_filter_look", "_seed_filter_flower",
                       "_seed_filter_gens"):
                setattr(self.app, _a, None)
            for _a in ("_seed_filter_crossed", "_seed_filter_ofcross", "_seed_filter_noted"):
                setattr(self.app, _a, False)
        if self._wait_condition_name == "several_removed":
            self._wait_baseline = len(getattr(self.app, "_remove_log", []) or [])
        if self._wait_condition_name == "note_saved":
            self._wait_baseline = int(getattr(self.app, "_notes_saved_count", 0) or 0)
        if self._wait_condition_name == "sunny_skip_used":
            self._wait_baseline = int(getattr(self.app, "_sunny_skip_count", 0) or 0)
        if self._wait_condition_name in ("s_key_harvest", "shift_s_harvest"):
            self._wait_baseline = len(getattr(self.app, "_key_harvest_log", []) or [])
        if self._wait_condition_name == "frost_harvest":
            self._wait_baseline = len(getattr(self.app, "_harvest_log", []) or [])
            self.app._tut_frost_need = min(2, _plants_with_ripe_pods(self.app))
        if self._wait_condition_name in ("pod_harvested", "pod_harvested_once"):
            self._wait_baseline = len(getattr(self.app, "harvest_inventory", []) or [])
            self.app._tut_harvest_seen = False
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
        # The portrait always shows whoever is speaking: Mendel's own lines
        # show Mendel, every line Cyril speaks shows Cyril (also the ones
        # that ask the player to do something).
        want_mendel = str(speaker).strip().lower() == "mendel"
        if want_mendel:
            self._mendel_shown = self._show_mendel_portrait()
        elif getattr(self, "_mendel_shown", False):
            self._mendel_shown = False
            self._caption_speaker = None      # force Cyril to be redrawn
        self._apply_speaker_caption(speaker)
        self._full_text = text
        self._char_pos = 0
        self._highlight_words = extra.get("highlight_words") or []
        self._end_image = _line_end_image(self.app, extra.get("end_image"))
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
        # Lines that ask for a flower to be selected start with none
        # selected (a selection left from an earlier step would count at once).
        if extra.get("clear_flower_selection"):
            _clear_flower_selection(self.app)
        if extra.get("open_plot2"):
            _open_plot2(self.app)
        # The real weather for a Fast Forward Cyril asks for (the winter,
        # the wait for a sunny morning) — not his visit's clear sky.
        if extra.get("release_sun"):
            _release_sun(self.app)
        # "real_time": back to real time (1 sec = 1 sec), e.g. while the
        # pollen has to be collected that very morning
        if extra.get("real_time"):
            _tutorial_set_speed(self.app, _TUTORIAL_DAY_LENGTH_S)
        # "force_weather": this weather from now on (e.g. a thunderstorm
        # before »Skip to next sunny day«), until a "release_sun" line
        if extra.get("force_weather"):
            try:
                g = self.app.garden
                g.weather_lock = extra["force_weather"]
                g.weather = extra["force_weather"]     # also underneath the lock
                self.app.render_all()
            except Exception:
                pass
        if extra.get("allow_sowing"):
            self.app._tut_no_sowing = False
        if extra.get("close_wildlife"):
            _close_inspector_section(self.app, "wildlife")
        if extra.get("give_colour_seeds") and idx not in self._granted_lines:
            self._granted_lines.add(idx)
            _give_colour_seeds(self.app)
        if extra.get("allow_tie"):
            self.app._tut_allow_tie = True      # part 5: the TIE is the player's
        # "ff_days": (suggested, at most) for the Fast Forward window while
        # this line shows (the very first Fast Forward); otherwise no cap
        if extra.get("ff_days"):
            _sug_d, _max_d = extra["ff_days"]
            self.app._ff_days_saved = getattr(self.app, "_ff_suggest_days", None)
            self.app._ff_suggest_days = lambda _d=_sug_d: _d
            self.app._ff_max_days = _max_d
        elif getattr(self.app, "_ff_max_days", None):
            self.app._ff_max_days = None
            self.app._ff_suggest_days = getattr(self.app, "_ff_days_saved", None)
        if extra.get("tie_sections") is not None:
            _set_tie_sections(self.app, dict(extra["tie_sections"]))
        # "tie_trait": the trait the TIE shows when it opens (an open TIE
        # switches to it right away); "" — the player's choice again
        if "tie_trait" in extra:
            self.app._tut_tie_trait = extra["tie_trait"] or None
            if extra["tie_trait"]:
                try:
                    t_ = _tie(self.app)
                    if t_ is not None:
                        t_.trait_mode.set(extra["tie_trait"])
                except Exception:
                    pass
        if extra.get("tie_tab") is not None:
            _set_tie_tab(self.app, int(extra["tie_tab"]))
        if self._wait_condition_name == "tie_alleles_hovered":
            self.app._tie_alleles_hovered = False
        if extra.get("unlock_buttons"):
            _unlock_buttons(self.app, extra["unlock_buttons"])
            if "fast_btn" in extra["unlock_buttons"]:
                _set_ff_locked(self.app, False)     # the F key works too now
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
        # No arrows into the inspection window (on Windows they kept
        # flickering between above and below it): its buttons only glow
        # (see the glow_targets below, which always include them).
        target_names = [n for n in (target_names or [])
                        if not str(n).startswith(("inspector_", "tie_", "gv_"))]
        # Inspect / Harvest only make sense for a marked plant: their arrow
        # appears once one of the marked plants is selected (and goes away
        # again if another plant is selected) — otherwise players click the
        # button straight away, with no or the wrong plant selected.
        _hp = extra.get("highlight_plants")
        if _hp is not None:
            for _gn in [n for n in target_names if n in ("inspect_button", "harvest_button")]:
                target_names.remove(_gn)
                self._poll_late_highlight(
                    _gn, idx, when=lambda _st=_hp: _marked_plant_selected(self.app, _st))
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

        if extra.get("highlight_plants") is not None:
            try:
                hp = extra["highlight_plants"]
                _show_plant_highlight(self, hp if isinstance(hp, str) else int(hp))
            except Exception:
                pass
        elif (extra.get("clear_plant_highlight")
              or extra.get("wait_for_condition") in _SOWING_CONDITIONS):
            # sowing: every plot can be picked again (the rings of an
            # earlier line would otherwise still limit the selection)
            _clear_plant_highlight(self)

        # "inspector_closed": the inspection window opens with every section
        # closed from now on (until part 3 ends) — the player's own saved
        # choice is left alone.
        if extra.get("inspector_closed"):
            try:
                self.app._tut_insp_sections = {k: False for k, _l in self.app._INSPECTOR_SECTIONS}
            except Exception:
                pass
        self.app._tut_praise = None
        if extra.get("glow_harvest"):
            self._poll_glow_harvest(idx)
        _glow = list(extra.get("glow_targets") or [])
        _ht = extra.get("highlight_target")
        for n in ([_ht] if isinstance(_ht, str) else list(_ht or [])):
            if str(n).startswith(("inspector_", "tie_", "gv_")) and n not in _glow:
                _glow.append(n)              # instead of an arrow: it glows
        # A line about the TIE / Genotype Explorer while that window is
        # closed: its button in the inspection window glows (and the arrow
        # goes to »Inspect« when that window is closed too).
        _reopen = None
        if _glow and all(str(n).startswith("tie_") for n in _glow):
            _reopen = ("tie_reopen", lambda: _tie(self.app) is None)
        elif _glow and all(str(n).startswith("gv_") for n in _glow):
            _reopen = ("gv_reopen", lambda: _live_widget(
                getattr(self.app, "_genotype_viewer_win", None)) is None)
        if _reopen and (extra.get("wait_for_condition") or extra.get("pause")):
            _glow.append(_reopen[0])

            def _both_closed(_w=_reopen[1]):
                if not _w():
                    return False
                win_ = _live_widget(getattr(self.app, "_inspector_win", None))
                try:
                    return win_ is None or not win_.winfo_viewable()
                except Exception:
                    return True
            self._poll_late_highlight("inspect_button", idx, when=_both_closed)
        if _glow:
            self._poll_glow_harvest(idx, _glow)
        # Everything this line points at lives in the inspection window:
        # if the player closed it, the arrow shows on »Inspect« first, so
        # nobody is left stuck (e.g. »Make note« with the window shut).
        _ht_all = [extra.get("highlight_target")] if isinstance(extra.get("highlight_target"), str) \
            else list(extra.get("highlight_target") or [])
        if (_glow and all(str(n).startswith("inspector_") for n in _glow)
                and "inspect_button" not in _ht_all
                and (extra.get("wait_for_condition") or extra.get("pause"))):
            def _insp_closed():
                if getattr(self.app, "_reopen_inspector_after_dialog", False):
                    return False           # only stepped aside for a dialog
                w = _live_widget(getattr(self.app, "_inspector_win", None))
                try:
                    return w is None or not w.winfo_viewable()
                except Exception:
                    return True
            self._poll_late_highlight("inspect_button", idx, when=_insp_closed)

        if extra.get("highlight_late"):
            for name in (target_names or []):
                if _HIGHLIGHT_TARGETS.get(name, lambda app: None)(self.app) is None:
                    self._poll_late_highlight(name, idx)
                    break

        self._fit_line()
        self._set_status(self._prefix)
        self._type_started = time.monotonic()
        self._type_next_char()
        self._start_live_readout()

    def _poll_glow_harvest(self, idx, targets=None):
        """A pulsing crimson outline on the ripe pods and the Harvest All
        button (or other named widgets) in the inspection window, while
        this line shows."""
        # Crimson pulse (good contrast on the inspector's beige): fades
        # between a light and a deep crimson over 3.6 s (12 steps of 300 ms).
        # Drawn as an overlay (_GlowRing: four thin borderless bars lying
        # on the widget's own edge), not as a widget border — a border
        # would make the widget bigger and the inspection window grow and
        # shift while the outline pulses.
        state = {"step": 0, "rings": {}}
        colors = ("#B0102C", "#EE8A9C")
        steps = 12

        def _clear():
            for ring in state["rings"].values():
                ring.destroy()
            state["rings"] = {}

        def _poll():
            if (getattr(self.app, "_tutorial_dialogue", None) is not self
                    or self._line_idx != idx):
                _clear()
                return
            ws = []
            if targets:
                # named widgets (e.g. a section button of the inspector)
                for name in targets:
                    w = _HIGHLIGHT_TARGETS.get(name, lambda app: None)(self.app)
                    if isinstance(w, (list, tuple)):
                        ws.extend(x for x in w if x is not None)
                    elif w is not None:
                        ws.append(w)
            else:
                hb = _live_widget(getattr(self.app, "_inspector_harvest_btn", None))
                if hb is not None:
                    ws.append(hb)
                for lbl, can in list(getattr(self.app, "_inspector_pod_labels", None) or []):
                    if can and _live_widget(lbl) is not None:
                        ws.append(lbl)
            state["step"] = (state["step"] + 1) % steps
            t = 0.5 - 0.5 * math.cos(2 * math.pi * state["step"] / steps)
            col = _lerp_color(colors[1], colors[0], t)
            keep = {}
            for w in ws:
                ring = state["rings"].pop(id(w), None)
                if ring is None or ring.widget is not w:
                    if ring is not None:
                        ring.destroy()
                    ring = _GlowRing(self.app, w)
                ring.update(col)
                keep[id(w)] = ring
            for ring in state["rings"].values():      # no longer glowing
                ring.destroy()
            state["rings"] = keep
            self.app.root.after(300, _poll)

        self.app.root.after(300, _poll)

    def _poll_late_highlight(self, name, idx, when=None):
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
            if when is not None:
                try:
                    if not when():
                        w = None                    # not yet (see "when")
                except Exception:
                    w = None
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
                    state["arrow"]._keep_above_target_window()   # above the inspector window
                    state["arrow"].win.lift()
                except Exception:
                    pass
            self.app.root.after(300, _poll)

        self.app.root.after(300, _poll)

    def _bind_arrow_dismiss_on_click(self, widget):
        def _on_click(event=None):
            # Not right here, during the press: taking the arrow down (on a
            # Mac: its many strips) held up the click itself — the button
            # only answered seconds later. The click goes first.
            # (only the arrow of this click: the click may already have
            # moved the dialogue on to a line with an arrow of its own)
            mine = getattr(self, "_active_arrow", None)

            def _later():
                if mine is not None and getattr(self, "_active_arrow", None) is mine:
                    _clear_dialogue_arrow(self)
            try:
                widget.after(120, _later)
            except Exception:
                _later()

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

        # "nudge": (ms, text, highlight words) — if the player still hasn't
        # done it after ms, the speaker says more plainly what to do
        try:
            _ent = self.lines[line_idx]
            _nudge = ((_ent[2] if len(_ent) > 2 else None) or {}).get("nudge")
        except Exception:
            _nudge = None
        nudged = {"done": False}

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

            if (not satisfied and _nudge and not nudged["done"]
                    and (time.monotonic() - started) * 1000.0 >= float(_nudge[0])):
                nudged["done"] = True
                try:
                    self._full_text = _nudge[1]
                    self._char_pos = len(_nudge[1])
                    self._highlight_words = list(_nudge[2] if len(_nudge) > 2 else [])
                    self._fit_line()
                    self._set_status(_nudge[1])
                except Exception:
                    pass

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
            self._stop_next_pulse()
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
            self.app._tutorial_cross_pods_only = False
            self.app._tutorial_pod_click_only = False
            self.app._tut_sow_gen = None
            self.app._tut_no_plant_all = False
            for btn_attr in ("next_btn", "back_btn"):
                try:
                    getattr(self, btn_attr).destroy()
                except Exception:
                    pass
            self._set_status("")
            _hide_rich_status_widget(self.app)
            _clear_plant_highlight(self)
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
    "harvest_btn", "pollen_btn", "emasc_btn", "pollinate_btn", "remove_btn",
    "genetics_btn", "tie_btn", "fast_btn", "sunny_ff_btn", "measure_temp_btn",
    "observatory_btn",
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


def key_blocked(app, name):
    """A shortcut of a button the tutorial has not explained yet does
    nothing (Garden-of-Inheritance.py, _bind_hotkeys)."""
    return _policy_active(app) and name not in (getattr(app, "_tutorial_unlocked", None) or ())


def removal_protected(app, plant):
    """Plants the tutorial still needs cannot be removed (with »Remove
    plant«, X or Delete): the cross's mother while her crossed flower is
    on its way, the children of the cross (F1) until their seeds grow,
    and the grandchildren (F2) until the tutorial is over."""
    if plant is None or not _policy_active(app):
        return False
    try:
        for f in plant.ensure_flowers() or []:
            if _hand_emasc(f) and not f.get("harvested"):
                return True
    except Exception:
        pass
    try:
        if _is_cross_child(plant) and not _f2_plants(app):
            return True
        if _is_f2(app, plant):
            return True
    except Exception:
        pass
    return False


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
# Name written on the portrait for each speaker
_SPEAKER_CAPTIONS = {"Cyril": "Cyril Napp"}
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
    _close_question(app)
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
    app._tutorial_cross_pods_only = False
    app._tutorial_pod_click_only = False
    app._tut_sow_gen = None
    app._tut_no_plant_all = False
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
            # how far parts 4 and 5 got (they have no save points of their own)
            "later_steps": _later_steps(app),
            "day_length_s": float(getattr(app, "day_length_s", 1.0)),
            "garden": app._serialize_garden_state(),
        }
        with open(path or _progress_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        if path is None:
            app._tutorial_part_done = int(part_done)
    except Exception:
        pass


def _later_steps(app):
    return {"ageing_seen": bool(getattr(app, "_tutorial_ageing_seen", False)),
            "spring_seen": bool(getattr(app, "_tutorial_spring_seen", False)),
            "sunny_btn": "sunny_ff_btn" in (getattr(app, "_tutorial_unlocked", None) or ()),
            "cross_done": int(getattr(app, "_tutorial_cross_done", 0) or 0),
            "plot2_open": bool(getattr(app, "_tutorial_plot2_open", False)),
            "p5": int(getattr(app, "_tutorial_p5", 0) or 0),
            "p5_spring": list(getattr(app, "_tut_p5_spring", None) or []),
            "allow_tie": bool(getattr(app, "_tut_allow_tie", False)),
            "starter_n": int(getattr(app, "_tut_starter_n", 0) or 0),
            "answers": dict(getattr(app, "_tut_answers", None) or {})}


def _set_later_steps(app, steps=None):
    steps = steps or {}
    app._tutorial_ageing_seen = bool(steps.get("ageing_seen", False))
    app._tutorial_spring_seen = bool(steps.get("spring_seen", False))
    # the »▶▶ ☀« button, once handed over (in the spring visit of part 4)
    if steps.get("sunny_btn", int(steps.get("cross_done", 0) or 0) > 0
                 or int(steps.get("p5", 0) or 0) > 0):
        _unlock_buttons(app, ["sunny_ff_btn"])
    app._tutorial_cross_done = int(steps.get("cross_done", 0) or 0)
    app._tutorial_p5 = int(steps.get("p5", 0) or 0)
    _sp = steps.get("p5_spring") or None
    app._tut_p5_spring = tuple(_sp) if _sp else None
    app._tut_allow_tie = bool(steps.get("allow_tie", False))
    app._tut_starter_n = int(steps.get("starter_n", 0) or 0)
    app._tut_answers = dict(steps.get("answers") or {})
    # (older saves without the flag: open once spring had come)
    app._tutorial_plot2_open = bool(steps.get("plot2_open", app._tutorial_spring_seen))
    # Garden 2 still closed: back to garden 1, and the "2" button greyed
    try:
        if not app._tutorial_plot2_open and int(getattr(app, "active_plot_index", 0) or 0) != 0:
            app._switch_to_plot(0)
        app._refresh_plot_switcher_buttons()
    except Exception:
        pass


def _clear_flower_selection(app):
    """Deselects every flower/bud in the Inspect window's flower row."""
    for sel in list((getattr(app, "_flower_sel", None) or {}).values()):
        try:
            sel.clear()          # the same set objects the flower row uses
        except Exception:
            pass
    live = getattr(app, "_flower_panel_live", None)
    if live:
        try:
            live[1]()
        except Exception:
            pass


def _open_plot2(app):
    """Part 4 (spring): garden 2 becomes the player's to use."""
    app._tutorial_plot2_open = True
    try:
        app._refresh_plot_switcher_buttons()
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
    """Every 2 s (between Cyril's lines): once the plants are gone and no
    seeds are left either, Abbot Cyril offers to go back to the last
    tutorial save. Asked once; asked again only after
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
                if (_tutorial_seeds_left(app) == 0
                        and int(getattr(app, "_tutorial_part_done", 0) or 0) >= 1
                        and (_tutorial_plants_lost(app) or _living_plants(app) == 0)):
                    if not getattr(app, "_tutorial_loss_asked", False):
                        app._tutorial_loss_asked = True
                        _offer_restart_after_loss(app)
                else:
                    app._tutorial_loss_asked = False
        except Exception:
            pass
        app._tutorial_loss_job = app.root.after(2000, _check)

    app._tutorial_loss_job = app.root.after(2000, _check)


_TUTORIAL_PART_AWARDS = {
    1: ("tutorial_1", "The First Seeds",
        "The peas are in the ground, Gregor. Every great experiment starts "
        "with a handful of seeds and a little faith."),
    2: ("tutorial_2", "The Seedlings",
        "Well tended! Watered, inspected and thriving — your seedlings "
        "are in good hands."),
    3: ("tutorial_3", "Buds, Flowers & Pods",
        "From the first bud to the first harvest — you have seen a whole "
        "pea season through. Now the real experiments can begin!"),
    5: ("tutorial_5", "Crossing",
        "Your first cross by hand, Gregor: emasculated, pollinated and "
        "harvested. These seeds have two parents you chose yourself."),
}


def _award_tutorial_part(app, n):
    """Achievement for finishing tutorial part n (1-3 as on the map; 5 is
    map part 4, »Crossing«, kept under its old key tutorial_5);
    Abbot Cyril congratulates the first time."""
    key, title, text = _TUTORIAL_PART_AWARDS.get(n, (None, None, None))
    if not key:
        return None
    try:
        if app._award_achievement(key):
            return app._show_cyril_congrats(title, text)
    except Exception:
        pass
    return None


def _offer_next_lesson_after(app, congrats_win=None, delay_ms=5000):
    """Abbot Cyril asks whether Gregor is ready for the next lesson:
    5 s after the achievement window closes (or after part 3 ends)."""
    def _ask():
        if not getattr(app, "_tutorial_active", False):
            return
        if getattr(app, "_tutorial_dialogue", None) is not None:
            app.root.after(2000, _ask)               # wait for a quiet moment
            return
        if (int(getattr(app, "_tutorial_cross_done", 0) or 0) >= 3
                and int(getattr(app, "_tutorial_p5", 0) or 0) > 0):
            return                                   # part 5 is already under way
        was_running = bool(getattr(app, "running", True))
        app.running = False
        try:
            yes = _cyril_ask(
                app,
                "\u201cGregor, you have taken to the garden wonderfully. I have "
                "another lesson waiting for you, whenever you feel ready.\u201d",
                "\u201cShall we begin the next lesson?\u201d",
                "Yes, let\u2019s begin", "Not just yet", portrait="franz_2.png")
        except Exception:
            yes = False
        app.running = was_running
        if yes:
            _begin_next_lesson(app)
        elif int(getattr(app, "_tutorial_cross_done", 0) or 0) >= 3:
            _watch_for_p5_spring_offer(app)          # he asks again next spring

    def _later(_e=None):
        try:
            app.root.after(delay_ms, _ask)
        except Exception:
            pass

    try:
        if congrats_win is not None and congrats_win.winfo_exists():
            congrats_win.bind("<Destroy>",
                              lambda e: _later() if e.widget is congrats_win else None,
                              add="+")
            return
    except Exception:
        pass
    _later()


def _p5_offer_ready(app, after):
    """Next spring's morning (March to May, 7:00-11:59, fine weather)
    after the (year, month) `after`."""
    try:
        g = app.garden
        y, mo, h = int(g.year), int(g.month), int(g.clock_hour) % 24
    except Exception:
        return False
    return ((y, mo) > tuple(after) and 3 <= mo <= 5 and 7 <= h < 12
            and _fair_weather(app))


def _watch_for_p5_spring_offer(app):
    """»Not just yet« to part 5: Abbot Cyril comes back next spring and
    asks again (the Fast Forward window suggests the days until then and a
    long Fast Forward stops there)."""
    _cancel_seedling_watch(app)
    try:
        after = (int(app.garden.year), int(app.garden.month))
    except Exception:
        after = (0, 0)
    if after[1] >= 3:
        after = (after[0], 12)                # not this spring any more: the next one
    app._tut_p5_offer_after = after

    def _ready():
        return _p5_offer_ready(app, after)

    def _days():
        import datetime as _dt
        import math as _m
        try:
            g = app.garden
            now = _dt.datetime(int(g.year), int(g.month), int(g.day_of_month), int(g.clock_hour) % 24)
            tgt = _dt.datetime(after[0] + 1 if after[1] >= 3 else after[0], 3, 1, 8)
            if tgt <= now:
                return 1
            return max(1, int(_m.ceil((tgt - now).total_seconds() / 86400.0)))
        except Exception:
            return 1
    app._ff_stop_check = _ready
    app._ff_suggest_days = _days

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        if _p5_step(app) > 0:
            return
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False) and _ready()):
            app._ff_stop_check = None
            app._ff_suggest_days = None
            _offer_next_lesson_after(app, delay_ms=0)
            return
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _begin_next_lesson(app):
    """Starts the next tutorial part: part 4 after part 3, part 5 after
    part 4 (the crossed pod harvested)."""
    if int(getattr(app, "_tutorial_cross_done", 0) or 0) >= 3:
        if _p5_step(app) == 0 and getattr(app, "_tutorial_dialogue", None) is None:
            _play_part_5(app)
        return
    nxt = globals().get("_play_part_4")
    if callable(nxt):
        nxt(app)
        return
    try:
        app._toast("Part 4 of the tutorial is still being prepared.", level="info")
    except Exception:
        pass


def _tutorial_seeds_left(app):
    try:
        return (int(getattr(app, "available_seeds", 0) or 0)
                + len(getattr(app, "harvest_inventory", []) or []))
    except Exception:
        return 0


def _ask_cyril_restart(app):
    """Abbot Cyril comes by when the garden is empty and the seed bags
    too, and offers to start this part of the tutorial again. True = yes."""
    return _cyril_ask(
        app,
        "\u201cGregor... not a single pea left, neither in the beds nor in your "
        "pockets! Even the weevils have packed up and gone home.\u201d",
        "\u201cShall we start this part of the tutorial again?\u201d",
        "Yes, start again", "Not now")


def _cyril_ask(app, text, question, yes_text, no_text, portrait="franz_1.png"):
    """A small window with Abbot Cyril asking something; True = yes."""
    import tkinter as tk
    BG = getattr(app, "INSPECTOR_BG", "#f5f0e6")
    INK = "#3b2a1a"
    answer = {"yes": False}
    win = tk.Toplevel(app.root)
    win.withdraw()
    win.title("Abbot Cyril")
    win.configure(bg=BG)
    win.resizable(False, False)
    try:
        win.attributes("-topmost", True)
        win.transient(app.root)
    except Exception:
        pass
    outer = tk.Frame(win, bg=BG, padx=22, pady=18)
    outer.pack(fill="both", expand=True)
    row = tk.Frame(outer, bg=BG)
    row.pack(fill="x")
    try:
        from PIL import Image, ImageTk
        for fn in (portrait, "franz_1.png", "franz.png", "franz_2.png"):
            pth = os.path.join(ICONS_DIR, fn)
            if os.path.isfile(pth):
                pil = Image.open(pth).convert("RGBA")
                pil.thumbnail((150, 220), Image.LANCZOS)
                img = ImageTk.PhotoImage(pil)
                lbl = tk.Label(row, image=img, bg=BG)
                lbl.image = img
                lbl.pack(side="left", padx=(0, 16), anchor="n")
                break
    except Exception:
        pass
    col = tk.Frame(row, bg=BG)
    col.pack(side="left", fill="both", expand=True)
    tk.Label(col, text="Abbot Cyril", font=("Segoe UI", 10, "italic"), bg=BG,
             fg="#6b5a44").pack(anchor="w")
    tk.Label(col, text=text,
             font=("Segoe UI", 12), bg=BG, fg=INK, wraplength=340,
             justify="left").pack(anchor="w", pady=(2, 8))
    tk.Label(col, text=question,
             font=("Segoe UI", 12, "bold"), bg=BG, fg=INK, wraplength=340,
             justify="left").pack(anchor="w")
    bar = tk.Frame(outer, bg=BG)
    bar.pack(fill="x", pady=(14, 0))

    def _choose(v):
        answer["yes"] = v
        try:
            win.destroy()
        except Exception:
            pass

    for btext, val, bg, fg in ((yes_text, True, "#7A9A3C", "white"),
                               (no_text, False, "#e0dccf", "#333333")):
        b = tk.Label(bar, text=btext, font=("Segoe UI", 11, "bold"), bg=bg, fg=fg,
                     padx=14, pady=6, cursor="hand2")
        b.pack(side="right", padx=(8, 0))
        _click(None, b, lambda v=val: (_click_sound(), _choose(v)))
    win.protocol("WM_DELETE_WINDOW", lambda: _choose(False))
    win.bind("<Escape>", lambda e: _choose(False))
    try:
        app._center_on_screen(win)
    except Exception:
        pass
    win.deiconify()
    try:
        win.lift()
        win.grab_set()
    except Exception:
        pass
    app.root.wait_window(win)
    return answer["yes"]


def _offer_restart_after_loss(app):
    was_running = bool(getattr(app, "running", True))
    app.running = False
    try:
        yes = _ask_cyril_restart(app)
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


# ---- Fast Forward: the window suggests the days to the next event ----------

def _days_to_stage(p, stage):
    """Whole days until plant p reaches `stage` (0 if it has), from its own
    pace, health and germination delay — as plant.advance_growth works."""
    import math as _m
    try:
        if int(p.stage) >= stage:
            return 0
        th = p.stage_thresholds()
        hf = 0 if p.health > 70 else (1 if p.health > 40 else 2)
        need = (th[stage] + hf + float(getattr(p, "germination_delay", 0) or 0)
                - float(p.days_since_planting))
        return max(0, int(_m.ceil(need)))
    except Exception:
        return None


def _days_until_n_at(plants, stage, n=1):
    """Days until n of these plants are at `stage` (None if they can't be)."""
    ds = sorted(d for d in (_days_to_stage(p, stage) for p in plants
                            if getattr(p, "alive", True)) if d is not None)
    if len(ds) < max(1, n):
        return None
    return ds[max(1, n) - 1]


def _suggest_ff(app, days_fn):
    """The Fast Forward window's number: the days to the next event (+1,
    as Cyril comes in the morning; a longer Fast Forward stops there by
    itself). Nothing to work out: it suggests the usual 3."""
    def _sug():
        d = days_fn()
        if d is None:
            raise ValueError("no estimate")
        return max(1, int(d) + 1)
    app._ff_suggest_days = _sug


def _watch_for_seedlings(app):
    """Polls once a second (while the tutorial is active and no dialogue
    is showing) for the moment all plants are seedlings, then plays part 2.
    Also refreshes the progress save every couple of minutes."""
    _cancel_seedling_watch(app)
    state = {"ticks": 0}
    _suggest_ff(app, lambda: _days_until_n_at(_living_plant_list(app), 2,
                                              max(1, len(_living_plant_list(app)))))

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
        _award_tutorial_part(app, 2)
        _watch_for_budding(app)

    _StatusBarDialogue(app, LECTURE_2_DIALOGUE, on_finish=_done)


_PLANTS_FOR_NEXT_PART = 3     # this many plants at a stage bring Cyril back
# ...except for the buds: Cyril comes for "the first buds" — with three,
# the earliest plants could already be in flower by then (their pace
# differs by days), and his talk about buds no longer fitted.
_PLANTS_FOR_STAGE = {4: 1}


def _any_at_stage(app, stage):
    """Is any living plant at `stage` or beyond?"""
    try:
        return any(t.plant is not None and getattr(t.plant, "alive", True)
                   and int(t.plant.stage) >= stage for t in app._all_plot_tiles())
    except Exception:
        return False

# After part N is done: (growth stage the plants must reach, next part).
# 4 budding, 5 flowering, 6 pods forming, 7 mature pods (see plant.STAGE_NAMES).
_STAGE_PARTS = {
    2: (4, 3),
    3: (5, 4),
    4: (6, 5),
    5: (7, 6),
}


# Extra days a plant must already be in a stage before it counts — young
# pods are hard to see on their first day, so Cyril waits a little.
_STAGE_EXTRA_DAYS = {6: 0.5}


def _days_in_stage(plant):
    """Game days this plant has been in its current stage."""
    try:
        from plant import get_lifecycle_settings
        th = (plant.stage_thresholds() if hasattr(plant, "stage_thresholds") else get_lifecycle_settings(getattr(plant, "difficulty", "off"))["base_thresholds"])
        st = int(plant.stage)
        eff = (float(getattr(plant, "days_since_planting", 0) or 0)
               - float(getattr(plant, "germination_delay", 0) or 0))
        return max(0.0, eff - th[st])
    except Exception:
        return 99.0


def _counts_for_stage(plant, stage):
    st = int(plant.stage)
    if st > stage:
        return True
    return st == stage and _days_in_stage(plant) >= _STAGE_EXTRA_DAYS.get(stage, 0.0)


def _enough_at_stage(app, stage):
    """True once at least _PLANTS_FOR_NEXT_PART living plants have reached
    `stage` (or further) — for pods, and been there half a day."""
    try:
        n = sum(1 for t in app._all_plot_tiles()
                if t.plant is not None and getattr(t.plant, "alive", True)
                and _counts_for_stage(t.plant, stage))
        return n >= _PLANTS_FOR_STAGE.get(stage, _PLANTS_FOR_NEXT_PART)
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
    state = {"saved": time.monotonic()}
    _suggest_ff(app, lambda: _days_until_n_at(
        _living_plant_list(app), stage, _PLANTS_FOR_STAGE.get(stage, _PLANTS_FOR_NEXT_PART)))

    def _ready():
        # Cyril only comes by in the morning (7:00-11:59), even if the
        # plants got there earlier.
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        # (the harvest lesson, part 6: on a dry morning)
        return (7 <= hour < 12 and _enough_at_stage(app, stage)
                and (nxt != 6 or _fair_weather(app)))

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
            if time.monotonic() - state["saved"] >= 120:     # every couple of minutes
                state["saved"] = time.monotonic()
                _save_tutorial_progress(app, part_done)
        app._tutorial_seedling_job = app.root.after(_poll_ms(), _check)

    def _poll_ms():
        # Once a game hour at least: a second at a time missed Cyril's
        # morning (7-12) for days at the fast speeds, while the plants
        # grew on past the stage he comes to talk about.
        try:
            per_hour = float(getattr(app, "day_length_s", 1.0) or 1.0) * 1000.0
        except Exception:
            per_hour = 1000.0
        return int(max(80, min(1000, per_hour * 0.5)))

    app._tutorial_seedling_job = app.root.after(_poll_ms(), _check)


_SENESCENT_FOR_PART_4 = 3     # this many old (senescent) plants start part 4


def _living_plant_list(app):
    try:
        return [t.plant for t in app._all_plot_tiles()
                if t.plant is not None and getattr(t.plant, "alive", True)]
    except Exception:
        return []


def _senescent_needed(app):
    """3 old plants (or all of them, if fewer are growing)."""
    return max(1, min(_SENESCENT_FOR_PART_4, len(_living_plant_list(app))))


def _enough_senescent(app):
    plants = _living_plant_list(app)
    if not plants:
        return False
    n = sum(1 for p in plants if getattr(p, "senescent", False))
    return n >= _senescent_needed(app)


def _days_until_ageing(app):
    """Game days until enough plants are senescent (they turn old 10 days
    before their maximum age — see garden.py)."""
    left = []
    for p in _living_plant_list(app):
        if getattr(p, "senescent", False):
            left.append(0)
            continue
        try:
            left.append(max(0, int(p.max_age_days) - 10 - int(p.days_since_planting)))
        except Exception:
            pass
    if not left:
        return 0
    left.sort()
    return left[min(len(left), _senescent_needed(app)) - 1] + 1


def _keep_sun_until_tomorrow(app):
    """Clear sky for the rest of today (the sunny sowing morning Cyril
    promised); the real weather comes back the next morning."""
    try:
        day0 = int(getattr(app.garden, "day", 0) or 0)
        app.garden.weather_lock = "\u2600\ufe0f"
    except Exception:
        return

    def _tick():
        try:
            if (not getattr(app, "_tutorial_active", False)
                    or int(getattr(app.garden, "day", 0) or 0) != day0):
                if getattr(app.garden, "weather_lock", None) == "\u2600\ufe0f":
                    app.garden.weather_lock = None
                    app.render_all()
                return
            app.root.after(2000, _tick)
        except Exception:
            pass
    app.root.after(2000, _tick)


def _play_cyril_visit(app, dialogue, after=None, stay_real_time=False):
    """Cyril comes by, says `dialogue`, and leaves again (like the stage
    lectures, without saving a part). stay_real_time: the clock stays in
    real time after he leaves (and today stays sunny)."""
    app._tutorial_portrait_free = False      # Cyril is back
    _swap_portrait_for_tutorial(app)
    _lock_down_sidebar(app)
    _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)   # real time while Cyril talks
    _lock_sun_weather(app)

    def _done():
        if stay_real_time:
            _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)
            _release_sun(app)
            _keep_sun_until_tomorrow(app)
        else:
            _tutorial_set_speed(app, 1.0)        # back to 1 sec = 1 hour
            _release_sun(app)
        _unlock_sidebar(app)
        _cyril_leaves(app)
        if after is not None:
            try:
                after()
            except Exception:
                pass

    _StatusBarDialogue(app, dialogue, on_finish=_done)


def _play_ageing_lecture(app):
    app._ff_stop_check = None
    # Part 4's start on the tutorial map ("Restart" goes back here).
    try:
        _save_tutorial_progress(app, max(6, int(getattr(app, "_tutorial_part_done", 6) or 6)),
                                path=_part_start_path(_MAP_PART_STEPS[4][0]))
    except Exception:
        pass
    app._tutorial_ageing_seen = True
    app._ff_suggest_days = lambda: _days_until_spring(app)   # FF window: days to spring
    app._ff_stop_check = lambda: _reached_spring(app)        # FF stops on 1 March
    _play_cyril_visit(app, LECTURE_AGEING_DIALOGUE, after=lambda: _watch_for_spring(app))


# The tutorial always begins on 1 April 1856 at 8:00 (see the garden reset
# in start_tutorial); part 4 goes on the next spring, on the first day the
# tutorial allows sowing again (March to May — see GardenApp.
# _season_gate_sowing): 1 March 1857, 8:00.
_TUTORIAL_START_DATE = (1856, 4, 1, 8)
_SOWING_OPENS = (3, 1)          # (month, day) the sowing season begins


def _spring_target():
    y, _m, _d, h = _TUTORIAL_START_DATE
    return (y + 1, _SOWING_OPENS[0], _SOWING_OPENS[1], h)


def _days_until_spring(app):
    """Whole days of Fast Forward from now until Cyril's spring visit
    (1 March, 8:00, when sowing may begin again) — at least 1."""
    import datetime as _dt
    import math as _m
    try:
        g = app.garden
        now = _dt.datetime(int(g.year), int(g.month), int(g.day_of_month),
                           int(g.clock_hour) % 24)
        y, mo, d, h = _spring_target()
        hours = (_dt.datetime(y, mo, d, h) - now).total_seconds() / 3600.0
        return max(1, int(_m.ceil(hours / 24.0)))
    except Exception:
        return 1


def _reached_spring(app):
    try:
        g = app.garden
        now = (int(g.year), int(g.month), int(g.day_of_month), int(g.clock_hour) % 24)
    except Exception:
        return False
    return now >= _spring_target()


def _watch_for_spring(app):
    """After the ageing talk: Cyril returns when the sowing season opens
    again. A Fast Forward stops exactly then (1 March 1857, 8:00)."""
    _cancel_seedling_watch(app)
    if getattr(app, "_tutorial_spring_seen", False):
        return
    app._ff_stop_check = lambda: _reached_spring(app)
    app._ff_suggest_days = lambda: _days_until_spring(app)

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False)
                and _reached_spring(app)):
            app._ff_stop_check = None
            app._ff_suggest_days = None
            app._tutorial_spring_seen = True
            app._tut_no_sowing = True        # until the sunny morning (see the visit)
            _true_breed_flower_colour(app)   # white x purple must work out
            _play_cyril_visit(app, LECTURE_SPRING_DIALOGUE,
                              after=lambda: _finish_part_4(app), stay_real_time=True)
            return
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _finish_part_4(app):
    """Spring is back (the prelude of »Crossing« is over): saves, then
    Cyril's first crossing visit."""
    pd = max(6, int(getattr(app, "_tutorial_part_done", 6) or 6))
    try:
        _save_tutorial_progress(app, pd)
        _save_checkpoint(app, pd)
    except Exception:
        pass
    _watch_for_cross_visit(app, 1)


def _plot_of(app, plant):
    """Index of the garden (plot) a plant grows in, or None."""
    try:
        for pi, tiles in enumerate(getattr(app, "_plot_tiles", []) or []):
            if any(getattr(t, "plant", None) is plant for t in tiles):
                return pi
    except Exception:
        pass
    return None


def _father_candidate(app, mother, strict=False):
    """(plant, k): a flower of another plant whose anthers are ripe right
    now — or, if none is, an open flower with anthers that can be made
    ripe for the lesson (see _pick_tutorial_father). None if no other
    plant has an open flower with anthers."""
    ripe, other = None, None
    plot = _plot_of(app, mother) if mother is not None else None
    # a father of the other flower colour (purple for the white mother);
    # only if there is none, any other plant
    mcol = _flower_colour(mother) if mother is not None else ""
    plants = _living_plant_list(app)
    pref = [p for p in plants if mcol and _flower_colour(p) and _flower_colour(p) != mcol]
    for group in ((pref,) if strict else (pref, plants)):
        r = _father_from(app, mother, plot, group)
        if r is not None:
            return r
    return None


def _contrast_may_flower(app, mother):
    """Does a plant of the other flower colour grow in the mother's garden
    that has (or will have) a flower with anthers?"""
    mcol = _flower_colour(mother)
    plot = _plot_of(app, mother)
    for p in _living_plant_list(app):
        if p is mother or not _flower_colour(p) or _flower_colour(p) == mcol:
            continue
        if plot is not None and _plot_of(app, p) != plot:
            continue
        try:
            if int(getattr(p, "stage", 0) or 0) < 4:
                return True                 # not flowering yet
            if any(st in ("bud", "open", "not yet") and not _hand_emasc(f) and _has_anthers(f)
                   for _k, st, f in _flower_info(app, p)):
                return True
        except Exception:
            pass
    return False


def _father_from(app, mother, plot, plants):
    ripe, other = None, None
    for p in plants:
        if p is mother:
            continue
        # only in the mother's own garden (switching between the gardens
        # confused the lesson)
        if plot is not None and _plot_of(app, p) != plot:
            continue
        try:
            if not p.can_collect_pollen()[0]:
                continue
        except Exception:
            continue
        for k, st, f in _flower_info(app, p):
            if st != "open" or _hand_emasc(f) or not _has_anthers(f):
                continue
            if ripe is None and _anthers_ripe_now(app, p, k, st, f):
                ripe = (p, k)
            if other is None:
                other = (p, k)
    return ripe or other


def _pick_tutorial_father(app):
    """Crossing visit 2: Cyril picks the father himself — a plant with a
    flower whose pollen is ripe right now (if none is ripe today, that
    flower's anthers are made ripe for the lesson), so the player is led
    straight to it instead of searching. The garden it grows in is shown."""
    app._tut_father = None
    app._tut_ripe_override = None
    cand = None
    # a mother with a father of the other flower colour in her garden —
    # only if there is none at all, any other father
    for strict in (True, False):
        for m in _cross_mothers(app):
            cand = _father_candidate(app, m, strict=strict)
            if cand is not None:
                break
        if cand is not None:
            break
    if cand is None:
        return None
    p, k = cand
    try:
        f = p.ensure_flowers()[k]
        if not app._flower_anthers_ready(p, k):
            app._tut_ripe_override = (getattr(p, "id", None), int(f.get("i", k + 1)), app._today())
    except Exception:
        pass
    app._tut_father = (getattr(p, "id", None), k)
    # mother and father grow in the same garden: show that one
    try:
        pi = _plot_of(app, p)
        if pi is not None and pi != getattr(app, "active_plot_index", 0):
            app._switch_to_plot(pi)
    except Exception:
        pass
    return cand


def _tut_father_plant(app):
    fa = getattr(app, "_tut_father", None)
    if not fa:
        return None, None
    for p in _living_plant_list(app):
        if getattr(p, "id", None) == fa[0]:
            return p, fa[1]
    return None, None


def _father_cell(app):
    """The inspector's cell of the flower Cyril chose (when the father is shown)."""
    try:
        p, k = _tut_father_plant(app)
        pid, st = getattr(app, "_inspector_flower_panel_st", None) or (None, None)
        sel = _selected_living_plant(app)
        if p is None or sel is not p or not st or pid != getattr(p, "id", None):
            return []
        cell = (st.get("cells") or {}).get(k)
        cell = cell[0] if isinstance(cell, (list, tuple)) else cell
        return [cell] if _live_widget(cell) is not None else []
    except Exception:
        return []


def _cross_visit_ready(app, n):
    """Is the garden ready for visit n of part 5 (see LECTURE_CROSS_*)?"""
    if n == 1:          # a bud that can still be emasculated
        for p, _k, st, f in _all_flowers(app):
            try:
                if st == "bud" and not _hand_emasc(f) and p.can_emasculate()[0]:
                    return True
            except Exception:
                pass
        return False
    if n == 2:          # the emasculated flower is open, and a father can give pollen
        mothers = _cross_mothers(app)
        if any(_father_candidate(app, m, strict=True) is not None for m in mothers):
            return True
        # a father of the same colour only when no plant of the other
        # colour in her garden is going to flower any more
        return any(_father_candidate(app, m) is not None and not _contrast_may_flower(app, m)
                   for m in mothers)
    # (or the player picked the crossed pod himself already)
    return _crossed_pod_ripe(app) or _crossed_pod_harvested(app)


_CROSS_DIALOGUES = {1: "LECTURE_CROSS_1_DIALOGUE", 2: "LECTURE_CROSS_2_DIALOGUE",
                    3: "LECTURE_CROSS_3_DIALOGUE"}


def _watch_for_cross_visit(app, n):
    """Part 5: waits (once a second) until the garden is ready for Cyril's
    visit n, then he comes (in the morning, 7:00-11:59). A long Fast
    Forward stops right there."""
    _cancel_seedling_watch(app)
    if n > 3 or int(getattr(app, "_tutorial_cross_done", 0) or 0) >= n:
        return

    def _cross_days():
        living = _living_plant_list(app)
        if n == 1:                    # a bud on a plant of the mother's colour
            mc = _tut_mother_colour(app)
            pool = [p for p in living if not mc or _flower_colour(p) in (mc, None)] or living
            return _days_until_n_at(pool, 4, 1)
        emasc = [p for p in living
                 if any(_hand_emasc(f) for f in (p.ensure_flowers() or []))]
        if n == 2:                    # the emasculated flower opens
            return _days_until_n_at(emasc or living, 5, 1)
        return _days_until_n_at(emasc or living, 7, 1)     # the crossed pod ripens
    _suggest_ff(app, _cross_days)

    def _ready():
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        # (visit 3 is the harvest of the crossed pod: on a dry morning)
        return 7 <= hour < 12 and _cross_visit_ready(app, n) and (n != 3 or _fair_weather(app))

    # (a long Fast Forward also stops when the cross is lost / done early)
    app._ff_stop_check = lambda: _ready() or _cross_rescue(app, n) is not None

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False)):
            if _ready():
                app._ff_stop_check = None
                _play_cross_visit(app, n)
                return
            rescue = _cross_rescue(app, n)
            if rescue is not None:
                app._ff_stop_check = None
                _play_cross_rescue(app, rescue)
                return
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _cross_waiting_flower(app):
    """A hand-emasculated flower (bud or open) still waiting for pollen."""
    for _p, _k, st, f in _all_flowers(app):
        if st in ("bud", "open") and _hand_emasc(f) and not f.get("pollen"):
            return True
    return False


def _cross_pollinated(app):
    """A crossed flower (emasculated, pollinated, not harvested) whose pod is
    still coming or ripe."""
    for p, _k, st, f in _all_flowers(app):
        try:
            if (_hand_emasc(f) and f.get("pollen") and not f.get("harvested")
                    and (st in ("bud", "open") or p.flower_sets_pod(f))):
                return True
        except Exception:
            pass
    return False


def _no_bud_coming(app):
    """Visit 1 waits for a bud to emasculate: True when none is left and
    none will come (every plant past its buds, or no plant at all) — e.g.
    after a long Fast Forward."""
    for p in _living_plant_list(app):
        try:
            if int(getattr(p, "stage", 0) or 0) < 4:
                return False                    # still to bud
        except Exception:
            return False
        for _k, st, f in _flower_info(app, p):
            if st in ("bud", "not yet") and not _hand_emasc(f):
                return False
    return True


def _fresh_both_sown(app):
    """Both flower colours growing among young plants (not yet budding) —
    the fresh sowing after "nobuds". A colour without seeds left is
    handed over once by Cyril."""
    young = {_flower_colour(p) for p in _living_plant_list(app)
             if not _is_cross_child(p) and int(getattr(p, "stage", 0) or 0) < 4}
    if {"white", "purple"} <= young:
        return True
    try:
        need = [c for c in _missing_seed_colours(app) if c not in young]
        if need and not getattr(app, "_tut_gave_fresh_colours", False):
            app._tut_gave_fresh_colours = True
            _give_colour_seeds(app, only=need)
    except Exception:
        pass
    return False


def _cross_rescue(app, n):
    """Visit n can no longer come as planned: "lost" (the prepared flower or
    the crossed pod is gone: back to visit 1, a fresh bud), "done" (the
    player pollinated it himself before visit 2: on to visit 3), "nobuds"
    (visit 1: no bud left and none coming — a fresh sowing), else None."""
    if n == 1 and _no_bud_coming(app):
        return "nobuds"
    if n == 2:
        if _cross_pollinated(app):
            return "done"
        if not _cross_waiting_flower(app):
            return "lost"
    if n == 3 and not _cross_pollinated(app) and not _crossed_pod_harvested(app):
        return "lost"
    return None


LECTURE_CROSS_LOST_DIALOGUE = [
    ("Cyril", "Gregor, the flower we prepared for our cross is lost.",
     {"pause": True}),
    ("Cyril", "Never mind, it happens to every gardener. We shall start again with a fresh bud.",
     {"mood": 2, "highlight_words": ["start again with a fresh bud"], "pause": True}),
]

LECTURE_CROSS_NOBUDS_DIALOGUE = [
    ("Cyril", "Gregor, the buds have all opened already: there is no bud left to prepare "
     "for our cross.",
     {"pause": True}),
    ("Cyril", "Never mind. Sow a few fresh seeds of both colors, white- and purple-flowering, "
     "and I shall come back when their first buds appear.",
     {"mood": 2, "highlight_words": ["fresh seeds", "white-", "purple-flowering"],
      "highlight_target": "plant_button", "unlock_buttons": ["plant_seeds_btn"],
      "pause": True, "no_skip": True, "wait_for_condition": "fresh_both_sown"}),
    ("Cyril", "Good. Call me when they begin to bud.",
     {"mood": 2, "auto_advance_ms": 4000}),
]

LECTURE_CROSS_SELF_DIALOGUE = [
    ("Cyril", "You have pollinated it already, Gregor? Splendid!",
     {"mood": 2, "pause": True}),
    ("Cyril", "Now we wait until its pod is ripe. I shall come back then.",
     {"highlight_words": ["until its pod is ripe"], "pause": True}),
]


def _play_cross_rescue(app, kind):
    if kind == "nobuds":
        dialogue, nxt, done = LECTURE_CROSS_NOBUDS_DIALOGUE, 1, 0
        app._tut_no_sowing = False
        app._tut_sow_any_season = True        # (whatever the month now is)
        app._tut_gave_fresh_colours = False
    elif kind == "lost":
        dialogue, nxt, done = LECTURE_CROSS_LOST_DIALOGUE, 1, 0
    else:
        dialogue, nxt, done = LECTURE_CROSS_SELF_DIALOGUE, 3, 2

    def _after():
        app._tutorial_cross_done = done
        try:
            _pd = max(6, int(getattr(app, "_tutorial_part_done", 6) or 6))
            _save_tutorial_progress(app, _pd)
            _save_checkpoint(app, _pd)
        except Exception:
            pass
        _watch_for_cross_visit(app, nxt)
    _play_cyril_visit(app, dialogue, after=_after)


def _play_cross_visit(app, n):
    dialogue = globals()[_CROSS_DIALOGUES[n]]
    if n == 3 and _crossed_pod_harvested(app) and not _crossed_pod_ripe(app):
        # the player picked the crossed pod himself already: no picking lesson
        try:
            i = next(j for j, l in enumerate(dialogue) if "whose flower color" in str(l[1]))
            dialogue = [
                ("Cyril", "You have picked the pod of your cross already, Gregor? Good: its "
                 "seeds are the first children (F1) of your own cross.",
                 {"mood": 2, "highlight_words": ["first children (F1)"], "pause": True}),
            ] + list(dialogue[i:])
        except StopIteration:
            pass

    def _after():
        app._tut_hold_morning = False
        app._tutorial_cross_done = n
        try:
            _pd = max(6, int(getattr(app, "_tutorial_part_done", 6) or 6))
            _save_tutorial_progress(app, _pd)
            _save_checkpoint(app, _pd)        # restart point after each visit
        except Exception:
            pass
        if n < 3:
            _watch_for_cross_visit(app, n + 1)
            return
        app._tut_insp_sections = None        # the player's own inspector sections again
        app._tut_tie_sections = None         # the player's own TIE sections again
        # Part 5's save point: the garden as it is when Cyril first asks.
        # »Continue« (or a restart of part 5) goes back to this day, even
        # if the player said »Not just yet« and the year went on.
        try:
            _save_tutorial_progress(app, max(6, int(getattr(app, "_tutorial_part_done", 6) or 6)),
                                    path=_part_start_path(_MAP_PART_STEPS[5][0]))
        except Exception:
            pass
        win = _award_tutorial_part(app, 5)
        _offer_next_lesson_after(app, win)   # part 5

    # Clear sky and working hours for the whole visit: rain or the evening
    # must not stop the emasculation or the pollination (released again
    # when Cyril leaves, see _play_cyril_visit).
    app._tutorial_keep_hours = False         # clear sky, but the clock runs on
    # visit 2: the morning lasts until the pollination is done (see _hold_morning)
    app._tut_hold_morning = (n == 2)
    app._tut_hold_morning_day = None
    if n == 2:
        _pick_tutorial_father(app)            # a plant whose pollen is ripe now
    _tutorial_force_sun(app)
    _start_sun_keeper(app)
    _play_cyril_visit(app, dialogue, after=_after)


# ============================================================================
# Part 5 — The Hidden Elements: the children of the cross (F1) and their
# children (F2), with the Genotype Viewer and the TIE.
#   step 0  Part 4 done; the player says yes to the next lesson
#   step 1  bridge talk done: the winter passes (Fast Forward to spring)
#   step 2  spring: the crossed seeds (F1) sown
#   step 3  visit 1, the F1 in bloom
#   step 4  visit 2, the F1 pods ripe: the TIE, then the Genotype Viewer
#   step 5  spring: the F1 seeds (F2) sown
#   step 6  visit 3, the F2 in bloom (white again): ratios,
#           revealing the alleles — the end of the tutorial
# ============================================================================
def _is_cross_child(p):
    """A plant grown from a crossed seed (two different parents)."""
    try:
        m, f = getattr(p, "mother_id", None), getattr(p, "father_id", None)
        return m not in (None, "", -1) and f not in (None, "", -1) and str(m) != str(f)
    except Exception:
        return False


def _archive_snap(app, pid):
    try:
        plants = (getattr(app, "archive", {}) or {}).get("plants", {}) or {}
        return plants.get(str(pid)) or plants.get(pid)
    except Exception:
        return None


def _is_f2(app, p):
    """A plant grown from a selfed seed of a crossed plant (F1)."""
    try:
        m, f = getattr(p, "mother_id", None), getattr(p, "father_id", None)
        if m in (None, "", -1) or (f not in (None, "", -1) and str(m) != str(f)):
            return False
        for q in _living_plant_list(app):
            if str(getattr(q, "id", "")) == str(m):
                return _is_cross_child(q)
        s = _archive_snap(app, m)
        if isinstance(s, dict):
            mm, ff = s.get("mother_id"), s.get("father_id")
            return mm not in (None, "", -1) and ff not in (None, "", -1) and str(mm) != str(ff)
    except Exception:
        pass
    return False


def _f1_plants(app):
    return [p for p in _living_plant_list(app) if _is_cross_child(p)]


def _f2_plants(app):
    return [p for p in _living_plant_list(app) if _is_f2(app, p)]


def _f2_seeds_left(app):
    """Seeds in the bag that would grow into F2 plants."""
    ids = set()
    try:
        for p in [t.plant for t in app._all_plot_tiles() if t.plant is not None]:
            if _is_cross_child(p):
                ids.add(str(getattr(p, "id", "")))
        for k, s in ((getattr(app, "archive", {}) or {}).get("plants", {}) or {}).items():
            if isinstance(s, dict):
                mm, ff = s.get("mother_id"), s.get("father_id")
                if mm not in (None, "", -1) and ff not in (None, "", -1) and str(mm) != str(ff):
                    ids.add(str(k))
    except Exception:
        pass
    n = 0
    for sd in list(getattr(app, "harvest_inventory", []) or []):
        try:
            if str(sd.get("source_id")) in ids and sd.get("donor_id") in (None, "", sd.get("source_id")):
                n += 1
        except Exception:
            pass
    return n


def _f1_ripe_left(app):
    return sum(int(p.ripe_pods() or 0) for p in _f1_plants(app))


def _f1_harvested(app):
    """Every ripe pod of the crossed plants picked (at least one)."""
    try:
        any_h = any(f.get("harvested") for p in _f1_plants(app) for f in p.ensure_flowers())
    except Exception:
        any_h = False
    return any_h and _f1_ripe_left(app) == 0


def _is_white_f2(app, p):
    return p is not None and _is_f2(app, p) and _flower_colour(p) == "white"


def _ensure_white_f2(app):
    """The tutorial must show white coming back among the grandchildren.
    Each F2 plant is white only by a 1 in 4 chance, so with few plants
    there may be none (8 plants: about 1 in 10). If no growing F2 plant is
    white, one that has not shown its flower colour yet (no buds) is made
    white (aa) — nothing visible changes. False if that is not possible
    any more (every F2 plant has already shown purple)."""
    f2 = _f2_plants(app)
    if any(_flower_colour(p) == "white" for p in f2):
        return True
    hidden = [p for p in f2 if int(getattr(p, "stage", 0) or 0) < 4]
    if not hidden:
        return False
    p = hidden[-1]
    try:
        geno = getattr(p, "genotype", None)
        if isinstance(geno, dict):
            geno["A"] = ("a", "a")
        p.traits["flower_color"] = "white"
    except Exception:
        return False
    return True


def _f2_white_impossible(app):
    """Every F2 plant has shown purple: no white can come any more."""
    f2 = _f2_plants(app)
    return bool(f2) and not _ensure_white_f2(app)


def _f2_bloom_ready(app):
    """F2 plants flowering (flower colour shown) and a white one among them."""
    _ensure_white_f2(app)
    blooming = [p for p in _f2_plants(app) if int(getattr(p, "stage", 0) or 0) >= 5]
    # (white is recessive: it shows again whichever parent was white)
    return len(blooming) >= 3 and any(_flower_colour(p) == "white" for p in blooming)


def _tie(app):
    return _live_widget(getattr(app, "_tie_win", None))


def _tie_shows(app, test):
    t = _tie(app)
    if t is None:
        return False
    try:
        return bool(test(t))
    except Exception:
        return False


def _tie_tab(t):
    """The TIE's open view: 0 Pod Seeds, 1 Punnett Square, 2 Trait Ratio,
    -1 when none of them is open."""
    try:
        return t._active_tab()
    except Exception:
        return t.tie_notebook.index(t.tie_notebook.select())


def _tie_focus_white_f2(app):
    """If the TIE shows something other than a white-flowering grandchild
    (e.g. a purple sibling), Cyril switches it to one — a sibling of the
    plant shown when there is one. True if the TIE now shows one."""
    t = _tie(app)
    if t is None:
        return False
    cur = _tie_current(app)
    if _is_white_f2(app, cur):
        return True
    try:
        whites = [p for p in _f2_plants(app) if _is_white_f2(app, p)
                  and int(getattr(p, "stage", 0) or 0) >= 4 and getattr(p, "alive", True)]
    except Exception:
        whites = []
    if not whites:
        return False

    def _mom(p):
        return str(getattr(p, "seed_parent_id", None) or getattr(p, "mother_id", None))
    sib = [p for p in whites if cur is not None and _mom(p) == _mom(cur)]
    pick = (sib or whites)[0]
    try:
        t._render_pid(getattr(pick, "id", None))
        return True
    except Exception:
        return False


def _tie_current(app):
    t = _tie(app)
    if t is None:
        return None
    pid = getattr(t, "current_pid", None)
    for p in [tl.plant for tl in app._all_plot_tiles() if tl.plant is not None]:
        if str(getattr(p, "id", "")) == str(pid):
            return p
    return None


def _set_tie_tab(app, idx):
    _set_tie_sections(app, {"tab": int(idx)})


def _set_tie_sections(app, secs):
    """Opens / closes sections of the TIE (plant, archive, tree, tab) — kept
    for a TIE opened later in the same lesson."""
    cur = dict(getattr(app, "_tut_tie_sections", None) or {})
    cur.update(secs)
    app._tut_tie_sections = cur
    t = _tie(app)
    if t is not None:
        try:
            t.set_sections(**secs)
        except Exception:
            try:
                if secs.get("tab") is not None:
                    t.tie_notebook.select(int(secs["tab"]))
            except Exception:
                pass


# Next 1 March (8:00) after now — where the Fast Forward of a part 5
# winter stops.
def _p5_next_spring(app, month_day=None):
    """month_day: (month, day) — Part 5's springs begin on 1 April."""
    md = tuple(month_day or (4, 1))
    try:
        g = app.garden
        now = (int(g.year), int(g.month), int(g.day_of_month), int(g.clock_hour) % 24)
        y = now[0] if now < (now[0], md[0], md[1], 8) else now[0] + 1
        return (y, md[0], md[1], 8)
    except Exception:
        return _spring_target()


def _p5_days_to(app, target):
    import datetime as _dt
    import math as _m
    try:
        g = app.garden
        now = _dt.datetime(int(g.year), int(g.month), int(g.day_of_month), int(g.clock_hour) % 24)
        hours = (_dt.datetime(*target) - now).total_seconds() / 3600.0
        return max(1, int(_m.ceil(hours / 24.0)))
    except Exception:
        return 1


def _p5_reached(app, target):
    try:
        g = app.garden
        return (int(g.year), int(g.month), int(g.day_of_month), int(g.clock_hour) % 24) >= tuple(target)
    except Exception:
        return False


def _p5_winter_line(app):
    tgt = getattr(app, "_tut_p5_spring", None) or _p5_next_spring(app)
    return f"Let the winter pass: Fast Forward {_p5_days_to(app, tgt)} days, until next spring."


def _p5_arm_winter(app, month_day=None):
    """The next spring is where the Fast Forward stops (and what its
    window suggests)."""
    tgt = _p5_next_spring(app, month_day)
    app._tut_p5_spring = tgt
    app._ff_suggest_days = lambda: _p5_days_to(app, tgt)
    app._ff_stop_check = lambda: _p5_reached(app, tgt)


def _true_breed_flower_colour(app):
    """The tutorial's seeds and plants breed true for flower colour (AA
    purple, aa white) — so the cross of part 4 and part 5 always works
    out, also from gardens saved before this rule."""
    def _fix(geno, colour):
        try:
            if isinstance(geno, dict) and colour in ("purple", "white"):
                geno["A"] = ("A", "A") if colour == "purple" else ("a", "a")
        except Exception:
            pass
    for sd in list(getattr(app, "harvest_inventory", []) or []):
        try:
            d = sd.get("donor_id")
            if d not in (None, "", sd.get("source_id")):
                continue             # a crossed seed is meant to be mixed
            _fix(sd.get("genotype"), str((sd.get("traits") or {}).get("flower_color", "")).lower())
        except Exception:
            pass
    for p in _living_plant_list(app):
        if _is_cross_child(p):
            continue                 # a cross is meant to be mixed
        _fix(getattr(p, "genotype", None), _flower_colour(p))


def _p5_season_line(app):
    try:
        mo = int(app.garden.month)
    except Exception:
        mo = 7
    if 3 <= mo <= 5:
        return "Spring is just the right time to sow them."
    if 6 <= mo <= 8:
        return "And there is still time to sow them this summer."
    return "It is late in the year, but we shall sow them all the same."


LECTURE_P5_BRIDGE_DIALOGUE = [
    ("Cyril", "The seeds of your cross are safe in your seed bag, Gregor.",
     {"mood": 2, "highlight_words": ["seeds of your cross"], "pause": True}),
    # (the season it is: he may come back in spring, see _watch_for_p5_spring_offer)
    ("Cyril", lambda app: _p5_season_line(app),
     {"highlight_words": ["this summer", "right time", "all the same"], "pause": True}),
    ("Cyril", "But first, make room: your old plants have done their work.",
     {"highlight_words": ["make room"], "highlight_plants": "old", "pause": True}),
    ("Cyril", "Select several at once: drag across them with the mouse, or hold Shift and click each one.",
     {"highlight_words": ["drag across them", "hold Shift"], "highlight_plants": "old",
      "pause": True}),
    # Waits until »Remove plant« has cleared at least two plants at once.
    ("Cyril", ("One can also use ⌘ + A to select them all at once." if sys.platform == "darwin"
               else "One can also use Ctrl + A to select them all at once."),
     {"highlight_words": ["Ctrl + A", "⌘ + A"], "highlight_plants": "old", "pause": True}),
    ("Cyril", "Then press »Remove plant« or use “X” to clear them all together.",
     {"highlight_words": ["Remove plant", "X"], "highlight_target": "remove_button",
      "unlock_buttons": ["remove_btn"], "highlight_plants": "old",
      "pause": True, "no_skip": True, "wait_for_condition": "several_removed"}),
    ("Cyril", "Well done. Now there is room for the next generation.",
     {"mood": 2, "highlight_words": ["room for the next generation"]}),
    ("Cyril", "Now sow the seeds of your cross.",
     {"highlight_words": ["seeds of your cross"], "pause": True}),
    # Waits until »F1« is chosen in the Choose Seeds window.
    ("Cyril", "Your seed bag may hold many seeds by now.",
     {"pause": True}),
    ("Cyril", "Press »Plant«, open »Filter« and tick »F1« under »Seeds from crosses«: the first generation.",
     {"highlight_words": ["Plant", "Filter", "F1"], "highlight_target": "plant_button",
      "glow_targets": ["seed_cross_tick", "seed_crossed_cb"], "unlock_buttons": ["plant_seeds_btn"],
      "sow_gen_only": "F1",
      "pause": True, "no_skip": True, "wait_for_condition": "seed_filter_crossed"}),
    # Waits until a crossed seed (two different parents) has been sown.
    ("Cyril", "Now only the seeds of your cross are left. Sow them!",
     {"highlight_words": ["seeds of your cross"], "sow_gen_only": "F1",
      "pause": True, "no_skip": True, "wait_for_condition": "f1_sown"}),
    ("Cyril", "Sow any other seeds you like as well."),
    ("Cyril", "I shall come back when the young plants flower.",
     {"auto_advance_ms": 4000}),
]

LECTURE_P5_SPRING_1_DIALOGUE = [
    ("Cyril", "Spring is here, Gregor!",
     {"mood": 2, "highlight_words": ["Spring"], "pause": True}),
    ("Cyril", "Now sow the seeds of your cross.",
     {"highlight_words": ["seeds of your cross"], "pause": True}),
    # Waits until a crossed seed (two different parents) has been sown.
    ("Cyril", "You will find them in your seed bag, marked with both of their parents.",
     {"highlight_words": ["both of their parents"], "highlight_target": "plant_button",
      "unlock_buttons": ["plant_seeds_btn"], "pause": True, "no_skip": True,
      "wait_for_condition": "f1_sown"}),
    ("Cyril", "Sow any other seeds you like as well."),
    ("Cyril", "I shall come back when the young plants flower.",
     {"auto_advance_ms": 4000}),
]

LECTURE_P5_VISIT_1_DIALOGUE = [
    ("Mendel", "Cyril, the children of my cross are flowering!",
     {"portrait": "mendel", "highlight_words": ["children of my cross"],
      "highlight_plants": "f1", "pause": True}),
    ("Cyril", "Well done, Gregor!",
     {"mood": 2}),
    ("Mendel", lambda app: _f1_colour_line(app),
     {"portrait": "mendel", "highlight_words": ["all of them are purple", "Not a single white one"],
      "highlight_plants": "f1", "pause": True}),
    ("Cyril", lambda app: f"Where did the {_white_parent_word(app)}’s white go, I wonder?",
     {"highlight_words": ["mother’s white", "father’s white"]}),
    ("Mendel", "It seems to me that purple dominates over white.",
     {"portrait": "mendel", "highlight_words": ["dominates"], "pause": True}),
    ("Cyril", "Good observation, Gregor! But is the white really lost, or merely hidden?",
     {"mood": 2, "highlight_words": ["really lost, or merely hidden"], "pause": True}),
    ("Mendel", "Their seeds will tell us.",
     {"portrait": "mendel", "highlight_words": ["Their seeds"]}),
    ("Cyril", "Yes, when their pods are ripe, I shall show you how to keep track of all your crosses.",
     {"highlight_words": ["keep track"], "pause": True}),
    ("Cyril", "Until then, Gregor.",
     {"auto_advance_ms": 4000}),
]

LECTURE_P5_VISIT_2_DIALOGUE = [
    ("Mendel", "Cyril, the pods of the young plants are ripe.",
     {"portrait": "mendel", "highlight_words": ["ripe"], "highlight_plants": "f1_ripe", "pause": True}),
    # Waits until every ripe pod of the crossed plants is harvested.
    ("Cyril", "Then harvest them, every one.",
     {"highlight_words": ["harvest them"], "portrait": "mendel", "pause": True,
      "no_skip": True, "unlock_buttons": ["harvest_btn", "inspect_btn"],
      "highlight_plants": "f1_ripe", "wait_for_condition": "f1_harvested"}),
    ("Mendel", "But keeping track of them all will be a lot of work.",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "Indeed, but let me show you something.",
     {"mood": 2}),
    # The TIE is the player's from here on (also in the tutorial).
    ("Cyril", "Inspect one of the young plants once again and open the »TIE«.",
     {"highlight_words": ["TIE"], "highlight_target": "inspect_button",
      "glow_targets": ["inspector_tie_button"], "allow_tie": True,
      "tie_sections": {"plant": False, "archive": False, "tree": True, "tab": None},
      "portrait": "mendel", "pause": True, "no_skip": True,
      "highlight_plants": "f1", "wait_for_condition": "tie_open"}),
    ("Mendel", "The TIE?",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "The Trait Inheritance Explorer. Think of it as your family book of peas.",
     {"mood": 2, "highlight_words": ["Trait Inheritance Explorer"]}),
    ("Cyril", "Every plant you have grown is recorded here.",
     {"glow_targets": ["tie_list"], "tie_sections": {"archive": True}, "pause": True}),
    ("Cyril", "Look at the family tree: grandparents, parents and children, they will all be here.",
     {"highlight_words": ["family tree"], "glow_targets": ["tie_tree"],
      "tie_sections": {"archive": False}, "pause": True}),
    ("Cyril", "The buttons above choose which trait the pictures show.",
     {"glow_targets": ["tie_trait_buttons"], "pause": True}),
    ("Cyril", "Choose »Seed color«.",
     {"highlight_words": ["Seed color"], "glow_targets": ["tie_seed_color_btn"],
      "pause": True, "no_skip": True, "wait_for_condition": "tie_seed_color"}),
    # The player opens »Pod Seeds« himself (the first time it is shown).
    ("Cyril", "Now click »Pod Seeds«: there you can see each pod and its seeds.",
     {"highlight_words": ["Pod Seeds"], "glow_targets": ["tie_pods_btn"],
      "pause": True, "no_skip": True, "wait_for_condition": "tie_tab_pods"}),
    ("Cyril", "On the right, the seeds of all the pods are added up.",
     {"glow_targets": ["tie_total_ratio"], "pause": True}),
    ("Mendel", "So I no longer need to count every pea by hand!",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "Correct! Now you can spend more time studying the results.",
     {"mood": 2, "pause": True}),
    # — the Genotype Explorer (after the TIE) —
    ("Cyril", "There is one more window, Gregor. Close the TIE for now.",
     {"highlight_words": ["One more window"], "pause": True, "no_skip": True,
      "wait_for_condition": "tie_closed"}),
    # Waits until a crossed plant is shown in the inspection window.
    ("Cyril", "Select any of your plants again.",
     {"highlight_words": ["Select"], "highlight_target": "inspect_button",
      "portrait": "mendel", "pause": True, "no_skip": True, "skip_if": "any_inspected",
      "unlock_buttons": ["inspect_btn"], "wait_for_condition": "any_inspected"}),
    ("Cyril", "Now open the »Genotype Explorer« at the bottom.",
     {"highlight_words": ["Genotype Explorer"], "glow_targets": ["inspector_genotype_button"],
      "close_wildlife": True,
      "portrait": "mendel", "pause": True, "no_skip": True,
      "wait_for_condition": "genotype_viewer_open"}),
    ("Cyril", "Here every trait has its own row: the seven you spoke of at supper, Gregor.",
     {"mood": 2, "highlight_words": ["the seven you spoke of at supper"], "pause": True}),
    ("Mendel", "Seven traits, each in two clear forms. Those are the ones I want to study.",
     {"portrait": "mendel", "highlight_words": ["two clear forms"], "pause": True}),
    ("Cyril", "At the top are seed shape and color.",
     {"highlight_words": ["seed shape and color"]}),
    ("Mendel", "Those traits are always revealed first at harvest. This could prove quite useful to me.",
     {"portrait": "mendel", "highlight_words": ["first at harvest"], "pause": True}),
    ("Cyril", "I think so, too. The other traits only emerge as the plant matures."),
    ("Cyril", "A question mark means the plant has not shown you that trait yet.",
     {"highlight_words": ["question mark"], "pause": True}),
    ("Mendel", "And these dots, under »Alleles«?",
     {"portrait": "mendel", "highlight_words": ["Alleles"], "pause": True}),
    ("Cyril", "They stand for what no eye can see: the hidden elements inside the plant.",
     {"highlight_words": ["hidden elements"]}),
    ("Mendel", "One from the mother, one from the father, perhaps?",
     {"portrait": "mendel", "highlight_words": ["one from the father"], "pause": True}),
    ("Cyril", "That, Gregor, is for you to discover.",
     {"mood": 2, "highlight_words": ["for you to discover"]}),
    ("Cyril", "And it may keep you busy for some time.",
     {"mood": 2, "auto_advance_ms": 3000}),
    ("Cyril", "Close the window when you are done.",
     {"pause": True, "no_skip": True, "wait_for_condition": "genotype_viewer_closed"}),
    ("Cyril", "Now sow the seeds of your young plants.",
     {"highlight_words": ["sow the seeds of your young plants"], "pause": True}),
    # Waits until »F2« is chosen in the Choose Seeds window.
    ("Cyril", "Press »Plant«, open »Filter« and tick »F2«, the next generation.",
     {"highlight_words": ["Plant", "Filter", "F2"], "highlight_target": "plant_button",
      "glow_targets": ["seed_cross_tick", "seed_ofcross_cb"], "unlock_buttons": ["plant_seeds_btn"],
      "sow_gen_only": "F2",
      "pause": True, "no_skip": True, "wait_for_condition": "seed_filter_ofcross"}),
    # Waits until eight of them are sown (or the bag holds no more of them).
    ("Mendel", "How many?",
     {"portrait": "mendel"}),
    ("Cyril", "As many as you can! The more plants, the clearer the picture.",
     {"highlight_words": ["As many as you can"], "highlight_target": "plant_button",
      "unlock_buttons": ["plant_seeds_btn"], "sow_gen_only": "F2", "pause": True, "no_skip": True,
      "wait_for_condition": "f2_sown", "release_sun": True}),
    ("Cyril", "Before I go, Gregor: what do you think these grandchildren will look like?",
     {"highlight_words": ["what do you think"], "pause": True, "no_skip": True,
      "question": "f2_predict", "wait_for_condition": "question_answered"}),
    ("Cyril", lambda app: _predict_reply(app),
     {"mood": 2, "highlight_words": ["We shall see"]}),
    ("Cyril", "I shall come back when they flower.",
     {"auto_advance_ms": 4000}),
]

LECTURE_P5_SPRING_2_DIALOGUE = [
    ("Cyril", "Spring once more, Gregor!",
     {"mood": 2, "highlight_words": ["Spring"], "pause": True}),
    ("Cyril", "Now sow the seeds of your young plants.",
     {"highlight_words": ["seeds of your young plants"], "pause": True}),
    # Waits until eight of them are sown (or the bag holds no more of them).
    ("Cyril", "As many as you can! The more plants, the clearer the picture.",
     {"highlight_words": ["As many as you can"], "highlight_target": "plant_button",
      "unlock_buttons": ["plant_seeds_btn"], "pause": True, "no_skip": True,
      "wait_for_condition": "f2_sown"}),
    ("Cyril", "I shall come back when they flower.",
     {"auto_advance_ms": 4000}),
]

# Part 5: all the grandchildren have flowered purple (white comes only by
# a 1 in 4 chance): Cyril asks for more of them before visit 3.
LECTURE_P5_MORE_F2_DIALOGUE = [
    ("Cyril", "All your young plants flower purple, Gregor.",
     {"highlight_words": ["flower purple"], "pause": True}),
    ("Cyril", "Too few plants can hide what is there. Sow more of their seeds: »Plant«, "
     "»Filter«, »F2«.",
     {"highlight_words": ["Sow more of their seeds", "Filter", "F2"],
      "highlight_target": "plant_button", "sow_gen_only": "F2",
      "unlock_buttons": ["plant_seeds_btn"], "pause": True, "no_skip": True,
      "wait_for_condition": "f2_more_sown", "release_sun": True}),
    ("Cyril", "I shall come back when they flower.",
     {"auto_advance_ms": 4000}),
]

LECTURE_P5_VISIT_3_DIALOGUE = [
    ("Mendel", "Cyril! Look: white flowers have appeared again!",
     {"portrait": "mendel", "highlight_words": ["white flowers"], "pause": True}),
    # the white parent of the cross: grandmother or grandfather
    ("Mendel", lambda app: f"A few grandchildren bloom white, like their {_white_grandparent(app)}.",
     {"portrait": "mendel", "highlight_words": ["like their grandmother", "like their grandfather"],
      "pause": True}),
    ("Cyril", lambda app: _predict_verdict(app),
     {"mood": 2, "highlight_words": ["Just as you guessed", "the white is back"],
      "skip_if": "no_f2_prediction", "pause": True}),
    ("Cyril", "How peculiar! Perhaps the white flower was never truly lost.",
     {"mood": 2, "highlight_words": ["never truly lost"], "auto_advance_ms": 3000}),
    ("Cyril", "Open the »TIE« once more, for one of the white-flowering grandchildren.",
     {"highlight_words": ["TIE"], "highlight_target": "inspect_button",
      "glow_targets": ["inspector_tie_button"], "allow_tie": True,
      "tie_sections": {"plant": False, "archive": False, "tree": True, "tab": None},
      "tie_trait": "Seed shape",      # so »Flower color« is the player's own choice
      "portrait": "mendel", "pause": True, "no_skip": True, "tie_focus": "f2_white",
      "highlight_plants": "f2_white", "wait_for_condition": "tie_open_f2_white"}),
    ("Cyril", "Choose »Flower color«.",
     {"highlight_words": ["Flower color"], "glow_targets": ["tie_flower_color_btn"],
      "tie_trait": "",
      "pause": True, "no_skip": True, "wait_for_condition": "tie_flower_color"}),
    # Pod Seeds first, then another plant of the family tree: the pods (and
    # the crimson band in the tree) follow the plant that is picked
    ("Cyril", "Under »Pod Seeds« you see it among its brothers and sisters.",
     {"highlight_words": ["Pod Seeds"], "glow_targets": ["tie_pods"], "tie_tab": 0,
      "pause": True}),
    ("Cyril", "Now click another circle in the family tree, its mother for instance.",
     {"highlight_words": ["another circle"], "glow_targets": ["tie_tree"],
      "pause": True, "no_skip": True, "wait_for_condition": "tie_other_plant"}),
    ("Cyril", "See? The pods now show the family of the plant you picked.",
     {"glow_targets": ["tie_pods"], "pause": True}),
    ("Cyril", "Now click the white grandchild’s own circle again.",
     {"highlight_words": ["own circle"], "glow_targets": ["tie_tree"],
      "pause": True, "no_skip": True, "wait_for_condition": "tie_back"}),
    ("Cyril", "»Trait Ratio« counts its brothers and sisters for you.",
     {"highlight_words": ["Trait Ratio"], "glow_targets": ["tie_ratio_btn"],
      "pause": True, "no_skip": True, "wait_for_condition": "tie_tab_ratio"}),
    ("Cyril", "But first, count your grandchildren yourself, Gregor.",
     {"highlight_words": ["count your grandchildren yourself"], "pause": True, "no_skip": True,
      "question": "f2_ratio", "wait_for_condition": "question_answered"}),
    ("Cyril", lambda app: _ratio_reply(app),
     {"highlight_words": ["purple", "white"], "pause": True}),
    ("Mendel", lambda app: _ratio_mendel(app),
     {"portrait": "mendel", "highlight_words": ["to one"], "auto_advance_ms": 2000}),
    ("Cyril", lambda app: _ratio_moral(app),
     {"mood": 2, "highlight_words": ["three to one"], "pause": True}),
    ("Cyril", "Further down, all families of the same kind are counted together."),
    ("Cyril", "Useful once you raise several families from the same kind of cross.",
     {"highlight_words": ["several families"]}),
    ("Cyril", "That pooled ratio is what counts when you claim one of your laws.",
     {"highlight_words": ["pooled ratio"], "pause": True}),
    ("Mendel", "Then the pattern is in the numbers, if only I can grow enough plants.",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "Exactly. The more plants, the clearer your results will become.",
     {"mood": 2, "auto_advance_ms": 3000}),
    # — revealing the alleles —
    ("Cyril", "One more thing, Gregor.",
     {"pause": True}),
    ("Cyril", "Both windows, the Genotype Explorer and the TIE, have a button: »Reveal Genotype«.",
     {"highlight_words": ["Reveal Genotype"], "glow_targets": ["tie_reveal_button"],
      "pause": True}),
    ("Mendel", "Reveal the genotype? What would that show me?",
     {"portrait": "mendel", "pause": True}),
    ("Cyril", "Not sure. I guess the hidden elements inside the plant, written as letters.",
     {"highlight_words": ["hidden elements"]}),
    ("Cyril", "But something tells me it would save you years of counting!",
     {"pause": True}),
    ("Cyril", "And it would spoil everything.",
     {"auto_advance_ms": 3000}),
    ("Cyril", "Once you reveal the genotype, no law and no achievement can be won anymore.",
     {"highlight_words": ["no law and no achievement"], "pause": True}),
    # the reveal is shown on a white grandchild (aa, with Aa parents)
    # (Cyril switches the TIE to a white grandchild himself, should it
    # show a purple sibling now)
    ("Cyril", "But let me show you a white-flowering grandchild again.",
     {"highlight_words": ["white-flowering grandchild"], "tie_focus": "f2_white",
      "skip_if": "tie_open_f2_white",
      "pause": True, "no_skip": True, "wait_for_condition": "tie_open_f2_white"}),
    ("Cyril", "Here, in my practice garden, it does no harm. Try it.",
     {"highlight_words": ["Try it"], "glow_targets": ["tie_reveal_button"],
      "pause": True, "no_skip": True, "wait_for_condition": "genotype_revealed"}),
    ("Cyril", "Now tick »Show alleles« to see them on every plant in the family tree.",
     {"highlight_words": ["Show alleles"], "glow_targets": ["tie_show_alleles"],
      "pause": True, "no_skip": True, "wait_for_condition": "tie_show_alleles"}),
    ("Cyril", "The capital letter is the dominant trait, such as purple flower colour.",
     {"highlight_words": ["dominant"], "pause": True}),
    ("Mendel", "A over a... So the purple children carried the white all along!",
     {"portrait": "mendel", "highlight_words": ["carried the white all along"], "pause": True}),
    ("Cyril", "Remember it well. In your own garden you will have to find it out by pure "
     "observation and counting.",
     {"mood": 2, "highlight_words": ["observation and counting"], "pause": True}),
    ("Cyril", "And when you start from scratch, nothing promises you that your plants breed "
     "true either. You will have to find out which ones do.",
     {"highlight_words": ["breed true"], "pause": True}),
    ("Cyril", "That is all I can teach you. The rest, the peas will tell you themselves.",
     {"mood": 2, "pause": True}),
    ("Cyril", "But I shall not leave you without work.",
     {"mood": 2}),
    ("Cyril", "My tasks for you wait in the greenhouse, on the Monastery map.",
     {"highlight_words": ["greenhouse", "Monastery map"], "highlight_target": "monastery_button",
      "pause": True}),
    ("Cyril", "And when your counts prove a rule, claim it with »Unlock« next to the "
     "Mendelian laws, below the garden.",
     {"highlight_words": ["Unlock"], "highlight_target": "laws_button", "pause": True}),
    ("Cyril", "I have faith in you, Gregor. Good luck.",
     {"mood": 2, "auto_advance_ms": 5000}),
]

_TUTORIAL_PART_AWARDS[6] = (
    "tutorial_6", "The Hidden Elements",
    "Purple, then white again in the grandchildren — and now you know where "
    "to look. The rest, Gregor, the peas will tell you themselves.")


def _p5_step(app):
    return int(getattr(app, "_tutorial_p5", 0) or 0)


def _p5_set(app, step):
    app._tutorial_p5 = int(step)
    try:
        _pd = max(6, int(getattr(app, "_tutorial_part_done", 6) or 6))
        _save_tutorial_progress(app, _pd)
        _save_checkpoint(app, _pd)            # restart point after each step
    except Exception:
        pass


def _play_part_5(app):
    """The player said yes to the next lesson after part 4: part 5 begins
    (its start save is what the map's »Restart« goes back to)."""
    _cancel_seedling_watch(app)
    app._tutorial_p5 = 0
    try:
        _save_tutorial_progress(app, max(6, int(getattr(app, "_tutorial_part_done", 6) or 6)),
                                path=_part_start_path(_MAP_PART_STEPS[5][0]))
    except Exception:
        pass
    # No winter any more: the seeds of the cross are sown right away
    # (the tutorial's spring-only sowing rule is lifted for part 5).
    app._ff_suggest_days = None
    app._ff_stop_check = None
    app._tut_no_sowing = False
    app._tut_sow_any_season = True
    _true_breed_flower_colour(app)

    def _after():
        _p5_set(app, 2)          # (step 1, the spring sowing, is part of this visit now)
        _watch_p5(app)

    _play_cyril_visit(app, LECTURE_P5_BRIDGE_DIALOGUE, after=_after)


# step done -> (ready?, dialogue, morning only?, before playing)
def _p5_table(app):
    tgt = getattr(app, "_tut_p5_spring", None) or _p5_next_spring(app)
    return {
        1: (lambda: _p5_reached(app, tgt), LECTURE_P5_SPRING_1_DIALOGUE, False),
        2: (lambda: any(int(getattr(p, "stage", 0) or 0) >= 5 for p in _f1_plants(app)),
            LECTURE_P5_VISIT_1_DIALOGUE, True),
        3: (lambda: _f1_ripe_left(app) > 0, LECTURE_P5_VISIT_2_DIALOGUE, True),
        4: (lambda: _p5_reached(app, tgt), LECTURE_P5_SPRING_2_DIALOGUE, False),
        5: (lambda: _f2_bloom_ready(app), LECTURE_P5_VISIT_3_DIALOGUE, True),
    }


def _watch_p5(app):
    """Waits (once a second) for the next part 5 visit and plays it. A
    long Fast Forward stops right there."""
    _cancel_seedling_watch(app)
    step = _p5_step(app)
    if step >= 2:
        app._tut_sow_any_season = True      # part 5 sows in any season (also after loading)
    table = _p5_table(app)
    if step not in table:
        return
    ready, dialogue, morning = table[step]
    if step in (1, 4):
        tgt = getattr(app, "_tut_p5_spring", None)
        if tgt:
            app._ff_suggest_days = lambda: _p5_days_to(app, tgt)
    elif step == 2:                            # the F1 flowers
        _suggest_ff(app, lambda: _days_until_n_at(_f1_plants(app), 5, 1))
    elif step == 3:                            # the F1 pods ripen
        _suggest_ff(app, lambda: _days_until_n_at(_f1_plants(app), 7, 1))
    elif step == 5:                            # three grandchildren in flower
        _suggest_ff(app, lambda: _days_until_n_at(_f2_plants(app), 5, 3))

    def _ok():
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        # (step 3 is the harvest of the F1 pods: on a dry morning)
        return ((not morning or 7 <= hour < 12) and bool(ready())
                and (step != 3 or _fair_weather(app)))

    app._ff_stop_check = _ok

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False)):
            if _ok():
                app._ff_stop_check = None
                _play_p5_visit(app, step, dialogue)
                return
            # visit 3 waits for a white grandchild: if every one of them has
            # flowered purple and seeds are left, Cyril asks for more
            if step == 5 and _f2_white_impossible(app) and _f2_seeds_left(app) > 0:
                try:
                    app.fast_forward = False
                except Exception:
                    pass
                app._ff_stop_check = None
                app._tut_no_sowing = False
                app._tut_sow_any_season = True
                _play_cyril_visit(app, LECTURE_P5_MORE_F2_DIALOGUE, after=lambda: _watch_p5(app))
                return
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _play_p5_visit(app, step, dialogue):
    if step in (1, 4):
        app._ff_suggest_days = None
        app._tut_no_sowing = False
    if step == 1:
        _true_breed_flower_colour(app)
    if step == 3:
        app._tut_allow_tie = True
        # the F2 seeds are sown right away (no second winter)
        app._tut_no_sowing = False
        app._tut_sow_any_season = True

    def _after():
        nxt = 5 if step == 3 else step + 1     # (step 4, the second spring, is skipped)
        _p5_set(app, nxt)
        if nxt >= 6:
            app._tut_insp_sections = None
            app._tut_tie_sections = None         # the player's own TIE sections again
            app._seed_filter_gen = None          # the seed window shows every generation again
            app._tut_mother_colour = None
            app._tut_gave_sow_colours = False
            app._seed_filter_crossed = app._seed_filter_ofcross = False
            _award_tutorial_part(app, 6)
            return
        _watch_p5(app)

    app._tutorial_keep_hours = False
    if step in (2, 3, 5):
        _tutorial_force_sun(app)
        _start_sun_keeper(app)
    _play_cyril_visit(app, dialogue, after=_after)


def _watch_for_ageing(app):
    """After part 3: waits (once a second) until enough plants have grown
    old, then Cyril comes back for the start of part 4. A long Fast Forward
    stops right there. Cyril only comes by in the morning (7:00-11:59)."""
    _cancel_seedling_watch(app)
    if getattr(app, "_tutorial_ageing_seen", False):
        return

    def _ready():
        try:
            hour = int(app.garden.clock_hour) % 24
        except Exception:
            hour = 9
        return 7 <= hour < 12 and _enough_senescent(app) and _fair_weather(app)

    app._ff_stop_check = _ready
    # The Fast Forward window suggests the days until the plants are old —
    # the number Cyril names (a longer Fast Forward stops right there)
    app._ff_suggest_days = lambda: max(1, int(_days_until_ageing(app)))

    def _check():
        app._tutorial_seedling_job = None
        if not getattr(app, "_tutorial_active", False):
            return
        if (getattr(app, "_tutorial_dialogue", None) is None
                and not getattr(app, "fast_forward", False)):
            if _ready():
                app._ff_stop_check = None
                app._ff_suggest_days = None
                _play_ageing_lecture(app)
                return
        app._tutorial_seedling_job = app.root.after(1000, _check)

    app._tutorial_seedling_job = app.root.after(1000, _check)


def _play_part_4(app):
    """The player said yes to the next lesson (after part 3): if the plants
    are already old, part 4 starts; otherwise Cyril asks for some Fast
    Forward first and comes back by himself (see _watch_for_ageing)."""
    if _enough_senescent(app):
        _cancel_seedling_watch(app)
        _play_ageing_lecture(app)
        return
    days = max(1, _days_until_ageing(app))
    _play_cyril_visit(app, _encourage_ff_dialogue(days),
                      after=lambda: _watch_for_ageing(app))


def _watch_for_budding(app):
    _watch_for_next_part(app, 2)


def _play_stage_lecture(app, part):
    """Plays part 3-6 (Cyril comes back, says his lines, leaves again)."""
    dialogue = {3: LECTURE_3_DIALOGUE, 4: LECTURE_4_DIALOGUE,
                5: LECTURE_5_DIALOGUE, 6: LECTURE_6_DIALOGUE}[part]
    app._tutorial_portrait_free = False      # Cyril is back
    _swap_portrait_for_tutorial(app)
    _lock_down_sidebar(app)
    # Fast Forward stays locked through part 3 (buds, flowers & pods) and
    # is handed over on the last line of its final stage (see LECTURE_6).
    _tutorial_set_speed(app, _TUTORIAL_DAY_LENGTH_S)   # real time while Cyril talks
    _lock_sun_weather(app)                   # no rain or storm while he is here

    def _done():
        _tutorial_set_speed(app, 1.0)        # back to 1 sec = 1 hour
        if part >= 6:
            _set_ff_locked(app, False)       # Fast Forward is the player's now
            app._tut_insp_sections = None    # the player's own inspector sections again
            app._tut_tie_sections = None         # the player's own TIE sections again
        _release_sun(app)                    # the weather is free again
        _unlock_sidebar(app)
        _cyril_leaves(app)
        _save_tutorial_progress(app, part)
        _save_checkpoint(app, part)
        if part >= 6:
            # Part 3 (parts 3-6) done: achievement, then — 5 s after the
            # congratulation is closed — Cyril asks about the next lesson.
            win = _award_tutorial_part(app, 3)
            _offer_next_lesson_after(app, win)
        _watch_for_next_part(app, part)
        if part >= 6:
            _watch_for_ageing(app)           # old plants bring Cyril back (part 4)

    _StatusBarDialogue(app, dialogue, on_finish=_done)


def _play_lecture_3(app):
    _play_stage_lecture(app, 3)


def _garden_when(progress):
    """(year, month, day) of a saved tutorial garden."""
    try:
        g = progress["garden"]
        g = g.get("garden", g)
        return (int(g.get("year")), int(g.get("month")), int(g.get("day_of_month")))
    except Exception:
        return None


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
        # A restarted / continued part always runs at 1 sec = 1 hour,
        # whatever speed was showing when it was saved (Cyril's lines
        # switch to real time by themselves while he talks).
        speed = 1.0
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
    _set_later_steps(app, progress.get("later_steps"))
    try:
        app._toast("Tutorial progress restored.", level="info")
    except Exception:
        pass
    _start_loss_watch(app)
    if app._tutorial_part_done == 1:
        _watch_for_seedlings(app)
    elif app._tutorial_part_done >= 2:
        if app._tutorial_part_done >= 6:
            _set_ff_locked(app, False)
        _watch_for_next_part(app, app._tutorial_part_done)
        if app._tutorial_part_done >= 6:
            # parts 4 and 5 go on where they were left
            if int(getattr(app, "_tutorial_cross_done", 0) or 0) >= 3:
                # part 5
                if _p5_step(app) == 0:
                    # not begun yet: back to the day Cyril first asked (the
                    # year may have gone on into winter meanwhile), then on
                    start = None if progress.get("_p5_start") else _load_part_start(
                        _MAP_PART_STEPS[5][0])
                    if start is not None and _garden_when(start) != _garden_when(
                            {"garden": {"year": app.garden.year, "month": app.garden.month,
                                        "day_of_month": app.garden.day_of_month}}):
                        start["_p5_start"] = True
                        app.root.after(10, lambda d=start: _resume_tutorial(app, d, True))
                        return
                    app.root.after(1500, lambda: _play_part_5(app))
                else:
                    if _p5_step(app) >= 4:
                        app._tut_allow_tie = True
                    _watch_p5(app)
            elif getattr(app, "_tutorial_spring_seen", False):
                _watch_for_cross_visit(app, int(getattr(app, "_tutorial_cross_done", 0) or 0) + 1)
            elif getattr(app, "_tutorial_ageing_seen", False):
                _watch_for_spring(app)
            else:
                _watch_for_ageing(app)


def exit_tutorial(app):
    app._tut_insp_sections = None            # the player's own inspector sections again
    app._tut_tie_sections = None         # the player's own TIE sections again
    app._seed_filter_gen = None
    app._tut_mother_colour = None
    app._tut_gave_sow_colours = False
    app._seed_filter_crossed = app._seed_filter_ofcross = False
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
    app._ff_suggest_days = None         # Fast Forward suggests 3 days again
    app._tut_allow_tie = False
    app._tut_no_sowing = False
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
    try:
        app._refresh_plot_switcher_buttons()         # every garden open again
    except Exception:
        pass
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
_P_PURPLE = {"plant_height": "tall", "flower_position": "axial", "flower_color": "purple",
             "pod_color": "green", "pod_shape": "inflated", "seed_color": "yellow",
             "seed_shape": "round"}
_P_WHITE = dict(_P_PURPLE, flower_color="white")
_P_BUDS = dict(_P_PURPLE, flower_position="terminal")

# One picture per part: one or more plants (stage, how far through it,
# traits), "x" for a cross sign between two of them. Drawn in the player's
# chosen plant style (Game ▸ Plant style), like the garden itself.
_TUTORIAL_PARTS = [
    ("Part 1", "The First Seeds", [(2, 0.6, _P_PURPLE)]),                  # a seedling
    ("Part 2", "The Seedlings", [(3, 0.5, _P_PURPLE)]),                    # a leafy young plant
    ("Part 3", "Buds, Flowers & Pods", [(4, 0.6, _P_BUDS), (7, 1.0, _P_PURPLE)]),  # buds … ripe pods
    ("Part 4", "Crossing", [(5, 0.95, _P_PURPLE), "x", (5, 0.95, _P_WHITE)]),        # purple × white
    ("Part 5", "The Hidden Elements", [(5, 0.95, _P_PURPLE), (5, 0.95, _P_WHITE)]),   # F2: purple and white again
]

# Part 4 (»Crossing«: the plants age, the winter passes, then the three
# crossing visits) has no internal step numbers of its own — it is tracked
# by the "later_steps" flags — so on the map it runs from step 7 (its
# start save, part7start, taken when Cyril comes for the ageing talk) to
# step 8 (the crossed pod harvested); see _map_progress_step.
_MAP_PART_STEPS = {1: (1, 1), 2: (2, 2), 3: (3, 6), 4: (7, 8), 5: (9, 10)}


def _map_progress_step(progress):
    """How far a saved tutorial got, on the map's step scale (1-8)."""
    if not progress:
        return 0
    pd = int(progress.get("tutorial_part_done", 0) or 0)
    if pd >= 6:
        steps = progress.get("later_steps") or {}
        if int(steps.get("p5", 0) or 0) >= 6:
            return 10
        if int(steps.get("p5", 0) or 0) >= 1:
            return 9
        if int(steps.get("cross_done", 0) or 0) >= 3:
            return 8
    return pd


def _plant_pil(app, stage, frac, traits, height):
    """One plant for the tutorial map, `height` px tall, in the player's
    plant style: drawn (grown / staked / painted) or the classic picture."""
    from PIL import Image
    style = str(getattr(app, "_plant_style", "grown") or "grown")
    im = None
    if style != "classic":
        try:
            import pea_render as _pr
            age = _pr.model_age(stage, frac, 6.0 if stage >= 7 else 0.0)
            im = _pr.plant_image(traits, 7, age, painterly=("painted" in style),
                                 staked=("staked" in style), size=max(64, height * 2))
        except Exception:
            im = None
    if im is None:
        try:
            from icon_loader import stage_icon_path, stage_icon_path_for_plant
            import types
            fake = types.SimpleNamespace(
                stage=stage, alive=True, traits=dict(traits), revealed_traits=dict(traits),
                health=100, pods_remaining=(5 if stage >= 6 else 0), pods_total=5,
                flipped_horizontally=False, fully_harvested=False, emasculated=False,
                days_since_planting=0, stage_thresholds=lambda: [0, 0, 4, 8, 13, 18, 25, 30])
            try:
                path = stage_icon_path_for_plant(fake)
            except Exception:
                path = stage_icon_path(stage)
            if path and os.path.isfile(path):
                im = Image.open(path).convert("RGBA")
        except Exception:
            im = None
    if im is None:
        return None
    # One scale for every plant: the whole picture (the plot) is `height`
    # tall, so a seedling stays small next to a grown plant.
    sc = height / float(max(1, im.size[1]))
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    w, h = im.size
    return im.resize((max(1, int(w * sc)), max(1, int(h * sc))), Image.LANCZOS)


def _round_rect(cv, x0, y0, x1, y1, r, **kw):
    """A rectangle with round corners (radius r) on a Canvas."""
    r = max(1, min(r, (x1 - x0) // 2, (y1 - y0) // 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


def _part_picture(app, spec, height, max_w, locked):
    """The picture for one part on the map: its plants side by side (a gap
    where spec has "x" — the cross sign is drawn by the caller). Returns
    (PhotoImage or None, [x offsets of the cross signs], width)."""
    from PIL import Image, ImageTk
    gap, cross_w = -6, 34          # plants may overlap a little (tendrils);
                                   # the cross sign keeps room around it
    items = []
    for it in spec:
        if it == "x":
            items.append("x")
        else:
            st, fr, tr = it
            im = _plant_pil(app, st, fr, tr, height)
            if im is not None:
                items.append(im)
    if not any(not isinstance(i, str) for i in items):
        return None, [], 0
    total = sum((cross_w if isinstance(i, str) else i.width) for i in items) + gap * (len(items) - 1)
    if total > max_w:                         # too wide: shrink everything
        f = max_w / float(total)
        items = [i if isinstance(i, str) else
                 i.resize((max(1, int(i.width * f)), max(1, int(i.height * f))), Image.LANCZOS)
                 for i in items]
        cross_w = int(cross_w * f)
        total = sum((cross_w if isinstance(i, str) else i.width) for i in items) + gap * (len(items) - 1)
    hh = max(i.height for i in items if not isinstance(i, str))
    out = Image.new("RGBA", (max(1, total), hh), (0, 0, 0, 0))
    x, crosses = 0, []
    for i in items:
        if isinstance(i, str):
            crosses.append(x + cross_w // 2)
            x += cross_w + gap
        else:
            out.paste(i, (x, hh - i.height), i)
            x += i.width + gap
    if locked:
        r, g, b, al = out.split()
        grey = Image.merge("RGB", (r, g, b)).convert("L").convert("RGB")
        al = al.point(lambda v: int(v * 0.45))
        out = Image.merge("RGBA", (*grey.split(), al))
    return ImageTk.PhotoImage(out), crosses, total


def _map_button(parent, text, command, bg="#8B4226", fg="white", hover="#5C2810"):
    # Label-based so colors work on macOS (tk.Button ignores them there).
    lbl = tk.Label(parent, text=text, font=("Segoe UI", 12, "bold"), bg=bg, fg=fg,
                   padx=14, pady=5, cursor="hand2")
    lbl.bind("<Enter>", lambda e: lbl.configure(bg=hover))
    lbl.bind("<Leave>", lambda e: lbl.configure(bg=bg))
    _click(None, lbl, lambda: (_click_sound(), command()))
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

    # fonts as in the inspection window
    tk.Label(win, text="Abbot Cyril's Lessons", font=("Segoe UI", 18, "bold"),
             bg=BG, fg=FG).pack(pady=(14, 2))
    tk.Label(win, text="Choose where to continue your training.",
             font=("Segoe UI", 12, "italic"), bg=BG, fg="#7a6a55").pack(pady=(0, 8))

    col_w = 180
    n = len(_TUTORIAL_PARTS)
    has_snapshot = _load_part1_snapshot() is not None
    has_progress = _load_tutorial_progress() is not None
    progress = _load_tutorial_progress() if has_progress else None
    part_done = _map_progress_step(progress)
    def _map_done(n):
        first, last = _MAP_PART_STEPS.get(n, (99, 99))
        return part_done >= last or (n == 1 and has_snapshot)

    # Parts available: every finished one plus the one being worked on.
    unlocked = 1
    for _n in sorted(_MAP_PART_STEPS):
        if _map_done(_n):
            unlocked = min(len(_TUTORIAL_PARTS), _n + 1)
    unlocked = min(unlocked, max(_MAP_PART_STEPS))

    # The path: a line through one picture per part (the plants of that
    # lesson, in the player's plant style), from seedling to crossing.
    node_rx, node_ry = col_w // 2 - 8, 58
    node_r = node_ry
    path = tk.Canvas(win, width=col_w * n, height=node_ry * 2 + 14, bg=BG,
                     highlightthickness=0)
    path.pack(padx=14)
    path._images = []
    cy = node_ry + 7
    path.create_line(col_w // 2, cy, col_w * n - col_w // 2, cy,
                     fill="#b59b73", width=5, capstyle="round")
    # the stretch of path already open is drawn darker
    if unlocked > 1:
        path.create_line(col_w // 2, cy, col_w * (unlocked - 1) + col_w // 2, cy,
                         fill="#8B4226", width=5, capstyle="round")
    for i, (_t, _s, spec) in enumerate(_TUTORIAL_PARTS):
        cx = col_w * i + col_w // 2
        ok = (i < unlocked)
        # round for one plant, oval for two (or more) side by side
        n_plants = sum(1 for it in spec if it != "x")
        rx = node_rx if n_plants > 1 else node_ry
        fill = "#fbf7ee" if ok else "#e6dfcf"
        edge = "#8B4226" if ok else "#b5ab95"
        if n_plants > 1:
            # two plants: a box with generous round corners
            _round_rect(path, cx - rx, cy - node_ry, cx + rx, cy + node_ry, 40,
                        fill=fill, outline=edge, width=3)
        else:
            path.create_oval(cx - rx, cy - node_ry, cx + rx, cy + node_ry,
                             fill=fill, outline=edge, width=3)
        pad = 12                               # room above and below the plants
        try:
            img, crosses, pw = _part_picture(app, spec, node_ry * 2 - 2 * pad - 4,
                                             (rx * 2 - 2 * pad) if n_plants > 1 else int(rx * 1.5),
                                             locked=not ok)
        except Exception:
            img, crosses, pw = None, [], 0
        if img is not None:
            path._images.append(img)
            if n_plants > 1:
                # the pair centred in its box: as much space above as below
                path.create_image(cx, cy, image=img)
                ground = cy + img.height() // 2
            else:
                ground = cy + node_ry - 12     # a single plant stands on the ground
                path.create_image(cx, ground, image=img, anchor="s")
            for xo in crosses:                 # the cross sign between two parents
                path.create_text(cx - pw // 2 + xo, ground - 30, text="\u00d7",
                                 fill=("#8B4226" if ok else "#aaa090"),
                                 font=("Segoe UI", 20, "bold"))
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

    for i, (title, sub, _spec) in enumerate(_TUTORIAL_PARTS):
        ok = (i < unlocked)
        col = tk.Frame(cards, bg=(PANEL if ok else BG), width=col_w - 10, height=196,
                       highlightbackground="#d9cdb4", highlightthickness=1)
        col.grid(row=0, column=i, padx=5, sticky="n")
        col.grid_propagate(False)
        col.pack_propagate(False)
        tk.Label(col, text=title, font=("Segoe UI", 14, "bold"),
                 bg=(PANEL if ok else BG), fg=(FG if ok else "#aaa090")).pack(pady=(10, 0))
        tk.Label(col, text=sub, font=("Segoe UI", 12, "italic"),
                 bg=(PANEL if ok else BG), fg=("#7a6a55" if ok else "#b5ab95"),
                 wraplength=col_w - 30).pack(pady=(0, 8))
        n = i + 1
        done = _map_done(n)
        first = _MAP_PART_STEPS.get(n, (n, n))[0]
        can_restart = (n == 1) or (_load_part_start(first) is not None)
        if ok and done:
            # Finished: ticked, and can be played again from its start.
            tk.Label(col, text="✓", font=("Segoe UI", 16, "bold"),
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
            tk.Label(col, text="🔒", font=("Segoe UI", 16), bg=BG,
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
        _set_later_steps(app)                # parts 4 and 5 start over too
        app._tut_starter_n = 0               # purple and white starter seeds in turn
        app._tutorial_active = True
        try:
            app._refresh_plot_switcher_buttons()     # garden 2 closed again
        except Exception:
            pass
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
        _award_tutorial_part(app, 1)
        _watch_for_seedlings(app)
        _start_loss_watch(app)

    def _on_dialogue_dismissed():
        wait_for = lecture.get("wait_for")
        if wait_for == "all_seeds_planted":
            _wait_for_all_seeds_planted(app, lecture, _on_finish)
        else:
            _on_finish()

    _StatusBarDialogue(app, lecture["dialogue"], on_finish=_on_dialogue_dismissed)
