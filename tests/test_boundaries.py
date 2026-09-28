"""Guards the project's structural rules."""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A bare Razor Enhanced global, not an attribute such as ``combo.Items.Add``.
RAZOR_NAMES = re.compile(r"(?<![.\w])(Player|Mobiles|Items|Target|Spells|Journal|Misc|Gumps|Statics)\.[A-Z]")
ALLOWED = {
    os.path.join("jevanced", "razor", "adapter.py"),
}


class BoundaryTest(unittest.TestCase):
    def test_only_the_adapter_calls_razor_enhanced(self):
        offenders = []
        for folder, _, files in os.walk(os.path.join(ROOT, "jevanced")):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, ROOT)
                if rel in ALLOWED:
                    continue
                with open(path) as handle:
                    for number, line in enumerate(handle, 1):
                        if RAZOR_NAMES.search(line.split("#")[0]):
                            offenders.append("{0}:{1}".format(rel, number))
        self.assertEqual(offenders, [])

    def test_adapter_reads_razor_objects_without_getattr(self):
        # In Razor Enhanced 1.0, Player.Hits works but getattr(Player, "Hits")
        # raises, so the adapter must use plain attribute access.
        with open(os.path.join(ROOT, "jevanced", "razor", "adapter.py")) as handle:
            self.assertFalse("getattr(" in handle.read(), "adapter.py uses getattr")

    def test_no_dataclasses_in_shipped_code(self):
        # Razor Enhanced's IronPython 3.4 has no dataclasses module.
        for folder, _, files in os.walk(os.path.join(ROOT, "jevanced")):
            for name in files:
                if name.endswith(".py"):
                    with open(os.path.join(folder, name)) as handle:
                        self.assertNotIn("dataclasses", handle.read(), name)


if __name__ == "__main__":
    unittest.main()
