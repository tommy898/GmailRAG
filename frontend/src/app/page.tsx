import { AskTestForm } from "@/components/ask-test-form";
import { SyncTestPanel } from "@/components/sync-test-panel";

import { ConnectGmailButton } from "@/components/auth/connect-gmail-button";
import { SignedOutScreen } from "@/components/auth/signed-out-screen";
import { createClient } from "@/lib/supabase/server";
import { SignOutButton } from "@/components/auth/sign-out-button";

type HomeProps = {
  searchParams: Promise<{
    gmail?: string | string[];
    gmail_error?: string | string[];
    error?: string | string[];
  }>;
};

const gmailErrorMessages: Record<string, string> = {
  access_denied: "Gmail access was not granted.",
  invalid_state: "The Gmail connection expired or was invalid. Try again.",
  account_mismatch: "Connect the same Google account used to sign in.",
  refresh_token_missing: "Google did not provide long-term access. Try again.",
  connection_failed: "Gmail could not be connected. Try again.",
};

const authErrorMessages: Record<string, string> = {
  missing_auth_code: "Google sign-in could not be completed. Try again.",
  auth_callback_failed: "Google sign-in could not be completed. Try again.",
};

function firstQueryValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Home({ searchParams }: HomeProps) {
  const supabase = await createClient();
  const query = await searchParams;
  const gmailStatus = firstQueryValue(query.gmail);
  const gmailError = firstQueryValue(query.gmail_error);
  const authError = firstQueryValue(query.error);
  const gmailErrorMessage = gmailError
    ? gmailErrorMessages[gmailError]
    : undefined;
  const authErrorMessage = authError
    ? authErrorMessages[authError]
    : undefined;

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return <SignedOutScreen authErrorMessage={authErrorMessage} />;
  }

  return (
    <main>
      <h1>GmailRAG</h1>
      {gmailStatus === "connected" ? (
        <p role="status">
          Gmail connected. Email syncing will be added next.
        </p>
      ) : null}

      {gmailErrorMessage ? (
        <p role="alert">{gmailErrorMessage}</p>
      ) : null}

      <p>Signed in as {user.email}</p>
      <SignOutButton />
      <ConnectGmailButton />
      <SyncTestPanel />
      <AskTestForm />
    </main>
  );
}
