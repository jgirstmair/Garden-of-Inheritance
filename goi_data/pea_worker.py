"""Background drawing helper for Garden of Inheritance.

Started by the game (one or a few copies) so the drawn plant pictures are
made on other CPU cores while the window stays responsive. It reads jobs
from stdin and writes finished pictures to stdout (both pickled):

    job    = (job_id, traits, seed, args, size, health)   or None to quit
    result = (job_id, (w, h), rgba_bytes, error_text_or_None)

Never run by hand; the game falls back to drawing itself if this file is
missing or the helper can't start.
"""
import os
import pickle
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    out = sys.stdout.buffer
    sys.stdout = sys.stderr            # stray prints must not break the protocol
    inp = sys.stdin.buffer
    import pea_render
    while True:
        try:
            job = pickle.load(inp)
        except (EOFError, OSError):
            break
        except Exception:
            break
        if job is None:
            break
        jid = job[0]
        try:
            _jid, traits, seed, args, size, health = job
            im = pea_render.final_image(traits, seed, args, size, health)
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            res = (jid, im.size, im.tobytes(), None)
        except Exception as e:                 # report, keep running
            res = (jid, None, None, repr(e))
        try:
            pickle.dump(res, out, protocol=pickle.HIGHEST_PROTOCOL)
            out.flush()
        except Exception:
            break


if __name__ == "__main__":
    main()
