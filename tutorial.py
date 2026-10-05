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
             "I see you already have nine pea seeds left from last year.",
             {"highlight_words": ["nine"], "highlight_target": "seed_count",
              "pause": True}),
            ("Cyril",
             "Excellent! They are quite ready to be planted."),
            ("Cyril",
             "You can choose »Plant«, the button at the top, to plant "
             "your first seeds.",
             # Waits for the player to actually plant via the Plant
             # button (rather than a fixed delay) before moving on —
             # see "wait_for_condition" above and _WAIT_CONDITIONS below.
             {"highlight_words": ["Plant"], "highlight_target": "plant_button",
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
             "Nicely done, Gregor! You're quite the natural gardener, "
             "I must say.",
             {"mood": 2}),
            ("Cyril",
             "I can hardly wait to see something spring from the soil!",
             {"mood": 2}),
            ("Cyril",
             "Now, this may take some time, Brother. So let me "
             "share with you a true gardener's secret!"),
            ("Cyril",
             "Hold Ctrl and tap the < or > arrow key to slow "
             "down or speed up time.",
             # Waits for the player to actually press Ctrl+Left or
             # Ctrl+Right (see "wait_for_keys" above) before moving on,
             # with no "▶" to skip past it ("no_skip").
             {"highlight_words": ["Ctrl", "< or > arrow key"],
              "pause": True, "no_skip": True,
              "wait_for_keys": ("<Control-Left>", "<Control-Right>"),
              "wait_for_condition": "key_pressed"}),
            ("Cyril",
             "Good, now set the pace to 1 sec = one hour.",
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
             "Splendid! Isn’t it almost magical? You may have noticed "
             "that day and night now pass with time.",
             {"mood": 2}),
            ("Cyril",
             "But remember, Brother, we all need time to sleep, "
             "study, pray, and eat."),
            ("Cyril",
             "So you may only tend to the garden at a reasonable hour."),
            ("Cyril",
             "I shall grant you access from 6 a.m. until 10 p.m.",
             {"highlight_words": ["6 a.m.", "10 p.m."]}),
            ("Cyril",
             "Even the most devoted gardener needs his rest!"),
            ("Cyril",
             "Oh, and should you ever feel a little overwhelmed by the "
             "passing of time,"),
            ("Cyril",
             "simply press Space to pause for a moment.",
             {"highlight_words": ["Space"]}),
            ("Cyril",
             "That will be all for today, Brother. I think you "
             "have learned quite a lot!",
             {"mood": 2}),
            ("Cyril",
             "Now, tend to your plants until you see the first little "
             "seedlings emerge from the soil.",
             {"highlight_words": ["seedlings"]}),
            ("Cyril",
             "Once they do, come and find me, and I shall teach you more.",
             # Last line of lecture 1 — no "▶": it ends by itself 5s
             # after it finishes typing, which hands control back
             # (start_tutorial's _on_finish) and puts up franz_0.
             {"auto_advance_ms": 5000}),
        ],
    },
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
}


# Maps a lecture line's "wait_for_condition" name to a function that
# checks whether it's been satisfied yet. Each function takes (app,
# baseline) — baseline is whatever app.available_seeds was the moment
# the line started showing, captured in _StatusBarDialogue._show_line —
# and returns True once the player has done the thing being asked.
# Polled every 400ms (see _StatusBarDialogue._poll_wait_condition),
# same cadence as _wait_for_all_seeds_planted below.
_WAIT_CONDITIONS = {
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

    def __init__(self, app, target_widget):
        self.app = app
        self.target = target_widget
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
        try:
            self.win.wm_attributes("-transparentcolor", self._key)
        except Exception:
            # Not supported on this platform — falls back to a plain,
            # non-transparent key-colored rectangle behind the glyph.
            pass

        self.canvas = tk.Canvas(
            self.win, bg=self._key, highlightthickness=0, bd=0,
            cursor="arrow",
        )
        self.canvas.pack()

        self._glyph = "⬆"
        self._font = ("Segoe UI", self.FONT_SIZE, "bold")
        self._build_items()
        self._reposition()
        self._start_cycling()

    def _build_items(self):
        # Measures the glyph with a throwaway text item first, so the
        # canvas (and the window around it) is sized to fit it plus the
        # outline's own offset, rather than some guessed fixed size.
        tmp = self.canvas.create_text(0, 0, text=self._glyph, font=self._font, anchor="center")
        bbox = self.canvas.bbox(tmp)
        self.canvas.delete(tmp)
        t = self.OUTLINE_THICKNESS
        pad = t + 4
        if bbox:
            w = (bbox[2] - bbox[0]) + pad * 2
            h = (bbox[3] - bbox[1]) + pad * 2
        else:
            w = h = self.FONT_SIZE * 2
        self.canvas.configure(width=w, height=h)
        cx, cy = w // 2, h // 2

        # A ring of just 8 copies at one fixed distance leaves visible
        # gaps/overlaps between them — most obvious at the arrow's
        # pointed tip and the corners of the shaft, where the gaps
        # between adjacent copies show through as odd little jagged
        # shapes. Filling every offset inside the outline's radius
        # (not just its rim) instead gives a solid, smooth outline with
        # no such artifacts, at the cost of more canvas items — cheap
        # enough for one static glyph drawn once.
        for dx in range(-t, t + 1):
            for dy in range(-t, t + 1):
                if dx == 0 and dy == 0:
                    continue
                if dx * dx + dy * dy > t * t:
                    continue
                self.canvas.create_text(
                    cx + dx, cy + dy, text=self._glyph, font=self._font,
                    fill="black", anchor="center",
                )
        self._main_id = self.canvas.create_text(
            cx, cy, text=self._glyph, font=self._font,
            fill=self.COLOR_A, anchor="center",
        )

    def _reposition(self):
        try:
            self.target.update_idletasks()
            x = self.target.winfo_rootx() + self.target.winfo_width() // 2
            y = self.target.winfo_rooty() + self.target.winfo_height() + 4
            self.win.update_idletasks()
            w = self.win.winfo_reqwidth()
            self.win.geometry(f"+{x - w // 2}+{y}")
        except Exception:
            pass

    def _set_step(self, step):
        self._step = max(0, min(self.STEPS, step))
        try:
            color = _lerp_color(self.COLOR_A, self.COLOR_B, self._step / self.STEPS)
            self.canvas.itemconfigure(self._main_id, fill=color)
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

    def __init__(self, app, lines, on_finish=None, speed_ms=18):
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
        btn = tk.Button(
            self.app.root, text=text, font=("Segoe UI", 11, "bold"),
            width=2, relief="flat", bd=0, bg=self._btn_bg_normal, fg="white",
            activebackground="#7A3A18", activeforeground="white",
            cursor="hand2", command=command,
        )
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
        if speaker == self._caption_speaker:
            return
        try:
            photo = None
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
        self._apply_speaker_caption(speaker)
        self._full_text = text
        self._char_pos = 0
        self._highlight_words = extra.get("highlight_words") or []
        self._apply_seed_grant(idx, extra.get("grant_seeds"))

        # Nothing to go back to from the very first line — _reposition_
        # buttons() simply place_forget()s it there.
        try:
            self.back_btn.configure(state=("normal" if idx > 0 else "disabled"))
        except Exception:
            pass

        target_name = extra.get("highlight_target")
        target_widget = _HIGHLIGHT_TARGETS.get(target_name, lambda app: None)(self.app) if target_name else None
        if target_widget is not None:
            self._active_arrow = _ArrowHighlight(self.app, target_widget)
            # Dismiss the arrow the moment the player actually clicks
            # the thing it's pointing at (e.g. clicking "Plant" opens
            # the Choose Seeds dialog) — not just when they advance the
            # dialogue text — so it doesn't linger on screen, on top of
            # whatever that click just opened, once its job is done.
            self._arrow_click_cleanup = self._bind_arrow_dismiss_on_click(target_widget)

        self._set_status(self._prefix)
        self._type_next_char()
        self._start_live_readout()

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
        self._char_pos += 1
        self._set_status(self._prefix + self._full_text[:self._char_pos])
        self._typing_job = self.app.root.after(self.speed_ms, self._type_next_char)

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

def _lock_down_sidebar(app):
    """Disables every button in the left action sidebar (Water, Inspect,
    Harvest, Pollinate, Remove, Genotype, ...) so the player can't do
    anything but follow along at first. Iterates the sidebar frame's
    children rather than naming each button, so it automatically covers
    any button added there later too — EXCEPT the Monastery button
    itself, which must stay clickable: it's the only way back to the
    Monastery map (and, from there, out of the tutorial), so it must
    never become unavailable."""
    try:
        monastery_btn = getattr(app, "monastery_btn", None)
        for child in app.left_actions.winfo_children():
            if child is monastery_btn:
                continue
            try:
                child.configure(state="disabled")
            except Exception:
                pass
    except Exception:
        pass


def _unlock_sidebar(app):
    """Re-enables every button in the left action sidebar."""
    try:
        for child in app.left_actions.winfo_children():
            try:
                child.configure(state="normal")
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


def _swap_portrait_for_tutorial(app, filename=_TUTOR_PORTRAIT_FILENAME):
    """
    Swaps the left-panel portrait (self.mendel_label, normally
    mendel.png) to the Abbot's own portrait for the tutorial. Falls back
    to leaving the existing portrait alone if the file isn't there yet —
    drop icons/franz.png in whenever it's ready; nothing else needs to
    change here.
    """
    try:
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
    def _check():
        # The player may have left the tutorial entirely (via "Mendel's
        # Garden") while this was waiting — stop rather than fire
        # against whatever garden state got restored underneath it.
        if not getattr(app, "_tutorial_active", False):
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


def exit_tutorial(app):
    """
    Leaves the tutorial and returns to the normal simulator. Bound to the
    Monastery map's "Mendel's Garden" region (replacing what used to open
    the Load Garden dialog there) — clicking it now always takes the
    player back to their real garden exactly as it was before the
    tutorial started, rather than opening a file picker.
    """
    try:
        restored = _restore_pre_tutorial_state(app)
    except Exception:
        restored = False
    app._tutorial_active = False
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

def start_tutorial(app, lecture_index=0):
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
    if lecture_index == 0 and getattr(app, "_tutorial_active", False):
        try:
            app._toast("Already in the tutorial.", level="info")
        except Exception:
            pass
        return

    lecture = LECTURES[lecture_index]

    if lecture_index == 0:
        app._tutorial_active = True
        _save_pre_tutorial_state(app)

    _swap_portrait_for_tutorial(app)
    _set_easy_difficulty(app)
    _set_tutorial_speed(app)
    _lock_down_sidebar(app)
    _apply_lecture_to_real_grid(app, lecture)

    def _on_finish():
        # Lecture 1 ends by handing control back to the player. Lecture
        # 2+ would chain here instead (e.g. re-lock a different patch
        # and call start_tutorial(app, lecture_index + 1)). The player
        # can also leave early at any point via the Monastery map's
        # "Mendel's Garden" region, which calls exit_tutorial() above.
        _unlock_sidebar(app)
        # Cyril leaves once the lecture is over; franz_0 stays up until
        # he is back for the next one.
        _swap_portrait_for_tutorial(app, _PORTRAIT_AWAY_FILENAME)

    def _on_dialogue_dismissed():
        wait_for = lecture.get("wait_for")
        if wait_for == "all_seeds_planted":
            _wait_for_all_seeds_planted(app, lecture, _on_finish)
        else:
            _on_finish()

    _StatusBarDialogue(app, lecture["dialogue"], on_finish=_on_dialogue_dismissed)
