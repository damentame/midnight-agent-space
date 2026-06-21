import type { DesignReadiness, FigmaImportResult, FigmaSectionSummary } from "../api";
import LoadingButton from "./LoadingButton";

type Props = {
  readiness: DesignReadiness | null;
  lastImport?: FigmaImportResult | null;
  onReimport?: () => void;
  reimporting?: boolean;
};

function WarningList({ warnings }: { warnings: Array<string | { severity?: string; message?: string }> }) {
  if (!warnings.length) return null;
  return (
    <ul className="mt-2 space-y-1 text-xs text-amber-900 list-disc pl-4">
      {warnings.map((w, i) => (
        <li key={i}>{typeof w === "string" ? w : w.message ?? JSON.stringify(w)}</li>
      ))}
    </ul>
  );
}

function SectionRow({ section }: { section: FigmaSectionSummary }) {
  return (
    <li className="flex justify-between gap-2 text-xs border border-neutral-200 rounded px-2 py-1.5">
      <span className="text-neutral-800 font-medium truncate">{section.name}</span>
      <span className="text-neutral-500 shrink-0">
        {section.node_count ?? 0} nodes · {section.has_png ? "PNG" : "no PNG"}
      </span>
    </li>
  );
}

export default function FigmaDesignStatus({ readiness, lastImport, onReimport, reimporting }: Props) {
  const sections = lastImport?.sections ?? readiness?.sections ?? [];
  const gaps = readiness?.gaps ?? [];
  const required = readiness?.required ?? false;
  const structuralReady = readiness?.structural_ready ?? true;

  if (!required && !lastImport) {
    return (
      <p className="text-xs text-neutral-500">
        No active Figma import. Import via the Figma API or upload a plugin design pack zip.
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-neutral-300 bg-paper-field p-3 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500">Design readiness</p>
          <p className="text-sm font-semibold text-neutral-900 mt-0.5">
            {structuralReady ? "Ready for execute" : "Not ready — fix gaps before execute"}
          </p>
          {readiness && (
            <p className="text-xs text-neutral-600 mt-1">
              {sections.length} section(s) · {readiness.asset_count ?? 0} asset(s) · v
              {readiness.extraction_version ?? lastImport?.extraction_version ?? "?"}
            </p>
          )}
        </div>
        {onReimport && (
          <LoadingButton
            loading={reimporting}
            loadingLabel="Re-importing…"
            disabled={reimporting}
            onClick={onReimport}
            className="px-3 py-1.5 rounded border border-orange-600 text-orange-700 text-[10px] font-bold uppercase tracking-widest hover:bg-orange-50 disabled:opacity-50"
          >
            Re-import
          </LoadingButton>
        )}
      </div>

      {lastImport?.tokens_summary && (
        <p className="text-xs text-neutral-600">
          Tokens: {lastImport.tokens_summary.colors} colors, {lastImport.tokens_summary.typography} fonts,{" "}
          {lastImport.tokens_summary.spacing} spacing
        </p>
      )}

      <WarningList warnings={lastImport?.warnings ?? gaps} />

      {gaps.length > 0 && structuralReady === false && (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-900">
          <p className="font-semibold">Blocking gaps</p>
          <ul className="mt-1 list-disc pl-4">
            {gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {sections.length > 0 && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-2">Sections</p>
          <ul className="space-y-1 max-h-40 overflow-y-auto">
            {sections.map((s) => (
              <SectionRow key={s.slug ?? s.name} section={s} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
