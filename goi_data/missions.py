"""
Missions — goals a player can pursue in Mendel's garden besides the laws.

Each mission is a small description (title, aim, Mendel's own experiment,
how to do it) plus a check function that reads the garden's records — the
archive of every plant (its mother, its father, the traits seen so far),
the plants growing now and the seeds harvested — and reports the progress
as a checklist.

A mission is accepted on the missions board; accepting starts a new
garden for it (app._active_mission, saved with the garden). Only the
active mission is checked, and it completes by itself (an achievement and
Abbot Cyril's congratulations) once its check passes. The active mission
is shown in the main window's side bar; clicking it opens its card.

Only plain observation counts: in a garden where the genotype was revealed
no mission can be completed (as with the laws and achievements), and
Abbot Cyril's practice garden (the tutorial) never counts.

To add a mission: write a check function returning a Progress, add an
entry to MISSIONS, and an achievement of the same key to
GardenApp.ACHIEVEMENTS (group "Missions").
"""

import tkinter as tk

# (trait key, name, dominant form, recessive form)
TRAITS = [
    ("flower_color", "flower colour", "purple", "white"),
    ("seed_shape", "seed shape", "round", "wrinkled"),
    ("seed_color", "seed colour", "yellow", "green"),
    ("plant_height", "plant height", "tall", "short"),
    ("pod_shape", "pod shape", "inflated", "constricted"),
    ("pod_color", "pod colour", "green", "yellow"),
    ("flower_position", "flower position", "axial", "terminal"),
]
SEED_TRAITS = ("seed_shape", "seed_color")
_TRAIT_NAME = {k: n for k, n, _d, _r in TRAITS}

# offspring needed in each direction of a reciprocal cross
RECIPROCAL_NEED_PLANTS = 5     # offspring plants grown from the crossed seeds
                               # (each must have shown the trait)
RECIPROCAL_NEED_SEEDS = 10     # or harvested seeds, for seed shape / colour

WATCH_MS = 4000                # how often the missions are checked


def _click(app, widget, fn):
    """A click that acts when the mouse button is released over the widget
    (the game's _bind_click): rebuilding or closing the window while the
    button is still pressed over it crashed Tk on the Mac."""
    b = getattr(app, "_bind_click", None)
    if b is not None:
        b(widget, fn)
    else:
        widget.bind("<Button-1>", lambda e: fn())


def _norm(v):
    v = str(v or "").strip().lower()
    return {"dwarf": "short"}.get(v, v)


class Progress:
    """What a mission's check found: done, a checklist of (text, ticked),
    and an optional hint for what to do next."""

    def __init__(self, done=False, items=None, hint=""):
        self.done = bool(done)
        self.items = list(items or [])
        self.hint = hint
        self.failed = False          # the mission can't succeed any more (see check_all)


# ---------------------------------------------------------------------------
# Reading the garden
# ---------------------------------------------------------------------------

def _all_plants(app):
    """{str(id): snapshot dict} — the archive, with the plants growing now
    laid over it (their traits and discoveries are the newest). Each entry
    also gets "mom" / "dad": the plant that bore the seed and the one that
    gave the pollen (mother_id / father_id are stored in id order, so they
    can't tell a cross from its reverse; older records only have those)."""
    out = {}
    try:
        for k, s in ((getattr(app, "archive", {}) or {}).get("plants", {}) or {}).items():
            if isinstance(s, dict):
                out[str(k)] = dict(s)
    except Exception:
        pass
    try:
        tiles = app._all_plot_tiles()
    except Exception:
        tiles = list(getattr(app, "tiles", []) or [])
    for t in tiles:
        p = getattr(t, "plant", None)
        if p is None or getattr(p, "id", None) is None:
            continue
        old = out.get(str(p.id)) or {}
        rt = dict(old.get("revealed_traits") or {})
        rt.update(getattr(p, "revealed_traits", None) or {})
        out[str(p.id)] = {
            "id": p.id,
            "mother_id": getattr(p, "mother_id", None),
            "father_id": getattr(p, "father_id", None),
            "seed_parent_id": getattr(p, "seed_parent_id", old.get("seed_parent_id")),
            "pollen_parent_id": getattr(p, "pollen_parent_id", old.get("pollen_parent_id")),
            "traits": dict(getattr(p, "traits", {}) or {}),
            "revealed_traits": rt,
            "_tile": t,
            "_plant": p,
        }
    for s in out.values():
        m = s.get("seed_parent_id")
        f = s.get("pollen_parent_id")
        if m in (None, "", -1):
            m, f = s.get("mother_id"), s.get("father_id")
        s["mom"] = None if m in (None, "", -1) else str(m)
        s["dad"] = None if f in (None, "", -1) else str(f)
    return out


def _known(snap, trait):
    """The form of `trait` the player has seen on this plant, or None.
    Seed shape and colour were seen on the pea it grew from."""
    if not isinstance(snap, dict):
        return None
    tr = snap.get("traits") or {}
    if trait not in SEED_TRAITS:
        rt = snap.get("revealed_traits")
        if isinstance(rt, dict) and trait not in rt:
            return None
    v = _norm(tr.get(trait))
    return v or None


def _crossed(mid, fid):
    return mid not in (None, "", -1) and fid not in (None, "", -1) and str(mid) != str(fid)


def _is_cross(s):
    return bool(s) and _crossed(s.get("mom"), s.get("dad"))


def _is_selfed(s):
    """Grown from a seed of its mother's own pollen."""
    if not s or s.get("mom") is None:
        return False
    return s.get("dad") in (None, s.get("mom"))


def _form_label(key, form):
    form = _norm(form)
    if key == "plant_height":
        return "dwarf" if form == "short" else "tall"
    noun = {"flower_color": "flowers", "flower_position": "flowers", "seed_color": "seeds",
            "seed_shape": "seeds", "pod_color": "pods", "pod_shape": "pods"}.get(key, "")
    return f"{form} {noun}".strip()


def _recessive(key):
    return next((r for k, _n, _d, r in TRAITS if k == key), None)


def _dominant(key):
    return next((d for k, _n, d, _r in TRAITS if k == key), None)


def _counts_line(c):
    return " · ".join(f"{v} {k}" for k, v in c.most_common())


def _cross_families(app):
    """{(seed parent, pollen parent): {trait: Counter of forms}} for every
    cross (two different parents) in the garden: plant traits from the
    offspring that were sown and have shown them while growing; seed shape
    and colour from every harvested seed (they show on the pea itself)."""
    from collections import Counter, defaultdict
    plants = _all_plants(app)
    fam = defaultdict(lambda: defaultdict(Counter))
    for s in plants.values():
        if not _is_cross(s):
            continue
        for key, *_ in TRAITS:
            if key in SEED_TRAITS:
                continue
            v = _known(s, key)
            if v:
                fam[(s["mom"], s["dad"])][key][v] += 1
    # every harvested crossed seed: kept under the plant that bore it, with
    # the plant that gave the pollen ("donor")
    try:
        store = (getattr(app, "archive", {}) or {}).get("pod_seeds") or {}
    except Exception:
        store = {}
    for m, recs in store.items():
        for r in recs or []:
            f = r.get("donor")
            if not _crossed(m, f):
                continue
            for key in SEED_TRAITS:
                v = _norm(r.get(key))
                if v:
                    fam[(str(m), str(f))][key][v] += 1
    return plants, fam


def _selfed_children(plants):
    """{parent id: [snapshots of its selfed offspring]}"""
    out = {}
    for s in plants.values():
        if _is_selfed(s):
            out.setdefault(s["mom"], []).append(s)
    return out


def _filial(plants, pid, memo=None, depth=0):
    """Generations since the last cross in this plant's line: 1 = grown
    from a crossed seed, 2 = from that plant's own seed, ... None: no cross
    in its line."""
    memo = {} if memo is None else memo
    pid = str(pid)
    if pid in memo:
        return memo[pid]
    memo[pid] = None
    s = plants.get(pid)
    if s is None or depth > 60:
        return None
    if _is_cross(s):
        r = 1
    elif _is_selfed(s):
        up = _filial(plants, s["mom"], memo, depth + 1)
        r = None if up is None else up + 1
    else:
        r = None
    memo[pid] = r
    return r


# ---------------------------------------------------------------------------
# EASY 1 — Pure lines
# ---------------------------------------------------------------------------

PURE_NEED = 15     # selfed offspring that showed the trait, all like the parent


def pure_line_trait(app):
    """The trait the player chose for True Breeders (None: not chosen)."""
    if getattr(app, "_active_mission", None) == "mission_pure_line":
        k = (getattr(app, "_active_mission_params", None) or {}).get("trait")
    else:
        k = (getattr(app, "_mission_choice", None) or {}).get("mission_pure_line")
    return k if k in _TRAIT_NAME else None


def setup_pure_line(app):
    return {"trait": (getattr(app, "_mission_choice", None) or {}).get("mission_pure_line")}


def check_pure_line(app):
    """Two true-breeding lines of the chosen trait, one for each form (e.g. a purple
    and a white line): each a parent whose PURE_NEED selfed offspring showed
    the trait, all like it. (Without a chosen trait — older saves — the
    trait closest to it counts.)"""
    from collections import Counter
    plants = _all_plants(app)
    kids = _selfed_children(plants)
    chosen = pure_line_trait(app)
    # best line per (trait, form): (score, parent, Counter)
    lines = {}
    for pid, ch in kids.items():
        par = plants.get(pid)
        for key, *_ in TRAITS:
            if chosen is not None and key != chosen:
                continue
            if chosen is None and key in SEED_TRAITS:
                continue
            form = _known(par, key)
            if not form:
                continue
            c = Counter(v for v in (_known(k, key) for k in ch) if v)
            if not c:
                continue
            ok = set(c) == {form}
            score = (ok and sum(c.values()) >= PURE_NEED, ok, min(sum(c.values()), PURE_NEED))
            cur = lines.get((key, form))
            if cur is None or score > cur[0]:
                lines[(key, form)] = (score, pid, c)

    def line_text(key, form):
        got = lines.get((key, form))
        lbl = _form_label(key, form).capitalize()
        if got is None:
            return (f"{lbl}: no selfed offspring raised yet", False)
        (done, ok, _n), pid, c = got
        tot = sum(c.values())
        txt = (f"{lbl} (#{pid}): {min(tot, PURE_NEED)}/{PURE_NEED} offspring showing their "
               f"{_TRAIT_NAME[key]}  ({_counts_line(c)})")
        if not ok:
            txt += " \u2014 not a true breeder"
        return (txt, done)

    # the chosen trait (else the one closest to two true-breeding lines)
    best_key, best_score = chosen, None
    for key, _n, dom, rec in TRAITS:
        if chosen is not None:
            break
        if key in SEED_TRAITS:
            continue
        sc = tuple(sum(x) for x in zip(*[(lines[(key, f)][0][0], lines[(key, f)][0][1],
                                          lines[(key, f)][0][2]) if (key, f) in lines
                                         else (0, 0, 0) for f in (dom, rec)]))
        if best_score is None or sc > best_score:
            best_key, best_score = key, sc
    key = best_key
    dom, rec = _dominant(key), _recessive(key)
    if not lines:
        n = sum(len(v) for v in kids.values())
        if chosen is not None:
            items = [("Let plants pollinate themselves and sow their seeds", n > 0),
                     line_text(key, dom), line_text(key, rec)]
            return Progress(False, items,
                            (f"Wait until the young plants show their {_TRAIT_NAME[key]}." if n else
                             f"Harvest the seeds of a plant with {_form_label(key, dom)} and of one "
                             f"with {_form_label(key, rec)}, and sow them."))
        items = [("Let plants pollinate themselves and sow their seeds", n > 0),
                 (f"A true breeder of one form: {PURE_NEED} offspring all like their parent", False),
                 ("A true breeder of the other form of the same trait", False)]
        return Progress(False, items,
                        ("Wait until the young plants show their traits." if n else
                         "Harvest the seeds of a purple and of a white plant, and sow them."))
    a, b = line_text(key, dom), line_text(key, rec)
    done = a[1] and b[1]
    items = [a, b]
    hint = ""
    if not done:
        bad = [f for f in (dom, rec) if (key, f) in lines and not lines[(key, f)][0][1]]
        if bad:
            hint = (f"The parent with {_form_label(key, bad[0])} is a hybrid: some offspring "
                    "differ. Try the seeds of another plant of that form.")
        elif (key, dom) not in lines or (key, rec) not in lines:
            hint = (f"Now raise the selfed offspring of a plant with "
                    f"{_form_label(key, rec if (key, rec) not in lines else dom)}.")
        else:
            hint = f"Raise more offspring: {PURE_NEED} of each line that show the trait."
    return Progress(done, items, hint)


# ---------------------------------------------------------------------------
# EASY 2 — Seven characters
# ---------------------------------------------------------------------------

SEVEN_KEY = "mission_seven"

# Each form as the notebook offers it: (word, how it looks — after Mendel's
# own descriptions, 1866) and what Cyril adds once it is named correctly.
SEVEN_FORMS = {
    ("seed_shape", "round"): ("round", "smooth and round, at most with shallow dents",
                              "Round peas keep their shape as they dry: they store mostly starch."),
    ("seed_shape", "wrinkled"): ("wrinkled", "angular and deeply wrinkled",
                                 "Wrinkled peas hold more sugar and water, so they shrink and "
                                 "crease as they dry."),
    ("seed_color", "yellow"): ("yellow", "the seed leaves inside the pea are pale to bright yellow",
                               "In yellow peas the green fades from the seed leaves as they ripen."),
    ("seed_color", "green"): ("green", "the seed leaves inside the pea are a clear green",
                              "Green peas keep their green even when they are fully ripe."),
    ("flower_color", "purple"): ("purple", "violet standard and purple wings",
                                 "Purple-flowered plants have grey or brown seed coats, too, and "
                                 "often a reddish spot where the leaves join the stem."),
    ("flower_color", "white"): ("white", "all petals white",
                                "White-flowered plants have white seed coats as well: one element "
                                "colours both."),
    ("plant_height", "tall"): ("tall", "a long stem: the plant grows high",
                               "Mendel's tall plants climbed six to seven feet high."),
    ("plant_height", "short"): ("dwarf", "a short stem: the plant stays low and compact",
                                "Mendel's dwarf plants stayed at three quarters of a foot to a "
                                "foot and a half."),
    ("pod_shape", "inflated"): ("inflated", "smoothly arched, not pinched between the seeds (a smooth outline)",
                                "An inflated pod has a stiff, papery inner layer that keeps it taut."),
    ("pod_shape", "constricted"): ("constricted", "deeply pinched in between the seeds (a wavy outline)",
                                   "A constricted pod lacks the stiff inner layer, so it shrinks "
                                   "around the seeds."),
    ("pod_color", "green"): ("green", "light to dark green while unripe",
                             "Green pods stay green until they ripen and dry."),
    ("pod_color", "yellow"): ("yellow", "a vivid yellow while still unripe",
                              "Yellow pods are yellow even while young and full of life; the "
                              "stalks and leaf veins often are, too."),
    ("flower_position", "axial"): ("axial", "the flowers spread along the stem, where the "
                                   "leaves join it",
                                   "Axial flowers open one after another, up along the stem."),
    ("flower_position", "terminal"): ("terminal", "the flowers bunched together at the top "
                                      "of the stem",
                                      "With terminal flowers the top of the stem is often "
                                      "broadened, too."),
}


def seven_active(app):
    m = active_mission(app)
    return m is not None and m.get("key") == SEVEN_KEY


def _sparams(app):
    """The notebook of »The Magnificent Seven«: recorded {trait: {form: plant
    id}} and wrong answers {"id:trait": day} (saved with the garden)."""
    p = getattr(app, "_active_mission_params", None)
    if not isinstance(p, dict):
        p = {}
        app._active_mission_params = p
    if not isinstance(p.get("recorded"), dict):
        p["recorded"] = {}
    if not isinstance(p.get("wrong"), dict):
        p["wrong"] = {}
    return p


def _seven_today(app):
    try:
        return int(app._today())
    except Exception:
        return 0


def _plant_counts(plant):
    """Grown from a seed harvested in this garden (not a starter)."""
    m = getattr(plant, "seed_parent_id", None)
    if m in (None, "", -1):
        m = getattr(plant, "mother_id", None)
    return m not in (None, "", -1)


def _plant_form(plant, trait):
    """The form of `trait` the plant shows (None while it is not discovered)."""
    if trait in SEED_TRAITS:
        v = (getattr(plant, "traits", {}) or {}).get(trait)
    else:
        rt = getattr(plant, "revealed_traits", None) or {}
        if trait not in rt:
            return None
        v = (getattr(plant, "traits", {}) or {}).get(trait) or rt.get(trait)
    v = _norm(v)
    return v if (trait, v) in SEVEN_FORMS else None


def seven_status(app, plant, trait):
    """How the inspection window shows this trait of the plant while the
    mission runs: None (nothing to record here: no mission, a starter, not
    discovered), "recorded" (this form is in the notebook), "locked" (named
    wrongly today) or "record"."""
    if plant is None or not seven_active(app) or not _plant_counts(plant):
        return None
    form = _plant_form(plant, trait)
    if form is None:
        return None
    p = _sparams(app)
    if form in (p["recorded"].get(trait) or {}):
        return "recorded"
    if p["wrong"].get(f"{getattr(plant, 'id', '')}:{trait}") == _seven_today(app):
        return "locked"
    return "record"


def seven_word(trait, form):
    """The form in the notebook's words (»dwarf« for short)."""
    return SEVEN_FORMS.get((trait, _norm(form)), (str(form or ""),))[0]


def open_seven_record(app, plant, trait, on_done=None, near=None):
    """Asks which of the two forms the plant shows. Named correctly, the
    form goes into the notebook; named wrongly, this plant can't record
    this trait again until tomorrow."""
    if seven_status(app, plant, trait) != "record":
        return None
    old = getattr(app, "_seven_win", None)
    try:
        if old is not None and old.winfo_exists():
            old.destroy()
    except Exception:
        pass
    import random as _r
    form = _plant_form(plant, trait)
    pid = getattr(plant, "id", "?")
    bg = getattr(app, "INSPECTOR_BG", BG)
    win = tk.Toplevel(app.root)
    app._seven_win = win
    win.title("Your notebook")
    win.configure(bg=bg)
    win.resizable(False, False)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    outer = tk.Frame(win, bg=bg, padx=22, pady=16)
    outer.pack(fill="both", expand=True)
    tk.Label(outer, text=f"{_TRAIT_NAME[trait].capitalize()} of plant #{pid}",
             font=("Segoe UI", 18, "bold"), bg=bg, fg=INK).pack(anchor="w")
    tk.Label(outer, text="Look at the plant closely. Which form does it show?",
             font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED).pack(anchor="w", pady=(2, 10))
    opts = tk.Frame(outer, bg=bg)
    opts.pack(fill="x")
    forms = [f for (k, f) in SEVEN_FORMS if k == trait]
    _r.shuffle(forms)
    result = tk.Frame(outer, bg=bg)
    result.pack(fill="x", pady=(12, 0))
    state = {"done": False}
    cards = []

    def _close():
        try:
            win.destroy()
        except Exception:
            pass

    def _answer(f):
        if state["done"]:
            return
        state["done"] = True
        p = _sparams(app)
        ok = (f == form)
        if ok:
            p["recorded"].setdefault(trait, {})[form] = str(pid)
        else:
            p["wrong"][f"{pid}:{trait}"] = _seven_today(app)
        for c, cf in cards:
            on = (cf == f)
            colr = (SEL_BG if on else CARD)
            c.configure(bg=colr, highlightbackground=(SEL_EDGE if on else EDGE), cursor="")
            for w_ in c.winfo_children():
                w_.configure(bg=colr, cursor="")
        word = SEVEN_FORMS[(trait, form)][0]
        if ok:
            tk.Label(result, text=f"\u2713  Recorded: {_form_label(trait, form)}",
                     font=("Segoe UI", 15, "bold"), bg=bg, fg=GREEN).pack(anchor="w")
            tk.Label(result, text="Cyril: \u201c" + SEVEN_FORMS[(trait, form)][2] + "\u201d",
                     font=("Segoe UI", 13, "italic"), bg=bg, fg=INK, wraplength=520,
                     justify="left").pack(anchor="w", pady=(4, 0))
            try:
                app._toast(f"Into your notebook: {word} ({_TRAIT_NAME[trait]}, #{pid}).",
                           level="info")
            except Exception:
                pass
        else:
            tk.Label(result, text="Not quite, Gregor. Look again at the picture.",
                     font=("Segoe UI", 15, "bold"), bg=bg, fg="#a0522d").pack(anchor="w")
            tk.Label(result, text=(f"Plant #{pid} can show you its {_TRAIT_NAME[trait]} again "
                                   "tomorrow; another plant may show it today."),
                     font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED, wraplength=520,
                     justify="left").pack(anchor="w", pady=(4, 0))
        btn = tk.Label(result, text="Close", font=("Segoe UI", 14, "bold"), bg="#e8e0cf",
                       fg=INK, padx=14, pady=4, cursor="hand2")
        btn.pack(anchor="e", pady=(10, 0))
        _click(app, btn, _close)
        try:
            check_all(app)
        except Exception:
            pass
        _refresh_indicator(app)
        if on_done is not None:
            try:
                on_done()
            except Exception:
                pass

    for i, f in enumerate(forms):
        word, desc, _x = SEVEN_FORMS[(trait, f)]
        c = tk.Frame(opts, bg=CARD, cursor="hand2", padx=12, pady=8, highlightthickness=2,
                     highlightbackground=EDGE)
        c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
        opts.grid_columnconfigure(i, weight=1, uniform="o")
        tk.Label(c, text=word, font=("Segoe UI", 16, "bold"), bg=CARD, fg=INK,
                 cursor="hand2").pack(anchor="w")
        tk.Label(c, text=desc, font=("Segoe UI", 13), bg=CARD, fg=MUTED, wraplength=230,
                 justify="left", cursor="hand2").pack(anchor="w", pady=(2, 0))
        cards.append((c, f))

        def _hov(on, c=c):
            if state["done"]:
                return
            colr = HOVER_BG if on else CARD
            c.configure(bg=colr)
            for w_ in c.winfo_children():
                w_.configure(bg=colr)
        for w_ in [c] + list(c.winfo_children()):
            _click(app, w_, lambda f=f: _answer(f))
            w_.bind("<Enter>", lambda e, h=_hov: h(True))
            w_.bind("<Leave>", lambda e, h=_hov, c=c: (
                None if c.winfo_containing(e.x_root, e.y_root) in [c] + list(c.winfo_children())
                else h(False)))
    win.protocol("WM_DELETE_WINDOW", _close)
    try:
        win.update_idletasks()
        ww, wh = win.winfo_reqwidth(), win.winfo_reqheight()
        if near is not None and near.winfo_exists():
            x = near.winfo_rootx() + near.winfo_width() // 2 - ww // 2
            y = near.winfo_rooty() + near.winfo_height() + 8
        else:
            x = app.root.winfo_rootx() + (app.root.winfo_width() - ww) // 2
            y = app.root.winfo_rooty() + (app.root.winfo_height() - wh) // 2
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(0, min(x, sw - ww - 10))
        y = max(0, min(y, sh - wh - 60))
        win.geometry(f"+{x}+{y}")
    except Exception:
        pass
    return win


def check_seven(app):
    rec = _sparams(app)["recorded"] if seven_active(app) else (
        (getattr(app, "_active_mission_params", None) or {}).get("recorded") or {})
    seen = {k: set((rec.get(k) or {}).keys()) for k, *_ in TRAITS}
    items = []
    n_done = 0
    for key, name, dom, rec_ in TRAITS:
        both = dom in seen[key] and rec_ in seen[key]
        n_done += both
        missing = [_form_label(key, f) for f in (dom, rec_) if f not in seen[key]]
        text = (f"{name.capitalize()}: both forms recorded" if both else
                f"{name.capitalize()}: still missing {' and '.join(missing)}")
        items.append((text, both,
                      [(key, dom, dom in seen[key]), (key, rec_, rec_ in seen[key])]))
    hint = "" if n_done == 7 else ("Only plants grown from seeds you harvested count. In the "
                                   "inspection window, click \u00bb\u270e Record\u00ab under a "
                                   "form that is new to your notebook and name it.")
    return Progress(n_done == 7, items, hint)


# ---------------------------------------------------------------------------
# EASY 3 — White islands (a little garden design)
# ---------------------------------------------------------------------------

ISLANDS_NEED = 3


def _flowering(app, p):
    try:
        return "open" in (app._flower_states(p) or [])
    except Exception:
        return False


def _colour_shown(p):
    rt = getattr(p, "revealed_traits", None) or {}
    if "flower_color" not in rt:
        return None
    return _norm((getattr(p, "traits", {}) or {}).get("flower_color"))


_ICON_CACHE = {}


def _trait_pil(trait, form, size):
    """The game's icon for one form of a trait (PIL image, `size` px), or a
    plain coloured dot if the icon file is missing."""
    from PIL import Image, ImageDraw
    key = (trait, form, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key].copy()
    im = None
    try:
        import icon_loader as il
        f_ = _norm(form)
        # the same pictures as the TIE: pods drawn as pods, flower
        # position as a flower on its stalk
        if trait == "flower_position":
            pth = (il.flower_icon_path_hi(f_, "purple") or il.flower_icon_path(f_, "purple")
                   or il.trait_icon_path(trait, f_))
        elif trait == "pod_shape":
            pth = il.pod_shape_icon_path(f_, "green") or il.trait_icon_path(trait, f_)
        elif trait == "pod_color":
            pth = il.pod_shape_icon_path("inflated", f_) or il.trait_icon_path(trait, f_)
        else:
            pth = il.trait_icon_path(trait, f_)
        if pth:
            im = Image.open(pth).convert("RGBA")
            bb = im.getbbox()
            if bb:
                im = im.crop(bb)
            im.thumbnail((size, size), Image.LANCZOS)
    except Exception:
        im = None
    if im is None:
        colours = {"purple": (146, 92, 170), "white": (250, 250, 245), "yellow": (236, 200, 60),
                   "green": (110, 160, 70), "round": (236, 200, 60), "wrinkled": (200, 170, 70)}
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((2, 2, size - 2, size - 2),
                                   fill=colours.get(_norm(form), (180, 160, 130)) + (255,),
                                   outline=(90, 70, 50, 255))
    _ICON_CACHE[key] = im
    return im.copy()


def _faded(im):
    """A form not seen yet: grey and faint."""
    from PIL import ImageOps
    g = ImageOps.grayscale(im).convert("RGBA")
    a = im.split()[3].point(lambda v: int(v * 0.35))
    g.putalpha(a)
    return g


def _photo_label(parent, im, bg, caption=None):
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(im, master=parent)
    box = tk.Frame(parent, bg=bg)
    lbl = tk.Label(box, image=photo, bg=bg)
    lbl.image = photo
    lbl.pack()
    if caption:
        tk.Label(box, text=caption, font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED).pack()
    return box


def seven_example(app, parent, bg):
    """The seven characters, one column each: the dominant form above, the
    recessive one below."""
    from PIL import Image
    cell, gap = 28, 3
    keys = [k for k, *_ in TRAITS]
    im = Image.new("RGBA", (len(keys) * (cell + gap) + gap, 2 * (cell + gap) + gap), (0, 0, 0, 0))
    for c, (k, _n, d, r) in enumerate(TRAITS):
        for row, f in enumerate((d, r)):
            ic = _trait_pil(k, f, cell)
            im.alpha_composite(ic, (gap + c * (cell + gap) + (cell - ic.width) // 2,
                                    gap + row * (cell + gap) + (cell - ic.height) // 2))
    return _photo_label(parent, im, bg, "the 14 forms")


def _forms_strip(parent, bg, which, caption):
    from PIL import Image
    cell, gap = 28, 3
    im = Image.new("RGBA", (len(TRAITS) * (cell + gap) + gap, cell + 2 * gap), (0, 0, 0, 0))
    for c, (k, _n, d, r) in enumerate(TRAITS):
        ic = _trait_pil(k, r if which == "rec" else d, cell)
        im.alpha_composite(ic, (gap + c * (cell + gap) + (cell - ic.width) // 2,
                                gap + (cell - ic.height) // 2))
    return _photo_label(parent, im, bg, caption)


def pure_line_example(app, parent, bg):
    """Two true-breeding lines: a purple and a white parent, each with offspring all
    like it."""
    from PIL import Image, ImageDraw
    big, small, gap, n = 34, 22, 4, 5
    w = big + 22 + n * (small + gap) + 14
    h = 2 * (big + 8)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for row, col in enumerate(("purple", "white")):
        y = row * (big + 8) + 4
        par = _trait_pil("flower_color", col, big - 6)
        dr.rounded_rectangle((0, y, big, y + big), 6, outline=(217, 165, 32, 255), width=2)
        im.alpha_composite(par, ((big - par.width) // 2, y + (big - par.height) // 2))
        ay = y + big // 2
        dr.line((big + 4, ay, big + 16, ay), fill=(122, 106, 85, 255), width=2)
        dr.polygon([(big + 16, ay - 4), (big + 21, ay), (big + 16, ay + 4)], fill=(122, 106, 85, 255))
        ch = _trait_pil("flower_color", col, small)
        for i in range(n):
            x = big + 24 + i * (small + gap)
            im.alpha_composite(ch, (x, y + (big - ch.height) // 2))
        dr.text((w - 12, ay - 6), "\u2026", fill=(122, 106, 85, 255))
    return _photo_label(parent, im, bg, "two true breeders")


def island_example(app, parent, bg):
    """A small picture of one island: a white flower with purple ones on
    all eight plots around it (the game's flower icons, or plain dots)."""
    from PIL import Image, ImageDraw, ImageTk
    cell, gap = 40, 3
    size = 3 * cell + 4 * gap
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    icons = {}
    try:
        from icon_loader import trait_icon_path
        for col in ("white", "purple"):
            pth = trait_icon_path("flower_color", col)
            if pth:
                ic = Image.open(pth).convert("RGBA")
                bb = ic.getbbox()
                if bb:
                    ic = ic.crop(bb)
                ic.thumbnail((cell - 8, cell - 8), Image.LANCZOS)
                icons[col] = ic
    except Exception:
        icons = {}
    for r in range(3):
        for c in range(3):
            x, y = gap + c * (cell + gap), gap + r * (cell + gap)
            col = "white" if (r, c) == (1, 1) else "purple"
            # the plot: brown soil, the middle one framed
            dr.rounded_rectangle((x, y, x + cell, y + cell), 6, fill=(150, 112, 76, 255),
                                 outline=((217, 165, 32, 255) if col == "white"
                                          else (120, 88, 60, 255)),
                                 width=(3 if col == "white" else 1))
            ic = icons.get(col)
            if ic is not None:
                im.alpha_composite(ic, (x + (cell - ic.width) // 2, y + (cell - ic.height) // 2))
            else:
                fill = (250, 250, 245, 255) if col == "white" else (146, 92, 170, 255)
                dr.ellipse((x + 9, y + 9, x + cell - 9, y + cell - 9), fill=fill,
                           outline=(90, 70, 50, 255))
    photo = ImageTk.PhotoImage(im, master=parent)
    box = tk.Frame(parent, bg=bg)
    lbl = tk.Label(box, image=photo, bg=bg)
    lbl.image = photo
    lbl.pack()
    tk.Label(box, text="one island", font=("Segoe UI", 13, "italic"), bg=bg,
             fg=MUTED).pack()
    return box


def check_islands(app):
    import sys
    cols = getattr(sys.modules.get(type(app).__module__), "TILES_PER_ROW", None) or 16
    try:
        tiles = app._all_plot_tiles()
    except Exception:
        tiles = list(getattr(app, "tiles", []) or [])
    grid = {}
    for t in tiles:
        grid[(getattr(t, "plot_idx", 0), getattr(t, "idx", None))] = t

    def plant_at(plot, idx):
        t = grid.get((plot, idx))
        p = getattr(t, "plant", None) if t is not None else None
        return p if (p is not None and getattr(p, "alive", True)) else None

    islands, best_partial = [], 0
    for (plot, idx), t in grid.items():
        p = plant_at(plot, idx)
        if p is None or idx is None or _colour_shown(p) != "white":
            continue
        r, c = divmod(idx, cols)
        nbs = []
        for dr, dc in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
            rr, cc = r + dr, c + dc
            if rr < 0 or cc < 0 or cc >= cols:
                nbs.append(None)
                continue
            nbs.append(plant_at(plot, rr * cols + cc))
        purple = [q for q in nbs if q is not None and _colour_shown(q) == "purple"]
        best_partial = max(best_partial, len(purple))
        if len(purple) == 8 and _flowering(app, p) and all(_flowering(app, q) for q in purple):
            islands.append(idx)
    n = len(islands)
    items = [(f"White-flowering plants completely surrounded by purple ones: {min(n, ISLANDS_NEED)}"
              f"/{ISLANDS_NEED}", n >= ISLANDS_NEED),
             ("All of them in flower at the same time", n >= ISLANDS_NEED)]
    hint = "" if n >= ISLANDS_NEED else (
        f"{n} island{'s' if n != 1 else ''} ready: make {ISLANDS_NEED - n} more." if n else
        f"So far at most {best_partial} of the 8 plots around a white plant hold a purple one "
        "(the corners count too). Plants grown from the seeds of "
        "a true-breeding white or purple plant come true." if best_partial else
        "Sow seeds of true-breeding white and purple plants in a pattern: "
        "a white one in the middle, purple ones around it.")
    return Progress(n >= ISLANDS_NEED, items, hint)


# ---------------------------------------------------------------------------
# MEDIUM 1 — Reciprocal crosses
# ---------------------------------------------------------------------------

def check_reciprocal(app):
    """Both ways round: ♀A × ♂B and ♀B × ♂A (A, B of contrasting forms of
    one trait), each with enough offspring, all alike — and alike in both
    directions."""
    plants, fam = _cross_families(app)

    def need(trait):
        return RECIPROCAL_NEED_SEEDS if trait in SEED_TRAITS else RECIPROCAL_NEED_PLANTS

    # families by (trait, mother's form, father's form)
    by_dir = {}
    for (m, f), traits in fam.items():
        for key, *_ in TRAITS:
            cnt = traits.get(key)
            if not cnt:
                continue
            a, b = _known(plants.get(m), key), _known(plants.get(f), key)
            if not a or not b or a == b:
                continue
            by_dir.setdefault((key, a, b), []).append(((m, f), cnt))

    def best(key, a, b):
        """The most convincing family of ♀a × ♂b: uniform and large first."""
        fams = by_dir.get((key, a, b)) or []
        if not fams:
            return None
        return max(fams, key=lambda x: (len(x[1]) == 1, sum(x[1].values())))

    candidates = []
    for key, _name, dom, rec in TRAITS:
        for a, b in ((rec, dom), (dom, rec)):
            if a > b:
                continue                 # each pair once (the two directions below)
            d1, d2 = best(key, a, b), best(key, b, a)
            if d1 is None and d2 is None:
                continue
            n = need(key)

            def score(d):
                if d is None:
                    return 0
                c = d[1]
                return min(sum(c.values()), n) * (2 if len(c) == 1 else 1)
            candidates.append((score(d1) + score(d2), key, a, b, d1, d2))

    if not candidates:
        n_sown = sum(1 for sn in plants.values() if _is_cross(sn))
        if n_sown:
            return Progress(False, [
                (f"{n_sown} plant{'s' if n_sown != 1 else ''} grown from crossed seeds", True),
                ("Their traits show as they grow", False),
                ("The offspring look alike in both directions", False),
            ], "Raise the young plants until they show the trait (flower colour shows "
               "when they flower).")
        return Progress(False, [
            ("Cross two plants of contrasting forms (e.g. ♀ white × ♂ purple)", False),
            ("Cross them the other way round (♀ purple × ♂ white)", False),
            ("Raise their offspring until the trait shows", False),
            ("The offspring look alike in both directions", False),
        ], "Start with two plants that differ in one trait you can see, "
           "ideally true-breeding ones.")

    candidates.sort(key=lambda c: -c[0])
    done_any = None
    for _s, key, a, b, d1, d2 in candidates:
        n = need(key)
        if (d1 and d2 and len(d1[1]) == 1 and len(d2[1]) == 1
                and sum(d1[1].values()) >= n and sum(d2[1].values()) >= n
                and set(d1[1]) == set(d2[1])):
            done_any = (key, a, b, d1, d2)
            break
    _s, key, a, b, d1, d2 = candidates[0] if done_any is None else (0,) + done_any
    n = need(key)
    unit = "seeds" if key in SEED_TRAITS else "plants"
    shown = "harvested" if key in SEED_TRAITS else "showing their " + _TRAIT_NAME[key]

    # offspring of each cross sown so far (shown the trait or not yet)
    from collections import Counter as _C
    sown = _C()
    for sn in plants.values():
        if _is_cross(sn):
            sown[(sn["mom"], sn["dad"])] += 1

    def line(mf, ff, d):
        title = f"♀ {mf} × ♂ {ff}"
        if d is None:
            n_sown = sum(n for (mm, ff_), n in sown.items()
                         if _known(plants.get(mm), key) == mf
                         and _known(plants.get(ff_), key) == ff)
            if n_sown:
                return (f"{title}: {n_sown} plant{'s' if n_sown != 1 else ''} sown, "
                        f"not showing their {_TRAIT_NAME[key]} yet", False)
            return (f"{title}: not crossed yet", False)
        c = d[1]
        tot = sum(c.values())
        ok = tot >= n and len(c) == 1
        return (f"{title} (♀#{d[0][0]} × ♂#{d[0][1]}): {min(tot, n)}/{n} {unit} {shown}  "
                f"({_counts_line(c)})", ok)

    items = [line(a, b, d1), line(b, a, d2)]
    same = bool(d1 and d2 and len(d1[1]) == 1 and len(d2[1]) == 1 and set(d1[1]) == set(d2[1]))
    items.append(("The offspring look alike in both directions", same and all(t for _x, t in items)))

    mixed = [d for d in (d1, d2) if d is not None and len(d[1]) > 1]
    if done_any:
        hint = ""
    elif mixed:
        hint = ("Mixed offspring: one parent was not true-breeding. Choose parents whose "
                "own selfed offspring all look like them, and cross again.")
    elif d1 is None or d2 is None:
        hint = "Now make the same cross the other way round: swap mother and father."
    else:
        hint = f"Raise more offspring: {n} {unit} in each direction."
    return Progress(done_any is not None, items, hint)


# ---------------------------------------------------------------------------
# MEDIUM 2 — Three to one (the hidden form returns)
# ---------------------------------------------------------------------------

F2_NEED = 24                 # F2 plants that showed the trait
F2_REC_RANGE = (0.15, 0.35)  # share of the recessive form (3 : 1 is 0.25)


def _f1_differs(plants, f1, key):
    """Did the two parents of this hybrid differ in `key`?"""
    gm, gf = plants.get(f1["mom"]), plants.get(f1["dad"])
    a, b = _known(gm, key), _known(gf, key)
    return bool(a and b and a != b)


def _f2_counts(plants, app=None):
    """{trait key: Counter} over the F2 of crosses whose two parents
    differed in that trait: the selfed offspring of the hybrids (F1). Plant
    traits from the grandchildren raised that showed them; seed shape and
    colour from every seed the hybrids bore by themselves (they show on the
    pea, as Mendel counted them)."""
    from collections import Counter
    out = {}
    for s in plants.values():
        if not _is_selfed(s):
            continue
        f1 = plants.get(s["mom"])
        if not _is_cross(f1):
            continue
        for key, *_ in TRAITS:
            if key in SEED_TRAITS or not _f1_differs(plants, f1, key):
                continue
            v = _known(s, key)
            if v:
                out.setdefault(key, Counter())[v] += 1
    try:
        store = (getattr(app, "archive", {}) or {}).get("pod_seeds") or {} if app else {}
    except Exception:
        store = {}
    for m, recs in store.items():
        f1 = plants.get(str(m))
        if not _is_cross(f1):
            continue
        for key in SEED_TRAITS:
            if not _f1_differs(plants, f1, key):
                continue
            for r in recs or []:
                d = r.get("donor")
                if d not in (None, "") and str(d) != str(m):
                    continue                     # crossed again: not the F2
                v = _norm(r.get(key))
                if v:
                    out.setdefault(key, Counter())[v] += 1
    return out


def check_three_to_one(app):
    plants = _all_plants(app)
    counts = _f2_counts(plants, app)
    n_f1 = sum(1 for s in plants.values() if _is_cross(s))
    if not counts:
        n_f2 = sum(1 for s in plants.values()
                   if _is_selfed(s) and _is_cross(plants.get(s["mom"])))
        items = [("Cross two plants that differ in one trait", n_f1 > 0),
                 ("Let the hybrids (F1) pollinate themselves and sow their seeds", n_f2 > 0),
                 (f"Raise {F2_NEED} of these grandchildren (F2) until the trait shows", False),
                 ("Both forms are back, about three to one", False),
                 ("Law of Segregation unlocked with the wizard (\u00bbUnlock Laws\u00ab)",
                  bool(getattr(app, "law2_ever_discovered", False)))]
        hint = ("Wait until the grandchildren show the trait." if n_f2 else
                "Harvest the seeds of the young hybrids and sow them." if n_f1 else
                "Begin with two true-breeding plants of contrasting forms, e.g. purple and white.")
        return Progress(False, items, hint)

    def score(item):
        key, c = item
        tot = sum(c.values())
        rec = c.get(_recessive(key), 0) / tot if tot else 0
        ok = tot >= F2_NEED and F2_REC_RANGE[0] <= rec <= F2_REC_RANGE[1]
        return (ok, min(tot, F2_NEED), tot)
    key, c = max(counts.items(), key=score)
    tot = sum(c.values())
    rec = c.get(_recessive(key), 0)
    share = rec / tot if tot else 0
    ok_ratio = F2_REC_RANGE[0] <= share <= F2_REC_RANGE[1]
    done = tot >= F2_NEED and ok_ratio
    ratio = f"{(tot - rec) / rec:.2f} : 1" if rec else "no recessive form yet"
    law = bool(getattr(app, "law2_ever_discovered", False))
    items = [("Hybrids (F1) raised", True),
             (f"Grandchildren (F2) showing their {_TRAIT_NAME[key]}: {min(tot, F2_NEED)}/{F2_NEED}  "
              f"({_counts_line(c)})", tot >= F2_NEED),
             (f"Both forms are back, about three to one (now {ratio})", done),
             ("Law of Segregation unlocked with the wizard (\u00bbUnlock Laws\u00ab)", law)]
    hint = "" if (done and law) else (
        f"Raise more grandchildren: {F2_NEED} that show the trait." if tot < F2_NEED else
        "The ratio is still far from 3 : 1: raise more plants, the numbers even out."
        if not done else
        "Now claim it: open \u00bbUnlock Laws\u00ab and unlock the Law of Segregation "
        "with your grandchildren.")
    return Progress(done and law, items, hint)


# ---------------------------------------------------------------------------
# MEDIUM 3 — The test cross
# ---------------------------------------------------------------------------

TEST_NEED = 12
TEST_REC_RANGE = (0.3, 0.7)        # 1 : 1 is 0.5


def check_test_cross(app):
    """A hybrid (grown from a cross of contrasting parents, showing the
    dominant form) crossed with a plant of the recessive form: about half
    of the offspring show the recessive form."""
    plants, fam = _cross_families(app)
    from collections import Counter
    pooled = {}
    for (m, f), traits in fam.items():
        for key, *_ in TRAITS:
            c = traits.get(key)
            if not c:
                continue
            rec, dom = _recessive(key), _dominant(key)
            pm, pf = plants.get(m), plants.get(f)
            for hyb, other in ((pm, pf), (pf, pm)):
                if not _is_cross(hyb) or _known(hyb, key) != dom or _known(other, key) != rec:
                    continue
                gm, gf = plants.get(hyb["mom"]), plants.get(hyb["dad"])
                if {_known(gm, key), _known(gf, key)} != {dom, rec}:
                    continue
                pooled.setdefault(key, Counter()).update(c)
                break
    if not pooled:
        n_f1 = sum(1 for s in plants.values() if _is_cross(s))
        items = [("Raise a hybrid: a plant grown from a cross of two contrasting plants", n_f1 > 0),
                 ("Cross it with a plant of the recessive form (e.g. white flowers)", False),
                 (f"Raise {TEST_NEED} offspring until the trait shows", False),
                 ("About half of them show the recessive form", False)]
        hint = ("Cross one of your hybrids with a recessive plant, and raise the offspring."
                if n_f1 else "First raise hybrids: cross two true-breeding plants of "
                             "contrasting forms.")
        return Progress(False, items, hint)

    def score(item):
        key, c = item
        tot = sum(c.values())
        share = c.get(_recessive(key), 0) / tot if tot else 0
        ok = tot >= TEST_NEED and TEST_REC_RANGE[0] <= share <= TEST_REC_RANGE[1]
        return (ok, min(tot, TEST_NEED), tot)
    key, c = max(pooled.items(), key=score)
    tot = sum(c.values())
    rec = c.get(_recessive(key), 0)
    share = rec / tot if tot else 0
    done = tot >= TEST_NEED and TEST_REC_RANGE[0] <= share <= TEST_REC_RANGE[1]
    items = [("Hybrid crossed with a recessive plant", True),
             (f"Offspring showing their {_TRAIT_NAME[key]}: {min(tot, TEST_NEED)}/{TEST_NEED}  "
              f"({_counts_line(c)})", tot >= TEST_NEED),
             (f"About half show the recessive form (now {round(share * 100)} %)", done)]
    hint = "" if done else (
        f"Raise more offspring: {TEST_NEED} that show the trait." if tot < TEST_NEED else
        "Still far from half and half: raise more plants.")
    return Progress(done, items, hint)


# ---------------------------------------------------------------------------
# HARD — Mendel's numbers: a close 3 : 1 over many plants
# ---------------------------------------------------------------------------

CLOSE_NEED = 101                 # more than 100
CLOSE_RANGE = (2.9, 3.1)


def check_close_ratio(app):
    plants = _all_plants(app)
    counts = _f2_counts(plants, app)
    if not counts:
        return Progress(False, [
            ("Cross two true-breeding lines and let their hybrids pollinate themselves", False),
            (f"More than {CLOSE_NEED - 1} grandchildren (F2) counted for one trait", False),
            (f"Their ratio between {CLOSE_RANGE[0]:.1f} : 1 and {CLOSE_RANGE[1]:.1f} : 1", False),
        ], "Seed shape and colour count on every pea the hybrids bear: the quickest way "
           "to large numbers.")

    def ratio(c, key):
        rec = c.get(_recessive(key), 0)
        return (sum(c.values()) - rec) / rec if rec else None

    def score(item):
        key, c = item
        tot = sum(c.values())
        r = ratio(c, key)
        ok = tot >= CLOSE_NEED and r is not None and CLOSE_RANGE[0] <= r <= CLOSE_RANGE[1]
        return (ok, min(tot, CLOSE_NEED), -abs((r or 0) - 3))
    key, c = max(counts.items(), key=score)
    tot = sum(c.values())
    r = ratio(c, key)
    ok_r = r is not None and CLOSE_RANGE[0] <= r <= CLOSE_RANGE[1]
    done = tot >= CLOSE_NEED and ok_r
    rtxt = f"{r:.2f} : 1" if r is not None else "no recessive form yet"
    items = [("Hybrids selfed, grandchildren counted", True),
             (f"{_TRAIT_NAME[key].capitalize()}: {tot} counted, more than {CLOSE_NEED - 1} "
              f"needed  ({_counts_line(c)})", tot >= CLOSE_NEED),
             (f"Ratio {rtxt}, between {CLOSE_RANGE[0]:.1f} and {CLOSE_RANGE[1]:.1f}", done)]
    hint = "" if done else (
        "Count more: the more plants, the closer the numbers come to 3 : 1." if tot < CLOSE_NEED
        else f"{rtxt} is not close enough yet: keep counting, chance evens out.")
    return Progress(done, items, hint)


# ---------------------------------------------------------------------------
# HARD 1 — True to type (a random combination of three traits)
# ---------------------------------------------------------------------------

TRUE_NEED = 8


def setup_true_to_type(app):
    import random
    keys = random.sample([k for k, *_ in TRAITS], 3)
    order = [k for k, *_ in TRAITS]
    keys.sort(key=order.index)
    target = []
    for k in keys:
        _k, _n, dom, rec = next(t for t in TRAITS if t[0] == k)
        target.append([k, random.choice([dom, rec])])
    # at least one dominant form: those take the real work (a true-breeding line)
    if all(f == _recessive(k) for k, f in target):
        target[0][1] = _dominant(target[0][0])
    return {"target": target}


def _targets(app):
    p = getattr(app, "_active_mission_params", None) or {}
    return [(k, f) for k, f in (p.get("target") or [])]


def _target_text(target):
    return ", ".join(_form_label(k, f) for k, f in target)


def check_true_to_type(app):
    target = _targets(app)
    if not target:
        return Progress(False, [("Accept the mission to receive your three traits", False)], "")
    plants = _all_plants(app)
    kids = _selfed_children(plants)

    def has_all(s):
        return all(_known(s, k) == f for k, f in target)

    def all_known(s):
        return all(_known(s, k) for k, _f in target)

    cands = [pid for pid, s in plants.items() if has_all(s)]
    best = None
    for pid in cands:
        ch = [k for k in kids.get(pid, []) if all_known(k)]
        good = sum(1 for k in ch if has_all(k))
        bad = len(ch) - good
        score = (bad == 0 and good >= TRUE_NEED, bad == 0, min(good, TRUE_NEED), -bad)
        if best is None or score > best[0]:
            best = (score, pid, good, bad)
    items = [(f"A plant with {_target_text(target)}", bool(cands))]
    if best is None:
        items += [(f"{TRUE_NEED} of its selfed offspring showing all three traits", False),
                  ("Every one of them like their parent", False)]
        hint = ("Cross plants that together have all three traits, then select among their "
                "offspring and grandchildren. Recessive forms breed true at once; a dominant "
                "form only when its seeds never bring up the other form.")
        return Progress(False, items, hint)
    _s, pid, good, bad = best
    done = bad == 0 and good >= TRUE_NEED
    items += [(f"#{pid}: {min(good + bad, TRUE_NEED)}/{TRUE_NEED} selfed offspring showing all "
               f"three traits", good + bad >= TRUE_NEED),
              ("Every one of them like their parent" + (f" ({bad} differ)" if bad else ""), done)]
    hint = "" if done else (
        f"#{pid} still carries a hidden form: some of its offspring differ. Take the seeds "
        "of one of its offspring that looks right and test that one." if bad else
        "Raise more of its selfed offspring until all three traits show.")
    return Progress(done, items, hint)


# ---------------------------------------------------------------------------
# HARD 2 — Six generations
# ---------------------------------------------------------------------------

SIX_NEED = 6


def check_six_generations(app):
    plants = _all_plants(app)
    memo = {}
    top = 0
    top_pid = None
    for pid, s in plants.items():
        g = _filial(plants, pid, memo)
        if g and _known(s, "flower_color") and g > top:
            top, top_pid = g, pid
    items = [("Cross two plants", any(_is_cross(s) for s in plants.values())),
             ("Let the line pollinate itself, generation after generation", top >= 2),
             (f"A plant of the F{SIX_NEED} in flower (furthest so far: "
              f"{'F' + str(top) if top else 'none'}"
              f"{f', #{top_pid}' if top_pid else ''})", top >= SIX_NEED)]
    hint = "" if top >= SIX_NEED else (
        "Sow the seeds of one plant of each generation and wait until it flowers. "
        "The F-numbers in the Choose Seeds window (Seeds from crosses) help." if top else
        "Begin with a cross; its seeds grow into the F1.")
    return Progress(top >= SIX_NEED, items, hint)


# ---------------------------------------------------------------------------
# HARD 3 — Two traits at once (9 : 3 : 3 : 1)
# ---------------------------------------------------------------------------

DI_NEED = 48
DI_CHI2_MAX = 7.81           # 3 degrees of freedom, 5 %


def check_dihybrid(app):
    from collections import Counter
    plants = _all_plants(app)
    best = None
    pairs = {}
    for s in plants.values():
        if not _is_selfed(s):
            continue
        f1 = plants.get(s["mom"])
        if not _is_cross(f1):
            continue
        gm, gf = plants.get(f1["mom"]), plants.get(f1["dad"])
        diff = [k for k, *_ in TRAITS
                if _known(gm, k) and _known(gf, k) and _known(gm, k) != _known(gf, k)]
        for i in range(len(diff)):
            for j in range(i + 1, len(diff)):
                k1, k2 = diff[i], diff[j]
                if k1 in SEED_TRAITS and k2 in SEED_TRAITS:
                    continue            # counted on the peas themselves, below
                v1, v2 = _known(s, k1), _known(s, k2)
                if v1 and v2:
                    pairs.setdefault((k1, k2), Counter())[
                        (v1 == _dominant(k1), v2 == _dominant(k2))] += 1
    # seed shape with seed colour: every pea the hybrids bore by themselves
    try:
        store = (getattr(app, "archive", {}) or {}).get("pod_seeds") or {}
    except Exception:
        store = {}
    k1, k2 = "seed_shape", "seed_color"
    for m, recs in store.items():
        f1 = plants.get(str(m))
        if not _is_cross(f1) or not (_f1_differs(plants, f1, k1) and _f1_differs(plants, f1, k2)):
            continue
        for r in recs or []:
            d = r.get("donor")
            if d not in (None, "") and str(d) != str(m):
                continue
            v1, v2 = _norm(r.get(k1)), _norm(r.get(k2))
            if v1 and v2:
                pairs.setdefault((k1, k2), Counter())[
                    (v1 == _dominant(k1), v2 == _dominant(k2))] += 1
    for (k1, k2), c in pairs.items():
        n = sum(c.values())
        exp = {(True, True): 9 / 16, (True, False): 3 / 16, (False, True): 3 / 16,
               (False, False): 1 / 16}
        chi2 = sum((c.get(cl, 0) - n * p) ** 2 / (n * p) for cl, p in exp.items()) if n else 99
        ok = n >= DI_NEED and all(c.get(cl, 0) for cl in exp) and chi2 <= DI_CHI2_MAX
        score = (ok, min(n, DI_NEED), -chi2)
        if best is None or score > best[0]:
            best = (score, k1, k2, c, n, chi2)
    if best is None:
        items = [("Cross two plants that differ in two traits", False),
                 ("Let the hybrids (F1) pollinate themselves and sow their seeds", False),
                 (f"Raise {DI_NEED} grandchildren (F2) that show both traits", False),
                 ("All four combinations, about 9 : 3 : 3 : 1", False)]
        return Progress(False, items, "Round yellow × wrinkled green is Mendel's own pair: "
                                      "seed traits show as soon as you sow.")
    (ok, _g, _c), k1, k2, c, n, chi2 = best
    d1, r1, d2, r2 = _dominant(k1), _recessive(k1), _dominant(k2), _recessive(k2)
    classes = " : ".join(str(c.get(cl, 0)) for cl in ((True, True), (True, False),
                                                       (False, True), (False, False)))
    items = [(f"Cross differing in {_TRAIT_NAME[k1]} and {_TRAIT_NAME[k2]}, hybrids selfed", True),
             (f"F2 showing both traits: {min(n, DI_NEED)}/{DI_NEED}", n >= DI_NEED),
             (f"{d1}+{d2} : {d1}+{r2} : {r1}+{d2} : {r1}+{r2} = {classes}  "
              f"(close to 9 : 3 : 3 : 1? {'yes' if chi2 <= DI_CHI2_MAX else 'not yet'})", ok)]
    hint = "" if ok else (
        f"Raise more grandchildren: {DI_NEED} that show both traits." if n < DI_NEED else
        "Not close to 9 : 3 : 3 : 1 yet: raise more plants.")
    return Progress(ok, items, hint)


# ---------------------------------------------------------------------------
# MEDIUM — The hidden seven (all seven recessive forms in one plant)
# ---------------------------------------------------------------------------

def check_hidden_seven(app):
    plants = _all_plants(app)
    best = None
    for pid, s in plants.items():
        if s.get("mom") is None:
            continue                     # bred in this garden, not a starter
        shown = [(k, _known(s, k)) for k, *_ in TRAITS]
        n_rec = sum(1 for k, v in shown if v == _recessive(k))
        n_known = sum(1 for _k, v in shown if v)
        score = (n_rec, n_known)
        if best is None or score > best[0]:
            best = (score, pid, dict(shown))
    rec_forms = [(k, _recessive(k)) for k, *_ in TRAITS]
    if best is None:
        icons = [(k, f, False) for k, f in rec_forms]
        return Progress(False, [("A plant bred in this garden with all seven recessive forms",
                                 False, icons)],
                        "Cross plants that carry the recessive forms, then let their offspring "
                        "pollinate themselves: hidden forms come out in the grandchildren.")
    (n_rec, _n), pid, shown = best
    icons = [(k, f, shown.get(k) == f) for k, f in rec_forms]
    done = n_rec == 7
    items = [(f"#{pid}: {n_rec} of the 7 recessive forms", done, icons)]
    missing = [_form_label(k, f) for k, f in rec_forms if shown.get(k) != f]
    hint = "" if done else ("Still missing on this plant: " + ", ".join(missing) + ". Some may "
                            "only not have shown yet (flowers, pods).")
    return Progress(done, items, hint)


# ---------------------------------------------------------------------------
# MEDIUM — Plant roulette: predict the offspring from the family tree
# ---------------------------------------------------------------------------

ROULETTE_NEED_PLANTS = 12        # offspring showing a plant trait
ROULETTE_NEED_SEEDS = 12         # or harvested seeds (seed shape / colour)

# one locus per trait for the roulette's plant (the others fixed so every
# trait follows a plain 3 : 1): pod shape uses P (V fixed VV), flower
# position Fa (Mfa fixed MfaMfa)
_LOCUS = {"seed_shape": "R", "seed_color": "I", "flower_color": "A", "plant_height": "Le",
          "pod_color": "Gp", "pod_shape": "P", "flower_position": "Fa"}
_FIXED = {"V": ("V", "V"), "Mfa": ("Mfa", "Mfa")}

# the four predictions per trait
PREDICT = (("all_dom", "only {dom}"), ("more_dom", "more {dom} than {rec}"),
           ("more_rec", "more {rec} than {dom}"), ("all_rec", "only {rec}"))


def _rparams(app):
    return getattr(app, "_active_mission_params", None) or {}


def _pred_text(key, choice):
    d, r = _form_label(key, _dominant(key)), _form_label(key, _recessive(key))
    for c, t in PREDICT:
        if c == choice:
            return t.format(dom=d, rec=r)
    return "?"


def _pred_ok(key, choice, c):
    d, r = c.get(_dominant(key), 0), c.get(_recessive(key), 0)
    return {"all_dom": d > 0 and r == 0, "all_rec": r > 0 and d == 0,
            "more_dom": d > r and r > 0, "more_rec": r > d and d > 0}.get(choice, False)


def _roulette_counts(app, plants, xid, key):
    """The selfed offspring of the roulette plant: harvested seeds for seed
    shape / colour, raised plants that showed it for the others."""
    from collections import Counter
    c = Counter()
    if key in SEED_TRAITS:
        try:
            recs = ((getattr(app, "archive", {}) or {}).get("pod_seeds") or {}).get(str(xid)) or []
        except Exception:
            recs = []
        for r in recs:
            dn = r.get("donor")
            if dn not in (None, "") and str(dn) != str(xid):
                continue
            v = _norm(r.get(key))
            if v:
                c[v] += 1
    else:
        for s in plants.values():
            if _is_selfed(s) and s["mom"] == str(xid):
                v = _known(s, key)
                if v:
                    c[v] += 1
    return c


def check_roulette(app):
    p = _rparams(app)
    traits = p.get("traits") or []
    xid = p.get("x")
    if len(traits) < 3 or xid is None:
        return Progress(False, [("Spin the wheel three times", False)],
                        "The wheel opens when you accept the mission.")
    preds = p.get("predictions") or {}
    plants = _all_plants(app)
    items = [(f"Study #{xid} and its family tree in the TIE", bool(preds)),
             ("Seal your predictions (before the first pod is opened)", bool(preds))]
    all_counted, all_ok = True, True
    for key in traits:
        c = _roulette_counts(app, plants, xid, key)
        need = ROULETTE_NEED_SEEDS if key in SEED_TRAITS else ROULETTE_NEED_PLANTS
        tot = sum(c.values())
        counted = tot >= need
        ok = counted and preds.get(key) is not None and _pred_ok(key, preds.get(key), c)
        all_counted &= counted
        all_ok &= ok
        said = _pred_text(key, preds[key]) if key in preds else "no prediction yet"
        unit = "seeds" if key in SEED_TRAITS else "plants"
        verdict = "" if not counted else ("  ✔ right" if ok else "  ✘ wrong")
        items.append((f"{_TRAIT_NAME[key].capitalize()}: you said »{said}« — "
                      f"{min(tot, need)}/{need} {unit}"
                      + (f" ({_counts_line(c)})" if tot else "") + verdict, ok,
                      [(key, _dominant(key), True), (key, _recessive(key), True)]))
    prog = Progress(bool(preds) and all_counted and all_ok, items)
    prog.failed = bool(preds) and all_counted and not all_ok
    if not preds:
        prog.hint = (f"Open the TIE for #{xid}: its parents and grandparents tell you what "
                     "its seeds will grow into. Your predictions are asked for when you "
                     "harvest its first pod.")
    elif not all_counted:
        prog.hint = ("Harvest all its pods, sow the seeds and raise the young plants until "
                     "the traits show.")
    return prog


def tie_family_only(app):
    """The TIE shows only the family tree while Plant Roulette is played
    (its pod, Punnett and ratio views would give the answer away)."""
    am = active_mission(app)
    return bool(am is not None and am["key"] == "mission_roulette"
                and _rparams(app).get("x") is not None)


def before_harvest(app, plant, action=None):
    """Called before a pod is harvested: the roulette plant's first pod
    waits for the player's predictions. False = don't harvest now; the
    harvest (`action`) is done once the predictions are sealed."""
    m = active_mission(app)
    if m is None or m["key"] != "mission_roulette":
        return True
    p = _rparams(app)
    if str(getattr(plant, "id", "")) != str(p.get("x")) or p.get("predictions"):
        return True
    app._roulette_pending_harvest = action
    open_prediction(app)
    return False


def open_prediction(app):
    """The predictions for the three traits: one of four answers each,
    sealed with one button (they can't be changed afterwards)."""
    old = getattr(app, "_roulette_pred_win", None)
    try:
        if old is not None and old.winfo_exists():
            old.lift()
            return old
    except Exception:
        pass
    p = _rparams(app)
    traits = p.get("traits") or []
    bg = getattr(app, "INSPECTOR_BG", BG)
    win = tk.Toplevel(app.root)
    app._roulette_pred_win = win
    win.title("Your predictions")
    win.configure(bg=bg)
    win.resizable(False, False)
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    outer = tk.Frame(win, bg=bg, padx=22, pady=16)
    outer.pack(fill="both", expand=True)
    tk.Label(outer, text="Before you open the first pod…", font=("Segoe UI", 18, "bold"),
             bg=bg, fg=INK).pack(anchor="w")
    tk.Label(outer, text=f"What will the seeds of #{p.get('x')} grow into? Choose for each "
                         "trait. Once sealed, the predictions can't be changed.",
             font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED, wraplength=520,
             justify="left").pack(anchor="w", pady=(2, 10))
    vars_ = {}
    for key in traits:
        box = tk.Frame(outer, bg=CARD, highlightbackground=EDGE, highlightthickness=1,
                       padx=12, pady=8)
        box.pack(fill="x", pady=4)
        tk.Label(box, text=_TRAIT_NAME[key].capitalize(), font=("Segoe UI", 15, "bold"),
                 bg=CARD, fg=INK).pack(anchor="w")
        v = tk.StringVar(value="")
        vars_[key] = v
        opts = tk.Frame(box, bg=CARD)
        opts.pack(fill="x", pady=(4, 0))
        d_, r_ = _dominant(key), _recessive(key)
        # each answer as pictures: [form] 100 %  or  [form] > [form]
        shapes = {"all_dom": (d_, "100 %", None), "more_dom": (d_, ">", r_),
                  "more_rec": (r_, ">", d_), "all_rec": (r_, "100 %", None)}
        # chosen like a bud in the inspection window: click it, it lights up
        # (one answer per trait)
        cells = {}

        def _paint(v=v, cells=cells):
            for c_, (cl, ws) in cells.items():
                on = (v.get() == c_)
                hov = getattr(cl, "_hover", False)
                colr = SEL_BG if on else (HOVER_BG if hov else CARD)
                cl.configure(bg=colr, highlightbackground=(SEL_EDGE if on else CARD))
                for w_ in ws:
                    try:
                        w_.configure(bg=colr)
                        for ww in w_.winfo_children():
                            ww.configure(bg=colr)
                    except Exception:
                        pass

        for i, (c, _t) in enumerate(PREDICT):
            a, sign, b = shapes[c]
            cell = tk.Frame(opts, bg=CARD, cursor="hand2", padx=8, pady=4,
                            highlightthickness=2, highlightbackground=CARD)
            cell.grid(row=0, column=2 * i, sticky="w")
            if i < len(PREDICT) - 1:
                # a thin line between the answers
                tk.Frame(opts, bg=EDGE, width=1).grid(row=0, column=2 * i + 1, sticky="ns",
                                                      padx=8, pady=4)
            parts = [_photo_label(cell, _trait_pil(key, a, 34), CARD),
                     tk.Label(cell, text=sign, font=("Segoe UI", 15, "bold"), bg=CARD, fg=INK)]
            if b is not None:
                parts.append(_photo_label(cell, _trait_pil(key, b, 34), CARD))
            for w_ in parts:
                w_.pack(side="left", padx=2)
            cells[c] = (cell, parts)

            def _pick(e=None, v=v, c=c, paint=_paint):
                v.set(c)
                paint()
                _upd()

            def _hover(e, on, cell=cell, paint=_paint):
                # icons and signs are one answer: moving between them inside
                # it is no leaving (only the pointer leaving the whole answer is)
                if not on:
                    try:
                        w_ = cell.winfo_containing(e.x_root, e.y_root)
                        while w_ is not None:
                            if w_ is cell:
                                return
                            w_ = w_.master
                    except Exception:
                        pass
                if getattr(cell, "_hover", False) == on:
                    return
                cell._hover = on
                paint()
                # the answer in words, under it, while the pointer is on it
                tip = getattr(cell, "_tip", None)
                if tip is not None:
                    try:
                        tip.destroy()
                    except Exception:
                        pass
                    cell._tip = None
                if on:
                    try:
                        t = tk.Toplevel(cell)
                        t.overrideredirect(True)
                        t.attributes("-topmost", True)
                        tk.Label(t, text=cell._words, font=("Segoe UI", 12), bg="#ffffe0",
                                 relief="solid", borderwidth=1, padx=4, pady=2).pack()
                        t.geometry(f"+{cell.winfo_rootx() + 8}+"
                                   f"{cell.winfo_rooty() + cell.winfo_height() + 4}")
                        cell._tip = t
                    except Exception:
                        pass
            for ww in [cell] + parts + [x for w_ in parts for x in w_.winfo_children()]:
                _click(app, ww, _pick)
                ww.bind("<Enter>", lambda e, h=_hover: h(e, True))
                ww.bind("<Leave>", lambda e, h=_hover: h(e, False))
                try:
                    ww.configure(cursor="hand2")
                except Exception:
                    pass
            cell._words = _pred_text(key, c)
    bar = tk.Frame(outer, bg=bg)
    bar.pack(fill="x", pady=(12, 0))
    note = tk.Label(bar, text="", font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED)
    note.pack(side="left")

    def _seal():
        if not all(v.get() for v in vars_.values()):
            note.configure(text="Choose an answer for every trait first.")
            return
        p["predictions"] = {k: v.get() for k, v in vars_.items()}
        app._active_mission_params = p
        try:
            win.destroy()
        except Exception:
            pass
        try:
            app._toast("Predictions sealed. Now harvest the pods, sow the seeds and see.",
                       level="info", duration=5000)
        except Exception:
            pass
        _refresh_board(app)
        # the harvest that was waiting for the predictions goes ahead now
        act = getattr(app, "_roulette_pending_harvest", None)
        app._roulette_pending_harvest = None
        if callable(act):
            try:
                app.root.after(150, act)
            except Exception:
                pass

    def _upd():
        note.configure(text="")
    mk = getattr(app, "_make_flat_button", None)
    btn = (mk(bar, "Seal predictions", _seal, bg="#7A9A3C", fg="white",
              font=("Segoe UI", 14, "bold")) if mk else
           tk.Button(bar, text="Seal predictions", command=_seal))
    btn.pack(side="right")
    later = (mk(bar, "Later", win.destroy, bg="#e0dccf", fg="#333333", font=("Segoe UI", 13))
             if mk else tk.Button(bar, text="Later", command=win.destroy))
    later.pack(side="right", padx=(0, 8))
    try:
        app._center_on_screen(win)
    except Exception:
        pass
    win.lift()
    return win


def _roulette_genotypes(traits, rng):
    """Genotypes for the roulette plant X, its parents M (seed) and F
    (pollen) and their parents (each true-breeding line: like its child). For each
    trait drawn: X a hybrid (M and F of contrasting true-breeding lines), or a pure
    line of the dominant or of the recessive form. Every other trait: one
    pure form for the whole family."""
    m, f = {}, {}
    for key, loc in _LOCUS.items():
        dom, rec = (loc, loc), (loc.lower(), loc.lower())
        if key in traits:
            kind = rng.choices(("hybrid", "pure_dom", "pure_rec"), weights=(5, 3, 2))[0]
        else:
            kind = rng.choice(("pure_dom", "pure_rec"))
        if kind == "hybrid":
            a, b = (dom, rec) if rng.random() < 0.5 else (rec, dom)
        elif kind == "pure_dom":
            a = b = dom
        else:
            a = b = rec
        m[loc], f[loc] = a, b
    for loc, pair in _FIXED.items():
        m[loc] = f[loc] = pair
    x = {loc: (m[loc][0], f[loc][0]) for loc in m}
    return m, f, x


def build_roulette_garden(app, traits):
    """The roulette's garden: a single plant in the middle (budding, so
    it flowers and pollinates itself), with its parents and grandparents
    in the archive for the TIE's family tree."""
    import random, sys
    mod = sys.modules.get(type(app).__module__)
    pheno = getattr(mod, "phenotype_from_genotype")
    rows = getattr(mod, "ROWS", 7)
    cols = getattr(mod, "TILES_PER_ROW", 16)
    rng = random.Random()
    gm, gf, gx = _roulette_genotypes(traits, rng)

    def traits_of(g):
        t = dict(pheno(g))
        return t

    arch = app.archive.setdefault("plants", {})
    ids = {}
    for name in ("mm", "mf", "fm", "ff", "m", "f"):
        ids[name] = app._next_id()

    def snap(pid, g, mom, dad, gen):
        t = traits_of(g)
        s = {"id": pid, "generation": gen, "traits": t, "revealed_traits": dict(t),
             "genotype": {k: tuple(v) for k, v in g.items()},
             "seed_parent_id": mom, "pollen_parent_id": dad,
             "ancestry": [], "paternal_ancestry": []}
        if mom is not None and dad is not None:
            s["mother_id"], s["father_id"] = (min(mom, dad), max(mom, dad)) if mom != dad else (mom, dad)
        else:
            s["mother_id"] = s["father_id"] = None
        arch[str(pid)] = s
    # grandparents: true-breeding lines, like their child
    snap(ids["mm"], gm, None, None, "F0")
    snap(ids["mf"], gm, None, None, "F0")
    snap(ids["fm"], gf, None, None, "F0")
    snap(ids["ff"], gf, None, None, "F0")
    snap(ids["m"], gm, ids["mm"], ids["mf"], "F1")
    snap(ids["f"], gf, ids["fm"], ids["ff"], "F1")

    # the plant itself, in the middle of garden 1
    from plant import Plant
    xid = app._next_id()
    xt = traits_of(gx)
    p = Plant(id=xid, env=app.garden, stage=1, generation="F2", traits=dict(xt))
    p.genotype = {k: tuple(v) for k, v in gx.items()}
    p.mother_id, p.father_id = min(ids["m"], ids["f"]), max(ids["m"], ids["f"])
    p.seed_parent_id, p.pollen_parent_id = ids["m"], ids["f"]
    p.selfed = False
    p.health = 100
    p.water = 70
    try:
        from plant import get_lifecycle_settings
        th = get_lifecycle_settings(p.difficulty)["base_thresholds"]
        p.germination_delay = 0
        p.stage = 4
        p.days_since_planting = th[4] + 0.2 * (th[5] - th[4])
    except Exception:
        pass
    # what a budding plant has shown: its seed (sown), its height
    for k in ("seed_shape", "seed_color", "plant_height"):
        p.revealed_traits[k] = xt[k]
    # the middle plot — or the nearest one that is a plain plot (not the
    # beehive or the measuring station)
    mid = (rows // 2) * cols + cols // 2

    def _plain(i):
        try:
            t = app.tiles[i]
            return (not getattr(t, "special_object", None) and not getattr(t, "locked", False)
                    and getattr(t, "plant", None) is None)
        except Exception:
            return False
    r0, c0 = divmod(mid, cols)
    cands = sorted(range(rows * cols), key=lambda i: (abs(i // cols - r0) + abs(i % cols - c0),
                                                      abs(i % cols - c0)))
    idx = next((i for i in cands if _plain(i)), mid)
    try:
        if getattr(app, "active_plot_index", 0) != 0:
            app._switch_to_plot(0)
    except Exception:
        pass
    app.tiles[idx].plant = p
    try:
        app._force_tile_soil(idx)
    except Exception:
        pass
    try:
        app.archive_snapshot(p)
    except Exception:
        pass
    # nothing else to sow: this plant is the whole garden
    app.available_seeds = 0
    app.harvest_inventory = []
    try:
        app._refresh_seed_counter_var()
    except Exception:
        pass
    app.selected_index = idx
    try:
        app.render_all()
    except Exception:
        pass
    return xid


def roulette_state(app):
    """The wheel's state, kept while the board is rebuilt or reopened."""
    st = getattr(app, "_roulette_state", None)
    if not isinstance(st, dict):
        st = app._roulette_state = {"angle": 90.0, "picked": [], "spinning": False}
    return st


def roulette_panel(app, parent, bg):
    """The wheel, inside the mission card's »Roulette« tab: seven traits,
    spun three times; a trait drawn is locked (it can't come again). Then
    the garden with the single plant opens."""
    import math, random
    outer = tk.Frame(parent, bg=bg)
    tk.Label(outer, text="Spin three times: the three traits you will have to predict.",
             font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED).pack(pady=(0, 6))
    S = 340
    R = 150
    # the wheel on the left, the three places for what it draws on the right
    mid = tk.Frame(outer, bg=bg)
    mid.pack(fill="x")
    cv = tk.Canvas(mid, width=S, height=S + 14, bg=bg, highlightthickness=0)
    cv.pack(side="left")
    keys = [k for k, *_ in TRAITS]
    n = len(keys)
    COLS = ("#c9a3d6", "#e8d27a", "#a9cf7f", "#9fc6a0", "#d9b98a", "#b7d47e", "#d7a7b8")
    st = roulette_state(app)
    picked_box = tk.Frame(mid, bg=bg, width=290)
    picked_box.pack(side="left", fill="y", padx=(24, 0))
    bar = tk.Frame(outer, bg=bg)
    bar.pack(fill="x", pady=(10, 0))
    cx, cy = S / 2, S / 2 + 12

    def draw():
        cv.delete("all")
        ext = 360.0 / n
        for i, k in enumerate(keys):
            start = st["angle"] + i * ext
            locked = k in st["picked"]
            cv.create_arc(cx - R, cy - R, cx + R, cy + R, start=start, extent=ext,
                          fill=("#d8d2c4" if locked else COLS[i % len(COLS)]),
                          outline="#6b5a44", width=2)
            mid = math.radians(start + ext / 2)
            tx, ty = cx + math.cos(mid) * R * 0.64, cy - math.sin(mid) * R * 0.64
            label = _TRAIT_NAME[k].replace(" ", "\n", 1)
            cv.create_text(tx, ty, text=("\U0001F512\n" if locked else "") + label,
                           font=("Segoe UI", 13, "bold"),
                           fill=("#9a9080" if locked else INK), justify="center")
        cv.create_oval(cx - 18, cy - 18, cx + 18, cy + 18, fill="#8B4226", outline="#5C2810",
                       width=2)
        # the pointer at the top
        cv.create_polygon(cx - 13, 2, cx + 13, 2, cx, 30, fill="#B02A2A", outline="#5C2810",
                          width=2)

    def sector_at_top():
        ext = 360.0 / n
        rel = (90.0 - st["angle"]) % 360.0
        return int(rel // ext) % n

    def spin():
        if st["spinning"] or len(st["picked"]) >= 3:
            return
        free = [i for i, k in enumerate(keys) if k not in st["picked"]]
        target = random.choice(free)
        ext = 360.0 / n
        # final angle: the target sector's middle under the pointer
        want = (90.0 - (target * ext + ext / 2)) % 360.0
        cur = st["angle"] % 360.0
        delta = (want - cur) % 360.0 + 360.0 * random.randint(3, 5)
        frames = 70
        st["spinning"] = True
        start_angle = st["angle"]

        def live():
            # the panel shown now (the board may have been rebuilt or closed
            # while the wheel turns; the spin goes on all the same)
            pnl = getattr(app, "_roulette_panel", None)
            try:
                return pnl if (pnl is not None and pnl.winfo_exists()) else None
            except Exception:
                return None

        def step(i=0):
            t = (i + 1) / frames
            ease = 1 - (1 - t) ** 3
            st["angle"] = start_angle + delta * ease
            pnl = live()
            if pnl is not None:
                pnl._draw()
            if i + 1 < frames:
                app.root.after(25, lambda: step(i + 1))
            else:
                st["spinning"] = False
                st["picked"].append(keys[target])
                if pnl is not None:
                    pnl._show_picked()
                    pnl._draw()
                    if len(st["picked"]) >= 3:
                        pnl._ready()
                # the bell rings each time the wheel comes to rest
                try:
                    import sys as _sys
                    _sys.modules.get(type(app).__module__)._play_sound_variant(
                        "bell[12].ogg", volume=1.0)
                except Exception:
                    pass
        step()

    def show_picked():
        """Three places, 1. ? 2. ? 3. ?, filled one by one with the trait
        drawn: its two forms as large icons, its name below."""
        for w in picked_box.winfo_children():
            w.destroy()
        tk.Frame(picked_box, bg=bg, height=16).pack()
        for i in range(3):
            k = st["picked"][i] if i < len(st["picked"]) else None
            slot = tk.Frame(picked_box, bg=bg, width=270, height=100)
            slot.pack(anchor="w", pady=2)
            slot.pack_propagate(False)
            tk.Label(slot, text=f"{i + 1}.", font=("Segoe UI", 20, "bold"),
                     bg=bg, fg=INK, width=2, anchor="e").pack(side="left", anchor="center")
            if k is None:
                tk.Label(slot, text="?", font=("Segoe UI", 34, "bold"), bg=bg,
                         fg="#c9bfa8").pack(side="left", padx=(28, 0))
            else:
                col = tk.Frame(slot, bg=bg)
                col.pack(side="left", padx=(14, 0))
                icons = tk.Frame(col, bg=bg)
                icons.pack()
                for f in (_dominant(k), _recessive(k)):
                    try:
                        _photo_label(icons, _trait_pil(k, f, 54), bg).pack(side="left", padx=5)
                    except Exception:
                        pass
                tk.Label(col, text=_TRAIT_NAME[k].capitalize(), font=("Segoe UI", 14, "bold"),
                         bg=bg, fg=INK).pack()
            if i < 2:
                tk.Frame(picked_box, bg="#e2d8c4", height=1, width=250).pack(anchor="w",
                                                                            padx=(10, 0))

    def go():
        p = dict(_rparams(app))
        p["traits"] = list(st["picked"])
        try:
            p["x"] = build_roulette_garden(app, p["traits"])
        except Exception:
            import logging
            logging.error("Roulette garden failed", exc_info=True)
        app._active_mission_params = p
        app._roulette_state = None
        # the missions board closes: the garden is what matters now
        try:
            bw = getattr(app, "_missions_win", None)
            if bw is not None and bw.winfo_exists():
                bw.destroy()
        except Exception:
            pass
        # real time: one second is one second (the plant grows while you
        # study its family tree; Fast Forward is there when you want it)
        try:
            import sys as _sys
            rt = getattr(_sys.modules.get(type(app).__module__), "SPEED_REAL_TIME_SECS", 3600.0)
            app._set_day_length(rt)
            app.day_length_s = rt
            app.running = True
            app._update_pause_button()
        except Exception:
            pass
        _refresh_board(app)
        try:
            app._toast(f"Plant #{p.get('x')} waits in the middle of your garden. Study its "
                       "family tree in the TIE.", level="info", duration=6000)
        except Exception:
            pass

    mk = getattr(app, "_make_flat_button", None)
    spin_btn = (mk(bar, "Spin the wheel", spin, bg="#7A9A3C", fg="white",
                   font=("Segoe UI", 15, "bold")) if mk else
                tk.Button(bar, text="Spin the wheel", command=spin))
    go_btn = (mk(bar, "Enter the garden", go, bg="#7A9A3C", fg="white",
                 font=("Segoe UI", 15, "bold")) if mk else
              tk.Button(bar, text="Enter the garden", command=go))
    if len(st["picked"]) >= 3:
        go_btn.pack(side="right")
    else:
        spin_btn.pack(side="right")
    draw()
    show_picked()
    def ready():
        spin_btn.pack_forget()
        go_btn.pack(side="right")
    outer._draw = draw
    outer._show_picked = show_picked
    outer._ready = ready
    outer._spin = spin
    outer._go = go
    outer._st = st
    app._roulette_panel = outer
    return outer


def open_roulette(app):
    """After accepting Plant Roulette: the board shows the mission's
    »Roulette« tab with the wheel."""
    tabs = getattr(app, "_missions_tabs", None)
    if not isinstance(tabs, dict):
        tabs = app._missions_tabs = {}
    already = tabs.get("mission_roulette") == "Roulette"
    tabs["mission_roulette"] = "Roulette"
    win = getattr(app, "_missions_win", None)
    try:
        if win is not None and win.winfo_exists():
            if already and getattr(win, "_shown_key", None) == "mission_roulette":
                return win          # the board shows the wheel already
            app._missions_tier = "medium"
            idxs = dict(getattr(app, "_missions_idx", None) or {})
            idxs["medium"] = tier_missions("medium").index(mission_by_key("mission_roulette"))
            app._missions_idx = idxs
            win._fill()
            return win
    except Exception:
        pass
    return open_board(app, focus="mission_roulette", tab="Roulette")


# ---------------------------------------------------------------------------
# Example pictures (below each mission's aim): the game's icons and plants
# ---------------------------------------------------------------------------

EX_ICON = 44                     # icon size in the pictures
EX_ICON_SIZES = (54, 48, 42, 36)   # tried in turn: the largest whose picture fits the card
_EX_SIZE = None                  # while a picture is drawn: every icon at this size


def _plant_pil(app, traits, stage=6, frac=0.6, height=150):
    """A plant drawn in the player's plant style (pea_render), as a PIL
    image `height` px tall; None if it can't be drawn."""
    key = ("plant", tuple(sorted(traits.items())), stage, frac, height,
           str(getattr(app, "_plant_style", "grown")))
    if key in _ICON_CACHE:
        return _ICON_CACHE[key].copy()
    im = None
    try:
        import pea_render as _pr
        style = str(getattr(app, "_plant_style", "grown") or "grown")
        age = _pr.model_age(stage, frac, 6.0 if stage >= 7 else 0.0)
        im = _pr.plant_image(dict(traits), 7, age, painterly=("painted" in style),
                             staked=("staked" in style), size=max(128, height * 2))
        bb = im.getbbox()
        if bb:
            im = im.crop(bb)
        s = height / float(im.height)
        from PIL import Image
        im = im.resize((max(1, int(im.width * s)), height), Image.LANCZOS)
    except Exception:
        im = None
    if im is not None:
        _ICON_CACHE[key] = im
        return im.copy()
    return None


_FULL_DOM = {"flower_color": "purple", "seed_shape": "round", "seed_color": "yellow",
             "plant_height": "tall", "pod_shape": "inflated", "pod_color": "green",
             "flower_position": "axial"}
_FULL_REC = {"flower_color": "white", "seed_shape": "wrinkled", "seed_color": "green",
             "plant_height": "dwarf", "pod_shape": "constricted", "pod_color": "yellow",
             "flower_position": "terminal"}


def _ex_frame(parent, bg):
    return tk.Frame(parent, bg=bg)


def _ex_row(parent, bg, parts, size=EX_ICON):
    """One line of a picture: ("i", trait, form) an icon, ("t", text) a
    word or sign, ("p", PIL image) any picture."""
    row = tk.Frame(parent, bg=bg)
    for part in parts:
        kind = part[0]
        if kind == "i":
            sz = _EX_SIZE or (part[3] if len(part) > 3 else size)
            try:
                _photo_label(row, _trait_pil(part[1], part[2], sz), bg).pack(side="left", padx=2)
            except Exception:
                pass
        elif kind == "f":                 # faded icon
            sz = _EX_SIZE or (part[3] if len(part) > 3 else size)
            try:
                _photo_label(row, _faded(_trait_pil(part[1], part[2], sz)), bg).pack(
                    side="left", padx=2)
            except Exception:
                pass
        elif kind == "p":
            if part[1] is not None:
                _photo_label(row, part[1], bg).pack(side="left", padx=4, anchor="s")
        else:
            big = part[2] if len(part) > 2 else 17
            tk.Label(row, text=part[1], font=("Segoe UI", big, "bold"), bg=bg,
                     fg=MUTED).pack(side="left", padx=4)
    return row


def _caption(parent, bg, text):
    tk.Label(parent, text=text, font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED).pack()


def ex_pure_line(app, parent, bg):
    f = _ex_frame(parent, bg)
    k = pure_line_trait(app) or "flower_color"
    for col in (_dominant(k), _recessive(k)):
        _ex_row(f, bg, [("i", k, col, 54), ("t", "→ selfed →", 14)]
                + [("i", k, col, 36)] * 6 + [("t", "…")]).pack(anchor="w", pady=2)
    _caption(f, bg, "two true breeders: every child like its parent")
    return f


def ex_seven(app, parent, bg):
    from PIL import Image
    cell, gap = 54, 5
    im = Image.new("RGBA", (len(TRAITS) * (cell + gap) + gap, 2 * (cell + gap) + gap), (0, 0, 0, 0))
    for c, (k, _n, d, r) in enumerate(TRAITS):
        for row, form in enumerate((d, r)):
            ic = _trait_pil(k, form, cell)
            im.alpha_composite(ic, (gap + c * (cell + gap) + (cell - ic.width) // 2,
                                    gap + row * (cell + gap) + (cell - ic.height) // 2))
    f = _ex_frame(parent, bg)
    _photo_label(f, im, bg).pack()
    _caption(f, bg, "the seven characters: dominant forms above, recessive below")
    return f


def ex_islands(app, parent, bg):
    from PIL import Image, ImageDraw
    cell, gap = 54, 4
    size = 3 * cell + 4 * gap
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    for r in range(3):
        for c in range(3):
            x, y = gap + c * (cell + gap), gap + r * (cell + gap)
            col = "white" if (r, c) == (1, 1) else "purple"
            dr.rounded_rectangle((x, y, x + cell, y + cell), 7, fill=(150, 112, 76, 255),
                                 outline=((217, 165, 32, 255) if col == "white"
                                          else (120, 88, 60, 255)),
                                 width=(3 if col == "white" else 1))
            ic = _trait_pil("flower_color", col, cell - 10)
            im.alpha_composite(ic, (x + (cell - ic.width) // 2, y + (cell - ic.height) // 2))
    f = _ex_frame(parent, bg)
    _photo_label(f, im, bg).pack()
    _caption(f, bg, f"one island: make {ISLANDS_NEED}")
    return f


def ex_reciprocal(app, parent, bg):
    f = _ex_frame(parent, bg)
    for m_, d_ in (("white", "purple"), ("purple", "white")):
        _ex_row(f, bg, [("t", "♀", 20), ("i", "flower_color", m_), ("t", "×", 20),
                        ("t", "♂", 20), ("i", "flower_color", d_), ("t", "→", 20)]
                + [("i", "flower_color", "purple", 36)] * 4).pack(anchor="w", pady=2)
    _caption(f, bg, "both ways round: the same children")
    return f


def ex_three_to_one(app, parent, bg):
    f = _ex_frame(parent, bg)
    _ex_row(f, bg, [("t", "P ", 15), ("i", "flower_color", "purple"), ("t", "\u00d7", 20),
                    ("i", "flower_color", "white"), ("t", "\u2192 F1", 15)]).pack(anchor="w", pady=2)
    _ex_row(f, bg, [("t", "F1", 15), ("i", "flower_color", "purple"),
                    ("t", "\u2192 selfed \u2192 F2", 15)]).pack(anchor="w", pady=2)
    _ex_row(f, bg, [("t", "F2", 15)] + [("i", "flower_color", "purple")] * 3
            + [("i", "flower_color", "white"), ("t", "3 : 1", 18)]).pack(anchor="w", pady=2)
    _caption(f, bg, "the white comes back in one of four grandchildren")
    return f


def ex_test_cross(app, parent, bg):
    f = _ex_frame(parent, bg)
    _ex_row(f, bg, [("t", "hybrid", 14), ("i", "flower_color", "purple"), ("t", "×", 20),
                    ("i", "flower_color", "white"), ("t", "→", 20),
                    ("i", "flower_color", "purple"), ("i", "flower_color", "purple"),
                    ("i", "flower_color", "white"), ("i", "flower_color", "white"),
                    ("t", "1 : 1", 18)]).pack(anchor="w", pady=2)
    _caption(f, bg, "a hybrid crossed with the recessive form: half and half")
    return f


def ex_hidden_seven(app, parent, bg):
    from PIL import Image
    cell, gap = 54, 5
    im = Image.new("RGBA", (len(TRAITS) * (cell + gap) + gap, cell + 2 * gap), (0, 0, 0, 0))
    for c, (k, _n, d, r) in enumerate(TRAITS):
        ic = _trait_pil(k, r, cell)
        im.alpha_composite(ic, (gap + c * (cell + gap) + (cell - ic.width) // 2,
                                gap + (cell - ic.height) // 2))
    f = _ex_frame(parent, bg)
    row = tk.Frame(f, bg=bg)
    row.pack()
    _photo_label(row, im, bg).pack(side="left")
    _caption(f, bg, "all seven recessive forms in one plant")
    return f


def _wheel_pil(size=150):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (size, size + 14), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    cols = [(201, 163, 214), (232, 210, 122), (169, 207, 127), (159, 198, 160),
            (217, 185, 138), (183, 212, 126), (215, 167, 184)]
    n = len(cols)
    box = (6, 18, size - 6, size + 6)
    for i, c in enumerate(cols):
        dr.pieslice(box, -90 + i * 360 / n, -90 + (i + 1) * 360 / n, fill=c + (255,),
                    outline=(107, 90, 68, 255), width=2)
    cx, cy = size / 2, (box[1] + box[3]) / 2
    dr.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=(139, 66, 38, 255))
    dr.polygon([(cx - 9, 2), (cx + 9, 2), (cx, 22)], fill=(176, 42, 42, 255),
               outline=(92, 40, 16, 255))
    return im


def ex_roulette(app, parent, bg):
    f = _ex_frame(parent, bg)
    pl = _plant_pil(app, _FULL_DOM, stage=4, frac=0.5, height=120)
    _ex_row(f, bg, [("p", _wheel_pil(140)), ("t", "→", 20), ("p", pl), ("t", "→", 20),
                    ("i", "flower_color", "purple", 40), ("t", "?", 24),
                    ("i", "flower_color", "white", 40)]).pack()
    _caption(f, bg, "spin, study the family tree, predict the offspring")
    return f


def ex_close_ratio(app, parent, bg):
    f = _ex_frame(parent, bg)
    _ex_row(f, bg, [("i", "seed_shape", "round"), ("t", "5474", 17), ("t", ":", 17),
                    ("i", "seed_shape", "wrinkled"), ("t", "1850", 17),
                    ("t", "= 2.96 : 1", 17)]).pack(anchor="w", pady=2)
    _ex_row(f, bg, [("i", "seed_color", "yellow"), ("t", "6022", 17), ("t", ":", 17),
                    ("i", "seed_color", "green"), ("t", "2001", 17),
                    ("t", "= 3.01 : 1", 17)]).pack(anchor="w", pady=2)
    _caption(f, bg, "Mendel's own counts")
    return f


def ex_true_to_type(app, parent, bg):
    f = _ex_frame(parent, bg)
    target = _targets(app) if active_mission(app) is mission_by_key("mission_true_to_type") else []
    if target:
        parts = []
        for k, form in target:
            parts.append(("i", k, form))
        tr = dict(_FULL_DOM)
        tr.update({k: form for k, form in target})
        pl = _plant_pil(app, tr, stage=6, frac=0.7, height=120)
        _ex_row(f, bg, parts + [("t", "→", 20), ("p", pl)]).pack()
        _caption(f, bg, "your three traits, bred true")
    else:
        _ex_row(f, bg, [("t", "?", 28), ("t", "+", 20), ("t", "?", 28), ("t", "+", 20),
                        ("t", "?", 28), ("t", "→", 20),
                        ("p", _plant_pil(app, _FULL_DOM, stage=6, frac=0.7, height=110))]).pack()
        _caption(f, bg, "three traits drawn when you accept, bred into one true-breeding line")
    return f


def ex_six_generations(app, parent, bg):
    f = _ex_frame(parent, bg)
    row1 = [("i", "flower_color", "purple", 36), ("t", "\u00d7", 16),
            ("i", "flower_color", "white", 36)]
    for g in range(1, 4):
        row1 += [("t", "\u2192", 16), ("t", f"F{g}", 15), ("i", "flower_color", "purple", 34)]
    row2 = []
    for g in range(4, 7):
        row2 += [("t", "\u2192", 16), ("t", f"F{g}", 15),
                 ("i", "flower_color", "purple" if g < 6 else "white", 34)]
    _ex_row(f, bg, row1).pack(anchor="w")
    _ex_row(f, bg, row2).pack(anchor="w", padx=(60, 0), pady=(2, 0))
    _caption(f, bg, "one line, selfed generation after generation, up to the F6")
    return f


def ex_dihybrid(app, parent, bg):
    f = _ex_frame(parent, bg)
    parts = []
    for sh, co, n in (("round", "yellow", "9"), ("round", "green", "3"),
                      ("wrinkled", "yellow", "3"), ("wrinkled", "green", "1")):
        if parts:
            parts.append(("t", ":", 20))
        parts += [("i", "seed_shape", sh, 38), ("i", "seed_color", co, 38), ("t", n, 18)]
    _ex_row(f, bg, parts).pack()
    _caption(f, bg, "two traits, each going its own way: 9 : 3 : 3 : 1")
    return f


EXAMPLES = {
    "mission_pure_line": ex_pure_line, "mission_seven": ex_seven,
    "mission_islands": ex_islands, "mission_reciprocal": ex_reciprocal,
    "mission_three_to_one": ex_three_to_one, "mission_test_cross": ex_test_cross,
    "mission_hidden_seven": ex_hidden_seven, "mission_roulette": ex_roulette,
    "mission_close_ratio": ex_close_ratio, "mission_true_to_type": ex_true_to_type,
    "mission_six_generations": ex_six_generations, "mission_dihybrid": ex_dihybrid,
}


# ---------------------------------------------------------------------------
# The missions
# ---------------------------------------------------------------------------

TIERS = ("easy", "medium", "hard")
TIER_NAMES = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}

MISSIONS = [
    # ---------------- easy ----------------
    {
        "key": "mission_pure_line",
        "tier": "easy",
        "title": "True Breeders",
        "short": "True Breeders",
        "aim": ("Choose a trait, then find two true breeders for it, one for each form (e.g. "
                "purple and white flowers): self-pollinated plants whose offspring all look "
                "like their parent."),
        "aim_active": ("Find two true breeders for {trait}, one for each form: self-pollinated "
                       "plants whose offspring all look like their parent."),
        "choose_trait": True,
        "setup": setup_pure_line,
        "background": (
            "Before any crossing, Mendel tested his peas. He obtained 34 varieties from "
            "seed merchants and grew them for two years, keeping only those that bred true "
            "year after year; 22 of them became his experimental plants."),
        "quote": ("“The experimental plants must necessarily possess constant "
                  "differentiating characters.”"),
        "quote_src": "Gregor Mendel, Experiments in Plant Hybridisation (1866)",
        "steps": [
            "Let a plant pollinate itself (a pea does that on its own) and harvest its seeds. "
            "Do the same with a plant of the other form of the trait, e.g. one purple and "
            "one white plant.",
            "Sow them. Seed shape and colour show on the pea itself; flower colour, height, "
            "pods and flower position once the young plants grow.",
            f"Needed for each form: {PURE_NEED} offspring that show the trait, all like their "
            "parent.",
        ],
        "check": check_pure_line,
        "example": pure_line_example,
        "achievement": "True Breeders",
        "congrats": ("Every child just like its parent, in both lines! True breeders, Gregor: "
                     "material you can trust. Mendel spent two whole years making sure of his."),
    },
    {
        "key": "mission_seven",
        "tier": "easy",
        "title": "The Magnificent Seven",
        "short": "Magnificent Seven",
        "aim": ("Find both forms of each of Mendel's seven characters in plants grown from "
                "seeds you harvested yourself, and name each one in your notebook: fourteen "
                "forms in all."),
        "background": (
            "Out of the many differences between his pea varieties Mendel chose seven that "
            "come in two clearly distinct forms: the shape and colour of the seed, the "
            "colour of the flower, the shape and colour of the pod, where the flowers sit "
            "and the length of the stem."),
        "steps": [
            "Sow many different starter seeds (a good mixture), raise them and harvest their "
            "seeds. The starters themselves don't count.",
            "Sow your harvest. Seed shape and colour you see on the pea; flower colour and "
            "position show when the plants flower, the pods once they form, the height as "
            "they grow.",
            "Inspect them. Under a form that is new to your notebook the inspection window "
            "shows \u00bb\u270e Record\u00ab: click it and name the form the plant shows. Look "
            "closely: after a wrong answer that plant must wait until tomorrow.",
            "Needed: both forms of all seven traits, named from the plants of your own harvest.",
        ],
        "check": check_seven,
        "example": seven_example,
        "achievement": "The Magnificent Seven",
        "congrats": ("Round and wrinkled, yellow and green, purple and white, tall and dwarf, "
                     "and all the rest! Now you know the alphabet the peas write in, Gregor."),
    },
    {
        "key": "mission_islands",
        "tier": "easy",
        "title": "White Islands",
        "short": "White Islands",
        "aim": (f"Design a flower bed: {ISLANDS_NEED} white-flowering plants, each completely "
                "surrounded by purple-flowering ones (all eight plots around it, corners too), "
                "all in flower at the same time."),
        "background": (
            "The abbey garden was not only a laboratory. To plan a bed like this you must "
            "know what colour a seed will flower before it is sown, and only seeds of a "
            "true-breeding line can promise that."),
        "steps": [
            "Collect seeds of true-breeding white and purple plants (their offspring all flower "
            "like them).",
            "Sow a white seed and purple seeds in all eight plots around it, the corners "
            f"included. Make {ISLANDS_NEED} such islands in all (their rings may share plots).",
            "Wait until all of them are in flower on the same day.",
        ],
        "check": check_islands,
        "example": island_example,
        "achievement": "White Islands",
        "congrats": ("What a sight: white islands in a purple sea! Planned before a single "
                     "seed was sown. You know your lines, Gregor."),
    },
    # ---------------- medium ----------------
    {
        "key": "mission_reciprocal",
        "tier": "medium",
        "title": "Equal Partners: Reciprocal Crosses",
        "short": "Equal Partners",
        "aim": ("Show that mother and father pass on their traits equally: a cross gives "
                "the same offspring, whichever of the two parents provides the pollen."),
        "background": (
            "In Mendel's day many naturalists believed that one parent, the mother or "
            "the father, had the greater share in the offspring. Mendel put it to the "
            "test: he crossed each pair of his varieties both ways, A as the mother with "
            "pollen of B, and B as the mother with pollen of A. His verdict:"),
        "quote": ("“It is perfectly immaterial whether the dominant character belongs "
                  "to the seed plant or to the pollen plant; the form of the hybrid "
                  "remains identical in both cases.”"),
        "quote_src": "Gregor Mendel, Experiments in Plant Hybridisation (1866)",
        "steps": [
            "Choose two plants that differ in one trait you can see, for example white and "
            "purple flowers, or round and wrinkled seeds. True-breeding ones work best: "
            "plants whose own selfed offspring all look like them.",
            "Emasculate a bud of plant A and pollinate it with pollen of plant B.",
            "Then the reverse: emasculate a bud of plant B and pollinate it with pollen of A.",
            "Harvest the crossed pods. Seed shape and colour show on the peas at once; for "
            "every other trait, sow the seeds and raise the young plants until it shows.",
            f"Needed in each direction: {RECIPROCAL_NEED_SEEDS} harvested seeds (seed shape "
            f"or colour) or {RECIPROCAL_NEED_PLANTS} offspring plants (any other trait), all "
            "alike, and alike in both directions.",
        ],
        "check": check_reciprocal,
        "achievement": "Equal Partners",
        "congrats": (
            "Whichever plant gave the pollen, the children are the same! Mother and father "
            "have an equal share in their offspring, Gregor. Many learned men would have "
            "wagered otherwise."),
    },
    {
        "key": "mission_three_to_one",
        "tier": "medium",
        "title": "Three to One (3 : 1)",
        "short": "Three to One",
        "aim": ("Cross two true-breeding lines, let their hybrids pollinate themselves, show that the "
                "hidden form returns in the grandchildren, in about one plant of four, and "
                "unlock the Law of Segregation with it."),
        "background": (
            "The hybrids of a cross all looked like one parent: the other form seemed lost. "
            "But in their offspring it came back. For flower colour Mendel counted 705 "
            "purple and 224 white plants, 3.15 to 1."),
        "quote": ("“… the recessive ones with their peculiarities fully developed, "
                  "and this occurs in the definitely expressed average proportion of three "
                  "to one …”"),
        "quote_src": "Gregor Mendel, Experiments in Plant Hybridisation (1866)",
        "steps": [
            "Cross two true-breeding plants that differ in one trait, e.g. purple and white "
            "flowers. Raise the hybrids (F1): they all look alike.",
            "Let the hybrids pollinate themselves, harvest and sow their seeds (F2: "
            "Choose Seeds › Seeds from crosses › F2).",
            f"Needed: {F2_NEED} grandchildren showing the trait, with the recessive form in "
            "15 to 35 of every hundred (3 : 1 is 25).",
            "Then claim the law: open \u00bbUnlock Laws\u00ab (at the bottom of the garden) "
            "and unlock the Law of Segregation in this garden.",
        ],
        "check": check_three_to_one,
        "achievement": "Three to One",
        "congrats": ("There it is again, the form that had vanished! Hidden in the hybrids, "
                     "returning in one of four grandchildren. That is the heart of it, Gregor."),
    },
    {
        "key": "mission_test_cross",
        "tier": "medium",
        "title": "The Test Cross",
        "short": "Test Cross",
        "aim": ("Cross a hybrid with a plant of the recessive form and show that half of the "
                "offspring are hybrids again and half show the recessive form: 1 : 1."),
        "background": (
            "To learn what the hybrids pass on, Mendel crossed them back with their parents. "
            "Crossed with the recessive parent, half the offspring showed the recessive form: "
            "so the hybrids form two kinds of egg and pollen cells, in equal numbers."),
        "steps": [
            "Raise hybrids (F1) from a cross of two true-breeding lines, e.g. purple × white.",
            "Cross a hybrid with a plant of the recessive form (white flowers, dwarf, "
            "terminal flowers, constricted or yellow pods). Either may be the mother.",
            f"Needed: {TEST_NEED} offspring showing the trait, the recessive form in 30 to "
            "70 of every hundred.",
        ],
        "check": check_test_cross,
        "achievement": "The Test Cross",
        "congrats": ("Half and half! The hybrid hides two kinds of elements and passes on "
                     "each of them equally often. You have looked into the hybrid itself, Gregor."),
    },
    # ---------------- hard ----------------
    {
        "key": "mission_hidden_seven",
        "tier": "medium",
        "title": "The Hidden Seven",
        "short": "Hidden Seven",
        "aim": ("Breed one plant that shows all seven recessive forms at once: wrinkled green "
                "seeds, white flowers at the top of the stem, constricted yellow pods, dwarf."),
        "background": (
            "Recessive forms hide in hybrids and only show when a plant has received the "
            "hidden element from both parents. Bringing all seven together means crossing "
            "the right plants and letting their offspring sort themselves out."),
        "steps": [
            "Find plants that between them show the recessive forms and cross them.",
            "Let the hybrids pollinate themselves: recessive forms come back in the "
            "grandchildren, in new combinations.",
            "Keep selecting and sowing the plants with the most recessive forms.",
            "Needed: one plant bred in this garden (not a starter) that shows all seven.",
        ],
        "check": check_hidden_seven,
        "example": lambda app, parent, bg: _forms_strip(parent, bg, "rec", "all seven recessive forms"),
        "achievement": "The Hidden Seven",
        "congrats": ("Wrinkled, green, white, terminal, constricted, yellow and dwarf, all in "
                     "one! Every hidden element brought into the light, Gregor."),
    },
    {
        "key": "mission_roulette",
        "tier": "medium",
        "title": "Plant Roulette",
        "short": "Plant Roulette",
        "aim": ("Spin the wheel for three traits. A single plant waits in your garden: read "
                "its family tree in the TIE and predict what its seeds will grow into."),
        "background": (
            "Mendel's laws let you predict before you sow. A plant from two true-breeding lines of "
            "the same form breeds true; a hybrid of two contrasting true-breeding lines gives both "
            "forms again, three of the dominant to one of the recessive."),
        "steps": [
            "Accept, then spin the wheel three times: three traits are drawn.",
            "A single plant grows in the middle of your new garden. Open the TIE for it "
            "and study its parents and grandparents.",
            "When you harvest its first pod, you seal one prediction per trait: only one "
            "form, more of one than the other, or the other way round.",
            "Harvest all its pods, sow the seeds and raise them: "
            f"{ROULETTE_NEED_PLANTS} plants per trait ({ROULETTE_NEED_SEEDS} seeds for seed "
            "shape or colour) reveal whether you were right. All three right: mission complete.",
        ],
        "check": check_roulette,
        "after_accept": open_roulette,
        "achievement": "Plant Roulette",
        "congrats": ("Three for three! You read the family tree like a book and the seeds "
                     "did exactly as you said. That is what a law is for, Gregor."),
        "failed_text": ("Not this time, Gregor. The seeds had other plans than your "
                        "predictions."),
    },
    {
        "key": "mission_close_ratio",
        "tier": "hard",
        "title": "Mendel's Numbers",
        "short": "Mendel's Numbers",
        "aim": (f"Count more than {CLOSE_NEED - 1} grandchildren (F2) of a cross for one trait "
                f"and come as close to 3 : 1 as Mendel did: between {CLOSE_RANGE[0]:.1f} : 1 "
                f"and {CLOSE_RANGE[1]:.1f} : 1."),
        "background": (
            "Single families can stray far from 3 : 1; only large numbers show the rule. "
            "Mendel counted thousands of plants and seeds: 5474 round to 1850 wrinkled "
            "seeds, 6022 yellow to 2001 green. Taking all his experiments together:"),
        "quote": ("“… there is found, as between the number of forms with the "
                  "dominant and recessive characters, an average ratio of 2.98 to 1, or "
                  "3 to 1.”"),
        "quote_src": "Gregor Mendel, Experiments in Plant Hybridisation (1866)",
        "steps": [
            "Cross two true-breeding lines that differ in one trait and raise the hybrids (F1).",
            "Let the hybrids pollinate themselves. For seed shape or colour, every pea they "
            "bear counts; for any other trait, sow the seeds and raise the grandchildren.",
            f"Needed: more than {CLOSE_NEED - 1} counted for one trait, the ratio between "
            f"{CLOSE_RANGE[0]:.1f} : 1 and {CLOSE_RANGE[1]:.1f} : 1.",
        ],
        "check": check_close_ratio,
        "achievement": "Mendel's Numbers",
        "congrats": ("Three to one, near enough to make Mendel nod! Large numbers, patient "
                     "counting, and the rule appears out of chance."),
    },
    {
        "key": "mission_true_to_type",
        "tier": "hard",
        "title": "True to Type",
        "short": "True to Type",
        "aim": ("Breed a true-breeding line with three traits chosen at random when you accept: a "
                "plant that shows all three, whose own offspring all show them too."),
        "aim_active": "Breed a true-breeding line with {target}: a plant that shows all three, whose "
                      "own selfed offspring all show them too.",
        "background": (
            "Combining the best of two varieties in one plant that breeds true is what "
            "breeders have done ever since. Mendel's laws tell how: cross, let the hybrids "
            "pollinate themselves, then select in the following generations."),
        "steps": [
            "Find plants that between them have the three traits and cross them.",
            "Let the offspring pollinate themselves; among the grandchildren some show all "
            "three traits.",
            "Test them: a plant breeds true when all its selfed offspring look like it. "
            "Recessive forms breed true at once; a dominant form must be tested.",
            f"Needed: a plant with all three traits and {TRUE_NEED} of its selfed offspring, "
            "all showing them.",
        ],
        "setup": setup_true_to_type,
        "check": check_true_to_type,
        "achievement": "True to Type",
        "congrats": ("A new true-breeding line, made by your own hand! Three traits brought together "
                     "and fixed for good. That is breeding, Gregor, not luck."),
    },
    {
        "key": "mission_six_generations",
        "tier": "hard",
        "title": "Six Generations",
        "short": "Six Generations",
        "aim": ("Follow a line from a cross through six generations of self-pollination, up "
                "to a flowering plant of the F6."),
        "background": (
            "Mendel did not stop at the grandchildren. He kept several experiments going "
            "for six generations and found that the hybrids grow rarer in each one, while "
            "the pure forms take over the line."),
        "steps": [
            "Cross two plants; their seeds grow into the F1.",
            "Each generation, sow the seeds of a plant of the last one (Choose Seeds › "
            "Seeds from crosses shows F1, F2, …).",
            f"Needed: a plant of the F{SIX_NEED} in flower.",
        ],
        "check": check_six_generations,
        "achievement": "Six Generations",
        "congrats": ("Six generations, Gregor! Few have the patience. Look how the hybrids "
                     "fade from the line while the pure forms remain."),
    },
    {
        "key": "mission_dihybrid",
        "tier": "hard",
        "title": "Two Traits at Once",
        "short": "Two Traits",
        "aim": ("Cross plants differing in two traits, raise their grandchildren and show the "
                "four combinations in about 9 : 3 : 3 : 1: the traits are inherited "
                "independently."),
        "background": (
            "Mendel crossed round yellow with wrinkled green peas. Among the 556 seeds of "
            "the second generation he counted 315 round yellow, 101 wrinkled yellow, 108 "
            "round green and 32 wrinkled green: each trait goes its own way."),
        "steps": [
            "Cross two true-breeding plants that differ in two traits, e.g. round yellow "
            "and wrinkled green seeds.",
            "Let the hybrids pollinate themselves. Seed shape and colour count on every pea "
            "they bear; for other traits, sow the seeds and raise the grandchildren (F2).",
            f"Needed: {DI_NEED} grandchildren showing both traits, all four combinations, "
            "close to 9 : 3 : 3 : 1.",
        ],
        "check": check_dihybrid,
        "achievement": "Two Traits at Once",
        "congrats": ("Nine, three, three, one! Each trait goes its own way, combined anew in "
                     "every grandchild. Brother Abbot will want to hear of this."),
    },
]


def mission_by_key(key):
    return next((m for m in MISSIONS if m["key"] == key), None)


def tier_missions(tier):
    return [m for m in MISSIONS if m["tier"] == tier]


def tier_unlocked(app, tier, got=None):
    """Easy missions are open from the start; the next tier opens once all
    missions of the tier before it are completed (in any order)."""
    if got is None:
        try:
            got = app._load_achievements()
        except Exception:
            got = {}
    i = TIERS.index(tier)
    return i == 0 or all(m["key"] in got for m in tier_missions(TIERS[i - 1]))


def mission_aim(app, m):
    if m.get("choose_trait") and m.get("aim_active") and active_mission(app) is m:
        k = (getattr(app, "_active_mission_params", None) or {}).get("trait")
        if k in _TRAIT_NAME:
            return m["aim_active"].format(trait=_TRAIT_NAME[k])
        return m["aim"]
    if m.get("aim_active") and active_mission(app) is m:
        target = _targets(app)
        if target:
            return m["aim_active"].format(target=_target_text(target))
    return m["aim"]


def _blocked_reason(app):
    if getattr(app, "_tutorial_active", False):
        return "Missions are not counted in Abbot Cyril's practice garden."
    if getattr(app, "_genotype_revealed", False):
        return ("The genotype was revealed in this garden: no mission can be completed "
                "here any more.")
    return ""


def evaluate(app, mission):
    try:
        return mission["check"](app)
    except Exception:
        import logging
        logging.exception("mission check failed: %s", mission.get("key"))
        return Progress(False, [], "")


def active_mission(app):
    """The mission accepted for this garden (None if there is none)."""
    if getattr(app, "_tutorial_active", False):
        return None
    return mission_by_key(getattr(app, "_active_mission", None))


# ---------------------------------------------------------------------------
# Accepting a mission
# ---------------------------------------------------------------------------

def accept(app, key, parent=None):
    """Accepting a mission starts a new garden for it (the current one is
    saved as "Before the mission" first)."""
    m = mission_by_key(key)
    if m is None:
        return False
    if not tier_unlocked(app, m["tier"]):
        app._toast("Complete the missions before it first.", level="info")
        return False
    if getattr(app, "_tutorial_active", False):
        # a mission is played in the player's own garden: leave Abbot
        # Cyril's practice garden first (the tutorial keeps its progress)
        try:
            yes = app._silent_askyesno(
                "Leave the practice garden?",
                f"»{m['short']}« is played in a garden of your own.\n\n"
                "Leave Abbot Cyril's practice garden now? You can come back to the "
                "tutorial later from the Friar's quarters.", parent=parent)
        except Exception:
            yes = False
        if not yes:
            return False
        try:
            import tutorial as _tut
            _tut.exit_tutorial(app)
        except Exception:
            import logging
            logging.error("Leaving the tutorial for a mission failed", exc_info=True)
            return False
        if getattr(app, "_tutorial_active", False):
            return False
    # (no question: the current garden is kept as a save of its own first)
    _save_before_mission(app)
    fresh = getattr(app, "_fresh_state", None)
    if not fresh:
        app._silent_showerror("Mission", "Could not start a new garden.")
        return False
    try:
        import copy
        app._deserialize_garden_state(copy.deepcopy(fresh))
        app._winter_prompted_key = None
    except Exception as e:
        import logging
        logging.error(f"Mission garden failed: {e}", exc_info=True)
        app._silent_showerror("Mission", f"Could not start a new garden:\n{e}")
        return False
    app._active_mission = key
    app._roulette_state = None          # (a fresh wheel)
    try:
        app._active_mission_params = m["setup"](app) if m.get("setup") else None
    except Exception:
        app._active_mission_params = None
    try:
        app._remember_realm("garden")
    except Exception:
        pass
    _refresh_indicator(app)
    try:
        app._toast(f"Mission accepted: {m['short']}. A new garden begins.", level="info")
    except Exception:
        pass
    if m.get("after_accept"):
        try:
            app.root.after(200, lambda: m["after_accept"](app))
        except Exception:
            pass
    return True


def _save_before_mission(app):
    """Keeps the garden a mission replaces: saved as "Before the mission"
    (listed in File > Load). Nothing to keep in a garden never sown."""
    import sys, os, json, datetime, logging
    try:
        plants = [t for t in app._all_plot_tiles() if getattr(t, "plant", None) is not None]
        archived = ((getattr(app, "archive", {}) or {}).get("plants") or {})
        if not plants and not archived:
            return None
        base = getattr(sys.modules.get(type(app).__module__), "_PG_BASE_DIR", None)
        if not base:
            return None
        try:
            app._eager_seed_and_backfill()
        except Exception:
            pass
        data = app._serialize_garden_state()
        data["garden_name"] = "Before the mission"
        data["realm"] = "garden"
        data_dir = os.path.join(base, "data")
        os.makedirs(data_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(data_dir, f"garden_Before_the_mission_{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        return path
    except Exception:
        logging.error("Saving the garden before the mission failed", exc_info=True)
        return None


def abandon(app, parent=None):
    m = active_mission(app)
    if m is None:
        return
    app._active_mission = None
    app._active_mission_params = None
    _refresh_indicator(app)
    try:
        app._toast(f"Mission abandoned: {m.get('short') or m['title']}. Your garden stays as it is.",
                   level="info")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Watching the garden
# ---------------------------------------------------------------------------

def check_all(app, announce=True):
    """Completes the active mission once its check passes (achievement,
    bell, Abbot Cyril's congratulations)."""
    m = active_mission(app)
    if m is None or _blocked_reason(app):
        return
    prog = evaluate(app, m)
    if getattr(prog, "failed", False):
        # e.g. a wrong prediction: the mission ends without the achievement
        wrong = "; ".join(t.split(" \u2014 ")[0] for t, ok, *_ in prog.items[2:] if not ok)
        app._active_mission = None
        app._active_mission_params = None
        _refresh_indicator(app)
        if announce:
            try:
                app.root.after(300, lambda: app._show_cyril_congrats(
                    m["title"], m.get("failed_text", "Not this time, Gregor."),
                    header="\u2718  Mission not passed",
                    button_text="I shall try again, Father"))
            except Exception:
                pass
        _refresh_board(app)
        return
    if not prog.done:
        return
    try:
        before = app._load_achievements()
    except Exception:
        before = {}
    new = app._award_achievement(m["key"])
    _save_record(app, m, prog)
    app._active_mission = None
    app._active_mission_params = None
    _refresh_indicator(app)
    if announce:
        extra = [f"\u2605  Achievement unlocked: {m['achievement']}"] if new else []
        # the last mission of a tier opens the next one
        for t in TIERS[1:]:
            if not tier_unlocked(app, t, before) and tier_unlocked(app, t):
                extra.append(f"\U0001F513  New missions unlocked: {TIER_NAMES[t]}")
        try:
            app.root.after(300, lambda: app._show_cyril_congrats(
                m["title"], m["congrats"], header="\u2714  Mission complete", extra=extra))
        except Exception:
            pass
    _refresh_board(app)


# ---------------------------------------------------------------------------
# How each mission was completed (kept for good, like the achievements)
# ---------------------------------------------------------------------------

def _records_path(app=None):
    import sys, os
    mods = []
    if app is not None:
        mods.append(sys.modules.get(type(app).__module__))
    mods += [sys.modules.get("__main__")] + list(sys.modules.values())
    for mod in mods:
        base = getattr(mod, "_PG_BASE_DIR", None)
        if isinstance(base, str) and base:
            return os.path.join(base, "data", "missions_record.json")
    return None


def load_records(app=None):
    import json
    p = _records_path(app)
    if not p:
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_record(app, m, prog):
    """The finished checklist (with the traits and numbers it was won
    with), shown on the card's Progress tab afterwards."""
    import json, os, datetime
    p = _records_path(app)
    if not p:
        return
    data = load_records(app)
    old = data.get(m["key"]) or {}
    items = []
    for it in prog.items:
        row = [str(it[0]), bool(it[1])]
        if len(it) > 2:
            row.append([list(x) for x in it[2]])
        items.append(row)
    data[m["key"]] = {"date": datetime.datetime.now().strftime("%d %b %Y"),
                      "times": int(old.get("times", 0) or 0) + 1,
                      "items": items,
                      "params": getattr(app, "_active_mission_params", None)}
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
    except Exception:
        pass


def start_watch(app):
    """Checks the active mission every few seconds (not during Fast Forward)."""
    old = getattr(app, "_missions_job", None)
    if old is not None:
        try:
            app.root.after_cancel(old)
        except Exception:
            pass

    def _tick():
        app._missions_job = None
        try:
            if not getattr(app, "fast_forward", False):
                check_all(app)
        except Exception:
            pass
        try:
            app._missions_job = app.root.after(WATCH_MS, _tick)
        except Exception:
            app._missions_job = None

    app._missions_job = app.root.after(WATCH_MS, _tick)


# ---------------------------------------------------------------------------
# The side bar: the active mission
# ---------------------------------------------------------------------------

def _refresh_indicator(app):
    try:
        app._refresh_mission_indicator()
    except Exception:
        pass
    _refresh_board(app)


# ---------------------------------------------------------------------------
# The missions board
# ---------------------------------------------------------------------------

BG = "#F4EFE3"
CARD = "#fbf7ee"
EDGE = "#d9cdb4"
INK = "#3b2a1a"
MUTED = "#7a6a55"
DONE_BG = "#FBF3D9"
DONE_EDGE = "#D9A520"
ACTIVE_EDGE = "#4f7d3a"
GREEN = "#4f7d3a"
TAB_ON = "#4f7d3a"
TAB_OFF = "#e8e0cf"

F_TITLE = ("Segoe UI", 17, "bold")
F_TEXT = ("Segoe UI", 14)
F_BOLD = ("Segoe UI", 14, "bold")
F_SMALL = ("Segoe UI", 13, "italic")
F_QUOTE = ("Georgia", 15, "italic")
TABS = ("Aim", "Details", "Progress")
SEL_BG = "#f2d48a"            # a chosen answer: the inspection window's selected bud
SEL_EDGE = "#d4a017"
HOVER_BG = "#f6e2b0"
PAGE_MIN_H = 150              # a tab's page: at least this tall (a full checklist)


def _refresh_board(app):
    win = getattr(app, "_missions_win", None)
    try:
        if win is not None and win.winfo_exists():
            win._fill()
    except Exception:
        pass


def open_board(app, focus=None, tab=None):
    """The missions board: one card per mission, with tabs for its aim,
    the details (Mendel's own experiment, how to do it) and the progress.
    `focus`: a mission key whose card opens on `tab`."""
    tabs = getattr(app, "_missions_tabs", None)
    if not isinstance(tabs, dict):
        tabs = app._missions_tabs = {}
    if focus and tab:
        tabs[focus] = tab
    fm = mission_by_key(focus) if focus else None
    app._missions_tier = fm["tier"] if fm else None     # (None: the default tier)
    if fm:
        app._missions_idx = dict(getattr(app, "_missions_idx", None) or {})
        app._missions_idx[fm["tier"]] = tier_missions(fm["tier"]).index(fm)
    old = getattr(app, "_missions_win", None)
    try:
        if old is not None and old.winfo_exists():
            old._fill()
            old.deiconify()
            old.lift()
            old.focus_force()
            return old
    except Exception:
        pass
    bg = getattr(app, "INSPECTOR_BG", BG)
    win = tk.Toplevel(app.root)
    win.withdraw()
    win.title("Missions")
    win.configure(bg=bg)
    win.resizable(False, True)
    app._missions_win = win
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass

    # (the title sits in the row of the Easy / Medium / Hard tabs, see _fill;
    # its explanation shows when the mouse is over it)
    tk.Frame(win, bg=bg, height=8).pack(fill="x")
    count_lbl = None
    warn = tk.Label(win, text="", font=("Segoe UI", 13, "bold"), bg=bg, fg="#a33",
                    padx=22, anchor="w", justify="left", wraplength=700)
    warn.pack(fill="x")

    body = tk.Frame(win, bg=bg)
    body.pack(fill="both", expand=True, padx=(22, 8), pady=(6, 0))
    canvas = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0)
    sb = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=bg)
    inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    W = 760

    def _explain(widget, text):
        """A note under the mouse while it is over `widget`."""
        tip = {"w": None}

        def _show(e):
            if tip["w"] is not None:
                return
            t = tk.Toplevel(win)
            t.overrideredirect(True)
            try:
                t.attributes("-topmost", True)
            except Exception:
                pass
            tk.Label(t, text=text, font=("Segoe UI", 13, "italic"), bg="#FFFDF2", fg=INK,
                     wraplength=420, justify="left", padx=10, pady=6,
                     highlightbackground=EDGE, highlightthickness=1).pack()
            t.geometry(f"+{e.x_root + 14}+{e.y_root + 18}")
            tip["w"] = t

        def _hide(e=None):
            if tip["w"] is not None:
                try:
                    tip["w"].destroy()
                except Exception:
                    pass
                tip["w"] = None
        widget.bind("<Enter>", _show)
        widget.bind("<Leave>", _hide)
        widget.bind("<Destroy>", _hide, add="+")

    def _fill():
        # built off-screen and swapped in when complete (no flicker of a
        # half-built page)
        nonlocal inner
        old_inner = inner
        inner = tk.Frame(canvas, bg=bg)
        try:
            got = app._load_achievements()
        except Exception:
            got = {}
        warn.configure(text=("You are in Abbot Cyril's practice garden: accepting a mission "
                             "takes you back to your own garden first."
                             if getattr(app, "_tutorial_active", False) else
                             _blocked_reason(app) if active_mission(app) else ""))
        n_done = sum(1 for m in MISSIONS if m["key"] in got)
        # one tier at a time: Easy | Medium | Hard (locked ones with a lock)
        cur_tier = getattr(app, "_missions_tier", None)
        if cur_tier not in TIERS:
            am = active_mission(app)
            cur_tier = am["tier"] if am else max(
                (t for t in TIERS if tier_unlocked(app, t, got)), key=TIERS.index)
        tierbar = tk.Frame(inner, bg=bg)
        tierbar.pack(fill="x", pady=(0, 2))
        ttl = tk.Label(tierbar, text="Missions", font=("Segoe UI", 20, "bold"), bg=bg, fg=INK,
                       cursor="question_arrow")
        ttl.pack(side="left", padx=(0, 14))
        _explain(ttl, "Experiments to pursue. Accept one to play it in a garden of its own; "
                      "it completes by itself once your garden shows the result. Complete all "
                      "missions of a level to unlock the next one.")
        tk.Label(tierbar, text=f"{n_done} of {len(MISSIONS)} completed",
                 font=("Segoe UI", 13, "italic"), bg=bg, fg=MUTED).pack(side="right")
        for t in TIERS:
            open_ = tier_unlocked(app, t, got)
            n_t = sum(1 for m in tier_missions(t) if m["key"] in got)
            on = (t == cur_tier)
            txt = f"{TIER_NAMES[t]}  {n_t}/{len(tier_missions(t))}" if open_ else \
                f"\U0001F512 {TIER_NAMES[t]}"
            lb = tk.Label(tierbar, text=txt, font=("Segoe UI", 14, "bold"), padx=16, pady=5,
                          bg=(TAB_ON if on else TAB_OFF),
                          fg=("white" if on else (INK if open_ else "#9a9080")), cursor="hand2")
            lb.pack(side="left", padx=(0, 6))
            _click(app, lb, lambda t=t: (setattr(app, "_missions_tier", t), _fill()))
        tk.Frame(inner, height=1, bg="#c8c0ac", width=W).pack(fill="x", pady=(4, 6))
        locked = not tier_unlocked(app, cur_tier, got)
        if locked:
            prev = TIERS[TIERS.index(cur_tier) - 1]
            tk.Label(inner, text=f"\U0001F512  Complete all {TIER_NAMES[prev].lower()} missions "
                                 f"(in any order) to unlock these.",
                     font=("Segoe UI", 14, "italic"), bg=bg, fg="#8a5a20", wraplength=W,
                     justify="left").pack(anchor="w", pady=(0, 6))
        # one mission at a time: ◀ n / N ▶ circles through the tier
        ms = tier_missions(cur_tier)
        idxs = getattr(app, "_missions_idx", None)
        if not isinstance(idxs, dict):
            idxs = app._missions_idx = {}
        if cur_tier not in idxs:
            am = active_mission(app)
            idxs[cur_tier] = ms.index(am) if am in ms else 0
        i = idxs[cur_tier] % len(ms)

        def _step(d, t=cur_tier, n=len(ms)):
            idxs[t] = (idxs.get(t, 0) + d) % n
            _fill()
        win._step = _step
        nav = tk.Frame(inner, bg=bg)
        nav.pack(fill="x", pady=(0, 4))
        for sym, d, side in (("\u25C0", -1, "left"), ("\u25B6", 1, "right")):
            a = tk.Label(nav, text=sym, font=("Segoe UI", 18, "bold"), bg=TAB_OFF, fg=INK,
                         padx=14, pady=2, cursor="hand2")
            a.pack(side=side)
            _click(app, a, lambda d=d: _step(d))
            a.bind("<Enter>", lambda e, a=a: a.configure(bg="#ddd3be"))
            a.bind("<Leave>", lambda e, a=a: a.configure(bg=TAB_OFF))
        dots = tk.Frame(nav, bg=bg)
        dots.pack(expand=True)
        tk.Label(dots, text=f"{i + 1} / {len(ms)}", font=("Segoe UI", 14, "bold"), bg=bg,
                 fg=MUTED).pack(side="left", padx=(0, 10))
        for j, mm in enumerate(ms):
            c = ("\u25CF" if j == i else "\u25CB")
            col = ("#B8860B" if mm["key"] in got else (GREEN if active_mission(app) is mm else MUTED))
            d_ = tk.Label(dots, text=c, font=("Segoe UI", 14), bg=bg, fg=col, cursor="hand2")
            d_.pack(side="left", padx=2)
            _click(app, d_, lambda j=j, t=cur_tier: (idxs.__setitem__(t, j), _fill()))
        _card(ms[i], got, locked)
        win._shown_key = ms[i]["key"]
        inner.update_idletasks()
        canvas.itemconfigure(inner_id, window=inner)
        try:
            old_inner.destroy()
        except Exception:
            pass
        win.update_idletasks()
        try:
            win._sig = win._signature()      # (no second rebuild by the live refresh)
        except Exception:
            pass
        need_h = inner.winfo_reqheight()
        need_w = max(W + 20, inner.winfo_reqwidth())
        view_h = min(need_h, int(win.winfo_screenheight() * 0.92) - 120)
        canvas.configure(width=need_w, height=view_h, scrollregion=(0, 0, need_w, need_h))
        if need_h > view_h:
            sb.pack(side="right", fill="y")
        else:
            sb.pack_forget()

    def _btn(parent, text, cmd, primary=False):
        mk = getattr(app, "_make_flat_button", None)
        if mk is not None:
            try:
                return mk(parent, text, cmd,
                          bg=("#7A9A3C" if primary else "#e0dccf"),
                          fg=("white" if primary else "#333333"),
                          font=("Segoe UI", 13, "bold" if primary else "normal"))
            except Exception:
                pass
        return tk.Button(parent, text=text, command=cmd, font=("Segoe UI", 13))

    def _card(m, got, locked=False):
        key = m["key"]
        done = key in got
        is_active = active_mission(app) is m
        cbg = DONE_BG if (done and not is_active) else CARD
        edge = ACTIVE_EDGE if is_active else (DONE_EDGE if done else EDGE)
        card = tk.Frame(inner, bg=cbg, highlightbackground=edge,
                        highlightthickness=(2 if is_active else 1), padx=16, pady=12)
        card.pack(fill="x", pady=5)

        # title row: star, title, state
        top = tk.Frame(card, bg=cbg)
        top.pack(fill="x")
        tk.Label(top, text=("\u2605" if done else "\u2606"), font=("Segoe UI", 20), bg=cbg,
                 fg=("#B8860B" if done else "#b5ab95")).pack(side="left", padx=(0, 8))
        tk.Label(top, text=m["title"], font=F_TITLE, bg=cbg,
                 fg=("#9a9080" if locked else INK)).pack(side="left")
        if locked:
            # a locked mission: its title and aim only
            tk.Label(card, text=m["aim"], font=F_TEXT, bg=cbg, fg="#9a9080",
                     wraplength=W - 60, justify="left").pack(anchor="w", pady=(6, 0))
            return
        if is_active:
            tk.Label(top, text="  ACTIVE  ", font=("Segoe UI", 13, "bold"), bg=GREEN,
                     fg="white").pack(side="right")
        elif done:
            tk.Label(top, text=f"completed {got.get(key, '')}", font=F_SMALL, bg=cbg,
                     fg="#8a7a50").pack(side="right")

        # tabs
        # Plant Roulette: while its wheel hasn't been spun to the end, the
        # wheel is a tab of its own (and the one shown)
        wheel_tab = (is_active and key == "mission_roulette"
                     and _rparams(app).get("x") is None)
        card_tabs = TABS + (("Roulette",) if wheel_tab else ())
        cur = tabs.get(key) or ("Roulette" if wheel_tab else
                                ("Progress" if is_active else "Aim"))
        if cur not in card_tabs:
            cur = "Roulette" if wheel_tab else ("Progress" if is_active else "Aim")
        tabbar = tk.Frame(card, bg=cbg)
        tabbar.pack(fill="x", pady=(10, 0))
        for t in card_tabs:
            on = (t == cur)
            lb = tk.Label(tabbar, text=t, font=("Segoe UI", 13, "bold"), padx=14, pady=4,
                          bg=(TAB_ON if on else TAB_OFF), fg=("white" if on else INK),
                          cursor="hand2")
            lb.pack(side="left", padx=(0, 4))
            _click(app, lb, lambda k=key, t=t: (tabs.__setitem__(k, t), _fill()))
        def _aim(p):
            # the aim, and a picture of it below
            tk.Label(p, text=mission_aim(app, m), font=F_TEXT, bg=cbg, fg=INK,
                     wraplength=W - 60, justify="left").pack(anchor="w")
            if m.get("choose_trait") and not is_active:
                _trait_picker(p)
            ex = EXAMPLES.get(m["key"]) or m.get("example")
            if ex is not None:
                # every icon as large as the card allows (all the same size:
                # the children as big as their parents)
                global _EX_SIZE
                try:
                    pic = None
                    for _sz in EX_ICON_SIZES:
                        _EX_SIZE = _sz
                        if pic is not None:
                            pic.destroy()
                        pic = ex(app, p, cbg)
                        pic.update_idletasks()
                        if pic.winfo_reqwidth() <= W - 60:
                            break
                    pic.pack(pady=(10, 0))
                except Exception:
                    import logging
                    logging.exception("mission picture failed: %s", m["key"])
                finally:
                    _EX_SIZE = None

        def _trait_picker(p):
            """The seven traits to click: the chosen one is the mission's."""
            choice = getattr(app, "_mission_choice", None)
            if not isinstance(choice, dict):
                choice = app._mission_choice = {}
            cur_k = choice.get(key)
            warn = getattr(win, "_pick_warn", None) == key and not cur_k
            tk.Label(p, text=("Choose a trait first:" if warn else "Your trait:"),
                     font=F_BOLD, bg=cbg, fg=("#B0102C" if warn else MUTED)
                     ).pack(anchor="w", pady=(10, 4))
            row = tk.Frame(p, bg=cbg)
            row.pack(anchor="w")
            # all boxes the same size (one grid row, equal columns), the
            # pictures in a band of fixed height and the names at the bottom
            for i, (tkey, tname, dom, rec) in enumerate(TRAITS):
                on = (tkey == cur_k)
                cbg2 = SEL_BG if on else cbg
                cell = tk.Frame(row, bg=cbg2, cursor="hand2", padx=4, pady=3,
                                highlightthickness=2,
                                highlightbackground=(SEL_EDGE if on else
                                                     ("#B0102C" if warn else "#ddd3be")))
                cell.grid(row=0, column=i, sticky="nsew", padx=(0, 5))
                row.grid_columnconfigure(i, uniform="trait")
                tk.Label(cell, text=tname.capitalize().replace(" ", "\n"),
                         font=("Segoe UI", 11, "bold" if on else "normal"),
                         bg=cbg2, fg=INK).pack(side="bottom")
                band = tk.Frame(cell, bg=cbg2, height=36, width=74)
                band.pack(side="top", fill="x")
                band.pack_propagate(False)
                ics = tk.Frame(band, bg=cbg2)
                ics.place(relx=0.5, rely=0.5, anchor="center")
                for fm in (dom, rec):
                    try:
                        _photo_label(ics, _trait_pil(tkey, fm, 30), cbg2).pack(side="left", padx=1)
                    except Exception:
                        pass

                def _pick(e=None, tk_=tkey):
                    choice[key] = tk_
                    win._pick_warn = None
                    _fill()
                for w in (cell, band, ics, *ics.winfo_children(), *cell.winfo_children()):
                    _click(app, w, _pick)
                    try:
                        w.configure(cursor="hand2")
                    except Exception:
                        pass

        def _details(p):
            tk.Label(p, text="Mendel's experiment", font=F_BOLD, bg=cbg, fg=MUTED
                     ).pack(anchor="w")
            tk.Label(p, text=m["background"], font=F_TEXT, bg=cbg, fg=INK,
                     wraplength=W - 80, justify="left").pack(anchor="w")
            if m.get("quote"):
                tk.Label(p, text=m["quote"], font=F_QUOTE, bg=cbg, fg="#5a4a20",
                         wraplength=W - 110, justify="left"
                         ).pack(anchor="w", padx=(18, 0), pady=(6, 0))
                tk.Label(p, text="\u2014 " + m.get("quote_src", ""), font=("Segoe UI", 13),
                         bg=cbg, fg=MUTED).pack(anchor="w", padx=(18, 0))
            tk.Label(p, text="How to do it", font=F_BOLD, bg=cbg, fg=MUTED
                     ).pack(anchor="w", pady=(10, 2))
            for i, st in enumerate(m["steps"], 1):
                row = tk.Frame(p, bg=cbg)
                row.pack(fill="x", anchor="w", pady=1)
                tk.Label(row, text=f"{i}.", font=F_BOLD, bg=cbg, fg=INK,
                         width=2, anchor="ne").pack(side="left", anchor="n")
                tk.Label(row, text=st, font=F_TEXT, bg=cbg, fg=INK,
                         wraplength=W - 110, justify="left").pack(side="left", anchor="w")

        def _rows(p, items):
            for it in items:
                    text, ok = it[0], it[1]
                    row = tk.Frame(p, bg=cbg)
                    row.pack(fill="x", anchor="w", pady=1)
                    tk.Label(row, text=("\u2611" if ok else "\u2610"), font=("Segoe UI", 16),
                             bg=cbg, fg=(GREEN if ok else MUTED)).pack(side="left", anchor="n")
                    # the forms as icons (faint while not seen yet)
                    for (tk_, fm, seen_) in (it[2] if len(it) > 2 else []):
                        try:
                            ic = _trait_pil(tk_, fm, 22)
                            _photo_label(row, ic if seen_ else _faded(ic), cbg).pack(
                                side="left", padx=(4, 0))
                        except Exception:
                            pass
                    n_ic = len(it[2]) if len(it) > 2 else 0
                    tk.Label(row, text=text, font=F_TEXT, bg=cbg,
                             fg=(INK if ok else "#6b5a44"), wraplength=W - 90 - 30 * n_ic,
                             justify="left").pack(side="left", anchor="w", padx=(6, 0))

        def _progress(p):
            if is_active:
                prog = evaluate(app, m)
                _rows(p, prog.items)
                if prog.hint:
                    tk.Label(p, text="\u2192 " + prog.hint, font=("Segoe UI", 14, "italic"),
                             bg=cbg, fg="#8a5a20", wraplength=W - 60, justify="left"
                             ).pack(anchor="w", pady=(6, 0))
            elif done:
                rec = load_records(app).get(key)
                if rec and rec.get("items"):
                    tk.Label(p, text=f"How you completed it ({rec.get('date', '')}"
                                     + (f", {rec.get('times')} times" if int(rec.get("times", 1) or 1) > 1
                                        else "") + "):",
                             font=F_BOLD, bg=cbg, fg=MUTED).pack(anchor="w", pady=(0, 4))
                    _rows(p, [tuple(x) if not isinstance(x, tuple) else x for x in rec["items"]])
                    tk.Label(p, text="Accept it again for another go.", font=F_SMALL, bg=cbg,
                             fg=MUTED).pack(anchor="w", pady=(6, 0))
                else:
                    tk.Label(p, text="Completed. You may accept it again for another go "
                                     "(with a different trait, perhaps).",
                             font=F_TEXT, bg=cbg, fg=INK, wraplength=W - 60, justify="left"
                             ).pack(anchor="w")
            else:
                tk.Label(p, text="Accept the mission to follow your progress here.",
                         font=F_TEXT, bg=cbg, fg=MUTED, wraplength=W - 60, justify="left"
                         ).pack(anchor="w")

        # Every tab has the same height: enough for the aim and the
        # progress (with room for a full checklist); the longer details
        # scroll inside it.
        def _measure(build):
            f = tk.Frame(card, bg=cbg)
            build(f)
            f.update_idletasks()
            h = f.winfo_reqheight()
            f.destroy()
            return h
        PAD = 10
        # ...and the details too, as far as the screen allows (only what
        # doesn't fit then scrolls)
        try:
            cap = max(220, int(win.winfo_screenheight() * 0.92) - 330)
        except Exception:
            cap = 420

        def _measure_details():
            f = tk.Frame(card, bg=cbg, padx=14, pady=PAD)
            _details(f)
            f.update_idletasks()
            h = f.winfo_reqheight()
            f.destroy()
            return h
        # as tall as the aim (with its picture) or the progress needs — no
        # more; the longer details scroll inside it
        page_h = max(_measure(_aim), _measure(_progress),
                     240) + 2 * PAD + 8
        page_h = min(page_h, cap)
        if cur == "Roulette":
            # the wheel needs its full height
            page_h = max(page_h, _measure(lambda f: roulette_panel(app, f, cbg).pack())
                         + 2 * PAD + 4)
            app._roulette_panel = None
        page = tk.Frame(card, bg=cbg, highlightbackground=EDGE, highlightthickness=1,
                        height=page_h)
        page.pack(fill="x")
        page.pack_propagate(False)

        if cur == "Details":
            dc = tk.Canvas(page, bg=cbg, highlightthickness=0, bd=0)
            dsb = tk.Scrollbar(page, orient="vertical", command=dc.yview)
            dc.configure(yscrollcommand=dsb.set)
            dsb.pack(side="right", fill="y")
            dc.pack(side="left", fill="both", expand=True)
            dinner = tk.Frame(dc, bg=cbg, padx=14, pady=PAD)
            dc.create_window((0, 0), window=dinner, anchor="nw")
            _details(dinner)
            dinner.update_idletasks()
            dc.configure(scrollregion=(0, 0, dinner.winfo_reqwidth(), dinner.winfo_reqheight()))
            dc._is_details = True
            win._details_canvas = dc
        else:
            body = tk.Frame(page, bg=cbg, padx=14, pady=PAD)
            body.pack(fill="both", expand=True)
            if cur == "Roulette":
                roulette_panel(app, body, cbg).pack(anchor="n")
            else:
                (_aim if cur == "Aim" else _progress)(body)

        # buttons
        bar = tk.Frame(card, bg=cbg)
        bar.pack(fill="x", pady=(10, 0))
        if is_active:
            _btn(bar, "Abandon mission", lambda: abandon(app, parent=win)).pack(side="right")
        else:
            def _acc(k=key, m=m):
                # a mission with a choice (Pure Lines: the trait) needs it first
                if m.get("choose_trait") and not (
                        getattr(app, "_mission_choice", None) or {}).get(k):
                    tabs[k] = "Aim"
                    win._pick_warn = k
                    _fill()
                    return
                # the tab to show is set first: accepting rebuilds the board
                # once, already on it
                before = tabs.get(k)
                tabs[k] = "Roulette" if k == "mission_roulette" else "Progress"
                if not accept(app, k, parent=win):
                    if before is None:
                        tabs.pop(k, None)
                    else:
                        tabs[k] = before
            _btn(bar, "Accept mission" if not done else "Accept again", _acc,
                 primary=True).pack(side="right")
            tk.Label(bar, text=(("Leaves the practice garden, saves your own garden "
                                 if getattr(app, "_tutorial_active", False) else
                                 "Saves your current garden ")
                                + "(\u201cBefore the mission\u201d, File > Load) and starts "
                                  "a new one for the mission."),
                     font=F_SMALL, bg=cbg, fg=MUTED, wraplength=W - 260, justify="left"
                     ).pack(side="left", anchor="w")

    win._fill = _fill

    bar = tk.Frame(win, bg=bg, padx=22, pady=12)
    bar.pack(fill="x")
    _btn(bar, "Close", win.destroy).pack(side="right")

    def _on_wheel(e):
        if getattr(e, "num", None) == 4:
            step = -1
        elif getattr(e, "num", None) == 5:
            step = 1
        else:
            d = int(getattr(e, "delta", 0) or 0)
            if d == 0:
                return
            step = -int(d / 120) if abs(d) >= 120 else (-1 if d > 0 else 1)
        # over a card's details: they scroll, not the board
        try:
            w = win.winfo_containing(e.x_root, e.y_root)
            while w is not None and w is not win:
                if getattr(w, "_is_details", False):
                    w.yview_scroll(step * 2, "units")
                    return
                w = w.master
        except Exception:
            pass
        canvas.yview_scroll(step * 2, "units")
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        win.bind(seq, _on_wheel)        # (the window's tag: every widget in it)
    win.bind("<Escape>", lambda e: win.destroy())
    # the arrow keys go through the missions of the tier shown
    win.bind("<Left>", lambda e: getattr(win, "_step", lambda d: None)(-1))
    win.bind("<Right>", lambda e: getattr(win, "_step", lambda d: None)(1))

    # live progress while the board is open (rebuilt only when it changed)
    def _signature():
        try:
            got = app._load_achievements()
        except Exception:
            got = {}
        m = active_mission(app)
        p = evaluate(app, m) if m is not None else None
        return (tuple(sorted(got)), getattr(app, "_active_mission", None),
                tuple(p.items) if p else (), p.hint if p else "", _blocked_reason(app))

    win._signature = _signature

    def _live():
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        try:
            sig = _signature()
            spinning = (getattr(app, "_roulette_state", None) or {}).get("spinning")
            if sig != getattr(win, "_sig", None) and not spinning:
                win._sig = sig
                y = canvas.yview()[0]
                _fill()
                canvas.yview_moveto(y)
        except Exception:
            pass
        win.after(3000, _live)

    _fill()
    try:
        win._sig = _signature()
    except Exception:
        pass
    # centred, at the top of the screen
    try:
        win.update_idletasks()
        x = max(0, (win.winfo_screenwidth() - win.winfo_reqwidth()) // 2)
        win.geometry(f"+{x}+{12}")
    except Exception:
        pass
    win.deiconify()
    win.lift()
    win.after(3000, _live)
    return win
