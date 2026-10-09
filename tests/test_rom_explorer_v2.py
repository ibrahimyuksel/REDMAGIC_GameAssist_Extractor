import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rom_explorer_v2 import Explorer, ExplorerError, is_match, patterns_from, safe_path, source_urls, parse_partitions

class ROMExplorerTests(unittest.TestCase):
    def test_patterns(self):
        self.assertTrue(is_match("system/app/GameAssist15_5.apk", ["GameAssist*.apk"]))
        self.assertFalse(is_match("system/app/notes.txt", ["*.apk"]))

    def test_path_safety(self):
        for path in ("../secret", "/root/x", "a/../secret", r"a\bad", "C:/bad"):
            self.assertIsNone(safe_path(path))
        self.assertEqual(safe_path("system/app/tool.apk"), "system/app/tool.apk")
        with self.assertRaises(ExplorerError):
            patterns_from("../secret")

    def test_split_urls(self):
        self.assertEqual(source_urls("https://example.com/rom.zip.00", 3), [
            "https://example.com/rom.zip.00", "https://example.com/rom.zip.01",
            "https://example.com/rom.zip.02"])
        self.assertEqual(parse_partitions("all"), ["system","system_ext","product","vendor","odm"])

    def test_zip_selective(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "rom.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("app/Tool.apk", b"APKTEST")
                z.writestr("app/Other.txt", b"other")
                z.writestr("../unsafe.apk", b"BAD")
            ctx = Explorer(root/"output", root/"work", "extract", ["Tool.apk"], [], 10)
            ctx.process_zip(archive)
            ctx.finish("https://example.com/rom.zip", "abc")
            self.assertEqual((root/"output/selected/archive/app/Tool.apk").read_bytes(), b"APKTEST")
            self.assertEqual(len(ctx.results), 1)

    def test_tar_selective(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "rom.tar.gz"
            with tarfile.open(archive, "w:gz") as tf:
                data = b"hello"
                entry = tarfile.TarInfo("system/app/Test.apk")
                entry.size = len(data)
                tf.addfile(entry, io.BytesIO(data))
            ctx = Explorer(root/"output", root/"work", "extract", ["*.apk"], [], 10)
            ctx.process_tar(archive)
            ctx.finish("https://example.com/rom.tar.gz", "abc")
            self.assertEqual((root/"output/selected/archive/system/app/Test.apk").read_bytes(), b"hello")

    def test_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root/"rom.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("app/Tool.apk", b"hello")
            ctx = Explorer(root/"output", root/"work", "list", [], [], 10)
            ctx.process_zip(archive)
            ctx.finish("https://example.com/rom.zip", "abc")
            self.assertIn("app/Tool.apk", (root/"output/FILE_LIST.csv").read_text())
            self.assertEqual(ctx.results, [])

if __name__ == "__main__":
    unittest.main()
