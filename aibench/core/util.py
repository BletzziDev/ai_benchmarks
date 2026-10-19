"""Small, dependency-free helpers shared across the framework."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

import yaml

IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".hypothesis", ".mypy_cache", ".ruff_cache", "node_modules"}


class PathEscapeError(ValueError):
    pass


def safe_join(base: Path, rel: str | os.PathLike[str]) -> Path:
    """Join ``rel`` to ``base`` and refuse anything that resolves outside ``base``.

    Symlinks are resolved, so a link pointing outside the base is rejected as well.
    """
    base_r = Path(base).resolve()
    rel_s = str(rel)
    if rel_s.startswith("/workspace/"):
        rel_s = rel_s[len("/workspace/"):]
    elif rel_s == "/workspace":
        rel_s = "."
    candidate = (base_r / rel_s).resolve()
    if candidate != base_r and not candidate.is_relative_to(base_r):
        raise PathEscapeError(f"path escapes the allowed directory: {rel}")
    return candidate


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path, ignore_git: bool = True) -> Iterable[Path]:
    """Deterministically ordered regular files under root (no symlink following)."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_NAMES and not (ignore_git and d == ".git"))
        for name in sorted(filenames):
            if name.endswith(".pyc"):
                continue
            p = Path(dirpath) / name
            if p.is_symlink() or not p.is_file():
                continue
            yield p


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha256_file(p) for p in iter_files(root)}


def combined_hash(hashes: dict[str, str]) -> str:
    h = hashlib.sha256()
    for k in sorted(hashes):
        h.update(k.encode())
        h.update(b"\0")
        h.update(hashes[k].encode())
        h.update(b"\n")
    return h.hexdigest()


def copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree without following symlinks and skipping caches.

    Symlinks are dropped rather than copied: fixtures are data, and a planted symlink must not be
    able to make a later step read or write outside the sandbox.
    """
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_NAMES and not os.path.islink(os.path.join(dirpath, d))]
        rel = Path(dirpath).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in filenames:
            s = Path(dirpath) / name
            if s.is_symlink() or name.endswith(".pyc"):
                continue
            shutil.copy2(s, dst / rel / name)


def dir_size_bytes(root: Path) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                if not os.path.islink(p):
                    total += os.path.getsize(p)
            except OSError:
                pass
    return total


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj


def write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(to_jsonable(obj), indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def glob_match(path: str, patterns: Iterable[str]) -> bool:
    """fnmatch with '**' support; patterns are matched against POSIX relative paths."""
    for pat in patterns:
        if fnmatch.fnmatch(path, pat):
            return True
        if pat.endswith("/**") and (path == pat[:-3] or path.startswith(pat[:-2])):
            return True
        if "**/" in pat and fnmatch.fnmatch(path, pat.replace("**/", "")):
            return True
    return False


def truncate_middle(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = limit * 2 // 3
    tail = limit - head
    omitted = len(text) - limit
    return f"{text[:head]}\n... [{omitted} characters omitted by harness] ...\n{text[-tail:]}", True


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:60] or "x"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars/4). Used only for harness-side context budgeting, never reported
    as provider usage."""
    return max(1, len(text) // 4)
