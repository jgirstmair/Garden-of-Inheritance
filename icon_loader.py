"""
Icon Loader Module

Handles loading and caching of plant stage icons, trait icons, and various
visual elements for the Pea Garden simulation.

Features:
- Icon path resolution with flexible fallback patterns
- Image caching to improve performance
- Support for scaled/subsampled images
- Fractional scaling support for precise sizing
"""

import base64
import os
from PIL import Image, ImageTk
from tkinter import PhotoImage


# Directory constants
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR = os.path.join(ROOT_DIR, "icons")

# Image cache
_image_cache = {}


# ============================================================================
# Stage Icon Resolution
# ============================================================================

def stage_icon_path(stage: int) -> str:
    """
    Get the icon path for a given growth stage.
    
    Args:
        stage: Plant growth stage (0-7)
        
    Returns:
        Path to icon file, or empty string if not found
    """
    stage_map = {
        0: "empty.png",
        1: "seed.png",
        2: "seedling.png",
        3: "leafy.png",
        4: "budding.png",
        5: "flowering.png",
        6: "mature.png",
        7: "mature.png",  # Could use seeds.png if available
    }
    
    # Try multiple candidate paths
    candidates = [
        os.path.join(ICONS_DIR, f"stage_{stage}.png"),
        os.path.join(ICONS_DIR, stage_map.get(stage, "plant.png")),
        os.path.join(ICONS_DIR, "plant.png"),
    ]
    
    for path in candidates:
        if os.path.exists(path):
            return path
    
    return ""


def stage_icon_path_for_plant(plant) -> str:
    """
    Get stage-specific icon for a plant, considering its traits and state.
    
    Handles special cases:
    - Dead plants → dead.png
    - Empty plots → empty.png
    - Seed color variations (yellow/green)
    - Stage 3 early/late leafy variants
    - Stage 4 budding with flower position/color
    - Stage 5+ flowering with position, color, and pod variations
    
    Prefers *_64x64.png variants for grid display when available.
    
    Args:
        plant: Plant instance or None
        
    Returns:
        Path to appropriate icon file
    """
    # Dead plants - check alive=False, not is_dead attribute
    if plant is not None and not getattr(plant, "alive", True):
        path = os.path.join(ICONS_DIR, "dead.png")
        path_hires = path.replace(".png", "_64x64.png")
        result = path_hires if os.path.exists(path_hires) else path
        return result

    # Empty plot
    if plant is None:
        path = stage_icon_path(0)
        path_hires = path.replace(".png", "_64x64.png")
        return path_hires if os.path.exists(path_hires) else path

    stage = getattr(plant, "stage", 0)

    # NOTE:
    # Stage 6–7 icon logic is handled later and depends ONLY on pods_remaining.
    # Do NOT add emasculation-based overrides here.

    # Stage 3: Split into early/late leafy without creating new stage
    if stage == 3:
        try:
            base_thresholds = [0, 0, 4, 8, 13, 18, 25, 30]
            health = int(getattr(plant, "health", 100))
            health_factor = 0 if health > 70 else (1 if health > 40 else 2)
            
            start_age = base_thresholds[3]
            end_age = base_thresholds[4] + health_factor
            if end_age <= start_age:
                end_age = start_age + 2
                
            age_in_stage = max(0, int(getattr(plant, "days_since_planting", 0)) - start_age)
            half_span = max(1, (end_age - start_age) // 2)
            use_late = age_in_stage >= half_span
            
            if use_late:
                for path in [
                    os.path.join(ICONS_DIR, "leafy_late_64x64.png"),
                    os.path.join(ICONS_DIR, "leafy_late.png")
                ]:
                    if os.path.exists(path):
                        return path
        except Exception:
            pass

    # Early-stage seed icon (stages 0-1)
    if stage <= 1:
        try:
            # Try genotype-based coloring first (I/i locus)
            genotype = getattr(plant, "genotype", None) or {}
            alleles = (genotype.get("I") or genotype.get("i") or 
                      genotype.get("seed") or genotype.get("seed_color") or
                      genotype.get("Seed"))
            
            if alleles:
                allele_str = "".join(alleles) if isinstance(alleles, (list, tuple)) else str(alleles or "")
                seed_color = "yellow" if ("I" in allele_str or "Y" in allele_str.upper()) else "green"
                
                for path in [
                    os.path.join(ICONS_DIR, f"seed_{seed_color}_64x64.png"),
                    os.path.join(ICONS_DIR, f"seed_{seed_color}.png")
                ]:
                    if os.path.exists(path):
                        return path
            
            # Fallback to trait-based
            traits = getattr(plant, "traits", {}) or {}
            if traits.get("seed_color") in ("yellow", "green"):
                seed_color = traits["seed_color"]
                for path in [
                    os.path.join(ICONS_DIR, f"seed_{seed_color}_64x64.png"),
                    os.path.join(ICONS_DIR, f"seed_{seed_color}.png")
                ]:
                    if os.path.exists(path):
                        return path
        except Exception:
            pass

    # Helper to get trait (revealed or true)
    def get_trait(trait_name):
        try:
            revealed = getattr(plant, "revealed_traits", None)
            if revealed and trait_name in revealed:
                return revealed.get(trait_name)
            return getattr(plant, "traits", {}).get(trait_name)
        except Exception:
            return None

    flower_position = get_trait("flower_position")
    flower_color = get_trait("flower_color")

    # Stage 4: Budding with flower traits
    if stage == 4:
        try:
            traits = getattr(plant, "traits", {}) or {}
            pos = traits.get("flower_position")
            col = traits.get("flower_color")
            
            if pos and col:
                path = budding_icon_path_hi(pos, col)
                if path:
                    return path
        except Exception:
            pass

    # Stage 5: Flowering
    if stage == 5 and flower_position and flower_color:
        try:
            path = flower_icon_path_hi(flower_position, flower_color)
            if path:
                return path
        except Exception:
            pass

    # Stage 6–7: Pod development depends ONLY on pods_remaining
    if 6 <= stage <= 7:
        pods_remaining = int(getattr(plant, "pods_remaining", 0) or 0)

        if pods_remaining > 0:
            # Show pod icons
            if flower_position and flower_color:
                pod_color = get_trait("pod_color")
                if pod_color:
                    filename_base = f"{flower_position}_{flower_color}-flowers_{pod_color}-pods"
                    for path in [
                        os.path.join(ICONS_DIR, f"{filename_base}_64x64.png"),
                        os.path.join(ICONS_DIR, f"{filename_base}.png"),
                    ]:
                        if os.path.exists(path):
                            return path
        else:
            # No pods → stay flowering
            if flower_position and flower_color:
                path = flower_icon_path_hi(flower_position, flower_color)
                if path:
                    return path

    # Default stage icon
    path = stage_icon_path(stage)
    path_hires = path.replace(".png", "_64x64.png")
    return path_hires if os.path.exists(path_hires) else path


# ============================================================================
# Trait Icon Resolution
# ============================================================================

def trait_icon_path(trait: str, value: str) -> str:
    """
    Get icon path for a specific trait/value combination.
    
    Args:
        trait: Trait name (e.g., "plant_height", "flower_color")
        value: Trait value (e.g., "tall", "purple")
        
    Returns:
        Path to icon file, or empty string if not found
    """
    # Normalize trait name
    trait_normalized = (trait or "").lower().replace(" ", "_")
    if trait_normalized == "stem_length":
        trait_normalized = "plant_height"
    
    # Normalize value
    value_normalized = (value or "").lower().replace(" ", "_")
    
    # Normalize height synonyms
    if trait_normalized == "plant_height":
        if value_normalized in ("dwarf", "short"):
            value_normalized = "short"
        elif value_normalized == "tall":
            value_normalized = "tall"
    
    path = os.path.join(ICONS_DIR, f"{trait_normalized}_{value_normalized}.png")
    return path if os.path.exists(path) else ""


def pod_icon_path(shape: str) -> str:
    """
    Resolve icon path for pod shape.
    
    Args:
        shape: Pod shape (e.g., "inflated", "constricted")
        
    Returns:
        Path to icon file, or empty string if not found
    """
    shape_normalized = (shape or "").strip().lower().replace(" ", "_")
    if not shape_normalized:
        return ""
    
    candidates = [
        os.path.join(ICONS_DIR, f"pod_shape_{shape_normalized}.png"),
        os.path.join(ICONS_DIR, f"pod_{shape_normalized}.png"),
        os.path.join(ICONS_DIR, f"pods_{shape_normalized}.png"),
        os.path.join(ICONS_DIR, "pod_shape", f"{shape_normalized}.png"),
        os.path.join(ICONS_DIR, "pod", f"{shape_normalized}.png"),
        os.path.join(ICONS_DIR, "pods", f"{shape_normalized}.png"),
        os.path.join(ICONS_DIR, "traits", f"pod_shape_{shape_normalized}.png"),
        os.path.join(ICONS_DIR, "traits", "pod", f"{shape_normalized}.png"),
    ]
    
    for path in candidates:
        try:
            if os.path.exists(path):
                return path
        except Exception:
            pass
    
    # Try using generic trait icon resolver
    try:
        path = trait_icon_path("pod_shape", shape_normalized)
        if path:
            return path
    except Exception:
        pass
    
    return ""


def flower_icon_path(position: str, color: str) -> str:
    """
    Resolve combined flower (position + color) icon without pods.
    
    Tries multiple flexible patterns:
    - flower_{position}_{color}.png
    - {position}_{color}.png
    - {position}-{color}.png
    
    Args:
        position: Flower position ("axial" or "terminal")
        color: Flower color ("purple" or "white")
        
    Returns:
        Path to icon file, or empty string if not found
    """
    pos = (position or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")

    basenames = [
        f"flower_{pos}_{col}",
        f"{pos}_{col}",
        f"{pos}-{col}",
    ]
    extensions = [".png", ".PNG"]

    for basename in basenames:
        for ext in extensions:
            path = os.path.join(ICONS_DIR, basename + ext)
            if os.path.exists(path):
                return path
    
    return ""


def flower_icon_path_hi(position: str, color: str) -> str:
    """
    Get high-res (64x64) flower icon for grid display.
    
    Args:
        position: Flower position ("axial" or "terminal")
        color: Flower color ("purple" or "white")
        
    Returns:
        Path to 64x64 icon file, or empty string if not found
    """
    pos = (position or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")
    path = os.path.join(ICONS_DIR, f"flower_{pos}_{col}_64x64.png")
    return path if os.path.exists(path) else ""


def budding_icon_path_hi(position: str, color: str) -> str:
    """
    Get high-res (64x64) budding stage icon.
    
    Args:
        position: Flower position ("axial" or "terminal")
        color: Flower color ("purple" or "white")
        
    Returns:
        Path to 64x64 budding icon, or empty string if not found
    """
    pos = (position or "").strip().lower().replace(" ", "_")
    col = (color or "").strip().lower().replace(" ", "_")
    path = os.path.join(ICONS_DIR, f"budding_{pos}_{col}_64x64.png")
    return path if os.path.exists(path) else ""


def pod_shape_icon_path(shape: str, color: str) -> str:
    """
    Resolve color-matched icon for pod shape (for left panel display).
    
    Preferred filename: pod_{color}_{shape}_64.png
    
    Args:
        shape: Pod shape (e.g., "inflated", "constricted")
        color: Pod color (e.g., "green", "yellow")
        
    Returns:
        Path to icon file, or empty string if not found
    """
    shape_normalized = (shape or "").strip().lower().replace(" ", "_")
    color_normalized = (color or "").strip().lower().replace(" ", "_")
    
    candidates = [
        os.path.join(ICONS_DIR, f"pod_{color_normalized}_{shape_normalized}_64.png"),
        os.path.join(ICONS_DIR, f"pod_{color_normalized}_{shape_normalized}.png"),
    ]
    
    for path in candidates:
        try:
            if os.path.exists(path):
                return path
        except Exception:
            pass
    
    return ""


# ============================================================================
# Image Loading & Caching
# ============================================================================

def placeholder_image():
    """
    Create a minimal 1x1 placeholder image.
    
    Returns:
        PhotoImage placeholder
    """
    try:
        return PhotoImage(width=1, height=1)
    except Exception:
        # Fallback: base64-encoded 1x1 GIF
        gif_1x1 = base64.b64decode(b'R0lGODdhAQABAIABAAAAAP///ywAAAAAAQABAAACAkQBADs=')
        return PhotoImage(data=gif_1x1)


def safe_image(file_path: str):
    """
    Load an image safely with caching.
    
    Args:
        file_path: Path to image file
        
    Returns:
        PhotoImage instance (or placeholder if loading fails)
    """
    cache_key = ("file", file_path)
    
    if cache_key in _image_cache:
        return _image_cache[cache_key]
    
    try:
        if file_path and os.path.exists(file_path):
            img = PhotoImage(file=file_path)
        else:
            img = placeholder_image()
        
        _image_cache[cache_key] = img
        return img
    except Exception:
        img = placeholder_image()
        _image_cache[cache_key] = img
        return img


def safe_image_scaled(file_path: str, sx=2, sy=2):
    """
    Load and scale an image with caching.
    
    Supports both integer subsampling (1/n shrink) and fractional scaling.
    
    Integer mode (sx/sy are ints):
        Subsample by factor (divide dimensions by sx/sy)
        
    Fractional mode (sx/sy are floats):
        Scale by exact factor using zoom + subsample approximation
        
    Args:
        file_path: Path to image file
        sx: X-axis scale factor (int for subsample, float for scale)
        sy: Y-axis scale factor (int for subsample, float for scale)
        
    Returns:
        Scaled PhotoImage instance (or placeholder if loading fails)
    """
    cache_key = ("file_sub", file_path, sx, sy)
    
    if cache_key in _image_cache:
        return _image_cache[cache_key]
    
    try:
        # Load base image
        if file_path and os.path.exists(file_path):
            base = PhotoImage(file=file_path)
        else:
            base = placeholder_image()

        # Fractional scaling path
        if isinstance(sx, float) or isinstance(sy, float):
            fx = max(0.01, float(sx))
            fy = max(0.01, float(sy))
            
            # Use zoom + subsample for approximation
            precision = 100  # Higher = more precise, slightly slower
            
            zoom_x = max(1, int(fx * precision))
            zoom_y = max(1, int(fy * precision))
            
            img = base.zoom(zoom_x, zoom_y)
            img = img.subsample(precision, precision)
        else:
            # Integer subsample (traditional 1/n shrink)
            img = base.subsample(max(1, int(sx)), max(1, int(sy)))

        _image_cache[cache_key] = img
        return img
        
    except Exception:
        # Fallback with same scaling logic
        try:
            if isinstance(sx, float) or isinstance(sy, float):
                fx = max(0.01, float(sx))
                fy = max(0.01, float(sy))
                precision = 100
                zoom_x = max(1, int(fx * precision))
                zoom_y = max(1, int(fy * precision))
                img = placeholder_image().zoom(zoom_x, zoom_y).subsample(precision, precision)
            else:
                img = placeholder_image().subsample(max(1, int(sx)), max(1, int(sy)))
        except Exception:
            img = placeholder_image()
        
        _image_cache[cache_key] = img
        return img
