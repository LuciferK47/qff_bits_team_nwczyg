"""Build the lean submission archive: source, locked requirements, saved data, figures, reports. Never the virtualenv,
caches, credentials or local paths."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INCLUDE_FILES = ["README.md", "pyproject.toml", "requirements.in", "requirements.lock", ".env.example", ".gitignore",
                 "results.csv", "resources.csv", "metadata.json"]
INCLUDE_DIRS = ["src", "tests", "configs", "scripts", "reports", "figures", "raw", "prereg", "logs"]
EXCLUDE_PARTS = {".venv", "__pycache__", ".pytest_cache", "dist", ".git", ".ipynb_checkpoints"}
EXCLUDE_SUFFIX = (".pyc", ".tmp", ".pkl")
TEXT_SUFFIX = (".log", ".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".sh", ".example", ".lock", ".in", ".toml")
SECRET_PATTERNS = [
    (re.compile(r"(?i)QISKIT_IBM_TOKEN[ \t]*=[ \t]*\S+"), "QISKIT_IBM_TOKEN assignment"),
    (re.compile(r"(?i)[\"']?(api[_-]?key|token|apikey)[\"']?[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9_\-]{16,}"), "credential-like value"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{16,}"), "bearer token"),
]
HOME_RE = re.compile(r"/home/[\w\-.]+(?:/[^\s'\"<>:,)\]]*)?")


def sanitize(text: str) -> str:
    """Replace local absolute paths so logs/records are shareable."""
    return HOME_RE.sub("<local-path>", text)


def scan(text: str) -> list[str]:
    return [name for pat, name in SECRET_PATTERNS if pat.search(text)] + (["local home path"] if HOME_RE.search(text) else [])


def collect(root: Path = ROOT) -> list[Path]:
    files = []
    for name in INCLUDE_FILES:
        if (root / name).exists():
            files.append(root / name)
    for d in INCLUDE_DIRS:
        for f in sorted((root / d).rglob("*")):
            if f.is_file() and not (set(f.relative_to(root).parts) & EXCLUDE_PARTS) and not f.name.endswith(EXCLUDE_SUFFIX) \
                    and ".egg-info" not in str(f):
                files.append(f)
    return files


def build(root: Path = ROOT, out_dir: Path | None = None, team_name: str | None = None) -> tuple[Path, dict]:
    team = team_name or yaml.safe_load((root / "configs/team.yaml").read_text())["team_name"]
    out_dir = out_dir or root / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{team}.zip"
    problems, n_sanitized = [], 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in collect(root):
            rel = f.relative_to(root).as_posix()
            if f.suffix in TEXT_SUFFIX or f.name in (".env.example", ".gitignore"):
                text = f.read_text(errors="replace")
                clean = sanitize(text) if f.suffix in (".log", ".json", ".csv", ".txt") or f.name.endswith(".md") else text
                n_sanitized += clean != text
                bad = scan(clean) if f.suffix not in (".py",) else [p for p in scan(text) if p != "local home path"]
                if bad:
                    problems.append(f"{rel}: {', '.join(bad)}")
                z.writestr(rel, clean)
            else:
                z.write(f, rel)
    if problems:
        target.unlink()
        raise RuntimeError("refusing to build the archive; found:\n  " + "\n  ".join(problems))
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
    required = ["README.md", "requirements.lock", "results.csv", "resources.csv", "metadata.json"]
    missing = [r for r in required if r not in names] + [d + "/" for d in ("src", "raw") if not any(n.startswith(d + "/") for n in names)]
    return target, dict(files=len(names), bytes=target.stat().st_size, sanitized_files=int(n_sanitized), missing_required=missing,
                        forbidden_present=[n for n in names if set(Path(n).parts) & EXCLUDE_PARTS or n == ".env"])
