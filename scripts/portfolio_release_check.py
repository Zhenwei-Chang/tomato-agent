"""Read-only pre-release checks for the curated portfolio surface."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tomato_fertigation_agent.portfolio_demo import load_index, load_scenario  # noqa: E402


PUBLIC_ROOTS = [
    ROOT / ".github",
    ROOT / "demo",
    ROOT / "docs" / "portfolio",
    ROOT / "docs" / "architecture",
    ROOT / "docs" / "evaluation",
    ROOT / "tomato_fertigation_agent",
    ROOT / "scripts",
    ROOT / "tests",
    ROOT / "configs",
]
PUBLIC_FILES = [
    ROOT / "README.md",
    ROOT / "README_EN.md",
    ROOT / "PUBLIC_RELEASE_MANIFEST.md",
    ROOT / "SECURITY.md",
    ROOT / ".gitattributes",
    ROOT / "pyproject.toml",
    ROOT / ".env.example",
    ROOT / ".gitignore",
    ROOT / "configs" / "agent.yaml",
]
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".html", ".css", ".js", ".svg", ""}
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret)\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
MD_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_PARTS = {"data", "outputs", "checkpoints", "models", "literature", "papers", "traces", "evals"}
FORBIDDEN_SUFFIXES = {".pt", ".pth", ".ckpt", ".onnx", ".joblib", ".pkl", ".pdf", ".parquet", ".xlsx", ".xls", ".jpg", ".jpeg", ".png", ".zip", ".7z"}
APPROVED_BINARY_ASSETS = {
    Path("docs/portfolio/screenshots/overview.png"),
    Path("docs/portfolio/screenshots/comprehensive-trace.png"),
    Path("docs/portfolio/screenshots/evidence-provenance.png"),
    Path("docs/portfolio/screenshots/benchmark.png"),
    Path("docs/portfolio/screenshots/mobile.png"),
}


def public_files() -> list[Path]:
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "--cached"], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        tracked = []
    files = [ROOT / item for item in tracked if (ROOT / item).is_file()]
    files.extend(p for p in PUBLIC_FILES if p.is_file())
    for root in PUBLIC_ROOTS:
        if root.is_dir():
            files.extend(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return sorted(set(files))


def check_fixtures(findings: list[str]) -> None:
    try:
        for entry in load_index()["scenarios"]:
            load_scenario(entry["id"])
    except Exception as exc:  # noqa: BLE001 - release gate must report all fixture failures
        findings.append(f"fixture validation: {type(exc).__name__}: {exc}")


def check_text(files: list[Path], findings: list[str]) -> None:
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if LOCAL_PATH.search(text):
            findings.append(f"local drive path: {rel}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"secret-like value: {rel}")
                break


def check_size(files: list[Path], findings: list[str]) -> None:
    for path in files:
        if path.stat().st_size > 1024 * 1024:
            findings.append(f"public candidate >1 MiB: {path.relative_to(ROOT).as_posix()}")


def check_inventory(files: list[Path], findings: list[str]) -> None:
    for path in files:
        rel = path.relative_to(ROOT)
        parts = {part.lower() for part in rel.parts[:-1]}
        if parts & FORBIDDEN_PARTS:
            findings.append(f"forbidden public directory: {rel.as_posix()}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES and rel not in APPROVED_BINARY_ASSETS:
            findings.append(f"forbidden public asset type: {rel.as_posix()}")
        if path.name == ".env":
            findings.append("real .env file is tracked")
        if path.is_symlink():
            findings.append(f"symbolic link requires manual review: {rel.as_posix()}")


def check_links(files: list[Path], findings: list[str]) -> None:
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for target in MD_LINK.findall(text):
            clean = target.strip().split("#", 1)[0]
            if not clean or clean.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / clean).resolve().exists():
                findings.append(f"broken Markdown link: {path.relative_to(ROOT).as_posix()} -> {target}")


def main() -> int:
    files = public_files()
    findings: list[str] = []
    check_fixtures(findings)
    check_text(files, findings)
    check_size(files, findings)
    check_inventory(files, findings)
    check_links(files, findings)
    if findings:
        print("Portfolio release check: FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"Portfolio release check: PASS ({len(files)} curated files inspected)")
    print("Reminder: Git history and third-party redistribution rights require separate owner review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
