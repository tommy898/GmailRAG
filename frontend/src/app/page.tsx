import { SignInButton } from "@/components/auth/sign-in-button";
import { createClient } from "@/lib/supabase/server";
import { SignOutButton} from "@/components/auth/sign-out-button";

export default async function Home() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main>
      <h1>GmailRAG</h1>

      {user ? (
      <>
        <p>Signed in as {user.email}</p>
        <SignOutButton />
       </>
      ) : (
        <>
          <p>Sign in to continue.</p>
          <SignInButton />
        </>
      )}
    </main>
  );
}