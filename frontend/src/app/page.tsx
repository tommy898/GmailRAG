import { AskTestForm } from "@/components/ask-test-form";

import { ConnectGmailButton } from "@/components/auth/connect-gmail-button";
import { SignInButton } from "@/components/auth/sign-in-button";
import { createClient } from "@/lib/supabase/server";
import { SignOutButton } from "@/components/auth/sign-out-button";

type HomeProps = {
  searchParams: Promise<{
    gmail?: string | string[];
    gmail_error?: string | string[];
  }>;
};

const gmailErrorMessages: Record<string, string> = {
  access_denied: "Gmail access was not granted.",
  invalid_state: "The Gmail connection expired or was invalid. Try again.",
  account_mismatch: "Connect the same Google account used to sign in.",
  refresh_token_missing: "Google did not provide long-term access. Try again.",
  connection_failed: "Gmail could not be connected. Try again.",
};

function firstQueryValue(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Home({ searchParams }: HomeProps) {
  const supabase = await createClient();
  const query = await searchParams;
  const gmailStatus = firstQueryValue(query.gmail);
  const gmailError = firstQueryValue(query.gmail_error);
  const gmailErrorMessage = gmailError
    ? gmailErrorMessages[gmailError]
    : undefined;

  const {
    data: { user },
  } = await supabase.auth.getUser();

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

      {user ? (
      <>
        <p>Signed in as {user.email}</p>
        <SignOutButton />
        <ConnectGmailButton />
        <AskTestForm />
       </>
      ) : (
        <>
          <p>Sign in to continue.</p>
          <SignInButton />
        </>
      )}
    </main>
  );
}
