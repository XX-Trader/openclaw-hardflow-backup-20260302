# HardFlow Rollback Strategy (T6)

## Trigger

Rollback is triggered when:

1. `hardflow-run.sh post-test` fails, and
2. `AUTO_ROLLBACK_ON_POST_TEST_FAIL=1` (default), and
3. `ROLLBACK_CMD` is configured.

## Behavior

1. `post_tester` gate is written as `passed:false`.
2. `rollback` stage runs automatically using `ROLLBACK_CMD`.
3. `rollback` gate is written:
   - `passed:true` when rollback succeeds
   - `passed:false` when rollback fails or is disabled
4. failure details are written to `issues.ndjson` and `post-test.log` / `rollback.log`.

## Manual rollback

```bash
bash scripts/hardflow/hardflow-run.sh rollback --reason "manual-emergency"
```

## Recommended env

```bash
export AUTO_ROLLBACK_ON_POST_TEST_FAIL=1
export ROLLBACK_CMD="bash ./rollback.sh"
```
