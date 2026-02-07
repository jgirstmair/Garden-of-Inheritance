import tkinter as tk
import time
from abc import ABC, abstractmethod
from typing import List


TICKS_PER_HOUR = 4
TICKS_PER_DAY = TICKS_PER_HOUR * 24

class Entity(ABC):
    @abstractmethod
    def update(self, tick_counter: int):
        pass


class GameTicker:

    def __init__(self, root: tk.Tk):
        self.root = root

        self._wants_running = False
        self._is_running = False

        self.tick_delay_ms = 17
        self.loop_id = None

        self.tick_counter: int = 0

        self.daily_entities: List[Entity] = []
        self.hourly_entities: List[Entity] = []
        self.granular_entities: List[Entity] = []


    def _loop(self):
        #do loop update
        if self.tick_counter%TICKS_PER_HOUR == 0:
            for entity in self.hourly_entities:
                entity.update(self.tick_counter)
        if self.tick_counter%TICKS_PER_DAY == 0:
            for entity in self.daily_entities:
                entity.update(self.tick_counter)
        for entity in self.granular_entities:
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




