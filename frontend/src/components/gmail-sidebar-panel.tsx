"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  beginGmailConnection,
  getApiErrorMessage,
  getGmailSyncStatus,
  startGmailSync,
} from "@/lib/api/client";
import type { GmailSyncStatusResponse } from "@/lib/api/types";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const SYNC_POLL_INTERVAL_MS = 3000;

function hasActiveJob(status: GmailSyncStatusResponse | null) {
  return status?.job?.status === "pending" || status?.job?.status === "running";
}

function formatLastSync(value: string | null) {
  if (!value) {
    return "Never";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unavailable";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function GmailSidebarPanel() {
  const [status, setStatus] = useState<GmailSyncStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);
  const actionInFlight = useRef(false);

  const refreshStatus = useCallback(async () => {
    setErrorMessage(null);
    setIsLoading(true);

    try {
      setStatus(await getGmailSyncStatus());
    } catch (error) {
      setStatus(null);
      setErrorMessage(
        getApiErrorMessage(error, "Gmail status could not be loaded."),
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;

    getGmailSyncStatus()
      .then((nextStatus) => {
        if (active) {
          setStatus(nextStatus);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(
            getApiErrorMessage(error, "Gmail status could not be loaded."),
          );
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const activeJobId = hasActiveJob(status) ? status?.job?.job_id : null;
  const activeJobStatus = hasActiveJob(status) ? status?.job?.status : null;

  useEffect(() => {
    if (!activeJobId) {
      return;
    }

    let cancelled = false;
    let timeoutId: number;

    async function pollStatus() {
      try {
        const nextStatus = await getGmailSyncStatus();

        if (cancelled) {
          return;
        }

        setStatus(nextStatus);
        setErrorMessage(null);

        if (hasActiveJob(nextStatus)) {
          timeoutId = window.setTimeout(pollStatus, SYNC_POLL_INTERVAL_MS);
        } else if (nextStatus.job?.status === "done") {
          setResultMessage("Gmail sync completed.");
        } else if (nextStatus.job?.status === "failed") {
          setResultMessage(null);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }

        setStatus(null);
        setResultMessage(null);
        setErrorMessage(
          getApiErrorMessage(error, "Gmail status could not be loaded."),
        );
      }
    }

    timeoutId = window.setTimeout(pollStatus, SYNC_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [activeJobId, activeJobStatus]);

  async function handleConnect() {
    if (actionInFlight.current) {
      return;
    }

    actionInFlight.current = true;
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      const response = await beginGmailConnection();
      window.location.assign(response.authorization_url);
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(error, "Gmail connection could not be started."),
      );
      setIsSubmitting(false);
      actionInFlight.current = false;
    }
  }

  async function handleSync() {
    if (actionInFlight.current) {
      return;
    }

    actionInFlight.current = true;
    setErrorMessage(null);
    setResultMessage(null);
    setIsSubmitting(true);

    try {
      const response = await startGmailSync();
      setResultMessage(
        response.created
          ? "Gmail sync was queued."
          : "An existing Gmail sync is in progress.",
      );
      await refreshStatus();
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(error, "Gmail sync could not be started."),
      );
    } finally {
      setIsSubmitting(false);
      actionInFlight.current = false;
    }
  }

  const isSyncActive = status?.sync_status === "syncing" || hasActiveJob(status);

  return (
    <section aria-labelledby="gmail-status-heading" className="space-y-8 px-4 py-8 [&_h2]:leading-6 [&_p]:leading-6">
      <div className="space-y-3">
        <h2 id="gmail-status-heading" className="text-sm font-medium">
          Gmail status
        </h2>
        {isLoading ? (
          <div role="status">
            <Skeleton aria-hidden="true" className="h-5 w-36" />
            <span className="sr-only">Checking Gmail status</span>
          </div>
        ) : status ? (
          <p
            role="status"
            className={`text-sm font-medium ${
              status.connected ? "text-success" : "text-error"
            }`}
          >
            {status.connected ? "Gmail connected" : "Gmail not connected"}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">Status unavailable</p>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">Last synchronized</p>
        <p className="text-sm">
          {status ? formatLastSync(status.last_synced_at) : "Unavailable"}
        </p>
      </div>

      <div className="space-y-3">
        {status?.connected ? (
          <Button
            type="button"
            className="w-full"
            disabled={isLoading || isSubmitting || isSyncActive}
            aria-busy={isSubmitting || isSyncActive}
            onClick={handleSync}
          >
            {isSubmitting || isSyncActive ? "Syncing..." : "Sync Gmail"}
          </Button>
        ) : status ? (
          <Button
            type="button"
            className="w-full"
            disabled={isLoading || isSubmitting}
            aria-busy={isSubmitting}
            onClick={handleConnect}
          >
            {isSubmitting ? "Connecting..." : "Connect Gmail"}
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            className="w-full"
            disabled={isLoading}
            onClick={() => void refreshStatus()}
          >
            Retry status
          </Button>
        )}

        {status?.connected ? (
          <Button
            type="button"
            variant="ghost"
            className="w-full"
            disabled={isLoading || isSubmitting}
            onClick={() => void refreshStatus()}
          >
            Refresh status
          </Button>
        ) : null}
      </div>

      {resultMessage ? (
        <p role="status" className="text-sm text-muted-foreground">
          {resultMessage}
        </p>
      ) : null}

      {status?.sync_status === "failed" && status.job?.status === "failed" ? (
        <Alert role="alert">
          <AlertDescription>
            {status.job?.error_message ?? "Gmail sync failed."}
          </AlertDescription>
        </Alert>
      ) : null}

      {errorMessage ? (
        <Alert>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}
