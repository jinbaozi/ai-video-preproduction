"""Recoverable, write-set transactions for the local project store."""
from __future__ import annotations

import fcntl
import json
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from .utils import atomic_write, canonical_json, ensure_relative_path

_locks: dict[str, threading.RLock] = {}
_active: dict[str, list[dict]] = {}


def _restore(root: Path, journal: dict) -> None:
    for entry in reversed(journal["entries"]):
        target = root / ensure_relative_path(entry["path"])
        if not target.resolve().is_relative_to(root):
            raise ValueError('Recovery path escapes project through a symbolic link')
        if entry["backup"] is None:
            target.unlink(missing_ok=True)
        else:
            backup = root / ensure_relative_path(entry["backup"])
            if not backup.resolve().is_relative_to(root / 'runtime/transactions'):
                raise ValueError('Recovery backup is outside the transaction journal')
            atomic_write(target, backup.read_bytes())


def before_write(root: Path, target: Path) -> None:
    relative = target.relative_to(root).as_posix()
    for journal in _active.get(str(root), []):
        if any(entry["path"] == relative for entry in journal["entries"]):
            continue
        backup = None
        if target.exists():
            backup = f"runtime/transactions/{journal['id']}/{len(journal['entries'])}.backup"
            saved = root / backup
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, saved)
        journal["entries"].append({"path": relative, "backup": backup})
        atomic_write(root / journal["pending_path"], canonical_json(journal).encode())


@contextmanager
def transaction(root: Path, *, savepoint: bool = False):
    root = root.resolve()
    key = str(root)
    lock = _locks.setdefault(key, threading.RLock())
    with lock:
        if _active.get(key) and not savepoint:
            yield
            return
        folder = root / "runtime/transactions"
        folder.mkdir(parents=True, exist_ok=True)
        handle = None
        if not _active.get(key):
            handle = (folder / ".lock").open("a+b")
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                pending = [json.loads(path.read_text()) for path in folder.glob("*.pending.json")]
                for old in sorted(pending, key=lambda item: item["created_ns"], reverse=True):
                    _restore(root, old)
                    (root / ensure_relative_path(old["pending_path"])).unlink()
            except BaseException:
                handle.close()
                raise
        identifier = uuid.uuid4().hex
        journal = {"id": identifier, "created_ns": time.time_ns(), "entries": [],
                   "pending_path": f"runtime/transactions/{identifier}.pending.json"}
        _active.setdefault(key, []).append(journal)
        try:
            yield
        except BaseException:
            _restore(root, journal)
            raise
        finally:
            _active[key].pop()
            (root / journal["pending_path"]).unlink(missing_ok=True)
            if handle is not None:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()


def project_transaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.store.transaction():
            return method(self, *args, **kwargs)
    return wrapped
