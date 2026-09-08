"""
Tile Canvas Module

Provides the TileCanvas widget for displaying individual garden plots.
Each tile shows a plant's icon, health bar, water bar, and status badges.
"""

import random
import tkinter as tk
from plant import Plant

try:
    from PIL import Image as _PilImage, ImageTk as _PilImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _find_base_image(pil_imgs, mode, season, vi, bucket):
    """
    Return the best available PIL image for (mode, season, vi, bucket).

    Fallback order (most-specific to least):
      1. Exact (mode, season, vi, bucket)
      2. Same season, nearest lower vi
      3. Any other season, same vi
      4. Any other season, nearest lower vi
    Returns None only if pil_imgs has nothing at all for this mode.
    """
    # 1. Exact match
    img = pil_imgs.get((mode, season, vi, bucket))
    if img is not None:
        return img
    # 2. Same season, nearest lower vi
    for v in range(vi - 1, -1, -1):
        img = pil_imgs.get((mode, season, v, bucket))
        if img is not None:
            return img
    # 3 & 4. Other seasons
    _SEASON_ORDER = ('spring', 'summer', 'autumn', 'winter')
    for s in _SEASON_ORDER:
        if s == season:
            continue
        img = pil_imgs.get((mode, s, vi, bucket))
        if img is not None:
            return img
        for v in range(vi - 1, -1, -1):
            img = pil_imgs.get((mode, s, v, bucket))
            if img is not None:
                return img
    return None


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
        # None, or a string like "beehive" / "measuring_station" — a tile
        # with this set permanently blocks planting and normal selection;
        # clicking it triggers its own special handler instead (see
        # GardenApp._on_tile_left_press). plot_idx is set externally by
        # the app right after construction (see __init__'s tile-building
        # loop), same as for the texture-variant plot differentiation.
        self.special_object = None
        
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
        
        # Texture background state
        self._lighting_bucket = 100   # 0=night … 100=full day; set by day/night loop
        self._bg_cache_key    = None  # last baked cache key
        self._bg_grass_vi     = None  # grass variant index — assigned lazily
        self._bg_soil_vi      = None  # soil variant index — assigned lazily
        self._soil_linger_until = 0   # sim-hour until which soil texture lingers after plant removal
        self._render_state    = None  # cached render state tuple for dirty-flag skip

        # Snow coverage (0.0 = bare soil, 1.0 = fully snow-covered).
        # Managed externally by the app via set_snow_cover().
        self.snow_cover = 0.0
        # The last raw (pre-snow-blend) colour passed to set_soil_color().
        # Needed so snow re-blends correctly when snow_cover changes between
        # day/night animation frames.
        self._last_applied_hex = soil_color
        
        # Per-tile snow parameters (lazy random, seeded by idx)
        _rng = random.Random(self.idx * 4999 + 83)
        self._snow_rate       = _rng.uniform(0.06, 0.16)   # accumulation per triggered hour
        self._snow_melt_rate  = _rng.uniform(0.04, 0.12)   # melt per triggered hour
        self._snow_since_hour = None                        # sim-hour when this tile first got snow
        
        # Initialize canvas — no highlight border; selection shown via the
        # 4 sel_line_* items (see _create_background / _update_selection_border)
        super().__init__(
            parent,
            width=self.w,
            height=self.h,
            bg=self.soil,
            highlightthickness=0,
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
        """Create the soil background rectangle and texture image slot."""
        # Solid-colour fallback (always present, hidden by bg_img_item when textures load)
        self.bg_rect = self.create_rectangle(
            0, 0, self.w, self.h,
            fill=self.soil,
            outline="", width=0,
            tags="bg"
        )
        # Texture image sits on top of bg_rect; starts empty (shows bg_rect through)
        self.bg_img_item = self.create_image(0, 0, anchor='nw', tags='bg_img')

        # Selection border — drawn as 4 independent line segments (one per
        # side), not a single rectangle, so each side can be shown or
        # hidden based on whether the tile touching it in that direction
        # is ALSO selected (see _update_selection_border). That gives a
        # full-thickness border around the outer edge of a selection, and
        # a single line (not doubled) at the seam between two adjacent
        # selected tiles. Each line spans the tile's full length along
        # its own axis (0 to self.w, or 0 to self.h); inset is only
        # applied on the perpendicular axis, to keep the line's own
        # half-width from being clipped at the canvas edge. Invisible by
        # default; color set to white when a given side is shown.
        SEL_W = 3
        inset = 1
        self.sel_line_top = self.create_line(
            0, inset, self.w, inset, width=SEL_W, fill="", tags="sel_border")
        self.sel_line_bottom = self.create_line(
            0, self.h - inset, self.w, self.h - inset, width=SEL_W, fill="", tags="sel_border")
        self.sel_line_left = self.create_line(
            inset, 0, inset, self.h, width=SEL_W, fill="", tags="sel_border")
        self.sel_line_right = self.create_line(
            self.w - inset, 0, self.w - inset, self.h, width=SEL_W, fill="", tags="sel_border")
    
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
        """Create the status label (plant ID or dead)."""
        label_gap = max(6, self.health_thick // 2)
        label_pad = int(self.configs.get("LABEL_PAD", 0))

        label_y = int(
            self.hb_y_start
            - label_gap
            - (self.label_h / 2)
            + label_pad
            + 6
        )
        self._label_y = label_y

        self.label_item = self.create_text(
            self.w // 2 + self.water_thick // 2,
            label_y,
            text="",
            font=("Segoe UI", 9, "bold"),
            fill="#ffffff",
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

    def set_special_object(self, kind):
        """
        Marks this tile as permanently occupied by a non-plant object —
        kind is "beehive" or "measuring_station". Blocks planting/normal
        selection (see is_free_for_planting and
        GardenApp._on_tile_left_press) and swaps in its icon in place of
        the usual plant/empty rendering (see _render_special_object).

        A measuring station spans two grid rows vertically — its actual
        real-world size doesn't fit a single plant plot convincingly (see
        GardenApp._place_measuring_station / _grid_tile, which handle the
        rowspan and hide the covered tile below it) — so this canvas
        widget itself is resized taller to match before the icon is
        scaled, rather than just drawing a bigger icon inside a
        single-tile-sized canvas, which would just get clipped at the
        normal tile boundary (Canvas clips its own content — it can't
        visually overflow into a neighboring widget's space).

        Icon scaled up via PIL when available — target is most of
        whatever the tile's actual footprint is now (single square for
        a beehive, tall rectangle for a measuring station) — since these
        tiles have no water/health bar to share space with, there's no
        reason for the icon to stay at the source PNG's native size.
        Falls back to that native size if PIL isn't available or the
        resize fails.
        """
        self.special_object = kind
        icon_file = {"beehive": "beehive.png",
                     "measuring_station": "measuringstation.png"}.get(kind)

        if kind == "measuring_station":
            try:
                self.h = self.w * 2
                self.config(height=self.h)
                # bg_rect, bg_img_item, and the sel_line_* selection-
                # border items were all created at construction time
                # (see _create_background), sized to the tile's original
                # square dimensions — resizing the canvas taller here
                # doesn't automatically resize items already drawn on
                # it. Texture tiling for a non-standard height isn't
                # worth the complexity for a tile that never shows a
                # plant, so: stretch the solid-colour fallback to the
                # full new height and hide the texture image entirely,
                # and extend the selection-border lines that run along
                # the height axis (left, right, and bottom's position)
                # to match.
                self.coords(self.bg_rect, 0, 0, self.w, self.h)
                self.itemconfig(self.bg_img_item, image='')
                inset = 1
                self.coords(self.sel_line_left, inset, 0, inset, self.h)
                self.coords(self.sel_line_right, self.w - inset, 0, self.w - inset, self.h)
                self.coords(self.sel_line_bottom, 0, self.h - inset, self.w, self.h - inset)
            except Exception:
                pass

        self._special_object_img = None
        if icon_file:
            path = f"icons/{icon_file}"
            target_w = max(24, int(self.w * 0.85))
            target_h = max(24, int(self.h * 0.85))
            if _PIL_AVAILABLE:
                try:
                    pil_img = _PilImage.open(path).convert("RGBA")
                    pil_img.thumbnail((target_w, target_h), _PilImage.LANCZOS)
                    self._special_object_img = _PilImageTk.PhotoImage(pil_img)
                except Exception:
                    self._special_object_img = None
            if self._special_object_img is None:
                try:
                    self._special_object_img = tk.PhotoImage(file=path)
                except Exception:
                    pass
        self._render_state = None  # force the next render() to actually apply this

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

    def _get_render_state(self):
        """
        Return a hashable tuple that encodes everything visible on this tile.
        render() compares this against _render_state and skips if unchanged.
        """
        p = self.plant
        if p is None:
            return (None, self.selected)
        alive = p.__dict__.get('alive', True)
        if not alive:
            return ('dead', id(p), self.selected)
        return (
            id(p),
            p.__dict__.get('stage', 0),
            p.__dict__.get('health', 100) // 5,   # 5-pt buckets avoid per-point redraws
            p.__dict__.get('water',  0)  // 5,
            id(p.__dict__.get('img_obj', None)),   # icon object identity
            bool(p.__dict__.get('pending_cross', False)),
            bool(p.__dict__.get('emasculated',   False)),
            bool(p.__dict__.get('anthers_available_today', False)),
            self.selected,
        )

    def _update_selection_border(self):
        """
        Shows/hides each of the 4 selection-border line segments — a
        side is shown only if THIS tile is selected AND the neighboring
        tile in that direction is NOT ALSO responsible for drawing that
        same boundary. That gives a full-thickness border around the
        outer edge of a multi-tile selection, and a single (not doubled)
        line at the seam between two contiguous selected tiles.

        TOP and LEFT are always drawn when this tile is selected,
        regardless of neighbors. BOTTOM and RIGHT are drawn UNLESS the
        neighbor in that direction is also selected — in that case, that
        neighbor is the one responsible for this boundary instead, from
        its own TOP/LEFT.

        Special-object tiles (beehive, measuring station) behave exactly
        like any other tile here. The one genuine exception: a measuring
        station's canvas is resized taller (see set_special_object) to
        visually span both the grid row it sits in and the row below,
        which holds its "covered" tile — a tile that's never actually
        gridded/visible at all (see _place_measuring_station). That's
        one real canvas object spanning two grid cells, not two separate
        visual tiles, so:
        - the station's own "down" neighbor for hand-off purposes is 2
          rows down (its real neighbor), not 1 (the invisible covered
          tile occupying the same visual space);
        - the two ordinary tiles diagonally adjacent to the covered
          position (one row down, one column to either side of the
          station) treat the covering station's own .selected/hand-off
          state as authoritative for the side facing the covered tile,
          rather than the covered tile's own .selected (always False,
          since it's excluded from selection) — the station's own full-
          height side line already covers that boundary when it draws.

        Called unconditionally at the top of render(), every call, not
        gated behind the dirty-flag check — a side's correct visibility
        can depend on a NEIGHBORING tile's selection state changing, not
        just this tile's own state, which this tile's own dirty-flag (it
        only tracks self.selected, not a neighbor's) can't detect.
        """
        try:
            show_any = self.selected
            lines = (self.sel_line_top, self.sel_line_bottom,
                     self.sel_line_left, self.sel_line_right)
            if not show_any:
                for line in lines:
                    self.itemconfig(line, fill="")
                return

            cols = int(self.configs.get('TILES_PER_ROW', 1)) or 1
            col = self.idx % cols

            def _neighbor(n_idx):
                try:
                    tiles = self.app.tiles
                    if 0 <= n_idx < len(tiles):
                        return tiles[n_idx]
                except Exception:
                    pass
                return None

            def _neighbor_responsible(n_idx):
                n = _neighbor(n_idx)
                return bool(n is not None and getattr(n, 'selected', False))

            def _covering_station(covered_idx):
                """Given the idx of a measuring-station 'covered' tile,
                return the measuring-station tile that visually occupies
                that same space (one row up), or None."""
                n = _neighbor(covered_idx - cols)
                if n is not None and getattr(n, 'special_object', None) == 'measuring_station':
                    return n
                return None

            def _ms_own_right_shown(ms_tile):
                """Would this measuring-station tile show its own right
                line? Same rule as any tile's right side: hidden only if
                its same-row right neighbor is selected."""
                if not getattr(ms_tile, 'selected', False):
                    return False
                ms_col = ms_tile.idx % cols
                if ms_col >= cols - 1:
                    return True
                return not _neighbor_responsible(ms_tile.idx + 1)

            is_measuring_station = getattr(self, 'special_object', None) == 'measuring_station'
            bottom_idx = self.idx + (2 * cols if is_measuring_station else cols)

            # Left/right need an explicit column-boundary check — idx-1 /
            # idx+1 stay within bounds even when wrapping to the previous
            # or next ROW, which the plain index bounds check alone
            # wouldn't catch (unlike top/bottom, where going off the grid
            # vertically is inherently out of bounds).
            bottom_owned_by_neighbor = _neighbor_responsible(bottom_idx)

            # This tile's own right side, when the right-neighbor is a
            # covered tile: defer to the covering station's .selected
            # instead (see docstring).
            right_neighbor_idx = self.idx + 1
            right_neighbor = _neighbor(right_neighbor_idx) if col < cols - 1 else None
            if right_neighbor is not None and getattr(right_neighbor, '_covered_by_measuring_station', False):
                covering = _covering_station(right_neighbor_idx)
                right_owned_by_neighbor = bool(covering is not None and getattr(covering, 'selected', False))
            else:
                right_owned_by_neighbor = (col < cols - 1) and _neighbor_responsible(right_neighbor_idx)

            # Mirror case: this tile's own left side is normally always
            # drawn — suppressed only when its left-neighbor is a
            # covered tile AND the covering station's own right line
            # would actually be showing (which already spans the full
            # height and covers this boundary). If the station's right
            # is handed off elsewhere instead, that only covers the
            # upper half, so this tile's own left still needs to draw.
            left_suppressed = False
            if col > 0:
                left_neighbor = _neighbor(self.idx - 1)
                if left_neighbor is not None and getattr(left_neighbor, '_covered_by_measuring_station', False):
                    covering = _covering_station(self.idx - 1)
                    if covering is not None and _ms_own_right_shown(covering):
                        left_suppressed = True

            self.itemconfig(self.sel_line_top,    fill="white")
            self.itemconfig(self.sel_line_left,   fill=("" if left_suppressed else "white"))
            self.itemconfig(self.sel_line_bottom, fill=("" if bottom_owned_by_neighbor else "white"))
            self.itemconfig(self.sel_line_right,  fill=("" if right_owned_by_neighbor else "white"))
            self.tag_raise("sel_border")
        except Exception:
            pass

    def render(self):
        """
        Render the tile based on current plant state.

        Dirty-flag guard: compares a state tuple against the last render.
        Skips all tkinter calls when nothing has changed — eliminates the
        majority of render work during stable simulation.
        """
        # Cheap and self-contained (depends only on this tile's own
        # state, not a neighbor's) — left unconditional here rather than
        # moved into the dirty-flag-gated section below, since it's
        # harmless either way.
        self._update_selection_border()

        state = self._get_render_state()
        if state == self._render_state:
            return
        self._render_state = state

        try:
            # Hide bars and badges by default using explicit IDs (much faster than tags)
            try:
                self.itemconfig(self.wb_bg,  state="hidden")
                self.itemconfig(self.wb_fill, state="hidden")
            except Exception:
                pass
            try:
                self.itemconfig(self.hb_bg,  state="hidden")
                self.itemconfig(self.hb_fill, state="hidden")
            except Exception:
                pass
            try:
                self.itemconfig("badge_group", state="hidden")
            except Exception:
                pass

            # Special object tile (beehive, measuring station) — takes over
            # rendering entirely; these can never hold a plant, so self.plant
            # stays None and none of the normal empty/dead/alive paths apply.
            if getattr(self, 'special_object', None):
                self._render_special_object()
                return

            # Empty plot
            if self.plant is None:
                self._render_empty()
                return

            # Dead plant
            if not self.plant.__dict__.get('alive', True):
                self._render_dead()
                return

            # Living plant
            self._render_alive()
        finally:
            # _create_background() (which creates the sel_line_* items)
            # runs before _create_water_bar()/_create_health_bar() in
            # __init__, so Tkinter's default stacking (creation order —
            # later on top) puts those bars above the border by default.
            # _update_selection_border()'s own tag_raise (top of this
            # method) only fixes that at the moment it runs — everything
            # below it can restack things above the border again before
            # this call finishes. try/finally re-applies it after EVERY
            # branch above, regardless of which one ran or returned
            # early — a plain call after the if/elif chain would get
            # skipped by all of their early returns.
            try:
                self.tag_raise("sel_border")
            except Exception:
                pass

    def is_free_for_planting(self):
        """
        True if this tile can receive a new plant — empty, or holds only
        a dead plant. Special-object tiles (beehive, measuring station)
        are never available, even though self.plant is None for them
        too — centralizing this check here (rather than the scattered
        "pl is None or not pl.alive" pattern repeated across several
        planting functions) means every one of those call sites
        automatically respects special tiles without having to be
        individually updated.
        """
        if getattr(self, 'special_object', None):
            return False
        return self.plant is None or not getattr(self.plant, 'alive', True)

    def _render_special_object(self):
        """Render a beehive/measuring-station icon in place of a plant —
        reuses the same plant-icon canvas item/tag rather than creating a
        new one. Repositioned to the tile's true center (the plant-icon
        item is normally offset to leave room for the water bar on the
        left and health bar at the bottom — special-object tiles have
        neither, so that offset just wastes space here). Uses self.h
        rather than assuming it equals self.w — a measuring station's
        canvas is resized taller than it is wide (see
        set_special_object), so its true vertical center isn't self.w."""
        try:
            self.itemconfig(self.label_item, text="", state="hidden")
        except Exception:
            pass
        img = getattr(self, '_special_object_img', None)
        if img is not None:
            try:
                self.itemconfig("plant_img", state="normal")
                self.itemconfig(self.img_item, image=img)
                self.coords(self.img_item, self.w // 2, self.h // 2)
            except Exception:
                pass
        else:
            try:
                self.itemconfig("plant_img", state="hidden")
            except Exception:
                pass

    def _render_empty(self):
        """Render an empty plot — label only, no icon (seedling is the first stage)."""
        try:
            self.itemconfig(self.label_item, text="", state="hidden")
        except Exception:
            pass
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
        
        # Show bars and icon using explicit IDs (faster than tag lookup)
        try:
            self.itemconfig(self.wb_bg,   state="normal")
            self.itemconfig(self.wb_fill,  state="normal")
            self.itemconfig(self.hb_bg,   state="normal")
            self.itemconfig(self.hb_fill,  state="normal")
            self.itemconfig("plant_img",   state="normal")
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
        Change the soil background colour.

        Fast path: when a texture image is active it covers bg_rect, wb_bg,
        hb_bg, and the canvas bg entirely — so we skip all those itemconfigure
        calls and only pay for the image lookup/swap.

        Slow path (no textures / PIL missing): solid colour + snow blend,
        with a hex-change guard so bar updates only fire when the colour
        actually changes.
        """
        self._last_applied_hex = soil_hex

        if self._try_set_bg_image():
            # Texture active — nothing else to update
            self.soil = soil_hex
            return

        # ── Fallback: solid colour + snow blend ───────────────────────────
        display = self._blend_snow(soil_hex)
        if display == getattr(self, '_last_display_hex', None):
            return   # colour unchanged — skip all tkinter calls
        self._last_display_hex = display
        self.soil = display

        try:
            self.itemconfigure(self.bg_rect, fill=display)
        except Exception:
            pass
        try:
            if hasattr(self, "wb_bg"):
                self.itemconfigure(self.wb_bg, fill=display)
            if hasattr(self, "hb_bg"):
                self.itemconfigure(self.hb_bg, fill=display)
        except Exception:
            pass
        try:
            self.configure(bg=display)
        except Exception:
            pass

    def _try_set_bg_image(self) -> bool:
        """
        Look up (or lazily bake) the PhotoImage for the current
        (mode, season, variant, lighting_bucket, snow_bucket) and swap it
        onto bg_img_item.  Returns True on success, False if not ready.

        Hot-path optimisations
        ──────────────────────
        • PIL imported at module level — no per-call import overhead.
        • Season read from app._bg_current_season (set once per sim-hour by
          _update_snow_covers) — not recomputed per tile per frame.
        • Early-exit on unchanged key — zero tkinter calls in the common case.
        • Variant indices assigned once at first call per tile.
        """
        if not _PIL_AVAILABLE:
            return False

        try:
            app = self.app
            if not app.__dict__.get('_bg_texture_enabled', True):
                # Textures turned off in Game Settings — fall back to the
                # plain solid-colour rendering path below (same one used
                # when PIL is unavailable). bg_img_item sits ON TOP of the
                # solid-colour rect and stays visible once an image is set
                # on it, so the fallback color change alone wouldn't show
                # through — it has to be explicitly cleared too. Guarded so
                # this only actually touches the canvas once, not on every
                # render call while textures stay disabled.
                if not getattr(self, '_bg_img_cleared_for_disabled', False):
                    try:
                        self.itemconfig(self.bg_img_item, image='')
                    except Exception:
                        pass
                    # Measuring station's second stacked texture copy
                    # (see below) needs clearing too, or it'd leave a
                    # stale texture on the bottom half even though the
                    # top half correctly went blank.
                    if hasattr(self, '_bg_img_item2'):
                        try:
                            self.itemconfig(self._bg_img_item2, image='')
                        except Exception:
                            pass
                    self._bg_img_cleared_for_disabled = True
                return False
            self._bg_img_cleared_for_disabled = False
            cache    = app.__dict__.get('_bg_photo_cache')
            pil_imgs = app.__dict__.get('_bg_pil_images')
            if not pil_imgs:   # None or empty — textures not loaded
                return False

            # ── Assign per-tile variant indices once ──────────────────────
            if self._bg_grass_vi is None:
                n_g = max(1, app.__dict__.get('_bg_grass_variants', 1))
                n_s = max(1, app.__dict__.get('_bg_soil_variants',  1))
                # Seeded by position AND plot — seeding on self.idx alone
                # meant every plot's tile at the same grid position (idx
                # ranges 0..GRID_SIZE-1 identically per plot) picked the
                # exact same variant, making every plot look like a clone
                # of the first regardless of soil colour. This same
                # variant index gets reused across every season change
                # (see below — season only picks which image FILE a given
                # variant number maps to), so this one fix is enough to
                # keep plots visually distinct through spring/summer/
                # autumn/winter too, without any separate seasonal fix.
                rng = random.Random(self.idx * 31337 + getattr(self, 'plot_idx', 0) * 104729)
                self._bg_grass_vi = rng.randint(0, n_g - 1)
                self._bg_soil_vi  = rng.randint(0, n_s - 1)

            # ── Mode and variant ──────────────────────────────────────────
            plant = self.plant
            plant_alive = plant is not None and plant.__dict__.get('alive', True)
            plant_dead  = plant is not None and not plant.__dict__.get('alive', True)
            linger      = self._soil_linger_until
            use_soil    = plant_alive or plant_dead or (linger > app.__dict__.get('_snow_sim_hour', 0))
            if use_soil:
                mode = 'soil';  vi = self._bg_soil_vi
            else:
                mode = 'grass'; vi = self._bg_grass_vi

            # ── Season ────────────────────────────────────────────────────
            season      = app.__dict__.get('_bg_current_season', 'spring')
            snow_bkt    = min(7, round(self.snow_cover * 7))

            # Winter always shows autumn textures as its base — winter textures
            # only appear when it's actually snowing (on any season).
            base_season = 'autumn' if season == 'winter' else season

            # When winter falls back to autumn, limit to grass_autumn1-5 /
            # soil_autumn1-5 so the heavier autumn variants don't appear
            # in winter. Cap vi to 4 (0-indexed → files 1-5).
            if season == 'winter':
                vi = min(vi, 4)

            bucket = self._lighting_bucket

            key = (mode, base_season, vi, bucket, snow_bkt)
            if key == self._bg_cache_key:
                return True   # nothing changed — zero tkinter calls

            # ── Lazily bake PhotoImage ────────────────────────────────────
            if cache is None:
                cache = {}
                app._bg_photo_cache = cache

            if key not in cache:
                base = _find_base_image(pil_imgs, mode, base_season, vi, bucket)
                if base is None:
                    return False

                if snow_bkt > 0:
                    # Snow on any season blends from base toward winter textures.
                    t = (snow_bkt / 7.0) ** 0.75
                    winter_tex = _find_base_image(pil_imgs, mode, 'winter', vi, bucket)
                    if winter_tex is not None:
                        img = _PilImage.blend(
                            base.convert('RGBA'),
                            winter_tex.convert('RGBA'), t)
                    else:
                        img = base
                else:
                    img = base
                cache[key] = _PilImageTk.PhotoImage(img)

            self.itemconfig(self.bg_img_item, image=cache[key])
            self._bg_cache_key = key

            # Measuring station's canvas is resized taller than a single
            # baked texture image (see set_special_object) — tile a
            # second copy of the same image directly below the first, to
            # cover the full doubled height rather than leaving the
            # bottom half untextured.
            if getattr(self, 'special_object', None) == 'measuring_station':
                try:
                    if not hasattr(self, '_bg_img_item2'):
                        self._bg_img_item2 = self.create_image(0, self.w, anchor='nw', tags='bg_img')
                        # Stack above bg_rect (so the texture actually
                        # shows, not just the solid fallback underneath
                        # it) but below the plant-icon item (so the
                        # station's icon stays visible on top, rather
                        # than getting covered by this new background
                        # layer created after it).
                        self.tag_raise(self._bg_img_item2, self.bg_rect)
                        self.tag_lower(self._bg_img_item2, self.img_item)
                    self.itemconfig(self._bg_img_item2, image=cache[key])
                except Exception:
                    pass

            return True

        except Exception:
            return False
    # ========================================================================
    # Snow System
    # ========================================================================

    def _blend_snow(self, soil_hex: str) -> str:
        """
        Blend *soil_hex* toward a cold blue-white based on self.snow_cover.

        The snow colour is slightly blue-white (not pure white) so it looks
        like packed snow on soil rather than a blank tile.  A mild gamma
        curve makes coverage visible early.
        """
        cover = self.snow_cover
        if cover <= 0.0:
            return soil_hex
        try:
            h = soil_hex.lstrip("#")
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            # Snow target: cold blue-white, with per-tile subtle variation
            sr, sg, sb = 238, 244, 255
            t = cover ** 0.75          # gamma: visible at low coverage too
            nr = int(r + (sr - r) * t)
            ng = int(g + (sg - g) * t)
            nb = int(b + (sb - b) * t)
            return f"#{nr:02x}{ng:02x}{nb:02x}"
        except Exception:
            return soil_hex

    def set_snow_cover(self, cover: float):
        """
        Update snow coverage (0.0–1.0) and refresh tile colours.

        Called each simulated hour by the garden app.  Uses the last colour
        the day/night system passed to set_soil_color() so snow blends
        correctly on top of whatever lighting is active.
        """
        cover = max(0.0, min(1.0, float(cover)))
        if abs(cover - self.snow_cover) < 0.004:
            return                                 # skip trivial updates
        self.snow_cover = cover
        self._bg_cache_key = None                  # force image rebake with new snow level
        last = getattr(self, "_last_applied_hex", self.soil.lstrip("#") and self.soil)
        self.set_soil_color(last)                  # re-composite with new cover
