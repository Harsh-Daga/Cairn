"""cairn security — audit and encryption helpers."""

from __future__ import annotations

import argparse
import json
import os

from cairn.ingest.project_paths import resolve_git_root
from cairn.security.audit import run_security_audit
from cairn.security.encrypt import decrypt_bytes, encrypt_bytes


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project

    if args.security_command == "audit":
        findings = run_security_audit(root)
        if args.json:
            print(json.dumps([f.to_dict() for f in findings], indent=2, sort_keys=True))
            return 0
        if not findings:
            print("No findings.")
            return 0
        for finding in findings:
            print(f"[{finding.level}] {finding.code}: {finding.message}")
        return 1 if any(f.level == "error" for f in findings) else 0

    if args.security_command == "encrypt":
        password = args.password or os.environ.get("CAIRN_ENCRYPTION_KEY")
        if not password:
            print("Set --password or CAIRN_ENCRYPTION_KEY.")
            return 1
        src = args.input.resolve()
        dest = args.output.resolve()
        payload = encrypt_bytes(src.read_bytes(), password)
        dest.write_bytes(payload)
        print(f"Encrypted: {dest}")
        return 0

    if args.security_command == "decrypt":
        password = args.password or os.environ.get("CAIRN_ENCRYPTION_KEY")
        if not password:
            print("Set --password or CAIRN_ENCRYPTION_KEY.")
            return 1
        src = args.input.resolve()
        dest = args.output.resolve()
        dest.write_bytes(decrypt_bytes(src.read_bytes(), password))
        print(f"Decrypted: {dest}")
        return 0

    return 1
