"use client";

import { useState } from "react";

import {
  getApiErrorMessage,
  getGmailSyncStatus,
  startGmailSync,
} from "@/lib/api/client";
import type { GmailSyncStatusResponse } from "@/lib/api/types";

export function SyncTestPanel() {
  const [syncStatus, setSyncStatus] =
    useState<GmailSyncStatusResponse | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);

  async function loadStatus() {
    setSyncStatus(await getGmailSyncStatus());
  }

  async function startSync() {
    setIsLoading(true);
    setErrorMessage(null);
    setResultMessage(null);

    try {
      const body = await startGmailSync();
      setResultMessage(
        body.created
          ? `Sync job created: ${body.status}`
          : `Existing sync job reused: ${body.status}`,
      );
      await loadStatus();
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(error, "The sync could not be started."),
      );
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshStatus() {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      await loadStatus();
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(error, "Sync status could not be refreshed."),
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section aria-labelledby="sync-test-heading">
      <h2 id="sync-test-heading">Gmail sync test</h2>
      <button type="button" disabled={isLoading} onClick={startSync}>
        {isLoading ? "Working..." : "Start Gmail sync"}
      </button>
      <button type="button" disabled={isLoading} onClick={refreshStatus}>
        Refresh sync status
      </button>

      {resultMessage ? <p role="status">{resultMessage}</p> : null}
      {errorMessage ? <p role="alert">{errorMessage}</p> : null}

      {syncStatus ? (
        <dl>
          <dt>Gmail connected</dt>
          <dd>{syncStatus.connected ? "Yes" : "No"}</dd>
          <dt>Account status</dt>
          <dd>{syncStatus.sync_status ?? "Unavailable"}</dd>
          <dt>Latest job</dt>
          <dd>{syncStatus.job?.status ?? "None"}</dd>
          <dt>Last synchronized</dt>
          <dd>{syncStatus.last_synced_at ?? "Never"}</dd>
          {syncStatus.job?.error_message ? (
            <>
              <dt>Safe error</dt>
              <dd>{syncStatus.job.error_message}</dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </section>
  );
}
