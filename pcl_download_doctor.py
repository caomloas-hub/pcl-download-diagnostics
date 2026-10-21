#!/usr/bin/env python3
"""Diagnose the PCL 230 notice; never patch a launcher or change authentication."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import datetime, timezone

NOTICE_ID = 230
SUPPORTED = {
    "77fbc26a13abf725dbd26038cba023224c2ce5518f3ee9c4608acb2274d753f0":
        "PCL 2.14.0.0 (verified Windows binary)",
}
REG_PATH = r"Software\PCL"
REG_NAME = "HintNotice"


def fingerprint(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_notice(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("Notice cache must be a JSON array.")
    return any(
        isinstance(item, dict)
        and item.get("id") == NOTICE_ID
        and item.get("title") == "悲报"
        and "PCL 不再提供 MC 下载功能" in str(item.get("description", ""))
        for item in data
    )


class Registry:
    def __init__(self):
        import winreg
        self.reg = winreg

    def read(self):
        try:
            with self.reg.OpenKey(self.reg.HKEY_CURRENT_USER, REG_PATH) as key:
                value, kind = self.reg.QueryValueEx(key, REG_NAME)
            if kind not in (self.reg.REG_SZ, self.reg.REG_DWORD):
                raise ValueError("Unsupported HintNotice registry type.")
            return {"exists": True, "value": value, "kind": kind}
        except FileNotFoundError:
            return {"exists": False, "value": None, "kind": None}

    def write(self, state):
        if state["exists"]:
            with self.reg.CreateKey(self.reg.HKEY_CURRENT_USER, REG_PATH) as key:
                self.reg.SetValueEx(key, REG_NAME, 0, state["kind"], state["value"])
        else:
            try:
                with self.reg.OpenKey(self.reg.HKEY_CURRENT_USER, REG_PATH,
                                      0, self.reg.KEY_SET_VALUE) as key:
                    self.reg.DeleteValue(key, REG_NAME)
            except FileNotFoundError:
                pass


def counter(state):
    value = int(state["value"]) if state["exists"] else 0
    if value < 0:
        raise ValueError("Invalid negative notice counter.")
    return value


def ensure_closed(executable):
    # No shell interpolation and no process termination.
    output = subprocess.run(
        ["tasklist.exe", "/FO", "CSV", "/NH"], check=True,
        capture_output=True, text=True, errors="replace",
    ).stdout
    for row in csv.reader(io.StringIO(output)):
        if row and row[0].casefold() == Path(executable).name.casefold():
            raise RuntimeError("Close PCL normally (Alt+F4), then retry. "
                               "This tool will not kill downloads or games.")


def repair(executable, notice, backup_dir, registry, closed_check=ensure_closed):
    digest = fingerprint(executable)
    if digest not in SUPPORTED:
        raise ValueError("Unverified launcher: refusing to modify settings. "
                         "This utility cannot restore removed download code.")
    if not validate_notice(notice):
        raise ValueError("The known notice 230 was not found; no changes made.")
    before = registry.read()
    if counter(before) >= NOTICE_ID:
        return {"changed": False, "message": "Notice already acknowledged. "
                "Close PCL normally and reopen it; no registry changes needed."}
    closed_check(executable)
    # PCL's own persisted acknowledgement; this does not disable future notices.
    after = {"exists": True, "value": str(NOTICE_ID), "kind": 1}
    folder = Path(backup_dir)
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / ("notice-" + uuid.uuid4().hex + ".json")
    document = {
        "schema": 1, "registry_key": REG_PATH, "registry_value": REG_NAME,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "executable_sha256": digest, "before": before, "after": after,
    }
    with backup.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    # Refuse if another process changed the state while the backup was written.
    if registry.read() != before:
        raise RuntimeError("Notice state changed concurrently; no changes made.")
    try:
        registry.write(after)
        if registry.read() != after:
            raise RuntimeError("Registry verification failed.")
    except Exception:
        registry.write(before)
        raise
    return {"changed": True, "backup": str(backup),
            "message": "Notice 230 acknowledged. Reopen PCL and test a download."}


def validate_state(state):
    if not isinstance(state, dict) or type(state.get("exists")) is not bool:
        raise ValueError("Invalid backup state.")
    if state["exists"]:
        if state.get("kind") == 1 and not isinstance(state.get("value"), str):
            raise ValueError("Invalid string registry value.")
        if state.get("kind") == 4 and type(state.get("value")) is not int:
            raise ValueError("Invalid DWORD registry value.")
        if state.get("kind") not in (1, 4):
            raise ValueError("Invalid registry type.")
        counter(state)
    elif state.get("value") is not None or state.get("kind") is not None:
        raise ValueError("Invalid absent registry value.")


def restore(backup, executable, registry, closed_check=ensure_closed):
    data = json.loads(Path(backup).read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("schema") != 1 or data.get("registry_key") != REG_PATH
            or data.get("registry_value") != REG_NAME
            or data.get("executable_sha256") not in SUPPORTED
            or fingerprint(executable) != data["executable_sha256"]
            or data.get("after") != {"exists": True, "value": "230", "kind": 1}):
        raise ValueError("Unsupported backup or launcher.")
    validate_state(data.get("before"))
    if counter(data["before"]) >= NOTICE_ID:
        raise ValueError("Invalid original notice counter.")
    closed_check(executable)
    if registry.read() != data["after"]:
        raise RuntimeError("State has changed since repair; refusing to overwrite it.")
    registry.write(data["before"])
    if registry.read() != data["before"]:
        raise RuntimeError("Restore verification failed.")
    return {"restored": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["inspect", "repair", "restore"])
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--notice", type=Path, default=Path(
        os.environ.get("TEMP", ".")) / "PCL" / "Cache" / "Notice.json")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--backup-dir", type=Path, default=Path(
        os.environ.get("LOCALAPPDATA", ".")) / "PCLDownloadDoctor" / "backups")
    args = parser.parse_args()
    try:
        if sys.platform != "win32":
            raise RuntimeError("The CLI supports Windows only.")
        registry = Registry()
        if args.mode == "inspect":
            digest = fingerprint(args.exe)
            try:
                known_notice = validate_notice(args.notice)
            except (OSError, ValueError):
                known_notice = False
            result = {
                "sha256": digest, "verified_build": SUPPORTED.get(digest),
                "known_notice_230": known_notice,
                "notice_counter": counter(registry.read()),
                "hint": "Try closing and reopening PCL first. "
                        "Unknown builds are diagnostic-only.",
            }
        elif args.mode == "repair":
            result = repair(args.exe, args.notice, args.backup_dir, registry)
        else:
            if not args.backup:
                parser.error("restore requires --backup")
            result = restore(args.backup, args.exe, registry)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
