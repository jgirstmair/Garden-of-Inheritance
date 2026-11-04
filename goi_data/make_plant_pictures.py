"""
make_plant_pictures.py — fills the plant picture store in advance.

The game draws every plant picture once and keeps it in
goi_data/plant_pictures/ (see pea_render.final_image). This script draws the
early stages (seed, seedling, leafy plant — the same for every flower and
pod colour) beforehand, so a new game starts without any drawing work.

Run it from the goi_data folder (or anywhere):
    python make_plant_pictures.py              # Grown, plain
    python make_plant_pictures.py --all        # plain, staked, painted, staked + painted
Takes a few minutes; uses all CPU cores but one.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _jobs(styles):
    import pea_render as pr
    ages = [x * 0.5 for x in range(0, int(2 * (pr.BUD_DAY - 1)))]
    out = []
    for painterly, staked in styles:
        for tall in (True, False):
            for terminal in (False, True):
                for v in range(pr.VARIANTS):
                    for age in ages:
                        seeds = ("yellow", "green") if age < pr.GERMINATE + 3 else ("yellow",)
                        for sc in seeds:
                            tr = {"plant_height": "tall" if tall else "dwarf",
                                  "flower_position": "terminal" if terminal else "axial",
                                  "flower_color": "purple", "pod_color": "green",
                                  "pod_shape": "inflated", "seed_color": sc}
                            args = dict(age=age, pods_visible=None, marks=None, late=[],
                                        painterly=painterly, staked=staked, sickness=0.0,
                                        flowers_max=None, flipped=False,
                                        tint=(False, False, False))
                            out.append((tr, 1000 + v, args))
    return out


def _work(job):
    import pea_render as pr
    tr, seed, args = job
    pr.stored_plant_image(tr, seed, args, pr.TILE)
    return 1


def main():
    import multiprocessing as mp
    styles = [(False, False)]
    if "--all" in sys.argv:
        styles = [(False, False), (False, True), (True, False), (True, True)]
    jobs = _jobs(styles)
    n = len(jobs)
    print(f"Drawing {n} plant pictures ...")
    t0 = time.time()
    workers = max(1, (os.cpu_count() or 2) - 1)
    done = 0
    with mp.Pool(workers) as pool:
        for _ in pool.imap_unordered(_work, jobs, chunksize=16):
            done += 1
            if done % 250 == 0 or done == n:
                print(f"  {done}/{n}  ({time.time() - t0:.0f} s)")
    import pea_render as pr
    total = 0
    for root, _d, names in os.walk(os.path.join(pr.STORE_DIR, pr.DRAW_VERSION)):
        total += sum(os.path.getsize(os.path.join(root, x)) for x in names)
    print(f"Done in {time.time() - t0:.0f} s — picture store: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
