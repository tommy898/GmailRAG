import type { GmailSyncStatusResponse } from "./types";

export const PENDING_LAUNCH_RETRY_DELAY_MS = 60_000;

export function getGmailSyncAction(
  status: GmailSyncStatusResponse | null,
  isLoading: boolean,
  isSubmitting: boolean,
  retryablePendingJobId: string | null,
) {
  const active =
    status?.sync_status === "syncing" ||
    status?.job?.status === "pending" ||
    status?.job?.status === "running";
  const retryable =
    status?.job?.status === "pending" &&
    status.job.job_id === retryablePendingJobId;

  return {
    disabled: isLoading || isSubmitting || (active && !retryable),
    busy: isSubmitting || (active && !retryable),
    label: isSubmitting
      ? "Syncing..."
      : retryable
        ? "Retry sync launch"
        : active
          ? "Syncing..."
          : "Sync Gmail",
  };
}
