#!/usr/bin/env python3
"""Serialized and atomic file write helpers for policy/ops scripts."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_AUDIT_FILE_ENV = "OPENCLAW_FILE_WRITE_AUDIT"
_AUDIT_DISABLED_ENV = "OPENCLAW_FILE_WRITE_AUDIT_DISABLED"
_DEFAULT_AUDIT_REL_PATH = Path("runtime") / "file_write_audit.jsonl"


class FileWriteError(RuntimeError):
    """Raised when a guarded file write fails."""

    def __init__(self, code: str, path: Path, detail: str = "") -> None:
        self.code = str(code).strip() or "write_failed"
        self.path = Path(path)
        self.detail = str(detail or "").strip()
        message = f"{self.code}:{self.path}"
        if self.detail:
            message = f"{message}:{self.detail}"
        super().__init__(message)


def _resolve_path(path: str | Path) -> Path:
    try:
        return Path(path).expanduser().resolve()
    except Exception as exc:
        raise FileWriteError("invalid_path", Path(path), str(exc)) from exc


def _assert_write_scope(path: Path, allowed_roots: Iterable[str | Path] | None) -> None:
    if not allowed_roots:
        return
    normalized_roots: list[Path] = []
    for root in allowed_roots:
        try:
            normalized_roots.append(Path(root).expanduser().resolve())
        except Exception:
            continue
    if not normalized_roots:
        return
    for root in normalized_roots:
        try:
            path.relative_to(root)
            return
        except ValueError:
            continue
    raise FileWriteError(
        "path_out_of_scope",
        path,
        f"allowed_roots={','.join(str(x) for x in normalized_roots)}",
    )


def _ensure_parent_dir(path: Path) -> None:
    parent = path.parent
    if parent.exists():
        if not parent.is_dir():
            raise FileWriteError("missing_parent_dir", path, f"parent_not_dir:{parent}")
    else:
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise FileWriteError("missing_parent_dir", path, str(exc)) from exc


def _check_write_permission(path: Path) -> None:
    parent = path.parent
    if not os.access(parent, os.W_OK):
        raise FileWriteError("permission_denied", path, f"parent_not_writable:{parent}")
    if path.exists() and (not os.access(path, os.W_OK)):
        raise FileWriteError("permission_denied", path, f"file_not_writable:{path}")


def _apply_mode(path: Path, mode: int | None, code: str) -> None:
    if mode is None:
        return
    if os.name == "nt":
        return
    try:
        os.chmod(path, int(mode))
    except Exception as exc:
        raise FileWriteError(code, path, str(exc)) from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_size_bytes(content: str, encoding: str) -> int:
    try:
        return len(str(content).encode(encoding, errors="ignore"))
    except Exception:
        return len(str(content).encode("utf-8", errors="ignore"))


def _resolve_audit_path() -> Path | None:
    disabled_raw = str(os.getenv(_AUDIT_DISABLED_ENV, "")).strip().lower()
    if disabled_raw in {"1", "true", "yes", "on"}:
        return None
    env_path = str(os.getenv(_AUDIT_FILE_ENV, "")).strip()
    if env_path:
        try:
            return _resolve_path(env_path)
        except Exception:
            return None
    return (Path(__file__).resolve().parent / _DEFAULT_AUDIT_REL_PATH).resolve()


def _emit_audit_event(event: dict[str, Any]) -> None:
    """Best-effort audit logging, never raises."""

    audit_path = _resolve_audit_path()
    if audit_path is None:
        return
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(event or {})
        payload.setdefault("ts_utc", _utc_now_iso())
        payload.setdefault("pid", os.getpid())
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(str(audit_path), os.O_CREAT | os.O_APPEND | os.O_WRONLY)
        try:
            os.write(fd, line.encode("utf-8", errors="ignore"))
        finally:
            os.close(fd)
    except Exception:
        return


@contextmanager
def file_lock(
    target_path: str | Path,
    *,
    timeout_sec: float = 15.0,
    poll_interval_sec: float = 0.05,
    stale_lock_sec: float = 300.0,
):
    """Per-target lock based on lock-file creation (cross-process)."""

    target = _resolve_path(target_path)
    _ensure_parent_dir(target)
    lock_path = target.with_name(f".{target.name}.lock")
    deadline = time.monotonic() + max(0.1, float(timeout_sec))

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()} {time.time():.6f}\n".encode("utf-8"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            if stale_lock_sec > 0:
                try:
                    age_sec = time.time() - lock_path.stat().st_mtime
                    if age_sec > stale_lock_sec:
                        lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                except Exception:
                    pass
            if time.monotonic() >= deadline:
                raise FileWriteError("lock_timeout", target, f"lock={lock_path}")
            time.sleep(max(0.01, float(poll_interval_sec)))
        except Exception as exc:
            raise FileWriteError("lock_create_failed", target, str(exc)) from exc

    try:
        yield target
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _atomic_write_text_unlocked(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
    file_mode: int | None = None,
    dir_mode: int | None = None,
) -> None:
    _ensure_parent_dir(path)
    _check_write_permission(path)
    _apply_mode(path.parent, dir_mode, "dir_permission_set_failed")

    tmp_path = path.with_name(f".{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try:
        with tmp_path.open("w", encoding=encoding, newline=newline) as fp:
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())
        last_exc: Exception | None = None
        for idx in range(12):
            try:
                os.replace(tmp_path, path)
                last_exc = None
                break
            except PermissionError as exc:
                # Windows may transiently hold a handle on fast replace loops.
                last_exc = exc
                time.sleep(0.01 * (idx + 1))
            except Exception as exc:
                last_exc = exc
                break
        if last_exc is not None:
            raise last_exc
        _apply_mode(path, file_mode, "file_permission_set_failed")
    except FileWriteError:
        raise
    except Exception as exc:
        raise FileWriteError("atomic_write_failed", path, str(exc)) from exc
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
    file_mode: int | None = None,
    dir_mode: int | None = None,
    allowed_roots: Iterable[str | Path] | None = None,
    lock_timeout_sec: float = 15.0,
    audit_op: str = "write_text",
) -> Path:
    target = _resolve_path(path)
    content_text = str(content)
    started = time.monotonic()
    try:
        _assert_write_scope(target, allowed_roots)
        with file_lock(target, timeout_sec=lock_timeout_sec):
            _atomic_write_text_unlocked(
                target,
                content_text,
                encoding=encoding,
                newline=newline,
                file_mode=file_mode,
                dir_mode=dir_mode,
            )
        _emit_audit_event(
            {
                "op": str(audit_op or "write_text"),
                "path": str(target),
                "status": "ok",
                "size_bytes": _safe_size_bytes(content_text, encoding),
                "duration_ms": round((time.monotonic() - started) * 1000.0, 3),
                "code": "ok",
            }
        )
        return target
    except FileWriteError as exc:
        _emit_audit_event(
            {
                "op": str(audit_op or "write_text"),
                "path": str(target),
                "status": "error",
                "size_bytes": _safe_size_bytes(content_text, encoding),
                "duration_ms": round((time.monotonic() - started) * 1000.0, 3),
                "code": exc.code,
                "detail": exc.detail,
            }
        )
        raise
    except Exception as exc:
        wrapped = FileWriteError("atomic_write_failed", target, str(exc))
        _emit_audit_event(
            {
                "op": str(audit_op or "write_text"),
                "path": str(target),
                "status": "error",
                "size_bytes": _safe_size_bytes(content_text, encoding),
                "duration_ms": round((time.monotonic() - started) * 1000.0, 3),
                "code": wrapped.code,
                "detail": wrapped.detail,
            }
        )
        raise wrapped from exc


def append_text_atomic(
    path: str | Path,
    append_text: str,
    *,
    create_with: str = "",
    encoding: str = "utf-8",
    newline: str | None = None,
    file_mode: int | None = None,
    dir_mode: int | None = None,
    allowed_roots: Iterable[str | Path] | None = None,
    lock_timeout_sec: float = 15.0,
) -> Path:
    target = _resolve_path(path)
    append_chunk = str(append_text)
    started = time.monotonic()
    try:
        _assert_write_scope(target, allowed_roots)
        with file_lock(target, timeout_sec=lock_timeout_sec):
            _ensure_parent_dir(target)
            _check_write_permission(target)
            if target.exists():
                try:
                    base_text = target.read_text(encoding=encoding)
                except Exception as exc:
                    raise FileWriteError("read_before_append_failed", target, str(exc)) from exc
            else:
                base_text = str(create_with or "")
            next_text = f"{base_text}{append_chunk}"
            _atomic_write_text_unlocked(
                target,
                next_text,
                encoding=encoding,
                newline=newline,
                file_mode=file_mode,
                dir_mode=dir_mode,
            )
        final_size = -1
        try:
            final_size = int(target.stat().st_size)
        except Exception:
            final_size = -1
        _emit_audit_event(
            {
                "op": "append_text",
                "path": str(target),
                "status": "ok",
                "append_bytes": _safe_size_bytes(append_chunk, encoding),
                "size_bytes": final_size,
                "duration_ms": round((time.monotonic() - started) * 1000.0, 3),
                "code": "ok",
            }
        )
        return target
    except FileWriteError as exc:
        _emit_audit_event(
            {
                "op": "append_text",
                "path": str(target),
                "status": "error",
                "append_bytes": _safe_size_bytes(append_chunk, encoding),
                "duration_ms": round((time.monotonic() - started) * 1000.0, 3),
                "code": exc.code,
                "detail": exc.detail,
            }
        )
        raise
    except Exception as exc:
        wrapped = FileWriteError("atomic_append_failed", target, str(exc))
        _emit_audit_event(
            {
                "op": "append_text",
                "path": str(target),
                "status": "error",
                "append_bytes": _safe_size_bytes(append_chunk, encoding),
                "duration_ms": round((time.monotonic() - started) * 1000.0, 3),
                "code": wrapped.code,
                "detail": wrapped.detail,
            }
        )
        raise wrapped from exc


def write_json_atomic(
    path: str | Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
    sort_keys: bool = False,
    encoding: str = "utf-8",
    file_mode: int | None = None,
    dir_mode: int | None = None,
    allowed_roots: Iterable[str | Path] | None = None,
    lock_timeout_sec: float = 15.0,
) -> Path:
    content = json.dumps(
        payload,
        ensure_ascii=ensure_ascii,
        indent=indent,
        sort_keys=sort_keys,
    ) + "\n"
    return atomic_write_text(
        path,
        content,
        encoding=encoding,
        file_mode=file_mode,
        dir_mode=dir_mode,
        allowed_roots=allowed_roots,
        lock_timeout_sec=lock_timeout_sec,
        audit_op="write_json",
    )
