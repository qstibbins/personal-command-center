import { redirect } from "next/navigation";

import { getAllowlistedSession } from "../../../auth-session";
import { signOutAction } from "../../auth-actions";
import { ChatShell } from "../chat-shell";

export const dynamic = "force-dynamic";

type ChatConversationPageProps = {
  params: Promise<{ conversationId: string }>;
};

export default async function ChatConversationPage({
  params,
}: ChatConversationPageProps) {
  const session = await getAllowlistedSession();
  if (!session) {
    redirect("/signin");
  }

  const { conversationId } = await params;
  if (!conversationId) {
    redirect("/chat");
  }

  const email = session.user?.email ?? "signed in";

  return (
    <ChatShell
      email={email}
      signOutAction={signOutAction}
      initialConversationId={conversationId}
    />
  );
}
