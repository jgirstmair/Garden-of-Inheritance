# Garden-of-Inheritance
<img width="158" height="265" alt="mendel" src="https://github.com/user-attachments/assets/a24fc04f-9603-46cc-8878-a7a7f7b54a32" />

## Getting Started

To launch the simulator, run: **Garden-of-Inheritance.py**
- Windows: double click the file
- Mac: open Terminal and enter `python path/to/Garden-of-Inheritance.py` (replace `path/to/` with the actual folder where the file is located)

- Press **H** at any time to open the in-game Help menu.
- For an introduction and gameplay overview, see [**Guide.pdf**](https://github.com/jgirstmair/Garden-of-Inheritance/blob/main/Guide.pdf).

## Requirements

### Python
- **Python 3.10 or higher**
  - Windows: 3.12 or newer recommended
  - Mac: 3.14.5 or newer from python.org recommended (see Mac notes below)

### Required library
- **Pillow** (images): `pip install pillow`

### Optional libraries
- **pygame** (sound effects and background music): `pip install pygame`
- **numpy** (smoother animal animations): `pip install numpy`

Or all at once: `pip install pillow pygame numpy`

### Standard library modules (already included with Python)
tkinter (GUI framework), dataclasses, json, csv, os, sys, time, datetime,
random, math, pathlib, and a few more. Nothing to install.

tkinter comes with Python from python.org on Windows and Mac.
On Linux, install it separately (e.g. `sudo apt install python3-tk`).

### Hardware
| | Minimum | Recommended |
|---|---|---|
| Processor | 2 cores | 4 cores or more |
| Memory | 4 GB | 8 GB |
| Screen (after zoom) | 1280 × 720 | 1920 × 1080 or more |

"After zoom" means the resolution divided by the display scaling:
3840 × 2400 at 225 % is 1707 × 1067. The game adapts to the screen on
first start, and the garden-size wizard recommends a garden that fits.

## Notes for Windows
- Install Python from python.org and tick **"Add Python to PATH"**.
- Full screen is on by default (F11 switches it); it gives room for an
  extra row of plots.

## Notes for Mac
- Use **Python 3.14.5 or newer from python.org**: it includes Tcl/Tk 9,
  which redraws the window much more efficiently on macOS.
  Homebrew (`brew install python-tk@3.14`) also uses Tk 9.
- Avoid Apple's built-in Python (`/usr/bin/python3`): its old Tk is unreliable.
- Pythons with Tk 8.6 (e.g. Miniforge/conda) work, but feel slower with
  a big garden. The game then paces itself: the clock and the animals
  move in bigger steps, and the rain in Mendel's picture stays still.
- Full screen is off by default on a Mac.

## Standard library modules (already included with Python)
- tkinter (GUI framework) - usually pre-installed with Python
- dataclasses
- json
- csv
- os
- sys
- time
- datetime
- random
- math
- pathlib

## License

This project is licensed under the BSD 3-Clause License – see the LICENSE file for details.
