"""Compile every file that ships to Razor Enhanced.

Run it under IronPython (``ipy tools/compile_check.py``) to catch syntax
Razor Enhanced's engine won't accept, including the Windows-only UI and
launcher that the unit tests can't import.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def shipped_files():
    yield os.path.join(ROOT, "run_jevanced.py")
    for folder, _, files in os.walk(os.path.join(ROOT, "jevanced")):
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def main():
    failures = 0
    count = 0
    for path in shipped_files():
        count += 1
        with open(path, "r") as handle:
            source = handle.read()
        try:
            compile(source, path, "exec")
        except SyntaxError as exc:
            failures += 1
            print("FAIL {0}: {1}".format(os.path.relpath(path, ROOT), exc))
    print("{0} files compiled, {1} failed ({2})".format(
        count, failures, sys.version.split("\n")[0]))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
