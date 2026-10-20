"""
inspector.py — the plant Inspect window of the Garden of Inheritance.

Holds everything that builds and refreshes the Inspect window: the header
with stage / health / water, the four fold-out sections (Traits, Harvest,
Crossing, Wildlife), the "Show traits only" window, and the helpers that
keep it on top of other windows and up to date while it is open.

The methods live on InspectorMixin, which the game's main class inherits
(class GardenApp(InspectorMixin)), so they are called exactly as before
(self._open_plant_inspector(...), app._INSPECTOR_SECTIONS, ...).

A few helpers are defined in the game file itself; the game hands them
over at start-up with install(globals()) — see GAME_NAMES.
"""
import logging
import os
import random
import tkinter as tk

from PIL import Image, ImageTk

from plant import STAGE_NAMES
from icon_loader import (ICONS_DIR, budding_icon_path_hi, flower_icon_path_hi,
                         pod_shape_icon_path, safe_image, trait_icon_path)

# Defined in Garden-of-Inheritance.py (filled in by install()).
GAME_NAMES = ("_attach_tooltip", "_load_display_settings", "_save_display_settings")


def _not_installed(*_a, **_k):
    raise RuntimeError("inspector.install() was not called")


_attach_tooltip = _load_display_settings = _save_display_settings = _not_installed


def install(game_globals):
    """Called once by the game file: hands over its helper functions."""
    g = globals()
    for name in GAME_NAMES:
        if name in game_globals:
            g[name] = game_globals[name]
        else:
            logging.warning("inspector: game helper %s is missing", name)


class InspectorMixin:
    """The plant Inspect window (inherited by GardenApp)."""

    def _on_inspect_unified(self):
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None

        if not plant:
            self._toast("Select a plant first.", level="info")
            return
        if not getattr(plant, "alive", True):
            self._toast("Dead plant.", level="warn")
            return

        # Keep original behavior: reveal one trait
        try:
            plant.reveal_trait()
            self._sel_traits_sig = None  # force sidebar refresh
        except Exception:
            pass

        # Do the biological anther check (only matters at stage 5)
        self._ensure_anther_check_today(plant)

        rows = self._build_inspector_status_rows(plant)

        self._open_plant_inspector(plant, rows)
        self._tutorial_inspected = True   # lets the tutorial know (see tutorial.py)
        self.render_all()
        self._raise_inspector()
        try:
            self._nudge_auto_loop()
        except Exception:
            pass

        # Start the smooth day/night animation loop
        try:
            self._start_daynight_animation()
        except Exception:
            pass

    def _raise_inspector(self):
        """Inspect pressed while the window is already open (perhaps behind
        other windows or minimised): bring it to the very front. Not while a
        dialog has it stepped aside (it comes back by itself then)."""
        w = getattr(self, "_inspector_win", None)
        try:
            if w is None or not w.winfo_exists():
                return
            if getattr(self, "_reopen_inspector_after_dialog", False) and not w.winfo_viewable():
                return
            if w.state() in ("iconic", "withdrawn"):
                w.deiconify()
            w.lift()
            # re-assert "always on top" so it also comes above other
            # on-top windows (e.g. the traits-only window)
            w.attributes("-topmost", False)
            w.attributes("-topmost", True)
            w.lift()
        except Exception:
            pass

    def _build_inspector_status_rows(self, plant):
        """
        Build the inspector's structured status rows from the plant's
        CURRENT state — no side effects (no trait reveal, no anther
        check). Split out of _on_inspect_unified so passively refreshing
        the inspector (e.g. when the player selects a different plant
        while it's open) doesn't also silently reveal a new trait or run
        the daily anther check, the way the explicit "Inspect" action does.
        """
        rows = []

        # Emasculate / Pollinate: per flower, in the flower list below
        # the header (see _build_flower_panel).

        # _apply_pollen requires stage == 5 EXACTLY (not >= 5 — a plant
        # past flowering can't be pollinated at all, not just "not yet")
        # and garden.phase in (morning, noon) — matching both here so the
        # button doesn't show and then fail when clicked.
        checked_today = getattr(plant, "last_anther_check_day", None) == self._today()
        pollen_ok = checked_today and bool(getattr(plant, "anthers_available_today", False))

        # pollen status — anthers/pollen collection remains possible past
        # flowering (see _ensure_anther_check_today), unlike "Can be
        # pollinated" above which is receiving pollen and genuinely does
        # require stage == 5 exactly. Only shown once today's check has
        # actually run — otherwise anthers_available_today could still be
        # holding yesterday's stale value.
        # (pollen availability / Collect Pollen: in the Flowers section)

        # buds / flowers: one per later pod (pods_total is the plant's
        # number of flowers; pods = flowers that set seed)
        # (buds / flowers: shown as icons in the Flowers section)

        # pods / harvest
        if getattr(plant, "stage", 0) >= 6:
            pods = int(getattr(plant, "pods_remaining", 0) or 0)
            is_emasculated = int(getattr(plant, "n_emasculated", 0) or 0) > 0

            if is_emasculated and pods == 0 and not any(
                    f.get("harvested") for f in (self._plant_flowers(plant))):
                rows.append({"text": "No pods (emasculated flowers not pollinated)",
                             "action_label": None, "action_cmd": None})
            elif getattr(plant, "stage", 0) >= 7 and pods > 0:
                rows.append({"text": f"Pods: {pods}", "action_label": "Harvest All",
                             "action_cmd": self._on_harvest_all_selected, "live": "pods"})
            elif pods > 0:
                rows.append({"text": f"Pods: {pods}", "action_label": None, "action_cmd": None,
                             "live": "pods"})
            elif pods == 0:
                rows.append({"text": "No pods", "action_label": None, "action_cmd": None})

        if len(rows) == 0 and int(getattr(plant, "stage", 0) or 0) < 6:
            # (from budding on, the Flowers section says what's going on —
            # the label just goes blank, updated in place)
            rows.append({"text": "Growing" if int(getattr(plant, "stage", 0) or 0) < 4 else "",
                         "action_label": None, "action_cmd": None, "live": "growing"})

        # Fully harvested override
        if getattr(plant, "fully_harvested", False):
            rows = [{"text": "Fully harvested — no pods remain", "action_label": None, "action_cmd": None}]

        # Prepend weak note (short, first in line)
        if getattr(plant, "is_weak", False):
            rows.insert(0, {"text": "⚠ Weak plant", "action_label": None, "action_cmd": None})
        if getattr(plant, "fruit_fails", False) and int(getattr(plant, "stage", 0) or 0) >= 6:
            rows.insert(0, {"text": "⚠ Set no fruit — the flowers dropped", "action_label": None, "action_cmd": None})

        return rows

    def _compute_inspector_sig(self, idx, plant):
        """
        Shared signature computation used by _refresh_inspector_if_open
        (to decide whether a rebuild is needed) and by smooth in-place
        updates (to keep the cache in sync after a surgical update, so a
        later refresh doesn't see stale-vs-real state and force an
        unnecessary rebuild right after).

        health/water deliberately NOT included — they change on
        essentially every simulation tick, and were previously causing a
        full inspector rebuild (visibly flashing the whole window) for
        every single point of fluctuation. Those two are now handled by
        a separate, lightweight in-place label update instead — see
        _update_inspector_health_water — called unconditionally whenever
        the inspector is open, independently of whether this signature
        changed enough to warrant a full rebuild for anything else.
        """
        if plant is None:
            return ("none",)
        try:
            # Only a different plant rebuilds the window; everything else
            # in it (stage, flowers, pods, traits, counts) changes in place
            # — see _open_plant_inspector / self._insp_live.
            return (idx, getattr(plant, "id", None), bool(getattr(plant, "alive", True)))
        except Exception:
            return None

    def _refresh_inspector_if_open(self):
        """
        If the plant inspector is currently open, refresh it to reflect
        whatever's selected right now — called whenever selection changes
        (see _render_selection_panel) so switching plants while it's open
        updates it instantly, without needing to close and reopen it.

        Selecting a NEW plant while the inspector is open behaves like
        pressing Inspect directly on it — same trait-reveal roll, same
        daily anther/pollen-availability check — so pollen discovery still
        happens naturally while browsing plants with the window open,
        rather than the window just passively mirroring whatever state
        already happened to exist. This is gated to fire only once per
        actual SELECTION CHANGE (see _inspector_last_selected_idx below),
        not on every render_all() tick the same plant stays selected —
        render_all() (and this) can run several times a second during
        active simulation, and reveal_trait() has no per-day throttle the
        way the anther check does, so calling it unconditionally on every
        tick would burn through every trait almost instantly.
        """
        try:
            self._refresh_traits_only_if_open()
        except Exception:
            logging.debug("traits-only refresh failed", exc_info=True)
        if getattr(self, "_suppress_inspector_refresh", False):
            # Set around calls like _on_harvest_selected(), which trigger
            # their own internal render_all() — without this, that
            # internal call could sneak in a full rebuild in the middle of
            # a caller's own controlled update sequence (e.g. a smooth
            # in-place pod removal), corrupting it (removing a second pod
            # cell on top of an already-rebuilt, already-one-shorter row).
            return
        try:
            win = getattr(self, "_inspector_win", None)
            if win is None or not win.winfo_exists():
                return
        except Exception:
            return

        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None
        if plant is not None and not getattr(plant, "alive", True):
            plant = None

        _unset = object()
        if plant is not None and idx != getattr(self, "_inspector_last_selected_idx", _unset):
            try:
                plant.reveal_trait()
                self._sel_traits_sig = None
            except Exception:
                pass
            try:
                self._ensure_anther_check_today(plant)
            except Exception:
                pass
        self._inspector_last_selected_idx = idx

        # Health/water are updated in-place here, unconditionally,
        # regardless of whether anything else below triggers a full
        # rebuild — deliberately excluded from the signature check just
        # below (see _compute_inspector_sig's docstring) specifically so
        # their near-constant fluctuation doesn't force one. If a full
        # rebuild DOES happen for some other reason, _open_plant_inspector
        # recreates these labels fresh anyway, so this update is harmless
        # either way, not just when a rebuild is skipped.
        self._update_inspector_health_water(plant)
        self._update_inspector_live_counts(plant)
        self._update_inspector_growth_bits(plant)
        if plant is not None and getattr(self, "_inspector_last_sig", (None, None))[1:2] == (getattr(plant, "id", None),):
            for fn in list(getattr(self, "_insp_live", None) or []):
                try:
                    fn()
                except Exception:
                    logging.debug("inspector live update failed", exc_info=True)

        sig = self._compute_inspector_sig(idx, plant)

        if sig is not None and sig == getattr(self, "_inspector_last_sig", None):
            return
        self._inspector_last_sig = sig

        if plant is None:
            self._open_plant_inspector(None, [])
        else:
            rows = self._build_inspector_status_rows(plant)
            self._open_plant_inspector(plant, rows)

    def _flower_trait_icon_path(self, plant, k, v, revealed=None):
        """Discovered-trait picture for flower colour / position: buds while
        the plant is budding (stage < 5), flowers from flowering on."""
        revealed = revealed if revealed is not None else (getattr(plant, "revealed_traits", {}) or {})
        budding = int(getattr(plant, "stage", 0) or 0) < 5
        path = None
        if k == "flower_position":
            col = revealed.get("flower_color") or getattr(plant, "traits", {}).get("flower_color")
            if v and col:
                if budding:
                    path = budding_icon_path_hi(v, col)
                if not path:
                    path = flower_icon_path_hi(v, col)
        elif k == "flower_color" and budding and v:
            for nm in (f"bud_{str(v).lower()}.png", f"bud_{str(v).lower()}_64.png"):
                bp = os.path.join(ICONS_DIR, nm)
                if os.path.exists(bp):
                    path = bp
                    break
        if not path:
            path = trait_icon_path(k, v)
        return path

    def _update_inspector_growth_bits(self, plant):
        """In place, while the Inspect window stays open: the Flowers row,
        the Stage line, bud -> flower trait pictures and the plant picture."""
        if plant is None:
            return
        live = getattr(self, "_flower_panel_live", None)
        if live and live[0] == getattr(plant, "id", None):
            try:
                live[1]()
            except Exception:
                logging.debug("flower panel update failed", exc_info=True)
        lbl = getattr(self, "_inspector_stage_label", None)
        try:
            if lbl is not None and lbl.winfo_exists():
                st = getattr(plant, "stage", None)
                txt = f"Stage: {STAGE_NAMES.get(st, f'Stage {st}')}"
                if lbl.cget("text") != txt:
                    lbl.configure(text=txt)
        except Exception:
            pass
        for i, (tl, k, v, old) in enumerate(list(getattr(self, "_inspector_flower_trait_lbls", None) or [])):
            try:
                if not tl.winfo_exists():
                    continue
                path = self._flower_trait_icon_path(plant, k, v)
                if path and path != old:
                    img = safe_image(path)
                    tl.configure(image=img)
                    tl.image = img
                    self._inspector_flower_trait_lbls[i] = (tl, k, v, path)
            except Exception:
                pass
        por = getattr(self, "_inspector_portrait", None)
        try:
            if por and por[0].winfo_exists() and getattr(plant, "_icon_key", None) != por[1]:
                ph = self._inspect_portrait_photo(plant)
                if ph is not None:
                    por[0].configure(image=ph)
                    por[0].image = ph
                self._inspector_portrait = (por[0], getattr(plant, "_icon_key", None))
        except Exception:
            pass

    def _update_inspector_live_counts(self, plant):
        """Pods and buds/flowers numbers in the open inspector, changed in
        place like Health/Water (no rebuild, no flashing). A rebuild still
        happens when a row appears or goes away (e.g. last pod harvested)."""
        labels = getattr(self, "_inspector_live_labels", None)
        if not labels or plant is None:
            return
        try:
            rows = self._build_inspector_status_rows(plant)
        except Exception:
            return
        for r in rows:
            key = r.get("live")
            lbl = labels.get(key) if key else None
            if lbl is None:
                continue
            try:
                if lbl.winfo_exists() and lbl.cget("text") != r["text"]:
                    lbl.configure(text=r["text"])
            except Exception:
                pass

    def _update_inspector_health_water(self, plant):
        """
        Reconfigures the inspector's Health/Water labels' text and color
        in place, without touching anything else in the window — see
        _refresh_inspector_if_open, which calls this unconditionally,
        every time, specifically because these two values change on
        nearly every simulation tick, and previously forced a full
        inspector rebuild (visibly flashing the whole window) for every
        single point of fluctuation. Same color thresholds as
        _open_plant_inspector's own initial creation of these labels —
        kept in sync deliberately, not derived from a shared helper, so
        double-check both places if these thresholds ever change.
        """
        health_lbl = getattr(self, "_inspector_health_label", None)
        water_lbl = getattr(self, "_inspector_water_label", None)
        if health_lbl is None and water_lbl is None:
            return
        try:
            if not health_lbl.winfo_exists():
                return
        except Exception:
            return

        health = getattr(plant, "health", None) if plant is not None else None
        water = getattr(plant, "water", None) if plant is not None else None

        try:
            if health_lbl is not None and health is not None:
                h_color = "#c0392b" if health < 30 else ("#b8860b" if health < 60 else "#2e7d32")
                health_lbl.configure(text=f"Health: {int(health)}%", fg=h_color)
        except Exception:
            pass

        try:
            if water_lbl is not None and water is not None:
                w = float(water)
                if w < 20 or w > 95:
                    w_color, w_note = "#c0392b", "  ⚠ CRITICAL"
                elif w < 30 or w > 85:
                    w_color, w_note = "#b8860b", "  ⚠ low/high"
                else:
                    w_color, w_note = "#2e7d32", ""
                water_lbl.configure(text=f"Water: {int(w)}%{w_note}", fg=w_color)
        except Exception:
            pass

    # Trait icon order used by the plant inspector's bottom row — every
    # trait shown in one line, revealed or not. seed_color is deliberately
    # NOT here — it's handled separately (see _open_plant_inspector),
    # split into the always-known "seed this plant grew from" on the far
    # left and the harvested-seed-color tally on the far right, since
    # neither is a simple single revealed-or-not value like these are.
    _INSPECTOR_TRAIT_ORDER = ("plant_height", "flower_position", "flower_color",
                              "pod_shape", "pod_color", "seed_shape")

    def _build_wildlife_table(self, parent, plant, BG):
        """Compact table of every garden visitor — garden-size picture,
        name, months it comes, and how often it visited `plant`. Used as
        the fold-out panel at the bottom of the plant inspector."""
        INK = "#3b2a1a"
        MUTED = "#6b5a44"
        wl = getattr(self, "wildlife", None)
        pools = getattr(wl, "_pools", {}) if wl is not None else {}
        try:
            import wildlife as _wl
            defs = {d[0]: d for d in _wl.CREATURE_DEFS}
        except Exception:
            defs = {}
        pvis = self._plant_visits(plant)

        def _months(kind):
            d = defs.get(kind)
            if not d:
                return ""
            m = sorted(d[4])
            return f"{self._MONTH_ABBR[m[0] - 1]}\u2013{self._MONTH_ABBR[m[-1] - 1]}"

        def _name(label, kind):
            base = label or ""
            for pre in ("butterfly", "bruchus_pisi", "bee"):
                if base.lower().startswith(pre):
                    base = base[len(pre):]
                    break
            base = base.strip("_- ").replace("_", " ").strip()
            if kind == "bee":
                return "Honey bee"
            if kind == "bruchus":
                return "Pea weevil"
            if not base or base.isdigit():
                return f"Butterfly {base}".strip()
            return base.title()

        ids = self._load_species_ids()
        _generic = {"butterfly": "Butterfly", "bee": "Bee", "bruchus": "Beetle"}

        def _aspect(v):
            try:
                import wildlife as _wl
                return (10 if _wl._is_top_view(v) else 0) + _wl._visible_aspect(v._refs[0])
            except Exception:
                return 0

        # One row per species: several pictures of the same butterfly (open
        # and folded wings) share a row; the open-winged one is shown.
        rows = []          # (kind, picture variant, species key)
        by_species = {}
        for kind in ("butterfly", "bee", "bruchus"):
            for v in (pools.get(kind) or []):
                sp = self._species_for_variant(kind, v)
                if sp is None:
                    rows.append((kind, v, None))
                elif sp not in by_species:
                    by_species[sp] = len(rows)
                    rows.append((kind, v, sp))
                elif kind == "butterfly" and _aspect(v) > _aspect(rows[by_species[sp]][1]):
                    rows[by_species[sp]] = (kind, v, sp)
        visits_by_species = {}
        for k, n in pvis.items():
            sp = self._visit_key_species(k)
            visits_by_species[sp or k] = visits_by_species.get(sp or k, 0) + int(n)

        frame = tk.Frame(parent, bg=BG)
        total = sum(pvis.values())
        tk.Label(frame, text=(f"Visitors \u2014 {total} visit{'s' if total != 1 else ''} "
                              f"to plant #{getattr(plant, 'id', '?')}"),
                 font=("Segoe UI", 14, "bold"), bg=BG, fg=INK).pack(anchor="w")
        tbl = tk.Frame(frame, bg=BG)
        tbl.pack(anchor="w", pady=(4, 0))
        HF = ("Segoe UI", 13, "bold")
        F = ("Segoe UI", 13)          # same size as the other inspector sections
        PER_COL = 4                    # rows per block; blocks sit side by side
        n_blocks = max(1, (len(rows) + PER_COL - 1) // PER_COL)
        for b in range(n_blocks):
            if b:
                tk.Frame(tbl, width=1, bg="#c8c0ac").grid(
                    row=0, column=b * 6 - 1, rowspan=PER_COL + 1, sticky="ns", padx=(4, 18))
            for c, h in enumerate(("", "Visitor", "Species identification", "Season", "Visits")):
                tk.Label(tbl, text=h, font=HF, bg=BG, fg=MUTED).grid(
                    row=0, column=b * 6 + c, sticky="w", padx=(0, 14))
        info = tk.Label(frame, text="", font=("Segoe UI", 12), bg="#FBF3D9", fg="#5a4a20",
                        wraplength=560, justify="left", padx=8, pady=6)

        def _weevil_info(e=None):
            info.configure(text=(
                "\u2691  This little beetle comes when the plants carry pods. "
                "It can carry pollen from flower to flower and, now and then, spoil "
                "a cross. You can catch it: when you see one on a plant, click it!"))
            if not info.winfo_ismapped():
                info.pack(fill="x", pady=(6, 0))
                try:
                    top = frame.winfo_toplevel()
                    top.update_idletasks()
                    top.geometry(f"{top.winfo_reqwidth()}x{top.winfo_reqheight()}")
                except Exception:
                    pass

        for idx, (kind, v, sp) in enumerate(rows):
            r = idx % PER_COL + 1
            col0 = (idx // PER_COL) * 6
            n = visits_by_species.get(sp if sp else f"{kind}:{getattr(v, 'label', '')}", 0)
            img = None
            try:
                img = v.frame(0)
            except Exception:
                pass
            cells = [
                tk.Label(tbl, image=img, bg=BG) if img is not None else tk.Label(tbl, text="", bg=BG),
                tk.Label(tbl, text=_generic.get(kind, kind.title()), font=F, bg=BG, fg=INK),
                self._species_cell(tbl, sp, ids, BG),
                tk.Label(tbl, text=_months(kind), font=F, bg=BG, fg=MUTED),
                tk.Label(tbl, text=(str(n) if n else "\u2013"),
                         font=(("Segoe UI", 13, "bold") if n else F), bg=BG,
                         fg=("#2e6b2e" if n else MUTED)),
            ]
            for c, w in enumerate(cells):
                w.grid(row=r, column=col0 + c, sticky="w", padx=(0, 14), pady=0)
            if kind == "bruchus":
                for w in (cells[0], cells[1], cells[3], cells[4]):
                    w.configure(cursor="hand2")
                    w.bind("<Button-1>", _weevil_info)
                try:
                    _attach_tooltip(cells[0], "Click to learn more")
                except Exception:
                    pass
        if not rows:
            tk.Label(tbl, text="(no pictures found)", font=("Segoe UI", 13, "italic"),
                     bg=BG, fg=MUTED).grid(row=1, column=0, columnspan=5, sticky="w")
        self._present_species = {sp for _kd, _vv, sp in rows if sp}
        return frame

    def _species_cell(self, parent, key, ids, BG):
        """The Species cell: the name the player found, or a box to type one."""
        F = ("Segoe UI", 13)
        if not key:
            return tk.Label(parent, text="", bg=BG)
        def _known(master, typed):
            """The name the player found, plus the Latin name."""
            box = tk.Frame(master, bg=BG)
            common, latin = self.SPECIES[key][:2]
            lbl = tk.Label(box, text=typed, font=("Segoe UI", 13, "bold"),
                           bg=BG, fg="#2e6b2e")
            lbl.pack(side="left")
            tk.Label(box, text=f" ({latin})", font=("Segoe UI", 13, "italic"),
                     bg=BG, fg="#6b5a44").pack(side="left")
            try:
                _attach_tooltip(lbl, f"{common} \u2014 {latin}")
            except Exception:
                pass
            return box

        if key in ids:
            return _known(parent, ids[key])
        holder = tk.Frame(parent, bg=BG)
        ent = tk.Entry(holder, width=16, font=F, bd=1, relief="solid",
                       bg="#FFFDF6", fg="#3b2a1a", insertbackground="#3b2a1a")
        ent.pack()
        drafts = getattr(self, "_species_drafts", None)
        if drafts is None:
            drafts = self._species_drafts = {}
        if drafts.get(key):
            ent.insert(0, drafts[key])     # survives an inspector refresh
        ent.bind("<KeyRelease>", lambda e: drafts.__setitem__(key, ent.get()), add="+")

        def _check(event=None, quiet=False):
            typed = ent.get().strip()
            if not typed:
                return
            if self._name_matches_species(key, typed):
                for w in holder.winfo_children():
                    w.destroy()
                _known(holder, typed).pack(anchor="w")
                drafts.pop(key, None)
                self._on_species_identified(key, typed)
            elif not quiet:
                ent.configure(bg="#F6D5CC")
                ent.after(700, lambda: ent.winfo_exists() and ent.configure(bg="#FFFDF6"))
            return "break"

        ent.bind("<Return>", _check)
        ent.bind("<KP_Enter>", _check)
        ent.bind("<FocusOut>", lambda e: _check(quiet=True))
        return holder

    def _inspector_home_pos(self, ww, wh):
        """Where a new Inspect window opens: its top left corner on the top
        left corner of the garden's first plot (kept on the screen). Falls
        back to the middle of the screen."""
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except Exception:
            sw, sh = 1920, 1080
        try:
            t = self.tiles[0]
            t.update_idletasks()
            x, y = int(t.winfo_rootx()), int(t.winfo_rooty())
            if t.winfo_ismapped() and x >= 0 and y >= 0:
                x = max(0, min(x, sw - ww))
                y = max(0, min(y, sh - wh - 48))     # room for the taskbar / dock
                return x, y
        except Exception:
            pass
        return max(0, (sw - ww) // 2), max(0, (sh - wh) // 2)

    def _let_window_go_above_inspector(self, other_win):
        """
        Let another window (Genotype Explorer, Trait Inheritance Explorer,
        ...) appear above the plant inspector, which is normally always
        on top of everything (see _open_plant_inspector) — restores the
        inspector's topmost status once `other_win` closes. Bound via
        <Destroy> on that specific window rather than overriding its own
        close handling, so this works regardless of how it actually gets
        closed (a Close button, the window's own X, Escape, ...).
        """
        insp = getattr(self, "_inspector_win", None)
        try:
            if insp is None or not insp.winfo_exists():
                insp = None
        except Exception:
            insp = None

        if insp is None:
            return

        def _yield_and_raise():
            # Turning off the inspector's topmost doesn't, by itself,
            # raise anything else above it — it only stops the inspector
            # from forcing itself back to the front. other_win still needs
            # to be explicitly lifted. Deferred (rather than done
            # immediately after construction) because windows like TIE do
            # their own maximize/positioning setup via their own delayed
            # after() calls — acting immediately here could race that and
            # get overridden by it.
            try:
                if insp.winfo_exists():
                    insp.attributes('-topmost', False)
            except Exception:
                pass
            try:
                other_win.lift()
                other_win.focus_force()
            except Exception:
                pass

        try:
            other_win.after(150, _yield_and_raise)
        except Exception:
            _yield_and_raise()

        def _restore(event=None):
            try:
                if insp.winfo_exists():
                    insp.attributes('-topmost', True)
            except Exception:
                pass

        try:
            other_win.bind("<Destroy>", _restore, add="+")
        except Exception:
            pass

    # Which Inspect-window sections are open (remembered between windows
    # and game sessions, see _inspector_sections)
    _INSPECTOR_SECTIONS = (("traits", "Traits"), ("harvest", "Harvest"),
                           ("crossing", "Crossing"), ("wildlife", "Wildlife"))

    # "Traits only": a small window with just the selected plant's traits,
    # stacked vertically, for browsing quickly through the garden. It
    # follows the selection; the arrow goes back to the full Inspect window.
    # Icons and text the same size as in the Inspect window.
    _TRAITS_ONLY_ICON = 64

    _INSPECTOR_SECTIONS_DEFAULT = {"crossing": False, "traits": True,
                                   "harvest": True, "wildlife": False}

    def _inspector_sections(self):
        # The tutorial can open the window with its own choice for a while
        # (then nothing is saved).
        ov = getattr(self, "_tut_insp_sections", None)
        if ov is not None:
            return ov
        st = getattr(self, "_insp_sections_state", None)
        if st is None:
            st = dict(self._INSPECTOR_SECTIONS_DEFAULT)
            try:
                saved = _load_display_settings().get("inspector_sections") or {}
                for k in st:
                    if k in saved:
                        st[k] = bool(saved[k])
            except Exception:
                pass
            self._insp_sections_state = st
        return st

    def _save_inspector_sections(self):
        if getattr(self, "_tut_insp_sections", None) is not None:
            return                               # the tutorial's choice, not the player's
        try:
            s = _load_display_settings()
            s["inspector_sections"] = dict(self._inspector_sections())
            _save_display_settings(s)
        except Exception:
            pass

    def _open_plant_inspector(self, plant, status_rows=None):
        """
        The Inspect window: a header (picture, number, stage, health/water,
        note) with section buttons — Crossing (flowers: emasculate,
        pollinate, collect pollen), Traits, Harvest (pods) and Wildlife —
        that fold their sections in and out (remembered for next time).

        Built once per selected plant. While it stays open everything in
        it changes in place (self._insp_live, called from
        _refresh_inspector_if_open): buds appearing and opening, stage,
        pods, traits being discovered, harvested-seed counts — the window
        is not rebuilt for those.
        """
        BG = "#f5f0e6"
        existing = getattr(self, "_inspector_win", None)
        reuse = False
        try:
            reuse = existing is not None and bool(existing.winfo_exists())
        except Exception:
            reuse = False

        if reuse:
            win = existing
            for w in win.winfo_children():
                w.destroy()
        else:
            win = tk.Toplevel(self.root)
            win.withdraw()   # hidden until fully built and positioned — see below
            self._inspector_win = win
        self._insp_live = []
        self._flower_panel_live = None
        self._inspector_flower_trait_lbls = []
        self._inspector_live_labels = {}

        try:
            win.attributes('-topmost', True)
        except Exception:
            pass

        if plant is None:
            win.title("Inspect")
            win.configure(bg=BG)
            win.resizable(False, False)
            msg_frame = tk.Frame(win, bg=BG)
            msg_frame.place(relx=0.5, rely=0.5, anchor="center")
            tk.Label(msg_frame, text="No plant selected", font=("Segoe UI", 18, "italic"),
                     bg=BG, fg="#999").pack()
            if not reuse:
                win.update_idletasks()
                ww, wh = 420, 220
                x, y = self._inspector_home_pos(ww, wh)
                win.geometry(f"{ww}x{wh}+{x}+{y}")
                win.deiconify()
            return

        pid = getattr(plant, "id", "?")
        gen = getattr(plant, "generation", "?")
        win.title(f"Inspect — Plant #{pid}")
        win.configure(bg=BG)
        win.resizable(False, False)

        def _fit_window():
            try:
                win.update_idletasks()
                win.geometry(f"{win.winfo_reqwidth()}x{win.winfo_reqheight()}")
            except Exception:
                pass

        def _run_action(cmd):
            cmd()
            self._refresh_inspector_if_open()

        def _run_action_close_first(cmd):
            # Dialogs (emasculation, pollination, anthers): the inspector
            # steps aside (hidden, not closed) and comes back afterwards
            # exactly as it was — updated in place, not rebuilt.
            try:
                if getattr(self, "_inspector_win", None) is not None:
                    # remembered, so it comes back at exactly the same place
                    self._inspector_geom = self._inspector_win.geometry()
                    self._inspector_win.withdraw()
            except Exception:
                pass
            self._reopen_inspector_after_dialog = True
            cmd()
            self.root.after(800, self._inspector_dialog_watch)

        # ================= header =================
        header = tk.Frame(win, bg=BG, padx=16, pady=10)
        header.pack(fill="x")

        portrait_img = self._inspect_portrait_photo(plant)
        if portrait_img is not None:
            portrait = tk.Label(header, image=portrait_img, bg=BG)
            portrait.image = portrait_img
            portrait.pack(side="left", padx=(0, 12))
            self._inspector_portrait = (portrait, getattr(plant, "_icon_key", None))

        id_box = tk.Frame(header, bg=BG)
        id_box.pack(side="left", anchor="w", padx=(0, 20))
        title_row = tk.Frame(id_box, bg=BG)
        title_row.pack(anchor="w")
        tk.Label(title_row, text=f"Plant #{pid}", font=("Segoe UI", 14, "bold"),
                 bg=BG).pack(side="left")
        tk.Label(title_row, text=f"   Generation: {gen}", font=("Segoe UI", 14),
                 bg=BG, fg="#555").pack(side="left")
        stage_name = STAGE_NAMES.get(getattr(plant, "stage", None), f"Stage {getattr(plant, 'stage', '?')}")
        self._inspector_stage_label = tk.Label(id_box, text=f"Stage: {stage_name}",
                                               font=("Segoe UI", 14, "bold"), bg=BG, fg="#333")
        self._inspector_stage_label.pack(anchor="w")

        # emasculated / pollinated counts and plant status (live)
        tags_row = tk.Frame(id_box, bg=BG)
        tags_row.pack(anchor="w")
        lbl_e = tk.Label(tags_row, text="", font=("Segoe UI", 14, "bold"), bg=BG, fg="#6a4fb3")
        lbl_p = tk.Label(tags_row, text="", font=("Segoe UI", 14, "bold"), bg=BG, fg="#2e7d32")
        lbl_s = tk.Label(id_box, text="", font=("Segoe UI", 13), bg=BG, fg="#8a5a20")

        def _upd_tags():
            try:
                fl = plant.ensure_flowers()
            except Exception:
                fl = []
            n_e = sum(1 for f in fl if f.get("emasc"))
            n_p = sum(1 for f in fl if f.get("pollen"))
            for lbl, txt, padx in ((lbl_e, f"✓ Emasculated: {n_e} of {len(fl)} flowers" if n_e else "", (0, 12)),
                                   (lbl_p, f"✓ Pollinated: {n_p}" if n_p else "", 0)):
                if txt:
                    if lbl.cget("text") != txt:
                        lbl.configure(text=txt)
                    if not lbl.winfo_ismapped():
                        lbl.pack(side="left", padx=padx)
                elif lbl.winfo_ismapped():
                    lbl.pack_forget()
            bits = []
            if getattr(plant, "is_weak", False):
                bits.append("⚠ Weak plant")
            if getattr(plant, "fruit_fails", False) and int(getattr(plant, "stage", 0) or 0) >= 6:
                bits.append("⚠ Set no fruit — the flowers dropped")
            if getattr(plant, "fully_harvested", False):
                bits.append("Fully harvested — no pods remain")
            elif int(getattr(plant, "stage", 0) or 0) < 4:
                bits.append("Growing")
            txt = "   ·   ".join(bits)
            if lbl_s.cget("text") != txt:
                lbl_s.configure(text=txt)
            if txt and not lbl_s.winfo_ismapped():
                lbl_s.pack(anchor="w", before=hw_row)
            elif not txt and lbl_s.winfo_ismapped():
                lbl_s.pack_forget()

        # health / water (updated in place by _update_inspector_health_water)
        health = getattr(plant, "health", None)
        water = getattr(plant, "water", None)
        hw_row = tk.Frame(id_box, bg=BG)
        hw_row.pack(anchor="w", pady=(4, 0))
        self._inspector_health_label = None
        self._inspector_water_label = None
        if health is not None:
            h_color = "#c0392b" if health < 30 else ("#b8860b" if health < 60 else "#2e7d32")
            self._inspector_health_label = tk.Label(
                hw_row, text=f"Health: {int(health)}%", font=("Segoe UI", 14, "bold"),
                bg=BG, fg=h_color)
            self._inspector_health_label.pack(side="left", padx=(0, 16))
        if water is not None:
            w = float(water)
            if w < 20 or w > 95:
                w_color, w_note = "#c0392b", "  ⚠ CRITICAL"
            elif w < 30 or w > 85:
                w_color, w_note = "#b8860b", "  ⚠ low/high"
            else:
                w_color, w_note = "#2e7d32", ""
            self._inspector_water_label = tk.Label(
                hw_row, text=f"Water: {int(w)}%{w_note}", font=("Segoe UI", 14, "bold"),
                bg=BG, fg=w_color)
            self._inspector_water_label.pack(side="left")
        _upd_tags()
        self._insp_live.append(_upd_tags)

        # right: the note
        right = tk.Frame(header, bg=BG)
        right.pack(side="right", anchor="ne", padx=(12, 0))
        bar = tk.Frame(right, bg=BG)
        bar.pack(anchor="e")
        # The section buttons get their own row on the left, under the
        # header: the window's left edge never moves, so they stay exactly
        # where they are when a section opens or closes and the window
        # changes its width.
        tabs = tk.Frame(win, bg=BG, padx=16)
        tabs.pack(fill="x", pady=(0, 2))
        sections = self._inspector_sections()
        slots, btns = {}, {}
        self._inspector_section_btns = btns      # the tutorial points at "Harvest"

        def _style_btn(key):
            on = sections.get(key, False)
            b = btns.get(key)
            if b is not None:
                b.configure(bg="#8a7a52" if on else "#e8e0cf", fg="white" if on else "#3b2a1a")

        def _toggle(key):
            sections[key] = not sections.get(key, False)
            self._save_inspector_sections()
            _show_section(key)
            _style_btn(key)
            _fit_window()

        for key, label in self._INSPECTOR_SECTIONS:
            b = tk.Label(tabs, text=label, font=("Segoe UI", 12, "bold"), padx=10, pady=4,
                         cursor="hand2", relief="flat")
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, k=key: _toggle(k))
            btns[key] = b
            _style_btn(key)

        # The note: button in the button row (right), preview box at the
        # top right. Changed in place after editing the note (no rebuild).
        # Same box as the section buttons: same font and padding, and its
        # holder is exactly as tall as they are (the ✎ sign alone can make
        # a label taller on some systems).
        note_hold = tk.Frame(tabs, bg=BG)
        note_hold.pack(side="right")
        note_btn = tk.Label(note_hold, text="✎  Make note", font=("Segoe UI", 12, "bold"),
                            padx=10, pady=4, cursor="hand2", relief="flat",
                            bg="#e8e0cf", fg="#3b2a1a")
        note_btn._is_flat_button = True          # keeps its colour (inspector theme)
        note_btn.place(x=0, y=0, relwidth=1, relheight=1)
        note_btn.bind("<Enter>", lambda e: note_btn.configure(bg="#d0c8b7"))
        note_btn.bind("<Leave>", lambda e: note_btn.configure(bg="#e8e0cf"))
        note_btn.bind("<Button-1>", lambda e, p=plant: self._edit_plant_note(p, parent=win))
        note_box = [None]

        def _size_note_btn():
            try:
                ref = btns.get("wildlife") or next(iter(btns.values()))
                note_hold.configure(width=note_btn.winfo_reqwidth(), height=ref.winfo_reqheight())
            except Exception:
                pass

        def _upd_note():
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            note_txt = self._plant_note(pid)
            try:
                note_btn.configure(text=("✎  Edit note" if note_txt else "✎  Make note"))
                _size_note_btn()
            except Exception:
                pass
            if note_box[0] is not None:
                try:
                    note_box[0].destroy()
                except Exception:
                    pass
                note_box[0] = None
            if note_txt:
                lines = [ln for ln in note_txt.splitlines() if ln.strip()] or [note_txt]
                preview = []
                for ln in lines[:2]:
                    preview.append(ln if len(ln) <= 38 else ln[:37].rstrip() + "…")
                if len(lines) > 2 and not preview[-1].endswith("…"):
                    preview[-1] += " …"
                nbox = tk.Frame(right, bg="#FBF3D9", highlightbackground="#D9A520",
                                highlightthickness=1, padx=8, pady=4, cursor="hand2")
                nbox.pack(anchor="e")
                nlbl = tk.Label(nbox, text="⚑  " + "\n".join(preview),
                                font=("Segoe UI", 11, "italic"), bg="#FBF3D9", fg="#5a4a20",
                                justify="left", cursor="hand2")
                nlbl.pack(anchor="w")
                for w_ in (nbox, nlbl):
                    w_.bind("<Button-1>", lambda e, p=plant: self._edit_plant_note(p, parent=win))
                _attach_tooltip(nlbl, "Click to read the whole note")
                note_box[0] = nbox

        _upd_note()
        self._insp_update_note = (str(pid), _upd_note)

        # ================= sections (fixed order, each in its own slot) =================
        for key, _label in self._INSPECTOR_SECTIONS:
            slot = tk.Frame(win, bg=BG)
            slot.pack(fill="x")
            slots[key] = slot
        contents = {}

        def _show_section(key):
            c = contents.get(key)
            if c is None:
                return
            if sections.get(key, False):
                c.pack(fill="x")
                if key == "wildlife":
                    self._check_popular_plant(plant)
            else:
                c.pack_forget()
                # an emptied Tk frame keeps its old size — shrink it by hand
                try:
                    slots[key].configure(height=1, width=1)
                except Exception:
                    pass

        def _section_frame(key):
            fr = tk.Frame(slots[key], bg=BG)
            tk.Frame(fr, height=1, bg="#c8c0ac").pack(fill="x", padx=16, pady=(4, 6))
            contents[key] = fr
            return fr

        # --- Crossing: the flowers ---
        try:
            self._build_flower_panel(_section_frame("crossing"), plant, BG,
                                     _run_action_close_first, _run_action)
        except Exception:
            logging.debug("Flower panel failed", exc_info=True)

        # --- Traits ---
        try:
            self._build_traits_section(_section_frame("traits"), plant, BG)
        except Exception:
            logging.debug("Traits section failed", exc_info=True)

        # --- Harvest: the pods ---
        try:
            self._build_harvest_section(_section_frame("harvest"), plant, BG, _run_action)
        except Exception:
            logging.debug("Harvest section failed", exc_info=True)

        # --- Wildlife ---
        try:
            wl = _section_frame("wildlife")
            self._build_wildlife_table(wl, plant, BG).pack(anchor="w", padx=16, pady=(0, 8))
        except Exception as e:
            logging.debug(f"Wildlife panel failed: {e}")

        for key, _label in self._INSPECTOR_SECTIONS:
            _show_section(key)

        # ================= bottom buttons =================
        bottom_row = tk.Frame(win, bg=BG)
        bottom_row.pack(pady=(8, 12))
        self._inspector_close_btn = self._make_flat_button(
            bottom_row, "Close", win.destroy, bg="#e0dccf", fg="#333333",
            font=("Segoe UI", 14, "bold"))               # the tutorial points at it
        self._inspector_close_btn.pack(side="left", padx=6)
        self._make_flat_button(bottom_row, "Genotype Explorer", self._on_genetics, bg="#e0dccf", fg="#333333",
                               font=("Segoe UI", 14, "bold")).pack(side="left", padx=6)

        def _open_tie_close_inspector_first():
            try:
                win.destroy()
            except Exception:
                pass
            self._open_tie_for_selected()

        if not getattr(self, "_tutorial_active", False):
            self._make_flat_button(bottom_row, "TIE", _open_tie_close_inspector_first,
                                   bg="#e0dccf", fg="#333333",
                                   font=("Segoe UI", 14, "bold")).pack(side="left", padx=6)

        def _open_law_wizard_close_inspector_first():
            try:
                win.destroy()
            except Exception:
                pass
            self._test_mendelian_laws_now()

        if not getattr(self, "_tutorial_active", False):
            self._make_flat_button(bottom_row, "Unlock Laws", _open_law_wizard_close_inspector_first,
                                   bg="#e0dccf", fg="#333333",
                                   font=("Segoe UI", 14, "bold")).pack(side="left", padx=6)

        self._insp_fit = _fit_window
        try:
            self._inspector_last_sig = self._compute_inspector_sig(getattr(self, "selected_index", None), plant)
        except Exception:
            pass
        win.update_idletasks()
        ww = win.winfo_reqwidth()
        wh = win.winfo_reqheight()
        if reuse:
            win.geometry(f"{ww}x{wh}")
        else:
            x, y = self._inspector_home_pos(ww, wh)
            win.geometry(f"{ww}x{wh}+{x}+{y}")
            win.deiconify()

    def _build_traits_section(self, parent, plant, BG):
        """Planted seed | discovered traits | harvested seeds — the
        discovered cells and the seed counts update in place."""
        bar = tk.Frame(parent, bg=BG, padx=16)
        bar.pack(fill="x")
        self._make_flat_button(bar, "Show traits only", self._open_traits_only,
                               bg="#e8e0cf", fg="#3b2a1a",
                               font=("Segoe UI", 11, "bold")).pack(side="right")
        row = tk.Frame(parent, bg=BG, padx=16, pady=4)
        row.pack(fill="x")

        def _vsep():
            tk.Frame(row, width=2, bg="#c8c0ac").pack(side="left", fill="y", padx=10)

        own_seed_color = (getattr(plant, "traits", {}) or {}).get("seed_color")
        own_cell = tk.Frame(row, bg=BG)
        own_cell.pack(side="left", padx=6)
        tk.Label(own_cell, text="planted seed", font=("Segoe UI", 14), bg=BG, fg="#999").pack()
        own_slot = tk.Frame(own_cell, bg=BG, height=64, width=64)
        own_slot.pack_propagate(False)
        own_slot.pack()
        if own_seed_color:
            try:
                p = trait_icon_path("seed_color", own_seed_color)
                img = safe_image(p) if p else None
            except Exception:
                img = None
            if img:
                ic = tk.Label(own_slot, image=img, bg=BG)
                ic.image = img
                ic.place(relx=0.5, rely=0.5, anchor="center")
            tk.Label(own_cell, text=str(own_seed_color), font=("Segoe UI", 14), bg=BG, fg="#555").pack()
        else:
            tk.Label(own_slot, text="?", font=("Segoe UI", 34, "bold"),
                     bg=BG, fg="#888888").place(relx=0.5, rely=0.5, anchor="center")
        _vsep()

        group = tk.Frame(row, bg=BG)
        group.pack(side="left")
        tk.Label(group, text="discovered traits", font=("Segoe UI", 14), bg=BG, fg="#999").pack()
        drow = tk.Frame(group, bg=BG)
        drow.pack()
        cells = {}
        for k in self._INSPECTOR_TRAIT_ORDER:
            cell = tk.Frame(drow, bg=BG)
            cell.pack(side="left", padx=6)
            slot = tk.Frame(cell, bg=BG, height=64, width=64)
            slot.pack_propagate(False)
            slot.pack()
            ic = tk.Label(slot, bg=BG)
            ic.place(relx=0.5, rely=0.5, anchor="center")
            cap = tk.Label(cell, text="", font=("Segoe UI", 14), bg=BG)
            cap.pack()
            cells[k] = (ic, cap, [None])

        def _icon_path(k, v, revealed):
            path = None
            try:
                if k in ("flower_position", "flower_color"):
                    path = self._flower_trait_icon_path(plant, k, v, revealed)
                elif k == "pod_shape":
                    col = revealed.get("pod_color")
                    if v and col:
                        path = pod_shape_icon_path(v, col)
                elif k == "pod_color":
                    shp = (revealed.get("pod_shape")
                           or (getattr(plant, "traits", {}) or {}).get("pod_shape"))
                    if v and shp:
                        path = pod_shape_icon_path(shp, v)
                if not path:
                    path = trait_icon_path(k, v)
            except Exception:
                path = None
            return path

        def _upd_traits():
            revealed = getattr(plant, "revealed_traits", {}) or {}
            for k, (ic, cap, last) in cells.items():
                if k in revealed:
                    v = revealed[k]
                    path = _icon_path(k, v, revealed)
                    key = ("v", v, path)
                    if last[0] != key:
                        img = None
                        try:
                            img = safe_image(path) if path else None
                        except Exception:
                            img = None
                        ic.configure(image=img or "", text="" if img else "?",
                                     font=("Segoe UI", 14), fg="#555")
                        ic.image = img
                        cap.configure(text=str(v), fg="#555")
                        last[0] = key
                else:
                    if last[0] != "?":
                        ic.configure(image="", text="?", font=("Segoe UI", 34, "bold"), fg="#888888")
                        ic.image = None
                        cap.configure(text=k.replace("_", " "), fg="#999")
                        last[0] = "?"
        _upd_traits()
        self._insp_live.append(_upd_traits)
        _vsep()

        tg = tk.Frame(row, bg=BG)
        tg.pack(side="left", padx=6)
        tk.Label(tg, text="harvested seeds", font=("Segoe UI", 14), bg=BG, fg="#999").pack()
        pair = tk.Frame(tg, bg=BG)
        pair.pack()
        self._inspector_tally_labels = {}
        for color in ("yellow", "green"):
            one = tk.Frame(pair, bg=BG)
            one.pack(side="left", padx=(0, 14))
            irow = tk.Frame(one, bg=BG)
            irow.pack()
            try:
                p = trait_icon_path("seed_color", color)
                img = safe_image(p) if p else None
            except Exception:
                img = None
            if img:
                ic = tk.Label(irow, image=img, bg=BG)
                ic.image = img
                ic.pack(side="left")
            cnt = tk.Label(irow, text="n = 0", font=("Segoe UI", 14), bg=BG, fg="#555",
                           width=8, anchor="w")
            cnt.pack(side="left", padx=(4, 0))
            irow.update_idletasks()
            extra = max(0, 64 - irow.winfo_reqheight())
            irow.pack_configure(pady=(extra // 2, extra - extra // 2))
            self._inspector_tally_labels[color] = cnt
            tk.Label(one, text=color, font=("Segoe UI", 14), bg=BG, fg="#555").pack()

        def _upd_tally():
            counts = getattr(plant, "_seed_color_counts", None) or {}
            for color, lbl in (getattr(self, "_inspector_tally_labels", None) or {}).items():
                try:
                    t = f"n = {counts.get(color, 0)}"
                    if lbl.winfo_exists() and lbl.cget("text") != t:
                        lbl.configure(text=t)
                except Exception:
                    pass
        _upd_tally()
        self._insp_live.append(_upd_tally)

    def _open_traits_only(self):
        pos = None
        try:
            w = getattr(self, "_inspector_win", None)
            if w is not None and w.winfo_exists():
                pos = (w.winfo_rootx(), w.winfo_rooty())
                w.destroy()
            self._inspector_win = None
        except Exception:
            pass
        BG = "#f5f0e6"
        tw = getattr(self, "_traits_only_win", None)
        try:
            if tw is not None and tw.winfo_exists():
                tw.lift()
                return
        except Exception:
            pass
        tw = tk.Toplevel(self.root)
        tw.withdraw()
        tw.title("Traits")
        tw.configure(bg=BG)
        tw.resizable(False, False)
        try:
            tw.attributes("-topmost", True)
        except Exception:
            pass
        self._traits_only_win = tw
        self._traits_only_sig = None
        top = tk.Frame(tw, bg=BG, padx=10, pady=6)
        top.pack(fill="x")

        def _back():
            try:
                self._traits_only_pos = (tw.winfo_rootx(), tw.winfo_rooty())
                tw.destroy()
            except Exception:
                pass
            self._traits_only_win = None
            self._on_inspect_unified()

        # "Return to" + the magnifier of the Inspect button
        mag = None
        try:
            _ip = os.path.join(ICONS_DIR, "inspect.png")
            if os.path.exists(_ip):
                _im = Image.open(_ip).convert("RGBA")
                _im.thumbnail((28, 28), Image.LANCZOS)
                mag = ImageTk.PhotoImage(_im)
        except Exception:
            mag = None
        back = tk.Label(top, text="Return to" + ("" if mag else "  \U0001F50D"), image=mag or "",
                        compound="right", font=("Segoe UI", 12, "bold"), bg="#e8e0cf",
                        fg="#3b2a1a", padx=8, pady=2, cursor="hand2")
        back.image = mag
        back.pack(side="left")
        # on mouse-up, so the click can't fall through to the garden
        back.bind("<ButtonRelease-1>", lambda e: _back())
        _attach_tooltip(back, "Back to the full Inspect window")
        self._traits_only_title = tk.Label(top, text="", font=("Segoe UI", 14, "bold"), bg=BG)
        tk.Frame(tw, width=360, height=1, bg=BG).pack()     # a comfortable minimum width
        self._traits_only_title.pack(side="left", padx=(10, 0))
        self._traits_only_body = tk.Frame(tw, bg=BG, padx=10, pady=4)
        self._traits_only_body.pack(fill="both", expand=True)
        def _close():
            try:
                self._traits_only_pos = (tw.winfo_rootx(), tw.winfo_rooty())
            except Exception:
                pass
            tw.destroy()
            self._traits_only_win = None
        tw.protocol("WM_DELETE_WINDOW", _close)
        self._refresh_traits_only_if_open(force=True)
        tw.update_idletasks()
        # Where it was last time; the first time it snaps to the right of
        # the garden: its right edge just past the last plot, its top level
        # with the top of the garden.
        pos = getattr(self, "_traits_only_pos", None)
        if pos is None:
            try:
                plots = [t for t in self._all_plot_tiles() if t.winfo_ismapped()]
                right = max(t.winfo_rootx() + t.winfo_width() for t in plots)
                top = min(t.winfo_rooty() for t in plots)
                pos = (max(0, right + 12 - tw.winfo_reqwidth()), max(0, top))
            except Exception:
                pos = (max(0, (tw.winfo_screenwidth() - tw.winfo_reqwidth()) // 2), 120)
        tw.geometry(f"+{pos[0]}+{pos[1]}")
        tw.deiconify()

    def _traits_only_harvest_buttons(self, parent, plant, BG):
        """Harvest | All next to the pods, like Water | All in the garden:
        one ripe pod, or all ripe pods of the selected plant."""
        box = tk.Frame(parent, bg="#e8e0cf")
        box.pack(side="right", padx=(6, 0))
        img = None
        try:
            hp = os.path.join(ICONS_DIR, "harvest.png")
            if os.path.exists(hp):
                im = Image.open(hp).convert("RGBA")
                im.thumbnail((30, 30), Image.LANCZOS)
                img = ImageTk.PhotoImage(im)
        except Exception:
            img = None
        try:
            ripe = int(plant.ripe_pods())
        except Exception:
            ripe = int(getattr(plant, "pods_remaining", 0) or 0) if int(getattr(plant, "stage", 0) or 0) >= 7 else 0
        fg = "#3b2a1a" if ripe else "#a09a8c"

        def one():
            self._suppress_inspector_refresh = True
            try:
                rec = self._on_harvest_selected()
            finally:
                self._suppress_inspector_refresh = False
            try:
                self._tally_seed_colors_from_pod_record(plant, rec)
            except Exception:
                pass
            self._refresh_inspector_if_open()

        def all_():
            self._on_harvest_all_selected()
            self._refresh_inspector_if_open()

        b1 = tk.Label(box, image=img or "", text="" if img else "Harvest", bg="#e8e0cf", fg=fg,
                      font=("Segoe UI", 12, "bold"), padx=8, pady=4, cursor="hand2")
        b1.image = img
        b1.pack(side="left")
        tk.Frame(box, width=1, bg="#9A9A9A").pack(side="left", fill="y", pady=3)
        b2 = tk.Label(box, text="All", bg="#e8e0cf", fg=fg, font=("Segoe UI", 12, "bold"),
                      padx=8, pady=4, cursor="hand2")
        b2.pack(side="left")
        b1.bind("<ButtonRelease-1>", lambda e: one())
        b2.bind("<ButtonRelease-1>", lambda e: all_())
        def _tip():
            try:
                n = int(plant.ripe_pods())
            except Exception:
                n = int(getattr(plant, "pods_remaining", 0) or 0) if int(getattr(plant, "stage", 0) or 0) >= 7 else 0
            return f"Harvest one ripe pod ({n} ripe)"
        _attach_tooltip(b1, _tip)        # worked out when hovering, so always current
        _attach_tooltip(b2, "Harvest all ripe pods")

    def _traits_only_icon(self, path, faded=False):
        cache = self.__dict__.setdefault("_traits_only_icons", {})
        key = (path, faded)
        if key in cache:
            return cache[key]
        ph = None
        try:
            im = Image.open(path).convert("RGBA")
            im.thumbnail((self._TRAITS_ONLY_ICON, self._TRAITS_ONLY_ICON), Image.LANCZOS)
            ph = ImageTk.PhotoImage(im)
        except Exception:
            ph = None
        cache[key] = ph
        return ph

    def _refresh_traits_only_if_open(self, force=False):
        tw = getattr(self, "_traits_only_win", None)
        if tw is None:
            return
        try:
            if not tw.winfo_exists():
                self._traits_only_win = None
                return
        except Exception:
            return
        idx = getattr(self, "selected_index", None)
        plant = self.tiles[idx].plant if (idx is not None and 0 <= idx < len(self.tiles)) else None
        if plant is not None and not getattr(plant, "alive", True):
            plant = None
        # a newly selected plant is inspected (one trait may be discovered,
        # like in the full Inspect window)
        if plant is not None and idx != getattr(self, "_traits_only_last_idx", object()):
            try:
                plant.reveal_trait()
                self._sel_traits_sig = None
            except Exception:
                pass
        self._traits_only_last_idx = idx
        revealed = dict(getattr(plant, "revealed_traits", {}) or {}) if plant else {}
        counts = dict(getattr(plant, "_seed_color_counts", None) or {}) if plant else {}
        try:
            ripe_n = int(plant.ripe_pods()) if plant else 0
        except Exception:
            ripe_n = 0
        sig = (getattr(plant, "id", None), tuple(sorted(revealed.items())),
               tuple(sorted(counts.items())), int(getattr(plant, "stage", 0) or 0) < 5 if plant else None,
               ripe_n)
        if not force and sig == getattr(self, "_traits_only_sig", None):
            return
        self._traits_only_sig = sig
        BG = "#f5f0e6"
        body = self._traits_only_body
        for w in body.winfo_children():
            w.destroy()
        if plant is None:
            # keep the window's size; the message sits in its middle
            self._traits_only_title.configure(text="")
            tk.Label(body, text="No plant selected", font=("Segoe UI", 14, "italic"),
                     bg=BG, fg="#999").place(relx=0.5, rely=0.5, anchor="center")
            return
        self._traits_only_title.configure(text=f"#{getattr(plant, 'id', '?')}   {getattr(plant, 'generation', '')}")

        def row(path, value, caption, unknown=False):
            r = tk.Frame(body, bg=BG)
            r.pack(anchor="w", fill="x", pady=1)
            slot = tk.Frame(r, bg=BG, width=self._TRAITS_ONLY_ICON + 4, height=self._TRAITS_ONLY_ICON + 2)
            slot.pack_propagate(False)
            slot.pack(side="left")
            img = self._traits_only_icon(path) if (path and not unknown) else None
            if img:
                tk.Label(slot, image=img, bg=BG).place(relx=0.5, rely=0.5, anchor="center")
            else:
                tk.Label(slot, text="?", font=("Segoe UI", 30, "bold"), bg=BG,
                         fg="#888").place(relx=0.5, rely=0.5, anchor="center")
            txt = tk.Frame(r, bg=BG)
            txt.pack(side="left", padx=(8, 12))
            tk.Label(txt, text=caption, font=("Segoe UI", 12), bg=BG, fg="#999").pack(anchor="w")
            tk.Label(txt, text=value, font=("Segoe UI", 14, "bold" if not unknown else "normal"),
                     bg=BG, fg="#444" if not unknown else "#999").pack(anchor="w")
            return r

        own = (getattr(plant, "traits", {}) or {}).get("seed_color")
        row(trait_icon_path("seed_color", own) if own else None, str(own or "?"), "planted seed",
            unknown=not own)
        tk.Frame(body, height=1, bg="#c8c0ac").pack(fill="x", pady=3)
        for k in self._INSPECTOR_TRAIT_ORDER:
            name = k.replace("_", " ")
            if k == "pod_color":
                continue                      # shown together with the pod shape
            if k == "pod_shape":
                shp, colr = revealed.get("pod_shape"), revealed.get("pod_color")
                path = None
                try:
                    if shp and colr:
                        path = pod_shape_icon_path(shp, colr)
                    elif shp:
                        path = trait_icon_path("pod_shape", shp)
                    elif colr:
                        path = trait_icon_path("pod_color", colr)
                except Exception:
                    path = None
                known = bool(shp or colr)
                r = row(path, f"{shp or '?'}",
                        "pod" if known else "pod — not discovered yet",
                        unknown=not known)
                self._traits_only_harvest_buttons(r, plant, BG)
                continue
            if k in revealed:
                v = revealed[k]
                path = None
                try:
                    if k in ("flower_position", "flower_color"):
                        path = self._flower_trait_icon_path(plant, k, v, revealed)
                    elif k == "pod_shape" and revealed.get("pod_color"):
                        path = pod_shape_icon_path(v, revealed.get("pod_color"))
                    elif k == "pod_color":
                        shp = revealed.get("pod_shape") or (getattr(plant, "traits", {}) or {}).get("pod_shape")
                        path = pod_shape_icon_path(shp, v) if shp else None
                    path = path or trait_icon_path(k, v)
                except Exception:
                    path = None
                row(path, str(v), name)
            else:
                row(None, name, "not discovered yet", unknown=True)
        tk.Frame(body, height=1, bg="#c8c0ac").pack(fill="x", pady=3)
        for color in ("yellow", "green"):
            row(trait_icon_path("seed_color", color), f"n = {counts.get(color, 0)}",
                f"harvested {color} seeds")
        try:
            tw.update_idletasks()
            tw.geometry(f"{tw.winfo_reqwidth()}x{tw.winfo_reqheight()}")
        except Exception:
            pass

    def _build_harvest_section(self, parent, plant, BG, run_action):
        """Pods: count, Harvest All, one icon per pod (click = harvest that
        pod). Its content is redrawn in place whenever the pods change."""
        box = tk.Frame(parent, bg=BG, padx=16, pady=2)
        box.pack(fill="x")
        last = {"key": None}

        def _harvest_one(lbl=None):
            last["clicked"] = lbl           # this exact pod icon goes away
            self._suppress_inspector_refresh = True
            try:
                pod_record = self._on_harvest_selected()
            except Exception:
                pod_record = None
            finally:
                self._suppress_inspector_refresh = False
            self._tally_seed_colors_from_pod_record(plant, pod_record)
            self._sel_traits_sig = None
            self._refresh_inspector_if_open()

        def _upd():
            try:
                if not box.winfo_exists():
                    return
            except Exception:
                return
            stage = int(getattr(plant, "stage", 0) or 0)
            pods = int(getattr(plant, "pods_remaining", 0) or 0)
            fls = self._plant_flowers(plant)
            harvested = sum(1 for f in fls if f.get("harvested"))
            # one entry per pod still on the plant: ripe (harvestable) or not
            pod_list = [plant.pod_is_ripe(f) for f in fls
                        if plant.flower_sets_pod(f) and not f.get("harvested")] if stage >= 6 else []
            ripe = sum(1 for r in pod_list if r)
            key = (stage >= 6, tuple(pod_list), harvested, bool(getattr(plant, "fully_harvested", False)))
            if key == last["key"]:
                return
            # A pod (or a few) harvested and nothing else changed: take that
            # many ripe pods away from random places in the row, in place.
            growing_now = len(pod_list) - ripe
            labs = last.get("labels") or []
            old_ripe = sum(1 for _l, r in labs if r)
            if (labs and last.get("growing") == growing_now and 0 < ripe < old_ripe
                    and last.get("stage6") == (stage >= 6)):
                try:
                    ripe_labs = [x for x in labs if x[1]]
                    gone = []
                    clicked = last.pop("clicked", None)
                    for x in ripe_labs:
                        if clicked is not None and x[0] is clicked:
                            gone.append(x)              # the pod that was clicked
                    rest = [x for x in ripe_labs if x not in gone]
                    need = (old_ripe - ripe) - len(gone)
                    if need > 0:
                        gone += random.sample(rest, need)   # harvested elsewhere: random ones
                    for x in gone:
                        # leave an empty slot exactly where the pod was, so
                        # the others don't slide left (with identical icons
                        # that would look like the rightmost one vanished)
                        cell = x[0].master
                        cw, ch = cell.winfo_width(), cell.winfo_height()
                        x[0].destroy()
                        if cw > 1 and ch > 1:
                            cell.configure(width=cw, height=ch)
                            cell.pack_propagate(False)
                        labs.remove(x)
                    txt = f"{ripe} ripe" + (f",  {growing_now} growing" if growing_now else "")
                    last["count_lbl"].configure(text=txt)
                    last["key"] = key
                    return
                except Exception:
                    pass
            last["key"] = key
            last["labels"] = []
            self._inspector_pod_labels = last["labels"]   # the tutorial lets them glow
            last["growing"] = growing_now
            last["stage6"] = stage >= 6
            for w in box.winfo_children():
                w.destroy()
            self._inspector_harvest_btn = None
            head = tk.Frame(box, bg=BG)
            head.pack(anchor="w")
            tk.Label(head, text="Pods", font=("Segoe UI", 14, "bold"), bg=BG).pack(side="left", padx=(0, 10))
            if stage < 6:
                tk.Label(head, text="No pods yet — they form after flowering.",
                         font=("Segoe UI", 12, "italic"), bg=BG, fg="#888").pack(side="left")
                return
            if not pod_list:
                n_e = int(getattr(plant, "n_emasculated", 0) or 0)
                txt = ("Fully harvested — no pods remain" if harvested
                       else ("No pods (emasculated flowers not pollinated)" if n_e else "No pods"))
                tk.Label(head, text=txt, font=("Segoe UI", 12), bg=BG, fg="#777").pack(side="left")
                return
            growing = len(pod_list) - ripe
            txt = f"{ripe} ripe" + (f",  {growing} growing" if growing else "")
            last["count_lbl"] = tk.Label(head, text=txt, font=("Segoe UI", 13), bg=BG, fg="#555")
            last["count_lbl"].pack(side="left")
            if ripe > 0:
                hb = self._make_flat_button(head, "Harvest All",
                                            lambda: run_action(self._on_harvest_all_selected),
                                            font=("Segoe UI", 13, "bold"))
                hb.pack(side="left", padx=(12, 0))
                self._inspector_harvest_btn = hb    # the tutorial points at it
            icon_path = None
            tr = getattr(plant, "traits", {}) or {}
            if tr.get("pod_shape") and tr.get("pod_color"):
                try:
                    icon_path = pod_shape_icon_path(tr["pod_shape"], tr["pod_color"])
                except Exception:
                    icon_path = None
            prow = tk.Frame(box, bg=BG)
            prow.pack(anchor="w", pady=(4, 0))
            for can in sorted(pod_list, reverse=True):       # ripe ones first
                img = None
                if icon_path:
                    try:
                        img = (safe_image(icon_path) if can else
                               self._greyscale_icon_from_path(icon_path, fade_to_bg=BG, opacity=0.4))
                    except Exception:
                        img = None
                pcell = tk.Frame(prow, bg=BG)          # keeps its place when the pod is gone
                pcell.pack(side="left", padx=4)
                lbl = tk.Label(pcell, image=img or "", text="" if img else "Pod", bg=BG,
                               font=("Segoe UI", 14), fg="#555" if can else "#999",
                               cursor="hand2" if can else "arrow")
                lbl.image = img
                lbl.pack()
                last["labels"].append((lbl, can))
                if can:
                    lbl.bind("<Button-1>", lambda e, l=lbl: _harvest_one(l))
            tk.Label(box, text=("Click a ripe pod to harvest it and reveal its seed colors." if ripe
                                else "Seeds aren't mature yet."),
                     font=("Segoe UI", 12, "italic"), fg="#888", bg=BG).pack(anchor="w", pady=(2, 0))

        def _upd_and_fit():
            before = last["key"]
            _upd()
            if last["key"] != before:
                fit = getattr(self, "_insp_fit", None)
                if fit:
                    fit()

        _upd()
        self._insp_live.append(_upd_and_fit)

    def _inspect_portrait_photo(self, plant):
        """Twice the tile size for the Inspect window: the drawn plant is
        rendered again at 128 px (real extra detail); classic pictures are
        enlarged 2x."""
        try:
            self._ensure_tile_icon(plant)
        except Exception:
            pass
        small = getattr(plant, "img_obj", None)
        args = getattr(plant, "_grown_args", None)
        key = getattr(plant, "_icon_key", None)
        if (args and isinstance(key, tuple) and key and key[0] == "grown"):
            try:
                return ImageTk.PhotoImage(self._grown_pil_render(plant, args, 128))
            except Exception:
                logging.debug("Big plant portrait failed", exc_info=True)
        if small is None:
            return None
        try:
            return small.zoom(2, 2)
        except Exception:
            try:
                big = ImageTk.getimage(small).resize(
                    (small.width() * 2, small.height() * 2), Image.NEAREST)
                return ImageTk.PhotoImage(big)
            except Exception:
                return small

    def _build_flower_panel(self, win, plant, BG, run_close_first, run_action=None):
        """The flowers in the Inspect window as a row of bud / flower icons.
        Click one to select it; the forceps emasculate it and the pollinate
        icon pollinates it. Its history shows below the row. Everything
        here is updated in place (self._flower_panel_live) as buds appear
        and open — the window is not rebuilt for that."""
        pid = getattr(plant, "id", None)
        color = str((getattr(plant, "traits", {}) or {}).get("flower_color", "purple")).lower()
        if color not in ("purple", "white"):
            color = "purple"
        selmap = self.__dict__.setdefault("_flower_sel", {})
        sel = selmap.setdefault(pid, set())
        SEL_BG, CELL_BG = "#f2d48a", BG

        box = tk.Frame(win, bg=BG, padx=16)
        box.pack(fill="x")
        inner = tk.Frame(box, bg=BG, pady=2)
        row = tk.Frame(inner, bg=BG)
        row.pack(anchor="w")
        tk.Label(row, text="Flowers", font=("Segoe UI", 14, "bold"), bg=BG).pack(side="left", padx=(0, 10))
        icons = tk.Frame(row, bg=BG)
        icons.pack(side="left")
        tools = tk.Frame(row, bg=BG)
        tools.pack(side="left")
        pollen_box = tk.Frame(row, bg=BG)
        pollen_box.pack(side="left")
        info = tk.Label(inner, text="", font=("Segoe UI", 11), bg=BG, fg="#5a4a20",
                        justify="left", anchor="w")
        info.pack(anchor="w", pady=(2, 0))

        st_ = {"cells": [], "looks": [], "pollen_key": None, "shown": False,
               "states": [], "fl": [], "can_poll": False}

        def can_emasc(k):
            stage = int(getattr(plant, "stage", 0) or 0)
            return (stage in (4, 5) and st_["states"][k] in ("bud", "open")
                    and not st_["fl"][k].get("emasc"))

        def can_pol(k):
            return st_["can_poll"] and st_["states"][k] == "open"

        def toggle(k):
            # one flower at a time
            was = k in sel
            sel.clear()
            if not was:
                sel.add(k)
            update()

        def run(kind):
            ks = sorted(sel)
            if not ks:
                self._toast("Select a flower first (click its icon).", level="info")
                return
            # Check everything BEFORE the window closes for the dialog, so
            # a refusal leaves the Inspect window open.
            if not self._flower_action_ok(plant, ks[0], kind, st_["states"]):
                return
            self._flower_queue = None
            if kind == "emasc":
                run_close_first(lambda: self._on_emasculate_selected(ks[0] + 1))
            elif kind == "pollen":
                run_close_first(lambda: self._on_collect_pollen(ks[0] + 1))
            else:
                run_close_first(lambda: self._on_pollinate(ks[0] + 1))

        def action_btn(names, fallback, tip, cmd, padl):
            img = self._action_icon(names)
            b = tk.Label(tools, image=img, text="" if img else fallback, compound="center",
                         font=("Segoe UI", 12, "bold"), bg="#e8e0cf", padx=6, pady=3,
                         relief="flat", cursor="hand2")
            b.image = img
            b.pack(side="left", padx=(padl, 0))
            b.bind("<Button-1>", lambda e: cmd())
            try:
                _attach_tooltip(b, tip)
            except Exception:
                pass
            return b

        btn_e = action_btn(("pollen.png",), "Emasculate",          # forceps
                           "Emasculate: Remove anthers", lambda: run("emasc"), 12)
        btn_p = action_btn(("pollinate.png",), "Pollinate",
                           "Pollinate flower (morning / noon)",
                           lambda: run("poll"), 4)

        def update():
            try:
                if not box.winfo_exists():
                    return
            except Exception:
                return
            states = self._flower_states(plant)
            fl = plant.ensure_flowers() if states else []
            st_["states"], st_["fl"] = states, fl
            # an open Inspect window counts as inspecting: today's anther
            # check is done by itself (also when a new day starts meanwhile)
            if "open" in states:
                try:
                    self._ensure_anther_check_today(plant)
                except Exception:
                    pass
            st_["can_poll"] = self._can_pollinate_now(plant)
            fit = getattr(self, "_insp_fit", None)
            if not states:
                if st_["shown"]:
                    inner.pack_forget()
                    st_["shown"] = False
                    try:
                        box.configure(height=1)
                    except Exception:
                        pass
                    if fit:
                        fit()
                return
            grew = False
            if not st_["shown"]:
                inner.pack(fill="x")
                st_["shown"] = True
                grew = True
            for k in list(sel):
                if k >= len(fl):
                    sel.discard(k)
            # Only buds and open flowers are listed — flowers that have
            # turned into pods (or dropped / been harvested) leave the row.
            vis = [k for k, st in enumerate(states) if st in ("bud", "open")]
            for k in list(sel):
                if k not in vis:
                    sel.discard(k)
            if vis != st_.get("vis"):
                for w in icons.winfo_children():
                    w.destroy()
                st_["cells"], st_["looks"], st_["vis"] = {}, {}, list(vis)
                for k in vis:
                    cell = tk.Frame(icons, bg=CELL_BG, padx=1, pady=1, cursor="hand2")
                    cell.pack(side="left", padx=1)
                    ic = tk.Label(cell, bg=CELL_BG, cursor="hand2")
                    ic.pack()
                    for w in (cell, ic):
                        w.bind("<Button-1>", lambda e, k=k: toggle(k))
                    st_["cells"][k] = (cell, ic)
                    st_["looks"][k] = None
                if not vis:
                    tk.Label(icons, text="no buds or open flowers at the moment",
                             font=("Segoe UI", 11, "italic"), bg=BG, fg="#888").pack(side="left")
                grew = True
            for k in vis:
                f, st = fl[k], states[k]
                look = ({"open": "open", "bud": "bud"}.get(st, "open"),
                        bool(f.get("emasc")), bool(f.get("pollen")))
                cell, ic = st_["cells"][k]
                if st_["looks"][k] != look:
                    img = self._flower_row_icon(color, *look)
                    ic.configure(image=img or "", text="" if img else "\u2022")
                    ic.image = img
                    st_["looks"][k] = look
                bgc = SEL_BG if k in sel else CELL_BG
                if str(cell.cget("bg")) != bgc:
                    cell.configure(bg=bgc)
                    ic.configure(bg=bgc)
            if grew and fit:
                self.root.after_idle(fit)
            ks = sorted(sel)
            txt = (self._flower_info_text(plant, ks, states) if ks else
                   "Click a flower to select it (click again to deselect).")
            if info.cget("text") != txt:
                info.configure(text=txt)
            en_e = any(can_emasc(k) for k in ks)
            en_p = any(can_pol(k) for k in ks)
            for btn, en in ((btn_e, en_e), (btn_p, en_p)):
                # always clickable (a click explains why not), only dimmed
                btn.configure(bg="#e8e0cf" if en else "#ece8de",
                              fg="#3b2a1a" if en else "#a09a8c")
            # pollen of this plant (anthers checked once a day from flowering on)
            today = self._today()
            stage = int(getattr(plant, "stage", 0) or 0)
            if "open" in states:
                checked = getattr(plant, "last_anther_check_day", None) == today
                pk = ("collect" if (checked and bool(getattr(plant, "anthers_available_today", False)))
                      else ("none" if checked else "unchecked"))
            else:
                pk = None
            ok_pollen = any(self._flower_anthers_ready(plant, k, st_["states"]) for k in ks)
            if pk != st_["pollen_key"]:
                st_["pollen_key"] = pk
                for w in pollen_box.winfo_children():
                    w.destroy()
                st_["pollen_btn"] = None
                if pk:
                    pbn = tk.Label(pollen_box, text="Collect Pollen", font=("Segoe UI", 12, "bold"),
                                   bg="#7A9A3C", fg="white", padx=8, pady=3, cursor="hand2")
                    pbn.pack(side="left", padx=(16, 0))
                    pbn.bind("<Button-1>", lambda e: run("pollen"))
                    try:
                        _attach_tooltip(pbn, "Collect pollen: take anthers from the selected open flower "
                                             "(one or several)")
                    except Exception:
                        pass
                    st_["pollen_btn"] = pbn
                    if pk != "collect":
                        tk.Label(pollen_box, text="no flower has ripe anthers today",
                                 font=("Segoe UI", 11, "italic"), bg=BG,
                                 fg="#888").pack(side="left", padx=(6, 0))
            if st_.get("pollen_btn") is not None:
                st_["pollen_btn"].configure(bg="#7A9A3C" if (ok_pollen and pk == "collect") else "#c9cfbd")

        self._flower_panel_live = (pid, update)
        update()

    def _restore_inspector_after_dialog(self):
        """Shows the inspector again after a dialog — the same window,
        refreshed in place (only rebuilt if it was really closed)."""
        w = getattr(self, "_inspector_win", None)
        try:
            if w is not None and w.winfo_exists():
                # update it while still hidden, so it reappears already
                # showing the change (no visible re-layout afterwards)
                self._refresh_inspector_if_open()
                w.update_idletasks()
                geom = getattr(self, "_inspector_geom", None)
                if geom:
                    try:
                        w.geometry(geom)
                    except Exception:
                        pass
                    fit = getattr(self, "_insp_fit", None)
                    if fit:
                        fit()                 # height may have changed (e.g. a tag line)
                w.deiconify()
                w.lift()
                return
        except Exception:
            pass
        self._on_inspect_unified()

    def _inspector_dialog_watch(self):
        """Safety net: if the inspector is still hidden but no dialog is
        open any more (e.g. the pollen chooser was simply closed), bring
        it back."""
        if not getattr(self, "_reopen_inspector_after_dialog", False):
            return
        w = getattr(self, "_inspector_win", None)
        try:
            if w is None or not w.winfo_exists() or w.winfo_viewable():
                return
        except Exception:
            return
        busy = False
        try:
            for c in self.root.winfo_children():
                if (isinstance(c, tk.Toplevel) and c is not w
                        and c is not getattr(self, "_traits_only_win", None)
                        and c.winfo_viewable() and not c.overrideredirect()):
                    busy = True
                    break
        except Exception:
            busy = False
        if busy:
            self.root.after(800, self._inspector_dialog_watch)
            return
        self._reopen_inspector_after_dialog = False
        self._restore_inspector_after_dialog()
