from dataclasses import dataclass, field, InitVar
import random
from typing import Optional

import tkinter as tk

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

TRAITS = {
    "plant_height": 3,
    "flower_position": 5,
    "flower_color": 5,
    "pod_shape": 7,
    "pod_color": 6,
    "seed_shape": 7,
    "seed_color": 7,
}

@dataclass
class Plant:
    id: int
    env: InitVar['GardenEnvironment'] # type: ignore #
    generation: str = "F0"
    stage: int = 0
    alive: bool = True
    health: int = 100
    water: int = 50
    days_since_planting: int = 0
    traits: dict = field(default_factory=dict)
    revealed_traits: dict = field(default_factory=dict)
    reveal_order: list = field(default_factory=list)
    observed_today: set = field(default_factory=set)
    entered_stage5_age: int = None
    # Lifespan controls
    max_age_days: int = field(default_factory=lambda: random.randint(60, 90))
    senescent: bool = False
    # Stores data about a successful pollination that will yield cross seeds at harvest
    pending_cross: Optional[dict] = None
    pollinated: bool = False

    # Emasculation state
    emasculated: bool = False
    emasc_day: int = None
    emasc_phase: str = None
    selfing_frac_before_emasc: float = 0.0
    # Reproductive capacity realism knobs
    pods_total: int = 0            # total pods expected on this plant
    pods_remaining: int = 0        # pods not yet exhausted
    ovules_per_pod: int = 0        # ovules capacity per pod
    ovules_left: int = 0           # remaining ovules in the current pod
    aborted_ovules: int = 0        # cumulative count (info only)
    ancestry: list = field(default_factory=list)  # maternal chain: [F0_id, F1_id, … up to parent]
    paternal_ancestry: list = field(default_factory=list)

    # --- Pollen / anther inspection state ---
    last_anther_check_day: int | None = None
    anthers_available_today: bool = False
    anthers_collected_day: int | None = None

    def __post_init__(self, env):
        # Normalize trait keys and ensure canonical set exists
        env.register_plant(self)

        # Ensure F0 plants have a visible lineage root.
        # The Trait Inheritance Explorer uses ancestry lists to display lineage.
        # If F0 starts with an empty ancestry, it can appear as “no lineage”.
        try:
            gen = str(getattr(self, "generation", "F0") or "F0")
            if gen.upper() == "F0" and not (getattr(self, "ancestry", None) or []):
                self.ancestry = [self.id]
            if gen.upper() == "F0" and not (getattr(self, "paternal_ancestry", None) or []):
                self.paternal_ancestry = [self.id]
        except Exception:
            pass
        if "plant_height" not in self.traits and "stem_length" in self.traits:
            self.traits["plant_height"] = self.traits.get("stem_length")
        defaults = {
            "plant_height": random.choice(("tall", "dwarf")),
            "flower_position": random.choice(("axial", "terminal")),
            "flower_color": random.choice(("purple", "white")),
            "pod_shape": random.choice(("inflated", "constricted")),
            "pod_color": random.choice(("green", "yellow")),
            "seed_shape": random.choice(("round", "wrinkled")),
            "seed_color": random.choice(("yellow", "green")),
        }
        for k, v in defaults.items():
            if k not in self.traits or self.traits[k] in (None, ""):
                self.traits[k] = v

        # Initialize reproduction knobs if unset
        try:
            if not getattr(self, "pods_total", 0):
                # Mendel-era conservative average ~10 pods per plant (±2), clamp 5..20
                self.pods_total = max(5, min(20, int(round(random.gauss(10, 2)))))
            if not getattr(self, "pods_remaining", 0):
                self.pods_remaining = int(self.pods_total)
            if not getattr(self, "ovules_per_pod", 0):
                # Typical peas ~7±2 ovules per flower (clamp 5..12)
                self.ovules_per_pod = max(5, min(12, int(round(random.gauss(7, 2)))))
            if not getattr(self, "ovules_left", 0):
                self.ovules_left = int(self.ovules_per_pod)
            if not hasattr(self, "aborted_ovules"):
                self.aborted_ovules = 0
        except Exception:
            pass
    
    def __hash__(self):
        return self.id

    def reveal_all_available(self):
        """Reveal every trait whose stage threshold has been reached, using true values from self.traits."""
        try:
            for t, threshold in TRAITS.items():
                if self.stage >= threshold and t not in self.revealed_traits:
                    self.revealed_traits[t] = self.traits.get(t, "?")
                    try:
                        if t not in getattr(self, "reveal_order", []):
                            self.reveal_order.append(t)
                    except Exception:
                        pass
        except Exception:
            pass

    def advance_growth(self):
        if not self.alive or self.stage >= 7:
            return
        base_thresholds = [0, 0, 4, 8, 13, 18, 25, 30]
        health_factor = 0 if self.health > 70 else (1 if self.health > 40 else 2)
        required_days = base_thresholds[self.stage + 1] + health_factor

        # --- Natural germination delay for stage 1 ---
        delay = getattr(self, "germination_delay", 0)

        if self.stage == 1:
            # Still incubating underground
            if self.days_since_planting < delay:
                return  # Not germinated yet


        # Normal growth rule
        if (self.days_since_planting - delay) >= required_days:
            self.stage += 1

            # mark entry age for stage 5 window
            try:
                if self.stage == 5 and getattr(self, 'entered_stage5_age', None) is None:
                    self.entered_stage5_age = self.days_since_planting
            except Exception:
                pass
            # reveal at least one, then ensure everything eligible is revealed
            self.reveal_trait()
            self.reveal_all_available()
            # Keep legacy staged reveal fill-in
            stage_to_index = {3:0, 4:1, 5:2}
            if self.stage in stage_to_index:
                idx = stage_to_index[self.stage]
                while len(self.revealed_traits) <= idx and len(self.revealed_traits) < len(self.reveal_order):
                    self.discover_next_trait()
        # if already mature, guarantee full reveal
        if self.stage >= 7:
            self.reveal_all_available()

    def tick_phase(self, weather: str):
        """Per-phase evap + rain assist + death check."""
        if not self.alive:
            return
        if weather in ("☀️", "⛅"):
            evap = 6
        elif weather in ("☁️",):
            evap = 4
        else:
            evap = 2
        self.water = max(0, self.water - evap)
        if weather in ("🌧", "⛈"):
            self.water = min(100, self.water + 8)

        # Water comfort bands:
        # - Too dry (<20): strong damage
        # - Ideal (40–70): slight healing
        # - Slightly dry/wet (30–40 or 70–85): minor stress
        # - Overwatered (>85): growing damage; very wet (>95): strong damage
        if self.water < 20:
            self.health -= 5
        elif self.water > 95:
            self.health -= 5
        elif self.water > 85:
            self.health -= 3
        elif 40 <= self.water <= 70:
            self.health = min(100, self.health + 2)
        elif 30 <= self.water < 40 or 70 < self.water <= 85:
            self.health = max(0, self.health - 1)
        else:
            # Neutral band (20–30): slight drift down
            self.health = max(0, self.health - 1)

        if self.health <= 0:
            self.alive = False
            self.stage = max(self.stage, 7)

    def tick_hour(self, weather: str, temp: float):
        """Hourly water & health update based on weather and temperature."""
        if not self.alive:
            return
        # Evaporation rate scaled for hourly steps (target ~24/day under sun):
        base = 0.8
        try:
            dt = float(temp) - 15.0
        except Exception:
            dt = 0.0
        rate = base + 0.06*max(0.0, dt) - 0.04*max(0.0, -dt)
        wf = 0.8
        if weather in ('☀️','🌞'):
            wf = 1.0
        elif weather in ('⛅',):
            wf = 0.85
        elif weather in ('☁️',):
            wf = 0.7
        elif weather in ('🌧','⛈'):
            wf = 0.4
        evap = max(0.2, min(2.2, rate*wf))
        # Apply evap (integer-ish effect)
        self.water = max(0, int(round(self.water - evap)))
        # Rain adds water
        if weather in ("🌧", "⛈") and self.water < 55:
            inc = 1 if weather == "🌧" else 2
            self.water = min(70, self.water + inc)
        # Health micro-adjustments
        if self.water < 20 or self.water > 95:
            self.health = max(0, self.health - 2)
        elif self.water > 85:
            self.health = max(0, self.health - 1)
        elif 40 <= self.water <= 70:
            self.health = min(100, self.health + 1)
        elif 30 <= self.water < 40 or 70 < self.water <= 85:
            pass  # near-neutral bands
        else:
            self.health = max(0, self.health - 1)
        if self.health <= 0:
            self.alive = False
            self.stage = max(self.stage, 7)

    def reveal_trait(self):
        if not self.alive:
            return None
        # Ensure reveal_order is a mutable list (older builds used a tuple)
        if isinstance(getattr(self, "reveal_order", []), tuple):
            try:
                self.reveal_order = list(self.reveal_order)
            except Exception:
                self.reveal_order = []
        available = [t for t, s in TRAITS.items() if s <= self.stage and t not in self.revealed_traits]
        if available:
            trait = random.choice(available)
            self.revealed_traits[trait] = self.traits.get(trait, "?")
            self.reveal_order.append(trait)
            return trait, self.revealed_traits[trait]
        return None

    def water_plant(self, phase: str):
        if not self.alive:
            return "Plant is dead."
        self.water = min(100, self.water + 30)
        if phase in ("noon", "afternoon"):
            penalty = random.randint(1, 3) if self.health >= 50 else random.randint(5, 10)
            self.health = max(0, self.health - penalty)
            if self.health == 0:
                self.alive = False
                self.stage = max(self.stage, 6)
            return f"Watered (stress -{penalty})."
        return "Watered."

    def color(self) -> str:
        if not self.alive:
            return "#666666"
        if self.health >= 80:
            base = "#008b1c"
        elif self.health >= 60:
            base = "#6f6000"
        elif self.health >= 40:
            base = "#cc6000"
        elif self.health >= 20:
            base = "#f90000"
        else:
            base = "#f33000"
        return base

    def discover_next_trait(self):
        """Reveal next trait using true self.traits (no randomness)."""
        # use reveal_order if it has pending items
        try:
            for k in getattr(self, "reveal_order", []):
                if k not in self.revealed_traits:
                    self.revealed_traits[k] = self.traits.get(k, self.revealed_traits.get(k, "?"))
                    return
        except Exception:
            pass
        # otherwise reveal any remaining trait that is eligible by stage
        try:
            for t, threshold in TRAITS.items():
                if self.stage >= threshold and t not in self.revealed_traits:
                    self.revealed_traits[t] = self.traits.get(t, "?")
                    try:
                        if t not in getattr(self, "reveal_order", []):
                            self.reveal_order.append(t)
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        return

    def can_emasculate(self):
        if not self.alive:
            return (False, "Plant not alive")
        if self.stage not in (4,5):
            return (False, "Emasculate during bud/early flowering (Stages 4–5)")
        # if getattr(self, "garden", None) and getattr(self.garden, "phase", "morning") not in ("morning","noon"):
        #     return (False, "Do this in morning or noon")
        if self.emasculated:
            return (False, "Already emasculated")
        return (True, "")
    
    def can_collect_pollen(self):
        # Disallow pollen collection after emasculation
        if self.emasculated:
            return False, "This flower was emasculated: it cannot produce pollen anymore."
        if not self.alive:
            return False, "Plant not alive!"
        if self.stage != 5:
            return False, "Collect during flowering stage!"
        # phase_now, _ = self.garden._hour_to_phase(int(getattr(self.garden, "clock_hour", 6)))
        # if phase_now not in ("morning", "noon"):
        #     return False, "Collect in morning or noon!"


        # if (self.days_since_planting - start) > 7:
        #     return False, "Pollen past prime!"

        if self.health < 70:
            return False, "Health must be ≥ 70!"
        return True, ""

    _ICONS = None

    @classmethod
    def get_icons(cls):
        """Lazy-loads icons only when needed."""
        if cls._ICONS is None:
            print("Loading icons from disk...")  # Only happens once
            cls._ICONS = {
                'seedling': tk.PhotoImage(file="seedling.png"),
                'adult': tk.PhotoImage(file="plant.png"),
                'dead': tk.PhotoImage(file="withered.png")
            }
        return cls._ICONS
