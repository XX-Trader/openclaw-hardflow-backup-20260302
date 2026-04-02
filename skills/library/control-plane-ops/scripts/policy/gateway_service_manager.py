#!/usr/bin/env python3
"""Reconcile OpenClaw gateway supervisors and restart the canonical service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ACTIVE_STATES = {"active", "activating", "reloading"}
ENABLED_STATES = {"enabled", "enabled-runtime", "linked", "linked-runtime", "alias"}
SYSTEM_UNIT_NAME = "openclaw.service"
USER_UNIT_NAME = "openclaw-gateway.service"


@dataclass(frozen=True)
class UnitStatus:
    scope: str
    name: str
    exists: bool
    active: bool
    enabled: bool
    load_state: str
    active_state: str
    unit_file_state: str


@dataclass(frozen=True)
class ServiceSnapshot:
    system: UnitStatus
    user: UnitStatus
    user_scope_ready: bool
    user_uid: int


@dataclass(frozen=True)
class ReconcilePlan:
    selected_scope: str
    action: str
    preferred_scope: str
    steps: list[dict[str, Any]]


def current_uid() -> int:
    try:
        return int(os.getuid())
    except AttributeError:
        raw = str(os.environ.get("UID") or os.environ.get("SUDO_UID") or "0").strip()
        return int(raw or "0")


def user_scope_env(uid: int) -> dict[str, str]:
    runtime_dir = f"/run/user/{int(uid)}"
    return {
        "XDG_RUNTIME_DIR": runtime_dir,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
    }


def user_scope_ready(uid: int) -> bool:
    return Path(f"/run/user/{int(uid)}/bus").exists()


def unit_file_path(scope: str, unit_name: str) -> Path | None:
    if scope == "user":
        return Path.home() / ".config" / "systemd" / "user" / unit_name
    for candidate in (
        Path("/etc/systemd/system") / unit_name,
        Path("/usr/lib/systemd/system") / unit_name,
        Path("/lib/systemd/system") / unit_name,
    ):
        if candidate.exists():
            return candidate
    return None


def run_cmd(args: list[str], *, env_overrides: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def show_property(
    *,
    scope: str,
    unit_name: str,
    prop: str,
    user_uid: int,
    runner=run_cmd,
) -> str:
    if shutil.which("systemctl") is None:
        return ""
    cmd = ["systemctl"]
    env_overrides: dict[str, str] | None = None
    if scope == "user":
        env_overrides = user_scope_env(user_uid)
        cmd.append("--user")
    cmd.extend(["show", unit_name, f"--property={prop}", "--value"])
    rc, out, _err = runner(cmd, env_overrides=env_overrides)
    if rc != 0:
        return ""
    return out.strip()


def probe_unit_status(
    *,
    scope: str,
    unit_name: str,
    user_uid: int,
    user_scope_is_ready: bool,
    runner=run_cmd,
) -> UnitStatus:
    fallback_exists = unit_file_path(scope, unit_name) is not None
    if scope == "user" and not user_scope_is_ready:
        exists = fallback_exists
        load_state = "loaded" if exists else "not-found"
        return UnitStatus(
            scope=scope,
            name=unit_name,
            exists=exists,
            active=False,
            enabled=False,
            load_state=load_state,
            active_state="inactive",
            unit_file_state="unknown",
        )

    load_state = show_property(
        scope=scope,
        unit_name=unit_name,
        prop="LoadState",
        user_uid=user_uid,
        runner=runner,
    )
    active_state = show_property(
        scope=scope,
        unit_name=unit_name,
        prop="ActiveState",
        user_uid=user_uid,
        runner=runner,
    )
    unit_file_state = show_property(
        scope=scope,
        unit_name=unit_name,
        prop="UnitFileState",
        user_uid=user_uid,
        runner=runner,
    )
    exists = fallback_exists or (load_state not in {"", "not-found"})
    return UnitStatus(
        scope=scope,
        name=unit_name,
        exists=exists,
        active=active_state in ACTIVE_STATES,
        enabled=unit_file_state in ENABLED_STATES,
        load_state=load_state or ("loaded" if fallback_exists else "not-found"),
        active_state=active_state or "inactive",
        unit_file_state=unit_file_state or ("disabled" if exists else "not-found"),
    )


def collect_service_snapshot(*, user_uid: int | None = None, runner=run_cmd) -> ServiceSnapshot:
    uid = current_uid() if user_uid is None else int(user_uid)
    ready = user_scope_ready(uid)
    return ServiceSnapshot(
        system=probe_unit_status(
            scope="system",
            unit_name=SYSTEM_UNIT_NAME,
            user_uid=uid,
            user_scope_is_ready=ready,
            runner=runner,
        ),
        user=probe_unit_status(
            scope="user",
            unit_name=USER_UNIT_NAME,
            user_uid=uid,
            user_scope_is_ready=ready,
            runner=runner,
        ),
        user_scope_ready=ready,
        user_uid=uid,
    )


def select_scope(snapshot: ServiceSnapshot, preferred_scope: str = "system") -> str:
    preferred = str(preferred_scope or "system").strip().lower()
    if preferred == "system" and snapshot.system.exists:
        return "system"
    if preferred == "user" and snapshot.user.exists and snapshot.user_scope_ready:
        return "user"
    if snapshot.system.exists:
        return "system"
    if snapshot.user.exists and snapshot.user_scope_ready:
        return "user"
    return "process"


def build_step(
    step_id: str,
    *,
    scope: str,
    args: list[str],
    ignore_failure: bool = False,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "scope": scope,
        "args": list(args),
        "ignore_failure": bool(ignore_failure),
    }


def build_reconcile_plan(
    snapshot: ServiceSnapshot,
    *,
    action: str = "restart",
    preferred_scope: str = "system",
    enable_preferred: bool = True,
) -> ReconcilePlan:
    requested_action = str(action or "restart").strip().lower()
    if requested_action not in {"restart", "start", "stop", "status"}:
        requested_action = "restart"

    selected_scope = select_scope(snapshot, preferred_scope=preferred_scope)
    steps: list[dict[str, Any]] = []

    if requested_action == "status":
        return ReconcilePlan(
            selected_scope=selected_scope,
            action=requested_action,
            preferred_scope=str(preferred_scope or "system"),
            steps=[],
        )

    if selected_scope == "system":
        if snapshot.user.exists and snapshot.user_scope_ready and (snapshot.user.active or snapshot.user.enabled):
            steps.append(
                build_step(
                    "user_disable_now",
                    scope="user",
                    args=["disable", "--now", USER_UNIT_NAME],
                    ignore_failure=True,
                )
            )
        if snapshot.user.exists and snapshot.user_scope_ready:
            steps.append(
                build_step(
                    "user_reset_failed",
                    scope="user",
                    args=["reset-failed", USER_UNIT_NAME],
                    ignore_failure=True,
                )
            )
        if enable_preferred and snapshot.system.exists and not snapshot.system.enabled:
            steps.append(build_step("system_enable", scope="system", args=["enable", SYSTEM_UNIT_NAME]))
        steps.append(
            build_step(
                f"system_{requested_action}",
                scope="system",
                args=[requested_action, SYSTEM_UNIT_NAME],
            )
        )
    elif selected_scope == "user":
        if enable_preferred and snapshot.user.exists and not snapshot.user.enabled:
            steps.append(build_step("user_enable", scope="user", args=["enable", USER_UNIT_NAME]))
        steps.append(
            build_step(
                f"user_{requested_action}",
                scope="user",
                args=[requested_action, USER_UNIT_NAME],
            )
        )
    else:
        cli_action = "restart" if requested_action == "restart" else requested_action
        steps.append(
            build_step(
                f"process_{cli_action}",
                scope="process",
                args=["openclaw", "gateway", cli_action],
            )
        )

    return ReconcilePlan(
        selected_scope=selected_scope,
        action=requested_action,
        preferred_scope=str(preferred_scope or "system"),
        steps=steps,
    )


def command_for_step(step: dict[str, Any], snapshot: ServiceSnapshot) -> tuple[list[str], dict[str, str] | None]:
    scope = str(step.get("scope") or "").strip().lower()
    args = [str(item) for item in step.get("args") or []]
    if scope == "system":
        return ["systemctl", *args], None
    if scope == "user":
        return ["systemctl", "--user", *args], user_scope_env(snapshot.user_uid)
    return args, None


def execute_plan(
    plan: ReconcilePlan,
    *,
    snapshot: ServiceSnapshot,
    dry_run: bool = False,
    runner=run_cmd,
) -> dict[str, Any]:
    executed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    ok = True
    for step in plan.steps:
        cmd, env_overrides = command_for_step(step, snapshot)
        if dry_run:
            executed.append(
                {
                    "id": step["id"],
                    "scope": step["scope"],
                    "command": cmd,
                    "dry_run": True,
                }
            )
            continue
        rc, out, err = runner(cmd, env_overrides=env_overrides)
        record = {
            "id": step["id"],
            "scope": step["scope"],
            "command": cmd,
            "returncode": rc,
            "stdout": out,
            "stderr": err,
            "ignored": bool(step.get("ignore_failure")),
        }
        executed.append(record)
        if rc != 0 and not bool(step.get("ignore_failure")):
            ok = False
            errors.append(record)
            break
    return {
        "ok": ok,
        "executed_steps": executed,
        "errors": errors,
    }


def snapshot_to_dict(snapshot: ServiceSnapshot) -> dict[str, Any]:
    return {
        "system": asdict(snapshot.system),
        "user": asdict(snapshot.user),
        "user_scope_ready": snapshot.user_scope_ready,
        "user_uid": snapshot.user_uid,
    }


def plan_to_dict(plan: ReconcilePlan) -> dict[str, Any]:
    return {
        "selected_scope": plan.selected_scope,
        "action": plan.action,
        "preferred_scope": plan.preferred_scope,
        "steps": plan.steps,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile OpenClaw gateway service managers")
    parser.add_argument("--action", choices=["restart", "start", "stop", "status"], default="restart")
    parser.add_argument("--prefer", choices=["system", "user"], default="system")
    parser.add_argument("--user-uid", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    parser.add_argument("--no-enable-preferred", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = collect_service_snapshot(user_uid=args.user_uid)
    plan = build_reconcile_plan(
        snapshot,
        action=args.action,
        preferred_scope=args.prefer,
        enable_preferred=not bool(args.no_enable_preferred),
    )
    result = {
        "ok": True,
        "snapshot": snapshot_to_dict(snapshot),
        "plan": plan_to_dict(plan),
    }
    if args.action == "status":
        if args.emit_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False))
        return 0

    execution = execute_plan(plan, snapshot=snapshot, dry_run=bool(args.dry_run))
    result.update(execution)
    result["ok"] = bool(execution.get("ok", True))
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
