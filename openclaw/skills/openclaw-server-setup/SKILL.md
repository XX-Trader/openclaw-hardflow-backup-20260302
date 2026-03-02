---
name: "openclaw-server-setup"
description: "OpenClaw + Codex CLI + tmux 鐨勫 Agent 鏍囧噯浣滀笟鎵嬪唽锛堝畬鏁寸増锛?
version: "1.25.0"
lastUpdated: "2026-02-28"
---

# OpenClaw + Codex CLI + tmux 澶?Agent 鏍囧噯鎿嶄綔鎵嬪唽锛? Agent锛?
## 0. 鐩爣绾︽潫锛堝繀椤婚伒瀹堬級

- OpenClaw 璐熻矗锛氶渶姹傚垎鏋愩€佷换鍔¤矾鐢便€佺姸鎬佹眹鎶ャ€佸闃呰皟搴︺€佹祴璇曠粨鏋滃悓姝ャ€?- **浠ｇ爜瀹炵幇蹇呴』鐢?Codex CLI 鍦?tmux 鎵ц**銆?- 涓讳細璇?涓绘ā鍨嬶細`gpt-5.3-codex-spark`锛孋odex 钀藉湴妯″瀷锛歚gpt-5.3-codex`銆?- 鏈嶅姟鍣ㄥ樊寮傦細鏅€氭湇鍔″櫒榛樿 `--full-auto`锛宍tokyo-claw` 閬囧埌 Landlock 闄愬埗鏃朵娇鐢?`--dangerously-bypass-approvals-and-sandbox`銆?- 姣忔璋冪敤鍙拷韪細`session_key`銆乣task_id`銆佸彉鏇存枃浠舵竻鍗曘€侀獙璇佸懡浠ゃ€佺粨鏋滅姸鎬併€?
## 0.1 榛樿宸ヤ綔妯″紡锛圤penClaw = 瑙勫垝鑰咃級

- 榛樿瑙掕壊瀹氫綅锛歚OpenClaw` 鍙仛闇€姹傛緞娓呫€佷换鍔℃媶鍒嗐€佽矾鐢卞垎鍙戙€佸鏍告祴璇曠紪鎺掋€佺粨鏋滄眹鎬汇€?- 缂栫爜杈圭晫锛歚OpenClaw` 涓嶇洿鎺ユ墽琛屼唬鐮佷慨鏀癸紱浠ｇ爜瀹炵幇缁熶竴璧?`tmux + Codex CLI`銆?- 鎵ц褰掑彛锛歚frontend-dev` 涓?`backend-dev` 鐨勫紑鍙戜换鍔″繀椤婚€氳繃 `run-with-skills.sh` 瑙﹀彂銆?- 澶辫触鍥炶矾锛歚reviewer` 鎴?`tester` 涓嶉€氳繃鏃讹紝浠呭洖娴佺粰寮€鍙戜唬鐞嗕慨澶嶏紝涓嶇敱 `main/coordinator` 鐩存帴鏀逛唬鐮併€?- 寮哄埗鎷︽埅锛歚main/coordinator` 鏀跺埌鈥滅洿鎺ユ敼浠ｇ爜鈥濊姹傛椂锛屽繀椤诲厛鏀瑰啓涓轰换鍔″崟骞跺垎鍙戠粰 `frontend-dev/backend-dev`锛岀姝㈠湪褰撳墠浼氳瘽鐩存帴浜у嚭浠ｇ爜琛ヤ竵銆?
## 0.2 浠ｇ爜淇敼鍚庢祴璇曢棬绂侊紙寮哄埗锛?
- 鍚庣闂ㄧ锛氳嚦灏戞墽琛屾帴鍙?鍗曞厓娴嬭瘯骞惰褰曠粨鏋溿€?- 鍓嶇闂ㄧ锛氳嚦灏戞墽琛屾瀯寤轰笌鍏抽敭椤甸潰鍐掔儫楠岃瘉銆?- 鑱旇皟闂ㄧ锛氳嚦灏戣鐩?1 鏉′富娴佺▼锛堝鐧诲綍/閴存潈锛変笌 1 鏉″紓甯告祦绋嬨€?- 鍙戝竷闂ㄧ锛氫换涓€闂ㄧ澶辫触锛岀姸鎬佸繀椤讳负 `need_fix`锛屼笉寰楄繘鍏?`deployer` 鍙戝竷闃舵銆?
## 1. 鐜涓庝緷璧栵紙鏈€灏忓彲杩愯锛?
```bash
dnf install -y cmake gcc gcc-c++ make git curl
node -v || curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
npm install -g openclaw
openclaw setup
mkdir -p ~/.openclaw/workspace
mkdir -p ~/.openclaw/workspace-coordinator ~/.openclaw/workspace-doc-writer ~/.openclaw/workspace-frontend-dev ~/.openclaw/workspace-backend-dev ~/.openclaw/workspace-reviewer ~/.openclaw/workspace-tester ~/.openclaw/workspace-deployer
codex --help > /tmp/codex-help.txt
```

### 1.1 Selenium 娴忚鍣ㄤ笌瀛椾綋渚濊禆锛堥粯璁ゆ祴璇曟爤锛?
褰?`tester` 闇€瑕佹墽琛屾祻瑙堝櫒鑷姩鍖栧洖褰掓椂锛岄粯璁や娇鐢?Selenium锛汸laywright 浠呯敤浜庢埅鍥捐瘖鏂垨 Selenium 鏃犳硶绋冲畾澶嶇幇鏃剁殑鍏滃簳銆?
```bash
# Selenium 娴嬭瘯渚濊禆锛堟帹鑽愶級
python -m pip install -U selenium webdriver-manager pytest pytest-xdist

# Chromium/Chrome锛堟寜鍙戣鐗堜簩閫変竴锛?sudo apt-get install -y chromium-browser || sudo dnf install -y chromium

# 涓枃瀛椾綋锛堟寜鍙戣鐗堜簩閫変竴锛?sudo apt-get install -y fonts-noto-cjk || sudo dnf install -y google-noto-sans-cjk-fonts

# 鍙€夛細Playwright 鍏滃簳鑳藉姏锛堜粎鍦ㄩ渶瑕佹椂瀹夎锛?npx playwright install --with-deps chromium
```

## 2. `openclaw.json` 鏍稿績妯℃澘锛堝彲鐩存帴澶嶅埗锛?
```json
{
  "meta": {
    "lastTouchedVersion": "2026.2.26",
    "lastTouchedAt": "2026-02-26T08:00:00.000Z"
  },
  "models": {
    "providers": {
      "openai-codex": {
        "baseUrl": "https://api.openai.com/v1",
        "api": "openai-completions",
        "apiKey": "<OPENAI_API_KEY>",
        "models": [
          { "id": "gpt-5.3-codex-spark", "name": "GPT-5.3 Codex Spark" },
          { "id": "gpt-5.3-codex", "name": "GPT-5.3 Codex" }
        ]
      },
      "glmcode": {
        "baseUrl": "https://open.bigmodel.cn/api/coding/paas/v4",
        "api": "openai-completions",
        "apiKey": "85d7fd33030d4925a6aae6e31a450e88.mrKxCoSOwRj7jsHo",
        "models": [
          { "id": "glm-5", "name": "GLM-5" }
        ]
      },
      "kimicode": {
        "baseUrl": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "api": "openai-completions",
        "apiKey": "<REDACTED_API_KEY>",
        "models": [
          { "id": "kimi-k2.5", "name": "Kimi K2.5" }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": { "primary": "openai-codex/gpt-5.3-codex-spark" },
      "workspace": "/root/.openclaw/workspace",
      "maxConcurrent": 4,
      "subagents": {
        "maxConcurrent": 8,
        "maxChildrenPerAgent": 5,
        "maxSpawnDepth": 2
      },
      "thinkingDefault": "high",
      "timeoutSeconds": 300
    },
    "list": [
      {
        "id": "main",
        "default": true,
        "name": "澶ф€荤",
        "workspace": "/root/.openclaw/workspace",
        "model": { "primary": "openai-codex/gpt-5.3-codex-spark" },
        "subagents": {
          "allowAgents": ["coordinator", "doc-writer", "frontend-dev", "backend-dev", "reviewer", "tester", "deployer"]
        }
      },
      { "id": "coordinator", "name": "coordinator", "workspace": "/root/.openclaw/workspace-coordinator", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } },
      { "id": "doc-writer", "name": "doc-writer", "workspace": "/root/.openclaw/workspace-doc-writer", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } },
      { "id": "frontend-dev", "name": "frontend-dev", "workspace": "/root/.openclaw/workspace-frontend-dev", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } },
      { "id": "backend-dev", "name": "backend-dev", "workspace": "/root/.openclaw/workspace-backend-dev", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } },
      { "id": "reviewer", "name": "reviewer", "workspace": "/root/.openclaw/workspace-reviewer", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } },
      { "id": "tester", "name": "tester", "workspace": "/root/.openclaw/workspace-tester", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } },
      { "id": "deployer", "name": "deployer", "workspace": "/root/.openclaw/workspace-deployer", "model": { "primary": "openai-codex/gpt-5.3-codex-spark" } }
    ]
  },
  "tools": {
    "alsoAllow": ["lobster"],
    "codex_exec_access": "rw-all",
    "agentToAgent": {
      "enabled": true,
      "allow": ["main", "coordinator", "doc-writer", "frontend-dev", "backend-dev", "reviewer", "tester", "deployer"]
    },
    "exec": { "notifyOnExit": false }
  },
  "commands": { "native": true, "nativeSkills": false, "restart": true, "ownerDisplay": "raw" },
  "channels": {
    "telegram": {
      "enabled": true,
      "dmPolicy": "pairing",
      "allowFrom": [],
      "groupPolicy": "open",
      "groupAllowFrom": [],
      "groups": {
        "*": { "requireMention": false }
      },
      "botToken": "<TELEGRAM_BOT_TOKEN>",
      "streamMode": "partial",
      "blockStreaming": true
    }
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "loopback",
    "auth": {
      "mode": "token",
      "token": "300bedf3c61aa436a61d67a31d8b99"
    }
  }
}
```

## 3. Telegram 缇ょ粍绛栫暐锛堝綋鍓嶇敓浜ч厤缃級

- `groupPolicy: open`
- `groupAllowFrom: []`锛坥pen 妯″紡涓嶄娇鐢ㄧ櫧鍚嶅崟锛?- `dmPolicy: pairing`
- `allowFrom: []`
- 绉佽亰蹇呴』 `/pair` 鍚庢墠鑳戒娇鐢紙棣栨鍙厤鍚堢鐞嗗憳鎻愬墠閰嶅锛?- 閲嶈锛欱otFather 闇€鎵ц `/setprivacy -> Disable`锛屽惁鍒欑兢閲屾湭 @ 鏈哄櫒浜虹殑娑堟伅鍙兘琚?Telegram 鎷︽埅銆?
甯哥敤鍛戒护锛?
```bash
openclaw config set channels.telegram.groupPolicy open
openclaw config set channels.telegram.groupAllowFrom '[]'
openclaw config set channels.telegram.groups '{"*":{"requireMention":false}}'
openclaw config set channels.telegram.dmPolicy pairing
openclaw config set channels.telegram.allowFrom '[]'
openclaw config set channels.telegram.commands.native true
openclaw config set channels.telegram.commands.nativeSkills false
openclaw gateway restart
```

## 4. 8 Agent 瑙掕壊瀹氫箟锛堜笉鑳界簿绠€鐗堬級

### 4.1 瑙掕壊鎬昏

| Agent | 瑙掕壊 | 涓昏鑱岃矗 | 鎶€鑳戒富绾?| 杈撳嚭缁欒皝 |
|---|---|---|---|---|
| `main` | 澶ф€荤 | 闇€姹傜‘璁ゃ€佷换鍔＄紪鎺掋€佷笂涓嬫父鑱氬悎銆侀獙鏀堕棴鐜?| `agent-manager,requirements-clarity,smart-workflow,result-synthesizer` | 鐢ㄦ埛 |
| `coordinator` | 浠诲姟鍗忚皟 | 鍏堟媶鍒嗗啀鍒嗗彂锛屾帶鍒跺苟鍙戜笌浼樺厛绾?| `task-decomposer,smart-workflow,dispatching-parallel-agents,parallel-executor` | `frontend-dev/backend-dev/reviewer/tester/deployer/doc-writer` |
| `doc-writer` | 鏂囨。娌荤悊 | 闇€姹傛枃妗?瀹炴柦鏂囨。/楠屾敹璇存槑/鍙樻洿璇存槑 | `writing-plans,docx,changelog-generator,internal-comms` | `main` |
| `frontend-dev` | 鍓嶇寮€鍙?| Vue 浠诲姟瀹炵幇銆佺粍浠舵敼鍔ㄣ€侀〉闈㈣仈璋冮獙璇?| `frontend-design,feature-development,ui-ux-pro-max,verification-before-completion` | `reviewer` |
| `backend-dev` | 鍚庣寮€鍙?| API/妯″瀷/鏁版嵁搴?閴存潈/涓氬姟娴佺▼寮€鍙?| `feature-development,systematic-debugging,auto-fix,verification-before-completion` | `reviewer` |
| `reviewer` | 浠ｇ爜瀹℃牳 | 璐ㄩ噺瀹℃煡銆佸畨鍏ㄥ璁°€佷竴鑷存€у鏍搞€侀闄╁垎绾?| `requesting-code-review,receiving-code-review,systematic-debugging,verification-before-completion` | `main/backend-dev/frontend-dev/tester` |
| `tester` | 娴嬭瘯楠屾敹 | 鐢ㄤ緥璁捐涓庢墽琛屻€佸洖褰掗獙璇併€佸紓甯稿満鏅鏌ワ紙榛樿 Selenium锛?| `deployment-test,systematic-debugging,auto-fix,webapp-testing` | `main` |
| `deployer` | 鍙戝竷杩愮淮 | 鍙戝竷銆佸仴搴锋鏌ャ€侀儴缃插洖婊氥€佺伆搴︾瓥鐣?| `db-deploy,deployment-test,github-actions-runner,windows-fullstack-deploy` | `main` |

### 4.2 Agent 鑱岃矗缁嗚妭

#### `main`
- 杈撳叆锛歚main:task_id`銆佺敤鎴烽渶姹傘€佸巻鍙蹭笂涓嬫枃銆?- 琛屼负锛氬厛纭闇€姹傝竟鐣岋紝涓嶇‘璁や笉鎵ц銆?- 杈撳嚭锛氶樁娈电粨璁恒€佸垎鍙戞寚浠ゃ€佹眹鎬绘姤鍛娿€?- 瑙勫垯锛氫笉寰楃洿鎺ヤ慨鏀逛笟鍔′唬鐮併€?
#### `coordinator`
- 杈撳叆锛氭媶鍒嗗璞★紙鍔熻兘/椤甸潰/API锛夈€佽妯°€佺揣鎬ュ害銆?- 琛屼负锛氬苟鍙戣鍒掑墠鍚庣锛屽垎閰?`frontend-dev` 涓?`backend-dev`銆?- 杈撳嚭锛氭槑纭紑鍙戞竻鍗曘€佹帴鍙ｈ竟鐣屻€侀獙璇佹竻鍗曘€佸洖璺鏁帮紙鏈€澶?3 杞級銆?- 瑙勫垯锛氬彧鍙戣捣浠诲姟锛屼笉鍐欒惤鍦颁唬鐮併€?
#### `doc-writer`
- 杈撳叆锛氶渶姹傚垵绋裤€佸彉鏇磋鍒掋€?- 琛屼负锛氳緭鍑?`requirements/implementation/api.md`锛屽苟缁欏嚭楠屾敹鏍囧噯銆?- 杈撳嚭锛氬彲鍙戝竷鏂囨锛堥渶姹傘€佸疄鏂姐€佸洖褰掞級銆?- 瑙勫垯锛氭枃鏈唴蹇呴』鏈夆€滄帴鍙ｅ彉鏇存竻鍗曗€濆拰鈥滈闄╅」鈥濄€?
#### `frontend-dev`
- 杈撳叆锛氶渶姹傜墖娈点€丄PI 绾﹀畾銆佽璁¤鏄庛€?- 琛屼负锛氬湪 Codex tmux 浼氳瘽鍐呰惤鍦板墠绔彉鏇淬€?- 杈撳嚭锛氫慨鏀规枃浠跺垪琛ㄣ€佸墠绔獙璇佺粨鏋滐紙build/lint/鍏抽敭 UI 妫€鏌ワ級銆?- 瑙勫垯锛氭瘡娆′换鍔″繀椤诲甫 `commit` 寤鸿涓庡洖褰掕矾寰勩€?
#### `backend-dev`
- 杈撳叆锛氭帴鍙ｅ畾涔夈€佹暟鎹彉鏇寸害瀹氥€侀敊璇爜瑙勮寖銆?- 琛屼负锛氬湪 Codex tmux 浼氳瘽鍐呭畬鎴愭帴鍙ｅ紑鍙戙€侀壌鏉冦€侀獙璇併€?- 杈撳嚭锛欰PI 娓呭崟銆佺姸鎬佺爜瑙勮寖銆佽縼绉昏鏄庛€?- 瑙勫垯锛氱姝㈠彧鏀逛竴澶勫悗鏈悓姝ユ帴鍙ｆ枃妗ｃ€?
#### `reviewer`
- 杈撳叆锛氬紑鍙戞彁浜ゃ€丏iff銆佸叧閿枃浠躲€?- 琛屼负锛氫唬鐮佽川閲?瀹夊叏妫€鏌ワ紝杈撳嚭 `pass/reject/need_confirm` 涓庝慨澶嶄紭鍏堢骇銆?- 杈撳嚭锛歅0-P3 椋庨櫓鍒嗙骇锛屽繀椤讳慨澶嶉」娓呭崟銆?- 瑙勫垯锛氫竴寰嬬粰鍑哄彲鎵ц淇寤鸿锛屼笉瑕佸彧缁欐娊璞¤瘎璁恒€?
#### `tester`
- 杈撳叆锛氬凡瀹￠槄閫氳繃浠ｇ爜銆佹祴璇曠洰鏍囥€佸満鏅垪琛ㄣ€?- 琛屼负锛氭墽琛岃嚜鍔ㄥ寲+浜哄伐楠屾敹娓呭崟锛岃緭鍑烘姤鍛婏紱娑夊強娴忚鍣ㄨ嚜鍔ㄥ寲鏃堕粯璁よ蛋 Selenium锛堟樉寮忕瓑寰?鍙鐜拌剼鏈級锛屼粎鍦ㄦ埅鍥捐瘖鏂垨 Selenium 涓嶇ǔ瀹氭椂鍚敤 Playwright 鍏滃簳銆?- 杈撳嚭锛氶€氳繃鐜囥€佸け璐ョ敤渚嬨€佸鐜版楠ゃ€佸缓璁€?- 瑙勫垯锛氬け璐ユ椂蹇呴』杩斿洖 `need_fix` 骞堕檮澶辫触璇佹嵁銆?
#### `deployer`
- 杈撳叆锛氬緟涓婄嚎鍙樻洿銆丟it commit銆佸洖婊氱瓥鐣ャ€?- 琛屼负锛氭墽琛屾瀯寤恒€佽縼绉汇€佹湇鍔″仴搴锋鏌ュ拰鍥炴粴婕旂粌銆?- 杈撳嚭锛氶儴缃叉棩蹇椼€佸仴搴风姸鎬併€佹槸鍚﹀彲閫愭鐏板害銆?- 瑙勫垯锛氫换浣曠敓浜у奖鍝嶅姩浣滈兘瑕佺暀鐥曪紝闄勬娴嬪懡浠ゃ€?
### 4.3 杩愯鏃?Persona 鏂囦欢锛圫OUL.md锛夋槸寮虹害鏉?
浠ヤ笅鏂囦欢灞炰簬 **agent 杩愯鏃跺垎宸?琛屼负閰嶇疆**锛屼笉鏄笟鍔′唬鐮侊細

- `~/.openclaw/agents/main/agent/SOUL.md`
- `~/.openclaw/agents/coordinator/agent/SOUL.md`

浣滅敤锛?
- 瀹氫箟 agent 韬唤銆佽亴璐ｈ竟鐣屻€佽涓鸿鍒欍€佸己鍒惰鍒欍€?- 鎺у埗闇€姹傛緞娓呫€佷换鍔″垎鍙戙€佹槸鍚﹀厑璁哥洿鎺ヨ惤鍦板疄鐜般€?- 涓?`openclaw.json` 涓€璧峰喅瀹?multi-agent 瀹為檯琛屼负銆?
## 5. Agent 璋冪敤閾撅紙绀轰緥锛?
### 5.1 涓€鑸紑鍙戦摼璺?
```js
sessions_send("coordinator", {
  task_id: "TASK-2026-0226-001",
  task: "瀹炵幇鐧诲綍琛ㄥ崟骞惰ˉ榻愰敊璇彁绀?,
  session_key: "project-a-login",
  priority: "high",
  output: {
    format: "structured",
    need_summary: true
  }
}, 0)
```

`coordinator` 鍐呴儴鎷嗗垎锛?
```js
sessions_send("frontend-dev", {
  task_id: "TASK-2026-0226-001",
  task: "瀹炵幇鐧诲綍椤电粍浠朵笌閿欒鎻愮ず",
  session_key: "project-a-login-frontend",
  spec_ref: "docs/requirements/REQ-2026-..."
}, 0)

sessions_send("backend-dev", {
  task_id: "TASK-2026-0226-001",
  task: "瀹炵幇鐧诲綍鎺ュ彛涓庨壌鏉冭竟鐣?,
  session_key: "project-a-login-backend"
}, 0)
```

骞跺彂瀹屾垚鍚庤Е鍙戯細

```js
sessions_send("reviewer", "瀹℃牳鐧诲綍鍔熻兘锛堝惈鍓嶅悗绔竴鑷存€с€佽緭鍏ユ牎楠屻€佽竟鐣岋級", 60)
```

瀹℃牳閫氳繃鍚庡啀锛?
```js
sessions_send("tester", "鎵ц鐧诲綍鍔熻兘鍐掔儫+寮傚父鐢ㄤ緥锛岃緭鍑鸿鐩栫巼涓庡け璐ユ槑缁?, 120)
```

### 5.2 澶辫触鍥炶矾锛堝繀椤诲疄鐜帮級

- reviewer fail 鈫?`frontend-dev/backend-dev` 鏀跺埌 `need_fix`
- 淇瀹屾垚鍚庡洖鍒?`reviewer`
- tester fail 鈫?鍥炲埌寮€鍙戜慨澶嶏紝鍐?reviewer锛屽啀 tester
- 閲嶈瘯涓婇檺锛氭瘡涓樁娈垫渶澶?3 杞紝浠嶅け璐ュ崌绾т汉宸ヤ粙鍏?
### 5.3 瑙勫垝鑰呬紭鍏堝垎娴侊紙榛樿鎬绘祦绋嬶級

1. 鎵€鏈夎姹傞粯璁よ繘鍏?`main`锛堝叆鍙?Agent锛夈€?2. `main` 鍏堝垽鏂换鍔″鏉傚害锛氱畝鍗曚换鍔＄洿鎺ュ洖澶嶏紱涓?澶嶆潅浠诲姟杞粰 `coordinator`銆?3. `coordinator` 杈撳嚭缁撴瀯鍖栦换鍔″崟骞跺垎鍙戝埌鎵ц Agent銆?4. 鎵ц瀹屾垚鍚庡浐瀹氳繘鍏?`reviewer`锛堝鏌ワ級涓?`tester`锛堥獙鏀讹級銆?5. 楠屾敹閫氳繃涓旈渶瑕佷笂绾挎椂鍐嶈繘鍏?`deployer`銆?
### 5.4 闅惧害璇勪及瑙勫垯锛堢敱 `main/coordinator` 鍏卞悓閬靛惊锛?
璇勫垎缁村害锛堟瘡椤?0~2 鍒嗭紝鎬诲垎 0~8锛夛細

- 鍙樻洿鑼冨洿锛氬崟鏂囦欢 0锛涘妯″潡 2銆?- 渚濊禆鑰﹀悎锛氭棤鑱斿姩 0锛涘墠鍚庣鑱斿姩 2銆?- 椋庨櫓绛夌骇锛氭櫘閫氭枃妗?灞曠ず 0锛涢壌鏉?璧勯噾/鐢熶骇椋庨櫓 2銆?- 楠屾敹澶嶆潅搴︼細鍗曡矾寰?0锛涘鍦烘櫙鍥炲綊 2銆?
鍒ゅ畾锛?
- `0~2`锛氱畝鍗曚换鍔★紙鍙崟 Agent 澶勭悊锛夈€?- `3~5`锛氫腑绛変换鍔★紙寤鸿 `coordinator` 鎷嗗垎 2~3 瀛愪换鍔★級銆?- `6~8`锛氬鏉備换鍔★紙蹇呴』澶?Agent + 瀹℃牳娴嬭瘯闂幆锛夈€?
### 5.5 澶氶噸璋冪敤鏂规锛堣嚦灏戜繚鐣欎袱濂楋級

#### 鏂规 A锛歚sessions_spawn`锛堟帹鑽愰粯璁わ級

閫傚悎澶嶆潅浠诲姟锛岄渶鏄惧紡鍒涘缓瀛愭櫤鑳戒綋涓婁笅鏂囧苟淇濈暀杩借釜閾捐矾銆?
```js
sessions_spawn("coordinator", {
  task_id: "TASK-20260227-001",
  goal: "瀹炵幇鐧诲綍閾捐矾骞跺畬鎴愰獙鏀?,
  session_key: "login-20260227"
})
```

#### 鏂规 B锛歚sessions_send`锛堣交閲忓苟鍙戯級

閫傚悎涓瓑浠诲姟锛岀洿鎺ュ悜鎸囧畾 agent 鍙戦€佷换鍔°€?
```js
sessions_send("frontend-dev", { task_id, task: "瀹炵幇椤甸潰", session_key }, 0)
sessions_send("backend-dev", { task_id, task: "瀹炵幇API", session_key }, 0)
```

#### 鏂规 C锛欱inding 璺敱锛堥暱鏈熻嚜鍔ㄥ垎娴侊級

閫傚悎鍥哄畾 Telegram 缇ゆ垨鍥哄畾璐﹀彿鍏ュ彛銆傚叆鍙ｇ粦瀹氬埌 `main` 鎴?`coordinator`锛屽悗缁啀鐢卞崗璋冨櫒鎷嗗垎銆?
```bash
openclaw agents list --bindings
# 鏍规嵁涓氬姟鎶婄壒瀹?peer/chat 缁戝畾鍒?main 鎴?coordinator
```

#### 鏂规 D锛氬伐鍏峰伐浣滄祦锛堝彲閫夛級

閫傚悎閲嶅鎬ч珮娴佺▼锛屼娇鐢?`lobster` 浣滀负纭畾鎬х紪鎺掑櫒锛屼覆鑱斺€滄媶鍒?-> 寮€鍙?-> 瀹℃煡 -> 娴嬭瘯 -> 鍙戝竷鈥濄€?
### 5.6 鍒嗘祦鏄犲皠瑙勫垯锛坈oordinator 鎵ц锛?
- 鍚?`椤甸潰/UI/浜や簰/鍓嶇` -> `frontend-dev`
- 鍚?`API/鏁版嵁搴?閴存潈/鍚庣` -> `backend-dev`
- 鍚?`鏂囨。/璇存槑/闇€姹俙 -> `doc-writer`
- 寮€鍙戝畬鎴愬悗 -> `reviewer`
- 瀹℃牳閫氳繃鍚?-> `tester`
- 娴嬭瘯閫氳繃涓旈渶涓婄嚎 -> `deployer`

### 5.7 coordinator 杈撳嚭妯℃澘锛堝繀椤荤粨鏋勫寲锛?
```json
{
  "task_id": "TASK-YYYYMMDD-XXX",
  "difficulty": "simple|medium|complex",
  "goal": "涓€鍙ヨ瘽鐩爣",
  "subtasks": [
    {
      "owner": "frontend-dev",
      "deliverable": "鐧诲綍椤典笌閿欒鎻愮ず",
      "depends_on": [],
      "done_when": "build 閫氳繃涓斿叧閿氦浜掑彲鐢?
    }
  ],
  "acceptance": ["涓绘祦绋嬮€氳繃", "寮傚父娴佺▼閫氳繃"],
  "risk": ["閴存潈杈圭晫"],
  "rollback": "鎸夋ā鍧楀洖婊?
}
```

### 5.8 鐘舵€佹満锛堢粺涓€瀛楁锛?
`new -> planned -> in_dev -> in_review -> in_test -> ready_deploy -> done`

澶辫触璺緞锛?
- `in_review -> need_fix -> in_dev`
- `in_test -> need_fix -> in_dev`
- 鍥炶矾瓒呰繃 3 娆★細`blocked`锛堜汉宸ヤ粙鍏ワ級

### 5.9 濡備綍鍒ゆ柇鈥滅湡鐨勮Е鍙戜簡澶?Agent鈥?
鑷冲皯鍛戒腑浠ヤ笅涓€鏉℃墠绠楃湡瀹炲垎娴侊細

- 鏃ュ織鍑虹幇闈?`main` lane锛歚session:agent:<id>` 涓?`<id> != main`
- 鏃ュ織鍑虹幇瀛愭櫤鑳戒綋锛歚subagent` / `sessions_spawn` / `agent:<id>:subagent:<uuid>`
- `openclaw agents list --bindings` 鏄剧ず鏈夋晥璺敱骞跺湪杩愯鏃ュ織涓鍛戒腑

### 5.10 鍏抽敭璇嶈矾鐢辨墿灞曡瘝搴擄紙鍙洿鎺ョ敤浜庡垎娴侊級

浼樺厛绾э紙浠庨珮鍒颁綆锛夛細

1. 鏄惧紡鎸囧畾 agent锛堝 `/agent reviewer`锛? 
2. 楂樻潈閲嶅叧閿瘝鍛戒腑锛堝畨鍏?鏁呴殰/涓婄嚎绛夛級  
3. 鏅€氬叧閿瘝鍛戒腑  
4. 鏃犲懡涓洖閫€ `coordinator`锛堢敱瑙勫垝鑰呬簩娆″垽鏂級

鍐茬獊澶勭悊锛?
- 鍚屾椂鍛戒腑鍓嶇+鍚庣锛氫氦 `coordinator` 鎷嗘垚骞惰瀛愪换鍔°€?- 鍚屾椂鍛戒腑寮€鍙?瀹℃牳锛氬厛寮€鍙戯紙`frontend-dev/backend-dev`锛夛紝鍚庡鏍革紙`reviewer`锛夈€?- 鍚屾椂鍛戒腑娴嬭瘯+閮ㄧ讲锛氬厛娴嬭瘯锛坄tester`锛夛紝閫氳繃鍚庡啀閮ㄧ讲锛坄deployer`锛夈€?
#### `coordinator` 鍏抽敭璇嶏紙瑙勫垝/鎷嗚В/鎺掔▼锛?
`闇€姹俙, `鎷嗚В`, `浠诲姟鎷嗗垎`, `鎺掓湡`, `閲岀▼纰慲, `浼樺厛绾, `骞跺彂`, `渚濊禆`, `娴佺▼`, `鏂规`, `鏋舵瀯`, `鎶€鏈€夊瀷`, `宸ヤ綔娴乣, `璺嚎鍥綻, `鑼冨洿鐣屽畾`, `MVP`, `璇勪及`, `澶嶆潅搴, `璧勬簮鍒嗛厤`, `澶氫换鍔, `鍗忎綔`, `鍒嗗伐`, `鎺ㄨ繘`, `姊崇悊`, `璋冨害`

#### `doc-writer` 鍏抽敭璇嶏紙鏂囨。/璇存槑/瑙勮寖锛?
`鏂囨。`, `闇€姹傛枃妗, `璁捐鏂囨。`, `鎺ュ彛鏂囨。`, `API鏂囨。`, `瀹炴柦鏂囨。`, `鍙樻洿璇存槑`, `鍙戝竷璇存槑`, `README`, `鎵嬪唽`, `鎿嶄綔鎸囧崡`, `SOP`, `楠屾敹鏍囧噯`, `澶嶇洏`, `鎬荤粨`, `浼氳绾`, `鍛ㄦ姤`, `鍏憡`, `FAQ`, `娉ㄩ噴瑙勮寖`, `鍛藉悕瑙勮寖`, `瀵归綈鏂囨。`, `杩佺Щ璇存槑`, `鍗囩骇鎸囧崡`, `changelog`

#### `frontend-dev` 鍏抽敭璇嶏紙鍓嶇/椤甸潰/浜や簰锛?
`鍓嶇`, `椤甸潰`, `鐣岄潰`, `UI`, `UX`, `浜や簰`, `缁勪欢`, `鏍峰紡`, `甯冨眬`, `鍔ㄧ敾`, `鍝嶅簲寮廯, `閫傞厤`, `绉诲姩绔痐, `H5`, `Vue`, `React`, `琛ㄥ崟`, `鎸夐挳`, `寮圭獥`, `鍒楄〃`, `琛ㄦ牸`, `鍥捐〃`, `涓婚`, `鏆楅粦妯″紡`, `鍙闂€, `鍩嬬偣`, `鍓嶇鑱旇皟`, `娴忚鍣ㄥ吋瀹筦

#### `backend-dev` 鍏抽敭璇嶏紙鍚庣/API/鏁版嵁锛?
`鍚庣`, `鎺ュ彛`, `API`, `鏁版嵁搴揱, `妯″瀷`, `琛ㄧ粨鏋刞, `杩佺Щ`, `SQL`, `鏌ヨ`, `浜嬪姟`, `缂撳瓨`, `Redis`, `闃熷垪`, `娑堟伅`, `Celery`, `閴存潈`, `璁よ瘉`, `鎺堟潈`, `JWT`, `鏉冮檺`, `闄愭祦`, `骞傜瓑`, `閿欒鐮乣, `鏃ュ織`, `鎬ц兘`, `骞跺彂`, `N+1`, `绱㈠紩`, `閲嶆瀯`, `鍚庣鑱旇皟`

#### `reviewer` 鍏抽敭璇嶏紙瀹℃煡/瀹夊叏/璐ㄩ噺锛?
`瀹℃牳`, `瀹℃煡`, `review`, `浠ｇ爜璐ㄩ噺`, `瑙勮寖妫€鏌, `闈欐€佹鏌, `瀹夊叏`, `婕忔礊`, `娉ㄥ叆`, `XSS`, `CSRF`, `瓒婃潈`, `鏁忔劅淇℃伅`, `鍚堣`, `椋庨櫓`, `椋庨櫓鍒嗙骇`, `P0`, `P1`, `鎶€鏈€篳, `鍙淮鎶ゆ€, `鍙鎬, `杈圭晫鏉′欢`, `涓€鑷存€ф鏌, `diff 妫€鏌, `merge 鍓嶆鏌

#### `tester` 鍏抽敭璇嶏紙娴嬭瘯/楠屾敹/鍥炲綊锛?
`娴嬭瘯`, `楠屾敹`, `鍥炲綊`, `鍐掔儫`, `鍗曟祴`, `闆嗘垚娴嬭瘯`, `绔埌绔痐, `E2E`, `鎺ュ彛娴嬭瘯`, `鍦烘櫙娴嬭瘯`, `寮傚父鍦烘櫙`, `杈圭晫娴嬭瘯`, `鍘嬫祴`, `绋冲畾鎬, `澶嶇幇`, `bug閲嶇幇`, `缂洪櫡楠岃瘉`, `閫氳繃鐜嘸, `娴嬭瘯鎶ュ憡`, `鑷姩鍖栨祴璇昤, `selenium`, `playwright`, `web娴嬭瘯`, `楠岃瘉鑴氭湰`

#### `deployer` 鍏抽敭璇嶏紙鍙戝竷/杩愮淮/鍥炴粴锛?
`閮ㄧ讲`, `鍙戝竷`, `涓婄嚎`, `鐏板害`, `鍥炴粴`, `杩愮淮`, `鐜`, `CI`, `CD`, `娴佹按绾縛, `鏋勫缓`, `鎵撳寘`, `闀滃儚`, `瀹瑰櫒`, `K8s`, `Nginx`, `鏈嶅姟閲嶅惎`, `鍋ュ悍妫€鏌, `鐩戞帶`, `鍛婅`, `璇佷功`, `鍩熷悕`, `DNS`, `杩佺Щ鍙戝竷`, `鍙樻洿绐楀彛`, `鍙戝竷纭`

#### `main` 鍏抽敭璇嶏紙鍏ュ彛/鎬绘帶锛?
`甯垜`, `鎬庝箞鍋歚, `鍏堣鍒抈, `鍏堝垎鏋恅, `缁欐柟妗坄, `鏁翠綋鎺ㄨ繘`, `鍏ㄦ祦绋媊, `绔埌绔痐, `缁熶竴瀹夋帓`, `鎬昏`, `姹囨€籤, `鐘舵€乣, `杩涘害`, `鍗′綇浜哷, `寮傚父澶勭悊`, `鍗忚皟`, `璺ㄥ洟闃焋, `鍐崇瓥`, `浼樺厛澶勭悊`, `绱ф€

#### 璺敱鍏滃簳绛栫暐

- 鍛戒腑鐜?< 2 涓叧閿瘝锛氬厛鍥?`main` 杩涜涓€娆℃緞娓咃紝鍐嶈浆 `coordinator`銆?- 鏂囨湰鍖呭惈 `鍏堜笉瑕佹墽琛?鍏堣璁?鍏堟柟妗坄锛氬己鍒跺彧鍒?`main/coordinator`锛岀姝㈢洿鎺ヤ笅鍙戝紑鍙戙€?- 鏂囨湰鍖呭惈 `鐩存帴淇?椹笂鏀筦 浣嗘棤涓婁笅鏂囷細鍏?`main` 琛ラ綈楠屾敹鏍囧噯锛屽啀鍒嗗彂銆?
## 6. OpenClaw 涓?Codex 鍒嗗伐杈圭晫锛堥噸鐐癸級

### 6.1 鎵ц杈圭晫

| 鍦烘櫙 | 鎵ц鑰?|
|---|---|
| 闇€姹傛緞娓?鎸囦护鎷嗚В/瑙掕壊璺敱 | OpenClaw |
| 浠ｇ爜鐢熸垚 / 閲嶆瀯 / Bug 淇 | **Codex CLI锛坱mux锛?* |
| 瀹℃牳銆佹祴璇曘€佸彂甯冨喅绛?| OpenClaw reviewer/tester/deployer |

### 6.2 Codex 鎵ц妯″瀷

- 榛樿缁熶竴妯″瀷锛歚gpt-5.3-codex`锛堢ǔ瀹氬彲鎺э級
- 浼氳瘽淇濈暀锛氭瘡涓换鍔′娇鐢ㄧ嫭绔?`session_key` 涓庢棩蹇楃洰褰?- 鍛戒护鍏ュ彛锛歚run-with-skills.sh <agent> "<task>" <session_key>`

## 7. 涓撲笟鎶€鑳藉垎閰嶏紙鎸?Agent锛?
| Agent | 鏍稿績鎶€鑳?| 鎵╁睍鎶€鑳?| 鍏稿瀷鍦烘櫙 |
|---|---|---|---|
| `main` | `agent-manager`, `requirements-clarity`, `smart-workflow` | `result-synthesizer`, `intelligent-router` | 闇€姹傛緞娓呫€侀噷绋嬬涓庢渶缁堟眹鎬?|
| `coordinator` | `task-decomposer`, `smart-workflow` | `dispatching-parallel-agents`, `parallel-executor` | 澶氫换鍔℃媶瑙ｃ€佸苟鍙戝垎閰嶃€佷緷璧栫鐞?|
| `doc-writer` | `writing-plans`, `docx` | `changelog-generator`, `internal-comms`, `product-requirements` | 闇€姹?瀹炴柦/鍙戝竷璇存槑鏂囨。 |
| `frontend-dev` | `frontend-design`, `feature-development` | `ui-ux-pro-max`, `verification-before-completion`, `auto-fix` | 鍓嶇椤甸潰銆佷氦浜掋€佽仈璋冧慨澶?|
| `backend-dev` | `feature-development`, `systematic-debugging` | `auto-fix`, `verification-before-completion`, `mcp-builder` | API 寮€鍙戙€侀壌鏉冦€佹€ц兘涓庣ǔ瀹氭€т慨澶?|
| `reviewer` | `requesting-code-review`, `receiving-code-review` | `systematic-debugging`, `verification-before-completion` | 浠ｇ爜瀹℃煡銆佸畨鍏ㄤ笌椋庨櫓鍒嗙骇 |
| `tester` | `deployment-test`, `systematic-debugging` | `auto-fix`, `webapp-testing` | 鍐掔儫銆佸洖褰掋€佸紓甯稿満鏅獙璇侊紙娴忚鍣ㄨ嚜鍔ㄥ寲榛樿 Selenium锛?|
| `deployer` | `db-deploy`, `deployment-test` | `github-actions-runner`, `windows-fullstack-deploy` | 鍙戝竷銆侀獙鏀躲€佸洖婊氫笌鐜娌荤悊 |

## 8. Codex 鎵ц鑴氭湰锛堢粺涓€鍏ュ彛锛?
鏂囦欢璺緞锛歚~/.openclaw/workspace/skills/codex-bridge/run-with-skills.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

AGENT="${1:-coding}"
TASK="${2:-璇锋寜涓氬姟瑕佹眰鎵ц寮€鍙戜换鍔"
PROJECT_DIR="${PROJECT_DIR:-/root/projects/DabaiPMwebsite}"
SESSION_KEY="${3:-$(date +%Y%m%d_%H%M%S)}"
HOSTNAME_NOW="${HOSTNAME_NOW:-$(hostname 2>/dev/null || echo unknown)}"
CODEX_MODEL="gpt-5.3-codex"
LOG_DIR="${HOME}/.openclaw/codex-runs/${SESSION_KEY}"

if [[ "$HOSTNAME_NOW" == *tokyo-claw* ]]; then
  EXEC_MODE="--dangerously-bypass-approvals-and-sandbox"
else
  EXEC_MODE="--full-auto"
fi

case "$AGENT" in
  main)
    ROLE_PROMPT="浣犳槸涓绘帶瑙勫垝鑰呫€傚厛婢勬竻闇€姹傝竟鐣屻€侀獙鏀舵爣鍑嗗拰椋庨櫓锛屽啀杈撳嚭鍙墽琛屼换鍔″崟骞跺垎鍙戙€傜姝㈢洿鎺ヤ慨鏀逛唬鐮併€?
    SKILLS="agent-manager,requirements-clarity,smart-workflow,result-synthesizer"
    ;;
  coordinator)
    ROLE_PROMPT="浣犳槸浠诲姟鍗忚皟瑙掕壊銆傚皢闇€姹傛媶鎴愬彲骞惰鎵ц鐨勫墠鍚庣浠诲姟锛屾爣娉ㄤ緷璧栧叧绯汇€佷紭鍏堢骇鍜屽洖璺鏁般€?
    SKILLS="task-decomposer,smart-workflow,dispatching-parallel-agents,parallel-executor"
    ;;
  doc-writer)
    ROLE_PROMPT="浣犳槸鏂囨。璐熻矗浜恒€傝緭鍑哄彲鐩存帴鍙戝竷鐨勯渶姹?瀹炵幇/楠屾敹璇存槑銆傚繀椤诲寘鍚渶姹傝寖鍥淬€佹帴鍙ｅ彉鏇淬€侀闄╅」銆佸洖褰掓竻鍗曘€?
    SKILLS="writing-plans,docx,changelog-generator,internal-comms,product-requirements"
    ;;
  frontend-dev)
    ROLE_PROMPT="浣犳槸鍓嶇寮€鍙戝伐绋嬪笀銆備娇鐢?Vue3/JS/CSS 钀藉湴椤甸潰/浜や簰銆備紭鍏堜繚璇佸彲缁存姢鎬с€佺敤鎴蜂綋楠屽拰杈圭晫澶勭悊銆?
    SKILLS="frontend-design,feature-development,ui-ux-pro-max,verification-before-completion,auto-fix"
    ;;
  backend-dev)
    ROLE_PROMPT="浣犳槸鍚庣寮€鍙戝伐绋嬪笀銆傚疄鐜?API銆佹潈闄愩€佹暟鎹簱涓€鑷存€с€侀敊璇爜涓庢棩蹇椼€備紭鍏堜繚璇侀壌鏉冦€佸畨鍏ㄣ€佸彲鍥炴粴銆?
    SKILLS="feature-development,systematic-debugging,auto-fix,verification-before-completion,mcp-builder"
    ;;
  reviewer)
    ROLE_PROMPT="浣犳槸浠ｇ爜瀹℃煡瑙掕壊銆傝緭鍑洪闄╁垎绾?P0-P3)銆侀棶棰樻竻鍗曘€佷慨澶嶄紭鍏堢骇銆佹槸鍚﹀彲鏀捐銆傝嫢涓嶉€氳繃璇风粰鍑哄彲鎵ц淇鐐广€?
    SKILLS="requesting-code-review,receiving-code-review,systematic-debugging,verification-before-completion"
    ;;
  tester)
    ROLE_PROMPT="浣犳槸娴嬭瘯楠屾敹瑙掕壊銆傝緭鍑哄啋鐑熴€佸洖褰掋€佽竟鐣屽拰寮傚父鍦烘櫙娴嬭瘯娓呭崟锛岀粰鍑洪€氳繃鐜囧拰澶辫触澶嶇幇銆傛祻瑙堝櫒鑷姩鍖栭粯璁?Selenium锛屼粎鍦ㄥ繀瑕佹椂浣跨敤 Playwright 鍏滃簳銆?
    SKILLS="deployment-test,systematic-debugging,auto-fix,webapp-testing"
    ;;
  deployer)
    ROLE_PROMPT="浣犳槸鍙戝竷杩愮淮瑙掕壊銆傝緭鍑洪儴缃叉楠ゃ€佸仴搴锋鏌ャ€佸洖婊氭柟妗堝拰缁撴灉缁撹銆傚け璐ユ椂缁欏嚭澶辫触鐐逛笌琛ユ晳鍔ㄤ綔銆?
    SKILLS="db-deploy,deployment-test,github-actions-runner,windows-fullstack-deploy"
    ;;
  *)
    ROLE_PROMPT="浣犳槸楂樻晥鎵ц鑰呫€傚厛缁欏彉鏇磋鍒掞紝鍐嶇粰鏈€灏忓彲楠岃瘉瀹炵幇锛屾渶鍚庣粰楠岃瘉缁撴灉銆?
    SKILLS="feature-development"
    ;;
esac

mkdir -p "$LOG_DIR"
TMUX_SESSION="codex-${AGENT}-${SESSION_KEY}"
TMUX_LOG="${LOG_DIR}/${AGENT}-${SESSION_KEY}.log"

PROMPT=$(cat <<EOF
浣犳湰娆′换鍔℃槸锛?{TASK}

璇峰姞杞藉苟涓ユ牸閬靛畧浠ヤ笅鎶€鑳界害鏉燂細${SKILLS}

瑙掕壊锛?${ROLE_PROMPT}

杈撳嚭瑕佹眰锛堝繀椤荤粰鍑猴級锛?1. 鍙楀奖鍝嶆枃浠跺垪琛紙鏂板缓/淇敼锛?2. 淇敼鍘熷洜涓庨獙璇佹€濊矾
3. 鎺ュ彛鍙樻洿璇存槑锛堝鏈夛級
4. 椋庨櫓涓庡洖閫€鐐?5. 寤鸿鎵ц鐨勯獙璇佸懡浠?6. 缁撹锛歱ass / reject / need_confirm

闄愬埗锛?- 鍙仛鏈换鍔¤寖鍥村唴鏀瑰姩
- 涓嶆搮鑷紩鍏ユ棤鍏虫灦鏋?- 濡傛湁涓嶇‘瀹氱偣璇峰垪鍑洪棶棰樺苟鏆傚仠
EOF
)

tmux new-session -d -s "$TMUX_SESSION" \
  "cd '$PROJECT_DIR' && codex $EXEC_MODE --model $CODEX_MODEL exec \"$PROMPT\" | tee '$TMUX_LOG'"

echo "agent=$AGENT"
echo "session=$TMUX_SESSION"
echo "log=$TMUX_LOG"
echo "mode=$EXEC_MODE"
echo "skills=$SKILLS"
```

### 8.1 鏍囧噯璋冪敤鏂瑰紡锛堝繀椤伙級

```bash
cd ~/.openclaw/workspace/skills/codex-bridge

# 鍗忚皟
bash run-with-skills.sh coordinator "姊崇悊鐧诲綍鍔熻兘鎷嗗垎骞剁‘璁よ竟鐣? "login-001"

# 鍓嶅悗绔苟琛?bash run-with-skills.sh frontend-dev "瀹炵幇鐧诲綍椤电粍浠朵笌琛ㄥ崟閿欒鎻愮ず" "login-001-fe"
bash run-with-skills.sh backend-dev "瀹炵幇鐧诲綍 API 涓庨壌鏉冭竟鐣? "login-001-be"

# 瀹℃牳涓庢祴璇?bash run-with-skills.sh reviewer "瀹℃煡鐧诲綍鍔熻兘瀹炵幇锛岀粰鍑烘槸鍚︽斁琛岀粨璁? "login-001-review"
bash run-with-skills.sh tester "鎵ц鐧诲綍鍔熻兘鍥炲綊娴嬭瘯骞剁粰鎶ュ憡" "login-001-test"
```

## 9. tmux 鎵ц瑙勮寖锛堝叧閿級

- 鍏ㄥ眬瑙勫垯锛氫唬鐮佷换鍔″彧鑳介€氳繃 `tmux + run-with-skills.sh` 瑙﹀彂锛涗笉鍏佽鍦?OpenClaw 鐩存帴 `exec` 闀夸换鍔°€?- 鏃ュ織鐩綍锛歚~/.openclaw/codex-runs/<task_id>/`
- 浼氳瘽鍛藉悕锛歚codex-<agent>-<task_id>`
- 浠诲姟鍏抽棴锛氫細璇濈粨鏉熷悗淇濈暀鏃ュ織锛屼笉鑷姩娓呯悊

```bash
tmux ls
tmux capture-pane -pt <session_name> -n 300
tmux attach -t <session_name>
tmux kill-session -t <session_name>   # 纭瀹屾垚鍚庡啀鎵嬪姩娓呯悊
```

### 9.1 澶т换鍔″苟琛屾ā鏉匡紙鍓嶅悗绔苟琛?+ 鏃ュ織姹囨€伙級

```bash
TASK_ID=login-20260226-001
PROJECT_DIR=/root/projects/DabaiPMwebsite
LOG_DIR=~/.openclaw/codex-runs/$TASK_ID
mkdir -p "$LOG_DIR"

cd ~/.openclaw/workspace/skills/codex-bridge
bash run-with-skills.sh frontend-dev "寮€鍙戠櫥褰曢〉涓庡墠绔仈璋? "${TASK_ID}-fe"
bash run-with-skills.sh backend-dev "寮€鍙戠櫥褰?API 涓庨壌鏉冮摼璺? "${TASK_ID}-be"

tmux ls | grep "${TASK_ID}"
```

## 10. 璐ㄩ噺涓庡鐩樿姹?
### 10.1 蹇呴』杈撳嚭锛堟瘡娆?Codex 浠诲姟鍚庯級
- task_id
- 淇敼鏂囦欢
- 鑷鍛戒护锛堣嚦灏戜竴鏉★級
- 椋庨櫓涓庡洖閫€鐐?- 褰撳墠寤鸿鐘舵€侊細`pass / need_fix / blocked`

### 10.2 鍏ㄩ摼璺姸鎬佸懡浠?
```bash
openclaw agents list --bindings
openclaw config get tools.agentToAgent
openclaw agents status
openclaw channels status --probe
openclaw config get channels.telegram
```

### 10.3 琛屾儏涓績鏈嶅姟鍣ㄥ疄娴嬪熀绾匡紙2026-02-27锛?
鐩爣鏈嶅姟鍣細`hangqing-zhongxin`锛坄43.163.219.215`, 鐢ㄦ埛 `ubuntu`锛?
瀹炴祴缁撴灉锛堝凡鑴辨晱锛夛細

- OpenClaw 鐗堟湰锛歚2026.2.24`
- 閰嶇疆璺緞锛歚/home/ubuntu/.openclaw/openclaw.json`
- Agent 鏁伴噺锛歚8`锛坄main/coordinator/doc-writer/frontend-dev/backend-dev/reviewer/tester/deployer`锛?- 榛樿妯″瀷锛歚openai-codex/gpt-5.3-codex-spark`
- agentToAgent锛歚enabled=true`锛宎llow=8 涓?agent
- Telegram 璺緞锛歚channels.telegram`
- Telegram 绛栫暐锛歚dmPolicy=pairing`銆乣groupPolicy=open`
- Telegram 鍏抽敭椤癸細`botToken` 宸茶缃€乣commands.native=true`銆乣nativeSkills=false`
- SOUL 鏂囦欢锛歚main/coordinator` 鍧囧瓨鍦?
闇€瑕侀噸鐐瑰叧娉細

- 褰撳墠绛栫暐涓?`groupPolicy=open` + `groups.*.requireMention=false`銆?- 鑻ョ兢鑱婁笉鍥炲锛屼紭鍏堟鏌?BotFather privacy锛歚/setprivacy -> Disable`銆?- 鑻ユ湭鏉ュ垏鍥?`allowlist`锛屽繀椤绘樉寮忓啓鍏ュ厑璁哥兢 ID锛堢ず渚嬶級锛?
```bash
openclaw config set channels.telegram.groupAllowFrom '["-1003333097130"]'
openclaw config set channels.telegram.groupPolicy 'allowlist'
openclaw config set channels.telegram.groups '{"-1003333097130":{"requireMention":false}}'
openclaw gateway restart
```

### 10.4 SOUL 鏂囦欢鍙樻洿瀹¤娓呭崟锛堟瘡娆℃敼瀹屽繀鐪嬶級

```markdown
[SOUL 鍙樻洿瀹¤]
1) 鍙樻洿 agent: main / coordinator / 鍏朵粬
2) 鍙樻洿鏂囦欢: ~/.openclaw/agents/<agent>/agent/SOUL.md
3) 鏂板瑙﹀彂瑙勫垯: xxx
4) 鏂板绂佺敤瑙勫垯: xxx
5) 鏄惁褰卞搷鑷姩鍒嗗彂: 鏄?鍚︼紙褰卞搷鐐硅鏄庯級
6) 鏄惁褰卞搷鈥滃厛婢勬竻鍚庡垎鍙戔€? 鏄?鍚?7) 鍥炲綊妫€鏌ュ懡浠?
   - openclaw agents list --bindings
   - openclaw channels status --probe
    - openclaw config get channels.telegram
```

### 10.5 鏈嶅姟鍣ㄤ笂鐨勫叧閿枃浠朵綅缃?
- 涓婚厤缃細`~/.openclaw/openclaw.json`
- 瑙掕壊 Persona锛?- `~/.openclaw/agents/main/agent/SOUL.md`
- `~/.openclaw/agents/coordinator/agent/SOUL.md`
- `~/.openclaw/agents/doc-writer/agent/SOUL.md`
- `~/.openclaw/agents/frontend-dev/agent/SOUL.md`
- `~/.openclaw/agents/backend-dev/agent/SOUL.md`
- `~/.openclaw/agents/reviewer/agent/SOUL.md`
- `~/.openclaw/agents/tester/agent/SOUL.md`
- `~/.openclaw/agents/deployer/agent/SOUL.md`
- Codex 妗ユ帴鑴氭湰锛歚~/.openclaw/workspace/skills/codex-bridge/run-with-skills.sh`
- 缃戝叧鏃ュ織锛歚~/.openclaw/gateway.log`
- 杩愯鏃ュ織锛歚/tmp/openclaw/openclaw-*.log`

### 10.6 鍒嗘祦璇婃柇鏈€灏忓懡浠ら泦

```bash
openclaw agents list --bindings
openclaw config get agents.list
openclaw config get agents.defaults.subagents
openclaw config get tools.agentToAgent
openclaw channels status --probe
tail -n 300 ~/.openclaw/gateway.log | rg "session:agent:|subagent|sessions_spawn|lane="
```

## 11. 甯哥敤楠岃瘉妯℃澘锛堝彲鐩存帴绮樿创鍒扮兢閲屽洖鎶ワ級

- [瀹屾垚] `frontend-dev login-001-fe`: 淇敼 4 鏂囦欢锛屽畬鎴?form+閿欒鎻愮ず锛宍pnpm -C frontend build` 閫氳繃
- [寰呭] `backend-dev login-001-be`: 淇敼 3 鏂囦欢锛岀櫥褰曟帴鍙ｅ弬鏁版牎楠岃ˉ榻?- [淇] reviewer: P1 闂 2 涓紝瑕佹眰闄愬埗澶辫触閲嶈瘯娆℃暟
- [楠屾敹] tester: 鍏抽敭鐢ㄤ緥 6/6 閫氳繃锛岃竟鐣岀敤渚?2/2 閫氳繃
- [鏈€缁圿 main: 闇€姹傝寖鍥?100%锛岀瓑寰呬笂绾挎垨閮ㄧ讲鎸囦护

## 12. 鐗堟湰璁板綍

| 鏃ユ湡 | 鐗堟湰 | 鍙樻洿 |
|---|---|---|
| 2026-02-28 | v1.25.0 | tester 娴忚鍣ㄨ嚜鍔ㄥ寲榛樿绛栫暐鍒囨崲涓?Selenium锛孭laywright 璋冩暣涓哄厹搴曪紱鍚屾鏇存柊渚濊禆瀹夎娈点€乼ester 鑱岃矗銆佸叧閿瘝銆佹妧鑳芥槧灏勪笌鑴氭湰妯℃澘 |
| 2026-02-27 | v1.24.0 | 鏂板鈥滃叧閿瘝璺敱鎵╁睍璇嶅簱鈥濓細8 瑙掕壊楂樺瘑搴﹀叧閿瘝銆佷紭鍏堢骇銆佸啿绐佸鐞嗐€佸厹搴曠瓥鐣ワ紙鏀寔澶氶噸鍒嗘祦鏂规锛?|
| 2026-02-27 | v1.23.0 | 鏂板鈥滆鍒掕€呬紭鍏堝垎娴佲€濆畬鏁存柟妗堬細闅惧害璇勪及銆佸洓绉嶈皟鐢ㄨ矾寰勶紙spawn/send/binding/lobster锛夈€佺姸鎬佹満銆佸垎娴佸垽瀹氥€佹湇鍔″櫒鍏抽敭鏂囦欢璺緞涓庤瘖鏂懡浠?|
| 2026-02-27 | v1.22.0 | Telegram 缇ょ粍绛栫暐鏇存柊涓?`open`锛坄groups=*`锛夛紝琛ュ厖 BotFather privacy 鍏抽棴瑕佹眰涓?allowlist 鍥為€€绀轰緥 |
| 2026-02-27 | v1.21.0 | 鍦ㄦā鏉?`agents.list.main` 涓柊澧?`subagents.allowAgents`锛屼笌鏈嶅姟鍣ㄥ疄閰嶄繚鎸佷竴鑷?|
| 2026-02-27 | v1.20.0 | 鏂板鈥滆鎯呬腑蹇冨疄娴嬪熀绾匡紙閰嶇疆+agent+SOUL锛夆€濄€丼OUL 鍙樻洿瀹¤娓呭崟锛岃ˉ鍏?runtime persona 鏂囦欢寮虹害鏉熻鏄?|
| 2026-02-26 | v1.19.0 | 鏂板 Playwright/涓枃瀛椾綋鎸夐渶瀹夎璇存槑锛屽苟灏?tester 瑙掕壊琛ュ厖涓衡€滄祻瑙堝櫒鑷姩鍖栧墠鍏堣渚濊禆鈥?|
| 2026-02-26 | v1.18.0 | 瑙掕壊鎶€鑳藉垎閰嶅崌绾т负涓撲笟鐭╅樀锛岃剼鏈笌瑙掕壊瀹氫箟瀵归綈锛岀粺涓€鐘舵€佸瓧娈碉紙pass/need_fix/blocked锛?|
| 2026-02-26 | v1.15.0 | 鍥為€€鈥滆繃搴︾簿绠€鈥濈瓥鐣ワ紝鎭㈠瀹屾暣 8 Agent 瑙掕壊瀹氫箟銆佹妧鑳芥槧灏勩€乼mux+codex 鍙屽眰璋冪敤閾?|
| 2026-02-26 | v1.14.1 | tmux 涓?Codex 琛屼负琛ュ厖 |
| 2026-02-25 | v1.13.0 | 澶?Agent 閫氶亾涓庤秴鏃?鏉冮檺琛ラ綈 |

## 重试与收敛策略（最多 3 次）

### 1) OpenClaw Agent 调用重试
- `main/coordinator` 调用子 Agent 失败时，最多重试 3 次。
- 仅对临时性失败重试：超时、限流（429）、瞬时网络错误。
- 业务逻辑错误不盲目重试，先回传问题点再进入修复。

### 2) Codex CLI 执行重试
- 同一任务命令最多执行 3 次。
- 临时性失败（超时/限流/网络）可自动重试；代码错误必须先修复后再执行。
- 默认模型：`gpt-5.3-codex`；默认思考强度：`xhigh`。

### 3) 审核/测试循环上限
- 标准链路：开发 -> 审核 -> 测试。
- 审核不通过或测试不通过时，最多循环 3 轮。
- 第 3 轮仍失败：停止自动循环，输出失败摘要并请求人工决策。

### 4) 失败上报模板
- 失败阶段：`开发/审核/测试`
- 已重试次数：`1/2/3`
- 最后错误：`<error>`
- 建议动作：`人工介入 / 降级方案 / 回滚`

## 11. 测试-修复闭环（文档驱动）

### 11.1 目标

将“测试 -> 修复 -> 测试 -> 修复”改为**可追踪状态机**，由测试报告驱动任务再分配，直到通过或达到上限。

### 11.2 状态机

1. `coordinator` 建立任务：`TASK_ID` 与当前轮次 `R1`。
2. `frontend-dev/backend-dev` 按需求开发。
3. `reviewer` 审核（质量+安全+一致性）。
4. `tester` 执行测试并产出 `TEST_REPORT`。
5. `coordinator` 必须先读取 `TEST_REPORT`，仅根据失败条目分发修复任务。
6. 修复后回到 `reviewer -> tester`。
7. 最多 3 轮（`R1-R3`），第 3 轮仍失败则停止自动循环并上报人工决策。

### 11.3 测试报告文件规范

- 路径：`~/.openclaw/workspace/docs/reports/TEST_REPORT-<TASK_ID>-R<N>.md`
- 必填字段：`case_id` `module` `status` `error` `repro` `owner_hint`

推荐模板：

```md
# TEST_REPORT TASK-20260227-001 R2

## Summary
- total: 12
- passed: 10
- failed: 2

## Failed Cases
| case_id | module | status | error | repro | owner_hint |
|---|---|---|---|---|---|
| API-LOGIN-003 | auth-api | failed | 401 on valid token refresh | POST /auth/refresh ... | backend-dev |
| WEB-LOGIN-007 | login-page | failed | missing error hint | open /login and submit empty form | frontend-dev |
```

### 11.4 coordinator 分配规则（读报告后执行）

- `module` 含 `api/auth/db/model` -> `backend-dev`
- `module` 含 `ui/page/component` -> `frontend-dev`
- `error` 含 `xss/csrf/injection/越权/secret` -> `reviewer`（安全复核）
- 每个失败条目必须形成独立修复任务，并带 `case_id`

### 11.5 收敛与上限

- 默认最多 3 轮，禁止无限循环。
- 达到上限后输出：失败清单、根因、建议动作（人工介入/降级/回滚）。
- 结论状态仅允许：`PASS` / `FAIL_LIMIT_REACHED` / `NEED_MANUAL_DECISION`。

## 12. 多 Agent 技能治理（2主1备）

### 12.1 目标

提升多 Agent 路由稳定性，避免技能过多导致提示词稀释与职责重叠。

### 12.2 强制规则

1. 每个 Agent 固定 `2 个主技能 + 1 个备技能`，禁止无限扩张技能池。
2. `reviewer` 必须执行安全优先审查，覆盖鉴权、输入校验、敏感信息、越权与注入风险。
3. `tester` 的 `auto-fix` 默认仅用于生成修复建议与复现信息，不直接改主分支代码。
4. `deployer` 的技能按运行环境收敛：Linux 场景优先 `db-deploy/deployment-test`，`windows-fullstack-deploy` 仅作备选。
5. 若安全风险达到 `P0/P1`，必须由 `reviewer` 驳回并阻断发布链路。

### 12.3 推荐技能矩阵（2主1备）

| Agent | 主技能 A | 主技能 B | 备技能 | 备注 |
|---|---|---|---|---|
| coordinator | `task-decomposer` | `smart-workflow` | `dispatching-parallel-agents` | 仅拆分与调度，不写代码 |
| doc-writer | `writing-plans` | `doc-coauthoring` | `changelog-generator` | 文档与发布说明 |
| frontend-dev | `frontend-design` | `feature-development` | `verification-before-completion` | 前端实现与联调 |
| backend-dev | `feature-development` | `systematic-debugging` | `verification-before-completion` | API、鉴权、数据一致性 |
| reviewer | `requesting-code-review` | `receiving-code-review` | `systematic-debugging` | 质量+安全审查，含风险分级 |
| tester | `webapp-testing` | `deployment-test` | `auto-fix` | `auto-fix` 默认建议模式 |
| deployer | `db-deploy` | `deployment-test` | `github-actions-runner` | Linux 发布链路优先 |

### 12.4 reviewer 安全审查最小清单

- 鉴权边界：未授权访问、越权操作、角色绕过
- 输入安全：注入、XSS、CSRF、反序列化风险
- 敏感信息：密钥/token/个人信息泄露
- 接口一致性：前后端字段/错误码/状态码一致
- 风险分级：`P0/P1/P2/P3`，并给出放行结论

### 12.5 tester 执行边界

- 测试失败后输出结构化报告：`case_id/module/error/repro/owner_hint`
- 默认不直接提交代码修改；修复任务回流 `frontend-dev/backend-dev`
- 仅在明确授权时，才允许 `auto-fix` 直接落地修复

### 12.6 deployer 环境策略

- Linux 服务器：主用 `db-deploy + deployment-test`
- Windows 本地开发：仅在明确目标为 Windows 时启用 `windows-fullstack-deploy`

### 12.7 执行建议

- 路由命中后优先使用主技能，失败或不匹配再切到备技能。
- 单轮任务中每个 Agent 最多装载 3 个技能，避免上下文过长。

## 13. Memory 策略（云端 embedding + 本地检索兜底，不用本地模型）

### 13.1 适用结论

- 低配置服务器不启用本地 embedding 模型（避免 CPU/内存压力）。
- Memory 主能力使用云端 embedding（推荐 `OpenRouter + baai/bge-m3`）。
- 云端失败时不切本地模型，而是退化为：
  - 会话历史读取（`sessions_history`）
  - Markdown 关键词检索（`MEMORY.md` + `memory/*.md`，fts-only）

### 13.2 推荐配置（生产）

```json
{
  "agents": {
    "defaults": {
      "memorySearch": {
        "enabled": true,
        "provider": "openai",
        "model": "baai/bge-m3",
        "fallback": "none",
        "remote": {
          "baseUrl": "https://openrouter.ai/api/v1",
          "apiKey": "<OPENROUTER_API_KEY>"
        },
        "sync": { "watch": true }
      }
    }
  }
}
```

### 13.3 禁止项（当前标准）

- 不配置 `memorySearch.local.modelPath`
- 不启用 `fallback: "local"`
- 不在低配置机器上下载/运行本地 embedding GGUF 模型

### 13.4 运维检查命令

```bash
# 查看 memory 状态
openclaw memory status

# 重建索引（必要时）
openclaw memory index --agent main

# 关键验证：云端失败时应退化为 fts-only，而不是拉起本地模型
openclaw memory search --agent main "关键词"
```

判定标准：
- 正常：`provider=openai` 且可返回语义相关结果
- 降级：`provider=none` + `mode=fts-only`（仍可关键词检索）

