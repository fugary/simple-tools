import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r = load("runner", "run.py")
d = load("selection", "detector.py")


class AutomationTests(unittest.TestCase):
    def test_four_platform_assets(self):
        names = ["mihomo-windows-amd64-compatible-v1.2.zip", "mihomo-windows-arm64-v1.2.zip",
                 "mihomo-darwin-amd64-compatible-v1.2.gz", "mihomo-darwin-arm64-v1.2.gz",
                 "mihomo-darwin-arm64-go120-v1.2.gz"]
        release = {"assets": [{"name": name, "digest": "sha256:" + "0" * 64,
                    "browser_download_url": "https://github.com/MetaCubeX/mihomo/releases/download/v1.2/" + name} for name in names]}
        for system, machine, index in [("Windows", "AMD64", 0), ("Windows", "ARM64", 1),
                                        ("Darwin", "x86_64", 2), ("Darwin", "arm64", 3)]:
            self.assertEqual(r.choose_asset(release, system, machine)["name"], names[index])

    def test_missing_digest_and_unofficial_origin_rejected(self):
        asset = {"name": "mihomo-darwin-arm64-v1.2.gz", "digest": None,
                 "browser_download_url": "https://evil.invalid/core"}
        with self.assertRaises(r.SetupError):
            r.choose_asset({"assets": [asset]}, "Darwin", "arm64")
        asset["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(r.SetupError):
            r.choose_asset({"assets": [asset]}, "Darwin", "arm64")

    def test_checksum_precedes_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, target = Path(folder) / "a", Path(folder) / "core"
            archive.write_bytes(b"corrupt")
            with self.assertRaises(r.SetupError):
                r.extract_verified(archive, {"name": "core.zip", "digest": "sha256:" + "0" * 64}, target)
            self.assertFalse(target.exists())

    def test_zip_and_gzip_extract_only_binary(self):
        with tempfile.TemporaryDirectory() as folder:
            archive, target = Path(folder) / "a", Path(folder) / "core"
            for suffix in ("zip", "gz"):
                if suffix == "zip":
                    with zipfile.ZipFile(archive, "w") as package:
                        package.writestr("../../untrusted-location.exe", b"binary")
                else:
                    archive.write_bytes(gzip.compress(b"binary"))
                digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
                r.extract_verified(archive, {"name": "core." + suffix, "digest": digest}, target)
                self.assertEqual(target.read_bytes(), b"binary")

    def test_cached_kernel_does_not_download(self):
        with patch.object(r.subprocess, "run", return_value=Mock(returncode=0, stdout=b'{"path":"cached-core"}')), \
             patch.object(r, "download") as download:
            self.assertEqual(r.ensure_kernel("python"), "cached-core")
            download.assert_not_called()

    def test_automation_forwards_filter_and_download_route(self):
        with patch.object(r, "ensure_python", return_value=Path("python")), \
             patch.object(r, "ensure_kernel", return_value="core"), \
             patch.object(r.shutil, "which", return_value="curl"), \
             patch.object(r.subprocess, "call", return_value=0) as call:
            self.assertEqual(r.main(["--input", "nodes.yaml", "--region", "US", "--limit", "3"]), 0)
            command = call.call_args.args[0]
            self.assertIn("--allow-direct-download", command)
            self.assertEqual(command[command.index("--region") + 1], "US")
            self.assertEqual(command[command.index("--limit") + 1], "3")

    def test_download_falls_back_without_dropping_explicit_proxy(self):
        opener = Mock()
        opener.open.side_effect = OSError("network failure")
        with patch.object(r.urllib.request, "build_opener", return_value=opener), \
             patch.object(r.shutil, "which", return_value="curl"), \
             patch.object(r, "run_checked") as run:
            r.download("https://github.com/file", Path("destination"), "http://127.0.0.1:7890")
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--proxy") + 1], "http://127.0.0.1:7890")

    def test_explicit_no_direct_download_does_not_provision_without_proxy(self):
        with patch.object(r, "ensure_python") as provision:
            self.assertEqual(r.main(["--no-direct-download", "--setup-only"]), 2)
            provision.assert_not_called()

    def test_us_filter_before_limit_and_no_false_substring_matches(self):
        nodes = [{"name": name} for name in ["日本01", "Australia", "Russia", "美国01", "US-02", "🇺🇸 03", "洛杉矶04"]]
        self.assertEqual([n["name"] for n in d.select_nodes(nodes, region="US", limit=2)], ["美国01", "US-02"])
        self.assertEqual(len(d.select_nodes(nodes, region="US")), 4)

    def test_filter_intersection_and_exact_names(self):
        nodes = [{"name": name} for name in ["US IPLC 01", "US IPLC 过期", "JP IPLC 01", "US普通"]]
        self.assertEqual(d.select_nodes(nodes, region="US", include="iplc", exclude="过期"), [nodes[0]])
        self.assertEqual(d.select_nodes(nodes, names=["US普通"]), [nodes[3]])

    def test_no_match_never_widens_scope(self):
        with self.assertRaises(d.DetectorError):
            d.select_nodes([{"name": "日本01"}], region="US")
        with self.assertRaises(d.DetectorError):
            d.select_nodes([{"name": "US01"}], include="[")


if __name__ == "__main__":
    unittest.main()
