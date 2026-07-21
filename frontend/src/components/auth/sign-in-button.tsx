"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export function SignInButton() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSignIn() {
    setErrorMessage(null);

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });

    if (error) {
      setErrorMessage(error.message);
    }
  }

  return (
    <>
      <button type="button" onClick={handleSignIn}>
        Continue with Google
      </button>

      {errorMessage ? <p role="alert">{errorMessage}</p> : null}
    </>
  );
}