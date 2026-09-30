"use client";

import { useState } from "react";

import {
  beginGmailConnection,
  getApiErrorMessage,
} from "@/lib/api/client";

export function ConnectGmailButton() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function connectGmail() {
    setErrorMessage(null);
    setIsLoading(true);

    try {
      const body = await beginGmailConnection();

      window.location.assign(body.authorization_url);
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(
          error,
          "Gmail authorization could not be started.",
        ),
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
