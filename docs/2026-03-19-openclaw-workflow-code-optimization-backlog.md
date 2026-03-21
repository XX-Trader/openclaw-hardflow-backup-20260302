# OpenClaw 工作流代码优化 Backlog

## 1. 文档目标

这份文档用于把当前 `OpenClaw` 工作流的优化事项整理成“可执行 backlog”，而不是停留在泛泛建议层。

本文档的用途：

1. 统一优化目标
2. 明确优先级
3. 明确每一项会改哪些文件
4. 明确每一项的依赖关系
5. 明确每一项的验收点
6. 明确每一项的回滚思路

后续执行规则：

1. 先按本文档确认执行顺序
2. 每次只推进一个明确子项
3. 每次实施前，先说明改动边界
4. 每次实施后，再回到本文档更新状态

## 2. 适用范围

本文档覆盖的范围包括：

- `OpenClaw` 安装入口与封装层
- workflow/profile 安装逻辑
- overlay 配置结构
- hooks 运行时交付形态
- jobs 安装与治理方式
- `Telegram` / `Feishu` 通道基线
- `OpenViking` 记忆路线
- auto-evolution 强制启用策略
- 部署后验收与回滚
- 多服务器统一治理

本文档当前不覆盖：

- 全量 Secret 管理重构
- 新增更多模型 provider
- 新增更多记忆后端
- 新增更多即时通讯通道
- 产品层需求变更

## 3. 当前基线

当前已确认的安装与运行底座如下。

### 3.1 仓库内正式安装入口

- `scripts/openclaw-ops/install_workflow_profile.py`
- `setup.py`

说明：

- `install_workflow_profile.py` 是当前真实安装底座
- `setup.py` 是仓库层统一入口封装

### 3.2 已有技能基线

已有相关技能：

- `C:/Users/superma/.claude/skills/openclaw-server-setup`
- `C:/Users/superma/.claude/skills/openclaw-hardflow-automation`
- `C:/Users/superma/.claude/skills/openclaw-auto-evolution`
- `C:/Users/superma/.claude/skills/openclaw-workflow-deploy`

当前判断：

- 前 3 个技能提供的是分片经验
- `openclaw-workflow-deploy` 是新建的总技能入口

### 3.3 已有部署说明文档

已存在文档：

- `docs/2026-03-19-openclaw-安装与工作流部署说明.md`
- `docs/2026-03-19-openclaw-windows-本机部署说明.md`
- `docs/2026-03-19-openclaw-linux-服务器部署说明.md`

### 3.4 当前明确的运行策略

当前策略已经基本明确：

- `Feishu` 标准安装命令：
  - `npx -y @larksuite/openclaw-lark install`
- 记忆路线只保留：
  - 官方内置能力
  - `OpenViking`
- `OpenViking` 官方仓库：
  - <https://github.com/volcengine/OpenViking>
- `auto-evolution` 视为强制启用项

## 4. 当前主要问题画像

当前不是“没有能力”，而是“能力分散且运行边界不够稳定”。

主要问题如下：

### 4.1 安装入口分散

现象：

- 技能里有一部分安装说明
- 仓库里有正式脚本
- 还有不少手工命令和历史经验

问题：

- 新机器上线时容易选错入口
- 文档和实际运行路径容易逐渐偏离

### 4.2 配置层次混杂

现象：

- 基线配置、平台差异、运行时状态、通道、模型、记忆项混在一起

问题：

- Windows / Linux 难以稳定复用
- 后续排障时很难判断问题属于哪一层

### 4.3 Hooks 运行时形态不稳定

现象：

- 运行时曾出现 `.ts` 裸加载失败

问题：

- 说明源码形态和运行时交付形态没有统一好

### 4.4 Jobs 体系可观测性不足

现象：

- jobs 数量已经不少
- 但元信息没有完全收敛

问题：

- 很难快速回答每个 job 的归属、频率、日志位置和关闭方式

### 4.5 通道落地方式缺模板

现象：

- 本机要 `Telegram + Feishu`
- 服务器当前多是 `Telegram`

问题：

- 缺少统一模板
- 每次补飞书都像临时工程

### 4.6 记忆方案表达不统一

现象：

- `memory-core`
- `memory-openviking`
- `OpenViking`
- `plugins.allow`
- `plugins.slots.memory`
  这几层概念容易混

问题：

- 新机器接入时容易误操作
- 日志排障时很难快速区分插件层和服务层

### 4.7 验收与回滚还不够“执行化”

现象：

- 已有验收文档
- 但还没有完全沉淀成统一检查链路

问题：

- 很容易出现“装好了但半坏着”

### 4.8 多服务器治理仍偏手工

现象：

- 已经有多台服务器
- 已有远程脚本工具

问题：

- 仍然依赖逐台检查和逐台修

## 5. 优先级裁决规则

本 backlog 的优先级以以下规则排序：

1. 会不会影响所有后续动作的稳定性
2. 会不会影响 Windows / Linux 双平台一致性
3. 会不会持续制造难以定位的运行时故障
4. 会不会阻塞多服务器统一治理

基于这个规则，当前优先级如下。

### P0

- 部署入口统一
- 配置分层
- Hooks 运行时交付形态标准化

### P1

- Jobs 声明式治理
- OpenViking 记忆方案标准化
- 通道模板化

### P2

- 验收与回滚自动化
- 多服务器批量巡检与统一治理

## 6. 阶段规划

### 阶段 1：入口与配置基线

目标：

- 把“怎么装”和“配置落哪层”这两个基础问题固定下来

包含项：

- 6.1 部署入口统一
- 6.2 配置分层

阶段产出：

- 正式安装入口清单
- 平台差异配置方案
- 统一文档口径

阶段验收：

- 任何部署说明都能指向同一正式入口
- Windows 和 Linux 的配置差异不再依赖人工记忆

### 阶段 2：运行时稳定性

目标：

- 解决 hooks、jobs、记忆这几类最容易造成运行中断的问题

包含项：

- 6.3 Hooks 运行时交付形态标准化
- 6.4 Jobs 声明式治理
- 6.5 OpenViking 记忆方案标准化

阶段产出：

- Hooks 交付规则
- Jobs 元信息基线
- OpenViking 标准接入基线

阶段验收：

- Hooks 能按统一方式启用
- Jobs 的归属、频率、日志更清楚
- OpenViking 接入流程更标准

### 阶段 3：通道与验收

目标：

- 把通道模板和部署后检查固定下来

包含项：

- 6.6 通道模板化
- 6.7 验收与回滚自动化

阶段产出：

- `telegram-only`
- `feishu-only`
- `telegram+feishu`
- 验收脚本或验收清单

阶段验收：

- 任意机器都能按模板快速落通道
- 部署后能快速得出可用性结论

### 阶段 4：多服务器治理

目标：

- 让多服务器统一治理成为正式能力

包含项：

- 6.8 多服务器批量巡检与统一治理

阶段产出：

- 多服务器差异巡检方法
- 批量修正入口
- 批量验收口径

阶段验收：

- 能统一查看关键配置差异
- 能批量补齐关键基线

## 7. 详细优化项

### 7.0 评分与 gate 接入主流程

优先级：

- `P0`

状态：

- `进行中（2026-03-20 已完成第一批接线）`

目标：

- 把 HardFlow 的 `G0-G6` 从“规则存在、步骤分散”升级成“有正式统一入口的主流程”

当前问题：

1. `score-policy.json`、`check-score-gate.mjs`、`hardflow-v1.lobster.yaml` 都已存在
2. direct 模式此前主要依赖超长命令串，而不是正式 workflow 入口
3. gate 虽然已经接在流程里，但入口不统一，后续难以继续挂接验证、验收和 review 规则

当前已落地：

1. `scripts/hardflow/hardflow-run.sh` 新增 `workflow` 子命令
2. `scripts/hardflow/hardflow-tmux-runner.sh` direct 模式改为调用 `workflow`
3. `scripts/hardflow/README.md` 已同步声明 `workflow` 为正式主流程入口

剩余步骤：

1. 决定 Lobster 模式是否也要收敛到统一入口
2. 明确 `post-test` 失败是否阻断 `release/final`
3. 把 gate 状态和 scorecard 产物继续挂接到更清晰的 workflow 编排层
4. 为后续“完成前验证”和“部署后验收”预留稳定挂载点

候选涉及文件：

- `scripts/hardflow/hardflow-run.sh`
- `scripts/hardflow/hardflow-tmux-runner.sh`
- `scripts/hardflow/hardflow-v1.lobster.yaml`
- `scripts/hardflow/README.md`
- `scripts/hardflow/score-policy.json`
- `scripts/hardflow/SCORECARD_SCHEMA.md`

验收点：

1. direct 模式下存在一个正式统一入口
2. `G0-G6` 不再只靠文档或长命令串维持
3. 后续验证、验收、review 能围绕同一个入口继续接线

回滚思路：

1. 若统一入口不稳定，可保留现有 `score-gate` 和分步命令不动
2. 先把 `workflow` 作为推荐入口，必要时仍允许逐步调试

风险：

1. direct 与 Lobster 双入口短期并存，仍可能产生少量口径分叉
2. 如果不继续推进后续接线，仍会停留在“入口统一了一部分”

#### 7.0.1 完成前验证制度接入主流程

优先级：

- `P0`

状态：

- `进行中（2026-03-20 已完成第一批硬阻断接线）`

目标：

- 把“没有新鲜验证证据，不允许声称完成”从治理规则推进到 hardflow 主流程里的实际阻断

当前问题：

1. 规则已经在治理文档和技能中明确，但 direct 主流程里还没有正式挂载点
2. `git-push` 之前缺少统一的验证产物，容易出现“流程跑完了，但没有明确验证证据”的状态
3. 缺少一个当前 run 级别的验证文件来承接 gate、日志和关键交付产物

当前已落地：

1. `scripts/hardflow/hardflow-run.sh` 新增 `verify-completion` 子命令
2. 新增 `scripts/hardflow/check-completion-verification.sh`
3. `workflow` 主流程已在 `quality_gate_postdeploy` 后、`git-push` 前强制执行 `verify-completion`
4. `git-push` 当前显式依赖 `.workflow/gates/completion_verification.json`
5. 当前 run 的验证产物固定为 `.workflow/runs/<run_id>/verification/completion.json`

剩余步骤：

1. 决定 Lobster 流程是否也要接入同样的硬阻断
2. 决定是否把更多交付动作也统一纳入 `completion_verification` 依赖
3. 继续把完成前验证与部署后验收之间的证据格式做进一步收敛

候选涉及文件：

- `scripts/hardflow/hardflow-run.sh`
- `scripts/hardflow/check-completion-verification.sh`
- `scripts/hardflow/README.md`
- `docs/2026-03-20-openclaw-workflow-主升级方案.md`
- `docs/2026-03-19-openclaw-工作流治理与执行闭环升级说明.md`

验收点：

1. direct workflow 下，`git-push` 不再允许绕过完成前验证
2. 当前 run 的 gate、日志与关键产物有统一验证文件
3. “完成前验证”不再只是文档要求，而是执行层动作

回滚思路：

1. 如硬阻断影响太大，可先保留 `verify-completion` 产物生成，但暂时移除 `git-push` 的阻断依赖
2. 保留文档规则不变，执行层逐步收紧

风险：

1. 当前仍只对 direct workflow 完成了第一批接线，Lobster 口径尚未完全统一
2. 若验证产物定义过窄，后续仍可能需要扩展校验范围

#### 7.0.2 部署后验收测试接入主流程

优先级：

- `P0`

状态：

- `进行中（2026-03-20 已完成第一批主流程接线）`

目标：

- 把部署后验收测试从“部署完成后的经验动作”升级成 hardflow 主流程中的正式阶段

当前问题：

1. 验收清单和验收想法已经存在，但还没有 workflow 里的正式挂载点
2. `verify-completion` 缺少一个专门承接部署后运行态检查的验收文件
3. `OpenClaw` 这类系统型交付仅靠 `deploy/post-test` 不足以覆盖通道、hooks、jobs、插件面

当前已落地：

1. `scripts/hardflow/hardflow-run.sh` 新增 `acceptance-test` 子命令
2. 新增 `scripts/hardflow/check-deployment-acceptance.sh`
3. `workflow` 主流程已在 `quality_gate_postdeploy` 之后、`verify-completion` 之前强制执行 `acceptance-test`
4. 当前默认必检项为：
   - `openclaw gateway status`
   - `openclaw status`
   - `openclaw plugins list`
   - `openclaw hooks check --json`
   - `openclaw cron status --json`
5. 当前 run 的验收产物固定为 `.workflow/runs/<run_id>/acceptance/deployment.json`
6. `verify-completion` 已显式依赖 `.workflow/gates/deployment_acceptance.json`

剩余步骤：

1. 决定 Lobster 流程是否也要接入同样的验收阶段
2. 把 `OpenViking`、`Telegram`、`Feishu` 的验收命令进一步模板化
3. 明确哪些环境下可以把更多可选检查提升为默认必检项

候选涉及文件：

- `scripts/hardflow/hardflow-run.sh`
- `scripts/hardflow/check-deployment-acceptance.sh`
- `scripts/hardflow/check-completion-verification.sh`
- `scripts/hardflow/README.md`
- `docs/2026-03-20-openclaw-workflow-主升级方案.md`
- `docs/2026-03-19-openclaw-工作流治理与执行闭环升级说明.md`

验收点：

1. direct workflow 下，部署后验收成为正式阶段而不是口头约定
2. 当前 run 的部署后运行态检查有统一 JSON 产物
3. `verify-completion` 不再能绕过部署后验收直接通过

回滚思路：

1. 如主流程阻断过强，可先保留验收产物生成，但暂时移除 `verify-completion` 对其依赖
2. 继续保留文档层验收清单，执行层逐步收紧

风险：

1. 当前默认必检项仍主要覆盖 `OpenClaw` 基础运行面，`OpenViking` 与通道层默认检查还需继续模板化
2. direct 与 Lobster 仍存在阶段接线差异

### 7.1 部署入口统一

优先级：

- `P0`

目标：

- 让所有安装、同步、重装动作最终都收敛到同一正式入口

当前问题：

- 仓库脚本是正式入口
- 技能和历史文档里还有早期安装方式
- 新同学或新机器容易走偏

当前正式基线：

- `scripts/openclaw-ops/install_workflow_profile.py`
- `setup.py`
- `C:/Users/superma/.claude/skills/openclaw-workflow-deploy/scripts/deploy_openclaw_workflow.py`

建议目标态：

- 安装底座只保留一套
- 技能与包装脚本只做封装与参数解释
- 文档全部回指统一入口

候选涉及文件：

- `scripts/openclaw-ops/install_workflow_profile.py`
- `setup.py`
- `docs/2026-03-19-openclaw-安装与工作流部署说明.md`
- `docs/2026-03-19-openclaw-windows-本机部署说明.md`
- `docs/2026-03-19-openclaw-linux-服务器部署说明.md`
- `C:/Users/superma/.claude/skills/openclaw-workflow-deploy/SKILL.md`
- `C:/Users/superma/.claude/skills/openclaw-workflow-deploy/scripts/deploy_openclaw_workflow.py`

建议执行步骤：

1. 定义“正式入口”和“包装入口”的职责边界
2. 统一文档口径
3. 检查是否还有历史安装指令与当前基线冲突
4. 收敛外部引用到同一入口

阶段产出：

- 正式入口说明
- 包装脚本说明
- 文档与技能统一口径

验收点：

- 任一部署文档都能说清：
  - 正式入口是谁
  - 包装入口是谁
  - 两者区别是什么
- 不再存在 2 套互相竞争的“官方入口”

回滚思路：

- 若统一入口引发问题，保留原安装底座不动
- 仅回退包装层与文档层

风险：

- 风险不在代码执行，而在口径不一致
- 如果边界写不清，后续所有优化都会继续分叉

### 7.2 配置分层

优先级：

- `P0`

目标：

- 把配置从“混合态”拆成“基线 + 平台差异 + 运行时最终态”

当前问题：

- 一份配置里混入：
  - 平台差异
  - 模型
  - 通道
  - 记忆
  - 路径
  - 运行时状态

建议目标态：

- 仓库保存通用基线
- 平台差异单独定义
- 运行时最终态仍然落到本机/服务器 `~/.openclaw/openclaw.json`

建议结构：

- `openclaw/openclaw.json`
  - 通用基线
- `openclaw/platforms/windows-local.json`
  - Windows 本机差异
- `openclaw/platforms/linux-server.json`
  - Linux 服务器差异
- 运行时最终态
  - `C:/Users/<user>/.openclaw/openclaw.json`
  - `~/.openclaw/openclaw.json`

候选涉及文件：

- `openclaw/openclaw.json`
- 可能新增 `openclaw/platforms/`
- 安装脚本中的 overlay 合并逻辑
- 平台化文档

建议执行步骤：

1. 明确哪些项属于“平台无关”
2. 明确哪些项属于“平台差异”
3. 明确哪些项只能存在于运行时
4. 修改 overlay 合并策略或文档策略

阶段产出：

- 配置分层清单
- 平台差异配置草案
- overlay 合并规则说明

验收点：

- Windows / Linux 的路径、通道、service 差异能独立表达
- 仓库基线配置不再承载所有运行时状态

回滚思路：

- 若分层方案不稳定，保留现有基线文件
- 暂时只更新文档，不强行切换运行时

风险：

- 拆层过猛会导致文档、脚本、运行时短期错位
- 必须和安装入口统一项配合推进

### 7.3 Hooks 运行时交付形态标准化

优先级：

- `P0`

目标：

- 统一 hooks 的源码形态与运行时形态，减少平台差异故障

当前问题：

- 运行时曾出现 `.ts` 直接加载失败
- 说明当前“源码”和“运行时产物”没有边界

建议目标态：

- 仓库存源码
- 运行时只加载稳定可执行形态
- 安装脚本清楚知道应复制/启用哪一层

建议结构方向：

- `hooks/<name>/src/`
  - 源码
- `hooks/<name>/dist/`
  - 运行时产物
- 运行时实际加载 `dist` 或统一入口脚本

候选涉及文件：

- hooks 目录
- hooks 启用配置
- 相关安装脚本
- 相关部署文档

建议执行步骤：

1. 盘点当前哪些 hooks 仍依赖源码形态
2. 定义运行时可接受形态
3. 修改安装/复制策略
4. 更新平台差异说明

当前已落地（2026-03-20）：

1. 已新增 `scripts/openclaw-ops/sync_openclaw_hooks_files.py`
2. `install_workflow_profile.py` 已接入 `sync_runtime_hooks` 步骤
3. hooks 运行时目录已标准化为 `~/.openclaw/hooks-runtime`
4. `hooks.internal.load.extraDirs` 已从仓库源码目录切到运行时目录
5. 运行时已明确禁止 `.ts/.tsx/.map` 进入 hooks runtime
6. `integration/openclaw-bridge/hooks-install.md` 已同步更新为运行时目录策略

阶段产出：

- hooks 交付规范
- hooks 运行时目录规范
- hooks 启用规范

验收点：

- Windows / Linux 上的 hooks 装载方式一致
- 不再把 `.ts` 裸文件当正式运行时入口

回滚思路：

- 若新形态未稳定，保留旧 hooks 目录结构
- 先只做“规范定义 + 新目录并行”，暂不立即全量切换

风险：

- hooks 会直接影响 gateway 启动稳定性
- 需要避免“一次性切全部 hooks”

### 7.4 Jobs 声明式治理

优先级：

- `P1`

目标：

- 让 jobs 成为“可管理对象”，而不是一组零散安装脚本

当前问题：

- jobs 逻辑已经很多
- 但缺少统一元信息

建议目标态：

- 每个 job 都有统一元信息：
  - job 名称
  - 负责模块
  - 默认频率
  - 日志位置
  - 安装入口
  - 回滚方式
  - 是否强制启用

建议结构方向：

- `scripts/openclaw-ops/jobs-manifest.json`
  - 统一 jobs 元信息

候选涉及文件：

- `scripts/openclaw-ops/install_*_job.py`
- `scripts/openclaw-ops/` 下 jobs 安装逻辑
- 可能新增的 `jobs-manifest.json`
- 部署说明文档

建议执行步骤：

1. 盘点所有现有 job
2. 给每个 job 补元信息
3. 收敛文档和安装逻辑
4. 统一日志归属和关闭方式

阶段产出：

- jobs 清单
- jobs manifest
- jobs 日志与回滚说明

验收点：

- 任一 job 都能回答：
  - 谁负责
  - 多久跑一次
  - 日志在哪
  - 怎么关

回滚思路：

- 若 manifest 方案未稳定，先保留旧安装脚本
- manifest 先只做说明与元信息管理

风险：

- 一次性梳理 jobs 量较大
- 容易在“文档化”与“代码收敛”之间拉扯

### 7.5 OpenViking 记忆方案标准化

优先级：

- `P1`

目标：

- 把 `OpenViking` 固化为标准记忆增强后端

当前问题：

- 插件层和服务层概念容易混
- 端口、日志、启动方式没有完全标准化

建议目标态：

- 服务层：
  - `OpenViking`
- 插件层：
  - `memory-openviking`
- 路由层：
  - `plugins.allow`
  - `plugins.slots.memory`
- 官方内置能力作为补充，而不是并行扩展路线

候选涉及文件：

- 记忆相关配置文档
- 运行时配置
- OpenViking 启动脚本
- `openclaw-workflow-deploy` 技能文档与脚本

建议执行步骤：

1. 固化“服务层 / 插件层 / 路由层”三层解释
2. 固化标准端口与例外处理方式
3. 固化健康检查与日志路径
4. 固化 Windows / Linux 差异说明

当前已落地（2026-03-20）：

1. 已新增 `scripts/openclaw-ops/check_openviking_stack.py`
2. 已新增 `integration/openclaw-bridge/openviking-stack.md`
3. `acceptance-test` 已默认接入 OpenViking 三层检查
4. 已把 OpenViking 标准产物固定为：
   - `.workflow/runs/<run_id>/acceptance/openviking-stack.json`
   - `.workflow/gates/openviking_stack.json`
5. `openclaw/openclaw.json` 已明确默认 `plugins.slots.memory = "memory-core"` 基线

阶段产出：

- OpenViking 标准接入说明
- 健康检查与日志说明
- 运行时配置说明

验收点：

- 新机器能按统一步骤接入 OpenViking
- 遇到故障时能快速区分：
  - 服务没起来
  - 插件没加载
  - 槽位没绑定

回滚思路：

- 若增强记忆接入不稳定，允许回退到官方内置能力
- 但不新增其他第三方记忆路线

风险：

- 记忆问题通常表现为“看起来能用，但质量不稳定”
- 所以必须把健康检查一起纳入标准化

### 7.6 通道模板化

优先级：

- `P1`

目标：

- 让 `Telegram` 与 `Feishu` 的接入变成模板，而不是手工经验

当前问题：

- 本机要双通道
- 服务器当前多数只有 TG
- 补飞书仍偏手工

建议目标态：

- 明确 3 种模板：
  - `telegram-only`
  - `feishu-only`
  - `telegram+feishu`

固定规则：

- `Feishu` 安装命令固定为：
  - `npx -y @larksuite/openclaw-lark install`

候选涉及文件：

- 平台部署文档
- `openclaw/openclaw.json`
- 可能新增的通道模板文档或 overlay 片段
- `openclaw-workflow-deploy` 技能文档

建议执行步骤：

1. 明确每种模板的最小配置项
2. 补齐服务器飞书方案说明
3. 把代理、token、policy 项写成模板清单

阶段产出：

- 通道模板说明
- 双通道标准方案

验收点：

- 任意机器都能按模板快速落地
- 不再把飞书视为“临时补丁”

回滚思路：

- 模板可先从文档层落地
- 不要求一次性把所有服务器都切成双通道

风险：

- 通道问题容易被网络环境放大
- 模板要区分“配置正确”和“网络可达”两层

### 7.7 验收与回滚自动化

优先级：

- `P2`

目标：

- 把部署后的检查和回滚从“经验动作”升级成“标准动作”

当前问题：

- 现在有验收文档
- 但还没有统一成固定检查链路

建议目标态：

- 有统一验收项
- 有统一输出格式
- 有统一回滚最小步骤

候选检查项：

- `openclaw --version`
- `openclaw gateway status`
- `openclaw status`
- `openclaw plugins list`
- hooks 状态
- jobs 状态
- `OpenViking` 健康状态
- `Telegram` 状态
- `Feishu` 状态

候选涉及文件：

- `integration/openclaw-bridge/acceptance-checklist.md`
- 可能新增验收脚本
- 部署技能文档

建议执行步骤：

1. 固化最小验收清单
2. 固化输出格式
3. 固化最小回滚步骤
4. 再考虑自动化脚本

阶段产出：

- 验收清单 v2
- 回滚清单 v1
- 候选自动化脚本

验收点：

- 部署后能快速判定：
  - 可用
  - 半可用
  - 不可用

回滚思路：

- 验收脚本本身不应变成系统单点依赖
- 失败时仍可回到手工最小检查

风险：

- 如果一开始就做成“全自动强校验”，反而可能卡住当前部署节奏

### 7.8 多服务器批量巡检与统一治理

优先级：

- `P2`

目标：

- 将多服务器治理从“人工逐台”升级成“有标准入口的运维动作”

当前问题：

- 已有多台服务器
- 已有远程脚本工具
- 但缺少统一巡检与批量修正方案

现有可用工具：

- `D:/ssh_keys/tmux-connect.sh`
- `D:/ssh_keys/tmux-ai-read.sh`
- `D:/ssh_keys/my-ssh.sh`
- `D:/ssh_keys/my-scp.sh`

建议目标态：

- 可批量查看关键配置差异
- 可批量补齐关键基线
- 可批量做最小验收

候选涉及文件：

- 多服务器巡检文档
- 技能脚本
- 远程运维包装脚本

建议执行步骤：

1. 定义需要统一巡检的关键项
2. 定义多服务器差异输出格式
3. 定义批量修正入口
4. 定义批量验收输出

阶段产出：

- 巡检清单
- 差异报告格式
- 批量执行入口

验收点：

- 能快速看到各服务器关键配置差异
- 能批量补齐至少一类高频配置项

回滚思路：

- 批量修正必须保留“逐台回退”能力
- 不直接做不可逆批量覆盖

风险：

- 多服务器批量操作天然有放大风险
- 必须建立在前面几阶段已经收敛完成的基础上

## 8. 第一批建议立即执行的事项

建议现在先执行这 4 项：

1. 7.0 评分与 gate 接入主流程
2. 7.0.1 完成前验证制度接入主流程
3. 7.0.2 部署后验收测试接入主流程
4. 7.1 部署入口统一
5. 7.2 配置分层
6. 7.3 Hooks 运行时交付形态标准化
7. 7.4 Jobs 声明式治理

原因：

- 7.0 决定 workflow 主流程是否真正“过线化”
- 这几项直接决定平台基线是否稳
- 后面的记忆、通道、验收和多服务器能力都会依赖它们

## 9. 暂不优先处理的事项

当前阶段先不优先处理：

- 全量 Secret 治理
- 模型 provider 再扩张
- 引入额外第三方记忆路线
- 扩充更多通道类型

原因：

- 这些事项不如“安装入口统一、配置收敛、运行稳定”更关键

## 10. 推荐执行顺序

严格建议按以下顺序推进：

1. 7.0 评分与 gate 接入主流程
2. 7.0.1 完成前验证制度接入主流程
3. 7.0.2 部署后验收测试接入主流程
4. 7.1 部署入口统一
5. 7.2 配置分层
6. 7.3 Hooks 运行时交付形态标准化
7. 7.4 Jobs 声明式治理
8. 7.5 OpenViking 记忆方案标准化
9. 7.6 通道模板化
10. 7.7 验收与回滚自动化
11. 7.8 多服务器批量巡检与统一治理

## 11. 每次实施时的输出要求

后续每次实施一个子项时，统一输出：

1. 修改文件
2. 直接影响
3. 间接影响
4. 配置变更
5. 验收点
6. 当前风险
7. 下一步建议

## 12. 当前建议

文档补细后，建议从以下动作开始：

- 先执行 `7.1 部署入口统一`

因为这一步做完后：

- 文档口径会统一
- 技能和脚本边界会统一
- 后续配置分层和 hooks/jobs 收敛都会更稳
