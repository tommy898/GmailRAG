"use client";

import { useRef, useState } from "react";

import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputFooter,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { EmailSources } from "@/components/email-sources";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { askQuestion, getApiErrorMessage } from "@/lib/api/client";
import type { AskResponse } from "@/lib/api/types";

export function LatestAnswerWorkspace() {
  const [draft, setDraft] = useState("");
  const [latestQuestion, setLatestQuestion] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const requestInFlight = useRef(false);

  async function handleSubmit(message: PromptInputMessage) {
    const question = message.text.trim();

    if (!question || requestInFlight.current) {
      return;
    }

    requestInFlight.current = true;
    setIsAsking(true);
    setDraft("");
    setLatestQuestion(question);
    setResult(null);
    setErrorMessage(null);

    try {
      setResult(await askQuestion(question));
    } catch (error) {
      setErrorMessage(
        getApiErrorMessage(error, "The question could not be answered."),
      );
      setDraft(question);
    } finally {
      requestInFlight.current = false;
      setIsAsking(false);
    }
  }

  return (
    <section
      aria-label="Question and answer workspace"
      className="flex min-h-0 flex-1 flex-col gap-6"
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        {latestQuestion ? (
          <div className="mx-auto w-full max-w-3xl space-y-6 py-6">
            <Message from="user">
              <MessageContent className="group-[.is-user]:bg-primary group-[.is-user]:text-primary-foreground">
                <p className="whitespace-pre-wrap break-words leading-6">
                  {latestQuestion}
                </p>
              </MessageContent>
            </Message>

            {isAsking ? (
              <Message from="assistant" role="status">
                <MessageContent className="group-[.is-assistant]:rounded-lg group-[.is-assistant]:bg-secondary group-[.is-assistant]:px-4 group-[.is-assistant]:py-3">
                  <span className="flex items-center gap-2 text-muted-foreground">
                    <Spinner /> Finding an answer...
                  </span>
                </MessageContent>
              </Message>
            ) : null}

            {result ? (
              <Message from="assistant" aria-label="Answer">
                <MessageContent className="group-[.is-assistant]:rounded-lg group-[.is-assistant]:bg-secondary group-[.is-assistant]:px-4 group-[.is-assistant]:py-3">
                  <MessageResponse
                    className="break-words leading-6"
                    controls={false}
                    disallowedElements={["a", "img"]}
                    mode="static"
                    plugins={{}}
                    unwrapDisallowed
                  >
                    {result.answer}
                  </MessageResponse>
                </MessageContent>
              </Message>
            ) : null}

            {result ? <EmailSources sources={result.sources} /> : null}

            {result ? (
              <p role="status" className="sr-only">
                Answer ready. {result.sources.length} email {result.sources.length === 1 ? "source" : "sources"}.
              </p>
            ) : null}

            {errorMessage ? (
              <Alert>
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            ) : null}
          </div>
        ) : (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>Ask about your inbox</EmptyTitle>
              <EmptyDescription>
                Your latest question and answer will appear here.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </div>

      <div className="mx-auto w-full max-w-3xl shrink-0">
        <label className="sr-only" htmlFor="inbox-question">
          Ask about your inbox
        </label>
        <PromptInput maxFiles={0} onSubmit={handleSubmit}>
          <PromptInputTextarea
            id="inbox-question"
            disabled={isAsking}
            onChange={(event) => setDraft(event.currentTarget.value)}
            placeholder="Ask about your inbox..."
            value={draft}
          />
          <PromptInputFooter className="justify-end">
            <PromptInputSubmit
              aria-label={isAsking ? "Asking" : "Ask question"}
              disabled={isAsking || !draft.trim()}
              status={isAsking ? "submitted" : "ready"}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </section>
  );
}
