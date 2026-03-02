# OpenClaw Cron -> Agent Mapping

- fd8ae471-69f7-4bb5-9d2e-46aa26b092f1 | log-watcher agent（双项目） | agent=ops-agent | exists=True | schedule=900000
- 57acbf75-0b04-461d-a888-ca02c70fc5d1 | agent-factory 自动创建(P1/P2) | agent=agent-factory | exists=True | schedule=1800000
- 8752680b-17d4-4a95-8f04-1360fc346fa9 | ops 汇总（cron+todo+done） | agent=ops-agent | exists=True | schedule=1800000
- 948d7307-6941-44ee-a8aa-57da767a31b7 | optimize-agent 治理巡检 | agent=optimize-agent | exists=True | schedule=11 2,8,14,20 * * *
- 22b1712a-ff4a-4502-bce6-4e39c44cbe9f | optimize 自我进化总结 | agent=optimize-agent | exists=True | schedule=37 4 * * *
- 7e12c6d4-adb0-4ad4-83a6-58bffec8eb53 | optimize 全量校准 | agent=optimize-agent | exists=True | schedule=23 3 */14 * *
- 8f9102f4-d62c-4a01-85ef-1d393e2244de | optimize 频率策略管理 | agent=optimize-agent | exists=True | schedule=11 4 * * *
- 16cb8d03-beb9-4697-927d-35952353bf8e | TODO 巡检（15分钟） | agent=ops-agent | exists=True | schedule=900000
- 2ce5fe63-8316-4503-95e4-48515042b453 | daily_todo_digest_daily | agent=ops-agent | exists=True | schedule=0 0 * * *
- e943eaf3-9049-4429-b71d-12b2dbe29178 | experience_maintain_daily | agent=optimize-agent | exists=True | schedule=15 1 * * *
- a5057f0a-3734-44c7-8844-f82d72aacd12 | experience_maintain_weekly | agent=optimize-agent | exists=True | schedule=30 1 * * 1
- 270256a7-d119-41d0-b923-42f8dd4faf73 | experience_maintain_monthly | agent=optimize-agent | exists=True | schedule=45 1 1 * *
- 5797cd5b-5539-4e95-8d58-dc65a4633ec5 | project_index_maintainer_30m | agent=project-agent | exists=True | schedule=*/30 * * * *
