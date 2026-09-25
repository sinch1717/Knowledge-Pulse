import { useEffect, useRef, useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import { usingMockData } from "@/lib/api";
import { Button, PageContainer, PageHeader, Panel } from "@/components/ui";
import {
  AssistantMessageBubble,
  ChatComposer,
  ChatEmptyState,
  ChatError,
  ChatLoadingBubble,
  UserMessageBubble,
} from "@/components/ask/chat";
import { useConversation } from "@/components/ask/conversation";

// The placeholder data describes an invoicing product; the live demo indexes
// the Plausible Analytics docs. Examples follow whichever is on screen.
const examples = usingMockData
  ? [
      "Can I edit an invoice after I've sent it?",
      "Why did my client's autopay not go through?",
      "Where do I add an LUT number for an export invoice?",
    ]
  : [
      "How do I add the tracking script to my site?",
      "Can I exclude my own visits from the stats?",
      "How do I set up a custom event goal?",
    ];

export function AskPage() {
  // The conversation lives above the routes (see conversation.tsx), so it is
  // still here after visiting another page, and reloads from the server.
  const { messages, loading, pending, failed, historyError, send, retry, reload, startNew } = useConversation();
  const [draft, setDraft] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Only once there is a conversation: scrolling the empty state would hide its heading.
    if (messages.length === 0 && !pending) return;
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, failed]);

  function submit(text: string) {
    if (!text.trim() || pending || loading) return;
    setDraft("");
    send(text);
  }

  const empty = messages.length === 0 && !pending && !loading && !historyError;

  return (
    <PageContainer narrow>
      <PageHeader centered title="Ask KnowledgePulse" description="Ask a question about your connected knowledge." />

      <Panel className="flex h-[calc(100vh-20rem)] min-h-[26rem] flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-rule px-5 py-2.5">
          <p className="text-small font-medium">Assistant</p>
          <Button
            variant="quiet"
            onClick={() => {
              setDraft("");
              startNew();
            }}
            disabled={pending || (messages.length === 0 && !failed)}
            className="px-3 py-1.5"
          >
            <MessageSquarePlus size={14} aria-hidden />
            New conversation
          </Button>
        </div>

        <div ref={scroller} className="flex-1 overflow-y-auto px-5 py-6" aria-live="polite">
          {loading ? (
            <p role="status" className="py-10 text-center text-small text-ink-faint">
              Loading this conversation
            </p>
          ) : historyError ? (
            <ChatError message={`Could not load this conversation. ${historyError}`} onRetry={reload} />
          ) : empty ? (
            <ChatEmptyState examples={examples} onPick={submit} />
          ) : (
            <div className="space-y-6">
              {messages.map((m) =>
                m.role === "customer" ? (
                  <UserMessageBubble key={m.id} text={m.text} />
                ) : (
                  <AssistantMessageBubble key={m.id} message={m} />
                ),
              )}
              {pending && <ChatLoadingBubble />}
              {failed && <ChatError message={failed.error} onRetry={retry} />}
            </div>
          )}
        </div>

        <div className="border-t border-rule p-3">
          <ChatComposer value={draft} onChange={setDraft} onSend={() => submit(draft)} disabled={pending || loading} />
          <p className="mt-2 px-1 text-micro text-ink-faint">
            Enter to send, Shift and Enter for a new line. Every question is logged for the period's analytics, and
            the conversation stays here until you start a new one.
          </p>
        </div>
      </Panel>
    </PageContainer>
  );
}
