"""
Tile Canvas Module

Provides the TileCanvas widget for displaying individual garden plots.
Each tile shows a plant's icon, health bar, water bar, and status badges.
"""

import tkinter as tk
from plant import Plant


# ============================================================================
# Color Utilities
# ============================================================================

def lerp(a, b, t):
    """Linear interpolation between two values."""
    return int(a + (b - a) * t)


def lerp_color(c1, c2, t):
    """
    Linear interpolation between two RGB colors.
    
    Args:
        c1: First color as (R, G, B) tuple
        c2: Second color as (R, G, B) tuple
        t: Interpolation factor (0.0 to 1.0)
        
    Returns:
        Hex color string
    """
    return "#{:02x}{:02x}{:02x}".format(
        lerp(c1[0], c2[0], t),
        lerp(c1[1], c2[1], t),
        lerp(c1[2], c2[2], t),
    )


# Color anchors (RGB tuples)
RED = (220, 53, 69)
YELLOW = (255, 193, 7)
GREEN = (40, 167, 69)

BLUE_LIGHT = (222, 235, 247)
BLUE_DARK = (33, 113, 181)


# ============================================================================
# Tile Canvas Widget
# ============================================================================

class TileCanvas(tk.Canvas):
    """
    Visual representation of a single garden plot.
    
    Displays:
    - Soil background
    - Plant icon
    - Water level bar (left side)
    - Health bar (bottom)
    - Status badges (P=pollinated, E=emasculated, !=pollen ready)
    - Plant ID or status label
    """
    
    def __init__(self, parent, idx, app, soil_color, plant: Plant, configs, selected: bool = False):
        """
        Initialize a tile canvas.
        
        Args:
            parent: Parent widget
            idx: Tile index in garden grid
            app: Main application reference
            soil_color: Background color for soil
            plant: Plant instance (or None for empty plot)
            configs: Configuration dictionary
            selected: Whether this tile is currently selected
        """
        self.configs = configs
        self.idx = idx
        self.app = app
        self.soil = soil_color
        self.plant = plant
        
        # Layout dimensions
        self.w = configs['TILE_SIZE']
        self.h = self.w
        
        # Bar configuration
        self.bar_pad = int(configs.get("BAR_PAD", 3))
        self.water_thick = int(configs.get("WATER_BAR_W", max(4, self.w // 8)))
        self.health_thick = int(configs.get("HEALTH_BAR_H", max(3, self.w // 14)))
        self.bottom_shift = int(configs.get("BOTTOM_SHIFT", 4))
        
        # Label and health bar spacing
        self.label_h = self.configs.get("LABEL_H", 14)
        self.hb_h = self.health_thick
        
        self.selected = selected
        
        # Initialize canvas
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
        
        # Create visual elements
        self._create_background()
        self._create_water_bar()
        self._create_health_bar()
        self._create_plant_icon()
        self._create_label()
        self._create_badges()
        
        # Cache special icons
        self._load_special_icons()
        
        # Bind interaction events
        self._set_bindings()
        
        # Initial render
        self.render()
    
    def _create_background(self):
        """Create the soil background rectangle."""
        self.bg_rect = self.create_rectangle(
            0, 0, self.w, self.h,
            fill=self.soil,
            outline="", width=0,
            tags="bg"
        )
    
    def _create_water_bar(self):
        """Create the vertical water level bar on the left side."""
        wb_w = self.water_thick
        wb_min_y = self.bar_pad
        wb_max_y = self.w - self.bar_pad
        
        # Background slot
        self.wb_bg = self.create_rectangle(
            self.bar_pad, wb_min_y, wb_w, wb_max_y,
            fill=self.soil,
            outline="", width=0,
            tags="water_items"
        )
        
        # Dynamic fill bar
        self.wb_fill = self.create_rectangle(
            self.bar_pad, wb_min_y, wb_w, wb_max_y,
            fill="blue",
            outline="", width=0,
            tags="water_items"
        )
    
    def _create_health_bar(self):
        """Create the horizontal health bar at the bottom."""
        # Position with bottom shift
        self.hb_y_end = self.w - self.bar_pad + self.bottom_shift
        self.hb_y_start = self.hb_y_end - self.hb_h
        
        # Background slot
        self.hb_bg = self.create_rectangle(
            self.bar_pad, self.hb_y_start, 
            self.w - self.bar_pad, self.hb_y_end,
            fill=self.soil, outline="", width=0,
            tags="health_items"
        )
        
        # Dynamic fill bar
        self.hb_fill = self.create_rectangle(
            self.bar_pad, self.hb_y_start, 
            self.w - self.bar_pad, self.hb_y_end,
            fill="green", outline="", width=0,
            tags="health_items"
        )
    
    def _create_plant_icon(self):
        """Create the centered plant icon."""
        icon_lift = max(6, self.w // 14)
        icon_drop = int(self.configs.get("ICON_DROP", 3))
        
        self.img_item = self.create_image(
            self.w // 2 + self.water_thick // 2,
            self.w // 2 - (self.health_thick // 2) - icon_lift + icon_drop,
            image=None,
            tags="plant_img"
        )
    
    def _create_label(self):
        """Create the status label (plant ID or "free"/"dead")."""
        label_gap = max(6, self.health_thick // 2)
        label_pad = int(self.configs.get("LABEL_PAD", 0))
        
        label_y = int(
            self.hb_y_start
            - label_gap
            - (self.label_h / 2)
            + label_pad
            + 6
        )
        
        self.label_item = self.create_text(
            self.w // 2 + self.water_thick // 2,
            label_y,
            text="",
            font=("Segoe UI", 9, "bold"),
            fill="#1f1f1f",
            tags=("tile_label",)
        )
    
    def _create_badges(self):
        """Create status badges (P, E, !) in corners."""
        self.badge_size = 18
        self.badge_y = 4
        self.p_inset_right = 2
        self.e_overhang_left = 0
        
        # Plant plot area (after water bar)
        plot_x0 = self.water_thick
        plot_x1 = self.w
        
        # P badge (pollinated): top-right
        p_x = plot_x1 - self.p_inset_right - self.badge_size
        p_y = self.badge_y
        self._draw_badge(p_x, p_y, "P", bg="#FFD54F", fg="#000000", tag="p_badge")
        
        # ! badge (pollen ready): same position as P
        self._draw_badge(p_x, p_y, "!", bg="#FFCDD2", fg="#B71C1C", tag="bang_badge")
        
        # E badge (emasculated): top-left
        e_x = plot_x0 - self.e_overhang_left
        e_y = self.badge_y
        self._draw_badge(e_x, e_y, "E", bg="#BBDEFB", fg="#0D47A1", tag="e_badge")
    
    def _draw_badge(self, x, y, char, bg, fg, tag):
        """
        Draw a flat square badge with character.
        
        Args:
            x, y: Top-left corner position
            char: Character to display
            bg: Background color
            fg: Foreground (text) color
            tag: Canvas tag for this badge
        """
        s = self.badge_size
        
        # Background rectangle
        self.create_rectangle(
            x, y, x + s, y + s,
            fill=bg,
            outline="", width=0,
            tags=(tag, "badge_group")
        )
        
        # Character text
        self.create_text(
            x + s / 2, y + s / 2,
            text=char,
            font=("Arial", 12, "bold"),
            fill=fg,
            tags=(tag, "badge_group")
        )
    
    def _load_special_icons(self):
        """Load cached empty and dead plant icons."""
        self.empty_img = None
        try:
            self.empty_img = tk.PhotoImage(
                file=self.configs.get("EMPTY_ICON_PATH", "icons/empty.png")
            )
        except Exception:
            pass
        
        self.dead_img = None
        try:
            self.dead_img = tk.PhotoImage(
                file=self.configs.get("DEAD_ICON_PATH", "icons/dead.png")
            )
        except Exception:
            pass
    
    def _set_bindings(self):
        """Set up mouse event bindings for interaction."""
        self.bind("<Button-1>", 
                 lambda e: self.app._on_tile_left_press(e, self.idx))
        self.bind("<B1-Motion>", 
                 self.app._on_drag_motion)
        self.bind("<ButtonRelease-1>", 
                 lambda e: self.app._on_tile_left_release(e, self.idx))
        self.bind("<Button-3>", 
                 lambda e: self.app._on_tile_right_click(self, e))
        self.bind("<Button-2>", 
                 lambda e: self.app._on_tile_right_click(self, e))
        self.bind("<Double-Button-1>", 
                 lambda e: self.app._on_tile_double_click(e, self.idx))
    
    # ========================================================================
    # Rendering
    # ========================================================================
    
    def render(self):
        """
        Render the tile based on current plant state.
        
        Handles three cases:
        1. Empty plot (no plant)
        2. Dead plant
        3. Living plant (with bars, badges, icon)
        """
        # Update selection border
        try:
            border_color = "darkorange" if self.selected else self.soil
            self.config(
                highlightbackground=border_color,
                highlightcolor=border_color
            )
        except Exception:
            pass
        
        # Hide all dynamic elements by default
        try:
            self.itemconfig("water_items", state="hidden")
            self.itemconfig("health_items", state="hidden")
            self.itemconfig("badge_group", state="hidden")
        except Exception:
            pass
        
        # Empty plot
        if self.plant is None:
            self._render_empty()
            return
        
        # Dead plant
        if not getattr(self.plant, "alive", True):
            self._render_dead()
            return
        
        # Living plant
        self._render_alive()
    
    def _render_empty(self):
        """Render an empty plot."""
        try:
            self.itemconfig(self.label_item, text="free", state="normal")
        except Exception:
            pass
        
        if self.empty_img is not None:
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
    
    def _render_dead(self):
        """Render a dead plant."""
        try:
            self.itemconfig(self.label_item, text="dead", state="normal")
        except Exception:
            pass
        
        if self.dead_img is not None:
            try:
                self.itemconfig("plant_img", state="normal")
                self.itemconfig(self.img_item, image=self.dead_img)
            except Exception:
                pass
        else:
            try:
                self.itemconfig("plant_img", state="hidden")
            except Exception:
                pass
    
    def _render_alive(self):
        """Render a living plant with all UI elements."""
        # Label
        try:
            plant_id = getattr(self.plant, 'id', '')
            self.itemconfig(self.label_item, text=f"#{plant_id}", state="normal")
        except Exception:
            pass
        
        # Show bars and icon
        try:
            self.itemconfig("water_items", state="normal")
            self.itemconfig("health_items", state="normal")
            self.itemconfig("plant_img", state="normal")
        except Exception:
            pass
        
        # Update bar values
        try:
            self.update_health(getattr(self.plant, "health", 100))
        except Exception:
            pass
        
        try:
            self.update_water(getattr(self.plant, "water", 0))
        except Exception:
            pass
        
        # Update badges
        self._update_badges()
        
        # Update plant icon
        try:
            img_obj = getattr(self.plant, "img_obj", None)
            if img_obj is not None:
                self.itemconfig(self.img_item, image=img_obj)
            else:
                self.itemconfig(self.img_item, image="")
        except Exception:
            pass
    
    def _update_badges(self):
        """Update visibility of status badges."""
        # P badge: plant has pending cross/pollinated
        try:
            has_pending = bool(getattr(self.plant, "pending_cross", False))
            self.itemconfig("p_badge", state="normal" if has_pending else "hidden")
        except Exception:
            pass
        
        # ! badge: pollen ready today (only show if not pollinated)
        try:
            today = None
            try:
                today = int(getattr(self.app, "_today", lambda: 0)())
            except Exception:
                pass
            
            inspected_today = (getattr(self.plant, "last_anther_check_day", None) == today)
            anthers_ok = bool(getattr(self.plant, "anthers_available_today", False))
            has_pending = bool(getattr(self.plant, "pending_cross", False))
            
            show_bang = (not has_pending) and inspected_today and anthers_ok
            
            # Clear stale availability if day changed
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
        
        # E badge: emasculated
        try:
            is_emasculated = getattr(self.plant, "emasculated", False)
            self.itemconfig("e_badge", state="normal" if is_emasculated else "hidden")
        except Exception:
            pass
    
    # ========================================================================
    # Bar Updates
    # ========================================================================
    
    def update_health(self, percent):
        """
        Update health bar display.
        
        Args:
            percent: Health percentage (0-100)
        """
        percent = max(0, min(100, percent))
        pad = self.bar_pad
        
        # Calculate bar width
        max_w = (self.w - pad) - pad
        new_x1 = pad + (max_w * (percent / 100))
        
        # Update bar geometry
        y0 = self.hb_y_start
        y1 = self.hb_y_end
        self.coords(self.hb_fill, pad, y0, new_x1, y1)
        
        # Color gradient: red → yellow → green
        t = percent / 100
        if t < 0.5:
            color = lerp_color(RED, YELLOW, t * 2)
        else:
            color = lerp_color(YELLOW, GREEN, (t - 0.5) * 2)
        
        self.itemconfig(self.hb_fill, fill=color)
    
    def update_water(self, percent):
        """
        Update water bar display.
        
        Args:
            percent: Water percentage (0-100)
        """
        percent = max(0, min(100, percent))
        pad = self.bar_pad
        
        # Calculate bar height (fills from bottom up)
        wb_min_y = pad
        wb_max_y = self.w - pad
        total_height = wb_max_y - wb_min_y
        
        new_y0 = wb_max_y - (total_height * (percent / 100))
        
        # Update bar geometry
        self.coords(
            self.wb_fill,
            pad,
            new_y0,
            self.water_thick,
            wb_max_y
        )
        
        # Color gradient: light blue → dark blue
        color = lerp_color(BLUE_LIGHT, BLUE_DARK, percent / 100)
        self.itemconfig(self.wb_fill, fill=color)
    
    # ========================================================================
    # Appearance
    # ========================================================================
    
    def set_soil_color(self, soil_hex: str):
        """
        Change the soil background color.
        
        Args:
            soil_hex: Hex color string (e.g., "#7f9f7a")
        """
        self.soil = soil_hex
        
        # Update background elements
        try:
            self.itemconfigure(self.bg_rect, fill=soil_hex)
        except Exception:
            pass
        
        try:
            if hasattr(self, "wb_bg"):
                self.itemconfigure(self.wb_bg, fill=soil_hex)
            if hasattr(self, "hb_bg"):
                self.itemconfigure(self.hb_bg, fill=soil_hex)
        except Exception:
            pass
        
        try:
            self.configure(bg=soil_hex)
        except Exception:
            pass
        
        # Update selection border (if not selected)
        try:
            if not self.selected:
                self.config(
                    highlightbackground=soil_hex,
                    highlightcolor=soil_hex
                )
        except Exception:
            pass
