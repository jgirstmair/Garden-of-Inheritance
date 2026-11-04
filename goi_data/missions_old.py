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


def check_pure_line(app):
    """Two pure lines of one trait, one for each form (e.g. a purple and a
    white line): each a parent whose PURE_NEED selfed offspring showed the
    trait, all like it."""
    from collections import Counter
    plants = _all_plants(app)
    kids = _selfed_children(plants)
    # best line per (trait, form): (score, parent, Counter)
    lines = {}
    for pid, ch in kids.items():
        par = plants.get(pid)
        for key, *_ in TRAITS:
            if key in SEED_TRAITS:
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
            txt += " \u2014 not pure"
        return (txt, done)

    # the trait closest to two pure lines
    best_key, best_score = None, None
    for key, _n, dom, rec in TRAITS:
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
        items = [("Let plants pollinate themselves and sow their seeds", n > 0),
                 (f"A pure line of one form: {PURE_NEED} offspring all like their parent", False),
                 ("A pure line of the other form of the same trait", False)]
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

def check_seven(app):
    plants = _all_plants(app)
    seen = {k: set() for k, *_ in TRAITS}
    for s in plants.values():
        for key, *_ in TRAITS:
            v = _known(s, key)
            if v:
                seen[key].add(v)
    items = []
    n_done = 0
    for key, name, dom, rec in TRAITS:
        both = dom in seen[key] and rec in seen[key]
        n_done += both
        marks = " and ".join(f"{_form_label(key, f)}" + ("" if f in seen[key] else " (not yet)")
                             for f in (dom, rec))
        items.append((f"{name.capitalize()}: {marks}", both))
    hint = "" if n_done == 7 else ("Sow seeds of many different plants: starter seeds are "
                                   "a good mixture. Traits show as the plants grow.")
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
    tk.Label(box, text="one island", font=("Segoe UI", 9, "italic"), bg=bg,
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
        "a pure white or pure purple plant come true." if best_partial else
        "Sow seeds of pure white and pure purple plants in a pattern: "
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
                 ("Both forms are back, about three to one", False)]
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
    items = [("Hybrids (F1) raised", True),
             (f"Grandchildren (F2) showing their {_TRAIT_NAME[key]}: {min(tot, F2_NEED)}/{F2_NEED}  "
              f"({_counts_line(c)})", tot >= F2_NEED),
             (f"Both forms are back, about three to one (now {ratio})", done)]
    hint = "" if done else (
        f"Raise more grandchildren: {F2_NEED} that show the trait." if tot < F2_NEED else
        "The ratio is still far from 3 : 1: raise more plants, the numbers even out.")
    return Progress(done, items, hint)


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
            ("Cross two pure lines and let their hybrids pollinate themselves", False),
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
    # at least one dominant form: those take the real work (a pure line)
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
# The missions
# ---------------------------------------------------------------------------

TIERS = ("easy", "medium", "hard")
TIER_NAMES = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}

MISSIONS = [
    # ---------------- easy ----------------
    {
        "key": "mission_pure_line",
        "tier": "easy",
        "title": "Pure Lines",
        "short": "Pure Lines",
        "aim": ("Find two pure lines of one trait, one for each form (e.g. purple and white "
                "flowers): self-pollinated plants whose offspring all look like their parent."),
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
            "Sow them and raise the young plants until they show the trait: flower colour, "
            "height, pods or flower position.",
            f"Needed for each form: {PURE_NEED} offspring that show the trait, all like their "
            "parent.",
        ],
        "check": check_pure_line,
        "achievement": "Pure Lines",
        "congrats": ("Every child just like its parent, in both lines! Pure lines, Gregor: "
                     "material you can trust. Mendel spent two whole years making sure of his."),
    },
    {
        "key": "mission_seven",
        "tier": "easy",
        "title": "The Seven Characters",
        "short": "Seven Characters",
        "aim": ("Find both forms of each of Mendel's seven characters growing in your "
                "garden: fourteen forms in all."),
        "background": (
            "Out of the many differences between his pea varieties Mendel chose seven that "
            "come in two clearly distinct forms: the shape and colour of the seed, the "
            "colour of the flower, the shape and colour of the pod, where the flowers sit "
            "and the length of the stem."),
        "steps": [
            "Sow many different seeds: the starter seeds are a good mixture.",
            "Seed shape and colour you see on the pea. Flower colour and position show "
            "when the plants flower, the pods once they form, the height as they grow.",
            "Needed: both forms of all seven traits seen in this garden.",
        ],
        "check": check_seven,
        "achievement": "The Seven Characters",
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
            "pure line can promise that."),
        "steps": [
            "Collect seeds of pure white and pure purple plants (their offspring all flower "
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
        "title": "Three to One",
        "short": "Three to One",
        "aim": ("Cross two pure lines, let their hybrids pollinate themselves, and show that "
                "the hidden form returns in the grandchildren, in about one plant of four."),
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
            "Raise hybrids (F1) from a cross of two pure lines, e.g. purple × white.",
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
            "Cross two pure lines that differ in one trait and raise the hybrids (F1).",
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
        "aim": ("Breed a pure line with three traits chosen at random when you accept: a "
                "plant that shows all three, whose own offspring all show them too."),
        "aim_active": "Breed a pure line with {target}: a plant that shows all three, whose "
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
        "congrats": ("A new pure line, made by your own hand! Three traits brought together "
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
    if getattr(app, "_tutorial_active", False):
        app._toast("Leave the tutorial first (Monastery > Mendel's Garden).", level="info")
        return False
    if not tier_unlocked(app, m["tier"]):
        app._toast("Complete the missions before it first.", level="info")
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
    if not evaluate(app, m).done:
        return
    try:
        before = app._load_achievements()
    except Exception:
        before = {}
    new = app._award_achievement(m["key"])
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

F_TITLE = ("Segoe UI", 15, "bold")
F_TEXT = ("Segoe UI", 12)
F_BOLD = ("Segoe UI", 12, "bold")
F_SMALL = ("Segoe UI", 10, "italic")
F_QUOTE = ("Georgia", 13, "italic")
TABS = ("Aim", "Details", "Progress")
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

    head = tk.Frame(win, bg=bg, padx=22, pady=14)
    head.pack(fill="x")
    tk.Label(head, text="Missions", font=("Segoe UI", 18, "bold"), bg=bg, fg=INK).pack(side="left")
    count_lbl = tk.Label(head, text="", font=("Segoe UI", 12, "italic"), bg=bg, fg=MUTED)
    count_lbl.pack(side="left", padx=(12, 0), pady=(4, 0))
    tk.Label(win, text="Experiments to pursue. Accept one to play it in a garden of its own; "
                       "it completes by itself once your garden shows the result.",
             font=("Segoe UI", 11, "italic"), bg=bg, fg=MUTED, padx=22,
             anchor="w", justify="left", wraplength=700).pack(fill="x")
    warn = tk.Label(win, text="", font=("Segoe UI", 11, "bold"), bg=bg, fg="#a33",
                    padx=22, anchor="w", justify="left", wraplength=700)
    warn.pack(fill="x")

    body = tk.Frame(win, bg=bg)
    body.pack(fill="both", expand=True, padx=(22, 8), pady=(6, 0))
    canvas = tk.Canvas(body, bg=bg, highlightthickness=0, bd=0)
    sb = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=bg)
    canvas.create_window((0, 0), window=inner, anchor="nw")

    W = 700

    def _fill():
        for w in inner.winfo_children():
            w.destroy()
        try:
            got = app._load_achievements()
        except Exception:
            got = {}
        warn.configure(text=("Missions can't be accepted in Abbot Cyril's practice garden."
                             if getattr(app, "_tutorial_active", False) else
                             _blocked_reason(app) if active_mission(app) else ""))
        n_done = sum(1 for m in MISSIONS if m["key"] in got)
        # (an accepted mission's tier is shown when the board opens for it)
        count_lbl.configure(text=f"{n_done} of {len(MISSIONS)} completed")
        # one tier at a time: Easy | Medium | Hard (locked ones with a lock)
        cur_tier = getattr(app, "_missions_tier", None)
        if cur_tier not in TIERS:
            am = active_mission(app)
            cur_tier = am["tier"] if am else max(
                (t for t in TIERS if tier_unlocked(app, t, got)), key=TIERS.index)
        tierbar = tk.Frame(inner, bg=bg)
        tierbar.pack(fill="x", pady=(6, 2))
        for t in TIERS:
            open_ = tier_unlocked(app, t, got)
            n_t = sum(1 for m in tier_missions(t) if m["key"] in got)
            on = (t == cur_tier)
            txt = f"{TIER_NAMES[t]}  {n_t}/{len(tier_missions(t))}" if open_ else \
                f"\U0001F512 {TIER_NAMES[t]}"
            lb = tk.Label(tierbar, text=txt, font=("Segoe UI", 12, "bold"), padx=16, pady=5,
                          bg=(TAB_ON if on else TAB_OFF),
                          fg=("white" if on else (INK if open_ else "#9a9080")), cursor="hand2")
            lb.pack(side="left", padx=(0, 6))
            lb.bind("<Button-1>", lambda e, t=t: (setattr(app, "_missions_tier", t), _fill()))
        tk.Frame(inner, height=1, bg="#c8c0ac", width=W).pack(fill="x", pady=(4, 6))
        locked = not tier_unlocked(app, cur_tier, got)
        if locked:
            prev = TIERS[TIERS.index(cur_tier) - 1]
            tk.Label(inner, text=f"\U0001F512  Complete all {TIER_NAMES[prev].lower()} missions "
                                 f"(in any order) to unlock these.",
                     font=("Segoe UI", 12, "italic"), bg=bg, fg="#8a5a20", wraplength=W,
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
            a = tk.Label(nav, text=sym, font=("Segoe UI", 16, "bold"), bg=TAB_OFF, fg=INK,
                         padx=14, pady=2, cursor="hand2")
            a.pack(side=side)
            a.bind("<Button-1>", lambda e, d=d: _step(d))
            a.bind("<Enter>", lambda e, a=a: a.configure(bg="#ddd3be"))
            a.bind("<Leave>", lambda e, a=a: a.configure(bg=TAB_OFF))
        dots = tk.Frame(nav, bg=bg)
        dots.pack(expand=True)
        tk.Label(dots, text=f"{i + 1} / {len(ms)}", font=("Segoe UI", 12, "bold"), bg=bg,
                 fg=MUTED).pack(side="left", padx=(0, 10))
        for j, mm in enumerate(ms):
            c = ("\u25CF" if j == i else "\u25CB")
            col = ("#B8860B" if mm["key"] in got else (GREEN if active_mission(app) is mm else MUTED))
            d_ = tk.Label(dots, text=c, font=("Segoe UI", 12), bg=bg, fg=col, cursor="hand2")
            d_.pack(side="left", padx=2)
            d_.bind("<Button-1>", lambda e, j=j, t=cur_tier: (idxs.__setitem__(t, j), _fill()))
        _card(ms[i], got, locked)
        win.update_idletasks()
        need_h = inner.winfo_reqheight()
        need_w = max(W + 20, inner.winfo_reqwidth())
        view_h = min(need_h, int(win.winfo_screenheight() * 0.7))
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
                          font=("Segoe UI", 11, "bold" if primary else "normal"))
            except Exception:
                pass
        return tk.Button(parent, text=text, command=cmd, font=("Segoe UI", 11))

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
        tk.Label(top, text=("\u2605" if done else "\u2606"), font=("Segoe UI", 18), bg=cbg,
                 fg=("#B8860B" if done else "#b5ab95")).pack(side="left", padx=(0, 8))
        tk.Label(top, text=m["title"], font=F_TITLE, bg=cbg,
                 fg=("#9a9080" if locked else INK)).pack(side="left")
        if locked:
            # a locked mission: its title and aim only
            tk.Label(card, text=m["aim"], font=F_TEXT, bg=cbg, fg="#9a9080",
                     wraplength=W - 60, justify="left").pack(anchor="w", pady=(6, 0))
            return
        if is_active:
            tk.Label(top, text="  ACTIVE  ", font=("Segoe UI", 10, "bold"), bg=GREEN,
                     fg="white").pack(side="right")
        elif done:
            tk.Label(top, text=f"completed {got.get(key, '')}", font=F_SMALL, bg=cbg,
                     fg="#8a7a50").pack(side="right")

        # tabs
        cur = tabs.get(key) or ("Progress" if is_active else "Aim")
        tabbar = tk.Frame(card, bg=cbg)
        tabbar.pack(fill="x", pady=(10, 0))
        for t in TABS:
            on = (t == cur)
            lb = tk.Label(tabbar, text=t, font=("Segoe UI", 11, "bold"), padx=14, pady=4,
                          bg=(TAB_ON if on else TAB_OFF), fg=("white" if on else INK),
                          cursor="hand2")
            lb.pack(side="left", padx=(0, 4))
            lb.bind("<Button-1>", lambda e, k=key, t=t: (tabs.__setitem__(k, t), _fill()))
        def _aim(p):
            ex = m.get("example")
            row = tk.Frame(p, bg=cbg)
            row.pack(fill="x")
            if ex is not None:
                try:
                    ex(app, row, cbg).pack(side="right", anchor="n", padx=(12, 0))
                except Exception:
                    pass
            tk.Label(row, text=mission_aim(app, m), font=F_TEXT, bg=cbg, fg=INK,
                     wraplength=(W - 60 - (150 if ex is not None else 0)),
                     justify="left").pack(side="left", anchor="nw")

        def _details(p):
            tk.Label(p, text="Mendel's experiment", font=F_BOLD, bg=cbg, fg=MUTED
                     ).pack(anchor="w")
            tk.Label(p, text=m["background"], font=F_TEXT, bg=cbg, fg=INK,
                     wraplength=W - 80, justify="left").pack(anchor="w")
            if m.get("quote"):
                tk.Label(p, text=m["quote"], font=F_QUOTE, bg=cbg, fg="#5a4a20",
                         wraplength=W - 110, justify="left"
                         ).pack(anchor="w", padx=(18, 0), pady=(6, 0))
                tk.Label(p, text="\u2014 " + m.get("quote_src", ""), font=("Segoe UI", 10),
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

        def _progress(p):
            if is_active:
                prog = evaluate(app, m)
                for text, ok in prog.items:
                    row = tk.Frame(p, bg=cbg)
                    row.pack(fill="x", anchor="w", pady=1)
                    tk.Label(row, text=("\u2611" if ok else "\u2610"), font=("Segoe UI", 14),
                             bg=cbg, fg=(GREEN if ok else MUTED)).pack(side="left", anchor="n")
                    tk.Label(row, text=text, font=F_TEXT, bg=cbg,
                             fg=(INK if ok else "#6b5a44"), wraplength=W - 90, justify="left"
                             ).pack(side="left", anchor="w", padx=(6, 0))
                if prog.hint:
                    tk.Label(p, text="\u2192 " + prog.hint, font=("Segoe UI", 12, "italic"),
                             bg=cbg, fg="#8a5a20", wraplength=W - 60, justify="left"
                             ).pack(anchor="w", pady=(6, 0))
            elif done:
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
        page_h = max(_measure(_aim), _measure(_progress),
                     PAGE_MIN_H if is_active else 100) + 2 * PAD + 2
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
            (_aim if cur == "Aim" else _progress)(body)

        # buttons
        bar = tk.Frame(card, bg=cbg)
        bar.pack(fill="x", pady=(10, 0))
        if is_active:
            _btn(bar, "Abandon mission", lambda: abandon(app, parent=win)).pack(side="right")
        elif not getattr(app, "_tutorial_active", False):
            def _acc(k=key):
                if accept(app, k, parent=win):
                    tabs[k] = "Progress"
                    _fill()
            _btn(bar, "Accept mission" if not done else "Accept again", _acc,
                 primary=True).pack(side="right")
            tk.Label(bar, text="Starts a new garden for the mission. Your current garden "
                               "is saved as \u201cBefore the mission\u201d (File > Load).",
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

    def _live():
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        try:
            sig = _signature()
            if sig != getattr(win, "_sig", None):
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
    try:
        app._center_on_screen(win)
    except Exception:
        pass
    win.deiconify()
    win.lift()
    win.after(3000, _live)
    return win
