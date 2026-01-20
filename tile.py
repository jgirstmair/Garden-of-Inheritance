import tkinter as tk

from plant import Plant

def lerp(a, b, t):
    return int(a + (b - a) * t)

def lerp_color(c1, c2, t):
    return "#{:02x}{:02x}{:02x}".format(
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
    )

# Color anchors (RGB)
RED    = (220,  53,  69)
YELLOW = (255, 193,   7)
GREEN  = ( 40, 167,  69)

BLUE_LIGHT = (222, 235, 247)
BLUE_DARK  = ( 33, 113, 181)

class TileCanvas(tk.Canvas):
    def __init__(self, parent, idx, app, soil_color, plant: Plant, configs, selected: bool=False):
        self.configs = configs
        self.idx = idx
        self.app = app
        self.soil: str = soil_color
        self.plant: Plant = plant
        
        self.w = configs['TILE_SIZE']

        # unified padding, but separate thicknesses for water + health
        self.bar_pad      = int(configs.get("BAR_PAD", 3))
        self.water_thick  = int(configs.get("WATER_BAR_W", max(4, self.w // 8)))
        self.health_thick = int(configs.get("HEALTH_BAR_H", max(3, self.w // 14)))

        # push the bottom UI stack down a bit (label + health bar feel lower)
        self.bottom_shift = int(configs.get("BOTTOM_SHIFT", 4))  # try 3..8

        # Reserve extra space below the icon area for label + health bar
        self.label_h = self.configs.get("LABEL_H", 14)  # space for "free/#id/dead"
        self.hb_h = self.health_thick

        self.h = self.w

        self.selected = selected
        
        super().__init__(
            parent,
            width=self.w,
            height=self.h,
            bg=self.soil,
            highlightthickness=4,
            highlightbackground="gray",
            bd=0,
            relief="flat"
        )

        # 1) Explicit Background Rectangle (no harsh outline)
        self.bg_rect = self.create_rectangle(
            0, 0, self.w, self.h,
            fill=self.soil,
            outline="", width=0,
            tags="bg"
        )

        # 2) Water Bar Group (no border rectangle; just a fill bar)
        wb_w = self.water_thick

        wb_min_y = self.bar_pad
        wb_max_y = self.w - self.bar_pad

        # Optional: a subtle "slot" behind the fill (still no outline)
        self.wb_bg = self.create_rectangle(
            self.bar_pad, wb_min_y, wb_w, wb_max_y,
            fill=self.soil,
            outline="", width=0,
            tags="water_items"
        )

        # Dynamic Fill (the actual water level)
        self.wb_fill = self.create_rectangle(
            self.bar_pad, wb_min_y, wb_w, wb_max_y,
            fill="blue",
            outline="", width=0,
            tags="water_items"
        )

        # Health bar at bottom (inside square) — same pad logic
        self.hb_y_end = self.w - self.bar_pad
        self.hb_y_start = self.hb_y_end - self.hb_h

        # shift the entire bottom stack DOWN (without resizing the tile)
        self.hb_y_start += self.bottom_shift
        self.hb_y_end   += self.bottom_shift

        # Slot behind fill (optional)
        self.hb_bg = self.create_rectangle(
            self.bar_pad, self.hb_y_start, self.w - self.bar_pad, self.hb_y_end,
            fill=self.soil, outline="", width=0,
            tags="health_items"
        )

        # Dynamic fill
        self.hb_fill = self.create_rectangle(
            self.bar_pad, self.hb_y_start, self.w - self.bar_pad, self.hb_y_end,
            fill="green", outline="", width=0,
            tags="health_items"
        )

        # Plant icon vertical tuning
        icon_lift = max(6, self.w // 14)      # upward bias
        icon_drop = int(self.configs.get("ICON_DROP", 3))  # positive = move DOWN

        self.img_item = self.create_image(
            self.w // 2 + wb_w // 2,
            self.w // 2 - (self.health_thick // 2) - icon_lift + icon_drop,
            image=None,
            tags="plant_img"
        )

        # Label INSIDE the square, with breathing room above the health bar
        self.label_pad = int(self.configs.get("LABEL_PAD", 0))

        # keep label clearly separated from the slim health bar
        label_gap = max(6, self.health_thick // 2)

        label_y = int(
            self.hb_y_start
            - label_gap
            - (self.label_h / 2)
            + self.label_pad
            + 6    # ← push text down (try 2–6)
        )

        self.label_item = self.create_text(
            self.w // 2 + wb_w // 2,
            label_y,
            text="",
            font=("Segoe UI", 9, "bold"),
            fill="#1f1f1f",
            tags=("tile_label",)
        )

        # Cache an "empty tile" icon (optional; only if file exists)
        self.empty_img = None
        try:
            self.empty_img = tk.PhotoImage(file=self.configs.get("EMPTY_ICON_PATH", "icons/empty.png"))
        except Exception:
            self.empty_img = None

        # Cache a "dead plant" icon (optional; only if file exists)
        self.dead_img = None
        try:
            self.dead_img = tk.PhotoImage(file=self.configs.get("DEAD_ICON_PATH", "icons/dead.png"))
        except Exception:
            self.dead_img = None

        # 5) Badges (P/E) — positioned relative to bar geometry
        self.badge_size = 18   # close to v1.8 label feel
        self.badge_y = 4       # v1.8 used y=4
        self.p_inset_right = 2 # v1.8 x=-4 at NE corner
        self.e_overhang_left = 0  # v1.8 x=-6 at NW corner

        # The "plant plot" starts right after the water bar.
        self.plot_x0 = wb_w
        self.plot_x1 = self.w

        # P badge: top-right of plant plot
        p_x = self.plot_x1 - self.p_inset_right - self.badge_size
        p_y = self.badge_y

        # "!" badge: same position as P (used to indicate collectable pollen today)
        bang_x = p_x
        bang_y = p_y

        # E badge: top-left of plant plot (slightly overhanging left like v1.8)
        e_x = self.plot_x0 - self.e_overhang_left
        e_y = self.badge_y

        self._draw_badge_v18(p_x, p_y, "P", bg="#FFD54F", fg="#000000", tag="p_badge")
        self._draw_badge_v18(e_x, e_y, "E", bg="#BBDEFB", fg="#0D47A1", tag="e_badge")
        self._draw_badge_v18(bang_x, bang_y, "!", bg="#FFCDD2", fg="#B71C1C", tag="bang_badge")



        # Bind mouse events (this is what makes selection work)
        self._set_bindings()

        # Initial render
        self.render()

    def set_soil_color(self, soil_hex: str):
        self.soil = soil_hex

        # Main tile background
        try:
            self.itemconfigure(self.bg_rect, fill=soil_hex)
        except Exception:
            pass

        # Bar background slots (water + health)
        try:
            if hasattr(self, "wb_bg"):
                self.itemconfigure(self.wb_bg, fill=soil_hex)
            if hasattr(self, "hb_bg"):
                self.itemconfigure(self.hb_bg, fill=soil_hex)
        except Exception:
            pass

        # Canvas background
        try:
            self.configure(bg=soil_hex)
        except Exception:
            pass

        # Keep selection border logic intact
        try:
            if not self.selected:
                self.config(highlightbackground=soil_hex, highlightcolor=soil_hex)
        except Exception:
            pass

    def _draw_badge_v18(self, x, y, char, bg, fg, tag):
        s = self.badge_size

        # Flat square badge (like v1.8 tk.Label: bd=0, relief='flat')
        self.create_rectangle(
            x, y, x + s, y + s,
            fill=bg,
            outline="",
            width=0,
            tags=(tag, "badge_group")
        )

        self.create_text(
            x + s/2, y + s/2,
            text=char,
            font=("Arial", 12, "bold"),
            fill=fg,
            tags=(tag, "badge_group")
        )

    def _set_bindings(self):
        self.bind("<Button-1>",        lambda e: self.app._on_tile_left_press(e, self.idx))
        self.bind("<B1-Motion>",       self.app._on_drag_motion)
        self.bind("<ButtonRelease-1>", lambda e: self.app._on_tile_left_release(e, self.idx))
        self.bind("<Button-3>",        lambda e: self.app._on_tile_right_click(self, e))
        self.bind("<Button-2>",        lambda e: self.app._on_tile_right_click(self, e))
        self.bind("<Double-Button-1>", lambda e: self.app._on_tile_double_click(e, self.idx))

    def render(self):
        """Render tile like v1.12: free/dead/#id + correct icons, badges, and hidden bars for empty/dead."""

        # selection border (keep your existing style)
        try:
            self.config(
                highlightbackground="darkorange" if self.selected else self.soil,
                highlightcolor="darkorange" if self.selected else self.soil
            )
        except Exception:
            pass

        # Always start by hiding bars + badges (v1.12 "persistent reset" idea)
        try:
            self.itemconfig("water_items", state="hidden")
            self.itemconfig("health_items", state="hidden")
            self.itemconfig("badge_group", state="hidden")
        except Exception:
            pass

        # --- EMPTY ---
        if self.plant is None:
            # label
            try:
                self.itemconfig(self.label_item, text="free", state="normal")
            except Exception:
                pass

            # icon
            if getattr(self, "empty_img", None) is not None:
                try:
                    self.itemconfig("plant_img", state="normal")
                    self.itemconfig(self.img_item, image=self.empty_img)
                except Exception:
                    pass
            else:
                try:
                    self.itemconfig("plant_img", state="hidden")
                except Exception:
                    pass
            return

        # --- DEAD ---
        if not getattr(self.plant, "alive", True):
            # label
            try:
                self.itemconfig(self.label_item, text="dead", state="normal")
            except Exception:
                pass

            # dead icon if you have it; else hide
            dead_img = getattr(self, "dead_img", None)
            if dead_img is not None:
                try:
                    self.itemconfig("plant_img", state="normal")
                    self.itemconfig(self.img_item, image=dead_img)
                except Exception:
                    pass
            else:
                try:
                    self.itemconfig("plant_img", state="hidden")
                except Exception:
                    pass
            return

        # --- ALIVE ---
        try:
            self.itemconfig(self.label_item, text=f"#{getattr(self.plant, 'id', '')}", state="normal")
        except Exception:
            pass

        # show bars
        try:
            self.itemconfig("water_items", state="normal")
            self.itemconfig("health_items", state="normal")
            self.itemconfig("plant_img", state="normal")
        except Exception:
            pass

        # update bars
        try:
            self.update_health(getattr(self.plant, "health", 100))
        except Exception:
            pass
        try:
            self.update_water(getattr(self.plant, "water", 0))
        except Exception:
            pass

        # badges
        # - P: plant has a pending cross / pollinated
        # - E: emasculated
        # - !: inspected today and mature anthers are available to collect (same position as P)
        try:
            has_pending = bool(getattr(self.plant, "pending_cross", False))
        except Exception:
            has_pending = False

        # Always prefer showing "P" over "!" if both would apply
        try:
            self.itemconfig("p_badge", state="normal" if has_pending else "hidden")
        except Exception:
            pass

        # Exclamation badge: only for *today* (stale pollen warning disappears automatically)
        try:
            today = None
            try:
                today = int(getattr(self.app, "_today", lambda: 0)())
            except Exception:
                today = None
            inspected_today = (getattr(self.plant, "last_anther_check_day", None) == today)
            anthers_ok = bool(getattr(self.plant, "anthers_available_today", False))
            show_bang = (not has_pending) and inspected_today and anthers_ok

            # If the day has changed, force-clear any leftover availability
            if (today is not None) and (getattr(self.plant, "last_anther_check_day", None) not in (None, today)):
                try:
                    self.plant.anthers_available_today = False
                except Exception:
                    pass
                show_bang = False

            self.itemconfig("bang_badge", state="normal" if show_bang else "hidden")
        except Exception:
            try:
                self.itemconfig("bang_badge", state="hidden")
            except Exception:
                pass
        try:
            self.itemconfig("e_badge", state="normal" if getattr(self.plant, "emasculated", False) else "hidden")
        except Exception:
            pass

        # plant icon
        try:
            img_obj = getattr(self.plant, "img_obj", None)
            if img_obj is not None:
                self.itemconfig(self.img_item, image=img_obj)
            else:
                # if no icon available, at least don't show stale empty/dead
                self.itemconfig(self.img_item, image="")
        except Exception:
            pass

    def update_health(self, percent):
        percent = max(0, min(100, percent))
        pad = self.bar_pad

        # width inside padding on both sides
        max_w = (self.w - pad) - pad
        new_x1 = pad + (max_w * (percent / 100))

        y0 = self.hb_y_start
        y1 = self.hb_y_end
        self.coords(self.hb_fill, pad, y0, new_x1, y1)

        t = percent / 100
        if t < 0.5:
            color = lerp_color(RED, YELLOW, t * 2)
        else:
            color = lerp_color(YELLOW, GREEN, (t - 0.5) * 2)

        self.itemconfig(self.hb_fill, fill=color)

    def update_water(self, percent):
        percent = max(0, min(100, percent))
        pad = self.bar_pad

        wb_min_y = pad
        wb_max_y = self.w - pad
        total_height = wb_max_y - wb_min_y

        new_y0 = wb_max_y - (total_height * (percent / 100))
        self.coords(
            self.wb_fill,
            pad,
            new_y0,
            self.water_thick,
            wb_max_y
        )

        color = lerp_color(BLUE_LIGHT, BLUE_DARK, percent / 100)
        self.itemconfig(self.wb_fill, fill=color)





