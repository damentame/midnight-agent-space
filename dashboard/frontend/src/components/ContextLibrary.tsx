import { useEffect, useMemo, useState } from "react";
import { api, type ProjectDocument } from "../api";

function docKind(doc: ProjectDocument): string {
  const kind = doc.content_kind;
  if (doc.document_type === "codebase_file") return "code";
  if (kind === "figma_import" || doc.document_type === "figma_import") return "figma";
  if (kind === "image") return "image";
  if (kind === "figma_design") return "design";
  if (kind === "document_asset") return "document";
  if (kind === "text") return "text";
  const mime = (doc.file_mime_type ?? "").toLowerCase();
  const ext = (doc.file_extension ?? "").toLowerCase();
  if (mime.startsWith("image/") || [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"].includes(ext)) return "image";
  if ([".fig", ".figma", ".sketch"].includes(ext)) return "design";
  if ([".pdf", ".docx"].includes(ext)) return "document";
  return "asset";
}

function formatBytes(size?: number | null): string {
  if (!size || size <= 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function ContextThumbnail({ projectId, doc }: { projectId: number; doc: ProjectDocument }) {
  const [url, setUrl] = useState<string | null>(null);
  const isImage = docKind(doc) === "image" && doc.has_file_content;

  useEffect(() => {
    if (!isImage) return;
    let active = true;
    let objectUrl: string | null = null;
    api
      .documentFileBlob(projectId, doc.document_id)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (active) setUrl(null);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [projectId, doc.document_id, isImage]);

  if (!isImage || !url) {
    return (
      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border border-neutral-300 bg-paper-bright text-[10px] font-bold uppercase tracking-widest text-neutral-500">
        {docKind(doc)}
      </div>
    );
  }

  return (
    <img
      src={url}
      alt={doc.document_name}
      className="h-14 w-14 shrink-0 rounded-md border border-neutral-300 object-cover bg-paper-bright"
    />
  );
}

type Props = {
  projectId: number;
  documents: ProjectDocument[];
  onDeleted: () => Promise<void> | void;
  disabled?: boolean;
};

export default function ContextLibrary({ projectId, documents, onDeleted, disabled }: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const selectedCount = selected.size;
  const allSelected = documents.length > 0 && selectedCount === documents.length;

  useEffect(() => {
    setSelected((prev) => {
      const valid = new Set(documents.map((doc) => doc.document_id));
      const next = new Set<number>();
      for (const id of prev) {
        if (valid.has(id)) next.add(id);
      }
      return next;
    });
  }, [documents]);

  const toggleOne = (documentId: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(documents.map((doc) => doc.document_id)));
  };

  const selectedLabels = useMemo(
    () =>
      documents
        .filter((doc) => selected.has(doc.document_id))
        .map((doc) => doc.document_name)
        .slice(0, 6),
    [documents, selected],
  );

  const runDelete = async () => {
    if (selectedCount === 0) return;
    setDeleting(true);
    setDeleteErr(null);
    try {
      await api.deleteDocuments(projectId, Array.from(selected));
      setSelected(new Set());
      setConfirmOpen(false);
      await onDeleted();
    } catch (ex: unknown) {
      setDeleteErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="glass p-5 border-neutral-200">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <p className="heading-sub">Context library</p>
        <div className="flex flex-wrap items-center gap-2">
          {documents.length > 0 && (
            <button
              type="button"
              disabled={disabled}
              onClick={toggleAll}
              className="rounded-md border border-neutral-300 bg-paper-field px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-neutral-600 hover:border-orange-300 disabled:opacity-50"
            >
              {allSelected ? "Clear selection" : "Select all"}
            </button>
          )}
          <button
            type="button"
            disabled={disabled || selectedCount === 0}
            onClick={() => {
              setDeleteErr(null);
              setConfirmOpen(true);
            }}
            className="rounded-md border border-neutral-400 bg-paper-field px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-neutral-800 hover:border-orange-400 disabled:opacity-50"
          >
            Delete selected ({selectedCount})
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {documents.map((doc) => {
          const checked = selected.has(doc.document_id);
          const instructions = doc.user_instructions?.trim();
          const preview =
            doc.raw_text_preview?.trim() ||
            doc.content_summary?.trim() ||
            (doc.has_file_content ? "Binary file stored for agent context." : "Ready for serialization.");
          return (
            <label
              key={doc.document_id}
              className={`flex gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                checked ? "border-orange-400 bg-orange-50/60" : "border-neutral-300 bg-paper-field"
              }`}
            >
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 shrink-0 accent-orange-600"
                checked={checked}
                disabled={disabled}
                onChange={() => toggleOne(doc.document_id)}
              />
              <ContextThumbnail projectId={projectId} doc={doc} />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-bold text-neutral-900 text-sm break-all">{doc.document_name}</p>
                  <span className="shrink-0 text-[10px] font-bold uppercase tracking-widest text-neutral-500">
                    {docKind(doc)}
                  </span>
                </div>
                {instructions && (
                  <p className="text-xs text-neutral-800 mt-1">
                    <span className="font-bold uppercase tracking-widest text-[10px] text-neutral-500">Notes · </span>
                    {instructions}
                  </p>
                )}
                <p className="text-xs text-neutral-600 mt-1 line-clamp-3">{preview}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-widest text-neutral-500">
                  {formatBytes(doc.file_size_bytes) && <span>{formatBytes(doc.file_size_bytes)}</span>}
                  {doc.serialization_status && <span>{doc.serialization_status}</span>}
                </div>
              </div>
            </label>
          );
        })}
        {documents.length === 0 && <p className="text-sm text-neutral-600">No context yet. Upload files or add text context.</p>}
      </div>

      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/40 p-4">
          <div className="w-full max-w-md rounded-lg border border-neutral-300 bg-paper-bright p-5 shadow-xl">
            <p className="heading-sub text-orange-700">Delete context</p>
            <p className="text-sm text-neutral-700 mt-2">
              Remove {selectedCount} selected item{selectedCount === 1 ? "" : "s"} from this project? This cannot be undone.
            </p>
            {selectedLabels.length > 0 && (
              <ul className="mt-3 max-h-32 overflow-y-auto text-xs text-neutral-600 list-disc pl-5 space-y-1">
                {selectedLabels.map((name) => (
                  <li key={name}>{name}</li>
                ))}
                {selectedCount > selectedLabels.length && <li>…and {selectedCount - selectedLabels.length} more</li>}
              </ul>
            )}
            {deleteErr && <p className="mt-3 text-xs text-neutral-800">{deleteErr}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={deleting}
                onClick={() => setConfirmOpen(false)}
                className="rounded-lg border border-neutral-300 px-4 py-2 text-xs font-bold uppercase tracking-widest text-neutral-700"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={runDelete}
                className="rounded-lg bg-neutral-900 px-4 py-2 text-xs font-bold uppercase tracking-widest text-white hover:bg-neutral-700 disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
