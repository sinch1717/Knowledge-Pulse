import { useRef, useState, type DragEvent } from "react";
import clsx from "clsx";
import { FileText, Globe, Loader2, UploadCloud } from "lucide-react";
import type { BackendState, Source, SourceKind, SourceStatus } from "@/lib/types";
import { relativeTime } from "@/lib/format";
import { Button, Dialog, Panel, StatusBadge, inputClass, type Tone } from "@/components/ui";

// ---- status -----------------------------------------------------------------

const statusCopy: Record<SourceStatus, { label: string; tone: Tone }> = {
  queued: { label: "Pending", tone: "ink" },
  crawling: { label: "Processing", tone: "ochre" },
  indexing: { label: "Processing", tone: "ochre" },
  ready: { label: "Ready", tone: "olive" },
  failed: { label: "Failed", tone: "oxblood" },
};

export const isProcessing = (s: SourceStatus) => s === "queued" || s === "crawling" || s === "indexing";

export function SourceStatusBadge({ status }: { status: SourceStatus }) {
  const s = statusCopy[status];
  return (
    <StatusBadge tone={s.tone}>
      {isProcessing(status) && status !== "queued" && <Loader2 size={11} className="animate-spin" aria-hidden />}
      {s.label}
    </StatusBadge>
  );
}

const kindLabel: Record<SourceKind, string> = {
  website: "Website",
  pdf: "PDF",
  docx: "Word document",
  text: "Text file",
};

const progressCopy: Partial<Record<SourceStatus, string>> = {
  queued: "Waiting to start...",
  crawling: "Crawling pages...",
  indexing: "Processing document...",
};

export function BackendStatus({ state }: { state: BackendState | null }) {
  const [dot, text] =
    state === "connected"
      ? ["bg-olive", "Connected"]
      : state === "unreachable"
        ? ["bg-oxblood", "Backend unreachable"]
        : state === "mock"
          ? ["bg-ochre", "Placeholder data"]
          : ["bg-ink-faint", "Checking connection"];
  return (
    <span className="inline-flex items-center gap-2 text-small text-ink-soft">
      <span aria-hidden className={clsx("h-2 w-2 rounded-full", dot)} />
      {text}
    </span>
  );
}

// ---- one source -------------------------------------------------------------

export function SourceCard({
  source: s,
  busy,
  onReindex,
  onDelete,
}: {
  source: Source;
  busy: boolean;
  onReindex: () => void;
  onDelete: () => void;
}) {
  const processing = isProcessing(s.status);
  const Icon = s.kind === "website" ? Globe : FileText;
  return (
    <Panel className={clsx("p-5 transition-opacity", busy && "opacity-60")}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 gap-3">
          <Icon size={18} className="mt-1 shrink-0 text-ink-faint" aria-hidden />
          <div className="min-w-0">
            <p className="text-lead font-medium">{s.label}</p>
            <p className="text-small text-ink-faint">{kindLabel[s.kind]}</p>
            <p className="mt-0.5 break-all font-mono text-micro text-ink-faint">{s.location}</p>
          </div>
        </div>
        <SourceStatusBadge status={s.status} />
      </div>

      <div className="mt-4 pl-[1.875rem]">
        {processing ? (
          <p className="text-small text-ink-soft">{progressCopy[s.status]}</p>
        ) : (
          <div className="tabular flex flex-wrap gap-x-5 gap-y-1 text-small text-ink-soft">
            <span>{s.pageCount.toLocaleString()} {s.pageCount === 1 ? "page" : "pages"}</span>
            <span>{s.chunkCount.toLocaleString()} chunks</span>
            <span className="text-ink-faint">
              {s.lastIndexedAt ? `Last indexed ${relativeTime(s.lastIndexedAt)}` : "Never indexed"}
            </span>
          </div>
        )}

        {s.error && (
          <p className="mt-3 border-l-2 border-oxblood pl-3 text-small text-oxblood-deep">{s.error}</p>
        )}

        {!processing && (
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="quiet" onClick={onReindex} disabled={busy}>
              Reindex
            </Button>
            <Button variant="danger" onClick={onDelete} disabled={busy}>
              Delete
            </Button>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ---- adding sources -----------------------------------------------------------

export function AddWebsiteForm({ onAdd }: { onAdd: (url: string, label: string) => Promise<void> }) {
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const valid = /^https?:\/\/\S+\.\S+/.test(url.trim());

  async function submit() {
    if (!valid) return;
    setBusy(true);
    try {
      await onAdd(url.trim(), label.trim());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="site-url" className="text-small text-ink-soft">Website address</label>
        <input
          id="site-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="https://docs.example.com"
          className={clsx(inputClass, "mt-1")}
        />
        <p className="mt-1 text-micro text-ink-faint">
          Crawling stays inside this domain and skips anything behind a login.
        </p>
      </div>
      <div>
        <label htmlFor="site-label" className="text-small text-ink-soft">Name (optional)</label>
        <input
          id="site-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Product documentation"
          className={clsx(inputClass, "mt-1")}
        />
      </div>
      <div className="flex justify-end">
        <Button onClick={submit} disabled={!valid} busy={busy}>
          Add website
        </Button>
      </div>
    </div>
  );
}

const ACCEPT = [".pdf", ".docx", ".txt"];

export function FileDropzone({ file, onFile }: { file: File | null; onFile: (f: File | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);

  function accept(f: File | undefined) {
    if (!f) return;
    const ok = ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext));
    setRejected(ok ? null : `${f.name} is not a PDF, Word or text file.`);
    onFile(ok ? f : null);
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    accept(e.dataTransfer.files[0]);
  };

  return (
    <div>
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={clsx(
          "flex w-full flex-col items-center justify-center rounded-md border border-dashed px-6 py-8 text-center transition-colors",
          over ? "border-oxblood bg-oxblood-wash" : "border-rule-strong bg-paper hover:bg-paper-sunk",
        )}
      >
        <UploadCloud size={22} className="text-ink-faint" aria-hidden />
        {file ? (
          <>
            <span className="mt-2 text-small font-medium text-ink">{file.name}</span>
            <span className="text-micro text-ink-faint">{(file.size / 1024).toFixed(0)} KB, click to change</span>
          </>
        ) : (
          <>
            <span className="mt-2 text-small text-ink">Drop a file here or click to choose</span>
            <span className="text-micro text-ink-faint">PDF, DOCX or TXT</span>
          </>
        )}
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT.join(",")}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => accept(e.target.files?.[0])}
      />
      {rejected && <p className="mt-2 text-small text-oxblood">{rejected}</p>}
    </div>
  );
}

export function UploadDocumentForm({ onUpload }: { onUpload: (file: File, label: string) => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!file) return;
    setBusy(true);
    try {
      await onUpload(file, label.trim());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <FileDropzone file={file} onFile={setFile} />
      <div>
        <label htmlFor="doc-label" className="text-small text-ink-soft">Name (optional)</label>
        <input
          id="doc-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Product manual"
          className={clsx(inputClass, "mt-1")}
        />
      </div>
      <div className="flex justify-end">
        <Button onClick={submit} disabled={!file} busy={busy}>
          Upload document
        </Button>
      </div>
    </div>
  );
}

export function AddSourceDialog({
  open,
  onClose,
  onAddWebsite,
  onUpload,
}: {
  open: boolean;
  onClose: () => void;
  onAddWebsite: (url: string, label: string) => Promise<void>;
  onUpload: (file: File, label: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<"website" | "document">("website");
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add source"
      description="The assistant answers only from sources you add here."
    >
      <div role="tablist" className="mb-5 flex gap-1 rounded border border-rule-strong bg-paper p-1">
        {(["website", "document"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={clsx(
              "flex-1 rounded px-3 py-1.5 text-small transition-colors",
              tab === t ? "bg-paper-raised font-medium text-ink shadow-sm" : "text-ink-soft hover:text-ink",
            )}
          >
            {t === "website" ? "Website" : "Upload document"}
          </button>
        ))}
      </div>
      {tab === "website" ? <AddWebsiteForm onAdd={onAddWebsite} /> : <UploadDocumentForm onUpload={onUpload} />}
    </Dialog>
  );
}
