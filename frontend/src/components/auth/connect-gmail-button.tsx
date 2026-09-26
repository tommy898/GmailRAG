"use client";

import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

type GmailConnectResponse = {
  authorization_url: string;
};

type ErrorResponse = {
  detail?: string;
};

export function ConnectGmailButton() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function connectGmail() {
    setErrorMessage(null);
    setIsLoading(true);

    try {
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

      const response = await fetch(`${apiUrl}/gmail/connect`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });

      const body = (await response.json()) as
        | GmailConnectResponse
        | ErrorResponse;

      if (!response.ok) {
        const message =
          "detail" in body && body.detail
            ? body.detail
            : "Could not start Gmail authorization";

        throw new Error(message);
      }

      window.location.assign(
        (body as GmailConnectResponse).authorization_url,
      );
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Could not start Gmail authorization",
      );
      setIsLoading(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        disabled={isLoading}
        onClick={connectGmail}
      >
        {isLoading ? "Connecting..." : "Connect Gmail"}
      </button>

      {errorMessage ? (
        <p role="alert">{errorMessage}</p>
      ) : null}
    </div>
  );
}
