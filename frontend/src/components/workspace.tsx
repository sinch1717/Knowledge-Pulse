import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import clsx from "clsx";
import { api, getWorkspaceId, setWorkspaceId } from "@/lib/api";
import type { Workspace, WorkspaceInput } from "@/lib/types";
import { Button, ConfirmDialog, Dialog, inputClass } from "@/components/ui";
import { useToast } from "@/components/toast";

interface WorkspaceState {
  workspaces: Workspace[];
  current: Workspace | null;
  select: (id: string) => void;
  refresh: () => Promise<void>;
  openCreate: () => void;
  openSettings: () => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return ctx;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentId, setCurrentId] = useState(getWorkspaceId());
  const [dialog, setDialog] = useState<"create" | "settings" | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api.getWorkspaces();
      setWorkspaces(list);
      // The saved workspace may have been deleted elsewhere; fall back to the first.
      if (list.length && !list.some((w) => w.id === getWorkspaceId())) {
        setWorkspaceId(list[0].id);
        setCurrentId(list[0].id);
      }
    } catch (e) {
      toast(`Could not load workspaces. ${(e as Error).message}`, "error");
    }
  }, [toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const select = useCallback((id: string) => {
    setWorkspaceId(id);
    setCurrentId(id);
  }, []);

  const current = workspaces.find((w) => w.id === currentId) ?? null;

  return (
    <WorkspaceContext.Provider
      value={{
        workspaces,
        current,
        select,
        refresh,
        openCreate: () => setDialog("create"),
        openSettings: () => setDialog("settings"),
      }}
    >
      {/* Keyed on the workspace so every page refetches its data on switch. */}
      <div key={currentId} className="contents">
        {children}
      </div>
      <WorkspaceDialog
        mode={dialog}
        workspace={dialog === "settings" ? current : null}
        onClose={() => setDialog(null)}
        onSaved={async (ws, created) => {
          setDialog(null);
          await refresh();
          if (created) select(ws.id);
          toast(created ? `Created ${ws.name}. Add a source to get started.` : `Saved ${ws.name}.`, "success");
        }}
        onDeleted={async (name) => {
          setDialog(null);
          select("ws_default");
          await refresh();
          toast(`Deleted ${name} and everything in it.`, "success");
        }}
      />
    </WorkspaceContext.Provider>
  );
}

// ---------------------------------------------------------------------------

function NumberField({
  id,
  label,
  hint,
  value,
  onChange,
  min,
  max,
}: {
  id: string;
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
  min: number;
  max: number;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-small text-ink-soft">
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={clsx(inputClass, "mt-1 tabular")}
      />
      <p className="mt-1 text-micro text-ink-faint">{hint}</p>
    </div>
  );
}

function WorkspaceDialog({
  mode,
  workspace,
  onClose,
  onSaved,
  onDeleted,
}: {
  mode: "create" | "settings" | null;
  workspace: Workspace | null;
  onClose: () => void;
  onSaved: (ws: Workspace, created: boolean) => void;
  onDeleted: (name: string) => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [size, setSize] = useState("");
  const [overlap, setOverlap] = useState("");
  const [pages, setPages] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!mode) return;
    setName(workspace?.name ?? "");
    setDescription(workspace?.description ?? "");
    setSize(String(workspace?.chunkTargetWords ?? 220));
    setOverlap(String(workspace?.chunkOverlapWords ?? 40));
    setPages(String(workspace?.crawlMaxPages ?? 120));
  }, [mode, workspace]);

  const sizeN = Number(size);
  const overlapN = Number(overlap);
  const pagesN = Number(pages);
  const problem =
    !name.trim()
      ? "Give the workspace a name."
      : !(sizeN >= 40 && sizeN <= 2000)
        ? "Chunk size must be between 40 and 2000 words."
        : !(overlapN >= 0 && overlapN < sizeN)
          ? "Overlap must be zero or more, and smaller than the chunk size."
          : !(pagesN >= 1 && pagesN <= 2000)
            ? "Page limit must be between 1 and 2000."
            : null;

  async function save() {
    if (problem) return;
    setBusy(true);
    const input: WorkspaceInput = {
      name: name.trim(),
      description: description.trim(),
      chunkTargetWords: sizeN,
      chunkOverlapWords: overlapN,
      crawlMaxPages: pagesN,
    };
    try {
      const ws = mode === "create" ? await api.createWorkspace(input) : await api.updateWorkspace(workspace!.id, input);
      onSaved(ws, mode === "create");
    } catch (e) {
      toast(`Could not save the workspace. ${(e as Error).message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!workspace) return;
    setBusy(true);
    try {
      await api.deleteWorkspace(workspace.id);
      setConfirmDelete(false);
      onDeleted(workspace.name);
    } catch (e) {
      toast(`Could not delete the workspace. ${(e as Error).message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  const settingsChanged =
    mode === "settings" &&
    workspace &&
    (sizeN !== workspace.chunkTargetWords || overlapN !== workspace.chunkOverlapWords) &&
    workspace.sourceCount > 0;

  return (
    <>
      <Dialog
        open={mode !== null && !confirmDelete}
        onClose={onClose}
        title={mode === "create" ? "New workspace" : "Workspace settings"}
        description={
          mode === "create"
            ? "A separate space with its own sources, conversations, insights and reports."
            : "Changes to chunking apply the next time a source is indexed or reindexed."
        }
      >
        <div className="space-y-4">
          <div>
            <label htmlFor="ws-name" className="text-small text-ink-soft">
              Name
            </label>
            <input
              id="ws-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="FastAPI docs"
              className={clsx(inputClass, "mt-1")}
            />
          </div>
          <div>
            <label htmlFor="ws-desc" className="text-small text-ink-soft">
              Description (optional)
            </label>
            <input
              id="ws-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this workspace is for"
              className={clsx(inputClass, "mt-1")}
            />
          </div>

          <fieldset className="rounded-md border border-rule p-4">
            <legend className="px-1 text-small font-medium">Chunking</legend>
            <div className="grid gap-4 sm:grid-cols-3">
              <NumberField id="ws-size" label="Chunk size" hint="Words per chunk" value={size} onChange={setSize} min={40} max={2000} />
              <NumberField id="ws-overlap" label="Overlap" hint="Words shared by neighbours" value={overlap} onChange={setOverlap} min={0} max={1999} />
              <NumberField id="ws-pages" label="Page limit" hint="Per website crawl" value={pages} onChange={setPages} min={1} max={2000} />
            </div>
            <p className="mt-3 text-micro text-ink-faint">
              Documents are split at headings first. Only sections longer than the chunk size are cut further, with the
              overlap carried between pieces. Keep overlap around 10 to 20 percent of the size.
            </p>
          </fieldset>

          {settingsChanged && (
            <p className="rounded border-l-2 border-ochre bg-ochre-wash px-3 py-2 text-small text-[#7A5A17]">
              Existing sources keep their current chunks until you reindex them on the Sources page.
            </p>
          )}
          {problem && name && <p className="text-small text-oxblood">{problem}</p>}

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            {mode === "settings" && workspace && workspace.id !== "ws_default" ? (
              <Button variant="danger" onClick={() => setConfirmDelete(true)} disabled={busy}>
                Delete workspace
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button variant="quiet" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              <Button onClick={save} busy={busy} disabled={problem !== null}>
                {mode === "create" ? "Create workspace" : "Save changes"}
              </Button>
            </div>
          </div>
        </div>
      </Dialog>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${workspace?.name ?? "workspace"}?`}
        description="This removes its sources, indexed chunks, conversations, insights, reports and evaluation runs. It cannot be undone."
        confirmLabel="Delete workspace"
        busy={busy}
        onConfirm={remove}
        onClose={() => setConfirmDelete(false)}
      />
    </>
  );
}
