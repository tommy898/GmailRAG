import type { CSSProperties } from "react";
import Image from "next/image";

import { AskTestForm } from "@/components/ask-test-form";
import { ConnectGmailButton } from "@/components/auth/connect-gmail-button";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { GmailSidebarPanel } from "@/components/gmail-sidebar-panel";
import { SyncTestPanel } from "@/components/sync-test-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import gmailRagLogo from "@/components/ui/gmailRAG.png";

type AuthenticatedShellProps = {
  email: string;
  gmailConnected: boolean;
  gmailErrorMessage?: string;
};

export function AuthenticatedShell({
  email,
  gmailConnected,
  gmailErrorMessage,
}: AuthenticatedShellProps) {
  return (
    <SidebarProvider
      className="min-w-0"
      style={
        {
          "--sidebar-width": "var(--layout-sidebar-width)",
        } as CSSProperties
      }
    >
      <SidebarInset className="min-w-0 w-auto">
        <header className="flex h-(--layout-header-height) shrink-0 items-center gap-4 border-b px-6">
          <Image
            src={gmailRagLogo}
            alt=""
            width={40}
            height={40}
            className="size-10 rounded-full object-cover"
          />
          <h1 className="text-base font-semibold tracking-tight">
            GmailRAG
          </h1>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-6 p-6">
          {gmailConnected ? (
            <Alert role="status">
              <AlertDescription>Gmail connected.</AlertDescription>
            </Alert>
          ) : null}

          {gmailErrorMessage ? (
            <Alert>
              <AlertDescription>{gmailErrorMessage}</AlertDescription>
            </Alert>
          ) : null}

          <section
            aria-label="Question and answer workspace"
            className="flex min-h-0 flex-1 flex-col"
          >
            <Empty>
              <EmptyHeader>
                <EmptyTitle>Ask about your inbox</EmptyTitle>
                <EmptyDescription>
                  Your latest question and answer will appear here.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </section>

          <details className="rounded-lg border p-4 text-sm">
            <summary className="cursor-pointer font-medium">
              Existing test controls
            </summary>
            <div className="mt-4 flex flex-col gap-4 overflow-auto">
              <ConnectGmailButton />
              <SyncTestPanel />
              <AskTestForm />
            </div>
          </details>
        </div>
      </SidebarInset>

      <Sidebar
        side="right"
        collapsible="none"
        className="sticky top-0 h-svh shrink-0 border-l border-sidebar-border"
      >
        <SidebarContent className="gap-0">
          <div className="my-auto w-full py-8">
            <SidebarHeader className="items-center gap-4 px-6 text-center">
              <Image
                src={gmailRagLogo}
                alt=""
                width={80}
                height={80}
                className="size-20 rounded-full object-cover"
              />
              <div className="space-y-1 [&_p]:leading-6">
                <p className="text-sm font-medium">AI Gmail Assistant</p>
              </div>
            </SidebarHeader>

            <SidebarGroup>
              <SidebarGroupContent>
                <GmailSidebarPanel />
              </SidebarGroupContent>
            </SidebarGroup>
          </div>
        </SidebarContent>

        <SidebarSeparator />
        <SidebarFooter className="gap-4 px-6 py-6">
          <div className="min-w-0 space-y-1 [&_p]:leading-6">
            <p className="text-xs text-muted-foreground">Signed in as</p>
            <p className="truncate text-sm font-medium" title={email}>
              {email}
            </p>
          </div>
          <SignOutButton />
        </SidebarFooter>
      </Sidebar>
    </SidebarProvider>
  );
}
