import type { AgentRun } from "../../api";
import { asRecord, textValue } from "../../lib/runMonitor";

type ContextEntry = Record<string, unknown>;

type Props = {
  task: Record<string, unknown>;
  run: AgentRun | null;
  contextEntries: ContextEntry[];
  designReferences: ContextEntry[];
  executionParameters: Record<string, unknown>;
  referenceSnippet: string;
};

export default function TaskDetailPanels({
  task,
  run,
  contextEntries,
  designReferences,
  executionParameters,
  referenceSnippet,
}: Props) {
  const taskData = asRecord(task.task_data);
  const agentEffort = asRecord(taskData.agent_effort);

  return (
    <div className="space-y-6">
      <div className="glass p-4 border-neutral-200">
        <p className="heading-sub mb-2">Task summary</p>
        <p className="text-sm text-neutral-800 leading-relaxed">
          {textValue(task.description, referenceSnippet)}
        </p>
        <div className="mt-3 grid sm:grid-cols-3 gap-3 text-xs">
          <div className="rounded-lg border border-neutral-300 bg-paper-field p-3">
            <p className="heading-sub text-[9px]">Type</p>
            <p className="text-neutral-800 mt-1">{textValue(task.task_type, "implementation")}</p>
          </div>
          <div className="rounded-lg border border-neutral-300 bg-paper-field p-3">
            <p className="heading-sub text-[9px]">Runtime</p>
            <p className="text-neutral-800 mt-1">{textValue(run?.runtime_provider, "agent")}</p>
          </div>
          <div className="rounded-lg border border-neutral-300 bg-paper-field p-3">
            <p className="heading-sub text-[9px]">Agent effort</p>
            <p className="text-neutral-800 mt-1">{textValue(agentEffort.level, "—")}</p>
          </div>
        </div>
      </div>

      <div className="glass p-4 border-neutral-200">
        <p className="heading-sub mb-3">Context used by this task</p>
        <div className="space-y-2">
          {contextEntries.slice(0, 8).map((entry, entryIndex) => (
            <div key={`context-${entryIndex}`} className="rounded-lg border border-neutral-300 bg-paper-field p-3 text-xs">
              <p className="font-semibold text-neutral-900">
                {textValue(entry.name ?? entry.document_name, `Context ${entryIndex + 1}`)}
              </p>
              <p className="text-neutral-600">
                {textValue(entry.content_kind, "document")} / document {textValue(entry.document_id, "unknown")}
              </p>
              <p className="text-neutral-600 mt-1 leading-relaxed">{textValue(entry.text_preview, "No text preview was stored.")}</p>
            </div>
          ))}
          {contextEntries.length === 0 && (
            <p className="text-sm text-neutral-600">No task context snapshot was stored.</p>
          )}
        </div>
      </div>

      <div className="glass p-4 border-neutral-200">
        <p className="heading-sub mb-3">Design references</p>
        <div className="space-y-2">
          {designReferences.map((entry, entryIndex) => (
            <div
              key={`design-${entryIndex}`}
              className="rounded-lg border border-orange-200 bg-orange-50 p-3 text-xs text-orange-900"
            >
              <p className="font-semibold">{textValue(entry.name ?? entry.document_name, `Design reference ${entryIndex + 1}`)}</p>
              <p className="break-all mt-1">{textValue(entry.text_preview, textValue(entry.content_kind, "design asset"))}</p>
            </div>
          ))}
          {designReferences.length === 0 && (
            <p className="text-sm text-neutral-600">
              No local SVG/image/design asset was attached to this task context.
            </p>
          )}
        </div>
      </div>

      <div className="glass p-4 border-neutral-200">
        <p className="heading-sub mb-2">Execution parameters</p>
        <pre className="max-h-56 overflow-auto rounded-lg border border-neutral-300 bg-paper-bright p-3 text-[11px] text-neutral-700 whitespace-pre-wrap">
          {Object.keys(executionParameters).length > 0
            ? JSON.stringify(executionParameters, null, 2)
            : "No explicit execution parameters were stored for this task."}
        </pre>
      </div>
    </div>
  );
}
