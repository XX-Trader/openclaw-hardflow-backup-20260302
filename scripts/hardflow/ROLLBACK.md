# HardFlow Rollback Strategy (T6)

## Trigger

Rollback is triggered when:

1. `hardflow-run.sh post-test` fails, and
2. `AUTO_ROLLBACK_ON_POST_TEST_FAIL=1` (default), and
3. `ROLLBACK_CMD` is configured.

Or:

1. `hardflow-run.sh test-loop` exhausts retries, and
2. `AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL=1`, and
3. classify stage has saved a git savepoint commit.

## Behavior

1. `post_tester` gate is written as `passed:false`.
2. `rollback` stage runs automatically using `ROLLBACK_CMD`.
3. `rollback` gate is written:
   - `passed:true` when rollback succeeds
   - `passed:false` when rollback fails or is disabled
4. failure details are written to `issues.ndjson` and `post-test.log` / `rollback.log`.
5. if `ROLLBACK_CMD` is empty, hardflow can fallback to `git reset --hard <savepoint>`.

## Manual rollback

```bash
bash scripts/hardflow/hardflow-run.sh rollback --reason "manual-emergency"
```

## Recommended env

```bash
export AUTO_ROLLBACK_ON_POST_TEST_FAIL=1
export ROLLBACK_CMD="bash ./rollback.sh"
export AUTO_GIT_ROLLBACK_ON_TEST_LOOP_FAIL=1
# Optional (dangerous): allow reset even when classify stage detected baseline dirty files
# export HARDFLOW_ROLLBACK_FORCE_DIRTY=1
```
