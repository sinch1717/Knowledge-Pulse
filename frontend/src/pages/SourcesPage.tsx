import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import type { Source, SourceStatus } from "@/lib/types";
import { Button, EmptyState, ErrorNote, Loading, Page } from "@/components/ui";

const statusCopy: Record<SourceStatus, { label: string; colour: string }> = {
  queued: { label: "Queued", colour: "#8B8171" },
  crawling: { label: "Crawling", colour: "#A87C2A" },
  indexing: { label: "Indexing", colour: "#A87C2A" },
  ready: { label: "Indexed", colour: "#5A6337" },
  failed: { label: "Failed", colour: "#7A2E2E" },
};

export function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    api.getSources().then(setSources).catch((e: Error) => setError(e.message));
  }, []);

  async function addSite() {
    const value = url.trim();
    if (!value) return;
    setAdding(true);
    try {
      const created = await api.addSource({ kind: "website", location: value });
      setSources((s) => [created, ...(s ?? [])]);
      setUrl("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  return (
    <Page
      title="Sources"
      standfirst="What the assistant is allowed to answer from. A site is crawled from the address you give down to the depth set in config; files are parsed on upload."
    >
      <div className="mb-10 max-w-measure">
        <label htmlFor="site" className="text-small text-ink-soft">
          Add a website
        </label>
        <div className="mt-2 flex gap-2">
          <input
            id="site"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addSite()}
            placeholder="https://docs.example.com"
            className="min-w-0 flex-1 rounded border border-rule-strong bg-paper-raised px-4 py-2.5 text-base placeholder:text-ink-faint"
          />
          <Button onClick={addSite} disabled={adding || !url.trim()}>
            {adding ? "Adding" : "Crawl site"}
          </Button>
        </div>
        <p className="mt-2 text-micro text-ink-faint">
          Crawling stays inside the domain you supply and skips anything behind a login.
        </p>
      </div>

      {error && <ErrorNote message={error} />}
      {!sources && !error && <Loading />}

      {sources && sources.length === 0 && (
        <EmptyState title="No sources yet. Add a documentation site above to give the assistant something to answer from." />
      )}

      {sources && sources.length > 0 && (
        <div className="border-t border-rule-strong">
          {sources.map((s) => {
            const st = statusCopy[s.status];
            return (
              <div key={s.id} className="border-b border-rule px-1 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                  <span className="text-lead">{s.label}</span>
                  <span className="text-micro font-medium" style={{ color: st.colour }}>
                    {st.label}
                  </span>
                </div>
                <p className="mt-0.5 break-all font-mono text-micro text-ink-faint">{s.location}</p>
                <div className="tabular mt-2 flex flex-wrap gap-x-6 gap-y-1 font-mono text-micro text-ink-faint">
                  <span>{s.kind}</span>
                  <span>{s.pageCount} pages</span>
                  <span>{s.chunkCount.toLocaleString()} chunks</span>
                  <span>indexed {dateLabel(s.lastIndexedAt)}</span>
                  {s.contentHash && <span>hash {s.contentHash}</span>}
                </div>
                {s.error && (
                  <p className="mt-2 border-l-2 border-oxblood pl-3 text-small text-oxblood-deep">{s.error}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Page>
  );
}
