"use client";

import Image from "next/image";
import { useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { createClient } from "@/lib/supabase/client";

type SignInButtonProps = {
  initialErrorMessage?: string;
};

const signInFailureMessage =
  "Google sign-in could not be started. Try again.";

export function SignInButton({
  initialErrorMessage,
}: SignInButtonProps) {
  const [errorMessage, setErrorMessage] = useState<string | null>(
    initialErrorMessage ?? null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const requestInFlight = useRef(false);

  async function handleSignIn() {
    if (requestInFlight.current) {
      return;
    }

    requestInFlight.current = true;
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });

      if (error) {
        setErrorMessage(signInFailureMessage);
        setIsLoading(false);
        requestInFlight.current = false;
      }
    } catch {
      setErrorMessage(signInFailureMessage);
      setIsLoading(false);
      requestInFlight.current = false;
    }
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <button
        type="button"
        className="rounded-full outline-none transition-opacity focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isLoading}
        aria-busy={isLoading}
        onClick={handleSignIn}
      >
        <span className="sr-only">
          {isLoading ? "Signing in with Google" : "Sign in with Google"}
        </span>
        <Image
          aria-hidden="true"
          src="/sign-in-with-google-neutral.png"
          alt=""
          width={180}
          height={40}
          priority
          draggable={false}
        />
      </button>

      {errorMessage ? (
        <Alert>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      {isLoading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Redirecting to Google...
        </p>
      ) : null}
    </div>
  );
}
