import { useEffect, useRef, useState } from "react";
import { api, usingMockData } from "@/lib/api";
import type { Message } from "@/lib/types";
import { PageContainer, PageHeader, Panel } from "@/components/ui";
import {
  AssistantMessageBubble,
  ChatComposer,
  ChatEmptyState,
  ChatError,
  ChatLoadingBubble,
  UserMessageBubble,
} from "@/components/ask/chat";

const sessionId = `sess_${Math.random().toString(36).slice(2, 10)}`;

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
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState<{ question: string; error: string } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, failed]);

  async function ask(question: string, addTurn: boolean) {
    if (addTurn) {
      setMessages((m) => [
        ...m,
        { id: `local_${Date.now()}`, role: "customer", text: question, createdAt: new Date().toISOString() },
      ]);
    }
    setFailed(null);
    setPending(true);
    try {
      const reply = await api.ask(question, sessionId);
      setMessages((m) => [...m, reply]);
    } catch (e) {
      setFailed({ question, error: (e as Error).message });
    } finally {
      setPending(false);
    }
  }

  function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setDraft("");
    void ask(question, true);
  }

  return (
    <PageContainer narrow>
      <PageHeader centered title="Ask KnowledgePulse" description="Ask a question about your connected knowledge." />

      <Panel className="flex h-[calc(100vh-20rem)] min-h-[26rem] flex-col">
        <div className="border-b border-rule px-5 py-3">
          <p className="text-small font-medium">Assistant</p>
        </div>

        <div ref={scroller} className="flex-1 overflow-y-auto px-5 py-6" aria-live="polite">
          {messages.length === 0 && !pending ? (
            <ChatEmptyState examples={examples} onPick={send} />
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
              {failed && <ChatError message={failed.error} onRetry={() => ask(failed.question, false)} />}
            </div>
          )}
        </div>

        <div className="border-t border-rule p-3">
          <ChatComposer value={draft} onChange={setDraft} onSend={() => send(draft)} disabled={pending} />
          <p className="mt-2 px-1 text-micro text-ink-faint">
            Enter to send, Shift and Enter for a new line. Every question is logged for the period's analytics.
          </p>
        </div>
      </Panel>
    </PageContainer>
  );
}
