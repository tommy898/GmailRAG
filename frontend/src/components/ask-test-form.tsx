"use client";

import { FormEvent, useState } from "react";

import { createClient } from "@/lib/supabase/client";

type AskResponse = {
  answer: string;
  sources: unknown[];
};

type ErrorResponse = {
  detail?: string;
};

export function AskTestForm() {
  const [question, setQuestion] = useState(
    "When is my UW orientation?",
  );
  const [result, setResult] = useState<AskResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    setResult(null);
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

      const response = await fetch(`${apiUrl}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ question }),
      });

      const body = (await response.json()) as
        | AskResponse
        | ErrorResponse;

      if (!response.ok) {
        const message =
          "detail" in body && body.detail
            ? body.detail
            : "Request failed";

        throw new Error(message);
      }

      setResult(body as AskResponse);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Request failed",
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <label htmlFor="question">Test question</label>
      <input
        id="question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
      />

      <button type="submit" disabled={isLoading}>
        {isLoading ? "Asking..." : "Test /ask"}
      </button>

      {errorMessage ? (
        <p role="alert">{errorMessage}</p>
      ) : null}

      {result ? (
        <pre>{JSON.stringify(result, null, 2)}</pre>
      ) : null}
    </form>
  );
}