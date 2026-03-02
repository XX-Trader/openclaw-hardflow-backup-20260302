# 部署测试报告

## 测试概览

| 项目 | 内容 |
|------|------|
| 项目名称 | {{projectName}} |
| 测试时间 | {{testTime}} |
| 测试人员 | {{tester}} |
| 测试环境 | {{environment}} |

## 测试摘要

| 指标 | 数值 |
|------|------|
| 总测试项 | {{totalTests}} |
| 通过 | {{passedTests}} |
| 失败 | {{failedTests}} |
| 通过率 | {{passRate}} |

---

## 端口检测结果

| 服务 | 端口 | 状态 | 响应时间 | 备注 |
|------|------|------|----------|------|
{{portTestResults}}

### 端口检测详情

{{portTestDetails}}

---

## API 测试结果

### 测试汇总

| 接口名称 | 方法 | 路径 | 预期状态 | 实际状态 | 预期Code | 实际Code | 结果 |
|---------|------|------|----------|----------|----------|----------|------|
{{apiTestResults}}

### 失败详情

{{apiTestFailures}}

### 成功接口示例

{{apiTestSuccess}}

---

## UI 测试结果

### 测试汇总

| 测试名称 | 页面 | 操作 | 结果 | 截图 |
|---------|------|------|------|------|
{{uiTestResults}}

### 失败详情

{{uiTestFailures}}

### 成功测试示例

{{uiTestSuccess}}

---

## 问题汇总

### 严重问题 (P0)

{{criticalIssues}}

### 重要问题 (P1)

{{majorIssues}}

### 一般问题 (P2)

{{minorIssues}}

---

## 建议

### 立即修复

{{immediateFixes}}

### 后续优化

{{futureImprovements}}

---

## 附录

### 测试环境信息

| 项目 | 内容 |
|------|------|
| 操作系统 | Windows 10/11 |
| Python 版本 | 3.10+ |
| Node.js 版本 | 20.19.0+ |
| 浏览器 | Chromium |

### 测试配置

```json
{{testConfig}}
```

### 测试日志

```
{{testLogs}}
```

---

**报告生成时间**: {{reportTime}}
**报告生成工具**: deployment-test skill v1.0
