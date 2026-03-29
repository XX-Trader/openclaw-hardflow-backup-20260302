# G2 Frontend — 评分标准

> 适用 Gate：`frontend` | 维度数：5 | 阈值：overall ≥ 92

## visual_design (视觉设计)

### 满分 (95-100)
- 使用了一致的设计系统（色板 ≤ 5 色，间距系统倍数统一）
- 有明确的视觉层次（标题/正文/辅助文字至少 3 级）
- 配色和谐、对比度符合 WCAG AA 标准
- 图标风格统一

### 良好 (85-94)
- 设计系统基本一致，偶尔有 1-2 处不统一
- 视觉层次基本清晰

### 需改进 (70-84)
- 色板混乱或超过 6 色
- 间距不一致（允差 > 4px）
- 缺少明确的视觉层次

### 不合格 (< 70)
- 无设计系统
- 颜色感觉随意
- 排版混乱

### 扣分规则
| 问题 | 扣分 |
|------|------|
| 无设计系统或色板混乱 | -15 |
| 间距不一致（允差 > 4px） | -8 |
| 缺少 hover/focus 状态 | -5 |
| 字体混用超过 3 种 | -5 |
| 图标风格不统一 | -3 |

---

## information_architecture (信息架构)

### 满分 (95-100)
- 导航结构清晰直观，用户 3 步内可达任何核心功能
- 页面信息分组合理，有清晰的视觉区块
- 面包屑/标签/侧边栏等导航辅助完整

### 良好 (85-94)
- 导航基本清晰，个别深层页面需要 4-5 步
- 信息分组基本合理

### 扣分规则
| 问题 | 扣分 |
|------|------|
| 核心功能需 5 步以上才能到达 | -10 |
| 页面信息无分组 | -8 |
| 缺少导航辅助（面包屑等） | -5 |

---

## interaction_quality (交互质量)

### 满分 (95-100)
- 所有可点击元素有 hover/active 状态反馈
- 表单有实时校验和清晰的错误提示
- 加载状态有 loading indicator
- 动画流畅（≤ 300ms 过渡）

### 扣分规则
| 问题 | 扣分 |
|------|------|
| 按钮无 hover 状态 | -5 |
| 表单无校验反馈 | -8 |
| 缺少 loading 状态 | -5 |
| 动画卡顿或过长 (> 500ms) | -3 |

---

## responsive_accessibility (响应式与无障碍)

### 满分 (95-100)
- 移动端/平板/桌面三端布局均可用
- 所有交互元素可通过键盘操作
- 色彩对比度 ≥ 4.5:1 (WCAG AA)
- 图片有 alt 属性

### 扣分规则
| 问题 | 扣分 |
|------|------|
| 移动端布局断裂 | -15 |
| 键盘无法操作关键功能 | -8 |
| 对比度不足 | -5 |
| 图片缺少 alt | -3 |

---

## code_structure (代码结构)

> 注：此维度会与确定性检查（lint 通过率）加权合并，权重约 40% 确定性 + 60% reviewer

### 满分 (95-100)
- 组件拆分合理（单组件 ≤ 300 行）
- 样式与逻辑分离
- 无重复代码块
- 命名语义化

### 扣分规则
| 问题 | 扣分 |
|------|------|
| 单组件超过 500 行 | -10 |
| 存在大量重复代码 | -8 |
| 命名不语义化 | -5 |
| 样式和逻辑混杂 | -5 |

---

## Few-shot 判分示例

### 示例 1：高分 (overall = 93)

```json
{
  "gate": "frontend",
  "dimensions": {
    "visual_design": 92,
    "information_architecture": 94,
    "interaction_quality": 91,
    "responsive_accessibility": 95,
    "code_structure": 93
  },
  "deduction_reasons": {
    "visual_design": ["按钮圆角不完全统一（部分 4px，部分 8px）"],
    "interaction_quality": ["下拉菜单关闭动画稍显突兀"]
  },
  "summary": "前端视觉和交互质量良好，仅有小的一致性问题"
}
```

### 示例 2：低分 (overall = 72)

```json
{
  "gate": "frontend",
  "dimensions": {
    "visual_design": 65,
    "information_architecture": 78,
    "interaction_quality": 68,
    "responsive_accessibility": 75,
    "code_structure": 72
  },
  "deduction_reasons": {
    "visual_design": [
      "无统一色板，至少使用了 8 种不同颜色",
      "间距从 8px 到 24px 无规律",
      "字体混用了 4 种"
    ],
    "interaction_quality": [
      "按钮无 hover 状态",
      "表单提交无 loading 状态",
      "错误提示不清晰"
    ],
    "responsive_accessibility": [
      "移动端下表格直接溢出"
    ],
    "code_structure": [
      "App.vue 超过 800 行",
      "多处重复的 API 调用逻辑"
    ]
  },
  "summary": "前端缺乏设计系统，交互反馈不完善，代码结构臃肿"
}
```
