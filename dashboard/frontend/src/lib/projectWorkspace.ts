import { api } from "../api";

export function slugifyProjectName(name: string): string {
  return (
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "project"
  );
}

export async function waitForCodebaseSerialization(
  projectId: number,
  onProgress?: (message: string, percent: number) => void,
): Promise<void> {
  for (;;) {
    const status = await api.codebaseSerializeStatus(projectId);
    onProgress?.(status.message, status.percent ?? 0);
    if (status.status === "completed") return;
    if (status.status === "failed") {
      throw new Error(status.error || status.message || "Codebase serialization failed");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 600));
  }
}
