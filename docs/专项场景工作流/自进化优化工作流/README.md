# 通用持续改进工作流

持续改进只基于可复现失败、代码审查、测试结果和运行指标，不按行业或历史项目写专用分支。

## 当前 owner

- 仓库巡检：`scripts/openclaw-ops/repo_hygiene_reviewer.py`
- 外部模式采集与复核：`skills/library/web-intelligence/scripts/web_intel_collect_runner.py`、`web_intel_review_runner.py`
- 优化建议与审查：`skills/library/control-plane-ops/scripts/control_plane_optimization_advisor.py`、`control_plane_optimization_review_runner.py`
- 实施闭环：`skills/library/project-delivery-pipeline/scripts/pipeline_runner.py`

任何自动建议都要经过适用性判断、定向测试、独立审查和回滚验证。
