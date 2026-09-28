import shutil
import tempfile
import unittest
import zipfile

from tools import build


class BuildTest(unittest.TestCase):
    def test_zip_has_launcher_and_package_only(self):
        out = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(build.build(out)) as archive:
                names = archive.namelist()
        finally:
            shutil.rmtree(out)
        self.assertIn("run_jevanced.py", names)
        self.assertIn("jevanced/razor/adapter.py", names)
        self.assertIn("jevanced/ui/winforms.py", names)
        self.assertFalse(any(n.startswith("tests/") for n in names))
        self.assertFalse(any("__pycache__" in n for n in names))
        self.assertTrue(all(n.endswith((".py", ".md")) for n in names))


if __name__ == "__main__":
    unittest.main()
