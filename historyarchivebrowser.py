"""
History Archive Browser Module

Provides the Trait Inheritance Explorer interface for browsing plant breeding
history, visualizing family trees, and detecting Mendelian laws.

Features:
- Plant archive browsing and visualization
- Family tree rendering with trait inheritance  
- Mendelian law detection (Dominance, Segregation, Independent Assortment)
- Pedigree analysis and sibling comparison
- CSV export of breeding experiments
- Genotype-phenotype relationship exploration

The module contains:
1. Standalone law-testing functions for integration with main app
2. HistoryArchiveBrowser class for the visual interface
"""

# ============================================================================
# Imports
# ============================================================================

# Standard library
import functools
import math
import os
import platform
import re
import traceback
from collections import Counter
from itertools import combinations

# Third-party
import tkinter as tk
from tkinter import messagebox, ttk

# Local
from icon_loader import *


# ============================================================================
# Configuration
# ============================================================================

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(ROOT_DIR, "export")

# Create export directory
try:
    os.makedirs(EXPORT_DIR, exist_ok=True)
except Exception:
    pass


# ============================================================================
# Standalone Mendelian Law Testing Functions
# ============================================================================


import functools
import math
import os
import re
import traceback
from collections import Counter
from itertools import combinations
import platform

import tkinter as tk
from tkinter import messagebox, ttk

from icon_loader import *

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(ROOT_DIR, "export")
try:
    os.makedirs(EXPORT_DIR, exist_ok=True)
except Exception:
    pass
    
def _test_mendelian_laws_now(self):
    try:
        # keep archive in sync (same prep as TIE)
        if hasattr(self, "_seed_archive_safe"):
            self._seed_archive_safe()
        # backfill helper exists on HistoryArchiveBrowser, not on the dict archive
        try:
            if hasattr(self, "_archive_backfill_cross_parents"):
                self._archive_backfill_cross_parents()
        except Exception:
            pass

        # call the shared law-testing function
        from historyarchivebrowser import test_mendelian_laws
        test_mendelian_laws(self, archive=getattr(self, "archive", None), pid=getattr(self, "law_context_pid", None), allow_credit=True, toast=True)

    except Exception as e:
        try:
            self._toast(f"Law test failed: {e}", level="warn")
        except Exception:
            print("Law test failed:", e)

def test_mendelian_laws(app, archive=None, pid=None, allow_credit=True, toast=True):
    """Run Mendelian-law detection using the *exact same rules* as the Trait Inheritance Explorer.

    This is the single shared entry point used by:
      - the main UI "Unlock" button (GardenApp)
      - the Trait Inheritance Explorer export/test button

    Returns: {"law1": bool, "law2": bool, "law3": bool, "new": ["law1","law2","law3"]}
    Also updates app.law*_ever_discovered and app.law2_ratio_ui / app.law3_ratio_ui, and refreshes
    app._update_law_status_label() when present.
    """

    # Use existing archive unless provided
    archive = archive if archive is not None else getattr(app, "archive", None)
    if not isinstance(archive, dict):
        return {"law1": False, "law2": False, "law3": False, "new": []}
    plants = archive.get("plants", {})
    if not isinstance(plants, dict) or not plants:
        return {"law1": False, "law2": False, "law3": False, "new": []}

    # Respect genotype reveal session rule (no credit once alleles were revealed)
    if (not allow_credit) or bool(getattr(app, "_genotype_revealed", False)):
        return {"law1": False, "law2": False, "law3": False, "new": []}

    # If pid wasn't provided, try to infer it like the main UI would.
    if pid in (None, "", -1):
        pid = getattr(app, "law_context_pid", None)

    # Robust snapshot fetch (string/int keys)
    def _get_snap_local(pid_):
        if pid_ in (None, "", -1):
            return None
        # try exact
        if pid_ in plants:
            return plants.get(pid_)
        # try str/int forms
        try:
            si = str(pid_)
            if si in plants:
                return plants.get(si)
        except Exception:
            pass
        try:
            ii = int(pid_)
            if ii in plants:
                return plants.get(ii)
        except Exception:
            pass
        return None

    snap = _get_snap_local(pid)
    if not snap:
        return {"law1": False, "law2": False, "law3": False, "new": []}

    # ---- helper: parent extraction (same as HistoryArchiveBrowser._parents_from_snapshot) ----
    def _parents_from_snapshot(snap_obj):
        if not isinstance(snap_obj, dict):
            return (getattr(snap_obj, "mother_id", None), getattr(snap_obj, "father_id", None))

        MOTHER_KEYS = [
            "mother_id","mother","maternal_id","mom_id",
            "female_parent","female_id","dam_id",
            "seed_parent_id","seed_parent","maternal_pid","female",
        ]
        FATHER_KEYS = [
            "father_id","father","paternal_id","dad_id",
            "male_parent","male_id","sire_id",
            "pollen_donor_id","pollen_source_id","pollen_parent_id","pollinator_id",
            "pollen_donor","pollen_source","pollen",
        ]
        NESTED = ["pollination","cross","cross_info","seed_source","source_pod","source_cross","repro","reproduction"]

        def pick(dct, keys):
            for k in keys:
                if isinstance(dct, dict) and k in dct and dct[k] not in (None, "", -1):
                    return dct[k]
            return None

        mid_ = pick(snap_obj, MOTHER_KEYS)
        fid_ = pick(snap_obj, FATHER_KEYS)
        if mid_ is None or fid_ is None:
            for nk in NESTED:
                nd = snap_obj.get(nk)
                if isinstance(nd, dict):
                    if mid_ is None:
                        mid_ = pick(nd, MOTHER_KEYS)
                    if fid_ is None:
                        fid_ = pick(nd, FATHER_KEYS)
        return (mid_, fid_)

    # ---- helpers used by the TIE law logic ----
    def _g(s, key, default=None):
        if isinstance(s, dict):
            return s.get(key, default)
        try:
            return getattr(s, key, default)
        except Exception:
            return default

    try:
        mid, fid = _parents_from_snapshot(snap)
    except Exception:
        mid, fid = (_g(snap, "mother_id", None), _g(snap, "father_id", None))

    try:
        traits = dict(snap.get("traits", {}) or {}) if isinstance(snap, dict) else dict(getattr(snap, "traits", {}) or {})
    except Exception:
        traits = {}

    # Snapshot lookup helper for IDs
    def _get_arch_snap(pid_):
        return _get_snap_local(pid_)

    # ---------------------- BEGIN: copied TIE law-test logic ----------------------
    # (This block is intentionally mirrored from HistoryArchiveBrowser._export_selected_traits)

    def _geno_from_snap_law2(s):
        try:
            if isinstance(s, dict):
                g = s.get("genotype") or {}
            else:
                g = getattr(s, "genotype", None) or {}
        except Exception:
            g = {}
        return dict(g) if isinstance(g, dict) else {}

    def _law1_cross_signature_for_trait(m_snap, f_snap, locus):
        """Canonical cross signature (order-independent) for Law 1 tests."""
        m_geno = _geno_from_snap_law2(m_snap)
        f_geno = _geno_from_snap_law2(f_snap)
        if not isinstance(m_geno, dict) or not isinstance(f_geno, dict):
            return None

        m_pair = m_geno.get(locus)
        f_pair = f_geno.get(locus)
        if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2):
            return None
        if not (isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
            return None

        m_a1, m_a2 = m_pair[0], m_pair[1]
        f_a1, f_a2 = f_pair[0], f_pair[1]

        if not (m_a1 == m_a2 and f_a1 == f_a2):
            return None
        if m_a1 == f_a1:
            return None

        def _canon(pair):
            a1, a2 = pair[0], pair[1]
            return "".join(sorted([str(a1), str(a2)]))

        return tuple(sorted([_canon(m_pair), _canon(f_pair)]))

    revealed = bool(getattr(app, "_genotype_revealed", False))

    law1_discovered = False
    law1_reason = ""

    law2_discovered = False
    law2_reason = ""
    law2_ratio_str = ""
    law2_trait_name = ""

    law3_discovered = False
    law3_reason = ""
    law3_ratio_str = ""
    law3_trait_pair = ()

    trait_to_locus = {
        "flower_color":  "A",
        "pod_color":     "Gp",
        "seed_color":    "I",
        "seed_shape":    "R",
        "plant_height":  "Le",
    }
    law_trait_keys = ["flower_color", "pod_color", "seed_color", "seed_shape", "plant_height"]

    arch_plants = plants

    # ---------------- Law 1 (Dominance) ----------------
    if not revealed:
        mother_snap = _get_arch_snap(mid)
        father_snap = _get_arch_snap(fid)

        if mother_snap and father_snap and mid not in (None, "", -1) and fid not in (None, "", -1) and str(mid) != str(fid):
            try:
                m_traits = dict(mother_snap.get("traits", {}) or {}) if isinstance(mother_snap, dict) else dict(getattr(mother_snap, "traits", {}) or {})
            except Exception:
                m_traits = {}
            try:
                f_traits = dict(father_snap.get("traits", {}) or {}) if isinstance(father_snap, dict) else dict(getattr(father_snap, "traits", {}) or {})
            except Exception:
                f_traits = {}

            m_geno = _geno_from_snap_law2(mother_snap)
            f_geno = _geno_from_snap_law2(father_snap)

            dominant_candidates = []

            for tk in law_trait_keys:
                cv = str(traits.get(tk, "")).strip()
                mv = str(m_traits.get(tk, "")).strip()
                fv = str(f_traits.get(tk, "")).strip()

                if not (cv and mv and fv and mv != fv and (cv == mv or cv == fv)):
                    continue

                loc = trait_to_locus.get(tk)
                if not loc:
                    continue

                cross_sig = _law1_cross_signature_for_trait(mother_snap, father_snap, loc)
                if cross_sig is None:
                    continue

                m_pair = m_geno.get(loc)
                f_pair = f_geno.get(loc)
                if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2 and isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
                    continue

                m_a1, m_a2 = m_pair[0], m_pair[1]
                f_a1, f_a2 = f_pair[0], f_pair[1]
                if not (m_a1 == m_a2 and f_a1 == f_a2):
                    continue
                if m_a1 == f_a1:
                    continue

                same_pheno_total = 0
                for _cid, csnap in arch_plants.items():
                    if isinstance(csnap, dict) and not csnap.get("alive", True):
                        continue

                    smid, sfid = _parents_from_snapshot(csnap if isinstance(csnap, dict) else {})
                    if smid in (None, "", -1) or sfid in (None, "", -1):
                        continue

                    m_snap2 = _get_arch_snap(smid)
                    f_snap2 = _get_arch_snap(sfid)
                    if not m_snap2 or not f_snap2:
                        continue

                    sig2 = _law1_cross_signature_for_trait(m_snap2, f_snap2, loc)
                    if sig2 is None or sig2 != cross_sig:
                        continue

                    try:
                        s_traits = csnap.get("traits", {}) if isinstance(csnap, dict) else getattr(csnap, "traits", {}) or {}
                    except Exception:
                        s_traits = {}
                    sv = str(s_traits.get(tk, "")).strip()
                    if sv == cv:
                        same_pheno_total += 1

                if same_pheno_total < LAW1_MIN_F1:
                    continue

                dominant_candidates.append((tk, cv, mv, fv, same_pheno_total))

            if dominant_candidates:
                law1_discovered = True
                tk, cv, mv, fv, sib_count = dominant_candidates[0]
                trait_label = tk.replace("_", " ")
                law1_reason = (
                    f"Observed in cross #{mid} × #{fid} for trait '{trait_label}': "
                    f"parents {mv} × {fv} → offspring {cv} "
                    f"in at least {sib_count + 1} F1 plants (including this plant), "
                    f"from true-breeding parental lines."
                )

    # ---------------- Law 2 (Segregation) ----------------
    try:
        has_parents = (mid not in (None, "", -1) and fid not in (None, "", -1))
    except Exception:
        has_parents = False

    parent_snap_m = _get_arch_snap(mid) if has_parents else None
    parent_snap_f = _get_arch_snap(fid) if has_parents else None

    def _law2_family_signature(parent_snap, gp_m, gp_f, locus):
        parent_geno = _geno_from_snap_law2(parent_snap)
        if not isinstance(parent_geno, dict):
            return None
        p_pair = parent_geno.get(locus)
        if not (isinstance(p_pair, (list, tuple)) and len(p_pair) >= 2):
            return None
        pa1, pa2 = p_pair[0], p_pair[1]
        if pa1 == pa2:
            return None

        gm_geno = _geno_from_snap_law2(gp_m)
        gf_geno = _geno_from_snap_law2(gp_f)
        if not isinstance(gm_geno, dict) or not isinstance(gf_geno, dict):
            return None

        m_pair = gm_geno.get(locus)
        f_pair = gf_geno.get(locus)
        if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2):
            return None
        if not (isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
            return None

        m_a1, m_a2 = m_pair[0], m_pair[1]
        f_a1, f_a2 = f_pair[0], f_pair[1]
        if not (m_a1 == m_a2 and f_a1 == f_a2):
            return None
        # REMOVED: if m_a1 == f_a1: return None
        # This check was too restrictive - it rejected selfed true-breeding lines.
        # Mendel used selfing to establish homozygous lines, then crossed them.
        # As long as grandparents are homozygous and parent is heterozygous,
        # we have valid Mendelian segregation regardless of whether grandparents
        # came from AA × aa or from selfed AA × AA lines.

        def _canon(pair):
            a1, a2 = pair[0], pair[1]
            return "".join(sorted([str(a1), str(a2)]))

        return tuple(sorted([_canon(m_pair), _canon(f_pair)]))

    def _get_grandparents_for_parent(parent_snap):
        try:
            pmid, pfid = _parents_from_snapshot(parent_snap)
        except Exception:
            pmid, pfid = (_g(parent_snap, "mother_id", None), _g(parent_snap, "father_id", None))
        gp_m = _get_arch_snap(pmid)
        gp_f = _get_arch_snap(pfid)
        return gp_m, gp_f

    gp_m = gp_f = None
    parent_snap = None
    parent_traits = None

    # Choose a representative "F1 parent" for Law2/3: prefer selfing if possible else sib-mating
    if not revealed and parent_snap_m and parent_snap_f:
        # If selfed: mother==father -> parent is that plant
        if str(mid) == str(fid):
            parent_snap = parent_snap_m
        else:
            # otherwise pick mother as "parent" reference; Law2/3 code uses family signatures anyway
            parent_snap = parent_snap_m

        try:
            parent_traits = dict(parent_snap.get("traits", {}) or {}) if isinstance(parent_snap, dict) else dict(getattr(parent_snap, "traits", {}) or {})
        except Exception:
            parent_traits = {}

        gp_m, gp_f = _get_grandparents_for_parent(parent_snap)

    if not revealed and parent_snap and gp_m and gp_f:
        parent_geno = _geno_from_snap_law2(parent_snap)
        # need a valid heterozygous locus with opposite homozygous grandparents and enough F2
        for tk in law_trait_keys:
            loc = trait_to_locus.get(tk)
            if not loc:
                continue

            fam_sig = _law2_family_signature(parent_snap, gp_m, gp_f, loc)
            if fam_sig is None:
                continue

            # collect F2 offspring for this family
            dom_pheno = str(parent_traits.get(tk, "")).strip().lower()
            counts = {"dom": 0, "rec": 0}
            total = 0

            for _cid2, csnap2 in arch_plants.items():
                if isinstance(csnap2, dict) and not csnap2.get("alive", True):
                    continue

                smid2, sfid2 = _parents_from_snapshot(csnap2 if isinstance(csnap2, dict) else {})
                if smid2 in (None, "", -1) or sfid2 in (None, "", -1):
                    continue

                # F2 must come from Aa×Aa parents belonging to this family signature
                pm = _get_arch_snap(smid2)
                pf = _get_arch_snap(sfid2)
                if not pm or not pf:
                    continue

                # parent pair must be heterozygous at loc
                pgm = _geno_from_snap_law2(pm)
                pgf = _geno_from_snap_law2(pf)
                pair_m = pgm.get(loc)
                pair_f = pgf.get(loc)
                if not (isinstance(pair_m, (list, tuple)) and len(pair_m) >= 2 and isinstance(pair_f, (list, tuple)) and len(pair_f) >= 2):
                    continue
                if len(set(pair_m[:2])) != 2 or len(set(pair_f[:2])) != 2:
                    continue

                # grandparents for each parent must match family signature
                gp_m2, gp_f2 = _get_grandparents_for_parent(pm)
                gp_m3, gp_f3 = _get_grandparents_for_parent(pf)
                sig_m = _law2_family_signature(pm, gp_m2, gp_f2, loc) if (gp_m2 and gp_f2) else None
                sig_f = _law2_family_signature(pf, gp_m3, gp_f3, loc) if (gp_m3 and gp_f3) else None
                if sig_m != fam_sig or sig_f != fam_sig:
                    continue

                # classify phenotype
                try:
                    ctraits2 = csnap2.get("traits", {}) if isinstance(csnap2, dict) else getattr(csnap2, "traits", {}) or {}
                except Exception:
                    ctraits2 = {}
                ph = str(ctraits2.get(tk, "")).strip().lower()
                if not ph:
                    continue

                total += 1
                if ph == dom_pheno:
                    counts["dom"] += 1
                else:
                    counts["rec"] += 1

            if total < LAW2_MIN_N:
                continue

            dom_frac = counts["dom"] / float(total) if total else 0.0
            if LAW2_DOM_FRAC_MIN <= dom_frac <= LAW2_DOM_FRAC_MAX:
                law2_discovered = True
                trait_label = tk.replace("_", " ")
                law2_trait_name = trait_label

                # ratio string: dominant:recessive, scaled so recessive=1 if possible
                try:
                    d = counts["dom"]
                    r = counts["rec"]
                    if r > 0:
                        x = d / float(r)
                        x_str = (f"{x:.2f}").replace(".", ",")
                        law2_ratio_str = f"{x_str}:1"
                    else:
                        law2_ratio_str = f"{d}:{r}"
                except Exception:
                    law2_ratio_str = ""

                law2_reason = (
                    f"Observed in F2 offspring (N = {total}) for trait '{trait_label}': "
                    f"dominant vs recessive phenotypes appear close to 3:1."
                )
                break

    # ---------------- Law 3 (Independent Assortment) ----------------
    if not revealed and parent_snap and gp_m and gp_f and arch_plants and not law3_discovered:
        parent_geno = _geno_from_snap_law2(parent_snap)

        def _law3_family_signature(parent_snap_, gp_m_, gp_f_, loc1, loc2):
            parent_geno_ = _geno_from_snap_law2(parent_snap_)
            if not isinstance(parent_geno_, dict):
                return None
            p1 = parent_geno_.get(loc1)
            p2 = parent_geno_.get(loc2)
            if not (isinstance(p1, (list, tuple)) and len(p1) >= 2 and isinstance(p2, (list, tuple)) and len(p2) >= 2):
                return None
            if len(set(p1[:2])) != 2 or len(set(p2[:2])) != 2:
                return None

            gm = _geno_from_snap_law2(gp_m_)
            gf = _geno_from_snap_law2(gp_f_)
            if not isinstance(gm, dict) or not isinstance(gf, dict):
                return None

            def _canon(pair):
                a1, a2 = pair[0], pair[1]
                return "".join(sorted([str(a1), str(a2)]))

            key1 = tuple(sorted([_canon(gm.get(loc1, ('?','?'))), _canon(gf.get(loc1, ('?','?')))]))
            key2 = tuple(sorted([_canon(gm.get(loc2, ('?','?'))), _canon(gf.get(loc2, ('?','?')))]))
            return tuple(sorted([(loc1, key1), (loc2, key2)]))

        from itertools import combinations
        from collections import Counter

        candidate_traits = [tk for tk in law_trait_keys if tk in (parent_traits or {}) and trait_to_locus.get(tk)]

        for tk1, tk2 in combinations(candidate_traits, 2):
            if {"pod_color", "seed_shape"} == {tk1, tk2}:
                continue

            loc1 = trait_to_locus.get(tk1)
            loc2 = trait_to_locus.get(tk2)
            if not loc1 or not loc2:
                continue

            pair1 = parent_geno.get(loc1)
            pair2 = parent_geno.get(loc2)
            if not (isinstance(pair1, (list, tuple)) and len(pair1) >= 2 and isinstance(pair2, (list, tuple)) and len(pair2) >= 2):
                continue
            if len(set(pair1[:2])) != 2 or len(set(pair2[:2])) != 2:
                continue

            fam_sig = _law3_family_signature(parent_snap, gp_m, gp_f, loc1, loc2)
            if fam_sig is None:
                continue

            combo_counts = Counter()
            dom1 = str((parent_traits or {}).get(tk1, "")).strip().lower()
            dom2 = str((parent_traits or {}).get(tk2, "")).strip().lower()

            for _cid2, csnap2 in arch_plants.items():
                if isinstance(csnap2, dict) and not csnap2.get("alive", True):
                    continue

                smid2, sfid2 = _parents_from_snapshot(csnap2 if isinstance(csnap2, dict) else {})
                if smid2 in (None, "", -1) or sfid2 in (None, "", -1):
                    continue

                pm = _get_arch_snap(smid2)
                pf = _get_arch_snap(sfid2)
                if not pm or not pf:
                    continue

                # both parents must belong to same dihybrid family signature
                gp_m2, gp_f2 = _get_grandparents_for_parent(pm)
                gp_m3, gp_f3 = _get_grandparents_for_parent(pf)
                sig_m = _law3_family_signature(pm, gp_m2, gp_f2, loc1, loc2) if (gp_m2 and gp_f2) else None
                sig_f = _law3_family_signature(pf, gp_m3, gp_f3, loc1, loc2) if (gp_m3 and gp_f3) else None
                if sig_m != fam_sig or sig_f != fam_sig:
                    continue

                try:
                    ctraits2 = csnap2.get("traits", {}) if isinstance(csnap2, dict) else getattr(csnap2, "traits", {}) or {}
                except Exception:
                    ctraits2 = {}
                ph1 = str(ctraits2.get(tk1, "")).strip().lower()
                ph2 = str(ctraits2.get(tk2, "")).strip().lower()
                if not ph1 or not ph2:
                    continue

                a = "D" if ph1 == dom1 else "r"
                b = "D" if ph2 == dom2 else "r"
                combo_counts[(a, b)] += 1

            needed_keys = [("D","D"), ("D","r"), ("r","D"), ("r","r")]
            total = sum(combo_counts.values())
            if total < LAW3_MIN_N:
                continue
            if any(combo_counts[k] == 0 for k in needed_keys):
                continue

            expected_ratios = {("D","D"): 9, ("D","r"): 3, ("r","D"): 3, ("r","r"): 1}
            chi2 = 0.0
            for k in needed_keys:
                obs = combo_counts[k]
                exp = expected_ratios[k] * (total / 16.0)
                if exp <= 0:
                    continue
                diff = obs - exp
                chi2 += (diff * diff) / exp

            if chi2 <= LAW3_CHI2_MAX:
                law3_discovered = True
                trait_label1 = tk1.replace("_", " ")
                trait_label2 = tk2.replace("_", " ")

                try:
                    vals = [combo_counts[k] for k in needed_keys]
                    total2 = sum(vals)
                    if total2 > 0:
                        scaled = [(v / total2) * 16.0 for v in vals]
                        pretty_parts = [f"{x:.1f}".replace(".", ",") for x in scaled]
                        law3_ratio_str = " : ".join(pretty_parts) + " (scaled to 16)"
                    else:
                        law3_ratio_str = ""
                    law3_trait_pair = (trait_label1, trait_label2)
                except Exception:
                    law3_ratio_str = ""
                    law3_trait_pair = (trait_label1, trait_label2)

                try:
                    cross_label = f"selfed F1 plant #{mid}" if str(mid) == str(fid) else f"F1 cross #{mid}×{fid}"
                except Exception:
                    cross_label = "F1 cross #?"

                law3_reason = (
                    f"Observed in dihybrid F2 offspring of {cross_label} "
                    f"for traits '{trait_label1}' and '{trait_label2}': "
                    f"the four phenotype combinations appear in an approximately 9:3:3:1 ratio (N = {total})."
                )

                break

    # ---------------- Apply discoveries to app + UI ----------------
    new = []

    if not revealed:
        if law1_discovered and not getattr(app, "law1_ever_discovered", False):
            setattr(app, "law1_ever_discovered", True)
            setattr(app, "law1_first_plant", pid)
            new.append("law1")
            if toast and hasattr(app, "_toast"):
                try:
                    app._toast(f"Law 1 (Dominance) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

        if law2_discovered and not getattr(app, "law2_ever_discovered", False):
            setattr(app, "law2_ever_discovered", True)
            setattr(app, "law2_first_plant", pid)
            new.append("law2")
            if toast and hasattr(app, "_toast"):
                try:
                    app._toast(f"Law 2 (Segregation) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

        if law3_discovered and not getattr(app, "law3_ever_discovered", False):
            setattr(app, "law3_ever_discovered", True)
            setattr(app, "law3_first_plant", pid)
            new.append("law3")
            if toast and hasattr(app, "_toast"):
                try:
                    app._toast(f"Law 3 (Independent Assortment) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

    # Push ratio info to the main app for the top-bar UI
    try:
        if not revealed:
            if law2_discovered:
                if not law2_ratio_str:
                    # best-effort fallback
                    law2_ratio_str = "Ratio __:__"
                setattr(app, "law2_ratio_ui", law2_ratio_str)
            if law3_discovered and law3_ratio_str:
                setattr(app, "law3_ratio_ui", law3_ratio_str)
            if hasattr(app, "_update_law_status_label"):
                app._update_law_status_label()
    except Exception:
        pass

    # Stash law ratio info into the archive snapshot
    try:
        if isinstance(snap, dict):
            if law2_discovered and law2_ratio_str:
                snap["law2_ratio"] = law2_ratio_str
                if law2_trait_name:
                    snap["law2_trait"] = law2_trait_name
            if law3_discovered and law3_ratio_str:
                snap["law3_ratio"] = law3_ratio_str
                if law3_trait_pair:
                    snap["law3_traits"] = f"{law3_trait_pair[0]} × {law3_trait_pair[1]}"
    except Exception:
        pass

    return {"law1": bool(law1_discovered), "law2": bool(law2_discovered), "law3": bool(law3_discovered), "new": new}

# =============================================================================
# Mendelian law unlock thresholds (single source of truth)
# =============================================================================

# Law 1 (Dominance): how many phenotype-only F1 offspring (same phenotype) needed
LAW1_MIN_F1 = 16

# Law 2 (Segregation, ~3:1): minimum F2 sample size and acceptable dominant fraction band
LAW2_MIN_N = 65
LAW2_DOM_FRAC_MIN = 0.73
LAW2_DOM_FRAC_MAX = 0.85

# Law 3 (Independent Assortment, ~9:3:3:1): minimum dihybrid F2 sample size and chi-square threshold
LAW3_MIN_N = 80
LAW3_CHI2_MAX = 4.0

class HistoryArchiveBrowser(tk.Toplevel):
    BG = "#0c1a21"
    PANEL = "#0f2230"
    CARD = "#102633"
    FG = "#e8f0f5"
    MUTED = "#a8bcc9"
    ACCENT = "#1f6aa5"
    PAD = 10

    # --- Background tints for pods (applied to whole pod card) ---
    POD_TINT_GREEN = "#2d5145"   # slightly less green
    POD_TINT_YELLOW = "#6a5a16"  # strong yellow/olive

    def _pod_tint_from_color(self, color_str):
        s = str(color_str or "").lower()
        if "green" in s:
            return self.POD_TINT_GREEN
        if "yellow" in s:
            return self.POD_TINT_YELLOW
        return self.CARD

    def _on_canvas_node_click(self, event=None):
        c = self.canvas
        try:
            item = c.find_closest(event.x, event.y)
            tags = c.gettags(item)
        except Exception:
            return
        pid = None
        for t in tags:
            if t.startswith("node_"):
                pid = t.split("_", 12)[1]
                break
        if pid is None:
            return
        # sync list selection
        try:
            ids = [str(x) for x in self._ids]
            if str(pid) in ids:
                idx = ids.index(str(pid))
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(idx)
                self.listbox.see(idx)
        except Exception:
            pass
        self._render_pid(str(pid)) if str(pid) == str(getattr(self, 'current_pid', None)) else self._render_preview(str(pid))

    def __init__(self, parent_window, app, default_pid=None):
        tk.Toplevel.__init__(self, parent_window)
        self.app = app
        self.title("Trait Inheritance Explorer")
        self.configure(bg=self.BG)
        self.minsize(1024, 600)

        if not hasattr(self.app, "archive") or not isinstance(getattr(self.app, "archive", None), dict):
            self.app.archive = {"plants": {}}
        elif "plants" not in self.app.archive or not isinstance(self.app.archive["plants"], dict):
            self.app.archive["plants"] = dict(self.app.archive.get("plants") or {})

        tb = tk.Frame(self, bg=self.BG)
        tb.pack(fill="x", padx=self.PAD, pady=(self.PAD, 4))

        # --- Cross-platform button styling: macOS Aqua ignores tk.Button colors ---
        IS_MAC = (platform.system() == "Darwin")

        # Force a theme that allows us to control button colors on macOS
        self._style = ttk.Style(self)
        if IS_MAC:
            try:
                self._style.theme_use("clam")
            except tk.TclError:
                pass

        # Toolbar button style
        self._style.configure(
            "Toolbar.TButton",
            padding=(10, 4),
            foreground=self.FG,
            background=self.CARD
        )
        self._style.map(
            "Toolbar.TButton",
            foreground=[("active", self.FG), ("pressed", self.FG)],
            background=[("active", self.CARD), ("pressed", self.CARD)],
        )

        def _mkbtn(parent, text, command, **extra):
            if IS_MAC:
                # On macOS use ttk + styled theme (reliable)
                return ttk.Button(parent, text=text, command=command, style="Toolbar.TButton")
            else:
                # On Windows/Linux classic tk.Button styling is fine
                kw = dict(bg=self.CARD, fg=self.FG, relief="groove")
                kw.update(extra)
                return tk.Button(parent, text=text, command=command, **kw)


        btn_refresh = _mkbtn(tb, "Refresh", self._reload_ids)
        btn_refresh.pack(side="left")

        btn_seed = _mkbtn(tb, "Seed from Live", lambda: (self._seed_from_live(), self._reload_ids()))
        btn_seed.pack(side="left", padx=(6,0))

        tk.Label(tb, text=" Find #", bg=self.BG, fg=self.FG).pack(side="left", padx=(12,4))
        self.find_entry = tk.Entry(tb)
        self.find_entry.pack(side="left", ipadx=3)
        _mkbtn(tb, "Go", self._find_and_select).pack(side="left", padx=(4,0))

        pw = ttk.Panedwindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=self.PAD, pady=(4, self.PAD))

        left = tk.Frame(pw, bg=self.PANEL, highlightthickness=1, highlightbackground="#153242")
        pw.add(left, weight=1)

        left_header = tk.Frame(left, bg=self.PANEL)
        left_header.pack(fill="x", padx=self.PAD, pady=(self.PAD, 6))
        self.lbl_left_title = tk.Label(left_header, text="—", bg=self.PANEL, fg=self.FG, font=("Segoe UI", 14, "bold"))
        self.lbl_left_title.pack(anchor="w")
        self.lbl_left_parents = tk.Label(left_header, text="", bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 12))
        self.lbl_left_parents.pack(anchor="w", pady=(2,0))

        # ✅ Proper traits box for the explorer
        traits_box = tk.LabelFrame(left, text="Traits", bg=self.PANEL, fg=self.FG, labelanchor="nw")
        traits_box.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        self.traits_container = tk.Frame(traits_box, bg=self.PANEL)
        self.traits_container.pack(fill="both", expand=True, padx=6, pady=6)

        list_box = tk.LabelFrame(left, text="Archived plants", bg=self.PANEL, fg=self.FG, labelanchor="nw")
        list_box.pack(fill="both", expand=False, padx=self.PAD, pady=(0, self.PAD))
        list_wrap = tk.Frame(list_box, bg=self.PANEL)
        list_wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self.listbox = tk.Listbox(list_wrap, height=10)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        sb = tk.Scrollbar(list_wrap, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        center = tk.Frame(pw, bg=self.PANEL, highlightthickness=1, highlightbackground="#153242")
        pw.add(center, weight=3)

        toggles = tk.Frame(center, bg=self.PANEL)
        toggles.pack(fill="x", padx=self.PAD, pady=(self.PAD, 6))
        self.trait_mode = tk.StringVar(value="Flowers")
        try:
            self.trait_mode.trace_add('write', lambda *a: self._refresh_views())
        except Exception:
            pass

        for label in ("Flowers", "Pod color", "Pod shape", "Seed color", "Seed shape", "Height"):
            rb = tk.Radiobutton(toggles, text=label, variable=self.trait_mode, value=label,
                                bg=self.PANEL, fg=self.FG, selectcolor=self.CARD, activebackground=self.PANEL,
                                indicatoron=True, command=lambda: self._draw_canvas_family(getattr(self, "current_pid", None)))
            rb.pack(side="left", padx=(0,12))

        self.canvas = tk.Canvas(center, bg="#0b1a22", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        right = tk.Frame(pw, bg=self.PANEL, highlightthickness=1, highlightbackground="#153242")
        pw.add(right, weight=2)

        # Export traits of the currently selected plant to CSV
        try:
            _mkbtn(
                right,
                " Click to Export Plant / Test Mendelian Laws ",
                self._export_selected_traits
            ).pack(anchor="ne", padx=self.PAD, pady=(self.PAD, 4))

        except Exception:
            pass

        parents_box = tk.LabelFrame(right, text="Parents", bg=self.PANEL, fg=self.FG, labelanchor="nw")
        parents_box.pack(fill="x", padx=self.PAD, pady=(self.PAD, 6))
        self.lbl_parents_right = tk.Label(parents_box, text="—", bg=self.PANEL, fg=self.MUTED)
        self.lbl_parents_right.pack(anchor="w", padx=6, pady=6)

        # Flat siblings area (no inner LabelFrame; no nested "window")
        self.sibs_inner = tk.Frame(right, bg=self.PANEL)
        self.sibs_inner.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        self._img_refs = []
        self._all_ids, self._ids = [], []
        self.current_pid = None
        self.preview_pid = None  # preview of an ancestor without switching selection
        # Icon scales (1 = native size)
        self.SCALE_NODE = 1
        self.SCALE_TRAIT = 1
        self.SCALE_SIB = 1
        # Vertical spacing scale for tree (1.0 = default)
        self.SPACING_SCALE_Y = 0.75
        # Visual style
        self.NODE_OUTER_W = 2
        self.LINK_W = 3
        self.NODE_LABEL_DX = 40
        self.NODE_LABEL_FONT = ("Segoe UI", 12, "bold")
        self._seed_from_live()
        self._reload_ids()

        # Make sure geometry is fully laid out so canvas width/height are correct
        try:
            self.update_idletasks()
        except Exception:
            pass

        if default_pid is not None and str(default_pid) in [str(x) for x in self._ids]:
            idx = [str(x) for x in self._ids].index(str(default_pid))
            self.listbox.selection_set(idx); self.listbox.see(idx)
            self._render_pid(str(default_pid))
        elif self._ids:
            self.listbox.selection_set(0)
            self._render_pid(self._ids[0])
        else:
            self._clear_render()

    def _seed_from_live(self):
        self.app.seed_archive_from_live()

    def _reload_ids(self):
        self.listbox.delete(0, "end")
        self._all_ids.clear(); self._ids.clear()
        arch_plants = {}
        try:
            arch_plants = (self.app.archive or {}).get("plants", {}) if isinstance(
                getattr(self.app, "archive", {}), dict) else {}
        except Exception:
            arch_plants = {}
        # --- helpers for ancestry / lineage tree -------------------------
        EMPTY_PID = (None, "", -1)

        def _get_arch_snap(pid_val):
            """Return archive snapshot for a plant id (string/int), or None."""
            if pid_val in EMPTY_PID:
                return None
            key = str(pid_val)
            # direct key as string
            try:
                if key in arch_plants:
                    return arch_plants[key]
            except Exception:
                pass
            # try as int
            try:
                ikey = int(key)
                if ikey in arch_plants:
                    return arch_plants[ikey]
            except Exception:
                pass
            # fallback: string match on any key
            for k, v in arch_plants.items():
                try:
                    if str(k) == key:
                        return v
                except Exception:
                    continue
            return None

        def _genotype_string_from_snap(snap_obj):
            """Flatten genotype dict of a snapshot to 'A/a; I/I; ...'."""
            if snap_obj is None:
                return ""
            try:
                if isinstance(snap_obj, dict):
                    g = snap_obj.get("genotype")
                else:
                    g = getattr(snap_obj, "genotype", None)
            except Exception:
                g = None
            if not isinstance(g, dict):
                return ""

            loci = [loc for loc in g.keys() if not str(loc).startswith("_")]
            loci = sorted(loci, key=str)
            parts = []
            for loc in loci:
                try:
                    pair = g.get(loc, ("?", "?")) or ("?", "?")
                    a1 = pair[0] if len(pair) > 0 else "?"
                    a2 = pair[1] if len(pair) > 1 else "?"
                    parts.append(f"{a1}/{a2}")
                except Exception:
                    continue
            return "; ".join(parts)

        def _generation_from_snap(snap_obj):
            """Get generation string like 'F3' from snapshot."""
            if snap_obj is None:
                return ""
            if isinstance(snap_obj, dict):
                return snap_obj.get("generation", "")
            try:
                return getattr(snap_obj, "generation", "")
            except Exception:
                return ""

        def _build_lineage_chain(root_pid, max_depth=6):
            """
            Walk up ancestors starting from root_pid (current plant),
            following mother (if present) else father, up to max_depth.
            Returns a list of dicts; oldest ancestor first.
            """
            chain = []
            cur = root_pid
            depth = 0
            seen = set()
            while cur not in EMPTY_PID and depth < max_depth:
                if cur in seen:
                    break
                seen.add(cur)
                snap_obj = _get_arch_snap(cur)
                if not snap_obj:
                    break
                try:
                    m_id, f_id = self._parents_from_snapshot(snap_obj)
                except Exception:
                    m_id, f_id = (None, None)

                mother_snap = _get_arch_snap(m_id) if m_id not in EMPTY_PID else None
                father_snap = _get_arch_snap(f_id) if f_id not in EMPTY_PID else None

                node = {
                    "pid": cur,
                    "gen": _generation_from_snap(snap_obj),
                    "mother": m_id,
                    "father": f_id,
                    "geno": _genotype_string_from_snap(snap_obj),
                    "geno_m": _genotype_string_from_snap(mother_snap) if mother_snap else "",
                    "geno_f": _genotype_string_from_snap(father_snap) if father_snap else "",
                }
                chain.append(node)

                # go "up": prefer mother if available, else father
                nxt = m_id if m_id not in EMPTY_PID else f_id
                if nxt in EMPTY_PID or nxt == cur:
                    break
                cur = nxt
                depth += 1

            # collected from leaf → root, so reverse to oldest → leaf
            chain.reverse()
            return chain

        def _lineage_tree_lines(root_pid):
            """
            Produce a visually nicer ASCII mini-tree with alleles and cross info,
            ending at root_pid (this plant). If a node is a cross (♀ != ♂),
            show parental alleles directly under that node.
            """
            chain = _build_lineage_chain(root_pid)
            if not chain:
                return []

            lines_local = []
            indent = ""
            root_str = str(root_pid)

            for idx, node in enumerate(chain):
                pid_str = str(node["pid"])
                gen_str = node["gen"] or ""
                is_leaf = (pid_str == root_str)
                m_id = node["mother"]
                f_id = node["father"]

                # cross information
                cross_info = ""
                if m_id not in EMPTY_PID or f_id not in EMPTY_PID:
                    if m_id == f_id and m_id not in EMPTY_PID:
                        # selfing
                        if is_leaf:
                            cross_info = f"(this plant, selfed from #{m_id})"
                        else:
                            cross_info = f"(selfed from #{m_id})"
                    else:
                        # proper cross
                        cross_info = f"(♀#{m_id} × ♂#{f_id})"
                elif is_leaf:
                    cross_info = "(this plant)"

                # main line: first ancestor uses a bullet, children use connectors
                if idx == 0:
                    base = f"{indent}# {pid_str}"
                else:
                    base = f"{indent}└─ # {pid_str}"

                if gen_str:
                    base += f" [{gen_str}]"
                if cross_info:
                    base += f" {cross_info}"

                lines_local.append(base.rstrip())

                # own alleles
                if node["geno"]:
                    lines_local.append(f"{indent}   alleles: {node['geno']}")

                # if real cross (two distinct parents), show parental alleles
                have_cross = (
                    m_id not in EMPTY_PID
                    and f_id not in EMPTY_PID
                    and m_id != f_id
                )
                if have_cross:
                    if node["geno_m"]:
                        lines_local.append(
                            f"{indent}   ♀#{m_id} alleles: {node['geno_m']}"
                        )
                    if node["geno_f"]:
                        lines_local.append(
                            f"{indent}   ♂#{f_id} alleles: {node['geno_f']}"
                        )

                # connector downwards, except for last (leaf)
                if idx < len(chain) - 1:
                    lines_local.append(f"{indent}   │")
                    indent += "   "

            return lines_local

        ls_plants = {}
        try:
            ls_plants = (getattr(self.app, "lineage_store", {}) or {}).get("plants", {})
        except Exception:
            ls_plants = {}
        keys = set()
        for k in getattr(arch_plants, "keys", lambda: [])():
            keys.add(str(k))
        for k in getattr(ls_plants, "keys", lambda: [])():
            keys.add(str(k))
        def _key(k):
            try: return (0, int(k))
            except Exception: return (1, str(k))
        for ks in sorted(keys, key=_key):
            self._all_ids.append(ks); self._ids.append(ks)
            self.listbox.insert("end", f"#{ks}")
        if not self._ids:
            self.listbox.insert("end", "(archive empty)")


    def _find_and_select(self):
        val = (self.find_entry.get() or "").strip()
        if not val:
            return
        target = None
        try:
            vi = int(val)
            if str(vi) in [str(x) for x in self._ids]:
                target = str(vi)
        except Exception:
            pass
        if target is None:
            for pid in self._ids:
                if str(pid) == val:
                    target = str(pid); break
        if target is None:
            return
        idx = [str(x) for x in self._ids].index(str(target))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx); self.listbox.see(idx)
        self._render_pid(target)

    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        if 0 <= idx < len(self._ids):
            self._render_pid(self._ids[idx])

    def _get_snap(self, pid):
        # Archive + lineage_store aware; robust id matching
        if pid is None:
            return None
        key = str(pid)
        app = getattr(self, "app", None)
        try:
            arch = getattr(app, "archive", {}) or {}
            plants = arch.get("plants", {}) if isinstance(arch, dict) else {}
            if key in plants: 
                return plants[key]
            for k, v in plants.items():
                try:
                    if str(k) == key: return v
                except Exception:
                    continue
        except Exception:
            pass
        try:
            ls = getattr(app, "lineage_store", {}) or {}
            plants = ls.get("plants", {})
            if key in plants:
                return plants[key]
            for k, v in plants.items():
                try:
                    if str(k) == key: return v
                except Exception:
                    continue
        except Exception:
            pass
        try:
            if hasattr(app, "_archive_get_ultra"):
                return app._archive_get_ultra(key)
        except Exception:
            pass
        try:
            if hasattr(app, "_archive_get"):
                return app._archive_get(key)
        except Exception:
            pass
        return None

    def _clear_render(self):
        self.lbl_left_title.config(text="—")
        self.lbl_left_parents.config(text="")
        self.lbl_parents_right.config(text="—")
        for w in self.traits_container.winfo_children(): w.destroy()
        for w in self.sibs_inner.winfo_children(): w.destroy()
        self.canvas.delete("all")
        self.canvas.create_text(20, 20, anchor="nw", text="Archive-only canvas (waiting for selection)", fill=self.MUTED, font=("Segoe UI", 12))

    def _parse_gen(self, gen_str):
        try:
            m = re.search(r'F(\\d+)', str(gen_str))
            return int(m.group(1)) if m else None
        except Exception:
            return None

    def _parents_from_snapshot(self, snap):
        """Return (mother_id, father_id) by scanning common cross/emasculation keys, including nested dicts."""
        if not isinstance(snap, dict):
            return (getattr(snap, "mother_id", None), getattr(snap, "father_id", None))

        MOTHER_KEYS = [
            "mother_id","mother","maternal_id","mom_id",
            "female_parent","female_id","dam_id",
            "seed_parent_id","seed_parent","maternal_pid","female",
        ]
        FATHER_KEYS = [
            "father_id","father","paternal_id","dad_id",
            "male_parent","male_id","sire_id",
            "pollen_donor_id","pollen_source_id","pollen_parent_id","pollinator_id",
            "pollen_donor","pollen_source","pollen",
        ]
        NESTED = ["pollination","cross","cross_info","seed_source","source_pod","source_cross","repro","reproduction"]

        def pick(dct, keys):
            for k in keys:
                if isinstance(dct, dict) and k in dct and dct[k] not in (None, "", -1):
                    return dct[k]
            return None

        mid = pick(snap, MOTHER_KEYS)
        fid = pick(snap, FATHER_KEYS)
        if mid is None or fid is None:
            for nk in NESTED:
                nd = snap.get(nk)
                if isinstance(nd, dict):
                    if mid is None: mid = pick(nd, MOTHER_KEYS)
                    if fid is None: fid = pick(nd, FATHER_KEYS)
        return (mid, fid)

    def _archive_backfill_cross_parents(self):
        """Fill missing father_id/mother_id from alternate fields (flat + nested). Non-destructive if already set."""
        arch = getattr(self.app, "archive", {})
        plants = arch.get("plants", {})
        if not isinstance(plants, dict):
            return 0

        MOTHER_KEYS = ["mother_id","mother","maternal_id","mom_id","female_parent","female_id","dam_id","seed_parent_id","seed_parent","maternal_pid","female"]
        FATHER_KEYS = ["father_id","father","paternal_id","dad_id","male_parent","male_id","sire_id","pollen_donor_id","pollen_source_id","pollen_parent_id","pollinator_id","pollen_donor","pollen_source","pollen"]
        NESTED = ["pollination","cross","cross_info","seed_source","source_pod","source_cross","repro","reproduction"]

        def pick(dct, keys):
            for k in keys:
                if isinstance(dct, dict) and k in dct and dct[k] not in (None, "", -1):
                    return dct[k]
            return None

        changes = 0
        for pid, snap in plants.items():
            if not isinstance(snap, dict):
                continue
            if snap.get("father_id") in (None, "", -1):
                cand = pick(snap, FATHER_KEYS)
                if cand is None:
                    for nk in NESTED:
                        nd = snap.get(nk)
                        if isinstance(nd, dict):
                            cand = pick(nd, FATHER_KEYS)
                            if cand is not None: break
                if cand is not None:
                    snap["father_id"] = cand; changes += 1
            if snap.get("mother_id") in (None, "", -1):
                cand = pick(snap, MOTHER_KEYS)
                if cand is None:
                    for nk in NESTED:
                        nd = snap.get(nk)
                        if isinstance(nd, dict):
                            cand = pick(nd, MOTHER_KEYS)
                            if cand is not None: break
                if cand is not None:
                    snap["mother_id"] = cand; changes += 1
        return changes

    def _export_selected_traits(self):
        """Export detailed information about the currently selected plant
        in the Trait Inheritance Explorer to a CSV file (TRAITS_CSV).

        Includes:
        - plant id, generation, parents
        - phenotypic traits
        - genotype (flattened string, if present)
        - ancestry (if present)
        - sibling trait distributions + reduced ratios and sample sizes
        """

        # Determine selection (fallback to currently rendered plant)
        pid = None
        try:
            sel = self.listbox.curselection()
        except Exception:
            sel = ()

        if sel:
            idx = sel[0]
            try:
                if 0 <= idx < len(self._ids):
                    pid = self._ids[idx]
            except Exception:
                pid = None

        # Fallback: use currently rendered plant id
        if pid is None:
            pid = getattr(self, "current_pid", None)

        if pid in (None, "", -1):
            try:
                messagebox.showinfo("Export traits", "Please select a plant in the list first.")
            except Exception:
                pass
            return

        snap = self._get_snap(pid)
        if not snap:
            try:
                messagebox.showerror("Export traits", f"No archive snapshot found for plant #{pid}.")
            except Exception:
                pass
            return

        def _g(s, key, default=None):
            if isinstance(s, dict):
                return s.get(key, default)
            try:
                return getattr(s, key, default)
            except Exception:
                return default

        # Basic metadata
        gen = _g(snap, "generation", "")
        try:
            mid, fid = self._parents_from_snapshot(snap)
        except Exception:
            mid, fid = (_g(snap, "mother_id", ""), _g(snap, "father_id", ""))

        # Traits dict
        try:
            if isinstance(snap, dict):
                traits = dict(snap.get("traits", {}) or {})
            else:
                traits = dict(getattr(snap, "traits", {}) or {})
        except Exception:
            traits = {}

        # Genotype, if present
        try:
            if isinstance(snap, dict):
                genotype_obj = snap.get("genotype")
            else:
                genotype_obj = getattr(snap, "genotype", None)
        except Exception:
            genotype_obj = None
        
        geno_str = ""
        if isinstance(genotype_obj, dict):
            # New export format: just A/a, I/I, a/a… (no leading "A:" etc.)
            parts = []
            # Optional: stable ordering of loci
            loci = [loc for loc in genotype_obj.keys() if not str(loc).startswith("_")]
            loci = sorted(loci, key=str)
            for loc in loci:
                try:
                    pair = genotype_obj.get(loc, ("?", "?")) or ("?", "?")
                    a1 = pair[0] if len(pair) > 0 else "?"
                    a2 = pair[1] if len(pair) > 1 else "?"
                    parts.append(f"{a1}/{a2}")
                except Exception:
                    continue
            geno_str = "; ".join(parts)

        # Ancestry fields (if present)
        def _list_to_str(v):
            try:
                if isinstance(v, (list, tuple)):
                    return ";".join(str(x) for x in v)
                return str(v)
            except Exception:
                return ""

        ancestry = ""
        paternal_ancestry = ""
        try:
            ancestry = _list_to_str(_g(snap, "ancestry", "")) or ""
        except Exception:
            pass
        try:
            paternal_ancestry = _list_to_str(_g(snap, "paternal_ancestry", "")) or ""
        except Exception:
            pass

        # Helper to read trait from any snapshot structure
        def _trait_from_snap(s, key):
            # direct dict-style traits
            if isinstance(s, dict):
                try:
                    t = s.get("traits")
                    if isinstance(t, dict) and key in t and t[key] is not None:
                        return t[key]
                except Exception:
                    pass
                if key in s and s[key] is not None:
                    return s[key]
            # object with .traits
            try:
                t = getattr(s, "traits", None)
                if isinstance(t, dict) and key in t and t[key] is not None:
                    return t[key]
            except Exception:
                pass
            # simple attribute
            try:
                v = getattr(s, key, None)
                if v is not None:
                    return v
            except Exception:
                pass
            return None



        trait_keys = ["flower_color", "pod_color", "seed_color", "seed_shape", "plant_height"]
        sib_counters = {k: Counter() for k in trait_keys}

        # Iterate over archived plants to collect siblings (same parents)
        try:
            arch = getattr(self.app, "archive", {}) or {}
            arch_plants = arch.get("plants", {}) if isinstance(arch, dict) else {}
        except Exception:
            arch_plants = {}
        # --- helpers for ancestry / lineage tree -------------------------
        EMPTY_PID = (None, "", -1)

        def _get_arch_snap(pid_val):
            """Return archive snapshot for a plant id (string/int), or None."""
            if pid_val in EMPTY_PID:
                return None
            key = str(pid_val)
            try:
                if key in arch_plants:
                    return arch_plants[key]
            except Exception:
                pass
            try:
                ikey = int(key)
                if ikey in arch_plants:
                    return arch_plants[ikey]
            except Exception:
                pass
            for k, v in arch_plants.items():
                try:
                    if str(k) == key:
                        return v
                except Exception:
                    continue
            return None
        
        def _genotype_string_from_snap(snap_obj):
            """
            Flatten genotype dict of a snapshot to 'R/r; I/I; A/a; ...'
            (no leading 'R:' etc., just the allele pairs, same style as Genotype).
            """
            if snap_obj is None:
                return ""
            try:
                if isinstance(snap_obj, dict):
                    g = snap_obj.get("genotype")
                else:
                    g = getattr(snap_obj, "genotype", None)
            except Exception:
                g = None
            if not isinstance(g, dict):
                return ""

            # Optional: sort loci so the order is stable
            loci = [loc for loc in g.keys() if not str(loc).startswith("_")]
            loci = sorted(loci, key=str)

            parts = []
            for loc in loci:
                try:
                    pair = g.get(loc, ("?", "?")) or ("?", "?")
                    a1 = pair[0] if len(pair) > 0 else "?"
                    a2 = pair[1] if len(pair) > 1 else "?"
                    parts.append(f"{a1}/{a2}")
                except Exception:
                    continue
            return "; ".join(parts)

        def _generation_from_snap(snap_obj):
            """Get generation string like 'F3' from snapshot."""
            if snap_obj is None:
                return ""
            if isinstance(snap_obj, dict):
                return snap_obj.get("generation", "")
            try:
                return getattr(snap_obj, "generation", "")
            except Exception:
                return ""

        def _build_lineage_chain(root_pid, max_depth=6):
            """
            Walk up ancestors starting from root_pid (current plant),
            following mother (if present) else father, up to max_depth.
            Returns a list of dicts; oldest ancestor first.
            """
            chain = []
            cur = root_pid
            depth = 0
            seen = set()
            while cur not in EMPTY_PID and depth < max_depth:
                if cur in seen:
                    break
                seen.add(cur)
                snap_obj = _get_arch_snap(cur)
                if not snap_obj:
                    break
                try:
                    m_id, f_id = self._parents_from_snapshot(snap_obj)
                except Exception:
                    m_id, f_id = (None, None)

                mother_snap = _get_arch_snap(m_id) if m_id not in EMPTY_PID else None
                father_snap = _get_arch_snap(f_id) if f_id not in EMPTY_PID else None

                node = {
                    "pid": cur,
                    "gen": _generation_from_snap(snap_obj),
                    "mother": m_id,
                    "father": f_id,
                    "geno": _genotype_string_from_snap(snap_obj),
                    "geno_m": _genotype_string_from_snap(mother_snap) if mother_snap else "",
                    "geno_f": _genotype_string_from_snap(father_snap) if father_snap else "",
                }
                chain.append(node)

                nxt = m_id if m_id not in EMPTY_PID else f_id
                if nxt in EMPTY_PID or nxt == cur:
                    break
                cur = nxt
                depth += 1

            chain.reverse()
            return chain

        def _lineage_tree_lines(root_pid):
            """
            Produce a visually nicer ASCII mini-tree with alleles and cross info,
            ending at root_pid (this plant). If a node is a cross (♀ != ♂),
            show parental alleles directly under that node.
            """
            chain = _build_lineage_chain(root_pid)
            if not chain:
                return []

            lines_local = []
            indent = ""
            root_str = str(root_pid)

            for idx, node in enumerate(chain):
                pid_str = str(node["pid"])
                gen_str = node["gen"] or ""
                is_leaf = (pid_str == root_str)
                m_id = node["mother"]
                f_id = node["father"]

                cross_info = ""
                if m_id not in EMPTY_PID or f_id not in EMPTY_PID:
                    if m_id == f_id and m_id not in EMPTY_PID:
                        if is_leaf:
                            cross_info = f"(this plant, selfed from #{m_id})"
                        else:
                            cross_info = f"(selfed from #{m_id})"
                    else:
                        cross_info = f"(♀#{m_id} × ♂#{f_id})"
                elif is_leaf:
                    cross_info = "(this plant)"

                if idx == 0:
                    base = f"{indent}# {pid_str}"
                else:
                    base = f"{indent}└─ # {pid_str}"

                if gen_str:
                    base += f" [{gen_str}]"
                if cross_info:
                    base += f" {cross_info}"

                lines_local.append(base.rstrip())

                if node["geno"]:
                    lines_local.append(f"{indent}   alleles: {node['geno']}")

                have_cross = (
                    m_id not in EMPTY_PID
                    and f_id not in EMPTY_PID
                    and m_id != f_id
                )
                if have_cross:
                    if node["geno_m"]:
                        lines_local.append(
                            f"{indent}   ♀#{m_id} alleles: {node['geno_m']}"
                        )
                    if node["geno_f"]:
                        lines_local.append(
                            f"{indent}   ♂#{f_id} alleles: {node['geno_f']}"
                        )

                if idx < len(chain) - 1:
                    lines_local.append(f"{indent}   │")
                    indent += "   "

            return lines_local

        for cid, csnap in arch_plants.items():
            try:
                m2, f2 = self._parents_from_snapshot(csnap)
            except Exception:
                m2, f2 = (None, None)

            same = False
            try:
                if mid not in (None, "", -1) or fid not in (None, "", -1):
                    if mid not in (None, "", -1) and fid not in (None, "", -1):
                        same = (m2 == mid and f2 == fid)
                    elif mid not in (None, "", -1):
                        same = (m2 == mid)
                    elif fid not in (None, "", -1):
                        same = (f2 == fid)
            except Exception:
                same = False
            if not same:
                continue

            for tk in trait_keys:
                v = _trait_from_snap(csnap, tk)
                if v:
                    val = str(v).lower()
                    sib_counters[tk][val] += 1

        def _reduced_ratio(counter):
            """
            Convert counts to a decimal ratio of the form X:1
            Example: {a:13, b:4} → "3,25:1"
            """
            vals = [int(c) for c in counter.values() if c > 0]

            if len(vals) < 2:
                return ""

            a = max(vals)
            b = min(vals)
            if b == 0:
                return ""

            ratio = a / b
            # two decimal places
            formatted = f"{ratio:.2f}"
            # comma instead of dot
            formatted = formatted.replace(".", ",")

            return f"{formatted}:1"


        def _fmt_counts(counter):
            return "; ".join(f"{k}={v}" for k, v in sorted(counter.items()))

        sib_counts = {}
        sib_ratios = {}
        sib_ns = {}
        for tk in trait_keys:
            c = sib_counters[tk]
            sib_counts[tk] = _fmt_counts(c)
            sib_ratios[tk] = _reduced_ratio(c)
            sib_ns[tk] = sum(c.values())

        
        
        # Prepare a human-readable text export for this plant.
        # Each export creates a separate .txt file for the selected plant.
        label = ""
        try:
            if isinstance(snap, dict):
                label = snap.get("label") or ""
            else:
                label = getattr(snap, "label", "") or ""
        except Exception:
            label = ""
        if not label:
            try:
                label = f"Plant {gen or ''} #{pid}"
            except Exception:
                label = str(pid)

        lines = []

        def _add_line(text=""):
            try:
                lines.append(str(text))
            except Exception:
                lines.append("")

        # Header
        _add_line(f"Plant ID     : {pid}")
        _add_line(f"Generation   : {gen or ''}")
        _add_line(f"Mother ID    : {'' if mid in (None, '', -1) else mid}")
        _add_line(f"Father ID    : {'' if fid in (None, '', -1) else fid}")
        _add_line(f"Ancestry     : {ancestry}")
        _add_line(f"Paternal anc.: {paternal_ancestry}")

        def _law1_cross_signature_for_trait(m_snap, f_snap, locus):
            """
            Return a canonical 'cross type' signature for a Law 1 test:
            - both parents homozygous at this locus
            - homozygous for DIFFERENT alleles (e.g. AA vs aa)
            - ignore concrete plant IDs and ♂/♀ order
            """
            m_geno = _geno_from_snap(m_snap)
            f_geno = _geno_from_snap(f_snap)
            if not isinstance(m_geno, dict) or not isinstance(f_geno, dict):
                return None

            m_pair = m_geno.get(locus)
            f_pair = f_geno.get(locus)
            if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2):
                return None
            if not (isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
                return None

            m_a1, m_a2 = m_pair[0], m_pair[1]
            f_a1, f_a2 = f_pair[0], f_pair[1]

            # both parents homozygous
            if not (m_a1 == m_a2 and f_a1 == f_a2):
                return None
            # alleles must differ
            if m_a1 == f_a1:
                return None

            def _canon(pair):
                a1, a2 = pair[0], pair[1]
                return "".join(sorted([str(a1), str(a2)]))

            # order-independent: AA×aa == aa×AA
            return tuple(sorted([_canon(m_pair), _canon(f_pair)]))

        # --- Genotype reveal / cheat status ---------------------------------
        app = getattr(self, "app", None)
        if app is not None:
            revealed = bool(getattr(app, "_genotype_revealed", False))
        else:
            revealed = False

        # --- Law 1 (Dominance) detection for THIS plant --------------------
        law1_discovered = False
        law1_reason = ""

        # --- Law 2 (Segregation) detection for THIS plant ------------------
        law2_discovered = False
        law2_reason = ""
        law2_ratio_str = ""      # e.g. "3,21:1"
        law2_trait_name = ""     # human-readable trait label

        # --- Law 3 (Independent Assortment) detection for THIS plant -------
        law3_discovered = False
        law3_reason = ""
        law3_ratio_str = ""      # e.g. "45:14:15:6" or "9:3:3:1"
        law3_trait_pair = ()     # (trait_label1, trait_label2)



        # Only consider if the player did NOT use the genotype reveal cheat.
        if not revealed:
            # Try to get parent snapshots from the archive
            try:
                mother_snap = _get_arch_snap(mid)
            except Exception:
                mother_snap = None
            try:
                father_snap = _get_arch_snap(fid)
            except Exception:
                father_snap = None

            # We only credit Law of Dominance if:
            # - both parents are known
            # - they are not the same plant (i.e. a true cross, not selfing)
            if mother_snap and father_snap and mid not in (None, "", -1) and fid not in (None, "", -1) and str(mid) != str(fid):
                # Phenotypes for parents + child
                try:
                    m_traits = dict(mother_snap.get("traits", {}) or {}) if isinstance(mother_snap, dict) else dict(getattr(mother_snap, "traits", {}) or {})
                except Exception:
                    m_traits = {}
                try:
                    f_traits = dict(father_snap.get("traits", {}) or {}) if isinstance(father_snap, dict) else dict(getattr(father_snap, "traits", {}) or {})
                except Exception:
                    f_traits = {}

                # Helper: safely extract genotype dict from any snapshot/proxy
                def _geno_from_snap(s):
                    try:
                        if isinstance(s, dict):
                            g = s.get("genotype") or {}
                        else:
                            g = getattr(s, "genotype", None) or {}
                    except Exception:
                        g = {}
                    return dict(g) if isinstance(g, dict) else {}

                m_geno = _geno_from_snap(mother_snap)
                f_geno = _geno_from_snap(father_snap)

                # Trait → locus mapping (single-locus traits only)
                trait_to_locus = {
                    "flower_color":  "A",
                    "pod_color":     "Gp",
                    "seed_color":    "I",
                    "seed_shape":    "R",
                    "plant_height":  "Le",
                }

                # Traits we care about (same as in sibling analysis)
                law_trait_keys = ["flower_color", "pod_color", "seed_color", "seed_shape", "plant_height"]

                # For sibling counting we need access to the whole archive
                app_obj = getattr(self, "app", None)
                try:
                    arch = getattr(app_obj, "archive", {}) if app_obj else {}
                    arch_plants = arch.get("plants", {}) if isinstance(arch, dict) else {}
                    if not isinstance(arch_plants, dict):
                        arch_plants = {}
                except Exception:
                    arch_plants = {}

                def _g_from_snap(s, key, default=None):
                    if isinstance(s, dict):
                        return s.get(key, default)
                    try:
                        return getattr(s, key, default)
                    except Exception:
                        return default

                # Normalize parent IDs for comparison
                mid_norm = str(mid)
                fid_norm = str(fid)

                dominant_candidates = []

                for tk in law_trait_keys:
                    cv = str(traits.get(tk, "")).strip()
                    mv = str(m_traits.get(tk, "")).strip()
                    fv = str(f_traits.get(tk, "")).strip()

                    # --- 1) Phenotypic dominance pattern --------------------
                    # - both parents have a clear phenotype
                    # - phenotypes are different
                    # - the child matches EXACTLY one of them
                    if not (cv and mv and fv and mv != fv and (cv == mv or cv == fv)):
                        continue

                    # --- 2) Parents must be homozygous for different alleles at the locus ---
                    loc = trait_to_locus.get(tk)
                    if not loc:
                        continue

                    # Get the cross signature for THIS plant's parents
                    cross_sig = _law1_cross_signature_for_trait(mother_snap, father_snap, loc)
                    if cross_sig is None:
                        # parents aren’t pure opposite at this locus
                        continue


                    m_pair = m_geno.get(loc)
                    f_pair = f_geno.get(loc)

                    # Need valid allele pairs
                    if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2 and
                            isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
                        continue

                    m_a1, m_a2 = m_pair[0], m_pair[1]
                    f_a1, f_a2 = f_pair[0], f_pair[1]

                    # Both parents homozygous (AA vs aa, LeLe vs lele, etc.)
                    if not (m_a1 == m_a2 and f_a1 == f_a2):
                        continue

                    # And homozygous for *different* alleles (AA vs aa, not AA vs AA)
                    if m_a1 == f_a1:
                        continue

                    # Count all F1 from the same genetic cross type, alive only
                    same_pheno_total = 0

                    for cid, csnap in arch_plants.items():
                        # ✅ Only living plants count
                        if not csnap.get("alive", True):
                            continue

                        # Must have both parents recorded
                        smid = _g_from_snap(csnap, "mother_id", None)
                        sfid = _g_from_snap(csnap, "father_id", None)
                        if smid in (None, "", -1) or sfid in (None, "", -1):
                            continue

                        # Get those parents’ snapshots
                        m_snap2 = _get_arch_snap(smid)
                        f_snap2 = _get_arch_snap(sfid)
                        if not m_snap2 or not f_snap2:
                            continue

                        # Same genetic cross type?
                        sig2 = _law1_cross_signature_for_trait(m_snap2, f_snap2, loc)
                        if sig2 is None or sig2 != cross_sig:
                            continue

                        # Same trait, same phenotype as this plant?
                        try:
                            s_traits = csnap.get("traits", {}) if isinstance(csnap, dict) else getattr(csnap, "traits", {}) or {}
                        except Exception:
                            s_traits = {}
                        sv = str(s_traits.get(tk, "")).strip()

                        if sv == cv:  # cv = current plant’s phenotype for tk
                            same_pheno_total += 1


                    # Need at least 15 plant with the same phenotype
                    if same_pheno_total < LAW1_MIN_F1:
                        continue


                    # Record this trait as a valid Law-1 candidate
                    dominant_candidates.append((tk, cv, mv, fv, same_pheno_total))

                if dominant_candidates:
                    law1_discovered = True
                    # Take the first trait as an example for the explanation
                    tk, cv, mv, fv, sib_count = dominant_candidates[0]
                    trait_label = tk.replace("_", " ")
                    law1_reason = (
                        f"Observed in cross #{mid} × #{fid} for trait '{trait_label}': "
                        f"parents {mv} × {fv} → offspring {cv} "
                        f"in at least {sib_count + 1} F1 plants (including this plant), "
                        f"from true-breeding parental lines."
                    )

        def _law2_family_signature(parent_snap, gp_m, gp_f, locus):
            """
            Signature for a Law 2 experiment:
            - F1 is heterozygous at 'locus'
            - Grandparents are homozygous at 'locus'
            
            Note: Grandparents may have same or different alleles (AA×AA, aa×aa, or AA×aa).
            Mendel established true-breeding lines via selfing before crossing them.
            """
            parent_geno = _geno_from_snap_law2(parent_snap)
            if not isinstance(parent_geno, dict):
                return None
            p_pair = parent_geno.get(locus)
            if not (isinstance(p_pair, (list, tuple)) and len(p_pair) >= 2):
                return None
            pa1, pa2 = p_pair[0], p_pair[1]

            # F1 must be heterozygous
            if pa1 == pa2:
                return None

            gm_geno = _geno_from_snap_law2(gp_m)
            gf_geno = _geno_from_snap_law2(gp_f)
            if not isinstance(gm_geno, dict) or not isinstance(gf_geno, dict):
                return None

            m_pair = gm_geno.get(locus)
            f_pair = gf_geno.get(locus)
            if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2):
                return None
            if not (isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
                return None

            m_a1, m_a2 = m_pair[0], m_pair[1]
            f_a1, f_a2 = f_pair[0], f_pair[1]

            # Grandparents must be homozygous
            if not (m_a1 == m_a2 and f_a1 == f_a2):
                return None
            # REMOVED: if m_a1 == f_a1: return None
            # This check rejected selfed true-breeding lines (e.g., AA × AA).
            # Mendel's method: self-pollinate to establish homozygous lines,
            # then cross them. As long as parent is heterozygous and grandparents
            # are homozygous, we have valid segregation.

            def _canon(pair):
                a1, a2 = pair[0], pair[1]
                return "".join(sorted([str(a1), str(a2)]))

            return tuple(sorted([_canon(m_pair), _canon(f_pair)]))

        # --------------------------------------------------------------------
        # --- Law 2 (Segregation) detection (builds on Law 1 F1) --------
        # ✅ Accept both:
        #   - classic selfing:   Aa x Aa where mother==father (same plant)
        #   - Mendel-style F1 sib mating: Aa x Aa where mother!=father but same true-breeding origin
        try:
            has_parents = (mid not in (None, "", -1) and fid not in (None, "", -1))
        except Exception:
            has_parents = False

        parent_snap_m = _get_arch_snap(mid) if has_parents else None
        parent_snap_f = _get_arch_snap(fid) if has_parents else None

        if parent_snap_m and parent_snap_f:
            # Use mother as the "reference F1" for dominant phenotype labels etc.
            parent_snap = parent_snap_m
            other_parent_snap = parent_snap_f

            # Parent traits (reference)
            try:
                if isinstance(parent_snap, dict):
                    parent_traits = dict(parent_snap.get("traits", {}) or {})
                else:
                    parent_traits = dict(getattr(parent_snap, "traits", {}) or {})
            except Exception:
                parent_traits = {}

            # Helper: get genotype dict from any snapshot/proxy
            def _geno_from_snap_law2(s):
                try:
                    if isinstance(s, dict):
                        g = s.get("genotype") or {}
                    else:
                        g = getattr(s, "genotype", {}) or {}
                except Exception:
                    g = {}
                if not isinstance(g, dict):
                    return {}
                return g

            # Helper: grandparents of ANY snapshot (parents of that snapshot)
            def _get_grandparents_of(psnap):
                try:
                    pmid_x, pfid_x = self._parents_from_snapshot(psnap)
                except Exception:
                    pmid_x = _g(psnap, "mother_id", None)
                    pfid_x = _g(psnap, "father_id", None)

                return _get_arch_snap(pmid_x), _get_arch_snap(pfid_x)

            # Grandparents of BOTH parents (needed to verify "same experiment family")
            gp_m, gp_f = _get_grandparents_of(parent_snap)
            gp_m_other, gp_f_other = _get_grandparents_of(other_parent_snap)

            # Trait → locus mapping and trait list (as in Law 1)
            trait_to_locus = {
                "flower_color":   "A",
                "pod_color":      "Gp",
                "seed_color":     "I",
                "seed_shape":     "R",
                "plant_height":   "Le",
            }

            law_trait_keys = [
                "flower_color",
                "pod_color",
                "seed_color",
                "seed_shape",
                "plant_height",
            ]

            # Pick the trait whose dominant fraction is *closest* to 3:1
            best_law2_delta = None
            best_law2_payload = None

            if parent_snap:
                # Parent traits (F1 phenotype)
                try:
                    if isinstance(parent_snap, dict):
                        parent_traits = dict(parent_snap.get("traits", {}) or {})
                    else:
                        parent_traits = dict(getattr(parent_snap, "traits", {}) or {})
                except Exception:
                    parent_traits = {}

                # Helper: get genotype dict from any snapshot/proxy
                def _geno_from_snap_law2(s):
                    try:
                        if isinstance(s, dict):
                            g = s.get("genotype") or {}
                        else:
                            g = getattr(s, "genotype", None) or {}
                    except Exception:
                        g = {}
                    return dict(g) if isinstance(g, dict) else {}

                parent_geno = _geno_from_snap_law2(parent_snap)

                # Grandparents of the current plant (parents of the F1)
                try:
                    pmid, pfid = self._parents_from_snapshot(parent_snap)
                except Exception:
                    pmid, pfid = (
                        _g(parent_snap, "mother_id", None),
                        _g(parent_snap, "father_id", None),
                    )

                gp_m = _get_arch_snap(pmid)
                gp_f = _get_arch_snap(pfid)

                # Trait → locus mapping and trait list (as in Law 1)
                trait_to_locus = {
                    "flower_color":  "A",
                    "pod_color":     "Gp",
                    "seed_color":    "I",
                    "seed_shape":    "R",
                    "plant_height":  "Le",
                }
                law_trait_keys = [
                    "flower_color",
                    "pod_color",
                    "seed_color",
                    "seed_shape",
                    "plant_height",
                ]

                # Pick the trait whose dominant fraction is *closest* to 3:1
                best_law2_delta = None
                best_law2_payload = None

                for tk in law_trait_keys:
                    loc = trait_to_locus.get(tk)
                    if not loc:
                        continue

                    # Parent (F1) must be heterozygous at this locus
                    pair_p = parent_geno.get(loc)
                    if not (isinstance(pair_p, (list, tuple)) and len(pair_p) >= 2):
                        continue
                    if len(set(pair_p[:2])) != 2:
                        continue  # not Aa

                    # Build a canonical Law-2 family signature (F1 + grandparents)
                    fam_sig = _law2_family_signature(parent_snap, gp_m, gp_f, loc)
                    fam_sig_other = _law2_family_signature(other_parent_snap, gp_m_other, gp_f_other, loc)

                    # ✅ Require BOTH parents to be valid F1 (Aa) from the same AA×aa setup
                    if fam_sig is None or fam_sig_other is None or fam_sig_other != fam_sig:
                        continue

                    # Grandparents must be true-breeding for opposite alleles (AA vs aa)
                    ok_grand = False
                    if gp_m and gp_f:
                        gm_geno = _geno_from_snap_law2(gp_m)
                        gf_geno = _geno_from_snap_law2(gp_f)
                        m_pair = gm_geno.get(loc)
                        f_pair = gf_geno.get(loc)
                        if (
                            isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2
                            and isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2
                        ):
                            m_a1, m_a2 = m_pair[0], m_pair[1]
                            f_a1, f_a2 = f_pair[0], f_pair[1]
                            if m_a1 == m_a2 and f_a1 == f_a2 and m_a1 != f_a1:
                                ok_grand = True
                    if not ok_grand:
                        continue

                    # Count F2 siblings for this trait
                    counts_counter = Counter()
                    if arch_plants:
                        for sid, csnap2 in arch_plants.items():

                            # ✅ only living F2 plants count
                            if not csnap2.get("alive", True):
                                continue

                            # Who are the parents of this candidate F2?
                            try:
                                smid2, sfid2 = self._parents_from_snapshot(csnap2)
                            except Exception:
                                smid2, sfid2 = (
                                    _g(csnap2, "mother_id", None),
                                    _g(csnap2, "father_id", None),
                                )

                            # ✅ Allow Aa×Aa where mother!=father (F1 sibling mating),
                            # as long as BOTH parents belong to the same Law-2 family signature.
                            if smid2 is None or sfid2 is None:
                                continue

                            f1_m = _get_arch_snap(smid2)
                            f1_f = _get_arch_snap(sfid2)
                            if not f1_m or not f1_f:
                                continue

                            # optionally: only count F2 from living F1
                            if not f1_m.get("alive", True) or not f1_f.get("alive", True):
                                continue

                            gp_m2a, gp_f2a = _get_grandparents_of(f1_m)
                            gp_m2b, gp_f2b = _get_grandparents_of(f1_f)
                            if not gp_m2a or not gp_f2a or not gp_m2b or not gp_f2b:
                                continue

                            fam_sig2a = _law2_family_signature(f1_m, gp_m2a, gp_f2a, loc)
                            fam_sig2b = _law2_family_signature(f1_f, gp_m2b, gp_f2b, loc)

                            if (
                                fam_sig2a is None or fam_sig2b is None
                                or fam_sig2a != fam_sig or fam_sig2b != fam_sig
                            ):
                                continue

                            # Now we know this F2 belongs to the same experiment type ⇒ count it
                            sv2 = _trait_from_snap(csnap2, tk)
                            if sv2 is None:
                                continue
                            val_norm = str(sv2).strip().lower()
                            if not val_norm:
                                continue
                            counts_counter[val_norm] += 1

                    total = sum(int(c) for c in counts_counter.values())
                    if total < LAW2_MIN_N:
                        continue

                    nonzero = [
                        (str(val).strip().lower(), int(c))
                        for val, c in counts_counter.items()
                        if c > 0
                    ]
                    if len(nonzero) != 2:
                        continue

                    norm_counts = {}
                    for val_norm, c in nonzero:
                        norm_counts[val_norm] = norm_counts.get(val_norm, 0) + c

                    dom_pheno = str(parent_traits.get(tk, "")).strip().lower()
                    dom_count = norm_counts.get(dom_pheno, 0)
                    if dom_count <= 0:
                        # fall back: whichever phenotype is more frequent is "dominant"
                        dom_pheno, dom_count = max(norm_counts.items(), key=lambda kv: kv[1])

                    rec_pheno = [v for v in norm_counts.keys() if v != dom_pheno]
                    if not rec_pheno:
                        continue
                    rec_pheno = rec_pheno[0]
                    rec_count = norm_counts.get(rec_pheno, 0)
                    if rec_count <= 0:
                        continue

                    n_used = dom_count + rec_count
                    frac_dom = dom_count / float(n_used)

                    # Only accept reasonably 3:1-ish families (75–85% dom)
                    #   if not (0.75 <= frac_dom <= 0.85):

                    # morerelaxed
                    if not (LAW2_DOM_FRAC_MIN <= frac_dom <= LAW2_DOM_FRAC_MAX):
                        continue

                    # Distance from the ideal 3:1 (= 75% dominant)
                    delta = abs(frac_dom - 0.75)

                    payload = {
                        "tk": tk,
                        "trait_label": tk.replace("_", " "),
                        "dom_pheno": dom_pheno,
                        "rec_pheno": rec_pheno,
                        "norm_counts": dict(norm_counts),
                        "frac_dom": frac_dom,
                        "n_used": n_used,
                    }

                    if best_law2_delta is None or delta < best_law2_delta:
                        best_law2_delta = delta
                        best_law2_payload = payload

                # After scanning all traits, credit Law 2 for the *best* 3:1 case, if any
                if best_law2_payload is not None:
                    law2_discovered = True

                    tk = best_law2_payload["tk"]
                    trait_label = best_law2_payload["trait_label"]
                    dom_pheno = best_law2_payload["dom_pheno"]
                    rec_pheno = best_law2_payload["rec_pheno"]
                    norm_counts = best_law2_payload["norm_counts"]
                    frac_dom = best_law2_payload["frac_dom"]
                    n_used = best_law2_payload["n_used"]

                    # Use the same ratio formatting as Trait Inheritance Explorer, but WITHOUT percentages
                    vals = list(norm_counts.values())

                    law2_ratio_str = ""
                    if vals:
                        if len(vals) == 2:
                            a, b = vals
                            # Make sure a is the larger count
                            if a < b:
                                a, b = b, a
                            if b > 0:
                                x = round(a / b, 2)   # e.g. 81/26 → 3.12
                                x_str = f"{x:.2f}".replace(".", ",")
                                law2_ratio_str = f"{x_str}:1"
                            else:
                                law2_ratio_str = f"{a}:{b}"
                        else:
                            law2_ratio_str = ":".join(str(v) for v in vals)

                    law2_trait_name = trait_label

                    # parent_id no longer always exists if Law2 is based on F1 sibling crosses (mid != fid)
                    try:
                        if str(mid) == str(fid):
                            parent_label = f"{mid}"          # selfing case
                            cross_label  = f"selfed F1 plant #{parent_label}"
                        else:
                            parent_label = f"{mid}×{fid}"    # sib-mating case
                            cross_label  = f"F1 cross #{parent_label}"
                    except Exception:
                        cross_label = "F1 cross #?"

                    law2_reason = (
                        f"Observed in F2 offspring of {cross_label} for trait '{trait_label}': "
                        f"dominant '{dom_pheno}' vs recessive '{rec_pheno}' "
                        f"in approx. {frac_dom*100:.0f}% : {(1.0-frac_dom)*100:.0f}% "
                        f"(N = {n_used}), following a cross of true-breeding parental lines in the previous generation."
                    )

                    def _law3_family_signature(parent_snap, gp_m, gp_f, loc1, loc2):
                        """
                        Signature for a Law 3 dihybrid experiment:
                        - F1 (parent_snap) is heterozygous at both loci (AaBb)
                        - Grandparents (gp_m, gp_f) are true-breeding for opposite alleles
                          at both loci (AA BB vs aa bb)
                        Returns a canonical signature tuple, or None if the setup is invalid.
                        """
                        gm_geno = _geno_from_snap_law2(gp_m)
                        gf_geno = _geno_from_snap_law2(gp_f)
                        parent_geno_local = _geno_from_snap_law2(parent_snap)

                        if not (isinstance(gm_geno, dict) and isinstance(gf_geno, dict) and isinstance(parent_geno_local, dict)):
                            return None

                        p1 = parent_geno_local.get(loc1)
                        p2 = parent_geno_local.get(loc2)

                        def _is_het(pair):
                            return isinstance(pair, (list, tuple)) and len(pair) >= 2 and pair[0] != pair[1]

                        # F1 must be heterozygous at both loci (Aa, Bb)
                        if not (_is_het(p1) and _is_het(p2)):
                            return None

                        m1 = gm_geno.get(loc1); f1 = gf_geno.get(loc1)
                        m2 = gm_geno.get(loc2); f2 = gf_geno.get(loc2)

                        def _is_pure_opp(a_pair, b_pair):
                            if not (isinstance(a_pair, (list, tuple)) and len(a_pair) >= 2):
                                return False
                            if not (isinstance(b_pair, (list, tuple)) and len(b_pair) >= 2):
                                return False
                            a1, a2 = a_pair[0], a_pair[1]
                            b1, b2 = b_pair[0], b_pair[1]
                            return a1 == a2 and b1 == b2 and a1 != b1

                        # Grandparents must be AA vs aa at each locus
                        if not (_is_pure_opp(m1, f1) and _is_pure_opp(m2, f2)):
                            return None

                        def _canon(pair):
                            a1, a2 = pair[0], pair[1]
                            return "".join(sorted([str(a1), str(a2)]))

                        key1 = tuple(sorted([_canon(m1), _canon(f1)]))
                        key2 = tuple(sorted([_canon(m2), _canon(f2)]))

                        # include locus names so we don't mix e.g. A/B families with I/Le families
                        return tuple(sorted([(loc1, key1), (loc2, key2)]))

                    # --- Law 3 (Independent Assortment) detection: dihybrid F2 9:3:3:1 ---
                    # Only try if we can use the same archive + parent info we already have.
                    if not law3_discovered and gp_m and gp_f and arch_plants:

                        # Helper: “dominant phenotype” = F1 parent’s phenotype for that trait
                        parent_traits = parent_traits or {}
                        N_MIN_LAW3 = LAW3_MIN_N  # need a decent F2 sample size

                        # Only use trait pairs that:
                        #  - exist on the parent
                        #  - are not *actually linked* in pea genetics
                        candidate_traits = [
                        tk for tk in law_trait_keys
                        if tk in parent_traits and trait_to_locus.get(tk)
                    ]

                        for tk1, tk2 in combinations(candidate_traits, 2):
                            # Skip the known linked pair in peas: pod_color (Gp) and seed_shape (R)
                            # → they are on the same chromosome and do *not* assort independently.
                            if {"pod_color", "seed_shape"} == {tk1, tk2}:
                                continue

                            # 🔧 NEW: map traits to loci and guard against missing loci
                            loc1 = trait_to_locus.get(tk1)
                            loc2 = trait_to_locus.get(tk2)
                            if not loc1 or not loc2:
                                continue

                            # F1 (parent) must be heterozygous at BOTH loci
                            pair1 = parent_geno.get(loc1)
                            pair2 = parent_geno.get(loc2)
                            if not (isinstance(pair1, (list, tuple)) and len(pair1) >= 2 and
                                    isinstance(pair2, (list, tuple)) and len(pair2) >= 2):
                                continue
                            if len(set(pair1[:2])) != 2 or len(set(pair2[:2])) != 2:
                                # not AaBb
                                continue

                            # Construct dihybrid family signature for this trait pair
                            fam_sig = _law3_family_signature(parent_snap, gp_m, gp_f, loc1, loc2)
                            if fam_sig is None:
                                # F1 not AaBb or grandparents not AA/aa BB/bb → not a valid Law-3 setup
                                continue

                            # Collect F2 siblings from this selfed F1, classify by two traits
                            combo_counts = Counter()

                            dom1 = str(parent_traits.get(tk1, "")).strip().lower()
                            dom2 = str(parent_traits.get(tk2, "")).strip().lower()

                            for cid2, csnap2 in arch_plants.items():
                                # ✅ only living F2 plants
                                if not csnap2.get("alive", True):
                                    continue

                                # parents of this F2
                                try:
                                    smid2, sfid2 = self._parents_from_snapshot(csnap2)
                                except Exception:
                                    smid2, sfid2 = (
                                        _g(csnap2, "mother_id", None),
                                        _g(csnap2, "father_id", None),
                                    )

                                # ✅ Allow AaBb×AaBb where mother!=father, as long as BOTH parents
                                # belong to the same dihybrid family signature.
                                if smid2 is None or sfid2 is None:
                                    continue

                                f1_m = _get_arch_snap(smid2)
                                f1_f = _get_arch_snap(sfid2)
                                if not f1_m or not f1_f:
                                    continue

                                if not f1_m.get("alive", True) or not f1_f.get("alive", True):
                                    continue

                                gp_m2a, gp_f2a = _get_grandparents_of(f1_m)
                                gp_m2b, gp_f2b = _get_grandparents_of(f1_f)
                                if not gp_m2a or not gp_f2a or not gp_m2b or not gp_f2b:
                                    continue

                                fam_sig2a = _law3_family_signature(f1_m, gp_m2a, gp_f2a, loc1, loc2)
                                fam_sig2b = _law3_family_signature(f1_f, gp_m2b, gp_f2b, loc1, loc2)

                                if (
                                    fam_sig2a is None or fam_sig2b is None
                                    or fam_sig2a != fam_sig or fam_sig2b != fam_sig
                                ):
                                    continue

                                # Now we know this F2 belongs to the same dihybrid experiment type
                                v1 = _trait_from_snap(csnap2, tk1)
                                v2 = _trait_from_snap(csnap2, tk2)
                                if v1 is None or v2 is None:
                                    continue

                                p1 = str(v1).strip().lower()
                                p2 = str(v2).strip().lower()
                                if not p1 or not p2:
                                    continue

                                c1 = "D" if p1 == dom1 else "r"
                                c2 = "D" if p2 == dom2 else "r"
                                combo_counts[(c1, c2)] += 1


                            total = sum(combo_counts.values())
                            if total < N_MIN_LAW3:
                                continue

                            # Need all 4 classes present
                            needed_keys = [("D","D"), ("D","r"), ("r","D"), ("r","r")]
                            if any(combo_counts[k] == 0 for k in needed_keys):
                                continue

                            # Compare to an ideal 9:3:3:1 via a simple chi-square test
                            expected_ratios = {("D","D"): 9, ("D","r"): 3, ("r","D"): 3, ("r","r"): 1}
                            chi2 = 0.0
                            for k in needed_keys:
                                obs = combo_counts[k]
                                exp = expected_ratios[k] * (total / 16.0)
                                if exp <= 0:
                                    continue
                                diff = obs - exp
                                chi2 += (diff * diff) / exp

                            # df = 3 → critical χ²(0.05) ≈ 7.8; we’ll be a bit generous
                            if chi2 <= LAW3_CHI2_MAX:
                                law3_discovered = True
                                trait_label1 = tk1.replace("_", " ")
                                trait_label2 = tk2.replace("_", " ")

                                # New Law 3 ratio formatting: scale counts to 16 total (Mendel-style)
                                try:
                                    vals = [combo_counts[k] for k in needed_keys]  # [DD, Dr, rD, rr]
                                    total = sum(vals)

                                    if total > 0:
                                        # Scale each class so that the sum of the four entries is 16 (like 9:3:3:1)
                                        scaled = [(v / total) * 16.0 for v in vals]

                                        # One decimal place, using decimal comma
                                        pretty_parts = [
                                            f"{x:.1f}".replace(".", ",")
                                            for x in scaled
                                        ]

                                        law3_ratio_str = " : ".join(pretty_parts) + " (scaled to 16)"

                                    else:
                                        law3_ratio_str = ""

                                    law3_trait_pair = (trait_label1, trait_label2)

                                except Exception:
                                    law3_ratio_str = ""
                                    law3_trait_pair = (trait_label1, trait_label2)

                                # parent_id may not exist (Law3 can be detected from AaBb×AaBb where mother != father)
                                try:
                                    if str(mid) == str(fid):
                                        cross_label = f"selfed F1 plant #{mid}"
                                    else:
                                        cross_label = f"F1 cross #{mid}×{fid}"
                                except Exception:
                                    cross_label = "F1 cross #?"

                                law3_reason = (
                                    f"Observed in dihybrid F2 offspring of {cross_label} "
                                    f"for traits '{trait_label1}' and '{trait_label2}': "
                                    f"the four phenotype combinations (dom/dom, dom/rec, rec/dom, rec/rec) "
                                    f"appear in an approximately 9:3:3:1 ratio (N = {total})."
                                )

                                break  # one good dihybrid family is enough

                        # end for (tk1, tk2)

        # --- Update global “ever discovered” flags on GardenApp for UI + feedback ---
        app = getattr(self, "app", None)
        if app is not None and not revealed:
            # Law 1
            if law1_discovered and not getattr(app, "law1_ever_discovered", False):
                app.law1_ever_discovered = True
                app.law1_first_plant = pid
                try:
                    app._toast(f"Law 1 (Dominance) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

            # Law 2
            if law2_discovered and not getattr(app, "law2_ever_discovered", False):
                app.law2_ever_discovered = True
                app.law2_first_plant = pid
                try:
                    app._toast(f"Law 2 (Segregation) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

            # Law 3
            if law3_discovered and not getattr(app, "law3_ever_discovered", False):
                app.law3_ever_discovered = True
                app.law3_first_plant = pid
                try:
                    app._toast(f"Law 3 (Independent Assortment) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass
        
        # --- Push law ratio info to the main app for the top-bar UI ---
        try:
            app = getattr(self, "app", None)
            if app is not None and not revealed:

                # Law 2 ratio in UI
                if law2_discovered:
                    # If the fancy formatter failed for some reason, keep at least *something*
                    if not law2_ratio_str:
                        vals = list(norm_counts.values()) if 'norm_counts' in locals() else []
                        if len(vals) == 2:
                            law2_ratio_str = f"{vals[0]}:{vals[1]}"
                        elif vals:
                            law2_ratio_str = ":".join(str(v) for v in vals)
                        else:
                            law2_ratio_str = "Ratio __:__"

                    setattr(app, "law2_ratio_ui", law2_ratio_str)


                # Law 3 ratio in UI
                if law3_discovered and law3_ratio_str:
                    setattr(app, "law3_ratio_ui", law3_ratio_str)

                # Refresh the display
                if hasattr(app, "_update_law_status_label"):
                    app._update_law_status_label()

        except Exception:
            pass

        # --- Stash law ratio info directly into the archive snapshot for this plant ---
        try:
            if isinstance(snap, dict):
                if law2_discovered and law2_ratio_str:
                    snap["law2_ratio"] = law2_ratio_str
                    if law2_trait_name:
                        snap["law2_trait"] = law2_trait_name
                if law3_discovered and law3_ratio_str:
                    snap["law3_ratio"] = law3_ratio_str
                    if law3_trait_pair:
                        snap["law3_traits"] = f"{law3_trait_pair[0]} × {law3_trait_pair[1]}"
            else:
                if law2_discovered and law2_ratio_str:
                    setattr(snap, "law2_ratio", law2_ratio_str)
                    if law2_trait_name:
                        setattr(snap, "law2_trait", law2_trait_name)
                if law3_discovered and law3_ratio_str:
                    setattr(snap, "law3_ratio", law3_ratio_str)
                    if law3_trait_pair:
                        setattr(snap, "law3_traits", f"{law3_trait_pair[0]} × {law3_trait_pair[1]}")
        except Exception:
            pass

        # --- Write genotype & Mendelian-law blocks to text ------------------
        _add_line("")
        _add_line("Genotype view status")
        _add_line("---------------------")
        if revealed:
            _add_line("[X] Genotype has been revealed in this session")
            _add_line("    (Player could see allele-level information not available to Mendel.)")
        else:
            _add_line("[X] Genotype has NOT been revealed in this session <3")
            _add_line("    (Player used only phenotype information, like Mendel.)")
        _add_line("")

        # ---------------- Mendelian law achievements (auto-synced with code thresholds) ----------------
        _add_line("Mendelian laws (based on this plant and its family)")
        _add_line("---------------------------------------------------")

        # Concise requirement strings (single source of truth)
        law1_req = f"Unlock: N ≥ {LAW1_MIN_F1} phenotype-only F1 offspring showing the same dominant phenotype."

        law2_req = (
            f"Unlock: N ≥ {LAW2_MIN_N} F2 offspring, dominant "
            f"{int(LAW2_DOM_FRAC_MIN*100)}–{int(LAW2_DOM_FRAC_MAX*100)}% (≈3:1)."
        )

        law3_req = (
            f"Unlock: N ≥ {LAW3_MIN_N} dihybrid F2 offspring, "
            f"all 4 phenotype classes present, χ² ≤ {LAW3_CHI2_MAX:g} vs 9:3:3:1."
        )

        # ---------------- Law 1 — Dominance ----------------
        if revealed:
            _add_line("[ ] Law 1 — Law of Dominance")
            _add_line("    Not credited: genotype view (alleles) was revealed in this session.")
            _add_line("    ----------------")
            _add_line(f"    {law1_req}")
        else:
            if law1_discovered:
                _add_line("[X] Law 1 — Law of Dominance")
                if law1_reason:
                    _add_line(f"    {law1_reason}")
                _add_line("    ----------------")
                _add_line(f"    {law1_req}")
            else:
                _add_line("[ ] Law 1 — Law of Dominance")
                _add_line("    Not yet detected from your phenotype-only crosses.")
                _add_line("    ----------------")
                _add_line(f"    {law1_req}")

        _add_line("")
     
        # ---------------- Law 2 — Segregation ----------------
        if revealed:
            _add_line("[ ] Law 2 — Law of Segregation")
            _add_line("    Not credited: genotype view (alleles) was revealed in this session.")
            _add_line("    ----------------")
            _add_line(f"    {law2_req}")
        else:
            if law2_discovered:
                label = "[X] Law 2 — Law of Segregation"
                if law2_ratio_str:
                    label += f" ({law2_ratio_str})"
                _add_line(label)
                if law2_reason:
                    _add_line(f"    {law2_reason}")
                _add_line("    ----------------")
                _add_line(f"    {law2_req}")
            else:
                _add_line("[ ] Law 2 — Law of Segregation")
                _add_line("    Not yet detected from your F2 families.")
                _add_line("    ----------------")
                _add_line(f"    {law2_req}")

        _add_line("")

        # ---------------- Law 3 — Independent Assortment ----------------
        if revealed:
            _add_line("[ ] Law 3 — Law of Independent Assortment")
            _add_line("    Not credited: genotype view (alleles) was revealed in this session.")
            _add_line("    ----------------")
            _add_line(f"    {law3_req}")
        else:
            if law3_discovered:
                label = "[X] Law 3 — Law of Independent Assortment"
                if law3_ratio_str:
                    label += f" ({law3_ratio_str})"
                _add_line(label)
                if law3_reason:
                    _add_line(f"    {law3_reason}")
                _add_line("    ----------------")
                _add_line(f"    {law3_req}")
            else:
                _add_line("[ ] Law 3 — Law of Independent Assortment")
                _add_line("    Not yet detected from your dihybrid F2 families.")
                _add_line("    ----------------")
                _add_line(f"    {law3_req}")

        # -----------------------------------------------------------------------------------------------

        # Lineage mini-tree (ancestors + alleles, with parental alleles for crosses)
        lineage_lines = _lineage_tree_lines(pid)
        if lineage_lines:
            _add_line("Lineage (ancestors + alleles)")
            _add_line("-------------------------------")
            for ln in lineage_lines:
                _add_line(ln)
            _add_line("")

        _add_line("Genotype")
        _add_line("---------")
        _add_line(geno_str or "(none)")
        _add_line("")

        # === NEW TRAIT BLOCK WITH GENOTYPES NEXT TO PHENOTYPES ===

        def _geno_for_trait(geno, loci):
            """Return allele string for given locus or list of loci, e.g. 'A/a' or 'P/p; V/V'."""
            if not isinstance(geno, dict):
                return ""
            if isinstance(loci, (str, bytes)):
                loci = [loci]
            parts = []
            for loc in loci:
                pair = geno.get(loc, None)
                if not pair or len(pair) < 2:
                    continue
                a1, a2 = pair[0], pair[1]
                parts.append(f"{a1}/{a2}")
            return "; ".join(parts)

        _add_line("Traits")
        _add_line("------")

        fc = traits.get('flower_color', '')
        fc_g = _geno_for_trait(genotype_obj, 'A')
        _add_line(f"Flower color    : {fc}{f' ({fc_g})' if fc_g else ''}")

        pheno_height = traits.get('plant_height', '')
        ph_g = _geno_for_trait(genotype_obj, 'Le')
        _add_line(f"Plant height    : {pheno_height}{f' ({ph_g})' if ph_g else ''}")

        pc = traits.get('pod_color', '')
        pc_g = _geno_for_trait(genotype_obj, 'Gp')
        _add_line(f"Pod color       : {pc}{f' ({pc_g})' if pc_g else ''}")

        ps = traits.get('pod_shape', '')
        ps_g = _geno_for_trait(genotype_obj, ['P', 'V'])
        _add_line(f"Pod shape       : {ps}{f' ({ps_g})' if ps_g else ''}")
        
        ss = traits.get('seed_shape', '')
        ss_g = _geno_for_trait(genotype_obj, 'R')
        _add_line(f"Seed shape      : {ss}{f' ({ss_g})' if ss_g else ''}")

        sc = traits.get('seed_color', '')
        sc_g = _geno_for_trait(genotype_obj, 'I')
        _add_line(f"Seed color      : {sc}{f' ({sc_g})' if sc_g else ''}")

        # Flower position has no genotype locus
        fp = traits.get('flower_position', '')
        fp_g = _geno_for_trait(genotype_obj, ['Fa', 'Mfa'])
        _add_line(f"Flower position : {fp}{f' ({fp_g})' if fp_g else ''}")

        _add_line("")

        # Sibling distributions section
        _add_line("Sibling distributions (same parents)")
        _add_line("------------------------------------")
        for tk, pretty in [
            ("flower_color", "Flower color"),
            ("pod_color", "Pod color"),
            ("seed_color", "Seed color"),
            ("seed_shape", "Seed shape"),
            ("plant_height", "Plant height"),
        ]:
            counts = sib_counts.get(tk, "")
            ratio  = sib_ratios.get(tk, "")
            n      = sib_ns.get(tk, 0)
            if not (counts or ratio or n):
                continue
            _add_line(f"{pretty}:")
            _add_line(f"  counts : {counts}")
            _add_line(f"  ratio  : {ratio}")
            _add_line(f"  N      : {n}")
            _add_line("")

        text = "\n".join(lines)

        # One text file per plant export → saved into export/ folder
        try:
            fname = f"traits_plant_{pid}.txt"
        except Exception:
            fname = "traits_plant_export.txt"

        out_path = os.path.join(EXPORT_DIR, fname)

        # Ensure export directory exists
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
        except Exception:
            pass

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            try:
                messagebox.showerror(
                    "Export traits",
                    f"Failed to write text file:\n{e}"
                )
            except Exception:
                pass

    def _build_layers_archive(self, root):

        plants = {}
        try:
            arch = getattr(self.app, "archive", {})
            plants = arch.get("plants", {})
            if not isinstance(plants, dict):
                plants = {}
        except Exception:
            plants = {}

        def get_snap(pid):
            if str(pid) in plants:
                return plants[str(pid)]
            try:
                return plants.get(int(str(pid)))
            except Exception:
                return None

        def parents(pid):
            s = get_snap(pid)
            return self._parents_from_snapshot(s or {})

        def generation(pid):
            s = get_snap(pid) or {}
            if isinstance(s, dict):
                return s.get("generation", "F?")
            return getattr(s, "generation", "F?")

        # --- BFS upwards, but place parents by their OWN generation (avoid duplicates) ---
        def _parse_F(s):
            try:
                s = str(s or "")
                if s.startswith("F") and s[1:].isdigit():
                    return int(s[1:])
            except Exception:
                pass
            return None

        up_levels = {}          # depth -> [pid_str, ...]
        level_nodes = {0: [str(root)]} if root is not None else {}
        levels_pos = {}         # depth -> {pid_str: leftmost_child_index}

        g0 = _parse_F(generation(root))
        max_depth = 5

        for d_child in range(0, max_depth):
            cur = level_nodes.get(d_child, [])
            if not cur:
                continue

            for child_idx, pid in enumerate(cur):
                m, f = parents(pid)
                for parent in (m, f):
                    if parent is None:
                        continue
                    sp = str(parent)
                    if get_snap(sp) is None:
                        continue

                    # default placement: direct parent
                    d_parent = d_child + 1

                    # if generation info exists, place by generation difference
                    if g0 is not None:
                        gp = _parse_F(generation(sp))
                        if gp is not None:
                            d_parent = max(d_parent, g0 - gp)

                    if d_parent <= 0 or d_parent > max_depth:
                        continue

                    level_nodes.setdefault(d_parent, [])
                    if sp not in level_nodes[d_parent]:
                        level_nodes[d_parent].append(sp)

                    levels_pos.setdefault(d_parent, {})
                    if sp not in levels_pos[d_parent] or child_idx < levels_pos[d_parent][sp]:
                        levels_pos[d_parent][sp] = child_idx

        # build ordered rows
        for depth, posmap in levels_pos.items():
            row = sorted(
                posmap.keys(),
                key=lambda s: (posmap.get(s, 10**9),
                               int(s) if s.isdigit() else s)
            )
            up_levels[depth] = row

        layers = []

        for depth in sorted(up_levels.keys(), reverse=True):
            label = f"F{g0-depth}" if g0 is not None else f"-{depth}"
            layers.append((label, up_levels[depth]))

        layers.append(
            (f"F{g0}" if g0 is not None else "F?",
             [str(root)] if root is not None else [])
        )
        return layers

    def _scale_image_fractional(self, img, sx: float, sy: float):
        """
        Scale a Tk PhotoImage using integer zoom/subsample to approximate
        fractional scaling factors sx and sy.
        """
        # resolution of scaling precision
        denom = 20   # try 20 or 50 for smoother steps
        
        # compute integer zoom factors
        zx = max(1, int(sx * denom))
        zy = max(1, int(sy * denom))
        
        # apply zoom
        img2 = img.zoom(zx, zy)
        
        # apply subsample (integer)
        img2 = img2.subsample(denom, denom)
        return img2

    def _icon_for_snap(self, trait_key, snap, sx=3, sy=3):

        try:
            traits = (snap.get("traits", {}) if isinstance(snap, dict) else getattr(snap, "traits", {}) or {})
            val = str(traits.get(trait_key, "")).strip().lower()
            
            # If traits are completely empty, try to derive from genotype
            if not traits or not any(traits.values()):
                try:
                    genotype = snap.get("genotype", {}) if isinstance(snap, dict) else getattr(snap, "genotype", {})
                    if genotype and trait_key in ("flowers", "flower", "flower_color"):
                        # Derive flower color from A locus
                        a_alleles = genotype.get("A", [])
                        if a_alleles and len(a_alleles) >= 2:
                            # If has at least one A allele → purple (dominant)
                            # If aa → white (recessive)
                            has_A = any(str(a).upper() == "A" for a in a_alleles)
                            val = "purple" if has_A else "white"
                            traits = {"flower_color": val}  # Update traits for fallthrough
                except Exception:
                    pass

            # Flowers: if the requested trait is color (or generic "flowers"), use color-only icon
            if trait_key in ("flowers", "flower", "flower_color"):
                col = str(traits.get("flower_color", val)).lower()
                try:
                    p = trait_icon_path("flower_color", col)
                except Exception:
                    p = ""
                if p:
                    im = safe_image_scaled(p, sx, sy)
                    if im is not None:
                        return im

            # Flower position: only when explicitly requested
            if trait_key in ("flower_position",):
                pos = str(traits.get("flower_position", val)).lower()
                # try dedicated position icon
                try:
                    p = trait_icon_path("flower_position", pos)
                except Exception:
                    p = ""
                if p:
                    im = safe_image_scaled(p, sx, sy)
                    if im is not None:
                        return im
                # fall back to composed (position + color) if available
                try:
                    p = flower_icon_path_hi(pos or None, str(traits.get("flower_color","")).lower() or None)
                except Exception:
                    p = ""
                if p:
                    im = safe_image_scaled(p, sx, sy)
                    if im is not None:
                        return im

            # Combined pod color/shape when asked for pod shape family
            if trait_key in ("pod_shape", "pod_color_shape", "pod"):
                c = str(traits.get("pod_color", "")).lower()
                s = str(traits.get("pod_shape", "")).lower()
                c = "green" if "green" in c else ("yellow" if "yellow" in c else c)
                s = "constricted" if "constrict" in s else ("inflated" if "inflate" in s else s)
                try:
                    p = pod_shape_icon_path(s, c)
                except Exception:
                    p = ""
                if p:
                    im = safe_image_scaled(p, sx, sy)
                    if im is not None:
                        return im

            # Generic trait icon
            try:
                p = trait_icon_path(trait_key, val)
            except Exception:
                p = ""
            if p:
                im = safe_image_scaled(p, sx, sy)
                if im is not None:
                    return im

            # Height synonyms
            if trait_key in ("height","plant_height"):
                try:
                    p = trait_icon_path("plant_height", val or traits.get("plant_height",""))
                except Exception:
                    p = ""
                if p:
                    im = safe_image_scaled(p, sx, sy)
                    if im is not None:
                        return im
        except Exception:
            pass
        return None

    def _render_preview(self, pid):
        """Preview an ancestor's details without switching the main selection or recalculating the tree root."""
        snap = self._get_snap(pid)
        if not snap:
            return
        self.preview_pid = str(pid)
        # Update left + right panels using preview plant
        def g(k, default=None): return snap.get(k, default) if isinstance(snap, dict) else getattr(snap, k, default)
        self.lbl_left_title.config(text=f"Plant {g('generation','F?')} #{g('id', pid)} (preview)")
        self.lbl_left_parents.config(text=f"Parents: ♀ #{g('mother_id','?')}  |  ♂ #{g('father_id','?')}")
        self.lbl_parents_right.config(text=f"♀ #{g('mother_id','?')}   ♂ #{g('father_id','?')}")
        self._render_traits(snap)
        self._render_siblings(g('id', pid))
        # Redraw the tree using the CURRENT root, but highlight the previewed ancestor
        root_id = getattr(self, "current_pid", None)
        if root_id is not None:
            self._draw_canvas_family(root_id)
        else:
            # Fallback: draw with the preview pid as root if nothing is selected yet
            self._draw_canvas_family(pid)

    def _refresh_views(self):
        """Re-render tree and sibling pods on trait-mode change or other triggers."""
        try:
            # Reset image references for a clean rebuild
            self._img_refs = []

            root_id = getattr(self, "current_pid", None)
            prev = getattr(self, "preview_pid", None)

            # Tree stays rooted on current plant
            if root_id is not None:
                self._draw_canvas_family(root_id)

            # Siblings reflect preview if active; else current
            pid = prev or root_id
            if pid is not None:
                self._render_siblings(pid)
        except Exception:
            pass

    def _draw_canvas_family(self, pid):
            c = self.canvas
            c.delete("all")

            # Make sure Tk has computed a real size for the canvas
            try:
                c.update_idletasks()
            except Exception:
                pass

            w = max(c.winfo_width(), 640)
            h = max(c.winfo_height(), 400)
            c.configure(scrollregion=(0, 0, w, h))

            # Palette, with safe fallback
            try:
                link = "#1a5c7f"
                node_outer = "#34b3e6"
                node_fill = "#193644"
            except Exception:
                link = "#1a5c7f"
                node_outer = "#34b3e6"
                node_fill = "#193644"

            layers = self._build_layers_archive(pid)
            if not layers:
                c.create_text(
                    w // 2, h // 2,
                    text="No archive data",
                    fill=self.MUTED,
                    font=("Segoe UI", 12, "bold"),
                )
                return

            # --- Vertical layout: grow downward from top, compress only if many generations ---
            L = len(layers)
            x_pad = 70
            pos = {}

            # F0 anchored near top, tree grows downward
            # Compute a top margin that leaves room for the "Lineage" title
            try:
                title_font = tk.font.Font(family="Segoe UI", size=16)
                title_h = title_font.metrics("linespace")
            except Exception:
                # reasonable fallback if font metrics fail
                title_h = 24

            # title is drawn at y=12 → leave its height + a little padding
            top_margin = 12 + title_h + 8   # e.g. ~44–48 px on most systems

            min_step = 50  # never closer than this
            # "comfortable" step for a few generations
            base_step = int(90 * (getattr(self, "SPACING_SCALE_Y", 0.75) or 0.75))

            if L <= 1:
                # Single generation: put it near the top, not centered
                y_positions = [top_margin]
            else:
                # How much vertical space is currently visible?
                available = max(120, h - top_margin - 40)
                # Step that would fit everything without scrolling
                max_step_to_fit = max(min_step, available // max(1, L - 1))
                # Use our comfortable step unless that would overflow badly
                y_step = min(base_step, max_step_to_fit)
                y_positions = [top_margin + i * y_step for i in range(L)]

            # Scrollregion grows with more generations, but we don't stretch few generations
            max_y = y_positions[-1] + 80
            c.configure(scrollregion=(0, 0, w, max(h, max_y)))

            # IDs for highlight logic
            cur_id = str(getattr(self, "current_pid", "")) if getattr(self, "current_pid", None) is not None else ""
            prev_id = str(getattr(self, "preview_pid", "")) if getattr(self, "preview_pid", None) is not None else ""

            # --- Draw generation labels + nodes + trait icons ---
            for (label, row), y in zip(layers, y_positions):
                n = max(1, len(row))
                x_step = max(110, (w - 2 * x_pad) // n)
                x = x_pad + x_step // 2

                # Generation label (e.g. F0, F1, F2)
                c.create_text(
                    18, y,
                    anchor="w",
                    text=str(label),
                    fill=self.MUTED,
                    font=("Segoe UI", 12, "bold"),
                )

                for pid_str in row:
                    pos[pid_str] = (x, y)
                    snap = self._get_snap(pid_str)
                    r1, r2 = 28, 24

                    # --- highlight colors depending on selection state ---
                    pid_norm = str(pid_str)
                    is_current = (pid_norm == cur_id)
                    is_preview = (pid_norm == prev_id and not is_current)

                    outer_color = node_outer
                    inner_color = node_fill
                    outer_w = self.NODE_OUTER_W

                    if is_current:
                        # main selected plant: warm gold accent
                        outer_color = "#f4c542"
                        inner_color = "#5a3b00"
                        outer_w = self.NODE_OUTER_W + 1
                    elif is_preview:
                        # previewed ancestor: cooler blue accent
                        outer_color = "#7fd3ff"
                        inner_color = "#123649"

                    # outer ring (clickable)
                    c.create_oval(
                        x - r1, y - r1, x + r1, y + r1,
                        outline=outer_color,
                        width=outer_w,
                        tags=(f"node_{pid_str}", "node"),
                    )

                    # inner fill (clickable)
                    c.create_oval(
                        x - r2, y - r2, x + r2, y + r2,
                        fill=inner_color,
                        outline="",
                        tags=(f"node_{pid_str}", "node"),
                    )


                    # inner fill (clickable)
                    c.create_oval(
                        x - r2, y - r2, x + r2, y + r2,
                        fill=node_fill,
                        outline="",
                        tags=(f"node_{pid_str}", "node"),
                    )

                    # trait icon in the center
                    try:
                        mode = (self.trait_mode.get() or "Flowers").lower()
                        key = {
                            "flowers": "flower_color",
                            "pod color": "pod_color",
                            "pod shape": "pod_shape",
                            "seed color": "seed_color",
                            "seed shape": "seed_shape",
                            "height": "plant_height",
                        }.get(mode, "flower_color")

                        im = self._icon_for_snap(key, snap, sx=self.SCALE_NODE, sy=self.SCALE_NODE)
                        if im is not None:
                            c.create_image(
                                x, y,
                                image=im,
                                tags=(f"node_{pid_str}", "node"),
                            )
                            self._img_refs.append(im)
                    except Exception:
                        pass

                    # label to the right (e.g. #1012)
                    c.create_text(
                        x + self.NODE_LABEL_DX, y,
                        anchor="w",
                        text=f"#{pid_str}",
                        fill=self.FG,
                        font=self.NODE_LABEL_FONT,
                        tags=(f"node_{pid_str}", "node"),
                    )

                    x += x_step

            # --- Draw parent links (branches) behind nodes/icons ---
            def parents_of(sid):
                s = self._get_snap(sid)
                if not s:
                    return (None, None)
                return self._parents_from_snapshot(s)

            for idx in range(1, len(layers)):
                _, row = layers[idx]
                for sid in row:
                    m, f = parents_of(sid)
                    for ppid in (m, f):
                        if ppid is None:
                            continue
                        sp = str(ppid)
                        if sp in pos and sid in pos:
                            x1, y1 = pos[sp]
                            x2, y2 = pos[sid]
                            c.create_line(
                                x1, y1 + 24,
                                x2, y2 - 24,
                                width=self.LINK_W,
                                fill=link,
                                tags=("edge",),
                            )

            # send branch lines behind nodes and trait icons
            try:
                c.tag_lower("edge")
            except Exception:
                pass

            # Title text
            c.create_text(
                12, 12,
                anchor="nw",
                text="Lineage",
                fill=self.MUTED,
                font=("Segoe UI", 16)
            )

            # enable click selection on nodes
            try:
                c.tag_bind("node", "<Button-1>", self._on_canvas_node_click)
            except Exception:
                pass

            except Exception as e:
                c.create_text(
                    20, 20,
                    anchor="nw",
                    text=f"Tree error: {e}",
                    fill="#ffb4b4",
                    font=("Segoe UI", 12, "bold")
                )
                traceback.print_exc()

    def _render_traits(self, snap):
        for w in self.traits_container.winfo_children():
            w.destroy()

        traits = {}
        try:
            traits = snap.get("traits", {}) if isinstance(snap, dict) else getattr(snap, "traits", {}) or {}
        except Exception:
            traits = {}

        if not traits:
            tk.Label(
                self.traits_container,
                text="No traits recorded in archive.",
                bg=self.PANEL,
                fg=self.MUTED
            ).pack(anchor="w")
            return

        priority = ["flower_color","flower_position","Flowers","pod_color",
                    "pod_shape","seed_color","seed_shape","plant_height","height"]
        ordered = sorted(
            traits.items(),
            key=lambda kv: (priority.index(kv[0]) if kv[0] in priority else 999, kv[0])
        )

        # 🔧 compact layout knobs
        row_pad = 0          # was 4
        icon_w = icon_h = 32 # was effectively 40 via canvas 40×40
        label_font = ("Segoe UI", 11, "bold")
        value_font = ("Segoe UI", 11)

        for name, value in ordered:
            row = tk.Frame(self.traits_container, bg=self.PANEL)
            row.pack(fill="x", pady=row_pad)

            # slightly smaller icons
            im = self._icon_for_snap(name, snap, sx=0.8, sy=0.8)  # was self.SCALE_TRAIT
            if im is not None:
                lbl = tk.Label(row, image=im, bg=self.PANEL)
                lbl.image = im
                lbl.pack(side="left")
                self._img_refs.append(im)
            else:
                ico = tk.Canvas(
                    row,
                    width=icon_w, height=icon_h,
                    bg=self.PANEL,
                    highlightthickness=0
                )
                ico.pack(side="left")
                r = icon_w // 2 - 4
                cx = cy = icon_w // 2
                ico.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill="#223c4d", outline="#2ea1db"
                )
                ico.create_text(
                    cx, cy,
                    text=str(name)[:1].upper(),
                    fill=self.FG,
                    font=("Segoe UI", 11, "bold")
                )

            tk.Label(
                row,
                text=f"{name.replace('_',' ')}:",
                bg=self.PANEL,
                fg=self.FG,
                font=label_font
            ).pack(side="left", padx=(8, 4))   # slightly less horizontal padding

            tk.Label(
                row,
                text=f"{value}",
                bg=self.PANEL,
                fg=self.FG,
                font=value_font
            ).pack(side="left")

    def _render_siblings(self, pid):
        # ---- pretty ratio helpers (local, refined) ----
        def _percentages_str(vals, places=1):
            total = sum(vals)
            if total <= 0:
                return [f"0%"] * len(vals)
            scale = 10 ** places
            raw = [v * 100.0 * scale / total for v in vals]  # e.g. places=1 → tenths
            floors = [int(math.floor(x)) for x in raw]
            rem = int(round(sum(raw))) - sum(floors)
            fracs = [(i, raw[i] - floors[i]) for i in range(len(vals))]
            fracs.sort(key=lambda t: t[1], reverse=True)
            for i in range(max(0, rem)):
                floors[fracs[i % len(floors)][0]] += 1
            # format back to percentage strings
            if places == 0:
                return [f"{p}%" for p in floors]
            else:
                return [f"{p/scale:.{places}f}%" for p in floors]

        def _gcd_list(lst):
            g = 0
            for v in lst:
                g = math.gcd(g, v)
            return g or 1

        def _reduce(vals):
            if not vals:
                return vals
            positives = [v for v in vals if v > 0]
            g = _gcd_list(positives or [1])
            return [v // g for v in vals]

        def _two_class_approx(a, b, max_den=6):
            # prefer *very small* denominators so the approx is genuinely simpler
            if b == 0:
                return None
            target = a / b
            best = None
            for q in range(1, max_den + 1):
                p = max(1, round(target * q))
                g = math.gcd(p, q)
                pr, qr = p // g, q // g
                if pr == 0 or qr == 0:
                    continue
                err = abs(pr / qr - target)
                cand = (err, pr, qr)
                if best is None or cand < best:
                    best = cand
            if best:
                _, pr, qr = best
                return [pr, qr]
            return None

        def pretty_ratio(vals, decimals=2, use_decimal_comma=True):
            """
            Mendel-style display for totals:
            - If there are exactly 2 classes and both counts > 0:
                show 'x:1' where x = round(max/min, decimals)
            - Append percentages (kept from current behaviour)
            - Fall back to reduced exact ratio for 3+ classes or zeros.
            """
            # percentages (kept)
            perc = _percentages_str(vals, places=1)  # e.g., '79.8%' / '20.2%'

            # two-class Mendel rounding
            if len(vals) == 2:
                a, b = vals
                if a < b:
                    a, b = b, a
                if b > 0:
                    x = round(a / b, decimals)
                    # format with fixed decimals
                    x_str = f"{x:.{decimals}f}"
                    if use_decimal_comma:
                        x_str = x_str.replace(".", ",")
                    return f"{x_str}:1 ({' / '.join(perc)})"
                else:
                    # one class absent → keep a compact exact form
                    red = _reduce(vals)
                    return f"{':'.join(str(v) for v in red)} ({' / '.join(perc)})"

            # 3+ classes → keep the reduced exact ratio + percentages
            red = _reduce(vals)
            exact = ':'.join(str(v) for v in red) if red else '0'
            return f"{exact} ({' / '.join(perc)})"

        # ---- end pretty ratio helpers ----

        # --- helpers ---
        def reduced_ratio(counts):
            vals = [int(c) for c in counts]
            if not vals or not any(vals):
                return "0"
            g = functools.reduce(math.gcd, vals)
            g = g if g else 1
            return ":".join(str(v // g) for v in vals)

        def g(s, k):  # get attribute or dict value
            return s.get(k) if isinstance(s, dict) else getattr(s, k, None)

        # conservative nested lookup + normalization for ratio only
        def _norm(v):
            try:
                s = str(v).strip().lower()
                if s in ("violet",): return "purple"
                if s in ("wh","w"):  return "white"
                if s in ("yl","y"):  return "yellow"
                if s in ("gr","g"):  return "green"
                return s
            except Exception:
                return v

        def _lookup_trait(snap, key):
            # direct
            if isinstance(snap, dict) and key in snap and snap[key] is not None:
                return snap[key]
            # common nests
            for nest in ("traits","phenotype","phenotypes","geno","genotype","data"):
                try:
                    sub = snap.get(nest) if isinstance(snap, dict) else getattr(snap, nest, None)
                    if isinstance(sub, dict) and key in sub and sub[key] is not None:
                        return sub[key]
                except Exception:
                    pass
            # fallback to getattr
            try:
                return getattr(snap, key, None)
            except Exception:
                return None

        # --- clear target panel ---
        for w in self.sibs_inner.winfo_children():
            w.destroy()

        sel = self._get_snap(pid)
        if not sel:
            tk.Label(self.sibs_inner, text="No archived siblings.", bg=self.PANEL, fg=self.MUTED).pack(anchor="w", padx=8, pady=8)
            return

        # which trait to render in sibling icons
        try:
            mode = (self.trait_mode.get() or 'Flowers').lower()
        except Exception:
            mode = 'flowers'
        trait_map = {
            'flowers': 'flower_color',
            'flower': 'flower_color',
            'pod color': 'pod_color', 'pod shape': 'pod_shape',
            'seed color': 'seed_color',
            'seed shape': 'seed_shape',
            'height': 'plant_height',
        }
        _sib_trait_key = trait_map.get(mode, 'flower_color')

        mid, fid = g(sel, "mother_id"), g(sel, "father_id")

        # Build pods -> list of children snapshots (include the selected one if it matches)
        plants = self.app.archive.get("plants", {}) if hasattr(self, 'app') and isinstance(getattr(self.app, 'archive', None), dict) else {}
        pods = {}
        for cid, csnap in (plants.items() if isinstance(plants, dict) else []):
            cm, cf = g(csnap, "mother_id"), g(csnap, "father_id")
            same = ((mid is not None and fid is not None and cm == mid and cf == fid) or
                    (mid is not None and fid is None and cm == mid) or
                    (mid is None and fid is not None and cf == fid))
            if same:
                pidx = g(csnap, "source_pod_index")
                pods.setdefault(pidx, []).append((cid, csnap))

        if not pods:
            tk.Label(self.sibs_inner, text="No archived siblings.", bg=self.PANEL, fg=self.MUTED).pack(anchor="w", padx=8, pady=8)
            return

        # ===== Flat layout: Canvas + H-scroll placed directly in sibs_inner =====
        pods_canvas = tk.Canvas(self.sibs_inner, bg=self.PANEL, highlightthickness=0, height=260)
        pods_canvas.pack(side="top", fill="both", expand=True)
        hscroll = tk.Scrollbar(self.sibs_inner, orient="horizontal", command=pods_canvas.xview)
        hscroll.pack(side="top", fill="x")
        pods_canvas.configure(xscrollcommand=hscroll.set)

        pods_row = tk.Frame(pods_canvas, bg=self.PANEL)
        pods_canvas.create_window((0,0), window=pods_row, anchor="nw")
        pods_row.bind("<Configure>", lambda e: pods_canvas.configure(scrollregion=pods_canvas.bbox("all")))

        # Total ratio label (directly in sibs_inner, no extra frame)
        total_label = tk.Label(self.sibs_inner, text="Total ratio: —", bg=self.PANEL, fg=self.FG, font=("Segoe UI", 12, "bold"))
        total_label.pack(side="top", pady=(6, 4))
        # --- Optional: show stored Law 2 / Law 3 ratios (Segregation / Independent Assortment) ---
        try:
            # sel is the snapshot for this pid (defined earlier in _render_siblings)
            if isinstance(sel, dict):
                law2_ratio = sel.get("law2_ratio")
                law2_trait = sel.get("law2_trait")   # NEW
                law3_ratio = sel.get("law3_ratio")
                law3_traits = sel.get("law3_traits")
            else:
                law2_ratio = getattr(sel, "law2_ratio", None)
                law2_trait = getattr(sel, "law2_trait", None)   # NEW
                law3_ratio = getattr(sel, "law3_ratio", None)
                law3_traits = getattr(sel, "law3_traits", None)

            if law2_ratio:
                # Line 1: Law name + ratio
                tk.Label(
                    self.sibs_inner,
                    text=f"Law of Segregation: {law2_ratio}",
                    bg=self.PANEL,
                    fg=self.FG,
                    font=("Segoe UI", 11, "italic"),
                ).pack(side="top", pady=(2, 1))

                # Line 2: centered trait (if available)
                if law2_trait:
                    tk.Label(
                        self.sibs_inner,
                        text=f"({law2_trait})",
                        bg=self.PANEL,
                        fg=self.FG,
                        font=("Segoe UI", 10),
                        justify="center",
                        anchor="center",
                    ).pack(side="top", pady=(0, 4))

            if law3_ratio:

                # Separator line between Law 2 and Law 3
                tk.Frame(
                    self.sibs_inner,
                    height=1,
                    bg=self.FG,        # or self.DIM for softer line
                ).pack(fill="x", pady=(6, 6))

                # Line 1: Law name + ratio
                tk.Label(
                    self.sibs_inner,
                    text=f"Law of Independent Assortment: {law3_ratio}",
                    bg=self.PANEL,
                    fg=self.FG,
                    font=("Segoe UI", 11, "italic"),
                ).pack(side="top", pady=(0, 2))

                # Line 2: traits in parentheses, centered
                if law3_traits:
                    tk.Label(
                        self.sibs_inner,
                        text=f"({law3_traits})",
                        bg=self.PANEL,
                        fg=self.FG,
                        font=("Segoe UI", 10),
                        justify="center",
                        anchor="center",
                    ).pack(side="top", pady=(0, 6))

        except Exception:
            pass

        # --- render pods left-to-right, contents vertical, icon-only with 2x2 subsample size ---
        grand_counter = Counter()
        highlight_id = str(pid)

        ordered_keys = sorted(pods.keys(), key=lambda x: (-1 if x is None else x))
        
        for pidx in ordered_keys:
            # Determine maternal pod color, then choose tint
            try:
                mother_snap = self._get_snap(mid)
                m_traits = mother_snap.get("traits", {}) if isinstance(mother_snap, dict) else getattr(mother_snap, "traits", {}) or {}
                pod_color_val = str(m_traits.get("pod_color", "")).lower()
            except Exception:
                pod_color_val = ""
            col_bg = self._pod_tint_from_color(pod_color_val)

            # Entire card (title + icons + ratio) uses the tint
            card = tk.Frame(pods_row, bg=col_bg, highlightthickness=1, highlightbackground="#2b4d59")
            card.pack(side="left", padx=10, pady=8, fill="y")

            tk.Label(card, text=f"Pod #{pidx if pidx is not None else '?'}",
                     bg=col_bg, fg=self.FG, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10,6))

            col = tk.Frame(card, bg=col_bg)
            col.pack(padx=10, pady=(0,8))

            local_counter = Counter()

            for cid, csnap in pods[pidx]:
                tval = _norm(_lookup_trait(csnap, _sib_trait_key))
                local_counter[tval] += 1
                grand_counter[tval] += 1

                row = tk.Frame(col, bg=col_bg)
                row.pack(anchor="w", pady=4)

                canvas_w = 40
                canvas_h = 40
                c = tk.Canvas(row, width=canvas_w, height=canvas_h, bg=col_bg, highlightthickness=0)
                c.pack()

                im = self._icon_for_snap(_sib_trait_key, csnap, sx=self.SCALE_SIB, sy=self.SCALE_SIB)
                img_id = None

                if im is not None:
                    try:
                        im2 = im.subsample(2, 2) if hasattr(im, "subsample") and callable(im.subsample) else im
                        img_id = c.create_image(canvas_w // 2, canvas_h // 2, image=im2)
                        self._img_refs.append(im2)
                    except Exception:
                        img_id = c.create_image(canvas_w // 2, canvas_h // 2, image=im)
                        self._img_refs.append(im)
                else:
                    # Fallback: simple disk placeholder when we have no icon
                    r = min(canvas_w, canvas_h) // 2 - 6
                    img_id = c.create_oval(
                        canvas_w // 2 - r, canvas_h // 2 - r,
                        canvas_w // 2 + r, canvas_h // 2 + r,
                        outline="#34b3e6", width=1
                    )

                # Highlight *behind* the icon so it never hides the trait icon
                if str(cid) == highlight_id and img_id is not None:
                    rect_id = c.create_rectangle(
                        2, 2, canvas_w - 2, canvas_h - 2,
                        outline="#ffd166", width=3
                    )
                    try:
                        # ensure the border sits underneath the icon in z-order
                        c.tag_lower(rect_id, img_id)
                    except Exception:
                        pass

            # Single per-pod ratio (no duplicates)
            if local_counter:
                ordered_local = sorted(local_counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
                counts_local = [cnt for _name, cnt in ordered_local]
                ratio_local = reduced_ratio(counts_local)
            else:
                ratio_local = "0"
            tk.Label(card, text=ratio_local, bg=col_bg, fg=self.FG, font=("Segoe UI", 12, "bold")).pack(padx=10, pady=(4,10), anchor="center")

        # total ratio across all pods
        if grand_counter:
            ordered_total = sorted(grand_counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
            counts_total = [cnt for _name, cnt in ordered_total]
            total_label.configure(text=f"Total ratio: {pretty_ratio(counts_total)}")
        else:
            total_label.configure(text=f"Total ratio: {pretty_ratio(counts_total)}")

        # --- auto-extend vertically to fit tallest pod ---
        try:
            self.sibs_inner.update_idletasks()
            max_h = 0
            for card in pods_row.winfo_children():
                h = card.winfo_reqheight()
                if h > max_h:
                    max_h = h
            if max_h:
                pods_canvas.configure(height=max_h + 40)
        except Exception:
            pass
    def _render_pid(self, pid):
        # clear any ancestor preview when switching selection
        self.preview_pid = None
        self._img_refs = []
        self.current_pid = pid
        snap = self._get_snap(pid)
        if not snap:
            self._clear_render(); return
        def g(k, default=None): return snap.get(k, default) if isinstance(snap, dict) else getattr(snap, k, default)
        self.lbl_left_title.config(text=f"Plant {g('generation','F?')} #{g('id', pid)}")
        self.lbl_left_parents.config(text=f"Parents: ♀ #{g('mother_id','?')}  |  ♂ #{g('father_id','?')}")
        self.lbl_parents_right.config(text=f"♀ #{g('mother_id','?')}   ♂ #{g('father_id','?')}")
        self._render_traits(snap)
        self._render_siblings(g('id', pid))
        self._draw_canvas_family(g('id', pid))