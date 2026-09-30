"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

type SyncJobStatus = {
  job_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  created_at: string;
};

type SyncStatusResponse = {
  connected: boolean;
  sync_status: string | null;
  last_synced_at: string | null;
  job: SyncJobStatus | null;
};

type SyncStartResponse = {
  job_id: string;
  status: string;
  created: boolean;
};

type ErrorResponse = {
  detail?: string;
};

async function authenticatedRequest(
  path: string,
  init?: RequestInit,
) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not set");
  }

  const supabase = createClient();
  const {
    data: { session },
    error: sessionError,
  } = await supabase.auth.getSession();

  if (sessionError) {
    throw sessionError;
  }

  if (!session) {
    throw new Error("No Supabase session found");
  }

  return fetch(`${apiUrl}${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${session.access_token}`,
    },
  });
}

async function readResponse<T extends object>(
  response: Response,
): Promise<T> {
  const body = (await response.json()) as T | ErrorResponse;

  if (!response.ok) {
    const message =
      "detail" in body && body.detail
        ? body.detail
        : "Sync request failed";

    throw new Error(message);
  }

  return body as T;
}

export function SyncTestPanel() {
  const [syncStatus, setSyncStatus] =
    useState<SyncStatusResponse | null>(null);
  const [resultMessage, setResultMessage] = useState<string | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);

  async function loadStatus() {
    const response = await authenticatedRequest("/sync/status");
    const body = await readResponse<SyncStatusResponse>(response);
    setSyncStatus(body);
  }

  async function startSync() {
    setIsLoading(true);
    setErrorMessage(null);
    setResultMessage(null);

    try {
      const response = await authenticatedRequest("/gmail/sync", {
        method: "POST",
      });
      const body = await readResponse<SyncStartResponse>(response);
      setResultMessage(
        body.created
          ? `Sync job created: ${body.status}`
          : `Existing sync job reused: ${body.status}`,
      );
      await loadStatus();
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Sync request failed",
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
        error instanceof Error ? error.message : "Status request failed",
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
