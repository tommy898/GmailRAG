"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestInFlight = useRef(false);

  async function handleSignOut() {
    if (requestInFlight.current) {
      return;
    }

    requestInFlight.current = true;
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signOut();

      if (error) {
        setErrorMessage("Sign out could not be completed. Try again.");
        setIsLoading(false);
        requestInFlight.current = false;
        return;
      }

      router.refresh();
    } catch {
      setErrorMessage("Sign out could not be completed. Try again.");
      setIsLoading(false);
      requestInFlight.current = false;
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="w-full"
        disabled={isLoading}
        aria-busy={isLoading}
        onClick={handleSignOut}
      >
        {isLoading ? "Signing out..." : "Log out"}
      </Button>

      {errorMessage ? (
        <Alert>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
    </>
  );
}
