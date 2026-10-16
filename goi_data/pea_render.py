"""
pea_render.py — draws a growing pea plant from its traits and age
(the "Grown" plant style of the Garden of Inheritance).

Structure: seed -> folded shoot that opens its first leaves -> leaf pair
after leaf pair (tall: long stem pieces, dwarf: short ones and fewer pairs)
-> buds -> flowers (axial in the leaf angles or terminal at the top,
purple or white) -> pods exactly where the flowers were (green or yellow,
inflated or constricted) -> dry, ripe pods. Optional soft painted polish.

Pictures are drawn with Pillow at 3x size and scaled down, once per plant
and half day (the game caches them) — never per frame.
"""
import math
import os
import random
import time

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

TILE = 64            # final picture size (same as the plant icons)
SS = 3               # supersampling
S = TILE * SS
OW = 2               # outline width at 3x (~2/3 px in the tile: soft, less pixelated)
# Strength of the "painted" style (Game Settings > Plant style)
PAINT_SHADE = 0.22   # leaf base a bit darker...
PAINT_LIGHT = 0.40   # ...and its sunlit half lighter
PAINT_GLOW = 0.32    # soft glow around the plant
PAINT_WARM = (1.02, 2, 0.97)   # a hint of golden light: red x1.02 +2, blue x0.97
PAINT_SAT = 1.12     # a little more colour, so the painted plants stay lush green
PAINTERLY = True     # soft, hand-painted polish (set per call by plant_image)

# ---------------------------------------------------------------- colours
OUT = (16, 20, 14, 255)          # thin, nearly black outline (~1 px in the tile)
HEIGHT = 0.9                     # overall plant height factor
DEPTH_ALPHA = 1.0                # leaves on the far side are drawn this opaque (depth cue)
DEPTH_BRIGHT = 0.15              # ...and this much brighter, as if further away in the light
STEM = (60, 128, 38, 255)
LEAF = (78, 150, 72, 255)      # slightly blue-green, like real pea leaves
LEAF_HI = (124, 190, 84, 255)       # light midrib / highlight
LEAF_OLD = (186, 170, 70, 255)      # yellowing at the end of the season
# Purple peas: a lilac standard with a deeper base and dark veins, deep
# wine-purple wings, a pale keel. White peas: white petals, the keel a touch green.
PURPLE = {"std": (184, 140, 214, 255), "std_base": (150, 92, 176, 255),
          "wing": (122, 46, 128, 255), "out": (26, 16, 36, 255)}
WHITE = {"std": (252, 252, 246, 255), "std_base": (236, 240, 222, 255),
         "wing": (240, 242, 232, 255), "out": (28, 30, 24, 255)}
POD_GREEN = (110, 182, 54, 255)
POD_YELLOW = (238, 214, 60, 255)
POD_DRY = (204, 172, 100, 255)
POD_DRY_OUT = (40, 30, 16, 255)
SEED = (122, 200, 70, 255)
SEED_COL = {"yellow": ((232, 204, 78, 255), (120, 96, 30, 255)),
            "green": ((128, 186, 76, 255), (44, 80, 30, 255))}
TENDRIL = (70, 112, 58, 255)        # thin stalks and tendrils

# ---------------------------------------------------------------- timing (days)
GERMINATE = 3          # seed leaves appear
FIRST_NODE = 6         # first true leaf pair
NODE_EVERY = 4.0
NODES_MAX = 5
FLOWER_FROM_NODE = 3   # axial: flowers at this leaf pair and above
BUD_DAY = 30
OPEN_AFTER = 3         # bud -> open flower
FLOWER_DAYS = 4        # open flower lasts
POD_GROW = 8           # pod grows to full size
POD_DRY_DAYS = 22      # then dries / ripens
SENESCE = 70           # leaves start yellowing


class PeaPlant:
    def __init__(self, tall=True, terminal=False, purple=True,
                 pod_yellow=False, constricted=False, seed=1):
        self.tall, self.terminal, self.purple = tall, terminal, purple
        self.pod_yellow, self.constricted = pod_yellow, constricted
        self.seed_color = "green"
        self.rseed = seed
        r = random.Random(seed)
        self.zig = [r.uniform(-1, 1) for _ in range(NODES_MAX + 2)]
        self.leaf_var = [r.uniform(0.9, 1.1) for _ in range(NODES_MAX + 2)]
        self.tilt = [r.uniform(-0.12, 0.12) for _ in range(NODES_MAX + 2)]
        self.flower_delay = [r.uniform(0, 2.0) for _ in range(NODES_MAX + 6)]
        # The first flower keeps to the game's calendar exactly, so a plant
        # in the "Budding" stage always shows a bud and a "Flowering" plant
        # always has an open flower; only the later ones vary.
        self.flower_delay[0] = 0.0
        self.lean = r.uniform(-0.05, 0.05)
        # Individual variation, fixed for the plant's life: every plant is
        # a little different in height, leaf size, colour and posture.
        self.h_var = r.uniform(0.84, 1.03)            # overall height
        self.inter_var = [r.uniform(0.85, 1.15) for _ in range(NODES_MAX + 2)]
        self.size_var = r.uniform(0.9, 1.1)            # leaf size
        self.spread_var = r.uniform(-0.16, 0.16)       # leaves held more upright / open
        self.green_var = r.uniform(-1, 1)              # a touch lighter/yellower or bluer/darker
        self.side_reach = r.uniform(0.85, 1.12)        # length of the side leaves
        # Dwarfs are drawn with fewer leaf pairs and pods so the short
        # plant doesn't look squeezed (a tile picture, not a botany plate).
        self.max_nodes = NODES_MAX if tall else 3
        self.node_every = NODE_EVERY if tall else NODE_EVERY * 1.8

    def node_count(self, age):
        if age < FIRST_NODE:
            return 0
        n = 1 + int((age - FIRST_NODE) / self.node_every)
        if self.terminal:
            n = min(n, self.max_nodes - 1)   # stem stops at the flower cluster
        return min(n, self.max_nodes)

    def internode(self):
        # Same leaf pairs, only the stem pieces differ: dwarfs ~1/3 as long.
        return ((S * 0.122) if self.tall else (S * 0.083)) * HEIGHT     # dwarfs +17%

    def flowers(self, age):
        """[(node, slot, start_day)]."""
        out = []
        if self.terminal:
            top = self.node_count(age)
            if top < self.max_nodes - 1:
                return out
            for k in range(3 if self.tall else 2):
                out.append((top, k, BUD_DAY + self.flower_delay[k] * 0.6))
        else:
            first = FLOWER_FROM_NODE if self.tall else 2
            for i, node in enumerate(range(first, self.max_nodes + 1)):
                start = BUD_DAY + i * 3.0 + self.flower_delay[i]
                out.append((node, 0, start))
                if i % 2 == 0 and self.tall:
                    out.append((node, 1, start + 1.2))   # a second flower on the same stalk
        return out


# ---------------------------------------------------------------- helpers
def _rot(px, py, ang):
    c, s = math.cos(ang), math.sin(ang)
    return px * c - py * s, px * s + py * c


_LEAF_PROFILE = {}


def _leaf_profile(steps):
    """Unit leaf outline (t along the leaf, half-width factor), computed once."""
    prof = _LEAF_PROFILE.get(steps)
    if prof is None:
        right = []
        for i in range(steps + 1):
            t = i / steps
            right.append((t, (math.sin(math.pi * t) ** 0.75) * 0.5 * (1.0 - 0.15 * t)))
        prof = right + [(t, -w) for t, w in reversed(right)]
        _LEAF_PROFILE[steps] = prof
    return prof


def leaf_shape(cx, cy, ang, length, width, steps=16):
    """Oval, slightly pointed leaflet from (cx, cy) along angle `ang`."""
    c, s = math.cos(ang), math.sin(ang)
    out = []
    for t, w in _leaf_profile(steps):
        x, y = t * length, w * width
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out


def poly(d, pts, fill, out=OUT, w=OW):
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=out, width=w, joint="curve")


# Gentle wiggle: every leaf gets its own small, smooth angle offset that
# depends on the animation phase (0..1). In the game a few phases per plant
# and day would be drawn once and cycled — not redrawn every frame.
WIGGLE_AMP = 0.05          # radians (~3 degrees)
WIGGLE_FRAMES = 16         # positions per cycle
_wig = {"phase": 0.0, "k": 0}


def wiggle():
    """Each leaf rests, then makes a tiny, quick shift to a new position and
    rests again — a few such moves per cycle, each leaf on its own schedule
    (no continuous bouncing)."""
    _wig["k"] += 1
    k = _wig["k"]
    rng = random.Random(k * 7919 + 13)
    moves = sorted(rng.sample(range(WIGGLE_FRAMES), 3))
    targets = [rng.uniform(-1, 1) for _ in moves]
    f = (_wig["phase"] % 1.0) * WIGGLE_FRAMES
    cur, prev = targets[-1], targets[-2]
    when = moves[-1] - WIGGLE_FRAMES
    for m, tgt, i in zip(moves, targets, range(len(moves))):
        if f >= m:
            cur, prev, when = tgt, targets[i - 1], m
    t = min(1.0, max(0.0, f - when))            # the move itself takes one frame
    return WIGGLE_AMP * (prev + (cur - prev) * t)


_layers = {"back": None}

# Sickness (0 = healthy .. 1 = nearly dead): some leaves dry up (brown,
# curled) and others get black spots with a yellow rim, like a leaf-spot
# fungus. Which leaf is hit is fixed per plant, so the damage doesn't jump
# around between redraws; lower (older) leaves go first.
_sick = {"level": 0.0, "seed": 0, "i": 0}
DRY = (156, 120, 62, 255)
DRY_DARK = (104, 74, 36, 255)
SPOT = (24, 20, 14, 255)
SPOT_RIM = (196, 176, 70, 255)


def _leaf_damage():
    """('dry' | 'spots' | None, rng) for the next leaf drawn."""
    i = _sick["i"]
    _sick["i"] = i + 1
    s = _sick["level"]
    if s <= 0:
        return None, None
    r = random.Random(_sick["seed"] * 7919 + i * 104729)
    u, v = r.random(), r.random()
    low = 1.35 - 0.7 * min(1.0, i / 14.0)            # older leaves first
    if u < s * 0.55 * low:
        return "dry", r
    if v < min(0.75, s * 0.85):
        return "spots", r
    return None, r


def leaf(d, x, y, ang, length, width, col, back=False):
    """`back=True`: the leaf sits on the far side of the stem — it goes on a
    layer that is drawn behind everything and a little transparent, which
    gives the flat picture a sense of depth (like points further away in a
    3-D plot)."""
    if back and _layers["back"] is not None:
        d = _layers["back"]
    ang += wiggle()
    dmg, rng = _leaf_damage()
    if dmg == "dry":
        # dried leaf: brown, a bit shrivelled and curled
        col = mix(DRY, DRY_DARK, rng.random() * 0.5)
        width *= 0.72
        length *= 0.92
        ang += rng.uniform(-0.25, 0.25)
    shape = leaf_shape(x, y, ang, length, width)
    if not PAINTERLY:
        poly(d, shape, col)
    else:
        # Painted look: base colour, a soft lighter half facing the light
        # (upper left), a touch of shade on the other side, then the outline.
        d.polygon(shape, fill=mix(col, (22, 70, 30, 255), PAINT_SHADE))      # deep green shade
        lit = 1 if math.sin(ang) < 0 else -1          # side of the leaf facing up
        hl = []
        c_, s_ = math.cos(ang), math.sin(ang)
        L2, W2, lim = length * 0.92, width * 0.72, -width * 0.05
        for t, w in _leaf_profile(16):
            py_ = w * W2
            if py_ * lit >= lim:
                a_, b_ = t * L2 + length * 0.03, py_ * 0.9 + lit * width * 0.06
                hl.append((x + a_ * c_ - b_ * s_, y + a_ * s_ + b_ * c_))
        if len(hl) > 2:
            d.polygon(hl, fill=mix(col, (176, 232, 128, 255), PAINT_LIGHT))  # fresh light green
        d.line(shape + [shape[0]], fill=OUT, width=OW, joint="curve")
    # light midrib for a bit of depth, like the hand-drawn icons
    x1, y1 = x + math.cos(ang) * length * 0.2, y + math.sin(ang) * length * 0.2
    x2, y2 = x + math.cos(ang) * length * 0.75, y + math.sin(ang) * length * 0.75
    d.line((x1, y1, x2, y2), fill=mix(col, (255, 255, 255, 255), 0.25), width=SS)
    if dmg == "spots":
        for _ in range(1 + int(_sick["level"] * 1.6 + rng.random() * 0.8)):
            t, o = rng.uniform(0.3, 0.8), rng.uniform(-0.28, 0.28)
            px_, py_ = _rot(length * t, width * o, ang)
            sx, sy = x + px_, y + py_
            rr = SS * rng.uniform(0.75, 1.15)
            rim = rr + SS * 0.45
            d.ellipse((sx - rim, sy - rim, sx + rim, sy + rim), fill=mix(col, SPOT_RIM, 0.4))
            d.ellipse((sx - rr, sy - rr, sx + rr, sy + rr), fill=SPOT)


def smooth(t):
    return t * t * (3 - 2 * t)


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def thick_line(d, pts, col, w):
    d.line(pts, fill=OUT, width=w + 2 * (OW - 1), joint="curve")
    d.line(pts, fill=col, width=w, joint="curve")


# ---------------------------------------------------------------- renderer
def render(plant, age, phase=0.0, pods_visible=None, sickness=0.0, flowers_max=None,
           marks=None, late=None):
    _wig["phase"], _wig["k"] = phase, 0
    _sick["level"] = max(0.0, min(1.0, float(sickness or 0)))
    _sick["seed"], _sick["i"] = int(getattr(plant, "rseed", 0) or 0), 0
    img = Image.new("RGBA", (S, HS), (0, 0, 0, 0))     # extra headroom, see _fit
    d = ImageDraw.Draw(img)
    back_img = Image.new("RGBA", (S, HS), (0, 0, 0, 0))
    _layers["back"] = ImageDraw.Draw(back_img)
    _layers["img"] = back_img
    ground = HS - 6 * SS
    cx = S // 2
    _layers["crumbs"] = (plant, cx, ground)      # drawn in _finish, in front of the stem foot

    old = max(0.0, min(1.0, (age - SENESCE) / 18.0))
    gv = plant.green_var
    base_leaf = mix(LEAF, (110, 170, 70, 255) if gv > 0 else (60, 128, 84, 255), abs(gv) * 0.45)
    leaf_col = mix(base_leaf, LEAF_OLD, old)
    stem_col = mix(STEM, LEAF_OLD, old * 0.7)

    # The seed it grew from, in its seed colour (yellow or green),
    # lies at the foot of the plant until the shoot is up.
    if age < GERMINATE + 3:
        _draw_seed(d, plant, cx + (0 if age < GERMINATE else 3 * SS), ground,
                   1.0 if age < GERMINATE else max(0.0, 1 - (age - GERMINATE) / 3.0))
    if age < GERMINATE:
        return _finish(img)
    n = plant.node_count(age)
    # Seedling: short stalk with two seed leaves. They grow smoothly and
    # stay at the base all season (no jump when the first pairs appear).
    gs = max(0.0, min(1.0, (age - GERMINATE + 1) / (FIRST_NODE + 3 - GERMINATE)))
    hyp = (4 + 5 * gs) * SS * HEIGHT
    seed_old = max(old, max(0.0, min(1.0, (age - 45) / 30.0)) * 0.6)

    # The shoot comes up as a closed, folded bud and then opens its first
    # leaf pair (like in the seed-to-pod video).
    seed_open = smooth(min(1.0, max(0.0, (age - GERMINATE - 1.5) / 3.0)))

    def seed_leaves(bx, by):
        col = mix(LEAF, LEAF_OLD, seed_old)
        for s2 in (-1, 1):
            leaf(d, bx, by, -math.pi / 2 + s2 * (0.12 + (0.73 + 0.35 * gs) * seed_open),
                 (7 + 6 * gs) * SS, (5 + 3.5 * gs) * SS, col, back=(s2 > 0 and seed_open > 0.5))

    if n == 0:
        top = ground - hyp
        thick_line(d, [(cx, ground), (cx, top)], stem_col, 3 * SS)
        seed_leaves(cx, top)
        return _finish(img)

    grow = min(1.0, (age - FIRST_NODE - (n - 1) * plant.node_every) / plant.node_every)
    inter = plant.internode()

    # Node positions (gently zig-zagging stem)
    nodes = [(cx, ground)]
    x, y = cx, ground - hyp
    nodes.append((x, y))
    for i in range(1, n + 1):
        seg = inter * plant.h_var * plant.inter_var[i] * (0.35 + 0.65 * grow if i == n else 1.0)
        x += plant.zig[i] * 2.5 * SS + plant.lean * seg
        y -= seg
        nodes.append((x, y))

    # Never grow out of the picture: leave room above the top for the
    # growing tip / flowers and squeeze the stem pieces if needed.
    room = 16 * SS
    y_base = nodes[1][1]
    if nodes[-1][1] < room and y_base > room:
        k = (y_base - room) / max(1.0, (y_base - nodes[-1][1]))
        nodes = nodes[:2] + [(nx_, y_base - (y_base - ny_) * k) for nx_, ny_ in nodes[2:]]

    # Stem (thicker at the base)
    thick_line(d, nodes, stem_col, 3 * SS)

    seed_leaves(*nodes[1])

    # Leaf pairs — older (lower) pairs are bigger and droop outward
    for i in range(1, n + 1):
        nx, ny = nodes[i + 1]
        node_age = age - (FIRST_NODE + (i - 1) * plant.node_every)
        g = max(0.55, min(1.0, node_age / 7.0)) * plant.leaf_var[i]
        size = 1.0 - 0.07 * (i - 1)                       # smaller towards the top
        if not plant.tall:
            size *= 0.85                                  # dwarf: a little smaller, less crowded
        droop = min(1.0, max(0.0, node_age / 30.0))       # spread out with age
        unfold = smooth(min(1.0, node_age / 3.0))         # opens from a folded bud
        spread = (0.95 + plant.spread_var + 0.45 * droop) * (0.15 + 0.85 * unfold)
        if not plant.tall:
            spread += 0.25                                # dwarfs grow bushier
        for s in (-1, 1):
            ang = -math.pi / 2 + s * spread + plant.tilt[i]
            leaf(d, nx, ny, ang, 11 * SS * g * size * plant.size_var, 7 * SS * g * size * plant.size_var,
                 leaf_col if s < 0 else mix(leaf_col, OUT, 0.08),
                 back=(unfold > 0.5 and (s > 0) == (i % 2 == 1)))    # alternating sides behind
        # Compound leaf (like the time-lapse): from the 2nd pair on, a thin
        # stalk reaches outward with one pair of small leaflets and ends in
        # a branched tendril with curly tips. Thin lines — light, not dense.
        if (i >= 1 and node_age > 2.5 and not (plant.terminal and i == n)
                and (plant.tall or i % 2 == 0)):      # dwarfs: side leaves only now and then
            side = 1 if i % 2 else -1
            reach = min(1.0, (node_age - 2.5) / 6.0) * size
            pang = -math.pi / 2 + side * (0.8 + 0.25 * droop) + wiggle() * 0.6
            L = 24 * SS * reach * plant.side_reach
            mx, my = nx + math.cos(pang) * L * 0.5, ny + math.sin(pang) * L * 0.5
            ex, ey = nx + math.cos(pang) * L, ny + math.sin(pang) * L
            d.line((nx, ny, ex, ey), fill=TENDRIL, width=SS)
            for s2 in (-1, 1):
                leaf(d, mx, my, pang + s2 * 0.85, 12 * SS * reach, 7 * SS * reach,
                     mix(leaf_col, LEAF_HI, 0.15), back=(s2 > 0))
            # tendril: three thin branches with curled ends
            for b in (-0.5, 0.05):
                ba = pang + b
                bl = 9 * SS * reach
                bx, by = ex + math.cos(ba) * bl, ey + math.sin(ba) * bl
                pts = [(ex, ey), (bx, by)]
                for k in range(4):                     # a single loose curl at the tip
                    a = ba + side * (k + 1) * 0.9
                    rr = 2.2 * SS * reach
                    pts.append((pts[-1][0] + math.cos(a) * rr, pts[-1][1] + math.sin(a) * rr))
                d.line(pts, fill=TENDRIL, width=SS - 1, joint="curve")

    # Growing tip: a folded bud of young leaves, as in the video
    if not (plant.terminal and n >= plant.max_nodes - 1) and n < plant.max_nodes:
        tx, ty = nodes[-1]
        k = 0.6 + 0.4 * grow
        for s2 in (-1, 1):
            leaf(d, tx, ty, -math.pi / 2 + s2 * 0.16 + plant.tilt[n] * 0.5, 9 * SS * k,
                 6 * SS * k, mix(leaf_col, LEAF_HI, 0.1 if s2 < 0 else 0.0))

    # Flowers / pods — same size on tall and dwarf plants. Only as many
    # pods are drawn as the plant really still carries (harvested pods
    # disappear; flowers that set no pod simply drop).
    pod_no = 0
    # in opening order, so drawn flower j matches the game's flower order
    fl = sorted(plant.flowers(age), key=lambda f_: f_[2])
    if flowers_max is not None:
        fl = fl[:max(0, int(flowers_max))]       # fewer flowers on plants that make fewer pods
    for j, (node, slot, start) in enumerate(fl):
        if node > n or age < start:
            continue
        mk = (marks[j] if marks is not None and j < len(marks) else None) or {}
        if age - start >= OPEN_AFTER + FLOWER_DAYS:
            if mk.get("gone"):                   # dropped (no pod) or already harvested
                continue
            pod_no += 1
            if pods_visible is not None and pod_no > pods_visible:
                continue
        nx, ny = nodes[node + 1]
        if plant.terminal:
            ang = -math.pi / 2 + (slot - 1) * 0.55
            ln = 9 * SS
        else:
            side = -1 if node % 2 else 1
            ang = -math.pi / 2 + side * (0.6 + 0.45 * slot)
            ln = (9 + 3 * slot) * SS
        fx, fy = nx + math.cos(ang) * ln, ny + math.sin(ang) * ln
        d.line((nx, ny, fx, fy), fill=OUT, width=SS + 1)        # flower stalk
        _flower_or_pod(d, plant, fx, fy, age - start, ang)

    # Re-flowering: new buds where ripe pods were — on the upper nodes,
    # on the other side of the stem (at most 4 drawn).
    for j, item in enumerate((late or [])[:4]):
        tm, sid = (item if isinstance(item, (tuple, list)) else (item, j))
        rl = random.Random(int(getattr(plant, "rseed", 0) or 0) * 1009 + int(sid) * 31)
        if plant.terminal:
            node = n                                   # in the cluster at the top
            ang = -math.pi / 2 + rl.uniform(-0.9, 0.9)
            ln = 9 * SS * rl.uniform(0.8, 1.15)
        else:                                          # in a leaf axil somewhere up the stem
            node = rl.randint(max(1, n // 3), max(1, n))
            side = rl.choice((-1, 1))
            ang = -math.pi / 2 + side * rl.uniform(0.6, 1.25)
            ln = rl.uniform(8, 12) * SS
        if node + 1 >= len(nodes):
            continue
        nx, ny = nodes[node + 1]
        fx, fy = nx + math.cos(ang) * ln, ny + math.sin(ang) * ln
        d.line((nx, ny, fx, fy), fill=OUT, width=SS + 1)
        _flower_or_pod(d, plant, fx, fy, float(tm), ang)

    return _finish(img)


CALYX = (92, 150, 62, 255)
PURPLE.update({"vein": (110, 50, 130, 255), "keel": (222, 214, 228, 255)})
WHITE.update({"vein": (206, 212, 192, 255), "keel": (222, 236, 206, 255)})


def _draw_seed(d, plant, x, y, fade=1.0):
    """A pea at the shoot's foot, in the plant's seed colour."""
    if fade <= 0:
        return
    fill, out = SEED_COL.get(plant.seed_color, SEED_COL["green"])
    fill = fill[:3] + (int(255 * fade),)
    out = out[:3] + (int(255 * fade),)
    r = 3.4 * SS
    d.ellipse((x - r, y - r * 1.4, x + r, y + r * 0.6), fill=fill, outline=out, width=OW)
    hl = tuple(min(255, c + 45) for c in fill[:3]) + (int(255 * fade),)
    d.ellipse((x - r * 0.55, y - r * 1.1, x - r * 0.1, y - r * 0.65), fill=hl)


def _local(fx, fy, ang):
    """Point mapper for a flower/pod: x along `ang`, y to its left."""
    c, s_ = math.cos(ang), math.sin(ang)
    return lambda x, y: (fx + x * c - y * s_, fy + x * s_ + y * c)


def _calyx(d, P, k=1.0, col=CALYX):
    """Green calyx where the flower / pod sits on its stalk: a short cup
    with five slender pointed sepals."""
    cup = [P(-0.6 * k * SS, -1.5 * k * SS), P(2.2 * k * SS, -2.1 * k * SS),
           P(2.6 * k * SS, 0), P(2.2 * k * SS, 2.1 * k * SS), P(-0.6 * k * SS, 1.5 * k * SS)]
    poly(d, cup, col)
    for off in (-2.0, -1.0, 0.0, 1.0, 2.0):           # the sepal tips
        base_y = off * 0.95 * k * SS
        tip = P((4.6 - 0.35 * abs(off)) * k * SS, off * 1.45 * k * SS)
        d.polygon([P(1.6 * k * SS, base_y - 0.55 * k * SS), tip,
                   P(1.6 * k * SS, base_y + 0.55 * k * SS)], fill=col)
        d.line([P(1.6 * k * SS, base_y - 0.55 * k * SS), tip,
                P(1.6 * k * SS, base_y + 0.55 * k * SS)], fill=OUT, width=1)


def _oval(P, cx, cy, rx, ry, rot=0.0, n=20):
    """Points of a (rotated) oval in a flower's local coordinates."""
    c, s_ = math.cos(rot), math.sin(rot)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = math.cos(t) * rx, math.sin(t) * ry
        pts.append(P(cx + x * c - y * s_, cy + x * s_ + y * c))
    return pts


def _draw_flower(d, plant, fx, fy, ang, k, wilt):
    """Pea flower seen from the side, as in the garden: the large rounded
    standard petal (banner) stands up behind with fine dark veins and a
    deeper-coloured base, two rounded wing petals point forward over the
    pale boat-shaped keel, all held in a green calyx. `ang` = direction
    the flower faces."""
    pal = PURPLE if plant.purple else WHITE
    brown = (176, 156, 120, 255)
    # every flower a little different: size, how it is turned, how far the
    # banner is open — and now and then one seen from the front
    rng = random.Random(int(fx) * 7919 + int(fy) * 104729 + int(getattr(plant, "rseed", 0) or 0))
    k *= rng.uniform(0.88, 1.10)
    ang += rng.uniform(-0.35, 0.35)
    open_ = rng.uniform(0.85, 1.15)
    wing_turn = rng.uniform(-0.25, 0.25)
    if rng.random() < 0.22:
        _draw_flower_front(d, plant, fx, fy, k, wilt, rng)
        return
    std = mix(pal["std"], brown, wilt * 0.6)
    std_base = mix(pal["std_base"], brown, wilt * 0.6)
    wing = mix(pal["wing"], brown, wilt * 0.6)
    wing2 = mix(wing, OUT, 0.18)
    keel = mix(pal["keel"], brown, wilt * 0.6)
    up = -1 if math.cos(ang) >= 0 else 1          # which side is "up" in local coords
    P = _local(fx, fy, ang)
    shrink = 1 - 0.25 * wilt
    u = k * SS
    # standard: a broad fan with a little notch at the top, leaning back
    sp = []
    for a in range(0, 361, 10):
        t = math.radians(a)
        r = (6.6 + 0.8 * math.cos(2 * t)) * u * shrink * open_
        notch = 0.8 if abs(math.sin(t) * up + 1) < 0.2 else 1.0
        sp.append(P(3.2 * u + math.cos(t) * r * 0.78, up * 5.4 * u + math.sin(t) * r * notch))
    poly(d, sp, std, out=pal["out"])
    # deeper colour towards its base, and the fine radiating veins
    d.polygon(_oval(P, 3.2 * u, up * 2.2 * u, 3.0 * u * shrink, 2.2 * u * shrink), fill=std_base)
    for vx in (-3.4, -1.7, 0.0, 1.7, 3.4):
        d.line([P(3.2 * u, up * 1.2 * u),
                P((3.2 + vx * 0.55) * u, up * 6.0 * u),
                P((3.2 + vx) * u, up * 9.6 * u * shrink)],
               fill=pal["vein"], width=1, joint="curve")
    # wings: two rounded petals forward, the far one a shade darker
    poly(d, _oval(P, 6.8 * u, up * 0.6 * u, 4.2 * u * shrink, 2.7 * u * shrink,
                  rot=up * (-0.35 + wing_turn)), wing2, out=pal["out"])
    poly(d, _oval(P, 6.2 * u, up * -0.5 * u, 4.0 * u * shrink, 2.6 * u * shrink,
                  rot=up * (-0.15 + wing_turn * 0.6)), wing, out=pal["out"])
    # keel: pale, boat-shaped, its tip curving up
    kpts = [P(3.0 * u, up * -1.6 * u), P(6.5 * u, up * -1.9 * u), P(9.4 * u, up * -1.2 * u),
            P(10.4 * u, up * 0.2 * u), P(9.2 * u, up * -2.8 * u), P(5.6 * u, up * -3.6 * u),
            P(3.0 * u, up * -3.0 * u)]
    poly(d, kpts, keel, out=pal["out"])
    _calyx(d, P, k)


def _draw_flower_front(d, plant, fx, fy, k, wilt, rng):
    """A pea flower seen from the front: the round banner fills the view,
    the two wings below it left and right, the keel peeping out between."""
    pal = PURPLE if plant.purple else WHITE
    brown = (176, 156, 120, 255)
    u = k * SS * (1 - 0.25 * wilt)
    cx, cy = fx + rng.uniform(-1, 1) * SS, fy - 4.5 * u
    std = mix(pal["std"], brown, wilt * 0.6)
    pts = []
    for a in range(0, 360, 10):
        t = math.radians(a)
        r = 6.6 * u * (0.93 if abs(math.sin(t) + 1) < 0.12 else 1.0)       # notch at the top
        pts.append((cx + math.cos(t) * r * 1.05, cy + math.sin(t) * r * 0.92))
    poly(d, pts, std, out=pal["out"])
    d.ellipse((cx - 3.0 * u, cy - 1.0 * u, cx + 3.0 * u, cy + 3.4 * u),
              fill=mix(pal["std_base"], brown, wilt * 0.6))
    for vx in (-0.9, -0.45, 0.0, 0.45, 0.9):
        d.line([(cx, cy + 2.4 * u), (cx + vx * 3.2 * u, cy - 1.8 * u),
                (cx + vx * 5.4 * u, cy - 5.2 * u)], fill=pal["vein"], width=1, joint="curve")
    wing = mix(pal["wing"], brown, wilt * 0.6)
    P0 = lambda x, y: (cx + x, cy + y)
    for sx in (-1, 1):
        poly(d, _oval(P0, sx * 2.6 * u, 4.6 * u, 2.9 * u, 2.2 * u, rot=sx * 0.5), wing, out=pal["out"])
    d.ellipse((cx - 1.2 * u, cy + 4.0 * u, cx + 1.2 * u, cy + 6.6 * u),
              fill=mix(pal["keel"], brown, wilt * 0.6), outline=pal["out"])
    d.line((fx, fy, cx, cy + 5.6 * u), fill=OUT, width=SS)        # little stalk to the calyx


def _draw_bud(d, plant, fx, fy, ang, g):
    """Closed bud: green calyx with the coloured petal tip peeking out."""
    pal = PURPLE if plant.purple else WHITE
    P = _local(fx, fy, ang)
    # clearly a bud from the start: full colour tip, a good size
    # (white buds stay greener, so they don't look like open flowers)
    tip = (mix((150, 196, 120, 255), pal["wing"], 0.55 + 0.4 * g) if plant.purple
           else mix((150, 196, 120, 255), pal["std"], 0.3 + 0.35 * g))
    sz = 0.9 + 0.2 * g
    pts = []
    for i2 in range(13):
        u = i2 / 12
        w = math.sin(math.pi * u) ** 0.7 * 3.9 * SS * sz
        pts.append((u * 11.0 * SS * sz, w))
    shape = [P(x, y) for x, y in pts] + [P(x, -y) for x, y in pts[::-1]]
    poly(d, shape, tip, out=pal["out"])
    _calyx(d, P, 0.9)


def _draw_pod(d, plant, fx, fy, side, g, dry):
    """Pea pod hanging from the flower stalk: slightly sickle-shaped with a
    slender curved beak, the star-shaped green calyx at the top, a light
    band along the back with the seam, a shaded belly and — once the peas
    fill out — their rounded shapes showing (deep waists between them on
    constricted pods)."""
    base = POD_YELLOW if plant.pod_yellow else POD_GREEN
    col = mix(base, POD_DRY, dry)
    outc = mix(OUT, POD_DRY_OUT, dry)
    light = mix(col, (255, 255, 225, 255), 0.38)
    shade = mix(col, (30, 50, 20, 255), 0.22)
    seam = mix(mix(base, (255, 255, 230, 255), 0.55), POD_DRY_OUT, dry * 0.7)
    L, W = 24 * SS * g, 6.4 * SS * g
    hang = math.pi / 2 - side * 0.28                  # down, a little outward
    P = _local(fx, fy, hang)
    n_seeds = 6
    back, belly, hl, sh = [], [], [], []
    for i2 in range(31):
        u = i2 / 30
        curve = math.sin(u * math.pi) * 1.8 * SS * g * -side       # gentle sickle bend
        w = math.sin(math.pi * min(1.0, u * 1.06)) ** 0.45 * W
        bump = 0.5 - 0.5 * math.cos(2 * math.pi * n_seeds * u)        # smooth: 0 between peas, 1 on a pea
        if plant.constricted:
            w *= 0.66 + 0.34 * bump
        elif g > 0.6:
            w *= 0.95 + 0.05 * bump                                      # peas showing a little
        top = curve - W * 0.28
        back.append(P(u * L, top))
        belly.append(P(u * L, top + w))
        hl.append(P(u * L, top + w * 0.36))
        sh.append(P(u * L, top + w * 0.74))
    # slender beak, curving a little upward
    beak = [P(L + 1.2 * SS * g, -W * 0.22), P(L + 2.6 * SS * g, -W * 0.42)]
    outline = back + beak + belly[::-1]
    d.polygon(outline, fill=col)
    if g > 0.25:
        d.polygon(back[1:-1] + hl[-2:0:-1], fill=light)           # sunlit back
        d.polygon(sh[1:-1] + belly[-2:0:-1], fill=shade)          # shaded belly
        if g > 0.6 and dry < 0.6:
            # the peas inside: soft rounded highlights along the middle
            for j in range(n_seeds):
                uu = (j + 0.5) / n_seeds * 0.92 + 0.03
                cx_, cy_ = P(uu * L, -W * 0.28 + W * 0.42 + math.sin(uu * math.pi) * 1.8 * SS * g * -side)
                r = W * (0.20 if plant.constricted else 0.15)
                d.ellipse((cx_ - r, cy_ - r * 0.8, cx_ + r, cy_ + r * 0.8),
                          fill=mix(light, (255, 255, 240, 255), 0.25))
    d.line(outline + [outline[0]], fill=outc, width=OW, joint="curve")
    # seam along the back
    d.line(back[2:-2], fill=seam, width=max(1, SS - 1))
    # dry pods: a few darker wrinkles
    if dry > 0.3:
        for u in (0.25, 0.45, 0.65, 0.82):
            a_ = P(u * L, -W * 0.1)
            b_ = P(u * L + 1.5 * SS, W * 0.45)
            d.line([a_, b_], fill=mix(col, POD_DRY_OUT, 0.5 * dry), width=max(1, SS - 1))
    _calyx(d, _local(fx, fy, hang), 0.95, col=mix(CALYX, POD_DRY, dry))


THREAD = (200, 40, 40, 255)        # red thread: emasculated flower
TAG = (250, 248, 236, 255)          # small paper tag: pollinated (crossed) flower


def _draw_marks(d, nx, ny, fx, fy, mk):
    """The gardener's marks on a flower stalk, which stay on the pod: a red
    thread for an emasculated flower, a little white tag for a pollinated
    one."""
    mx, my = nx + (fx - nx) * 0.45, ny + (fy - ny) * 0.45
    if mk.get("e"):
        r = 1.6 * SS
        d.ellipse((mx - r, my - r, mx + r, my + r), outline=THREAD, width=SS)
    if mk.get("p"):
        tx, ty = mx + 1.5 * SS, my + 1.0 * SS
        d.line((mx, my, tx, ty), fill=OUT, width=1)
        w, h = 3.2 * SS, 4.2 * SS
        d.rectangle((tx - w / 2, ty, tx + w / 2, ty + h), fill=TAG, outline=OUT, width=max(1, SS - 1))


def _flower_or_pod(d, plant, fx, fy, t, ang):
    if t < OPEN_AFTER:                                   # bud
        _draw_bud(d, plant, fx, fy, ang, t / OPEN_AFTER)
        return
    t -= OPEN_AFTER
    if t < FLOWER_DAYS:                                  # open flower
        wilt = max(0.0, (t - FLOWER_DAYS * 0.6) / (FLOWER_DAYS * 0.4))
        _draw_flower(d, plant, fx, fy, ang, 1.0, wilt)
        return
    t -= FLOWER_DAYS
    g = min(1.0, 0.3 + 0.7 * t / POD_GROW)
    dry = max(0.0, min(1.0, (t - POD_GROW) / POD_DRY_DAYS))
    side = 1 if math.cos(ang) >= 0 else -1
    _draw_pod(d, plant, fx, fy, side, g, dry)


HS = int(S * 1.5)        # drawing canvas height (headroom above the tile picture)


# Lookup tables for the colour passes (built once, not per picture)
_LUT_A20 = [255 if v > 20 else 0 for v in range(256)]
_LUT_A100 = [255 if v > 100 else 0 for v in range(256)]
_LUT_EDGE = [190 if v else 0 for v in range(256)]
_LUT_EDGE_SOFT = [min(255, int(v * 0.9)) for v in range(256)]
_LUT_BACK = [min(255, int(v * (1.0 + DEPTH_BRIGHT))) for v in range(256)]
_LUT_BACK_A = [int(v * DEPTH_ALPHA) for v in range(256)]
_LUT_WARM_R = [min(255, int(v * PAINT_WARM[0] + PAINT_WARM[1])) for v in range(256)]
_LUT_WARM_B = [int(v * PAINT_WARM[2]) for v in range(256)]


def _fit(img):
    """Back to an S x S picture standing on its bottom edge. If anything
    reaches above the picture, the whole plant is scaled down a little to
    fit — so no plant ever grows out of its plot."""
    if img.height <= S:
        return img
    a = img.getchannel("A").point(_LUT_A20)
    bb = a.getbbox()
    top = bb[1] if bb else img.height - S
    need = img.height - top + 3 * SS              # content height + a little air (and the outline)
    if need <= S:
        return img.crop((0, img.height - S, S, img.height))
    k = S / float(need)
    small = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS,
                       reducing_gap=2.0)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(small, ((S - small.width) // 2, S - small.height), small)
    return out


SOIL = ((150, 112, 72, 255), (176, 136, 92, 255), (120, 86, 54, 255), (196, 160, 112, 255),
        (96, 68, 42, 255))


def _draw_crumbs(d, plant, cx, ground):
    """A few tiny crumbs of earth where the stem meets the soil (fixed per
    plant, so they don't jump around between redraws)."""
    r = random.Random(int(getattr(plant, "rseed", 0) or 0) * 31 + 7)
    for _ in range(r.randint(10, 14)):
        side = r.choice((-1, 1))
        x = cx + side * r.uniform(1.2, 9.5) * SS
        y = ground + r.uniform(-0.8, 1.6) * SS
        w = r.uniform(0.8, 1.9) * SS
        h = w * r.uniform(0.6, 0.9)
        col = r.choice(SOIL)
        d.ellipse((x - w, y - h, x + w, y + h), fill=col, outline=mix(col, OUT, 0.55), width=1)
        # a tiny light speck on top
        d.ellipse((x - w * 0.45, y - h * 0.75, x, y - h * 0.2), fill=mix(col, (255, 240, 210, 255), 0.35))


def _finish(img):
    c = _layers.pop("crumbs", None)
    if c:
        try:
            _draw_crumbs(ImageDraw.Draw(img), *c)
        except Exception:
            pass
    back = _layers.get("img")
    _layers["back"] = None
    _layers["img"] = None
    if back is not None and back.getbbox():
        if back.size != img.size:
            back = back.resize(img.size)
        # far-side leaves: slightly brighter (and transparent if DEPTH_ALPHA < 1)
        r, g, b, a = back.split()
        r, g, b = r.point(_LUT_BACK), g.point(_LUT_BACK), b.point(_LUT_BACK)
        if DEPTH_ALPHA < 1.0:
            a = a.point(_LUT_BACK_A)
        img = Image.alpha_composite(Image.merge("RGBA", (r, g, b, a)), img)
    img = _fit(img)
    out_px = int(_layers.get("out_px") or TILE)  # TILE, or larger (e.g. the Inspect window)
    small = img.resize((out_px, out_px), Image.LANCZOS, reducing_gap=2.0)
    plant_a = small.getchannel("A")
    if PAINTERLY:
        small = _paint_polish(small)          # done at tile size: same look, ~9x fewer pixels
    else:
        small = _ground_shadow(small)         # the plain style gets the shadow too
    # ~1-px dark border around the plant's outline. Built from the soft
    # (anti-aliased) outline rather than a hard on/off mask, so it is
    # smooth instead of a stair-stepped pixel line — at no extra cost.
    m = plant_a
    # leave thin things (tendrils, stalks) out: only solid shapes get the border
    solid = m.point(_LUT_A100).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    solid = ImageChops.multiply(solid.filter(ImageFilter.MaxFilter(3)), m.filter(ImageFilter.MaxFilter(3)))
    edge = ImageChops.subtract(solid, m)
    line = Image.new("RGBA", (out_px, out_px), (14, 16, 12, 0))
    line.putalpha(edge.point(_LUT_EDGE_SOFT))
    return Image.alpha_composite(small, line)


def _paint_polish(img):
    """Subtle finishing touches in a soft, hand-painted storybook spirit:
    warm sunlight, a gentle glow around the plant and a soft shadow on
    the ground. Only colours are touched — shapes stay exactly as drawn."""
    a = img.getchannel("A")
    rgb = img.convert("RGB")
    # warm, slightly golden light
    r, g, b = rgb.split()
    r = r.point(_LUT_WARM_R)
    b = b.point(_LUT_WARM_B)
    rgb = Image.merge("RGB", (r, g, b))
    # Works at any size: blur radii scale with the picture (drawn at S,
    # polished at TILE).
    k = img.width / float(S)
    # soft glow: a blurred copy screened over the plant at low strength
    glow = rgb.filter(ImageFilter.GaussianBlur(5 * SS / 3.0 * k))
    rgb = Image.blend(rgb, ImageChops.screen(rgb, glow), PAINT_GLOW)
    if PAINT_SAT != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(PAINT_SAT)
    out = Image.merge("RGBA", (*rgb.split(), a))
    return _ground_shadow(out, a, k)


def _ground_shadow(out, a=None, k=None):
    """Soft shadow on the soil under the plant (both plant styles)."""
    img = out
    if a is None:
        a = out.getchannel("A")
    if k is None:
        k = out.width / float(S)
    sh = Image.new("L", img.size, 0)
    dd = ImageDraw.Draw(sh)
    bbox = a.getbbox()
    if bbox:
        # compact, centred under the stem (the middle of the picture)
        cx = img.width / 2.0
        w = min((bbox[2] - bbox[0]) * 0.26, img.width * 0.2)
        # flat, soft, and kept inside the picture (it used to be cut off
        # at the bottom edge)
        ry, blur = 2.0 * SS * k, 1.5 * SS * k
        gy = min(bbox[3] - 2 * SS * k, img.height - 1 - ry - 2 * blur)
        dd.ellipse((cx - w, gy - ry, cx + w, gy + ry), fill=80)
        sh = sh.filter(ImageFilter.GaussianBlur(blur))
        shadow = Image.new("RGBA", img.size, (40, 30, 20, 0))
        shadow.putalpha(sh)
        out = Image.alpha_composite(shadow, out)
    return out




# ---------------------------------------------------------------- game API
_POD_SLOTS = {}


def pod_slots(tall, terminal):
    """How many pods the drawn plant can show at most (fixed per plant
    type, so worked out once)."""
    k = (bool(tall), bool(terminal))
    n = _POD_SLOTS.get(k)
    if n is None:
        p = PeaPlant(tall=k[0], terminal=k[1])
        n = _POD_SLOTS[k] = len(p.flowers(999))
    return n


def late_model_age(days):
    """Game days since a re-flowering bud appeared -> this drawing's flower
    timeline (bud 3 days, open 4, pod growing 5, then ripening)."""
    d = max(0.0, float(days))
    if d <= OPEN_AFTER + FLOWER_DAYS:
        return d
    if d <= 12:
        return OPEN_AFTER + FLOWER_DAYS + (d - 7) * (POD_GROW / 5.0)
    return OPEN_AFTER + FLOWER_DAYS + POD_GROW + min(POD_DRY_DAYS, (d - 12) * 1.5)


def flowers_drawn(tall, terminal, n_flowers):
    """How many of the plant's flowers (= later pods) the picture shows. A
    tile can't show 15 pods, so the drawing is a scaled-down view: about
    one drawn flower per 2 real ones, never fewer than one. Dwarfs carry
    half as many flowers and have fewer places to show them."""
    slots = pod_slots(tall, terminal)
    n = int(n_flowers or 0)
    if n <= 0:
        return 0
    ref = 12.0 if tall else 6.0
    return max(1, min(slots, int(slots * n / ref + 0.5)))


_FLAGS_CACHE = {}


def trait_flags(traits):
    """The drawing's yes/no traits from a plant's trait dict (cached)."""
    try:
        k = tuple(sorted((str(a), str(b)) for a, b in (traits or {}).items()))
    except Exception:
        return _trait_flags(traits)
    f = _FLAGS_CACHE.get(k)
    if f is None:
        if len(_FLAGS_CACHE) > 512:
            _FLAGS_CACHE.clear()
        f = _FLAGS_CACHE[k] = _trait_flags(traits)
    return dict(f)


def _trait_flags(traits):
    """The drawing's yes/no traits from a plant's trait dict. Tolerates the
    game's synonyms ("short" = "dwarf", "swollen" = "inflated", "violet" =
    "purple") and the old key stem_length."""
    t = {str(k).lower(): str(v).strip().lower() for k, v in (traits or {}).items()}
    h = t.get("plant_height", t.get("stem_length", "tall"))
    return {
        "tall": h not in ("dwarf", "short"),
        "terminal": t.get("flower_position", "axial") == "terminal",
        "purple": t.get("flower_color", "purple") != "white",
        "pod_yellow": t.get("pod_color", "green") == "yellow",
        "constricted": t.get("pod_shape", "inflated") == "constricted",
        "seed_yellow": t.get("seed_color", "green") == "yellow",
    }


def plant_image(traits, seed, age, pods_visible=None, painterly=True, phase=0.0,
                sickness=0.0, flowers_max=None, size=TILE, marks=None, late=None):
    """PIL RGBA picture (TILE x TILE) of a plant with these Mendel traits
    (dict with plant_height, flower_position, flower_color, pod_color,
    pod_shape) at `age` model days."""
    global PAINTERLY
    f = trait_flags(traits)
    plant = PeaPlant(
        tall=f["tall"], terminal=f["terminal"], purple=f["purple"],
        pod_yellow=f["pod_yellow"], constricted=f["constricted"],
        seed=int(seed) if str(seed).lstrip("-").isdigit() else abs(hash(seed)) % 100000)
    plant.seed_color = "yellow" if f["seed_yellow"] else "green"
    old = PAINTERLY
    PAINTERLY = bool(painterly)
    # The drawing is made at S x S (3x the tile), so a bigger picture of up
    # to S pixels simply keeps more of that detail.
    _layers["out_px"] = max(16, min(S, int(size or TILE)))
    try:
        return render(plant, float(age), phase=phase, pods_visible=pods_visible,
                      sickness=sickness, flowers_max=flowers_max, marks=marks, late=late)
    finally:
        PAINTERLY = old
        _layers["out_px"] = TILE


def final_image(traits, seed, args, size, health=100):
    """The tile picture as the game shows it: plant_image() plus the flip
    and the weak / late-season tint. `args` is the game's _grown_args dict.
    (Used by the game itself and by its background helper pea_worker.py.)"""
    pil = plant_image(traits, seed, args["age"],
                      pods_visible=args.get("pods_visible"), painterly=args["painterly"],
                      sickness=args["sickness"], flowers_max=args["flowers_max"],
                      size=size, marks=args.get("marks"), late=args.get("late"))
    if args.get("flipped"):
        pil = pil.transpose(Image.FLIP_LEFT_RIGHT)
    is_weak, is_late, needs_tint = args.get("tint", (False, False, False))
    if needs_tint:
        r, g, b, a = pil.split()
        if is_late and not is_weak:
            t = max(0.0, min(1.0, (80 - float(health)) / 80.0))
            r_m, g_m, b_m = 1.0 + 0.12 * t, 1.0 + 0.03 * t, 1.0 - 0.35 * t
        else:
            r_m, g_m, b_m = 1.10, 1.05, 0.70
        r = r.point(lambda v: min(255, int(v * r_m)))
        g = g.point(lambda v: min(255, int(v * g_m)))
        b = b.point(lambda v: max(0, int(v * b_m)))
        pil = Image.merge("RGBA", (r, g, b, a))
    return pil


# The game's growth stages (plant.STAGE_NAMES) on this drawing's timeline:
# where each stage begins, in model days.
STAGE_AGE = {0: 0.0, 1: 0.0, 2: 3.0, 3: 7.0, 4: 31.0, 5: 33.5, 6: 38.0, 7: 50.0}


def model_age(stage, frac, days_in_stage7=0.0):
    """Model age for a plant `frac` (0..1) of the way through `stage`."""
    stage = max(0, min(7, int(stage)))
    if stage >= 7:
        return STAGE_AGE[7] + min(28.0, max(0.0, days_in_stage7) * 0.8)
    a0, a1 = STAGE_AGE[stage], STAGE_AGE[stage + 1]
    return a0 + (a1 - a0) * max(0.0, min(1.0, frac))
