#!/usr/bin/env python3
"""Install these demos into the OFFICIAL Tildagon simulator (emfcamp/badge-2024
-software) so they show up in its launcher menu.

    git clone --recursive https://github.com/emfcamp/badge-2024-software.git
    python3 demos/sim/install_to_official_sim.py path/to/badge-2024-software
    cd path/to/badge-2024-software/sim
    cp config.py.default config.py        # remaps buttons to number keys
    pipenv install && pipenv run python run.py

The sim launcher reads apps from sim/apps/<Name>/ and needs metadata.json (NOT
tildagon.toml). Folder/class names are Capitalised so they are valid Python
identifiers -- important for "for", whose folder becomes "For" (a bare "for"
package cannot be imported). App bodies are copied verbatim; only the wrapper
files are generated.
"""
import json
import os
import shutil
import sys

# name -> (number, human title). Order = the shortlist in the research brief.
DEMOS = [
    ("uan", 1, "Tixy grid"),
    ("ciu", 2, "Moire rings"),
    ("tri", 3, "Qix tracer"),
    ("for", 4, "IMU starfield"),
    ("faiv", 5, "Polar tunnel"),
    ("sics", 6, "Hex kaleidoscope"),
    ("seven", 7, "Hopalong plotter"),
    ("eit", 8, "Matrix rain"),
    ("nain", 9, "Plasma tiles"),
    ("ten", 10, "LED phase-lock"),
    ("ileven", 11, "Pipes grower"),
    ("twelv", 12, "Cellular playground"),
    ("thurteen", 13, "Drift lines"),
    ("forteen", 14, "Orbiting metaballs"),
]

HERE = os.path.dirname(os.path.abspath(__file__))
DEMOS_DIR = os.path.dirname(HERE)


def cap(name):
    return name[:1].upper() + name[1:]


def find_sim(root):
    # accept either the repo root or the sim/ dir itself
    for cand in (os.path.join(root, "sim"), root):
        if os.path.isdir(os.path.join(cand, "apps")) or \
                os.path.isfile(os.path.join(cand, "run.py")):
            return cand
    return None


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sim = find_sim(os.path.abspath(sys.argv[1]))
    if not sim:
        print("could not find the simulator (no sim/run.py or apps/) under %r"
              % sys.argv[1])
        sys.exit(1)
    appsdir = os.path.join(sim, "apps")
    os.makedirs(appsdir, exist_ok=True)

    for name, num, title in DEMOS:
        src = os.path.join(DEMOS_DIR, name, "app.py")
        if not os.path.isfile(src):
            print("skip %s (no app.py)" % name)
            continue
        cls = cap(name)
        dst = os.path.join(appsdir, cls)
        os.makedirs(dst, exist_ok=True)
        shutil.copyfile(src, os.path.join(dst, "app.py"))
        with open(os.path.join(dst, "__init__.py"), "w") as f:
            f.write("from .app import %s\n" % cls)
        with open(os.path.join(dst, "metadata.json"), "w") as f:
            json.dump({"callable": cls,
                       "name": "%02d %s" % (num, title),
                       "category": "Demos",
                       "hidden": False}, f, indent=2)
        print("installed %-9s -> %s" % (name, dst))

    print("\nDone. Now:")
    print("  cd %s" % sim)
    print("  cp config.py.default config.py   # number-key buttons, WASD = tilt")
    print("  pipenv install && pipenv run python run.py")
    print("Pick a 'Demos' entry from the launcher (buttons 1/2/3/8/9/0).")


if __name__ == "__main__":
    main()
