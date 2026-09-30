"use client";

import { FormEvent, useState } from "react";

import {
  askQuestion,
  getApiErrorMessage,
} from "@/lib/api/client";
import type { AskResponse } from "@/lib/api/types";

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
      setResult(await askQuestion(question));
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(error, "The question could not be answered."),
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
