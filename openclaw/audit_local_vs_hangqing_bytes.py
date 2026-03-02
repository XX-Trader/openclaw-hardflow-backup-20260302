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

roots=[('openclaw',home/'.openclaw'/'skills'),('claude',home/'.claude'/'skills'),('cc-switch',home/'.cc-switch'/'skills')]
placeholder_re=re.compile(r'replace with description of the skill|template skill', re.I)
yaml_key_re=re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*\s*:')

entries=[]
for label,root in roots:
    if not root.exists():
        continue
    for p in root.rglob('*'):
        if not p.is_file() or p.name not in ('SKILL.md','skill.md'):
            continue
        b=p.read_bytes()
        sha=hashlib.sha256(b).hexdigest()
        text=b.decode('utf-8',errors='ignore')
        lines=text.splitlines()
        header_issue=False
        if lines and lines[0].strip()=='---':
            end=None
            for i in range(1,min(300,len(lines))):
                if lines[i].strip()=='---':
                    end=i; break
            if end is None:
                header_issue=True
            else:
                body=lines[end+1:]
                k=0
                while k<len(body) and body[k].strip()=='': k+=1
                if k<len(body) and yaml_key_re.match(body[k].strip()):
                    header_issue=True
        skill=p.parent.name
        entries.append({
            'skill':skill,'root':label,'path':str(p),'sha256':sha,
            'server_match':(skill in server_map and sha==server_map[skill]),
            'in_server_set':skill in server_set,
            'placeholder':bool(placeholder_re.search(text)),
            'header_issue':header_issue,
        })

by_skill={}
for e in entries: by_skill.setdefault(e['skill'],[]).append(e)
synced=[];drift=[];local_only=[]
for s,arr in sorted(by_skill.items()):
    any_match=any(x['server_match'] for x in arr)
    in_server=any(x['in_server_set'] for x in arr)
    if in_server and any_match: synced.append(s)
    elif in_server and not any_match: drift.append(s)
    else: local_only.append(s)
server_missing=sorted(list(server_set-set(by_skill.keys())))
summary={
 'generated_at':datetime.now().isoformat(timespec='seconds'),
 'server_skill_count':len(server_set),
 'local_file_count':len(entries),
 'local_unique_skill_names':len(by_skill),
 'sync':{'synced_count':len(synced),'drift_count':len(drift),'local_only_count':len(local_only),'server_missing_count':len(server_missing)},
}
out={'summary':summary,'synced_skills':synced,'drift_skills':drift,'local_only_skills':local_only,'server_missing_skills':server_missing,'entries':entries}
out_json=home/'.openclaw'/'local_skill_audit_vs_hangqing_bytes.json'
out_json.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
