import json, hashlib, re
from pathlib import Path
from datetime import datetime

home=Path('C:/Users/superma')
server_hash_file=home/'.openclaw'/'hangqing_skill_hashes.json'
raw=server_hash_file.read_bytes()
server_obj=None
for enc in ('utf-8','utf-8-sig','utf-16','utf-16le','utf-16be','gbk'):
    try:
        server_obj=json.loads(raw.decode(enc))
        break
    except Exception:
        pass
if server_obj is None:
    raise RuntimeError('cannot decode hangqing_skill_hashes.json')

server_map={x['skill']:x['sha256'] for x in server_obj.get('items',[])}
server_set=set(server_map.keys())

roots=[
    ('openclaw', home/'.openclaw'/'skills'),
    ('claude', home/'.claude'/'skills'),
    ('cc-switch', home/'.cc-switch'/'skills'),
]

placeholder_re=re.compile(r'replace with description of the skill|template skill', re.I)
use_when_re=re.compile(r'use when|when to use|适用场景|触发条件|trigger', re.I)
workflow_re=re.compile(r'workflow|步骤|流程|phase|执行流程', re.I)
yaml_key_re=re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*\s*:')

entries=[]
for label,root in roots:
    if not root.exists():
        continue
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        if p.name not in ('SKILL.md','skill.md'):
            continue
        text=p.read_text(encoding='utf-8',errors='ignore')
        b=text.encode('utf-8',errors='ignore')
        sha=hashlib.sha256(b).hexdigest()
        lines=text.splitlines()
        fm=False
        fm_closed=False
        header_issue=False
        if lines and lines[0].strip()=='---':
            fm=True
            end=None
            for i in range(1,min(300,len(lines))):
                if lines[i].strip()=='---':
                    end=i
                    break
            if end is not None:
                fm_closed=True
                body=lines[end+1:]
                k=0
                while k<len(body) and body[k].strip()=='':
                    k+=1
                if k<len(body) and yaml_key_re.match(body[k].strip()):
                    header_issue=True
            else:
                header_issue=True
        skill_name=p.parent.name
        entries.append({
            'skill':skill_name,
            'root':label,
            'path':str(p),
            'sha256':sha,
            'size':len(b),
            'has_frontmatter':fm,
            'frontmatter_closed':fm_closed,
            'header_issue':header_issue,
            'placeholder':bool(placeholder_re.search(text)),
            'has_use_when':bool(use_when_re.search(text)),
            'has_workflow':bool(workflow_re.search(text)),
            'server_match':(skill_name in server_map and sha==server_map[skill_name]),
            'in_server_set':(skill_name in server_set),
        })

by_skill={}
for e in entries:
    by_skill.setdefault(e['skill'],[]).append(e)

summary={
    'generated_at':datetime.now().isoformat(timespec='seconds'),
    'server_skill_count':len(server_set),
    'local_file_count':len(entries),
    'local_unique_skill_names':len(by_skill),
}

root_counts={}
for r, _ in roots:
    arr=[e for e in entries if e['root']==r]
    root_counts[r]={
        'files':len(arr),
        'unique_skills':len(set(e['skill'] for e in arr)),
        'server_match_files':sum(1 for e in arr if e['server_match']),
        'header_issues':sum(1 for e in arr if e['header_issue']),
        'placeholders':sum(1 for e in arr if e['placeholder']),
    }
summary['roots']=root_counts

synced=[]
drift=[]
local_only=[]
for s,arr in sorted(by_skill.items()):
    any_match=any(x['server_match'] for x in arr)
    in_server=any(x['in_server_set'] for x in arr)
    if in_server and any_match:
        synced.append(s)
    elif in_server and not any_match:
        drift.append(s)
    elif not in_server:
        local_only.append(s)

server_missing=sorted(list(server_set - set(by_skill.keys())))

summary['sync']={
    'synced_count':len(synced),
    'drift_count':len(drift),
    'local_only_count':len(local_only),
    'server_missing_count':len(server_missing),
}

format_issues=[e for e in entries if e['header_issue']]
placeholders=[e for e in entries if e['placeholder']]

out={
    'summary':summary,
    'synced_skills':synced,
    'drift_skills':drift,
    'local_only_skills':local_only,
    'server_missing_skills':server_missing,
    'format_issues':format_issues,
    'placeholders':placeholders,
    'entries':entries,
}

out_json=home/'.openclaw'/'local_skill_audit_vs_hangqing.json'
out_json.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
out_md=home/'.openclaw'/'local_skill_audit_vs_hangqing.md'
lines=[]
lines.append('# Local Skills Audit vs hangqing-zhongxin')
lines.append('')
lines.append('## Summary')
lines.append('')
for k in ['server_skill_count','local_file_count','local_unique_skill_names']:
    lines.append(f'- {k}: {summary[k]}')
for k,v in summary['sync'].items():
    lines.append(f'- {k}: {v}')
lines.append('')
lines.append('## Drift Skills')
for x in drift: lines.append(f'- {x}')
lines.append('')
lines.append('## Local-only Skills')
for x in local_only: lines.append(f'- {x}')
lines.append('')
lines.append('## Server Missing Skills')
for x in server_missing: lines.append(f'- {x}')
lines.append('')
lines.append('## Format Issues')
for e in format_issues: lines.append(f"- {e['skill']} | {e['root']} | {e['path']}")
out_md.write_text('\n'.join(lines)+'\n',encoding='utf-8')

print('OUT_JSON={}'.format(out_json))
print('OUT_MD={}'.format(out_md))
print(json.dumps(summary,ensure_ascii=False))
