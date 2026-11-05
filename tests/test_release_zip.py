"""Verify installable package paths, contents and exclusion of local files."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("release_zip", ROOT / "scripts/build_release_zip.py")
release_zip = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_zip)


class TestReleaseZip(unittest.TestCase):
    def test_real_package_matches_tracked_integration_without_repo_wrapper(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "integration.zip"
            count = release_zip.build_archive(ROOT, output)
            with ZipFile(output) as archive:
                names = set(archive.namelist())
                expected = {p.relative_to(release_zip.PREFIX).as_posix()
                            for p in release_zip.tracked_files(ROOT)} | {"LICENSE"}
                self.assertEqual(names, expected)
                self.assertEqual(count, len(expected))
                self.assertIn("manifest.json", names)
                self.assertIn("translations/de.json", names)
                self.assertNotIn("AGENTS.md", names)
                self.assertFalse(any(n.startswith("custom_components/") for n in names))
                self.assertIsNone(archive.testzip())
                for name in names:
                    self.assertEqual(archive.read(name), (ROOT / name if name == "LICENSE" else ROOT / release_zip.PREFIX / name).read_bytes())
            other = Path(folder) / "other.zip"
            release_zip.build_archive(ROOT, other)
            self.assertEqual(output.read_bytes(), other.read_bytes())

    def test_untracked_private_file_is_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / release_zip.PREFIX
            source.mkdir(parents=True)
            manifest = source / "manifest.json"
            manifest.write_text(json.dumps({"domain": release_zip.DOMAIN, "version": "1.0.0"}))
            (root / "LICENSE").write_text("Synthetic license")
            (source / "private.json").write_text('SECRET')
            with patch.object(release_zip, "tracked_files", return_value=[release_zip.PREFIX / "manifest.json"]):
                output = root / "release.zip"
                release_zip.build_archive(root, output)
            with ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"manifest.json", "LICENSE"})

    def test_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / release_zip.PREFIX
            source.mkdir(parents=True)
            (source / "manifest.json").write_text(json.dumps({"domain": release_zip.DOMAIN, "version": "1.0.0"}))
            (root / "private.txt").write_text('SECRET')
            (source / "leak.txt").symlink_to(root / "private.txt")
            with patch.object(release_zip, "tracked_files", return_value=[release_zip.PREFIX / "leak.txt"]):
                with self.assertRaises(ValueError):
                    release_zip.build_archive(root, root / "release.zip")
