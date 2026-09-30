export type GmailAccountSyncStatus =
  | "not_synced"
  | "syncing"
  | "ready"
  | "failed";

export type GmailSyncJobStatus =
  | "pending"
  | "running"
  | "done"
  | "failed";

export type EmailSource = {
  chunk_id: string;
  subject: string | null;
  from_email: string | null;
  date: string | null;
  score: number | null;
  preview: string;
};

export type AskRequest = {
  question: string;
};

export type AskResponse = {
  answer: string;
  sources: EmailSource[];
};

export type GmailConnectResponse = {
  authorization_url: string;
};

export type GmailSyncResponse = {
  job_id: string;
  status: "pending" | "running";
  created: boolean;
};

export type GmailSyncJob = {
  job_id: string;
  status: GmailSyncJobStatus;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  created_at: string;
};

export type GmailSyncStatusResponse = {
  connected: boolean;
  sync_status: GmailAccountSyncStatus | null;
  last_synced_at: string | null;
  job: GmailSyncJob | null;
};
