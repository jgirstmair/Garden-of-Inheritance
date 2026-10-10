"""
Wildlife Module — Garden of Inheritance
========================================
Bees, butterflies, and the pea weevil (Bruchus pisi) roam garden tiles,
preferring purple/white flower pixels of the plant icons.

Place PNG files in  icons/wildlife/  next to Garden-of-Inheritance.py.
Naming convention — numbered variants are auto-discovered:

    butterfly1_frame1.png     ← required per variant
    butterfly1_frame2.png     ← optional (animation frame 2)
    butterfly2_frame1.png
    bee1_frame1.png  ...
    bruchus_pisi_frame1.png   ← single variant is fine

Each spawn picks a random variant. Only one creature is allowed per flower
cluster at a time — if all flowers on a tile are occupied, that tile is skipped.
"""

import logging
import math
import os
import random
import tkinter as tk

try:
    from PIL import Image, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

log = logging.getLogger("Wildlife")

# ---------------------------------------------------------------------------
# Icon directory
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_SEARCH = [
    os.path.join(_HERE, "icons", "wildlife"),
    os.path.join(_HERE, "wildlife"),
    os.path.join(_HERE, "icons"),
    _HERE,
]

def _find_icon_dir():
    for p in _SEARCH:
        if os.path.isdir(p):
            try:
                if any(f.endswith("_frame1.png") for f in os.listdir(p)):
                    return p
            except Exception:
                pass
    return None

# ---------------------------------------------------------------------------
# Colour landmarks — calibrated from actual plant icon pixel values
# ---------------------------------------------------------------------------
_PURPLE_FLOWER = [
    (154, 130, 182), (171, 144, 193), (144, 105, 163),
    (130,  90, 160), (160, 120, 190), (178, 156, 218),
    (191, 166, 232), (166, 145, 188),
]
_WHITE_FLOWER = [
    (238, 239, 237), (239, 244, 236), (220, 220, 230),
    (230, 230, 235), (245, 245, 243),
]
_POD_GREEN  = [(80,160,60),(70,140,50),(90,170,70),(100,150,60),(60,130,50)]
_POD_YELLOW = [(200,180,60),(210,190,70),(190,170,50),(220,200,80)]

_FLOWER_TOL = 42
_POD_TOL    = 48

def _cdist(a, b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))

def _matches(rgb, targets, tol):
    return any(_cdist(rgb, t) <= tol for t in targets)

# ---------------------------------------------------------------------------
# Creature definitions: (name, icon_prefix, weight, pods_only, active_months)
# ---------------------------------------------------------------------------
# TEST SWITCH: True = every visitor is a pea weevil (Bruchus pisi), in any
# month, on any flowering or growing plant, and much more often — to try
# out catching it. Set back to False for normal wildlife.
DEBUG_ALL_BRUCHUS = False

# At game speeds of SLOW_SPEED_SECS real seconds per game hour or slower
# (Real Time = 3600), wildlife also gets a spawn check every SLOW_CHECK_MS.
SLOW_SPEED_SECS = 300.0
SLOW_CHECK_MS = 3 * 60 * 1000

CREATURE_DEFS = [
    ("butterfly", "butterfly",    8, False, (3,4,5,6,7,8,9,10)),
    ("bee",       "bee",          8, False, (3,4,5,6,7,8,9)),
    ("bruchus",   "bruchus_pisi", 1, True,  (5,6,7,8)),
]

# ---------------------------------------------------------------------------
# Timing (milliseconds)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Frequency presets (applied via WildlifeManager.set_frequency)
# ---------------------------------------------------------------------------
_FREQ_PRESETS = {
    "low":    dict(spawn_chance=0.18, max_active=2, revisit_min=18000, revisit_max=55000),
    "medium": dict(spawn_chance=0.32, max_active=3, revisit_min=10000, revisit_max=35000),
    "high":   dict(spawn_chance=0.45, max_active=4, revisit_min=6000,  revisit_max=25000),
}

FRAME_MS    = 900
WANDER_MS   = 1400
MIN_STAY_MS = 12000         # one visit lasts 12–42 s (real time)
MAX_STAY_MS = 42000

# Flight (bees and top-view butterflies glide from flower to flower)
FLY_STEP_MS   = 40          # ~25 fps, only while actually flying
FLAP_STEPS    = 3           # swap wing frame every 3 flight steps
HOP_MIN_MS    = 2500        # pause on a flower before maybe flying on
HOP_MAX_MS    = 5500
HOP_OTHER_PLANT = 0.5       # chance a hop goes to a nearby flowering plant
HOP_RANGE_TILES = 2.5       # how far (in plot widths) such a hop may go
REVISIT_MIN = 18000   # default: low frequency
REVISIT_MAX = 55000
MAX_ACTIVE  = 2
SPAWN_CHANCE = 0.18

def _visible_aspect(pil):
    """Width / height of the drawn part of a picture (transparent margins
    ignored) — open wings seen from above are wide, folded wings tall."""
    try:
        box = pil.convert("RGBA").getchannel("A").point(lambda a: 255 if a > 40 else 0).getbbox()
        if box:
            w, h = box[2] - box[0], box[3] - box[1]
            return w / max(1, h)
        return pil.width / max(1, pil.height)
    except Exception:
        return 1.0

# The butterfly pictures by file name: species and whether the picture
# shows open wings from above (True) or folded wings from the side (False).
BUTTERFLY_FILES = {
    "butterfly1": ("white",      True),    # Small white (Pieris rapae)
    "butterfly2": ("orangetip",  True),    # Orange-tip (Anthocharis cardamines)
    "butterfly3": ("commonblue", True),    # Common blue (Polyommatus icarus)
    "butterfly4": ("fritillary", True),    # Queen of Spain fritillary (Issoria lathonia)
    "butterfly5": ("peacock",    True),    # Peacock (Aglais io)
    "butterfly6": ("peacock",    False),   # Peacock, wings folded
    "butterfly7": ("fritillary", False),   # Queen of Spain fritillary, wings folded
}

def butterfly_species(variant):
    entry = BUTTERFLY_FILES.get(str(getattr(variant, "label", "")).lower())
    return entry[0] if entry else None

def _is_top_view(variant):
    """Open wings seen from above — by the file-name table first, then by
    words in the name ('side'/'closed'/'folded' vs 'top'/'open'), else by
    the picture's shape."""
    name = str(getattr(variant, "label", "")).lower()
    if name in BUTTERFLY_FILES:
        return BUTTERFLY_FILES[name][1]
    if any(w in name for w in ("side", "closed", "folded", "sitting")):
        return False
    if any(w in name for w in ("top", "open", "spread")):
        return True
    try:
        return _visible_aspect(variant._refs[0]) >= 1.1
    except Exception:
        return True

# ---------------------------------------------------------------------------
# Variant (one numbered icon set, e.g. butterfly3 with frame1 + frame2)
# ---------------------------------------------------------------------------
class _Variant:
    def __init__(self, label: str):
        self.label  = label
        self.frames = []
        self._refs  = []

    def load_from(self, icon_dir: str):
        self.frames = []
        self._refs  = []
        for n in (1, 2):
            path = os.path.join(icon_dir, f"{self.label}_frame{n}.png")
            if not os.path.exists(path):
                break
            try:
                if _PIL:
                    pil = Image.open(path).convert("RGBA")
                    img = ImageTk.PhotoImage(pil)
                    self._refs.append(pil)
                else:
                    img = tk.PhotoImage(file=path)
                self.frames.append(img)
            except Exception as exc:
                log.error("Wildlife: failed loading %s — %s", path, exc)
                break

    def ready(self):
        return len(self.frames) > 0

    def frame(self, idx: int):
        if not self.frames:
            return None
        return self.frames[idx % len(self.frames)]


def _discover_variants(icon_dir: str, prefix: str) -> list:
    if not icon_dir or not os.path.isdir(icon_dir):
        return []
    try:
        files = os.listdir(icon_dir)
    except Exception:
        return []
    bases = set()
    for f in files:
        if f.endswith("_frame1.png") and f.startswith(prefix):
            bases.add(f[:-len("_frame1.png")])
    variants = []
    for base in sorted(bases):
        v = _Variant(base)
        v.load_from(icon_dir)
        if v.ready():
            variants.append(v)
    return variants

# ---------------------------------------------------------------------------
# Pixel scanning and clustering
# ---------------------------------------------------------------------------
def _scan_spots(pil_img, pods_only: bool) -> list:
    """Return (x,y) flower/pod pixel positions in the PIL image."""
    if pil_img is None:
        return []
    try:
        data = pil_img.load()
        w, h = pil_img.size
    except Exception:
        return []

    flower_spots, pod_spots = [], []
    for y in range(h):
        for x in range(w):
            try:
                r, g, b, a = data[x, y]
            except Exception:
                continue
            if a < 80:
                continue
            rgb = (r, g, b)
            if not pods_only:
                if (_matches(rgb, _PURPLE_FLOWER, _FLOWER_TOL) or
                        _matches(rgb, _WHITE_FLOWER, _FLOWER_TOL)):
                    flower_spots.append((x, y))
            if (_matches(rgb, _POD_GREEN, _POD_TOL) or
                    _matches(rgb, _POD_YELLOW, _POD_TOL)):
                pod_spots.append((x, y))

    return pod_spots if pods_only else flower_spots


def _cluster_spots(spots: list, radius: int = 8) -> list:
    """Group nearby (x,y) spots into clusters. Returns list of cluster lists."""
    if not spots:
        return []
    remaining = list(spots)
    clusters = []
    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        queue = [seed]
        while queue:
            cx, cy = queue.pop(0)
            still = []
            for p in remaining:
                if abs(p[0] - cx) <= radius and abs(p[1] - cy) <= radius:
                    cluster.append(p)
                    queue.append(p)
                else:
                    still.append(p)
            remaining = still
        clusters.append(cluster)
    return clusters


def _centroid(cluster):
    """Return integer (x, y) centroid of a cluster."""
    return (
        int(sum(p[0] for p in cluster) / len(cluster)),
        int(sum(p[1] for p in cluster) / len(cluster)),
    )

# ---------------------------------------------------------------------------
# Single creature
# ---------------------------------------------------------------------------
class _Creature:
    def __init__(self, mgr, type_name: str, pods_only: bool,
                 tile, cx: int, cy: int, variant: _Variant,
                 cluster_key: tuple):
        self.mgr         = mgr
        self.type_name   = type_name
        self.pods_only   = pods_only
        self.tile        = tile
        self.variant     = variant
        self.cluster_key = cluster_key   # (id(tile), cx, cy) for occupancy
        self.cx          = cx
        self.cy          = cy
        self._fi         = 0
        self._item       = None
        self._alive      = True
        self._jobs       = []
        self._flying     = False
        self._rest_variant = variant
        self._fly_variant  = variant
        self.flier       = self._is_flier()
        self._appear()

    def _is_flier(self):
        """Bees and butterflies seen from above fly; folded-wing side views
        and the weevil stay put."""
        if self.type_name == "bee":
            return True
        if self.type_name != "butterfly":
            return False
        if _is_top_view(self.variant):
            return True
        # Seen from the side (wings folded): it rests like that, and opens
        # its wings — switches to the same species' top view — to fly.
        top = self.mgr._top_view_partner(self.variant)
        if top is None:
            return False
        self._fly_variant = top
        return True

    def _set_view(self, flying):
        """Side-view butterflies show their open-wing picture in flight."""
        v = self._fly_variant if flying else self._rest_variant
        if v is self.variant or self._item is None:
            return
        self.variant = v
        try:
            self.tile.itemconfig(self._item, image=v.frame(0))
        except Exception:
            pass

    def _appear(self):
        img = self.variant.frame(0)
        if img is None:
            self._alive = False
            return
        try:
            self._item = self.tile.create_image(
                self.cx, self.cy, image=img,
                anchor="center", tags=("wildlife", self.type_name))
            if self.type_name == "bruchus":
                # The pea weevil can be caught: a hand over it hints so.
                self.tile.tag_bind(self._item, "<Enter>",
                                   lambda e: self.tile.configure(cursor="hand2"))
                self.tile.tag_bind(self._item, "<Leave>",
                                   lambda e: self.tile.configure(cursor=""))
            self.tile.tag_raise("wildlife")
        except Exception as exc:
            log.debug("Wildlife appear error: %s", exc)
            self._alive = False
            return

        stay = random.randint(MIN_STAY_MS, MAX_STAY_MS)
        self._later(FRAME_MS,  self._tick_anim)
        self._later(WANDER_MS, self._wander)
        if self.flier:
            # Appears on its flower, then hops around from there.
            self._schedule_hop()
            self._later(stay, self._leave)
        else:
            self._later(stay, self._depart)

    # ── Flight ────────────────────────────────────────────────────────────────
    def _ts(self):
        try:
            return int(getattr(self.tile, "w", 0) or self.tile.winfo_width() or 85)
        except Exception:
            return 85

    def _edge_point(self):
        ts = self._ts()
        m = 14
        side = random.randint(0, 3)
        r = random.randint(0, ts)
        return [(-m, r), (ts + m, r), (r, -m), (r, ts + m)][side]

    def _fly_to(self, tx, ty, then=None, dest=None):
        """Glide to (tx, ty) on `dest` (a plot canvas; default: the current
        one) on a gently curved, slightly wobbly path. Every plot is its own
        canvas, so the flight is planned in screen coordinates and the
        picture is handed over to whichever plot it is flying over."""
        if not self._alive or self._item is None:
            return
        dest = dest or self.tile
        self._set_view(True)
        try:
            ox, oy = self.tile.winfo_rootx(), self.tile.winfo_rooty()
            dx0, dy0 = dest.winfo_rootx(), dest.winfo_rooty()
        except Exception:
            ox = oy = dx0 = dy0 = 0
            dest = self.tile
        self._flying = True
        x0, y0 = float(ox + self.cx), float(oy + self.cy)        # screen coords
        X1, Y1 = float(dx0 + tx), float(dy0 + ty)
        dx, dy = X1 - x0, Y1 - y0
        dist = max(1.0, math.hypot(dx, dy))
        butterfly = self.type_name == "butterfly"
        speed = random.uniform(55, 85) if butterfly else random.uniform(80, 120)  # px/s
        steps = max(6, int(dist / speed * 1000 / FLY_STEP_MS))
        arc = random.uniform(-0.35, 0.35) * dist if butterfly else random.uniform(-0.15, 0.15) * dist
        arc = max(-60.0, min(60.0, arc))
        wob = 1.6 if butterfly else 0.7
        nx, ny = -dy / dist, dx / dist           # perpendicular
        state = {"i": 0, "f": 0}

        # Plots the path may cross (screen rectangles), measured once.
        rects = []
        if dest is not self.tile:
            pad = abs(arc) + 20
            bx0, bx1 = min(x0, X1) - pad, max(x0, X1) + pad
            by0, by1 = min(y0, Y1) - pad, max(y0, Y1) + pad
            for t in self.mgr._visible_tiles():
                try:
                    rx, ry = t.winfo_rootx(), t.winfo_rooty()
                    rw, rh = t.winfo_width(), t.winfo_height()
                except Exception:
                    continue
                if rx < bx1 and rx + rw > bx0 and ry < by1 and ry + rh > by0:
                    rects.append((t, rx, ry, rw, rh))

        def host_at(X, Y):
            for t, rx, ry, rw, rh in rects:
                if rx <= X < rx + rw and ry <= Y < ry + rh:
                    return t, rx, ry
            return None

        def step():
            if not self._alive or self._item is None:
                return
            if getattr(self.mgr.app, "fast_forward", False):
                self.destroy()
                return
            state["i"] += 1
            t = state["i"] / steps
            e = t * t * (3 - 2 * t)              # ease in/out
            bend = math.sin(math.pi * t) * arc
            X = x0 + dx * e + nx * bend + random.uniform(-wob, wob)
            Y = y0 + dy * e + ny * bend + random.uniform(-wob, wob)
            if state["i"] >= steps:
                X, Y = X1, Y1
            try:
                if state["i"] % FLAP_STEPS == 0 and len(self.variant.frames) > 1:
                    state["f"] ^= 1
                img = self.variant.frame(state["f"])
                if rects:
                    h = host_at(X, Y)
                    if state["i"] >= steps:
                        h = (dest, dx0, dy0)
                    if h is not None and h[0] is not self.tile:
                        self._move_to_canvas(h[0])
                    self._sync_ghosts(X, Y, img, rects, final=state["i"] >= steps)
                    rx, ry = self._root_of(self.tile, rects)
                else:
                    rx, ry = ox, oy
                self.cx, self.cy = int(round(X - rx)), int(round(Y - ry))
                self.tile.coords(self._item, self.cx, self.cy)
                self.tile.itemconfig(self._item, image=img)
                self.tile.tag_raise("wildlife")
            except Exception:
                return
            if state["i"] < steps:
                self._later(FLY_STEP_MS, step)
            else:
                self._flying = False
                if then is not self._depart:
                    self._set_view(False)        # wings folded again on the flower
                if then:
                    then()

        self._later(FLY_STEP_MS, step)

    @staticmethod
    def _root_of(tile, rects):
        for t, rx, ry, _w, _h in rects:
            if t is tile:
                return rx, ry
        return tile.winfo_rootx(), tile.winfo_rooty()

    def _move_to_canvas(self, new_tile):
        """The plot under the creature's centre becomes its home canvas. If
        that plot already shows a mirror copy of it, the copy takes over."""
        ghosts = self.__dict__.setdefault("_ghosts", {})
        old_tile, old_item = self.tile, self._item
        new_item = ghosts.pop(new_tile, None)
        if new_item is None:
            try:
                new_item = new_tile.create_image(
                    -100, -100, image=self.variant.frame(0),
                    anchor="center", tags=("wildlife", self.type_name))
            except Exception:
                new_item = None
        if old_item is not None:
            ghosts[old_tile] = old_item          # kept as a mirror; sync may drop it
        self.tile, self._item = new_tile, new_item

    def _sync_ghosts(self, X, Y, img, rects, final=False):
        """While crossing between plots, draw the creature on every plot its
        picture overlaps, so it moves across the border in one piece instead
        of being cut off and popping over."""
        ghosts = self.__dict__.setdefault("_ghosts", {})
        try:
            hw, hh = img.width() // 2 + 1, img.height() // 2 + 1
        except Exception:
            hw = hh = 17
        keep = set()
        if not final:
            for t, rx, ry, rw, rh in rects:
                if t is self.tile:
                    continue
                if X + hw > rx and X - hw < rx + rw and Y + hh > ry and Y - hh < ry + rh:
                    keep.add(t)
                    item = ghosts.get(t)
                    try:
                        if item is None:
                            item = t.create_image(X - rx, Y - ry, image=img, anchor="center",
                                                  tags=("wildlife", self.type_name))
                            ghosts[t] = item
                        else:
                            t.coords(item, X - rx, Y - ry)
                            t.itemconfig(item, image=img)
                        t.tag_raise("wildlife")
                    except Exception:
                        pass
        for t in list(ghosts):
            if t not in keep:
                try:
                    t.delete(ghosts[t])
                except Exception:
                    pass
                ghosts.pop(t, None)

    def _clear_ghosts(self):
        for t, item in list(getattr(self, "_ghosts", {}).items()):
            try:
                t.delete(item)
            except Exception:
                pass
        self._ghosts = {}

    def _schedule_hop(self):
        if self._alive:
            self._later(random.randint(HOP_MIN_MS, HOP_MAX_MS), self._hop)

    def _hop(self):
        """Fly on to another free flower — on this plant or a nearby one."""
        if not self._alive or self._flying:
            return
        dest, res = self.tile, None
        try:
            if random.random() < HOP_OTHER_PLANT:
                other = self.mgr._pick_nearby_tile(self.tile, self.pods_only)
                if other is not None:
                    r = self.mgr._pick_pixel(other, self.pods_only)
                    if r is not None:
                        dest, res = other, r
            if res is None:
                res = self.mgr._pick_pixel(self.tile, self.pods_only)
                dest = self.tile
        except Exception:
            res = None
        if res is None:
            self._schedule_hop()
            return
        nx_, ny_, key = res
        try:
            self.mgr._occupied.discard(self.cluster_key)
            self.mgr._occupied.add(key)
        except Exception:
            pass
        self.cluster_key = key
        if dest is not self.tile:
            def _landed(d=dest):
                # A new plant got a visit.
                try:
                    rec = getattr(self.mgr.app, "_record_wildlife_visit", None)
                    if rec:
                        rec(getattr(d, "plant", None), self.type_name,
                            getattr(self.variant, "label", ""))
                except Exception:
                    pass
                self._schedule_hop()
            self._fly_to(nx_, ny_, then=_landed, dest=dest)
        else:
            self._fly_to(nx_, ny_, then=self._schedule_hop)

    def _leave(self):
        """End of the visit: disappears from the flower it sits on."""
        if not self._alive:
            return
        if self._flying:                      # land first, then vanish
            self._later(300, self._leave)
            return
        self._depart()

    def _later(self, ms, fn):
        try:
            self._jobs.append(self.tile.after(ms, fn))
            if len(self._jobs) > 80:          # flights add many short jobs;
                self._jobs = self._jobs[-40:]  # every callback checks _alive
        except Exception:
            pass

    def _tick_anim(self):
        if not self._alive:
            return
        if self._flying:                      # flight drives its own frames
            self._later(FRAME_MS, self._tick_anim)
            return
        self._fi = (self._fi + 1) % max(1, len(self.variant.frames))
        img = self.variant.frame(self._fi)
        if img and self._item:
            try:
                self.tile.itemconfig(self._item, image=img)
                self.tile.tag_raise("wildlife")   # stay on top after every render
            except Exception:
                pass
        self._later(FRAME_MS, self._tick_anim)

    def _wander(self):
        if not self._alive:
            return
        if self._flying:
            self._later(WANDER_MS, self._wander)
            return
        ts = getattr(self.tile, 'w', 85)
        try:
            f = self.variant.frames[0] if self.variant.frames else None
            mx = f.width()  // 2 if f else 16
            my = f.height() // 2 if f else 16
        except Exception:
            mx = my = 16
        self.cx = max(mx, min(ts - mx, self.cx + random.randint(-2, 2)))
        self.cy = max(my, min(ts - my, self.cy + random.randint(-2, 2)))
        if self._item:
            try:
                self.tile.coords(self._item, self.cx, self.cy)
                self.tile.tag_raise("wildlife")
            except Exception:
                pass
        self._later(WANDER_MS, self._wander)

    def _depart(self):
        for j in self._jobs:
            try:
                self.tile.after_cancel(j)
            except Exception:
                pass
        self._jobs  = []
        self._alive = False
        self._clear_ghosts()
        if self._item:
            try:
                self.tile.delete(self._item)
            except Exception:
                pass
            self._item = None
        self.mgr._departed(self)

    def destroy(self):
        if self.type_name == "bruchus":
            try:
                self.tile.configure(cursor="")
            except Exception:
                pass
        self._depart()

# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class WildlifeManager:
    """
    Attach once to GardenApp, then call tick() every simulated hour.

        self.wildlife = WildlifeManager(app=self, tk_root=self.root)
        # in _on_next_phase and _auto_advance_phase:
        self.wildlife.tick()
    """

    def __init__(self, app, tk_root):
        self.app              = app
        self.root             = tk_root
        self._active          = []
        self._pools: dict     = {}
        self._occupied        = set()
        self._enabled         = True
        self._frequency       = "low"   # default
        self._init_pools()
        # Slow speeds (Real Time etc.): tick() runs only once per game hour,
        # i.e. once per real hour in Real Time — far too rare. An extra
        # spawn check every few real minutes keeps visitors coming.
        try:
            self.root.after(SLOW_CHECK_MS, self._slow_speed_check)
        except Exception:
            pass

    def _slow_speed_check(self):
        try:
            secs = float(getattr(self.app, "day_length_s", 1.0) or 1.0)
            if secs >= SLOW_SPEED_SECS and getattr(self.app, "running", True):
                self.tick()
        except Exception as exc:
            log.debug("Wildlife slow-speed check error: %s", exc)
        try:
            self.root.after(SLOW_CHECK_MS, self._slow_speed_check)
        except Exception:
            pass

    def set_frequency(self, level: str):
        """Set spawn frequency: 'low', 'medium', or 'high'."""
        global SPAWN_CHANCE, MAX_ACTIVE, REVISIT_MIN, REVISIT_MAX
        preset = _FREQ_PRESETS.get(level, _FREQ_PRESETS["low"])
        SPAWN_CHANCE = preset["spawn_chance"]
        MAX_ACTIVE   = preset["max_active"]
        REVISIT_MIN  = preset["revisit_min"]
        REVISIT_MAX  = preset["revisit_max"]
        self._frequency = level

    def set_enabled(self, enabled: bool):
        """Enable or disable wildlife spawning. Removes active creatures when disabled."""
        self._enabled = enabled
        if not enabled:
            self.destroy_all()

    # ── Load ─────────────────────────────────────────────────────────────────

    def _init_pools(self):
        icon_dir = _find_icon_dir()
        self._pools = {}
        if icon_dir is None:
            print(f"[Wildlife] No icon dir found. Put PNGs in: "
                  f"{os.path.join(_HERE, 'icons', 'wildlife')}")
        else:
            print(f"[Wildlife] Scanning: {icon_dir}")
        for type_name, prefix, *_ in CREATURE_DEFS:
            variants = _discover_variants(icon_dir, prefix)
            self._pools[type_name] = variants
        for type_name, variants in self._pools.items():
            if variants:
                print(f"[Wildlife] {type_name}: {len(variants)} variant(s) — "
                      f"{[v.label for v in variants]}")
            else:
                print(f"[Wildlife] {type_name}: no icons found")

    # ── Tick ─────────────────────────────────────────────────────────────────

    def tick(self):
        """Call once per simulated hour."""
        if not self._enabled:
            return

        # During fast-forward dismiss immediately and don't spawn
        if getattr(self.app, "fast_forward", False):
            if self._active:
                for c in list(self._active):
                    c.destroy()
                self._active.clear()
                self._occupied.clear()
            return

        try:
            if not self._is_daytime():
                if self._active:
                    for c in list(self._active):
                        c.destroy()
                    self._active.clear()
                    self._occupied.clear()
                return

            # Wildlife shelters during rain — same dismiss-and-don't-
            # spawn treatment as nighttime/fast-forward above, rather
            # than butterflies and bees carrying on as if it were a
            # clear day.
            if getattr(self.app, "garden", None) is not None and \
                    getattr(self.app.garden, "weather", None) in ("🌧", "⛈"):
                if self._active:
                    for c in list(self._active):
                        c.destroy()
                    self._active.clear()
                    self._occupied.clear()
                return

            if not self._is_season() and not DEBUG_ALL_BRUCHUS:
                return

            eligible = self._count_eligible_tiles()
            dynamic_cap = max(1, min(6 if DEBUG_ALL_BRUCHUS else MAX_ACTIVE, eligible))

            defs = CREATURE_DEFS
            if DEBUG_ALL_BRUCHUS:
                defs = [("bruchus", "bruchus_pisi", 8, False, tuple(range(1, 13)))]
            for cdef in defs:
                type_name, _, weight, pods_only, months = cdef
                if len(self._active) >= dynamic_cap:
                    break
                if self._current_month() not in months:
                    continue
                pool = self._pools.get(type_name, [])
                if not pool:
                    continue
                if pods_only and not self._any_pods():
                    continue
                chance = 0.9 if DEBUG_ALL_BRUCHUS else SPAWN_CHANCE * (weight / 8.0)
                if random.random() < chance:
                    self._spawn(type_name, pods_only, random.choice(pool))
        except Exception as exc:
            log.error("Wildlife tick() error: %s", exc)

    def _is_wet(self) -> bool:
        try:
            return getattr(self.app.garden, "weather", None) in ("🌧", "⛈")
        except Exception:
            return False

    def rain_check(self):
        """Called often by the app: as soon as rain or a storm starts,
        everything still out in the garden flies off at once."""
        if self._active and self._is_wet():
            self.destroy_all()

    def creature_at(self, tile, x, y, type_name=None):
        """The creature drawn on `tile` at canvas point (x, y), or None."""
        try:
            hits = set(tile.find_overlapping(x - 3, y - 3, x + 3, y + 3))
        except Exception:
            return None
        for c in self._active:
            if (c.tile is tile and c._item in hits
                    and (type_name is None or c.type_name == type_name)):
                return c
        return None

    def destroy_all(self):
        for c in list(self._active):
            c.destroy()
        self._active.clear()
        self._occupied.clear()

    # ── Spawn ─────────────────────────────────────────────────────────────────

    def _spawn(self, type_name: str, pods_only: bool, variant: _Variant):
        try:
            tile = self._pick_tile(pods_only)
            if tile is None:
                return
            result = self._pick_pixel(tile, pods_only)
            if result is None:
                return
            cx, cy, cluster_key = result
            # Mark cluster as occupied before creating creature
            self._occupied.add(cluster_key)
            c = _Creature(self, type_name, pods_only, tile, cx, cy, variant,
                          cluster_key)
            if c._alive:
                self._active.append(c)
                # Tell the game which plant got a visitor (visit counts).
                try:
                    rec = getattr(self.app, "_record_wildlife_visit", None)
                    if rec:
                        rec(getattr(tile, "plant", None), type_name,
                            getattr(variant, "label", ""))
                except Exception:
                    pass
            else:
                # Creation failed — free the slot immediately
                self._occupied.discard(cluster_key)
        except Exception as exc:
            log.error("Wildlife _spawn(%s) error: %s", type_name, exc)

    def _departed(self, creature: _Creature):
        try:
            self._active.remove(creature)
        except ValueError:
            pass
        # Free the flower cluster this creature was sitting on
        self._occupied.discard(creature.cluster_key)
        gap = random.randint(REVISIT_MIN, REVISIT_MAX)
        self.root.after(gap, lambda: self._revisit(creature.type_name,
                                                    creature.pods_only))

    def _revisit(self, type_name: str, pods_only: bool):
        if not self._enabled:
            return
        if getattr(self.app, "fast_forward", False):
            return
        if not self._is_daytime() or not self._is_season() or self._is_wet():
            return
        eligible = self._count_eligible_tiles()
        if len(self._active) >= max(1, min(MAX_ACTIVE, eligible)):
            return
        # The next visitor is drawn afresh by the usual weights — otherwise a
        # weevil, once it came, would keep returning as a weevil all day.
        if not DEBUG_ALL_BRUCHUS:
            choices, weights = [], []
            month = self._current_month()
            for t, _pre, w, po, months in CREATURE_DEFS:
                if month not in months or not self._pools.get(t):
                    continue
                if po and not self._any_pods():
                    continue
                choices.append((t, po))
                weights.append(w)
            if not choices:
                return
            type_name, pods_only = random.choices(choices, weights=weights, k=1)[0]
        pool = self._pools.get(type_name, [])
        if pool:
            self._spawn(type_name, pods_only, random.choice(pool))

    # ── Tile picking ──────────────────────────────────────────────────────────

    def _top_view_partner(self, variant):
        """The open-wing picture of the same species as `variant`."""
        sp_of = getattr(self.app, "_species_for_variant", None)
        if sp_of is None:
            return None
        try:
            want = sp_of("butterfly", variant)
        except Exception:
            return None
        if not want:
            return None
        for v in self._pools.get("butterfly", []) or []:
            if v is variant or not _is_top_view(v):
                continue
            try:
                if sp_of("butterfly", v) == want:
                    return v
            except Exception:
                pass
        return None

    def _visible_tiles(self):
        out = []
        try:
            for t in list(self.app.tiles):
                try:
                    if t.winfo_ismapped():
                        out.append(t)
                except Exception:
                    pass
        except Exception:
            pass
        return out

    def _pick_nearby_tile(self, tile, pods_only: bool):
        """Another visible flowering plant near `tile` (nearer = likelier)."""
        try:
            x0, y0 = tile.winfo_rootx(), tile.winfo_rooty()
            ts = max(1, tile.winfo_width())
        except Exception:
            return None
        cands, weights = [], []
        for t in self._visible_tiles():
            if t is tile:
                continue
            plant = getattr(t, "plant", None)
            if not plant or not getattr(plant, "alive", False):
                continue
            if int(getattr(plant, "stage", 0)) < 5:
                continue
            try:
                d = math.hypot(t.winfo_rootx() - x0, t.winfo_rooty() - y0) / ts
            except Exception:
                continue
            if d <= HOP_RANGE_TILES:
                cands.append(t)
                weights.append(1.0 / (0.5 + d))
        if not cands:
            return None
        return random.choices(cands, weights=weights, k=1)[0]

    def _pick_tile(self, pods_only: bool):
        try:
            tiles = list(self.app.tiles)
        except Exception:
            return None

        eligible = []
        for t in tiles:
            plant = getattr(t, "plant", None)
            if not plant or not getattr(plant, "alive", False):
                continue
            if int(getattr(plant, "stage", 0)) >= 5:
                eligible.append(t)

        return random.choice(eligible) if eligible else None

    # ── Pixel picking ─────────────────────────────────────────────────────────

    def _pick_pixel(self, tile, pods_only: bool):
        """
        Return (cx, cy, cluster_key) for a free flower cluster on this tile,
        or None if no unoccupied flower pixel exists.
        """
        ts = getattr(tile, "w", 85)

        # Reproduce TileCanvas icon-center formula
        water_thick  = getattr(tile, "water_thick",  max(4, ts // 8))
        health_thick = getattr(tile, "health_thick", max(3, ts // 14))
        icon_lift    = max(6, ts // 14)
        try:
            icon_drop = int(tile.configs.get("ICON_DROP", 3))
        except Exception:
            icon_drop = 3

        icx = ts // 2 + water_thick // 2
        icy = ts // 2 - health_thick // 2 - icon_lift + icon_drop

        # Half-dimensions of the wildlife image — need to stay inside canvas bounds
        # Get from first loaded frame; fall back to 16 (half of standard 32x32)
        try:
            frame0 = next(
                (v.frames[0] for pool in self._pools.values()
                 for v in pool if v.frames), None)
            img_hw = frame0.width()  // 2 if frame0 else 16
            img_hh = frame0.height() // 2 if frame0 else 16
        except Exception:
            img_hw = img_hh = 16

        # Safe zone: avoid bars/label AND keep full wildlife image inside canvas
        safe_x0 = max(water_thick + 2, img_hw)
        safe_x1 = min(ts - img_hw, ts - 4)
        hb_y_start = getattr(tile, "hb_y_start",
                             ts - health_thick - getattr(tile, "bar_pad", 3)
                             + getattr(tile, "bottom_shift", 4))
        safe_y0 = max(4, img_hh)
        safe_y1 = min(int(hb_y_start) - getattr(tile, "label_h", 14) - 2,
                      ts - img_hh)

        try:
            pil = self._pil_for_tile(tile)
            if pil is None:
                return None

            pw, ph = pil.size
            icon_x0 = icx - pw // 2
            icon_y0 = icy - ph // 2

            spots = _scan_spots(pil, pods_only)

            # Translate to tile canvas coords and filter to safe zone
            safe_spots = []
            for px, py in spots:
                tx = icon_x0 + px
                ty = icon_y0 + py
                if safe_x0 <= tx <= safe_x1 and safe_y0 <= ty <= safe_y1:
                    safe_spots.append((tx, ty))

            if not safe_spots:
                return None

            # Cluster into individual flowers
            clusters = _cluster_spots(safe_spots, radius=8)
            if not clusters:
                return None

            # Filter to clusters not already occupied
            tile_id = id(tile)
            free_clusters = []
            for cluster in clusters:
                cx, cy = _centroid(cluster)
                key = (tile_id, cx, cy)
                if key not in self._occupied:
                    free_clusters.append((cluster, key))

            if not free_clusters:
                return None   # all flowers on this tile are taken

            # Pick a free cluster weighted by size
            weights = [len(c) for c, _ in free_clusters]
            chosen_cluster, cluster_key = random.choices(
                free_clusters, weights=weights, k=1)[0]

            sx, sy = _centroid(chosen_cluster)
            sx = max(safe_x0, min(safe_x1, sx + random.randint(-2, 2)))
            sy = max(safe_y0, min(safe_y1, sy + random.randint(-2, 2)))
            return sx, sy, cluster_key

        except Exception as exc:
            log.error("Wildlife _pick_pixel error: %s", exc)
            return None

    def _pil_for_tile(self, tile):
        if not _PIL:
            return None
        try:
            plant = getattr(tile, "plant", None)
            if plant is None:
                return None
            from icon_loader import stage_icon_path_for_plant, cached_path_exists
            path = stage_icon_path_for_plant(plant)
            if path and cached_path_exists(path):
                return Image.open(path).convert("RGBA")
        except Exception as exc:
            log.debug("Wildlife _pil_for_tile: %s", exc)
        return None

    # ── Environment ───────────────────────────────────────────────────────────

    def _is_daytime(self) -> bool:
        try:
            import datetime as dt
            env = self.app.garden
            d = dt.date(int(env.year), int(env.month), int(env.day_of_month))
            return not env._is_night_in_brno(d, float(env.clock_hour))
        except Exception:
            try:
                return 6 <= int(self.app.garden.clock_hour) < 20
            except Exception:
                return True

    def _is_season(self) -> bool:
        try:
            return 3 <= int(self.app.garden.month) <= 10
        except Exception:
            return True

    def _current_month(self) -> int:
        try:
            return int(self.app.garden.month)
        except Exception:
            return 6

    def _count_eligible_tiles(self) -> int:
        try:
            return sum(
                1 for t in self.app.tiles
                if getattr(t, "plant", None)
                   and getattr(t.plant, "alive", False)
                   and int(getattr(t.plant, "stage", 0)) >= 5
            )
        except Exception:
            return 0

    def _any_pods(self) -> bool:
        try:
            return any(
                int(getattr(getattr(t, "plant", None), "stage", 0)) >= 6
                for t in self.app.tiles
                if getattr(t, "plant", None)
                   and getattr(t.plant, "alive", False)
            )
        except Exception:
            return False


# ---------------------------------------------------------------------------
# BeeScene — a small self-contained "plot" for info popups
# ---------------------------------------------------------------------------
class BeeScene:
    """
    A single garden plot drawn on its own small Canvas: spring soil texture
    behind a randomly chosen mature (flowering) plant, with a few bees
    behaving like the ones in the wildlife simulator — each lands on a free
    flower cluster of the plant icon, flaps (frame animation), wanders a
    couple of pixels at a time, stays 4-14 s, then leaves and later returns
    to another free flower cluster. Only the revisit gap is shorter than in
    the simulator, so a popup scene always has bees in it.

    Everything (soil, plant, bees) is drawn at `scale` times its tile size.
    Use `.canvas` to place it; it stops itself when the canvas is destroyed.
    """

    REVISIT_MIN_MS = 1500
    REVISIT_MAX_MS = 5000

    def __init__(self, parent, app, tile_size=85, scale=1.5, n_bees=3,
                 bg="#f5f0e6"):
        self.app = app
        self.ts = int(tile_size)
        self.k = float(scale)
        self.S = int(round(self.ts * self.k))
        self.canvas = tk.Canvas(parent, width=self.S, height=self.S,
                                highlightthickness=0, bd=0, bg=bg)
        self._alive = True
        self._jobs = set()
        self._refs = []
        self._occupied = set()
        self._clusters = []     # (key, x, y, weight) in canvas pixels
        self._variants = []     # list of lists of PhotoImage frames
        self.canvas.bind("<Destroy>", lambda e: self._stop(), add="+")
        if not _PIL:
            return
        try:
            self._build_background()
            self._build_plant()
            self._load_bee_frames()
        except Exception as exc:
            log.error("BeeScene build error: %s", exc)
            return
        if self._clusters and self._variants:
            for i in range(n_bees):
                self._later(250 + i * 700, self._spawn)

    # -- scheduling --------------------------------------------------------
    def _later(self, ms, fn):
        if not self._alive:
            return None
        try:
            jid = self.canvas.after(ms, fn)
            self._jobs.add(jid)
            return jid
        except Exception:
            return None

    def _stop(self):
        self._alive = False
        for j in list(self._jobs):
            try:
                self.canvas.after_cancel(j)
            except Exception:
                pass
        self._jobs.clear()

    # -- scene -------------------------------------------------------------
    def _photo(self, pil):
        ph = ImageTk.PhotoImage(pil)
        self._refs.append(ph)
        return ph

    def _scaled(self, pil):
        w = max(1, round(pil.width * self.k))
        h = max(1, round(pil.height * self.k))
        return pil.resize((w, h), Image.LANCZOS)

    def _build_background(self):
        img = None
        try:
            from tile import _find_base_image
            pil_imgs = getattr(self.app, "_bg_pil_images", None) or {}
            n = max(1, int(getattr(self.app, "_bg_soil_variants", 1) or 1))
            img = _find_base_image(pil_imgs, "soil", "spring",
                                   random.randint(0, n - 1), 100)
        except Exception:
            img = None
        if img is None:
            img = Image.new("RGBA", (self.ts, self.ts), (107, 79, 53, 255))
        img = img.convert("RGBA").resize((self.S, self.S), Image.LANCZOS)
        # Rounded corners: cut the soil image with an anti-aliased
        # rounded-rectangle alpha mask (drawn 4x larger, then shrunk), so
        # the corners show the canvas background instead.
        try:
            from PIL import ImageDraw
            r = max(6, round(self.S * 0.12))
            big = Image.new("L", (self.S * 4, self.S * 4), 0)
            ImageDraw.Draw(big).rounded_rectangle(
                (0, 0, self.S * 4 - 1, self.S * 4 - 1), radius=r * 4, fill=255)
            mask = big.resize((self.S, self.S), Image.LANCZOS)
            alpha = img.getchannel("A")
            from PIL import ImageChops
            img.putalpha(ImageChops.multiply(alpha, mask))
        except Exception:
            pass
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo(img))

    def _build_plant(self):
        import icon_loader as il
        pos = random.choice(("axial", "terminal"))
        col = random.choice(("purple", "white"))
        path = ""
        try:
            path = il.flower_icon_path_hi(pos, col) or il.flower_icon_path(pos, col)
        except Exception:
            path = ""
        if not path:
            path = il.stage_icon_path(5)
        pil = Image.open(path).convert("RGBA")
        if random.random() < 0.5:
            pil = pil.transpose(Image.FLIP_LEFT_RIGHT)

        icx = self.ts // 2
        icy = self.ts // 2 + 4
        x0 = icx - pil.width // 2
        y0 = icy - pil.height // 2
        clusters = _cluster_spots(_scan_spots(pil, False), radius=8)
        for cl in clusters:
            cx, cy = _centroid(cl)
            sx = round((x0 + cx) * self.k)
            sy = round((y0 + cy) * self.k)
            self._clusters.append(((sx, sy), sx, sy, len(cl)))

        self.canvas.create_image(round(icx * self.k), round(icy * self.k),
                                 anchor="center",
                                 image=self._photo(self._scaled(pil)))

    def _load_bee_frames(self):
        d = _find_icon_dir()
        if not d:
            return
        bases = sorted(f[:-len("_frame1.png")] for f in os.listdir(d)
                       if f.startswith("bee") and f.endswith("_frame1.png"))
        for base in bases:
            frames = []
            for n in (1, 2):
                p = os.path.join(d, f"{base}_frame{n}.png")
                if not os.path.exists(p):
                    break
                frames.append(self._photo(self._scaled(Image.open(p).convert("RGBA"))))
            if frames:
                self._variants.append(frames)

    # -- bees --------------------------------------------------------------
    def _spawn(self):
        if not self._alive:
            return
        free = [c for c in self._clusters if c[0] not in self._occupied]
        if not free:
            self._later(2000, self._spawn)
            return
        key, x, y, _w = random.choices(free, weights=[c[3] for c in free], k=1)[0]
        self._occupied.add(key)
        frames = random.choice(self._variants)
        mx = frames[0].width() // 2
        my = frames[0].height() // 2
        bee = {"x": x, "y": y, "fi": 0, "frames": frames, "key": key,
               "mx": mx, "my": my, "live": True}
        bee["item"] = self.canvas.create_image(x, y, image=frames[0],
                                               anchor="center", tags="bee")
        self.canvas.tag_raise("bee")
        self._later(FRAME_MS, lambda: self._anim(bee))
        self._later(WANDER_MS, lambda: self._wander(bee))
        self._later(random.randint(MIN_STAY_MS, MAX_STAY_MS),
                    lambda: self._depart(bee))

    def _anim(self, bee):
        if not (self._alive and bee["live"]):
            return
        bee["fi"] = (bee["fi"] + 1) % len(bee["frames"])
        try:
            self.canvas.itemconfig(bee["item"], image=bee["frames"][bee["fi"]])
            self.canvas.tag_raise("bee")
        except Exception:
            return
        self._later(FRAME_MS, lambda: self._anim(bee))

    def _wander(self, bee):
        if not (self._alive and bee["live"]):
            return
        step = max(1, round(2 * self.k))
        bee["x"] = max(bee["mx"], min(self.S - bee["mx"],
                                      bee["x"] + random.randint(-step, step)))
        bee["y"] = max(bee["my"], min(self.S - bee["my"],
                                      bee["y"] + random.randint(-step, step)))
        try:
            self.canvas.coords(bee["item"], bee["x"], bee["y"])
        except Exception:
            return
        self._later(WANDER_MS, lambda: self._wander(bee))

    def _depart(self, bee):
        bee["live"] = False
        try:
            self.canvas.delete(bee["item"])
        except Exception:
            pass
        self._occupied.discard(bee["key"])
        self._later(random.randint(self.REVISIT_MIN_MS, self.REVISIT_MAX_MS),
                    self._spawn)
