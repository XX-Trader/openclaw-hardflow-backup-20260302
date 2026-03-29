# G4 Security — 评分标准

> 适用 Gate：`security` | 维度数：6 | 阈值：overall ≥ 95 | ⚠️ 支持 Veto

## authn_authz (认证授权)
满分（95-100）：所有敏感接口有认证、权限粒度到操作级别。
扣分：存在未认证接口 -15 (veto)、权限粒度不够 -5

## input_validation (输入校验)
满分（95-100）：所有外部输入（表单/URL参数/请求体）有类型校验和范围限制。
扣分：存在未校验输入 -10、SQL 拼接 -20 (veto)、XSS 风险 -15 (veto)

## secrets_protection (密钥保护)
满分（95-100）：无硬编码密钥、所有密钥通过环境变量或密钥管理器。
扣分：代码中硬编码密钥/Token -20 (veto)、密钥出现在日志中 -15 (veto)

## dependency_security (依赖安全)
> 此维度与确定性检查（安全扫描）加权合并：50% 确定性 + 50% reviewer

满分（95-100）：无已知高危漏洞依赖、依赖版本有明确锁定。
扣分：每个高危漏洞 -5、每个 critical 漏洞 -10 (veto)

## auditability (可审计性)
满分（95-100）：敏感操作有审计日志、日志包含操作者/时间/内容。
扣分：敏感操作无日志 -8、日志缺少操作者信息 -5

## privileged_access_control (特权访问控制)
满分（95-100）：管理员权限最小化、特权操作有二次确认。
扣分：管理员权限过大 -8、特权操作无确认 -5

## Veto 规则

以下问题直接触发一票否决（Gate 失败，不计分数）：
- severity 为 `critical` 且 status 为 `open` 的 finding
- severity 为 `high` 且 status 为 `open` 的 finding
- 代码中硬编码密钥/Token
- SQL 拼接
- XSS 漏洞
