    
from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import List, Literal

import tkinter as tk
from tkinter import Toplevel, ttk

from plant import Plant, STAGE_NAMES
from icon_loader import *

@dataclass
class InventoryItem:
    name: str
    id: int
    # attribs: dict = field(default_factory=dict)
    # hidden_attribs: dict = field(default_factory=dict)
    # quantity: int = 1

@dataclass
class Seed(InventoryItem):
    source_id: int
    donor_id: int | None
    traits: dict
    generation: int
    pod_index: int
    genotype: dict
    ancestry: List

    def plant(self) -> Plant:
        # Create a new Plant instance based on the seed's species and traits
        new_plant = Plant(species=self.species, traits=self.attribs)
        return new_plant
    
    def __repr__(self):
        return f"Seed({self.label}, Traits: {self.traits})"

    def is_selfed(self) -> bool:
        return self.donor_id is None

    def get(self, key, default=None):
        return getattr(self, key, default)
    
@dataclass
class Pollen(InventoryItem):
    source_plant: Plant
    collection_time: int

    # --- fields used by the Summary/Pollen tab ---
    source_id: int = 0
    collected_day: int = 0
    expires_day: int = 0
    genotype: dict = field(default_factory=dict)
    traits: dict = field(default_factory=dict)

    def __post_init__(self):
        # derive metadata from the source plant if possible
        try:
            self.source_id = int(getattr(self.source_plant, "id", 0) or 0)
        except Exception:
            self.source_id = 0
        try:
            if not self.genotype:
                g = getattr(self.source_plant, "genotype", None)
                if isinstance(g, dict):
                    self.genotype = dict(g)
        except Exception:
            pass
        try:
            if not self.traits:
                t = getattr(self.source_plant, "traits", None)
                if isinstance(t, dict):
                    self.traits = dict(t)
        except Exception:
            pass

    def __repr__(self):
        return f"Pollen(source_id={self.source_id}, collected_day={self.collected_day}, expires_day={self.expires_day})"

    def get(self, key, default=None):
        """
        Behave like dict.get():
        - return pollen packet fields first
        - fallback to source_plant fields if needed
        """
        if hasattr(self, key):
            return getattr(self, key, default)
        try:
            return getattr(self.source_plant, key, default)
        except Exception:
            return default


class Inventory():
    
    def __init__(self):
        self._items_misc: List[InventoryItem] = []
        self._items_seeds: List[Seed] = []
        self._items_pollen: List[Pollen] = []

    def add(self, item: InventoryItem):
        if isinstance(item, Seed):
            self._items_seeds.append(item)
        elif isinstance(item, Pollen):
            self._items_pollen.append(item)
        else:
            self._items_misc.append(item)
    
    def remove(self, item: InventoryItem):
        if isinstance(item, Seed):
            self._items_seeds.remove(item)
        elif isinstance(item, Pollen):
            self._items_pollen.remove(item)
        else:
            self._items_misc.remove(item)

    def get_all(self, type: Literal['misc', 'seeds', 'pollen']) -> List[InventoryItem]:
        if type == 'misc':
            return self._items_misc
        elif type == 'seeds':
            return self._items_seeds
        elif type == 'pollen':
            return self._items_pollen
        else:
            raise ValueError("Invalid inventory type. Choose from 'misc', 'seeds', or 'pollen'.")
        

class InventoryPopup(Toplevel):
    
    def __init__(self, master, garden, inventory: Inventory, on_seed_selected, 
                 app=None, initial_tab=None):
        super().__init__(master)
        try:
            self.attributes("-topmost", True)
            self.lift()
        except Exception:
            pass

        # Keep a direct reference to the GardenApp if provided
        self.app = app
        # Backward-compat: try to discover app from master if not provided
        if self.app is None:
            try:
                self.app = master.master  # may have been set externally
            except Exception:
                self.app = None
        self.title("Summary")
        self.garden = garden
        self.inventory = inventory
        self.on_seed_selected = on_seed_selected

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # # Plants tab
        # self.plants_frame = tk.Frame(self.nb, padx=8, pady=8)
        # self.nb.add(self.plants_frame, text="Plants")
        # self.plants_page = 0
        # self._build_plants_tab()

        # Seeds tab
        self.seeds_frame = tk.Frame(self.nb, padx=8, pady=8)
        self.nb.add(self.seeds_frame, text="Seeds")
        self.seeds_page = 0
        self._build_seeds_tab()
        # Pollen tab
        self.pollen_frame = tk.Frame(self.nb, padx=8, pady=8)
        self.nb.add(self.pollen_frame, text="Pollen")
        self.pollen_page = 0
        self._build_pollen_tab()
        # Select initial tab if requested
        try:
            if initial_tab == 'Pollen':
                self.nb.select(self.pollen_frame)
            elif initial_tab == 'Seeds':
                self.nb.select(self.seeds_frame)
        except Exception:
            pass


    def refresh_current_tab(self):
        """Re-render whichever tab is currently selected."""
        try:
            current = self.nb.select()
        except Exception:
            current = None
        try:
            if current and hasattr(self, "pollen_frame") and str(current) == str(self.pollen_frame):
                self._render_pollen_page()
                return
            if current and hasattr(self, "seeds_frame") and str(current) == str(self.seeds_frame):
                self._render_seeds_page()
                return
            if current and hasattr(self, "plants_frame") and str(current) == str(self.plants_frame):
                self._render_plants_page()
                return

            # Fallback: try rendering all
            if hasattr(self, "_render_pollen_page"):
                self._render_pollen_page()
            if hasattr(self, "_render_seeds_page"):
                self._render_seeds_page()
            if hasattr(self, "_render_plants_page"):
                self._render_plants_page()
        except Exception:
            pass
        try:
            current = self.nb.select()
        except Exception:
            current = None
        try:
            # Pollen tab
            if current and hasattr(self, "pollen_frame") and str(current) == str(self.pollen_frame):
                try:
                    self._render_pollen_page()
                    return
                except Exception:
                    pass
            # Seeds tab
            if current and hasattr(self, "seeds_frame") and str(current) == str(self.seeds_frame):
                try:
                    self._render_seeds_page()
                    return
                except Exception:
                    pass
            # Plants tab
            if current and hasattr(self, "plants_frame") and str(current) == str(self.plants_frame):
                try:
                    self._render_plants_page()
                    return
                except Exception:
                    pass
            # Fallback: try rendering all
            try:
                if hasattr(self, "_render_pollen_page"): self._render_pollen_page()
            except Exception: pass
            try:
                if hasattr(self, "_render_seeds_page"): self._render_seeds_page()
            except Exception: pass
            try:
                if hasattr(self, "_render_plants_page"): self._render_plants_page()
            except Exception: pass
        except Exception:
            pass
    def _label_with_bold_gender(self, parent, text, base_font=("Segoe UI", 12), bold_font=("Segoe UI", 12, "bold")):
        c = tk.Frame(parent)
        for part in re.split(r'([♀♂])', text):
            if not part:
                continue
            tk.Label(c, text=part, font=bold_font if part in ("♀","♂") else base_font).pack(side="left")
        return c

    MAX_PER_PAGE_PLANTS = 6
    MAX_PER_PAGE_SEEDS = 9

    # ---- Pollen tab ----
    MAX_PER_PAGE_POLLEN = 9
    def _build_pollen_tab(self):
        # header & nav
        for w in self.pollen_frame.winfo_children():
            w.destroy()
        header = tk.Frame(self.pollen_frame)
        header.pack(fill="x")

        # Refresh button – same style as Seeds tab
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

        # ◀ Prev
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

        # Next ▶
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

        self.pln_grid = tk.Frame(self.pollen_frame)
        self.pln_grid.pack(fill="both", expand=True, pady=(8,0))
        self._render_pollen_page()

    def _render_pollen_page(self):
        # Legend: STALE badge explanation (singleton)
        if getattr(self, "_pollen_legend", None) is None or not self._pollen_legend.winfo_exists():
            self._pollen_legend = tk.Frame(self.pollen_frame)
            self._pollen_legend._is_legend = True
            self._pollen_legend.pack(fill="x", padx=6, pady=(4,4))
            badge = tk.Label(self._pollen_legend, text="STALE", fg="#b45309", bg="#fff7ed", bd=1, relief="solid", font=("Segoe UI",12))
            badge.pack(side="left", padx=(0,4))
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
            self._pollen_legend.pack(fill="x", padx=6, pady=(4,4))

        # Clear
        for w in self.pln_grid.winfo_children():
            w.destroy()

        # Gather and group
        # InventoryPopup can be opened either with a real Inventory() (pollination window)
        # or with a plain list of harvested seed dicts (summary window). Handle both.
        if isinstance(self.inventory, list):
            # Try to show pollen from the main app inventory if available; otherwise show none.
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
        for p in items:
            # group by plant id (int) so UI doesn't print full Plant(...)
            groups[int(getattr(p, "source_id", 0) or 0)].append(p)


        keys = sorted(groups.keys(), key=lambda x: (x is None, x))
        total = len(keys)
        start = self.pollen_page * self.MAX_PER_PAGE_POLLEN
        end = min(total, start + self.MAX_PER_PAGE_POLLEN)
        self.pln_page_label.configure(text=f"Pollen groups {start+1}-{end} of {total}" if total else "No pollen packets yet")

        if total == 0:
            f = tk.Frame(self.pln_grid, borderwidth=1, relief="groove", padx=6, pady=12)
            f.pack(fill="x", expand=True, padx=6, pady=6)
            tk.Label(f, text="No pollen collected yet.", font=("Segoe UI", 12)).pack()
            return

        today = getattr(self.app.garden, 'day', None) if self.app else None

        shown = keys[start:end]
        for i, src in enumerate(shown):
            packets = groups[src]

            f = tk.Frame(self.pln_grid, borderwidth=1, relief="groove", padx=6, pady=6)
            f.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew")

            # --- Header row: title + ✕ (Seeds-style) ---
            header = tk.Frame(f)
            header.pack(fill="x", anchor="w")

            title = f"Pollen #{src} — x{len(packets)}"
            tk.Label(header, text=title, font=("Segoe UI", 12, "bold")).pack(side="left", anchor="w")

            def delete_all_pollen_from_group(_src=src):
                try:
                    inv = self.app.inventory if (self.app and hasattr(self.app, "inventory")) else (self.inventory if not isinstance(self.inventory, list) else None)
                    if inv is None:
                        return
                    for p in list(inv.get_all("pollen")):
                        if int(getattr(p, "source_id", 0) or 0) == int(_src):
                            inv.remove(p)
                    if hasattr(self.app, "_toast"):
                        self.app._toast(f"Deleted pollen from plant #{_src}.")
                except Exception:
                    pass
                self._render_pollen_page()

            discard_btn = tk.Button(
                header,
                text="✕",
                width=2,
                fg="red",
                command=delete_all_pollen_from_group,
                **(self.app.button_style if self.app else {}),
            )
            if self.app:
                self.app._apply_hover(discard_btn)
            discard_btn.pack(side="right", anchor="e")

            def _as_int(x, default=0):
                try:
                    return int(x)
                except Exception:
                    return default

            # --- Info line ---
            today = _as_int(
                getattr(self.app.garden, "day_of_month",
                        getattr(self.app.garden, "day", 0)),
                default=-1
            )

            def get_field(pkt, key, default=None):
                if isinstance(pkt, dict):
                    return pkt.get(key, default)
                return getattr(pkt, key, default)

            viable = [pp for pp in packets if _as_int(get_field(pp, "expires_day", -999999), -999999) == today]

            tk.Label(f, text=f"Viable today: {len(viable)}").pack(anchor="w")

            # --- STALE badge + age info ---
            if len(viable) == 0 and len(packets) > 0 and today is not None:
                badge_row = tk.Frame(f)
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

                # Show how long it's expired (based on expires_day)
                try:
                    exp = min(_as_int(pp.get("expires_day"), today) for pp in packets)
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

            # --- Pick packet to use (FRESH ONLY) ---
            pkt = viable[0] if viable else None

            # --- Use button (enabled only if viable pollen exists) ---
            if self.app is not None:
                use_btn = tk.Button(
                    f,
                    text="    Use    ",
                    fg="green",
                    state=("normal" if pkt is not None else "disabled"),
                    command=(lambda p=pkt: self._use_pollen(p)) if pkt is not None else None,
                    **self.app.button_style,
                )
                self.app._apply_hover(use_btn)
            else:
                use_btn = tk.Button(
                    f,
                    text="Use",
                    state=("normal" if pkt is not None else "disabled"),
                    command=(lambda p=pkt: self._use_pollen(p)) if pkt is not None else None,
                )

            use_btn.pack(pady=(6, 0), anchor="center")

    def _pollen_prev(self):
        if self.pollen_page > 0:
            self.pollen_page -= 1
            self._render_pollen_page()

    def _pollen_next(self):
        # Total groups (same grouping logic as _render_pollen_page)
        try:
            if isinstance(self.inventory, list):
                items = self.app.inventory.get_all("pollen") if (self.app and hasattr(self.app, "inventory")) else []
            else:
                items = self.inventory.get_all("pollen")
        except Exception:
            items = []

        groups = defaultdict(list)
        for p in items:
            groups[int(getattr(p, "source_id", 0) or 0)].append(p)

        total_groups = len(groups)

        if (self.pollen_page + 1) * self.MAX_PER_PAGE_POLLEN < total_groups:
            self.pollen_page += 1
            self._render_pollen_page()

    def _use_pollen(self, packet):
        try:
            if self.app and callable(getattr(self.app, "_apply_pollen", None)):
                self.app._apply_pollen(packet)
                self._render_pollen_page()
        except Exception:
            pass

    # ---- Plants tab ----
    def _build_plants_tab(self):
        # header & nav
        header = tk.Frame(self.plants_frame)
        header.pack(fill="x")
        try:
            tk.Button(header, text='Refresh', command=self.refresh_current_tab).pack(side='right')
        except Exception:
            pass
        self.pl_prev = tk.Button(header, text="◀ Prev", command=self._plants_prev)
        self.pl_prev.pack(side="left")
        self.pl_page_label = tk.Label(header, text="")
        self.pl_page_label.pack(side="left", padx=8)
        self.pl_next = tk.Button(header, text="Next ▶", command=self._plants_next)
        self.pl_next.pack(side="right")

        self.pl_grid = tk.Frame(self.plants_frame)
        self.pl_grid.pack(fill="both", expand=True, pady=(8,0))

        self._render_plants_page()

    def _render_plants_page(self):
        for w in self.pl_grid.winfo_children():
            w.destroy()

        living = [p for p in self.garden.plants if p and p.alive]
        total = len(living)
        start = self.plants_page * self.MAX_PER_PAGE_PLANTS
        end = min(total, start + self.MAX_PER_PAGE_PLANTS)

        self.pl_page_label.configure(text=f"Plants {start+1}-{end} of {total}" if total else "No living plants")

        for i, idx in enumerate(range(start, end)):
            p = living[idx]
            f = tk.Frame(self.pl_grid, borderwidth=1, relief="groove", padx=6, pady=6)
            f.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew")
            title = f"Plant #{p.id} ({p.generation}) — {STAGE_NAMES.get(p.stage, p.stage)}"
            tk.Label(f, text=title, font=("Segoe UI", 12, "bold")).pack(anchor="w")
            tk.Label(f, text=f"H{p.health} W{p.water}").pack(anchor="w")
            if p.revealed_traits:
                for k in ("flower_position", "flower_color", "pod_color"):
                    if k in p.revealed_traits:
                        tk.Label(f, text=f"• {k}: {p.revealed_traits[k]}").pack(anchor="w")
            else:
                tk.Label(f, text="(no traits discovered)").pack(anchor="w")

    def _plants_prev(self):
        if self.plants_page > 0:
            self.plants_page -= 1
            self._render_plants_page()

    def _plants_next(self):
        living = [p for p in self.garden.plants if p and p.alive]
        if (self.plants_page + 1) * self.MAX_PER_PAGE_PLANTS < len(living):
            self.plants_page += 1
            self._render_plants_page()

    # ---- Seeds tab ----
    def _build_seeds_tab(self):
        header = tk.Frame(self.seeds_frame)
        header.pack(fill="x")

        # Optional: Refresh button (can also be styled if you like)
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

        # ◀ Prev
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

        # Next ▶
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



        self.sd_grid = tk.Frame(self.seeds_frame)
        self.sd_grid.pack(fill="both", expand=True, pady=(8,0))

        self._render_seeds_page()
    def _render_seeds_page(self):
        for w in self.sd_grid.winfo_children():
            w.destroy()

        # Group by ('X', source_id, donor_id) vs ('H', source_id, None)
        inv = list(self.inventory) if isinstance(self.inventory, list) else []
        groups = defaultdict(list)
        for s in inv:
            k = ('X' if s.get('donor_id') else 'H', s.get('source_id'), s.get('donor_id'))
            groups[k].append(s)

        keys = list(groups.keys())
        total = len(keys)

        # Clamp page index so we never go past the last page
        if total > 0:
            max_page = (total - 1) // self.MAX_PER_PAGE_SEEDS
            if self.seeds_page > max_page:
                self.seeds_page = max_page

        start = self.seeds_page * self.MAX_PER_PAGE_SEEDS
        end = min(total, start + self.MAX_PER_PAGE_SEEDS)

        if total:
            self.sd_page_label.configure(text=f"Seed groups {start+1}-{end} of {total}")
        else:
            self.sd_page_label.configure(text="No seeds yet")

        if total == 0:
            f = tk.Frame(self.sd_grid, borderwidth=1, relief="groove", padx=6, pady=12)
            f.pack(fill="x", expand=True, padx=6, pady=6)
            tk.Label(f, text="No harvested seeds yet.", font=("Segoe UI", 12)).pack()
            return

        shown = keys[start:end]
        for i, key in enumerate(shown):
            items = groups[key]
            kind, src, donor = key
            title = f"♀#{src} × ♂#{donor}" if kind=='X' else f"Seed #{src}"
            f = tk.Frame(self.sd_grid, borderwidth=1, relief="groove", padx=6, pady=6)
            f.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="nsew")
            # --- Header row: title + discard (X) ---
            header = tk.Frame(f)
            header.pack(fill="x", anchor="w")

            # Title (left)
            self._label_with_bold_gender(
                header,
                f"{title} — x{len(items)}",
                base_font=("Segoe UI", 12),
                bold_font=("Segoe UI", 12, "bold"),
            ).pack(side="left", anchor="w")

            # Discard whole seed group (X button)
            def _discard_group(_kind=kind, _src=src, _donor=donor):
                before = len(self.inventory)
                self.inventory[:] = [
                    s for s in self.inventory
                    if not (
                        (_kind == 'X' and s.get("source_id") == _src and s.get("donor_id") == _donor)
                        or (_kind == 'H' and s.get("source_id") == _src and not s.get("donor_id"))
                    )
                ]
                removed = before - len(self.inventory)
                if removed > 0 and self.app and hasattr(self.app, "_toast"):
                    self.app._toast(f"Discarded {removed} seeds.")
                self._render_seeds_page()

            discard_btn = tk.Button(
                header,
                text="✕",
                width=2,
                fg="red",
                command=_discard_group,
                **(self.app.button_style if self.app else {}),
            )

            if self.app:
                self.app._apply_hover(discard_btn)

            discard_btn.pack(side="right", anchor="e")


            traits = items[0].get("traits", {}) or {}

            # --- Seed phenotype icons: seed_shape + seed_color ---
            icon_row = tk.Frame(f)
            icon_row.pack(anchor="w", pady=(4, 2))

            # Keep image references alive (Tk will otherwise drop them)
            if not hasattr(self, "_img_refs"):
                self._img_refs = []

            def _add_trait_icon(trait_key, value):
                if not value:
                    return False
                try:
                    p = trait_icon_path(trait_key, value)
                    if p:
                        img = safe_image(p)
                        lbl = tk.Label(icon_row, image=img)
                        lbl.image = img
                        lbl.pack(side="left", padx=(0, 6))
                        self._img_refs.append(img)
                        return True
                except Exception:
                    pass
                return False

            shown_any = False
            shown_any |= _add_trait_icon("seed_shape", traits.get("seed_shape"))
            shown_any |= _add_trait_icon("seed_color", traits.get("seed_color"))

            if not shown_any:
                tk.Label(f, text="• (no seed preview)", fg="#666666").pack(anchor="w")


            # Plant consumes one from that group
            def plant_one_from_group(_kind=kind, _src=src, _donor=donor):
                # pick first matching seed still present
                target = None
                idx = None
                for j, s in enumerate(self.inventory):
                    if (
                        (_kind == 'X' and s.get('donor_id') == _donor and s.get('source_id') == _src)
                        or (_kind == 'H' and (not s.get('donor_id')) and s.get('source_id') == _src)
                    ):
                        target = s
                        idx = j
                        break
                if target is None:
                    return
                if callable(self.on_seed_selected):
                    self.on_seed_selected(target)
                # on_seed_selected removes the seed from app.inventory
                self._render_seeds_page()

            if self.app is not None:
                btn = tk.Button(
                    f,
                    text="Plant on selected tile",
                    fg="green",
                    command=plant_one_from_group,
                    **self.app.button_style,
                )
                self.app._apply_hover(btn)
            else:
                btn = tk.Button(
                    f,
                    text="Plant on selected tile",
                    fg="green",
                    command=plant_one_from_group,
                )
            btn.pack(anchor="e", pady=(6,0))



            # NEW: delete all seeds in this group
            def _discard_seed_group(self, kind, src, donor):
                before = len(self.inventory)
                self.inventory[:] = [
                    s for s in self.inventory
                    if not (
                        (kind == 'X' and s.get("source_id") == src and s.get("donor_id") == donor)
                        or (kind == 'H' and s.get("source_id") == src and not s.get("donor_id"))
                    )
                ]
                removed = before - len(self.inventory)
                if removed and self.app and hasattr(self.app, "_toast"):
                    self.app._toast(f"Discarded {removed} seeds.")


        # Fill blanks (never allow negative)
        slots = max(0, min(self.MAX_PER_PAGE_SEEDS, total - start))
        for j in range(slots, self.MAX_PER_PAGE_SEEDS):
            f = tk.Frame(self.sd_grid, borderwidth=1, relief="groove", padx=6, pady=6, width=160, height=90)
            f.grid(row=j // 3, column=j % 3, padx=6, pady=6, sticky="nsew")
            f.pack_propagate(False)
            tk.Label(f, text="Empty").pack()

    def _plant(self, seed):
        if callable(self.on_seed_selected):
            self.on_seed_selected(seed)
        self.destroy()

    def _seeds_prev(self):
        if self.seeds_page > 0:
            self.seeds_page -= 1
            self._render_seeds_page()

    def _seeds_next(self):
        if (self.seeds_page + 1) * self.MAX_PER_PAGE_SEEDS < len(self.inventory):
            self.seeds_page += 1
            self._render_seeds_page()