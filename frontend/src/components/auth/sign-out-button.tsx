"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSignOut() {
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signOut();

      if (error) {
        setErrorMessage("Sign out could not be completed. Try again.");
        return;
      }

      router.refresh();
    } catch {
      setErrorMessage("Sign out could not be completed. Try again.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="w-full"
        disabled={isLoading}
        onClick={handleSignOut}
      >
        {isLoading ? "Signing out..." : "Log out"}
      </Button>

      {errorMessage ? <p role="alert">{errorMessage}</p> : null}
    </>
  );
}
