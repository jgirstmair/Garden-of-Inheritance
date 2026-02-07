"""
Plant Module

Defines the Plant class representing individual pea plants in the garden.
Handles growth stages, trait revelation, watering, health, and reproduction.
"""

from dataclasses import dataclass, field, InitVar
import random
from typing import Optional
import tkinter as tk


# Growth stage names for display
STAGE_NAMES = {
    0: "Empty",
    1: "Seed",
    2: "Seedling",
    3: "Young plant",
    4: "Budding",
    5: "Flowering",
    6: "Pod development",
    7: "Mature seeds",
}

# Traits and the stage at which they become observable
TRAITS = {
    "plant_height": 3,
    "flower_position": 5,
    "flower_color": 5,
    "pod_shape": 7,
    "pod_color": 6,
    "seed_shape": 7,
    "seed_color": 7,
}

# Difficulty-based lifecycle settings
LIFECYCLE_SETTINGS = {
    "off": {  # Casual - Fast growth, short lifespan
        "base_thresholds": [0, 0, 4, 8, 13, 18, 25, 30],
        "max_age_range": (60, 90),
        "description": "Casual: Fast growth for genetics experimentation"
    },
    "overlay": {  # Moderate - Medium growth, medium lifespan
        "base_thresholds": [0, 0, 5, 10, 20, 30, 42, 55],
        "max_age_range": (75, 105),
        "description": "Moderate: Balanced growth speed"
    },
    "enforce": {  # Realistic - Slow growth, long lifespan (Mendel-era timing)
        "base_thresholds": [0, 0, 7, 14, 28, 42, 60, 85],
        "max_age_range": (90, 120),
        "description": "Realistic: Historical pea plant lifecycle"
    }
}

def get_lifecycle_settings(difficulty="off"):
    """
    Get lifecycle settings for the given difficulty.
    
    Args:
        difficulty: One of "off" (casual), "overlay" (moderate), "enforce" (realistic)
        
    Returns:
        Dict with base_thresholds and max_age_range
    """
    return LIFECYCLE_SETTINGS.get(difficulty, LIFECYCLE_SETTINGS["off"])


@dataclass
class Plant:
    """
    Represents a single pea plant in the garden.
    
    Tracks growth, health, water levels, trait revelation, and reproduction state.
    """
    
    # Core identity
    id: int
    env: InitVar['GardenEnvironment']  # type: ignore
    generation: str = "F0"
    
    # Growth state
    stage: int = 0
    alive: bool = True
    days_since_planting: int = 0
    
    # Resource levels
    health: int = 100
    water: int = 50
    
    # Genetics and traits
    traits: dict = field(default_factory=dict)
    revealed_traits: dict = field(default_factory=dict)
    reveal_order: list = field(default_factory=list)
    observed_today: set = field(default_factory=set)
    
    # Growth timing
    entered_stage5_age: Optional[int] = None
    max_age_days: int = 0  # Will be set in __post_init__ based on difficulty
    senescent: bool = False
    germination_delay: int = 0
    difficulty: str = "off"  # Track difficulty for this plant
    
    # Reproduction state
    pending_cross: Optional[dict] = None
    pollinated: bool = False
    emasculated: bool = False
    emasc_day: Optional[int] = None
    emasc_phase: Optional[str] = None
    selfing_frac_before_emasc: float = 0.0
    
    # Reproductive capacity (realistic pod/ovule counts)
    pods_total: int = 0
    pods_remaining: int = 0
    ovules_per_pod: int = 0
    ovules_left: int = 0
    aborted_ovules: int = 0
    
    # Lineage tracking
    ancestry: list = field(default_factory=list)
    paternal_ancestry: list = field(default_factory=list)
    
    # Pollen collection state
    last_anther_check_day: Optional[int] = None
    anthers_available_today: bool = False
    anthers_collected_day: Optional[int] = None
    
    # Class-level icon cache (lazy-loaded)
    _ICONS = None

    def __post_init__(self, env):
        """Initialize plant after dataclass creation."""
        # Register with environment
        env.register_plant(self)
        
        # Get difficulty from environment (with fallback)
        try:
            # Try to get difficulty from the app via the garden environment
            if hasattr(env, '_app'):
                app = env._app
                self.difficulty = str(getattr(app, '_season_mode', 'off'))
            else:
                self.difficulty = "off"
        except Exception:
            self.difficulty = "off"
        
        # Set max_age based on difficulty
        if self.max_age_days == 0:  # Only set if not already set
            settings = get_lifecycle_settings(self.difficulty)
            min_age, max_age = settings["max_age_range"]
            self.max_age_days = random.randint(min_age, max_age)
        
        # Set up F0 lineage
        try:
            gen = str(getattr(self, "generation", "F0") or "F0")
            if gen.upper() == "F0":
                if not (getattr(self, "ancestry", None) or []):
                    self.ancestry = [self.id]
                if not (getattr(self, "paternal_ancestry", None) or []):
                    self.paternal_ancestry = [self.id]
        except Exception:
            pass
        
        # Normalize trait keys (plant_height vs stem_length)
        if "plant_height" not in self.traits and "stem_length" in self.traits:
            self.traits["plant_height"] = self.traits.get("stem_length")
        
        # Set default traits if missing
        defaults = {
            "plant_height": random.choice(("tall", "dwarf")),
            "flower_position": random.choice(("axial", "terminal")),
            "flower_color": random.choice(("purple", "white")),
            "pod_shape": random.choice(("inflated", "constricted")),
            "pod_color": random.choice(("green", "yellow")),
            "seed_shape": random.choice(("round", "wrinkled")),
            "seed_color": random.choice(("yellow", "green")),
        }
        
        for trait_name, default_value in defaults.items():
            if trait_name not in self.traits or self.traits[trait_name] in (None, ""):
                self.traits[trait_name] = default_value
        
        # Initialize reproductive capacity
        self._init_reproduction()
    
    def _init_reproduction(self):
        """Initialize realistic pod and ovule counts."""
        try:
            if not getattr(self, "pods_total", 0):
                # Mendel-era average ~10 pods per plant (±2), clamped 5-20
                self.pods_total = max(5, min(20, int(round(random.gauss(10, 2)))))
            
            # Pods exist by default ONLY for non-emasculated plants (selfing possible)
            if not self.emasculated:
                self.pods_remaining = int(self.pods_total)
            else:
                self.pods_remaining = 0
            
            if not getattr(self, "ovules_per_pod", 0):
                # Typical peas ~7±2 ovules per flower (clamped 5-12)
                self.ovules_per_pod = max(5, min(12, int(round(random.gauss(7, 2)))))
            
            if not getattr(self, "ovules_left", 0):
                self.ovules_left = int(self.ovules_per_pod)
            
            if not hasattr(self, "aborted_ovules"):
                self.aborted_ovules = 0
        except Exception:
            pass
    
    def __hash__(self):
        """Make plants hashable by ID."""
        return self.id
    
    # ========================================================================
    # Growth & Trait Revelation
    # ========================================================================
    
    def advance_growth(self):
        """
        Advance plant growth stage based on age and health.
        Growth speed varies by difficulty setting.
        """
        if not self.alive or self.stage >= 7:
            return

        # ------------------------------------------------------------
        # Safety invariant:
        # Emasculated plants without pollination must not have pods
        # ------------------------------------------------------------
        if self.emasculated and not self.pollinated:
            self.pods_remaining = 0
        elif self.pollinated and self.pods_remaining <= 0:
            # Pollination restores pod development
            self.pods_remaining = int(self.pods_total)

        # Get difficulty-appropriate thresholds
        settings = get_lifecycle_settings(getattr(self, 'difficulty', 'off'))
        base_thresholds = settings["base_thresholds"]
        
        # Handle germination delay for seeds
        delay = getattr(self, "germination_delay", 0)
        effective_age = self.days_since_planting - delay
        
        if self.stage == 1 and effective_age < 0:
            return  # Still underground, not germinated
        
        # Check all stages we can advance to
        # Keep advancing while we meet the requirements
        while self.stage < 7:
            next_stage = self.stage + 1
            
            # Health affects growth speed (penalty days added to threshold)
            health_factor = 0 if self.health > 70 else (1 if self.health > 40 else 2)
            required_days = base_thresholds[next_stage] + health_factor
            
            # Check if ready to advance to next stage
            if effective_age >= required_days:
                self.stage = next_stage
                
                # Mark entry to flowering stage
                try:
                    if self.stage == 5 and getattr(self, 'entered_stage5_age', None) is None:
                        self.entered_stage5_age = self.days_since_planting
                except Exception:
                    pass
                
                # Reveal traits appropriate to new stage
                self.reveal_trait()
                self.reveal_all_available()
                
                # Legacy staged reveal support
                stage_to_index = {3: 0, 4: 1, 5: 2}
                if self.stage in stage_to_index:
                    idx = stage_to_index[self.stage]
                    while len(self.revealed_traits) <= idx and len(self.revealed_traits) < len(self.reveal_order):
                        self.discover_next_trait()
            else:
                # Can't advance further, stop checking
                break
        
        # Ensure full revelation at maturity
        if self.stage >= 7:
            self.reveal_all_available()
    
    def reveal_trait(self):
        """
        Reveal a random trait that has reached its stage threshold.
        
        Returns:
            Tuple of (trait_name, trait_value) if revealed, None otherwise
        """
        if not self.alive:
            return None
        
        # Ensure reveal_order is mutable
        if isinstance(getattr(self, "reveal_order", []), tuple):
            try:
                self.reveal_order = list(self.reveal_order)
            except Exception:
                self.reveal_order = []
        
        # Find available traits to reveal
        available = [
            trait for trait, stage_threshold in TRAITS.items()
            if stage_threshold <= self.stage and trait not in self.revealed_traits
        ]
        
        if available:
            trait = random.choice(available)
            self.revealed_traits[trait] = self.traits.get(trait, "?")
            self.reveal_order.append(trait)
            return trait, self.revealed_traits[trait]
        
        return None
    
    def reveal_all_available(self):
        """Reveal all traits whose stage threshold has been reached."""
        try:
            for trait, threshold in TRAITS.items():
                if self.stage >= threshold and trait not in self.revealed_traits:
                    self.revealed_traits[trait] = self.traits.get(trait, "?")
                    try:
                        if trait not in getattr(self, "reveal_order", []):
                            self.reveal_order.append(trait)
                    except Exception:
                        pass
        except Exception:
            pass
    
    def discover_next_trait(self):
        """Reveal the next trait using true values (no randomness)."""
        # Check reveal_order first
        try:
            for trait in getattr(self, "reveal_order", []):
                if trait not in self.revealed_traits:
                    self.revealed_traits[trait] = self.traits.get(trait, self.revealed_traits.get(trait, "?"))
                    return
        except Exception:
            pass
        
        # Otherwise reveal any eligible trait
        try:
            for trait, threshold in TRAITS.items():
                if self.stage >= threshold and trait not in self.revealed_traits:
                    self.revealed_traits[trait] = self.traits.get(trait, "?")
                    try:
                        if trait not in getattr(self, "reveal_order", []):
                            self.reveal_order.append(trait)
                    except Exception:
                        pass
                    return
        except Exception:
            pass
    
    # ========================================================================
    # Water & Health Management
    # ========================================================================
    
    def tick_phase(self, weather: str):
        """
        Update plant per growth phase (legacy 4-phase system).
        
        Args:
            weather: Current weather symbol
        """
        if not self.alive:
            return
        
        # Evaporation based on weather
        if weather in ("☀️", "⛅"):
            evap = 6
        elif weather in ("☁️",):
            evap = 4
        else:
            evap = 2
        
        self.water = max(0, self.water - evap)
        
        # Rain replenishes water
        if weather in ("🌧", "⛈"):
            self.water = min(100, self.water + 8)
        
        # Health adjustments based on water level
        self._update_health_from_water()
    
    def tick_hour(self, weather: str, temp: float):
        """
        Update plant per hour (fine-grained system).
        
        Args:
            weather: Current weather symbol
            temp: Current temperature in °C
        """
        if not self.alive:
            return
        
        # Temperature-adjusted evaporation
        try:
            temp_diff = float(temp) - 15.0
        except Exception:
            temp_diff = 0.0
        
        base_evap = 0.8
        evap_rate = base_evap + 0.06 * max(0.0, temp_diff) - 0.04 * max(0.0, -temp_diff)
        
        # Weather modifier
        weather_factor = {
            '☀️': 1.0, '🌞': 1.0,
            '⛅': 0.85,
            '☁️': 0.7,
            '🌧': 0.4, '⛈': 0.4,
        }.get(weather, 0.8)
        
        evap = max(0.2, min(2.2, evap_rate * weather_factor))
        self.water = max(0, int(round(self.water - evap)))
        
        # Rain adds water (with ceiling)
        if weather in ("🌧", "⛈") and self.water < 55:
            inc = 1 if weather == "🌧" else 2
            self.water = min(70, self.water + inc)
        
        # Micro health adjustments
        self._update_health_from_water()
    
    def _update_health_from_water(self):
        """Adjust health based on current water level."""
        if self.water < 20 or self.water > 95:
            self.health = max(0, self.health - 2)
        elif self.water > 85:
            self.health = max(0, self.health - 1)
        elif 40 <= self.water <= 70:
            # Senescent plants cannot recover health
            if not getattr(self, 'senescent', False):
                self.health = min(100, self.health + 1)
        elif 30 <= self.water < 40 or 70 < self.water <= 85:
            pass  # Neutral bands
        else:
            self.health = max(0, self.health - 1)
        
        # Death check
        if self.health <= 0:
            self.alive = False
            # Don't change stage - dead plant keeps its stage at time of death
    
    def water_plant(self, phase: str):
        """
        Manually water the plant.
        
        Args:
            phase: Current time of day ("morning", "noon", "afternoon", "evening")
            
        Returns:
            Status message
        """
        if not self.alive:
            return "Plant is dead."
        
        self.water = min(100, self.water + 30)
        
        # Midday watering causes stress
        if phase in ("noon", "afternoon"):
            penalty = random.randint(1, 3) if self.health >= 50 else random.randint(5, 10)
            self.health = max(0, self.health - penalty)
            
            if self.health == 0:
                self.alive = False
                # Don't change stage - dead plant keeps its stage
            
            return f"Watered (stress -{penalty})."
        
        return "Watered."
    
    # ========================================================================
    # Reproduction & Pollination
    # ========================================================================
    
    def can_emasculate(self):
        """
        Check if plant can be emasculated (anthers removed).
        
        Returns:
            Tuple of (bool, str) - (can_emasculate, reason)
        """
        if not self.alive:
            return (False, "Plant not alive")
        
        if self.stage not in (4, 5):
            return (False, "Emasculate during bud/early flowering (Stages 4–5)")
        
        if self.emasculated:
            return (False, "Already emasculated")
        
        return (True, "")
    
    def can_collect_pollen(self):
        """
        Check if pollen can be collected from this plant.
        
        Returns:
            Tuple of (bool, str) - (can_collect, reason)
        """
        if self.emasculated:
            return False, "This flower was emasculated: it cannot produce pollen anymore."
        
        if not self.alive:
            return False, "Plant not alive!"
        
        if self.stage != 5:
            return False, "Collect during flowering stage!"
        
        if self.health < 70:
            return False, "Health must be ≥ 70!"
        
        return True, ""
    
    # ========================================================================
    # Display & Visual
    # ========================================================================
    
    def color(self) -> str:
        """
        Get display color based on health status.
        
        Returns:
            Hex color string
        """
        if not self.alive:
            return "#666666"
        
        if self.health >= 80:
            return "#008b1c"
        elif self.health >= 60:
            return "#6f6000"
        elif self.health >= 40:
            return "#cc6000"
        elif self.health >= 20:
            return "#f90000"
        else:
            return "#f33000"
    
    @classmethod
    def get_icons(cls):
        """
        Lazy-load icon resources (class method).
        
        Returns:
            Dictionary of icon PhotoImages
        """
        if cls._ICONS is None:
            print("Loading icons from disk...")
            cls._ICONS = {
                'seedling': tk.PhotoImage(file="seedling.png"),
                'adult': tk.PhotoImage(file="plant.png"),
                'dead': tk.PhotoImage(file="withered.png")
            }
        return cls._ICONS
