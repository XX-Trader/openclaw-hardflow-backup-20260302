#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')
DEFAULT_REGISTRY = Path.home() / '.openclaw/ops/task-center/project-registry.json'
DEFAULT_LOG_ROOT = Path.home() / '.openclaw/ops/task-center/workflow-io/project-agent/manual/project-index-maintainer'
SOURCE_EXTS = {'.py', '.js', '.ts', '.tsx', '.json', '.yml', '.yaml', '.md', '.sh'}
ROUTE_RE = re.compile(r"@(app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)")


def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def atomic_write_text(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding='utf-8') if path.exists() else None
    if old == text:
        return False
    tmp = path.with_name(f'.{path.name}.tmp.{os.getpid()}')
    tmp.write_text(text, encoding='utf-8')
    os.replace(tmp, path)
    return True


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str, int]:
    st = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip(), int((time.time() - st) * 1000)
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or '').strip(), f'timeout: {e}', int((time.time() - st) * 1000)


def load_projects(path: Path) -> list[dict[str, Any]]:
    obj = safe_load_json(path, {})
    rows = obj.get('projects', []) if isinstance(obj, dict) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        project_id = str(row.get('project_id') or '').strip()
        repo_path = str(row.get('repo_path') or '').strip()
        if not project_id or not repo_path:
            continue
        out.append(row)
    return out


def git_sync(repo: Path, pull: bool) -> dict[str, Any]:
    info: dict[str, Any] = {'repo': str(repo), 'pull_attempted': pull}
    if not repo.exists() or not (repo / '.git').exists():
        info['ok'] = False
        info['error'] = 'repo_not_found_or_not_git'
        return info

    rc, out, _, _ = run_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], repo)
    info['branch'] = out if rc == 0 else 'unknown'
    rc, out, _, _ = run_cmd(['git', 'rev-parse', 'HEAD'], repo)
    info['before_commit'] = out if rc == 0 else 'unknown'

    if pull:
        rc, out, err, cost = run_cmd(['git', 'pull', '--ff-only'], repo, timeout=180)
        info['pull_rc'] = rc
        info['pull_stdout'] = out[-1000:]
        info['pull_error'] = err[-1000:]
        info['pull_duration_ms'] = cost
    else:
        info['pull_rc'] = 0

    rc, out, _, _ = run_cmd(['git', 'rev-parse', 'HEAD'], repo)
    info['after_commit'] = out if rc == 0 else info.get('before_commit', 'unknown')
    info['changed'] = info.get('before_commit') != info.get('after_commit')

    rc, out, _, _ = run_cmd(['git', 'status', '--porcelain'], repo)
    info['dirty_files'] = len(out.splitlines()) if rc == 0 and out else 0
    info['ok'] = True
    return info


def scan_source_stats(base: Path) -> dict[str, Any]:
    out = {'path': str(base), 'exists': base.exists(), 'files': 0, 'by_ext': {}}
    if not base.exists() or not base.is_dir():
        return out
    by_ext: dict[str, int] = {}
    files = 0
    for p in base.rglob('*'):
        if not p.is_file():
            continue
        px = p.as_posix()
        if '/.git/' in px or '/.workflow/' in px or '/.venv' in px:
            continue
        ext = p.suffix.lower()
        if ext not in SOURCE_EXTS:
            continue
        files += 1
        by_ext[ext] = by_ext.get(ext, 0) + 1
    out['files'] = files
    out['by_ext'] = dict(sorted(by_ext.items(), key=lambda kv: kv[0]))
    return out


def scan_routes(base: Path) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    if not base.exists() or not base.is_dir():
        return routes
    for p in base.rglob('*.py'):
        px = p.as_posix()
        if '/.git/' in px or '/.workflow/' in px:
            continue
        try:
            lines = p.read_text(encoding='utf-8', errors='ignore').splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, start=1):
            m = ROUTE_RE.search(line)
            if not m:
                continue
            routes.append({'method': m.group(2).upper(), 'path': m.group(3), 'file': str(p), 'line': i})
    return routes


def state_hash(obj: dict[str, Any]) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return hashlib.sha1(payload).hexdigest()


def make_docs(row: dict[str, Any], git_info: dict[str, Any], modules: list[dict[str, Any]], routes: list[dict[str, Any]], st_hash: str) -> dict[str, str]:
    project_id = str(row.get('project_id'))
    name = str(row.get('name') or project_id)
    repo = Path(str(row.get('repo_path'))).expanduser()
    mod_total = sum(int(m.get('files') or 0) for m in modules)

    mod_lines = []
    for m in modules:
        rel = os.path.relpath(m['path'], str(repo)) if str(m['path']).startswith(str(repo)) else m['path']
        mod_lines.append(f"- `{rel}`: files={m.get('files',0)}, by_ext={json.dumps(m.get('by_ext',{}), ensure_ascii=False)}")

    route_lines = []
    for r in routes[:200]:
        rel_file = os.path.relpath(r['file'], str(repo)) if str(r['file']).startswith(str(repo)) else r['file']
        route_lines.append(f"- `{r['method']}` `{r['path']}` -> `{rel_file}:{r['line']}`")
    if len(routes) > 200:
        route_lines.append(f"- ... ({len(routes)-200} more routes omitted)")

    project_index = f"""# Project Index (auto maintained)

- project_id: `{project_id}`
- name: `{name}`
- repo: `{repo}`
- branch: `{git_info.get('branch','unknown')}`
- latest_commit: `{git_info.get('after_commit','unknown')}`
- pull_rc: `{git_info.get('pull_rc',0)}`
- state_hash: `{st_hash}`

## Summary

- module_dirs: `{len(modules)}`
- source_files: `{mod_total}`
- api_routes: `{len(routes)}`

## Index Files

- modules: `modules/MODULE_INDEX.md`
- apis: `apis/API_INDEX.md`
- process: `process/RUN_AND_CHANGE_FLOW.md`
- manifest: `project-index-manifest.json`
"""

    module_index = '# Module Index (auto maintained)\n\n' + '\n'.join(mod_lines) + '\n'
    api_index = '# API Index (auto maintained)\n\n' + ('\n'.join(route_lines) if route_lines else '- no routes found\n') + '\n'

    process_doc = """# Run and Change Flow

1. Entry: coordinator.
2. Coordinator fetches project context from project-agent index.
3. Coordinator creates task packet and assigns execution.
4. High risk or unclear requirement -> human confirmation.
5. Low risk -> auto dispatch.
6. Tester failure -> jobs high priority feedback loop.

Required record fields:
- task_id
- step status
- duration
- token usage
- cost estimate
"""

    return {
        'PROJECT_INDEX.md': project_index,
        'modules/MODULE_INDEX.md': module_index,
        'apis/API_INDEX.md': api_index,
        'process/RUN_AND_CHANGE_FLOW.md': process_doc,
    }


def maintain_project(row: dict[str, Any], git_pull: bool) -> dict[str, Any]:
    st = now_ms()
    repo = Path(str(row['repo_path'])).expanduser()
    index_dir = Path(str(row.get('index_dir') or (repo / 'docs/project-index'))).expanduser()

    git_info = git_sync(repo, git_pull)
    module_dirs = [repo / str(x) for x in (row.get('module_dirs') or [])]
    api_dirs = [repo / str(x) for x in (row.get('api_dirs') or [])]

    modules = [scan_source_stats(p) for p in module_dirs]
    routes: list[dict[str, Any]] = []
    for p in api_dirs:
        routes.extend(scan_routes(p))
    routes = sorted(routes, key=lambda r: (str(r.get('method','')), str(r.get('path','')), str(r.get('file','')), int(r.get('line') or 0)))

    route_hash = hashlib.sha1(json.dumps(routes, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    state_obj = {
        'project_id': row['project_id'],
        'repo': str(repo),
        'branch': git_info.get('branch', 'unknown'),
        'latest_commit': git_info.get('after_commit', 'unknown'),
        'dirty_files': int(git_info.get('dirty_files') or 0),
        'modules': modules,
        'route_hash': route_hash,
        'route_count': len(routes),
    }
    st_hash = state_hash(state_obj)

    manifest_path = index_dir / 'project-index-manifest.json'
    old_manifest = safe_load_json(manifest_path, {})
    old_hash = str(old_manifest.get('state_hash') or '') if isinstance(old_manifest, dict) else ''

    changed_files: list[str] = []
    if old_hash != st_hash:
        docs = make_docs(row, git_info, modules, routes, st_hash)
        for rel, txt in docs.items():
            f = index_dir / rel
            if atomic_write_text(f, txt):
                changed_files.append(str(f))

        manifest = {
            'project_id': row['project_id'],
            'name': row.get('name') or row['project_id'],
            'updated_at': now_iso(),
            'repo_path': str(repo),
            'index_dir': str(index_dir),
            'state_hash': st_hash,
            'state': state_obj,
            'git': git_info,
        }
        mtxt = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
        if atomic_write_text(manifest_path, mtxt):
            changed_files.append(str(manifest_path))

    return {
        'project_id': row['project_id'],
        'name': row.get('name') or row['project_id'],
        'repo_path': str(repo),
        'index_dir': str(index_dir),
        'git': git_info,
        'api_routes': len(routes),
        'state_hash': st_hash,
        'changed_files': changed_files,
        'duration_ms': now_ms() - st,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Project index maintainer')
    ap.add_argument('--registry', default=str(DEFAULT_REGISTRY))
    ap.add_argument('--project-id', default='')
    ap.add_argument('--git-pull', action='store_true')
    ap.add_argument('--emit-json', action='store_true')
    ap.add_argument('--always-reply', action='store_true')
    args = ap.parse_args()

    t0 = now_ms()
    reg = Path(args.registry).expanduser()
    projects = load_projects(reg)
    if args.project_id:
        projects = [p for p in projects if str(p.get('project_id')) == args.project_id]

    if not projects:
        print('NO_REPLY')
        return 0

    results = [maintain_project(p, git_pull=bool(args.git_pull)) for p in projects]
    changed_count = sum(1 for r in results if r.get('changed_files'))

    row = {
        'ts': now_ms(),
        'at': now_iso(),
        'workflow_name': 'project-index-maintainer',
        'input': {
            'registry': str(reg),
            'project_id': args.project_id,
            'git_pull': bool(args.git_pull),
            'project_count': len(projects),
        },
        'output': {
            'changed_count': changed_count,
            'results': results,
        },
        'runtime': {
            'duration_ms': now_ms() - t0,
        },
        'usage': {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
        },
        'cost_estimate': {
            'currency': 'USD',
            'total_cost': 0.0,
        },
    }

    day = datetime.now(TZ).strftime('%Y-%m-%d')
    append_jsonl(DEFAULT_LOG_ROOT / f'{day}.jsonl', row)

    if changed_count == 0 and not args.always_reply:
        print('NO_REPLY')
        return 0

    if args.emit_json:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    else:
        lines = ['project-index maintenance result:']
        for r in results:
            lines.append(f"- {r['project_id']}: changed_files={len(r['changed_files'])}, routes={r['api_routes']}, duration_ms={r['duration_ms']}")
        print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
