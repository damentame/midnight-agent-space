import type { TemporalActivity } from "../api";

function dotClass(status: string): string {
  switch (status) {
    case "running":
      return "bg-orange-500 dot-glow-orange animate-pulse-slow scale-110";
    case "completed":
      return "bg-neutral-300";
    case "failed":
      return "bg-neutral-900 border-2 border-white";
    case "timed_out":
      return "bg-neutral-500 border border-neutral-300";
    case "scheduled":
    default:
      return "bg-neutral-400 opacity-80";
  }
}

type Props = {
  activities: TemporalActivity[];
  selectedId: number | null;
  onSelect: (a: TemporalActivity) => void;
};

/**
 * One dot per Temporal activity; click for detail panel.
 */
export default function ActivityDots({ activities, selectedId, onSelect }: Props) {
  return (
    <div className="rounded-xl overflow-hidden border border-neutral-300/90 bg-paper-lift/75">
      <div className="p-6 min-h-[140px] flex flex-wrap gap-4 content-start items-center justify-center border-b border-neutral-200">
        {activities.map((a, i) => {
          const sel = selectedId === a.scheduled_event_id;
          return (
            <button
              key={a.scheduled_event_id}
              type="button"
              title={`${a.activity_name} (${a.status})`}
              onClick={() => onSelect(a)}
              className={`w-4 h-4 rounded-full transition-transform hover:scale-125 animate-float ${dotClass(a.status)} ${
                sel ? "ring-2 ring-orange-500 ring-offset-2 ring-offset-paper" : ""
              }`}
              style={{ animationDelay: `${(i % 7) * 0.2}s` }}
            />
          );
        })}
      </div>
      <div className="px-4 pb-3 pt-2">
        <p className="heading-sub mb-2">Activity list</p>
        <ul className="space-y-1.5 text-xs text-neutral-600 max-h-40 overflow-y-auto">
          {activities.map((a) => (
            <li key={a.scheduled_event_id}>
              <button
                type="button"
                onClick={() => onSelect(a)}
                className={`text-left w-full hover:text-orange-600 ${selectedId === a.scheduled_event_id ? "text-orange-600" : ""}`}
              >
                <span className="text-neutral-500 font-mono text-[10px] mr-2">{a.scheduled_event_id}</span>
                <span className="text-neutral-800">{a.activity_name}</span>
                <span className="text-neutral-500 ml-2">({a.status})</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
