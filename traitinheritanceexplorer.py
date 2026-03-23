"""
Trait Inheritance Explorer Module

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
2. TraitInheritanceExplorer class for the visual interface
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
try:
    from PIL import Image, ImageOps, ImageTk as _PILImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

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
        # backfill helper exists on TraitInheritanceExplorer, not on the dict archive
        try:
            if hasattr(self, "_archive_backfill_cross_parents"):
                self._archive_backfill_cross_parents()
        except Exception:
            pass

        # call the shared law-testing function
        from traitinheritanceexplorer import test_mendelian_laws
        test_mendelian_laws(self, archive=getattr(self, "archive", None), pid=getattr(self, "law_context_pid", None), allow_credit=True, toast=True)

    except Exception as e:
        try:
            self._toast(f"Law test failed: {e}", level="warn")
        except Exception:
            print("Law test failed:", e)

def test_mendelian_laws(app, archive=None, pid=None, allow_credit=True, toast=True, target_law=None):
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
    revealed = bool(getattr(app, "_genotype_revealed", False))
    if revealed and allow_credit:
        # Genotype was peeked — can still detect for display but don't credit
        allow_credit = False

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

    # ---- helper: parent extraction (same as TraitInheritanceExplorer._parents_from_snapshot) ----
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
    # (This block is intentionally mirrored from TraitInheritanceExplorer._export_selected_traits)

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
    law1_trait_name = ""
    law1_dominant_value = ""  # the phenotype value that is dominant
    law1_all_valid = []       # all (trait_key, dominant_value) pairs that qualify

    law2_discovered = False
    law2_reason = ""
    law2_ratio_str = ""
    law2_trait_name = ""
    law2_dominant_value = ""  # the phenotype value that appears ~75% of the time
    law2_all_valid = []       # all (trait_key, dominant_value) pairs that qualify
    law2_all_valid_ratios = {}  # trait_key -> ratio_str for the qualifying traits

    law3_discovered = False
    law3_reason = ""
    law3_ratio_str = ""
    law3_trait_pair = ()
    law3_all_valid_pairs = []   # all (tk1, tk2) pairs that pass the chi-square test
    law3_all_valid_pairs_ratios = {}  # frozenset({tk1,tk2}) -> ratio string

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
                law1_trait_name = tk
                law1_dominant_value = cv  # cv is the child's phenotype = the dominant value
                # store ALL valid (trait_key, dominant_value) pairs for wizard validation
                law1_all_valid = [(t, c) for t, c, *_ in dominant_candidates]
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
                law2_trait_name = tk  # store raw key so wizard can compare directly
                law2_dominant_value = dom_pheno

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
                law2_all_valid.append((tk, dom_pheno))
                law2_all_valid_ratios[tk] = law2_ratio_str
                # don't break — collect all valid traits

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

                # accumulate ALL valid pairs (for wizard validation)
                law3_all_valid_pairs.append((tk1, tk2))
                law3_all_valid_pairs_ratios[frozenset({tk1, tk2})] = law3_ratio_str

                try:
                    cross_label = f"selfed F1 plant #{mid}" if str(mid) == str(fid) else f"F1 cross #{mid}×{fid}"
                except Exception:
                    cross_label = "F1 cross #?"

                law3_reason = (
                    f"Observed in dihybrid F2 offspring of {cross_label} "
                    f"for traits '{trait_label1}' and '{trait_label2}': "
                    f"the four phenotype combinations appear in an approximately 9:3:3:1 ratio (N = {total})."
                )

                # don't break — keep scanning to collect all valid pairs

    # ---------------- Apply discoveries to app + UI ----------------
    new = []

    if not revealed:
        if law1_discovered and not getattr(app, "law1_ever_discovered", False) \
                and (target_law is None or target_law == 1):
            setattr(app, "law1_ever_discovered", True)
            setattr(app, "law1_first_plant", pid)
            new.append("law1")
            if toast and hasattr(app, "_toast"):
                try:
                    app._toast(f"Law 1 (Dominance) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

        if law2_discovered and not getattr(app, "law2_ever_discovered", False) \
                and (target_law is None or target_law == 2):
            setattr(app, "law2_ever_discovered", True)
            setattr(app, "law2_first_plant", pid)
            new.append("law2")
            if toast and hasattr(app, "_toast"):
                try:
                    app._toast(f"Law 2 (Segregation) discovered from plant #{pid}!", level="info")
                except Exception:
                    pass

        if law3_discovered and not getattr(app, "law3_ever_discovered", False) \
                and (target_law is None or target_law == 3):
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

    return {
        "law1": bool(law1_discovered),
        "law2": bool(law2_discovered),
        "law3": bool(law3_discovered),
        "new": new,
        # expose which specific trait/pair triggered each law (used by wizard)
        "law1_trait": law1_trait_name if law1_discovered else None,
        "law1_dominant_value": law1_dominant_value if law1_discovered else None,
        "law1_all_valid": law1_all_valid if law1_discovered else [],
        "law2_trait": law2_trait_name if law2_discovered else None,
        "law2_dominant_value": law2_dominant_value if law2_discovered else None,
        "law2_all_valid": law2_all_valid if law2_discovered else [],
        "law2_all_valid_ratios": law2_all_valid_ratios if law2_discovered else {},
        "law3_traits": tuple(law3_trait_pair) if (law3_discovered and law3_trait_pair) else None,
        "law3_all_valid_pairs": law3_all_valid_pairs if law3_discovered else [],
        "law3_all_valid_pairs_ratios": law3_all_valid_pairs_ratios if law3_discovered else {},
    }

# =============================================================================
# Mendelian law unlock thresholds (single source of truth)
# =============================================================================

# Law 1 (Dominance): how many phenotype-only F1 offspring (same phenotype) needed
LAW1_MIN_F1 = 16

# Law 2 (Segregation, ~3:1): minimum F2 sample size and acceptable dominant fraction band
LAW2_MIN_N = 65
LAW2_DOM_FRAC_MIN = 0.677  # 2.1:1  (2.1/3.1)
LAW2_DOM_FRAC_MAX = 0.796  # 3.9:1  (3.9/4.9)

# Law 3 (Independent Assortment, ~9:3:3:1): minimum dihybrid F2 sample size and chi-square threshold
LAW3_MIN_N = 80
LAW3_CHI2_MAX = 4.0

class TraitInheritanceExplorer(tk.Toplevel):
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

    def _on_canvas_node_click(self, event=None, source_canvas=None):
        c = source_canvas if source_canvas is not None else self.canvas
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
        if str(pid) == str(getattr(self, 'current_pid', None)):
            self._render_pid(str(pid))
        else:
            self._render_preview(str(pid))

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


        _mkbtn(tb, "Export Plant", self._export_selected_traits).pack(side="left")

        tk.Label(tb, text=" Find #", bg=self.BG, fg=self.FG).pack(side="left", padx=(12,4))
        self.find_entry = tk.Entry(tb, width=5)
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

        # ── Single right pane containing a two-tab notebook ────────────────────
        right_pane = tk.Frame(pw, bg=self.PANEL, highlightthickness=1, highlightbackground="#153242")
        pw.add(right_pane, weight=5)

        # ── Notebook tab styling ──────────────────────────────────────────────
        nb_style = ttk.Style()
        nb_style.theme_use("clam")
        nb_style.configure(
            "TIE.TNotebook",
            background=self.PANEL,
            borderwidth=0,
            tabmargins=[0, 0, 0, 0],
        )
        nb_style.configure(
            "TIE.TNotebook.Tab",
            background="#0f2535",
            foreground="#5a8fa8",
            padding=[12, 5],
            font=("Segoe UI", 11),
            borderwidth=0,
            focuscolor="#1e6fa0",
            focusthickness=0,
            relief="flat",
        )
        nb_style.map(
            "TIE.TNotebook.Tab",
            background=[("selected", "#1e6fa0"), ("active", "#16506e")],
            foreground=[("selected", "#ffffff"),  ("active",  "#cce8f5")],
            padding=[("selected", [16, 7])],
            font=[("selected", ("Segoe UI", 12, "bold"))],
            expand=[("selected", [0, 0, 0, 2])],
            focuscolor=[("selected", "#1e6fa0"), ("active", "#16506e")],
            relief=[("selected", "flat"), ("active", "flat")],
        )

        self.tie_notebook = ttk.Notebook(right_pane, style="TIE.TNotebook")
        self.tie_notebook.pack(side="top", fill="x", padx=4, pady=(4, 0))
        self.tie_notebook.enable_traversal()
        self.tie_notebook.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_changed())

        # ── Shared trait toolbar (below tab bar, above content) ───────────────
        self.trait_mode = tk.StringVar(value="Flowers")
        try:
            self.trait_mode.trace_add('write', lambda *a: self._refresh_views())
        except Exception:
            pass
        shared_toolbar = tk.Frame(right_pane, bg=self.PANEL)
        shared_toolbar.pack(side="top", fill="x", padx=self.PAD, pady=(6, 4))
        self._shared_toolbar = shared_toolbar
        for label in ("Flowers", "Pod color", "Pod shape", "Seed color", "Seed shape", "Height"):
            rb = tk.Radiobutton(shared_toolbar, text=label, variable=self.trait_mode, value=label,
                                bg=self.PANEL, fg=self.FG, selectcolor=self.CARD, activebackground=self.PANEL,
                                indicatoron=True, font=("Segoe UI", 10),
                                command=lambda: self._refresh_views())
            rb.pack(side="left", padx=(0, 12))

        # ── Content switcher — each tab's body frame lives here ───────────────
        tab_content = tk.Frame(right_pane, bg=self.PANEL)
        tab_content.pack(side="top", fill="both", expand=True, padx=4, pady=(0, 4))

        # ── Tab 1: Lineage tree ───────────────────────────────────────────────
        center = tk.Frame(tab_content, bg=self.PANEL)
        self._tab_frames = [center]   # index matches notebook tab order
        center.pack(fill="both", expand=True)
        self.tie_notebook.add(tk.Frame(self.tie_notebook, bg=self.PANEL, height=1), text="  Lineage  ")

        canvas_frame = tk.Frame(center, bg="#0b1a22", highlightthickness=0)
        canvas_frame.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        self.canvas = tk.Canvas(canvas_frame, bg="#0b1a22", highlightthickness=0)
        _tree_vscroll = tk.Scrollbar(canvas_frame, orient="vertical",   command=self.canvas.yview)
        _tree_hscroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=_tree_vscroll.set, xscrollcommand=_tree_hscroll.set)
        _tree_vscroll.pack(side="right",  fill="y")
        _tree_hscroll.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)

        def _tree_mousewheel(event):
            try:
                if event.state & 0x1:
                    self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        self.canvas.bind("<MouseWheel>", _tree_mousewheel)
        self.canvas.bind("<Button-4>",   lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>",   lambda e: self.canvas.yview_scroll( 1, "units"))

        # ── Tab 2: Pods (parents + siblings) ─────────────────────────────────
        self.tie_notebook.add(tk.Frame(self.tie_notebook, bg=self.PANEL, height=1), text="  Pod Seeds  ")
        right = tk.Frame(tab_content, bg=self.PANEL)
        self._tab_frames.append(right)

        pods_body = tk.Frame(right, bg=self.PANEL)
        pods_body.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        # Grid layout: col 0 = pods (expands), col 1 = ratio (natural width, top-anchored)
        pods_body.columnconfigure(0, weight=1)
        pods_body.columnconfigure(1, weight=0)
        pods_body.rowconfigure(1, weight=1)

        # Nav bar row 0, col 0 — hidden until >1 page
        self.pods_nav_frame = tk.Frame(pods_body, bg=self.PANEL)
        # gridded dynamically when needed

        # Pods canvas row 1, col 0
        self.pods_scroll_canvas = tk.Canvas(pods_body, bg=self.PANEL, highlightthickness=0)
        self.pods_scroll_canvas.grid(row=1, column=0, sticky="nsew")
        self.pods_hscroll = None

        # Ratio col 1, rows 0+1, top-anchored
        self.pods_tab_ratio_frame = tk.Frame(pods_body, bg=self.PANEL)
        self.pods_tab_ratio_frame.grid(row=0, column=1, rowspan=2, sticky="n", padx=(12, 0))

        # pods_row = permanent content frame inside canvas
        self.pods_row = tk.Frame(self.pods_scroll_canvas, bg=self.PANEL)
        self._pods_win = self.pods_scroll_canvas.create_window((0, 0), window=self.pods_row, anchor="nw")
        self.pods_row.bind("<Configure>",
            lambda e: self.pods_scroll_canvas.configure(
                scrollregion=self.pods_scroll_canvas.bbox("all")))
        # mousewheel horizontal scroll on pods canvas
        def _pods_hwheel(event):
            try:
                self.pods_scroll_canvas.xview_scroll(int(-1*(event.delta/120)), "units")
            except Exception:
                pass
        self.pods_scroll_canvas.bind("<MouseWheel>", _pods_hwheel)
        self.pods_scroll_canvas.bind("<Shift-MouseWheel>", _pods_hwheel)

        self.sibs_inner = self.pods_row   # compat: _render_siblings clears this
        self.pods_ratio_frame = self.sibs_inner
        self._pods_page = 0

        # ── Tab 3: Ratio ──────────────────────────────────────────────────────
        self.tie_notebook.add(tk.Frame(self.tie_notebook, bg=self.PANEL, height=1), text="  Trait Ratio  ")
        ratio_tab_body = tk.Frame(tab_content, bg=self.PANEL)
        self._tab_frames.append(ratio_tab_body)

        self.ratio_tab_frame = tk.Frame(ratio_tab_body, bg=self.PANEL)
        self.ratio_tab_frame.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        # ── Tab 4: Lineage + Pods combined ────────────────────────────────────
        self.tie_notebook.add(tk.Frame(self.tie_notebook, bg=self.PANEL, height=1), text="  Lineage + Pod Seeds  ")
        combo_outer = tk.Frame(tab_content, bg=self.PANEL)
        self._tab_frames.append(combo_outer)

        # ── Unified combo canvas: shared h+v scrollbars, tree left, ratio+pods right ──
        combo_body = tk.Frame(combo_outer, bg=self.PANEL)
        combo_body.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))

        _combo_vscroll = tk.Scrollbar(combo_body, orient="vertical")
        _combo_vscroll.pack(side="right", fill="y")
        _combo_hscroll = tk.Scrollbar(combo_body, orient="horizontal")
        _combo_hscroll.pack(side="bottom", fill="x")

        # One big canvas covering the full combo area
        self._combo_main_canvas = tk.Canvas(
            combo_body, bg=self.PANEL, highlightthickness=0,
            xscrollcommand=_combo_hscroll.set,
            yscrollcommand=_combo_vscroll.set)
        self._combo_main_canvas.pack(fill="both", expand=True)
        _combo_hscroll.config(command=self._combo_main_canvas.xview)
        _combo_vscroll.config(command=self._combo_main_canvas.yview)

        # Inner frame embedded in the big canvas
        self._combo_inner = tk.Frame(self._combo_main_canvas, bg=self.PANEL)
        self._combo_inner_win = self._combo_main_canvas.create_window(
            (0, 0), window=self._combo_inner, anchor="nw")

        # Left column: lineage tree canvas (sized to content after render)
        combo_left = tk.Frame(self._combo_inner, bg="#0b1a22")
        combo_left.pack(side="left", fill="y")   # no expand — sized by combo_canvas
        self.combo_canvas = tk.Canvas(combo_left, bg="#0b1a22", highlightthickness=0,
                                      width=600, height=500)
        self.combo_canvas.pack()
        self.combo_canvas.bind("<Button-1>",
            lambda e: self._on_canvas_node_click(e, source_canvas=self.combo_canvas))

        # Right column: ratio on top, nav+pods below (grows to fit content)
        combo_right = tk.Frame(self._combo_inner, bg=self.PANEL)
        combo_right.pack(side="left", fill="both", padx=(6, 0))
        self._combo_right = combo_right   # stored so _render_siblings can hide/show it

        # Combo right order: nav (top, hidden) → pods → ratio
        self.combo_nav_frame = tk.Frame(combo_right, bg=self.PANEL)
        # packed dynamically above sibs when >1 page

        # Pods — plain frame directly in combo_right; outer canvas scrolls everything
        self.combo_sibs_inner = tk.Frame(combo_right, bg=self.PANEL)
        self.combo_sibs_inner.pack(side="top", fill="x")
        # alias used in _render_siblings combo path
        self.combo_pods_canvas = combo_right

        self.combo_ratio_frame = tk.Frame(combo_right, bg=self.PANEL)
        self.combo_ratio_frame.pack(side="top", fill="x", pady=(6, 0))
        self.combo_ratio_frame.bind("<Configure>", lambda e: self._update_combo_scrollregion())
        self.combo_sibs_inner.bind("<Configure>", lambda e: self._update_combo_scrollregion())

        # Sync inner frame changes → outer scrollregion
        def _combo_inner_configure(e):
            self._combo_main_canvas.configure(
                scrollregion=self._combo_main_canvas.bbox("all"))
        self._combo_inner.bind("<Configure>", _combo_inner_configure)

        # Mousewheel: vertical on main canvas
        def _combo_vwheel(event):
            try:
                self._combo_main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except Exception:
                pass
        def _combo_hwheel(event):
            try:
                self._combo_main_canvas.xview_scroll(int(-1*(event.delta/120)), "units")
            except Exception:
                pass
        for _w in (self._combo_main_canvas, self.combo_canvas, self.combo_pods_canvas):
            _w.bind("<MouseWheel>", _combo_vwheel)
            _w.bind("<Shift-MouseWheel>", _combo_hwheel)
            _w.bind("<Button-4>", lambda e: self._combo_main_canvas.yview_scroll(-1,"units"))
            _w.bind("<Button-5>", lambda e: self._combo_main_canvas.yview_scroll( 1,"units"))

        # No PanedWindow → no self.combo_pw; set a dummy for _auto_resize_window compat
        self.combo_pw = None

        # ── Tab 5: Cross Diagrams (Punnett square) ────────────────────────────
        self.tie_notebook.add(tk.Frame(self.tie_notebook, bg=self.PANEL, height=1), text="  Punnett Square  ")
        cross_outer = tk.Frame(tab_content, bg=self.PANEL)
        self._tab_frames.append(cross_outer)

        # ── Reorder tabs: Combo→2, Punnett→3, Trait Ratio→4 ───────────────
        # Original order: Lineage(0), Pod Seeds(1), Trait Ratio(2), Combo(3), Punnett(4)
        # Target  order: Lineage(0), Pod Seeds(1), Combo(2), Punnett(3), Trait Ratio(4)
        # NOTE: cross_outer must already be in _tab_frames (done above) before this runs.
        try:
            _tabs = self.tie_notebook.tabs()
            self.tie_notebook.insert(2, _tabs[3])   # Combo: 3→2
            _tabs = self.tie_notebook.tabs()
            self.tie_notebook.insert(3, _tabs[4])   # Punnett: 4→3  (Ratio falls to 4)
            _tf = list(self._tab_frames)             # copy before reassigning
            self._tab_frames = [_tf[0], _tf[1], _tf[3], _tf[4], _tf[2]]
        except Exception:
            pass

        cross_ctrl = tk.Frame(cross_outer, bg=self.PANEL)
        cross_ctrl.pack(side="top", fill="x", padx=self.PAD, pady=(self.PAD, 4))

        self._cross_mode = tk.StringVar(value="Monohybrid")
        tk.Label(cross_ctrl, text="Type:", bg=self.PANEL, fg=self.FG,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        for _cm, _cv in (("Monohybrid  3:1", "Monohybrid"), ("Dihybrid  9:3:3:1", "Dihybrid")):
            tk.Radiobutton(cross_ctrl, text=_cm, variable=self._cross_mode, value=_cv,
                           bg=self.PANEL, fg=self.FG, selectcolor=self.CARD,
                           activebackground=self.PANEL, activeforeground=self.FG,
                           font=("Segoe UI", 10),
                           command=lambda: self.after(10, self._on_cross_settings_changed)
                           ).pack(side="left", padx=(10, 0))

        _CROSS_TRAITS = [
            ("Flower Color",    "flower_color"),    ("Flower Position", "flower_position"),
            ("Pod Color",       "pod_color"),       ("Pod Shape",       "pod_shape"),
            ("Seed Color",      "seed_color"),      ("Seed Shape",      "seed_shape"),
            ("Plant Height",    "plant_height"),
        ]
        self._cross_trait_labels = [t[0] for t in _CROSS_TRAITS]
        self._cross_trait_keys   = [t[1] for t in _CROSS_TRAITS]

        tk.Label(cross_ctrl, text="  Trait 1:", bg=self.PANEL, fg=self.FG,
                 font=("Segoe UI", 11)).pack(side="left", padx=(20, 0))
        self._cross_t1 = tk.StringVar(value=self._cross_trait_labels[3])  # Seed Color
        self._cross_t1_menu = tk.OptionMenu(
            cross_ctrl, self._cross_t1, *self._cross_trait_labels,
            command=lambda *_: self.after(10, self._on_cross_settings_changed))
        self._cross_t1_menu.config(bg=self.CARD, fg=self.FG, activebackground=self.CARD,
                                    activeforeground=self.FG, highlightthickness=0,
                                    relief="flat", font=("Segoe UI", 10))
        self._cross_t1_menu["menu"].config(bg=self.CARD, fg=self.FG)
        self._cross_t1_menu.pack(side="left", padx=(4, 0))

        self._cross_t2_lbl = tk.Label(cross_ctrl, text="  Trait 2:", bg=self.PANEL, fg=self.FG,
                                       font=("Segoe UI", 11))
        self._cross_t2_lbl.pack(side="left", padx=(16, 0))
        self._cross_t2 = tk.StringVar(value=self._cross_trait_labels[4])  # Seed Shape
        self._cross_t2_menu = tk.OptionMenu(
            cross_ctrl, self._cross_t2, *self._cross_trait_labels,
            command=lambda *_: self.after(10, self._on_cross_settings_changed))
        self._cross_t2_menu.config(bg=self.CARD, fg=self.FG, activebackground=self.CARD,
                                    activeforeground=self.FG, highlightthickness=0,
                                    relief="flat", font=("Segoe UI", 10))
        self._cross_t2_menu["menu"].config(bg=self.CARD, fg=self.FG)
        self._cross_t2_menu.pack(side="left", padx=(4, 0))

        # "Best fit" button — scans the full archive and selects the trait(s)
        # that best match 9:3:3:1 (Dihybrid) or 3:1 (Monohybrid).
        # Also serves as the pack anchor for Trait 2 re-insertion.
        self._cross_best_btn = tk.Button(
            cross_ctrl, text="⟳ Best fit", bg="#1e4d6b", fg=self.FG,
            relief="flat", bd=0, font=("Segoe UI", 9), padx=10,
            command=self._cross_auto_detect)
        self._cross_best_btn.pack(side="left", padx=(16, 0))

        _cross_scroll_wrap = tk.Frame(cross_outer, bg=self.PANEL)
        _cross_scroll_wrap.pack(fill="both", expand=True, padx=self.PAD, pady=(0, self.PAD))
        _cross_vsb = tk.Scrollbar(_cross_scroll_wrap, orient="vertical")
        _cross_vsb.pack(side="right", fill="y")
        _cross_hsb = tk.Scrollbar(_cross_scroll_wrap, orient="horizontal")
        _cross_hsb.pack(side="bottom", fill="x")
        self.cross_canvas = tk.Canvas(_cross_scroll_wrap, bg="#0d1f2e",
                                       highlightthickness=0,
                                       xscrollcommand=_cross_hsb.set,
                                       yscrollcommand=_cross_vsb.set)
        self.cross_canvas.pack(fill="both", expand=True)
        _cross_hsb.config(command=self.cross_canvas.xview)
        _cross_vsb.config(command=self.cross_canvas.yview)
        self._cross_img_refs = []

        # ── Initial window sizing (one-shot) ──────────────────────────────────
        def _fix_sash():
            try:
                pw.update_idletasks()
                left_w  = 230
                total_w = max(1024, left_w + 1060 + 36)   # left + notebook + chrome
                pw.sashpos(0, left_w)
                cur_h = self.winfo_height()
                self.geometry(f"{total_w}x{max(600, cur_h if cur_h > 1 else 700)}")
            except Exception:
                pass
        def _fix_sash_once():
            _fix_sash()
            self._layout_done = True
        self.after(50, _fix_sash_once)

        self._img_refs = []
        self._all_ids, self._ids = [], []
        self.current_pid = None
        self._pods_pid = None
        self._saved_preview_pid = None
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
        pass  # parents_right removed
        for w in self.traits_container.winfo_children(): w.destroy()
        for w in self.pods_row.winfo_children(): w.destroy()
        for w in self.pods_nav_frame.winfo_children(): w.destroy()
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
            # sync live plants into archive first (catches the most recently bred plant)
            try:
                app_ref = getattr(self, "app", None)
                if app_ref and hasattr(app_ref, "_seed_archive_safe"):
                    app_ref._seed_archive_safe()
            except Exception:
                pass
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
        law1_all_valid = []          # (trait_key, dominant_value) pairs

        # --- Law 2 (Segregation) detection for THIS plant ------------------
        law2_discovered = False
        law2_reason = ""
        law2_ratio_str = ""      # e.g. "3,21:1"
        law2_trait_name = ""     # human-readable trait label
        law2_all_valid = []          # (trait_key, dominant_value) pairs
        law2_all_valid_ratios = {}   # trait_key -> ratio string

        # --- Law 3 (Independent Assortment) detection for THIS plant -------
        law3_discovered = False
        law3_reason = ""
        law3_ratio_str = ""      # e.g. "45:14:15:6" or "9:3:3:1"
        law3_trait_pair = ()     # (trait_label1, trait_label2)
        law3_all_valid_pairs = []         # (tk1, tk2) pairs
        law3_all_valid_pairs_ratios = {}  # frozenset({tk1,tk2}) -> ratio string



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

                    law2_trait_name = tk  # store raw key so wizard can compare directly
                    law2_dominant_value = dom_pheno
                    law2_all_valid.append((tk, dom_pheno))
                    law2_all_valid_ratios[tk] = law2_ratio_str

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

                                law3_all_valid_pairs.append((tk1, tk2))
                                law3_all_valid_pairs_ratios[frozenset({tk1, tk2})] = law3_ratio_str
                                # don't break — collect all valid pairs

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
            f"Unlock: N ≥ {LAW2_MIN_N} F2 offspring, dominant-to-recessive ratio "
            f"between 2.1:1 and 3.9:1 (≈3:1)."
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

        def _parse_F(s):
            try:
                s = str(s or "")
                if s.startswith("F") and s[1:].isdigit():
                    return int(s[1:])
            except Exception:
                pass
            return None

        # ── Step 1: BFS upward to collect all ancestor nodes ─────────────────
        # Each node is visited at most once; parent_map stores its parents.
        to_visit = [str(root)]
        visited   = {str(root)}
        parent_map = {}   # pid_str → (m_str | None, f_str | None)
        while to_visit:
            pid = to_visit.pop(0)
            m, f = parents(pid)
            m_s = str(m) if m is not None and get_snap(str(m)) is not None else None
            f_s = str(f) if f is not None and get_snap(str(f)) is not None else None
            parent_map[pid] = (m_s, f_s)
            for par in (m_s, f_s):
                if par is not None and par not in visited:
                    visited.add(par)
                    to_visit.append(par)

        # ── Step 2: Assign each node to a unique display row ─────────────────
        # Primary key: actual generation number Fn (higher n → lower in tree).
        # Fallback for unknown generation: structural depth from root.
        g0 = _parse_F(generation(str(root)))

        struct_depth = {str(root): 0}
        queue = [str(root)]
        while queue:
            pid = queue.pop(0)
            for par in parent_map.get(pid, (None, None)):
                if par is not None and par not in struct_depth:
                    struct_depth[par] = struct_depth[pid] + 1
                    queue.append(par)

        # display_row: larger value = higher in tree (older ancestor)
        node_row = {}
        for pid_s in visited:
            gn = _parse_F(generation(pid_s))
            if gn is not None and g0 is not None:
                node_row[pid_s] = g0 - gn           # e.g. F0 plant → g0-0 = g0 (top)
            elif gn is not None:
                node_row[pid_s] = gn                 # no g0 fallback
            else:
                node_row[pid_s] = struct_depth.get(pid_s, 0)

        # ── Step 3: Ensure every parent is strictly above its child ──────────
        # Iteratively push parents one row higher if they sit at or below a child.
        # This handles same-generation parent-child (e.g. #386 F4 → #444 F4).
        changed = True
        MAX_ITER = len(visited) + 2
        iters    = 0
        while changed and iters < MAX_ITER:
            changed = False
            iters  += 1
            for pid_s in list(visited):
                child_row = node_row[pid_s]
                for par in parent_map.get(pid_s, (None, None)):
                    if par is not None and node_row.get(par, 0) <= child_row:
                        node_row[par] = child_row + 1
                        changed = True

        # ── Step 4: Group nodes into rows, sort top-down ─────────────────────
        rows = {}
        for pid_s, rn in node_row.items():
            rows.setdefault(rn, []).append(pid_s)

        layers = []
        for rn in sorted(rows.keys(), reverse=True):   # largest row → oldest ancestor → top
            row = rows[rn]
            # Label from actual generation of nodes in this row
            label = None
            for p in row:
                gn = _parse_F(generation(p))
                if gn is not None:
                    label = f"F{gn}"
                    break
            if label is None:
                # Fallback: derive from root's generation and offset
                if g0 is not None:
                    offset = g0 - rn
                    label  = f"F{max(0, offset)}" if offset >= 0 else "F0"
                else:
                    label = "F?"
            # Sort nodes within a row by their plant id for a stable left-to-right order
            row_sorted = sorted(row, key=lambda s: (int(s) if s.isdigit() else float("inf"), s))
            layers.append((label, row_sorted))

        # Root always last (bottom of tree)
        if str(root) not in {p for _, row in layers for p in row}:
            layers.append((f"F{g0}" if g0 is not None else "F?", [str(root)]))

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
                col = str(traits.get("flower_color", "")).lower()
                # Build candidate paths: hi-res with known colors first, then
                # non-hi variants, then generic — all loaded via PIL because
                # tkinter PhotoImage cannot open these 64x64 PNG files.
                _fp_candidates = []
                for _col in ([col] if col else []) + ["purple", "white"]:
                    try:
                        _fp_candidates.append(flower_icon_path_hi(pos, _col))
                    except Exception:
                        pass
                    try:
                        _fp_candidates.append(flower_icon_path(pos, _col))
                    except Exception:
                        pass
                try:
                    _fp_candidates.append(trait_icon_path("flower_position", pos))
                except Exception:
                    pass
                for p in _fp_candidates:
                    if not p:
                        continue
                    try:
                        from PIL import Image as _PILImg, ImageTk as _PILTk
                        _pil = _PILImg.open(p).convert("RGBA")
                        _tgt = max(1, int(round(64 * float(sx))))
                        _pil = _pil.resize((_tgt, _tgt), _PILImg.LANCZOS)
                        im = _PILTk.PhotoImage(_pil)
                        return im
                    except Exception:
                        pass

            # Combined pod color/shape when asked for pod shape family
            if trait_key in ("pod_shape", "pod_color_shape", "pod"):
                c = str(traits.get("pod_color", "")).lower()
                s = str(traits.get("pod_shape", "")).lower()
                c = "green" if "green" in c else ("yellow" if "yellow" in c else c)
                s = "constricted" if "constrict" in s else ("inflated" if "inflate" in s else s)
                # Try known colors if c is empty (e.g. fake dict had no pod_color)
                for _pc in ([c] if c else []) + ["green", "yellow"]:
                    try:
                        p = pod_shape_icon_path(s, _pc)
                    except Exception:
                        p = ""
                    if p:
                        try:
                            from PIL import Image as _PILImg, ImageTk as _PILTk
                            _pil = _PILImg.open(p).convert("RGBA")
                            _tgt = max(1, int(round(64 * float(sx))))
                            _pil = _pil.resize((_tgt, _tgt), _PILImg.LANCZOS)
                            im = _PILTk.PhotoImage(_pil)
                            return im
                        except Exception:
                            pass

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
        def g(k, default=None): return snap.get(k, default) if isinstance(snap, dict) else getattr(snap, k, default)
        self.lbl_left_title.config(text=f"Plant {g('generation','F?')} #{g('id', pid)}")
        self.lbl_left_parents.config(text=f"Parents: ♀ #{g('mother_id','?')}  |  ♂ #{g('father_id','?')}")
        self._render_traits(snap)

        try:
            tab_idx = self.tie_notebook.index(self.tie_notebook.select())
        except Exception:
            tab_idx = 0
        root_id = getattr(self, "current_pid", None)

        if tab_idx == 2:
            self._render_siblings(g('id', pid),
                                  target_sibs=self.combo_sibs_inner,
                                  target_ratio=self.combo_ratio_frame)
            tgt = root_id if root_id is not None else pid
            self._draw_canvas_family(tgt, target_canvas=self.combo_canvas)
        else:
            self._render_siblings(g('id', pid))
            tgt = root_id if root_id is not None else pid
            self._draw_canvas_family(tgt)

    def _refresh_views(self):
        """Re-render tree and sibling pods on trait-mode change or other triggers."""
        try:
            self._img_refs = []
            root_id = getattr(self, "current_pid", None)
            prev    = getattr(self, "preview_pid", None)
            try:
                _tab = self.tie_notebook.index(self.tie_notebook.select())
            except Exception:
                _tab = 0
            # On Lineage/combo: use preview if active; on Pods/Ratio: use _pods_pid
            if _tab in (0, 2):
                pid = prev or root_id
            elif _tab in (1, 4):
                pid = getattr(self, "_pods_pid", None) or root_id
            else:
                pid = root_id

            tab_idx = _tab

            if tab_idx == 4:
                self._render_ratio_tab(root_id or pid)
            elif tab_idx == 2:
                if root_id is not None:
                    self._draw_canvas_family(root_id, target_canvas=self.combo_canvas)
                if pid is not None:
                    self._render_siblings(pid,
                                          target_sibs=self.combo_sibs_inner,
                                          target_ratio=self.combo_ratio_frame)
            else:
                if root_id is not None:
                    self._draw_canvas_family(root_id)
                if pid is not None:
                    self._render_siblings(pid)
        except Exception:
            pass

    # Edge-color palette — one per unique PARENT NODE.
    # Coloring by individual parent (not parent-pair) makes it immediately clear
    # which lines originate from which plant.  When two parents each connect to
    # two children, the four lines form a visual × with each "arm" in its own color.
    # Palette is perceptually distinct on dark backgrounds.
    _EDGE_PALETTE = [
        "#2a8fc4",   # vivid sky-blue
        "#d4662a",   # warm orange
        "#2ab88a",   # teal-green
        "#c45a9a",   # rose-purple
        "#d4b02a",   # golden-yellow
        "#6a4ac4",   # violet
        "#2ac45a",   # grass-green
        "#c42a2a",   # red
        "#2a6ac4",   # mid-blue
        "#c49a2a",   # amber
    ]

    def _draw_canvas_family(self, pid, target_canvas=None):
            c = target_canvas if target_canvas is not None else self.canvas
            c.delete("all")

            try:
                c.update_idletasks()
            except Exception:
                pass

            vp_w = max(c.winfo_width(),  480)
            vp_h = max(c.winfo_height(), 400)

            node_outer = "#34b3e6"
            node_fill  = "#193644"

            layers = self._build_layers_archive(pid)
            if not layers:
                c.create_text(vp_w // 2, vp_h // 2, text="No archive data",
                              fill=self.MUTED, font=("Segoe UI", 12, "bold"))
                c.configure(scrollregion=(0, 0, vp_w, vp_h))
                return

            # ── Vertical spacing — fixed generous step, canvas scrolls ────────
            L = len(layers)
            try:
                title_h = tk.font.Font(family="Segoe UI", size=16).metrics("linespace")
            except Exception:
                title_h = 24
            top_margin  = 12 + title_h + 20
            y_step      = max(100, int(130 * (getattr(self, "SPACING_SCALE_Y", 0.75) or 0.75))) + 15
            y_positions = [top_margin + i * y_step for i in range(L)]

            # ── Helpers ───────────────────────────────────────────────────────
            def parents_of(sid):
                s = self._get_snap(sid)
                return self._parents_from_snapshot(s) if s else (None, None)

            def is_selfed(sid):
                m, f = parents_of(sid)
                return (m is not None and f is not None and str(m) == str(f))

            child_map = {}
            for _lbl, row in layers:
                for p in row:
                    m, f = parents_of(p)
                    for par in (m, f):
                        if par is not None:
                            sp = str(par)
                            child_map.setdefault(sp, [])
                            if p not in child_map[sp]:
                                child_map[sp].append(p)

            # ── Uniform grid horizontal layout ────────────────────────────────
            # All nodes live on a shared column grid.  Column index is a float
            # so a single node centred between two others sits at e.g. col 0.5.
            # Minimum spacing between siblings in the same row: 1.0 column.
            # The widest layer is anchored first; every other layer is derived
            # by cascading outward (upward toward ancestors, downward toward
            # offspring), always centering a node over the mean column of its
            # adjacent-layer relatives.
            x_pad       = 60
            GEN_LABEL_W = 48
            NODE_STEP   = 120   # pixels per column unit

            n_max = max(len(row) for _, row in layers)
            content_w = GEN_LABEL_W + x_pad + n_max * NODE_STEP + x_pad

            def _cx(col_f):
                """Float column index → pixel x, centred within its slot."""
                return GEN_LABEL_W + x_pad + (col_f + 0.5) * NODE_STEP

            col = {}   # str(pid) → float column index

            def _place_layer(row, desired):
                """
                Assign final column indices to all nodes in `row`.

                1. Sort nodes by desired column (left to right).
                2. Enforce a minimum gap of 1.0 column between neighbours.
                3. Re-centre the whole row around the mean desired column so
                   the group stays over its children / parents.
                """
                ordered = sorted([str(p) for p in row],
                                 key=lambda sp: desired.get(sp, (n_max - 1) / 2.0))
                mid_ref = (n_max - 1) / 2.0
                cs = [desired.get(sp, mid_ref) for sp in ordered]
                # enforce minimum 1-column gap
                for j in range(1, len(cs)):
                    if cs[j] - cs[j - 1] < 1.0:
                        cs[j] = cs[j - 1] + 1.0
                # re-centre around the mean of the desired (pre-push) positions
                if len(cs) > 1:
                    desired_mid = sum(desired.get(sp, mid_ref) for sp in ordered) / len(ordered)
                    current_mid = (cs[0] + cs[-1]) / 2.0
                    shift = desired_mid - current_mid
                    cs = [c + shift for c in cs]
                for sp, c in zip(ordered, cs):
                    col[sp] = c

            # 1. Anchor the widest layer at evenly-spaced integer columns.
            widest_idx  = max(range(len(layers)), key=lambda i: len(layers[i][1]))
            _, wide_row = layers[widest_idx]
            n_wide      = len(wide_row)
            start_col   = (n_max - n_wide) / 2.0   # centre within the grid
            for i, p in enumerate(wide_row):
                col[str(p)] = start_col + float(i)

            # 2. Cascade UPWARD: centre each ancestor over its children's columns.
            for i in range(widest_idx - 1, -1, -1):
                _, row     = layers[i]
                _, adj_row = layers[i + 1]
                adj_set    = set(adj_row)
                desired    = {}
                for p in row:
                    sp   = str(p)
                    kids = [k for k in child_map.get(sp, [])
                            if k in col and k in adj_set]
                    if not kids:
                        kids = [k for k in child_map.get(sp, []) if k in col]
                    desired[sp] = (sum(col[k] for k in kids) / len(kids)
                                   if kids else (n_max - 1) / 2.0)
                _place_layer(row, desired)

            # 3. Cascade DOWNWARD: centre each offspring below its parents' columns.
            for i in range(widest_idx + 1, len(layers)):
                _, row     = layers[i]
                _, adj_row = layers[i - 1]
                adj_set    = set(adj_row)
                desired    = {}
                for p in row:
                    sp   = str(p)
                    m, f = parents_of(sp)
                    pcols = [col[str(par)] for par in (m, f)
                             if par is not None and str(par) in col
                             and str(par) in adj_set]
                    if not pcols:
                        pcols = [col[str(par)] for par in (m, f)
                                 if par is not None and str(par) in col]
                    desired[sp] = (sum(pcols) / len(pcols)
                                   if pcols else (n_max - 1) / 2.0)
                _place_layer(row, desired)

            # 4. Convert column indices → pixel positions.
            pos = {}
            for li, (_, row) in enumerate(layers):
                for p in row:
                    sp = str(p)
                    if sp in col:
                        pos[sp] = (_cx(col[sp]), y_positions[li])

            # ── Snap selfed-only parents to exactly their child's x ───────────
            for i in range(len(layers) - 2, -1, -1):
                _, row = layers[i]
                _, nxt = layers[i + 1]
                adj    = set(nxt)
                for p in row:
                    sp       = str(p)
                    adj_kids = [k for k in child_map.get(sp, [])
                                if k in pos and k in adj]
                    if len(adj_kids) == 1:
                        ck = adj_kids[0]
                        cm, cf = parents_of(ck)
                        if (cm is not None and cf is not None
                                and str(cm) == sp and str(cf) == sp):
                            pos[sp] = (pos[ck][0], pos[sp][1])

            # ── Prune orphans ─────────────────────────────────────────────────
            # Keep a node only if it has at least one child that is also in pos.
            # The bottom row is always kept.  Repeat until stable (handles chains).
            _, bottom_row = layers[-1]
            for _ in range(len(layers)):   # max passes = depth of tree
                has_child = set(bottom_row)
                for idx in range(1, len(layers)):
                    _, row = layers[idx]
                    for sid in row:
                        if sid not in pos:
                            continue
                        m, f = parents_of(sid)
                        for ppid in (m, f):
                            if ppid is not None and str(ppid) in pos:
                                has_child.add(str(ppid))
                new_pos = {p: xy for p, xy in pos.items() if p in has_child}
                if new_pos == pos:
                    break
                pos = new_pos
            # Rebuild layers to match pruned pos
            layers = [(lbl, [p for p in row if p in pos]) for lbl, row in layers]
            layers = [(lbl, row) for lbl, row in layers if row]
            if not layers:
                c.create_text(vp_w // 2, vp_h // 2, text="No archive data",
                              fill=self.MUTED, font=("Segoe UI", 12, "bold"))
                c.configure(scrollregion=(0, 0, vp_w, vp_h))
                return

            # ── Recompute y_positions for the (possibly smaller) pruned layer set ──
            # The original y_positions were based on pre-prune layer count.  Any
            # removed rows would leave a gap, so we recompute from scratch and
            # re-synchronise every node's y-coordinate in pos.
            L_pruned    = len(layers)
            y_positions = [top_margin + i * y_step for i in range(L_pruned)]
            for li, (_, row) in enumerate(layers):
                for pid_str in row:
                    if pid_str in pos:
                        pos[pid_str] = (pos[pid_str][0], y_positions[li])

            # Actual bounding box → scrollregion
            all_xs = [x for x, _ in pos.values()]
            all_ys = [y for _, y in pos.values()]
            # Use actual rightmost node position — don't pad with full content_w
            actual_max_x = (max(all_xs) if all_xs else 0)
            real_w = actual_max_x + x_pad + 80
            # Use actual content height (not clamped to viewport) so tall F3/F4
            # trees correctly drive the auto-resize.
            content_h = (max(all_ys) if all_ys else 0) + 120
            real_h    = max(content_h, vp_h)
            c.configure(scrollregion=(0, 0, real_w, real_h))

            # ── Store raw content size for auto-resize (no vp_h floor) ────────
            is_combo = (target_canvas is not None)
            if is_combo:
                self._combo_tree_w = int(actual_max_x + x_pad + 80)
                self._combo_tree_h = int(content_h)
                try:
                    # Size the tree canvas exactly to its content
                    self.combo_canvas.configure(
                        width=self._combo_tree_w,
                        height=self._combo_tree_h)
                    self._update_combo_scrollregion()
                except Exception:
                    pass
            else:
                self._tree_content_w = int(actual_max_x + x_pad + 80)
                self._tree_content_h = int(content_h)
                # Resize window to fit the tree — lineage tab has no other resize trigger
                self.after(80, self._auto_resize_window)

            # ── Title ─────────────────────────────────────────────────────────
            c.create_text(12, 12, anchor="nw", text="Lineage",
                          fill=self.MUTED, font=("Segoe UI", 16))

            # ── Build per-parent-node color map ──────────────────────────────
            # Each unique parent node gets its own color from the palette.
            # Edges are then drawn in the color of their source (parent) node,
            # so you can instantly see which lines come from which plant.
            # When two parents connect to two children the four curves cross and
            # each "arm" of the X is in the parent's individual color.
            node_color_map = {}   # str(parent_pid) → hex color
            palette = self._EDGE_PALETTE
            palette_idx = [0]

            def _node_color(pid_str):
                if pid_str not in node_color_map:
                    node_color_map[pid_str] = palette[palette_idx[0] % len(palette)]
                    palette_idx[0] += 1
                return node_color_map[pid_str]

            # Pre-assign colors top-down so the assignment is deterministic.
            for _lbl, row in layers:
                for p in row:
                    m, f = parents_of(p)
                    for par in (m, f):
                        if par is not None:
                            _node_color(str(par))

            # ── Draw connectors ───────────────────────────────────────────────
            # Style: cubic S-curve that departs *vertically* from the parent node
            # and arrives *vertically* at the child node.  The two Bezier control
            # points stay at the same x as their respective endpoints, so the curve
            # is smooth and tree-like but still sweeps diagonally between nodes at
            # different x positions.  When two parents each connect to two children
            # (a cross), the two curves physically intersect mid-way, forming a
            # graceful × that makes the breeding event immediately readable.
            #
            # Approximation via tkinter smooth=True spline with 4 points:
            #   P0 = (x1, y1+r)                          — parent bottom
            #   P1 = (x1, y1+r + span*0.45)              — upper ctrl, x locked to parent
            #   P2 = (x2, y2-r - span*0.45)              — lower ctrl, x locked to child
            #   P3 = (x2, y2-r)                          — child top
            r_connect = 26
            drawn_edges = set()

            for idx in range(1, len(layers)):
                _, row = layers[idx]
                for sid in row:
                    m, f   = parents_of(sid)
                    selfed = (m is not None and f is not None and str(m) == str(f))

                    for ppid in (m, f):
                        if ppid is None:
                            continue
                        sp       = str(ppid)
                        edge_key = (sp, sid)
                        if edge_key in drawn_edges or sp not in pos or sid not in pos:
                            continue
                        drawn_edges.add(edge_key)

                        color  = _node_color(sp)
                        x1, y1 = pos[sp]
                        x2, y2 = pos[sid]
                        span   = max(1, (y2 - r_connect) - (y1 + r_connect))
                        ctrl   = span * 0.45

                        if selfed:
                            # Selfed → x1 ≈ x2: draw a clean vertical S so any
                            # tiny residual x-offset stays invisible.
                            c.create_line(
                                x1, y1 + r_connect,
                                x1, y1 + r_connect + ctrl,
                                x2, y2 - r_connect - ctrl,
                                x2, y2 - r_connect,
                                smooth=True, width=self.LINK_W, fill=color,
                                tags=("edge",),
                            )
                        else:
                            # Cross → elegant cubic S that sweeps from parent x
                            # to child x.  Opposite-direction curves from two
                            # parents will naturally intersect to form a visible ×.
                            c.create_line(
                                x1, y1 + r_connect,
                                x1, y1 + r_connect + ctrl,
                                x2, y2 - r_connect - ctrl,
                                x2, y2 - r_connect,
                                smooth=True, width=self.LINK_W, fill=color,
                                tags=("edge",),
                            )
            try:
                c.tag_lower("edge")
            except Exception:
                pass

            # ── Highlight logic ───────────────────────────────────────────────
            # Preview active → previewed node = gold, bottom plant = plain
            # No preview     → bottom (current) plant = gold
            cur_id         = str(getattr(self, "current_pid", "") or "")
            prev_id        = str(getattr(self, "preview_pid", "") or "")
            gold_id        = prev_id if prev_id else cur_id

            def _node_colors(pid_str):
                if pid_str == gold_id:
                    return "#f4c542", "#5a3b00", self.NODE_OUTER_W + 1
                return node_outer, node_fill, self.NODE_OUTER_W

            # ── Trait icon key ────────────────────────────────────────────────
            try:
                mode = (self.trait_mode.get() or "Flowers").lower()
            except Exception:
                mode = "flowers"
            icon_key = {
                "flowers":    "flower_color",
                "pod color":  "pod_color",
                "pod shape":  "pod_shape",
                "seed color": "seed_color",
                "seed shape": "seed_shape",
                "height":     "plant_height",
            }.get(mode, "flower_color")

            # ── Draw nodes ────────────────────────────────────────────────────
            for (label, row), y in zip(layers, y_positions):
                c.create_text(14, y, anchor="w", text=str(label),
                              fill=self.MUTED, font=("Segoe UI", 12, "bold"))
                for pid_str in row:
                    if pid_str not in pos:
                        continue
                    x, y    = pos[pid_str]
                    snap    = self._get_snap(pid_str)
                    r1, r2  = 28, 24
                    outer_color, inner_color, outer_w = _node_colors(pid_str)

                    c.create_oval(x - r1, y - r1, x + r1, y + r1,
                                  outline=outer_color, width=outer_w,
                                  tags=(f"node_{pid_str}", "node"))
                    c.create_oval(x - r2, y - r2, x + r2, y + r2,
                                  fill=inner_color, outline="",
                                  tags=(f"node_{pid_str}", "node"))
                    try:
                        im = self._icon_for_snap(icon_key, snap,
                                                 sx=self.SCALE_NODE, sy=self.SCALE_NODE)
                        if im is not None:
                            c.create_image(x, y, image=im,
                                           tags=(f"node_{pid_str}", "node"))
                            self._img_refs.append(im)
                    except Exception:
                        pass
                    c.create_text(x + r1 + 4, y, anchor="w",
                                  text=f"#{pid_str}", fill=self.FG,
                                  font=self.NODE_LABEL_FONT,
                                  tags=(f"node_{pid_str}", "node"))

            try:
                if c is self.combo_canvas:
                    c.tag_bind("node", "<Button-1>",
                               lambda e: self._on_canvas_node_click(e, source_canvas=self.combo_canvas))
                else:
                    c.tag_bind("node", "<Button-1>", self._on_canvas_node_click)
            except Exception:
                pass

            except Exception as e:
                c.create_text(20, 20, anchor="nw", text=f"Tree error: {e}",
                              fill="#ffb4b4", font=("Segoe UI", 12, "bold"))
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

            text_col = tk.Frame(row, bg=self.PANEL)
            text_col.pack(side="left", padx=(8, 4))
            tk.Label(
                text_col,
                text=f"{name.replace('_',' ')}:",
                bg=self.PANEL,
                fg=self.FG,
                font=label_font
            ).pack(anchor="w")
            tk.Label(
                text_col,
                text=f"{value}",
                bg=self.PANEL,
                fg=self.FG,
                font=value_font
            ).pack(anchor="w")

    def _populate_ratio_panel(self, panel, ratio_text, law_parts):
        """Clear panel and render a boxed ratio display."""
        for w in panel.winfo_children():
            w.destroy()
        # outer box
        box = tk.Frame(panel, bg="#12303f",
                       highlightthickness=2, highlightbackground="#2a5a7a")
        box.pack(fill="x", padx=10, pady=16)
        tk.Label(box, text="Total ratio",
                 bg="#12303f", fg=self.MUTED,
                 font=("Segoe UI", 11)).pack(pady=(10, 2))
        tk.Label(box, text=ratio_text,
                 bg="#12303f", fg=self.FG,
                 font=("Segoe UI", 14, "bold"),
                 wraplength=150, justify="center").pack(padx=8, pady=(0, 10))
        for lp in law_parts:
            tk.Frame(panel, height=1, bg="#2a5a7a").pack(fill="x", padx=10, pady=(4, 4))
            tk.Label(panel, text=lp,
                     bg=self.PANEL, fg=self.MUTED,
                     font=("Segoe UI", 10, "italic"),
                     wraplength=160, justify="center").pack(fill="x", padx=6)

    def _render_siblings(self, pid, target_sibs=None, target_ratio=None):
        _sibs_frame  = target_sibs  if target_sibs  is not None else self.sibs_inner
        _ratio_frame = target_ratio if target_ratio is not None else self.pods_ratio_frame
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

        is_combo = (target_sibs is not None)

        # --- resolve persistent canvas/row/nav targets ---
        if is_combo:
            pods_canvas = self.combo_pods_canvas
            pods_row_frame = self.combo_sibs_inner
            nav_frame = self.combo_nav_frame
            _win_id = None
            # hide the whole right column while rebuilding to prevent flicker
            try:
                self._combo_right.pack_forget()
            except Exception:
                pass
            # clear content frames
            for w in pods_row_frame.winfo_children(): w.destroy()
            for w in nav_frame.winfo_children(): w.destroy()
            for w in self.combo_ratio_frame.winfo_children(): w.destroy()
        else:
            pods_canvas = self.pods_scroll_canvas
            pods_row_frame = self.pods_row
            nav_frame = self.pods_nav_frame
            _win_id = getattr(self, "_pods_win", None)
            # hide during rebuild to prevent flicker
            try:
                if _win_id:
                    pods_canvas.itemconfig(_win_id, state="hidden")
            except Exception:
                pass
            for w in pods_row_frame.winfo_children(): w.destroy()
            for w in nav_frame.winfo_children(): w.destroy()

        sel = self._get_snap(pid)
        if not sel:
            tk.Label(pods_row_frame, text="No archived siblings.", bg=self.PANEL, fg=self.MUTED).pack(anchor="w", padx=8, pady=8)
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
            tk.Label(_sibs_frame, text="No archived siblings.", bg=self.PANEL, fg=self.MUTED).pack(anchor="w", padx=8, pady=8)
            return

        # ===== Use persistent canvas/row (set up in __init__) =====
        pods_row = pods_row_frame

        # --- render pods left-to-right with pagination (max 7 per page) ---
        grand_counter = Counter()
        highlight_id = str(pid)

        PODS_PER_PAGE = 5
        ordered_keys = sorted(pods.keys(), key=lambda x: (-1 if x is None else x))
        total_pages = max(1, (len(ordered_keys) + PODS_PER_PAGE - 1) // PODS_PER_PAGE)
        # Clamp page
        if not hasattr(self, '_pods_page'): self._pods_page = 0
        self._pods_page = max(0, min(self._pods_page, total_pages - 1))
        page_keys = ordered_keys[self._pods_page * PODS_PER_PAGE : (self._pods_page + 1) * PODS_PER_PAGE]

        # Grand counter still covers ALL pods for the total ratio
        for pidx_all in ordered_keys:
            for cid, csnap in pods[pidx_all]:
                grand_counter[_norm(_lookup_trait(csnap, _sib_trait_key))] += 1

        # Pagination nav bar — shown when >1 page
        if is_combo:
            nav_frame.pack_forget()
        else:
            try: nav_frame.grid_remove()
            except Exception: pass
        if total_pages > 1:
            if is_combo:
                # Re-pack to keep order: nav → sibs → ratio
                self.combo_sibs_inner.pack_forget()
                self.combo_ratio_frame.pack_forget()
                nav_frame.pack(side="top", anchor="w", padx=(0, 0), pady=(0, 4))
                self.combo_sibs_inner.pack(side="top", fill="x")
                self.combo_ratio_frame.pack(side="top", fill="x", pady=(6, 0))
            else:
                # Pods tab: nav in grid row 0 col 0
                nav_frame.grid(row=0, column=0, sticky="w", pady=(0, 4))
            nav = nav_frame
            _tgt_s = target_sibs
            _tgt_r = target_ratio
            cur = self._pods_page
            def _go_page(p, _pid=pid, _ts=_tgt_s, _tr=_tgt_r):
                self._pods_page = p
                self._render_siblings(_pid, target_sibs=_ts, target_ratio=_tr)
            BTN_BG = "#2a5a7a"
            tk.Button(nav, text="◀", command=lambda: _go_page(cur - 1),
                      bg=BTN_BG, fg="#ffffff", relief="flat", bd=0,
                      font=("Segoe UI", 11), padx=8,
                      state="normal" if cur > 0 else "disabled"
                      ).pack(side="left", padx=(0, 6))
            tk.Label(nav, text=f"{cur + 1} / {total_pages}",
                     bg=self.PANEL, fg=self.FG, font=("Segoe UI", 10)).pack(side="left")
            tk.Button(nav, text="▶", command=lambda: _go_page(cur + 1),
                      bg=BTN_BG, fg="#ffffff", relief="flat", bd=0,
                      font=("Segoe UI", 11), padx=8,
                      state="normal" if cur < total_pages - 1 else "disabled"
                      ).pack(side="left", padx=(6, 0))

        for pidx in page_keys:
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

                row = tk.Frame(col, bg=col_bg)
                row.pack(anchor="w", pady=4)

                canvas_w = 28 if is_combo else 56
                canvas_h = 28 if is_combo else 56
                c = tk.Canvas(row, width=canvas_w, height=canvas_h, bg=col_bg, highlightthickness=0)
                c.pack()

                im = self._icon_for_snap(_sib_trait_key, csnap, sx=self.SCALE_SIB, sy=self.SCALE_SIB)
                img_id = None

                if im is not None:
                    if is_combo and hasattr(im, "subsample"):
                        try: im = im.subsample(2, 2)
                        except Exception: pass
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

        # --- inline ratio section below pods ---
        if grand_counter:
            ordered_total = sorted(grand_counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
            counts_total  = [cnt for _name, cnt in ordered_total]
            ratio_text    = f"Sibling ratio: {pretty_ratio(counts_total)}"
        else:
            ratio_text = "Sibling ratio: —"

        law_parts = []
        try:
            if isinstance(sel, dict):
                _l2r = sel.get("law2_ratio"); _l2t = sel.get("law2_trait")
                _l3r = sel.get("law3_ratio"); _l3t = sel.get("law3_traits")
            else:
                _l2r = getattr(sel,"law2_ratio",None); _l2t = getattr(sel,"law2_trait",None)
                _l3r = getattr(sel,"law3_ratio",None); _l3t = getattr(sel,"law3_traits",None)
            if _l2r: law_parts.append(f"Segregation: {_l2r}" + (f"  ({_l2t})" if _l2t else ""))
            if _l3r: law_parts.append(f"Assortment: {_l3r}"  + (f"  ({_l3t})" if _l3t else ""))
        except Exception:
            pass

        if is_combo:
            ordered_combo = sorted(grand_counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
            self._render_ratio_box(self.combo_ratio_frame, _sib_trait_key, ordered_combo,
                                   sum(grand_counter.values()), law_parts, compact=True,
                                   title="Sibling ratio")
        else:
            # Pods tab: show ratio in right panel
            try:
                for w in self.pods_tab_ratio_frame.winfo_children(): w.destroy()
                ordered_pods = sorted(grand_counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
                self._render_ratio_box(self.pods_tab_ratio_frame, _sib_trait_key, ordered_pods,
                                       sum(grand_counter.values()), law_parts, compact=True)
            except Exception:
                pass

        # --- auto-extend vertically to fit tallest pod ---
        try:
            pods_row.update_idletasks()
            max_h = 0
            pod_total_w = 0
            for card in pods_row.winfo_children():
                h = card.winfo_reqheight()
                w = card.winfo_reqwidth()
                if h > max_h: max_h = h
                pod_total_w += w + 20
            if max_h:
                pods_canvas.configure(height=max_h + 40)
            if is_combo:
                self._combo_pods_w = pod_total_w
                # Measure actual total height of combo right column content
                try:
                    pods_row.update_idletasks()
                    ratio_h = self.combo_ratio_frame.winfo_reqheight()
                    nav_h = self.combo_nav_frame.winfo_reqheight() if self.combo_nav_frame.winfo_ismapped() else 0
                    self._combo_pods_h = max_h + ratio_h + nav_h + 80
                except Exception:
                    self._combo_pods_h = max_h + 200
                # Refresh outer unified canvas scrollregion
                try:
                    self._update_combo_scrollregion()
                except Exception:
                    pass
            else:
                self._pods_content_w = pod_total_w
                self._pods_content_h = max_h + 160
        except Exception:
            pass
        # Reveal pods canvas now content is built — prevents flicker
        try:
            if not is_combo and getattr(self, "_pods_win", None):
                self.pods_scroll_canvas.itemconfig(self._pods_win, state="normal")
        except Exception:
            pass
        # Reveal combo right column now that all widgets are in place
        try:
            if is_combo:
                self._combo_right.pack(side="left", fill="both", padx=(6, 0))
        except Exception:
            pass
        self.after(80, self._auto_resize_window)

    def _greyscale_icon_from_path(self, path, sx=1, sy=1):
        """Load an icon from file path, convert to greyscale, return PhotoImage or None."""
        if not path or not _PIL_AVAILABLE:
            return None
        try:
            pil_img = Image.open(path).convert("RGBA")
            if sx != 1 or sy != 1:
                w, h = pil_img.size
                pil_img = pil_img.resize((w * sx, h * sy), Image.NEAREST)
            # Desaturate: convert to L then back to RGBA to preserve alpha
            r, g, b, a = pil_img.split()
            grey_rgb = ImageOps.grayscale(pil_img.convert("RGB"))
            grey_rgba = Image.merge("RGBA", (grey_rgb, grey_rgb, grey_rgb, a))
            return _PILImageTk.PhotoImage(grey_rgba)
        except Exception:
            return None

    def _render_left_ratio(self, panel, tkey, ordered, total, law_parts):
        """Compact ratio display for the left panel: inline box + icon counts."""
        for w in panel.winfo_children():
            w.destroy()
        if not ordered or total == 0:
            return
        counts = [c for _, c in ordered]
        if len(counts) == 2 and counts[1] > 0:
            ratio_str = f"{round(counts[0]/counts[1],2):.2f}".replace(".", ",") + ":1"
        elif len(counts) == 2:
            ratio_str = "all dominant"
        else:
            import math
            def _g(a, b): return a if b == 0 else _g(b, a % b)
            g = counts[0]
            for c in counts[1:]: g = _g(g, c)
            ratio_str = " : ".join(str(c // g) for c in counts)
        pct = "  /  ".join(f"{v*100/total:.1f}%" for v in counts)

        # Compact box
        box = tk.Frame(panel, bg="#12303f",
                       highlightthickness=1, highlightbackground="#2a5a7a")
        box.pack(fill="x", pady=(0, 4))
        top = tk.Frame(box, bg="#12303f")
        top.pack(fill="x", padx=6, pady=(4, 2))
        tk.Label(top, text="Total ratio", bg="#12303f", fg=self.MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Label(top, text=ratio_str, bg="#12303f", fg=self.FG,
                 font=("Segoe UI", 11, "bold")).pack(side="right")
        tk.Label(box, text=pct, bg="#12303f", fg=self.MUTED,
                 font=("Segoe UI", 8), anchor="center").pack(padx=6, pady=(0, 4))

        # Icon row
        icon_row = tk.Frame(panel, bg=self.PANEL)
        icon_row.pack(pady=(0, 2))
        self._img_refs = getattr(self, "_img_refs", [])
        for i, (val_name, count) in enumerate(ordered):
            if i > 0:
                tk.Label(icon_row, text=" : ", bg=self.PANEL, fg=self.FG,
                         font=("Segoe UI", 11, "bold")).pack(side="left")
            cell = tk.Frame(icon_row, bg=self.PANEL)
            cell.pack(side="left", padx=4)
            if tkey == "pod_shape":
                s = str(val_name).lower()
                s = "constricted" if "constrict" in s else ("inflated" if "inflate" in s else s)
                try: _p = pod_shape_icon_path(s, "green")
                except: _p = ""
                im = self._greyscale_icon_from_path(_p, sx=1, sy=1) if _p else None
                if im is None:
                    im = self._icon_for_snap(tkey, {"traits": {tkey: val_name}}, sx=1, sy=1)
            else:
                im = self._icon_for_snap(tkey, {"traits": {tkey: val_name}}, sx=1, sy=1)
            if im is not None:
                self._img_refs.append(im)
                c = tk.Canvas(cell, width=im.width(), height=im.height(),
                               bg=self.PANEL, highlightthickness=0)
                c.pack()
                c.create_image(0, 0, anchor="nw", image=im)
            else:
                tk.Label(cell, text=val_name, bg=self.PANEL, fg=self.MUTED,
                         font=("Segoe UI", 8)).pack()
            tk.Label(cell, text=str(count), bg=self.PANEL, fg=self.FG,
                     font=("Segoe UI", 10, "bold")).pack(pady=(2, 0))

    def _render_ratio_box(self, parent, tkey, ordered, total, law_parts, compact=False, title="Total ratio"):
        """Render the full ratio box + icon/count row into `parent` frame."""
        counts = [c for _, c in ordered]
        if total > 0 and counts:
            if len(counts) == 2 and counts[1] > 0:
                x = round(counts[0] / counts[1], 2)
                ratio_str = f"{x:.2f}".replace(".", ",") + ":1"
            elif len(counts) == 2:
                ratio_str = "all dominant"
            else:
                import math
                def _gcd2(a, b): return a if b == 0 else _gcd2(b, a % b)
                g2 = counts[0]
                for c in counts[1:]: g2 = _gcd2(g2, c)
                ratio_str = " : ".join(str(c // g2) for c in counts)
            pct_parts = [f"{v*100/total:.1f}%" for v in counts]
        else:
            ratio_str = "—"
            pct_parts = []

        top_pad   = (6, 2)  if compact else (16, 4)
        box_pad   = (10, 6) if compact else (30, 12)
        box_ipad  = 8       if compact else 24
        box_ipady = 6       if compact else 12
        ratio_fs  = 16      if compact else 24
        pct_fs    = 9       if compact else 10
        sep_fs    = 12      if compact else 16
        cnt_fs    = 10      if compact else 12
        icon_pad  = 4       if compact else 8
        icon_sc   = 1

        tk.Label(parent, text=title,
                 bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9 if compact else 11)).pack(pady=top_pad)

        box = tk.Frame(parent, bg="#12303f",
                       highlightthickness=2, highlightbackground="#2a5a7a")
        box.pack(padx=box_pad[0], pady=(0, box_pad[1]),
                 ipadx=box_ipad, ipady=box_ipady)

        tk.Label(box, text=ratio_str,
                 bg="#12303f", fg=self.FG,
                 font=("Segoe UI", ratio_fs, "bold"),
                 anchor="center").pack(pady=(2, 0))

        if pct_parts:
            tk.Label(box, text="  /  ".join(pct_parts),
                     bg="#12303f", fg=self.MUTED,
                     font=("Segoe UI", pct_fs),
                     anchor="center").pack(pady=(2, 4))

        # Icon + count row
        if ordered and total > 0:
            icon_row = tk.Frame(parent, bg=self.PANEL)
            icon_row.pack(pady=(0, 4))
            self._img_refs = getattr(self, "_img_refs", [])
            for i, (val_name, count) in enumerate(ordered):
                if i > 0:
                    tk.Label(icon_row, text=" : ",
                             bg=self.PANEL, fg=self.FG,
                             font=("Segoe UI", sep_fs, "bold")).pack(side="left")
                cell = tk.Frame(icon_row, bg=self.PANEL)
                cell.pack(side="left", padx=icon_pad)
                if tkey == "pod_shape":
                    dummy = {"traits": {"pod_shape": val_name, "pod_color": "green"}}
                else:
                    dummy = {"traits": {tkey: val_name}}
                try:
                    if tkey == "pod_shape":
                        # Greyscale pod shape: load from path with PIL
                        s = str(val_name).lower()
                        s = "constricted" if "constrict" in s else ("inflated" if "inflate" in s else s)
                        try:
                            _p = pod_shape_icon_path(s, "green")
                        except Exception:
                            _p = ""
                        im = self._greyscale_icon_from_path(_p, sx=icon_sc, sy=icon_sc) if _p else None
                        if im is None:
                            im = self._icon_for_snap(tkey, dummy, sx=icon_sc, sy=icon_sc)
                    else:
                        im = self._icon_for_snap(tkey, dummy, sx=icon_sc, sy=icon_sc)
                except Exception:
                    im = None
                if im is not None:
                    self._img_refs.append(im)
                    c = tk.Canvas(cell, width=im.width(), height=im.height(),
                                  bg=self.PANEL, highlightthickness=0)
                    c.pack()
                    c.create_image(0, 0, anchor="nw", image=im)
                else:
                    tk.Label(cell, text=val_name,
                             bg=self.PANEL, fg=self.MUTED,
                             font=("Segoe UI", 9)).pack()
                tk.Label(cell, text=str(count),
                         bg=self.PANEL, fg=self.FG,
                         font=("Segoe UI", cnt_fs, "bold")).pack(pady=(2, 0))

        for lp in law_parts:
            tk.Label(parent, text=lp,
                     bg=self.PANEL, fg=self.MUTED,
                     font=("Segoe UI", 10, "italic"),
                     anchor="center").pack(fill="x", pady=(4, 0))

    def _collect_segregation_contributors(self, pid, tkey):
        """Replicate the Law 2 family-signature filter for `tkey`.

        Returns (dom_pheno, rec_pheno, total_dom, total_rec, families) where
        families is a list of dicts sorted by n descending:
          { mid, fid, mid_gen, fid_gen, dom, rec, n }

        Returns (None, None, 0, 0, []) when tkey has no locus mapping or
        insufficient pedigree data is available.
        """
        from collections import defaultdict

        trait_to_locus = {
            "flower_color": "A", "pod_color": "Gp", "seed_color": "I",
            "seed_shape":   "R", "plant_height": "Le",
        }
        loc = trait_to_locus.get(tkey)
        if not loc:
            return None, None, 0, 0, []

        snap = self._get_snap(pid)
        if not snap:
            return None, None, 0, 0, []

        plants = (getattr(self.app, "archive", {}).get("plants", {})
                  if hasattr(self, "app") else {})

        # ---- local helpers (mirrors module-level test_mendelian_laws) ----
        def _geno(s):
            try:
                g = s.get("genotype") or {} if isinstance(s, dict) else getattr(s, "genotype", None) or {}
                return dict(g) if isinstance(g, dict) else {}
            except Exception:
                return {}

        def _parents(s):
            if isinstance(s, dict):
                return s.get("mother_id"), s.get("father_id")
            return getattr(s, "mother_id", None), getattr(s, "father_id", None)

        def _get_s(pid_):
            if pid_ in (None, "", -1): return None
            for k in [pid_, str(pid_)]:
                if k in plants: return plants[k]
            try:
                k = int(pid_)
                if k in plants: return plants[k]
            except Exception:
                pass
            return None

        def _fam_sig(parent_s, gp_m, gp_f):
            """Canonical signature: parent heterozygous, grandparents homozygous."""
            pg = _geno(parent_s)
            p_pair = pg.get(loc)
            if not (isinstance(p_pair, (list, tuple)) and len(p_pair) >= 2): return None
            if p_pair[0] == p_pair[1]: return None          # parent must be Aa
            gm_g = _geno(gp_m); gf_g = _geno(gp_f)
            m_pair = gm_g.get(loc); f_pair = gf_g.get(loc)
            if not (isinstance(m_pair, (list, tuple)) and len(m_pair) >= 2 and
                    isinstance(f_pair, (list, tuple)) and len(f_pair) >= 2):
                return None
            if m_pair[0] != m_pair[1] or f_pair[0] != f_pair[1]: return None  # gp must be AA/aa
            def _canon(pair): return "".join(sorted([str(pair[0]), str(pair[1])]))
            return tuple(sorted([_canon(m_pair), _canon(f_pair)]))

        # ---- derive reference parent + family signature from selected plant ----
        ref_mid, _ = _parents(snap)
        parent_s = _get_s(ref_mid)
        if not parent_s: return None, None, 0, 0, []
        gp_mid, gp_fid = _parents(parent_s)
        gp_m = _get_s(gp_mid); gp_f = _get_s(gp_fid)
        if not (gp_m and gp_f): return None, None, 0, 0, []

        fam_sig = _fam_sig(parent_s, gp_m, gp_f)
        if fam_sig is None: return None, None, 0, 0, []

        parent_traits = (parent_s.get("traits", {}) if isinstance(parent_s, dict)
                         else getattr(parent_s, "traits", {}) or {})
        dom_pheno = str(parent_traits.get(tkey, "")).strip().lower()

        # ---- scan every archive plant ----
        fam_data  = defaultdict(lambda: {"dom": 0, "rec": 0})
        all_phenos = set()
        total_dom = total_rec = 0

        for csnap in plants.values():
            if isinstance(csnap, dict) and not csnap.get("alive", True):
                continue
            smid, sfid = _parents(csnap if isinstance(csnap, dict) else {})
            if smid in (None, "", -1) or sfid in (None, "", -1): continue

            pm = _get_s(smid); pf = _get_s(sfid)
            if not pm or not pf: continue

            # both parents must be heterozygous at loc
            pgm = _geno(pm); pgf = _geno(pf)
            pair_m = pgm.get(loc); pair_f = pgf.get(loc)
            if not (isinstance(pair_m, (list, tuple)) and len(pair_m) >= 2 and
                    isinstance(pair_f, (list, tuple)) and len(pair_f) >= 2): continue
            if len(set(pair_m[:2])) != 2 or len(set(pair_f[:2])) != 2: continue

            # check family signature for both parents
            gpm_mid, gpm_fid = _parents(pm); gpf_mid, gpf_fid = _parents(pf)
            gp_mm = _get_s(gpm_mid); gp_mf = _get_s(gpm_fid)
            gp_fm = _get_s(gpf_mid); gp_ff = _get_s(gpf_fid)
            sig_m = _fam_sig(pm, gp_mm, gp_mf) if (gp_mm and gp_mf) else None
            sig_f = _fam_sig(pf, gp_fm, gp_ff) if (gp_fm and gp_ff) else None
            if sig_m != fam_sig or sig_f != fam_sig: continue

            # classify phenotype
            try:
                ct = (csnap.get("traits", {}) if isinstance(csnap, dict)
                      else getattr(csnap, "traits", {}) or {})
            except Exception:
                ct = {}
            ph = str(ct.get(tkey, "")).strip().lower()
            if not ph: continue
            all_phenos.add(ph)

            key = (smid, sfid)
            if ph == dom_pheno:
                fam_data[key]["dom"] += 1
                total_dom += 1
            else:
                fam_data[key]["rec"] += 1
                total_rec += 1

        rec_candidates = all_phenos - {dom_pheno}
        rec_pheno = next(iter(rec_candidates), "recessive") if rec_candidates else "recessive"

        # ---- build sorted families list ----
        families = []
        for (fm_id, ff_id), counts in fam_data.items():
            pm_s = _get_s(fm_id); pf_s = _get_s(ff_id)
            def _gen(s):
                if s is None: return "?"
                return (s.get("generation", "?") if isinstance(s, dict)
                        else getattr(s, "generation", "?"))
            families.append({
                "mid": fm_id, "fid": ff_id,
                "mid_gen": _gen(pm_s), "fid_gen": _gen(pf_s),
                "dom": counts["dom"], "rec": counts["rec"],
                "n": counts["dom"] + counts["rec"],
            })
        families.sort(key=lambda f: -f["n"])
        return dom_pheno, rec_pheno, total_dom, total_rec, families

    def _render_ratio_tab(self, pid):
        """Populate the Trait Ratio tab: direct siblings → contributing families (with totals) → pooled ratio."""
        frame = self.ratio_tab_frame
        for w in frame.winfo_children():
            w.destroy()
        if not pid:
            tk.Label(frame, text="Select a plant to see its ratio.",
                     bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 11)).pack(pady=40)
            return
        snap = self._get_snap(pid)
        if not snap:
            tk.Label(frame, text="No data.", bg=self.PANEL, fg=self.MUTED,
                     font=("Segoe UI", 11)).pack(pady=40)
            return
        def g(k, d=None): return snap.get(k, d) if isinstance(snap, dict) else getattr(snap, k, d)

        from collections import Counter
        try:
            mode = (self.trait_mode.get() or "Flowers").lower()
        except Exception:
            mode = "flowers"
        trait_map = {
            "flowers": "flower_color", "pod color": "pod_color",
            "pod shape": "pod_shape",  "seed color": "seed_color",
            "seed shape": "seed_shape","height": "plant_height",
        }
        tkey = trait_map.get(mode, "flower_color")
        mid, fid = g("mother_id"), g("father_id")
        plants = self.app.archive.get("plants", {}) if hasattr(self, "app") else {}

        # ── Scrollable wrapper ────────────────────────────────────────────
        scroll_canvas = tk.Canvas(frame, bg=self.PANEL, highlightthickness=0)
        vscroll = tk.Scrollbar(frame, orient="vertical", command=scroll_canvas.yview)
        vscroll.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scroll_canvas.configure(yscrollcommand=vscroll.set)
        inner = tk.Frame(scroll_canvas, bg=self.PANEL)
        inner_win = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>",
                           lambda e: scroll_canvas.itemconfig(inner_win, width=e.width))
        def _mwheel(e):
            scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        def _mwheel_lin_up(e):
            scroll_canvas.yview_scroll(-1, "units")
        def _mwheel_lin_dn(e):
            scroll_canvas.yview_scroll(1, "units")

        def _bind_scroll(widget):
            """Recursively bind mousewheel on widget and all descendants."""
            widget.bind("<MouseWheel>", _mwheel, add="+")
            widget.bind("<Button-4>",   _mwheel_lin_up, add="+")
            widget.bind("<Button-5>",   _mwheel_lin_dn, add="+")

        for _w in (scroll_canvas, inner):
            _bind_scroll(_w)
        # Re-bind after inner content is populated
        inner.bind("<Configure>",
                   lambda e: [scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")),
                               _bind_all_children(inner, _bind_scroll)],
                   add="+")

        def _bind_all_children(w, fn):
            fn(w)
            for child in w.winfo_children():
                _bind_all_children(child, fn)

        SEP_BG     = "#1e3a4a"
        HDR_FONT   = ("Segoe UI", 11, "bold")
        NOTE_FONT  = ("Segoe UI", 10)
        MONO_FONT  = ("Consolas", 10)
        GREEN_NOTE = "#6dbf67"

        def _sep():
            tk.Frame(inner, height=1, bg=SEP_BG).pack(fill="x", padx=12, pady=8)

        def _white_sep():
            tk.Frame(inner, height=1, bg="#c8d8e0").pack(fill="x", padx=12, pady=(6, 4))

        # Collect pooled data up front (needed by both families and pooled sections)
        dom_pheno, rec_pheno, sci_dom, sci_rec, families = \
            self._collect_segregation_contributors(pid, tkey)
        sci_total = sci_dom + sci_rec

        # ── Section 1: Direct siblings (same parents only) ────────────────
        sec1 = tk.Frame(inner, bg=self.PANEL)
        sec1.pack(fill="x", padx=12, pady=(12, 4))

        tk.Label(sec1, text="Ratio from direct siblings",
                 bg=self.PANEL, fg=self.FG, font=HDR_FONT).pack(anchor="w")
        tk.Label(sec1,
                 text=(f"Plants sharing exactly the same parents:  ♀ #{mid}  ×  ♂ #{fid}.  "
                       "May differ from the pooled ratio below."),
                 bg=self.PANEL, fg=self.MUTED, font=NOTE_FONT,
                 wraplength=460, justify="left").pack(anchor="w", pady=(2, 4))

        counter = Counter()
        for cid, csnap in (plants.items() if isinstance(plants, dict) else []):
            cm = (csnap.get("mother_id") if isinstance(csnap, dict)
                  else getattr(csnap, "mother_id", None))
            cf = (csnap.get("father_id") if isinstance(csnap, dict)
                  else getattr(csnap, "father_id", None))
            same = ((mid is not None and fid is not None and cm == mid and cf == fid) or
                    (mid is not None and fid is None  and cm == mid) or
                    (mid is None and fid is not None  and cf == fid))
            if same:
                def _g2(s, k):
                    t = s.get("traits", {}) if isinstance(s, dict) else getattr(s, "traits", {}) or {}
                    return t.get(k) or (s.get(k) if isinstance(s, dict) else getattr(s, k, None))
                val = str(_g2(csnap, tkey) or "unknown").lower()
                counter[val] += 1
        sib_total = sum(counter.values())
        sib_ordered = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
        self._render_ratio_box(sec1, tkey, sib_ordered, sib_total, [],
                               compact=True, title="Sibling ratio")

        _sep()

        # ── Section 2: Contributing families + totals row ─────────────────
        sec2 = tk.Frame(inner, bg=self.PANEL)
        sec2.pack(fill="x", padx=12, pady=(0, 4))

        tk.Label(sec2, text="Ratio from contributing families",
                 bg=self.PANEL, fg=self.FG, font=HDR_FONT).pack(anchor="w")
        tk.Label(sec2,
                 text="All qualifying Aa \u00d7 Aa parent pairs that share the same grandparent cross type, pooled across families.",
                 bg=self.PANEL, fg=self.MUTED, font=NOTE_FONT,
                 wraplength=460, justify="left").pack(anchor="w", pady=(2, 4))

        if not families:
            tk.Label(sec2,
                     text="No qualifying families found for this trait.",
                     bg=self.PANEL, fg=self.MUTED, font=NOTE_FONT).pack(anchor="w", pady=6)
        else:
            n_fam   = len(families)
            dom_lbl = (dom_pheno or "dominant").title()
            rec_lbl = (rec_pheno or "recessive").title()

            tk.Label(sec2,
                     text=(f"{sci_total} plants across {n_fam} parent pair"
                           f"{'s' if n_fam != 1 else ''} qualify for the pooled ratio:"),
                     bg=self.PANEL, fg=self.MUTED, font=NOTE_FONT).pack(anchor="w", pady=(2, 6))

            # ── table — use grid so every row shares the same column widths ──
            tbl = tk.Frame(sec2, bg=self.PANEL)
            tbl.pack(fill="x")

            # Column definitions: (header, anchor, min-width-px, stretch)
            # col 0-2: identifiers (left-aligned), col 3-6: numbers (right-aligned)
            COLS = [
                ("Mother",    "w", 70,  False),
                ("Father",    "w", 70,  False),
                ("Gen ♀/♂",  "w", 90,  False),
                (dom_lbl,     "e", 70,  False),
                (rec_lbl,     "e", 70,  False),
                ("N",         "e", 50,  False),
                ("Ratio",     "e", 90,  False),
            ]

            HDR_ROW_FONT  = ("Segoe UI",  10, "bold")
            DATA_ROW_FONT = ("Consolas",  11)
            TOT_ROW_FONT  = ("Segoe UI",  11, "bold")
            PAD_X = (6, 6)

            # configure column weights so the last column fills available space
            for ci, (_, _, minw, stretch) in enumerate(COLS):
                tbl.columnconfigure(ci, minsize=minw, weight=1 if stretch else 0)

            # header row
            hdr_bg = "#0a1e2a"
            for ci, (hdr_txt, anc, _, _) in enumerate(COLS):
                tk.Label(tbl, text=hdr_txt, bg=hdr_bg, fg=self.MUTED,
                         font=HDR_ROW_FONT, anchor=anc,
                         padx=6, pady=4
                         ).grid(row=0, column=ci, sticky="ew", padx=(0, 0))

            # data rows
            for ri, fam in enumerate(families):
                row_bg = self.CARD if ri % 2 == 0 else "#0d1f2e"
                if fam["rec"] > 0:
                    ratio_str = f"{fam['dom'] / fam['rec']:.2f}:1".replace(".", ",")
                elif fam["dom"] > 0:
                    ratio_str = "all dom."
                else:
                    ratio_str = "—"
                gen_str = f"{fam['mid_gen']} / {fam['fid_gen']}"
                row_vals = [
                    f"#{fam['mid']}",
                    f"#{fam['fid']}",
                    gen_str,
                    str(fam["dom"]),
                    str(fam["rec"]),
                    str(fam["n"]),
                    ratio_str,
                ]
                for ci, (val, (_, anc, _, _)) in enumerate(zip(row_vals, COLS)):
                    tk.Label(tbl, text=val, bg=row_bg, fg=self.FG,
                             font=DATA_ROW_FONT, anchor=anc,
                             padx=6, pady=3
                             ).grid(row=ri + 1, column=ci, sticky="ew")

            last_data_row = len(families) + 1

            # thin white separator spanning all columns
            sep = tk.Frame(tbl, height=1, bg="#c8d8e0")
            sep.grid(row=last_data_row, column=0, columnspan=len(COLS),
                     sticky="ew", pady=(2, 0))

            # totals row
            tot_ratio_str = "—"
            if sci_rec > 0:
                tot_ratio_str = f"{sci_dom / sci_rec:.2f}:1".replace(".", ",")
            elif sci_dom > 0:
                tot_ratio_str = "all dom."

            tot_bg  = "#0a2030"
            tot_vals = [
                "Total",
                "",
                f"{n_fam} fam.",
                str(sci_dom),
                str(sci_rec),
                str(sci_total),
                tot_ratio_str,
            ]
            for ci, (val, (_, anc, _, _)) in enumerate(zip(tot_vals, COLS)):
                tk.Label(tbl, text=val, bg=tot_bg, fg="#e8f0f5",
                         font=TOT_ROW_FONT, anchor=anc,
                         padx=6, pady=5
                         ).grid(row=last_data_row + 1, column=ci, sticky="ew")

        _sep()

        # ── Section 3: Pooled Ratio (the grand result, used by Law Wizard) ─
        sec3 = tk.Frame(inner, bg=self.PANEL)
        sec3.pack(fill="x", padx=12, pady=(0, 16))

        hdr3 = tk.Frame(sec3, bg=self.PANEL)
        hdr3.pack(fill="x")
        tk.Label(hdr3, text="Pooled Ratio",
                 bg=self.PANEL, fg=self.FG, font=HDR_FONT).pack(side="left")
        tk.Label(hdr3, text="  \u2713 counts toward unlocking Mendelian laws",
                 bg=self.PANEL, fg=GREEN_NOTE, font=NOTE_FONT).pack(side="left", padx=(4, 0))

        # N = x line with ? button
        n_row = tk.Frame(sec3, bg=self.PANEL)
        n_row.pack(anchor="w", pady=(4, 2))
        tk.Label(n_row, text=f"N = {sci_total}",
                 bg=self.PANEL, fg=self.MUTED, font=NOTE_FONT).pack(side="left")

        def _show_pool_help():
            win = tk.Toplevel(sec3)
            win.title("What counts toward the Pooled Ratio?")
            win.resizable(False, False)
            win.configure(bg=self.PANEL)
            try:
                win.transient(self.root)
                win.grab_set()
            except Exception:
                pass
            pad = tk.Frame(win, bg=self.PANEL, padx=18, pady=14)
            pad.pack(fill="both", expand=True)
            tk.Label(pad, text="Which plants count toward the Pooled Ratio?",
                     bg=self.PANEL, fg=self.FG,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
            criteria = [
                "1.  The plant's mother and father are both heterozygous (Aa) for this trait \u2014 "
                "meaning each parent shows the dominant form but carries the recessive allele.",
                "2.  Both parents trace back to the same grandparent-cross type: "
                "one fully dominant grandparent (AA) crossed with one fully recessive grandparent (aa).",
                "3.  The plant itself has a recorded phenotype for this trait.",
            ]
            for c in criteria:
                tk.Label(pad, text=c, bg=self.PANEL, fg=self.MUTED,
                         font=NOTE_FONT, wraplength=400, justify="left").pack(anchor="w", pady=(0, 6))
            tk.Label(pad,
                     text="Plants meeting all three criteria form the scientifically valid F2 generation "
                          "needed to detect Mendel\u2019s Law of Segregation and Law of Independent Assortment.",
                     bg=self.PANEL, fg=GREEN_NOTE,
                     font=NOTE_FONT, wraplength=400, justify="left").pack(anchor="w", pady=(4, 0))
            tk.Button(pad, text="Close", command=win.destroy,
                      font=NOTE_FONT).pack(anchor="e", pady=(10, 0))

        help_btn = tk.Button(n_row, text="?", command=_show_pool_help,
                             font=("Segoe UI", 9, "bold"),
                             bg="#1e3a4a", fg=self.MUTED,
                             activebackground="#2a4a5a", activeforeground=self.FG,
                             relief="flat", bd=0, padx=5, pady=0, cursor="hand2")
        help_btn.pack(side="left", padx=(8, 0))

        if sci_total > 0 and dom_pheno:
            sci_ordered = []
            if sci_dom > 0: sci_ordered.append((dom_pheno, sci_dom))
            if sci_rec > 0: sci_ordered.append((rec_pheno, sci_rec))
            sci_law_parts = []
            try:
                _l2r = g("law2_ratio"); _l2t = g("law2_trait")
                _l3r = g("law3_ratio"); _l3t = g("law3_traits")
                if _l2r: sci_law_parts.append(
                    f"Segregation: {_l2r}" + (f"  ({_l2t})" if _l2t else ""))
                if _l3r: sci_law_parts.append(
                    f"Assortment: {_l3r}"  + (f"  ({_l3t})" if _l3t else ""))
            except Exception:
                pass
            self._render_ratio_box(sec3, tkey, sci_ordered, sci_total,
                                   sci_law_parts, compact=True, title="Scientific ratio")
        else:
            msg = ("Not enough data for this trait in the verified pool yet." if tkey in
                   {"flower_color", "pod_color", "seed_color", "seed_shape", "plant_height"}
                   else "This trait has no single-locus mapping; a pooled ratio cannot be calculated.")
            tk.Label(sec3, text=msg,
                     bg=self.PANEL, fg=self.MUTED, font=NOTE_FONT,
                     wraplength=460, justify="left").pack(anchor="w", pady=6)

    def _switch_tab_frame(self, tab_idx):
        """Show only the content frame for tab_idx, hide all others."""
        frames = getattr(self, "_tab_frames", [])
        for i, f in enumerate(frames):
            try:
                if i == tab_idx:
                    f.pack(fill="both", expand=True)
                else:
                    f.pack_forget()
            except Exception:
                pass

    def _on_tab_changed(self):
        """Re-render active tab and recalculate window size when tab is switched."""
        pid = getattr(self, "current_pid", None)
        if pid is None:
            return
        try:
            tab_idx = self.tie_notebook.index(self.tie_notebook.select())
        except Exception:
            tab_idx = 0
        self._switch_tab_frame(tab_idx)
        # Hide the shared trait toolbar on the Punnett Square tab (it has its own selectors)
        try:
            if tab_idx == 3:
                self._shared_toolbar.pack_forget()
            else:
                # Re-pack AFTER the notebook so it stays between the tabs and content area
                self._shared_toolbar.pack(side="top", fill="x",
                                          padx=self.PAD, pady=(6, 4),
                                          after=self.tie_notebook)
        except Exception:
            pass
        # Leaving Lineage: save the highlighted node, remember it for Pods/Ratio
        if tab_idx != 0:
            prev = getattr(self, "preview_pid", None)
            if prev:
                self._pods_pid = str(prev)
                self._saved_preview_pid = str(prev)   # remember for return
            else:
                self._pods_pid = str(pid) if pid else None
                # keep _saved_preview_pid as-is (don't overwrite with None)
            self.preview_pid = None
        else:
            # Returning to Lineage: restore saved highlighted node
            self.preview_pid = getattr(self, "_saved_preview_pid", None)
            self._pods_pid = None
        pods_pid = getattr(self, "_pods_pid", None) or pid
        if tab_idx == 0:
            self._draw_canvas_family(pid)
        elif tab_idx == 1:
            self._render_siblings(pods_pid)
        elif tab_idx == 4:
            self._render_ratio_tab(pods_pid)
        elif tab_idx == 3:
            self._on_cross_settings_changed(_skip_render=True)  # show/hide Trait 2 correctly
            self._render_cross_tab(pods_pid)
        else:
            # Combo tab — render both sides, then do ONE resize after both settle
            self._combo_sizing_pending = True
            self._draw_canvas_family(pid, target_canvas=self.combo_canvas)
            self._render_siblings(pods_pid,
                                  target_sibs=self.combo_sibs_inner,
                                  target_ratio=self.combo_ratio_frame)
            self._combo_sizing_pending = False
            # Give Tkinter one full event-loop pass to finish geometry, then size.
            # A second pass at 300 ms catches pod widgets that haven't settled yet
            # on the first paint (which makes _combo_pods_w come back near-zero).
            self.after(80, self._auto_resize_window)
            self.after(300, self._auto_resize_window)

    def _update_combo_scrollregion(self):
        """Set combo main canvas scrollregion from actual inner content bbox."""
        try:
            self._combo_main_canvas.update_idletasks()
            bb = self._combo_main_canvas.bbox("all")
            if bb:
                # Ensure minimum right-panel visibility even for tiny trees
                tree_w = getattr(self, "_combo_tree_w", 0)
                min_w = max(bb[2], tree_w + 440)   # tree + right panel
                self._combo_main_canvas.configure(
                    scrollregion=(0, 0, min_w, bb[3]))
        except Exception:
            pass

    def _auto_resize_window(self):
        """Resize window to fit active tab content. Capped at 1024px tall."""
        if getattr(self, "_combo_sizing_pending", False):
            return   # let the explicit after(80) handle it
        try:
            self.update_idletasks()
            LEFT_W   = 230
            CHROME   = 36
            PAD      = 60
            TAB_BAR  = 36
            TOGGLES  = 34
            RATIO_H  = 36
            CHROME_V = 80
            MAX_H    = 1024

            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()

            try:
                tab_idx = self.tie_notebook.index(self.tie_notebook.select())
            except Exception:
                tab_idx = 0

            if tab_idx == 2:
                # Combo tab: tree + pods side by side
                tree_w = getattr(self, "_combo_tree_w", getattr(self, "_tree_content_w", 0))
                tree_h = getattr(self, "_combo_tree_h", getattr(self, "_tree_content_h", 0))
                pods_w = getattr(self, "_combo_pods_w", getattr(self, "_pods_content_w", 0))
                pods_h = getattr(self, "_combo_pods_h", getattr(self, "_pods_content_h", 0))
                notebook_w = max(700, tree_w + pods_w + PAD)
                notebook_h = max(600, max(tree_h, pods_h) + TAB_BAR + TOGGLES + CHROME_V)
            elif tab_idx == 0:
                # Lineage tab: size only to the tree content
                tree_w = getattr(self, "_tree_content_w", 0)
                tree_h = getattr(self, "_tree_content_h", 0) + TAB_BAR + TOGGLES + CHROME_V
                notebook_w = max(700, tree_w + PAD)
                notebook_h = max(600, tree_h)
            else:
                # Pods / Ratio / Punnett tabs: size to their own content
                pods_w = getattr(self, "_pods_content_w", 0)
                pods_h = getattr(self, "_pods_content_h", 0) + TAB_BAR + TOGGLES + RATIO_H + CHROME_V
                _prev_w = getattr(self, "_last_non_combo_w", 0) - LEFT_W - CHROME
                notebook_w = max(700, pods_w + PAD, _prev_w)
                notebook_h = max(600, pods_h)

            total_w = LEFT_W + notebook_w + CHROME
            total_w = max(900, min(total_w, screen_w - 20))
            total_h = max(600, min(notebook_h, MAX_H, screen_h - 60))

            cur_x = self.winfo_x()
            cur_y = self.winfo_y()
            self.geometry(f"{total_w}x{total_h}+{cur_x}+{cur_y}")
            self.update_idletasks()
            # Re-pin the outer left sash (plant list vs notebook)
            for w in self.winfo_children():
                if isinstance(w, ttk.Panedwindow):
                    w.sashpos(0, LEFT_W)
                    break
            # Combo tab: resize the right panel width and update combo_canvas height
            if tab_idx == 2:
                try:
                    _ctw = getattr(self, "_combo_tree_w", getattr(self, "_tree_content_w", 400))
                    _cth = getattr(self, "_combo_tree_h", getattr(self, "_tree_content_h", 400))
                    self.combo_canvas.configure(width=_ctw, height=_cth)
                    self.update_idletasks()
                    self._update_combo_scrollregion()
                except Exception:
                    pass
            if tab_idx != 2:
                self._last_non_combo_w = total_w
                self._last_non_combo_h = total_h
            self._layout_done = True
        except Exception:
            pass

    def _render_pid(self, pid):
        # clear any ancestor preview when switching selection
        self.preview_pid = None
        self._saved_preview_pid = None
        self._pods_pid = None
        self._img_refs = []
        self._pods_page = 0   # reset pagination on new plant
        self.current_pid = pid
        snap = self._get_snap(pid)
        if not snap:
            self._clear_render(); return
        def g(k, default=None): return snap.get(k, default) if isinstance(snap, dict) else getattr(snap, k, default)
        self.lbl_left_title.config(text=f"Plant {g('generation','F?')} #{g('id', pid)}")
        self.lbl_left_parents.config(text=f"Parents: ♀ #{g('mother_id','?')}  |  ♂ #{g('father_id','?')}")
        pass  # parents_right removed
        self._render_traits(snap)
        try:
            tab_idx = self.tie_notebook.index(self.tie_notebook.select())
        except Exception:
            tab_idx = 0
        if tab_idx == 4:
            self._render_ratio_tab(g('id', pid))
        elif tab_idx == 2:
            self._render_siblings(g('id', pid),
                                  target_sibs=self.combo_sibs_inner,
                                  target_ratio=self.combo_ratio_frame)
            self._draw_canvas_family(g('id', pid), target_canvas=self.combo_canvas)
        elif tab_idx == 3:
            self._render_cross_tab(g('id', pid))
        else:
            self._render_siblings(g('id', pid))
            self._draw_canvas_family(g('id', pid))
    # =========================================================================
    # Cross Diagrams tab — Punnett square renderer
    # =========================================================================

    # Trait meta: key → (dom_allele, rec_allele, dom_phenotype, rec_phenotype, display_name)
    _CROSS_TRAIT_META = {
        "flower_color":    ("A",  "a",  "purple",   "white",       "Flower Color"),
        "flower_position": ("Fa", "fa", "axial",    "terminal",    "Flower Position"),
        "pod_color":       ("G",  "g",  "green",    "yellow",      "Pod Color"),
        "pod_shape":       ("P",  "p",  "inflated", "constricted", "Pod Shape"),
        "seed_color":      ("I",  "i",  "yellow",   "green",       "Seed Color"),
        "seed_shape":      ("R",  "r",  "round",    "wrinkled",    "Seed Shape"),
        "plant_height":    ("L",  "l",  "tall",     "short",       "Plant Height"),
    }

    # 4 phenotype-class colours (dom/dom, dom/rec, rec/dom, rec/rec)
    _PUNNETT_COLORS = ["#17543a", "#1a3f6b", "#4a2468", "#6b1f2a"]
    # mono: dominant, recessive
    _PUNNETT_COLORS_MONO = ["#17543a", "#6b1f2a"]
    # dimmed versions when count == 0
    _PUNNETT_DIM = ["#0e2e20", "#0e2238", "#271342", "#381018"]
    _PUNNETT_DIM_MONO = ["#0e2e20", "#381018"]

    def _on_cross_settings_changed(self, _skip_render=False):
        pid = getattr(self, "current_pid", None)
        # Show/hide Trait 2 selector depending on mono/dihybrid
        try:
            if self._cross_mode.get() == "Dihybrid":
                self._cross_t2_lbl.pack(side="left", padx=(16, 0),
                                        before=self._cross_best_btn)
                self._cross_t2_menu.pack(side="left", padx=(4, 0),
                                         before=self._cross_best_btn)
            else:
                self._cross_t2_lbl.pack_forget()
                self._cross_t2_menu.pack_forget()
        except Exception:
            pass
        if _skip_render:
            return
        if pid is None:
            return
        try:
            tab_idx = self.tie_notebook.index(self.tie_notebook.select())
        except Exception:
            tab_idx = -1
        if tab_idx == 3:
            self._render_cross_tab(pid)


    def _cross_auto_detect(self):
        """Scan the full archive and select the trait(s) with the best fit
        to the expected Mendelian ratio, ranked purely by chi-square.

          Monohybrid → lowest χ² vs 3:1  (trait must be within the 2.1:1–3.9:1 band)
          Dihybrid   → lowest χ² vs 9:3:3:1 (all 4 classes must be present)

        Key design decisions
        --------------------
        - Families are POOLED by parent pair (all offspring of the same mother×father
          are merged), which is exactly how test_mendelian_laws detects law 3.
          This prevents per-family sample noise from hiding the best pair.
        - No hard chi-square ceiling for the scan: we rank by chi2 and pick the
          best available, so the button always shows something meaningful even when
          no family individually clears the formal detection threshold of 4.0.
        - The formal LAW2_DOM_FRAC band is still enforced for monohybrid so we
          don't accidentally show a 1:1 trait as "3:1".
        """
        app  = getattr(self, "app", None)
        mode = self._cross_mode.get()
        lbl_map = dict(zip(self._cross_trait_keys, self._cross_trait_labels))

        try:
            plants = dict((getattr(app, "archive", {}) or {}).get("plants", {}) or {})
        except Exception:
            plants = {}

        if not plants:
            try:
                app._toast("No plants in the archive yet.", level="info")
            except Exception:
                pass
            return

        # ── helpers ───────────────────────────────────────────────────────────

        def _tv(snap, key):
            try:
                t = snap.get("traits", {}) if isinstance(snap, dict)                     else getattr(snap, "traits", {}) or {}
                return str(t.get(key, "")).strip().lower()
            except Exception:
                return ""

        def _mid(snap):
            v = snap.get("mother_id") if isinstance(snap, dict)                 else getattr(snap, "mother_id", None)
            return str(v) if v not in (None, "", -1) else ""

        def _fid(snap):
            v = snap.get("father_id") if isinstance(snap, dict)                 else getattr(snap, "father_id", None)
            return str(v) if v not in (None, "", -1) else ""

        def _sid(snap):
            v = snap.get("id") if isinstance(snap, dict) else getattr(snap, "id", None)
            return str(v) if v is not None else ""

        # Pool all snaps by parent pair (same logic as test_mendelian_laws).
        # This merges all offspring of the same cross so chi-square is stable.
        from collections import defaultdict
        family_index = defaultdict(list)
        for snap in plants.values():
            m, f = _mid(snap), _fid(snap)
            if not m:
                continue
            family_index[(m, f if f else m)].append(snap)

        # ── full archive scan ─────────────────────────────────────────────────
        # best_law2: (chi2, N, index_pid, tk)
        # best_law3: (chi2, N, index_pid, tk1, tk2)
        # No hard chi2 ceiling — rank by best available, let the user see data.
        best_law2 = None
        best_law3 = None

        for (m, f), sibs in family_index.items():
            index_pid = _sid(sibs[0])

            # ── monohybrid: best 3:1 trait ────────────────────────────────────
            if len(sibs) >= LAW2_MIN_N:
                for tk in self._cross_trait_keys:
                    meta = self._CROSS_TRAIT_META.get(tk)
                    if not meta:
                        continue
                    _, _, dom_ph, rec_ph, _ = meta
                    dom = sum(1 for s in sibs if _tv(s, tk) == dom_ph)
                    rec = sum(1 for s in sibs if _tv(s, tk) == rec_ph)
                    total = dom + rec
                    if total < LAW2_MIN_N:
                        continue
                    dom_frac = dom / float(total)
                    # Still enforce the acceptance band so we don't show a 1:1 trait
                    if not (LAW2_DOM_FRAC_MIN <= dom_frac <= LAW2_DOM_FRAC_MAX):
                        continue
                    exp_dom = 0.75 * total
                    exp_rec = 0.25 * total
                    chi2 = ((dom - exp_dom)**2 / exp_dom
                            + (rec - exp_rec)**2 / exp_rec)
                    if (best_law2 is None
                            or chi2 < best_law2[0]
                            or (chi2 == best_law2[0] and total > best_law2[1])):
                        best_law2 = (chi2, total, index_pid, tk)

            # ── dihybrid: best 9:3:3:1 pair ──────────────────────────────────
            # Minimum N is halved vs formal detection so per-family noise doesn't
            # hide pairs that are clearly present in pooled data.
            min_n3 = max(20, LAW3_MIN_N // 2)
            if len(sibs) >= min_n3:
                for i, tk1 in enumerate(self._cross_trait_keys):
                    meta1 = self._CROSS_TRAIT_META.get(tk1)
                    if not meta1:
                        continue
                    _, _, dom1, rec1, _ = meta1
                    for tk2 in self._cross_trait_keys[i + 1:]:
                        meta2 = self._CROSS_TRAIT_META.get(tk2)
                        if not meta2:
                            continue
                        _, _, dom2, rec2, _ = meta2
                        counts = {("D","D"): 0, ("D","r"): 0,
                                  ("r","D"): 0, ("r","r"): 0}
                        for s in sibs:
                            v1, v2 = _tv(s, tk1), _tv(s, tk2)
                            if not v1 or not v2:
                                continue
                            counts[("D" if v1 != rec1 else "r",
                                    "D" if v2 != rec2 else "r")] += 1
                        total = sum(counts.values())
                        if total < min_n3:
                            continue
                        # All 4 classes must be present
                        if any(v == 0 for v in counts.values()):
                            continue
                        exp_r = {("D","D"): 9, ("D","r"): 3,
                                 ("r","D"): 3, ("r","r"): 1}
                        chi2 = sum((counts[k] - exp_r[k] * total / 16.0) ** 2
                                   / (exp_r[k] * total / 16.0)
                                   for k in counts)
                        # No ceiling — just pick lowest chi2 across all pairs
                        if (best_law3 is None
                                or chi2 < best_law3[0]
                                or (chi2 == best_law3[0] and total > best_law3[1])):
                            best_law3 = (chi2, total, index_pid, tk1, tk2)

        # ── apply results ─────────────────────────────────────────────────────

        found_pid = None

        if mode == "Dihybrid":
            if best_law3:
                _, _, found_pid, tk1, tk2 = best_law3
                self._cross_t1.set(lbl_map[tk1])
                self._cross_t2.set(lbl_map[tk2])
            elif best_law2:
                _, _, found_pid, tk = best_law2
                self._cross_mode.set("Monohybrid")
                self._cross_t1.set(lbl_map[tk])
                try:
                    app._toast(
                        "No 9:3:3:1 data yet — switched to Monohybrid "
                        "with best 3:1 trait.", level="info")
                except Exception:
                    pass
            else:
                try:
                    app._toast(
                        "No fitting ratio found yet. "
                        "Grow more F2 offspring and try again.", level="info")
                except Exception:
                    pass
                return

        else:  # Monohybrid
            if best_law2:
                _, _, found_pid, tk = best_law2
                self._cross_t1.set(lbl_map[tk])
            elif best_law3:
                _, _, found_pid, tk1, tk2 = best_law3
                self._cross_mode.set("Dihybrid")
                self._cross_t1.set(lbl_map[tk1])
                self._cross_t2.set(lbl_map[tk2])
                try:
                    app._toast(
                        "No 3:1 data yet — switched to Dihybrid "
                        "with best 9:3:3:1 pair.", level="info")
                except Exception:
                    pass
            else:
                try:
                    app._toast(
                        "No fitting ratio found yet. "
                        "Grow more F2 offspring and try again.", level="info")
                except Exception:
                    pass
                return

        # ── select winning plant in listbox and redraw canvas ─────────────────
        if found_pid is not None:
            try:
                ids = [str(x) for x in self._ids]
                if str(found_pid) in ids:
                    idx = ids.index(str(found_pid))
                    self.listbox.selection_clear(0, "end")
                    self.listbox.selection_set(idx)
                    self.listbox.see(idx)
                    self.current_pid = str(found_pid)
            except Exception:
                pass

        self._on_cross_settings_changed(_skip_render=True)
        self._render_cross_tab(getattr(self, "current_pid", None))


    def _render_cross_tab(self, pid):
        """Draw the Punnett square on self.cross_canvas for plant `pid`."""
        c = self.cross_canvas
        c.delete("all")
        self._cross_img_refs = []

        snap = self._get_snap(pid)
        if not snap:
            self._cross_msg(c, "No plant selected.")
            return

        def _g(k, d=None):
            return snap.get(k, d) if isinstance(snap, dict) else getattr(snap, k, d)

        mid, fid = _g("mother_id"), _g("father_id")

        lbl_to_key = dict(zip(self._cross_trait_labels, self._cross_trait_keys))
        tk1 = lbl_to_key.get(self._cross_t1.get(), "seed_color")
        tk2 = lbl_to_key.get(self._cross_t2.get(), "seed_shape")
        is_dihybrid = self._cross_mode.get() == "Dihybrid"

        if tk1 not in self._CROSS_TRAIT_META:
            self._cross_msg(c, f"Trait '{tk1}' not supported for cross diagrams.")
            return
        if is_dihybrid and tk1 == tk2:
            self._cross_msg(c, "Please select two different traits for the dihybrid cross.")
            return

        # Collect siblings (children sharing same two parents)
        plants = {}
        try:
            plants = self.app.archive.get("plants", {}) if hasattr(self, "app") else {}
        except Exception:
            pass

        def _tv(snap_obj, key):
            try:
                t = snap_obj.get("traits", {}) if isinstance(snap_obj, dict) else getattr(snap_obj, "traits", {}) or {}
                return str(t.get(key, "")).strip().lower()
            except Exception:
                return ""

        siblings = []
        if mid not in (None, "", -1) and fid not in (None, "", -1):
            for _cid, cs in (plants.items() if isinstance(plants, dict) else []):
                cm = cs.get("mother_id") if isinstance(cs, dict) else getattr(cs, "mother_id", None)
                cf = cs.get("father_id") if isinstance(cs, dict) else getattr(cs, "father_id", None)
                if str(cm) == str(mid) and str(cf) == str(fid):
                    siblings.append(cs)
        elif mid not in (None, "", -1):
            # selfed — mother == father
            for _cid, cs in (plants.items() if isinstance(plants, dict) else []):
                cm = cs.get("mother_id") if isinstance(cs, dict) else getattr(cs, "mother_id", None)
                cf = cs.get("father_id") if isinstance(cs, dict) else getattr(cs, "father_id", None)
                if str(cm) == str(mid) and str(cf) == str(mid):
                    siblings.append(cs)

        if not siblings and mid in (None, "", -1):
            self._cross_msg(c,
                "This plant has no recorded parents.\n\n"
                "Select a plant with known parents to see the cross diagram.\n\n"
                "↺  Try another plant")
            return

        meta1 = self._CROSS_TRAIT_META[tk1]
        d1, r1, dom1, rec1, name1 = meta1

        if is_dihybrid:
            meta2 = self._CROSS_TRAIT_META[tk2]
            d2, r2, dom2, rec2, name2 = meta2
            self._draw_dihybrid(c, siblings, _tv,
                                tk1, d1, r1, dom1, rec1, name1,
                                tk2, d2, r2, dom2, rec2, name2)
        else:
            self._draw_monohybrid(c, siblings, _tv,
                                  tk1, d1, r1, dom1, rec1, name1)

    # ── Monohybrid 2×2 ───────────────────────────────────────────────────────

    def _draw_monohybrid(self, c, siblings, _tv,
                         tk1, d1, r1, dom1, rec1, name1):
        CELL  = 110
        ML    = 90   # left margin (row headers)
        MT    = 115  # top margin (col headers) — increased to give title/subtitle room
        PAD   = 20
        FONT  = ("Segoe UI", 11, "bold")
        FONT_S= ("Segoe UI", 10)
        FONT_G= ("Segoe UI", 14, "bold")   # genotype inside cell
        FG    = self.FG
        MUTED = self.MUTED

        gametes = [d1, r1]  # both parents assumed Dd (heterozygous)

        # Count siblings by phenotype
        n_dom = sum(1 for s in siblings if _tv(s, tk1) != rec1 and _tv(s, tk1))
        n_rec = sum(1 for s in siblings if _tv(s, tk1) == rec1)
        total = n_dom + n_rec

        W = ML + 2 * CELL + PAD + 60   # extra width so badge + ratio text fits
        H = MT + 2 * CELL + PAD + 140

        c.configure(scrollregion=(0, 0, W, H))

        # Title
        c.create_text(W // 2, 12, text=f"Monohybrid Cross — {name1}",
                      fill=FG, font=("Segoe UI", 14, "bold"), anchor="n")
        c.create_text(W // 2, 38, text=f"Parent × Parent  ({d1}{r1} × {d1}{r1})",
                      fill=MUTED, font=FONT_S, anchor="n")

        # Column headers
        for ci, gam in enumerate(gametes):
            cx = ML + ci * CELL + CELL // 2
            c.create_rectangle(ML + ci * CELL, MT - 38, ML + (ci + 1) * CELL, MT,
                                fill="#12303f", outline="#2a5060")
            c.create_text(cx, MT - 19, text=gam, fill=FG, font=FONT_G)

        # Row headers
        for ri, gam in enumerate(gametes):
            ry = MT + ri * CELL + CELL // 2
            c.create_rectangle(ML - 44, MT + ri * CELL, ML, MT + (ri + 1) * CELL,
                                fill="#12303f", outline="#2a5060")
            c.create_text(ML - 22, ry, text=gam, fill=FG, font=FONT_G)

        # Diagonal corner header
        c.create_rectangle(ML - 44, MT - 38, ML, MT, fill="#0a1e2a", outline="#2a5060")
        c.create_text(ML - 22, MT - 19, text="×", fill=MUTED, font=FONT)

        # Cells
        for ri, rg in enumerate(gametes):
            for ci, cg in enumerate(gametes):
                x0 = ML + ci * CELL
                y0 = MT + ri * CELL
                x1, y1 = x0 + CELL, y0 + CELL

                geno = "".join(sorted([rg, cg], key=lambda x: (x.islower(), x.lower())))  # capital allele first
                is_dom = (d1 in [rg, cg])
                pheno = dom1 if is_dom else rec1
                cls_idx = 0 if is_dom else 1

                observed = n_dom if is_dom else n_rec
                has_data = observed > 0
                bg = self._PUNNETT_COLORS_MONO[cls_idx] if has_data else self._PUNNETT_DIM_MONO[cls_idx]

                c.create_rectangle(x0, y0, x1, y1, fill=bg, outline="#2a5060", width=2)

                # Genotype
                c.create_text(x0 + CELL // 2, y0 + 18, text=geno,
                               fill=FG if has_data else MUTED, font=FONT)

                # Trait icon
                try:
                    fake = {"traits": {tk1: pheno}}
                    im = self._icon_for_snap(tk1, fake, sx=1.2, sy=1.2)
                    if im:
                        c.create_image(x0 + CELL // 2, y0 + CELL // 2 + 8, image=im)
                        self._cross_img_refs.append(im)
                except Exception:
                    pass

                # Phenotype label
                c.create_text(x0 + CELL // 2, y1 - 18, text=pheno.capitalize(),
                               fill=FG if has_data else MUTED, font=FONT_S)

        # Count badges on phenotype classes
        for cls_idx, (pheno_label, observed) in enumerate(
                [(dom1, n_dom), (rec1, n_rec)]):
            bx = ML + 2 * CELL + 12
            by = MT + cls_idx * CELL + CELL // 2
            badge_col = self._PUNNETT_COLORS_MONO[cls_idx]
            c.create_oval(bx, by - 14, bx + 28, by + 14, fill=badge_col, outline="")
            c.create_text(bx + 14, by, text=str(observed),
                          fill=FG, font=("Segoe UI", 10, "bold"))

        # Legend / ratio summary — left-aligned and wrapped so text is never clipped
        ly = MT + 2 * CELL + 30
        ratio_str = self._cross_ratio_str([n_dom, n_rec], ["Dominant", "Recessive"])
        c.create_text(ML - 44, ly, text=ratio_str, fill=MUTED,
                      font=("Segoe UI", 11), anchor="nw",
                      width=W - (ML - 44) - 8)
        if total == 0:
            c.create_text(ML - 44, ly + 36,
                          text="No sibling data yet — showing expected structure.\n"
                               "Try another plant or grow more seeds.",
                          fill="#c08040", font=("Segoe UI", 10), anchor="nw",
                          width=W - (ML - 44) - 8)

    # ── Dihybrid 4×4 ─────────────────────────────────────────────────────────

    def _draw_dihybrid(self, c, siblings, _tv,
                       tk1, d1, r1, dom1, rec1, name1,
                       tk2, d2, r2, dom2, rec2, name2):
        CELL  = 95
        ML    = 108  # left margin
        MT    = 120  # top margin — increased to give title/subtitle clear room
        PAD   = 20
        FONT  = ("Segoe UI", 10, "bold")
        FONT_S= ("Segoe UI", 10)
        FONT_G= ("Segoe UI", 12, "bold")
        FG    = self.FG
        MUTED = self.MUTED

        # Gametes for a dihybrid parent (d1d2, d1r2, r1d2, r1r2)
        gametes = [(d1, d2), (d1, r2), (r1, d2), (r1, r2)]
        gam_labels = [f"{a}{b}" for a, b in gametes]

        # Count siblings per phenotype class: (is_dom1, is_dom2)
        counts = {(True, True): 0, (True, False): 0, (False, True): 0, (False, False): 0}
        total = 0
        for s in siblings:
            v1 = _tv(s, tk1); v2 = _tv(s, tk2)
            if v1 and v2:
                counts[(v1 != rec1, v2 != rec2)] += 1
                total += 1

        pheno_class_names = [
            f"{dom1.capitalize()} + {dom2.capitalize()}",
            f"{dom1.capitalize()} + {rec2.capitalize()}",
            f"{rec1.capitalize()} + {dom2.capitalize()}",
            f"{rec1.capitalize()} + {rec2.capitalize()}",
        ]
        pheno_class_keys = [(True,True),(True,False),(False,True),(False,False)]
        expected_ratio = [9, 3, 3, 1]

        LEGEND_X = ML + 4 * CELL + 18
        LEGEND_W = 180   # extra width reserved for the legend column
        W = LEGEND_X + LEGEND_W + PAD
        H = MT + 4 * CELL + PAD + 140

        c.configure(scrollregion=(0, 0, W, H))

        # Title — centred over the grid portion only
        grid_cx = ML + 2 * CELL
        c.create_text(grid_cx, 12, anchor="n",
                      text=f"Dihybrid Cross — {name1}  ×  {name2}",
                      fill=FG, font=("Segoe UI", 14, "bold"))
        parent_gam = f"{d1}{d2}{r1}{r2}"  # e.g. "RrIi"
        c.create_text(grid_cx, 38, anchor="n",
                      text=f"Parent × Parent  ({parent_gam[:2]}{parent_gam[2:]} × {parent_gam[:2]}{parent_gam[2:]})",
                      fill=MUTED, font=FONT_S)

        # Column headers
        for ci, gl in enumerate(gam_labels):
            cx = ML + ci * CELL + CELL // 2
            c.create_rectangle(ML + ci * CELL, MT - 46, ML + (ci+1)*CELL, MT,
                                fill="#12303f", outline="#2a5060")
            c.create_text(cx, MT - 23, text=gl, fill=FG, font=FONT_G)

        # Row headers
        for ri, gl in enumerate(gam_labels):
            ry = MT + ri * CELL + CELL // 2
            c.create_rectangle(ML - 52, MT + ri * CELL, ML, MT + (ri+1)*CELL,
                                fill="#12303f", outline="#2a5060")
            c.create_text(ML - 26, ry, text=gl, fill=FG, font=FONT_G)

        # Corner
        c.create_rectangle(ML - 52, MT - 46, ML, MT, fill="#0a1e2a", outline="#2a5060")
        c.create_text(ML - 26, MT - 23, text="×", fill=MUTED, font=FONT)

        # Cells
        for ri, (ra1, ra2) in enumerate(gametes):
            for ci, (ca1, ca2) in enumerate(gametes):
                x0 = ML + ci * CELL
                y0 = MT + ri * CELL
                x1, y1 = x0 + CELL, y0 + CELL

                # Genotype strings per trait
                t1_alleles = sorted([ra1, ca1], key=lambda x: (x.islower(), x.lower()))
                t2_alleles = sorted([ra2, ca2], key=lambda x: (x.islower(), x.lower()))
                geno1 = "".join(t1_alleles)
                geno2 = "".join(t2_alleles)

                is_dom_t1 = d1 in [ra1, ca1]
                is_dom_t2 = d2 in [ra2, ca2]
                cls_key   = (is_dom_t1, is_dom_t2)
                cls_idx   = pheno_class_keys.index(cls_key)
                observed  = counts[cls_key]
                has_data  = observed > 0

                bg = self._PUNNETT_COLORS[cls_idx] if has_data else self._PUNNETT_DIM[cls_idx]
                c.create_rectangle(x0, y0, x1, y1, fill=bg, outline="#2a5060", width=1)

                mid_x = x0 + CELL // 2
                pheno1 = dom1 if is_dom_t1 else rec1
                pheno2 = dom2 if is_dom_t2 else rec2

                # Top label: trait 1 phenotype + alleles  e.g. "purple – Aa"
                label1 = f"{pheno1.capitalize()} \u2013 {geno1}"
                c.create_text(mid_x, y0 + 10, text=label1,
                               fill=FG if has_data else MUTED,
                               font=("Segoe UI", 7, "bold"), anchor="center")

                # Icons for both traits — shifted up slightly
                icon_y = y0 + CELL // 2 - 4
                try:
                    fake1 = {"traits": {tk1: pheno1,
                                        "pod_color": "green",
                                        "flower_color": "purple"}}
                    im1 = self._icon_for_snap(tk1, fake1, sx=0.75, sy=0.75)
                    if im1:
                        c.create_image(mid_x - 16, icon_y, image=im1)
                        self._cross_img_refs.append(im1)
                except Exception:
                    pass
                try:
                    fake2 = {"traits": {tk2: pheno2,
                                        "pod_color": "green",
                                        "flower_color": "purple"}}
                    im2 = self._icon_for_snap(tk2, fake2, sx=0.75, sy=0.75)
                    if im2:
                        c.create_image(mid_x + 16, icon_y, image=im2)
                        self._cross_img_refs.append(im2)
                except Exception:
                    pass

                # Below icons: trait 2 phenotype + alleles  e.g. "round – Rr"
                label2 = f"{pheno2.capitalize()} \u2013 {geno2}"
                c.create_text(mid_x, y1 - 20, text=label2,
                               fill=FG if has_data else MUTED,
                               font=("Segoe UI", 7, "bold"), anchor="center")

                # Bottom: n = observed count
                n_text = f"n = {observed}" if has_data else "n = 0"
                c.create_text(mid_x, y1 - 8, text=n_text,
                               fill=FG if has_data else "#7a9aaa",
                               font=("Segoe UI", 7), anchor="center")

        # ── Legend aligned beside the grid ────────────────────────────────────
        # Each of the 4 phenotype classes corresponds to a band of rows in the grid.
        # Class 0 (TT): rows 0 only → gametes (d1d2 × *) → first 1 row of grid row-headers
        # but for a dihybrid Punnett the row structure is simply 4 rows total.
        # We center each legend entry on the vertical midpoint of the row-band it belongs to:
        #   class 0 (DD): rows 0       → y_center = MT + 0.5*CELL
        #   class 1 (Dr): rows 1       → y_center = MT + 1.5*CELL
        #   class 2 (rD): rows 2       → y_center = MT + 2.5*CELL
        #   class 3 (rr): rows 3       → y_center = MT + 3.5*CELL
        # The row of the grid that produces each class depends on the row gamete, not a fixed map,
        # so we instead spread legend entries evenly across the full grid height, one per CELL.
        lx = LEGEND_X
        for i, (cls_key, cls_name, exp) in enumerate(
                zip(pheno_class_keys, pheno_class_names, expected_ratio)):
            observed = counts[cls_key]
            has_data = observed > 0
            col = self._PUNNETT_COLORS[i] if has_data else self._PUNNETT_DIM[i]
            # Center each legend item at the vertical midpoint of its corresponding row
            ly_center = MT + i * CELL + CELL // 2
            exp_pct = int(round(exp / 16 * 100))
            # colour swatch
            c.create_rectangle(lx, ly_center - 8, lx + 14, ly_center + 6,
                                fill=col, outline="")
            # phenotype name — slightly larger font
            c.create_text(lx + 20, ly_center - 6, anchor="w", text=cls_name,
                          fill=FG if has_data else MUTED, font=("Segoe UI", 10, "bold"))
            # observed + expected on second line
            c.create_text(lx + 20, ly_center + 9, anchor="w",
                          text=f"Observed: {observed}  (exp. ~{exp_pct}%)",
                          fill=MUTED, font=("Segoe UI", 9))

        # Ratio summary below grid — left-aligned from grid left edge, with wrap
        cy_summary = MT + 4 * CELL + 28
        GRID_W = 4 * CELL   # grid content width for text wrapping
        counts_list = [counts[k] for k in pheno_class_keys]
        ratio_str = self._cross_ratio_str(counts_list, pheno_class_names)
        c.create_text(ML - 52, cy_summary, anchor="nw",
                      text=ratio_str, fill=MUTED, font=("Segoe UI", 11),
                      width=ML + GRID_W + 52)
        if total == 0:
            c.create_text(ML - 52, cy_summary + 36, anchor="nw",
                          text="No sibling data yet — showing expected structure. "
                               "Try another plant or grow more seeds.",
                          fill="#c08040", font=("Segoe UI", 10),
                          width=ML + GRID_W + 52)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _cross_msg(self, c, text):
        """Show a centred message on the cross canvas."""
        try:
            c.update_idletasks()
            w = max(c.winfo_width(), 500)
            h = max(c.winfo_height(), 300)
        except Exception:
            w, h = 500, 300
        c.configure(scrollregion=(0, 0, w, h))
        c.create_text(w // 2, h // 2, text=text, fill=self.MUTED,
                      font=("Segoe UI", 13), justify="center", anchor="center")

    def _cross_ratio_str(self, counts, labels):
        """Format observed counts as a ratio string."""
        total = sum(counts)
        if total == 0:
            return "Observed ratio: — (no data)"
        parts = [f"{c}" for c in counts]
        ratio = " : ".join(parts)
        pct = "  |  " + "  /  ".join(
            f"{labels[i]}: {counts[i]/total*100:.0f}%"
            for i in range(len(counts)) if counts[i] > 0)
        return f"Observed ratio: {ratio}{pct}  (N={total})"
