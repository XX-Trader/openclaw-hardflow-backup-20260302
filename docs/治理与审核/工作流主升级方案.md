# 2026-03-20 OpenClaw Workflow 主升级方案

更新时间：2026-03-20（北京时间）

## 1. 文档定位

这份文档用于把当前 `OpenClaw` workflow 最值得先做的升级事项，收敛成一份可以直接执行的主方案。

它不是替代已有文档，而是把两份已存在文档中的最高优先级事项统一起来，作为当前阶段的临时 SSOT：

- `docs/2026-03-19-openclaw-工作流治理与执行闭环升级说明.md`
- `docs/2026-03-19-openclaw-workflow-code-optimization-backlog.md`

当前阶段，我们不追求一次性把整个 workflow 全量重构，而是优先把真正影响稳定性、可追踪性、可复制性的 5 个核心项接进主流程。

---

## 2. 本次主升级目标

把当前 `OpenClaw` workflow 从“能运行、能部署”升级为：

1. 有正式评分门禁
2. 有强制验证纪律
3. 有部署后验收闭环
4. 有标准化记忆链路
5. 有稳定的 hooks 运行时交付形态

本次主升级范围只覆盖以下 5 项：

1. 评分与 gate 接入主流程
2. 完成前验证制度
3. 部署后验收测试
4. `OpenViking` 记忆链路标准化
5. hooks 运行时标准化

本次主升级明确不优先覆盖：

1. `GitHub Actions Runner`
2. 更多即时通讯通道
3. 更多第三方记忆后端
4. 全量 Secret 治理重构

---

## 3. 当前问题总览

当前 workflow 已具备不少零件，但它们还没有被真正接成主流程。

当前问题可以归纳为：

1. 评分体系存在，但还没有成为每次任务必须经过的正式门禁
2. “完成”常常依赖口头判断，而不是新鲜验证证据
3. 部署后检查存在文档，但还没有形成统一验收动作
4. `memory-core`、`memory-openviking`、`OpenViking`、slot、allow 的边界不够清晰
5. hooks 的源码形态与运行时形态没有彻底分离，跨平台稳定性不足

这 5 个问题共同导致：

1. 结果可追踪性不足
2. 运行时问题复现和定位成本高
3. 新机器和多服务器复制成本高
4. “看起来能跑”与“真正可控”之间仍有明显差距

---

## 4. 本次主升级的总原则

本次升级遵循以下原则：

1. 先把已经有的关键能力接进主流程，不先发明更多新能力
2. 先做制度化与标准化，再做大规模自动化
3. 先修影响全局稳定性的底座，再修局部体验
4. 先让 Windows / Linux / 多服务器的行为可解释，再追求更复杂的扩展
5. 所有“完成、通过、可用”都必须有可复盘证据

---

## 5. 五项主升级方案

### 5.1 主升级项一：评分与 gate 正式接入主 workflow

优先级：

- `P0`

目标：

- 把 HardFlow 评分系统从“存在的规则”升级成“每次 workflow 必经步骤”

现有基础：

- `scripts/hardflow/score-policy.json`
- `scripts/hardflow/SCORECARD_SCHEMA.md`
- `C:/Users/superma/.claude/skills/openclaw-hardflow-automation/SKILL.md`

当前问题：

1. 评分规则存在，但没有被统一纳入 workflow 主链路
2. gate 的阈值、veto、scorecard 产物没有在执行层被强绑定
3. 容易出现“任务做完了，但没有明确过 gate”的模糊状态

目标态：

1. 每次 workflow 必须经过 `G0-G6`
2. 每个 gate 都有独立 scorecard
3. gate 失败后必须回流整改
4. `critical/high` 风险未闭环时，`security` gate 直接 veto

当前确认阈值：

1. `G0 requirements >= 93`
2. `G1 solution >= 92`
3. `G2 frontend >= 92`
4. `G3 backend >= 93`
5. `G4 security >= 95`
6. `G5 release >= 92`
7. `G6 final >= 93`

涉及文件：

- `scripts/hardflow/score-policy.json`
- `scripts/hardflow/SCORECARD_SCHEMA.md`
- `C:/Users/superma/.claude/skills/openclaw-hardflow-automation/SKILL.md`
- 后续可能新增或修改 workflow 编排文档与执行脚本

执行步骤：

1. 固化 `G0-G6` 为主流程正式阶段
2. 明确每个 gate 的输入、输出、责任角色
3. 明确 scorecard JSON 的标准路径与字段
4. 明确 gate 失败后的回流与重评分规则
5. 将 gate 结果纳入最终是否允许部署/完成的决策条件

当前落地状态（2026-03-20）：

1. 已新增正式主流程入口：
   - `bash scripts/hardflow/hardflow-run.sh workflow --task "..." --max-retries N --score-max-retries N`
2. `hardflow-tmux-runner.sh` 的 direct 模式已切换为调用 `workflow` 入口
3. `scripts/hardflow/README.md` 已同步声明 `workflow` 为 direct 模式正式主流程
4. `hardflow-v1.lobster.yaml` 当前仍保留显式分步编排，暂不在本批次改动

当前剩余待办：

1. 决定 Lobster 模式是否也要收敛到统一入口
2. 决定 `post-test` 失败后是否应阻断 `release/final` gate
3. 继续把 gate 状态与 scorecard 产物接入更明确的 workflow 编排层

验收点：

1. 任一完整 workflow 都能明确回答当前停在哪个 gate
2. 每个 gate 都有独立产物
3. gate 失败时不会直接进入后续阶段
4. 最终“通过”不再是口头状态，而是 gate 全通过

风险：

1. 一次性把 gate 卡得太死，短期会增加流程摩擦
2. 如果 scorecard 产物路径和输出格式没统一，会造成“形式上接入、实际上不可用”

回滚思路：

1. 先允许 gate 以“记录 + 提示”方式并行运行
2. 稳定后再切成真正阻断式

依赖关系：

- 无前置依赖
- 它是后续“完成前验证”和“部署后验收”的上游基线

---

### 5.2 主升级项二：完成前验证制度

优先级：

- `P0`

目标：

- 把“完成前验证”从习惯动作升级成硬规则

现有基础：

- `C:/Users/superma/.claude/skills/verification-before-completion/SKILL.md`

当前问题：

1. 多 agent、多脚本、多服务器环境下，最容易出现“看起来完成了，实际上没验证”
2. “修好了”“通过了”“可用了”这类结论容易缺少真实命令证据
3. workflow 里还没有把验证结果当成正式产物

目标态：

1. 没有新鲜验证证据，不允许声称完成
2. 没有真实输出，不允许声称通过
3. 在任务完成、交付、部署前，必须有验证记录

核心规则：

- `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE`

涉及文件：

- `C:/Users/superma/.claude/skills/verification-before-completion/SKILL.md`
- 后续治理文档
- 后续执行模板、review 模板、交付模板

执行步骤：

1. 明确哪些结论必须附验证证据
2. 明确验证证据允许的形式
3. 明确“无验证不得宣称完成”的输出规范
4. 把验证作为 gate 通过与最终完成之间的必经层

当前落地状态（2026-03-20）：

1. 已在 `scripts/hardflow/hardflow-run.sh` 中新增 `verify-completion` 阶段
2. `workflow` 主流程已在 `postdeploy quality gate` 之后、`git-push` 之前强制执行该阶段
3. `git-push` 现在显式依赖 `.workflow/gates/completion_verification.json`
4. 当前 run 的验证产物已固定为：
   - `.workflow/runs/<run_id>/verification/completion.json`
   - `.workflow/gates/completion_verification.json`

当前剩余待办：

1. 决定 Lobster 模式是否也需要同样的完成前验证硬阻断
2. 继续明确哪些额外交付动作也必须依赖 `completion_verification`
3. 后续把验证证据与部署后验收输出继续收敛成更统一的交付产物

验收点：

1. 任何“已完成/已修复/已可用”都能追溯到具体验证动作
2. 文档、群消息、执行日志中不再出现无证据完成宣称
3. review 与验收阶段都能复用验证产物

风险：

1. 如果规则写得太泛，容易流于形式
2. 如果验证粒度不合理，会造成执行负担过高

回滚思路：

1. 先在关键任务上强制执行
2. 非关键任务先以提示为主，逐步收紧

依赖关系：

- 依赖 `5.1 评分与 gate` 的流程接入
- 会直接影响 `5.3 部署后验收测试`

---

### 5.3 主升级项三：部署后验收测试纳入正式闭环

优先级：

- `P0`

目标：

- 把部署后的检查从“经验动作”升级成“正式验收环节”

现有基础：

- `C:/Users/superma/.claude/skills/deployment-test/SKILL.md`
- 现有部署说明文档
- `integration/openclaw-bridge/acceptance-checklist.md`

当前问题：

1. 现在有部署说明，也有一些验收想法，但缺少统一验收最小集
2. 通道、记忆、hooks、jobs 这些系统部件很多，单靠口头确认不够
3. 经常只能回答“装了”，但不能快速回答“是否真的可用”

目标态：

1. 部署完成后必须经过最小验收清单
2. 验收结果可明确区分：
   - 可用
   - 半可用
   - 不可用
3. 验收结论可被 gate 与完成前验证复用

最小验收清单建议：

1. `openclaw gateway status`
2. `openclaw status`
3. `openclaw plugins list`
4. hooks 状态
5. jobs 状态
6. `OpenViking` 健康状态
7. `Telegram` 状态
8. `Feishu` 状态

涉及文件：

- `integration/openclaw-bridge/acceptance-checklist.md`
- 部署文档
- `C:/Users/superma/.claude/skills/deployment-test/SKILL.md`
- 后续可能新增验收脚本

执行步骤：

1. 固化统一最小验收清单
2. 固化验收输出格式
3. 把验收动作接入部署后标准步骤
4. 明确失败时的最小回滚建议

当前落地状态（2026-03-20）：

1. 已在 `scripts/hardflow/hardflow-run.sh` 中新增 `acceptance-test` 阶段
2. 已新增 `scripts/hardflow/check-deployment-acceptance.sh`
3. `workflow` 主流程已在 `quality_gate_postdeploy` 之后强制执行 `acceptance-test`
4. 当前 run 的验收产物已固定为：
   - `.workflow/runs/<run_id>/acceptance/deployment.json`
   - `.workflow/gates/deployment_acceptance.json`
5. `verify-completion` 当前已显式依赖 `deployment_acceptance`
6. 2026-03-20 本机验收已验证：
   - `bash scripts/hardflow/check-deployment-acceptance.sh` 可通过
   - `bash scripts/hardflow/hardflow-run.sh acceptance-test` 已能实际跑通到验收脚本并通过
7. 同一次本机验证中，`verify-completion` 的阻断原因已收敛为“缺少完整上游 workflow 产物”，不再包含 `deployment_acceptance` 失败
8. 2026-03-20 本机已完成一次无外部提交的安全演练：
   - `run_id=20260320_142433`
   - `G0-G6` 全通过
   - `quality_gate_predeploy` / `quality_gate_postdeploy` 通过
   - `deployment_acceptance` 通过
   - `completion_verification` 通过

当前剩余待办：

1. 决定 Lobster 模式是否也要接入同样的验收阶段
2. 继续把 `OpenViking`、`Telegram`、`Feishu` 的验收规则收敛成默认模板
3. 后续将验收输出与完成前验证进一步统一成更稳定的交付证据

验收点：

1. 任一部署后都能快速得出统一结论
2. 验收不是自由发挥，而是统一口径
3. 验收失败时能指出失败层级

风险：

1. 如果一开始就把验收做成过重的全自动系统，会拖慢当前节奏
2. 通道可达性和网络环境可能放大噪音

回滚思路：

1. 先固化文档化清单
2. 再逐步脚本化

依赖关系：

- 依赖 `5.2 完成前验证制度`
- 和 `5.4 OpenViking 标准化`、`5.5 hooks 标准化` 强相关

---

### 5.4 主升级项四：OpenViking 记忆链路标准化

优先级：

- `P1`

目标：

- 把 `OpenViking` 固化为标准记忆增强链路，消除服务层、插件层、路由层的混乱表达

现有基础：

- `https://github.com/volcengine/OpenViking`
- 现有 `memory-openviking`
- 当前本机与服务器的实践经验

当前问题：

1. `memory-core`、`memory-openviking`、`OpenViking` 常被混为一谈
2. `plugins.allow` 与 `plugins.slots.memory` 的定位容易混
3. 服务端口、健康检查、日志路径、启动方式还不够统一

目标态：

标准三层明确为：

1. 服务层：
   - `OpenViking`
2. 插件层：
   - `memory-openviking`
3. 路由层：
   - `plugins.allow`
   - `plugins.slots.memory`

约束：

1. 标准记忆增强后端统一为 `OpenViking`
2. 标准插件统一为 `memory-openviking`
3. 官方内置能力作为补充，而不是并行第三方路线扩张

涉及文件：

- 部署文档
- `openclaw.json`
- `openclaw-workflow-deploy` 技能文档
- 相关启动脚本、健康检查说明

执行步骤：

1. 固化三层解释
2. 固化默认端口、可替代端口和异常处理策略
3. 固化健康检查、日志路径和启动方式
4. 固化 Windows / Linux 差异

当前落地状态（2026-03-20）：

1. 已新增 `scripts/openclaw-ops/check_openviking_stack.py`
2. 已新增标准说明文档：
   - `integration/openclaw-bridge/openviking-stack.md`
3. `acceptance-test` 当前默认会执行 `check_openviking_stack.py`
4. 当前 run 的 OpenViking 标准化产物已固定为：
   - `.workflow/runs/<run_id>/acceptance/openviking-stack.json`
   - `.workflow/gates/openviking_stack.json`
5. `openclaw/openclaw.json` 已显式补出默认 `plugins.slots.memory = "memory-core"` 基线
6. `check_openviking_stack.py` 已支持优先读取运行时 `memory-openviking.config.port` / `healthUrl` / `baseUrl`
7. 2026-03-20 本机验收已验证 Windows 本地 `29333` 端口场景可正确识别并通过健康检查
8. 2026-03-20 本机安全演练 `run_id=20260320_142433` 已复用该检查并通过 `openviking_stack`

当前剩余待办：

1. 后续继续把 `memory-openviking` 的正式安装策略与多服务器 rollout 模板收敛
2. 继续把 Windows / Linux 的端口差异和启动方式补到平台文档
3. 视实际运行情况，再决定是否把更多 OpenViking 检查提升为强阻断项

验收点：

1. 新机器能按统一文档接入
2. 故障能快速区分是服务层、插件层还是路由层问题
3. 不再把插件白名单误当成运行故障根因

风险：

1. 记忆问题常表现为“能用但不稳定”，容易误判
2. 平台差异与端口占用问题会放大复杂度

回滚思路：

1. 若增强记忆不稳定，可暂时回退到官方内置能力
2. 但不再额外扩张其他第三方记忆路线

依赖关系：

- 建议在 `5.3 部署后验收测试` 基线确定后推进
- 其健康状态应被纳入正式验收

---

### 5.5 主升级项五：hooks 运行时标准化

优先级：

- `P1`

目标：

- 不再让 hooks 的源码形态直接充当运行时形态，统一运行时交付规则

现有基础：

- 当前 hooks 目录
- 现有部署与同步脚本
- 已发生过 `.ts` 裸加载失败的实际案例

当前问题：

1. `.ts` hook 裸加载失败已经证明当前形态不稳
2. Windows / Linux 对源码运行和路径处理的差异容易造成漂移
3. hooks 直接影响 gateway 启动稳定性

目标态：

1. 仓库存源码
2. 运行时只加载稳定产物
3. hooks 安装与启用策略明确区分源码层和运行时层

建议结构方向：

1. `hooks/<name>/src/`
2. `hooks/<name>/dist/`
3. 运行时只加载统一入口或 `dist`

涉及文件：

- hooks 目录
- hooks 启用配置
- 安装脚本
- 部署文档

执行步骤：

1. 盘点现有 hooks 中哪些还依赖源码形态
2. 定义正式运行时交付标准
3. 明确同步/复制/启用规则
4. 更新平台差异文档

当前落地状态（2026-03-20）：

1. 已新增 `scripts/openclaw-ops/sync_openclaw_hooks_files.py`
2. `install_workflow_profile.py` 现在会先同步仓库 `hooks/` 到 `~/.openclaw/hooks-runtime`
3. `hooks.internal.load.extraDirs` 已改为指向运行时目录，而不是仓库源码目录
4. 已更新 `integration/openclaw-bridge/hooks-install.md`
5. 当前运行时 hooks 明确采用：
   - `runtime_entry_policy = handler-js-runtime`
   - 每个 hook 的可执行入口以 `handler.js` / `index.js` 为准

当前剩余待办：

1. 继续确认 Lobster / 多服务器场景下的 hooks 运行时目录策略
2. 后续如果出现新的自定义 hook 类型，再决定是否扩展允许的运行时文件类型
3. 继续把平台差异补到 Windows / Linux 部署文档

验收点：

1. Windows / Linux 上 hooks 装载方式一致
2. 不再把 `.ts` 裸文件当成正式运行时入口
3. hooks 相关故障能快速定位到源码层还是运行时层

风险：

1. 一次性切全部 hooks 风险过高
2. 如果没有并行过渡期，可能直接影响 gateway 启动

回滚思路：

1. 先做“规范定义 + 新旧并行”
2. 不一次性全量切换

依赖关系：

- 依赖 `5.3 部署后验收测试`
- 和 `5.1 评分与 gate` 没有强前置，但会影响整体运行稳定性

---

## 6. 本次主升级的推荐执行顺序

建议严格按以下顺序推进：

1. `5.1 评分与 gate 接入主流程`
2. `5.2 完成前验证制度`
3. `5.3 部署后验收测试`
4. `5.4 OpenViking 记忆链路标准化`
5. `5.5 hooks 运行时标准化`

排序原因：

1. 先把治理规则接进主链路
2. 再把“完成”和“验收”的证据体系固定
3. 再标准化容易导致运行不稳的底层部件

---

## 7. 阶段划分

### 阶段 A：治理闭环建立

包含：

1. 评分与 gate
2. 完成前验证

阶段目标：

- 先把“能不能过线”和“能不能宣称完成”固化下来

阶段产出：

1. HardFlow gate 进入主流程
2. 完成前验证规则进入正式执行口径

阶段验收：

1. 任一任务都能明确是否过 gate
2. 任一完成结论都必须有证据

### 阶段 B：部署验收闭环建立

包含：

1. 部署后验收测试

阶段目标：

- 让部署不再只等于“命令跑完”

阶段产出：

1. 统一最小验收清单
2. 统一验收输出格式

阶段验收：

1. 任一部署都可快速判断可用性

### 阶段 C：运行时稳定性标准化

包含：

1. `OpenViking` 标准化
2. hooks 标准化

阶段目标：

- 解决最容易制造跨平台与运行时漂移的问题

阶段产出：

1. 记忆链路标准说明
2. hooks 运行时交付规范

阶段验收：

1. 新机器接入和旧机器排障都更可复制

---

## 8. 成功标准

当以下条件成立时，可以认为本次主升级阶段完成：

1. workflow 正式引入 `G0-G6`
2. “完成”必须附验证证据
3. 部署后有统一验收清单
4. `OpenViking` 三层边界清晰
5. hooks 不再以源码裸形态直接充当运行时入口

如果这 5 条完成，当前 workflow 就能从：

- “能跑”

升级为：

- “可控”
- “可追踪”
- “可复制”

---

## 9. 与现有文档的关系

这份主方案负责“收口”和“排优先级”。

已有文档继续保留各自职责：

1. `docs/2026-03-19-openclaw-工作流治理与执行闭环升级说明.md`
   - 负责治理视角、规则视角
2. `docs/2026-03-19-openclaw-workflow-code-optimization-backlog.md`
   - 负责代码与执行项 backlog

后续执行原则：

1. 先按本文档决定优先级和顺序
2. 再回到 backlog 拿具体执行项
3. 需要制度说明时，回到治理文档扩写细节

---

## 10. 下一步建议

下一步建议从 `5.1 评分与 gate 接入主流程` 开始。

原因：

1. 它是整个 workflow 从“做任务”变成“过线流程”的分水岭
2. 后面的验证、验收、review 都会依赖它
3. 它最符合当前 HardFlow 的体系风格

本次主升级开始后，后续每次执行一个子项，建议统一输出：

1. 修改文件
2. 直接影响
3. 间接影响
4. 配置变更
5. 验收点
6. 当前风险
7. 下一步建议
