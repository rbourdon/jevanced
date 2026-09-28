"""Package jevanced for Razor Enhanced.

    python tools/build.py

Writes dist/jevanced-<version>.zip. Unzip it into Razor Enhanced's
Scripts folder so that run_jevanced.py and the jevanced folder sit side
by side, then add run_jevanced.py in the Scripting tab.
"""

import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def version():
    with open(os.path.join(ROOT, "jevanced", "__init__.py")) as handle:
        return re.search(r'__version__ = "([^"]+)"', handle.read()).group(1)


def files():
    yield "run_jevanced.py"
    yield "README.md"
    for folder, dirs, names in os.walk(os.path.join(ROOT, "jevanced")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(names):
            if name.endswith(".py"):
                yield os.path.relpath(os.path.join(folder, name), ROOT)


def build(out_dir=None):
    out_dir = out_dir or os.path.join(ROOT, "dist")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    target = os.path.join(out_dir, "jevanced-{0}.zip".format(version()))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in files():
            archive.write(os.path.join(ROOT, rel), rel.replace(os.sep, "/"))
    return target


if __name__ == "__main__":
    path = build(sys.argv[1] if len(sys.argv) > 1 else None)
    print("Built " + os.path.relpath(path, ROOT))
