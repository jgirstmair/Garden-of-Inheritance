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
MIN_STAY_MS = 4000
MAX_STAY_MS = 14000
REVISIT_MIN = 18000   # default: low frequency
REVISIT_MAX = 55000
MAX_ACTIVE  = 2
SPAWN_CHANCE = 0.18

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
        self._appear()

    def _appear(self):
        img = self.variant.frame(0)
        if img is None:
            self._alive = False
            return
        try:
            self._item = self.tile.create_image(
                self.cx, self.cy, image=img,
                anchor="center", tags="wildlife")
            self.tile.tag_raise("wildlife")
        except Exception as exc:
            log.debug("Wildlife appear error: %s", exc)
            self._alive = False
            return

        stay = random.randint(MIN_STAY_MS, MAX_STAY_MS)
        self._later(FRAME_MS,  self._tick_anim)
        self._later(WANDER_MS, self._wander)
        self._later(stay,      self._depart)

    def _later(self, ms, fn):
        try:
            self._jobs.append(self.tile.after(ms, fn))
        except Exception:
            pass

    def _tick_anim(self):
        if not self._alive:
            return
        self._fi = (self._fi + 1) % max(1, len(self.variant.frames))
        img = self.variant.frame(self._fi)
        if img and self._item:
            try:
                self.tile.itemconfig(self._item, image=img)
            except Exception:
                pass
        self._later(FRAME_MS, self._tick_anim)

    def _wander(self):
        if not self._alive:
            return
        ts = getattr(self.tile, 'w', 85)
        self.cx = max(6, min(ts - 6, self.cx + random.randint(-2, 2)))
        self.cy = max(6, min(ts - 6, self.cy + random.randint(-2, 2)))
        if self._item:
            try:
                self.tile.coords(self._item, self.cx, self.cy)
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
        if self._item:
            try:
                self.tile.delete(self._item)
            except Exception:
                pass
            self._item = None
        self.mgr._departed(self)

    def destroy(self):
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

    def reload_icons(self):
        self._init_pools()

    # ── Tick ─────────────────────────────────────────────────────────────────

    def tick(self):
        """Call once per simulated hour."""
        if not self._enabled:
            return
        try:
            if not self._is_daytime():
                if self._active:
                    for c in list(self._active):
                        c.destroy()
                    self._active.clear()
                    self._occupied.clear()
                return

            if not self._is_season():
                return

            eligible = self._count_eligible_tiles()
            dynamic_cap = max(1, min(MAX_ACTIVE, eligible))

            for cdef in CREATURE_DEFS:
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
                if random.random() < SPAWN_CHANCE * (weight / 8.0):
                    self._spawn(type_name, pods_only, random.choice(pool))
        except Exception as exc:
            log.error("Wildlife tick() error: %s", exc)

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
        if not self._is_daytime() or not self._is_season():
            return
        eligible = self._count_eligible_tiles()
        if len(self._active) >= max(1, min(MAX_ACTIVE, eligible)):
            return
        pool = self._pools.get(type_name, [])
        if pool:
            self._spawn(type_name, pods_only, random.choice(pool))

    # ── Tile picking ──────────────────────────────────────────────────────────

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

        # Safe zone (avoid bars and label)
        safe_x0 = water_thick + 2
        safe_x1 = ts - 4
        hb_y_start = getattr(tile, "hb_y_start",
                             ts - health_thick - getattr(tile, "bar_pad", 3)
                             + getattr(tile, "bottom_shift", 4))
        safe_y0 = 4
        safe_y1 = int(hb_y_start) - getattr(tile, "label_h", 14) - 2

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
            from icon_loader import stage_icon_path_for_plant
            path = stage_icon_path_for_plant(plant)
            if path and os.path.exists(path):
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
