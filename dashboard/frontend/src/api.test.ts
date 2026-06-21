import { describe, expect, it } from "vitest";

describe("api client error messages", () => {
  it("documents timeout guidance in fetch layer", () => {
    const path = "/api/projects/5/tasks";
    const message = `Request timed out (${path}). Check that the API is running on port 8001 and Postgres is reachable.`;
    expect(message).toContain("8001");
    expect(message).toContain(path);
  });

  it("documents 404 refresh hint", () => {
    const path = "/api/projects/5/refresh";
    const message = `Not found (${path}). If you recently updated the dashboard, restart the API on port 8001.`;
    expect(message).toContain("restart the API");
  });
});
