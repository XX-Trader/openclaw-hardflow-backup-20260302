# 数据库设计文档模板

> **适用场景**: 中等/复杂功能
> **填写说明**: 定义所有表结构、字段、索引、关联关系

---

## 1. 数据库概览

**✅ 列出所有新增/修改的表**

| 表名 | 说明 | 操作 |
|------|------|------|
| pm_trader_group | 交易员分组表 | 新增 |
| pm_trader_group_member | 交易员分组关联表 | 新增 |

---

## 2. 表结构详细设计

### 2.1 pm_trader_group（交易员分组表）

**表说明**: 存储交易员分组的基础信息

**字段列表**:

| 字段名 | 类型 | 长度 | 允许NULL | 默认值 | 约束 | 索引 | 说明 |
|--------|------|------|----------|--------|------|------|------|
| id | BIGINT | - | ❌ | AUTO | PK | ✅ 主键 | 主键ID |
| user_id | BIGINT | - | ❌ | - | FK | ✅ 普通索引 | 所属用户ID，关联user.id |
| group_name | VARCHAR | 100 | ❌ | - | - | - | 分组名称 |
| description | TEXT | - | ✅ | NULL | - | - | 分组描述 |
| is_deleted | TINYINT | 1 | ❌ | 0 | - | - | 是否删除（0=否，1=是） |
| created_at | DATETIME | - | ❌ | NOW | - | - | 创建时间 |
| updated_at | DATETIME | - | ❌ | NOW_ON_UPDATE | - | - | 更新时间 |

**索引设计**:

| 索引名 | 字段 | 类型 | 说明 |
|--------|------|------|------|
| PRIMARY | id | PRIMARY | 主键索引 |
| idx_user_id | user_id | INDEX | 用户ID索引，加速查询用户的分组 |
| idx_user_deleted | user_id, is_deleted | COMPOSITE | 复合索引，加速查询未删除的分组 |

**约束说明**:
- `user_id` 外键关联 `user.id`，级联删除
- `group_name` 在同一用户下唯一

**Django Model 定义**:
```python
class PMTraderGroup(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        'user.User',
        on_delete=models.CASCADE,
        db_column='user_id',
        verbose_name='所属用户'
    )
    group_name = models.CharField(
        max_length=100,
        verbose_name='分组名称'
    )
    description = models.TextField(
        null=True,
        blank=True,
        verbose_name='分组描述'
    )
    is_deleted = modelsTinyIntField(
        default=0,
        verbose_name='是否删除'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )

    class Meta:
        db_table = 'pm_trader_group'
        indexes = [
            models.Index(fields=['user_id']),
            models.Index(fields=['user_id', 'is_deleted']),
        ]
        unique_together = [['user', 'group_name']]
```

---

### 2.2 pm_trader_group_member（交易员分组关联表）

**表说明**: 存储交易员和分组的多对多关系

**字段列表**:

| 字段名 | 类型 | 长度 | 允许NULL | 默认值 | 约束 | 索引 | 说明 |
|--------|------|------|----------|--------|------|------|------|
| id | BIGINT | - | ❌ | AUTO | PK | ✅ 主键 | 主键ID |
| group_id | BIGINT | - | ❌ | - | FK | ✅ 普通索引 | 分组ID，关联pm_trader_group.id |
| trader_id | BIGINT | - | ❌ | - | - | ✅ 普通索引 | 交易员ID（关联交易员表的ID字段） |
| joined_at | DATETIME | - | ❌ | NOW | - | - | 加入时间 |

**索引设计**:

| 索引名 | 字段 | 类型 | 说明 |
|--------|------|------|------|
| PRIMARY | id | PRIMARY | 主键索引 |
| idx_group_id | group_id | INDEX | 分组ID索引，加速查询分组下的交易员 |
| idx_trader_id | trader_id | INDEX | 交易员ID索引，加速查询交易员所属分组 |
| unique_group_trader | group_id, trader_id | UNIQUE | 唯一索引，防止重复添加 |

**约束说明**:
- `(group_id, trader_id)` 联合唯一，防止一个交易员重复加入同一分组
- `group_id` 外键关联 `pm_trader_group.id`，级联删除（删除分组时自动删除关联记录）
- `trader_id` 为逻辑外键，关联交易员表（不设置物理外键，提升性能）

**Django Model 定义**:
```python
class PMTraderGroupMember(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(
        PMTraderGroup,
        on_delete=models.CASCADE,
        db_column='group_id',
        verbose_name='所属分组'
    )
    trader_id = models.BigIntegerField(
        verbose_name='交易员ID'
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='加入时间'
    )

    class Meta:
        db_table = 'pm_trader_group_member'
        indexes = [
            models.Index(fields=['group_id']),
            models.Index(fields=['trader_id']),
        ]
        unique_together = [['group', 'trader_id']]
```

---

## 3. ER图（实体关系图）

```
┌─────────────────┐
│     user        │
│  (用户表)        │
└────────┬────────┘
         │ 1
         │
         │ N
┌────────▼────────┐
│pm_trader_group  │
│  (分组表)        │
├─────────────────┤
│ id (PK)         │◄──────┐
│ user_id (FK)    │       │ 1
│ group_name      │       │
│ description     │       │
│ is_deleted      │       │ N
│ created_at      │       │
│ updated_at      │       │
└────────┬────────┘       │
         │ 1              │
         │                │
         │ N              │
┌────────▼────────┐       │
│pm_trader_group_ │       │
│    member       │       │
│  (关联表)        │───────┘
├─────────────────┤
│ id (PK)         │
│ group_id (FK)   │
│ trader_id       │
│ joined_at       │
└─────────────────┘
```

**关系说明**:
- 一个用户可以有多个分组 (1:N)
- 一个分组可以包含多个交易员 (1:N，通过关联表实现)
- 一个交易员只能属于一个分组（业务层控制）

---

## 4. 数据迁移计划

**✅ 说明数据库升级步骤**

### 4.1 创建表

```sql
-- 创建分组表
CREATE TABLE `pm_trader_group` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` BIGINT NOT NULL COMMENT '所属用户ID',
  `group_name` VARCHAR(100) NOT NULL COMMENT '分组名称',
  `description` TEXT COMMENT '分组描述',
  `is_deleted` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否删除',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_user_deleted` (`user_id`, `is_deleted`),
  UNIQUE KEY `unique_user_group` (`user_id`, `group_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易员分组表';

-- 创建关联表
CREATE TABLE `pm_trader_group_member` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `group_id` BIGINT NOT NULL COMMENT '分组ID',
  `trader_id` BIGINT NOT NULL COMMENT '交易员ID',
  `joined_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '加入时间',
  PRIMARY KEY (`id`),
  INDEX `idx_group_id` (`group_id`),
  INDEX `idx_trader_id` (`trader_id`),
  UNIQUE KEY `unique_group_trader` (`group_id`, `trader_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易员分组关联表';
```

### 4.2 Django迁移命令

```bash
# 生成迁移文件
python manage.py makemigrations

# 查看迁移SQL（可选）
python manage.py sqlmigrate pm_robot 0001

# 执行迁移
python manage.py migrate

# 记录迁移状态
python manage.py showmigrations pm_robot
```

### 4.3 回滚方案

**如果迁移失败，如何回滚**:

```bash
# 回滚最后一次迁移
python manage.py migrate pm_robot zero

# 或回滚到指定版本
python manage.py migrate pm_robot 0001
```

**注意事项**:
- ⚠️ 生产环境迁移前，先备份数据库
- ⚠️ 在测试环境验证迁移脚本
- ⚠️ 迁移时关闭数据库写入（或使用只读副本）

---

## 5. 性能优化建议

**✅ 数据库性能相关建议**

| 优化项 | 建议 | 原因 |
|--------|------|------|
| 索引 | 已添加 `user_id` 和 `(user_id, is_deleted)` 复合索引 | 加速用户分组查询 |
| 分表 | 暂不需要 | 预估数据量 < 10万 |
| 分区 | 暂不需要 | 预估数据量 < 100万 |
| 缓存 | 使用Redis缓存分组列表 | 减少数据库查询 |
| 读写分离 | 暂不需要 | 当前读写压力不大 |

---

**文档版本**: v1.0
**最后更新**: YYYY-MM-DD
**状态**: 待确认 / 已确认
