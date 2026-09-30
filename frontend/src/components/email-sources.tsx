import { Fragment } from "react";

import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemSeparator,
  ItemTitle,
} from "@/components/ui/item";
import type { EmailSource } from "@/lib/api/types";

type EmailSourceItemProps = {
  source: EmailSource;
  number: number;
};

function EmailSourceItem({ source, number }: EmailSourceItemProps) {
  return (
    <Item role="listitem" className="min-w-0 px-0 py-4">
      <ItemContent className="min-w-0 gap-2">
        <p className="text-xs font-medium text-muted-foreground">
          Source {number}
        </p>
        <ItemTitle className="block w-full line-clamp-none break-words leading-6">
          {source.subject?.trim() || "No subject"}
        </ItemTitle>
        <ItemDescription className="line-clamp-none break-all">
          From: {source.from_email?.trim() || "Sender unavailable"}
        </ItemDescription>
        <ItemDescription className="line-clamp-none break-words">
          Date: {source.date?.trim() || "Unavailable"}
        </ItemDescription>
        <ItemDescription className="line-clamp-none whitespace-pre-wrap break-words">
          {source.preview.trim() || "No matching excerpt available."}
        </ItemDescription>
      </ItemContent>
    </Item>
  );
}

type EmailSourcesProps = {
  sources: EmailSource[];
};

export function EmailSources({ sources }: EmailSourcesProps) {
  return (
    <section aria-labelledby="email-sources-heading" className="space-y-2">
      <h2 id="email-sources-heading" className="text-sm font-semibold">
        Sources
      </h2>
      {sources.length === 0 ? (
        <p className="text-sm leading-6 text-muted-foreground">
          No matching email sources were returned for this answer.
        </p>
      ) : (
        <ItemGroup className="gap-0">
          {sources.map((source, index) => (
            <Fragment key={source.chunk_id}>
              {index > 0 ? <ItemSeparator className="my-0" /> : null}
              <EmailSourceItem source={source} number={index + 1} />
            </Fragment>
          ))}
        </ItemGroup>
      )}
    </section>
  );
}
