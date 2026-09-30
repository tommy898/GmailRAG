import assert from "node:assert/strict";
import { test } from "node:test";

import { getGmailSyncAction, PENDING_LAUNCH_RETRY_DELAY_MS } from "../src/lib/api/sync-action.ts";

const pending = { sync_status: "not_synced", job: { job_id: "job-a", status: "pending" } };

test("pending launch is initially disabled, with a 60-second retry delay", () => {
  assert.equal(PENDING_LAUNCH_RETRY_DELAY_MS, 60_000);
  assert.deepEqual(getGmailSyncAction(pending, false, false, null), {
    disabled: true, busy: true, label: "Syncing...",
  });
});

test("same pending ID can retry without inventing a new job", () => {
  assert.deepEqual(getGmailSyncAction(pending, false, false, "job-a"), {
    disabled: false, busy: false, label: "Retry sync launch",
  });
});

test("a stale timer cannot enable a different pending job", () => {
  assert.equal(getGmailSyncAction(pending, false, false, "old-job").disabled, true);
});

test("running jobs never allow relaunch, even after a pending timer", () => {
  const running = { sync_status: "syncing", job: { job_id: "job-a", status: "running" } };
  assert.deepEqual(getGmailSyncAction(running, false, false, "job-a"), {
    disabled: true, busy: true, label: "Syncing...",
  });
});

test("requests in flight and status loading prevent duplicate clicks", () => {
  assert.equal(getGmailSyncAction(pending, true, false, "job-a").disabled, true);
  assert.deepEqual(getGmailSyncAction(pending, false, true, "job-a"), {
    disabled: true, busy: true, label: "Syncing...",
  });
});

test("failed and completed jobs permit a new sync", () => {
  for (const status of ["failed", "done"]) {
    const settled = { sync_status: status === "done" ? "ready" : "failed", job: { job_id: "job-a", status } };
    assert.deepEqual(getGmailSyncAction(settled, false, false, "job-a"), {
      disabled: false, busy: false, label: "Sync Gmail",
    });
  }
});
