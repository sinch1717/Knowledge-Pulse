import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { api, usingMockData } from "@/lib/api";
import type { BackendState, Source } from "@/lib/types";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  PageContainer,
  PageHeader,
  RowSkeletons,
} from "@/components/ui";
import { useToast } from "@/components/toast";
import { AddSourceDialog, BackendStatus, SourceCard, isProcessing } from "@/components/sources/parts";

const POLL_MS = 4000;

export function SourcesPage() {
  const toast = useToast();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backend, setBackend] = useState<BackendState | null>(null);
  const [adding, setAdding] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<Source | null>(null);

  const load = useCallback(async () => {
    try {
      setSources(await api.getSources());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
    api.getHealth().then(setBackend);
  }, [load]);

  // Keep polling while anything is being crawled or indexed, so status updates on its own.
  const anyProcessing = sources?.some((s) => isProcessing(s.status)) ?? false;
  useEffect(() => {
    if (!anyProcessing || usingMockData) return;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [anyProcessing, load]);

  function added(created: Source) {
    setSources((s) => [created, ...(s ?? [])]);
    setAdding(false);
    toast(`Added ${created.label}. It will be ready to answer from once indexing finishes.`, "success");
  }

  async function addWebsite(url: string, label: string) {
    try {
      added(await api.addSource({ kind: "website", location: url, label: label || undefined }));
    } catch (e) {
      toast(`Could not add the website. ${(e as Error).message}`, "error");
    }
  }

  async function upload(file: File, label: string) {
    try {
      added(await api.uploadSource(file, label || undefined));
    } catch (e) {
      toast(`Could not upload ${file.name}. ${(e as Error).message}`, "error");
    }
  }

  async function reindex(source: Source) {
    setBusyId(source.id);
    try {
      await api.reindexSource(source.id);
      setSources((all) => all?.map((s) => (s.id === source.id ? { ...s, status: "queued", error: undefined } : s)) ?? null);
      toast(`Reindexing ${source.label}. Its old chunks are replaced, nothing else changes.`, "info");
      if (!usingMockData) void load();
    } catch (e) {
      toast(`Could not reindex ${source.label}. ${(e as Error).message}`, "error");
    } finally {
      setBusyId(null);
    }
  }

  async function confirmDelete() {
    if (!toDelete) return;
    const target = toDelete;
    setBusyId(target.id);
    try {
      await api.deleteSource(target.id);
      setSources((all) => all?.filter((s) => s.id !== target.id) ?? null);
      toast(`Deleted ${target.label}.`, "success");
      setToDelete(null);
    } catch (e) {
      toast(`Could not delete ${target.label}. ${(e as Error).message}`, "error");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <PageContainer>
      <PageHeader
        title="Sources"
        description="Manage the knowledge used by KnowledgePulse."
        meta={<BackendStatus state={backend} />}
        actions={
          <Button onClick={() => setAdding(true)}>
            <Plus size={14} aria-hidden />
            Add source
          </Button>
        }
      />

      {error && !sources && <ErrorState message={error} onRetry={load} />}
      {!sources && !error && <RowSkeletons rows={3} />}

      {sources && sources.length === 0 && (
        <EmptyState
          title="No sources yet"
          description="Add a documentation website or upload a PDF or Word file to give the assistant something to answer from."
          action={
            <Button onClick={() => setAdding(true)}>
              <Plus size={14} aria-hidden />
              Add source
            </Button>
          }
        />
      )}

      {sources && sources.length > 0 && (
        <div className="space-y-4">
          {sources.map((s) => (
            <SourceCard
              key={s.id}
              source={s}
              busy={busyId === s.id}
              onReindex={() => reindex(s)}
              onDelete={() => setToDelete(s)}
            />
          ))}
        </div>
      )}

      <AddSourceDialog open={adding} onClose={() => setAdding(false)} onAddWebsite={addWebsite} onUpload={upload} />

      <ConfirmDialog
        open={toDelete !== null}
        title={`Delete ${toDelete?.label ?? "source"}?`}
        description="Its chunks are removed from the index and the assistant stops answering from it. Conversations already logged are kept."
        confirmLabel="Delete source"
        busy={busyId === toDelete?.id}
        onConfirm={confirmDelete}
        onClose={() => setToDelete(null)}
      />
    </PageContainer>
  );
}
