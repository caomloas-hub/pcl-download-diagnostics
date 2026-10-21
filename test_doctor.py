import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pcl_download_doctor as doctor


class FakeRegistry:
    def __init__(self, state):
        self.state = state.copy()

    def read(self):
        return self.state.copy()

    def write(self, state):
        self.state = state.copy()


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / "PCL.exe"
        self.exe.write_bytes(b"test fixture, not a launcher")
        self.digest = doctor.fingerprint(self.exe)
        self.notice = self.root / "Notice.json"
        self.notice.write_text(json.dumps([{
            "id": 230, "title": "悲报",
            "description": "为遵守相关法律法规，PCL 不再提供 MC 下载功能",
        }]), encoding="utf-8")
        self.registry = FakeRegistry({"exists": False, "value": None, "kind": None})

    def run_repair(self):
        return doctor.repair(self.exe, self.notice, self.root / "backup",
                             self.registry, lambda _: None)

    def test_unknown_binary_refused(self):
        with self.assertRaises(ValueError):
            self.run_repair()
        self.assertFalse(self.registry.read()["exists"])

    def test_repair_restore_and_executable_unchanged(self):
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            result = self.run_repair()
            self.assertTrue(result["changed"])
            self.assertEqual(doctor.counter(self.registry.read()), 230)
            doctor.restore(result["backup"], self.exe, self.registry, lambda _: None)
        self.assertFalse(self.registry.read()["exists"])
        self.assertEqual(self.digest, doctor.fingerprint(self.exe))

    def test_preserve_existing_type_on_restore(self):
        original = {"exists": True, "value": 229, "kind": 4}
        self.registry.write(original)
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            result = self.run_repair()
            doctor.restore(result["backup"], self.exe, self.registry, lambda _: None)
        self.assertEqual(self.registry.read(), original)

    def test_already_seen_and_newer_notice_unchanged(self):
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            for value in ("230", "999"):
                state = {"exists": True, "value": value, "kind": 1}
                self.registry.write(state)
                self.assertFalse(self.run_repair()["changed"])
                self.assertEqual(self.registry.read(), state)
        self.assertFalse((self.root / "backup").exists())

    def test_restore_refuses_newer_state(self):
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            result = self.run_repair()
            self.registry.write({"exists": True, "value": "231", "kind": 1})
            with self.assertRaises(RuntimeError):
                doctor.restore(result["backup"], self.exe, self.registry, lambda _: None)

    def test_wrong_notice_refused(self):
        self.notice.write_text('[{"id":231}]', encoding="utf-8")
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            with self.assertRaises(ValueError):
                self.run_repair()

    def test_running_launcher_refused(self):
        def running(_):
            raise RuntimeError("Running")
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            with self.assertRaises(RuntimeError):
                doctor.repair(self.exe, self.notice, self.root / "backup",
                              self.registry, running)
        self.assertFalse((self.root / "backup").exists())

    def test_malformed_backup_refused(self):
        path = self.root / "invalid.json"
        for data in ([], None, {}):
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                doctor.restore(path, self.exe, self.registry, lambda _: None)

    def test_tampered_backup_refused(self):
        with patch.dict(doctor.SUPPORTED, {self.digest: "test"}):
            result = self.run_repair()
            path = Path(result["backup"])
            data = json.loads(path.read_text())
            data["registry_value"] = "UnrelatedSetting"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                doctor.restore(path, self.exe, self.registry, lambda _: None)


if __name__ == "__main__":
    unittest.main()
