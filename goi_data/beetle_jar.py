"""
A glass jar with the pea weevils the player has caught, crawling about
inside it (beetle_jar.BeetleJar, a tk.Canvas).

Each beetle walks, turns and rests on its own (its own pace, size, way of
turning and resting), so no two of them move alike. The jar is drawn with
PIL: the back of the glass behind the beetles, the shine and the rim in
front of them, so they seem to be inside.
"""

import math
import os
import random
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
except Exception:          # (no PIL: an empty canvas)
    Image = None

STEP_MS = 50                 # one animation step
ANGLE_STEP = 15              # beetle pictures are turned in 15° steps
MAX_SHOWN = 30               # more beetles than this: the jar shows 30


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _fallback_beetle(size=24):
    """A small beetle drawn here (head up), if there is no picture."""
    k = 4
    S = size * k
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    leg = (60, 40, 25, 255)
    for i, y in enumerate((0.42, 0.55, 0.68)):
        for sx in (-1, 1):
            x0 = S / 2 + sx * S * 0.16
            d.line([(x0, S * y), (x0 + sx * S * 0.2, S * (y + 0.06 * (i - 1)))],
                   fill=leg, width=k * 2)
    d.line([(S * 0.45, S * 0.24), (S * 0.32, S * 0.06)], fill=leg, width=k * 2)
    d.line([(S * 0.55, S * 0.24), (S * 0.68, S * 0.06)], fill=leg, width=k * 2)
    d.ellipse([S * 0.34, S * 0.30, S * 0.66, S * 0.86], fill=(120, 80, 40, 255),
              outline=(70, 45, 20, 255), width=k)
    d.ellipse([S * 0.40, S * 0.18, S * 0.60, S * 0.34], fill=(90, 60, 30, 255))
    for (x, y) in ((0.45, 0.5), (0.56, 0.62), (0.47, 0.72), (0.55, 0.45)):
        d.ellipse([S * x - k * 2, S * y - k * 2, S * x + k * 2, S * y + k * 2],
                  fill=(230, 210, 170, 255))
    return im.resize((size, size), Image.LANCZOS)


def load_beetle(path=None):
    """The weevil's picture (PIL, RGBA, cropped) and the direction its head
    points in the picture (0 = up, 90 = right)."""
    im = None
    if Image is None:
        return None, 0
    try:
        if path and os.path.exists(path):
            im = Image.open(path).convert("RGBA")
            bb = im.getbbox()
            if bb:
                im = im.crop(bb)
    except Exception:
        im = None
    if im is None or min(im.size) < 2:
        return _fallback_beetle(), 0
    # (a picture wider than tall is taken to face right)
    return im, (90 if im.width > im.height * 1.2 else 0)


def jar_images(w, h, bg):
    """(back, front): the glass behind the beetles and the shine, rim and
    lid in front of them, both RGBA of size (w, h)."""
    k = 3
    W, H = w * k, h * k
    body = (int(W * 0.08), int(H * 0.20), int(W * 0.92), int(H * 0.97))
    r = int(W * 0.16)
    back = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(back)
    # soft shadow on the ground
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([body[0] + W * 0.04, H * 0.92, body[2] - W * 0.04, H * 1.0],
                               fill=(60, 45, 25, 70))
    back.alpha_composite(sh.filter(ImageFilter.GaussianBlur(k * 3)))
    # the glass: a faint green-blue tint, a little darker at the bottom
    d.rounded_rectangle(body, radius=r, fill=(205, 226, 224, 120))
    d.rounded_rectangle((body[0], int(H * 0.86), body[2], body[3]), radius=r,
                        fill=(180, 205, 200, 110))
    # a few grains of soil and a pea leaf on the floor
    rnd = random.Random(7)
    for _ in range(26):
        x = rnd.uniform(body[0] + r * 0.6, body[2] - r * 0.6)
        y = rnd.uniform(H * 0.90, body[3] - k * 4)
        s = rnd.uniform(k * 1.5, k * 3.5)
        d.ellipse([x - s, y - s * 0.7, x + s, y + s * 0.7],
                  fill=rnd.choice([(120, 90, 55, 200), (95, 70, 40, 200), (140, 110, 70, 190)]))
    d.ellipse([W * 0.52, H * 0.86, W * 0.78, H * 0.93], fill=(110, 150, 70, 220))
    d.line([(W * 0.53, H * 0.895), (W * 0.77, H * 0.895)], fill=(80, 120, 50, 230), width=k)

    front = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = ImageDraw.Draw(front)
    # the glass's edge
    f.rounded_rectangle(body, radius=r, outline=(120, 150, 150, 230), width=k * 2)
    # shine: a long stripe on the left, a short one on the right
    f.rounded_rectangle((body[0] + W * 0.07, body[1] + H * 0.08, body[0] + W * 0.12,
                         body[3] - H * 0.14), radius=k * 4, fill=(255, 255, 255, 120))
    f.rounded_rectangle((body[2] - W * 0.12, body[1] + H * 0.10, body[2] - W * 0.09,
                         body[1] + H * 0.30), radius=k * 3, fill=(255, 255, 255, 90))
    # the neck and its rim
    neck = (int(W * 0.20), int(H * 0.11), int(W * 0.80), int(H * 0.21))
    f.rounded_rectangle(neck, radius=k * 5, fill=(214, 232, 230, 170),
                        outline=(120, 150, 150, 230), width=k * 2)
    # the cork
    cork = (int(W * 0.24), int(H * 0.01), int(W * 0.76), int(H * 0.13))
    f.rounded_rectangle(cork, radius=k * 6, fill=(190, 140, 85, 255),
                        outline=(125, 85, 45, 255), width=k * 2)
    for _ in range(18):
        x = rnd.uniform(cork[0] + k * 6, cork[2] - k * 6)
        y = rnd.uniform(cork[1] + k * 4, cork[3] - k * 4)
        f.ellipse([x - k, y - k, x + k, y + k], fill=(150, 105, 60, 255))
    f.line([(cork[0] + k * 6, cork[1] + k * 5), (cork[2] - k * 6, cork[1] + k * 5)],
           fill=(215, 170, 115, 255), width=k * 2)
    back = back.resize((w, h), Image.LANCZOS)
    front = front.resize((w, h), Image.LANCZOS)
    return back, front


class _Beetle:
    """One weevil: where it is, where it heads, how it likes to move."""

    def __init__(self, rnd, box):
        x0, y0, x1, y1 = box
        self.x = rnd.uniform(x0, x1)
        self.y = rnd.uniform(y0 + (y1 - y0) * 0.35, y1)     # most start low
        self.heading = rnd.uniform(0, 360)
        self.size = rnd.uniform(0.82, 1.18)                 # not all the same size
        self.speed = rnd.uniform(0.35, 1.25)                # px per step
        self.wiggle = rnd.uniform(4.0, 16.0)                # how much it wavers
        self.rest_bias = rnd.uniform(0.3, 1.0)              # how lazy it is
        self.mirror = rnd.random() < 0.5
        self.state = "rest" if rnd.random() < 0.5 else "walk"
        self.left = rnd.randint(5, 60)                      # steps left in this state
        self.turn = 0.0
        self.item = None
        self.shown = None


class BeetleJar(tk.Canvas):
    """The jar with `count` weevils in it (at most MAX_SHOWN are drawn)."""

    def __init__(self, parent, count=1, sprite_path=None, bg="#f5f0e6", width=150,
                 height=190, beetle_px=None, seed=None, **kw):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0,
                         bd=0, **kw)
        self._jw, self._jh = width, height
        self._bg = bg
        self._rnd = random.Random(seed)
        self._job = None
        self._imgs = {}
        self._beetles = []
        if Image is None:
            return
        back, front = jar_images(width, height, bg)
        self._back = ImageTk.PhotoImage(back)
        self._front = ImageTk.PhotoImage(front)
        self.create_image(0, 0, image=self._back, anchor="nw", tags="back")
        self._sprite, self._face = load_beetle(sprite_path)
        self._bpx = int(beetle_px or max(14, min(30, width * 0.16)))
        # where a beetle may be (inside the glass)
        self._box = (width * 0.20, height * 0.30, width * 0.80, height * 0.90)
        self.set_count(count)
        self.create_image(0, 0, image=self._front, anchor="nw", tags="front")
        self.bind("<Destroy>", self._stop, add="+")
        self._job = self.after(STEP_MS, self._step)

    # -- pictures --------------------------------------------------------
    def _img(self, size_k, angle, mirror):
        """The beetle turned to `angle` (degrees, 0 = head up, clockwise)."""
        sk = round(size_k * 10) / 10.0
        a = int(round(angle / ANGLE_STEP) * ANGLE_STEP) % 360
        key = (sk, a, mirror)
        im = self._imgs.get(key)
        if im is None:
            src = self._sprite
            px = max(8, int(self._bpx * sk))
            s = px / float(max(src.width, src.height))
            pil = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))),
                             Image.LANCZOS if s < 2 else Image.NEAREST)
            if mirror:
                pil = pil.transpose(Image.FLIP_LEFT_RIGHT)
            # (PIL turns counter-clockwise; the picture's own facing first)
            pil = pil.rotate(-(a - self._face), resample=Image.BICUBIC, expand=True)
            im = ImageTk.PhotoImage(pil)
            self._imgs[key] = im
        return im

    # -- the beetles -----------------------------------------------------
    def set_count(self, count):
        n = max(0, min(MAX_SHOWN, int(count or 0)))
        while len(self._beetles) > n:
            b = self._beetles.pop()
            if b.item is not None:
                self.delete(b.item)
        while len(self._beetles) < n:
            b = _Beetle(self._rnd, self._box)
            b.item = self.create_image(b.x, b.y, image=self._img(b.size, b.heading, b.mirror),
                                       tags="beetle")
            self._beetles.append(b)
        try:
            self.tag_raise("front")
        except Exception:
            pass

    def _step(self):
        self._job = None
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        rnd = self._rnd
        x0, y0, x1, y1 = self._box
        for b in self._beetles:
            b.left -= 1
            if b.state == "rest":
                if b.left <= 0:
                    b.state, b.left = "walk", rnd.randint(15, 90)
                    b.turn = rnd.uniform(-1, 1) * b.wiggle
                elif rnd.random() < 0.04:
                    b.heading += rnd.uniform(-25, 25)        # looks round a little
            else:
                if b.left <= 0:
                    b.state = "rest"
                    b.left = int(rnd.randint(10, 70) * (0.5 + b.rest_bias))
                else:
                    if rnd.random() < 0.08:
                        b.turn = rnd.uniform(-1, 1) * b.wiggle
                    b.heading += b.turn * 0.35
                    rad = math.radians(b.heading)
                    nx = b.x + math.sin(rad) * b.speed
                    ny = b.y - math.cos(rad) * b.speed
                    # at the glass: turn back towards the middle
                    if not (x0 <= nx <= x1 and y0 <= ny <= y1):
                        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                        want = math.degrees(math.atan2(cx - b.x, -(cy - b.y)))
                        b.heading = want + rnd.uniform(-50, 50)
                        nx = min(x1, max(x0, nx))
                        ny = min(y1, max(y0, ny))
                    b.x, b.y = nx, ny
            shown = (round(b.x), round(b.y),
                     int(round(b.heading / ANGLE_STEP)) % (360 // ANGLE_STEP))
            if shown != b.shown:
                b.shown = shown
                try:
                    self.coords(b.item, b.x, b.y)
                    self.itemconfigure(b.item, image=self._img(b.size, b.heading, b.mirror))
                except Exception:
                    pass
        self._job = self.after(STEP_MS, self._step)

    def _stop(self, e=None):
        if e is not None and e.widget is not self:
            return
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None


def jar_icon(count, sprite_path=None, bg="#f5f0e6", w=34, h=44, seed=3):
    """A small still picture of the jar (PIL, RGB on `bg`) with a few of the
    caught weevils in it — for a button."""
    if Image is None:
        return None
    k = 3
    back, front = jar_images(w * k, h * k, bg)
    im = Image.new("RGBA", back.size, _hex(bg) + (255,))
    im.alpha_composite(back)
    sprite, face = load_beetle(sprite_path)
    rnd = random.Random(seed)
    n = max(0, min(6, int(count or 0)))
    W, H = back.size
    for i in range(n):
        px = int(W * rnd.uniform(0.20, 0.30))
        s = px / float(max(sprite.width, sprite.height))
        b = sprite.resize((max(1, int(sprite.width * s)), max(1, int(sprite.height * s))),
                          Image.LANCZOS)
        b = b.rotate(-(rnd.uniform(0, 360) - face), resample=Image.BICUBIC, expand=True)
        x = int(rnd.uniform(W * 0.22, W * 0.78 - b.width))
        y = int(rnd.uniform(H * 0.40, H * 0.90 - b.height))
        im.alpha_composite(b, (max(0, x), max(0, y)))
    im.alpha_composite(front)
    return im.resize((w, h), Image.LANCZOS).convert("RGB")
