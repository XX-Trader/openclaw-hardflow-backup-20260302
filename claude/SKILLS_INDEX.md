# 技能索引 (SKILLS_INDEX)

> 本索引列出了所有可用的专业技能。在执行任务前，请先查阅本索引，找到匹配的技能并读取其内容。

**最后更新**: 2026-01-25
**最新升级**:
- ✨ **智能路由系统 v1.0** - NEW ⭐ 自动任务路由，117 个 Subagent，150+ 关键词，80+ 文件类型
- `ui-ux-pro-max` v2.1.0 - UI/UX 设计智能系统（50+ 风格、21+ 配色、9 种技术栈）
- `universal-travel-planner` v2.6 - 新增多景点对比与选择决策指南

---

## 📂 目录

- [🤖 智能路由系统](#-智能路由系统) **NEW**
- [项目开发](#项目开发)
- [部署运维](#部署运维)
- [测试修复](#测试修复)
- [文档处理](#文档处理)
- [设计创作](#设计创作)
- [思考工具](#思考工具)
- [生活工具](#生活工具)
- [其他工具](#其他工具)

---

## 🤖 智能路由系统

### intelligent-router ⭐ NEW
**路径**: `~/.claude/skills/intelligent-router/SKILL.md`
**版本**: 1.0.0 | **更新**: 2026-01-25
**类型**: 自动任务路由系统
**用途**: 基于关键词匹配和文件类型检测的自动任务路由

**核心功能**:
| 功能 | 数量 | 说明 |
|------|------|------|
| **Subagent 支持** | 117 个 | 覆盖产品、设计、架构、开发、测试、运维 |
| **关键词路由** | 150+ | 自动识别任务类型并路由 |
| **文件类型路由** | 80+ | 基于文件扩展名智能匹配 |
| **优先级系统** | 4 级 | 用户显式 > 关键词 > 文件类型 > 任务推断 |

**工作流程**:
```
用户输入 → 显式调用检测 → 关键词/文件类型匹配 → 路由到 Subagent → Task tool 执行 → 结果整合
```

**显式调用系统** ⭐ NEW:

为了更精确地控制任务路由，系统支持三种显式调用格式：

##### 1. 技能调用
```
[调用技能: <技能名>] 执行 <任务描述>
```
**示例**:
- `[调用技能: pdf] 提取这个 PDF 中的表格数据`
- `[调用技能: frontend-design] 设计一个登录页面`
- `[调用技能: auto-fix] 修复这个测试失败的问题`

##### 2. Subagent 调用
```
[调用 Subagent: <Agent 类型>] 执行 <任务描述>
```
**示例**:
- `[调用 Subagent: smart-flow:python-expert] 优化这段代码性能`
- `[调用 Subagent: smart-flow:backend-developer] 创建用户认证 API`
- `[调用 Subagent: pr-review-toolkit:code-reviewer] 审查这个 PR`

##### 3. 组合调用
```
[调用组合: <组合名>] 执行 <任务描述>
```
**示例**:
- `[调用组合: 量化交易组合] 分析这个策略的风险和收益`
- `[调用组合: 全栈开发组合] 从零开发一个待办事项应用`
- `[调用组合: 代码审查组合] 审查这个 PR 的代码质量和安全性`

**优先级**:
```
1. 显式调用声明（最高优先级）⭐
   └─> 直接使用指定技能/Agent，无需匹配

2. 用户显式指定
   └─> 如"使用 XXX agent"

3. 关键词匹配
   └─> 根据 triggers.keywords 自动匹配

4. 文件类型检测
   └─> 根据正在编辑的文件类型匹配
```

**详细文档**: [显式调用使用指南](skills/intelligent-router/docs/EXPLICIT_CALL_GUIDE.md)

**支持的 Subagent 类别**:

#### 产品与设计 (8个)
- `product-manager` - 产品经理（PRD、需求分析）
- `ui-ux-designer` - UI/UX 设计师
- `architect-review` - 架构审查
- `api-documenter` - API 文档工程师
- `impact-analyzer-frontend/backend/strategy` - 需求分析

#### 架构与后端 (15个)
- `backend-architect` - 后端架构师
- `database-architect` - 数据库架构师
- `backend-developer` - 后端开发
- `php-developer` / `ruby-expert` / `rails-expert` - PHP/Ruby 专家
- `graphql-architect` - GraphQL 架构师
- `database-optimizer` / `database-admin` / `sql-expert` - 数据库优化
- `laravel-vue-developer` / `directus-developer` / `drupal-developer` - 全栈/开发

#### 前端开发 (12个)
- `frontend-developer` - 前端开发
- `react-performance-optimization` - React 性能优化
- `typescript-expert` / `javascript-developer` - TS/JS 专家
- `nextjs-app-router-developer` - Next.js App Router 专家

#### 数据与AI (10个)
- `ai-engineer` - AI 工程师
- `data-engineer` - 数据工程师
- `ml-engineer` - 机器学习工程师
- `quant-analyst` - 量化分析师
- `data-analyst` - 数据分析师
- `prompt-engineer` - Prompt 优化专家

#### 运维与部署 (10个)
- `deployment-engineer` - 部署工程师
- `devops-troubleshooter` - DevOps 故障排查
- `cloud-architect` - 云架构师
- `github-actions-runner` - GitHub Actions 专家
- `db-deploy` / `windows-fullstack-deploy` / `deployment-test` - 部署技能

#### 测试与质量 (8个)
- `test-automator` - 测试自动化
- `code-reviewer` - 代码审查
- `security-auditor` - 安全审计
- `debugger` - 调试专家
- `test-driven-development` - TDD

#### 编程语言 (11个)
- `python-expert` / `golang-expert` / `java-developer` - Python/Go/Java
- `cpp-engineer` / `rust-expert` / `c-developer` - C++/Rust/C
- `typescript-expert` / `javascript-developer` - TS/JS

#### 研究与分析 (10个)
- `research-orchestrator` - 研究协调器
- `comprehensive-researcher` - 综合研究员
- `technical-researcher` - 技术研究员
- `academic-researcher` - 学术研究员

#### 其他专业 (30+)
- 区块链: `blockchain-developer`, `crypto-trader`, `arbitrage-bot`, `defi-strategist`
- MCP: `mcp-server-architect`, `mcp-security-auditor`, `mcp-testing-engineer`
- 网络: `network-engineer`, `performance-engineer`
- 内容: `social-media-copywriter`, `podcast-transcriber`
- 文本处理: `ocr-grammar-fixer`, `text-comparison-validator`

**触发方式**: 自动触发（无需手动指定）
- ✅ 关键词匹配：用户输入包含特定关键词
- ✅ 文件类型检测：正在编辑特定类型文件
- ✅ 用户显式指定："使用 XXX agent"

**配置文件**:
- `config/agent_registry.json` - 117 个 Subagent 注册表
- `config/keyword_routes.json` - 150+ 关键词路由规则
- `config/file_type_routes.json` - 80+ 文件类型路由规则

**优势**:
- 🚀 **零配置** - 无需手动指定，系统自动识别
- 🔒 **上下文隔离** - Task tool 独立上下文执行
- ⚡ **并行执行** - 支持多个 Subagent 同时工作
- 📊 **实时进度** - 完整的执行状态跟踪

---

## 项目开发

### crypto-exchange-api
**路径**: `skills/crypto-exchange-api.md`
**版本**: 1.1.0 | **更新**: 2026-01-19
**用途**: 加密货币交易所API参考技能（CEX + DEX + 衍生品）
**适用场景**:
- 交易所API端点查询（Binance/OKX/Gate.io/Bitget/Bybit）
- DEX API查询（Hyperliquid/dYdX/GMX/Drift）
- 期权平台API（Deribit/Aevo/Derive）
- 预测市场API（Polymarket）
- 现货聚合器（Jupiter/1inch/Uniswap）
- 符号格式转换、响应结构处理
- 实测避坑指南（Gate.io直接返回list、Bitget V2端点）
**核心内容 - CEX**:
| 交易所 | 现货端点 | 合约端点 | Symbol格式 |
|--------|----------|----------|------------|
| Binance | `/api/v3/exchangeInfo` | `/fapi/v1/exchangeInfo` | `RIVERUSDT` |
| OKX | `?instType=SPOT` | `?instType=SWAP` | `RIVER-USDT` |
| Gate.io | `/api/v4/spot/currency_pairs` | `/api/v4/futures/usdt/contracts` | `RIVER_USDT` |
| Bitget | `/api/v2/spot/public/symbols` | `?productType=USDT-FUTURES` | `RIVERUSDT` |
| Bybit | `/v5/market/tickers?spot` | `?category=linear` | `RIVERUSDT` |
**核心内容 - DEX/衍生品**:
| 类型 | 推荐平台 | 文档 |
|------|---------|------|
| 🔥 Perp DEX | Hyperliquid, dYdX, GMX, Drift | 链上高性能合约 |
| 📊 期权 | Deribit⭐, Aevo, Derive | 行业标准期权API |
| 🔮 预测市场 | Polymarket | Polygon CTF框架 |
| 💱 现货DEX | Jupiter⭐, 1inch, Uniswap | 聚合器最优路径 |
| 📡 价格喂价 | Pyth, CoinGecko, DexScreener | 实时数据预言机 |
**触发关键词**: "交易所API"、"查询交易对"、"Binance/OKX/Gate.io/Bitget/Bybit"、"现货合约"、"DEX"、"Hyperliquid"、"dYdX"、"Jupiter"、"Deribit"、"Polymarket"

### feature-development
**路径**: `skills/feature-development/SKILL.md`
**用途**: Django + Vue 全栈功能开发标准化流程
**适用场景**:
- 新功能开发（简单/中等/复杂）
- 需求分析、技术方案设计、API设计、数据库设计、UI原型设计
**触发关键词**: "新功能"、"开发"、"实现"、"添加功能"

---

## 部署运维

### db-deploy
**路径**: `skills/db-deploy/DEPLOYMENT_CHECKLIST.md`
**用途**: 全栈项目自动部署技能（服务器部署）
**适用场景**:
- Django 后端 + Vue3 前端 + MySQL 数据库 + Redis 缓存 + Nginx 反向代理
- 服务器部署、项目更新、维护
**触发关键词**: "部署"、"发布"、"上线"、"服务器"

### windows-fullstack-deploy
**路径**: `skills/windows-fullstack-deploy/SKILL.md`
**用途**: Windows 本地开发环境自动化部署
**适用场景**:
- 在 Windows 上搭建本地开发环境
- Django/FastAPI/Flask + Vue3/React + MySQL + Redis
**触发关键词**: "本地环境"、"本地部署"、"Windows 环境"

### deployment-test
**路径**: `skills/deployment-test/SKILL.md`
**用途**: 部署后自动化测试
**适用场景**:
- 部署后的验收测试
- 端口检测、API接口测试、浏览器UI自动化测试
**触发关键词**: "测试部署"、"验收测试"、"部署后测试"

---

## 测试修复

### auto-fix
**路径**: `skills/auto-fix/SKILL.md`
**用途**: 全自动测试-修复循环系统
**适用场景**:
- 自动运行测试、分析问题、修复代码、验证修复、Git提交
- Django + Vue 全栈项目
**触发关键词**: "修复bug"、"测试失败"、"自动修复"

---

## 文档处理

### docx
**路径**: `skills/skills/document-skills/docx/SKILL.md`
**用途**: Word 文档处理
**适用场景**: 创建、编辑、分析 .docx 文件

### pdf
**路径**: `skills/skills/document-skills/pdf/SKILL.md`
**用途**: PDF 文档处理
**适用场景**: 提取文本/表格、创建/合并/拆分 PDF、表单填写

### xlsx
**路径**: `skills/skills/document-skills/xlsx/SKILL.md`
**用途**: Excel 表格处理
**适用场景**: 创建/编辑/分析电子表格、公式、格式化、数据可视化

### pptx
**路径**: `skills/skills/document-skills/pptx/SKILL.md`
**用途**: PowerPoint 演示文稿处理
**适用场景**: 创建/编辑/分析 .pptx 文件、布局、演示

---

## 设计创作

### frontend-design
**路径**: `skills/skills/document-skills/frontend-design/SKILL.md`
**用途**: 前端界面设计
**适用场景**: 创建高质量前端界面、网页组件、应用界面

### algorithmic-art
**路径**: `skills/skills/algorithmic-art/SKILL.md`
**用途**: 算法艺术创作
**适用场景**: 使用 p5.js 创建算法艺术、生成艺术、流场、粒子系统

### canvas-design
**路径**: `skills/skills/canvas-design/SKILL.md`
**用途**: Canvas 设计创作
**适用场景**: 创建 PNG/PDF 格式的视觉设计、海报、艺术作品

### brand-guidelines
**路径**: `skills/skills/brand-guidelines/SKILL.md`
**用途**: 品牌规范应用
**适用场景**: 应用 Anthropic 官方品牌色彩和排版

### theme-factory
**路径**: `skills/skills/theme-factory/SKILL.md`
**用途**: 主题样式工具
**适用场景**: 为文档/幻灯片/网页应用预定义主题

### ui-ux-pro-max ⭐ NEW
**路径**: `skills/ui-ux-pro-max/SKILL.md`
**版本**: 2.1.0 | **更新**: 2026-01-19
**用途**: UI/UX 设计智能系统
**适用场景**:
- 设计新的 UI 组件或页面
- 选择配色方案和字体搭配
- 审查代码的 UX 问题
- 构建落地页或仪表盘
- 实现无障碍访问要求
**核心功能**:
| 类别 | 数量 | 说明 |
|------|------|------|
| **UI 风格** | 50+ | 极简主义、玻璃拟态、新拟态、野兽派、3D超写实、暗色模式等 |
| **配色方案** | 21+ | SaaS、电商、金融、医疗、教育、游戏等不同产品类型 |
| **技术栈** | 9 种 | React, Next.js, Vue, Svelte, SwiftUI, React Native, Flutter, Tailwind, shadcn/ui |
| **字体搭配** | 50+ | 标题与正文的字体配对 |
| **图表类型** | 20+ | 不同数据可视化场景 |
| **UX 规范** | 99+ | 无障碍访问、交互、性能等最佳实践 |
**设计原则优先级**:
1. **无障碍访问** (关键) - WCAG 4.5:1 对比度、焦点环、ARIA 标签
2. **触摸与交互** (关键) - 44x44px 触摸目标、加载状态、错误反馈
3. **性能** (高) - 图片优化、减少动画
4. **布局与响应式** (高) - viewport、16px 最小字体、z-index 管理
**触发关键词**:
- "设计界面"、"UI/UX"、"前端界面"
- "配色方案"、"字体搭配"
- "落地页"、"仪表盘"、"SaaS 产品"
- "无障碍访问"、"可访问性"
- "玻璃拟态"、"极简主义"、"暗色模式"

---

## 思考工具

### deepdive
**路径**: `skills/deepdive/deepdive-en.md`
**用途**: 深度迭代思考
**适用场景**:
- 架构设计问题
- 技术选型问题
- 产品方向问题
- 任何没有明确答案的复杂问题
**触发关键词**: "深度思考"、"深入分析"、"探索"

---

## 生活工具

### universal-travel-planner v2.6
**路径**: `skills/universal-travel-planner.md`
**版本**: 2.6.0 | **更新**: 2025-01-18
**用途**: 全功能旅游规划技能（整合高德地图、小红书、百度地图）
**适用场景**:
- 制定旅游攻略（爬山、海滩、城市游览等）
- 路线规划（自驾、步行、公交）
- 天气查询、装备推荐
- 生成带地图的交互式HTML攻略
- 多景点对比与选择决策（NEW）
**核心功能**:
| 服务 | 功能 |
|------|------|
| **高德地图** | 天气、POI、周边、位置、路线规划（GCJ-02） |
| **小红书** | 攻略采集、用户评价、避坑指南、景点对比 |
| **百度地图** | 路线规划、轨迹绘制、HTML地图可视化（BD-09） |
| **智能推荐** | 根据天气+地点+活动+体力，生成装备清单 |
| **阻力分析** | 详细矩阵+检查清单（人/堵车/情绪/意外） |
| **路线说明** | 开车路线+徒步路线，含详细导航指令 |
| **详细攻略** | 厕所位置、补给点价格、拍照打卡点、放弃点、潮汐、开放时间 |
| **景点对比** | 多景点对比、选择决策、场景化推荐（NEW） |
| **替代方案** | 小红书MCP未安装时的浏览器搜索+通用知识 |
**触发关键词**:
- 核心：攻略、旅游、出行、路线、计划
- 地点：景点、美食、酒店、海滩、爬山、徒步、露营
- 服务：天气、装备、怎么去、推荐、预算
- 状态：周末去哪、假期去哪、附近有什么
**输出目录**: `旅游/output/`、`旅游/攻略/`
**地图访问**: 启动本地服务器后访问 `http://127.0.0.1:6789/`
**MCP依赖**:
- 高德地图：`amap-maps` ✅ 已安装
- 小红书：`@iflow-mcp/xhs-mcp@0.8.7` 🔧 需全局安装
- 百度地图：`@baidumap/mcp-server-baidu-map@1.0.5` 🔧 需全局安装
**统一管理目录**: `skills/travel-skills/` - 一键启动脚本、统一配置管理
**实战案例**: 广州南村万博 → 深圳东西冲海岸线徒步（已验证）

---

## 其他工具

### mcp-builder
**路径**: `skills/skills/mcp-builder/SKILL.md`
**用途**: MCP 服务器构建指南
**适用场景**: 创建 Model Context Protocol 服务器

### skill-creator
**路径**: `skills/skills/skill-creator/SKILL.md`
**用途**: 技能创建指南
**适用场景**: 创建新的自定义技能

### internal-comms
**路径**: `skills/skills/internal-comms/SKILL.md`
**用途**: 内部沟通写作
**适用场景**: 状态报告、领导层更新、公司通讯、FAQ等

### webapp-testing
**路径**: `skills/skills/webapp-testing/SKILL.md`
**用途**: Web 应用测试
**适用场景**: 使用 Playwright 进行交互式测试

---

## 使用原则

1. **按需加载**: 只在任务匹配时读取对应技能文件
2. **优先级**: 用户显式指令 > 项目 md文件 > 技能文件 > 常识最佳实践
3. **轻量原则**: 保持上下文轻量，避免盲目加载所有技能
4. **动态匹配**: 根据任务描述自动判断需要哪些技能

---

## 快速查找

| 需求 | 推荐技能 |
|------|---------|
| **交易所API** | **`crypto-exchange-api`** |
| **查询交易对** | **`crypto-exchange-api`** |
| **DEX/DeFi API** | **`crypto-exchange-api`** |
| **Hyperliquid/dYdX** | **`crypto-exchange-api`** |
| **Jupiter/Uniswap** | **`crypto-exchange-api`** |
| **Deribit/期权** | **`crypto-exchange-api`** |
| **Polymarket** | **`crypto-exchange-api`** |
| 新功能开发 | `feature-development` |
| 服务器部署 | `db-deploy` |
| 本地环境搭建 | `windows-fullstack-deploy` |
| 部署测试 | `deployment-test` |
| 修复Bug | `auto-fix` |
| 深度思考 | `deepdive` |
| **旅游攻略** | **`universal-travel-planner v2.2`** |
| **天气查询** | **`universal-travel-planner v2.2`** |
| **装备推荐** | **`universal-travel-planner v2.2`** |
| Word文档 | `docx` |
| PDF文档 | `pdf` |
| Excel表格 | `xlsx` |
| PPT演示 | `pptx` |
| 前端设计 | `frontend-design` |
| 创作艺术 | `algorithmic-art` |
| MCP服务器 | `mcp-builder` |
| 创建技能 | `skill-creator` |
