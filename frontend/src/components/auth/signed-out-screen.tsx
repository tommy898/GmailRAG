import Image from "next/image";

import { SignInButton } from "@/components/auth/sign-in-button";
import gmailRagLogo from "@/components/ui/gmailRAG.png";

type SignedOutScreenProps = {
  authErrorMessage?: string;
};

export function SignedOutScreen({
  authErrorMessage,
}: SignedOutScreenProps) {
  return (
    <main className="flex min-h-svh flex-col bg-background">
      <section
        className="flex flex-1 items-center justify-center px-6 py-16"
        aria-labelledby="sign-in-heading"
      >
        <div className="flex w-full max-w-sm flex-col items-center text-center">
          <div className="flex flex-col items-center gap-4">
            <Image
              src={gmailRagLogo}
              alt=""
              width={56}
              height={56}
              className="size-14 rounded-full object-cover"
            />
            <h1
              id="sign-in-heading"
              className="text-3xl font-semibold tracking-tight"
            >
              GmailRAG
            </h1>
          </div>

          <p className="mt-8 text-lg font-medium text-balance">
            Address all questions about your Gmail inbox
          </p>

          <div className="mt-10 w-full">
            <SignInButton initialErrorMessage={authErrorMessage} />
          </div>

          <p className="mt-8 max-w-xs text-sm leading-6 text-muted-foreground">
            Please contact tzzhao@cs.washington.edu if you are interested to
            become a test user.
          </p>
        </div>
      </section>

      <footer className="px-6 pb-12 text-center text-sm font-medium">
        <a
          className="underline underline-offset-4 transition-colors hover:text-muted-foreground focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          href="https://github.com/tommy898/GmailRAG"
          target="_blank"
          rel="noreferrer noopener"
        >
          More about this project on GitHub
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      </footer>
    </main>
  );
}
