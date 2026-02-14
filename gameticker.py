import tkinter as tk
from abc import ABC, abstractmethod
from collections import defaultdict


class Entity(ABC):
    @abstractmethod
    def update(self, tick_counter: int):
        pass
    
    @abstractmethod
    def __hash__(self):
        pass


class GameTicker:

    def __init__(self, root: tk.Tk):
        self.root = root

        self._wants_running = False
        self._is_running = False

        self.tick_delay_ms = 17

        self.tick_counter: int = 0

        # A map of {frequency_in_ticks: set(entities)}
        # e.g., {1: {granular}, 4: {hourly}, 96: {daily}}
        self._registry: dict[int, set[Entity]] = defaultdict(set)


    def _loop(self):
        for frequency, entities in self._registry.items():
            if self.tick_counter % frequency == 0:
                for entity in entities:
                    entity.update(self.tick_counter)

        self.tick_counter += 1

        if self._wants_running:
            self.root.after(self.tick_delay_ms, self._loop)
        else:
            self._is_running = False

    def set_target_tps(self, tps: float):
        self.tick_delay_ms = int(1000 / tps)
    
    @property
    def is_running(self):
        return self._is_running

    @property
    def wants_running(self):
        return self._wants_running
    
    @wants_running.setter
    def wants_running(self, val: bool):

        self._wants_running = val
        if not self._is_running and self._wants_running:
            self._is_running = True
            self._loop()

    def register(self, entity: Entity, frequency: int=1):
        self._registry[frequency].add(entity)
        entity.update(self.tick_counter)

    def unregister(self, entity: Entity, frequency: int=1):
        self._registry[frequency].remove(entity)

        
if __name__ == '__main__':

    root = tk.Tk()

    ticker = GameTicker(root)

    def pause_ticker(t: GameTicker):
        t.wants_running = False
        print(t.tick_counter)
    ticker.wants_running = True
    ticker.set_target_tps(1000000000)
    root.after(4000, pause_ticker, ticker)
    root.mainloop()




