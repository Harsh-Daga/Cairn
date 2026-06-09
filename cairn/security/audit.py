"""Project security audit checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cairn.ingest.project_paths import resolve_git_root
from cairn.render.scrub import scrub_text
from cairn.security.auth import api_token_from_env

FindingLevel = Literal["info", "warn", "error"]

_INLINE_SECRET = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{12,}"
)


@dataclass(frozen=True)
class SecurityFinding:
    level: FindingLevel
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "code": self.code, "message": self.message}


def run_security_audit(project_root: Path) -> list[SecurityFinding]:
    """Run local security checks for a Cairn project."""
    root = resolve_git_root(project_root) or project_root.resolve()
    findings: list[SecurityFinding] = []

    findings.append(
        SecurityFinding(
            level="info",
            code="scrub.enabled",
            message="Bundle scrubbing is enabled via render/scrub.py for exports.",
        )
    )

    if api_token_from_env() is None:
        findings.append(
            SecurityFinding(
                level="warn",
                code="api.token.missing",
                message="Set CAIRN_API_TOKEN before exposing cairn api serve beyond localhost.",
            )
        )
    else:
        findings.append(
            SecurityFinding(
                level="info",
                code="api.token.set",
                message="CAIRN_API_TOKEN is configured for API bearer auth.",
            )
        )

    toml_path = root / "cairn.toml"
    if toml_path.is_file():
        toml_text = toml_path.read_text(encoding="utf-8")
        if _INLINE_SECRET.search(toml_text):
            findings.append(
                SecurityFinding(
                    level="error",
                    code="config.inline_secret",
                    message=(
                        "cairn.toml appears to contain inline secrets; "
                        "use environment variables."
                    ),
                )
            )

    env_path = root / ".env"
    if env_path.is_file():
        findings.append(
            SecurityFinding(
                level="warn",
                code="env.present",
                message=".env file exists; ensure it is gitignored and never exported in bundles.",
            )
        )

    sessions_dir = root / ".cairn" / "sessions"
    if sessions_dir.is_dir():
        mirrors = list(sessions_dir.glob("*.json"))[:5]
        unscrubbed = False
        for mirror in mirrors:
            raw = mirror.read_text(encoding="utf-8")
            if raw != scrub_text(raw):
                findings.append(
                    SecurityFinding(
                        level="warn",
                        code="session.unscrubbed",
                        message=(
                            f"Session mirror {mirror.name} contains patterns "
                            "that scrub would redact."
                        ),
                    )
                )
                unscrubbed = True
                break
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                findings.append(
                    SecurityFinding(
                        level="warn",
                        code="session.invalid_json",
                        message=f"Session mirror {mirror.name} is not valid JSON.",
                    )
                )
                break
        if mirrors and not unscrubbed:
            findings.append(
                SecurityFinding(
                    level="info",
                    code="session.mirrors",
                    message=(
                        f"Checked {len(mirrors)} session mirror(s); "
                        "no obvious secret patterns."
                    ),
                )
            )

    return findings
