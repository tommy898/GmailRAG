"use client";

import { useCallback, useEffect, useState } from "react";

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

function getAccountState(status: GmailSyncStatusResponse) {
  if (!status.connected) {
    return "Connect Gmail to start using your inbox.";
  }

  if (status.job?.status === "pending" || status.job?.status === "running") {
    return "Synchronization is in progress.";
  }

  switch (status.sync_status) {
    case "not_synced":
      return "Gmail is connected and ready for its first sync.";
    case "syncing":
      return "Synchronization is in progress.";
    case "ready":
      return "Your inbox is ready for questions.";
    case "failed":
      return status.job?.error_message ?? "Gmail sync failed";
    default:
      return "Gmail status is unavailable.";
  }
}

export function GmailSidebarPanel() {
  const [status, setStatus] = useState<GmailSyncStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(null);

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

  async function handleConnect() {
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
    }
  }

  async function handleSync() {
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
    }
  }

  const isSyncActive =
    status?.sync_status === "syncing" ||
    status?.job?.status === "pending" ||
    status?.job?.status === "running";

  return (
    <section aria-labelledby="gmail-status-heading" className="space-y-6 px-4 py-6">
      <div className="space-y-2">
        <h2 id="gmail-status-heading" className="text-sm font-medium">
          Gmail status
        </h2>
        {isLoading ? (
          <Skeleton aria-label="Checking Gmail status" className="h-5 w-36" />
        ) : status ? (
          <p
            className={`text-sm font-medium ${
              status.connected ? "text-success" : "text-error"
            }`}
          >
            {status.connected ? "Gmail connected" : "Gmail not connected"}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">Status unavailable</p>
        )}
        {status ? (
          <p className="text-sm text-muted-foreground">
            {getAccountState(status)}
          </p>
        ) : null}
      </div>

      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">Last synchronized</p>
        <p className="text-sm">
          {status ? formatLastSync(status.last_synced_at) : "Unavailable"}
        </p>
      </div>

      <div className="space-y-2">
        {status?.connected ? (
          <Button
            type="button"
            className="w-full"
            disabled={isSubmitting || isSyncActive}
            onClick={handleSync}
          >
            {isSubmitting || isSyncActive ? "Syncing..." : "Sync Gmail"}
          </Button>
        ) : status ? (
          <Button
            type="button"
            className="w-full"
            disabled={isSubmitting}
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

      {errorMessage ? (
        <Alert>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}
