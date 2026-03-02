# HardFlow Issue Schema (T5)

Each line in `.workflow/runs/<run_id>/issues.ndjson` is a JSON object with fields:

1. `schema_version`: currently `1`
2. `issue_id`: unique id (`<run_id>-<stage>-<attempt>-<timestamp>`)
3. `run_id`: workflow run id
4. `ts`: UTC timestamp
5. `stage`: `test-loop` / `post-test` / `score-<gate>`
6. `attempt`: numeric attempt index
7. `status`: `failed` (can be extended)
8. `command`: command that failed
9. `failure_reason`: short reason
10. `reproduce_steps`: reproducible command hint
11. `fix_command`: command used for auto-fix
12. `fix_commit_before`: git commit hash before fix
13. `fix_commit_after`: git commit hash after fix
14. `regression_result`: `retry-pending` | `retry-exhausted` | `manual-check-required`
15. `test_log`: path to stage test log
16. `fix_log`: path to fix or rollback log

Example record:

```json
{"schema_version":"1","issue_id":"20260228_123000-test-loop-1-1700000000","run_id":"20260228_123000","ts":"2026-02-28T12:30:00Z","stage":"test-loop","attempt":1,"status":"failed","command":"pytest -q","failure_reason":"test command failed","reproduce_steps":"run hardflow-run.sh test-loop --max-retries 3","fix_command":"codex fix ...","fix_commit_before":"abc123","fix_commit_after":"def456","regression_result":"retry-pending","test_log":".workflow/runs/20260228_123000/attempt-1/test.log","fix_log":".workflow/runs/20260228_123000/attempt-1/fix.log"}
```
