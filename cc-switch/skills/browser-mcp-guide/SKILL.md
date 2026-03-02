---
name: browser-mcp-guide
description: Chrome MCP 浏览器自动化工具使用指南
category: automation
tags: [browser, chrome, mcp, automation, testing]
version: 1.0.0
---

# Browser MCP Guide - Chrome 浏览器自动化指南

## 🎯 技能说明

本技能提供 Chrome MCP 工具的完整使用指南，帮助 Claude 正确、高效地使用浏览器自动化功能。

**适用场景**:
- 浏览器自动化测试
- UI 交互和验证
- 网页内容抓取
- 截图和录屏
- 网络请求监控

---

## ⚡ 自动读取机制

**重要**: 当用户请求涉及浏览器操作时，Claude 必须：

1. **首先读取**: [TOOLS.md](./TOOLS.md) - 完整的 Chrome MCP API 参考文档
2. **理解参数**: 查看每个工具的参数说明和示例
3. **参考示例**: 按照文档中的 Usage Examples 执行
4. **验证响应**: 对照 Response Format 确保正确解析返回数据

**触发条件**（满足任一即自动读取 TOOLS.md）:
- ✅ 用户明确提到"浏览器"、"chrome"、"打开网页"
- ✅ 需要截图、点击、填充表单等浏览器交互
- ✅ 需要监控网络请求、分析网页内容
- ✅ 任何使用 `mcp__chrome_____` 前缀的工具时
- ✅ 用户说"帮我查看网页"、"分析页面"等

**如何使用**:
```
用户: "帮我打开网页并截图"
Claude: [自动读取 TOOLS.md] → 查看 chrome_screenshot 参数 → 执行操作
```

---

## 📚 核心工具分类

### 1. 页面读取工具

#### `chrome_read_page` ⭐ 最重要
**用途**: 获取页面上可见元素的语义树

**何时使用**:
- 需要了解页面结构
- 查找可交互元素
- 定位按钮、链接、输入框
- **在任何交互前都应该先读取页面**

**关键参数**:
- `filter`: "interactive" 只显示可交互元素（推荐）
- `depth`: 限制 DOM 深度，减少输出
- `refId`: 聚焦某个元素的子树

**返回值**:
- 元素的 `ref` (用于后续点击/填充)
- 元素类型、文本内容
- 可访问性属性

**示例**:
```python
# 读取所有可见元素
chrome_read_page()

# 只读交互元素（推荐）
chrome_read_page(filter="interactive")
```

---

### 2. 交互工具

#### `chrome_click_element` ⭐ 推荐
**用途**: 点击页面元素（优先使用）

**何时使用**:
- 简单的点击操作
- 已知 ref 或选择器

**关键参数**:
- `ref`: 从 chrome_read_page 获取（优先使用）
- `selector`: CSS 选择器或 XPath
- `selectorType`: "css" 或 "xpath"
- `waitForNavigation`: 等待导航完成

**示例**:
```python
# 使用 ref（推荐）
chrome_click_element(ref="ref_123")

# 使用选择器
chrome_click_element(
    selector="button.submit",
    selectorType="css",
    waitForNavigation=True
)
```

#### `chrome_computer` ⭐ 最强大
**用途**: 鼠标键盘交互 + 截图

**何时使用**:
- chrome_click_element 失败时
- 需要复杂交互（拖拽、悬停）
- 需要截图验证
- **作为备用工具**

**action 类型**:
- `left_click` / `right_click` / `double_click` / `triple_click`
- `left_click_drag` - 拖拽
- `scroll` / `scroll_to` - 滚动
- `type` / `key` - 键盘输入
- `fill` / `fill_form` - 填充表单
- `hover` - 悬停
- `screenshot` - 截图（重要！）

**坐标系统**:
- 优先使用 `ref` 而非 `coordinates`
- 如果需要坐标，先用截图获取

**示例**:
```python
# 截图（验证或获取坐标）
chrome_computer(action="screenshot")

# 点击（使用 ref）
chrome_computer(
    action="left_click",
    ref="ref_123"
)

# 滚动
chrome_computer(
    action="scroll",
    scrollDirection="down",
    scrollAmount=3
)
```

---

### 3. 导航工具

#### `chrome_navigate`
**用途**: 导航到 URL 或刷新页面

**action 参数**:
- URL: 直接导航
- "back" / "forward": 历史导航
- `refresh=True`: 刷新页面

**示例**:
```python
chrome_navigate(url="https://example.com")
chrome_navigate(action="back")
chrome_navigate(refresh=True)
```

---

### 4. 表单工具

#### `chrome_fill_or_select`
**用途**: 填充表单（支持输入框、下拉、复选框）

**参数**:
- `value`: 字符串/数字/布尔值
- `selector` / `ref`: 元素定位

**示例**:
```python
chrome_fill_or_select(
    ref="ref_456",
    value="test@example.com"
)
```

#### `chrome_keyboard`
**用途**: 模拟键盘输入

**keys 示例**:
- 单键: "Enter", "Tab", "Escape"
- 组合键: "Ctrl+C", "Shift+Tab"
- 文本: "Hello World"

**示例**:
```python
chrome_keyboard(keys="Ctrl+C")
chrome_keyboard(keys="Enter")
```

---

### 5. 数据获取工具

#### `chrome_get_web_content`
**用途**: 获取页面文本或 HTML

**参数**:
- `textContent`: 获取可见文本（默认）
- `htmlContent`: 获取 HTML
- `selector`: 只获取某个元素

**示例**:
```python
# 获取全部文本
chrome_get_web_content(textContent=True)

# 获取某个元素的文本
chrome_get_web_content(
    selector="div.content",
    textContent=True
)
```

#### `chrome_console`
**用途**: 捕获浏览器控制台日志

**模式**:
- `snapshot`: 一次性捕获（等待2秒）
- `buffer`: 立即读取缓冲区

**用途**:
- 调试 JavaScript 错误
- 查看网络请求日志
- 验证前端行为

**示例**:
```python
chrome_console(mode="snapshot")
chrome_console(mode="buffer", pattern="error")
```

---

### 6. 截图和录屏

#### `chrome_screenshot`
**用途**: 截取页面截图

**参数**:
- `savePng`: 是否保存文件
- `storeBase64`: 是否返回 base64（推荐设为 true）
- `fullPage`: 全页面截图
- `selector`: 只截取某个元素

**示例**:
```python
# 查看（不保存）
chrome_screenshot(
    savePng=False,
    storeBase64=True,
    fullPage=True
)
```

#### `chrome_gif_recorder`
**用途**: 录制 GIF 动画

**action**:
- `start`: 开始录制（固定 FPS）
- `auto_start`: 自动录制（交互时自动捕获帧）
- `stop`: 停止并保存

**示例**:
```python
chrome_gif_recorder(action="auto_start")
# ... 执行一些操作 ...
chrome_gif_recorder(action="stop")
```

---

### 7. 高级工具

#### `chrome_request_element_selection`
**用途**: 用户手动选择元素（人机协作）

**何时使用**:
- 自动定位失败 3 次以上
- 元素没有明确的 ref 或选择器
- 需要用户精确指定

**示例**:
```python
chrome_request_element_selection(
    requests=[{
        "name": "提交按钮",
        "description": "点击页面右下角的提交按钮"
    }]
)
```

#### `chrome_network_capture`
**用途**: 捕获网络请求

**参数**:
- `needResponseBody`: 是否捕获响应体（需要 Debugger API）
- `includeStatic`: 是否包含静态资源

**示例**:
```python
chrome_network_capture(action="start", needResponseBody=True)
# ... 执行操作 ...
result = chrome_network_capture(action="stop")
```

---

## 🎓 最佳实践

### 1. 标准工作流程

```python
# 1. 导航到页面
chrome_navigate(url="https://example.com")

# 2. 读取页面结构（必须！）
chrome_read_page(filter="interactive")

# 3. 定位元素并交互
chrome_click_element(ref="ref_123")

# 4. 验证结果
chrome_computer(action="screenshot")
```

### 2. 降级策略

```python
# 优先使用 chrome_click_element
try:
    chrome_click_element(ref="ref_123")
except:
    # 失败则使用 chrome_computer
    chrome_computer(
        action="left_click",
        ref="ref_123"
    )
```

### 3. 复杂场景处理

**需要滚动查找元素**:
```python
chrome_read_page(filter="interactive")
chrome_computer(action="scroll", scrollDirection="down")
chrome_read_page(filter="interactive")
```

**表单填充**:
```python
# 方式1: 逐个填充
chrome_fill_or_select(ref="ref_1", value="name")
chrome_fill_or_select(ref="ref_2", value="email")

# 方式2: 批量填充
chrome_computer(
    action="fill_form",
    elements=[
        {"ref": "ref_1", "value": "name"},
        {"ref": "ref_2", "value": "email"}
    ]
)
```

**等待元素出现**:
```python
chrome_computer(
    action="wait",
    text="加载完成",
    appear=True,
    timeout=10000
)
```

---

## ⚠️ 常见错误和解决方法

### 错误 1: 元素找不到
**原因**: 没有先 read_page 或页面未加载完成

**解决**:
```python
# 先读取页面
chrome_read_page(filter="interactive")

# 或者等待
chrome_computer(action="wait", duration=2)
```

### 错误 2: 点击位置不对
**原因**: ref 过期或元素位置变化

**解决**:
```python
# 重新读取页面
chrome_read_page(filter="interactive")

# 或者使用坐标（需要先截图）
chrome_computer(action="screenshot")
chrome_computer(
    action="left_click",
    coordinates={"x": 500, "y": 300}
)
```

### 错误 3: 弹窗处理
**原因**: 有 alert/confirm/prompt 对话框

**解决**:
```python
# 处理对话框
chrome_handle_dialog(action="accept")

# 或者输入文本后接受
chrome_handle_dialog(
    action="accept",
    promptText="Hello"
)
```

---

## 📊 工具选择流程图

```
需要操作页面
    ↓
是否需要了解页面结构？
    ├─ 是 → chrome_read_page(filter="interactive")
    └─ 否 → 继续
         ↓
    是简单点击？
    ├─ 是 → chrome_click_element(ref=...)
    └─ 否 → 继续
         ↓
    需要截图/验证？
    ├─ 是 → chrome_computer(action="screenshot")
    └─ 否 → 继续
         ↓
    chrome_computer(action=...)
```

---

## 🔧 调试技巧

### 1. 查看 console 日志
```python
chrome_console(mode="snapshot", onlyErrors=True)
```

### 2. 截图验证
```python
chrome_screenshot(savePng=False, storeBase64=True)
```

### 3. 捕获网络请求
```python
chrome_network_capture(action="start")
# ... 执行操作 ...
chrome_network_capture(action="stop")
```

### 4. 逐步验证
```python
# 1. 截图
chrome_computer(action="screenshot")

# 2. 尝试操作
chrome_computer(action="left_click", ref="ref_123")

# 3. 再次截图验证
chrome_computer(action="screenshot")
```

---

## 🎯 典型使用场景

### 场景 1: 登录网站
```python
# 1. 导航
chrome_navigate(url="https://example.com/login")

# 2. 读取页面
chrome_read_page(filter="interactive")

# 3. 填充表单
chrome_fill_or_select(ref="ref_username", value="myuser")
chrome_fill_or_select(ref="ref_password", value="mypass")

# 4. 点击登录
chrome_click_element(ref="ref_login")

# 5. 等待导航
chrome_computer(action="wait", text="欢迎", appear=True)

# 6. 验证
chrome_screenshot(storeBase64=True)
```

### 场景 2: 数据抓取
```python
# 1. 导航
chrome_navigate(url="https://example.com/data")

# 2. 读取页面
chrome_read_page(filter="interactive")

# 3. 获取内容
content = chrome_get_web_content(textContent=True)

# 4. 或执行 JS
chrome_javascript(code="""
    return document.querySelectorAll('.item').map(el => el.textContent)
""")
```

### 场景 3: UI 测试
```python
# 1. 导航
chrome_navigate(url="https://example.com")

# 2. 记录 console
chrome_console(mode="snapshot", includeExceptions=True)

# 3. 执行操作
chrome_click_element(ref="ref_button")

# 4. 截图验证
chrome_screenshot(storeBase64=True)

# 5. 检查错误
chrome_console(onlyErrors=True)
```

---

## 📚 相关资源

**其他工具**:
- `chrome_javascript` - 执行 JS 代码
- `chrome_upload_file` - 上传文件
- `chrome_switch_tab` - 切换标签页
- `get_windows_and_tabs` - 获取所有窗口
- `chrome_close_tabs` - 关闭标签页

**完整工具列表**: 查看系统 prompt 中的 `available_tools` 部分

---

**更新时间**: 2026-01-05
**维护者**: superma
**版本**: 1.0.0
