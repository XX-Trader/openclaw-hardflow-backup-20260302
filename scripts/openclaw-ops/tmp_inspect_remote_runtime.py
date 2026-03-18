#!/usr/bin/env python3
import json
from pathlib import Path

import sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else str(Path.home())
base = Path(TARGET).expanduser()

jobs_file = base / '.openclaw' / 'cron' / 'jobs.json'
queue_dirs = [
    base / '.openclaw' / 'delivery-queue' / 'pending',
    base / '.openclaw' / 'delivery-queue' / 'deferred',
    base / '.openclaw' / 'delivery-queue' / 'failed',
]
runtime_env = base / '.openclaw' / 'ops' / 'runtime.env'
openclaw_json = base / '.openclaw' / 'openclaw.json'

bad = '-1003333097130'

result = {
    'home': str(base),
    'jobs_file_exists': jobs_file.exists(),
    'jobs_old_target_count': 0,
    'jobs_target_values': [],
    'delivery_queue_old_counts': {},
    'runtime_env_exists': runtime_env.exists(),
}

if jobs_file.exists():
    try:
        jobs_obj = json.loads(jobs_file.read_text(encoding='utf-8'))
        jobs = jobs_obj.get('jobs', []) if isinstance(jobs_obj, dict) else []
        targets = []
        for item in jobs:
            if not isinstance(item, dict):
                continue
            delivery = item.get('delivery')
            if not isinstance(delivery, dict):
                continue
            target = str(delivery.get('to', '') or '').strip()
            if target and target not in targets:
                targets.append(target)
            if target == bad:
                result['jobs_old_target_count'] += 1
        result['jobs_target_values'] = targets
        result['jobs_total'] = len(jobs)
    except Exception as exc:
        result['jobs_error'] = str(exc)

for d in queue_dirs:
    old_count = 0
    if d.exists():
        for p in d.glob('*.json'):
            try:
                payload = json.loads(p.read_text(encoding='utf-8')).get('payload', {})
                target = str(payload.get('to', '') or '').strip() if isinstance(payload, dict) else ''
                if target == bad:
                    old_count += 1
            except Exception:
                pass
    result['delivery_queue_old_counts'][str(d.name)] = old_count

if runtime_env.exists():
    lines = runtime_env.read_text(encoding='utf-8', errors='ignore').splitlines()
    result['runtime_env_keys'] = [
        line.split('=', 1)[0]
        for line in lines
        if '=' in line and not line.startswith('#') and line.split('=', 1)[0]
    ]
    env_dict = {}
    for line in lines:
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env_dict[k.strip()] = v.strip()
    result['dingtalk_webhook_exists'] = 'DINGTALK_WEBHOOK_URL' in env_dict
    result['dingtalk_secret_exists'] = 'DINGTALK_SECRET' in env_dict

if openclaw_json.exists():
    try:
        cfg = json.loads(openclaw_json.read_text(encoding='utf-8'))
        channels = cfg.get('channels', {}) if isinstance(cfg, dict) else {}
        telegram = channels.get('telegram', {}) if isinstance(channels, dict) else {}
        result['telegram_allow_from'] = [
            str(x)
            for x in telegram.get('allowFrom', [])
            if isinstance(telegram.get('allowFrom', []), list)
        ] if isinstance(telegram.get('allowFrom', []), list) else []
        diagnostics = cfg.get('diagnostics', {}) if isinstance(cfg, dict) else {}
        result['diagnostics_enabled'] = bool(diagnostics.get('enabled'))
        result['diagnostics_flags'] = diagnostics.get('flags', [])
        session = cfg.get('session', {}) if isinstance(cfg, dict) else {}
        result['session_dm_scope'] = session.get('dmScope')
    except Exception as exc:
        result['openclaw_json_error'] = str(exc)

print(json.dumps(result, ensure_ascii=False))
