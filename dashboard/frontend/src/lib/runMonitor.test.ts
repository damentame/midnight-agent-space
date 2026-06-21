import { describe, expect, it } from "vitest";
import type { AgentEvent, AgentRun } from "../api";
import {
  classifyTaskStatus,
  parseApiTimestamp,
  resolveBoardRun,
  taskStatusFromRunEvents,
  timelineWindow,
} from "./runMonitor";
import type { TaskTimelineEntry } from "./runMonitor";

describe("taskStatusFromRunEvents", () => {
  it("promotes TASK_STARTED to RUNNING", () => {
    const events: AgentEvent[] = [
      {
        agent_event_id: 1,
        event_type: "TASK_STARTED",
        event_payload: { task_id: 10 },
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    expect(taskStatusFromRunEvents(10, events, "QUEUED")).toBe("RUNNING");
  });

  it("keeps fallback when no events", () => {
    expect(taskStatusFromRunEvents(10, [], "PLANNED")).toBe("PLANNED");
  });
});

describe("classifyTaskStatus", () => {
  it("maps running and completed consistently", () => {
    expect(classifyTaskStatus("RUNNING")).toBe("running");
    expect(classifyTaskStatus("COMPLETED")).toBe("completed");
    expect(classifyTaskStatus("QUEUED")).toBe("queued");
  });
});

describe("parseApiTimestamp", () => {
  it("treats timezone-less API timestamps as UTC", () => {
    const withZ = parseApiTimestamp("2026-06-06T13:00:00Z");
    const bare = parseApiTimestamp("2026-06-06T13:00:00");
    expect(withZ).toBe(bare);
  });
});

describe("timelineWindow", () => {
  it("anchors now marker at current progress for active runs", () => {
    const runStart = Date.parse("2026-06-06T13:00:00Z");
    const now = runStart + 30 * 60 * 1000;
    const entries: TaskTimelineEntry[] = [
      {
        task: {},
        taskId: 1,
        key: "1",
        name: "Task",
        status: "RUNNING",
        statusKind: "running",
        progress: 55,
        agent: "Agent",
        depth: 0,
        sequenceIndex: 0,
        references: [],
        referenceSnippet: "",
        elapsed: "30m",
        startMs: runStart + 20 * 60 * 1000,
        endMs: null,
        lastEventMs: runStart + 25 * 60 * 1000,
        isActive: true,
        isStalled: false,
        issueMessage: null,
      },
    ];
    const run = {
      agent_run_id: 1,
      project_id: 5,
      status: "RUNNING",
      runtime_provider: "claude-cli",
      started_at: "2026-06-06T13:00:00",
    };
    const events = [
      {
        agent_event_id: 1,
        event_type: "RUN_STARTED",
        event_payload: {},
        created_at: "2026-06-06T13:00:00",
      },
    ];
    const window = timelineWindow(entries, run, now, events);
    expect(window.nowPercent).toBeGreaterThan(90);
    expect(window.nowPercent).toBeLessThanOrEqual(100);
  });
});

describe("resolveBoardRun", () => {
  const failedRun: AgentRun = {
    agent_run_id: 35,
    project_id: 5,
    status: "FAILED",
    runtime_provider: "cursor-agent",
  };

  it("does not pin terminal failed run when tasks are queued", () => {
    expect(resolveBoardRun([failedRun], true)).toBeUndefined();
  });

  it("shows latest run when tasks are not all queued", () => {
    expect(resolveBoardRun([failedRun], false)?.agent_run_id).toBe(35);
  });

  it("prefers active run over terminal latest", () => {
    const running: AgentRun = { ...failedRun, agent_run_id: 36, status: "RUNNING" };
    expect(resolveBoardRun([running, failedRun], false)?.agent_run_id).toBe(36);
  });
});
