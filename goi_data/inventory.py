"""
Inventory Module

Manages the inventory system for seeds and pollen in the Pea Garden simulation.
Provides dataclasses for inventory items and a popup UI for browsing/managing them.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import List, Literal, Optional, Callable

import tkinter as tk
from tkinter import Toplevel, ttk

from plant import Plant, STAGE_NAMES
from icon_loader import *


class _FlatIconButton(tk.Label):
    """
    Local copy of Garden-of-Inheritance.py's _FlatIconButton (same
    reasoning applies here: on macOS, tk.Button ignores bg/fg/relief/
    activebackground styling entirely and always shows native chrome —
    a visible box — regardless of what's configured; tk.Label doesn't
    have that problem). Duplicated here rather than imported, since
    Garden-of-Inheritance.py imports FROM this module (PollenChooserPopup
    etc.), so importing the other way would be circular.
    """
    def __init__(self, parent, text="", image=None, compound=None,
                 command=None, bg="#F4F4F4", fg="black", hover_bg="#E4E4E4",
                 disabled_bg="#F4F4F4", disabled_fg="#999999",
                 font=("Segoe UI", 12), padx=12, pady=6, **kwargs):
        self._base_bg = bg
        self._base_fg = fg
        self._hover_bg = hover_bg
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        self._command = command
        self._enabled = True

        super().__init__(parent, text=text, image=image, compound=compound,
                          bg=bg, fg=fg, font=font, padx=padx, pady=pady,
                          cursor="hand2", relief="flat", bd=0,
                          highlightthickness=0, anchor="w", **kwargs)
        if image is not None:
            self.image = image  # keep a reference so it isn't garbage-collected

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, event=None):
        if self._enabled:
            tk.Label.configure(self, bg=self._hover_bg)

    def _on_leave(self, event=None):
        if self._enabled:
            tk.Label.configure(self, bg=self._base_bg)

    def _on_click(self, event=None):
        if self._enabled and self._command:
            self._command()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._enabled = (state != "disabled")
            if self._enabled:
                tk.Label.configure(self, bg=self._base_bg, fg=self._base_fg,
                                    cursor="hand2")
            else:
                tk.Label.configure(self, bg=self._disabled_bg, fg=self._disabled_fg,
                                    cursor="arrow")
        if "activebackground" in kwargs:
            self._hover_bg = kwargs.pop("activebackground")
        kwargs.pop("activeforeground", None)
        # Keep _base_bg/_base_fg in sync with any explicit bg/fg change —
        # without this, the next <Leave> would revert to whatever
        # _base_bg was at construction time, undoing this call's color.
        if "bg" in kwargs:
            self._base_bg = kwargs["bg"]
        if "fg" in kwargs:
            self._base_fg = kwargs["fg"]
        if kwargs:
            tk.Label.configure(self, **kwargs)

    config = configure


# ============================================================================
# Inventory Item Classes
# ============================================================================

@dataclass
class InventoryItem:
    """Base class for inventory items."""
    name: str
    id: int


@dataclass
class Seed(InventoryItem):
    """
    Represents a harvested seed.
    
    Contains genetic information and lineage data for planting.
    """
    source_id: int  # Maternal plant ID
    donor_id: Optional[int]  # Paternal plant ID (None for selfed seeds)
    traits: dict
    generation: int
    pod_index: int
    genotype: dict
    ancestry: List

    def __repr__(self):
        return f"Seed({self.label}, Traits: {self.traits})"

    def is_selfed(self) -> bool:
        """Check if this seed is from self-pollination."""
        return self.donor_id is None

    def get(self, key, default=None):
        """Get attribute value with fallback."""
        return getattr(self, key, default)


@dataclass
class Pollen(InventoryItem):
    """
    Represents collected pollen from a plant.
    
    Contains genetic information and expiration tracking.
    """
    source_plant: Plant
    collection_time: int

    # Metadata fields
    source_id: int = 0
    collected_day: int = 0
    expires_day: int = 0
    genotype: dict = field(default_factory=dict)
    traits: dict = field(default_factory=dict)

    def __post_init__(self):
        """Derive metadata from source plant."""
        # Set source ID
        try:
            self.source_id = int(getattr(self.source_plant, "id", 0) or 0)
        except Exception:
            self.source_id = 0
        
        # Copy genotype
        try:
            if not self.genotype:
                genotype = getattr(self.source_plant, "genotype", None)
                if isinstance(genotype, dict):
                    self.genotype = dict(genotype)
        except Exception:
            pass
        
        # Copy traits
        try:
            if not self.traits:
                traits = getattr(self.source_plant, "traits", None)
                if isinstance(traits, dict):
                    self.traits = dict(traits)
        except Exception:
            pass

    def __repr__(self):
        return (f"Pollen(source_id={self.source_id}, "
                f"collected_day={self.collected_day}, "
                f"expires_day={self.expires_day})")

    def get(self, key, default=None):
        """
        Get attribute value with fallback to source plant.
        
        Args:
            key: Attribute name
            default: Default value if not found
            
        Returns:
            Attribute value or default
        """
        if hasattr(self, key):
            return getattr(self, key, default)
        try:
            return getattr(self.source_plant, key, default)
        except Exception:
            return default


# ============================================================================
# Inventory Container
# ============================================================================

class Inventory:
    """
    Container for managing inventory items.
    
    Organizes items into categories: misc, seeds, and pollen.
    """
    
    def __init__(self):
        """Initialize empty inventory."""
        self._items_misc: List[InventoryItem] = []
        self._items_seeds: List[Seed] = []
        self._items_pollen: List[Pollen] = []

    def add(self, item: InventoryItem):
        """
        Add an item to the appropriate category.
        
        Args:
            item: Item to add (Seed, Pollen, or other InventoryItem)
        """
        if isinstance(item, Seed):
            self._items_seeds.append(item)
        elif isinstance(item, Pollen):
            self._items_pollen.append(item)
        else:
            self._items_misc.append(item)
    
    def remove(self, item: InventoryItem):
        """
        Remove an item from inventory.

        Uses identity (is) matching rather than equality (==) to avoid
        issues with dataclass __eq__ on complex fields like Plant objects.

        Args:
            item: Item to remove
        """
        if isinstance(item, Seed):
            self._items_seeds = [x for x in self._items_seeds if x is not item]
        elif isinstance(item, Pollen):
            self._items_pollen = [x for x in self._items_pollen if x is not item]
        else:
            self._items_misc = [x for x in self._items_misc if x is not item]

    def remove_by_id(self, item_id: int):
        """
        Remove an item from inventory by its ID field.

        Fallback for cases where the original object reference is unavailable.

        Args:
            item_id: The id field of the item to remove
        """
        self._items_seeds   = [x for x in self._items_seeds   if getattr(x, "id", None) != item_id]
        self._items_pollen  = [x for x in self._items_pollen  if getattr(x, "id", None) != item_id]
        self._items_misc    = [x for x in self._items_misc    if getattr(x, "id", None) != item_id]

    def get_all(self, item_type: Literal['misc', 'seeds', 'pollen']) -> List[InventoryItem]:
        """
        Get all items of a specific type.
        
        Args:
            item_type: Type of items to retrieve
            
        Returns:
            List of items of the specified type
            
        Raises:
            ValueError: If item_type is invalid
        """
        if item_type == 'misc':
            return self._items_misc
        elif item_type == 'seeds':
            return self._items_seeds
        elif item_type == 'pollen':
            return self._items_pollen
        else:
            raise ValueError("Invalid inventory type. Choose from 'misc', 'seeds', or 'pollen'.")


# ============================================================================
# Standalone Pollen Chooser
# ============================================================================

class PollenChooserPopup(Toplevel):
    """Standalone pollen chooser window opened when the player pollinates.

    Mirrors the card layout of choose_seed_for_tiles: a 3-column paginated
    grid where each card shows the source flower icon, the anther_small.png icon,
    viability info, and a Use button.  No notebook tabs.
    """

    MAX_PER_PAGE = 9
    ICON_SIZE    = 64   # display size for both icons (pixels)

    def __init__(self, master, app):
        super().__init__(master)

        self.app   = app
        self.page  = 0
        self._img_refs = []

        self.title("Choose Pollen")
        # Same size as choose_seed_for_tiles's picker (760x640) — this
        # used to be a different, larger 800x700, and also forced itself
        # "always on top" (-topmost) with an internal lift() on top of
        # the caller's own lift()/focus_force() — neither of which the
        # seed picker does; it just relies on Toplevel's normal above-
        # its-parent behavior. Matched here so the two pickers actually
        # look and behave the same way, not just similarly.
        self.geometry("760x640")
        self.resizable(True, True)
        # Should never open maximized just because the main window
        # happens to be — see GardenApp._force_window_not_maximized's
        # docstring for why this needs an explicit call on macOS.
        try:
            self.app._force_window_not_maximized(self)
        except Exception:
            pass

        self._build()

    # ── Build ────────────────────────────────────────────────────────────────

    def _build(self):
        bstyle = self.app.button_style if self.app else {}

        outer = tk.Frame(self, padx=10, pady=10)
        outer.pack(fill="both", expand=True)

        # ── Header ──────────────────────────────────────────────────────────
        header = tk.Frame(outer)
        header.pack(fill="x", pady=(0, 6))

        btn_prev = tk.Button(header, text="◀ Prev", command=self._prev, **bstyle)
        btn_next = tk.Button(header, text="Next ▶", command=self._next, **bstyle)
        if self.app:
            self.app._apply_hover(btn_prev)
            self.app._apply_hover(btn_next)

        self._page_lbl = tk.Label(header, text="", font=("Segoe UI", 11))

        btn_close = tk.Button(header, text="✕", command=self.destroy, **bstyle)
        if self.app:
            self.app._apply_hover(btn_close)

        self._page_lbl.pack(side="left", padx=8)
        btn_prev.pack(side="left")
        btn_close.pack(side="right")
        btn_next.pack(side="right", padx=(0, 6))

        # ── Card grid ───────────────────────────────────────────────────────
        self._grid = tk.Frame(outer)
        self._grid.pack(fill="both", expand=True)
        for c in range(3):
            self._grid.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(3):
            self._grid.grid_rowconfigure(r, weight=0)

        self._render()

    # ── Render ───────────────────────────────────────────────────────────────

    def _get_items_and_today(self):
        """Return (pollen_list, today_int) from the app's inventory."""
        try:
            items = self.app.inventory.get_all("pollen")
        except Exception:
            items = []
        try:
            today = int(getattr(self.app.garden, "day_of_month",
                                getattr(self.app.garden, "day", 0)))
        except Exception:
            today = 0
        return items, today

    def _render(self):
        # Discard stale image refs and clear grid
        self._img_refs = []
        for w in self._grid.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        items, today = self._get_items_and_today()

        # Group by source plant
        groups = defaultdict(list)
        for pkt in items:
            groups[int(getattr(pkt, "source_id", 0) or 0)].append(pkt)

        keys  = sorted(groups.keys())
        total = len(keys)

        # Clamp page
        if total > 0:
            max_page = (total - 1) // self.MAX_PER_PAGE
            self.page = min(self.page, max_page)
        else:
            self.page = 0

        start = self.page * self.MAX_PER_PAGE
        end   = min(total, start + self.MAX_PER_PAGE)

        if total:
            self._page_lbl.configure(text=f"Pollen groups {start+1}–{end} of {total}")
        else:
            self._page_lbl.configure(text="No pollen collected yet")

        shown = keys[start:end]

        if not shown:
            f = tk.Frame(self._grid, borderwidth=1, relief="groove", padx=10, pady=10)
            f.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")
            tk.Label(f, text="No pollen collected yet.",
                     fg="#666666", font=("Segoe UI", 12, "italic")).pack()
            return

        for idx, source_id in enumerate(shown):
            packets = groups[source_id]
            self._render_card(idx, source_id, packets, today)

    def _render_card(self, idx, source_id, packets, today):
        bstyle = self.app.button_style if self.app else {}
        r, c   = idx // 3, idx % 3

        # No fixed size — let content determine height so Use button is never clipped
        card = tk.Frame(self._grid, borderwidth=1, relief="groove", padx=8, pady=8)
        card.grid(row=r, column=c, padx=8, pady=8, sticky="new")
        card._img_refs = []

        # ── Header: icon (left) + title (after it) ──────────────────────────
        hdr = tk.Frame(card)
        hdr.pack(fill="x")

        def _discard(sid=source_id):
            try:
                inv = self.app.inventory
                for pkt in list(inv.get_all("pollen")):
                    if int(getattr(pkt, "source_id", 0) or 0) == int(sid):
                        inv.remove(pkt)
                if hasattr(self.app, "_toast"):
                    self.app._toast(f"Deleted pollen from plant #{sid}.")
            except Exception:
                pass
            self._render()

        # Remove icon (left, before the name) — matches self.remove_btn on
        # the left panel and the same fix applied to choose_seed_for_tiles's
        # own per-card delete button, replacing a plain tk.Button("✕") that
        # showed macOS's unstylable native chrome (a visible box). Packed
        # on the LEFT, before the title, with its own right-side padx as
        # spacing to the name — pinned to the right edge (side="right") it
        # was getting visibly clipped by the card's own border there.
        # safe_image, not a raw tk.PhotoImage(file=...) — the latter
        # re-loads and re-decodes the PNG from disk fresh on every single
        # pollen card, instead of reusing the same cached image object
        # via safe_image's own file-path cache (see icon_loader.py).
        try:
            _remove_img = safe_image(os.path.join(ICONS_DIR, "remove.png"))
        except Exception:
            _remove_img = None
        btn_x = _FlatIconButton(
            hdr,
            text="" if _remove_img is not None else "✕",
            image=_remove_img,
            compound="center",
            bg=hdr.cget("bg"),
            fg="red",
            hover_bg="#DDDDDD",
            disabled_bg=hdr.cget("bg"),
            font=bstyle.get("font", ("Segoe UI", 12)),
            padx=6,
            pady=6,
            command=_discard,
        )
        # Overrides _FlatIconButton's own hardcoded anchor="w" — see the
        # matching comment in choose_seed_for_tiles for why "center" is
        # needed here specifically for an image-only button like this.
        btn_x.configure(anchor="center")
        if _remove_img is not None:
            btn_x.image = _remove_img
        btn_x.pack(side="left", anchor="w", padx=(0, 8))

        tk.Label(hdr, text=f"from Plant #{source_id}",
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        # ── Icon row: flower icon + anther icon ──────────────────────────────
        icon_row = tk.Frame(card)
        icon_row.pack(anchor="w", pady=(4, 2))

        sz = self.ICON_SIZE

        # Gather traits from first packet that has them
        flower_pos   = None
        flower_color = None
        for pkt in packets:
            t = getattr(pkt, "traits", {}) or {}
            if isinstance(t, dict):
                flower_pos   = flower_pos   or t.get("flower_position")
                flower_color = flower_color or t.get("flower_color")
            if flower_pos and flower_color:
                break

        # Flower icon (hi-res first, then standard)
        flower_loaded = False
        if flower_pos and flower_color:
            for path_fn in (flower_icon_path_hi, flower_icon_path):
                try:
                    p = path_fn(flower_pos, flower_color)
                    if p:
                        raw = safe_image(p)
                        if raw:
                            img = raw.subsample(
                                max(1, raw.width()  // sz),
                                max(1, raw.height() // sz),
                            )
                            lbl = tk.Label(icon_row, image=img)
                            lbl.pack(side="left", padx=(0, 4))
                            self._img_refs.append(img)
                            card._img_refs.append(img)
                            flower_loaded = True
                            break
                except Exception:
                    pass

        if not flower_loaded:
            # Fallback: coloured square placeholder
            tk.Label(icon_row, text="🌸", font=("Segoe UI", sz // 2)).pack(
                side="left", padx=(0, 4))

        # Anther icon
        try:
            anther_path = os.path.join(ICONS_DIR, "anther_small.png")
            if os.path.exists(anther_path):
                raw = safe_image(anther_path)
                if raw:
                    img = raw.subsample(
                        max(1, raw.width()  // sz),
                        max(1, raw.height() // sz),
                    )
                    lbl = tk.Label(icon_row, image=img)
                    lbl.pack(side="left", padx=(0, 4))
                    self._img_refs.append(img)
                    card._img_refs.append(img)
            else:
                tk.Label(icon_row, text="🌿", font=("Segoe UI", sz // 2)).pack(side="left")
        except Exception:
            tk.Label(icon_row, text="🌿", font=("Segoe UI", sz // 2)).pack(side="left")

        # ── Viability ────────────────────────────────────────────────────────
        def _exp(pkt):
            try:
                return int(getattr(pkt, "expires_day", -999999))
            except Exception:
                return -999999

        viable = [p for p in packets if _exp(p) == today]
        viable_count = len(viable)

        # ── Info + Use row (Use aligned right under the ✕ discard button) ──
        pkt_placeholder = [None]  # must be defined before _use closure captures it
        pkt = viable[0] if viable else None
        pkt_placeholder[0] = pkt

        def _use():
            p = pkt_placeholder[0]
            if p and self.app and callable(getattr(self.app, "_apply_pollen", None)):
                applied = self.app._apply_pollen(p)
                if applied:
                    # Pollen was accepted (recipient valid, in season, viable) and
                    # handed off to the pollination flow — close the picker so the
                    # player isn't left staring at a stale list.
                    try:
                        self.destroy()
                    except Exception:
                        pass
                else:
                    # Validation rejected it (e.g. recipient not flowering, wrong
                    # phase, pollen expired) — keep the picker open, just refresh
                    # so any now-stale packets drop out of the list.
                    try:
                        self._render()
                    except Exception:
                        pass

        info_row = tk.Frame(card)
        info_row.pack(fill="x", pady=(4, 0))

        # Use button — right side, aligned under the ✕
        btn_use = tk.Button(info_row, text="Use", fg="green",
                            state=("normal" if pkt else "disabled"),
                            command=_use if pkt else None, **bstyle)
        if self.app:
            self.app._apply_hover(btn_use)
        btn_use.pack(side="right")

        # Count text — left side
        stale_tag = "  STALE" if viable_count == 0 and packets else ""
        tk.Label(info_row,
                 text=f"×{len(packets)} collected  |  {viable_count} viable{stale_tag}",
                 font=("Segoe UI", 9),
                 fg=("#b45309" if stale_tag else "#444444")).pack(side="left")

    # ── Pagination ────────────────────────────────────────────────────────────

    def _prev(self):
        if self.page > 0:
            self.page -= 1
            self._render()

    def _next(self):
        items, _ = self._get_items_and_today()
        groups = defaultdict(list)
        for pkt in items:
            groups[int(getattr(pkt, "source_id", 0) or 0)].append(pkt)
        if (self.page + 1) * self.MAX_PER_PAGE < len(groups):
            self.page += 1
            self._render()
