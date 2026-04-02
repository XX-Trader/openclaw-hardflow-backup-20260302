#!/usr/bin/env python3
"""Manage OpenClaw official upstream binding for this repository.

Recommended flow:
1) init   : add official source as submodule/subtree at vendor path
2) update : move to a newer stable tag/release ref
3) status : inspect current binding state
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / ".workflow" / "openclaw-upstream-binding.json"
DEFAULT_VENDOR_DIR = "vendor/openclaw-official"
DEFAULT_BRIDGE_DIR = "integration/openclaw-bridge"
DEFAULT_PATCH_DIR = "patches/openclaw"


class BindingError(RuntimeError):
    """Raised when binding operations fail."""


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_cmd(cmd: list[str], cwd: Path | None = None, dry_run: bool = False) -> str:
    rendered = " ".join(shlex.quote(c) for c in cmd)
    print(f"$ {rendered}")
    if dry_run:
        return ""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or f"command failed with exit={proc.returncode}"
        raise BindingError(detail)
    return (proc.stdout or "").strip()


def ensure_repo_root() -> None:
    if not (PROJECT_ROOT / ".git").exists():
        raise BindingError(f"not a git repository: {PROJECT_ROOT}")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def vendor_abs_path(vendor_dir: str) -> Path:
    return (PROJECT_ROOT / vendor_dir).resolve()


def is_submodule_path(vendor_dir: str) -> bool:
    try:
        out = run_cmd(["git", "submodule", "status", "--", vendor_dir])
        return bool(out.strip())
    except BindingError:
        return False


def ensure_paths(vendor_dir: str, bridge_dir: str, patch_dir: str) -> None:
    (PROJECT_ROOT / bridge_dir).mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / patch_dir).mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / Path(vendor_dir).parent).mkdir(parents=True, exist_ok=True)


def build_config(
    *,
    strategy: str,
    repo_url: str,
    ref: str,
    vendor_dir: str,
    submodule_name: str,
    bridge_dir: str,
    patch_dir: str,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "strategy": strategy,
        "vendor_dir": vendor_dir,
        "submodule_name": submodule_name,
        "bridge_dir": bridge_dir,
        "patch_dir": patch_dir,
        "upstream": {
            "repo_url": repo_url,
            "ref": ref,
        },
        "updated_at": now_iso_utc(),
    }


def add_submodule(repo_url: str, vendor_dir: str, submodule_name: str, dry_run: bool) -> None:
    if is_submodule_path(vendor_dir):
        return
    vendor = vendor_abs_path(vendor_dir)
    if vendor.exists() and any(vendor.iterdir()):
        raise BindingError(
            f"vendor path not empty and not a submodule: {vendor}. "
            "please clean path or choose another --vendor-dir"
        )
    run_cmd(
        [
            "git",
            "submodule",
            "add",
            "--name",
            submodule_name,
            repo_url,
            vendor_dir,
        ],
        dry_run=dry_run,
    )


def checkout_submodule_ref(vendor_dir: str, ref: str, dry_run: bool) -> None:
    vendor = vendor_abs_path(vendor_dir)
    run_cmd(["git", "submodule", "update", "--init", "--", vendor_dir], dry_run=dry_run)
    run_cmd(["git", "-C", str(vendor), "fetch", "--tags", "origin"], dry_run=dry_run)
    run_cmd(["git", "-C", str(vendor), "checkout", ref], dry_run=dry_run)
    run_cmd(["git", "-C", str(vendor), "submodule", "update", "--init", "--recursive"], dry_run=dry_run)
    run_cmd(["git", "add", "--", vendor_dir], dry_run=dry_run)


def add_subtree(repo_url: str, vendor_dir: str, ref: str, dry_run: bool) -> None:
    vendor = vendor_abs_path(vendor_dir)
    if vendor.exists():
        raise BindingError(
            f"vendor path already exists: {vendor}. "
            "subtree init expects a clean path."
        )
    run_cmd(
        ["git", "subtree", "add", "--prefix", vendor_dir, repo_url, ref, "--squash"],
        dry_run=dry_run,
    )


def update_subtree(repo_url: str, vendor_dir: str, ref: str, dry_run: bool) -> None:
    run_cmd(
        ["git", "subtree", "pull", "--prefix", vendor_dir, repo_url, ref, "--squash"],
        dry_run=dry_run,
    )


def cmd_init(args: argparse.Namespace) -> int:
    ensure_repo_root()
    ensure_paths(args.vendor_dir, args.bridge_dir, args.patch_dir)
    strategy = args.strategy
    if strategy == "submodule":
        add_submodule(args.repo_url, args.vendor_dir, args.submodule_name, args.dry_run)
        checkout_submodule_ref(args.vendor_dir, args.ref, args.dry_run)
    else:
        add_subtree(args.repo_url, args.vendor_dir, args.ref, args.dry_run)
    data = build_config(
        strategy=strategy,
        repo_url=args.repo_url,
        ref=args.ref,
        vendor_dir=args.vendor_dir,
        submodule_name=args.submodule_name,
        bridge_dir=args.bridge_dir,
        patch_dir=args.patch_dir,
    )
    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    write_json(Path(args.config), data)
    print(f"binding config saved: {args.config}")
    return 0


def resolve_config_and_args(args: argparse.Namespace) -> dict[str, Any]:
    cfg = read_json(Path(args.config))
    repo_url = str(args.repo_url or cfg.get("upstream", {}).get("repo_url", "")).strip()
    ref = str(args.ref or cfg.get("upstream", {}).get("ref", "")).strip()
    strategy = str(args.strategy or cfg.get("strategy", "submodule")).strip()
    vendor_dir = str(args.vendor_dir or cfg.get("vendor_dir", DEFAULT_VENDOR_DIR)).strip()
    submodule_name = str(args.submodule_name or cfg.get("submodule_name", "openclaw-official")).strip()
    bridge_dir = str(args.bridge_dir or cfg.get("bridge_dir", DEFAULT_BRIDGE_DIR)).strip()
    patch_dir = str(args.patch_dir or cfg.get("patch_dir", DEFAULT_PATCH_DIR)).strip()
    if not repo_url:
        raise BindingError("repo url is required (provide --repo-url or init config first)")
    if not ref:
        raise BindingError("ref is required (provide --ref or init config first)")
    if strategy not in {"submodule", "subtree"}:
        raise BindingError(f"unsupported strategy: {strategy}")
    return {
        "repo_url": repo_url,
        "ref": ref,
        "strategy": strategy,
        "vendor_dir": vendor_dir,
        "submodule_name": submodule_name,
        "bridge_dir": bridge_dir,
        "patch_dir": patch_dir,
    }


def cmd_update(args: argparse.Namespace) -> int:
    ensure_repo_root()
    merged = resolve_config_and_args(args)
    ensure_paths(merged["vendor_dir"], merged["bridge_dir"], merged["patch_dir"])
    if merged["strategy"] == "submodule":
        add_submodule(merged["repo_url"], merged["vendor_dir"], merged["submodule_name"], args.dry_run)
        checkout_submodule_ref(merged["vendor_dir"], merged["ref"], args.dry_run)
    else:
        if not vendor_abs_path(merged["vendor_dir"]).exists():
            add_subtree(merged["repo_url"], merged["vendor_dir"], merged["ref"], args.dry_run)
        else:
            update_subtree(merged["repo_url"], merged["vendor_dir"], merged["ref"], args.dry_run)
    data = build_config(**merged)
    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    write_json(Path(args.config), data)
    print(f"binding config updated: {args.config}")
    return 0


def safe_git_out(cmd: list[str]) -> str:
    try:
        return run_cmd(cmd)
    except BindingError:
        return ""


def cmd_status(args: argparse.Namespace) -> int:
    ensure_repo_root()
    cfg = read_json(Path(args.config))
    vendor_dir = str(args.vendor_dir or cfg.get("vendor_dir", DEFAULT_VENDOR_DIR))
    vendor = vendor_abs_path(vendor_dir)
    result: dict[str, Any] = {
        "config_file": str(Path(args.config)),
        "config_exists": Path(args.config).exists(),
        "config": cfg,
        "vendor_dir": vendor_dir,
        "vendor_exists": vendor.exists(),
        "is_submodule": is_submodule_path(vendor_dir),
        "vendor_head": "",
        "vendor_ref_exact_tag": "",
        "vendor_dirty": False,
        "root_submodule_status": "",
    }
    if vendor.exists():
        result["vendor_head"] = safe_git_out(["git", "-C", str(vendor), "rev-parse", "HEAD"])
        result["vendor_ref_exact_tag"] = safe_git_out(
            ["git", "-C", str(vendor), "describe", "--tags", "--exact-match"]
        )
        result["vendor_dirty"] = bool(safe_git_out(["git", "-C", str(vendor), "status", "--short"]))
        result["root_submodule_status"] = safe_git_out(["git", "submodule", "status", "--", vendor_dir])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw official upstream binding manager")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_flags(
        p: argparse.ArgumentParser,
        *,
        include_strategy: bool = True,
        require_repo_ref: bool = False,
        strategy_default: str = "",
    ) -> None:
        p.add_argument("--config", default=str(DEFAULT_CONFIG))
        p.add_argument("--repo-url", default="", required=require_repo_ref)
        p.add_argument("--ref", default="", required=require_repo_ref, help="stable tag/release/commit to pin")
        p.add_argument("--vendor-dir", default=DEFAULT_VENDOR_DIR)
        p.add_argument("--submodule-name", default="openclaw-official")
        p.add_argument("--bridge-dir", default=DEFAULT_BRIDGE_DIR)
        p.add_argument("--patch-dir", default=DEFAULT_PATCH_DIR)
        if include_strategy:
            p.add_argument("--strategy", choices=["submodule", "subtree"], default=strategy_default)
        p.add_argument("--dry-run", action="store_true")

    init_p = sub.add_parser("init", help="initialize upstream binding")
    add_common_flags(init_p, include_strategy=True, require_repo_ref=True, strategy_default="submodule")
    init_p.set_defaults(func=cmd_init)

    upd_p = sub.add_parser("update", help="update pinned upstream ref")
    add_common_flags(upd_p, include_strategy=True, strategy_default="")
    upd_p.set_defaults(func=cmd_update)

    st_p = sub.add_parser("status", help="show current binding status")
    st_p.add_argument("--config", default=str(DEFAULT_CONFIG))
    st_p.add_argument("--vendor-dir", default="")
    st_p.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BindingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
