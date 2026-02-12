"""
Garden of Inheritance - Pea Garden Genetics Simulator

Main application file for Mendel's Pea Garden simulation.
Provides a visual interface for exploring Mendelian genetics through
plant breeding experiments.

Overview:
---------
This application simulates a garden where users can plant, breed, and observe
pea plants to discover Mendelian genetics principles. The simulation includes:

Features:
---------
- Interactive garden grid with tile-based plant placement
- Real-time plant growth and development simulation
- Genetic trait inheritance (flower color, pod color, seed traits, height)
- Breeding mechanics (pollination, emasculation, self-pollination)
- Seed harvesting and inventory management
- Historical archive browser for pedigree analysis
- Mendelian law detection (Dominance, Segregation, Independent Assortment)
- Environmental simulation (weather, temperature, seasons)
- Day/night visual cycles
- Time controls (pause, fast-forward, auto-advance)

Architecture:
-------------
The application is organized around these main components:

1. **GardenApp**: Main application class managing UI and game loop
2. **GardenEnvironment**: Manages time, weather, and environmental state
3. **Plant**: Individual plant simulation with genetics
4. **TileCanvas**: Visual representation of garden tiles
5. **Inventory**: Seed and pollen storage
6. **HistoryArchiveBrowser**: Pedigree viewer and analysis tool

File Structure:
---------------
- Lines 1-365: Imports, configuration, helper classes
- Lines 366-5892: GardenApp class (main application)
  - Event handlers
  - UI building (_build_ui)
  - Rendering (render_all, selection panel)
  - Plant interactions (pollinate, harvest, etc.)
  - Time and simulation controls
  - Archive and save system

Version: v69
Author: Based on Gregor Mendel's pea experiments (1856-1863)
"""


# ============================================================================
# Imports
# ============================================================================

# --- Standard Library (Built-ins) ---
import csv
import json
import logging
import os
import random
import re
import sys
import time
import datetime as dt
import math
from collections import defaultdict
from pathlib import Path
from typing import List, Set

# --- Third-Party / Installed Modules ---
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk
from tkinter import (
    colorchooser,
    messagebox,
    simpledialog,
    Toplevel,
    ttk,
)

# --- Local Modules / Single-File Embeds ---
from crashhandler import CrashHandler
from tile import TileCanvas
from plant import Plant, STAGE_NAMES
from historyarchivebrowser import HistoryArchiveBrowser
from garden import GardenEnvironment
from mendelclimate import MendelClimate
from icon_loader import *
from inventory import Inventory, InventoryPopup, Seed, Pollen
from mendel_temperature_tracker import TemperatureTracker
from emasculation_dialog import EmasculationDialog
from pollination_dialog import PollinationDialog


# ============================================================================
# Logging Configuration
# ============================================================================

def _pg_base_dir():
    """Get base directory for the application."""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


_PG_BASE_DIR = _pg_base_dir()
_PG_LOG_PATH = os.path.join(_PG_BASE_DIR, "pea_garden.log")

# Configure logging (if not already configured)
if not logging.getLogger().handlers:
    logging.basicConfig(
        filename=_PG_LOG_PATH,
        filemode="a",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s"
    )


# ============================================================================
# Resource Path Management
# ============================================================================

def __pg_script_dir():
    """
    Get script directory, handling both normal and PyInstaller execution.
    
    Returns:
        Path object pointing to script directory
    """
    try:
        if getattr(sys, "frozen", False):
            return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
        return Path(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        return Path(os.getcwd())


__PG_BASE_DIR = __pg_script_dir()


def resource_path(*parts) -> Path:
    """
    Get path to resource file relative to application base.
    
    Args:
        *parts: Path components to join
        
    Returns:
        Path object to resource
    """
    return __PG_BASE_DIR.joinpath(*parts)


# Set working directory to script location
try:
    os.chdir(__PG_BASE_DIR)
except Exception:
    pass


# ============================================================================
# Helper Function for Pollen Day Tracking
# ============================================================================

def _today(self) -> int:
    """
    Get current day of month from garden environment.
    
    Single source of truth for "today" used by pollen, seeds, UI, fast-forward.
    
    Args:
        self: Object with garden attribute
        
    Returns:
        Current day of month (0 if unavailable)
    """
    return int(getattr(self.garden, "day_of_month", getattr(self.garden, "day", 0)))


# ============================================================================
# Visual Configuration
# ============================================================================

SOIL_COLORS = [
    "#7f9f7a",  # muted meadow green
    "#88a884",  # fresh spring grass
    "#8fb28b",  # sunlit patch
    "#6f8f6a",  # cool, dense grass
    "#9abf97",  # young growth
    "#83a37f",  # slightly dry grass
    "#7a9a76",  # balanced neutral
    "#8caf89",  # warm green
    "#a3c6a0",  # very light, fresh
    "#8fae8b",  # soft garden green
    "#93b28f",  # spring grass
    "#9ab89a",  # sunlit patch
    "#84a77f",  # cool green
]


# ============================================================================
# Dialog Classes
# ============================================================================

class FFDialog(simpledialog.Dialog):
    """
    Fast-Forward dialog with options for:
    - Number of days to advance
    - Daily rendering toggle
    - Hourly render interval (1-23 hours)
    """
    
    def body(self, master):
        """
        Build dialog body with input fields.
        
        Args:
            master: Parent widget
            
        Returns:
            Widget to receive initial focus
        """
        tk.Label(
            master,
            text="Enter the number of days to fast-forward:"
        ).grid(row=0, column=0, sticky="w", pady=4)
        
        # Days to fast-forward
        self.days_var = tk.StringVar()
        self.entry = tk.Entry(master, textvariable=self.days_var)
        self.entry.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        
        # Daily rendering checkbox (ticked by default)
        self.daily_var = tk.BooleanVar(value=True)
        self.cb = tk.Checkbutton(
            master,
            text="Daily render (once per day)",
            variable=self.daily_var,
            anchor="w"
        )
        self.cb.grid(row=2, column=0, sticky="w", pady=(0, 4))
        
        # Hourly render interval
        tk.Label(
            master,
            text="Render every N simulated h (1–23):"
        ).grid(row=3, column=0, sticky="w", pady=(4, 2))
        
        self.interval_var = tk.IntVar(value=9)  # Default 9 hours
        self.interval_spin = tk.Spinbox(
            master,
            from_=1,
            to=23,
            textvariable=self.interval_var,
            width=5
        )
        self.interval_spin.grid(row=4, column=0, sticky="w", pady=(0, 6))
        
        return self.entry  # Initial focus on day entry
    
    def apply(self):
        """Store dialog results when OK is pressed."""
        self.result = {
            "days": self.days_var.get(),
            "daily": self.daily_var.get(),
            "interval": self.interval_var.get(),
        }
"""

pea_garden_ui_topbar.py — UI reorganized
- All buttons at the top (global + plant actions)
- Mendel image no longer at the bottom; sidebar on the left
- Grid on the right
"""
def _infer_pair_from_trait(dom, rec, is_dom_pheno, rng):
    # Bias toward heterozygote when phenotype is dominant
    if is_dom_pheno:
        return (dom, rec) if rng.random() < 0.5 else (dom, dom)
    else:
        return (rec, rec)
def infer_genotype_from_traits(traits, rng):
    t = {k.lower(): (v or "").lower() for k,v in (traits or {}).items()}
    # Loci: R/r (seed shape), I/i (cotyledon), A/a (flower color), Le/le (height), Gp/gp (pod color),
    #       P/p and V/v (pod parchment/shape), Fa/fa with Mfa/mfa (modifier)
    pair_R = _infer_pair_from_trait('R','r', t.get('seed_shape','') in ('round',''), rng)
    pair_I = _infer_pair_from_trait('I','i', t.get('seed_color','') in ('yellow',''), rng)
    pair_A = _infer_pair_from_trait('A','a', t.get('flower_color','') in ('purple','pigmented',''), rng)
    pair_Le= _infer_pair_from_trait('Le','le', t.get('plant_height','') in ('tall',''), rng)
    pair_Gp= _infer_pair_from_trait('Gp','gp', t.get('pod_color','') in ('green',''), rng)

    ps = t.get('pod_shape','')
    if ps in ('inflated',''):
        pair_P = _infer_pair_from_trait('P','p', True, rng)
        pair_V = _infer_pair_from_trait('V','v', True, rng)
    else:
        if rng.random() < 0.5:
            pair_P = ('p','p'); pair_V = _infer_pair_from_trait('V','v', True, rng)
        else:
            pair_V = ('v','v'); pair_P = _infer_pair_from_trait('P','p', True, rng)

    fp = t.get('flower_position','')
    if fp.startswith('terminal'):
        pair_Fa = ('fa','fa')
        pair_Mfa= ('Mfa','Mfa')
    else:
        pair_Fa = _infer_pair_from_trait('Fa','fa', True, rng)
        pair_Mfa= _infer_pair_from_trait('Mfa','mfa', True, rng)

    return {'R':pair_R,'I':pair_I,'A':pair_A,'Le':pair_Le,'Gp':pair_Gp,'P':pair_P,'V':pair_V,'Fa':pair_Fa,'Mfa':pair_Mfa}
def random_gamete(geno, rng):
    """
    Create a gamete from a genotype.

    Genetics model:
    - By default, loci assort independently.
    - We add explicit linkage for Mendel loci that are on the same chromosome:
        * Le (plant height) and V (pod form): ~12.6 cM apart  -> recomb_frac ≈ 0.126
        * R (seed shape) and Gp (pod colour): very weakly linked -> here we approximate recomb_frac ≈ 0.30
    - All other Mendel loci (including A and I) are treated as unlinked.
    """
    # Start with independent assortment for all non-internal loci
    gam = {loc: rng.choice(pair) for loc, pair in geno.items()
           if not str(loc).startswith("_")}

    def _apply_pair_linkage(locus1, locus2, hap_tag, recomb_frac):
        """
        Adjust the gamete for a pair of linked loci if the parent is
        double-heterozygous at these loci.

        We cache the parental phase (two haplotypes) in geno[hap_tag]
        so that repeated meioses from the same parent are consistent.
        """
        pair1 = geno.get(locus1)
        pair2 = geno.get(locus2)
        if not (pair1 and pair2):
            return

        # Need heterozygous at both loci, otherwise linkage is irrelevant
        if len(set(pair1)) != 2 or len(set(pair2)) != 2:
            return

        # Get or establish parental haplotypes
        hap = geno.get(hap_tag)
        if hap is None:
            a1, a2 = pair1[0], pair1[1]
            b1, b2 = pair2[0], pair2[1]

            # Randomly choose coupling-like vs repulsion-like phase
            if rng.random() < 0.5:
                # hap1 = (a1, b1), hap2 = (a2, b2)
                hap = ((a1, b1), (a2, b2))
            else:
                # hap1 = (a1, b2), hap2 = (a2, b1)
                hap = ((a1, b2), (a2, b1))

            try:
                geno[hap_tag] = hap
            except Exception:
                pass

        # Decide whether this gamete is non-recombinant or recombinant
        if rng.random() < (1.0 - recomb_frac):
            # Non-recombinant: choose one of the parental haplotypes
            chosen = hap[0] if rng.random() < 0.5 else hap[1]
        else:
            # Recombinant: mix the two parental haplotypes
            h1, h2 = hap
            recomb_options = ((h1[0], h2[1]), (h2[0], h1[1]))
            chosen = recomb_options[0] if rng.random() < 0.5 else recomb_options[1]

        gam[locus1], gam[locus2] = chosen[0], chosen[1]

    # Real linkage pairs from pea genetics
    _apply_pair_linkage("Le", "V", "_LeV_haps", recomb_frac=0.126)  # strong-ish linkage
    _apply_pair_linkage("R",  "Gp", "_RGp_haps", recomb_frac=0.30)  # weak linkage (almost independent)

    return gam

def child_genotype(maternal_geno, pollen_gamete, rng):
    child = {}
    for loc,pair in maternal_geno.items():
        a_m = rng.choice(pair)
        a_p = pollen_gamete.get(loc, rng.choice(pair))
        dom = loc
        # sort dominant-first for stable display
        child[loc] = tuple(sorted([a_m,a_p], key=lambda x: (0 if dom in str(x) else 1, str(x))))
    # If child is double-heterozygous at I and A, assign a random phase for its future gametogenesis
    try:
        if len(set(child.get('I', ('?','?')))) == 2 and len(set(child.get('A', ('?','?')))) == 2:
            child['_IA_haplotypes'] = (('I','A'), ('i','a')) if rng.random() < 0.5 else (('I','a'), ('i','A'))
    except Exception:
        pass
    return child
def phenotype_from_genotype(geno):
    # Resolve phenotype strings from genotype with simple dominance/epistasis
    def has_dom(loc):
        a1,a2 = geno.get(loc, ('?','?'))
        return (loc in str(a1)) or (loc in str(a2))
    def is_homo(loc, allele):
        a1,a2 = geno.get(loc, ('?','?'))
        return a1==allele and a2==allele

    ph = {}
    ph['seed_shape']    = 'round'   if has_dom('R')  else 'wrinkled'
    ph['seed_color']    = 'yellow'  if has_dom('I')  else 'green'
    ph['flower_color']  = 'purple'  if has_dom('A')  else 'white'
    ph['plant_height']  = 'tall'    if has_dom('Le') else 'dwarf'
    ph['pod_color']     = 'green'   if has_dom('Gp') else 'yellow'
    ph['pod_shape']     = 'constricted' if (is_homo('P','p') or is_homo('V','v')) else 'inflated'
    ph['flower_position']= 'axial'  if (not is_homo('Fa','fa') or is_homo('Mfa','mfa')) else 'terminal'
    return ph
class _Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _show(self, event=None):
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except Exception:
            x, y = 0, 0
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text, justify="left",
                       relief="solid", borderwidth=1, font=("Segoe UI", 12), bg="#ffffe0")
        lbl.pack(ipadx=4, ipady=2)

    def _hide(self, event=None):
        try:
            if self.tip:
                self.tip.destroy()
        except Exception:
            pass
        self.tip = None
def _attach_tooltip(widget, text):
    try:
        _Tooltip(widget, text)
    except Exception:
        pass
ROWS = 7
COLS = 16
GRID_SIZE = ROWS * COLS
TILES_PER_ROW = COLS

TILE_SIZE = 85   # change to 64 or 128 later
INNER_ICON = int(TILE_SIZE * 0.8125)

# unified bar thickness (same for water + health)
BAR_THICK = max(4, TILE_SIZE // 8)

# keep water thickness as before
WATER_BAR_W = BAR_THICK

# make health bar slimmer
HEALTH_BAR_H = max(3, TILE_SIZE // 14)   # ~6 @85-90, ~4 @64, ~9 @128

# optional: keep if you use it elsewhere
WATER_BAR_H = TILE_SIZE
WATER_BAR_MAX = int(TILE_SIZE * 0.80)
BORDER_THICKNESS = max(2, TILE_SIZE // 21)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(ROOT_DIR, "export")
os.makedirs(EXPORT_DIR, exist_ok=True)
SEEDS_CSV = os.path.join(ICONS_DIR, "seeds.csv")  # keep next to icons for convenience
TRAITS_CSV = os.path.join(ROOT_DIR, "traits_export.csv")  # export of selected plant traits


class GardenApp:
    SEASON_MODES = ["off", "overlay", "enforce"]

    @staticmethod
    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def _rgb_to_hex(rgb):
        r, g, b = rgb
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _mix(c1, c2, t):
        t = max(0.0, min(1.0, float(t)))
        r1, g1, b1 = GardenApp._hex_to_rgb(c1)
        r2, g2, b2 = GardenApp._hex_to_rgb(c2)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return GardenApp._rgb_to_hex((r, g, b))

    @staticmethod
    def _darken(c, amount):
        return GardenApp._mix(c, "#000000", amount)


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_inspect_unified(self):
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None

        if not plant:
            self._toast("Select a plant first.", level="info")
            return
        if not getattr(plant, "alive", True):
            self._toast("Dead plant.", level="warn")
            return

        # Keep your original behavior: reveal one trait
        try:
            plant.reveal_trait()
            self._sel_traits_sig = None  # force sidebar refresh
        except Exception:
            pass

        # Do the biological anther check (only matters at stage 5)
        pollen_ok = self._ensure_anther_check_today(plant)  # True/False/None

        # Build one concise line
        parts = []
        stage_name = STAGE_NAMES.get(plant.stage, f"Stage {plant.stage}")
        parts.append(f"Stage: {stage_name}")

        # actions
        try:
            ok, _ = plant.can_emasculate()
            if ok:
                parts.append("Can be emasculated")
        except Exception:
            pass

        if getattr(plant, "stage", 0) >= 5 and not getattr(plant, "pollinated", False):
            parts.append("Can be pollinated")

        # pollen status (only if flowering)
        if pollen_ok is True:
            parts.append("Pollen available")
        elif pollen_ok is False:
            parts.append("No pollen available")

        # pods / harvest
        if getattr(plant, "stage", 0) >= 6:
            pods = int(getattr(plant, "pods_remaining", 0) or 0)
            is_emasculated = getattr(plant, "emasculated", False)
            
            if is_emasculated and pods == 0:
                # Emasculated plant with no pods - explain why
                parts.append("No pods (emasculated, not pollinated)")
            elif getattr(plant, "stage", 0) >= 7 and pods > 0:
                parts.append(f"Harvestable ({pods})")
            elif pods > 0:
                parts.append(f"Pods: {pods}")
            elif pods == 0:
                parts.append("No pods")

        if len(parts) == 1:
            parts.append("Growing")

        self._toast(" | ".join(parts), level="info")
        self.render_all()
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

    def _on_tile_double_click(self, event, index: int):
        print("DOUBLE CLICK", index)
        self._toast(f"Double-click #{index}", level="info")
        # ensure the tile becomes selected (same behavior as click)
        try:
            self._on_tile_left_release(event, index)
        except Exception:
            # fallback: at least set selected_index
            self.selected_index = index

        # open TIE only if there's a plant
        plant = self.tiles[index].plant if (0 <= index < len(self.tiles)) else None
        if plant is None:
            return

        self._open_tie_for_selected()

    def _test_mendelian_laws_now(self):
        try:
            # Ensure archive is current
            try:
                self._seed_archive_safe()
            except Exception:
                pass

            # Use selected plant as context (like TIE)
            idx = getattr(self, "selected_index", None)
            plant = None
            if idx is not None:
                try:
                    if 0 <= idx < len(self.tiles):
                        plant = self.tiles[idx].plant
                except Exception:
                    plant = None

            if not plant:
                self._toast("Select a plant first.", level="info")
                return

            pid = getattr(plant, "id", None)
            if pid is None:
                return

            from historyarchivebrowser import test_mendelian_laws
            res = test_mendelian_laws(self, archive=getattr(self, "archive", None), pid=pid, allow_credit=True, toast=True)

            # Optional: feedback if nothing new
            if hasattr(self, "_toast") and not res.get("new"):
                self._toast("No new Mendelian laws detected yet.", level="info")

        except Exception as e:
            try:
                self._toast(f"Law test failed: {e}", level="warn")
            except Exception:
                print("Law test failed:", e)

    def _ensure_anther_check_today(self, plant):
        """If plant is flowering (stage 5), ensure today's anther check is computed."""
        try:
            stage = int(getattr(plant, "stage", 0))
        except Exception:
            stage = 0

        if stage != 5:
            return None  # not applicable

        today = self._today()

        # Emasculated flowers have no anthers -> never show pollen availability
        if bool(getattr(plant, "emasculated", False)):
            plant.last_anther_check_day = today
            plant.anthers_available_today = False
            plant.anthers_collected_day = None
            return False

        # Only roll once per day
        if getattr(plant, "last_anther_check_day", None) != today:
            plant.last_anther_check_day = today
            plant.anthers_available_today = (random.random() < 0.5)
            plant.anthers_collected_day = None  # reset daily collection flag

        return bool(getattr(plant, "anthers_available_today", False))

    def _compute_light_factor(self, date_obj: dt.date, hour_float: float) -> float:
        # Prefer using GardenEnvironment’s sunrise/sunset (Brno+DST), already in garden.py
        sr, ss = self.garden._sunrise_sunset_local_hours(date_obj)  # :contentReference[oaicite:6]{index=6}
        h = hour_float % 24.0

        twilight = 0.35
        twilight_peak = 0.18

        if h < sr - twilight or h > ss + twilight:
            return 0.0

        if sr - twilight <= h < sr:
            t = (h - (sr - twilight)) / twilight
            return twilight_peak * t

        if ss < h <= ss + twilight:
            t = (h - ss) / twilight
            return twilight_peak * (1.0 - t)

        # daytime dome
        mid = (sr + ss) / 2.0
        half = max(1e-6, (ss - sr) / 2.0)
        x = abs(h - mid) / half
        core = max(0.0, 1.0 - x**3.0)
        return twilight_peak + (1.0 - twilight_peak) * core

    def _toggle_daynight(self):
        self.enable_daynight = bool(self.daynight_var.get())

        if not self.enable_daynight:
            # restore original soil colors immediately
            for t in self.tiles:
                base = getattr(t, "base_soil", None)
                if base:
                    t.set_soil_color(base)

        self.render_all()

    def _apply_daynight_to_tiles(self):
        # init caches once
        if not hasattr(self, "_daynight_cache"):
            self._daynight_cache = {}  # (base_hex, bucket)->tinted_hex

        # get sim date + hour from environment
        yr  = int(getattr(self.garden, "year", 1856))
        mon = int(getattr(self.garden, "month", 4))
        dom = int(getattr(self.garden, "day_of_month", 1))
        d = dt.date(yr, mon, dom)

        hour = float(getattr(self.garden, "clock_hour", 12))
        minute = float(getattr(self.garden, "clock_minute", 0))
        h = hour + minute/60.0

        L = self._compute_light_factor(d, h)  # 0..1
        bucket = int(max(0, min(255, round(L * 255))))  # smoother, 256 steps

        # mapping knobs (tweak to taste)
        night_dark = 0.35 * (1.0 - L)
        day_bright = 0.08 * L
        day_tint_target = "#bfe3b0"  # subtle “sun wash”

        for i, tile in enumerate(self.tiles):  # your TileCanvas list in the new app :contentReference[oaicite:7]{index=7}
            base = getattr(tile, "base_soil", None)
            if not base:
                # store the original base once (don’t overwrite it with tinted colors)
                base = getattr(tile, "soil", "#88a884")
                tile.base_soil = base

            key = (base, bucket)
            shaded = self._daynight_cache.get(key)
            if shaded is None:
                c = base
                if night_dark > 0:
                    c = GardenApp._darken(c, night_dark)
                if day_bright > 0:
                    c = GardenApp._mix(c, day_tint_target, day_bright)
                shaded = c
                self._daynight_cache[key] = shaded

            tile.set_soil_color(shaded)


    def _today(self) -> int:
        """Single source of truth for 'today' used by pollen, seeds, UI, fast-forward."""
        try:
            return int(getattr(self.garden, "day_of_month", getattr(self.garden, "day", 0)))
        except Exception:
            return 0

    def _ensure_tile_icon(self, plant, selected=False):
        """Ensure plant.img_obj exists so TileCanvas.render() can show the icon."""
        try:
            if plant is None:
                return

            icon_path = None
            try:
                icon_path = stage_icon_path_for_plant(plant)
            except Exception:
                icon_path = None

            # fallback
            if not icon_path or not isinstance(icon_path, str) or not os.path.exists(icon_path):
                fb = os.path.join(ICONS_DIR, "plant.png")
                if os.path.exists(fb):
                    icon_path = fb
                else:
                    return

            key = (icon_path, int(getattr(plant, "stage", -1)))
            if getattr(plant, "_icon_key", None) == key and getattr(plant, "img_obj", None) is not None:
                return

            img = safe_image(icon_path)
            if img is None:
                return

            plant.img_obj = img
            plant._icon_key = key
        except Exception:
            pass

# ============================================================================
# Initialization
# ============================================================================
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Garden of Inheritance")
        self.enable_daynight = True 
        self.garden = GardenEnvironment(size=GRID_SIZE)
        self.garden._app = self  # Give garden access to app for difficulty settings
        self.inventory = Inventory()
        self._eager_seed_and_backfill()
        self._img_cache = {}  # cache for composited tile images
        self.next_plant_id = 1
        # === Unique Plant ID System ===
        self.used_ids = set()
        try:
            for tile in self.tiles:
                if tile.plant is not None and getattr(tile.plant, "id", None) is not None:
                    self.used_ids.add(int(tile.plant.id))
            arch = getattr(self, "archive", {}) or {}
            for _k in list(arch.keys()):
                self.used_ids.add(int(_k))
            if self.used_ids:
                self.next_plant_id = max(self.used_ids) + 1
        except Exception:
            pass
        
        self.harvest_inventory = []
        self.seed_counter = 0  # for H<timestamp><n> suffix
        self.available_seeds = 22  # starter F0 seeds
        # NEW: global Mendelian-law discovery flags
        self.law1_ever_discovered = False   # Dominance
        self.law1_first_plant = None
        self.law2_ever_discovered = False   # Segregation
        self.law2_first_plant = None
        self.auto_water_ff = tk.BooleanVar(value=True)

        # Auto-water toggles (defaults as in screenshot)
        self.auto_water_ff = tk.BooleanVar(value=True)      # ✅
        self.auto_water_normal = tk.BooleanVar(value=False) # ☐
        # cross_random removed - was non-functional legacy setting
        self.auto_record_temperature = tk.BooleanVar(value=True)  # ✅ "Auto-record temperature"
        self.auto_record_temperature.trace_add(
            "write", lambda *_: self._update_temp_button_state()
        )

        # 🔗 Bridge auto-record flag to garden for TemperatureTracker
        self.garden.auto_record_temperature = self.auto_record_temperature

        # Fast-forward rendering mode: hourly vs daily redraw
        self.ff_render_daily = tk.BooleanVar(value=False)
        self.ff_render_interval = tk.IntVar(value=9)  # default: every 9 simulated hours

        # --- multi-selection state for drag selection ---
        self.multi_selected_indices = set()
        self._drag_start_x = None
        self._drag_start_y = None
        self._dragging_select = False

        # Anchor for keyboard Shift+Arrow range selection
        self._kb_anchor_index = None

        # Auto‑water during normal mode (non-FF)
        self.auto_water_normal = tk.BooleanVar(value=False)

        # Auto progression state
        self.running = False
        self.fast_forward = False
        self.day_length_s = 0.25
        self._recalc_timers()
        self.subphase_counter = 0

        self.grid_bg = "#eeeeee"
        self.grid_bg = getattr(self, "grid_bg", "#eeeeee")
        self._build_ui()
        self._update_temp_button_state()


        # ✅ add this so day/night shading always starts from the true base color
        for t in self.tiles:
            t.base_soil = t.soil

        self._bind_hotkeys()
        self.render_all()

        # Start automated phase progression (slight delay for safety)
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

        # ==== Season overlay (non-invasive; optional) ====

        try:
            from pea_season_model import PeaSeasonModelV1F4 as Season
        except Exception:
                self._toast("Season model unavailable (missing file).", level="info")
                return False

        self._season_mode = self.SEASON_MODES[0]  # Start in "off" (casual) mode
        self._season_last_date = None
        climate = getattr(self, "_climate_v2", None)
        if climate is None:
            try:
                climate = MendelClimate(mode=globals().get("CLIMATE_MODE", "stochastic"))
            except Exception:
                climate = None
        self._season = Season(climate)
        self._season_registered = set()

        # Initialize climate on garden for temperature tracker
        if climate:
            self.garden.climate = climate
        
        # Add datetime property helper to garden for temperature tracker
        def _get_datetime(garden_self):
            """Property to get current simulation datetime."""
            import datetime as dt
            try:
                return dt.datetime(
                    year=garden_self.year,
                    month=garden_self.month,
                    day=garden_self.day_of_month,
                    hour=int(garden_self.clock_hour),
                    minute=int((garden_self.clock_hour % 1) * 60)
                )
            except Exception:
                return dt.datetime(1856, 4, 1, 6, 0)
        
        # Attach as a property-like attribute
        self.garden.datetime = property(lambda self: _get_datetime(self))
        # Also store the function for direct access
        self.garden._get_datetime = lambda: _get_datetime(self.garden)
        
        # Initialize temperature tracker
        try:
            self.temp_tracker = TemperatureTracker(
                self.garden,
                data_dir="data",
                climate_csv="climate/mendel_yearly_monthly_6_14_22.csv"
            )
            self._last_temp_check_hour = self.garden.clock_hour

            # 🔑 IMPORTANT: sync temp button state now that tracker exists
            self._update_temp_button_state()

        except Exception as e:
            logging.error(f"Failed to initialize temperature tracker: {e}")
            self.temp_tracker = None

        # app._season_cycle_mode = lambda e=None: (
        #     setattr(app, "_season_mode", {"off":"overlay","overlay":"enforce","enforce":"off"}[getattr(app, "_season_mode", "off")]) or
        #     (getattr(app, "_toast", lambda *a, **k: None)(f"Season model: {getattr(app, '_season_mode', 'off')}"))
        # )
        self.root.bind("<F9>", self._season_cycle_mode)
        
        # User-friendly initial message
        mode_names = {
            "off": "Casual",
            "overlay": "Moderate", 
            "enforce": "Realistic"
        }
        friendly_name = mode_names.get(self._season_mode, self._season_mode)
        self._toast(f"Season model loaded (Difficulty: {friendly_name}). Press F9 to cycle or use Game Settings menu.")
        
        # Periodic season polling to apply lethal/stress without day change
        def _season_poll_loop():
            self._season_poll()
            self.root.after(1200, _season_poll_loop)
        _season_poll_loop()

    
    def _confirm_remove_all(self):
        """Ask once before clearing the entire grid."""
        try:
            ok = messagebox.askyesno(
                "Remove all plants",
                "This will remove EVERY plant on the grid.\nContinue?"
            )
        except Exception:
            ok = True
        if ok:
            self._on_remove_all_plants()



        try:
            pass

            self._snapshot_all_live_plants()

        except Exception:

            pass

# ============================================================================
# Event Handlers
# ============================================================================
    def _on_remove_all_plants(self):
        try:
            self._ga_snapshot_all_live_plants()
        except Exception:
            pass
        try:
            self._eager_seed_and_backfill()
        except Exception:
            pass

        try:
            self._snapshot_all_live_plants()
        except Exception:
            pass

        """Remove all plants currently on the grid."""
        count = 0

        for tile in self.tiles:
            if tile.plant is not None:
                tile.plant = None
                count += 1
        try:
            self._toast(f"Removed {count} plants from the grid.")
        except Exception:
            pass
        try:
            self.render_all()
        except Exception:
            try:
                self.render_all()
            except Exception:
                pass
    # --- Emasculation helpers ---
    
    def _estimate_selfing_fraction(self, plant):
        """Estimate the fraction of ovules that likely self-fertilized before emasculation.
        Biology: selfing happens inside closed flowers; weather has negligible effect.
        Driven only by timing (days since Stage 5 began) with slight randomness.
        """
        try:
            st = int(getattr(plant, "stage", 0))
            if st <= 4:
                return 0.0
            start = getattr(plant, "entered_stage5_age", None)
            if start is None:
                return 0.0
            d = max(0, int(getattr(plant, "days_since_planting", 0)) - int(start))
            if d == 0:
                base = 0.05
            elif d == 1:
                base = 0.30
            elif d == 2:
                base = 0.60
            else:
                base = 0.85
            return float(max(0.0, min(1.0, base + random.uniform(-0.05, 0.05))))
        except Exception:
            return 0.0


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_emasculate_selected(self):
        idx = self.selected_index
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None
        ok, reason = plant.can_emasculate()
        if not ok:
            self._toast(f"Cannot emasculate: {reason}")
            return
        
        # Show interactive emasculation dialog
        def on_emasculation_complete(success):
            if success:
                frac = self._estimate_selfing_fraction(plant)
                try:
                    plant.selfing_frac_before_emasc = max(float(getattr(plant, "selfing_frac_before_emasc", 0.0)), float(frac))
                except Exception:
                    plant.selfing_frac_before_emasc = float(frac)
                plant.emasculated = True
                plant.emasc_day = int(getattr(self.garden, "day", 0))
                plant.emasc_phase = getattr(self.garden, "phase", "morning")

                # Emasculation removes anthers -> clear any pollen/anther state immediately
                plant.anthers_available_today = False
                plant.last_anther_check_day = None
                plant.anthers_collected_day = None

                self._toast(f"Emasculated - selfing ~{int(100*plant.selfing_frac_before_emasc)}%")
                self.render_all()
            else:
                self._toast("Emasculation cancelled")
        
        try:
            # Get flower color from plant traits
            flower_color = plant.traits.get("flower_color", "purple")
            dialog = EmasculationDialog(self.root, flower_color, on_emasculation_complete)
        except Exception as e:
            # Fallback to immediate emasculation if dialog fails
            print(f"Error opening emasculation dialog: {e}")
            on_emasculation_complete(True)

    def _open_speed_dialog(self):
        """Popup to adjust simulation speed: seconds of real time per simulated HOUR."""
        win = Toplevel(self.root)
        win.title("Simulation Speed")
        frm = tk.Frame(win, padx=12, pady=12)
        frm.pack(fill="both", expand=True)

        # Current value (seconds per simulated hour)
        current_len = float(getattr(self, 'day_length_s', 0.25))
        cur = tk.StringVar(value=f"{current_len:.2f} sec per hour")
        tk.Label(frm, textvariable=cur, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        # This StringVar is used by the entry AND by Apply
        val = tk.StringVar(value=f"{current_len:.2f}")

        # Slider callback: update label + val so Apply sees slider changes

# ============================================================================
# Event Handlers
# ============================================================================
        def _on_slide(v):
            try:
                secs = max(0.1, float(v))          # allow 0.1 s/hour
                cur.set(f"{secs:.2f} s / hour")    # show decimals
                val.set(f"{secs:.2f}")
            except Exception:
                pass

        # Slider: 0.1 .. 120 seconds per simulated hour
        scale = tk.Scale(
            frm,
            from_=0.1,
            to=120,
            orient="horizontal",
            length=260,
            command=_on_slide,
            resolution=0.05,   # fine steps for fast speeds
        )
        try:
            scale.set(current_len)
        except Exception:
            scale.set(1)
        scale.pack(anchor="w", fill="x")

        # Preset buttons
        presets = tk.Frame(frm)
        presets.pack(anchor="w", pady=(10, 0))
        tk.Label(presets, text="Presets:").pack(side="left")

        def set_p(n):
            # Try to move the slider (may clamp if n > slider max),
            # then explicitly update label + entry using _on_slide logic.
            try:
                scale.set(n)
            except Exception:
                pass
            _on_slide(n)

        # Fast + normal presets (seconds per simulated hour)
        for n in (0.1, 0.25, 0.5, 1, 5, 15, 30, 60, 120):
            tk.Button(presets, text=f"{n:g}s", command=lambda n=n: set_p(n)).pack(
                side="left", padx=2
            )

        # Real-time preset (1 real second = 1 simulated second)
        def set_real_time():
            # 3600 seconds per simulated hour => 24*3600 per simulated day
            set_p(3600.0)

        tk.Button(presets, text="RT", command=set_real_time).pack(side="left", padx=4)


        # Custom entry
        row2 = tk.Frame(frm)
        row2.pack(anchor="w", pady=(10, 0))
        tk.Label(row2, text="Custom:").pack(side="left")
        ent = tk.Entry(row2, width=6, textvariable=val)
        ent.pack(side="left", padx=(6, 6))
        tk.Label(row2, text="seconds / simulated hour").pack(side="left")   

        # Informational note
        tk.Label(
            frm,
            text="Hint: Real time (RT) ≈ 3,600 s/hour.",
            anchor="w",
            fg="#555",
        ).pack(anchor="w", pady=(8, 0))

        # Apply button (no real-time mode)
        def on_apply():
            try:
                try:
                    secs = float(val.get())
                except ValueError:
                    secs = float(scale.get())
                if secs < 0.1:
                    secs = 0.1
                self._set_day_length(secs)
                # store the same value so the dialog re-opens consistently
                self.day_length_s = secs
            except Exception as e:
                print("Error applying new speed:", e)
            finally:
                try:
                    win.destroy()
                except Exception:
                    pass

        tk.Button(frm, text="Apply", command=on_apply).pack(anchor="w", pady=(12, 0))

        try:
            ent.focus_set()
            ent.select_range(0, 'end')
        except Exception:
            pass

    def _ensure_auto_loop(self, delay_ms=500):
        """Ensure exactly one auto-advance loop is scheduled."""
        try:
            if getattr(self, "_auto_loop_id", None) is not None:
                try:
                    self.root.after_cancel(self._auto_loop_id)
                except Exception:
                    pass
            self._auto_loop_id = self.root.after(delay_ms, self._auto_advance_phase)
        except Exception:
            self._auto_loop_id = None
    def _auto_advance_phase(self):
        """Auto-advance phases with a single stable loop (no duplication)."""
        # If paused, just reschedule and return
        if not getattr(self, "running", True):
            self._ensure_auto_loop(delay_ms=max(600, getattr(self, 'phase_ms', 600)))
            return

        # If fast-forward is active, keep UI responsive but don't advance here
        if getattr(self, "fast_forward", False):
            try:
                self.render_all()
            except Exception:
                pass
            self._ensure_auto_loop(delay_ms=max(300, getattr(self, 'sub_ms', 300)))
            return

        try:
            # Consume temperature sub-updates first
            if getattr(self.garden, "temp_updates_remaining", 0) > 0:
                try:
                    n = getattr(self, "_frame_skip_counter", 0)
                    # draw only every 2nd temperature substep
                    if n % 2 == 0:
                        self.render_all()
                    self._frame_skip_counter = n + 1
                except Exception:
                    pass
                self._ensure_auto_loop(delay_ms=getattr(self, 'sub_ms', 350))
                return

            # Advance phase and optionally render
            self.garden.next_phase()
            
            # Update temperature button state when hour changes (+ auto-record if enabled)
            try:
                current_hour = int(getattr(self.garden, 'clock_hour', 6))
                last_hour = getattr(self, "_last_temp_check_hour", None)

                if last_hour is None:
                    self._last_temp_check_hour = current_hour
                elif current_hour != last_hour:
                    self._update_temp_button_state()
                    self._last_temp_check_hour = current_hour

                    # AUTO-RECORD (same logic as _on_next_phase)
                    auto_record_enabled = self.auto_record_temperature.get()
                    has_tracker = self.temp_tracker is not None

                    if auto_record_enabled and has_tracker:
                        try:
                            can_measure, hour, reason = self.temp_tracker.can_measure_now()

                            if can_measure:
                                success, message = self.temp_tracker.take_measurement()
                                if success:
                                    logging.info(f"Auto-recorded: {message}")
                                else:
                                    logging.warning(f"Auto-record failed: {message}")
                        except Exception as e:
                            logging.error(f"Error in auto-record: {e}", exc_info=True)
            except Exception:
                pass
            
            # Auto-water in NORMAL mode at safe phases (morning/evening)
            try:
                if (not getattr(self, 'fast_forward', False)) and getattr(
                    self, 'auto_water_normal', tk.BooleanVar(value=False)
                ).get():
                    if self.garden.phase in ('morning', 'evening') and self.garden.weather not in ('🌧', '⛈'):
                        msg = getattr(self.garden, "water_all_smart", self.garden.water_all_safe)()
                        # Toast message removed to reduce notification spam
                        # Players can see water levels in the UI without constant messages
            except Exception:
                pass
            try:
                n = getattr(self, "_frame_skip_counter", 0)
                # draw only every 2nd phase
                if n % 2 == 0:
                    self.render_all()
                self._frame_skip_counter = n + 1
            except Exception:
                pass
            self._ensure_auto_loop(delay_ms=getattr(self, 'phase_ms', 600))

        except Exception:
            self._ensure_auto_loop(delay_ms=getattr(self, 'phase_ms', 600))


    def _toggle_climate_mode(self):
        """Toggle climate mode between 'stochastic' and 'historical'."""
        try:
            current = str(globals().get("CLIMATE_MODE", "stochastic")).lower()
            new = "historical" if current != "historical" else "stochastic"
            globals()["CLIMATE_MODE"] = new
            # Update any existing climate instances so the change takes effect immediately.
            try:
                clim = getattr(self, "_climate_v2", None)
                if clim is not None:
                    setattr(clim, "mode", new)
            except Exception:
                pass
            try:
                gclim = globals().get("_CLIMATE_V2_SINGLETON", None)
                if gclim is not None:
                    setattr(gclim, "mode", new)
            except Exception:
                pass
            try:
                self._toast(f"Climate mode: {new}", level="info")
            except Exception:
                pass
        except Exception:
            pass

    def _bind_hotkeys(self):
        """Bind global hotkeys for quick actions."""
        try:
            self.root.focus_set()
        except Exception:
            pass
        # Action mappings
        self.root.bind('<w>', lambda e: self._on_water_selected())
        self.root.bind('<W>', lambda e: self._on_water_all())
        self.root.bind('<Shift-X>', lambda e: self._confirm_remove_all())
        self.root.bind('<h>', lambda e: self._show_help())
        self.root.bind('<i>', lambda e: self._on_inspect_unified())
        self.root.bind('<I>', lambda e: self._on_inspect_unified())
        self.root.bind('<Return>', lambda e: self._on_inspect_unified())
        self.root.bind('<H>', lambda e: self._show_help())
        self.root.bind('<f>', lambda e: self._on_fast_forward())
        self.root.bind('<F>', lambda e: self._on_fast_forward())
        # P key now used for pollination (pause remains on Spacebar only)
        self.root.bind('<p>', lambda e: self._on_pollinate())
        self.root.bind('<P>', lambda e: self._on_pollinate())
        self.root.bind('<s>', lambda e: self._on_harvest_selected())
        # Shift+S → harvest ALL pods on selected plant
        self.root.bind('<S>', lambda e: self._on_harvest_all_selected())
        self.root.bind('<l>', lambda e: self._open_summary())
        self.root.bind('<L>', lambda e: self._open_summary())
        self.root.bind('<n>', lambda e: self._open_summary())
        self.root.bind('<N>', lambda e: self._open_summary())
        self.root.bind('<g>', lambda e: self._choose_grid_bg())
        self.root.bind('<G>', lambda e: self._choose_grid_bg())
        self.root.bind('<F10>', lambda e: self._toggle_climate_mode())

        # Navigation

        # Plain arrows: move single selection
        self.root.bind('<Left>',  lambda e: self._move_selection(0, -1, extend=False))
        self.root.bind('<Right>', lambda e: self._move_selection(0,  1, extend=False))
        self.root.bind('<Up>',    lambda e: self._move_selection(-1, 0, extend=False))
        self.root.bind('<Down>',  lambda e: self._move_selection(1,  0, extend=False))

        # Shift+Arrows: extend selection as row/column stripe
        self.root.bind('<Shift-Left>',  lambda e: self._move_selection(0, -1, extend=True))
        self.root.bind('<Shift-Right>', lambda e: self._move_selection(0,  1, extend=True))
        self.root.bind('<Shift-Up>',    lambda e: self._move_selection(-1, 0, extend=True))
        self.root.bind('<Shift-Down>',  lambda e: self._move_selection(1,  0, extend=True))

        self.root.bind('<space>',  lambda e: self._toggle_run())

        self.root.bind('<Delete>', lambda e: self._on_remove_selected())
        self.root.bind('<x>', lambda e: self._on_remove_selected())
        self.root.bind('<X>', lambda e: self._on_remove_selected())
        
        # Pollination auxiliaries & lab operations
        self.root.bind('<e>', lambda e: self._on_emasculate_selected())
        self.root.bind('<E>', lambda e: self._on_emasculate_selected())
        self.root.bind('<c>', lambda e: self._on_collect_pollen())
        self.root.bind('<C>', lambda e: self._on_collect_pollen())
        
        # Quick open Summary → Pollen tab
        self.root.bind('<Shift-O>', lambda e: self._open_summary(initial_tab='Pollen'))
        
        # Quick open Genotype window
        self.root.bind('<Shift-G>', lambda e: self._on_genetics())
        
        # Select all tiles (plants + empty + dead)
        self.root.bind('<Control-a>', lambda e: self._on_select_all())
        self.root.bind('<Control-A>', lambda e: self._on_select_all())


    def _move_selection(self, drow, dcol, extend=False):
        """Move plant selection in the grid.

        Plain arrows → move single selection.
        Shift+Arrows (extend=True) → select a row/column stripe from the anchor to the new cell.
        """
        try:
            total = GRID_SIZE
            cols = TILES_PER_ROW
        except Exception:
            return

        # Initialize selection if nothing selected yet
        if self.selected_index is None:
            self.selected_index = 0
            try:
                self.multi_selected_indices = {0}
            except Exception:
                self.multi_selected_indices = set()
            try:
                self._kb_anchor_index = 0
            except Exception:
                pass
            try:
                self.render_all()
            except Exception:
                pass
            return

        cur = self.selected_index
        row = cur // cols
        col = cur % cols

        # Compute tentative new position within bounds
        row = max(0, min((total - 1) // cols, row + drow))
        col = max(0, min(cols - 1, col + dcol))
        new_index = row * cols + col

        if not extend:
            # Simple move: reset multi-selection & keyboard anchor
            self.selected_index = new_index
            try:
                self.multi_selected_indices = {new_index}
            except Exception:
                self.multi_selected_indices = set()
            try:
                self._kb_anchor_index = new_index
            except Exception:
                pass
        else:
            # Shift+Arrow: extend selection as a full rectangle from the anchor to the new cell
            try:
                anchor = getattr(self, "_kb_anchor_index", None)
            except Exception:
                anchor = None
            if anchor is None:
                # If no anchor yet, start from the current cell
                anchor = cur
                try:
                    self._kb_anchor_index = anchor
                except Exception:
                    pass

            a_row = anchor // cols
            a_col = anchor % cols

            # Rectangle bounds between anchor and new cell
            r0 = min(a_row, row)
            r1 = max(a_row, row)
            c0 = min(a_col, col)
            c1 = max(a_col, col)

            indices = set()
            for rr in range(r0, r1 + 1):
                for cc in range(c0, c1 + 1):
                    idx = rr * cols + cc
                    if 0 <= idx < total:
                        indices.add(idx)

            self.selected_index = new_index
            try:
                self.multi_selected_indices = indices
            except Exception:
                pass

        self.render_all()


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_grid_wizard(self):
        """Allow user to reopen the garden size wizard from the menu."""
        try:
            cfg = _load_grid_config()
        except Exception:
            cfg = None

        # Fallback: use current globals if no config
        if cfg is None:
            cfg = {
                "rows": ROWS,
                "cols": COLS,
                "show_dialog": True,
            }

        try:
            rows, cols, show_dialog_next = _ask_grid_size(self.root, cfg)
            _apply_grid_size(rows, cols)
            _save_grid_config(rows, cols, show_dialog_next)
            # Current grid is already built, so we inform user a restart is needed
            try:
                self._toast("Grid settings saved. Restart the simulator to apply the new garden size.")
            except Exception:
                # Fallback if _toast not available
                messagebox.showinfo(
                    "Garden size",
                    "Grid settings saved.\nPlease restart the simulator to apply the new garden size."
                )
        except Exception:
            try:
                self._toast("Could not open grid wizard (see console).")
            except Exception:
                pass

    def _choose_grid_bg(self):
        """Open a color picker to change grid background."""
        try:
            color = colorchooser.askcolor(
                title="Choose Grid Background Color",
                initialcolor=self.grid_bg
            )[1]
        except Exception:
            color = None

        if not color:
            return

        # Store new background
        self.grid_bg = color

        # Grid frame itself
        try:
            self.grid_frame.configure(bg=soil)
        except Exception:
            pass

        # Cell frames: keep per-tile soil colors
        try:
            for j, cell in enumerate(self.tiles):
                soil = getattr(self, "tile_soil_colors", {}).get(j, self.grid_bg)
                cell.configure(
                    bg=soil,
                    highlightbackground=soil,
                    highlightcolor=soil,
                )
        except Exception:
            pass

        for tile in self.tiles:
            tile.soil = soil

        # Redraw so borders use the new color
        self.render_all()

    def _get_seed_groups(self):
        groups = []

        # Starter seeds
        starters = int(getattr(self, "available_seeds", 0) or 0)
        groups.append(
            ('S', None, None, starters,
             f"Starter seeds (F0) — x{starters}",
             lambda s: False)
        )

        # Group harvested seeds by mother plant
        gmap = defaultdict(list)
        for s in self.harvest_inventory:
            k = ('M', s.get('source_id'))
            gmap[k].append(s)

        # Build UI groups
        for (kind, src), items in sorted(
            gmap.items(),
            key=lambda kv: kv[0][1] or 0
        ):
            count = len(items)

            # --- label (genetic-style, keep seed count) ---
            selfed_seeds = [s for s in items if not s.get("donor_id")]
            crossed_seeds = [s for s in items if s.get("donor_id")]

            if crossed_seeds and not selfed_seeds:
                donor = crossed_seeds[0].get("donor_id")
                label = f"♀#{src} × ♂#{donor} — x{count}"

            elif selfed_seeds and not crossed_seeds:
                label = f"♀#{src} (selfed) — x{count}"

            elif crossed_seeds and selfed_seeds:
                donor = crossed_seeds[0].get("donor_id")
                label = f"♀#{src} × ♂#{donor} (?) — x{count}"

            else:
                label = f"Seeds from ♀#{src} — x{count}"

            # --- match function: all seeds from this mother ---
            def make_match_fn(_src=src):
                return lambda s: s.get("source_id") == _src

            groups.append(('M', src, None, count, label, make_match_fn()))

        return groups

    def _plant_one_from_group(self, index, kind, match_fn):

        # Starter seeds
        if kind == 'S':

            # Season gate for starter seeds
            if not self._season_gate_sowing():
                try:
                    self._toast("Sowing blocked by season rules.", level="warn")
                except Exception:
                    pass
                return False
            if getattr(self, "available_seeds", 0) <= 0:
                self._toast("No starter seeds left.")
                return False
            pid = self._next_id()
            traits = self._starter_traits_for_next_seed()
            geno = infer_genotype_from_traits(traits, random)
            p = Plant(id=pid, env=self.garden, stage=1, generation="F0", traits=traits)
            p.germination_delay = random.randint(1, 3)

            try:
                pass
                p.genotype = dict(geno)
            except Exception:
                pass

            self.tiles[index].plant = p
            self.available_seeds -= 1
            self._toast("Starter seed planted.")
            self.render_all()

            return True
            
        # Harvested or crossed seeds: pick one seed from this group
        idx_seed = None
        seed = None
        for i, s in enumerate(self.harvest_inventory):
            try:
                if match_fn(s):
                    idx_seed = i
                    seed = s
                    break
            except Exception:
                # Defensive: if match_fn misbehaves, skip this seed
                continue

        if idx_seed is None or seed is None:
            self._toast("No seeds left in that group.", level="warn")
            return False

        # Season check
        if not self._season_gate_sowing():
            return False

        # Create and place the plant through the unified helper
        p = self.plant_seed(seed, index)
        if p is None:
            self._toast("Planting failed (internal error).", level="error")
            return False

        # Remove this seed from the harvest inventory
        try:
            sid = seed.get("id")
            if sid:
                self.harvest_inventory = [
                    s for s in self.harvest_inventory if s.get("id") != sid
                ]
            else:
                del self.harvest_inventory[idx_seed]
        except Exception:
            pass

        # UI feedback
        self._toast(f"Planted → {p.generation}")
        self.render_all()

        return True

    def _neighbors4(self, idx):
        cols = getattr(self.garden, "cols", TILES_PER_ROW)
        rows = getattr(self.garden, "rows", max(1, len(self.tiles)//cols))
        x, y = idx % cols, idx // cols
        out = []
        if x > 0: out.append(idx-1)
        if x+1 < cols: out.append(idx+1)
        if y > 0: out.append(idx-cols)
        if y+1 < rows: out.append(idx+cols)
        return [i for i in out if 0 <= i < len(self.tiles)]

    def _contiguous_empty_region(self, start_idx):
        """Find contiguous region of empty or dead-plant tiles for area planting."""
        if start_idx is None: return []
        # Start tile must be empty or have a dead plant
        start_plant = self.tiles[start_idx].plant
        if start_plant is not None and getattr(start_plant, 'alive', True):
            return []  # Living plant blocks area planting
        
        seen = {start_idx}
        q = [start_idx]
        region = [start_idx]
        while q:
            cur = q.pop(0)
            for nb in self._neighbors4(cur):
                if nb in seen: continue
                nb_plant = self.tiles[nb].plant
                # Include empty tiles and tiles with dead plants
                if nb_plant is None or not getattr(nb_plant, 'alive', True):
                    seen.add(nb); q.append(nb); region.append(nb)
        return region


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_plant_area_from_group(self, kind, match_fn):
        """Plant seeds in a contiguous area, automatically replacing dead plants."""
        idx = self.selected_index
        if idx is None:
            self._toast("Select a tile first.", level="warn"); return
        
        # Check if starting tile is available (empty or dead plant)
        pl = self.tiles[idx].plant
        if pl is not None and getattr(pl, 'alive', True):
            self._toast("Select an empty tile or dead plant to start planting.", level="warn")
            return
        
        # Get region including dead plants
        region = self._contiguous_empty_region(idx) or [idx]
        
        if kind == 'S':
            avail = int(getattr(self, "available_seeds", 0) or 0)
        else:
            avail = sum(1 for s in self.harvest_inventory if match_fn(s))
        if avail <= 0:
            self._toast("No seeds available in this group.", level="warn"); return
        
        planted = 0
        for slot in region:
            if planted >= avail: break
            # Clear dead plant if present, then plant
            slot_plant = self.tiles[slot].plant
            if slot_plant is not None and not getattr(slot_plant, 'alive', True):
                self.tiles[slot].plant = None
            # Now plant if tile is empty
            if self.tiles[slot].plant is None:
                if self._plant_one_from_group(slot, kind, match_fn):
                    planted += 1
        
        self._toast(f"Planted {planted} seed(s) in area.", level="info")
        self.render_all()

    def _on_plant_seed_from_group(self, kind, match_fn):
        """Plant a single seed from a group, automatically replacing dead plants."""
        idx = self.selected_index
        if idx is None:
            self._toast("Select a tile first.", level="warn"); return
        
        # Allow planting on empty tiles or dead plants
        pl = self.tiles[idx].plant
        if pl is not None and getattr(pl, 'alive', True):
            self._toast("Select an empty tile or dead plant to plant.", level="warn")
            return
        
        # Clear dead plant if present
        if pl is not None and not getattr(pl, "alive", True):
            self.tiles[idx].plant = None
        
        self._plant_one_from_group(idx, kind, match_fn)


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_plant_seed_quick(self):
        """Open grouped seed chooser for the currently selected tile (empty or dead → empty)."""
        if len(self.selected_tiles) == 0:
            self._toast("Select a tile first.", level="warn")
            return

        plantable_tiles = [t for t in self.selected_tiles 
                           if t.plant is None or not getattr(t.plant, 'alive', True)]

        if len(plantable_tiles) == 0:
            self._toast("Select an empty tile to plant.", level="warn")
            return
        # Do I need to remove dead plants first? -> probably not, just overwrite
        self.choose_seed_for_tiles(plantable_tiles)


    def _build_ui(self):

        # ---- Menubar with larger font ----
        self.menubar = tk.Menu(self.root, font=("Segoe UI", 11)) if not hasattr(self, "menubar") else self.menubar
        
        # ---- File Menu ----
        file_menu = tk.Menu(self.menubar, tearoff=0, font=("Segoe UI", 11))
        file_menu.add_command(label="Save Garden", command=self._on_save_garden)
        
        # Load submenu (dynamically populated)
        self.load_submenu = tk.Menu(file_menu, tearoff=0, font=("Segoe UI", 11), postcommand=lambda: self._build_load_menu(self.load_submenu))
        file_menu.add_cascade(label="Load Garden", menu=self.load_submenu)
        
        file_menu.add_separator()
        file_menu.add_command(label="Delete Saves…", command=self._on_delete_saves)
        
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        self.menubar.add_cascade(label="File", menu=file_menu)
        
        # ---- View Menu ----
        view_menu = tk.Menu(self.menubar, tearoff=0, font=("Segoe UI", 11))
        
        # Meteorological Observatory
        def _open_observatory():
            if hasattr(self, 'temp_tracker') and self.temp_tracker:
                self.temp_tracker.open_observatory()
            else:
                messagebox.showinfo("Observatory", "Temperature tracker not available")
        
        view_menu.add_command(label="Help / Legend", command=self._show_help)
        
        view_menu.add_separator()
        view_menu.add_command(
            label="Genotype Viewer…",
            command=self._on_genetics
        )
        view_menu.add_command(
            label="Trait Inheritance Explorer…",
            command=self._open_tie_for_selected
        )
        
        view_menu.add_separator()
        view_menu.add_command(
            label="Meteorological Observatory…",
            command=_open_observatory
        )

        # Attach the View menu
        self.menubar.add_cascade(label=" View", menu=view_menu)
        self.root.config(menu=self.menubar)

        # Shortcut for Genetics
        self.root.bind_all("<Control-g>", lambda e: self._on_genetics())

        # --- NEW: Game Settings menu ---
        game_menu = tk.Menu(self.menubar, tearoff=0, font=("Segoe UI", 11))
        
        # --- Day / Night toggle ---
        self.daynight_var = tk.BooleanVar(value=self.enable_daynight)
        game_menu.add_checkbutton(
            label="Day / Night cycle",
            variable=self.daynight_var,
            command=self._toggle_daynight
        )
        
        # --- Difficulty (Season Model) submenu ---
        difficulty_menu = tk.Menu(game_menu, tearoff=0, font=("Segoe UI", 11))
        
        # Initialize difficulty variable if not exists
        if not hasattr(self, '_difficulty_var'):
            current_mode = getattr(self, '_season_mode', 'off')
            self._difficulty_var = tk.StringVar(value=current_mode)
        
        difficulty_menu.add_radiobutton(
            label="Casual — No environmental stress",
            variable=self._difficulty_var,
            value="off",
            command=self._on_difficulty_change
        )
        difficulty_menu.add_radiobutton(
            label="Moderate — Environmental effects (advisory)",
            variable=self._difficulty_var,
            value="overlay",
            command=self._on_difficulty_change
        )
        difficulty_menu.add_radiobutton(
            label="Realistic — Full Mendel-era conditions",
            variable=self._difficulty_var,
            value="enforce",
            command=self._on_difficulty_change
        )
        
        game_menu.add_cascade(label="Difficulty", menu=difficulty_menu)
        game_menu.add_separator()
        
        # --- NEW: Time Speed (moved from top buttons) ---
        game_menu.add_command(
            label="Time Speed…",
            command=self._open_speed_dialog
        )
        
        game_menu.add_separator()
        game_menu.add_checkbutton(label="Auto-water",
                                    variable=self.auto_water_normal)
        game_menu.add_checkbutton(label="Auto-water in FF",
                                    variable=self.auto_water_ff)
        # game_menu.add_checkbutton(label="Random X on harvest",  # Removed - non-functional
        #                             variable=self.cross_random)
        game_menu.add_checkbutton(label="Auto-record temperature",
                                    variable=self.auto_record_temperature)
        
        game_menu.add_separator()
        game_menu.add_command(
            label="Garden size wizard…",
            command=self._on_grid_wizard
        )

        self.menubar.add_cascade(label="Game Settings", menu=game_menu)

        # Apply menubar
        self.root.config(menu=self.menubar)

        # ---------- Top status + global controls ----------
        self.topbar = tk.Frame(self.root, padx=8, pady=6)
        self.topbar.pack(fill="x")

        # Font setup
        self.font_seed   = ("Segoe UI", 14, "bold")   # same as buttons
        self.font_law    = ("Segoe UI", 14)           # law status text

        # Modern UI font + shared button style
        self.font_button = ("Segoe UI", 12, "bold")
        self.button_style = {
            "font": self.font_button,
            "bg": "#F4F4F4",
            "activebackground": "#E4E4E4",
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "padx": 12,
            "pady": 6,
        }

        # -----------------
        # Hover effect (keeps per-button base colors)
        # -----------------
        def _hover_on(event):
            w = event.widget
            # If a button defines its own hover color, use it; else use default light gray
            hover = getattr(w, "_hover_bg", None)
            if hover:
                w.configure(bg=hover)
            else:
                w.configure(bg="#E8E8E8")

        def _hover_off(event):
            w = event.widget
            base = getattr(w, "_base_bg", None)
            if base:
                w.configure(bg=base)
            else:
                w.configure(bg="#F4F4F4")

        def _apply_hover(btn):
            # Record original bg as the "base" color if not already set
            try:
                if not hasattr(btn, "_base_bg"):
                    btn._base_bg = btn.cget("bg")
            except Exception:
                pass
            btn.bind("<Enter>", _hover_on)
            btn.bind("<Leave>", _hover_off)

        self._apply_hover = _apply_hover   # attach method to instance

        # Left: status (EMPTY now - everything moved below to grid_header)
        status = tk.Frame(self.topbar)
        status.pack(side="left")

        # Seeds/Starter/Buttons will be created later in grid_header (above the grid)
        # Just initialize the variables here
        self.seed_counter_var = tk.StringVar(value="Seeds: 0")
        self.starter_var = tk.StringVar(value=f"Starter: {0}")

        # New: Mendelian laws status (will be shown below grid)
        self.law_status_var = tk.StringVar(
            value=(
                "☐ Law of Dominance     "
                "☐ Law of Segregation (Ratio: not yet revealed)     "
                "☐ Law of Independent Assortment (Ratio: not yet revealed)"
            )
        )

        # Placeholders that will be filled once Law 2 / Law 3 are credited
        self.law2_ratio_ui = "Ratio __:__"
        self.law3_ratio_ui = "Ratio __:__:__:__"
        self.law2_placeholder = "3:1"
        self.law3_placeholder = "9:3:3:1"   

        self._update_law_status_label()

        # All buttons will be created in grid_header (not in topbar)
        self.status_var = tk.StringVar(value="")

        # ---------- Main content area: left and right panels ----------
        self.content = tk.Frame(self.root, padx=8, pady=8)
        self.content.pack(fill="both", expand=True)

        if not hasattr(self, 'grid_bg'):
            self.grid_bg = '#eeeeee'

        # ========== LEFT PANEL (clean, no borders) ==========
        self.left_panel = tk.Frame(self.content, padx=6, pady=8, bg=self.grid_bg)
        self.left_panel.pack(side="left", anchor="n")

        # Mendel portrait at the TOP of left panel
        mendel_img = safe_image(os.path.join(ICONS_DIR, "mendel.png"))
        self.mendel_label = tk.Label(self.left_panel, image=mendel_img, bg=self.grid_bg)
        self.mendel_label.image = mendel_img
        self.mendel_label.pack(anchor="w", pady=(0, 0))  # No bottom padding

        # Container for icon with ID and generation text
        self.icon_row = tk.Frame(self.left_panel, bg=self.grid_bg)
        self.icon_row.pack(anchor="center", pady=(0, 2))  # No top padding
        
        # ID label (left of icon) - fixed width to prevent shifting
        self.id_label = tk.Label(
            self.icon_row,
            text="",
            font=("Segoe UI", 10, "bold"),
            bg=self.grid_bg,
            fg="#000000",
            width=4,  # Fixed width for up to 3 digits (e.g., "#999")
            anchor="e"  # Right-align text
        )
        self.id_label.grid(row=0, column=0, padx=(0, 4))

        # Plant icon display (center) - will show empty/dead icons too
        self.plant_icon_label = tk.Label(self.icon_row, bg=self.grid_bg)
        self.plant_icon_label.grid(row=0, column=1)
        
        # Generation label (right of icon) - fixed width
        self.gen_label = tk.Label(
            self.icon_row,
            text="",
            font=("Segoe UI", 10, "bold"),
            bg=self.grid_bg,
            fg="#000000",
            width=3,  # Fixed width (e.g., "F99")
            anchor="w"  # Left-align text
        )
        self.gen_label.grid(row=0, column=2, padx=(4, 0))
        
        # Stage info label (centered, below icon)
        self.stage_label = tk.Label(
            self.left_panel,
            text="",
            font=("Segoe UI", 10, "italic"),
            bg=self.grid_bg,
            fg="#555555"
        )
        self.stage_label.pack(anchor="center", pady=(0, 8))
        
        # Load empty and dead icons for display (same as tile.py)
        try:
            self.empty_icon = tk.PhotoImage(file="icons/empty.png")
        except Exception as e:
            print(f"Failed to load empty icon: {e}")
            self.empty_icon = None
        
        try:
            self.dead_icon = tk.PhotoImage(file="icons/dead.png")
        except Exception as e:
            print(f"Failed to load dead icon: {e}")
            self.dead_icon = None

        # 2) make the actions frame stretch horizontally
        self.left_actions = tk.Frame(self.left_panel)
        self.left_actions.pack(anchor="nw", pady=(0,6), fill="x")   # ← add fill="x"

        self.btn_font = ("Segoe UI", 12)

        def make_icon_button(parent, text, icon_name, command):
            # base style for sidebar buttons derived from main style
            style = dict(self.button_style)
            style["bg"] = self.grid_bg
            style["activebackground"] = "#DDDDDD"

            try:
                img = tk.PhotoImage(file=os.path.join(ICONS_DIR, icon_name))
                btn = tk.Button(
                    parent,
                    text=text,
                    image=img,
                    compound="left",
                    command=command,
                    **style,
                )
                btn.image = img
            except Exception as e:
                print(f"⚠ Could not load icon {icon_name}: {e}")
                btn = tk.Button(
                    parent,
                    text=text,
                    command=command,
                    **style,
                )

            self._apply_hover(btn)
            btn.pack(anchor="nw", pady=2, fill="x")
            return btn

        self.water_btn     = make_icon_button(self.left_actions, "Water",         "can.png",       self._on_water_selected)
        self.inspect_btn = make_icon_button(
            self.left_actions,
            "Inspect",
            "inspect.png",
            self._on_inspect_unified
        )
        self.inspect_btn.bind("<Button-3>", self._open_tie_for_selected)
        self.harvest_btn   = make_icon_button(self.left_actions, "Harvest seeds", "harvest.png",   self._on_harvest_selected)
        self.pollen_btn    = make_icon_button(self.left_actions, "Collect pollen","pollen.png",    self._on_collect_pollen)
        self.pollinate_btn = make_icon_button(self.left_actions, "Pollinate",     "pollinate.png", self._on_pollinate)
        self.remove_btn    = make_icon_button(self.left_actions, "Remove plant",  "remove.png",    self._on_remove_selected)

        # Genetics tools
        try:
            self.genetics_btn = make_icon_button(self.left_actions, "Genotype", "genetics.png", self._on_genetics)
        except Exception:
            pass

        # Separator line
        tk.Frame(self.left_panel, height=1, bg="#999999").pack(fill="x", pady=(0, 0))

        # Centered "Traits" header
        self.traits_header = tk.Label(
            self.left_panel,
            text="Traits:",
            font=("Segoe UI", 12, "bold"),
            bg=self.grid_bg,
            anchor="center",   # text centered inside the label
            justify="center",
        )

        # # Left-aligned "Traits" header
        # self.traits_header = tk.Label(
        #     self.left_panel,
        #     text="Traits:",
        #     font=("Segoe UI", 12, "bold"),
        #     bg=self.grid_bg,
        #     anchor="w",      # ← left-align **inside** the label
        #     justify="left",  # ← just to be safe
        # )
        # self.traits_header.pack(side="top", anchor="w", pady=(8, 2))  # ← stick to the left


        # Center the label itself and let it span the full width
        self.traits_header.pack(side="top", fill="x", pady=(8, 2))

        # Traits below, left-aligned inside their own container
        self.traits_container = tk.Frame(self.left_panel, bg=self.grid_bg)
        self.traits_container.pack(side="top", fill="x", pady=(4, 0), anchor="n")


        # ========== RIGHT PANEL (clean, no borders) ==========
        right_panel = tk.Frame(self.content, bg=self.grid_bg)
        right_panel.pack(side="left", fill="both", expand=True, padx=(8, 0))

        # Date/Time/Weather/Temp at the TOP of right panel (its own line)
        self.phase_label = tk.Label(right_panel, text="", font=("Segoe UI", 20, "bold"), bg=self.grid_bg)
        self.phase_label.pack(fill="x", pady=(4, 8))

        # Status message bar
        self.status_msg = tk.Label(
            right_panel,
            textvariable=self.status_var,
            anchor="w",
            fg="#c01818",
            bg="#dcdcdc",
            font=("Segoe UI", 14, "bold"),
            justify="left",
            wraplength=980,
            relief="groove",
            bd=1,
            padx=6,
            pady=4,
        )
        self.status_msg.pack(fill="x", pady=(0, 4))

        # ---------- Seeds/Starter/All Buttons row ----------
        self.inventory_row = tk.Frame(right_panel, bg=self.grid_bg)
        self.inventory_row.pack(anchor="w", fill="x", pady=(4, 8))

        # Left-aligned container for Seeds/Starter
        inventory_left = tk.Frame(self.inventory_row, bg=self.grid_bg)
        inventory_left.pack(side="left", anchor="w")

        # Seeds label
        self.seed_label = tk.Label(
            inventory_left,
            textvariable=self.seed_counter_var,
            font=self.font_seed,
            bg=self.grid_bg
        )
        self.seed_label.pack(side="left", padx=(0, 12))

        # Starter label
        self.starter_label = tk.Label(
            inventory_left,
            textvariable=self.starter_var,
            font=self.font_seed,
            bg=self.grid_bg
        )
        self.starter_label.pack(side="left", padx=(0, 20))

        # ALL BUTTONS (moved from topbar)
        btn_kwargs = dict(self.button_style)
        
        # Observatory button with custom icon
        try:
            observatory_icon = tk.PhotoImage(file=os.path.join(ICONS_DIR, "observatory.png"))
            self.observatory_btn = tk.Button(
                inventory_left,
                text=" Observatory",
                image=observatory_icon,
                compound="left",
                command=lambda: (
                    self.temp_tracker.open_observatory() if hasattr(self, 'temp_tracker') and self.temp_tracker
                    else messagebox.showinfo("Observatory", "Temperature tracker not available")
                ),
                **btn_kwargs,
            )
            self.observatory_btn.image = observatory_icon  # Keep reference
        except Exception as e:
            print(f"⚠ Could not load observatory icon: {e}")
            self.observatory_btn = tk.Button(
                inventory_left,
                text="🔭 Observatory",
                command=lambda: (
                    self.temp_tracker.open_observatory() if hasattr(self, 'temp_tracker') and self.temp_tracker
                    else messagebox.showinfo("Observatory", "Temperature tracker not available")
                ),
                **btn_kwargs,
            )
        self._apply_hover(self.observatory_btn)
        self.observatory_btn.pack(side="left", padx=2)

        # Pause/Resume button
        self.pause_btn = tk.Button(
            inventory_left,
            text=("▶ Resume" if not self.running else "⏸ Pause"),
            command=self._toggle_run,
            **btn_kwargs,
        )
        self._apply_hover(self.pause_btn)
        self.pause_btn.pack(side="left", padx=2)

        # Fast Forward button
        self.fast_btn = tk.Button(
            inventory_left,
            text="FF ▶▶",
            command=self._on_fast_forward,
            **btn_kwargs,
        )
        self._apply_hover(self.fast_btn)
        self.fast_btn.pack(side="left", padx=2)

        # Speed button moved to Game Settings menu

        # Next Phase button
        self.next_phase_btn = tk.Button(
            inventory_left,
            text="Next ⏵1h",
            command=self._on_next_phase,
            **btn_kwargs,
        )
        self._apply_hover(self.next_phase_btn)
        self.next_phase_btn.pack(side="left", padx=2)

        # Plant Seeds button with shovel icon
        try:
            plant_icon = tk.PhotoImage(file=os.path.join(ICONS_DIR, "shovel.png"))
            self.plant_seeds_btn = tk.Button(
                inventory_left,
                text=" Plant",
                image=plant_icon,
                compound="left",
                command=self._on_plant_seed_quick,
                **btn_kwargs,
            )
            self.plant_seeds_btn.image = plant_icon  # Keep reference
        except Exception as e:
            print(f"⚠ Could not load shovel icon: {e}")
            self.plant_seeds_btn = tk.Button(
                inventory_left,
                text="Plant 🌱",
                command=self._on_plant_seed_quick,
                **btn_kwargs,
            )
        self._apply_hover(self.plant_seeds_btn)
        self.plant_seeds_btn.pack(side="left", padx=2)

        # Water All button with watering can icon
        try:
            water_all_icon = tk.PhotoImage(file=os.path.join(ICONS_DIR, "can.png"))
            self.water_all_btn = tk.Button(
                inventory_left,
                text=" Water All",
                image=water_all_icon,
                compound="left",
                command=self._on_water_all,
                **btn_kwargs,
            )
            self.water_all_btn.image = water_all_icon  # Keep reference
        except Exception as e:
            print(f"⚠ Could not load can icon: {e}")
            self.water_all_btn = tk.Button(
                inventory_left,
                text="Water All 💧",
                command=self._on_water_all,
                **btn_kwargs,
            )
        self._apply_hover(self.water_all_btn)
        self.water_all_btn.pack(side="left", padx=2)
        
        # Temperature measurement button
        self.measure_temp_btn = tk.Button(
            inventory_left,
            text="°C Measure Temp",
            command=self._on_measure_temperature,
            **btn_kwargs,
        )
        self._apply_hover(self.measure_temp_btn)
        self.measure_temp_btn.pack(side="left", padx=2)
        # Set initial state
        try:
            self._update_temp_button_state()
        except Exception:
            pass

        # Summary button
        self.summary_btn = tk.Button(
            inventory_left,
            text="Summary",
            command=self._open_summary,
            **btn_kwargs,
        )
        self._apply_hover(self.summary_btn)
        self.summary_btn.pack(side="left", padx=2)

        # Grid frame (in right_panel)
        self.grid_frame = tk.Frame(right_panel, padx=0, pady=0, bg=self.grid_bg)
        self.grid_frame.pack(anchor="w", pady=(0, 5))

        # Create a config dict to pass sizes into the class
        tile_configs = {
            'TILE_SIZE': TILE_SIZE,
            'WATER_BAR_W': WATER_BAR_W,
            'WATER_BAR_H': WATER_BAR_H,
            'HEALTH_BAR_H': HEALTH_BAR_H
        }

        self.tiles: List[TileCanvas] = [] 
        for idx in range(GRID_SIZE):
            soil = random.choice(SOIL_COLORS)
            
            # Create the custom widget
            tile = TileCanvas(self.grid_frame, idx, self, soil, None, tile_configs)
            # Position it
            tile.grid(row=idx // TILES_PER_ROW, column=idx % TILES_PER_ROW, padx=2, pady=2)
            # Store the single object
            self.tiles.append(tile)

        # ---------- Mendelian laws row (below the grid in right_panel) ----------
        self.law_row = tk.Frame(right_panel, bg=self.grid_bg, padx=0, pady=8)
        self.law_row.pack(anchor="w", fill="x", pady=(4, 0))

        # Left-aligned container (prevents right-push by expanding widgets)
        law_left = tk.Frame(self.law_row, bg=self.grid_bg)
        law_left.pack(side="left", anchor="w")

        # Title label (left)
        tk.Label(
            law_left,
            text="Mendelian laws:",
            font=("Segoe UI", 14),
            bg=self.grid_bg
        ).pack(side="left", anchor="w", padx=(0, 10))

        # The actual laws status text
        # IMPORTANT: keep the name self.law_status_label because _update_law_status_label() uses it
        self.law_status_label = tk.Label(
            law_left,
            textvariable=self.law_status_var,
            font=("Segoe UI", 14),
            bg=self.grid_bg,
            anchor="w",
            justify="left"
        )
        self.law_status_label.pack(side="left", anchor="w", padx=(0, 10))

        # Unlock button (left, next to laws)
        self.btn_test_laws = tk.Button(
            law_left,
            text="Unlock",
            command=self._test_mendelian_laws_now,
            **self.button_style
        )
        self._apply_hover(self.btn_test_laws)
        self.btn_test_laws.pack(side="left", padx=(8, 10))

    # ---------- Rendering ----------

    def _update_law_status_label(self):
        """Refresh the top-bar 'Mendelian laws' string based on ever_discovered flags."""
        try:
            if not hasattr(self, "law_status_var"):
                return

            law1_done = bool(getattr(self, "law1_ever_discovered", False))
            law2_done = bool(getattr(self, "law2_ever_discovered", False))
            law3_done = bool(getattr(self, "law3_ever_discovered", False))

            # Expected Mendelian ratios as placeholders (what the user *would* expect)
            expected_law2 = "3:1"
            expected_law3 = "9:3:3:1"

            # User-discovered ratios (may be empty)
            law2_ratio = (getattr(self, "law2_ratio_ui", "") or "").strip()
            law3_ratio = (getattr(self, "law3_ratio_ui", "") or "").strip()

            def box(done: bool) -> str:
                return "☑" if done else "☐"

            # If a law is discovered and we have a ratio -> show that
            # Otherwise -> show the expected placeholder ratio
            if law2_done and law2_ratio:
                seg_suffix = f" ({law2_ratio})"
            else:
                seg_suffix = f" ({expected_law2})"

            if law3_done and law3_ratio:
                ind_suffix = f" ({law3_ratio})"
            else:
                ind_suffix = f" ({expected_law3})"

            self.law_status_var.set(
                f"{box(law1_done)} Law of Dominance     "
                f"{box(law2_done)} Law of Segregation{seg_suffix}     "
                f"{box(law3_done)} Law of Independent Assortment{ind_suffix}"
            )

            # OPTIONAL: make the whole label grey while nothing is discovered yet
            # (Tkinter can't color only part of a single Label's text)
            if hasattr(self, "law_status_label"):
                if not (law1_done or law2_done or law3_done):
                    # all three still undiscovered -> show text in soft grey
                    self.law_status_label.configure(fg="#888888")
                else:
                    # at least one discovered -> normal black text
                    self.law_status_label.configure(fg="#000000")

        except Exception:
            # Don’t crash the simulation just because of a cosmetic label
            pass



    def _update_header(self):
        def _mon_name(m):
            names = ['January','February','March','April','May','June','July','August','September','October','November','December']
            try:
                return names[int(m)-1]
            except Exception:
                return str(m)
        def _fmt_clock(h, mi):
            try:
                return f"{int(h):02d}:{int(mi):02d}"
            except Exception:
                return '06:00'
        try:
            mon = _mon_name(getattr(self.garden, 'month', 4))
            yr = getattr(self.garden, 'year', 1856)
            dom = getattr(self.garden, 'day_of_month', getattr(self.garden, 'day', 1))
            wx = getattr(self.garden, 'weather', '')
            hh = getattr(self.garden, 'clock_hour', 6)
            mm = getattr(self.garden, 'clock_minute', 0)
            tmp = f"{getattr(self.garden, 'temp', 0.0):.1f}°C" if hasattr(self.garden, 'temp') else ''
            self.header_label.configure(text=f"📅 {mon} {yr} — Day {dom} — { _fmt_clock(hh,mm) } — {wx}  {tmp}")
        except Exception:
            pass


# ============================================================================
# Rendering Methods
# ============================================================================
    def render_all(self):
        try:
            self._update_header()
        except Exception:
            pass

        # 🌗 Apply day/night only if enabled
        if getattr(self, "enable_daynight", True):
            try:
                self._apply_daynight_to_tiles()
            except Exception as e:
                print("day/night failed:", e)
        else:
            # restore base soil colors when disabled
            for t in self.tiles:
                base = getattr(t, "base_soil", None)
                if base:
                    t.set_soil_color(base)

        self.garden.drift_temperature_once()

        if hasattr(self, "starter_var"):
            self.starter_var.set(f"Starter: {self.available_seeds}")

        if hasattr(self, "seed_counter_var"):
            try:
                self.seed_counter_var.set(f"Seeds: {len(self.harvest_inventory)}")
            except Exception:
                pass

        # --- Update Mendelian law status in top bar ---
        self._update_law_status_label()
        # if not hasattr(self, "tile_buttons"):
        #     return

        # --- multi-selection set (may be empty) ---
        sel_set = getattr(self, "multi_selected_indices", None) or set()

        for i, tile in enumerate(self.tiles):
            # Determine selection state (single + multi-select)
            is_sel = (getattr(self, "selected_index", None) == i) or (i in sel_set)
            tile.selected = is_sel

            # Ensure the tile icon exists for this plant before rendering
            if tile.plant is not None and getattr(tile.plant, "alive", True):
                self._ensure_tile_icon(tile.plant, selected=is_sel)

            tile.render()

        # Update centered header (Day / Phase / Weather)
        try:
            mon_names = ['January','February','March','April','May','June','July','August','September','October','November','December']
            mon = mon_names[getattr(self.garden, 'month', 4)-1] if 1 <= getattr(self.garden, 'month', 4) <= 12 else str(getattr(self.garden, 'month', 4))
            dom = getattr(self.garden, 'day_of_month', getattr(self.garden, 'day', 1))
            yr  = getattr(self.garden, 'year', 1856)
            hh  = getattr(self.garden, 'clock_hour', 6)
            mm  = getattr(self.garden, 'clock_minute', 0)
            wx  = getattr(self.garden, 'weather', '')
            tmp = f"{getattr(self.garden, 'temp', 0.0):.1f}°C" if hasattr(self.garden, 'temp') else ''
            clock = f"{int(hh):02d}:{int(mm):02d}"
            self.phase_label.configure(text=f"{dom} {mon} {yr} — {clock} — {wx} {tmp}")
            try:
                # Season overlay info suppressed from status bar to avoid permanent message
                # (kept available via self._season_mode for other UI components if needed)
                mode = getattr(self, '_season_mode', 'off')
                # intentionally not writing to self.status_var here
            except Exception:
                pass
        except Exception:
            pass
        self._render_selection_panel()
        
    def _label_with_bold_gender(self, parent, text, base_font=("Segoe UI", 12), bold_font=("Segoe UI", 12, "bold")):
        """Create inline labels where ♀ and ♂ are bold for visibility."""
        container = tk.Frame(parent)
        parts = re.split(r'([♀♂])', text)
        for part in parts:
            if not part:
                continue
            if part in ("♀", "♂"):
                tk.Label(container, text=part, font=bold_font).pack(side="left")
            else:
                tk.Label(container, text=part, font=base_font).pack(side="left")
        return container

    def _render_selection_panel(self):
        idx = getattr(self, "selected_index", None)

        # fall back to multi-select if needed
        if idx is None:
            sel = getattr(self, "multi_selected_indices", None) or set()
            if sel:
                idx = min(sel)

        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None


        # Ensure all eligible traits are revealed for any living plant
        try:
            if plant and getattr(plant, 'alive', True):
                plant.reveal_all_available()
        except Exception:
            pass

        # --- lightweight cache to avoid flicker ---
        try:
            if plant is None:
                sig = ("none",)
            else:
                try:
                    # Prefer revealed_traits; fall back to full traits dict
                    revealed = getattr(plant, "revealed_traits", None)
                    if not revealed:
                        revealed = getattr(plant, "traits", {}) or {}
                except Exception:
                    revealed = {}

                sig = (
                    getattr(self, "selected_index", None),  # Use selected_index (display_index doesn't exist in this version)
                    getattr(plant, "id", None),
                    getattr(plant, "stage", None),
                    tuple(sorted(getattr(revealed, "items", lambda: [])())),
                    getattr(plant, "alive", None),
                )
        except Exception:
            sig = None

        # Guard: no plant (empty tile) - show empty icon and "free"
        if plant is None:
            try:
                self.id_label.configure(text="")  # No # for empty plot
                self.gen_label.configure(text="")  # Clear generation
                self.stage_label.configure(text='free')  # Show "free"
                
                # Show empty icon
                if hasattr(self, 'empty_icon') and self.empty_icon:
                    self.plant_icon_label.configure(image=self.empty_icon)
                    self.plant_icon_label.image = self.empty_icon
                else:
                    self.plant_icon_label.configure(image='')
            except Exception as e:
                print("clear selection failed:", e)

            try:
                self.water_btn.configure(state="disabled")
                self.inspect_btn.configure(state="disabled")
                self.harvest_btn.configure(state="disabled")
                self.pollen_btn.configure(state="disabled")
            except Exception as e:
                print("button disable failed:", e)

            # Clear the cached signature
            self._sel_traits_sig = None
            return

        # ALWAYS update selection when we have a plant (moved before cache check)
        try:
            # Check if plant is dead
            is_dead = not getattr(plant, "alive", True)
            
            if is_dead:
                # Show dead plant
                self.id_label.configure(text="")  # No # for dead plant
                self.gen_label.configure(text="")  # Clear generation
                self.stage_label.configure(text='dead')  # Show "dead"
                
                # Show dead icon
                if hasattr(self, 'dead_icon') and self.dead_icon:
                    self.plant_icon_label.configure(image=self.dead_icon)
                    self.plant_icon_label.image = self.dead_icon
                else:
                    self.plant_icon_label.configure(image='')
                
                # Disable most buttons for dead plant
                self.water_btn.configure(state="disabled")
                self.inspect_btn.configure(state="disabled")
                self.harvest_btn.configure(state="disabled")
                self.pollen_btn.configure(state="disabled")
                return
            
            # Living plant - update normally
            # Update ID and generation text labels
            self.id_label.configure(text=f"#{plant.id}")
            self.gen_label.configure(text=plant.generation)
            
            # Debug output
            print(f"[SELECTION] Updating: #{plant.id} {plant.generation}")
            
            # Update plant icon
            try:
                # Ensure the icon is loaded
                self._ensure_tile_icon(plant)
                
                if hasattr(plant, 'img_obj') and plant.img_obj:
                    self.plant_icon_label.configure(image=plant.img_obj)
                    self.plant_icon_label.image = plant.img_obj  # Keep reference
                    print(f"[SELECTION] Updated plant icon")
                else:
                    # Show placeholder if no icon
                    if hasattr(self, 'placeholder_label') and self.placeholder_label:
                        self.plant_icon_label.configure(image='')
                    print(f"[SELECTION] No plant icon available")
            except Exception as e:
                print(f"[WARNING] Failed to update plant icon: {e}")
            
            # Update stage label (centered below icon)
            try:
                stage_name = STAGE_NAMES.get(plant.stage, plant.stage)
                self.stage_label.configure(text=stage_name)
            except Exception as e:
                print(f"[WARNING] Failed to update stage label: {e}")
            
            self.water_btn.configure(state="normal")
            self.inspect_btn.configure(state="normal")
            self.harvest_btn.configure(state=("normal" if (plant.stage >= 7 and plant.alive) else "disabled"))
        except Exception as e:
            print(f"[ERROR] Failed to update selection: {e}")

        # NOW check cache for traits rendering
        prev_sig = getattr(self, "_sel_traits_sig", None)
        if prev_sig == sig:
            # Nothing important changed since last render; keep existing trait widgets
            return

        # Cache new signature so we only re-render traits when something actually changes
        self._sel_traits_sig = sig

        for w in self.traits_container.winfo_children():
            w.destroy()

        # --- badges for emasculation / pollination ---
        try:
            badges = []

            # Emasculation badge (if applicable)
        #    if getattr(plant, "emasculated", False):
        #        d = getattr(plant, "emasc_day", None)
        #        ph = getattr(plant, "emasc_phase", None)
        #        frac = int(100 * float(getattr(plant, "selfing_frac_before_emasc", 0.0)))
        #        badges.append(f"E (day {d}, {ph})")

            # Pollination donor
            pc = getattr(plant, "pending_cross", None)
            donor_id = None

            if isinstance(pc, dict):
                donor_id = pc.get("donor_id")
            elif pc:
                donor_id = getattr(pc, "donor_id", None)

            if donor_id:
                badges.append(f"Pollinated by #{donor_id}")

            # Render badge label
            if badges:
                lbl = tk.Label(
                    self.traits_container,
                    text="  •  ".join(badges),
                    font=("Segoe UI", 12, "italic"),
                    fg="#5da8d0"
                )
                lbl.pack(anchor="w", pady=(0))

        except Exception as e:
            print("Badge block failed:", e)
            self.water_btn.configure(state="disabled")
            self.inspect_btn.configure(state="disabled")
            self.harvest_btn.configure(state="disabled")
            return


        # Pollen button state (already updated above, but check again for pollen)
        ok, _ = plant.can_collect_pollen()
        try:
            self.pollen_btn.configure(state=("normal" if ok else "disabled"))
        except Exception:
            pass

        
        if getattr(plant, "revealed_traits", None):
            trait_order = ["plant_height","flower_position","flower_color","pod_shape","seed_shape","seed_color"]
            # Two-column grid container
            tbl = tk.Frame(self.traits_container)
            tbl.pack(anchor="w", padx=(0,6), pady=(0,4))
            try:
                tbl.grid_columnconfigure(0, weight=1, uniform="traits")
                tbl.grid_columnconfigure(1, weight=1, uniform="traits")
            except Exception:
                pass
            t_index = 0
            for k in trait_order:
                if k in plant.revealed_traits:
                    v = plant.revealed_traits[k]
                    cell = tk.Frame(tbl)
                    r, c = divmod(t_index, 2)   # 2 columns
                    try:
                        cell.grid(row=r, column=c, padx=(0,8), pady=(0,8), sticky="nw")
                    except Exception:
                        # Fallback if grid misbehaves
                        cell.pack(anchor="w", padx=(0,8), pady=(0,8))
                    icon_used = ""
                    if k == "flower_position":
                        try:
                            pos = v
                            col = plant.revealed_traits.get("flower_color") or getattr(plant, "traits", {}).get("flower_color")
                            if pos and col:
                                hi = flower_icon_path_hi(pos, col)
                                if hi:
                                    img = safe_image(hi)
                                    icon_lbl = tk.Label(cell, image=img)
                                    icon_lbl.image = img
                                    icon_lbl.pack(anchor="center")
                                    icon_used = "hi"
                        except Exception:
                            pass
                    if not icon_used and k == "pod_shape":
                        try:
                            shape = v
                            col = plant.revealed_traits.get("pod_color")
                            if shape and col:
                                p = pod_shape_icon_path(shape, col)
                                if p:
                                    img = safe_image(p)
                                    icon_lbl = tk.Label(cell, image=img)
                                    icon_lbl.image = img
                                    icon_lbl.pack(anchor="center")
                                    icon_used = "pod"
                        except Exception:
                            pass
                    if not icon_used:
                        icon_path = trait_icon_path(k, v)
                        if icon_path:
                            img = safe_image(icon_path)
                            icon_lbl = tk.Label(cell, image=img)
                            icon_lbl.image = img
                            icon_lbl.pack(anchor="center")
                    tk.Label(cell, text=str(v)).pack(anchor="center")
                    t_index += 1

     # ---------- Pollen helpers ----------


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_pollinate(self):
        """
        If exactly one viable pollen source exists today, auto-apply it.
        Otherwise open Summary focused on Pollen tab so user can pick.
        """
        # Must have a valid recipient selected
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None
        if not plant or not getattr(plant, "alive", False):
            self._toast("Select a living recipient plant first.")
            return

        today = self._today()

        # Gather viable pollen packets (same-day only)
        try:
            packets = self.inventory.get_all("pollen") if hasattr(self.inventory, "get_all") else []
        except Exception:
            packets = []

        def get_expires_day(pkt):
            try:
                if isinstance(pkt, dict):
                    return int(pkt.get("expires_day", -999999))
                return int(getattr(pkt, "expires_day", -999999))
            except Exception:
                return -999999

        viable = [p for p in packets if get_expires_day(p) == today]

        # Group by source_id
        groups = defaultdict(list)
        for p in viable:
            try:
                sid = int(p.get("source_id")) if isinstance(p, dict) else int(getattr(p, "source_id", 0) or 0)
            except Exception:
                sid = 0
            groups[sid].append(p)

        # Auto-apply if exactly one pollen source is available
        if len(groups) == 1 and len(viable) > 0:
            only_sid = next(iter(groups.keys()))
            pkt = groups[only_sid][0]
            self._apply_pollen(pkt)
            return

        # Otherwise open the chooser (current behavior)
        try:
            pop = InventoryPopup(self.root, self.garden, self.inventory, self._on_seed_selected, app=self)
            try:
                self.summary_popup = pop
            except Exception:
                pass

            try:
                pop.nb.select(pop.pollen_frame)
            except Exception:
                pass

            try:
                pop.lift()
                pop.focus_force()
            except Exception:
                pass

        except Exception as e:
            self._toast(f"Could not open pollen chooser: {e}")

    def _on_collect_pollen(self):
        """Collect 10 anthers (10 pollen packets) from selected plant if inspected today and anthers are available."""
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None

        if not plant or not getattr(plant, "alive", False):
            self._toast("Select a living plant first.")
            return

        today = self._today()

        # ---must inspect flowers first (today) ---
        if getattr(plant, "last_anther_check_day", None) != today:
            self._toast("You must inspect the flowers first (Inspect) before collecting pollen.")
            return

        if not bool(getattr(plant, "anthers_available_today", False)):
            self._toast("No mature anthers available today — cannot collect pollen.")
            return

        if getattr(plant, "anthers_collected_day", None) == today:
            self._toast("You already collected anthers from this plant today.")
            return

        # Keep your existing biological constraints (flowering stage, health, etc.)
        ok, reason = plant.can_collect_pollen()
        if not ok:
            self._toast(f"Cannot collect pollen: {reason}")
            return

        def set_field(pkt, key, value):
            if isinstance(pkt, dict):
                pkt[key] = value
            else:
                setattr(pkt, key, value)

        # --- Collect 10 anthers as 10 pollen packets ---
        n_anthers = 10
        for i in range(n_anthers):
            packet = Pollen(
                id=random.randint(100000, 999999),
                name=f"Anther {i+1}/{n_anthers} from #{plant.id} (Day {today})",
                source_plant=plant,
                collection_time=getattr(self.garden, "clock_hour", 6),
            )

            # IDs / source
            set_field(packet, "source_id", int(getattr(plant, "id", 0) or 0))

            # Genotype / traits snapshots
            set_field(packet, "genotype", dict(getattr(plant, "genotype", {}) or {}))
            set_field(packet, "traits",   dict(getattr(plant, "traits",   {}) or {}))

            # Viability: same-day only (keep your existing "stale" behavior)
            for k in ("collected_day", "day_collected", "collected_on_day"):
                set_field(packet, k, today)
            for k in ("expires_day", "expiry_day", "valid_until_day"):
                set_field(packet, k, today)

            self.inventory.add(packet)

        # Consume today's anther availability and mark collection done
        try:
            plant.anthers_collected_day = today
            plant.anthers_available_today = False
        except Exception:
            pass

        self._toast(f"Collected {n_anthers} anthers from plant #{plant.id}.")
        self.render_all()

        # If Summary is open, refresh to show new pollen immediately
        try:
            if getattr(self, "summary_popup", None) is not None and self.summary_popup.winfo_exists():
                self.summary_popup.refresh_current_tab()
        except Exception:
            pass

    def _apply_pollen(self, packet):
        """Apply selected pollen to the currently selected plant (with interactive dialog)."""

        if packet is None:
            self._toast("No pollen selected.")
            return

        packet_obj = packet  # keep original for inventory removal

        # --- normalize packet (Pollen object → dict-like) ---
        if not isinstance(packet, dict):
            src = getattr(packet, "source_plant", None)
            packet = {
                "id": getattr(packet, "id", None),
                "source_id": getattr(src, "id", "?") if src else "?",
                "genotype": dict(getattr(src, "genotype", {})) if src and getattr(src, "genotype", None) else None,
                "traits": dict(getattr(src, "traits", {})) if src else {},
                "expires_day": getattr(packet, "expires_day", self._today()),
            }
        else:
            packet.setdefault("id", None)

        # --- recipient plant ---
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None

        if not plant or not getattr(plant, "alive", True):
            self._toast("Select a living recipient plant first.")
            return

        if getattr(plant, "stage", None) != 5:
            self._toast("Recipient must be flowering (Stage 5).")
            return

        if getattr(self.garden, "phase", None) not in ("morning", "noon"):
            self._toast("Apply pollen in morning or noon.")
            return

        # --- viability check BEFORE consuming ---
        today = self._today()
        try:
            if int(packet.get("expires_day", -1)) != int(today):
                self._toast("This pollen is no longer viable.")
                return
        except Exception:
            self._toast("This pollen is no longer viable.")
            return

        # --- All checks passed, now show interactive pollination dialog ---
        
        # Get flower color
        flower_color = plant.traits.get('flower_color', 'purple')
        
        # Check if emasculated
        is_emasculated = getattr(plant, 'emasculated', False)
        
        # Pollen source name
        pollen_source_id = packet.get('source_id', '?')
        pollen_source_name = f"Plant #{pollen_source_id}"
        
        def on_pollination_complete(success):
            """Callback when pollination dialog completes."""
            if not success:
                # User cancelled - don't consume pollen
                self._toast("Pollination cancelled", level="info")
                return
            
            # User successfully clicked stigma - apply pollination
            
            # --- genotypes ---
            maternal_geno = getattr(plant, "genotype", None)
            if not maternal_geno:
                maternal_geno = infer_genotype_from_traits(getattr(plant, "traits", {}), random)

            donor_geno = packet.get("genotype")
            if not donor_geno:
                donor_geno = infer_genotype_from_traits(packet.get("traits", {}), random)

            # --- record pending cross ---
            pc = getattr(plant, "pending_cross", {}) or {}
            donors = pc.setdefault("donors", [])
            donors.append({
                "donor_id": packet.get("source_id", "?"),
                "donor_genotype": dict(donor_geno),
                "day": getattr(self.garden, "day", None),
            })
            plant.pending_cross = pc
            plant.pollinated = True

            # Pods for emasculated plants only after successful pollination
            if getattr(plant, "emasculated", False) and int(getattr(plant, "pods_remaining", 0) or 0) <= 0:
                plant.pods_remaining = int(getattr(plant, "pods_total", 0) or 0)
                plant.ovules_left = int(getattr(plant, "ovules_per_pod", 0) or 0)

            # --- NOW consume pollen (single-use) ---
            consumed = False
            try:
                if hasattr(self.inventory, "remove"):
                    self.inventory.remove(packet_obj)
                    consumed = True
            except Exception:
                consumed = False

            if not consumed:
                pid = packet.get("id", None)
                try:
                    if pid is not None and hasattr(self.inventory, "items"):
                        self.inventory.items = [x for x in self.inventory.items if getattr(x, "id", None) != pid]
                except Exception:
                    pass

            # Refresh summary popup if open
            try:
                if getattr(self, "summary_popup", None) is not None and self.summary_popup.winfo_exists():
                    self.summary_popup.refresh_current_tab()
            except Exception:
                pass

            self._toast(f"Pollinated ♀#{plant.id} with ♂#{packet.get('source_id')}")
            self.render_all()
        
        # Show the interactive pollination dialog
        try:
            dialog = PollinationDialog(
                self.root,
                flower_color=flower_color,
                is_emasculated=is_emasculated,
                pollen_source=pollen_source_name,
                callback=on_pollination_complete
            )
        except Exception as e:
            # Fallback if dialog fails - apply directly
            print(f"Pollination dialog failed: {e}, applying directly")
            on_pollination_complete(True)
   
    # ---------- Events ----------
    def _open_tie_for_selected(self, event=None):
        """Open Trait Inheritance Explorer for the currently selected plant."""
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None
        if not plant:
            self._toast("Select a plant first.", level="info")
            return

        try:
            self._seed_archive_safe()
        except Exception:
            pass

        pid = getattr(plant, "id", None)
        if pid is None:
            return

        self.open_history_archive_browser(self.root, default_pid=pid)


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_genetics(self):
        idx = self.selected_index
        plant = self.tiles[idx].plant if (idx is not None) else None

        win = tk.Toplevel(self.root)
        win.title("Genotype Viewer")

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True)
        toolbar = tk.Frame(win)
        toolbar.pack(fill="x", padx=6, pady=(6,2))

        def _reveal_alleles():
            """Reveal all hidden allele labels in this Genetics window."""
            def _walk(widget):
                # If the widget is one of our allele labels, restore its true text
                if hasattr(widget, "_allele_real"):
                    try:
                        widget.config(text=getattr(widget, "_allele_real", ""))
                    except Exception:
                        pass
                # Recurse into children (Frames, etc.)
                try:
                    for child in widget.winfo_children():
                        _walk(child)
                except Exception:
                    pass

            _walk(win)

            # Mark in this session that we used the genotype reveal (cheat).
            # Any export after this will be annotated in the .txt file.
            self._genotype_revealed = True

        def _open_history_archiveonly():

            # Archive Browser: ensure archive is populated, then open
            idx_now = getattr(self, "selected_index", None)
            _plant = None
            if idx_now is not None:
                try:
                    pass
                    _plant = self.tiles[idx_now].plant
                except Exception:
                    _plant = None
            if _plant is None:
                _plant = getattr(self, "selected_plant", None)
            _pid = getattr(_plant, "id", None) if _plant is not None else None

            # Pre-seed archive (force where supported) for the freshest view
            try:
                self._seed_archive_safe()
            except Exception:
                pass

            # Prefer the dedicated browser, else fall back to History viewer in archive-only mode
            self.open_history_archive_browser(self.root, default_pid=_pid)
            
        btn = tk.Button(
            toolbar,
            text="  Reveal Genotype  ",
            command=_reveal_alleles,
            **self.button_style,
        )
        self._apply_hover(btn)
        btn.pack(side="left", padx=(0,6))
        btn = tk.Button(
            toolbar,
            text=" Trait Inheritance Explorer ",
            command=_open_history_archiveonly,
            **self.button_style,
        )
        self._apply_hover(btn)
        btn.pack(side="left", padx=(6,0))

        logging.debug("[Genetics] Buttons created: Trait Inheritance Explorer")

        def _find_by_id_local(pid):
            try:
                for tile in self.tiles:
                    if tile.plant is not None and getattr(tile.plant, "id", None) == pid:
                        return tile.plant
            except Exception:
                pass
            return None
        def _find_any(pid):
            # 1) live grid
            pl = _find_by_id_local(pid)
            if pl is not None:
                return pl
            # 2) registry
            try:
                reg = getattr(self, 'registry', {}) or {}
                pl = reg.get(int(pid)) or reg.get(str(pid))
                if pl is not None:
                    return pl
            except Exception:
                pass
            # 3) hidden ghosts
            try:
                for gp in getattr(self, 'hidden_plants', []) or []:
                    if gp is not None and getattr(gp, 'id', None) == pid:
                        return gp
            except Exception:
                pass
            # 4) archive snapshot
            try:
                if hasattr(self, '_archive_get'):
                    return self._archive_get(pid)
            except Exception:
                pass
            return None

        def _allele_str(geno, loci):
            """
            For a single locus (e.g. ['A']) return strings like 'A/A', 'A/a', 'a/a',
            i.e. only the alleles, no extra leading 'A '. For multiple loci we keep
            the locus label for clarity (e.g. 'P: P/p; V: V/v').
            """
            parts = []
            single = (len(loci) == 1)
            for loc in loci:
                pair = geno.get(loc, ('?','?'))
                a1 = pair[0] if len(pair) > 0 else '?'
                a2 = pair[1] if len(pair) > 1 else '?'
                if single:
                    # Just show A/a, A/A, a/a …
                    parts.append(f"{a1}/{a2}")
                else:
                    # For combined rows (P/V + Gp) keep locus labels
                    parts.append(f"{loc}: {a1}/{a2}")
            return "; ".join(parts)

        def _table_row(tbl, r, trait_label, icon_path, chrom_text, allele_text, why):
            cell = tk.Frame(tbl)
            cell.grid(row=r, column=0, padx=(6,6), pady=(2,0), sticky="w")
            tk.Label(cell, text=trait_label, font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0,6))
            img = safe_image_scaled(icon_path, 2, 2)
            icon_lbl = tk.Label(cell, image=img); icon_lbl.image = img
            icon_lbl.pack(side="left")

            # Chromosome column (new)
            chrom_lbl = tk.Label(tbl, text=str(chrom_text or ""), font=("Segoe UI", 12))
            chrom_lbl.grid(row=r, column=1, sticky="w", padx=6)

            # Alleles are stored but initially hidden; they will be revealed by a button.
            alle = tk.Label(tbl, text="•••", font=("Segoe UI", 12, "bold"))
            alle._allele_real = allele_text  # stash the true text here
            alle.grid(row=r, column=2, sticky="w", padx=6)

            # Only create a text label in the "Why" column if we actually have text.
            if why:
                why_lbl = tk.Label(tbl, text=why, font=("Segoe UI", 12))
                why_lbl.grid(row=r, column=3, sticky="w", padx=6)
                _attach_tooltip(why_lbl, why)

            sep = tk.Frame(tbl, height=1, bg="#DDDDDD")
            sep.grid(row=r+1, column=0, columnspan=4, sticky="ew", padx=6, pady=(2,2))
            return r+2

        def _tab_meta(frame, plant_obj):
            try:
                if not plant_obj:
                    return
                m = getattr(plant_obj, "mother_id", None)
                f = getattr(plant_obj, "father_id", None)
                
                                # fallback to ancestry for mother if missing
                if m is None:
                    anc = list(getattr(plant_obj, 'ancestry', []) or [])
                    if anc:
                        m = anc[-1]
                if f is None:
                    panc = list(getattr(plant_obj, 'paternal_ancestry', []) or [])
                    if panc:
                        f = panc[-1]
                badges = []
                if getattr(plant_obj, "selfed", False) or (m is not None and f is not None and m == f):
                    badges.append("selfed")
                meta = f"Parents: mother #{m if m is not None else '?'}  |  father #{f if f is not None else '?'}"
                if badges:
                    meta += "   [" + ", ".join(badges) + "]"
                tk.Label(frame, text=meta, font=("Segoe UI", 12, "italic")).pack(anchor="w", padx=8, pady=(4,6))
            except Exception:
                pass

        def _legend_genetics(parent):

            # Legend removed in Genetics window

            pass


        def _fill_tab(frame, plant_obj, label_hint):
            if plant_obj is None:
                tk.Label(
                    frame,
                    text=f"{label_hint}: unknown...",
                    font=("Segoe UI", 12, "italic")
                ).pack(anchor="w", padx=8, pady=6)
                return

            geno = getattr(plant_obj, "genotype", None) or {}
            ph = phenotype_from_genotype(geno) if geno else dict(getattr(plant_obj, "traits", {}))

            tbl = tk.Frame(frame)
            tbl.pack(fill="x", expand=True)

            # Extra column 4 for the '?' button
            for c in (0, 1, 2, 3, 4):
                tbl.grid_columnconfigure(c, weight=(0 if c == 0 else 1))

            tk.Label(tbl, text="Trait",       font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=6)
            tk.Label(tbl, text="Chr.", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w", padx=6)
            tk.Label(tbl, text="Alleles",     font=("Segoe UI", 12, "bold")).grid(row=0, column=2, sticky="w", padx=6)
            tk.Label(tbl, text="Why",         font=("Segoe UI", 12, "bold")).grid(row=0, column=3, sticky="w", padx=6)
            rowi = 1

            # --------------------------------------------------------
            # Flower color (A)
            # --------------------------------------------------------
            fc = ph.get("flower_color", "")
            icon_fc = trait_icon_path("flower_color", fc)
            alle_fc = _allele_str(geno, ["A"])

            base_row = rowi
            rowi = _table_row(
                tbl, rowi,
                "Flower color",
                icon_fc,
                "6",  # Chromosome 6 (A locus)
                alle_fc,
                ""  # leave explanation empty; we place our own
            )

            short_fc = "Flower color depends on anthocyanin production controlled by A."
            expl_long_fc = (
                "The A gene controls the plant’s ability to make anthocyanin pigment. Plants with "
                "at least one A allele (A/A or A/a) produce purple flowers. Plants with the recessive "
                "genotype a/a cannot produce anthocyanin and therefore have white flowers.\n\n"
                "In short:\n"
                "– A/_ → purple\n"
                "– a/a → white"
            )

            lbl_fc = tk.Label(
                tbl,
                text=short_fc,
                font=("Segoe UI", 12),
                justify="left",
                anchor="w",
                wraplength=350,
            )
            lbl_fc.grid(row=base_row, column=3, sticky="w", padx=6)

            def _show_fc_expl():
                popup = tk.Toplevel(win)
                popup.title("Flower color genetics")
                popup.transient(win)

                outer = tk.Frame(popup, bd=2, relief="groove", padx=12, pady=12)
                outer.pack(fill="both", expand=True)

                tk.Label(
                    outer,
                    text=short_fc,
                    font=("Segoe UI", 13, "bold"),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

                tk.Label(
                    outer,
                    text=expl_long_fc,
                    font=("Segoe UI", 12),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x")

                tk.Button(outer, text="Close", command=popup.destroy).pack(pady=(10, 0), anchor="e")

            btn_fc = tk.Button(tbl, text="?", width=2, command=_show_fc_expl)
            btn_fc.grid(row=base_row, column=4, sticky="w", padx=6)

            # --------------------------------------------------------
            # Plant height (Le)
            # --------------------------------------------------------
            phgt = ph.get("plant_height", "")
            icon_phgt = trait_icon_path("plant_height", phgt)
            alle_phgt = _allele_str(geno, ["Le"])

            base_row = rowi
            rowi = _table_row(
                tbl, rowi,
                "Plant height",
                icon_phgt,
                "5",  # Chromosome 5 (Le locus)
                alle_phgt,
                ""
            )

            short_phgt = "Plant height is controlled by Le."
            expl_long_phgt = (
                "The Le gene regulates stem elongation. Plants with at least one Le allele (Le/Le or "
                "Le/le) produce enough growth hormone to grow tall. Plants with le/le produce much less "
                "and grow as short dwarf plants.\n\n"
                "In short:\n"
                "– Le/_ → tall\n"
                "– le/le → dwarf"
            )

            lbl_phgt = tk.Label(
                tbl,
                text=short_phgt,
                font=("Segoe UI", 12),
                justify="left",
                anchor="w",
                wraplength=350,
            )
            lbl_phgt.grid(row=base_row, column=3, sticky="w", padx=6)

            def _show_phgt_expl():
                popup = tk.Toplevel(win)
                popup.title("Plant height genetics")
                popup.transient(win)

                outer = tk.Frame(popup, bd=2, relief="groove", padx=12, pady=12)
                outer.pack(fill="both", expand=True)

                tk.Label(
                    outer,
                    text=short_phgt,
                    font=("Segoe UI", 13, "bold"),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

                tk.Label(
                    outer,
                    text=expl_long_phgt,
                    font=("Segoe UI", 12),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x")

                tk.Button(outer, text="Close", command=popup.destroy).pack(pady=(10, 0), anchor="e")

            btn_phgt = tk.Button(tbl, text="?", width=2, command=_show_phgt_expl)
            btn_phgt.grid(row=base_row, column=4, sticky="w", padx=6)

            # --------------------------------------------------------
            # Pod color / shape (P, V, Gp)
            # --------------------------------------------------------
            pod_shape = ph.get("pod_shape", "")
            pod_color = ph.get("pod_color", "")
            icon_pod = pod_shape_icon_path(pod_shape, pod_color)

            pod_alleles = (
                f"{_allele_str(geno, ['P'])}; "
                f"{_allele_str(geno, ['V'])} | "
                f"{_allele_str(geno, ['Gp'])}"
            )

            base_row = rowi
            rowi = _table_row(
                tbl, rowi,
                "Pod color/shape",
                icon_pod,
                "1, 3, 5",  # P: chr1; Gp: chr3; V: chr5
                pod_alleles,
                ""
            )

            short_pod = (
                "Pod shape and color depend on P, V and Gp. "
                "V shares a chromosome with Le (height) and Gp shares one with R (seed shape)."
            )

            expl_long_pod = (
                "Pod shape depends on two genes, P and V. For a pod to be fully inflated, the plant "
                "needs at least one dominant allele at both loci (P/_ and V/_). If either gene is "
                "homozygous recessive (p/p or v/v), the pods become constricted around the seeds and "
                "look more pointed.\n\n"
                "Pod color is controlled by the Gp gene. Plants with at least one Gp allele (Gp/Gp or "
                "Gp/gp) produce chlorophyll in the pod wall, making pods green. Plants with gp/gp lack "
                "this green color and have yellow pods.\n\n"
                "In short:\n"
                "– P/_ V/_ → inflated\n"
                "– p/p or v/v → constricted\n"
                "– Gp/_ → green pods\n"
                "– gp/gp → yellow pods\n\n"
                "Chromosome locations and linkage\n"
                "• P is on chromosome 1.\n"
                "• Gp is on chromosome 3, on the same chromosome as R (seed shape).\n"
                "• V is on chromosome 5, on the same chromosome as Le (plant height).\n\n"
                "In this simulator, Le and V are modelled as closely linked (~12.6% recombination), "
                "and R and Gp as more weakly linked (~30% recombination). That means some crosses involving these loci "
                "deviate from the classic 9:3:3:1 F2 ratio and illustrate genetic linkage as an "
                "exception to Mendel’s third law (independent assortment)."
            )


            lbl_pod = tk.Label(
                tbl,
                text=short_pod,
                font=("Segoe UI", 12),
                justify="left",
                anchor="w",
                wraplength=350,
            )
            lbl_pod.grid(row=base_row, column=3, sticky="w", padx=6)

            def _show_pod_expl():
                popup = tk.Toplevel(win)
                popup.title("Pod color and shape genetics")
                popup.transient(win)

                outer = tk.Frame(popup, bd=2, relief="groove", padx=12, pady=12)
                outer.pack(fill="both", expand=True)

                tk.Label(
                    outer,
                    text=short_pod,
                    font=("Segoe UI", 13, "bold"),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

                tk.Label(
                    outer,
                    text=expl_long_pod,
                    font=("Segoe UI", 12),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x")

                tk.Button(outer, text="Close", command=popup.destroy).pack(pady=(10, 0), anchor="e")

            btn_pod = tk.Button(tbl, text="?", width=2, command=_show_pod_expl)
            btn_pod.grid(row=base_row, column=4, sticky="w", padx=6)

            # --------------------------------------------------------
            # Seed shape (R)
            # --------------------------------------------------------
            sd_shape = ph.get("seed_shape", "")
            icon_sd_shape = trait_icon_path("seed_shape", sd_shape)
            alle_sd_shape = _allele_str(geno, ["R"])

            base_row = rowi
            rowi = _table_row(
                tbl, rowi,
                "Seed shape",
                icon_sd_shape,
                "3",  # Chromosome 3 (R locus)
                alle_sd_shape,
                ""
            )

            short_sd_shape = "Seed shape is controlled by R, which affects starch production."
            expl_long_sd_shape = (
                "The R gene controls how starch fills the developing seed. Plants with at least one "
                "R allele (R/R or R/r) produce normal starch, giving round seeds. Plants with r/r "
                "produce less starch, causing seeds to wrinkle when they dry.\n\n"
                "In short:\n"
                "– R/_ → round\n"
                "– r/r → wrinkled"
            )

            lbl_sd_shape = tk.Label(
                tbl,
                text=short_sd_shape,
                font=("Segoe UI", 12),
                justify="left",
                anchor="w",
                wraplength=350,
            )
            lbl_sd_shape.grid(row=base_row, column=3, sticky="w", padx=6)

            def _show_sdshape_expl():
                popup = tk.Toplevel(win)
                popup.title("Seed shape genetics")
                popup.transient(win)

                outer = tk.Frame(popup, bd=2, relief="groove", padx=12, pady=12)
                outer.pack(fill="both", expand=True)

                tk.Label(
                    outer,
                    text=short_sd_shape,
                    font=("Segoe UI", 13, "bold"),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

                tk.Label(
                    outer,
                    text=expl_long_sd_shape,
                    font=("Segoe UI", 12),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x")

                tk.Button(outer, text="Close", command=popup.destroy).pack(pady=(10, 0), anchor="e")

            btn_sdshape = tk.Button(tbl, text="?", width=2, command=_show_sdshape_expl)
            btn_sdshape.grid(row=base_row, column=4, sticky="w", padx=6)

            # --------------------------------------------------------
            # Seed color (I)
            # --------------------------------------------------------
            sd_color = ph.get("seed_color", "")
            icon_sd_color = trait_icon_path("seed_color", sd_color)
            alle_sd_color = _allele_str(geno, ["I"])

            base_row = rowi
            rowi = _table_row(
                tbl, rowi,
                "Seed color",
                icon_sd_color,
                "2",  # Chromosome 2 (I locus)
                alle_sd_color,
                ""
            )

            short_sd_color = "Seed color is regulated by I, which controls chlorophyll breakdown."
            expl_long_sd_color = (
                "The I gene determines how much chlorophyll remains in the seed as it matures. "
                "Plants with at least one I allele (I/I or I/i) break down chlorophyll and turn yellow. "
                "Seeds with the recessive genotype i/i retain chlorophyll and stay green.\n\n"
                "In short:\n"
                "– I/_ → yellow\n"
                "– i/i → green"
            )

            lbl_sd_color = tk.Label(
                tbl,
                text=short_sd_color,
                font=("Segoe UI", 12),
                justify="left",
                anchor="w",
                wraplength=350,
            )
            lbl_sd_color.grid(row=base_row, column=3, sticky="w", padx=6)

            def _show_sdcolor_expl():
                popup = tk.Toplevel(win)
                popup.title("Seed color genetics")
                popup.transient(win)

                outer = tk.Frame(popup, bd=2, relief="groove", padx=12, pady=12)
                outer.pack(fill="both", expand=True)

                tk.Label(
                    outer,
                    text=short_sd_color,
                    font=("Segoe UI", 13, "bold"),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

                tk.Label(
                    outer,
                    text=expl_long_sd_color,
                    font=("Segoe UI", 12),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x")

                tk.Button(outer, text="Close", command=popup.destroy).pack(pady=(10, 0), anchor="e")

            btn_sdcolor = tk.Button(tbl, text="?", width=2, command=_show_sdcolor_expl)
            btn_sdcolor.grid(row=base_row, column=4, sticky="w", padx=6)

            # --------------------------------------------------------
            # Flower position (Fa + Mfa)  – your existing pattern
            # --------------------------------------------------------
            fp = ph.get("flower_position", "")
            fc = ph.get("flower_color", "")
            fp_icon = flower_icon_path(fp, fc) or trait_icon_path("flower_position", fp)

            # Alleles column: Fa/Fa; Mfa/mfa (no 'Fa:' prefix)
            alle_fp = f"{_allele_str(geno, ['Fa'])}; {_allele_str(geno, ['Mfa'])}"

            base_row = rowi
            rowi = _table_row(
                tbl, rowi,
                "Flower position",
                fp_icon,
                "4",  # Chromosome 4 (Fa locus; Mfa is a modifier)
                alle_fp,
                ""  # leave explanation empty; we will place our own
            )

            # Short explanation (appears inline)
            short_expl = "Flower position is determined by Fa with modification by Mfa."

            lbl_short = tk.Label(
                tbl,
                text=short_expl,
                font=("Segoe UI", 12),
                justify="left",
                anchor="w",
                wraplength=350,
            )
            lbl_short.grid(row=base_row, column=3, sticky="w", padx=6)

            # Long explanation (popup text)
            expl_long = (
                "The Fa gene normally keeps flowers arranged along the stem (axial). "
                "Plants with two copies of the fa allele (fa/fa) tend to form a broader, "
                "flattened shoot tip. This pushes the flowers toward the very top, giving "
                "a terminal appearance.\n\n"
                "A second gene, Mfa, decides how strong this effect is. Plants with "
                "fa/fa mfa/mfa often look almost normal again because the widening of the "
                "stem tip is reduced. In contrast, fa/fa plants that still have at least "
                "one Mfa allele (Mfa/_) usually show clear terminal flowers.\n\n"
                "In short:\n"
                "– Fa/_ Mfa/_ → normal axial flowers\n"
                "– fa/fa Mfa/_ → clearly terminal flowers\n"
                "– fa/fa mfa/mfa → weakly terminal or near-normal"
            )

            def _show_flower_expl():
                popup = tk.Toplevel(win)
                popup.title("Flower position genetics")
                popup.transient(win)

                outer = tk.Frame(popup, bd=2, relief="groove", padx=12, pady=12)
                outer.pack(fill="both", expand=True)

                tk.Label(
                    outer,
                    text=short_expl,
                    font=("Segoe UI", 13, "bold"),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x", pady=(0, 8))

                tk.Label(
                    outer,
                    text=expl_long,
                    font=("Segoe UI", 12),
                    wraplength=520,
                    justify="left",
                    anchor="w",
                ).pack(fill="x")

                tk.Button(outer, text="Close", command=popup.destroy).pack(pady=(10, 0), anchor="e")

            # '?' button placed after the short text
            info_btn = tk.Button(tbl, text="?", width=2, command=_show_flower_expl)
            info_btn.grid(row=base_row, column=4, sticky="w", padx=6)

        if not plant:
            tab = tk.Frame(nb); nb.add(tab, text="(none)")
            tk.Label(tab, text="No plant selected.", font=("Segoe UI", 12, "italic")).pack(padx=8, pady=8, anchor="w")
        else:
            cur_tab = tk.Frame(nb); nb.add(cur_tab, text=f"{plant.generation} #{plant.id}")
            _tab_meta(cur_tab, plant); _fill_tab(cur_tab, plant, f"{plant.generation}"); _legend_genetics(cur_tab)

    # --- drag-selection helpers ---

    def _clear_drag_state(self):
        self._drag_start_x = None
        self._drag_start_y = None
        self._dragging_select = False


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_tile_left_press(self, event, index: int):
        """Start of a left-click: may become a drag-selection or a Shift-click multi-select."""

        # Detect Shift key (Tk uses a bitmask in event.state)
        try:
            is_shift = bool(event.state & 0x0001)
        except Exception:
            is_shift = False

        if is_shift:
            # --- SHIFT + left-click: add this tile to the selection, no drag ---
            try:
                if not hasattr(self, "multi_selected_indices") or self.multi_selected_indices is None:
                    self.multi_selected_indices = set()
            except Exception:
                self.multi_selected_indices = set()

            self.multi_selected_indices.add(index)
            self.selected_index = index

            # Optional: set anchor if none yet (useful for later Shift+Arrow)
            try:
                if getattr(self, "_kb_anchor_index", None) is None:
                    self._kb_anchor_index = index
            except Exception:
                pass

            # Make sure drag-selection does NOT start for Shift-click
            self._drag_start_x = None
            self._drag_start_y = None
            self._dragging_select = False

            try:
                self.render_all()
            except Exception:
                pass
            return

        # --- Normal left-click: can become drag-selection ---
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._dragging_select = False

        # Start with a single-tile selection and reset keyboard anchor
        self.selected_index = index
        self.multi_selected_indices = {index}
        try:
            self._kb_anchor_index = index
        except Exception:
            pass
        self.render_all()

    def _on_drag_motion(self, event: tk.Event):
        """While the left button is held: update box-selection."""
        if self._drag_start_x is None or self._drag_start_y is None:
            return

        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y

        # Only treat as drag if we moved a bit (avoid tiny jitter)
        if not self._dragging_select and (dx * dx + dy * dy) < 25:
            return

        self._dragging_select = True

        x1 = min(self._drag_start_x, event.x_root)
        x2 = max(self._drag_start_x, event.x_root)
        y1 = min(self._drag_start_y, event.y_root)
        y2 = max(self._drag_start_y, event.y_root)

        sel = set()
        for i, cell in enumerate(self.tiles):
            try:
                cx = cell.winfo_rootx()
                cy = cell.winfo_rooty()
                cw = cell.winfo_width()
                ch = cell.winfo_height()
            except Exception:
                continue
            if cw <= 0 or ch <= 0:
                continue

            # Use the cell centre point for hit-testing
            mx = cx + cw / 2.0
            my = cy + ch / 2.0
            if x1 <= mx <= x2 and y1 <= my <= y2:
                sel.add(i)

        # Clear old selection (tile-object selection)
        for t in list(getattr(self, "selected_tiles", set())):
            try:
                t.selected = False
            except Exception:
                pass
        try:
            self.selected_tiles.clear()
        except Exception:
            self.selected_tiles = set()

        # Apply new selection (tile-object selection)
        for idx in sel:
            try:
                self.tiles[idx].selected = True
                self.selected_tiles.add(self.tiles[idx])
            except Exception:
                pass

        # --- CRITICAL: sync index-based selection used by sidebar/notebook ---
        self.multi_selected_indices = set(sel)
        self.selected_index = min(sel) if sel else None
        try:
            if self.selected_index is not None:
                self._kb_anchor_index = self.selected_index
        except Exception:
            pass

        self.render_all()



# ============================================================================
# Event Handlers
# ============================================================================
    def _on_tile_left_release(self, event, index: int):
        """Finish click / drag. If it was just a click, behave like old _on_tile_click."""
        dragging = bool(self._dragging_select)
        self._clear_drag_state()

        if dragging:
            # Box selection already applied in _on_drag_motion
            self.render_all()
            return

        # --- Normal click: single selection ---
        # Clear selection first (tile-object selection)
        for t in list(getattr(self, "selected_tiles", set())):
            try:
                t.selected = False
            except Exception:
                pass
        try:
            self.selected_tiles.clear()
        except Exception:
            self.selected_tiles = set()

        # Select the tile (tile-object selection)
        try:
            self.tiles[index].selected = True
        except Exception:
            pass
        try:
            self.selected_tiles.add(self.tiles[index])
        except Exception:
            self.selected_tiles = {self.tiles[index]}

        # --- CRITICAL: sync index-based selection used by sidebar/notebook ---
        self.selected_index = index
        self.multi_selected_indices = {index}
        try:
            self._kb_anchor_index = index
        except Exception:
            pass

        self.render_all()

    def _on_tile_right_click(self, tile: TileCanvas, event: tk.Event):
        """Context menu on right-click. Works on both empty tiles and existing plants."""

        # --- Right-click ALWAYS moves selection to the clicked tile ---
        try:
            # clear selection first
            for t in list(getattr(self, "selected_tiles", set())):
                try:
                    t.selected = False
                except Exception:
                    pass
            try:
                self.selected_tiles.clear()
            except Exception:
                self.selected_tiles = set()

            # select the tile
            try:
                tile.selected = True
            except Exception:
                pass
            try:
                self.selected_tiles.add(tile)
            except Exception:
                self.selected_tiles = {tile}

            # keep index-based selection in sync (trait panel etc.)
            self.selected_index = getattr(tile, "idx", None)
            self.multi_selected_indices = {self.selected_index} if self.selected_index is not None else set()
            try:
                if self.selected_index is not None:
                    self._kb_anchor_index = self.selected_index
            except Exception:
                pass

            self.render_all()
        except Exception:
            pass

        # ---- Build menu (keep your existing code below) ----
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

        plantable_tiles = [t for t in self.selected_tiles 
                           if t.plant is None or not getattr(t.plant, 'alive', True)]

        menu = tk.Menu(self.root, tearoff=False)

        if len(plantable_tiles) > 0:
            # Mirror empty-tile actions
            
            menu.add_command(
                label="Plant Seed…",
                command=lambda p=plantable_tiles: self.choose_seed_for_tiles(p),
            )

            # Starter seeds
            starters_left = int(getattr(self, "available_seeds", 0) or 0)
            menu.add_command(
                label=f"Plant Starter (F0)",
                state=("normal" if starters_left else "disabled"),
                command=lambda i=tile.idx: self._plant_one_from_group(i, 'S', lambda s: False),
            )

            # ▼ define and fill the submenu *before* using it
            area_menu = tk.Menu(menu, tearoff=False)
            for kind, src, donor, count, label, match_fn in (self._get_seed_groups() or []):
                area_menu.add_command(
                    label=label,
                    state=("normal" if count else "disabled"),
                    command=lambda k=kind, mf=match_fn: self._on_plant_area_from_group(k, mf),
                )

            menu.add_cascade(label="Plant Group ▸", menu=area_menu)
            menu.add_separator()
            menu.add_command(label="Remove ALL Plants…", command=self._confirm_remove_all)
            menu.add_command(label="Remove Plant…", state="disabled")
            menu.add_separator()
            # Emasculate entry (disabled because no plant is present)
            menu.add_command(label="Emasculate…", state="disabled")
            # Existing disabled Collect Pollen
            menu.add_command(label="Collect Pollen…", state="disabled")
            menu.add_separator()

        if tile.plant is not None:
            # Existing plant actions
            menu.add_command(label="Inspect…", command=self._on_inspect_unified)
            menu.add_separator()
            menu.add_command(label="Genotype Viewer…",  command=self._on_genetics)
            menu.add_command(
                label="Trait Inheritance Explorer…",
                command=self._open_tie_for_selected
            )
            menu.add_separator()
            menu.add_command(label="Water…",            command=self._on_water_selected)

            can_harvest = bool(
                getattr(tile.plant, "pods_remaining", 0) > 0 and
                getattr(tile.plant, "ovules_left", 0) > 0
            )
            menu.add_command(
                label="Harvest seeds…",
                state=("normal" if can_harvest else "disabled"),
                command=self._on_harvest_selected,
            )

            # New: harvest all pods in one go
            can_harvest_any = bool(getattr(tile.plant, "pods_remaining", 0) > 0)
            menu.add_command(
                label="Harvest ALL seeds…",
                state=("normal" if can_harvest_any else "disabled"),
                command=self._on_harvest_all_selected,
            )

            menu.add_command(
                label="Pollinate…",
                command=self._on_pollinate)

            ok, _ = tile.plant.can_emasculate()
            menu.add_command(
                label="Emasculate…",
                state=("normal" if ok else "disabled"),
                command=self._on_emasculate_selected,
            )

            can_collect, _ = tile.plant.can_collect_pollen()

            today = self._today()
            inspected_today = (getattr(tile.plant, "last_anther_check_day", None) == today)
            anthers_today   = bool(getattr(tile.plant, "anthers_available_today", False))
            already_taken   = (getattr(tile.plant, "anthers_collected_day", None) == today)

            # must pass BOTH biology + inspection gate
            can_collect_now = bool(
                can_collect
                and inspected_today
                and anthers_today
                and (not already_taken)
            )

            # Determine menu label (for disabled explanation)
            label = "Collect Pollen…"
            if can_collect:
                if not inspected_today:
                    label = "Collect Pollen… (inspect first)"
                elif not anthers_today:
                    label = "Collect Pollen… (no anthers today)"
                elif already_taken:
                    label = "Collect Pollen… (already collected)"

            menu.add_command(
                label=label,
                state=("normal" if can_collect_now else "disabled"),
                command=self._on_collect_pollen
            )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()



# ============================================================================
# Event Handlers
# ============================================================================
    def _on_next_phase(self):
        old_hour = int(getattr(self.garden, 'clock_hour', 6))
        self.garden.next_phase()
        new_hour = int(getattr(self.garden, 'clock_hour', 6))
        
        # Update temperature button if hour changed
        if old_hour != new_hour:
            try:
                self._update_temp_button_state()
                self._last_temp_check_hour = new_hour
            except Exception as e:
                logging.error(f"Error updating temp button: {e}")
            
            # AUTO-RECORD: Take measurement if enabled (separate try-catch for clarity)
            auto_record_enabled = self.auto_record_temperature.get()
            has_tracker = self.temp_tracker is not None
            
            if auto_record_enabled and has_tracker:
                try:
                    can_measure, hour, reason = self.temp_tracker.can_measure_now()
                    
                    if can_measure:
                        success, message = self.temp_tracker.take_measurement()
                        if success:
                            logging.info(f"Auto-recorded: {message}")
                        else:
                            logging.warning(f"Auto-record failed: {message}")
                    # else: stay silent when measurement is not allowed

                except Exception as e:
                    logging.error(f"Error in auto-record: {e}", exc_info=True)
        
        # Traits rarely change every phase; keep cache so we don't rebuild unless needed.
        self.render_all()
# Start automated phase progression (slight delay for safety)
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

    def _on_water_all(self):
        if self.garden.weather in ("🌧", "⛈"):
            self._toast("Rainy day! Gregor leaves the plants to the clouds.", level="info")
            return
        msg = self.garden.water_all()
        self.render_all()
        # Start automated phase progression (slight delay for safety)
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass
        print(msg)

    def _on_measure_temperature(self):
        """Quick temperature measurement from button."""
        try:
            if self.temp_tracker:
                success, message = self.temp_tracker.take_measurement()
                if success:
                    self._toast(message, level="info")
                else:
                    self._toast(message, level="warn")
            else:
                self._toast("Temperature tracker not available", level="warn")
        except Exception as e:
            logging.error(f"Error taking measurement: {e}")
            self._toast("Error taking measurement", level="error")

    def _update_temp_button_state(self):
        """Update temp button: green+clickable only when manual recording is allowed and time is right."""
        try:
            btn = getattr(self, "measure_temp_btn", None)
            if btn is None:
                return

            # No tracker -> disable
            if self.temp_tracker is None:
                btn.config(state="disabled")
                return

            auto_on = bool(self.auto_record_temperature.get())

            # ✅ If auto-record is ON: disable manual measurement (auto will take it)
            if auto_on:
                btn.config(state="disabled")
                # neutral style (not green)
                btn.configure(
                    bg="#F4F4F4",
                    activebackground="#E4E4E4",
                    fg="#333333",
                    activeforeground="#333333"
                )
                btn._base_bg = "#F4F4F4"
                btn._hover_bg = "#E8E8E8"
                return

            # Auto-record OFF -> manual allowed only at valid hours and if not yet measured
            can_measure, hour, reason = self.temp_tracker.can_measure_now()

            if can_measure:
                btn.config(state="normal")
                btn.configure(
                    bg="#D4EDDA",            # light green
                    activebackground="#C3E6CB",
                    fg="#333333",
                    activeforeground="#333333"
                )
                btn._base_bg = "#D4EDDA"
                btn._hover_bg = "#C3E6CB"
            else:
                btn.config(state="disabled")
                btn.configure(
                    bg="#F4F4F4",
                    activebackground="#E4E4E4",
                    fg="#333333",
                    activeforeground="#333333"
                )
                btn._base_bg = "#F4F4F4"
                btn._hover_bg = "#E8E8E8"

        except Exception:
            pass

    def _selected_indices(self):
        """Return list of currently selected tile indices (multi or single)."""
        sel = getattr(self, "multi_selected_indices", None) or set()
        if sel:
            return sorted(i for i in sel if 0 <= i < len(self.tiles))

        idx = getattr(self, "selected_index", None)
        if idx is not None and 0 <= idx < len(self.tiles):
            return [idx]
        return []


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_remove_selected(self):
        indices = self._selected_indices()
        if not indices:
            return

        removed = 0
        for idx in indices:
            plant = self.tiles[idx].plant
            if plant is None:
                continue

            self.tiles[idx].plant = None
            self.tiles[idx].plant = None
            removed += 1

        if removed == 1:
            self._toast("Plant removed.")
        elif removed > 1:
            self._toast(f"{removed} plants removed.")

        self.render_all()

    def _on_select_all(self):
        """Select all grid tiles (plants, empty, dead)."""
        try:
            total = GRID_SIZE
        except Exception:
            # Fallback if GRID_SIZE isn't available for some reason
            total = len(getattr(self, "garden").plants)

        indices = set(i for i in range(total))

        try:
            self.multi_selected_indices = indices
        except Exception:
            self.multi_selected_indices = indices

        # Focus the first tile if possible
        if total > 0:
            self.selected_index = 0
            try:
                self._kb_anchor_index = 0
            except Exception:
                pass
        else:
            self.selected_index = None

        self.render_all()




# ============================================================================
# Event Handlers
# ============================================================================
    def _on_water_selected(self):
        indices = self._selected_indices()
        if not indices:
            return

        if self.garden.weather in ("🌧", "⛈"):
            self._toast("It's raining — watering not needed.")
            return

        msgs = []
        watered = 0
        for idx in indices:
            plant = self.tiles[idx].plant if (idx is not None) else None
            if not plant:
                continue
            try:
                msg = plant.water_plant(self.garden.phase)
                msgs.append(msg)
                watered += 1
            except Exception:
                continue

        self.render_all()


        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

        if watered == 1:
            self._toast("Plant watered.")
        elif watered > 1:
            self._toast(f"{watered} plants watered.")

        for m in msgs:
            print("Watering:", m)

        # Start automated phase progression (slight delay for safety)
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass
        print("Watering:", msg)

    def _on_inspect_selected(self):
        idx = self.selected_index
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None

        if not plant:
            self._toast("Select a plant first.", level="info")
            return

        # --- keep existing behaviour: reveal one trait ---
        try:
            plant.reveal_trait()
        except Exception:
            pass

        # Force left panel to refresh with the new trait
        try:
            self._sel_traits_sig = None
        except Exception:
            pass

        # --- NEW: flowering anther inspection (once per day) ---
        try:
            stage = int(getattr(plant, "stage", 0))
        except Exception:
            stage = 0

        if stage != 5:
            self._toast("Inspection: this plant is not in flowering stage.")
            self.render_all()
            return

        today = self._today()

        # Only allow the anther check once per day
        if getattr(plant, "last_anther_check_day", None) != today:
            plant.last_anther_check_day = today
            plant.anthers_available_today = (random.random() < 0.5)
            # reset “collected today” when a new day’s check happens
            plant.anthers_collected_day = None

        if getattr(plant, "anthers_available_today", False):
            self._toast("Inspection: mature anthers found — pollen can be collected today.")
        else:
            self._toast("Inspection: no mature anthers today — cannot collect pollen.")

        self.render_all()

        # Keep auto-loop alive as before
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

    
    def _abortion_probability(self, plant) -> float:
        """Return per-ovule abortion probability based on plant state."""
        try:
            # Baseline small loss
            p = 0.05
            # Health effects
            if getattr(plant, "health", 100) < 70: p += 0.05
            if getattr(plant, "health", 100) < 40: p += 0.10
            # Water stress
            if getattr(plant, "water", 50) < 30: p += 0.05
            if getattr(plant, "water", 50) < 15: p += 0.10
            # Cap between 0 and 0.6
            return max(0.0, min(0.6, p))
        except Exception:
            return 0.10


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_harvest_selected(self):
            idx = self.selected_index
            plant = self.tiles[idx].plant if (idx is not None) else None
            if not plant or not plant.alive or plant.stage < 7:
                self._toast("Plant is not ready to harvest.")
                return
            
            # Check if emasculated and has no pods
            is_emasculated = getattr(plant, "emasculated", False)
            pods_remaining = int(getattr(plant, "pods_remaining", 0) or 0)
            
            if is_emasculated and pods_remaining <= 0:
                self._toast("No pods to harvest: this plant was emasculated and not successfully pollinated.", level="warn")
                return
            
            # Realism: manage pods/ovules capacity — use up ONE WHOLE POD per click
            try:
                if pods_remaining <= 0:
                    self._toast("No pods remaining on this plant.")
                    return
                # If this pod has no ovules left, advance to next pod now
                if getattr(plant, "ovules_left", 0) <= 0:
                    plant.pods_remaining = max(0, int(getattr(plant, "pods_remaining", 0)) - 1)
                    plant.ovules_left = int(getattr(plant, "ovules_per_pod", 7))
                    if plant.pods_remaining <= 0:
                        self._toast("No pods remaining on this plant.")
                        return
            except Exception:
                pass


            # Number of ovules to attempt (whole pod)
            ovules = int(getattr(plant, "ovules_left", 0) or getattr(plant, "ovules_per_pod", 7))
            if ovules <= 0:
                ovules = int(getattr(plant, "ovules_per_pod", 7))

            # Per-seed abortion probability
            abort_p = self._abortion_probability(plant)

            made = 0
            aborted = 0

            ts = time.strftime("%m%d%H%M")

            def _pick_fresh_donor(donors_list, current_day, rng):
                """
                Choose a donor with a freshness-weighted probability:
                - pollen applied today gets weight 1.0
                - yesterday gets ~0.5
                - two days ago gets ~0.33
                etc.
                If no day info, default weight = 1.0.
                """
                if not donors_list:
                    return None
                weights = []
                for d in donors_list:
                    d_day = d.get("day", current_day)
                    try:
                        age = max(0, int(current_day) - int(d_day))
                    except Exception:
                        age = 0
                    # freshness: newer pollen ⇒ higher weight
                    w = 1.0 / (1.0 + age)
                    weights.append(w)
                total_w = sum(weights)
                if total_w <= 0:
                    # fallback: uniform choice
                    return rng.choice(donors_list)
                r = rng.random() * total_w
                acc = 0.0
                for d, w in zip(donors_list, weights):
                    acc += w
                    if r <= acc:
                        return d
                # numeric safety fallback
                return donors_list[-1]


            # Determine current pod index (1-based)
            try:
                pod_index = int(getattr(plant, "pods_total", 0)) - int(getattr(plant, "pods_remaining", 0)) + 1
                if pod_index < 1: pod_index = 1
            except Exception:
                pod_index = 1

            # Prepare pod record for archive snapshot
            pod_record = {
                'idx': int(pod_index),
                'ts': ts,
                'seeds': [],
                'children': [],
                'counts': {},
            }

            # Helpers to get maternal genotype
            maternal_geno = getattr(plant, 'genotype', None) or infer_genotype_from_traits(dict(getattr(plant, 'traits', {})), random)

            # Prepare donor pool if any pending cross (mixed donors allowed)
            pc = getattr(plant, "pending_cross", None) or {}
            donors = pc.get("donors") or []
            if (not donors) and pc.get("donor_id"):
                # back-compat: single donor_id stored
                did = pc.get("donor_id")
                # attempt to reconstruct donor genotype from current garden
                donor_pl = None
                try:
                    donor_pl = next((t.plant for t in self.tiles if t.plant is not None and getattr(t.plant, "id", None) == did), None)
                except Exception:
                    donor_pl = None
                dgen = {}
                try:
                    dgen = infer_genotype_from_traits(dict(getattr(donor_pl, "traits", {})), random) if donor_pl else {}
                except Exception:
                    dgen = {}
                donors = [{"donor_id": did, "donor_genotype": dgen}]

            # --- Emasculation / non-emasculation: compute selfing/cross quotas ---
            emasculated = bool(getattr(plant, "emasculated", False))
            selfing_quota = 0
            cross_quota = 0

            if emasculated:
                # Same as before: some ovules may already be selfed before emasculation
                already = max(0.0, min(1.0, float(getattr(plant, "selfing_frac_before_emasc", 0.0))))
                selfing_quota = int(round(ovules * already))
                cross_quota = max(0, ovules - selfing_quota)

            else:
                # Non-emasculated + donor pollen → pistil-level all-or-nothing
                if bool(pc) and bool(donors):
                    base_prob = 0.10  # 10% chance that this pollination "wins" the pistil
                    if random.random() < base_prob:
                        # Cross succeeds: treat like a normal clean cross at this pistil
                        selfing_quota = 0
                        cross_quota = ovules
                    else:
                        # Cross fails: all ovules self
                        selfing_quota = ovules
                        cross_quota = 0
                else:
                    # No donor pollen → pure selfing
                    selfing_quota = ovules
                    cross_quota = 0

            for _ in range(ovules):
                # Choose cross vs self
                # Decide by quotas: use up selfing_quota first, then cross if donors available
                do_self = False
                selfing_by_quota = False
                if selfing_quota > 0:
                    do_self = True
                    selfing_by_quota = True
                    selfing_quota -= 1
                elif bool(pc) and bool(donors) and (cross_quota > 0):
                    do_self = False
                    cross_quota -= 1
                else:
                    # Default path: if emasculated, unfertilized ovule aborts (no fallback selfing)
                    if getattr(plant, "emasculated", False):
                        aborted += 1
                        continue
                    do_self = True
                if not do_self:
                    d = _pick_fresh_donor(donors, self.garden.day, random)
                    if not d:
                        # no usable donor for some reason; fall back to selfing
                        do_self = True
                    else:
                        donor_id = d.get("donor_id", "?")
                        donor_geno = d.get("donor_genotype", {})
                        pol_gam = random_gamete(donor_geno, random)
                        child = child_genotype(maternal_geno, pol_gam, random)
                    try:
                        pheno = phenotype_from_genotype(child)
                    except Exception:
                        pheno = dict(getattr(plant, "traits", {}))
                    self.seed_counter += 1
                    seed_id = f"X{ts}{self.seed_counter:02d}"
 
                    # carry ancestry forward (maternal chain + mother id)
                    try:
                        parent_chain = list(getattr(plant, 'ancestry', []) or [])
                        if getattr(plant, 'id', None) is not None:
                            parent_chain = parent_chain + [int(plant.id)]
                    except Exception:
                        parent_chain = []

                    seed = Seed(f"Cross {seed_id} (♀#{plant.id} × ♂#{donor_id})",
                                seed_id, plant.id, donor_id, dict(pheno), plant.generation,
                                pod_index, child, parent_chain)

                else:
                    # Selfed seed with true Mendelian segregation
                    egg = random_gamete(maternal_geno, random)
                    pollen = random_gamete(maternal_geno, random)
                    child = child_genotype(maternal_geno, pollen, random)
                    try:
                        pheno = phenotype_from_genotype(child)
                    except Exception:
                        pheno = dict(getattr(plant, 'traits', {}))
                    self.seed_counter += 1
                    seed_id = f"H{ts}{self.seed_counter:02d}"
                    seed = Seed(f"Seed {seed_id} from #{plant.id} (Day {self.garden.day})",
                                seed_id, plant.id, None, dict(pheno), plant.generation,
                                pod_index, child, list(getattr(plant, 'ancestry', []) or []))

                # Abortion check
                if random.random() < (1.0 - abort_p):
                    self.harvest_inventory.append(seed)
                    # Mirror into pod record
                    try:
                        pod_record['seeds'].append({'id': seed.get('id'), 'traits': dict(seed.get('traits', {})), 'selfed': bool(seed.is_selfed()), 'donor_id': seed.get('donor_id'), 'pod_index': seed.get('pod_index')})
                    except Exception:
                        pass
                    try:
                        self._append_seed_csv(seed)
                    except Exception:
                        pass
                    made += 1
                else:
                    try:
                        plant.aborted_ovules = int(getattr(plant, 'aborted_ovules', 0)) + 1
                    except Exception:
                        pass
                    aborted += 1

            # Pod is spent
            try:
                plant.ovules_left = 0
                plant.pods_remaining = max(0, int(getattr(plant, "pods_remaining", 0)) - 1)
                if plant.pods_remaining > 0:
                    plant.ovules_left = int(getattr(plant, "ovules_per_pod", 7))
            except Exception:
                pass

            
            self._toast(f"Harvested {made} seeds (aborted {aborted}). Pods left: {getattr(plant, 'pods_remaining', 0)}")
            # Auto-remove when pods are exhausted — archive first like bulk removal
            try:
                if int(getattr(plant, 'pods_remaining', 0)) <= 0:
                    try:
                        if hasattr(self, '_ga_snapshot_all_live_plants'):
                            self._ga_snapshot_all_live_plants()
                    except Exception:
                        pass
                    try:
                        self._eager_seed_and_backfill()
                    except Exception:
                        pass
                    try:
                        if hasattr(self, '_snapshot_all_live_plants'):
                            self._snapshot_all_live_plants()
                    except Exception:
                        pass
                    self.tiles[idx].plant = None
                    self.tiles[idx].plant = None
                    self._toast('Plant removed after final harvest.')
            except Exception:
                pass
            self.render_all()
            try:
                self._ensure_auto_loop(delay_ms=50)
            except Exception:
                pass


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_harvest_all_selected(self):
        """Harvest all remaining pods from the selected plant, then remove it."""
        idx = self.selected_index
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None

        if not plant or not getattr(plant, "alive", True) or getattr(plant, "stage", 0) < 7:
            self._toast("Plant is not ready to harvest.")
            return

        # Initial pods count (upper bound for iterations)
        try:
            remaining = int(getattr(plant, "pods_remaining", 0))
        except Exception:
            remaining = 0

        # Check if emasculated with no pods
        is_emasculated = getattr(plant, "emasculated", False)
        if is_emasculated and remaining <= 0:
            self._toast("No pods to harvest: this plant was emasculated and not successfully pollinated.", level="warn")
            return

        if remaining <= 0:
            self._toast("No pods remaining on this plant.")
            return

        harvested_pods = 0

        # Bound the loop by the initial number of pods
        for _ in range(remaining):
            # Re-fetch plant each time because _on_harvest_selected may remove it
            plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None
            if not plant or not getattr(plant, "alive", True):
                break

            try:
                pods_left = int(getattr(plant, "pods_remaining", 0))
            except Exception:
                pods_left = 0

            if pods_left <= 0:
                break

            # Reuse existing single-pod harvest logic (includes seeds, archive, auto-removal)
            self._on_harvest_selected()
            harvested_pods += 1

        # Optional: one summarizing toast (the per-pod toasts still happen inside _on_harvest_selected)
        if harvested_pods > 1:
            try:
                self._toast(f"Harvested all remaining pods ({harvested_pods}).")
            except Exception:
                pass

        # Final UI refresh (mostly redundant, but harmless)
        self.render_all()

        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass


    def _append_seed_csv(self, seed: dict):
        os.makedirs(os.path.dirname(SEEDS_CSV), exist_ok=True)
        file_exists = os.path.exists(SEEDS_CSV)
        with open(SEEDS_CSV, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["id","source_id","generation","flower_position","flower_color","pod_color"])
            if not file_exists:
                writer.writeheader()
            traits = seed.get("traits", {})
            writer.writerow({
                "id": seed.get("id",""),
                "source_id": seed.get("source_id",""),
                "generation": seed.get("generation",""),
                "flower_position": traits.get("flower_position",""),
                "flower_color": traits.get("flower_color",""),
                "pod_color": traits.get("pod_color",""),
            })

    def _open_summary(self, initial_tab=None):
        InventoryPopup(self.root, self.garden, self.harvest_inventory, self._on_seed_selected, app=self, initial_tab=initial_tab)

    def plant_seed(self, seed: Seed, slot: int):
        """
        Create and place a Plant from a harvested/crossed seed into the given slot.
        Handles:
          - Plant creation from seed
          - Parentage, pod origin, ancestry, genotype
          - Garden placement
          - Archive snapshot & pod-children linking
        Returns the Plant or None on failure.
        """
        # Basic sanity
        if slot is None or slot < 0 or slot >= len(self.tiles):
            return None

        # Create plant core
        pid = self._next_id()
        gen = self._next_generation(seed.get("generation", "F0"))
        p = Plant(id=pid, env=self.garden, stage=1, generation=gen,
                    traits=dict(seed.get("traits", {})))

        # Small natural variation in germination
        p.germination_delay = random.randint(1, 3)

        # --- Parentage & selfing flag (Canonicalize parent order) ---
        try:
            mid = seed.get("source_id")
            fid = seed.get("donor_id") or seed.get("source_id")

            # Normalize IDs to ints if possible (safe if they're already ints)
            try:
                mid_i = int(mid) if mid not in (None, "", -1) else None
            except Exception:
                mid_i = None
            try:
                fid_i = int(fid) if fid not in (None, "", -1) else None
            except Exception:
                fid_i = None

            # Canonicalize: mother_id is always the smaller id, father_id the larger id
            if mid_i is not None and fid_i is not None and mid_i != fid_i:
                m2, f2 = (mid_i, fid_i) if mid_i < fid_i else (fid_i, mid_i)
                p.mother_id = m2
                p.father_id = f2
                p.selfed = False
            else:
                # Selfed or missing donor
                p.mother_id = mid_i if mid_i is not None else mid
                p.father_id = fid_i if fid_i is not None else fid
                p.selfed = True if (fid_i is not None and mid_i is not None and fid_i == mid_i) else bool(
                    seed.get("selfed") or (seed.get("donor_id") in (None, seed.get("source_id")))
                )
        except Exception:
            pass


        # --- Pod origin (for siblings-by-pod view) ---
        try:
            if 'pod_index' in seed:
                p.source_pod_index = int(seed.get('pod_index'))
        except Exception:
            # fall back gracefully
            p.source_pod_index = seed.get('pod_index', None)

        # --- Ancestry info (if present) ---
        try:
            if seed.get('ancestry'):
                p.ancestry = list(seed.get('ancestry') or [])
            if seed.get('paternal_ancestry'):
                p.paternal_ancestry = list(seed.get('paternal_ancestry') or [])
        except Exception:
            pass

        # --- Genotype (robust: works for dict seeds AND Seed objects) ---
        geno = None

        # 1) Try dict-style access
        try:
            if isinstance(seed, dict):
                geno = seed.get("genotype", None)
            else:
                # Some Seed classes implement .get(...)
                try:
                    geno = seed.get("genotype", None)
                except Exception:
                    geno = None
        except Exception:
            geno = None

        # 2) Try attribute-style access (Seed.dataclass / object)
        if geno is None:
            try:
                geno = getattr(seed, "genotype", None)
            except Exception:
                geno = None

        # 3) Assign genotype (or infer as fallback so Genetics Viewer always has something)
        if geno is not None:
            try:
                p.genotype = dict(geno)
            except Exception:
                try:
                    p.genotype = geno
                except Exception:
                    pass
        else:
            # Fallback: infer from traits (better than leaving genotype missing)
            try:
                p.genotype = dict(infer_genotype_from_traits(dict(getattr(p, "traits", {}) or {}), random))
            except Exception:
                pass

        self.tiles[slot].plant = p

        # 2) Ensure minimal F0 snapshots exist for parents (from _on_seed_selected)
        mid = getattr(p, "mother_id", None)
        fid = getattr(p, "father_id", None)

        # Infer mother from ancestry if missing
        if mid in (None, "", -1):
            try:
                anc = list(getattr(p, "ancestry", []) or [])
            except Exception:
                anc = []
            if anc:
                mid = anc[-1]
                try:
                    p.mother_id = mid
                except Exception:
                    pass

        # Assume selfed if donor missing
        if fid in (None, "", -1):
            fid = mid
            try:
                p.father_id = fid
            except Exception:
                pass

        # --- Canonicalize parent order (Option A) ---
        try:
            mid = getattr(p, "mother_id", None)
            fid = getattr(p, "father_id", None)

            if mid not in (None, "", -1) and fid not in (None, "", -1):
                mi = int(mid)
                fi = int(fid)

                if mi != fi:
                    p.mother_id, p.father_id = (mi, fi) if mi < fi else (fi, mi)
        except Exception:
            pass

        # Ensure we can check whether parent IDs already exist in the archive
        arch = getattr(self, "archive", {}) or {}
        plants = arch.get("plants", {}) if isinstance(arch, dict) else {}
        if not isinstance(plants, dict):
            plants = {}

        def _ensure_min(pid0, gen0="F0"):
            if pid0 in (None, "", -1):
                return
            key_int = int(pid0) if str(pid0).isdigit() else pid0
            if key_int not in plants and str(key_int) not in plants:
                self.archive_snapshot({"id": key_int, "generation": gen0})

        _ensure_min(mid, "F0")
        _ensure_min(fid, "F0")


        try:
            self._eager_seed_and_backfill()
        except Exception:
            pass

        return p


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_seed_selected(self, seed: dict):
        idx = self.selected_index
        plant_here = self.tiles[idx].plant if idx is not None else None
        if idx is None:
            return
        # Allow planting on dead plants (auto-replaces them) or empty tiles
        if plant_here is not None and getattr(plant_here, 'alive', True):
            self._toast("Select an empty tile first.")
            return
        # Gate: seeds usable next year only
        hy = seed.get('harvest_year', None)
        if hy is not None:
            try:
                hy = int(hy)
            except Exception:
                pass
            if isinstance(hy, int) and hy >= getattr(self.garden, 'year', 1856):
                self._toast(f"This seed will be plantable next year (available in {hy+1}).")
                return

        # Season gate before planting an individual harvested seed
        if not self._season_gate_sowing():
            try:
                self._toast("Sowing blocked by season rules.", level="warn")
            except Exception:
                pass
            return

        # Actually plant the harvested seed into this slot
        p = self.plant_seed(seed, idx)
        if p is None:
            self._toast("Planting failed (internal error).", level="error")
            return
        # consume the seed from inventory
        sid = seed.get("id")
        if sid:
            self.harvest_inventory = [
                s for s in self.harvest_inventory if s.get("id") != sid
            ]

        self._toast(f"Planted seed {sid or ''} → {p.generation}")
        self.render_all()
        try:
            self._ensure_auto_loop(delay_ms=50)
        except Exception:
            pass

    def choose_seed_for_tiles(self, tiles: List[TileCanvas]):
        """Popup to choose what to plant in a given empty slot (3×3 paged grid of seed groups)."""
        # If totally empty, bail
        if not self.harvest_inventory and int(getattr(self, "available_seeds", 0) or 0) <= 0:
            self._toast("You have no seeds to plant.")
            return

        PER_PAGE = 9  # 3×3

        picker = Toplevel(self.root)
        picker.title("Choose Seed")
        picker.geometry("760x640")
        picker.resizable(True, True)

        # Keep page state on the window itself
        picker._seed_page = 0

        outer = tk.Frame(picker, padx=10, pady=10)
        outer.pack(fill="both", expand=True)

        # -----------------------
        # Header: Prev / Page / Next + Close (X)
        # -----------------------
        header = tk.Frame(outer)
        header.pack(fill="x")

        def _close_picker():
            try:
                picker.destroy()
            except Exception:
                pass

        try:
            picker.protocol("WM_DELETE_WINDOW", _close_picker)
        except Exception:
            pass

        btn_prev = tk.Button(header, text="◀ Prev", **self.button_style)
        btn_next = tk.Button(header, text="Next ▶", **self.button_style)
        self._apply_hover(btn_prev)
        self._apply_hover(btn_next)

        lbl_page = tk.Label(header, text="", font=("Segoe UI", 11))

        btn_close = tk.Button(header, text="✕", command=_close_picker, **self.button_style)
        self._apply_hover(btn_close)

        lbl_page.pack(side="left", padx=8)
        btn_prev.pack(side="left")
        btn_close.pack(side="right")              # far right
        btn_next.pack(side="right", padx=(0, 6))  # just left of X


        # -----------------------
        # Grid  
        # -----------------------
        grid = tk.Frame(outer)
        grid.pack(fill="both", expand=True, pady=(10, 0))

        for c in range(3):
            grid.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(3):
            grid.grid_rowconfigure(r, weight=1, uniform="row")

        # -----------------------
        # Helpers
        # -----------------------
        def _get_sample_traits_for_group(kind, src, donor, match_fn):
            """Return a dict of traits for preview (from first matching harvested seed)."""
            if kind == "S":
                return {}  # starters are randomized founders; no single preview
            try:
                for s in self.harvest_inventory:
                    if match_fn(s):
                        return dict(s.get("traits", {}) or {})
            except Exception:
                pass
            return {}

        def _delete_group(kind, src, donor, match_fn):
            if kind == "S":
                return
            before = len(self.harvest_inventory)
            try:
                self.harvest_inventory = [s for s in self.harvest_inventory if not match_fn(s)]
            except Exception:
                # ultra defensive fallback
                self.harvest_inventory = list(self.harvest_inventory or [])
            removed = before - len(self.harvest_inventory)
            if removed > 0:
                self._toast(f"Deleted {removed} seeds from this group.")
            else:
                self._toast("No seeds deleted from this group.", level="warn")
            _render()

        def _plant_one(tiles, kind, match_fn):
            """Plant exactly one seed from a group into the chosen tile index."""
            ok = False
            for tile in tiles:
                ok = self._plant_one_from_group(tile.idx, kind, match_fn)
                # hanle errors??

            if ok:
                picker.destroy()
                self.render_all()
                try:
                    self._ensure_auto_loop(delay_ms=50)
                except Exception:
                    pass

        def _plant_area(kind, match_fn):
            """Plant seeds from a group into the contiguous empty region starting at selected tile."""
            try:
                self._on_plant_area_from_group(kind, match_fn)
            except Exception:
                pass
            try:
                picker.destroy()
            except Exception:
                pass

        def _render():
            # Clear grid
            for w in grid.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

            # Get fresh groups each render (so counts are current)
            try:
                groups = list(self._get_seed_groups() or [])
            except Exception:
                groups = []

            # Filter out empty groups (but keep starter shown even if 0)
            cleaned = []
            for kind, src, donor, count, label, match_fn in groups:
                if kind == "S":
                    cleaned.append((kind, src, donor, int(count or 0), label, match_fn))
                else:
                    if int(count or 0) > 0:
                        cleaned.append((kind, src, donor, int(count or 0), label, match_fn))

            groups = cleaned
            total = len(groups)

            # Clamp page
            if total > 0:
                max_page = (total - 1) // PER_PAGE
                if picker._seed_page > max_page:
                    picker._seed_page = max_page
            else:
                picker._seed_page = 0

            start = picker._seed_page * PER_PAGE
            end = min(total, start + PER_PAGE)

            # Update header UI
            if total > 0:
                lbl_page.configure(text=f"Seed groups {start+1}-{end} of {total}")
            else:
                lbl_page.configure(text="No seeds available")
            btn_prev.configure(state=("normal" if picker._seed_page > 0 else "disabled"))
            btn_next.configure(state=("normal" if (picker._seed_page + 1) * PER_PAGE < total else "disabled"))

            # Fill cards
            shown = groups[start:end]

            # If nothing to show, add one message card
            if not shown:
                f = tk.Frame(grid, borderwidth=1, relief="groove", padx=10, pady=10)
                f.grid(row=1, column=1, padx=8, pady=8, sticky="nsew")
                tk.Label(f, text="No seed groups to show.", fg="#666666", font=("Segoe UI", 12, "italic")).pack()
                return

            for i, (kind, src, donor, count, label, match_fn) in enumerate(shown):
                r = i // 3
                c = i % 3

                card = tk.Frame(grid, borderwidth=1, relief="groove", padx=10, pady=10, width=190, height=135)
                card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")
                card.grid_propagate(False)

                # --- Card header: title (left) + red ✕ (right) ---
                card_header = tk.Frame(card)
                card_header.pack(fill="x", anchor="w")

                # Title (left)
                try:
                    if ("♀" in str(label)) or ("♂" in str(label)):
                        self._label_with_bold_gender(
                            card_header,
                            str(label),
                            base_font=("Segoe UI", 11),
                            bold_font=("Segoe UI", 11, "bold"),
                        ).pack(side="left", anchor="w")
                    else:
                        tk.Label(
                            card_header,
                            text=str(label),
                            font=("Segoe UI", 11, "bold"),
                            wraplength=170,
                            justify="left"
                        ).pack(side="left", anchor="w")
                except Exception:
                    tk.Label(
                        card_header,
                        text=str(label),
                        font=("Segoe UI", 11, "bold"),
                        wraplength=170,
                        justify="left"
                    ).pack(side="left", anchor="w")

                # Red ✕ (right) — delete this group (disabled for starter seeds)
                btn_group_x = tk.Button(
                    card_header,
                    text="✕",
                    width=2,
                    fg="red",
                    state=("disabled" if kind == "S" else "normal"),
                    command=lambda k=kind, s=src, d=donor, mf=match_fn: _delete_group(k, s, d, mf),
                    **self.button_style,
                )
                self._apply_hover(btn_group_x)
                btn_group_x.pack(side="right", anchor="e")

                # Preview traits as icons (seed_shape + seed_color)
                traits = _get_sample_traits_for_group(kind, src, donor, match_fn) or {}

                icon_row = tk.Frame(card)
                icon_row.pack(anchor="w", pady=(4, 2))

                # Keep image references so Tk doesn't garbage-collect them
                if not hasattr(card, "_img_refs"):
                    card._img_refs = []

                def _add_trait_icon(trait_key, value):
                    if not value:
                        return False
                    try:
                        p = trait_icon_path(trait_key, value)  # should map to your existing icons
                        if p:
                            img = safe_image(p)
                            lbl = tk.Label(icon_row, image=img)
                            lbl.image = img
                            lbl.pack(side="left", padx=(0, 6))
                            card._img_refs.append(img)
                            return True
                    except Exception:
                        pass
                    return False

                shown_any = False
                shown_any |= _add_trait_icon("seed_shape", traits.get("seed_shape"))
                shown_any |= _add_trait_icon("seed_color", traits.get("seed_color"))

                if not shown_any:
                    # Fallback text if this group doesn't have seed traits yet
                    if kind == "S":
                        tk.Label(card, text="• randomized founders", font=("Segoe UI", 10), fg="#666666").pack(anchor="w")
                    else:
                        tk.Label(card, text="• (no preview)", font=("Segoe UI", 10), fg="#666666").pack(anchor="w")


                # Buttons row
                btn_row = tk.Frame(card)
                btn_row.pack(side="bottom", fill="x", pady=(8, 0))

                # Plant one (green text)
                b_plant = tk.Button(
                    btn_row,
                    text="Plant (1)",
                    fg="green",
                    state=("normal" if count > 0 else "disabled"),
                    command=lambda t = tiles, k=kind, mf=match_fn: _plant_one(t, k, mf),
                    **self.button_style,
                )
                self._apply_hover(b_plant)
                b_plant.pack(side="left", padx=(0, 6))

                # Plant area (optional power feature)
                b_area = tk.Button(
                    btn_row,
                    text="Plant area",
                    state=("normal" if count > 0 else "disabled"),
                    command=lambda k=kind, mf=match_fn: _plant_area(k, mf),
                    **self.button_style,
                )
                self._apply_hover(b_area)
                b_area.pack(side="left")

                # Discard group (red)
                b_del = tk.Button(
                    btn_row,
                    text="Discard",
                    fg="red",
                    state=("disabled" if kind == "S" else "normal"),
                    command=lambda k=kind, s=src, d=donor, mf=match_fn: _delete_group(k, s, d, mf),
                    **self.button_style,
                )
                self._apply_hover(b_del)
                b_del.pack(side="right")

        # Wire prev/next
        def _prev():
            if picker._seed_page > 0:
                picker._seed_page -= 1
                _render()

        def _next():
            picker._seed_page += 1
            _render()

        btn_prev.configure(command=_prev)
        btn_next.configure(command=_next)

        _render()

    def _toggle_run(self):
        self.running = not getattr(self, "running", True)
        try:
            # Update button label
            if hasattr(self, "pause_btn"):
                self.pause_btn.configure(text=("⏸ Pause" if self.running else "⏵ Resume"))
        except Exception:
            pass
        # Keep loop consistent
        if self.running:
            self._ensure_auto_loop(delay_ms=50)
        else:
            # When pausing, keep a light heartbeat so UI can still refresh
            self._ensure_auto_loop(delay_ms=getattr(self, 'phase_ms', 600))
        # Feedback toast
        try:
            self._toast("Resumed." if self.running else "Paused.")
        except Exception:
            pass


# ============================================================================
# Event Handlers
# ============================================================================
    def _on_fast_forward(self):
        # Dialog: ask for days + daily render option
        dlg = FFDialog(self.root, title="Fast Forward")

        if not getattr(dlg, "result", None):
            return

        resp = dlg.result["days"].strip()
        daily_mode = bool(dlg.result["daily"])

        # Read chosen hourly interval (1–23); ignore if daily render is used
        interval = dlg.result.get("interval", 9)
        try:
            interval = int(interval)
        except Exception:
            interval = 9
        # Clamp to 1–23; 24 would be equivalent to daily render, so we skip 24
        if interval < 1:
            interval = 1
        elif interval > 23:
            interval = 23

        # Store choices in app-level vars
        try:
            self.ff_render_daily.set(daily_mode)
        except Exception:
            pass
        try:
            self.ff_render_interval.set(interval)
        except Exception:
            # Fallback if variable didn't exist for some reason
            self.ff_render_interval = tk.IntVar(value=interval)

        # Validate day count
        try:
            days = int(resp)
            if days <= 0:
                raise ValueError
        except Exception:
            self._toast("Please enter a positive integer.", level="error")
            return

        was_running = self.running
        self.running = False
        self.fast_forward = True

        total_hours = days * 24  # simulate N full days
        last_day_key = None

        for step in range(total_hours):
            # ---------------- New day detection & daily setup ----------------
            try:
                day_key = (
                    self.garden.year,
                    self.garden.month,
                    self.garden.day_of_month,
                )
            except Exception:
                day_key = None

            if day_key != last_day_key:
                # Daily climate & weather
                try:
                    sim_date = dt.date(
                        self.garden.year,
                        self.garden.month,
                        self.garden.day_of_month,
                    )
                    st = self._climate_v2.daily_state(sim_date)
                    self.garden.target_temps = {
                        "hours": st["hours"],
                        "morning":   sum(st["hours"][6:11]) / 5.0,
                        "noon":      sum(st["hours"][11:14]) / 3.0,
                        "afternoon": sum(st["hours"][14:18]) / 4.0,
                        "evening":   sum(st["hours"][18:23]) / 5.0,
                    }
                    self.garden.temp_updates_remaining = 3
                    if st.get("rain_today"):
                        self.garden.weather = "⛈" if st.get("thunder_today") else "🌧"
                    elif st.get("snow_today"):
                        self.garden.weather = "❄️"
                    else:
                        c = st.get("cloud_0_10", 5.0)
                        self.garden.weather = (
                            "☀️" if c < 4 else ("⛅" if c < 7 else "☁️")
                        )
                    rain_today = bool(st.get("rain_today"))
                except Exception:
                    rain_today = False

                # Tiny daily health top-up over live plants (currently 0)
                # if has_live_plants:
                #     try:
                #         for p in self.plants:
                #             if p and getattr(p, "alive", True):
                #                 p.health = min(100, p.health + 0)
                #     except Exception:
                #         pass

                # Choose a watering phase for this FF day
                last_day_key = day_key

            # ---------------- One simulated HOUR step ----------------

            self.garden.water_all_smart()

            # Advance simulation by one hour
            try:
                self.garden.next_phase()
            except Exception:
                pass

            # ---------------- UI refresh logic ----------------
            try:
                if getattr(self, "ff_render_daily", None) is not None and self.ff_render_daily.get():
                    # Daily mode: render once per simulated day
                    if (step + 1) % 24 == 0:
                        self.render_all()
                        try:
                            self.root.update_idletasks()
                            self.root.update()
                        except Exception:
                            pass
                else:
                    # Normal FF mode: render every N simulated hours (user-defined)
                    try:
                        interval = int(self.ff_render_interval.get())
                    except Exception:
                        interval = 9
                    if interval < 1:
                        interval = 1
                    elif interval > 23:
                        interval = 23

                    self._ff_ui_counter = getattr(self, "_ff_ui_counter", 0) + 1
                    if (self._ff_ui_counter % interval) == 0:
                        self.render_all()
                        try:
                            self.root.update_idletasks()
                            self.root.update()
                        except Exception:
                            pass
            except Exception:
                pass

        # After the loop, always do a final render so the clock & header are correct
        self.render_all()
        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass


        # Restore state after fast-forward
        self.fast_forward = False
        self.running = was_running
        self.pause_btn.configure(
            text="⏸ Pause" if self.running else "⏵ Resume"
        )


        self.running = was_running
        try:
            self.pause_btn.configure(text="⏸ Pause" if self.running else "⏵ Resume")
        except Exception:
            pass

    def _toast(self, msg, duration=3000, level=None, **kwargs):
        """Lightweight status message in status bar; falls back gracefully."""
        if 'ms' in kwargs and isinstance(kwargs['ms'], int):
            duration = kwargs['ms']
        try:
            prefix = {'info': 'ℹ️ ', 'warn': '⚠️ ', 'error': '⛔ '}.get(level, '')
            self.status_var.set(prefix + str(msg))
            self.root.after(duration, lambda: self.status_var.set(""))
        except Exception:
            pass

    # ============================================================================
    # Save / Load System
    # ============================================================================
    
    def _on_save_garden(self):
        """Save the entire garden state to a JSON file with optional naming."""
        import datetime
        
        # Ensure data directory exists
        data_dir = os.path.join(_PG_BASE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # Show naming dialog
        garden_name = self._show_save_name_dialog()
        
        # Generate timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create filename based on whether a name was provided
        if garden_name and garden_name.strip():
            # Named save: garden_NAME_TIMESTAMP.json
            safe_name = self._sanitize_filename(garden_name.strip())
            
            # Check if a save with this name already exists
            existing_save = self._find_save_by_name(data_dir, garden_name.strip())
            
            if existing_save:
                # Ask if user wants to replace
                replace = messagebox.askyesno(
                    "Replace Existing Save?",
                    f'A garden named "{garden_name.strip()}" already exists.\n\n'
                    f"Do you want to replace it with the current garden state?\n\n"
                    f"Old save: {existing_save['display_date']}\n"
                    f"New save: {timestamp[:8]}-{timestamp[8]}-{timestamp[9:11]}:{timestamp[11:13]}",
                    icon='warning'
                )
                
                if replace:
                    # Delete the old save
                    try:
                        os.remove(existing_save['filepath'])
                        logging.info(f"Replaced old save: {existing_save['filename']}")
                    except Exception as e:
                        logging.warning(f"Failed to delete old save: {e}")
                else:
                    # User cancelled the replacement
                    return
            
            filename = f"garden_{safe_name}_{timestamp}.json"
            is_named = True
        else:
            # Unnamed save: garden_TIMESTAMP.json
            filename = f"garden_{timestamp}.json"
            is_named = False
        
        filepath = os.path.join(data_dir, filename)
        
        try:
            save_data = self._serialize_garden_state()
            
            # Add garden name to save data if provided
            if is_named:
                save_data['garden_name'] = garden_name.strip()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            # Clean up old unnamed saves (keep only 10 most recent)
            if not is_named:
                self._cleanup_unnamed_saves(data_dir)
            
            display_name = garden_name.strip() if is_named else f"Unnamed ({timestamp})"
            self._toast(f"Garden saved: {display_name}", level="info")
            logging.info(f"Garden saved to {filepath}")
            
        except Exception as e:
            logging.error(f"Failed to save garden: {e}", exc_info=True)
            messagebox.showerror("Save Failed", f"Could not save garden:\n{str(e)}")
    
    def _show_save_name_dialog(self):
        """Show a simple dialog to enter garden name."""
        from tkinter import simpledialog
        
        # Create dialog without sound
        name = simpledialog.askstring(
            "Save Garden",
            "Enter a name for your garden:\n(leave blank for unnamed save)",
            parent=self.root
        )
        
        return name if name else ""
    
    def _sanitize_filename(self, name):
        """Sanitize a name for use in filename."""
        # Remove or replace invalid filename characters
        import re
        # Replace spaces with underscores
        name = name.replace(" ", "_")
        # Remove any characters that aren't alphanumeric, underscore, or hyphen
        name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
        # Limit length to 50 characters
        name = name[:50]
        return name
    
    def _find_save_by_name(self, data_dir, garden_name):
        """Find an existing save file with the given garden name.
        
        Returns a dict with save info if found, None otherwise.
        """
        try:
            for filename in os.listdir(data_dir):
                if filename.startswith("garden_") and filename.endswith(".json"):
                    filepath = os.path.join(data_dir, filename)
                    
                    # Try to read the garden name from the file
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            save_data = json.load(f)
                            stored_name = save_data.get('garden_name')
                            
                            # Check if names match (case-insensitive comparison)
                            if stored_name and stored_name.strip().lower() == garden_name.strip().lower():
                                # Extract timestamp from filename for display
                                name_part = filename.replace("garden_", "").replace(".json", "")
                                timestamp_str = name_part[-15:] if len(name_part) >= 15 else ""
                                
                                try:
                                    if len(timestamp_str) == 15:
                                        date_part = timestamp_str[:8]
                                        time_part = timestamp_str[9:]
                                        display_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                                    else:
                                        display_date = "Unknown date"
                                except:
                                    display_date = "Unknown date"
                                
                                return {
                                    'filename': filename,
                                    'filepath': filepath,
                                    'garden_name': stored_name,
                                    'display_date': display_date
                                }
                    except:
                        # Skip files that can't be read
                        continue
            
            return None
        except Exception as e:
            logging.warning(f"Error searching for existing save: {e}")
            return None
    
    def _cleanup_unnamed_saves(self, data_dir):
        """Keep only the 10 most recent unnamed saves, delete older ones."""
        try:
            # Find all unnamed save files (those without a name between garden_ and timestamp)
            unnamed_saves = []
            
            for filename in os.listdir(data_dir):
                if filename.startswith("garden_") and filename.endswith(".json"):
                    # Check if it's an unnamed save (garden_TIMESTAMP.json pattern)
                    # Unnamed: garden_20260131_123456.json (20 chars before .json)
                    # Named: garden_NAME_20260131_123456.json (more than 20 chars)
                    name_part = filename.replace("garden_", "").replace(".json", "")
                    
                    # If name_part is exactly YYYYMMDD_HHMMSS (15 chars), it's unnamed
                    if len(name_part) == 15 and name_part[8] == '_':
                        filepath = os.path.join(data_dir, filename)
                        mtime = os.path.getmtime(filepath)
                        unnamed_saves.append((filename, filepath, mtime))
            
            # Sort by modification time (oldest first for deletion)
            unnamed_saves.sort(key=lambda x: x[2])
            
            # Keep only the 10 most recent (delete the rest)
            if len(unnamed_saves) > 10:
                to_delete = unnamed_saves[:-10]  # All except the last 10
                for filename, filepath, mtime in to_delete:
                    try:
                        os.remove(filepath)
                        logging.info(f"Deleted old unnamed save: {filename}")
                    except Exception as e:
                        logging.warning(f"Failed to delete old save {filename}: {e}")
        
        except Exception as e:
            logging.warning(f"Failed to cleanup unnamed saves: {e}")
    
    def _on_delete_saves(self):
        """Show dialog to delete multiple save files."""
        data_dir = os.path.join(_PG_BASE_DIR, "data")
        
        if not os.path.exists(data_dir):
            messagebox.showinfo("No Saves", "No save files found.")
            return
        
        # Get all save files
        save_files = []
        for filename in os.listdir(data_dir):
            if filename.startswith("garden_") and filename.endswith(".json"):
                filepath = os.path.join(data_dir, filename)
                mtime = os.path.getmtime(filepath)
                
                # Try to read garden name
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        save_data = json.load(f)
                        garden_name = save_data.get('garden_name')
                except:
                    garden_name = None
                
                save_files.append({
                    'filename': filename,
                    'filepath': filepath,
                    'mtime': mtime,
                    'garden_name': garden_name
                })
        
        if not save_files:
            messagebox.showinfo("No Saves", "No save files found.")
            return
        
        # Sort by modification time (newest first)
        save_files.sort(key=lambda x: x['mtime'], reverse=True)
        
        # Create dialog
        dialog = Toplevel(self.root)
        dialog.title("Delete Saves")
        dialog.geometry("500x600")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Title
        title_frame = tk.Frame(dialog, bg="#2b4d59", pady=10)
        title_frame.pack(fill="x")
        tk.Label(
            title_frame,
            text="Select saves to delete",
            font=("Segoe UI", 14, "bold"),
            bg="#2b4d59",
            fg="white"
        ).pack()
        
        # Select All checkbox
        select_all_frame = tk.Frame(dialog, bg="#f0f0f0", pady=8)
        select_all_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        select_all_var = tk.BooleanVar(value=False)
        checkboxes = []  # Store all checkbox variables
        
        def toggle_all():
            state = select_all_var.get()
            for var in checkboxes:
                var.set(state)
        
        tk.Checkbutton(
            select_all_frame,
            text="Select All",
            variable=select_all_var,
            command=toggle_all,
            font=("Segoe UI", 10, "bold"),
            bg="#f0f0f0"
        ).pack(anchor="w", padx=5)
        
        # Scrollable list of saves
        list_frame = tk.Frame(dialog)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        canvas = tk.Canvas(list_frame, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Add checkboxes for each save
        for save_info in save_files:
            var = tk.BooleanVar(value=False)
            checkboxes.append(var)
            
            # Create display name
            if save_info['garden_name']:
                # Named save
                name_part = save_info['filename'].replace("garden_", "").replace(".json", "")
                timestamp_str = name_part[-15:] if len(name_part) >= 15 else ""
                
                try:
                    if len(timestamp_str) == 15:
                        date_part = timestamp_str[:8]
                        time_part = timestamp_str[9:]
                        display_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                        display_time = f"{time_part[:2]}:{time_part[2:4]}"
                        display_name = f"📗 {save_info['garden_name']} ({display_date} {display_time})"
                    else:
                        display_name = f"📗 {save_info['garden_name']}"
                except:
                    display_name = f"📗 {save_info['garden_name']}"
            else:
                # Unnamed save
                try:
                    parts = save_info['filename'].replace("garden_", "").replace(".json", "")
                    date_part = parts[:8]
                    time_part = parts[9:]
                    display_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                    display_time = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                    display_name = f"📄 {display_date} {display_time}"
                except:
                    display_name = f"📄 {save_info['filename']}"
            
            # Checkbox frame with hover effect
            cb_frame = tk.Frame(scrollable_frame, bg="white")
            cb_frame.pack(fill="x", padx=5, pady=2)
            
            cb = tk.Checkbutton(
                cb_frame,
                text=display_name,
                variable=var,
                font=("Segoe UI", 10),
                bg="white",
                anchor="w"
            )
            cb.pack(fill="x", padx=5, pady=3)
            
            # Store filepath in the variable for later access
            var.filepath = save_info['filepath']
            var.filename = save_info['filename']
        
        # Button frame
        button_frame = tk.Frame(dialog, bg="#f0f0f0", pady=10)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        def delete_selected():
            # Count selected
            to_delete = [var for var in checkboxes if var.get()]
            
            if not to_delete:
                messagebox.showinfo("No Selection", "No saves selected for deletion.", parent=dialog)
                return
            
            # Confirm
            count = len(to_delete)
            if not messagebox.askyesno(
                "Confirm Deletion",
                f"Are you sure you want to delete {count} save file{'s' if count != 1 else ''}?\n\nThis action cannot be undone.",
                parent=dialog
            ):
                return
            
            # Delete files
            deleted_count = 0
            for var in to_delete:
                try:
                    os.remove(var.filepath)
                    logging.info(f"Deleted save: {var.filename}")
                    deleted_count += 1
                except Exception as e:
                    logging.error(f"Failed to delete {var.filename}: {e}")
            
            # Show result
            if deleted_count > 0:
                messagebox.showinfo(
                    "Deletion Complete",
                    f"Successfully deleted {deleted_count} save file{'s' if deleted_count != 1 else ''}.",
                    parent=dialog
                )
            
            # Close dialog
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        tk.Button(
            button_frame,
            text="Delete Selected",
            command=delete_selected,
            bg="#d32f2f",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side="left", padx=5)
        
        tk.Button(
            button_frame,
            text="Cancel",
            command=cancel,
            bg="#757575",
            fg="white",
            font=("Segoe UI", 10),
            padx=20,
            pady=5
        ).pack(side="left", padx=5)
    
    def _on_load_garden(self):
        """Show submenu of available save files to load."""
        # This will be called by the submenu items
        pass
    
    def _build_load_menu(self, parent_menu):
        """Build dynamic submenu showing available save files."""
        data_dir = os.path.join(_PG_BASE_DIR, "data")
        
        # Find all garden save files
        named_saves = []
        unnamed_saves = []
        
        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.startswith("garden_") and filename.endswith(".json"):
                    filepath = os.path.join(data_dir, filename)
                    mtime = os.path.getmtime(filepath)
                    
                    # Parse filename to determine if named or unnamed
                    name_part = filename.replace("garden_", "").replace(".json", "")
                    
                    # Try to read the save file to get the stored name
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            save_data = json.load(f)
                            stored_name = save_data.get('garden_name')
                    except:
                        stored_name = None
                    
                    # If it has a stored name, it's a named save
                    if stored_name:
                        # Extract timestamp from filename (last 15 chars before .json)
                        timestamp_str = name_part[-15:] if len(name_part) >= 15 else ""
                        named_saves.append((stored_name, filename, filepath, mtime, timestamp_str))
                    else:
                        # Unnamed save
                        unnamed_saves.append((filename, filepath, mtime))
        
        # Sort both lists by modification time (newest first)
        named_saves.sort(key=lambda x: x[3], reverse=True)
        unnamed_saves.sort(key=lambda x: x[2], reverse=True)
        
        # Clear existing items
        parent_menu.delete(0, 'end')
        
        if not named_saves and not unnamed_saves:
            parent_menu.add_command(label="(No save files found)", state="disabled")
            return
        
        # Add named saves first
        if named_saves:
            parent_menu.add_command(label="═══ Named Gardens ═══", state="disabled")
            for garden_name, filename, filepath, mtime, timestamp_str in named_saves:
                # Format: "Garden Name (2026-01-31 14:23)"
                try:
                    import datetime
                    if len(timestamp_str) == 15:
                        date_part = timestamp_str[:8]
                        time_part = timestamp_str[9:]
                        display_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                        display_time = f"{time_part[:2]}:{time_part[2:4]}"
                        display_name = f"{garden_name} ({display_date} {display_time})"
                    else:
                        display_name = garden_name
                except:
                    display_name = garden_name
                
                parent_menu.add_command(
                    label=display_name,
                    command=lambda fp=filepath: self._load_garden_from_file(fp)
                )
        
        # Add separator if we have both types
        if named_saves and unnamed_saves:
            parent_menu.add_separator()
        
        # Add unnamed saves
        if unnamed_saves:
            parent_menu.add_command(label="═══ Recent Autosaves ═══", state="disabled")
            for filename, filepath, mtime in unnamed_saves:
                # Create display name from filename
                # garden_20260130_204706.json -> 2026-01-30 20:47:06
                try:
                    import datetime
                    parts = filename.replace("garden_", "").replace(".json", "")
                    date_part = parts[:8]  # YYYYMMDD
                    time_part = parts[9:]   # HHMMSS
                    display_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                    display_time = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                    display_name = f"{display_date} {display_time}"
                except:
                    display_name = filename
                
                parent_menu.add_command(
                    label=display_name,
                    command=lambda fp=filepath: self._load_garden_from_file(fp)
                )
    
    def _load_garden_from_file(self, filepath):
        """Load garden state from a specific file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            # Confirm before loading (this will replace current garden)
            filename = os.path.basename(filepath)
            result = messagebox.askyesno(
                "Load Garden",
                f"Loading '{filename}' will replace your current garden.\n\nContinue?",
                icon='warning'
            )
            
            if not result:
                return
            
            self._deserialize_garden_state(save_data)
            
            self._toast(f"Garden loaded: {filename}", level="info")
            logging.info(f"Garden loaded from {filepath}")
            
        except Exception as e:
            logging.error(f"Failed to load garden: {e}", exc_info=True)
            messagebox.showerror("Load Failed", f"Could not load garden:\n{str(e)}")
    
    def _serialize_garden_state(self):
        """Serialize the entire garden state to a dictionary."""
        import datetime
        
        # Serialize all plants
        plants_data = []
        for tile in self.tiles:
            if tile.plant and tile.plant.alive:
                plant_data = {
                    'tile_idx': tile.idx,
                    'id': tile.plant.id,
                    'generation': tile.plant.generation,
                    'stage': tile.plant.stage,
                    'alive': tile.plant.alive,
                    'days_since_planting': tile.plant.days_since_planting,
                    'health': tile.plant.health,
                    'water': tile.plant.water,
                    'traits': tile.plant.traits,
                    'revealed_traits': tile.plant.revealed_traits,
                    'reveal_order': tile.plant.reveal_order,
                    'entered_stage5_age': tile.plant.entered_stage5_age,
                    'max_age_days': tile.plant.max_age_days,
                    'senescent': tile.plant.senescent,
                    'germination_delay': tile.plant.germination_delay,
                    'pending_cross': tile.plant.pending_cross,
                    'pollinated': tile.plant.pollinated,
                    'emasculated': tile.plant.emasculated,
                    'emasc_day': tile.plant.emasc_day,
                    'emasc_phase': tile.plant.emasc_phase,
                    'selfing_frac_before_emasc': tile.plant.selfing_frac_before_emasc,
                    'pods_total': tile.plant.pods_total,
                    'pods_remaining': tile.plant.pods_remaining,
                    'ovules_per_pod': tile.plant.ovules_per_pod,
                    'ovules_left': tile.plant.ovules_left,
                    'aborted_ovules': tile.plant.aborted_ovules,
                    'ancestry': tile.plant.ancestry,
                    'paternal_ancestry': tile.plant.paternal_ancestry,
                    'last_anther_check_day': tile.plant.last_anther_check_day,
                    'anthers_available_today': tile.plant.anthers_available_today,
                    'anthers_collected_day': tile.plant.anthers_collected_day,
                }
                plants_data.append(plant_data)
        
        # Serialize inventory
        inventory_data = {
            'seeds': [
                {
                    'name': seed.name,
                    'id': seed.id,
                    'source_id': seed.source_id,
                    'donor_id': seed.donor_id,
                    'traits': seed.traits,
                    'generation': seed.generation,
                    'pod_index': seed.pod_index,
                    'genotype': seed.genotype,
                    'ancestry': seed.ancestry,
                }
                for seed in self.harvest_inventory
            ],
            'pollen': [
                {
                    'name': pollen.name,
                    'id': pollen.id,
                    'source_id': pollen.source_id,
                    'collected_day': pollen.collected_day,
                    'expires_day': pollen.expires_day,
                    'genotype': pollen.genotype,
                    'traits': pollen.traits,
                }
                for pollen in self.inventory.get_all('pollen')
            ]
        }
        
        # Serialize garden environment state
        garden_data = {
            'day': self.garden.day,
            'phase_index': self.garden.phase_index,
            'phase': self.garden.phase,
            'clock_hour': self.garden.clock_hour,
            'year': self.garden.year,
            'month': self.garden.month,
            'day_of_month': self.garden.day_of_month,
            'weather': self.garden.weather,
            'temp': self.garden.temp,
            'target_temps': getattr(self.garden, 'target_temps', {}),
            'temp_updates_remaining': getattr(self.garden, 'temp_updates_remaining', 3),
        }
        
        # Serialize history (stored on GardenApp or GardenEnvironment)
        history_data = list(getattr(self.garden, 'history', []))
        
        # Serialize next_plant_id (stored on GardenApp)
        next_plant_id = getattr(self, 'next_plant_id', 1)
        
        # Serialize temperature tracker
        temp_tracker_data = None
        if hasattr(self, 'temp_tracker') and self.temp_tracker:
            temp_tracker_data = {
                'measurements': self.temp_tracker.measurements,
                'modern_measurements': getattr(self.temp_tracker, 'modern_measurements', []),
            }
        
        # Serialize UI settings
        ui_settings = {
            'running': self.running,
            'enable_daynight': self.enable_daynight,
            'auto_water_ff': self.auto_water_ff.get(),
            'auto_water_normal': self.auto_water_normal.get(),
            # 'cross_random': removed (non-functional legacy setting)
            'auto_record_temperature': self.auto_record_temperature.get(),
            'available_seeds': self.available_seeds,
            'grid_rows': ROWS,
            'grid_cols': COLS,
        }
        
        # Serialize archive (for Trait Inheritance Explorer)
        archive_data = None
        if hasattr(self, 'archive') and isinstance(self.archive, dict):
            archive_data = {
                'plants': dict(self.archive.get('plants', {}))
            }
        
        # Compile everything
        save_data = {
            'version': 'v1.0',
            'save_date': datetime.datetime.now().isoformat(),
            'plants': plants_data,
            'inventory': inventory_data,
            'garden': garden_data,
            'history': history_data,
            'archive': archive_data,
            'next_plant_id': next_plant_id,
            'temperature_tracker': temp_tracker_data,
            'ui_settings': ui_settings,
        }
        
        return save_data
    
    def _deserialize_garden_state(self, save_data):
        """Restore garden state from serialized data."""
        
        # Clear current garden
        for tile in self.tiles:
            tile.plant = None
        
        # Restore garden environment
        garden_data = save_data['garden']
        self.garden.day = garden_data.get('day', 1)
        self.garden.phase_index = garden_data.get('phase_index', 0)
        self.garden.phase = garden_data.get('phase', 'morning')
        self.garden.clock_hour = garden_data.get('clock_hour', 6)
        self.garden.year = garden_data.get('year', 1856)
        self.garden.month = garden_data.get('month', 4)
        self.garden.day_of_month = garden_data.get('day_of_month', 1)
        self.garden.weather = garden_data.get('weather', '☀️')
        self.garden.temp = garden_data.get('temp', 12.0)
        
        # Restore optional attributes
        if 'target_temps' in garden_data:
            self.garden.target_temps = garden_data['target_temps']
        if 'temp_updates_remaining' in garden_data:
            self.garden.temp_updates_remaining = garden_data['temp_updates_remaining']
        
        # Restore history
        if not hasattr(self.garden, 'history'):
            self.garden.history = []
        self.garden.history = save_data.get('history', [])
        
        # Restore archive (for Trait Inheritance Explorer)
        if not hasattr(self, 'archive'):
            self.archive = {}
        archive_data = save_data.get('archive')
        if archive_data and isinstance(archive_data, dict):
            self.archive['plants'] = archive_data.get('plants', {})
        else:
            # Initialize empty archive if none in save file
            self.archive['plants'] = {}
        
        # Restore next_plant_id
        self.next_plant_id = save_data.get('next_plant_id', 1)
        
        # Restore temperature tracker
        if save_data.get('temperature_tracker') and hasattr(self, 'temp_tracker') and self.temp_tracker:
            temp_data = save_data['temperature_tracker']
            self.temp_tracker.measurements = temp_data.get('measurements', [])
            self.temp_tracker.modern_measurements = temp_data.get('modern_measurements', [])
        
        # Restore UI settings
        ui_settings = save_data.get('ui_settings', {})
        self.running = ui_settings.get('running', False)
        self.enable_daynight = ui_settings.get('enable_daynight', True)
        self.auto_water_ff.set(ui_settings.get('auto_water_ff', False))
        self.auto_water_normal.set(ui_settings.get('auto_water_normal', False))
        # self.cross_random removed (non-functional legacy setting)
        self.auto_record_temperature.set(ui_settings.get('auto_record_temperature', True))
        self.available_seeds = ui_settings.get('available_seeds', 10)
        
        # Check if grid size changed
        saved_rows = ui_settings.get('grid_rows', ROWS)
        saved_cols = ui_settings.get('grid_cols', COLS)
        if saved_rows != ROWS or saved_cols != COLS:
            messagebox.showwarning(
                "Grid Size Mismatch",
                f"Save file has {saved_rows}x{saved_cols} grid, but current is {ROWS}x{COLS}.\n\n"
                "Plants will be loaded where possible."
            )
        
        # Restore inventory
        inventory_data = save_data['inventory']
        
        # Clear both inventory systems
        self.inventory._items_seeds.clear()
        self.harvest_inventory.clear()
        
        seeds_to_restore = inventory_data.get('seeds', [])
        logging.info(f"Restoring {len(seeds_to_restore)} seeds from save file")
        
        for seed_data in seeds_to_restore:
            try:
                # Seed inherits from InventoryItem(name, id)
                # Then has: source_id, donor_id, traits, generation, pod_index, genotype, ancestry
                seed = Seed(
                    name=seed_data.get('name', f"Seed_{seed_data['id']}"),
                    id=seed_data['id'],
                    source_id=seed_data['source_id'],
                    donor_id=seed_data.get('donor_id'),
                    traits=seed_data.get('traits', {}),
                    generation=seed_data.get('generation', 0),
                    pod_index=seed_data.get('pod_index', 0),
                    genotype=seed_data.get('genotype', {}),
                    ancestry=seed_data.get('ancestry', []),
                )
                # Add to both inventory systems for compatibility
                self.inventory._items_seeds.append(seed)
                self.harvest_inventory.append(seed)
                logging.info(f"Restored seed: {seed.name} (ID: {seed.id})")
            except Exception as e:
                logging.warning(f"Failed to restore seed: {e}")
        
        logging.info(f"Total seeds in inventory after restore: {len(self.inventory._items_seeds)}")
        logging.info(f"Total seeds in harvest_inventory after restore: {len(self.harvest_inventory)}")
        
        self.inventory._items_pollen.clear()
        for pollen_data in inventory_data.get('pollen', []):
            try:
                # Pollen inherits from InventoryItem(name, id)
                # Then requires: source_plant, collection_time
                # Optional: source_id, collected_day, expires_day, genotype, traits
                
                # We can't restore source_plant reference, so we pass None
                # The __post_init__ will be skipped since we provide the metadata directly
                pollen = Pollen(
                    name=pollen_data.get('name', f"Pollen_{pollen_data['id']}"),
                    id=pollen_data['id'],
                    source_plant=None,  # Can't restore plant reference
                    collection_time=0,
                    source_id=pollen_data.get('source_id', 0),
                    collected_day=pollen_data.get('collected_day', 0),
                    expires_day=pollen_data.get('expires_day', 0),
                    genotype=pollen_data.get('genotype', {}),
                    traits=pollen_data.get('traits', {}),
                )
                self.inventory._items_pollen.append(pollen)
            except Exception as e:
                logging.warning(f"Failed to restore pollen: {e}")
        
        # Restore plants
        for plant_data in save_data['plants']:
            tile_idx = plant_data['tile_idx']
            
            # Skip if tile index is out of bounds
            if tile_idx >= len(self.tiles):
                continue
            
            tile = self.tiles[tile_idx]
            
            # Create plant (using Plant constructor with minimal args)
            plant = Plant(
                id=plant_data['id'],
                env=self.garden,
                generation=plant_data['generation'],
            )
            
            # Restore all plant attributes
            plant.stage = plant_data['stage']
            plant.alive = plant_data['alive']
            plant.days_since_planting = plant_data['days_since_planting']
            plant.health = plant_data['health']
            plant.water = plant_data['water']
            plant.traits = plant_data['traits']
            plant.revealed_traits = plant_data['revealed_traits']
            plant.reveal_order = plant_data['reveal_order']
            plant.entered_stage5_age = plant_data.get('entered_stage5_age')
            plant.max_age_days = plant_data['max_age_days']
            plant.senescent = plant_data['senescent']
            plant.germination_delay = plant_data['germination_delay']
            plant.pending_cross = plant_data.get('pending_cross')
            plant.pollinated = plant_data['pollinated']
            plant.emasculated = plant_data['emasculated']
            plant.emasc_day = plant_data.get('emasc_day')
            plant.emasc_phase = plant_data.get('emasc_phase')
            plant.selfing_frac_before_emasc = plant_data['selfing_frac_before_emasc']
            plant.pods_total = plant_data['pods_total']
            plant.pods_remaining = plant_data['pods_remaining']
            plant.ovules_per_pod = plant_data['ovules_per_pod']
            plant.ovules_left = plant_data['ovules_left']
            plant.aborted_ovules = plant_data['aborted_ovules']
            plant.ancestry = plant_data['ancestry']
            plant.paternal_ancestry = plant_data['paternal_ancestry']
            plant.last_anther_check_day = plant_data.get('last_anther_check_day')
            plant.anthers_available_today = plant_data['anthers_available_today']
            plant.anthers_collected_day = plant_data.get('anthers_collected_day')
            
            tile.plant = plant
        
        # Update UI
        self.render_all()
        self._update_temp_button_state()
        
        # Update seed counter display
        if hasattr(self, "seed_counter_var"):
            try:
                self.seed_counter_var.set(f"Seeds: {len(self.harvest_inventory)}")
            except Exception:
                pass
        
        # Update pause button text
        self.pause_btn.configure(
            text=("⏸ Pause" if self.running else "▶ Resume")
        )

    def _show_help(self):
        # --- Window ---
        top = Toplevel(self.root)
        top.title("Help / Legend")
        top.geometry("520x600")

        # --- Outer frame for canvas + scrollbar ---
        outer = tk.Frame(top)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        vscroll = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)

        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # --- Inner scrollable frame ---
        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")

        # --- Update scrollregion whenever size changes ---

# ============================================================================
# Event Handlers
# ============================================================================
        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _on_configure)

        # --- Mouse wheel scrolling ---
        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        BODY_FONT = ("Segoe UI", 11)
        SUBHEAD_FONT = ("Segoe UI", 12, "bold")
        HEAD_FONT = ("Segoe UI", 13, "bold")

        def add_paragraph(text, padx=20, pady=(0, 6)):
            tk.Label(inner, text=text, font=BODY_FONT, wraplength=480, justify="left")\
              .pack(anchor="w", padx=padx, pady=pady)

        def add_bullets(lines, padx=20):
            for line in lines:
                tk.Label(inner, text="• " + line, font=BODY_FONT, wraplength=480, justify="left")\
                  .pack(anchor="w", padx=padx)

        # ============================================================
        # ======================  HELP CONTENT  ======================
        # ============================================================

        # --- Title ---
        tk.Label(inner, text="Help / Legend", font=("Segoe UI", 16, "bold")).pack(pady=(10, 10))

        # ------------------------------------------------------------
        # HEALTH COLORS
        # ------------------------------------------------------------
        tk.Label(inner, text="🌿 Health Levels", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10)

        health_items = [
            ("#0c0", "Healthy (81–100)"),
            ("#6f6", "Okay (61–80)"),
            ("#ff0", "Stressed (41–60)"),
            ("#f90", "Critical (21–40)"),
            ("#f33", "Dying (1–20)"),
            ("#666", "Dead (0)")
        ]

        for color, label in health_items:
            f = tk.Frame(inner)
            f.pack(anchor='w', padx=20)
            c = tk.Canvas(f, width=20, height=20, highlightthickness=1)
            c.create_rectangle(0, 0, 20, 20, fill=color, width=0)
            c.pack(side=tk.LEFT)
            tk.Label(f, text=label, font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=6)

        # ------------------------------------------------------------
        # WATER BAR
        # ------------------------------------------------------------
        tk.Label(inner, text="💧 Water Bar", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 0))

        tk.Label(
            inner,
            text="Left vertical blue bar shows water level (0–100). "
                 "100 does NOT fill the tile completely (75% max) to avoid overflow effects.",
            wraplength=480,
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 6))

        # ------------------------------------------------------------
        # SOIL MOISTURE COLORS
        # ------------------------------------------------------------
        tk.Label(inner, text="🌱 Soil Moisture Colors", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10, pady=(10, 0))

        soil_items = [
            ("#FFD54F", "Dry (0–25)"),
            ("#81D4FA", "Slightly moist (26–50)"),
            ("#42A5F5", "Evenly moist (51–75)"),
            ("#1565C0", "Soggy (76–90)"),
            ("#003F8C", "Waterlogged (91–100)")
        ]

        for color, label in soil_items:
            f = tk.Frame(inner)
            f.pack(anchor="w", padx=20)
            c = tk.Canvas(f, width=20, height=20, highlightthickness=1)
            c.create_rectangle(0, 0, 20, 20, fill=color, width=0)
            c.pack(side=tk.LEFT)
            tk.Label(f, text=label, font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=6)

        # ------------------------------------------------------------
        # TIPS
        # ------------------------------------------------------------
        tk.Label(inner, text="⚠️ Tips", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10, pady=(12, 0))

        tips = [
            "Water only morning or evening to avoid heat stress.",
            "Rain gently increases water level and blocks manual watering.",
            "Overwatering (>85) slowly damages plants.",
            "Very wet soil (>95) damages plants strongly.",
            "Plants with poor health (≤20) might die at phase transitions.",
            "Temperature changes gradually over the day.",
        ]

        for t in tips:
            tk.Label(inner, text="• " + t, wraplength=480, justify="left").pack(anchor="w", padx=20)

        # ------------------------------------------------------------
        # KEYBOARD SHORTCUTS
        # ------------------------------------------------------------
        tk.Label(inner, text="⌨️ Keyboard Shortcuts", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=10, pady=(12, 0))

        shortcuts = [
            ("H", "Help / Legend"),
            ("W", "Water all plants"),
            ("w", "Water selected plant"),
            ("F", "Fast Forward mode"),
            ("Space / P", "Pause / Resume day cycle"),
            ("Arrow keys", "Move selection"),
            ("Enter", "Inspect selected plant"),
            ("X / Del", "Remove selected plant"),
            ("Shift+X", "Remove ALL plants"),
            ("E", "Emasculate selected plant"),
            ("C", "Collect pollen"),
            ("O", "Perform pollination"),
            ("Shift+O", "Open Summary → Pollen"),
            ("S", "Harvest seeds (one pod)"),
            ("Shift+S", "Harvest ALL seeds (remove plant)"),
            ("N", "Plant from harvested seeds"),
            ("L", "Open Mendel’s Notebook"),
            ("G", "Toggle garden background"),
            ("Ctrl+G", "Show genotype viewer"),
        ]

        for key, text in shortcuts:
            row = tk.Frame(inner)
            row.pack(anchor="w", padx=20)
            tk.Label(row, text=f"{key}:", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT, padx=(0, 6))
            tk.Label(row, text=text, font=("Segoe UI", 11)).pack(side=tk.LEFT)

        # ------------------------------------------------------------
        # REPRODUCTION: EMASCULATION / POLLINATION / POLLEN
        # ------------------------------------------------------------
        tk.Label(inner, text="Reproduction: Emasculation & Pollination", font=HEAD_FONT)\
          .pack(anchor="w", padx=10, pady=(12, 0))

        add_paragraph("Reproductive actions are possible once a plant reaches the Budding/Flowering stage.")

        tk.Label(inner, text="Emasculation", font=SUBHEAD_FONT)\
          .pack(anchor="w", padx=20, pady=(6, 0))

        add_bullets([
            "Emasculation means removing the male organs (anthers) from a flower to prevent further self-fertilization.",
            "It can be done during the Budding/Flowering stage (early or late), but only once per plant.",
            "Timing matters: peas often self-fertilize before the flower opens.",
            "Early emasculation leaves most ovules unfertilized; late emasculation has a high risk that selfing already occurred.",
            "Emasculation cannot undo self-fertilization that already happened — it only reduces additional selfing afterwards.",
        ], padx=30)

        tk.Label(inner, text="Pollination", font=SUBHEAD_FONT)\
          .pack(anchor="w", padx=20, pady=(10, 0))

        add_bullets([
            "Pollination means applying pollen to the female part of a flower.",
            "It can be done during Flowering.",
            "Emasculation is optional, but recommended for controlled crosses (to reduce selfing).",
            "After successful pollination, pods develop and mature seeds can later be harvested.",
        ], padx=30)

        tk.Label(inner, text="Pollen availability", font=SUBHEAD_FONT)\
          .pack(anchor="w", padx=20, pady=(10, 0))

        add_bullets([
            "Flowering plants do not produce collectable pollen every day.",
            "Pollen availability is determined once per flowering day.",
            "Inspecting a flowering plant shows today’s pollen status.",
            "Status messages: “Pollen available” (can collect today) or “No pollen available” (try another day).",
        ], padx=30)

    def _prev_generation(self, gen: str) -> str:
        m = re.match(r"F(\d+)", str(gen or "F0"))
        try:
            n = int(m.group(1)) if m else 0
            return f"F{max(0, n-1)}"
        except Exception:
            return "F0"

    def _next_generation(self, gen: str) -> str:
        m = re.match(r"F(\d+)", str(gen or "F0"))
    
        try:
            n = int(m.group(1)) if m else 0
        except Exception:
            n = 0
        return f"F{n+1}"

    def _next_id(self) -> int:
        try:
            if not hasattr(self, "used_ids"):
                self.used_ids = set()
            pid = self.next_plant_id
            while pid in self.used_ids:
                pid += 1
            self.used_ids.add(pid)
            self.next_plant_id = pid + 1
            return pid
        except Exception:
            pid = self.next_plant_id
            self.next_plant_id += 1
            return pid

    def _starter_traits_for_next_seed(self):
        # Balanced founders: independent 50/50 for each classic trait to avoid bias
        return {
            "flower_color": random.choice(["purple","white"]),
            "seed_color":   random.choice(["yellow","green"]),
            "seed_shape":   random.choice(["round","wrinkled"]),
            "plant_height": random.choice(["tall","short"]),
            "pod_color":    random.choice(["green","yellow"]),
            "pod_shape":    "inflated",
            "flower_position": random.choice(["axial","terminal"]),
        }

    def _default_starter_traits(self):

        # Fallback founders (unused when _starter_traits_for_next_seed is called)
        return {

            "flower_color": "purple",
            "seed_color": "yellow",
            "seed_shape": "round",
            "plant_height": "tall",
            "pod_color": "green",
            "pod_shape": "inflated",
            "flower_position": "axial",
        }

    def _find_plant(self, pid):
        try:
            if hasattr(self, "_get_plant_by_id"):
                p = self._get_plant_by_id(pid)
                if p is not None:
                    return p
        except Exception:
            pass
        try:
            for p in getattr(self.garden, "plants", []) or []:
                if p is not None and getattr(p, "id", None) == pid:
                    return p
        except Exception:
            pass
        try:
            if pid in getattr(self, "registry", {}):
                return self.registry[pid]
        except Exception:
            pass
        try:
            for p in getattr(self, "hidden_plants", []) or []:
                if getattr(p, "id", None) == pid:
                    return p
        except Exception:
            pass
        return None

    def _season_register_live(self, sim_date):
        try:
            for p in getattr(self.garden, "plants", []) or []:
                if p is None or not getattr(p, "alive", True):
                    continue
                pid = getattr(p, "id", None)
                if pid is None or pid in getattr(self, "_season_registered", set()):
                    continue
                sow_date = getattr(p, "sow_date", None)
                if not sow_date:
                    try:
                        sow_date = sim_date
                        setattr(p, "sow_date", sow_date)
                    except Exception:
                        sow_date = sim_date
                try:
                    self._season.register_plant(pid, sow_date)
                    self._season_registered.add(pid)
                except Exception:
                    pass
        except Exception:
            pass

    def _season_daily_update(self, sim_date):
        mode = str(getattr(self, "_season_mode", "off")).lower()
        if mode not in ("overlay", "enforce"):
            return
        try:
            try:
                self._season.update_soil(sim_date)
            except Exception:
                pass
            self._season_register_live(sim_date)
            ids = []
            try:
                for p in getattr(self.garden, "plants", []) or []:
                    if p is not None and getattr(p, "alive", True):
                        ids.append(getattr(p, "id", None))
            except Exception:
                pass
            ids = [i for i in ids if i is not None]
            if not ids:
                return
            events = []
            try:
                events = self._season.update_day(sim_date, ids)
            except Exception:
                events = []
            for ev in events or []:
                try:
                    if str(ev.get('type','')).lower() == 'senescence_start':
                        self._toast(f"Plant #{ev.get('plant_id')} entered senescence")
                except Exception:
                    pass
                pid = ev.get("plant_id")
                plant = self._find_plant(pid)
                if plant is None:
                    continue
                
                # Skip processing for already dead plants
                if not getattr(plant, "alive", False):
                    continue
                
                try:
                    delta = int(ev.get("suggested_health_delta", 12) or 0)
                except Exception:
                    delta = 0
                
                # Apply health delta with variation already built into season model
                if delta < 0:
                    try:
                        cur = int(getattr(plant, "health", 100))
                        new_health = max(0, cur + delta)
                        setattr(plant, "health", new_health)
                        
                        # Natural death when health reaches 0 (only if was alive)
                        if new_health <= 0 and getattr(plant, "alive", True):
                            plant.alive = False
                            try:
                                etype = str(ev.get("type", "")).lower()
                                # Determine death message based on cause
                                if "critical_stress" in etype or "chronic" in etype:
                                    death_msg = f"Plant #{pid} died from prolonged stress"
                                elif "senescent" in etype:
                                    death_msg = f"Plant #{pid} died of old age"
                                elif "lethal" in etype or "freeze" in etype:
                                    death_msg = f"Plant #{pid} killed by freeze"
                                else:
                                    death_msg = f"Plant #{pid} died from health failure"
                                
                                self._toast(death_msg, level="warning")
                            except Exception:
                                pass
                    except Exception:
                        pass
                
                # Only handle true lethal events (instant death regardless of health)
                deathish = False
                try:
                    t = str(ev.get("type", "")).lower()
                    m = str(ev.get("message", "")).lower()
                    sd = ev.get("suggested_health_delta", 12) or 0
                    # ONLY instant death for: lethal_freeze or massive instant damage
                    # Removed: wither, accumulated stress (those now drain health gradually)
                    deathish = (
                        t in ("lethal_freeze",)  # Only lethal freeze causes instant death
                        or (isinstance(sd, (int, float)) and sd <= -9000)  # Or massive instant damage
                    )
                except Exception:
                    deathish = False
                
                if deathish and (mode == "enforce" or t == "lethal_freeze"):
                    try:
                        # Check again if plant is still alive before killing
                        if getattr(plant, "alive", False):
                            plant.alive = False
                            if hasattr(plant, "health"):
                                plant.health = 0
                            try:
                                self._toast(f"Plant #{pid} killed by freeze — {ev.get('message','')}", level="warning")
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

    def _season_poll(self):
        try:
            sim_date = dt.date(int(getattr(self.garden, "year")), int(getattr(self.garden, "month")), int(getattr(self.garden, "day_of_month")))
        except Exception:
            sim_date = None
        last = getattr(self, "_season_last_date", None)
        if sim_date is not None and sim_date != last:
            self._season_last_date = sim_date
            try:
                self._season_daily_update(sim_date)
            except Exception:
                pass
        elif sim_date is not None:
            # No date change: still check for immediate lethal conditions
            try:
                res = self._season.can_grow(sim_date)
                ok, why = (res if isinstance(res, tuple) else (bool(res), ""))
            except Exception:
                ok, why = (True, "")
            try:
                if (not ok) and ("lethal" in str(why).lower()):
                    
                    self._season_daily_update(sim_date)
                    self._season_apply_hourly_lethal(-20)
                    self._season_daily_update(sim_date)
            except Exception:
                pass
        try:
            self.root.after(500, self._season_poll)
        except Exception:
            pass

    def _season_apply_hourly_lethal(self, points_per_hour=-20):
        try:
            interval = int(getattr(self, 'SEASON_HOURLY_MS', 2500))
        except Exception:
            interval = 2500
        now_ms = int(time.time() * 1000)
        last = getattr(self, '_season_last_hourly_tick', None)
        if last is None or (now_ms - int(last)) >= interval:
            self._season_last_hourly_tick = now_ms
            pts = int(points_per_hour) if isinstance(points_per_hour, (int, float)) else -20
            for plant in getattr(self.garden, 'plants', []) or []:
                if plant is None or not getattr(plant, 'alive', True):
                    continue
                try:
                    h = int(getattr(plant, 'health', 100))
                except Exception:
                    h = 100
                newh = max(0, h + pts)
                try:
                    plant.health = newh
                except Exception:
                    pass
                if newh <= 0:
                    try:
                        plant.alive = False
                    except Exception:
                        pass
            try:
                self.render_all()
            except Exception:
                pass

        
    def _update_plants_for_difficulty_change(self):
        """
        Updates all existing plants to match the new difficulty setting.
        
        Adjusts:
        - plant.difficulty (for growth thresholds)
        - plant.max_age_days (proportionally scaled to new difficulty range)
        
        This ensures fair gameplay when switching difficulty mid-game.
        """
        from plant import get_lifecycle_settings
        
        try:
            new_mode = self._season_mode
            
            # Get all living plants
            plants = []
            for tile in self.tiles:
                if tile.plant and getattr(tile.plant, 'alive', False):
                    plants.append(tile.plant)
            
            if not plants:
                return  # No plants to update
            
            # Update each plant
            for plant in plants:
                old_difficulty = getattr(plant, 'difficulty', 'off')
                
                # Update difficulty setting
                plant.difficulty = new_mode
                
                # Proportionally scale max_age to new difficulty range
                old_settings = get_lifecycle_settings(old_difficulty)
                new_settings = get_lifecycle_settings(new_mode)
                
                old_min, old_max = old_settings["max_age_range"]
                new_min, new_max = new_settings["max_age_range"]
                
                current_max_age = getattr(plant, 'max_age_days', old_min)
                
                # Calculate relative position in old range (0.0 to 1.0)
                if old_max > old_min:
                    position = (current_max_age - old_min) / (old_max - old_min)
                    position = max(0.0, min(1.0, position))  # Clamp to 0-1
                else:
                    position = 0.5  # Default to middle if range invalid
                
                # Apply same relative position to new range
                new_max_age = int(new_min + position * (new_max - new_min))
                plant.max_age_days = new_max_age
                
                # If plant is already senescent, make sure it stays consistent
                current_age = getattr(plant, 'days_since_planting', 0)
                if getattr(plant, 'senescent', False):
                    # Already senescent, ensure max_age is still ahead
                    plant.max_age_days = max(new_max_age, current_age + 5)
            
            # Log the update
            print(f"[DIFFICULTY] Updated {len(plants)} plants to {new_mode} mode")
            
        except Exception as e:
            print(f"[ERROR] Failed to update plants for difficulty change: {e}")

    def _season_cycle_mode(self, event=None):
        """
        Cycles the season mode (F9 key binding).
        Syncs with menu and displays toast notification.
        Updates existing plants to match new difficulty.
        """
        idx = self.SEASON_MODES.index(getattr(self, "_season_mode", "off"))
        next_idx = (idx + 1) % len(self.SEASON_MODES)
        self._season_mode = self.SEASON_MODES[next_idx]
        
        # Update existing plants to match new difficulty
        self._update_plants_for_difficulty_change()
        
        # Sync with menu radio buttons
        if hasattr(self, '_difficulty_var'):
            self._difficulty_var.set(self._season_mode)
        
        # User-friendly messages
        messages = {
            "off": "Difficulty: Casual (F9)",
            "overlay": "Difficulty: Moderate (F9)",
            "enforce": "Difficulty: Realistic (F9)"
        }
        
        msg = messages.get(self._season_mode, f"Season model: {self._season_mode}")
        self._toast(msg)

    def _on_difficulty_change(self):
        """
        Called when user changes difficulty setting from the menu.
        Updates the season mode and displays appropriate notification.
        Updates existing plants to match new difficulty.
        """
        new_mode = self._difficulty_var.get()
        self._season_mode = new_mode
        
        # Update existing plants to match new difficulty
        self._update_plants_for_difficulty_change()
        
        # Update difficulty variable to stay in sync
        if hasattr(self, '_difficulty_var'):
            self._difficulty_var.set(new_mode)
        
        # User-friendly messages
        messages = {
            "off": "Difficulty: Casual — Plants only affected by water/health",
            "overlay": "Difficulty: Moderate — Temperature effects shown (no deaths)",
            "enforce": "Difficulty: Realistic — Full environmental simulation (Mendel-era)"
        }
        
        msg = messages.get(new_mode, f"Difficulty: {new_mode}")
        self._toast(msg)

    def _season_gate_sowing(self):
        """
        Returns True if sowing is allowed under the current season model; otherwise
        shows a toast explaining why and returns False. Safe to call even if the
        season module is not installed or is disabled.
        """
        try:
            if hasattr(self, "_season") and str(getattr(self, "_season_mode", "off")).lower() in ("overlay", "enforce"):
                sim_date = dt.date(
                    int(getattr(self.garden, 'year', 1866)),
                    int(getattr(self.garden, 'month', 4)),
                    int(getattr(self.garden, 'day_of_month', 1))
                )
                res = self._season.can_sow(sim_date)
                ok, why = (res if isinstance(res, tuple) else (bool(res), ""))
                if not ok:
                    try:
                        self._toast(f"Sowing blocked by season model: {why}", level="warn")
                    except Exception:
                        pass
                    return False

                # Extra safety: block if climate says it's below 0°C right now (soil/air)
                try:
                    temp_now = None
                    if hasattr(self, '_climate_v2') and self._climate_v2:
                        # Prefer soil temp if available
                        temp_now = getattr(self._climate_v2, 'current_soil_temp', None) or getattr(self._climate_v2, 'current_air_temp', None)
                    if temp_now is None:
                        # Fallback: garden temp if present
                        temp_now = getattr(self.garden, 'temp', None)
                    if isinstance(temp_now, (int, float)) and temp_now < 0:
                        try:
                            self._toast(f"Sowing blocked: too cold (current temp {temp_now:.1f}°C).", level="warn")
                        except Exception:
                            pass
                        return False
                except Exception:
                    pass
        except Exception:
            # Any errors: don't hard-crash sowing decision; allow sowing
            pass
        return True

    def _seed_archive_safe(self):
        """Try to seed the archive before opening archive-only views.
        Calls seed_archive_from_live(self, force=True) if available; else falls back to seed_archive_from_live(self).
        """
        return self.seed_archive_from_live(force=True)

    def _eager_seed_and_backfill(self):
        """Seed archive from live + parent backfill + lineage merge."""
        # seed from live
        self.seed_archive_from_live(force=True)
        # backfill parents
        try:
            self.archive._archive_backfill_cross_parents(self)
        except Exception:
            pass
        # merge archive => lineage_store
        try:
            if "lineage_store" in dir(self):
                pls = self.lineage_store.setdefault("plants", {})
                for k, v in (getattr(self, "archive", {}).get("plants", {}) or {}).items():
                    pls[str(k)] = v
        except Exception:
            pass

    def seed_archive_from_live(self, force=False):
        """
        If app.archive['plants'] is empty and live plants exist,
        create minimal snapshots so the Archive Browser and archive-only lineage can show data.
        Returns True if it added any snapshots, else False.
        """
        try:
            if not hasattr(self, "archive"):
                self.archive = {}
            if "plants" not in self.archive or not isinstance(self.archive["plants"], dict):
                self.archive["plants"] = {}
            # already populated?
            if self.archive["plants"] and not force:
                return False

            garden = getattr(self, "garden", None)
            live = getattr(garden, "plants", None) if garden is not None else None
            if not live:
                return False

            def get(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            count = 0
            for p in live:
                try:
                    pid = get(p, "id", None)
                    if pid is None:
                        continue
                    snap = {
                        "id": pid,
                        "generation": get(p, "generation", get(p, "gen", "F?")),
                        "mother_id": get(p, "mother_id", get(p, "motherId", None)),
                        "father_id": get(p, "father_id", get(p, "fatherId", None)),
                        "traits": get(p, "traits", {}) or {},
                        # Lineage helpers used by the Trait Inheritance Explorer
                        "ancestry": list(get(p, "ancestry", []) or []),
                        "paternal_ancestry": list(get(p, "paternal_ancestry", []) or []),
                    }

                    # Safety: ensure F0 lineage is never blank in archive-only views
                    try:
                        if str(snap.get("generation", "")).upper() == "F0":
                            if not snap.get("ancestry"):
                                snap["ancestry"] = [pid]
                            if not snap.get("paternal_ancestry"):
                                snap["paternal_ancestry"] = [pid]
                    except Exception:
                        pass
                    geno = get(p, "genotype", None)
                    if geno:
                        snap["genotype"] = geno
                    pidx = get(p, "source_pod_index", get(p, "pod_index", None))
                    if pidx is not None:
                        snap["source_pod_index"] = pidx
                    self.archive["plants"][pid] = snap
                    count += 1
                except Exception:
                    pass
            return count > 0
        except Exception:
            return False
        
    def open_history_archive_browser(self, parent_window, default_pid=None):
        # Simple wrapper used by the Genetics window button.
        HistoryArchiveBrowser(parent_window, self, default_pid=default_pid)

    def _set_day_length(self, secs, reschedule=True):
        """Compatibility wrapper: old UI calls _set_day_length(), v2 uses _set_day_length_patched()."""
        return self._set_day_length_patched(secs, reschedule=reschedule)

    def _set_day_length_patched(self, secs, reschedule=True):
        try:
            secs = float(secs)

            # Allow very fast speeds but avoid UI lockups
            if secs < 0.1:
                secs = 0.1

            # seconds of real time per simulated HOUR
            self.day_length_s = secs

        except Exception:
            return

        # Recompute derived timers (phase_ms, sub_ms, etc.)
        try:
            self._recalc_timers()
        except Exception:
            pass

        # Reschedule the auto-loop so the change takes effect immediately
        try:
            if reschedule and not getattr(self, "real_time_mode", False):
                if getattr(self, "_auto_loop_id", None) is not None:
                    try:
                        self.root.after_cancel(self._auto_loop_id)
                    except Exception:
                        pass
                    self._auto_loop_id = None

                self._ensure_auto_loop(delay_ms=max(50, getattr(self, "phase_ms", 600)))
        except Exception:
            pass

    def _phase_from_wallclock_patched(self):
        try:
            now = dt.datetime.now()
            h = now.hour
            if 6 <= h < 12: return "morning"
            if 12 <= h < 15: return "noon"
            if 15 <= h < 19: return "afternoon"
            return "evening"
        except Exception:
            return getattr(self.garden, "phase", "morning")

    def _enable_real_time_patched(self, enabled: bool):
        try:
            self.real_time_mode = bool(enabled)
        except Exception:
            self.real_time_mode = False
        try:
            if getattr(self, "_auto_loop_id", None) is not None:
                try: self.root.after_cancel(self._auto_loop_id)
                except Exception: pass
                self._auto_loop_id = None
        except Exception:
            pass
        if self.real_time_mode:
            try:
                self._real_time_heartbeat()
            except Exception:
                pass
        else:
            try:
                if getattr(self, "running", True):
                    self._ensure_auto_loop(delay_ms=max(50, getattr(self, 'phase_ms', 600)))
            except Exception:
                pass

    def _real_time_heartbeat_patched(self):
        try:
            target = self._phase_from_wallclock()
            cur = getattr(self.garden, "phase", None)
            max_steps = 4
            while cur != target and max_steps > 0:
                try:
                    self.garden.next_phase()
                except Exception:
                    break
                max_steps -= 1
                cur = getattr(self.garden, "phase", None)
            try: self.render_all()
            except Exception: pass
        except Exception:
            pass
        try:
            if getattr(self, "real_time_mode", False):
                self._auto_loop_id = self.root.after(30000, self._real_time_heartbeat)
        except Exception:
            pass

    def _recalc_timers(self):
        """Compute per-phase sub-update and phase delays (ms)
        from desired speed (seconds per simulated hour)."""
        try:
            # day_length_s is interpreted as *seconds of real time per simulated HOUR*
            per_hour = max(0.1, float(self.day_length_s))  # allow very fast speeds
        except Exception:
            per_hour = 1.0

        # Keep the old proportions: 3 temperature sub-updates vs one phase wait
        # (1050 ms vs 600 ms at the old reference speed)
        sub_ratio_total = 1050.0
        phase_ratio = 600.0
        total = sub_ratio_total + phase_ratio  # 1650

        # Total wall time for one simulated hour ≈ per_hour seconds
        sub_total = per_hour * (sub_ratio_total / total)  # seconds across 3 substeps

        # Milliseconds per substep / phase
        self.sub_ms = max(50, int((sub_total / 3.0) * 1000))                 # ms per substep
        self.phase_ms = max(50, int((per_hour * (phase_ratio / total)) * 1000))  # ms after phase advance

    def archive_snapshot(self, plant, **extras):
        """
        Upsert a single plant snapshot into app.archive['plants'].
        Extras (e.g., source_pod_index=...) will be merged in.
        """
        try:
            if not hasattr(self, "archive"):
                self.archive = {}
            plants = self.archive.setdefault("plants", {})
            def g(o, k, d=None):
                return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)
            pid = g(plant, "id", None)
            if pid is None:
                return False
            snap = {
                "id": pid,
                "generation": g(plant, "generation", g(plant, "gen", "F?")),
                "mother_id": g(plant, "mother_id", g(plant, "motherId", None)),
                "father_id": g(plant, "father_id", g(plant, "fatherId", None)),
                "traits": g(plant, "traits", {}) or {},
                # Lineage helpers used by the Trait Inheritance Explorer
                "ancestry": list(g(plant, "ancestry", []) or []),
                "paternal_ancestry": list(g(plant, "paternal_ancestry", []) or []),
            }

            # Safety: ensure F0 lineage is never blank in archive-only views
            try:
                if str(snap.get("generation", "")).upper() == "F0":
                    if not snap.get("ancestry"):
                        snap["ancestry"] = [pid]
                    if not snap.get("paternal_ancestry"):
                        snap["paternal_ancestry"] = [pid]
            except Exception:
                pass
            geno = g(plant, "genotype", None)
            if geno:
                snap["genotype"] = geno
            snap.update(extras or {})
            plants[pid] = snap
            return True
        except Exception:
            return False



def _grid_config_path():
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        base = os.getcwd()
    return os.path.join(base, "mendel_garden_config.json")


def _load_grid_config():
    path = _grid_config_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        rows = int(cfg.get("rows", ROWS))
        cols = int(cfg.get("cols", COLS))
        if rows <= 0 or cols <= 0:
            raise ValueError
        show_dialog = bool(cfg.get("show_dialog", True))
        return {"rows": rows, "cols": cols, "show_dialog": show_dialog}
    except Exception:
        # Broken config → ignore & use defaults
        return None


def _save_grid_config(rows, cols, show_dialog):
    path = _grid_config_path()
    cfg = {"rows": int(rows), "cols": int(cols), "show_dialog": bool(show_dialog)}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        # Failing to save config should never kill the app
        pass

def _apply_grid_size(rows, cols):
    """Update global grid constants so the rest of the sim picks them up."""
    global ROWS, COLS, GRID_SIZE, TILES_PER_ROW
    ROWS = int(rows)
    COLS = int(cols)
    GRID_SIZE = ROWS * COLS
    TILES_PER_ROW = COLS

def _ask_grid_size(root, existing_config=None):
    """Small popup to choose grid size (rows x cols) with recommended resolutions."""

    # Start with existing config if available, otherwise current defaults
    if existing_config:
        rows = existing_config.get("rows", ROWS)
        cols = existing_config.get("cols", COLS)
        show_dialog_next_time = existing_config.get("show_dialog", True)
    else:
        rows = ROWS
        cols = COLS
        show_dialog_next_time = True

    win = tk.Toplevel(root)
    win.title("Garden size")
    win.transient(root)
    win.grab_set()
    win.resizable(False, False)

    try:
        win.geometry("+%d+%d" % (root.winfo_rootx() + 80, root.winfo_rooty() + 80))
    except Exception:
        pass

    main = tk.Frame(win, padx=12, pady=12)
    main.pack(fill="both", expand=True)

    # Preset combo
    tk.Label(main, text="Preset:", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0,4))

    presets = {
        # 4K Ultra HD (3840×2160)
        "32 × 14   (4K Ultra HD ≥ 3840×2160)":     (32, 14),
        "28 × 12   (4K compact)":                  (28, 12),

        # 1440p (2560×1440)
        "24 × 10   (QHD ≥ 2560×1440)":             (24, 10),
        "20 × 9    (QHD compact)":                 (20, 9),

        # 1080p / Full HD (1920×1080)
        "18 × 8    (Full HD max)":                 (18, 8),
        "17 × 8    (Full HD Lenovo X1)":           (17, 8),
        "16 × 7    (Full HD standard)":            (16, 7),   # ← **comma was missing here**

        # 900p (1600×900)
        "14 × 7    (1600×900)":                    (14, 7),

        # HD+ / HD
        "10 × 5    (HD+ ≥ 1366×768)":              (10, 5),
        "8 × 3     (HD ≥ 1280×720)":               (8, 3),
    }

    preset_names = list(presets.keys())

    # Default to the Full HD standard preset (string must match key exactly)
    preset_var = tk.StringVar(value="16 × 7    (Full HD standard)")

    cols_var = tk.StringVar(value=str(cols))
    rows_var = tk.StringVar(value=str(rows))

    def on_preset(*_):
        # Interpret preset as (cols, rows)
        c, r = presets[preset_var.get()]
        cols_var.set(str(c))
        rows_var.set(str(r))


    combo = ttk.Combobox(main, textvariable=preset_var, values=preset_names, state="readonly", width=30)
    combo.grid(row=0, column=1, columnspan=2, sticky="w", padx=(6,0), pady=(0,4))
    combo.bind("<<ComboboxSelected>>", on_preset)

    # Manual entry for cols/rows
    tk.Label(main, text="Columns (x):").grid(row=1, column=0, sticky="e", pady=4)
    cols_entry = ttk.Entry(main, textvariable=cols_var, width=6)
    cols_entry.grid(row=1, column=1, sticky="w", pady=4)

    tk.Label(main, text="Rows (y):").grid(row=2, column=0, sticky="e", pady=4)
    rows_entry = ttk.Entry(main, textvariable=rows_var, width=6)
    rows_entry.grid(row=2, column=1, sticky="w", pady=4)

    # Info text
    info = (
        "Tip:\n"
        "• More columns/rows → more plants, but needs a larger screen.\n"
        "• If the grid does not fit, try a smaller preset."
    )
    tk.Label(main, text=info, justify="left", wraplength=320).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6,8))

    # Checkbox: don't show at next start
    dont_show_var = tk.IntVar()
    if not show_dialog_next_time:
        dont_show_var.set(1)
    chk = ttk.Checkbutton(main, text="Don't show at next start", variable=dont_show_var)
    chk.grid(row=4, column=0, columnspan=3, sticky="w", pady=(0,8))

    # Buttons
    btns = tk.Frame(main)
    btns.grid(row=5, column=0, columnspan=3, sticky="e")

    cancelled = {"value": False}

    def on_ok():
        try:
            c = int(cols_var.get())
            r = int(rows_var.get())
            if c <= 0 or r <= 0:
                raise ValueError
            if c * r > 400:
                if not messagebox.askyesno(
                        "Large grid",
                        f"This will create {c*r} tiles.\nIt may be slow. Continue?"):
                    return
            # Update outer variables
            nonlocal rows, cols, show_dialog_next_time
            cols, rows = c, r
            show_dialog_next_time = not bool(dont_show_var.get())
            win.destroy()
        except Exception:
            messagebox.showerror("Invalid input", "Please enter positive integers for rows and columns.")

    def on_cancel():
        # Just close; keep previous values & show_dialog setting
        cancelled["value"] = True
        win.destroy()

    ok_btn = ttk.Button(btns, text="OK", command=on_ok)
    ok_btn.pack(side="right", padx=(4,0))
    cancel_btn = ttk.Button(btns, text="Cancel", command=on_cancel)
    cancel_btn.pack(side="right")

    win.bind("<Return>", lambda e: on_ok())
    cols_entry.focus_set()
    root.wait_window(win)

    # If cancelled, rows/cols/show_dialog_next_time remain as before
    return rows, cols, show_dialog_next_time
#%% Main entry point
def main():
    root = tk.Tk()
    handler = CrashHandler()
    handler.install()
    # Load last used settings (if any)
    cfg = None
    try:
        cfg = _load_grid_config()
    except Exception:
        cfg = None

    # If user chose to skip dialog: directly apply last settings
    if cfg and not cfg.get("show_dialog", True):
        try:
            _apply_grid_size(cfg["rows"], cfg["cols"])
        except Exception:
            # If something goes wrong, fall back to asking again
            cfg = None

    # If no config, or dialog should be shown → open popup
    if cfg is None or cfg.get("show_dialog", True):
        try:
            rows, cols, show_dialog_next = _ask_grid_size(root, cfg)
            _apply_grid_size(rows, cols)

            # Only save if user selected "Don't show again"
            if show_dialog_next is False:
                _save_grid_config(rows, cols, show_dialog_next)
            else:
                # If user wants dialog next time, remove old config if it exists
                path = _grid_config_path()
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

        except Exception:
            # If dialog fails, just run with whatever global defaults are
            pass

    try:
        # Start maximized on Windows
        root.state('zoomed')
    except Exception:
        try:
            # Cross-platform best-effort
            root.attributes('-zoomed', True)
        except Exception:
            pass

    app = GardenApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
