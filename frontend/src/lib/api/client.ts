import "client-only";

import { createClient } from "@/lib/supabase/client";

import type {
  AskRequest,
  AskResponse,
  EmailSource,
  GmailAccountSyncStatus,
  GmailConnectResponse,
  GmailSyncJob,
  GmailSyncJobStatus,
  GmailSyncResponse,
  GmailSyncStatusResponse,
} from "@/lib/api/types";

export type ApiErrorCode =
  | "configuration"
  | "authentication"
  | "authorization"
  | "invalid_request"
  | "not_found"
  | "gmail_not_connected"
  | "conflict"
  | "rate_limited"
  | "service_unavailable"
  | "network"
  | "invalid_response"
  | "request_failed";

const errorMessages: Record<ApiErrorCode, string> = {
  configuration: "The app is not configured correctly.",
  authentication: "Your session has expired. Sign in again.",
  authorization: "You do not have permission to do that.",
  invalid_request: "The request could not be completed.",
  not_found: "The requested service was not found.",
  gmail_not_connected: "Connect Gmail before starting a sync.",
  conflict: "This action is not available for the current account state.",
  rate_limited: "Too many requests. Try again shortly.",
  service_unavailable: "The service is temporarily unavailable. Try again.",
  network: "The service could not be reached. Check your connection and try again.",
  invalid_response: "The service returned an unexpected response. Try again.",
  request_failed: "The request failed. Try again.",
};

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number | null;

  constructor(code: ApiErrorCode, status: number | null = null) {
    super(errorMessages[code]);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

type ResponseDecoder<T> = (value: unknown) => T | null;

const safeSyncErrorMessages = new Set([
  "Gmail authorization is unavailable; reconnect Gmail",
  "Gmail messages could not be downloaded",
  "A Gmail message could not be normalized",
  "Gmail messages could not be indexed",
  "Gmail sync failed",
  "Gmail sync was interrupted; retry synchronization",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function isNullableNumber(value: unknown): value is number | null {
  return (typeof value === "number" && Number.isFinite(value)) || value === null;
}

function decodeEmailSource(value: unknown): EmailSource | null {
  if (
    !isRecord(value) ||
    typeof value.chunk_id !== "string" ||
    !isNullableString(value.subject) ||
    !isNullableString(value.from_email) ||
    !isNullableString(value.date) ||
    !isNullableNumber(value.score) ||
    typeof value.preview !== "string"
  ) {
    return null;
  }

  return {
    chunk_id: value.chunk_id,
    subject: value.subject,
    from_email: value.from_email,
    date: value.date,
    score: value.score,
    preview: value.preview,
  };
}

function decodeAskResponse(value: unknown): AskResponse | null {
  if (
    !isRecord(value) ||
    typeof value.answer !== "string" ||
    !Array.isArray(value.sources)
  ) {
    return null;
  }

  const sources: EmailSource[] = [];

  for (const sourceValue of value.sources) {
    const source = decodeEmailSource(sourceValue);

    if (!source) {
      return null;
    }

    sources.push(source);
  }

  return {
    answer: value.answer,
    sources,
  };
}

function decodeGmailConnectResponse(
  value: unknown,
): GmailConnectResponse | null {
  if (!isRecord(value) || typeof value.authorization_url !== "string") {
    return null;
  }

  try {
    const authorizationUrl = new URL(value.authorization_url);

    if (
      authorizationUrl.protocol !== "https:" ||
      authorizationUrl.hostname !== "accounts.google.com"
    ) {
      return null;
    }

    return { authorization_url: authorizationUrl.toString() };
  } catch {
    return null;
  }
}

function isGmailSyncJobStatus(value: unknown): value is GmailSyncJobStatus {
  return (
    value === "pending" ||
    value === "running" ||
    value === "done" ||
    value === "failed"
  );
}

function isGmailAccountSyncStatus(
  value: unknown,
): value is GmailAccountSyncStatus {
  return (
    value === "not_synced" ||
    value === "syncing" ||
    value === "ready" ||
    value === "failed"
  );
}

function decodeGmailSyncResponse(value: unknown): GmailSyncResponse | null {
  if (
    !isRecord(value) ||
    typeof value.job_id !== "string" ||
    (value.status !== "pending" && value.status !== "running") ||
    typeof value.created !== "boolean"
  ) {
    return null;
  }

  return {
    job_id: value.job_id,
    status: value.status,
    created: value.created,
  };
}

function decodeGmailSyncJob(value: unknown): GmailSyncJob | null {
  if (
    !isRecord(value) ||
    typeof value.job_id !== "string" ||
    !isGmailSyncJobStatus(value.status) ||
    !isNullableString(value.started_at) ||
    !isNullableString(value.finished_at) ||
    !isNullableString(value.error_message) ||
    typeof value.created_at !== "string"
  ) {
    return null;
  }

  const errorMessage =
    value.error_message === null ||
    safeSyncErrorMessages.has(value.error_message)
      ? value.error_message
      : "Gmail sync failed";

  return {
    job_id: value.job_id,
    status: value.status,
    started_at: value.started_at,
    finished_at: value.finished_at,
    error_message: errorMessage,
    created_at: value.created_at,
  };
}

function decodeGmailSyncStatusResponse(
  value: unknown,
): GmailSyncStatusResponse | null {
  if (
    !isRecord(value) ||
    typeof value.connected !== "boolean" ||
    (value.sync_status !== null &&
      !isGmailAccountSyncStatus(value.sync_status)) ||
    !isNullableString(value.last_synced_at)
  ) {
    return null;
  }

  const job = value.job === null ? null : decodeGmailSyncJob(value.job);

  if (value.job !== null && !job) {
    return null;
  }

  return {
    connected: value.connected,
    sync_status: value.sync_status,
    last_synced_at: value.last_synced_at,
    job,
  };
}

function getApiBaseUrl() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");

  if (!apiUrl) {
    throw new ApiError("configuration");
  }

  return apiUrl;
}

async function getAccessToken() {
  let supabase;

  try {
    supabase = createClient();
  } catch {
    throw new ApiError("configuration");
  }

  try {
    const {
      data: { session },
      error,
    } = await supabase.auth.getSession();

    if (error || !session?.access_token) {
      throw new ApiError("authentication");
    }

    return session.access_token;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    throw new ApiError("authentication");
  }
}

function getHttpError(status: number, path: string) {
  if (status === 400 || status === 422) {
    return new ApiError("invalid_request", status);
  }

  if (status === 401) {
    return new ApiError("authentication", status);
  }

  if (status === 403) {
    return new ApiError("authorization", status);
  }

  if (status === 404) {
    return new ApiError("not_found", status);
  }

  if (status === 409) {
    if (path === "/gmail/sync") {
      return new ApiError("gmail_not_connected", status);
    }

    return new ApiError("conflict", status);
  }

  if (status === 429) {
    return new ApiError("rate_limited", status);
  }

  if (status >= 500) {
    return new ApiError("service_unavailable", status);
  }

  return new ApiError("request_failed", status);
}

async function authenticatedApiRequest<T>(
  path: string,
  decoder: ResponseDecoder<T>,
  init?: RequestInit,
): Promise<T> {
  const apiUrl = getApiBaseUrl();
  const accessToken = await getAccessToken();
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;

  try {
    response = await fetch(`${apiUrl}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("network");
  }

  if (!response.ok) {
    throw getHttpError(response.status, path);
  }

  let body: unknown;

  try {
    body = await response.json();
  } catch {
    throw new ApiError("invalid_response", response.status);
  }

  const decodedBody = decoder(body);

  if (!decodedBody) {
    throw new ApiError("invalid_response", response.status);
  }

  return decodedBody;
}

export function getApiErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export function askQuestion(question: string) {
  const request: AskRequest = { question };

  return authenticatedApiRequest("/ask", decodeAskResponse, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });
}

export function beginGmailConnection() {
  return authenticatedApiRequest(
    "/gmail/connect",
    decodeGmailConnectResponse,
  );
}

export function startGmailSync() {
  return authenticatedApiRequest("/gmail/sync", decodeGmailSyncResponse, {
    method: "POST",
  });
}

export function getGmailSyncStatus() {
  return authenticatedApiRequest(
    "/sync/status",
    decodeGmailSyncStatusResponse,
  );
}
