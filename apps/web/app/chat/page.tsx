import { redirect } from "next/navigation";

import { getAllowlistedSession } from "../../auth-session";
import { signOutAction } from "../auth-actions";
import { ChatShell } from "./chat-shell";

export const dynamic = "force-dynamic";

export default async function ChatPage() {
  const session = await getAllowlistedSession();
  if (!session) {
    redirect("/signin");
  }

  const email = session.user?.email ?? "signed in";

  return (
    <ChatShell
      email={email}
      signOutAction={signOutAction}
      initialConversationId={null}
    />
  );
}
