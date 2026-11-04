#!/usr/bin/env python3
"""
make_figure.py — publication figures of the pea plants in Garden of Inheritance.

Runs on its own (the game does not need to be open). Put it in the game
folder, next to pea_render.py, icon_loader.py and the icons folder, then:

    python make_figure.py                     # plant style from your game settings
    python make_figure.py --style classic     # the classic stage pictures
    python make_figure.py --style grown_painted
    python make_figure.py --style all         # one set of files per plant style
    python make_figure.py --traits drawn      # the seven traits drawn instead of the icons

Plant styles: classic, grown, grown_painted, grown_staked, grown_staked_painted
(the same choice as Game Settings > Plant style).

It writes, into the folder given with --out (default: figures/):
    pea_figure_plants_<style>.png   growth stages, flower to pod, the seven traits
    pea_figure_care_<style>.png     soil water and the difficulty levels
    pea_figure_plants_<style>.pptx  the same figures as editable PowerPoint slides
    pea_figure_care_<style>.pptx    (text, pictures and shapes are separate objects)

The pictures of the seven traits are the game's own icons, the same ones the
Genotype Explorer (TIE) shows. If an icon file is missing, a drawn picture
stands in for it and the script says which file it looked for.

Needs: Pillow, matplotlib (PNG) and python-pptx (PowerPoint):
    pip install pillow matplotlib python-pptx
"""
import argparse
import io
import json
import math
import os
import random
import sys
import textwrap
import types

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter  # noqa: E402

import pea_render as pr  # noqa: E402
import icon_loader as il  # noqa: E402

STYLES = ("classic", "grown", "grown_painted", "grown_staked", "grown_staked_painted")

# --------------------------------------------------------------------------- look
INK, MUTED, RULE = "#222222", "#555555", "#bbbbbb"
CHIP = {"emasc": "#f6d5d5", "poll": "#d8e6f5", "pollen": "#fbefc4", "harv": "#dcebd2"}
F_LETTER, F_TITLE, F_HEAD, F_BODY, F_NOTE = 13, 10.5, 9, 8.5, 8      # pt
FONT_PPTX = "Arial"
W = 7.087                                  # 180 mm: a double-column figure
WATER_BANDS = [("#FFD54F", "Dry", "0–25 %", "health −2 per hour"),
               ("#81D4FA", "Slightly moist", "26–50 %", "no change (weak plants −1)"),
               ("#42A5F5", "Evenly moist", "51–75 %", "health +1 per hour"),
               ("#1565C0", "Soggy", "76–90 %", "no change (weak plants −1)"),
               ("#003F8C", "Waterlogged", "91–100 %", "health −2 per hour")]

BASE = {"plant_height": "tall", "flower_position": "axial", "flower_color": "purple",
        "pod_color": "green", "pod_shape": "inflated", "seed_color": "yellow",
        "seed_shape": "round"}

MISSING = []                               # icon files that were not found


def LH(fs):
    """height of one text line in inches"""
    return fs * 1.2 / 72.0


def n_lines(s):
    return s.count("\n") + 1


def wrap(s, width_in, fs):
    n = max(8, int(width_in * 72 / (fs * 0.47)))
    return "\n".join(textwrap.fill(p, n) for p in s.split("\n"))


def text_w(s, fs):
    """rough width of a text in inches (for PowerPoint text boxes)"""
    return max(len(line) for line in s.split("\n")) * fs * 0.56 / 72.0 + 0.06



# --------------------------------------------------------------------------- resampling
def _hard_alpha(im):
    """True if the picture's transparency is (nearly) all-or-nothing, as in
    small pixel icons: its edges are stair steps that need smoothing."""
    h = im.getchannel("A").histogram()
    edge = sum(h[1:255])
    solid = h[0] + h[255]
    return solid > 0 and edge < 0.04 * (edge + solid)


def content_bbox(im, thr=40):
    """The visible part of a picture: pixels at least a little opaque (a faint
    glow or shadow around an icon does not count)."""
    return im.getchannel("A").point(lambda v: 255 if v > thr else 0).getbbox()


def scale2x(im):
    """Scale2x (EPX) for pixel art: doubles the size, smoothing stair-step
    edges by copying neighbours instead of blending colours."""
    import numpy as np
    a = np.asarray(im.convert("RGBA")).astype(np.int32)
    key = (a[..., 0] << 24) | (a[..., 1] << 16) | (a[..., 2] << 8) | a[..., 3]
    P = np.pad(key, 1, mode="edge")
    B, D, F, H = P[:-2, 1:-1], P[1:-1, :-2], P[1:-1, 2:], P[2:, 1:-1]
    E = key
    ok = (B != H) & (D != F)
    e0 = np.where(ok & (D == B), D, E)
    e1 = np.where(ok & (B == F), F, E)
    e2 = np.where(ok & (D == H), D, E)
    e3 = np.where(ok & (H == F), F, E)
    h, w = key.shape
    out = np.empty((h * 2, w * 2), dtype=np.int64)
    out[0::2, 0::2], out[0::2, 1::2], out[1::2, 0::2], out[1::2, 1::2] = e0, e1, e2, e3
    rgba = np.stack([(out >> 24) & 255, (out >> 16) & 255, (out >> 8) & 255, out & 255], -1)
    return Image.fromarray(rgba.astype(np.uint8), "RGBA")


def fit_pixels(im, w_px, h_px):
    """Scales a picture to w_px x h_px without the dark / light fringes and
    ringing that plain resampling of a transparent picture gives:
    premultiplied alpha, bicubic for enlargement (Lanczos only to shrink),
    and smooth edges for icons whose transparency is all-or-nothing."""
    w_px, h_px = max(1, int(round(w_px))), max(1, int(round(h_px)))
    im = im.convert("RGBA")
    if (w_px, h_px) == im.size:
        return im
    up = w_px > im.width
    hard = up and _hard_alpha(im)
    # small pixel icons: enlarge with Scale2x first (keeps outlines and
    # diagonals clean instead of blurring them into a blob)
    while up and max(im.size) <= 400 and w_px / float(im.width) >= 2.5:
        im = scale2x(im)
    pm = im.convert("RGBa")                       # premultiplied: no colour bleeding at the edges
    pm = pm.resize((w_px, h_px), Image.BICUBIC if up else Image.LANCZOS)
    out = pm.convert("RGBA")
    if hard:
        # the enlarged stair-step outline, softened and kept crisp
        k = w_px / float(im.width)
        a = out.getchannel("A").filter(ImageFilter.GaussianBlur(max(0.6, k * 0.35)))
        a = a.point(lambda v: 0 if v < 70 else (255 if v > 185 else int((v - 70) * 255 / 115)))
        out.putalpha(a)
    return out

# --------------------------------------------------------------------------- layout
class Layout:
    """Everything on one figure, in inches from the top left corner. Drawn
    twice: by matplotlib (PNG) and as PowerPoint shapes."""

    def __init__(self):
        self.items = []
        self.height = 0.0

    def text(self, x, y, s, fs=F_BODY, bold=False, italic=False, color=INK, ha="center",
             rot=0, bg=None):
        self.items.append(dict(k="text", x=x, y=y, s=s, fs=fs, bold=bold, italic=italic,
                               color=color, ha=ha, rot=rot, bg=bg))

    def image(self, x, y, w, h, im, anchor="S"):
        """the picture fitted into the box (x, y, w, h), keeping its shape;
        anchor S = bottom centre, C = centre"""
        if im is None:
            return
        bb = (content_bbox(im) if im.mode == "RGBA"
              and not im.info.get("keep_frame") else None)
        if bb:
            im = im.crop(bb)
        k = min(w / im.width, h / im.height)
        iw, ih = im.width * k, im.height * k
        ix = x + (w - iw) / 2
        iy = y + (h - ih) if anchor == "S" else y + (h - ih) / 2
        self.items.append(dict(k="image", x=ix, y=iy, w=iw, h=ih, im=im))

    def line(self, x0, y0, x1, y1, color=RULE, lw=0.6):
        self.items.append(dict(k="line", x0=x0, y0=y0, x1=x1, y1=y1, color=color, lw=lw))

    def arrow(self, x0, x1, y, label=None):
        self.items.append(dict(k="arrow", x0=x0, x1=x1, y=y, color=MUTED))
        if label:
            self.text((x0 + x1) / 2, y - 0.05 - LH(F_NOTE), label, F_NOTE, color=MUTED)

    def polygon(self, pts, fill, edge="#333333"):
        self.items.append(dict(k="poly", pts=pts, fill=fill, edge=edge))

    # ------------------------------------------------------------ PNG
    def save_png(self, path, dpi=600):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from matplotlib.patches import FancyArrowPatch, Polygon
        import numpy as np
        have = {f.name for f in font_manager.fontManager.ttflist}
        family = next((f for f in ("Arial", "Helvetica", "Liberation Sans", "FreeSans",
                                   "DejaVu Sans") if f in have), "DejaVu Sans")
        plt.rcParams.update({"font.family": family})
        H = self.height
        fig = plt.figure(figsize=(W, H))
        tf = fig.transFigure
        fx = lambda x: x / W
        fy = lambda y: 1.0 - y / H
        for it in self.items:
            k = it["k"]
            if k == "image":
                ax = fig.add_axes([fx(it["x"]), fy(it["y"] + it["h"]), it["w"] / W, it["h"] / H])
                pic = fit_pixels(it["im"], it["w"] * dpi, it["h"] * dpi)
                ax.imshow(np.asarray(pic), interpolation="none")
                ax.set_axis_off()
            elif k == "text":
                kw = dict(fontsize=it["fs"], color=it["color"], ha=it["ha"], va="top",
                          linespacing=1.2, fontweight="bold" if it["bold"] else "normal",
                          style="italic" if it["italic"] else "normal", rotation=it["rot"])
                if it["rot"]:
                    kw["va"] = "center"
                if it["bg"]:
                    kw["bbox"] = dict(boxstyle="round,pad=0.3,rounding_size=0.4", fc=it["bg"], ec="none")
                fig.text(fx(it["x"]), fy(it["y"]), it["s"], **kw)
            elif k == "line":
                fig.add_artist(plt.Line2D([fx(it["x0"]), fx(it["x1"])], [fy(it["y0"]), fy(it["y1"])],
                                          color=it["color"], lw=it["lw"]))
            elif k == "arrow":
                fig.add_artist(FancyArrowPatch((fx(it["x0"]), fy(it["y"])), (fx(it["x1"]), fy(it["y"])),
                                               transform=tf, arrowstyle="-|>", mutation_scale=7,
                                               lw=0.7, color=it["color"]))
            elif k == "poly":
                fig.add_artist(Polygon([(fx(x), fy(y)) for x, y in it["pts"]], closed=True,
                                       transform=tf, fc=it["fill"], ec=it["edge"], lw=0.6))
        buf = io.BytesIO()
        fig.savefig(buf, dpi=dpi, format="png")
        plt.close(fig)
        return write_file(path, buf.getvalue())

    # ------------------------------------------------------------ PowerPoint
    def add_slide(self, prs):
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
        from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
        slide = prs.slides.add_slide(prs.slide_layouts[6])     # blank
        rgb = lambda h: RGBColor.from_string(h.lstrip("#").upper())

        def textbox(it):
            s, fs = it["s"], it["fs"]
            # generous boxes (the lines are already broken): no unwanted wrapping
            w = text_w(s, fs) * 1.35 + 0.15
            if it["ha"] == "left" and not it["bg"]:
                w = max(w, min(W - it["x"] - 0.02, w * 1.5))
            if it["bg"]:
                w = text_w(s, fs) + 0.04
            h = n_lines(s) * LH(fs) + 0.02
            x = it["x"] - (w / 2 if it["ha"] == "center" else (w if it["ha"] == "right" else 0))
            y = it["y"]
            if it["rot"]:
                # rotated 90°: the box turns around its centre
                cx, cy = it["x"], it["y"]
                x, y = cx - w / 2, cy - h / 2
            if it["bg"]:
                pad = 0.035
                shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x - pad), Inches(y - pad),
                                             Inches(w + 2 * pad), Inches(h + 2 * pad))
                shp.fill.solid()
                shp.fill.fore_color.rgb = rgb(it["bg"])
                shp.line.fill.background()
                shp.shadow.inherit = False
                tfm = shp.text_frame
            else:
                shp = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
                tfm = shp.text_frame
            tfm.word_wrap = bool(it["bg"]) is False
            tfm.auto_size = MSO_AUTO_SIZE.NONE
            for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
                setattr(tfm, m, 0)
            tfm.vertical_anchor = MSO_ANCHOR.TOP if not it["bg"] else MSO_ANCHOR.MIDDLE
            align = {"center": PP_ALIGN.CENTER, "left": PP_ALIGN.LEFT, "right": PP_ALIGN.RIGHT}[it["ha"]]
            for i, line in enumerate(s.split("\n")):
                p = tfm.paragraphs[0] if i == 0 else tfm.add_paragraph()
                p.alignment = align
                p.line_spacing = 1.0
                r = p.add_run()
                r.text = line
                f = r.font
                f.size = Pt(fs)
                f.name = FONT_PPTX
                f.bold = it["bold"]
                f.italic = it["italic"]
                f.color.rgb = rgb(it["color"])
            if it["rot"]:
                shp.rotation = 270

        for it in self.items:
            k = it["k"]
            if k == "image":
                buf = io.BytesIO()
                pic = it["im"]
                if pic.width < it["w"] * 300:
                    pic = fit_pixels(pic, it["w"] * 300, it["h"] * 300)
                pic.save(buf, "PNG")
                buf.seek(0)
                slide.shapes.add_picture(buf, Inches(it["x"]), Inches(it["y"]),
                                         Inches(it["w"]), Inches(it["h"]))
            elif k == "text":
                textbox(it)
            elif k in ("line", "arrow"):
                if k == "line":
                    x0, y0, x1, y1 = it["x0"], it["y0"], it["x1"], it["y1"]
                else:
                    x0, y0, x1, y1 = it["x0"], it["y"], it["x1"], it["y"]
                c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x0), Inches(y0),
                                               Inches(x1), Inches(y1))
                try:
                    c.shadow.inherit = False
                except Exception:
                    pass
                c.line.color.rgb = rgb(it["color"])
                c.line.width = Pt(it.get("lw", 0.7))
                if k == "arrow":
                    ln = c.line._get_or_add_ln()
                    from pptx.oxml.ns import qn
                    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
                    ln.append(tail)
            elif k == "poly":
                pts = it["pts"]
                ff = slide.shapes.build_freeform(Inches(pts[0][0]), Inches(pts[0][1]), scale=1.0)
                ff.add_line_segments([(Inches(x), Inches(y)) for x, y in pts[1:]], close=True)
                shp = ff.convert_to_shape()
                shp.fill.solid()
                shp.fill.fore_color.rgb = rgb(it["fill"])
                shp.line.color.rgb = rgb(it["edge"])
                shp.line.width = Pt(0.6)
                shp.shadow.inherit = False
        return slide


# --------------------------------------------------------------------------- pictures
def _largest_version(path):
    """The same icon in the highest resolution there is: e.g. for
    flower_axial_purple_64x64.png also flower_axial_purple.png,
    ..._128x128.png, ..._256.png (the game shows the small ones on tiles)."""
    d, fn = os.path.split(path)
    stem, ext = os.path.splitext(fn)
    import re
    base = re.sub(r"_(\d+)(x\d+)?$", "", stem)
    cands = {path}
    try:
        for f in os.listdir(d):
            st, ex = os.path.splitext(f)
            if ex.lower() == ext.lower() and (st == base or re.fullmatch(re.escape(base) + r"_\d+(x\d+)?", st)):
                cands.add(os.path.join(d, f))
    except Exception:
        pass
    best, area = path, -1
    for c in cands:
        try:
            with Image.open(c) as im:
                a = im.width * im.height
        except Exception:
            continue
        if a > area:
            best, area = c, a
    return best


def _icon(path, what, expected=None):
    """the icon file (its largest version) as a picture, or None (noted in
    MISSING with the file name the game looks for)"""
    if path and os.path.exists(path):
        path = _largest_version(path)
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            pass
    MISSING.append(f"{what}: icons/{expected or os.path.basename(path or '') or '?'}")
    return None


def _icon_named(names, what):
    for nm in names:
        p = os.path.join(il.ICONS_DIR, nm)
        if os.path.exists(p):
            return _icon(p, what)
    MISSING.append(f"{what}: {' or '.join(names)}")
    return None


def _polish(img, painted):
    """the warm 'painted' finish of the game's painted style"""
    if not painted:
        return img
    a = img.getchannel("A")
    r, g, b = img.convert("RGB").split()
    rgb = Image.merge("RGB", (r.point(pr._LUT_WARM_R), g, b.point(pr._LUT_WARM_B)))
    glow = rgb.filter(ImageFilter.GaussianBlur(max(1, img.width / 90)))
    rgb = Image.blend(rgb, ImageChops.screen(rgb, glow), pr.PAINT_GLOW)
    rgb = ImageEnhance.Color(rgb).enhance(pr.PAINT_SAT)
    return Image.merge("RGBA", (*rgb.split(), a))


def _fake(purple=True, pod_yellow=False, constricted=False, seed_color="yellow"):
    return types.SimpleNamespace(purple=purple, pod_yellow=pod_yellow, constricted=constricted,
                                 seed_color=seed_color, rseed=3, tall=True, terminal=False)


def organ(kind, plant=None, g=1.0, dry=0.0, wilt=0.0, painted=True, out=360, stalk=True):
    """one bud / flower / pod drawn by the game's plant drawing (pea_render)"""
    plant = plant or _fake()
    big, ssb = 2400, 14
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    saved = (pr.SS, pr.OW, pr.poly.__defaults__)
    try:
        pr.SS = ssb
        pr.OW = max(2, round(2 * ssb / 3))
        pr.poly.__defaults__ = (pr.OUT, pr.OW)
        S = pr.SS
        fx, fy = (big * 0.40, big * 0.32) if kind == "pod" else (big * 0.42, big * 0.42)
        if kind == "flower":                 # a side view, not the (random) front view
            for dx in range(400):
                rng = random.Random(int(fx + dx) * 7919 + int(fy) * 104729 + int(plant.rseed))
                for _ in range(4):
                    rng.uniform(0, 1)
                if rng.random() >= 0.22:
                    fx += dx
                    break
        nx, ny = fx - 4.5 * S, fy - 5.5 * S
        if stalk:
            d.line([(nx, ny), ((nx + fx) / 2, ny + (fy - ny) * 0.2), (fx, fy)],
                   fill=pr.TENDRIL, width=int(S * 0.9), joint="curve")
        if kind == "bud":
            pr._draw_bud(d, plant, fx, fy, -0.55, g)
        elif kind == "flower":
            pr._draw_flower(d, plant, fx, fy, -0.55, 1.0, wilt)
        else:
            pr._draw_pod(d, plant, fx, fy, 1, g, dry)
    finally:
        pr.SS, pr.OW, pr.poly.__defaults__ = saved
    img = img.crop(img.getbbox())
    k = out / max(img.size)
    img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
    return _polish(img, painted)


def drawn_seed(color="yellow", shape="round", out=200):
    """a pea (stand-in when the seed icons are missing)"""
    fill, edge = pr.SEED_COL[color]
    big = 1200
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, R = big / 2, big / 2, big * 0.36
    rng = random.Random(7)
    ph = [rng.uniform(0, 6.28) for _ in range(3)]
    pts = []
    for i in range(180):
        t = 2 * math.pi * i / 180
        r = (R * (1 + 0.035 * math.sin(2 * t + ph[0])) if shape == "round" else
             R * 0.9 * (1 + 0.07 * math.sin(3 * t + ph[0]) + 0.06 * math.sin(5 * t + ph[1])
                        + 0.035 * math.sin(9 * t + ph[2])))
        pts.append((cx + math.cos(t) * r * 1.06, cy + math.sin(t) * r * 0.94))
    d.polygon(pts, fill=fill)
    if shape != "round":
        for _ in range(9):
            a0, r0 = rng.uniform(0, 6.28), rng.uniform(0.15, 0.75) * R
            x, y = cx + math.cos(a0) * r0, cy + math.sin(a0) * r0
            ang, L, ln = rng.uniform(0, 6.28), rng.uniform(0.25, 0.55) * R, []
            for _ in range(12):
                ang += rng.uniform(-0.45, 0.45)
                ln.append((x, y))
                x += math.cos(ang) * L / 11
                y += math.sin(ang) * L / 11
            d.line(ln, fill=pr.mix(fill, edge, 0.95), width=int(big * 0.03), joint="curve")
    d.ellipse((cx - R * 0.55, cy - R * 0.6, cx - R * 0.15, cy - R * 0.3), fill=(255, 255, 240, 160))
    d.line(pts + [pts[0]], fill=pr.OUT, width=int(big * 0.018), joint="curve")
    img = img.crop(img.getbbox())
    return img.resize((out, int(out * img.height / img.width)), Image.LANCZOS)


class Pictures:
    """The plant pictures of one plant style."""

    def __init__(self, style, drawn_traits=False):
        self.style = style
        self.drawn_traits = drawn_traits          # --traits drawn: no icon files for panel c
        self.classic = style == "classic"
        self.painted = "painted" in style
        self.staked = "staked" in style

    def plant(self, age, stage, seed=1003, **tr):
        t = dict(BASE)
        t.update(tr)
        if self.classic:
            return self._classic(stage, t)
        return pr.plant_image(t, seed, age, painterly=self.painted, staked=self.staked, size=512)

    def _classic(self, stage, t):
        if stage == "dead":
            return _icon_named(["dead_64x64.png", "dead.png"], "dead plant")
        p = types.SimpleNamespace(alive=True, stage=int(stage), traits=t, revealed_traits=t,
                                  genotype={}, pods_remaining=5, health=100,
                                  days_since_planting=9)
        path = il.stage_icon_path_for_plant(p)
        want = {1: "seed_yellow_64x64.png", 2: "seedling_64x64.png", 3: "leafy_64x64.png",
                4: "budding_axial_purple_64x64.png", 5: "flower_axial_purple_64x64.png",
                6: "axial_purple-flowers_green-pods_64x64.png",
                7: "axial_purple-flowers_green-pods_64x64.png"}.get(int(stage))
        if not (path and os.path.exists(path)) and want:
            path = os.path.join(il.ICONS_DIR, want)
        im = _icon(path, f"classic stage {stage}", want)
        if im is None:                        # stand-in: the plain drawn plant
            age = {1: 0.0, 2: 4.5, 3: 12, 4: 31.2, 5: 34.5, 6: 40, 7: 52}.get(int(stage), 40)
            im = pr.plant_image(t, 1003, age, painterly=False, size=512)
        return im

    # ----- one flower, bud to seed
    def flower_steps(self):
        """[(name, picture, arrow label to the next one)] — the game's classic
        icons in every plant style (a drawn stand-in only for a missing file)"""
        bud = _icon_named(["bud_purple.png", "bud_purple_64.png", "flower_bud_purple.png"],
                          "bud (classic)")
        fl = _icon(il.trait_icon_path("flower_color", "purple"), "flower colour purple",
                   "flower_color_purple.png")
        if bud is None and fl is not None:      # the game's own way: the flower, faded
            r, g, b, a = fl.split()
            bud = Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * 0.55))))
        pod = _icon(il.pod_shape_icon_path("inflated", "green"), "pod green inflated",
                    "pod_green_inflated_64.png")
        seed = _icon(il.trait_icon_path("seed_color", "yellow"), "seed colour yellow",
                     "seed_color_yellow.png")
        if seed is not None:
            seed.info["scale"] = 0.5
        return [("Bud", bud or organ("bud", g=0.7, painted=False), "3 days"),
                ("Open flower", fl or organ("flower", painted=False), "4 days"),
                ("Pod", pod or organ("pod", painted=False), "ripens"),
                ("Harvested seeds", seed or drawn_seed("yellow"), None)]

    # ----- the Genotype Explorer's trait icons
    def trait_icon(self, trait, value, other=None):
        if self.drawn_traits:
            return self._drawn_trait(trait, value, other)
        p = self.painted
        if trait == "plant_height":
            im = _icon(il.trait_icon_path("plant_height", value), f"plant height {value}",
                       f"plant_height_{value}.png")
            if im is None:
                return self._drawn_pair("plant_height", 1003, ("tall", "dwarf"))[
                    "dwarf" if value in ("short", "dwarf") else "tall"]
            # both icons fill their square: show the dwarf as much smaller as
            # the dwarf plant really is (measured on the plant drawing)
            im.info["rel"] = 1.0 if value == "tall" else self._dwarf_ratio()
            return im
        if trait == "flower_position":
            path = il.flower_icon_path_hi(value, "purple") or il.flower_icon_path(value, "purple") \
                or il.trait_icon_path("flower_position", value)
            im = _icon(path, f"flower position {value}", f"flower_{value}_purple_64x64.png")
            return im or pr.plant_image(dict(BASE, flower_position=value), 1002, 34.5,
                                        painterly=p, size=512)
        if trait == "flower_color":
            im = _icon(il.trait_icon_path("flower_color", value), f"flower colour {value}",
                       f"flower_color_{value}.png")
            return im or organ("flower", _fake(value == "purple"), painted=p, stalk=False)
        if trait in ("pod_color", "pod_shape"):
            col = value if trait == "pod_color" else (other or "green")
            shp = value if trait == "pod_shape" else (other or "inflated")
            im = _icon(il.pod_shape_icon_path(shp, col), f"pod {col} {shp}", f"pod_{col}_{shp}_64.png")
            return im or organ("pod", _fake(pod_yellow=col == "yellow",
                                            constricted=shp == "constricted"), painted=p, stalk=False)
        if trait in ("seed_color", "seed_shape"):
            im = _icon(il.trait_icon_path(trait, value), f"{trait.replace('_', ' ')} {value}",
                       f"{trait}_{value}.png")
            if im is None:
                im = (drawn_seed(value) if trait == "seed_color" else drawn_seed("yellow", value))
            return im
        return None

    def _dwarf_ratio(self):
        hs = []
        for h in ("tall", "dwarf"):
            im = pr.plant_image(dict(BASE, plant_height=h), 1003, 34.5, painterly=False, size=512)
            bb = im.getchannel("A").getbbox()
            hs.append(bb[3] - bb[1])
        return hs[1] / float(hs[0])

    def _drawn_pair(self, key, seed, values):
        """two drawn plants cropped alike, so they keep their true sizes"""
        ims = [pr.plant_image(dict(BASE, **{key: v}), seed, 34.5, painterly=self.painted,
                              staked=self.staked, size=512) for v in values]
        bbs = [im.getchannel("A").getbbox() for im in ims]
        u = (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))
        out = []
        for im in ims:
            im = im.crop(u)
            im.info["keep_frame"] = True
            out.append(im)
        return dict(zip(values, out))

    def _drawn_trait(self, trait, value, other=None):
        p = self.painted
        if trait == "plant_height":
            pair = self._drawn_pair("plant_height", 1003, ("tall", "dwarf"))
            return pair["dwarf" if value in ("short", "dwarf") else "tall"]
        if trait == "flower_position":
            return self._drawn_pair("flower_position", 1002, ("axial", "terminal"))[value]
        if trait == "flower_color":
            return organ("flower", _fake(value == "purple"), painted=p, stalk=False)
        if trait in ("pod_color", "pod_shape"):
            col = value if trait == "pod_color" else (other or "green")
            shp = value if trait == "pod_shape" else (other or "inflated")
            return organ("pod", _fake(pod_yellow=col == "yellow", constricted=shp == "constricted"),
                         painted=p, stalk=False)
        return drawn_seed(value) if trait == "seed_color" else drawn_seed("yellow", value)


# --------------------------------------------------------------------------- panels
SEED_IN_C = 0.5                               # seeds: half the size of the other trait icons


def trait_box():
    """size (inches) of a trait icon in the seven-traits panel"""
    dcw = (W - 0.12 - 0.55) / 7
    return min(dcw * 0.78, 0.72)


def panel_title(L, y, letter, title):
    L.text(0.10, y, letter, F_LETTER, bold=True, ha="left")
    L.text(0.38, y + 0.02, title, F_TITLE, bold=True, ha="left")


def panel_growth(L, y, letter, P):
    panel_title(L, y, letter, "Growth stages of one plant")
    stages = [("Stage 1", "Seed", 0.0, 1), ("Stage 2", "Seedling", 4.5, 2),
              ("Stage 3", "Young plant", 12, 3), ("Stage 4", "Budding", 31.2, 4),
              ("Stage 5", "Flowering", 34.5, 5), ("Stage 6", "Pod\ndevelopment", 40, 6),
              ("Stage 7", "Mature\nseeds", 52, 7),
              ("after 7", "Ageing", 82, "dead" if P.classic else 7)]
    thr = {"Casual": [0, 4, 8, 13, 18, 25, 30], "Moderate": [0, 5, 10, 20, 30, 42, 55],
           "Realistic": [0, 7, 14, 28, 42, 60, 85]}
    death = {"Casual": "dies 60–90", "Moderate": "dies 85–115", "Realistic": "dies 125–160"}
    seen = ["seed\nshape", "–", "plant\nheight", "flower\ncolour,\nposition", "–",
            "pod\ncolour", "pod shape,\nseed\ncolour", "–"]
    x0 = 0.78                     # narrow label column: the plants get the width
    colw = (W - 0.12 - x0) / 8
    pics = [None if st == "dead" else P.plant(age, st) for _, _, age, st in stages]
    if not P.classic:                    # one scale for all: crop them alike
        bbs = [im.getchannel("A").getbbox() for im in pics]
        u = (min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs))
        pics = [im.crop(u) for im in pics]
        imgh = colw * (u[3] - u[1]) / (u[2] - u[0])
    else:
        # classic: every stage picture fills its icon, so each one is scaled to
        # the true height of the plant at that stage (from the plant drawing):
        # the seed a tiny point, the seedling small, the grown plant full size
        imgh = colw * 1.05
        hs = []
        for _, _, age, st in stages:
            ref = pr.plant_image(BASE, 1003, age, painterly=False, size=512)
            bb = ref.getchannel("A").getbbox()
            hs.append((bb[3] - bb[1]) if bb else 0)
        top_h = float(max(hs) or 1)
        rel = [h / top_h for h in hs]
        rel[0] = 0.05                         # the seed: a small point on the ground
        # heights in that relation; if a picture would be too wide for its
        # column, all of them shrink together (so the relation stays)
        boxes = []
        for i, im in enumerate(pics):
            if im is None:
                boxes.append(None)
                continue
            bb = content_bbox(im)
            im = pics[i] = im.crop(bb) if bb else im
            h = imgh * rel[i]
            boxes.append((h * im.width / float(im.height), h))
        g = min([1.0] + [colw * 0.95 / b[0] for b in boxes if b and b[0] > 0])
    ytop = y + 0.32
    for i, (lab, name, _, _) in enumerate(stages):
        cx = x0 + colw * (i + 0.5)
        if pics[i] is not None:
            if P.classic:
                bw, bh_ = boxes[i][0] * g, boxes[i][1] * g
                L.image(cx - bw / 2, ytop + imgh - bh_, bw, bh_, pics[i], "S")
            else:
                L.items.append(dict(k="image", x=cx - colw / 2, y=ytop, w=colw, h=imgh, im=pics[i]))
        yy = ytop + imgh + 0.04
        L.text(cx, yy, lab, F_NOTE, color=MUTED)
        L.text(cx, yy + LH(F_NOTE) + 0.02, name, F_HEAD, bold=True)
    y = ytop + imgh + 0.04 + LH(F_NOTE) + 0.02 + 2 * LH(F_HEAD) + 0.14
    L.line(0.10, y - 0.06, W - 0.10, y - 0.06)
    L.text(0.12, y, "Stage starts on game day", F_NOTE, bold=True, color=MUTED, ha="left")
    y += LH(F_NOTE) + 0.06
    for key in thr:
        L.text(x0 - 0.08, y, key, F_BODY, ha="right")
        for i in range(8):
            L.text(x0 + colw * (i + 0.5), y, f"≥ {thr[key][i]}" if i < 7 else death[key], F_BODY)
        y += LH(F_BODY) + 0.06
    y += LH(F_BODY) * 0.6
    L.text(x0 - 0.08, y, "Trait\nvisible", F_BODY, bold=True, ha="right")
    for i in range(8):
        L.text(x0 + colw * (i + 0.5), y, seen[i], F_BODY)
    return y + 3 * LH(F_BODY) + 0.25


def panel_flower(L, y, letter, P):
    panel_title(L, y, letter, "Each flower, from bud to "
                + "harvest" + ", and what the gardener can do")
    steps = P.flower_steps()
    n = len(steps)
    bx0 = 0.30
    bcw = (W - 0.15 - bx0) / n
    bh = 0.45                                 # the icons at half their former size
    yb = y + 0.42
    for i, (name, im, lab) in enumerate(steps):
        cx = bx0 + bcw * (i + 0.5)
        if name == "Harvested seeds":             # the same size as the seeds in panel c
            sz = trait_box() * SEED_IN_C
            L.image(cx - sz / 2, yb + (bh - sz) / 2, sz, sz, im, "C")
        else:
            L.image(cx - bcw * 0.165, yb, bcw * 0.33, bh, im, "C")
        L.text(cx, yb + bh + 0.06, name, F_HEAD, bold=True)
        if lab:
            L.arrow(cx + bcw * 0.36, cx + bcw * 0.64, yb + bh / 2, lab)
    acts = {0: [("Emasculate\n0–3 % already\nself-pollinated", "emasc")],
            1: [("Emasculate\n5–85 % already\nself-pollinated", "emasc"), ("Pollinate", "poll"),
                ("Collect pollen\nanthers ripe on\n55 % of days", "pollen")],
            n - 1: [("Harvest\n5–8 seeds\nper pod", "harv")]}
    ych = yb + bh + 0.06 + LH(F_HEAD) + 0.14
    for i in range(n):
        cx = bx0 + bcw * (i + 0.5)
        a = acts.get(i)
        if not a:
            L.text(cx, ych, "seeds develop", F_NOTE, color=MUTED, italic=True)
            continue
        yy = ych
        for s, k in a:
            L.text(cx, yy, s, F_NOTE, bg=CHIP[k])
            yy += n_lines(s) * LH(F_NOTE) + 0.14
    y = ych + 7 * LH(F_NOTE) + 3 * 0.14 + 0.08
    note = wrap("Durations are for flowers that form later on a ripe plant; a plant's first flowers "
                "follow its growth stages 4–7. The longer a flower has been open, the more it has "
                "already self-pollinated.", W - 0.6, F_NOTE)
    L.text(0.38, y, note, F_NOTE, color=MUTED, ha="left")
    return y + n_lines(note) * LH(F_NOTE) + 0.25


def panel_traits(L, y, letter, P):
    panel_title(L, y, letter, "The seven characters Mendel studied: dominant (top) and recessive (bottom)")
    traits = [("Plant\nheight", "Le / le", "stage 3", ("plant_height", "tall", "tall"),
               ("plant_height", "short", "dwarf")),
              ("Flower\nposition", "Fa / fa", "stage 4", ("flower_position", "axial", "axial"),
               ("flower_position", "terminal", "terminal")),
              ("Flower\ncolour", "A / a", "stage 4", ("flower_color", "purple", "purple"),
               ("flower_color", "white", "white")),
              ("Pod\ncolour", "Gp / gp", "stage 6", ("pod_color", "green", "green"),
               ("pod_color", "yellow", "yellow")),
              ("Pod\nshape", "P / p", "stage 7", ("pod_shape", "inflated", "inflated"),
               ("pod_shape", "constricted", "constricted")),
              ("Seed\ncolour", "I / i", "stage 7", ("seed_color", "yellow", "yellow"),
               ("seed_color", "green", "green")),
              ("Seed\nshape", "R / r", "seen on the seed", ("seed_shape", "round", "round"),
               ("seed_shape", "wrinkled", "wrinkled"))]
    dx0 = 0.55
    dcw = (W - 0.12 - dx0) / 7
    yh = y + 0.40
    for i, (name, al, st, _, _) in enumerate(traits):
        cx = dx0 + dcw * (i + 0.5)
        L.text(cx, yh, name, F_HEAD, bold=True)
        L.text(cx, yh + 2 * LH(F_HEAD) + 0.03, al, F_BODY, color=MUTED)
        L.text(cx, yh + 2 * LH(F_HEAD) + 0.03 + LH(F_BODY), st, F_NOTE, color=MUTED)
    box = trait_box()                         # one size for every icon, as in the Explorer
    yd = yh + 2 * LH(F_HEAD) + 2 * LH(F_BODY) + 0.16
    for r in range(2):
        yy = yd + r * (box + 0.34)
        for i, t in enumerate(traits):
            trait, value, label = t[3 + r]
            cx = dx0 + dcw * (i + 0.5)
            pic = P.trait_icon(trait, value)
            rel = pic.info.get("rel") if pic is not None else None
            if rel:                                   # plant height icons: true sizes, one baseline
                L.image(cx - box / 2, yy + box * (1 - rel), box, box * rel, pic, "S")
            else:
                f = SEED_IN_C if trait.startswith("seed") else 1.0     # seeds at half size
                L.image(cx - box * f / 2, yy + box * (1 - f) / 2, box * f, box * f, pic,
                        "S" if pic is not None and pic.info.get("keep_frame") else "C")
            L.text(cx, yy + box + 0.04, label, F_BODY)
        L.text(0.30, yy + box / 2, "dominant" if r == 0 else "recessive", F_NOTE, color=MUTED, rot=90)
    return yd + 2 * box + 0.34 + 0.04 + LH(F_BODY) + 0.22


def panel_water(L, y, letter, P):
    panel_title(L, y, letter, "Soil water: the drop icon on every plot")
    wx, yy = 0.45, y + 0.45
    for col, name, rng, eff in WATER_BANDS:
        # the game's drop (tile.py _teardrop_points): a round bulb with a point on top
        cx, cy, r = wx + 0.06, yy + 0.10, 0.055
        gap = math.radians(35)
        pts = []
        for k in range(25):
            t = math.pi / 2 + gap + (2 * math.pi - 2 * gap) * k / 24
            pts.append((cx + r * math.cos(t), cy - r * math.sin(t)))
        pts.append((cx, cy - 2.0 * r))
        L.polygon(pts, col)
        L.text(wx + 0.24, yy, name, F_BODY, bold=True, ha="left")
        L.text(wx + 1.30, yy, rng, F_BODY, color=MUTED, ha="left")
        L.text(wx + 2.00, yy, eff, F_BODY, ha="left")
        yy += 0.24
    notes = ["Watering adds 30 %.", "Watering at noon or in the afternoon stresses the plant.",
             "Sun and warmth dry the soil, rain wets it.", "Weak plants dry out 1.5 times faster.",
             "Ageing (senescent), weak and late-season plants no longer regain health."]
    nx, yn = 4.15, y + 0.45
    for s in notes:
        t = wrap("• " + s, W - 0.15 - nx, F_BODY)
        L.text(nx, yn, t, F_BODY, ha="left")
        yn += n_lines(t) * LH(F_BODY) + 0.07
    return max(yy, yn) + 0.20


def panel_season(L, y, letter, P):
    panel_title(L, y, letter, "Ageing and season on the three difficulty levels")
    cols = ["Lifespan and ageing", "Sowing", "Weather and season", "Autumn"]
    rows = [("Casual",
             "Dies at day 60–90. Ageing in the last 10 days: health −2 per day, after that −8 to −15 per day.",
             "Any time of year.", "No season model: only water and weather.", "No autumn decline."),
            ("Moderate",
             "Dies at day 85–115. Ageing starts once the plant's heat sum (degree days) is reached; "
             "it then dies within 30–50 days.",
             "Season model: open March–May; otherwise blocked by the frost window, cold soil or summer heat.",
             "Frost and heat stress (noon ≥ 34 °C) cost health, at most −12 per day.",
             "No autumn decline."),
            ("Realistic", "Dies at day 125–160. Ageing as on Moderate.",
             "As Moderate. Sowing takes time (15 min per seed).",
             "As Moderate. 7 % of seeds do not sprout, 3 % of plants set no pods.",
             "From 15 Sep health falls: −1 to −3 per day, Oct −5 to −8, Nov −10 to −15, "
             "Dec −20 to −30; all plants die in January.")]
    ex0 = 1.10
    ecw = (W - 0.12 - ex0) / 4
    yy = y + 0.42
    for j, c in enumerate(cols):
        L.text(ex0 + ecw * j, yy, c, F_HEAD, bold=True, ha="left")
    yy += LH(F_HEAD) + 0.12
    for r, row in enumerate(rows):
        if r:
            L.line(0.38, yy - 0.07, W - 0.10, yy - 0.07)
        L.text(0.38, yy, row[0], F_HEAD, bold=True, ha="left")
        n = 1
        for j, cell in enumerate(row[1:]):
            t = wrap(cell, ecw - 0.12, F_BODY)
            L.text(ex0 + ecw * j, yy, t, F_BODY, ha="left")
            n = max(n, n_lines(t))
        yy += n * LH(F_BODY) + 0.16
    return yy


def build(panels, P):
    L = Layout()
    y = 0.10
    for i, (fn, letter) in enumerate(panels):
        if i:
            L.line(0.10, y - 0.08, W - 0.10, y - 0.08)
        y = fn(L, y, letter, P)
    L.height = y + 0.02
    return L


# --------------------------------------------------------------------------- main
def settings_style():
    try:
        with open(os.path.join(HERE, "mendel_garden_display_settings.json"), encoding="utf-8") as f:
            v = json.load(f).get("plant_style")
        return v if v in STYLES else "grown"
    except Exception:
        return "grown"


def write_file(path, data):
    """Writes the finished file. If Windows will not let us replace the old
    one (open in PowerPoint or a picture viewer, or a OneDrive file that is
    only in the cloud), the new one gets a free name instead: ..._2.png etc.
    Returns the path written, or None."""
    stem, ext = os.path.splitext(path)
    for k in range(0, 50):
        p = path if k == 0 else f"{stem}_{k + 1}{ext}"
        try:
            with open(p, "wb") as f:
                f.write(data)
            if k:
                print(f"  ({os.path.basename(path)} could not be replaced — is it open in "
                      f"another program? Saved as {os.path.basename(p)})")
            return p
        except OSError as e:
            last = e
            continue
    print(f"  Could not write {path}: {last}")
    return None


def make(style, out_dir, dpi, drawn_traits=False):
    P = Pictures(style, drawn_traits)
    figs = [("plants", build([(panel_growth, "a"), (panel_flower, "b"), (panel_traits, "c")], P)),
            ("care", build([(panel_water, "a"), (panel_season, "b")], P))]
    for name, L in figs:
        path = os.path.join(out_dir, f"pea_figure_{name}_{style}.png")
        path = L.save_png(path, dpi)
        if path:
            print(f"  {path}   ({W * 25.4:.0f} x {L.height * 25.4:.0f} mm)")
    try:
        from pptx import Presentation
        from pptx.util import Inches
    except ImportError:
        print("  (no PowerPoint file: python-pptx is not installed —  pip install python-pptx)")
        return
    for name, L in figs:                 # one file per figure, the slide as big as the figure
        prs = Presentation()
        prs.slide_width = Inches(W)
        prs.slide_height = Inches(L.height)
        L.add_slide(prs)
        buf = io.BytesIO()
        prs.save(buf)
        path = write_file(os.path.join(out_dir, f"pea_figure_{name}_{style}.pptx"), buf.getvalue())
        if path:
            print(f"  {path}")


def main():
    ap = argparse.ArgumentParser(description="Figures of the pea plants in Garden of Inheritance.")
    ap.add_argument("--style", default=None,
                    help="classic, grown, grown_painted, grown_staked, grown_staked_painted or all "
                         "(default: the plant style chosen in the game)")
    ap.add_argument("--out", default=os.path.join(HERE, "figures"), help="output folder")
    ap.add_argument("--dpi", type=int, default=600, help="PNG resolution (default 600)")
    ap.add_argument("--traits", choices=("icons", "drawn"), default="icons",
                    help="pictures of the seven traits: the game's icons (default) or drawn "
                         "by the plant drawing (sharp at any size)")
    a = ap.parse_args()
    style = a.style or settings_style()
    styles = STYLES if style == "all" else (style,)
    for s in styles:
        if s not in STYLES:
            ap.error(f"unknown style {s!r}; choose from {', '.join(STYLES)} or all")
    os.makedirs(a.out, exist_ok=True)
    for s in styles:
        print(f"Plant style: {s}")
        MISSING.clear()
        make(s, a.out, a.dpi, a.traits == "drawn")
        if MISSING:
            print("  Icons not found (a drawn picture was used instead):")
            for m in sorted(set(MISSING)):
                print("    -", m)


if __name__ == "__main__":
    main()
