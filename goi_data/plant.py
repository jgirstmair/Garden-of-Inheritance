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
    "flower_position": 4,
    "flower_color": 4,
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
        "max_age_range": (85, 115),  # stage 7 at day 55; min 85 gives ≥30-day harvest window
        "description": "Moderate: Balanced growth speed"
    },
    "enforce": {  # Realistic - Slow growth, long lifespan (Mendel-era timing)
        "base_thresholds": [0, 0, 7, 14, 28, 42, 60, 85],
        "max_age_range": (125, 160),  # stage 7 at day 85; min 125 gives ≥40-day harvest window
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


# Re-flowering: when a pod has ripened, a new flower bud may form in its
# place (1 in 5). A plant never carries more than 12 buds/flowers and 12
# pods at the same time. Timing of such late flowers in game days:
REFLOWER_CHANCE = 0.2
MAX_FLOWERS_AT_ONCE = 12
MAX_PODS_AT_ONCE = 12
# Growth speed: every plant gets its own pace (about ±6 %, at most ±12 %),
# so plants sown together don't all change stage on the same day. Weak
# plants grow this much slower on top.
GROWTH_PACE_SD = 0.06
GROWTH_PACE_RANGE = (0.88, 1.12)
WEAK_GROWTH_SLOWDOWN = 1.2
# Seeds (ovules) per pod. Mendel: well-developed pods held "6-9 seeds on
# average"; the game uses 5-8. Each pod gets its own number (see pod_ovules).
SEEDS_PER_POD = (5, 8)
# Realistic difficulty only — Mendel's own sowing results: of sown seeds,
# 89-94 % gave plants that bore fruit ("einige Samen nicht keimten";
# e.g. 102 of 108, 96 of 108, 639 of 687). Split into seeds that never
# come up and plants that grow and flower but set no pods.
SPROUT_FAIL_CHANCE = 0.07
FRUIT_FAIL_CHANCE = 0.03
LATE_BUD_DAYS = 3      # bud
LATE_OPEN_DAYS = 4     # open flower (can be emasculated / pollinated)
LATE_POD_DAYS = 5      # pod growing, then ripe


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
    # One entry per flower (= per possible pod), in the order they open:
    #   {"i": 1.., "emasc": None | {"self_frac", "selfed_before", "when", "day"},
    #    "pollen": [donor dicts], "harvested": bool, "anthers_removed": 0..10}
    # The plant-level fields above (emasculated, pollinated, pending_cross,
    # pods_remaining) are summaries kept in sync by sync_reproduction().
    flowers: list = field(default_factory=list)
    n_emasculated: int = 0
    
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

    # Vigour / weak-plant flag (Mendel excluded weak specimens from experiments)
    # Set once at planting based on difficulty; never changes afterwards.
    is_weak: bool = False
    # If True the plant is constitutionally unable to reach flowering (stage 5+).
    # ~70% of weak plants are blocked; the other 30% flower but bear very few pods.
    weak_blocks_flowering: bool = False
    # Own growth speed (1.0 = normal, >1 = slower); rolled once at planting.
    growth_pace: float = 0.0
    # Sowing losses (Realistic difficulty, see roll_sowing_losses)
    sprout_fails: bool = False         # the seed never comes up
    fruit_fails: bool = False          # grows and flowers, but sets no pods
    failed_to_sprout: bool = False     # it happened: the seed didn't come up

    # Late-season stress flag (enforce/realistic mode only).
    # Set externally by _season_daily_update when the calendar enters autumn.
    # Once True: health cannot recover, color shifts to sick palette, stress
    # damage is amplified — plant will die before January.
    late_season_stress: bool = False

    # Purely cosmetic: decided once at planting so the garden grid looks less
    # uniform. When True, this plant's icon is mirrored horizontally at every
    # growth stage for its entire life.
    flipped_horizontally: bool = False

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
        
        # Roll a one-time cosmetic horizontal flip so the garden grid doesn't
        # look like a repeated, uniform pattern. Decided once here and never
        # re-rolled, so it stays consistent across every growth stage.
        if not getattr(self, "flipped_horizontally", False):
            self.flipped_horizontally = (random.random() < 0.5)

        # Roll weak-plant status based on difficulty (only if not already set)
        # Probabilities follow Mendel's own observation that a noticeable minority
        # of plants were too weak to give reliable results.
        if not getattr(self, "is_weak", False):
            _weak_prob = {"off": 0.0, "overlay": 0.125, "enforce": 0.225}.get(
                self.difficulty, 0.0)
            if _weak_prob > 0.0 and random.random() < _weak_prob:
                self.is_weak = True
                # 70% blocked from flowering entirely; 30% flower but low fertility
                self.weak_blocks_flowering = (random.random() < 0.70)

        # Each plant's own growth speed (see GROWTH_PACE_SD).
        if not getattr(self, "growth_pace", 0.0):
            lo, hi = GROWTH_PACE_RANGE
            self.growth_pace = max(lo, min(hi, random.gauss(1.0, GROWTH_PACE_SD)))

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
                if getattr(self, "is_weak", False):
                    # Weak plants that manage to flower bear very few pods (1-3)
                    self.pods_total = random.randint(1, 3)
                else:
                    # Mendel-era average ~10 pods per plant (±2), clamped 5-20
                    self.pods_total = max(5, min(MAX_PODS_AT_ONCE, int(round(random.gauss(10, 2)))))
                    # Dwarf plants carry about half as many flowers (and pods)
                    _h = str((self.traits or {}).get("plant_height", "tall")).lower()
                    if _h in ("dwarf", "short"):
                        self.pods_total = max(2, int(round(self.pods_total / 2.0)))
            
            # Pods exist by default ONLY for non-emasculated plants (selfing possible)
            if not self.emasculated:
                self.pods_remaining = int(self.pods_total)
            else:
                self.pods_remaining = 0
            
            if not getattr(self, "ovules_per_pod", 0):
                # The plant's typical pod (its pods vary by one around it)
                self.ovules_per_pod = random.randint(*SEEDS_PER_POD)
            
            if not getattr(self, "ovules_left", 0):
                self.ovules_left = int(self.ovules_per_pod)
            
            if not hasattr(self, "aborted_ovules"):
                self.aborted_ovules = 0
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # Per-flower reproduction
    # ------------------------------------------------------------------
    def ensure_flowers(self):
        """Makes sure there is one record per flower (pods_total). Old
        saves (plant-level emasculation / pollination) are converted: every
        flower gets the plant's old state."""
        n = int(getattr(self, "pods_total", 0) or 0)
        fl = getattr(self, "flowers", None)
        if not isinstance(fl, list):
            fl = []
        if len(fl) == n and all(isinstance(f, dict) for f in fl):
            self.flowers = fl
            if getattr(self, "fruit_fails", False):
                for f in fl:
                    f["no_fruit"] = True
            return fl
        legacy = not fl
        fl = [f for f in fl if isinstance(f, dict)][:n]
        while len(fl) < n:
            fl.append({"i": len(fl) + 1, "emasc": None, "pollen": [],
                       "harvested": False, "anthers_removed": 0})
        for k, f in enumerate(fl):
            f["i"] = k + 1
            f.setdefault("emasc", None)
            f.setdefault("pollen", [])
            f.setdefault("harvested", False)
            f.setdefault("anthers_removed", 0)
        if legacy:
            pc = getattr(self, "pending_cross", None) or {}
            donors = list(pc.get("donors") or [])
            if not donors and pc.get("donor_id") is not None:
                donors = [{"donor_id": pc.get("donor_id"), "donor_genotype": {}}]
            if getattr(self, "emasculated", False):
                frac = float(getattr(self, "selfing_frac_before_emasc", 0.0) or 0.0)
                n_self = self.selfed_pods_after_emasculation()
                for k, f in enumerate(fl):
                    f["emasc"] = {"self_frac": frac, "selfed_before": k < n_self,
                                  "when": None, "day": getattr(self, "emasc_day", None)}
            if donors:
                for f in fl:
                    f["pollen"] = [dict(d) for d in donors]
            # pods already harvested from an old save
            podf = [f for f in fl if self.flower_sets_pod(f)]
            done = max(0, len(podf) - int(getattr(self, "pods_remaining", len(podf)) or 0))
            if int(getattr(self, "stage", 0) or 0) >= 7:
                for f in podf[:done]:
                    f["harvested"] = True
        self.flowers = fl
        return fl

    def pod_ovules(self, f):
        """Seeds (ovules) in this flower's pod: the plant's typical number,
        give or take one, within SEEDS_PER_POD. Decided once per pod."""
        lo, hi = SEEDS_PER_POD
        n = f.get("ovules") if isinstance(f, dict) else None
        if not isinstance(n, int):
            base = int(getattr(self, "ovules_per_pod", 0) or 0) or random.randint(lo, hi)
            base = max(lo, min(hi, base))           # older saves could have up to 12
            n = max(lo, min(hi, base + random.choice((-1, 0, 0, 1))))
            if isinstance(f, dict):
                f["ovules"] = n
        return n

    @staticmethod
    def flower_sets_pod(f):
        """A flower becomes a pod unless it was emasculated, got no pollen
        and had not already pollinated itself before."""
        if f.get("no_fruit"):
            return False                  # plant that sets no fruit (Realistic)
        e = f.get("emasc")
        if not e:
            return True
        return bool(f.get("pollen")) or bool(e.get("selfed_before"))

    def next_pod_flower(self, ripe_only=True):
        """The next flower whose (ripe) pod can still be harvested, or None."""
        for f in self.ensure_flowers():
            if self.flower_sets_pod(f) and not f.get("harvested"):
                if not ripe_only or self.pod_is_ripe(f):
                    return f
        return None

    # --- re-flowering: a ripe pod may be followed by a new bud (1 in 5) ---
    def late_flower_age(self, f):
        """Game days since a re-flowering bud appeared (None for the plant's
        first flowers, which follow its growth stages)."""
        born = f.get("born")
        if born is None:
            return None
        return int(getattr(self, "days_since_planting", 0) or 0) - int(born)

    def late_flower_phase(self, f):
        """'bud' / 'open' / 'pod' (growing) / 'ripe' for a re-flowering bud."""
        a = self.late_flower_age(f)
        if a is None:
            return None
        if a < LATE_BUD_DAYS:
            return "bud"
        if a < LATE_BUD_DAYS + LATE_OPEN_DAYS:
            return "open"
        if a < LATE_BUD_DAYS + LATE_OPEN_DAYS + LATE_POD_DAYS:
            return "pod"
        return "ripe"

    def pod_is_ripe(self, f):
        if f.get("born") is not None:
            return self.late_flower_phase(f) == "ripe"
        return int(getattr(self, "stage", 0) or 0) >= 7

    def ripe_pods(self):
        return sum(1 for f in self.ensure_flowers()
                   if self.flower_sets_pod(f) and not f.get("harvested") and self.pod_is_ripe(f))

    def _flowers_in_bloom(self):
        """Buds and open flowers right now."""
        n = 0
        st = int(getattr(self, "stage", 0) or 0)
        for f in self.ensure_flowers():
            ph = self.late_flower_phase(f)
            if ph in ("bud", "open"):
                n += 1
            elif ph is None and st in (4, 5):
                n += 1
        return n

    def daily_reflower(self):
        """Once a day: every pod that has just ripened gets one 1-in-5
        chance to be followed by a new flower bud — never more than
        MAX_FLOWERS_AT_ONCE buds/flowers and MAX_PODS_AT_ONCE pods at once.
        Not on weak, ageing (senescent) or late-season plants."""
        try:
            if (not self.alive or int(getattr(self, "stage", 0) or 0) < 7
                    or getattr(self, "is_weak", False) or getattr(self, "senescent", False)
                    or getattr(self, "late_season_stress", False)):
                return 0
            fl = self.ensure_flowers()
            added = 0
            for f in list(fl):
                if f.get("rerolled") or not self.flower_sets_pod(f) or not self.pod_is_ripe(f):
                    continue
                f["rerolled"] = True
                if random.random() >= REFLOWER_CHANCE:
                    continue
                pods_now = sum(1 for g in fl if self.flower_sets_pod(g) and not g.get("harvested"))
                if self._flowers_in_bloom() >= MAX_FLOWERS_AT_ONCE or pods_now >= MAX_PODS_AT_ONCE:
                    continue
                fl.append({"i": len(fl) + 1, "emasc": None, "pollen": [], "harvested": False,
                           "anthers_removed": 0,
                           "born": int(getattr(self, "days_since_planting", 0) or 0)})
                self.pods_total = len(fl)
                added += 1
            if added:
                self.fully_harvested = False
                self.sync_reproduction()
            return added
        except Exception:
            return 0

    def sync_reproduction(self):
        """Recomputes the plant-level summaries from the flowers."""
        try:
            fl = self.ensure_flowers()
            emasc = [f for f in fl if f.get("emasc")]
            self.n_emasculated = len(emasc)
            self.emasculated = bool(fl) and len(emasc) == len(fl)   # no anthers left at all
            if emasc:
                self.selfing_frac_before_emasc = sum(
                    float(f["emasc"].get("self_frac", 0) or 0) for f in emasc) / len(emasc)
            donors = [d for f in fl for d in (f.get("pollen") or [])]
            self.pollinated = bool(donors)
            if donors:
                pc = self.pending_cross if isinstance(self.pending_cross, dict) else {}
                pc = dict(pc)
                pc["donors"] = donors
                pc.pop("donor_id", None)
                self.pending_cross = pc
            else:
                self.pending_cross = None
            self.pods_remaining = sum(1 for f in fl
                                      if self.flower_sets_pod(f) and not f.get("harvested"))
        except Exception:
            pass

    def selfed_pods_after_emasculation(self):
        """Pods an emasculated, unpollinated plant still sets because some
        flowers had already pollinated themselves: the selfing share of
        all pods (at least one when the share is noticeable)."""
        try:
            frac = max(0.0, min(1.0, float(getattr(self, "selfing_frac_before_emasc", 0.0) or 0.0)))
            total = int(getattr(self, "pods_total", 0) or 0)
            n = int(round(total * frac))
            if n == 0 and frac >= 0.05 and total > 0:
                n = 1
            return n
        except Exception:
            return 0

    def __hash__(self):
        """Make plants hashable by ID."""
        return self.id
    
    # ========================================================================
    # Growth & Trait Revelation
    # ========================================================================
    
    def roll_sowing_losses(self):
        """Called once when a seed is sown. Realistic difficulty only."""
        self.sprout_fails = False
        self.fruit_fails = False
        if str(getattr(self, "difficulty", "off")).lower() != "enforce":
            return
        r = random.random()
        if r < SPROUT_FAIL_CHANCE:
            self.sprout_fails = True
        elif r < SPROUT_FAIL_CHANCE + FRUIT_FAIL_CHANCE:
            self.fruit_fails = True

    def growth_factor(self):
        """How much longer than normal this plant takes per stage."""
        try:
            f = float(getattr(self, "growth_pace", 1.0) or 1.0)
        except Exception:
            f = 1.0
        if getattr(self, "is_weak", False):
            f *= WEAK_GROWTH_SLOWDOWN
        return f

    def stage_thresholds(self):
        """Days (after germination) at which this plant reaches each
        stage: the difficulty's thresholds stretched by its own pace."""
        base = get_lifecycle_settings(getattr(self, "difficulty", "off"))["base_thresholds"]
        f = self.growth_factor()
        return [round(t * f, 2) for t in base]

    def advance_growth(self):
        """
        Advance plant growth stage based on age and health.
        Growth speed varies by difficulty setting.
        """
        if not self.alive or self.stage >= 7:
            return
        if getattr(self, 'fully_harvested', False):
            return

        # ------------------------------------------------------------
        # Emasculated plants without pollination only keep the pods of
        # the flowers that had already selfed before the anthers came
        # off (emasculated too late) — fewer pods the earlier it was
        # done; none at all for a clean, early emasculation.
        # (Pods are only harvested at stage 7, so nothing is lost here.)
        # ------------------------------------------------------------
        # Per flower now: pods = flowers that set seed (see sync_reproduction).
        self.sync_reproduction()

        # Get difficulty-appropriate thresholds
        base_thresholds = self.stage_thresholds()     # own pace, weak = slower
        
        # Handle germination delay for seeds
        delay = getattr(self, "germination_delay", 0)
        effective_age = self.days_since_planting - delay
        
        if self.stage == 1 and effective_age < 0:
            return  # Still underground, not germinated

        # A seed that never comes up: once it should have sprouted, it's
        # gone (the plot is cleared and the player told — see
        # GardenApp._cleanup_old_dead_plants).
        if (self.stage == 1 and getattr(self, "sprout_fails", False)
                and effective_age >= base_thresholds[2]):
            self.alive = False
            self.failed_to_sprout = True
            return
        
        # Weak plants that block flowering cannot advance past stage 4 (budding).
        # This mirrors Mendel's observation that weak specimens "entweder gar nicht
        # zur Blüthe gelangen" (either don't reach flowering at all).
        flowering_cap = 4 if (getattr(self, "is_weak", False)
                              and getattr(self, "weak_blocks_flowering", False)) else 7

        # Check all stages we can advance to
        # Keep advancing while we meet the requirements
        while self.stage < flowering_cap:
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

        seed_color is deliberately excluded here — it can only be revealed
        by clicking a mature pod in the plant inspector window (see
        reveal_seed_color), not through the general trait-reveal roll.
        
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
            if trait != "seed_color" and stage_threshold <= self.stage and trait not in self.revealed_traits
        ]
        
        if available:
            trait = random.choice(available)
            self.revealed_traits[trait] = self.traits.get(trait, "?")
            self.reveal_order.append(trait)
            return trait, self.revealed_traits[trait]
        
        return None
    
    def reveal_all_available(self):
        """Reveal all traits whose stage threshold has been reached.

        seed_color is deliberately excluded — see reveal_trait().
        """
        try:
            for trait, threshold in TRAITS.items():
                if trait == "seed_color":
                    continue
                if self.stage >= threshold and trait not in self.revealed_traits:
                    self.revealed_traits[trait] = self.traits.get(trait, "?")
                    try:
                        if trait not in getattr(self, "reveal_order", []):
                            self.reveal_order.append(trait)
                    except Exception:
                        pass
        except Exception:
            pass

    def reveal_seed_color(self):
        """
        Reveal the seed_color trait specifically — called when the player
        clicks a mature pod in the plant inspector window. Requires the
        plant to actually be at the stage where seeds exist (same
        threshold as TRAITS["seed_color"]); a no-op otherwise or if
        already revealed.
        """
        if not self.alive:
            return None
        threshold = TRAITS.get("seed_color", 7)
        if self.stage < threshold:
            return None
        if "seed_color" in self.revealed_traits:
            return "seed_color", self.revealed_traits["seed_color"]
        self.revealed_traits["seed_color"] = self.traits.get("seed_color", "?")
        try:
            if isinstance(getattr(self, "reveal_order", []), tuple):
                self.reveal_order = list(self.reveal_order)
            if "seed_color" not in self.reveal_order:
                self.reveal_order.append("seed_color")
        except Exception:
            pass
        return "seed_color", self.revealed_traits["seed_color"]
    
    def discover_next_trait(self):
        """Reveal the next trait using true values (no randomness).

        seed_color is deliberately excluded — see reveal_trait().
        """
        # Check reveal_order first
        try:
            for trait in getattr(self, "reveal_order", []):
                if trait == "seed_color":
                    continue
                if trait not in self.revealed_traits:
                    self.revealed_traits[trait] = self.traits.get(trait, self.revealed_traits.get(trait, "?"))
                    return
        except Exception:
            pass
        
        # Otherwise reveal any eligible trait
        try:
            for trait, threshold in TRAITS.items():
                if trait == "seed_color":
                    continue
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
        
        # Evaporation based on weather (weak plants lose ~50% more)
        if weather in ("☀️", "⛅"):
            evap = 6
        elif weather in ("☁️",):
            evap = 4
        else:
            evap = 2
        if getattr(self, "is_weak", False):
            evap = int(round(evap * 1.5))

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
        
        # Weak plants lose water ~50% faster (reduced root system / poor stomatal control)
        if getattr(self, "is_weak", False):
            evap_rate *= 1.5
        evap = max(0.2, min(3.3, evap_rate * weather_factor))
        self.water = max(0, int(round(self.water - evap)))
        
        # Rain adds water (with ceiling)
        if weather in ("🌧", "⛈") and self.water < 55:
            inc = 1 if weather == "🌧" else 2
            self.water = min(70, self.water + inc)
        
        # Micro health adjustments
        self._update_health_from_water()
    
    def _update_health_from_water(self):
        """Adjust health based on current water level.

        Thresholds are aligned to the same 5-band Soil Moisture legend shown
        in the in-game Help dialog and used to color the water bar/drop
        (Dry 0-25, Slightly moist 26-50, Evenly moist 51-75, Soggy 76-90,
        Waterlogged 91-100), so the visible color always tells you which
        health regime a tile is in:
          - Dry / Waterlogged: outright penalty for everyone.
          - Slightly moist / Soggy: safe for normal plants, but weak plants
            still decline.
          - Evenly moist: the only band that regenerates health.

        Weak plants suffer ~50% more from stress (any out-of-range water level
        deals 1.5× the normal penalty), consistent with Mendel's note that weak
        specimens produce unreliable results under adverse conditions.
        """
        _weak = getattr(self, "is_weak", False)

        if self.water <= 25 or self.water > 90:
            # Dry (0-25) or Waterlogged (91-100)
            penalty = 3 if _weak else 2
            self.health = max(0, self.health - penalty)
        elif 51 <= self.water <= 75:
            # Evenly moist (51-75)
            # Senescent, weak, or late-season-stressed plants cannot recover health
            _late = getattr(self, 'late_season_stress', False)
            if not getattr(self, 'senescent', False) and not _weak and not _late:
                self.health = min(100, self.health + 1)
        else:
            # Slightly moist (26-50) or Soggy (76-90)
            if _weak:
                self.health = max(0, self.health - 1)  # weak plants decline even in neutral band

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
        
        if self.stage < 4:
            return (False, "No flowers yet — emasculate buds or open flowers")
        
        if self.emasculated:
            return (False, "All flowers are emasculated")
        
        return (True, "")
    
    def can_collect_pollen(self):
        """
        Check if pollen can be collected from this plant.
        
        Returns:
            Tuple of (bool, str) - (can_collect, reason)
        """
        if getattr(self, "is_weak", False):
            return False, "Weak plant — pollen from weak specimens gives unreliable results."

        if self.emasculated:
            return False, "All flowers were emasculated: no anthers left for pollen."
        
        if not self.alive:
            return False, "Plant not alive!"
        
        if self.stage < 5:
            return False, "Collect once flowering has started!"
        
        if self.health < 70:
            return False, "Health must be ≥ 70!"
        
        return True, ""
    
    # ========================================================================
    # Display & Visual
    # ========================================================================
    
    def color(self) -> str:
        """
        Get display color based on health status.
        Weak plants are shown in a yellowish palette to distinguish them visually.
        
        Returns:
            Hex color string
        """
        if not self.alive:
            return "#666666"

        if getattr(self, "is_weak", False) or getattr(self, "late_season_stress", False):
            # Yellowish-amber sick palette: used for weak plants and late-season decline.
            # Health 80+ stays green so a freshly-stressed plant isn't immediately alarming;
            # below 80 it gradually shifts through amber and ochre as the season kills it.
            if self.health >= 80:
                return "#008b1c"  # still green at full health
            elif self.health >= 60:
                return "#c8a822"  # pale yellow — first sign of stress
            elif self.health >= 40:
                return "#b07010"  # amber
            elif self.health >= 20:
                return "#885500"  # ochre-brown
            else:
                return "#704000"  # dark brown — near death

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
