# PITFALLS

## 2026-05-07 - 不要把方案质量 blocker 当成实现前硬停

类型：pitfall
范围：`solution_review.md`、`solution_review_soft_gate.md`、`code_execution`、`code_review`
事实：用户确认方案侧 review 应该长期吸收和改进，而不是普通计划问题一出现就停住。旧链路会把 `solution_review` 的 `requires_revision` 一律阻断，导致方案质量问题、路径缺口、验收命令缺口和 docs/memory 断言不足被反复卡在方案阶段。现在这些属于软门禁：先记录、吸收、继续实现，再由 code_review 检查是否按要求改对。高风险策略动作也不应因为出现关键词永久停住；它们应进入人工确认和后续 reviewer/测试门禁。凭证/密钥/cookie/auth-state、force push 和破坏性生产数据仍是实现前硬边界。
证据：新增 `solution_review_soft_gate.md` artifact 与 `PIPELINE_SOLUTION_REVIEW_SOFT_GATE_FILE`；普通 blocker 测试通过并继续到 code_execution，凭证 blocker 测试仍硬停。
最后验证：2026-05-07 15:32
复用建议：以后看到“方案评审未通过”先看 blocker 类型。计划质量问题要进入 soft gate；安全/凭证/破坏性生产问题才硬停。用户纠正“这个不是高风险”时，应沉淀到风险分类和项目记忆，不要简单删除整套风险门禁。

## 2026-05-07 - solution_review 不能只返回泛化失败结论

类型：pitfall
范围：`solution_review.md`、`failure_summary.md`、`delivery_plan.json`、`revise_solution` 自动回流
事实：`discord-spreadagent-20260507T061852834760Z` 已经进入 `solution_review`，两个 reviewer fallback 后都产出有效 `requires_revision`，所以阻塞是正确的；问题在于旧输出没有把未通过原因变成下一轮可执行修订契约，导致状态卡反复只说“方案评审未通过 / revise_solution”，而 `delivery_plan.json` 仍可能保留 root 日期文件、缺失 `create_if_missing` 理由、模板化 `Inspect ... define gap` 步骤、docs/memory 内容断言不足、compileall 缺 `scripts`、git publish containment 和 Discord manual acceptance gate 不完整等问题。
证据：修复后 runner 会提取 reviewer blocker 并输出 `Joint Non-Pass Reasons` 与 `Complete Revision Plan`；`plan_path_rejection_reason()` 拒绝根目录日期文件；`create_if_missing_rationale()` 覆盖 docs 与 SmartMulti 项目 memory 目标；`implementation_step_description()` 为已知 API、scripts、docs/memory/todo/done 生成具体动作；`configured_verification_commands()` / `explicit_verification_commands()` 补齐 `scripts` compileall、内容断言和 git containment。回归 replay 证明上述缺口已收敛。
最后验证：2026-05-07 15:02
复用建议：后续方案评审卡住时，先判断是“reviewer provider/model 失败”还是“有效 reviewer 真实 blocker”。前者修 fallback；后者必须让 reviewer 输出完整修订方案，并让 `delivery_plan.json` 自动吸收，不能通过降低 review 标准、删除 reviewer 或重跑同一份方案绕过。

## 2026-05-07 - external_research 空失败不能等同于缺少联网资料

类型：pitfall
范围：`smart_arb_live_bridge.py`、nofx `/home/arbops/.hermes/pipeline-runs/<run_id>`、`research_report.md`
事实：run `discord-spreadagent-20260507T051921542201Z` 卡在 `external_research`，状态卡显示 live mode 需要 external research evidence，但 artifact 里实际只有 bridge 的最小失败输出：stdout 为 `LIVE_BRIDGE_STAGE: external_research` 与 `LIVE_BRIDGE_STATUS: fail`，stderr 为空，没有任何模型回答、诊断或外部资料错误。该类问题的根因是 Hermes stage 未产生可解析输出或 bridge 没有降级/诊断，不等同于“必须去联网查资料”。本轮需求是 nofx 工作流回归重试，source 只有 `discord:spreadagent`，本地上下文、项目记忆、Git 和 Graphify artifact 已足够判断“不需要外部资料核对”。
证据：修复后 bridge 只在纯本地来源且需求没有外部资料要求时合成 `NO_EXTERNAL_LOOKUP_NEEDED`；若存在 http/https source URL 或需求明确要求官方/外部/联网资料，则不会合成 pass。新增测试覆盖两条分支。
最后验证：2026-05-07 14:01
复用建议：以后 `external_research` 阶段失败要先分类：1. 有外部 URL/官方资料要求但 web-agent 没完成，继续修 research；2. 纯本地 workflow/runtime 回归且 Hermes 空失败，修 bridge/runtime 输出或使用本地证据降级；3. Hermes 返回内容但不含 pass/verdict，优先看 session 文件恢复与脱敏后的 assistant 输出。

## 2026-05-07 - Graphify 推荐验证命令不能进入 pre-execution 风险扫描

类型：pitfall
范围：`pre_execution_risk.json`、`graphify_scope_validation.md`、`delivery_plan.json.verification_commands`
事实：`graphify_scope_validation.md` 会展示 runner 推荐的安全扫描命令，该命令里可能含 `place_order`、`transfer`、`PRODUCTION_TRADING_ENABLED=true` 等敏感字符串。它们是验证规则，不是用户或方案的执行意图。旧逻辑把 graphify markdown 整体并入 pre-execution risk scan，导致 dry-run happy path 和真实 nofx run 被 `place_real_order` 误判为 high-risk。修复后 pre-execution 风险扫描只读取需求、目标文件、实施步骤、需求讨论/评审和方案评审；Graphify 仍单独通过 `scope_status=block` 触发 hard block，但不把推荐命令正文反向当作风险意图。
证据：`assess_pre_execution_risk()` 不再把 `graphify_scope_validation` markdown 并入 `scan_text`，但仍读取它判断 `graphify_scope_block`；`configured_verification_commands()` 在存在显式安全/git 命令时补回 `git diff --check` 和非文档任务默认 `compileall`，避免验收命令只剩安全扫描和 git containment；回归测试覆盖 dry-run happy path risk 为 `auto_execute`、README/tooling 和 code+docs 任务仍带 compileall、真实 nofx run replay 输出 `bad_targets=[]` 且 `commands_count=14`。
最后验证：2026-05-07 12:53
复用建议：以后新增验证命令、Graphify 报告或安全扫描报告时，必须先判断它属于“验证证据/规则”还是“方案执行意图”。风险扫描应只吃意图字段；验证规则里的敏感词只能用于阻止新增危险 diff，不能阻止 pipeline 进入安全实现。

## 2026-05-07 - 安全边界和状态摘要不能反向触发风险门禁

类型：pitfall
范围：`pipeline_runner.py`、`smart_arb_pipeline_entry.py`、`delivery_plan.json`、`graphify_scope_validation.json`、`pre_execution_risk.json`
事实：自动生成的安全边界、状态摘要和安全扫描命令里经常会出现“真实交易/下单/划转/提现/资金/credential/transfer”等词。它们不是执行意图，不能被当成 high-risk 阻塞条件。旧逻辑把整个 `delivery_plan.json` 与状态卡文本一起扫，导致“没有启动真实交易”“文本中仍出现真实交易关键词”“新增行扫描 transfer”这类元信息反向触发 `risk_gate` 或 Graphify block。修复后 pre-execution 风险扫描只看用户需求、目标文件和实施步骤；Graphify 只扫可执行步骤；entry 会剥离“触发点/原因/自动修复判断”这类历史状态摘要。正向 `PRODUCTION_TRADING_ENABLED=true`、启用真实交易、真实下单、资金划转或读取凭证仍会触发 high-risk。
证据：`pre_execution_plan_scan_text()` 只返回 `target_files` 与 `implementation_steps`；`scope_scan_text_from_plan()` 不再扫描 `verification_commands` / `risk_boundaries` / `release_gates`；`SAFE_DOCUMENTATION_HISTORY_PATTERNS` 新增状态摘要清洗。回归测试覆盖纯否定安全状态不触发 high-risk、正向真实交易仍阻断、Graphify stock token 业务路径不被 token 字样误判。
最后验证：2026-05-07 10:58
复用建议：以后修门禁误伤时，不要直接扩大白名单或删掉风险关键词；应先把“执行意图字段”和“安全说明/状态摘要/验证命令”分开扫描，再保留正向高风险动作的 hard gate。

## 2026-05-07 - delivery_plan 低信任路径不能覆盖用户显式业务范围

类型：pitfall
范围：`delivery_plan.json.target_files`、`requirements_review.md`、`solution_review.md`
事实：reviewer 和历史 artifact 里常会混入 workflow 宿主文件名、pipeline artifact、项目记忆控制文件和组合路径。旧解析会把 `smart_arb_live_bridge.py`、`smart_arb_pipeline_entry.py`、`todo.md/done.md` 或裸 `PROJECT_PROFILE.md/DECISIONS.md` 当作业务 target，导致 solution reviewer 正确阻塞。修复后用户原始需求/修复上下文是高可信来源；requirements review/research/memory 只是低信任候选，必须过滤 workflow host basename、`scripts/openclaw-ops/*` 这类宿主路径、组合文件路径和否定上下文。若同一路径已经被用户显式接受，不再把低信任重复发现写成异常反馈。
证据：新增 `WORKFLOW_HOST_BASENAMES`、`combined_file_paths` 拒绝原因、`drop_accepted_target_findings()`；`PATH_CONTEXT_SPLIT_RE` 会在“只有/only”处分段，保留“只有 memory/... 才合法”中的正向 repo-relative memory 目标。回归测试覆盖 workflow 宿主 basename 与组合路径过滤、合法 memory 路径保留和显式 target 不重复异常反馈。
最后验证：2026-05-07 10:58
复用建议：solution review 提到 target drift 时，先看 `plan_findings.filtered_target_candidates` 的 source/reason/context。不要把 reviewer 举例、历史状态卡、pipeline artifact 或否定句中的路径直接写进 `target_files`。

## 2026-05-07 - reviewer 模型不可用不能误判为需求阻塞

类型：pitfall
范围：`smart_arb_live_bridge.py`、`pipeline_runner.py`、nofx review command reports
事实：`kimi-coding/kimi-k2.6` 这类 reviewer provider/model 可能返回 HTTP 404 或连续重试失败。旧逻辑把 reviewer-b 的 `missing_verdict` 合并成 `final verdict: requires_revision`，导致 reviewer-a 已通过、业务需求已清楚时仍被需求评审卡住。修复后 live bridge 会对 review 阶段逐个尝试 fallback 模型；runner 只把有效 reviewer 的明确 blocker 当作阻断，模型失败/缺 verdict 本身不再阻断已有有效通过结果。
证据：`run_hermes_stage()` 输出 `# reviewer fallback attempt failed` 并切换模型；`dual_review_pass()` 要求至少一个有效期望 verdict 且无明确 blocker；新增测试覆盖 Kimi 404 后 GLM 通过、单有效 reviewer 放行和具体 blocker 仍阻断。
最后验证：2026-05-07 00:55
复用建议：排查 `reviewer-b provider/model ... HTTP 404` 时，不要先降低需求质量门禁或要求人工确认；先确认 fallback 链是否配置、实际使用的 provider/model 是否写入 command report，以及是否存在真实 `requires_revision` finding。

## 2026-05-06 - 混合句风险清洗不能整行丢弃真实交易请求

类型：pitfall
范围：`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、`pre_execution_risk.json`、nofx `smart-arb-pipeline`
事实：旧 `scrub_negated_risk_lines()` 以整行维度处理风险文本。若用户或 agent 在同一句里写“允许真实交易下单，但不读取凭证”，整行会因为包含否定式凭证边界被丢弃，导致真实交易/下单没有进入 pre-execution high-risk 分类。修复后先剥离纯否定风险列表，再按中英文标点和转折/并列词切分子句；纯否定安全边界被删除，但正向 `PRODUCTION_TRADING_ENABLED=true`、真实交易、真实下单仍触发 high-risk。人工确认后 `execution_decision=confirmed_execute`，未确认仍阻塞。
证据：新增 `test_pre_execution_risk_keeps_positive_trading_when_same_line_has_negated_credentials` 覆盖“允许真实交易下单 smoke，不读取或打印凭证”仍判 high；新增 `test_pre_execution_risk_ignores_pure_negated_trading_and_credentials` 覆盖“不启动真实交易、不下单、不划转、Do not place orders, transfer funds, or enable live trading”仍判 low。本地 `test_project_delivery_pipeline_runner` 55 项 OK，入口/backlog/installer/profile 58 项 OK；nofx 远端定向 62 项 OK；高风险确认 smoke `cli-spreadagent-20260506T153935576001Z` 验证 high-risk confirmed 继续执行。
最后验证：2026-05-06 23:40
复用建议：以后遇到风险误判时不要回到“整行丢弃”或简单关键词删除；必须按子句区分否定安全边界与正向高风险动作，并同时覆盖“纯否定不阻塞”和“混合句正向风险仍识别”两类测试。

## 2026-05-06 - 高风险确认写入 Task Center 但未透传到 pipeline 会导致重复阻断

类型：pitfall
范围：`human_inbox.py`、`backlog_runner.py`、`smart_arb_pipeline_entry.py`、`pipeline_runner.py`
事实：人工确认只写在 Task Center 的 `human_confirmed=true` 不足以让 pipeline 继续。旧链路里 `backlog_runner` 即使用人工确认选中任务，也没有把确认传给 `smart_arb_pipeline_entry.py`；`pipeline_runner.py` 的 `risk_gate` 也没有确认输入，因此高风险方案在用户确认后仍会阻塞到 `await_human_confirmation`。已新增 `--human-risk-confirmed` 并贯通入口、runner 和风险门禁。
证据：`backlog_runner.py` 已确认高风险候选会设置 `human_risk_confirmed` 并追加 `--human-risk-confirmed`；`smart_arb_pipeline_entry.py` 会把该参数传给 runner；`pipeline_runner.py` 写入 `human_confirmation_confirmed` 与 `confirmed_execute`；`test_confirmed_high_risk_task_passes_human_risk_flag_to_pipeline`、`test_main_passes_human_risk_confirmation_to_runner`、`test_high_risk_plan_runs_after_human_risk_confirmation` 覆盖该链路。
最后验证：2026-05-06 22:58
复用建议：以后不要通过删除高风险扫描解决“确认后仍阻拦”；正确做法是保留 high-risk 分类，确认后传递明确凭证，并让后续测试、review、部署和发布门禁继续工作。

## 2026-05-06 - 双 reviewer 同模型会被判定为伪双审

类型：pitfall
范围：`dual_review_pass()`、nofx live bridge reviewer command report
事实：该问题在 2026-05-06 表现为两个 reviewer 都使用 `openai-codex/gpt-5.5` 时会被判定为伪双审。入口已将 reviewer-b 默认设为 `kimi-coding/kimi-k2.6`，smoke echo/hybrid 输出也补齐 provider/model。2026-05-07 起，同模型/缺失第二路只作为质量降级信号；如果至少一个有效 reviewer 通过且没有明确 blocker，不再因为第二路模型失败或重复模型而硬阻断。
证据：`test_dual_review_prefers_but_does_not_require_distinct_reviewer_models` 覆盖同模型降级；`test_main_defaults_reviewer_b_to_distinct_model` 覆盖入口默认不同模型；`hermes_profile_smoke.py` 的 `echo_outputs()` 和 `with_reviewer_role()` 会补 reviewer provider/model。
最后验证：2026-05-06 22:58
复用建议：排查 review 卡住时，先读 `command-runs/requirements_review-*.json`、`solution_review-*.json` 或 `code_review-*.json` 的 metadata 和 `reviewer_fallback` 输出，确认是运行时降级还是有效 blocker。

## 2026-05-05 - graphify 不读 .gitignore，项目级排除必须写 .graphifyignore

类型：pitfall
范围：`.graphifyignore`、`graphify-out/`、`vendor/`、项目知识图谱索引
事实：graphify 的扫描边界由 `.graphifyignore` / `.graphifyinclude` 控制，不会自动沿用 `.gitignore`。本仓库首次直接运行 `graphify update .` 时，因为没有 `.graphifyignore`，`vendor/` 被纳入扫描，导致 7675 个支持文件中 7029 个来自 `vendor`，生成图达到 38625 nodes / 100707 edges，`graph.html` 因超过 5000 节点限制被跳过，God Nodes 出现 `str()` / `print()` 等第三方噪声。已新增 `.graphifyignore` 排除 `vendor/`，并删除旧 `graphify-out/` 后重新生成 AST-only 图。
证据：新增 `.graphifyignore` 内容为 `vendor/`；重新运行 `graphify update .` 后输出 `4414 nodes, 8324 edges, 295 communities` 且生成 `graph.html`；`graphify.detect` 复核 `total_files=646`、`graphifyignore_patterns=1`、`vendor_detected=false`；读取 `graphify-out/graph.json` 复核 `vendor_nodes=0`。
最后验证：2026-05-05 21:16
复用建议：后续给任意项目启用 graphify 前，先按项目边界写 `.graphifyignore`，至少排除第三方源码快照、超大运行态目录和生成物；如果已有污染图，不能只跑 `graphify update`，要先删除旧 `graphify-out/` 或做干净重建，否则旧节点可能被保留。

## 2026-04-29 - WSL 访问 GitHub 偶发超时优先查 v2rayN/sing-box TUN 与 WSL2 NAT

类型：pitfall
范围：本机 WSL2 Ubuntu、Windows v2rayN/sing-box TUN、GitHub HTTPS/SSH、WSL Git 拉取链路
事实：本机 Windows 访问 GitHub 稳定，但 WSL 内部访问 `github.com:443` 会偶发 TCP 建连超时。该现象不是 GitHub 凭证问题，也不是 DNS 解析失败；失败时 `curl -v https://github.com` 已解析到 `20.27.177.113`，但卡在 `Trying 20.27.177.113:443...` 并在 connect timeout 后退出。当前 Windows 默认出口走 `singbox_tun`，v2rayN/sing-box 开启 TUN `StrictRoute=true`；即使用户已把 v2rayN `AllowLANConn` 打开到 `true`，运行态仍未在 WSL 网关 `172.27.112.1:10800/10806` 暴露可用 HTTP/SOCKS 入站。WSL2 只能经 NAT 间接穿 Windows TUN，因此仍会出现 WSL 侧 GitHub 443 偶发黑洞。WSL 全局 Git 还把 `git@github.com:` 重写到 HTTPS，导致原本可用的 SSH 22 也会被改走不稳定的 HTTPS 链路。
证据：WSL `curl` 连续 10 次访问 GitHub 时多次 `Connection timeout after 3001 ms`，`namelookup` 约 0.002s 且 `connect=0`；Windows `curl.exe` 连续 10 次访问同一 GitHub IP 全部 200；WSL `ssh -T git@github.com` 返回已认证成功，`ssh -p 443 git@ssh.github.com` 超时；WSL `/etc/resolv.conf` 为 WSL 自动生成 DNS，默认网关为 `172.27.112.1`；Windows `Find-NetRoute 20.27.177.113` 走 `singbox_tun`。2026-04-29 用户开启局域网访问后复查：v2rayN 配置显示 `AllowLANConn=True`，但 Windows 运行态只监听 `127.0.0.1:10806` 与 `172.18.0.1:12517`，WSL 到 `172.27.112.1:10800/10806` 均 `Connection refused`，到 `172.18.0.1:12517` 端口可达但 HTTP/SOCKS 代理协议不可用；WSL 直连 GitHub 12 次仍有 1 次 443 connect timeout。用户重启 v2rayN/sing-box 后复查：运行态仍只监听 `127.0.0.1:10806` 与 `172.18.0.1:<随机端口>`，WSL 到 `172.27.112.1:10800/10806/7890` 仍关闭；生成的 `binConfigs/config.json` 只有 `type=tun` inbound，`clash_api.external_controller=127.0.0.1:10806`，没有 SOCKS/HTTP/mixed inbound；GUI 配置里 `TunModeItem.EnableExInbound=false`。再次重启后复查：v2rayN 以 `rebootas` 启动，sing-box PID 已变化，但配置仍为 `EnableExInbound=false`、生成配置仍只有 `type=tun` inbound；WSL 到 `172.27.112.1:10800/10806/7890` 仍关闭，`172.18.0.1:<随机端口>` 可连但 HTTP 代理返回 reset；WSL 直连 GitHub 10 次出现多次 `502` 与 2 次 connect timeout，说明直连链路仍不稳定。最终打开 TUN `EnableExInbound=true` 后，生成配置出现 `type=mixed, listen=0.0.0.0, listen_port=10800`，Windows 运行态监听 `0.0.0.0:10800`，WSL 到 `172.27.112.1:10800` 可连；`curl --proxy socks5h://172.27.112.1:10800 https://github.com` 与 `http://172.27.112.1:10800` 均返回 200。已在 WSL 配置 `git config --global http.https://github.com.proxy socks5h://172.27.112.1:10800`，私有 origin 与公开 repo 各 5 次 `git ls-remote` 均成功。
最后验证：2026-04-29 17:25
复用建议：再次遇到 WSL 里 GitHub 偶发连不上时，先分层跑 `getent ahostsv4 github.com`、`curl -v --connect-timeout 3 https://github.com`、Windows `curl.exe` 对照和 `ssh -T git@github.com`。若只有 WSL HTTPS 443 失败，优先处理 WSL 与 Windows 代理的边界：v2rayN/sing-box 不仅要配置 `AllowLANConn=true`，还必须启用 TUN 的额外入站或等价 HTTP/SOCKS/mixed inbound，让生成配置中出现非 `tun` inbound，并在运行态看到 WSL 网关可访问的监听（本机稳定值为 `172.27.112.1:10800` / `0.0.0.0:10800`）。必须用 `curl --proxy socks5h://172.27.112.1:10800 https://github.com` 验证通过后，再设置 WSL GitHub 专用代理：`git config --global http.https://github.com.proxy socks5h://172.27.112.1:10800`；不要把“配置已勾选/服务已重启”误判成“WSL 已经走代理”。备选方案是取消 WSL Git 的 `git@github.com:` 到 HTTPS 重写，改用已验证可通的 SSH 22；不要先怀疑 GitHub 凭证或反复清 token。

## 2026-04-28 - capability registry 默认条目必须带 agent_id

类型：pitfall
范围：`skills/library/control-plane-ops/scripts/policy/task_capability_binding.py`、workflow selector / create-task 临时运行态
事实：`DEFAULT_CAPABILITY_REGISTRY.agent_defaults` 中不能存在缺少 `agent_id` 的条目；否则新临时 runtime 初始化 `PolicyEnforcer` 时会在 `normalize_capability_registry()` 报 `capability agent default #0 missing agent_id`，连 route-task / create-task 测试都会被初始化阶段阻塞。已删除 4 个无 `agent_id` 的无效默认条目，保留具名 agent 默认配置。
证据：修复前 `tests/scripts_openclaw_ops/test_workflow_selector.py` 和 `test_policy_task_manual_route.py` 均在 `PolicyEnforcer(paths)` 阶段失败；修复后 `python -m unittest tests.scripts_openclaw_ops.test_deadline_to_task_bridge tests.scripts_openclaw_ops.test_human_inbox tests.scripts_openclaw_ops.test_backlog_runner tests.scripts_openclaw_ops.test_policy_task_manual_route tests.scripts_openclaw_ops.test_workflow_selector -v` 15 项 OK。
最后验证：2026-04-28 21:40
复用建议：后续若临时 runtime 初始化在 capability registry 校验阶段失败，先检查 `agent_defaults` 是否全都有 `agent_id`，再排查 workflow selector 本身；不要把初始化失败误判成 route-task 逻辑失败。

## 2026-04-27 - Discord 只显示 Still working 不是 agent 没产出

类型：pitfall
范围：nofx Discord Hermes profile、`smart_arb_pipeline_entry.py`、`pipeline_runner.py`
事实：Discord 频道只看到 `Still working...` 通常是入口在同步等待长子进程，Hermes 只能发 runtime 心跳；不代表 pipeline 内部没有阶段进展。修复后入口默认轮询 `pipeline_state.json` 和 `command-runs/*.json` 输出 `# nofx 任务执行进度`，但 profile 必须实际调用新版 entry，并把状态卡回传频道。进度卡默认只输出阶段、当前命令状态和证据文件，不允许直接贴原始 agent stdout/stderr。
证据：`run_pipeline_command()` 在 progress interval 大于 0 时用 `subprocess.Popen` 轮询 run state；`pipeline_runner.py` 在 stage command 开始前写入 running state；`render_progress_update()` 从 state 和 command reports 生成中文进度卡；测试覆盖长命令执行中 state 已落盘、进度卡展示当前阶段和最近命令状态、默认不展示 command stdout、开启调试开关后才输出脱敏摘要。
最后验证：2026-04-27 19:10
复用建议：排查同类问题按三步走：1. 确认 profile SOUL/入口命令包含 `--progress-interval-seconds` 或默认未关闭进度；2. 看 run 目录 `pipeline_state.json` 是否持续刷新；3. 看 Discord gateway/profile 是否把中文状态卡分段发回频道。不要只凭 Hermes 心跳判断卡死；也不要为了证明“还在工作”把 `[Background process ...]` 或 command stdout/stderr 原文转发到聊天频道。

## 2026-04-27 - git_publish secret scan 只应阻断真实新增密钥值

类型：pitfall
范围：`smart_arb_live_bridge.py --stage git_publish`、staged diff secret scan、nofx Discord workflow publish gate
事实：`Secret-like content detected in staged diff` 不一定代表业务代码审查失败，也不一定代表存在真实密钥；旧扫描器会把 staged diff 里的 `DASHBOARD_BASIC_PASS`、`BASIC_PASS`、`rotatable-pass`、`Authorization: Basic Auth` 或“替换为实际强密码”等环境变量名、测试假密码和文档占位误判为 secret。修复后扫描器只看新增行，并按 value 上下文判断：真实 token、cookie、Authorization payload、OAuth secret、交易所 key、`.env` 实值、高熵随机串和 PEM private key 仍阻断；环境变量名、空值、`os.getenv(...)` 空默认、测试假密码、Markdown 行内 Basic Auth / Bearer token 占位说明放行；`os.getenv(..., '真实 token')` 与 `Authorization: Bearer live-real-short-token test only` 这类真实短值不放行。阻断报告必须输出脱敏的文件、行号、规则、风险等级和片段，不能只给笼统一句 secret-like。
证据：`staged_diff_secret_findings()` 解析 staged diff 新增行，输出 `file/line/rule/risk/blocking/snippet`；`run_git_publish()` 在 `## Secret Scan Findings` 中展示脱敏 findings；测试覆盖误报放行、真 secret 阻断、docs/tests/.env.example 中短真实密钥阻断、非占位 example assignment 仍阻断、hardcoded getenv fallback secret 阻断、PEM private key marker/material 阻断、删除旧 secret 行不阻塞、阻断报告不泄露原 secret、Basic Auth/Bearer token 文档占位不阻塞、真实短 Bearer 值即使带 test/example only 仍阻断、`fix_git_publish` 遇到 secret scan high/blocking finding 不自动回流。本地 `python -B -m unittest tests.scripts_openclaw_ops.test_smart_arb_live_bridge tests.scripts_openclaw_ops.test_smart_arb_pipeline_entry` 64 项 OK；`python -B -m compileall -q scripts/openclaw-ops skills/library/project-delivery-pipeline` 通过。
最后验证：2026-04-27 19:10
复用建议：后续遇到 `git_publish/fix_git_publish`，先判断失败文本是否来自 secret scan；如果是，必须定位 staged diff 的新增行和 finding rule。真实 secret/high-risk evidence 仍停人工确认。只允许调整 allowlist/context-aware scan，不允许关闭 hard block 或发布含真实 secret 的 diff。

## 2026-04-27 - 部署重启 gateway 前必须检查是否有活跃 Discord pipeline

类型：pitfall
范围：nofx `/home/arbops/.hermes/pipeline-runs`、`hermes-discord-arbitrage`、`hermes-discord-spread`、`smart-arb-pipeline`
事实：Discord 里反复出现 `Still working...` 通常是 gateway 正在等待后台 `smart-arb-pipeline` 子进程完成；它不是业务结论，只是等待心跳。2026-04-27 14:43 的 `discord-spreadagent-20260427T064306800586Z` 在 14:56 阻塞于 `code_review`，随后自动 repair run `discord-spreadagent-20260427T064306800586Z-repair1` 在 15:02 阻塞于 `requirements_review`。本次 14:55 部署重启了 `hermes-discord-spread`，正好发生在该任务等待期间，因此最终阻塞状态卡可能没有回到 Discord，用户只看到多轮 `Still working...`。
证据：远端 `pipeline_state.json` 显示原 run `status=blocked failed_stage=code_review next_action=return_to_code_execution updated_at=2026-04-27T06:56:13Z`，repair1 显示 `status=blocked failed_stage=requirements_review next_action=revise_requirements updated_at=2026-04-27T07:02:32Z`；`ps` 复核时已无 `smart-arb-pipeline` 活跃进程，两个 Discord gateway 均为 `running/connected`。
最后验证：2026-04-27 15:15
复用建议：部署或重启 gateway 前，先查 `ps -ef | grep smart-arb-pipeline` 和最近 `/home/arbops/.hermes/pipeline-runs/*/pipeline_state.json`；如有 running/新近未完成 run，先等它完成或手工记录 run id，再重启。遇到用户只看到 `Still working...`，先按 run id 打开 `pipeline_state.json` 和 `command-runs/*.json`，不要把心跳当成最终失败原因。

## 2026-04-27 - nofx 上跑 live bridge deployment 相关单测后要复核 smart-arb-api cwd

类型：pitfall
范围：`tests/scripts_openclaw_ops/test_smart_arb_live_bridge.py`、nofx tmux `smart-arb-api`、`scripts/openclaw-ops/smart_arb_live_bridge.py`
事实：在 nofx 安装态执行 `test_smart_arb_live_bridge` 的定向单测时，deployment 相关测试会输出并演练 `tmux has-session/kill-session/new-session -s smart-arb-api` 以及 `curl` smoke。虽然本次最终核对 `smart-arb-api` 的 pane cwd 仍是 `/home/arbops/projects/SmartMultiPlatformArbitrage/智能多平台套利`，但这类测试后必须显式复核，不能只看 HTTP smoke。
证据：2026-04-27 远端安装验证中，53 项定向单测 OK；随后通过 `tmux list-panes -t smart-arb-api -F '#{pane_pid}|#{pane_current_path}|#{pane_start_command}'` 确认 cwd 为 SmartMultiPlatformArbitrage 的 `智能多平台套利` 目录，进程命令为 `/home/arbops/.venvs/smart-arbitrage/bin/uvicorn api.main:app --host 127.0.0.1 --port 18080`。
最后验证：2026-04-27 14:58
复用建议：nofx 服务器上验证 live bridge 时，优先用 `compileall`、安装器测试和 echo smoke；如运行包含 deployment 的单测，测试后必须检查 tmux pane cwd、uvicorn 进程 cwd 和 `/health`，必要时按 `smart-arb-nofx-live-evidence-bridge.md` 的标准命令重启内控 API。

## 2026-04-27 - 工作流自身不能通过同一个 Discord pipeline 自修

类型：pitfall
范围：nofx `spreadagent` / `arbitrageagent` SOUL、`smart-arb-pipeline`、`pipeline_runner.py`、SmartMultiPlatformArbitrage 主工作区
事实：用户明确说“不要走工作流”“可以绕过”或“直接修工作流”时，旧 SOUL 仍把请求包装成新的 coordinator pipeline，导致 `discord-spreadagent-20260427T072912161741Z` 与后续 `discord-spreadagent-20260427T074448323797Z` 继续自修。该模式会在旧 runtime 上反复读取/生成 artifact，并可能把未通过 review 的业务补丁留在 SmartMulti 主工作区。
证据：远端进程曾显示两个 self-repair run 仍在执行；SmartMulti 工作区残留 `multi_exchange_arbitrage.py`、`execution_orchestration.py`、`tests/test_execution_orchestration.py`、`.workflow/`、`memory/smart-arb/`。本次已终止活跃 self-repair run，并把残留业务漂移保存为 `stash@{0}: pre-workflow-fix-rejected-business-drift-20260427T075431Z`。
最后验证：2026-04-27 15:54
复用建议：工作流宿主自修不能再通过同一条 `smart-arb-pipeline` 递归执行；2026-04-28 起可由 Discord profile 的高权限工作流维护模式或外部 operator/Codex 经 SSH 直接修改 hardflow 仓库和安装态。后续若用户说“可以绕过”“不要走工作流”或看到 `Still working...` 对应的 run 目标是修 `smart-arb-pipeline` / `pipeline_runner.py` / `smart_arb_live_bridge.py`，先停止或避开该 self-repair run，再维护 hardflow 宿主、测试并部署修复后的 runtime。

## 2026-04-26 - P0 记忆写回不应被否定式敏感词或 session_id 输出卡住

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、nofx Discord `smart-arb-pipeline`
事实：run `discord-spreadagent-20260426T065131327963Z` 的 P0-1 OpenClaw 历史蒸馏已完成 external_research，但 code_execution 被安全门禁误判 high-risk；原因是报告里出现“未读取 / 不输出 token、key、cookie、OAuth、API key、credential”等否定式安全边界。随后新 run `discord-spreadagent-20260426T075133316811Z` 已完成 15 个阶段：external_research、需求讨论、code_execution、verification、code_review、deployment、acceptance、writeback 均通过。
证据：`smart_arb_pipeline_entry.py` 现在按子句处理风险扫描：纯否定式安全边界、历史文档清理记录、普通 `session_id=[REDACTED]` 和否定式预脱敏噪音可回流；`Need api_key=[REDACTED]`、`Need Authorization: [REDACTED]`、`Need session_id=[REDACTED]`、真实 credential assignment、真实交易/资金/破坏性操作仍按 high 停人工确认。`smart_arb_live_bridge.py` 会在 Hermes CLI 只输出 `session_id` 时，从固定 profile session 文件恢复最新 assistant 输出并脱敏；`external_research` 的 `NO_EXTERNAL_LOOKUP_NEEDED` 可据此合成 pass。entry 还会在 memory/docs-only、no service control、no deployment、no restart 需求下跳过 deployment command，避免纯写回任务重启 `smart-arb-api`。
最后验证：2026-04-26 16:00
复用建议：遇到 P0/P1 文档或项目记忆写回任务被凭证词卡住时，先判断这些词是否处在否定句、历史清理记录或预脱敏噪音中；不要为了绕过门禁删除安全边界。若命令输出只有 `session_id`，去 profile session JSON 核对实际 assistant 输出。若需求写明不触碰服务，确认 runner 命令没有 `--deployment-command`。

## 2026-04-26 - external_research local-only 证据不应因 artifact 写入失败被判阻塞

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、nofx Discord `smart-arb-pipeline`
事实：最新 nofx run `discord-spreadagent-20260426T025738089361Z` 的 `external_research` 实际已经产出 local-only 研究证据，并说明不需要互联网检索；失败根因是 Hermes 阶段尝试直接编辑 `research_report.md`，触发 review diff 后 bridge 返回 `LIVE_BRIDGE_STATUS: fail`。同时失败证据里的“不得泄露凭证 / 不启动真实交易”是安全边界，不应被当作正向高风险请求。
证据：`smart_arb_live_bridge.py` 已要求非代码阶段不编辑 pipeline artifacts，只在 stdout/final answer 返回证据，并在启动非代码 Hermes 子进程前剔除 `PIPELINE_*_REPORT_FILE` artifact 路径变量；`external_research` 可输出 `NO_EXTERNAL_LOOKUP_NEEDED` 作为有效证据；`code_execution` prompt 会消费前序阶段上下文，避免 P0 任务漂移到后续 S1 策略重构，并在注入前脱敏常见 header/assignment、长 token、GitHub PAT、OpenAI `sk-`、Slack/HF/Google/AWS key。`smart_arb_pipeline_entry.py` 已把 `run_external_research` 纳入自动回流白名单，并按分句剥离纯否定式安全边界；混合句中的正向凭证/资金操作仍判高风险。测试 `test_negated_safety_terms_do_not_block_external_research_repair`、`test_positive_credential_or_trading_request_still_high_risk`、`test_negated_english_safety_terms_do_not_block_repair`、`test_redacts_short_known_secret_shapes_from_failure_evidence`、`test_non_code_hermes_env_hides_pipeline_artifact_paths`、`test_pipeline_context_redacts_sensitive_context_values`、`test_external_research_prompt_forbids_file_edits_and_allows_local_only_pass`、`test_code_execution_prompt_includes_prior_stage_context` 覆盖该行为。
最后验证：2026-04-26
复用建议：遇到 live gate 说 `run_external_research` 时，先查 `command-runs/external_research-*.json` 是否已有 local-only 证据；如果有，不要让 agent 直接改 `research_report.md`，而是通过自动回流重新生成 stdout 证据并由 runner 写入 artifact。

## 2026-04-26 - nofx Discord 状态卡不能只回 failed_stage

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、nofx Discord `smart-arb-pipeline`
事实：只把 `pipeline_state.json` 的 `status`、`failed_stage`、`next_action` 发回 Discord，会让用户看不到目标完成情况和具体阻塞证据。入口会读取 `command-runs/*.json`，状态卡包含 `阶段命令状态`、`阻塞原因` 和 `自动修复判断`；默认只展示 stage/agent/returncode/证据文件，避免把 reviewer/tester 原始输出刷进聊天频道。
证据：`smart_arb_pipeline_entry.py` 新增 command report 状态行、失败证据提取、高风险分类和自动回流；`smart_arb_live_bridge.py` 会读取 `PIPELINE_REPAIR_CONTEXT_FILE` / `SMART_ARB_ENTRY_REPAIR_CONTEXT_FILE` 或内联 `PIPELINE_REPAIR_CONTEXT`，把上一轮失败证据注入后续 stage prompt；测试 `test_render_chat_summary_shows_block_reason_and_repair_decision`、`test_main_auto_repairs_low_risk_blocked_run`、`test_main_auto_repair_keeps_context_when_context_file_write_fails`、`test_main_does_not_auto_repair_high_risk_blocked_run` 覆盖该行为。
最后验证：2026-04-26 11:30
复用建议：遇到 Discord 回复“已阻塞，不能绕过 pipeline”时，先检查入口是否为新版；新版会在低/中风险下自动回流，只有凭证、真实交易、资金、破坏性数据操作等高风险才停人工确认。

## 2026-04-26 - nofx smart-arb-pipeline 旧默认值会把执行请求跑成 dry-run

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、nofx `/home/arbops/.local/bin/smart-arb-pipeline`、Discord `arbitrageagent` / `spreadagent`
事实：旧入口只有显式 `--live` 才真实执行，否则会向 runner 追加 `--dry-run`，导致 Discord 对“继续”“都依次完成”这类执行请求只生成编排证据并提示 `No product code was modified by this runner.`。已改为固定 live；`smart-arb-pipeline` 项目入口不再提供 simulation/dry-run 模式。
证据：`smart_arb_pipeline_entry.py` 不再追加 `--dry-run`，并默认注入 live bridge commands；两个 nofx profile SOUL 已改成“执行类需求默认 live pipeline”。
最后验证：2026-04-26 00:00
复用建议：遇到 Discord 回复“默认 pipeline dry-run/simulation”时，先查入口版本和 runner 命令；不要再要求用户补一句“继续真实执行”。

## 2026-04-26 - nofx 早期 workflow 权限按高信任模式配置

类型：decision
范围：nofx `/home/arbops/.hermes/profiles/*/config.yaml`、`/etc/sudoers.d/90-arbops-hermes`
事实：用户明确要求前期不做细粒度权限划分，workflow 和其他 agent 必须能直接执行服务器级修复。当前 nofx 两个 Discord profile 已关闭命令审批和 security scan，`arbops` 配置为无密码 sudo。真实交易仍由 `PRODUCTION_TRADING_ENABLED=false` 与策略手册边界约束，不在 Hermes 权限层放开。
证据：profile 模板 `config/nofx-hermes-profiles/*/config.yaml` 包含 `approvals.mode: 'off'` 与 `security.tirith_enabled: false`；nofx `/etc/sudoers.d/90-arbops-hermes` 写入 `arbops ALL=(ALL) NOPASSWD:ALL` 并通过 `visudo -cf`。
最后验证：2026-04-26 00:00
复用建议：后期收紧权限时，先把 sudoers 改成命令 allowlist，再打开 profile security scan；不要在用户要求“直接可用”阶段重新引入 approval gate。

## 2026-04-26 - nofx `/sethome` 写配置失败通常是 profile config 属主错误

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/<profile>/config.yaml`
事实：`/sethome` 需要 Hermes gateway 进程写当前 profile 的 `config.yaml`。如果文件被 root 写成 `root:root` 且 `0600`，`arbops` 用户运行的 gateway 会无法写入并返回 `[Errno 13]`。已将两个 Discord profile 的 `config.yaml` 修回 `arbops:arbops` + `0600`。
证据：远端 stat 曾显示 `spreadagent/config.yaml` 和 `arbitrageagent/config.yaml` 均为 `root:root 0600`，而 profile 目录与 `.env` 为 `arbops:arbops`；修复后以 `arbops` 身份完成写入 smoke。
最后验证：2026-04-26 00:00
复用建议：通过 root/SFTP 改 profile 配置后必须立即 `chown arbops:arbops /home/arbops/.hermes/profiles/<profile>/config.yaml`；不要只修 `.env`。

## 2026-04-25 - nofx live bridge 容易被误判为真实多 agent 分发

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、`scripts/openclaw-ops/smart_arb_live_bridge.py`、`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`、nofx Hermes runtime
事实：`smart-arb-pipeline --live` 当前仍默认注入 `smart_arb_live_bridge.py`，但已经补上 per-agent workspace 隔离：`web-agent`、`project-agent`、`reviewer`、`backend-dev`、`tester` 等 owner 会有独立 workspace 记录，`code_execution` workspace diff 会回流主项目并注入后续验收 workspace。Task Center 的 `agent_id` / `module_communications` 仍是责任标签与状态机镜像，不等于已经真实启动了多个宿主 native agent。
证据：`pipeline_runner.py` 固定使用 Git worktree、`agent-workspaces/manifest.json`、`PIPELINE_AGENT_REPO_DIR` 注入和 `command-runs/code_execution-1.patch`；`smart_arb_pipeline_entry.py` 不再暴露 `--agent-workspace-mode`；`smart_arb_live_bridge.py` 默认使用 `PIPELINE_AGENT_REPO_DIR` 作为阶段项目目录；nofx smoke `codex-arbitrageagent-20260425T140605083467Z` 的 Task Center 命令阶段为 `runtime-agent-workspace` / `isolated-agent-workspace`。
最后验证：2026-04-25 22:06
复用建议：如果用户问“为什么任务没有转给其他 agent”，先区分三层：责任标签、独立 workspace、宿主 native session。现在 workspace 层已落地；若要宣称 native fan-out，仍必须检查 command evidence 中是否存在独立 session/run id。

## 2026-04-25 - nofx SSH 并发采样可能触发临时拒绝

类型：pitfall
范围：nofx 远程巡检、PowerShell 原生 `ssh`、Paramiko
事实：本轮先用 PowerShell 原生 `ssh` 并发采样时空退，随后 Paramiko 曾成功一次，再出现 `Not allowed at this time`、`Error reading SSH protocol banner` 和连接重置。该状态下不能把“连不上 SSH”误认为 nofx runtime 自身异常。
证据：本地 socket 连接 22 端口返回 `Not allowed at this time`；Paramiko 报 `Authentication failed: transport shut down or saw EOF`、`No existing session`、`Error reading SSH protocol banner`。
最后验证：2026-04-25 19:05
复用建议：nofx 巡检优先单连接、低频重试；避免一次性并发多个 SSH 会话。若需要多项采样，应在同一连接内顺序执行，或等待服务端限制窗口恢复。

## 2026-04-25 - nofx Hermes profile SOUL 乱码导致 coordinator 约束变弱

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/arbitrageagent/SOUL.md`、`/home/arbops/.hermes/profiles/spreadagent/SOUL.md`
事实：远程两个 profile 的 `SOUL.md` 主体曾变成问号乱码，只有后追加的 `Pipeline Boundary Update` 可读。19:10 的 `spreadagent` Discord 会话收到“都依次完成吧”后没有创建新的 `smart-arb-pipeline` run，而是在 profile 会话里直接规划任务，说明 coordinator pipeline 约束没有稳定生效。
证据：远程读取 `SOUL.md` 首段显示 `# ???????`；`/home/arbops/.hermes/profiles/spreadagent/sessions/session_20260425_191017_e8d87b.json` 为 Discord 会话，用户消息为“都依次完成吧”，但 `/home/arbops/.hermes/pipeline-runs` 当时最新仍是 18:00 smoke run。
最后验证：2026-04-25 19:20
复用建议：profile 提示词不要用 PowerShell 内联中文写远程文件；应从仓库 UTF-8 模板按字节上传。更新后必须重启对应 tmux gateway，并确认 `gateway_state=running`、`discord=connected`。

## 2026-04-25 - nofx Command Approval Required 不能只改全局 Hermes 配置

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/arbitrageagent/config.yaml`、`/home/arbops/.hermes/profiles/spreadagent/config.yaml`、本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest/config.yaml`
事实：本机 WSL 虽然全局 `/home/ubuntu/.hermes/config.yaml` 仍是 `approvals.mode: manual`，但 live `trend-backtest` profile 是顶层 `approvals.mode: 'off'`，所以实际不会弹命令审批。nofx 没有 `/home/arbops/.hermes/config.yaml`，两个 Discord profile 原先也没有顶层 `approvals` 配置，遇到 Hermes security scan 的 `Command Approval Required` 仍会进入人工审批。已在 nofx 两个 profile 中补齐顶层 `approvals.mode: 'off'`，并重启 `hermes-discord-arbitrage`、`hermes-discord-spread`。
证据：本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest/config.yaml` 第 7-8 行为 `approvals.mode: 'off'`；nofx 两个 profile 配置已验证 `approvals_mode_off=True`；`gateway_state.json` 显示 `arbitrageagent` 为 `running updated_at=2026-04-25T14:56:14.570586+00:00`，`spreadagent` 为 `running updated_at=2026-04-25T15:01:19.106822+00:00`；日志尾部未发现新的 `Command Approval Required` / `confusable` 记录，只有 22:48 的历史 Discord button approval。
最后验证：2026-04-25 23:03
复用建议：排查 nofx Hermes 审批问题时，先看 profile 级 `config.yaml`，不要用全局 `~/.hermes/config.yaml` 做结论。改配置后必须重启对应 tmux gateway；旧会话里已经生成的审批卡片不代表新配置未生效，后续新命令才会按 profile 配置执行。

## 2026-04-25 - nofx live verification 不应默认跑全量 unittest discover

类型：pitfall
范围：`scripts/openclaw-ops/smart_arb_live_bridge.py`、`scripts/openclaw-ops/smart_arb_pipeline_entry.py`、nofx `/home/arbops/.hermes/pipeline-runs/discord-spreadagent-20260425T145231185916Z`
事实：机器人回复里的 `external_research` 阻塞不是最新真实状态；真实最新 run `discord-spreadagent-20260425T145231185916Z` 已完成 `external_research`、`requirements_discussion`、`code_execution` 三段，真正卡住的是 `verification`：默认 `/home/arbops/.venvs/smart-arbitrage/bin/python -m unittest discover -s tests -p 'test_*.py'` 长时间停在 async/zmq 相关等待。已把 live 默认验证收敛为 `git diff --check` 与 `compileall -q scripts strategy_runtime`，并新增 `--verification-command-timeout-seconds` 显式参数。
证据：旧 run `pipeline_state.json` 为 `status=blocked failed_stage=verification next_action=return_to_code_execution`；`verification_report.md` 显示 unittest 子进程被终止后 returncode=-15，stderr 含 `asyncio.exceptions.CancelledError` 与 zmq future；安装态真实 verification smoke 显示 `git diff --check` 和 `/home/arbops/.venvs/smart-arbitrage/bin/python -m compileall -q scripts strategy_runtime` 均 returncode 0；echo live smoke `codex-spreadagent-20260425T154609125415Z` 15 阶段 completed，`verification-1.json` 命令包含 `--verification-command-timeout-seconds 180`。
最后验证：2026-04-25 23:46
复用建议：Discord live pipeline 只跑有限安全验证；全量 unittest 放到 CI 或人工排障。遇到“卡在 external_research”的机器人回复，先查最新 run 目录和 `ps`，不要相信旧 run_id 或错误路径。

## 2026-04-25 - root 写回 profile .env 会导致 Hermes gateway 立即退出

类型：pitfall
范围：nofx `/home/arbops/.hermes/profiles/arbitrageagent/.env`、`/home/arbops/.hermes/profiles/spreadagent/.env`、`start-gateway.sh`
事实：用 root/SFTP 修改 profile `.env` 后，如果权限变成 root:root 且 `0600`，`arbops` 启动的 Hermes gateway 会因无法读取 `.env` 立即退出，tmux 会话看起来创建成功但很快消失。已修正两个 `.env` 为 `arbops:arbops` + `0600`，并用 profile `start-gateway.sh` 加载 `.env` 启动。
证据：两个 profile 的 `gateway.log` 曾出现 `PermissionError: [Errno 13] Permission denied: '/home/arbops/.hermes/profiles/<profile>/.env'`；修正属主后 `hermes-discord-arbitrage`、`hermes-discord-spread` 均在 tmux 中存在，`gateway_state.json` 显示 `running updated_at=2026-04-25T15:45:14/15Z`。
最后验证：2026-04-25 23:45
复用建议：profile `.env` 含凭证，不打印内容；只检查属主和 mode。通过 root 修改后必须 `chown arbops:arbops`，然后再重启对应 tmux gateway。
## 2026-04-27 - Hermes Discord connected 但频道发言 403

类型：pitfall
范围：本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest`、Discord bot “多核电脑”、`本地项目 / #常规`
事实：`gateway_state.json` 显示 Discord `connected` 只能证明 bot token 有效且 gateway websocket 已连上；它不证明 bot 对目标频道有发送消息权限。2026-04-27 将 `trend-backtest` 接到新 bot 后，Hermes 日志显示 `[Discord] Connected as 多核电脑#8868`，但用 bot token 向 `1498225531923988562` 发消息返回 `403 Forbidden`。
证据：`hermes -p trend-backtest status` 显示 Discord home channel 为 `1498225531923988562` 且 gateway running；`POST https://discord.com/api/v10/channels/1498225531923988562/messages` 返回 HTTP 403。
最后验证：2026-04-27 16:03
复用建议：遇到“online/connected 但聊天不回”时不要只查 `hermes status`。先查 channel 发送权限，再查 Message Content Intent。免 @ 最小安全配置是 `require_mention: true` + `free_response_channels=<目标频道>`，不要为了免 @ 直接把 `require_mention=false` 放到多频道 guild，除非这是专用单频道服务器。

## 2026-04-27 - 替代 TG 入口不能沿用专项 profile SOUL

类型：pitfall
范围：本机 WSL `/home/ubuntu/.hermes/profiles/trend-backtest`、旧 TG 全局 Hermes、Discord “多核电脑”入口
事实：把新 Discord bot 接到现有 `trend-backtest` profile 后，若只替换 token 和频道，bot 会继续加载该 profile 原有“趋势回测机器人 SOUL”，从而在新频道开场自称趋势回测 agent，并固定宣称默认工作目录 `/home/ubuntu/projects/SmartTrendTracker`。这与“替代之前 TG 频道、沿用 TG 记忆”的目标冲突。最终修正不是继续复用 `trend-backtest`，而是拆出独立 `multicore` profile，让 `trend-backtest` 回到旧趋势回测 bot/旧频道，让 `multicore` 承接新多核电脑 bot/新频道。
证据：2026-04-27 用户在 Discord 看到回复“我是趋势回测 agent，默认工作目录是 /home/ubuntu/projects/SmartTrendTracker”；随后核对发现全局 `~/.hermes/SOUL.md` 是旧 Telegram 的 Hermes SDLC 总协调官提示词，全局 `~/.hermes/memories/MEMORY.md` 是旧 TG 记忆，而 profile `SOUL.md` 是趋势回测专项提示词。
最后验证：2026-04-27 16:41
复用建议：做“渠道替换”时必须迁移 identity、SOUL、memory、session 四件套；只改 platform token 会造成入口身份漂移。如果原 profile 还代表另一个 agent，不要覆盖它，应该新建 profile 并把旧 profile 恢复到原 bot、原频道、原 cwd。

## 2026-04-27 - 两个 Discord agent 不能共用未隔离的 gateway

类型：pitfall
范围：本机 WSL Hermes Discord gateway、`/home/ubuntu/.hermes/profiles/{trend-backtest,multicore}`、`gateway/platforms/discord.py`
事实：同一个 Discord bot token 默认只能被一个 gateway 进程持有；即使不同 profile 绑定不同频道，如果没有频道白名单和 DM 禁用，也可能出现抢消息或 DM 双回复。当前本机两个 agent 使用不同 bot token，并各自设置 `DISCORD_ALLOWED_CHANNELS`；Hermes Discord adapter 还补了受控开关：`DISCORD_ALLOW_SHARED_BOT_TOKEN=true` 只有在同时设置 `DISCORD_ALLOWED_CHANNELS` 时才允许共享 token 分锁，`DISCORD_ALLOW_DMS=false` 会让 profile 忽略 DM。
证据：`gateway/platforms/discord.py` 在 `connect()` 中将共享 token 锁身份收敛为 `token:allowed_channels`，缺少 `DISCORD_ALLOWED_CHANNELS` 时返回 fatal；`_handle_message()` 在 DM 分支优先检查 `DISCORD_ALLOW_DMS=false` 并丢弃。相关回归测试 `test_discord_connect.py`、`test_discord_channel_controls.py`、`test_discord_reply_mode.py` 共 50 项通过。
最后验证：2026-04-27 16:41
复用建议：以后做多 Discord agent，不要只靠“频道不同”作为隔离。至少要有 profile 独立、session 独立、cwd 独立、`allowed_channels` 白名单、DM 策略；如果共享同一个 bot token，还必须有锁身份隔离。
