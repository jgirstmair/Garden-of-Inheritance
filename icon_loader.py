import base64
import os

from PIL import Image, ImageTk
from tkinter import PhotoImage

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(ROOT_DIR, "icons")


def stage_icon_path(stage: int) -> str:
    # Prefer explicit stage icons, then semantic fallbacks
    stage_map = {
        0: "empty.png",
        1: "seed.png",
        2: "seedling.png",
        3: "leafy.png",
        4: "budding.png",
        5: "flowering.png",
        6: "mature.png",   # green pods
        7: "mature.png",   # seeds; change to seeds.png if you have one
    }
    candidates = [
        os.path.join(ICONS_DIR, f"stage_{stage}.png"),
        os.path.join(ICONS_DIR, stage_map.get(stage, "plant.png")),
        os.path.join(ICONS_DIR, "plant.png"),
    ]
    for pth in candidates:
        if os.path.exists(pth):
            return pth
    return ""
    return f"{flower_position}_{flower_color}-flowers_{pod_color}-pods.png"
def trait_icon_path(trait: str, value: str) -> str:
    """Return an icon path for a given trait/value if it exists; else empty string."""
    t = (trait or "").lower().replace(" ", "_")
    # normalize trait name
    if t == "stem_length":
        t = "plant_height"
    v = (value or "").lower().replace(" ", "_")
    # normalize value synonyms for height
    if t == "plant_height":
        if v in ("dwarf", "short"):
            v = "short"
        elif v == "tall":
            v = "tall"
    candidates = [
        os.path.join(ICONS_DIR, f"{t}_{v}.png"),
    ]
    for pth in candidates:
        if os.path.exists(pth):
            return pth
    return ""
def pod_icon_path(shape: str) -> str:
    s = (shape or "").strip().lower().replace(" ", "_")
    if not s:
        return ""
    candidates = [
        os.path.join(ICONS_DIR, f"pod_shape_{s}.png"),
        os.path.join(ICONS_DIR, f"pod_{s}.png"),
        os.path.join(ICONS_DIR, f"pods_{s}.png"),
        os.path.join(ICONS_DIR, "pod_shape", f"{s}.png"),
        os.path.join(ICONS_DIR, "pod", f"{s}.png"),
        os.path.join(ICONS_DIR, "pods", f"{s}.png"),
        os.path.join(ICONS_DIR, "traits", f"pod_shape_{s}.png"),
        os.path.join(ICONS_DIR, "traits", "pod", f"{s}.png"),
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                return p
        except Exception:
            pass
    try:
        p = trait_icon_path("pod_shape", s)
        if p:
            return p
    except Exception:
        pass
    return ""
def flower_icon_path(position: str, color: str) -> str:
    """
    Resolve a combined flower (position + color) icon without pods.
    Tries multiple flexible patterns and locations:
      icons/flower_{position}_{color}.png / .PNG
      icons/{position}_{color}.png / .PNG
      icons/{position}-{color}.png / .PNG
      icons/flowers/{position}_{color}.png
      icons/traits/flower_{position}_{color}.png
    position ∈ {"axial","terminal"}, color ∈ {"purple","white"}.
    """
    pos = (position or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")

    # candidate basenames
    bases = [
        f"flower_{pos}_{col}",
        f"{pos}_{col}",
        f"{pos}-{col}",
    ]
    exts = [".png", ".PNG"]

    candidates = []
    for b in bases:
        for ext in exts:
            candidates.append(os.path.join(ICONS_DIR, b + ext))
    # extra folders
    for pth in candidates:
        if os.path.exists(pth):
            return pth
    return ""
def flower_icon_path_hi(position: str, color: str) -> str:
    """
    Simplified: prefer only icons/flower_{position}_{color}_64x64.png
    """
    pos = (position or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")
    pth = os.path.join(ICONS_DIR, f"flower_{pos}_{col}_64x64.png")
    return pth if os.path.exists(pth) else ""

def budding_icon_path_hi(position: str, color: str) -> str:
    """
    Stage 4 (budding): use only icons/budding_{position}_{color}_64x64.png
    """
    pos = (position or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")
    pth = os.path.join(ICONS_DIR, f"budding_{pos}_{col}_64x64.png")
    return pth if os.path.exists(pth) else ""

def pod_shape_icon_path(shape: str, color: str) -> str:
    """Resolve a color‑matched icon for pod shape in the left panel.
    Preferred filenames (first wins):
      icons/pod_{color}_{shape}_64.png
    Returns "" (empty) if nothing exists.
    """
    sh = (shape or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")
    candidates = [
        os.path.join(ICONS_DIR, f"pod_{col}_{sh}_64.png"),   # primary
        os.path.join(ICONS_DIR, f"pod_{col}_{sh}.png"),      # fallback (no _64)
    ]
    for pth in candidates:
        try:
            if os.path.exists(pth):
                return pth
        except Exception:
            pass
    return ""

def stage_icon_path_for_plant(plant) -> str:
    """Stage-specific icon with trait-based composites.
    - Stage 5: flower position + color
    - Stage ≥6: flower position + color + pod color
    Prefers *_64x64.png variants for grid when available.
    """
    # 🔴 NEW: dead plants → dead.png
    if plant is not None and getattr(plant, "is_dead", False):
        p = os.path.join(ICONS_DIR, "dead.png")
        p32 = p.replace(".png", "_64x64.png")
        return p32 if os.path.exists(p32) else p

    if plant is None:
        p = stage_icon_path(0)
        p32 = p.replace(".png", "_64x64.png")
        return p32 if os.path.exists(p32) else p

    st = getattr(plant, "stage", 0)
    # ... rest of your existing logic (leafy_late, seed color, composites, etc.) ...

    # Stage 3 → split leafy icon into early/late without creating a new stage
    if st == 3:
        try:
            # Estimate half of Stage 3 using nominal thresholds and health factor
            base_thresholds = [0, 0, 4, 8, 13, 18, 25, 30]
            h = int(getattr(plant, "health", 100))
            health_factor = 0 if h > 70 else (1 if h > 40 else 2)
            start_age = base_thresholds[3]
            end_age = base_thresholds[4] + health_factor
            if end_age <= start_age:
                end_age = start_age + 2
            age_in_stage = max(0, int(getattr(plant, "days_since_planting", 0)) - start_age)
            half_span = max(1, (end_age - start_age) // 2)
            use_late = age_in_stage >= half_span
            if use_late:
                p = os.path.join(ICONS_DIR, "leafy_late_64x64.png")
                if os.path.exists(p): return p
                p = os.path.join(ICONS_DIR, "leafy_late.png")
                if os.path.exists(p): return p
            # else: default 'leafy' picked by stage_icon_path
        except Exception:
            pass


    # EARLY-STAGE SEED ICON (no trait reveal): prefer genotype; fallback to true trait
    try:
        if st <= 1:
            # 1) Genotype-based: use seed-color locus (I/i); 'I' → yellow, 'i' → green
            g = getattr(plant, "genotype", None) or {}
            alleles = g.get("I") or g.get("i") or g.get("seed") or g.get("seed_color") or g.get("Seed")
            if alleles:
                s = "".join(alleles) if isinstance(alleles, (list, tuple)) else str(alleles or "")
                seed_col = "yellow" if ("I" in s or "Y" in s.upper()) else "green"
                p = os.path.join(ICONS_DIR, f"seed_{seed_col}.png")
                p32 = p.replace(".png", "_64x64.png")
                if os.path.exists(p32): return p32
                if os.path.exists(p):  return p
            # 2) Trait-based fallback (uses true traits, not UI-revealed state)
            t = getattr(plant, "traits", {}) or {}
            if t.get("seed_color") in ("yellow", "green"):
                seed_col = t["seed_color"]
                p = os.path.join(ICONS_DIR, f"seed_{seed_col}.png")
                p32 = p.replace(".png", "_64x64.png")
                if os.path.exists(p32): return p32
                if os.path.exists(p):  return p
    except Exception:
        pass


    def _get(tr):
        try:
            if getattr(plant, "revealed_traits", None) and tr in plant.revealed_traits:
                return plant.revealed_traits.get(tr)
            return getattr(plant, "traits", {}).get(tr)
        except Exception:
            return None

    pos = _get("flower_position")
    col = _get("flower_color")
    
    # Stage 4 → budding_{position}_{color}_64x64.png (grid) — USE TRUE TRAITS
    if st == 4:
        try:
            traits = getattr(plant, "traits", {}) or {}
            pos_t = traits.get("flower_position")
            col_t = traits.get("flower_color")
            if pos_t and col_t:
                bp = budding_icon_path_hi(pos_t, col_t)
                if bp:
                    return bp
        except Exception:
            pass
    # Stage 5 → flower_{position}_{color}_64x64.png (grid, simplified)
    if st == 5:
        try:
            def _get(tr):
                try:
                    if getattr(plant, "revealed_traits", None) and tr in plant.revealed_traits:
                        return plant.revealed_traits.get(tr)
                    return getattr(plant, "traits", {}).get(tr)
                except Exception:
                    return None
            pos5 = _get("flower_position")
            col5 = _get("flower_color")
            if pos5 and col5:
                fp = flower_icon_path_hi(pos5, col5)
                if fp:
                    return fp
        except Exception:
            pass


    if st >= 6 and pos and col:
        pod = _get("pod_color")
        if pod:
            filename = f"{pos}_{col}-flowers_{pod}-pods.png"
            path = os.path.join(ICONS_DIR, filename)
            if os.path.exists(path):
                p32 = path.replace(".png", "_64x64.png")
                return p32 if os.path.exists(p32) else path

    p = stage_icon_path(st)
    p32 = p.replace(".png", "_64x64.png")
    return p32 if os.path.exists(p32) else p


_image_cache = {}

def placeholder_image():
    try:
        return PhotoImage(width=1, height=1)
    except Exception:
        gif_1x1 = base64.b64decode(b'R0lGODdhAQABAIABAAAAAP///ywAAAAAAQABAAACAkQBADs=')
        return PhotoImage(data=gif_1x1)
    
def safe_image(file_path: str):
    key = ("file", file_path)
    if key in _image_cache:
        return _image_cache[key]
    try:
        if file_path and os.path.exists(file_path):
            img = PhotoImage(file=file_path)
        else:
            img = placeholder_image()
        _image_cache[key] = img
        return img
    except Exception:
        _image_cache[key] = placeholder_image()
        return _image_cache[key]

def safe_image_scaled(file_path: str, sx=2, sy=2):
    """
    If sx/sy are ints  -> behave like before: subsample (1/n shrink).
    If sx/sy are floats -> treat them as scale factors and approximate via zoom+subsample.
    """
    key = ("file_sub", file_path, sx, sy)
    if key in _image_cache:
        return _image_cache[key]
    try:
        if file_path and os.path.exists(file_path):
            base = PhotoImage(file=file_path)
        else:
            base = placeholder_image()

        # --- NEW: fractional scaling path ---
        if isinstance(sx, float) or isinstance(sy, float):
            fx = float(sx)
            fy = float(sy)
            # avoid zero/negative
            if fx <= 0: fx = 1.0
            if fy <= 0: fy = 1.0

            # choose precision for approximation
            denom = 100  # higher = more precise, slightly slower

            zx = max(1, int(fx * denom))
            zy = max(1, int(fy * denom))

            img = base.zoom(zx, zy)
            img = img.subsample(denom, denom)
        else:
            # OLD BEHAVIOUR: integer subsample (1/n)
            img = base.subsample(max(1, int(sx)), max(1, int(sy)))

        _image_cache[key] = img
        return img
    except Exception:
        try:
            if isinstance(sx, float) or isinstance(sy, float):
                fx = float(sx)
                fy = float(sy)
                if fx <= 0: fx = 1.0
                if fy <= 0: fy = 1.0
                denom = 100
                zx = max(1, int(fx * denom))
                zy = max(1, int(fy * denom))
                img = placeholder_image().zoom(zx, zy).subsample(denom, denom)
            else:
                img = placeholder_image().subsample(max(1, int(sx)), max(1, int(sy)))
        except Exception:
            img = placeholder_image()
        _image_cache[key] = img
        return img
