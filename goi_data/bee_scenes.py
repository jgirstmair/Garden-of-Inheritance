"""
Little animated scenes for the beehive window — one for every page, each
matching what that page tells (Garden-of-Inheritance.py,
_open_beehive_popup):

  "hive"    the garden's beehive and two pea plants in flower
  "comb"    a honeycomb; bees (drawn here, seen from above) crawl about
            on it the way the weevils do in the jar (beetle_jar.py)
  "ratio"   one hive and a pea plant on each side; light (Italian) drones
            fly to the left one, dark (German) ones to the right one
  "abbey"   the abbey wall, its beehive and two pea plants in front
  "house"   Mendel's brick bee house of 1871 with the band of hive fronts
            under its roof, a beehive and two pea plants
  "meadow"  two pea plants in flower

At most two pea plants and one beehive per page.

The bees behave as in the pea garden (wildlife.py): they come out of the
hive, glide to a flower on a gently curved, slightly wobbly path (eased in
and out), sit there flapping slowly and shifting a little, hop on to
another free flower after a few seconds, and after a while fly home into
the hive. One bee per flower. They are never mirrored — the game's bee
pictures (icons/wildlife/bee*_frame1/2.png) are used as they are, at the
garden's size relative to the plants. The plants are the game's flowering
plant pictures, and the bees land on their flowers.

BeeStage(parent, kind, width, height, bg).canvas — place it; it stops on
its own when the canvas is destroyed.
"""

import math
import os
import random
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    Image = None

SCENES = ("hive", "comb", "ratio", "abbey", "house", "meadow")

# The garden's own flight settings (wildlife.py), so both look the same.
FLY_STEP_MS, FLAP_STEPS, FRAME_MS, WANDER_MS = 40, 3, 900, 1400
HOP_MIN_MS, HOP_MAX_MS, MAX_FLIGHT_S = 2500, 5500, 3.5
MIN_STAY_MS, MAX_STAY_MS = 12000, 42000
try:
    import wildlife as _wl
    FLY_STEP_MS, FLAP_STEPS = _wl.FLY_STEP_MS, _wl.FLAP_STEPS
    FRAME_MS, WANDER_MS = _wl.FRAME_MS, _wl.WANDER_MS
    HOP_MIN_MS, HOP_MAX_MS, MAX_FLIGHT_S = _wl.HOP_MIN_MS, _wl.HOP_MAX_MS, _wl.MAX_FLIGHT_S
    MIN_STAY_MS, MAX_STAY_MS = _wl.MIN_STAY_MS, _wl.MAX_STAY_MS
except Exception:
    _wl = None

GARDEN_TILE = 85       # plot size the garden's pictures are made for
GROUND = 0.88          # where things stand (share of the scene's height)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Pictures from the game
# ---------------------------------------------------------------------------

def _drawn_bee(px=22, wings_up=True):
    """A small bee seen from above — only used without the game's icons."""
    k = 4
    S = px * k
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    spread = 0.30 if wings_up else 0.22
    for sx in (-1, 1):
        cx = S * (0.5 + sx * spread)
        d.ellipse((cx - S * 0.18, S * 0.20, cx + S * 0.18, S * 0.52),
                  fill=(235, 245, 255, 170), outline=(150, 170, 190, 220), width=k)
    d.ellipse((S * 0.36, S * 0.30, S * 0.64, S * 0.90), fill=(240, 190, 40, 255),
              outline=(60, 40, 10, 255), width=k)
    for y in (0.50, 0.62, 0.74):
        d.rectangle((S * 0.37, S * y, S * 0.63, S * (y + 0.05)), fill=(45, 30, 10, 255))
    d.ellipse((S * 0.40, S * 0.16, S * 0.60, S * 0.34), fill=(45, 30, 10, 255))
    return im.resize((px, px), Image.LANCZOS)


def load_bee_frames(scale=1.0):
    """[(frame1, frame2), ...] PIL images of the game's bee pictures at the
    garden's size times `scale`; a drawn bee if there are none."""
    out = []
    d = _wl._find_icon_dir() if _wl is not None else None
    try:
        names = sorted(f[:-len("_frame1.png")] for f in os.listdir(d)
                       if f.startswith("bee") and f.endswith("_frame1.png")) if d else []
    except Exception:
        names = []
    for base in names:
        fr = []
        for n in (1, 2):
            p = os.path.join(d, f"{base}_frame{n}.png")
            if not os.path.exists(p):
                break
            try:
                im = Image.open(p).convert("RGBA")
                if scale != 1.0:
                    im = im.resize((max(1, round(im.width * scale)),
                                    max(1, round(im.height * scale))), Image.LANCZOS)
                fr.append(im)
            except Exception:
                break
        if fr:
            if len(fr) == 1:
                fr.append(fr[0])
            out.append(tuple(fr))
    if len(out) > 1:
        # some garden bees are much bigger (other kinds of bee) — only the
        # ordinary-sized ones here
        sizes = [max(f[0].size) for f in out]
        small = min(sizes)
        out = [f for f, sz in zip(out, sizes) if sz <= small * 1.25]
    if not out:
        px = max(12, round(22 * scale))
        out = [(_drawn_bee(px, True), _drawn_bee(px, False))]
    return out


def _crawl_bee(length, legs=0):
    """A worker bee seen from above, head up, `length` px long, drawn here
    for the comb (it is turned as it walks, so it has to look right from
    every side). `legs` 0/1: the two steps of its walk."""
    k = 6
    L = length * k
    S = int(L * 1.25)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = S / 2
    top = (S - L) / 2
    ol = (35, 24, 10, 255)
    lw = max(1, int(0.07 * L / 2))
    # legs: three pairs from the thorax, swinging a little
    ty = top + L * 0.40
    sw = (1 if legs else -1) * L * 0.05
    for j, (dy, ang) in enumerate(((-0.08, -0.55), (0.0, 0.05), (0.08, 0.55))):
        for side in (-1, 1):
            off = sw * (1 if (j % 2 == 0) == (side < 0) else -1)
            x0, y0 = cx + side * L * 0.08, ty + L * dy
            x1 = cx + side * L * 0.30
            y1 = y0 + L * 0.20 * ang + off
            d.line([(x0, y0), (x1, y1)], fill=ol, width=lw)
    # antennae
    for side in (-1, 1):
        d.line([(cx + side * L * 0.03, top + L * 0.12), (cx + side * L * 0.10, top + L * 0.02),
                (cx + side * L * 0.15, top)], fill=ol, width=lw)
    # abdomen with stripes
    ab = (cx - L * 0.17, top + L * 0.42, cx + L * 0.17, top + L * 1.0)
    d.ellipse(ab, fill=(236, 178, 40, 255), outline=ol, width=lw)
    for f in (0.56, 0.70, 0.84):
        y = top + L * f
        half = L * 0.17 * math.sqrt(max(0.0, 1 - ((y - (top + L * 0.71)) / (L * 0.29)) ** 2))
        d.line([(cx - half + lw, y), (cx + half - lw, y)], fill=(45, 30, 10, 255),
               width=int(L * 0.06))
    # thorax (fuzzy) and head
    d.ellipse((cx - L * 0.14, top + L * 0.26, cx + L * 0.14, top + L * 0.52),
              fill=(150, 105, 45, 255), outline=ol, width=lw)
    d.ellipse((cx - L * 0.10, top + L * 0.09, cx + L * 0.10, top + L * 0.28),
              fill=(55, 38, 18, 255), outline=ol, width=lw)
    # wings folded back over the abdomen
    wing = Image.new("RGBA", im.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wing)
    for side in (-1, 1):
        x_in, x_out = cx + side * L * 0.03, cx + side * L * 0.19
        wd.ellipse((min(x_in, x_out), top + L * 0.38, max(x_in, x_out), top + L * 0.74),
                   fill=(230, 240, 252, 95), outline=(120, 140, 165, 200), width=lw)
    im.alpha_composite(wing)
    return im


def _tint_dark(im):
    """A dark drone (the »German« kind, next to the light »Italian«)."""
    r, g, b, a = im.split()
    r = r.point(lambda v: int(v * 0.42))
    g = g.point(lambda v: int(v * 0.36))
    b = b.point(lambda v: int(v * 0.34))
    return Image.merge("RGBA", (r, g, b, a))


def _plant(rnd, height):
    """A flowering pea plant as in the garden (its own picture), `height` px
    tall, and the flower spots on it (x, y in the picture) — or None."""
    try:
        import icon_loader as il
        pos = "terminal"              # looks right from the side
        col = rnd.choice(("purple", "white"))
        path = il.flower_icon_path_hi(pos, col) or il.flower_icon_path(pos, col)
        if not path:
            return None
        pil = Image.open(path).convert("RGBA")
    except Exception:
        return None
    if rnd.random() < 0.5:
        pil = pil.transpose(Image.FLIP_LEFT_RIGHT)
    spots = []
    try:
        cl = _wl._cluster_spots(_wl._scan_spots(pil, False), radius=8) if _wl else []
        for c in cl:
            if len(c) >= 5:
                spots.append(_wl._centroid(c))
    except Exception:
        spots = []
    s = height / float(pil.height)
    pil = pil.resize((max(1, round(pil.width * s)), max(1, round(height))), Image.LANCZOS)
    return pil, [(x * s, y * s) for x, y in spots]


def _put_plant(img, rnd, cx, ground, height, flowers):
    p = _plant(rnd, height)
    if p is None:
        return
    pil, spots = p
    x0, y0 = int(cx - pil.width / 2), int(ground - pil.height)
    img.alpha_composite(pil, (x0, max(0, y0)))
    for x, y in spots:
        flowers.append((x0 + x, max(0, y0) + y))


def _draw_hive(img, cx, ground, h, homes=None):
    """The garden's beehive (icons/beehive.png) seen from the front, so it
    stands in these side-view scenes: white roof with its little handle
    block, a white box, a yellow box with the entrance, the dark stand.
    Adds the entrance to `homes`."""
    k = 4
    w = h * 0.78
    W_, H_ = int(w * k + 8 * k), int(h * k + 2 * k)
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ol = (25, 22, 20, 255)
    lw = max(1, int(1.3 * k))
    mx = W_ / 2
    bw = w * k
    x0, x1 = mx - bw / 2, mx + bw / 2
    Hk = h * k
    y_stand = Hk * 0.80
    # stand: two legs with a cross bar
    for lx in (x0 + bw * 0.10, x1 - bw * 0.10):
        d.rectangle((lx - 2.2 * k, y_stand, lx + 2.2 * k, Hk), fill=(70, 64, 58, 255), outline=ol,
                    width=max(1, k // 2))
    d.rectangle((x0 + bw * 0.06, y_stand + (Hk - y_stand) * 0.45, x1 - bw * 0.06,
                 y_stand + (Hk - y_stand) * 0.62), fill=(70, 64, 58, 255), outline=ol,
                width=max(1, k // 2))
    d.rectangle((x0 - 1.5 * k, y_stand - 2.5 * k, x1 + 1.5 * k, y_stand + 1.5 * k),
                fill=(110, 80, 52, 255), outline=ol, width=lw)          # landing board
    # yellow box (lower), white box (upper)
    y_yel = Hk * 0.48
    d.rectangle((x0, y_yel, x1, y_stand - 2.5 * k), fill=(236, 182, 58, 255), outline=ol, width=lw)
    d.rectangle((x0 + lw, y_stand - 7 * k, x1 - lw, y_stand - 3.5 * k), fill=(214, 156, 40, 255))
    y_wh = Hk * 0.22
    d.rectangle((x0, y_wh, x1, y_yel), fill=(246, 242, 234, 255), outline=ol, width=lw)
    d.rectangle((mx - bw * 0.12, (y_wh + y_yel) / 2 - 1.3 * k, mx + bw * 0.12,
                 (y_wh + y_yel) / 2 + 1.3 * k), fill=(60, 50, 40, 255))   # hand hold
    # the roof: a white slab, wider than the boxes, with a shadowed edge
    d.rectangle((x0 - 3.5 * k, Hk * 0.12, x1 + 3.5 * k, y_wh), fill=(252, 250, 246, 255),
                outline=ol, width=lw)
    d.line([(x0 - 3.5 * k + lw, y_wh - lw * 1.2), (x1 + 3.5 * k - lw, y_wh - lw * 1.2)],
           fill=(205, 200, 192, 255), width=lw)
    # the handle block on top
    d.rectangle((mx - bw * 0.17, Hk * 0.03, mx + bw * 0.17, Hk * 0.12 + lw / 2),
                fill=(140, 92, 52, 255), outline=ol, width=lw)
    # entrance slit
    ey = y_stand - 4.5 * k
    d.rectangle((mx - bw * 0.22, ey - 1.2 * k, mx + bw * 0.22, ey + 1.2 * k), fill=(30, 20, 10, 255))
    im = im.resize((max(1, W_ // k), max(1, H_ // k)), Image.LANCZOS)
    img.alpha_composite(im, (int(cx - im.width / 2), int(ground - h)))
    if homes is not None:
        homes.append((cx, ground - h + ey / k))


# ---------------------------------------------------------------------------
# Backdrops (drawn 3x larger and shrunk, for smooth edges)
# ---------------------------------------------------------------------------

def _meadow(d, W, H, k, rnd, flowers=True):
    """Grass along the bottom, a few small flowers."""
    gy = H * 0.80
    d.rectangle((0, gy, W, H), fill=(150, 185, 95, 255))
    for _ in range(int(W / (6 * k))):
        x = rnd.uniform(0, W)
        h = rnd.uniform(H * 0.06, H * 0.14)
        d.line([(x, gy + 2 * k), (x + rnd.uniform(-2, 2) * k, gy - h)],
               fill=(110, 155, 70, 255), width=max(1, k))
    if flowers:
        for _ in range(int(W / (55 * k)) + 2):
            x = rnd.uniform(W * 0.05, W * 0.95)
            y = gy + rnd.uniform(-H * 0.06, H * 0.08)
            r = rnd.uniform(2.5, 4) * k
            col = rnd.choice([(250, 250, 250, 255), (170, 120, 200, 255), (250, 220, 90, 255)])
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)



def _comb_backdrop(W, H, bg, rnd, k=3):
    im = Image.new("RGBA", (W * k, H * k), _hex(bg) + (0,))
    d = ImageDraw.Draw(im)
    # a rounded comb panel
    pad = 4 * k
    d.rounded_rectangle((pad, pad, W * k - pad, H * k - pad), radius=14 * k,
                        fill=(214, 160, 50, 255), outline=(160, 110, 30, 255), width=2 * k)
    r = 9 * k
    hx = r * math.sqrt(3)
    spots = []
    row = 0
    y = pad + r
    while y < H * k - pad - r * 0.5:
        x = pad + r + (hx / 2 if row % 2 else 0)
        while x < W * k - pad - r * 0.5:
            pts = [(x + r * math.cos(math.radians(60 * j + 30)),
                    y + r * math.sin(math.radians(60 * j + 30))) for j in range(6)]
            capped = rnd.random() < 0.35
            honey = rnd.random() < 0.3
            fill = (236, 198, 110, 255) if capped else ((240, 175, 40, 255) if honey
                                                        else (196, 135, 35, 255))
            d.polygon(pts, fill=fill, outline=(150, 100, 25, 255))
            if not capped and not honey and rnd.random() < 0.25:
                d.ellipse((x - 2 * k, y - 3 * k, x + 2 * k, y + 3 * k), fill=(250, 245, 230, 255))
            spots.append((x / k, y / k))
            x += hx
        y += r * 1.5
        row += 1
    return im.resize((W, H), Image.LANCZOS), spots



def _house_backdrop(W, H, bg, rnd, k=3):
    """Mendel's bee house of 1871 (as it still stands at the abbey): red
    brick, a grey metal roof, under it the band of yellow and green hive
    fronts with their little entrances, a brown door and a small window —
    the beehive in front is added by the stage."""
    im = Image.new("RGBA", (W * k, H * k), _hex(bg) + (0,))
    d = ImageDraw.Draw(im)
    Wk, Hk = W * k, H * k
    # a tree at the left, behind
    tx = Wk * 0.03
    d.rectangle((tx - 3 * k, Hk * 0.30, tx + 3 * k, Hk * 0.82), fill=(95, 75, 55, 255))
    for _ in range(9):
        cx_ = tx + rnd.uniform(-14, 18) * k
        cy_ = Hk * rnd.uniform(0.06, 0.36)
        r_ = rnd.uniform(9, 15) * k
        d.ellipse((cx_ - r_, cy_ - r_, cx_ + r_, cy_ + r_),
                  fill=rnd.choice([(110, 150, 70, 255), (95, 135, 60, 255), (125, 165, 80, 255)]))
    _meadow(d, Wk, Hk, k, rnd)
    # the house
    x0, x1 = Wk * 0.10, Wk * 0.50
    yb, yt = Hk * 0.84, Hk * 0.30
    bh, bw = 4 * k, 10 * k
    d.rectangle((x0, yt, x1, yb), fill=(170, 80, 58, 255))
    yy, r_ = yt, 0
    while yy < yb:
        xx = x0 - ((bw / 2) if r_ % 2 else 0)
        while xx < x1:
            d.rectangle((max(x0, xx), yy, min(x1, xx + bw - k), min(yb, yy + bh - k)),
                        fill=rnd.choice([(178, 86, 62, 255), (162, 76, 56, 255),
                                         (186, 96, 68, 255), (150, 70, 52, 255)]))
            xx += bw
        yy += bh
        r_ += 1
    # the band of hive fronts under the eaves: yellow and green slats,
    # every other one with a little entrance at the bottom
    band_t, band_b = yt + 2 * k, yt + (yb - yt) * 0.46
    bx0, bx1 = x0 + (x1 - x0) * 0.05, x0 + (x1 - x0) * 0.72
    d.rectangle((bx0, band_t, bx1, band_b), fill=(120, 150, 70, 255))
    n_sl = 18
    holes = []
    for i in range(n_sl):
        sx0 = bx0 + (bx1 - bx0) * i / n_sl
        sx1 = bx0 + (bx1 - bx0) * (i + 1) / n_sl - k
        d.rectangle((sx0 + k, band_t + k, sx1, band_b - 2 * k),
                    fill=(232, 210, 90, 255) if i % 2 == 0 else (214, 196, 78, 255))
        if i % 2 == 0:
            cx_ = (sx0 + sx1) / 2
            d.rectangle((cx_ - 2 * k, band_b - 5 * k, cx_ + 2 * k, band_b - 3 * k),
                        fill=(60, 40, 20, 255))
            holes.append((cx_ / k, (band_b - 4 * k) / k))
    d.rectangle((bx0 - k, band_b - 2 * k, bx1 + k, band_b), fill=(90, 110, 55, 255))  # sill
    # the door, and a small window
    dx0 = x0 + (x1 - x0) * 0.76
    d.rectangle((dx0, yt + (yb - yt) * 0.22, dx0 + (x1 - x0) * 0.17, yb), fill=(122, 70, 42, 255),
                outline=(80, 45, 25, 255), width=k)
    for j in range(1, 3):
        yy_ = yt + (yb - yt) * (0.22 + 0.26 * j)
        d.line([(dx0 + 2 * k, yy_), (dx0 + (x1 - x0) * 0.17 - 2 * k, yy_)],
               fill=(95, 55, 32, 255), width=k)
    wx0 = x0 + (x1 - x0) * 0.20
    d.rectangle((wx0, yt + (yb - yt) * 0.58, wx0 + 12 * k, yt + (yb - yt) * 0.84),
                fill=(120, 60, 40, 255), outline=(225, 215, 195, 255), width=k)
    # the grey metal roof, one long slope with ribs
    d.polygon([(x0 - 8 * k, yt + 3 * k), (x0 + 6 * k, yt - Hk * 0.16),
               (x1 + 4 * k, yt - Hk * 0.16), (x1 + 10 * k, yt + 3 * k)],
              fill=(186, 190, 192, 255), outline=(130, 134, 138, 255))
    for i in range(1, 16):
        rx = x0 - 8 * k + (x1 - x0 + 18 * k) * i / 16
        d.line([(rx, yt + 3 * k), (rx + 4 * k, yt - Hk * 0.16)], fill=(160, 164, 168, 255),
               width=max(1, k // 2))
    return im.resize((W, H), Image.LANCZOS), holes



def _abbey_wall(d, W, H, k, rnd):
    """The abbey: a stone wall with arched windows."""
    top, bot = H * 0.18, H * 0.82
    d.rectangle((0, top, W, bot), fill=(222, 210, 186, 255))
    sh, sw = 9 * k, 20 * k
    y = top
    r_ = 0
    while y < bot:
        x = -(sw / 2 if r_ % 2 else 0)
        while x < W:
            d.rectangle((x + k, y + k, x + sw - k, min(bot, y + sh) - k),
                        fill=rnd.choice([(214, 200, 174, 255), (226, 214, 190, 255),
                                         (206, 192, 166, 255)]))
            x += sw
        y += sh
        r_ += 1
    d.rectangle((0, top - 4 * k, W, top), fill=(180, 165, 140, 255))      # coping
    for fx in (0.22, 0.5, 0.78):
        cx = W * fx
        ww, wh = 16 * k, (bot - top) * 0.55
        wy = top + (bot - top) * 0.14
        d.rectangle((cx - ww / 2, wy + ww / 2, cx + ww / 2, wy + wh), fill=(92, 104, 120, 255))
        d.pieslice((cx - ww / 2, wy, cx + ww / 2, wy + ww), 180, 360, fill=(92, 104, 120, 255))
        d.line([(cx, wy + 2 * k), (cx, wy + wh)], fill=(200, 188, 164, 255), width=k)




# ---------------------------------------------------------------------------
# The stage
# ---------------------------------------------------------------------------

class _Bee:
    def __init__(self, frames, big=1.0):
        self.frames = frames          # (PhotoImage, PhotoImage)
        self.item = None
        self.x = self.y = 0.0
        self.state = "inside"         # inside / fly / sit / away
        self.t = 0                    # ms left in the state (inside, away)
        self.spot = None              # index into stage.flowers while sitting
        self.base = (0.0, 0.0)        # the flower it sits on
        self.fi = 0
        self.anim_t = 0
        self.wander_t = 0
        self.hop_t = 0
        self.stay_t = 0               # ms left of the visit
        self.path = None
        self.then = None
        self.big = big


class BeeStage:
    """An animated bee scene on its own canvas (see the module's text)."""

    def __init__(self, parent, kind, width=520, height=110, bg="#f5f0e6", seed=None,
                 n_bees=None):
        kind = {"skep": "hive"}.get(kind, kind)       # older name of the first page
        self.kind = kind if kind in SCENES else "meadow"
        self.W, self.H = int(width), int(height)
        self.bg = bg
        self.rnd = random.Random(seed)
        self.canvas = tk.Canvas(parent, width=self.W, height=self.H, bg=bg,
                                highlightthickness=0, bd=0)
        self._alive = True
        self._job = None
        self._refs = []
        self.bees = []
        self.flowers = []             # where bees sit (flowers, comb cells)
        self.homes = []               # hive entrances
        self.taken = set()
        if Image is None:
            return
        self.canvas.bind("<Destroy>", self._stop, add="+")
        self.k = self.H / float(GARDEN_TILE) * 0.95     # garden size → scene size
        self._build()
        if self.kind == "comb":
            self._start_crawlers(n_bees or 7)
            return
        frames = load_bee_frames(self.k)
        n = n_bees if n_bees is not None else {"hive": 4, "ratio": 4, "abbey": 4,
                                               "house": 4, "meadow": 3}[self.kind]
        n = min(n, max(1, len(self.flowers)))
        for i in range(n):
            fr = self.rnd.choice(frames)
            dark = False
            if self.kind == "ratio":
                # light (Italian) drones keep to the left plant, dark
                # (German) ones to the right one
                dark = (i % 2 == 1)
                if dark:
                    fr = (_tint_dark(fr[0]), _tint_dark(fr[1]))
            self._add_bee(i, fr, dark=dark)
        self._job = self.canvas.after(FLY_STEP_MS, self._step)

    def _photo(self, pil):
        ph = ImageTk.PhotoImage(pil)
        self._refs.append(ph)
        return ph

    # -- the picture -------------------------------------------------------
    def _build(self):
        W, H, rnd = self.W, self.H, self.rnd
        g = H * GROUND
        ph = H * 0.74                  # plant height (the garden's proportion)
        hh = H * 0.56                  # hive height
        if self.kind == "comb":
            back, cells = _comb_backdrop(W, H, self.bg, rnd)
            self.flowers = cells
        elif self.kind == "house":
            back, holes = _house_backdrop(W, H, self.bg, rnd)
            self.homes = list(holes)
            _draw_hive(back, W * 0.62, g, hh, self.homes)
            for fx in (0.80, 0.94):
                _put_plant(back, rnd, W * fx, g + 2, ph * rnd.uniform(0.92, 1.0), self.flowers)
        else:
            im = Image.new("RGBA", (W * 3, H * 3), _hex(self.bg) + (0,))
            d = ImageDraw.Draw(im)
            if self.kind == "abbey":
                _abbey_wall(d, W * 3, H * 3, 3, rnd)
            _meadow(d, W * 3, H * 3, 3, rnd, flowers=(self.kind != "meadow"))
            back = im.resize((W, H), Image.LANCZOS)
            if self.kind == "hive":
                _draw_hive(back, W * 0.18, g, hh * 1.15, self.homes)
                xs = (0.56, 0.80)
            elif self.kind == "abbey":
                _draw_hive(back, W * 0.84, g, hh, self.homes)
                xs = (0.22, 0.52)
            elif self.kind == "ratio":
                _draw_hive(back, W * 0.5, g, hh * 1.12, self.homes)
                xs = (0.20, 0.80)
            else:                                          # meadow
                xs = (0.34, 0.66)
            for fx in xs:
                _put_plant(back, rnd, W * fx + rnd.uniform(-8, 8), g + 2,
                           ph * rnd.uniform(0.9, 1.0), self.flowers)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo(back))

    # -- bees --------------------------------------------------------------
    def _add_bee(self, i, frames, dark=False):
        rnd = self.rnd
        b = _Bee((self._photo(frames[0]), self._photo(frames[1])))
        b.queen = False
        b.allow = None
        if self.kind == "ratio":
            half = self.W / 2
            b.allow = {j for j, (x, y) in enumerate(self.flowers) if (x > half) == dark}
        b.item = self.canvas.create_image(-50, -50, image=b.frames[0], anchor="center",
                                          state="hidden")
        self.bees.append(b)
        # half are already sitting on a flower when the page opens; the
        # others come out of the hive (or fly in) one after the other
        if i < 2 or (i % 2 == 0):
            sp = self._free_spot(allow=b.allow)
            if sp is not None:
                self._sit(b, sp)
                return
        b.state = "inside" if self.homes else "away"
        b.t = 400 + i * rnd.randint(700, 1400)

    def _free_spot(self, near=None, max_d=None, allow=None):
        free = [i for i in range(len(self.flowers)) if i not in self.taken
                and (allow is None or i in allow)]
        if near is not None and max_d is not None:
            nf = [i for i in free if math.hypot(self.flowers[i][0] - near[0],
                                                self.flowers[i][1] - near[1]) <= max_d]
            free = nf or free
        return self.rnd.choice(free) if free else None

    def _sit(self, b, idx):
        rnd = self.rnd
        self.taken.add(idx)
        b.spot = idx
        b.base = self.flowers[idx]
        b.x, b.y = b.base
        b.state = "sit"
        b.anim_t = FRAME_MS
        b.wander_t = WANDER_MS
        b.hop_t = rnd.randint(HOP_MIN_MS, HOP_MAX_MS) * (2 if getattr(b, "queen", False) else 1)
        if b.stay_t <= 0:
            b.stay_t = (10 ** 9 if self.kind == "comb"
                        else rnd.randint(MIN_STAY_MS, MAX_STAY_MS))
        self.canvas.itemconfigure(b.item, state="normal", image=b.frames[b.fi])
        self.canvas.coords(b.item, b.x, b.y)

    def _release(self, b):
        if b.spot is not None:
            self.taken.discard(b.spot)
            b.spot = None

    def _edge_point(self):
        rnd, W, H = self.rnd, self.W, self.H
        m = 16
        return rnd.choice([(-m, rnd.uniform(0, H * 0.7)), (W + m, rnd.uniform(0, H * 0.7)),
                           (rnd.uniform(0, W), -m)])

    def _fly(self, b, tx, ty, then):
        """A garden flight (wildlife._Creature._fly_to): eased in and out,
        a gentle bend, a little wobble, about 80–120 px/s."""
        rnd = self.rnd
        dx, dy = tx - b.x, ty - b.y
        dist = max(1.0, math.hypot(dx, dy))
        speed = rnd.uniform(80, 120) * self.k
        speed = max(speed, dist / MAX_FLIGHT_S)
        steps = max(6, int(dist / speed * 1000 / FLY_STEP_MS))
        arc = max(-60.0, min(60.0, rnd.uniform(-0.15, 0.15) * dist))
        b.path = dict(x0=b.x, y0=b.y, dx=dx, dy=dy, steps=steps, i=0, arc=arc,
                      nx=-dy / dist, ny=dx / dist, f=b.fi)
        b.then = then
        b.state = "fly"
        self.canvas.itemconfigure(b.item, state="normal")

    def _go_to_flower(self, b, near=None):
        sp = self._free_spot(near=near, allow=getattr(b, "allow", None))
        if sp is None:
            b.state = "inside" if self.homes else "away"
            b.t = 2000
            self.canvas.itemconfigure(b.item, state="hidden")
            return
        self.taken.add(sp)                       # reserved while flying there
        fx, fy = self.flowers[sp]

        def _land(sp=sp):
            self.taken.discard(sp)
            self._sit(b, sp)
        self._fly(b, fx, fy, _land)

    def _leave(self, b):
        """End of the visit: home into the hive (or away off the picture)."""
        self._release(b)
        b.stay_t = 0
        if self.homes:
            hx, hy = self.rnd.choice(self.homes)

            def _in():
                b.state = "inside"
                b.t = self.rnd.randint(3000, 12000)
                self.canvas.itemconfigure(b.item, state="hidden")
            self._fly(b, hx, hy, _in)
        else:
            ex, ey = self._edge_point()

            def _gone():
                b.state = "away"
                b.t = self.rnd.randint(2000, 8000)
                self.canvas.itemconfigure(b.item, state="hidden")
            self._fly(b, ex, ey, _gone)

    def _step(self):
        self._job = None
        if not self._alive:
            return
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        rnd, ms = self.rnd, FLY_STEP_MS
        for b in self.bees:
            try:
                if b.state in ("inside", "away"):
                    b.t -= ms
                    if b.t <= 0:
                        if b.state == "inside":
                            b.x, b.y = rnd.choice(self.homes)
                        else:
                            b.x, b.y = self._edge_point()
                        self.canvas.coords(b.item, b.x, b.y)
                        self._go_to_flower(b)
                elif b.state == "sit":
                    b.stay_t -= ms
                    b.anim_t -= ms
                    if b.anim_t <= 0:              # slow wing beat, as on a flower
                        b.anim_t = FRAME_MS
                        b.fi ^= 1
                        self.canvas.itemconfigure(b.item, image=b.frames[b.fi])
                    b.wander_t -= ms
                    if b.wander_t <= 0:            # shifts a little on the flower
                        b.wander_t = WANDER_MS
                        bx, by = b.base
                        b.x = max(bx - 3, min(bx + 3, b.x + rnd.randint(-2, 2)))
                        b.y = max(by - 3, min(by + 3, b.y + rnd.randint(-2, 2)))
                        self.canvas.coords(b.item, b.x, b.y)
                    if b.stay_t <= 0:
                        self._leave(b)
                    else:
                        b.hop_t -= ms
                        if b.hop_t <= 0:           # on to another free flower
                            here = b.base
                            self._release(b)
                            self._go_to_flower(b, near=here)
                elif b.state == "fly":
                    p = b.path
                    p["i"] += 1
                    t = p["i"] / float(p["steps"])
                    e = t * t * (3 - 2 * t)
                    bend = math.sin(math.pi * t) * p["arc"]
                    if p["i"] >= p["steps"]:
                        b.x, b.y = p["x0"] + p["dx"], p["y0"] + p["dy"]
                    else:
                        b.x = p["x0"] + p["dx"] * e + p["nx"] * bend + rnd.uniform(-0.7, 0.7)
                        b.y = p["y0"] + p["dy"] * e + p["ny"] * bend + rnd.uniform(-0.7, 0.7)
                    if p["i"] % FLAP_STEPS == 0:
                        b.fi ^= 1
                        self.canvas.itemconfigure(b.item, image=b.frames[b.fi])
                    self.canvas.coords(b.item, b.x, b.y)
                    if p["i"] >= p["steps"]:
                        b.path = None
                        fn, b.then = b.then, None
                        if fn:
                            fn()
            except Exception:
                pass
        self._job = self.canvas.after(ms, self._step)

    # -- the comb: bees crawl about, as the weevils do in the jar ----------
    CRAWL_STEP_MS = 50
    CRAWL_ANGLE = 15

    def _crawl_img(self, size_k, angle, legs):
        sk = round(size_k * 10) / 10.0
        a = int(round(angle / self.CRAWL_ANGLE) * self.CRAWL_ANGLE) % 360
        key = (sk, a, legs)
        im = self._cimgs.get(key)
        if im is None:
            big = self._cbase[legs]
            pil = big.rotate(-a, resample=Image.BICUBIC, expand=False)
            px = max(8, int(self._cpx * 1.25 * sk))
            pil = pil.resize((px, px), Image.LANCZOS)
            im = ImageTk.PhotoImage(pil)
            self._cimgs[key] = im
        return im

    def _start_crawlers(self, n):
        rnd = self.rnd
        self._cpx = max(14, int(self.H * 0.21))          # bee length
        self._cbase = (_crawl_bee(self._cpx, 0), _crawl_bee(self._cpx, 1))
        self._cimgs = {}
        m = self._cpx * 0.55
        self._cbox = (m, m, self.W - m, self.H - m)
        x0, y0, x1, y1 = self._cbox
        self.crawlers = []
        for _ in range(n):
            c = dict(x=rnd.uniform(x0, x1), y=rnd.uniform(y0, y1),
                     heading=rnd.uniform(0, 360), size=rnd.uniform(0.88, 1.10),
                     speed=rnd.uniform(0.45, 1.20), wiggle=rnd.uniform(4.0, 14.0),
                     lazy=rnd.uniform(0.3, 1.0), state=rnd.choice(("rest", "walk")),
                     left=rnd.randint(5, 60), turn=0.0, legs=0, lt=0, shown=None)
            c["item"] = self.canvas.create_image(c["x"], c["y"], image=self._crawl_img(
                c["size"], c["heading"], 0))
            self.crawlers.append(c)
        self._job = self.canvas.after(self.CRAWL_STEP_MS, self._crawl_step)

    def _crawl_step(self):
        self._job = None
        if not self._alive:
            return
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        rnd = self.rnd
        x0, y0, x1, y1 = self._cbox
        for c in self.crawlers:
            c["left"] -= 1
            if c["state"] == "rest":
                if c["left"] <= 0:
                    c["state"], c["left"] = "walk", rnd.randint(20, 110)
                    c["turn"] = rnd.uniform(-1, 1) * c["wiggle"]
                elif rnd.random() < 0.04:
                    c["heading"] += rnd.uniform(-25, 25)      # looks round a little
            else:
                if c["left"] <= 0:
                    c["state"] = "rest"
                    c["left"] = int(rnd.randint(10, 60) * (0.5 + c["lazy"]))
                else:
                    if rnd.random() < 0.08:
                        c["turn"] = rnd.uniform(-1, 1) * c["wiggle"]
                    c["heading"] += c["turn"] * 0.35
                    rad = math.radians(c["heading"])
                    nx = c["x"] + math.sin(rad) * c["speed"]
                    ny = c["y"] - math.cos(rad) * c["speed"]
                    if not (x0 <= nx <= x1 and y0 <= ny <= y1):   # edge: turn back
                        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                        want = math.degrees(math.atan2(cx - c["x"], -(cy - c["y"])))
                        c["heading"] = want + rnd.uniform(-50, 50)
                        nx = min(x1, max(x0, nx))
                        ny = min(y1, max(y0, ny))
                    c["x"], c["y"] = nx, ny
                    c["lt"] += 1
                    if c["lt"] >= 3:                     # a step of the legs
                        c["lt"] = 0
                        c["legs"] ^= 1
            shown = (round(c["x"]), round(c["y"]),
                     int(round(c["heading"] / self.CRAWL_ANGLE)) % (360 // self.CRAWL_ANGLE),
                     c["legs"])
            if shown != c["shown"]:
                c["shown"] = shown
                try:
                    self.canvas.coords(c["item"], c["x"], c["y"])
                    self.canvas.itemconfigure(c["item"], image=self._crawl_img(
                        c["size"], c["heading"], c["legs"]))
                except Exception:
                    pass
        self._job = self.canvas.after(self.CRAWL_STEP_MS, self._crawl_step)

    def _stop(self, e=None):
        if e is not None and e.widget is not self.canvas:
            return
        self._alive = False
        if self._job is not None:
            try:
                self.canvas.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
