import { useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Message } from "@/lib/types";
import { Button, Page } from "@/components/ui";

const sessionId = `sess_${Math.random().toString(36).slice(2, 10)}`;

const starters = [
  "Can I edit an invoice after I've sent it?",
  "Why did my client's autopay not go through?",
  "Where do I add an LUT number for an export invoice?",
];

export function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  async function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setDraft("");
    setMessages((m) => [
      ...m,
      { id: `local_${Date.now()}`, role: "customer", text: question, createdAt: new Date().toISOString() },
    ]);
    setPending(true);
    try {
      const reply = await api.ask(question, sessionId);
      setMessages((m) => [...m, reply]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: `err_${Date.now()}`,
          role: "assistant",
          text: `The assistant is not reachable. ${(e as Error).message}`,
          createdAt: new Date().toISOString(),
        },
      ]);
    } finally {
      setPending(false);
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: "smooth" }));
    }
  }

  return (
    <Page
      title="Ask"
      standfirst="The customer-facing side. Every turn here is logged with its retrieval confidence and feeds the analytics batch."
    >
      <div className="max-w-measure">
        {messages.length === 0 && (
          <div className="mb-8">
            <p className="text-ink-soft">Try one of these, or type your own.</p>
            <div className="mt-3 space-y-2">
              {starters.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="block w-full border-l-2 border-rule-strong px-4 py-2 text-left text-small text-ink-soft transition-colors hover:border-oxblood hover:bg-paper-raised hover:text-ink"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-8">
          {messages.map((m) =>
            m.role === "customer" ? (
              <p key={m.id} className="border-l-2 border-ink pl-4 text-lead">
                {m.text}
              </p>
            ) : (
              <div key={m.id}>
                {m.text.split("\n\n").map((para, n) => (
                  <p key={n} className="mb-3 text-base text-ink-soft last:mb-0">
                    {para}
                  </p>
                ))}

                {typeof m.confidence === "number" && (
                  <div className="mt-4 flex items-center gap-3">
                    <div className="h-1 w-32 bg-paper-sunk">
                      <div
                        className="h-full"
                        style={{
                          width: `${m.confidence * 100}%`,
                          background: m.confidence < 0.4 ? "#7A2E2E" : "#5A6337",
                        }}
                      />
                    </div>
                    <span className="tabular font-mono text-micro text-ink-faint">
                      retrieval confidence {m.confidence.toFixed(2)}
                      {m.confidence < 0.4 && " — the sources may not cover this"}
                    </span>
                  </div>
                )}

                {m.citations && m.citations.length > 0 && (
                  <div className="mt-4 space-y-3">
                    {m.citations.map((c) => (
                      <figure key={c.chunkId} className="border-l border-rule-strong pl-4">
                        <blockquote className="text-small text-ink-soft">{c.excerpt}</blockquote>
                        <figcaption className="mt-1 font-mono text-micro text-ink-faint">
                          {c.sourceLabel} · {c.headingPath} · {c.similarity.toFixed(2)}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
              </div>
            ),
          )}
          {pending && <p className="text-small text-ink-faint">Searching the sources…</p>}
          <div ref={endRef} />
        </div>

        <div className="sticky bottom-0 mt-10 flex gap-2 border-t border-rule bg-paper py-4">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(draft)}
            placeholder="Ask about invoicing, payments or your account"
            className="min-w-0 flex-1 rounded border border-rule-strong bg-paper-raised px-4 py-2.5 text-base placeholder:text-ink-faint"
          />
          <Button onClick={() => send(draft)} disabled={pending || !draft.trim()}>
            Send
          </Button>
        </div>
      </div>
    </Page>
  );
}
