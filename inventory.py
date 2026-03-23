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

    def plant(self) -> Plant:
        """
        Create a Plant instance from this seed.
        
        Note: This method may need updating based on Plant constructor.
        """
        new_plant = Plant(species=self.species, traits=self.attribs)
        return new_plant
    
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
# Inventory Popup UI
# ============================================================================

class InventoryPopup(Toplevel):
    """Seeds-only popup for browsing and planting harvested seeds."""

    MAX_PER_PAGE_SEEDS = 9

    def __init__(self, master, garden, inventory, on_seed_selected: Callable,
                 app=None, initial_tab=None):
        super().__init__(master)
        try:
            self.attributes("-topmost", True)
            self.lift()
        except Exception:
            pass

        self.app = app
        if self.app is None:
            try:
                self.app = master.master
            except Exception:
                self.app = None

        self.title("Seeds")
        self.geometry("800x560")
        self.garden = garden
        self.inventory = inventory
        self.on_seed_selected = on_seed_selected
        self.seeds_page = 0

        self.seeds_frame = tk.Frame(self, padx=8, pady=8)
        self.seeds_frame.pack(fill="both", expand=True)
        self._build_seeds_tab()

    def refresh_current_tab(self):
        """Re-render the seeds page."""
        try:
            self._render_seeds_page()
        except Exception:
            pass

    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _label_with_bold_gender(self, parent, text, base_font=("Segoe UI", 12), bold_font=("Segoe UI", 12, "bold")):
        """Create a label with bold gender symbols (♀, ♂)."""
        container = tk.Frame(parent)
        for part in re.split(r'([♀♂])', text):
            if not part:
                continue
            font = bold_font if part in ("♀", "♂") else base_font
            tk.Label(container, text=part, font=font).pack(side="left")
        return container

    # ========================================================================
    # Pollen Tab
    # ========================================================================

    def _build_pollen_tab(self):
        """Build the pollen tab UI."""
        # Clear and rebuild
        for widget in self.pollen_frame.winfo_children():
            widget.destroy()
        
        # Header with pagination controls
        header = tk.Frame(self.pollen_frame)
        header.pack(fill="x")

        # Refresh button
        try:
            if self.app is not None:
                btn_refresh = tk.Button(
                    header,
                    text="Refresh",
                    command=self.refresh_current_tab,
                    **self.app.button_style,
                )
                self.app._apply_hover(btn_refresh)
            else:
                btn_refresh = tk.Button(header, text="Refresh", command=self.refresh_current_tab)
            btn_refresh.pack(side="right")
        except Exception:
            pass

        # Previous button
        if self.app is not None:
            self.pln_prev = tk.Button(
                header,
                text="◀ Prev",
                command=self._pollen_prev,
                **self.app.button_style,
            )
            self.app._apply_hover(self.pln_prev)
        else:
            self.pln_prev = tk.Button(header, text="◀ Prev", command=self._pollen_prev)
        self.pln_prev.pack(side="left")

        # Page label
        self.pln_page_label = tk.Label(header, text="")
        self.pln_page_label.pack(side="left", padx=8)

        # Next button
        if self.app is not None:
            self.pln_next = tk.Button(
                header,
                text="Next ▶",
                command=self._pollen_next,
                **self.app.button_style,
            )
            self.app._apply_hover(self.pln_next)
        else:
            self.pln_next = tk.Button(header, text="Next ▶", command=self._pollen_next)
        self.pln_next.pack(side="right")

        # Grid for pollen groups
        self.pln_grid = tk.Frame(self.pollen_frame)
        self.pln_grid.pack(fill="both", expand=True, pady=(8, 0))

        self._render_pollen_page()

    def _render_pollen_page(self):
        """Render the current page of pollen groups."""
        # Legend (STALE badge explanation)
        if getattr(self, "_pollen_legend", None) is None or not self._pollen_legend.winfo_exists():
            self._pollen_legend = tk.Frame(self.pollen_frame)
            self._pollen_legend._is_legend = True
            self._pollen_legend.pack(fill="x", padx=6, pady=(4, 4))
            
            badge = tk.Label(
                self._pollen_legend,
                text="STALE",
                fg="#b45309",
                bg="#fff7ed",
                bd=1,
                relief="solid",
                font=("Segoe UI", 12)
            )
            badge.pack(side="left", padx=(0, 4))
            
            tk.Label(
                self._pollen_legend,
                text=" Pollen is viable only on the day it is collected",
            ).pack(side="left")
        else:
            # Ensure legend stays on top
            try:
                self._pollen_legend.pack_forget()
            except Exception:
                pass
            self._pollen_legend.pack(fill="x", padx=6, pady=(4, 4))

        # Clear grid
        for widget in self.pln_grid.winfo_children():
            widget.destroy()

        # Get pollen and group by source plant
        if isinstance(self.inventory, list):
            # Summary window mode - get from app inventory
            try:
                if getattr(self, "app", None) is not None and hasattr(self.app, "inventory"):
                    items = self.app.inventory.get_all("pollen")
                else:
                    items = []
            except Exception:
                items = []
        else:
            items = self.inventory.get_all("pollen")

        groups = defaultdict(list)
        for pollen in items:
            source_id = int(getattr(pollen, "source_id", 0) or 0)
            groups[source_id].append(pollen)

        keys = sorted(groups.keys())
        total = len(keys)
        
        # Clamp page index
        if total > 0:
            max_page = (total - 1) // self.MAX_PER_PAGE_POLLEN
            if self.pollen_page > max_page:
                self.pollen_page = max_page

        start = self.pollen_page * self.MAX_PER_PAGE_POLLEN
        end = min(total, start + self.MAX_PER_PAGE_POLLEN)

        # Update page label
        if total:
            self.pln_page_label.configure(text=f"Pollen groups {start + 1}-{end} of {total}")
        else:
            self.pln_page_label.configure(text="No pollen packets yet")

        # Show empty message if no pollen
        if total == 0:
            frame = tk.Frame(self.pln_grid, borderwidth=1, relief="groove", padx=6, pady=12)
            frame.pack(fill="x", expand=True, padx=6, pady=6)
            tk.Label(frame, text="No pollen collected yet.", font=("Segoe UI", 12)).pack()
            return

        # Get current day for viability check
        today = getattr(self.app.garden, 'day_of_month', 
                       getattr(self.app.garden, 'day', 0)) if self.app and hasattr(self.app, 'garden') else 0

        # Display pollen groups
        shown = keys[start:end]
        for i, source_id in enumerate(shown):
            packets = groups[source_id]
            self._render_pollen_group(i, source_id, packets, today)

        # Fill empty slots
        slots = max(0, min(self.MAX_PER_PAGE_POLLEN, total - start))
        for j in range(slots, self.MAX_PER_PAGE_POLLEN):
            frame = tk.Frame(
                self.pln_grid,
                borderwidth=1,
                relief="groove",
                padx=6,
                pady=6,
                width=160,
                height=90
            )
            frame.grid(row=j // 3, column=j % 3, padx=6, pady=6, sticky="nsew")
            frame.pack_propagate(False)
            tk.Label(frame, text="Empty").pack()

    def _render_pollen_group(self, index: int, source_id: int, packets: list, today: int):
        """Render a single pollen group in the grid."""
        frame = tk.Frame(self.pln_grid, borderwidth=1, relief="groove", padx=6, pady=6)
        frame.grid(row=index // 3, column=index % 3, padx=6, pady=6, sticky="nsew")

        # Header row with title and ✕ button
        header = tk.Frame(frame)
        header.pack(fill="x", anchor="w")

        title = f"Pollen #{source_id} — x{len(packets)}"
        tk.Label(header, text=title, font=("Segoe UI", 12, "bold")).pack(side="left", anchor="w")

        # Discard all pollen from this group
        def delete_all_pollen():
            try:
                inv = self.app.inventory if (self.app and hasattr(self.app, "inventory")) else \
                      (self.inventory if not isinstance(self.inventory, list) else None)
                if inv is None:
                    return
                
                for pollen in list(inv.get_all("pollen")):
                    if int(getattr(pollen, "source_id", 0) or 0) == int(source_id):
                        inv.remove(pollen)
                
                if hasattr(self.app, "_toast"):
                    self.app._toast(f"Deleted pollen from plant #{source_id}.")
            except Exception:
                pass
            self._render_pollen_page()

        discard_btn = tk.Button(
            header,
            text="✕",
            width=2,
            fg="red",
            command=delete_all_pollen,
            **(self.app.button_style if self.app else {}),
        )
        if self.app:
            self.app._apply_hover(discard_btn)
        discard_btn.pack(side="right", anchor="e")

        # Check viability
        def get_expires_day(pkt):
            try:
                if isinstance(pkt, dict):
                    return int(pkt.get("expires_day", -999999))
                return int(getattr(pkt, "expires_day", -999999))
            except Exception:
                return -999999

        viable = [p for p in packets if get_expires_day(p) == today]

        # Viability info
        tk.Label(frame, text=f"Viable today: {len(viable)}").pack(anchor="w")

        # STALE badge if no viable pollen
        if len(viable) == 0 and len(packets) > 0 and today is not None:
            badge_row = tk.Frame(frame)
            badge_row.pack(fill="x", pady=(4, 0))

            tk.Label(
                badge_row,
                text="STALE",
                fg="#b45309",
                bg="#fff7ed",
                bd=1,
                relief="solid",
                font=("Segoe UI", 10, "bold"),
                padx=6,
                pady=2,
            ).pack(side="left")

            tk.Label(
                badge_row,
                text=" (not usable)",
                font=("Segoe UI", 10),
                fg="#666666",
            ).pack(side="left")

            # Show how long expired
            try:
                exp = min(get_expires_day(p) for p in packets)
                days_expired = int(today) - int(exp)
                if days_expired > 0:
                    tk.Label(
                        badge_row,
                        text=f"  (expired {days_expired} day{'s' if days_expired != 1 else ''} ago)",
                        font=("Segoe UI", 10),
                        fg="#666666",
                    ).pack(side="left")
            except Exception:
                pass

        # Use button (enabled only if viable pollen exists)
        pkt = viable[0] if viable else None
        
        if self.app is not None:
            use_btn = tk.Button(
                frame,
                text="    Use    ",
                fg="green",
                state=("normal" if pkt is not None else "disabled"),
                command=(lambda p=pkt: self._use_pollen(p)) if pkt is not None else None,
                **self.app.button_style,
            )
            self.app._apply_hover(use_btn)
        else:
            use_btn = tk.Button(
                frame,
                text="Use",
                state=("normal" if pkt is not None else "disabled"),
                command=(lambda p=pkt: self._use_pollen(p)) if pkt is not None else None,
            )

        use_btn.pack(pady=(6, 0), anchor="center")
    
    def _use_pollen(self, packet):
        """Apply pollen to selected plant."""
        try:
            if self.app and callable(getattr(self.app, "_apply_pollen", None)):
                self.app._apply_pollen(packet)
                self._render_pollen_page()
        except Exception:
            pass

    def _pollen_prev(self):
        """Go to previous page of pollen."""
        if self.pollen_page > 0:
            self.pollen_page -= 1
            self._render_pollen_page()

    def _pollen_next(self):
        """Go to next page of pollen."""
        # Get pollen and group to count total groups
        try:
            if isinstance(self.inventory, list):
                items = self.app.inventory.get_all("pollen") if (self.app and hasattr(self.app, "inventory")) else []
            else:
                items = self.inventory.get_all("pollen")
        except Exception:
            items = []

        groups = defaultdict(list)
        for pollen in items:
            groups[int(getattr(pollen, "source_id", 0) or 0)].append(pollen)

        total_groups = len(groups)

        if (self.pollen_page + 1) * self.MAX_PER_PAGE_POLLEN < total_groups:
            self.pollen_page += 1
            self._render_pollen_page()

    # ========================================================================
    # Seeds Tab
    # ========================================================================

    def _build_seeds_tab(self):
        """Build the seeds tab UI."""
        # Header with pagination controls
        header = tk.Frame(self.seeds_frame)
        header.pack(fill="x", pady=(0, 8))

        # Previous button
        if self.app is not None:
            self.sd_prev = tk.Button(
                header,
                text="◀ Prev",
                command=self._seeds_prev,
                **self.app.button_style,
            )
            self.app._apply_hover(self.sd_prev)
        else:
            self.sd_prev = tk.Button(header, text="◀ Prev", command=self._seeds_prev)
        self.sd_prev.pack(side="left")

        # Page label
        self.sd_page_label = tk.Label(header, text="")
        self.sd_page_label.pack(side="left", padx=8)

        # Next button
        if self.app is not None:
            self.sd_next = tk.Button(
                header,
                text="Next ▶",
                command=self._seeds_next,
                **self.app.button_style,
            )
            self.app._apply_hover(self.sd_next)
        else:
            self.sd_next = tk.Button(header, text="Next ▶", command=self._seeds_next)
        self.sd_next.pack(side="right")

        # Grid for seed groups
        self.sd_grid = tk.Frame(self.seeds_frame)
        self.sd_grid.pack(fill="both", expand=True, pady=(8, 0))

        self._render_seeds_page()

    def _render_seeds_page(self):
        """Render the current page of seed groups."""
        # Clear existing widgets
        for widget in self.sd_grid.winfo_children():
            widget.destroy()

        # Get seeds - handle both list mode (summary window) and Inventory mode
        if isinstance(self.inventory, list):
            inventory = list(self.inventory)
        else:
            # Inventory object - get seeds
            inventory = self.inventory.get_all('seeds') if hasattr(self.inventory, 'get_all') else []
        
        # Group by (cross_type, source_id, donor_id)
        groups = defaultdict(list)
        for seed in inventory:
            # Handle both dict and object access
            if hasattr(seed, 'get'):
                donor = seed.get('donor_id')
                source = seed.get('source_id')
            else:
                donor = getattr(seed, 'donor_id', None)
                source = getattr(seed, 'source_id', 0)
            
            key = ('X' if donor else 'H', source, donor)
            groups[key].append(seed)

        keys = list(groups.keys())
        total = len(keys)

        # Clamp page index
        if total > 0:
            max_page = (total - 1) // self.MAX_PER_PAGE_SEEDS
            if self.seeds_page > max_page:
                self.seeds_page = max_page

        start = self.seeds_page * self.MAX_PER_PAGE_SEEDS
        end = min(total, start + self.MAX_PER_PAGE_SEEDS)

        # Update page label
        if total:
            self.sd_page_label.configure(text=f"Seed groups {start + 1}-{end} of {total}")
        else:
            self.sd_page_label.configure(text="No seeds yet")

        # Show empty message if no seeds
        if total == 0:
            frame = tk.Frame(self.sd_grid, borderwidth=1, relief="groove", padx=6, pady=12)
            frame.pack(fill="x", expand=True, padx=6, pady=6)
            tk.Label(frame, text="No harvested seeds yet.", font=("Segoe UI", 12)).pack()
            return

        # Display seed groups
        shown = keys[start:end]
        for i, key in enumerate(shown):
            items = groups[key]
            self._render_seed_group(i, key, items)

        # Fill empty slots
        slots = max(0, min(self.MAX_PER_PAGE_SEEDS, total - start))
        for j in range(slots, self.MAX_PER_PAGE_SEEDS):
            frame = tk.Frame(
                self.sd_grid,
                borderwidth=1,
                relief="groove",
                padx=6,
                pady=6,
                width=160,
                height=90
            )
            frame.grid(row=j // 3, column=j % 3, padx=6, pady=6, sticky="nsew")
            frame.pack_propagate(False)
            tk.Label(frame, text="Empty").pack()

    def _render_seed_group(self, index: int, key: tuple, items: list):
        """Render a single seed group in the grid."""
        kind, source_id, donor_id = key
        title = f"♀#{source_id} × ♂#{donor_id}" if kind == 'X' else f"Seed #{source_id}"
        
        frame = tk.Frame(self.sd_grid, borderwidth=1, relief="groove", padx=6, pady=6)
        frame.grid(row=index // 3, column=index % 3, padx=6, pady=6, sticky="nsew")
        
        # Header row
        header = tk.Frame(frame)
        header.pack(fill="x", anchor="w")

        # Title
        self._label_with_bold_gender(
            header,
            f"{title} — x{len(items)}",
            base_font=("Segoe UI", 12),
            bold_font=("Segoe UI", 12, "bold"),
        ).pack(side="left", anchor="w")

        # Discard button
        def discard_group():
            before = len(self.inventory)
            
            # Filter out seeds from this group
            if isinstance(self.inventory, list):
                # List mode - filter in place
                self.inventory[:] = [
                    s for s in self.inventory
                    if not self._seed_matches_group(s, kind, source_id, donor_id)
                ]
            else:
                # Inventory object mode
                for seed in list(items):
                    try:
                        self.inventory.remove(seed)
                    except Exception:
                        pass
            
            removed = before - len(self.inventory)
            if removed > 0 and self.app and hasattr(self.app, "_toast"):
                self.app._toast(f"Discarded {removed} seeds.")
            self._render_seeds_page()

        discard_btn = tk.Button(
            header,
            text="✕",
            width=2,
            fg="red",
            command=discard_group,
            **(self.app.button_style if self.app else {}),
        )
        
        if self.app:
            self.app._apply_hover(discard_btn)
        
        discard_btn.pack(side="right", anchor="e")

        # Seed trait icons
        first_seed = items[0]
        if hasattr(first_seed, 'get'):
            traits = first_seed.get("traits", {}) or {}
        else:
            traits = getattr(first_seed, 'traits', {}) or {}
        
        self._render_seed_icons(frame, traits)

        # ── Plant buttons row: "Plant (n)" + "Plant ALL" ──────────────────────────
        match_fn = lambda s, k=kind, sid=source_id, did=donor_id: self._seed_matches_group(s, k, sid, did)
        count = sum(1 for s in self.inventory if match_fn(s)) if not isinstance(self.inventory, list)             else sum(1 for s in self.inventory if match_fn(s))

        btn_row = tk.Frame(frame)
        btn_row.pack(fill="x", pady=(6, 0))

        bstyle = self.app.button_style if self.app else {}

        # Entry + "Plant (n)" -------------------------------------------------
        plant_n_frame = tk.Frame(btn_row)
        plant_n_frame.pack(side="left", padx=(0, 4))

        entry_n = tk.Entry(plant_n_frame, width=4, font=("Segoe UI", 9))
        entry_n.pack(side="left", padx=(0, 2))
        entry_n.insert(0, str(count))

        def _plant_n(k=kind, mf=match_fn, entry=entry_n):
            try:
                n = int(entry.get().strip())
                if n <= 0:
                    raise ValueError
            except ValueError:
                if self.app:
                    self.app._toast("Enter a valid positive number.", level="warn")
                return
            if self.app and hasattr(self.app, "_on_plant_n_from_group"):
                self.app._on_plant_n_from_group(k, mf, n)
                self._render_seeds_page()
            elif callable(self.on_seed_selected):
                # fallback: plant one
                for seed in list(self.inventory):
                    if mf(seed):
                        self.on_seed_selected(seed)
                        self._render_seeds_page()
                        break

        b_plant_n = tk.Button(
            plant_n_frame,
            text="Plant (n)",
            fg="green",
            state=("normal" if count > 0 else "disabled"),
            command=_plant_n,
            **bstyle,
        )
        if self.app:
            self.app._apply_hover(b_plant_n)
        b_plant_n.pack(side="left")

        # "Plant ALL" ---------------------------------------------------------
        def _plant_all(k=kind, mf=match_fn):
            if self.app and hasattr(self.app, "_on_plant_area_from_group"):
                self.app._on_plant_area_from_group(k, mf)
                self._render_seeds_page()
            elif callable(self.on_seed_selected):
                for seed in list(self.inventory):
                    if mf(seed):
                        self.on_seed_selected(seed)
                self._render_seeds_page()

        b_all = tk.Button(
            btn_row,
            text="Plant ALL",
            fg="green",
            state=("normal" if count > 0 else "disabled"),
            command=_plant_all,
            **bstyle,
        )
        if self.app:
            self.app._apply_hover(b_all)
        b_all.pack(side="left")
    
    def _seed_matches_group(self, seed, kind, source_id, donor_id):
        """Check if a seed matches a group key."""
        # Handle both dict and object access
        if hasattr(seed, 'get'):
            s_donor = seed.get("donor_id")
            s_source = seed.get("source_id")
        else:
            s_donor = getattr(seed, "donor_id", None)
            s_source = getattr(seed, "source_id", 0)
        
        if kind == 'X':
            return s_donor == donor_id and s_source == source_id
        else:
            return not s_donor and s_source == source_id

    def _render_seed_icons(self, parent, traits: dict):
        """Render trait icons for a seed."""
        icon_row = tk.Frame(parent)
        icon_row.pack(anchor="w", pady=(4, 2))

        # Keep image references alive
        if not hasattr(self, "_img_refs"):
            self._img_refs = []

        def add_trait_icon(trait_key, value):
            if not value:
                return False
            try:
                path = trait_icon_path(trait_key, value)
                if path:
                    img = safe_image(path)
                    label = tk.Label(icon_row, image=img)
                    label.image = img
                    label.pack(side="left", padx=(0, 6))
                    self._img_refs.append(img)
                    return True
            except Exception:
                pass
            return False

        shown_any = False

        # Show seed_color only (seed_shape icon not needed)
        if isinstance(traits, dict):
            shown_any |= add_trait_icon("seed_color", traits.get("seed_color"))
        else:
            shown_any |= add_trait_icon("seed_color", getattr(traits, "seed_color", None))

        if not shown_any:
            tk.Label(parent, text="• (no seed preview)", fg="#666666").pack(anchor="w")

    def _label_with_bold_gender(self, parent, text, base_font, bold_font):
        """Create a label with bold gender symbols (♀, ♂)."""
        label = tk.Label(parent, text=text, font=base_font)
        
        # This is a simplified version - you may want to implement
        # actual bold rendering for ♀ and ♂ symbols if needed
        
        return label

    def _seeds_prev(self):
        """Go to previous page of seeds."""
        if self.seeds_page > 0:
            self.seeds_page -= 1
            self._render_seeds_page()

    def _seeds_next(self):
        """Go to next page of seeds."""
        # Get seeds and count groups
        if isinstance(self.inventory, list):
            inventory = list(self.inventory)
        else:
            inventory = self.inventory.get_all('seeds') if hasattr(self.inventory, 'get_all') else []
        
        # Group to count total
        groups = defaultdict(list)
        for seed in inventory:
            if hasattr(seed, 'get'):
                donor = seed.get('donor_id')
                source = seed.get('source_id')
            else:
                donor = getattr(seed, 'donor_id', None)
                source = getattr(seed, 'source_id', 0)
            
            key = ('X' if donor else 'H', source, donor)
            groups[key].append(seed)
        
        total_groups = len(groups)
        
        if (self.seeds_page + 1) * self.MAX_PER_PAGE_SEEDS < total_groups:
            self.seeds_page += 1
            self._render_seeds_page()

    def _plant(self, seed):
        """Plant a seed and close the popup."""
        if callable(self.on_seed_selected):
            self.on_seed_selected(seed)
        self.destroy()


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
        try:
            self.attributes("-topmost", True)
            self.lift()
        except Exception:
            pass

        self.app   = app
        self.page  = 0
        self._img_refs = []

        self.title("Choose Pollen")
        self.geometry("800x700")
        self.resizable(True, True)

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

        # ── Header: title (left) + ✕ (right) ────────────────────────────────
        hdr = tk.Frame(card)
        hdr.pack(fill="x")

        tk.Label(hdr, text=f"from Plant #{source_id}",
                 font=("Segoe UI", 11, "bold")).pack(side="left")

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

        btn_x = tk.Button(hdr, text="✕", width=2, fg="red",
                          command=_discard, **bstyle)
        if self.app:
            self.app._apply_hover(btn_x)
        btn_x.pack(side="right")

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
                self.app._apply_pollen(p)
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
