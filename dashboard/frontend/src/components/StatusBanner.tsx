type BannerSeverity = "error" | "warning" | "info";

export type StatusBannerItem = {
  id: string;
  message: string;
  severity?: BannerSeverity;
  hint?: string;
};

type Props = {
  items: StatusBannerItem[];
  onDismiss?: (id: string) => void;
};

const STYLES: Record<BannerSeverity, string> = {
  error: "border-red-300 bg-red-50 text-red-900",
  warning: "border-orange-300 bg-orange-50 text-orange-900",
  info: "border-neutral-300 bg-paper-field text-neutral-800",
};

export default function StatusBanner({ items, onDismiss }: Props) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      {items.map((item) => {
        const severity = item.severity ?? "error";
        return (
          <div
            key={item.id}
            className={`flex items-start justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${STYLES[severity]}`}
          >
            <div className="min-w-0">
              <p>{item.message}</p>
              {item.hint && <p className="mt-1 text-xs opacity-80">{item.hint}</p>}
            </div>
            {onDismiss && (
              <button
                type="button"
                onClick={() => onDismiss(item.id)}
                className="shrink-0 text-xs font-semibold uppercase tracking-wide opacity-70 hover:opacity-100"
              >
                Dismiss
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
