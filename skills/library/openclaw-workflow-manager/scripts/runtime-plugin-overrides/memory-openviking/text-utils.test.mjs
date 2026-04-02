import test from "node:test";
import assert from "node:assert/strict";

import {
  isTranscriptLikeIngest,
  sanitizeUserTextForCapture,
} from "./text-utils.ts";

test("does not treat cron automation prompts as transcript-like ingest", () => {
  const text = `
[cron:c2c75adf-5e80-4b50-bf18-40ceadfa6bd6 task_executor_10m] You are ops-agent scheduled runner. Run command only:
python3 "/home/ubuntu/.openclaw/ops/policy/task_executor_runner.py" --task cron:task-executor --db "/home/ubuntu/.openclaw/ops/task-center/task_center.db"
Your first assistant turn MUST contain exactly one exec tool call for that command and no text.
Current time: Thursday, March 12th, 2026 - 7:38 PM (Asia/Shanghai) / 2026-03-12 11:38 UTC
Return your summary as plain text; it will be delivered automatically.
`.trim();

  const result = isTranscriptLikeIngest(text, {
    minSpeakerTurns: 2,
    minChars: 200,
  });

  assert.equal(result.shouldAssist, false);
  assert.equal(result.reason, "automation_prompt");
});

test("sanitize strips prior ingest assist wrapper before downstream checks", () => {
  const text = `
<ingest-reply-assist>
Reply with 1-2 concise sentences to acknowledge key points.
</ingest-reply-assist>

Alice: we restarted the gateway.
Bob: task executor should use exec first.
`.trim();

  assert.equal(
    sanitizeUserTextForCapture(text),
    "Alice: we restarted the gateway. Bob: task executor should use exec first.",
  );
});

test("still recognizes real multi-speaker transcripts", () => {
  const text = `
Alice: We deployed the patch and restarted the gateway.
Bob: Good. Watch the next task_executor_10m run and confirm it uses exec first.
Alice: I will verify the transcript after the cron trigger.
`.trim();

  const result = isTranscriptLikeIngest(text, {
    minSpeakerTurns: 2,
    minChars: 80,
  });

  assert.equal(result.shouldAssist, true);
  assert.equal(result.reason, "transcript_like_ingest");
  assert.equal(result.speakerTurns, 3);
});
