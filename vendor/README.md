# Vendor 目录说明

本目录用于存放第三方上游源码，不放业务自定义逻辑。

- 推荐路径：`vendor/openclaw-official/`
- 推荐方式：`git submodule`
- 版本策略：固定稳定 `tag/release`，不要直接跟 `main`

初始化与升级请使用：

```bash
python scripts/openclaw-ops/openclaw_upstream_binding.py --help
```
