"""Recoverable, write-set transactions for the local project store.

The project directory is a trusted local store, not an agent security sandbox.
A failed restore MUST retain its journal; recovery is retried under the same lock.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from .utils import atomic_write, canonical_json, ensure_relative_path, sync_directory

_locks: dict[str, threading.RLock] = {}
_active: dict[str, list[dict]] = {}
_poisoned: set[str] = set()


def _contained(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Invalid recovery path")
    path = root / ensure_relative_path(relative)
    if path == root or not path.resolve().is_relative_to(root):
        raise ValueError("Recovery path escapes project")
    if path.is_symlink() or path.is_dir():
        raise ValueError("Recovery requires regular file paths")
    return path


def _validate_journal(root: Path, journal: dict, observed: Path | None = None) -> list:
    """Check the entire write set before touching ANY target, including cleanup."""
    if (not isinstance(journal, dict)
            or set(journal) != {"id", "created_ns", "entries", "pending_path"}
            or not isinstance(journal["id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", journal["id"]) is None
            or type(journal["created_ns"]) is not int or journal["created_ns"] < 0
            or not isinstance(journal["entries"], list)):
        raise ValueError("Invalid transaction journal")
    pending = f"runtime/transactions/{journal['id']}.pending.json"
    if journal["pending_path"] != pending or (observed is not None and observed != root / pending):
        raise ValueError("Transaction journal identity/path mismatch")
    _contained(root, pending)
    folder = root / "runtime/transactions"
    seen, prepared = set(), []
    for index, entry in enumerate(journal["entries"]):
        if not isinstance(entry, dict) or set(entry) != {"path", "backup"}:
            raise ValueError("Invalid transaction write-set entry")
        target = _contained(root, entry["path"])
        canonical = target.resolve()
        if canonical in seen or canonical.is_relative_to(folder):
            raise ValueError("Duplicate target or journal self-modification")
        seen.add(canonical)
        backup = None
        if entry["backup"] is not None:
            expected = f"runtime/transactions/{journal['id']}/{index}.backup"
            if entry["backup"] != expected:
                raise ValueError("Recovery backup does not belong to this transaction entry")
            backup = _contained(root, expected)
            if backup.resolve() != backup or not backup.is_file():
                raise ValueError("Recovery backup missing or redirected")
        prepared.append((target, backup))
    return prepared


def _unlink_durable(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    sync_directory(path.parent)


def _restore(root: Path, journal: dict) -> None:
    for target, backup in reversed(_validate_journal(root, journal)):
        if backup is None:
            _unlink_durable(target)
        else:
            atomic_write(target, backup.read_bytes())


def before_write(root: Path, target: Path) -> None:
    root = root.resolve()
    key = str(root)
    if key in _poisoned:
        raise ValueError("Transaction recovery required before further writes")
    try:
        relative = target.relative_to(root).as_posix()
        for journal in _active.get(key, []):
            _contained(root, relative)
            if target.resolve().is_relative_to(root / "runtime/transactions"):
                raise ValueError("A transaction cannot modify its own journal")
            if any(entry["path"] == relative for entry in journal["entries"]):
                continue
            backup = None
            if target.exists():
                backup = f"runtime/transactions/{journal['id']}/{len(journal['entries'])}.backup"
                saved = root / backup
                saved.parent.mkdir(parents=True, exist_ok=True)
                # Stream the backup: production media must not be loaded just to journal it.
                shutil.copyfile(target, saved)
                with saved.open("rb") as stream:
                    os.fsync(stream.fileno())
                sync_directory(saved.parent)
                sync_directory(saved.parent.parent)
            journal["entries"].append({"path": relative, "backup": backup})
            atomic_write(root / journal["pending_path"], canonical_json(journal).encode())
    except BaseException:
        if _active.get(key):
            _poisoned.add(key)
        raise


def _recover_pending(root: Path, folder: Path) -> None:
    pending = []
    for path in folder.glob("*.pending.json"):
        if path.is_symlink():
            raise ValueError("Transaction journal cannot be a symbolic link")
        journal = json.loads(path.read_text(encoding="utf-8"))
        _validate_journal(root, journal, path)
        pending.append((path, journal))
    # A nested savepoint is restored before its parent. A corrupt journal blocks
    # all recovery rather than permitting a partially trusted cleanup sequence.
    for path, journal in sorted(pending, key=lambda row: row[1]["created_ns"], reverse=True):
        _restore(root, journal)
        _unlink_durable(path)


@contextmanager
def transaction(root: Path, *, savepoint: bool = False):
    root = root.resolve()
    key = str(root)
    lock = _locks.setdefault(key, threading.RLock())
    with lock:
        if key in _poisoned:
            raise ValueError("Transaction recovery required before continuing")
        if _active.get(key) and not savepoint:
            yield
            return
        folder = root / "runtime/transactions"
        if folder.resolve() != folder:
            raise ValueError("Transaction directory cannot be redirected")
        folder.mkdir(parents=True, exist_ok=True)
        handle = None
        if not _active.get(key):
            lock_path = folder / ".lock"
            if lock_path.is_symlink():
                raise ValueError("Transaction lock cannot be a symbolic link")
            handle = lock_path.open("a+b")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX)
                _recover_pending(root, folder)
            except BaseException:
                handle.close()
                raise
        identifier = uuid.uuid4().hex
        parents = _active.get(key, [])
        created_ns = max(time.time_ns(), parents[-1]["created_ns"] + 1 if parents else 0)
        journal = {"id": identifier, "created_ns": created_ns, "entries": [],
                   "pending_path": f"runtime/transactions/{identifier}.pending.json"}
        _active.setdefault(key, []).append(journal)
        try:
            try:
                yield
                if key in _poisoned:
                    raise ValueError("Nested recovery failed; cannot commit the parent")
            except BaseException:
                # Do not restore a parent ahead of an unresolved child. Leave both
                # journals for ordered recovery on the next outer transaction.
                if key not in _poisoned:
                    try:
                        _restore(root, journal)
                        _unlink_durable(root / journal["pending_path"])
                    except BaseException:
                        _poisoned.add(key)
                        raise
                raise
            else:
                try:
                    _unlink_durable(root / journal["pending_path"])
                except BaseException:
                    _poisoned.add(key)
                    raise
        finally:
            _active[key].pop()
            if handle is not None:
                try:
                    fcntl.flock(handle, fcntl.LOCK_UN)
                finally:
                    handle.close()
                    _poisoned.discard(key)


def project_transaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.store.transaction():
            return method(self, *args, **kwargs)
    return wrapped
