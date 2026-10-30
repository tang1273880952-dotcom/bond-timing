"""Public artifact must include every referenced live website file, no raw caches."""
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_pages import build, PUBLIC


class BuildPagesTests(unittest.TestCase):
    def test_minimal_assets(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "pages"
            build(folder)
            self.assertTrue((folder / ".nojekyll").exists())
            for item in PUBLIC:
                self.assertTrue((folder / item).is_file(), item)
            self.assertFalse((folder / "scripts" / "update.py").exists())
            self.assertFalse((folder / "data" / "csi500_erp_daily.csv").exists())
            self.assertFalse((folder / "a-share").exists())
            self.assertFalse((folder / ".github").exists())
            self.assertFalse((folder / "tests").exists())
            self.assertFalse((folder / "site").exists())

    def test_never_overwrite_repo(self):
        from build_pages import ROOT
        with self.assertRaises(ValueError):
            build(ROOT)
        with self.assertRaises(ValueError):
            build(ROOT / "site")


if __name__ == "__main__":
    unittest.main()
