const STORAGE_KEY = "mas.figmaApiToken";

export function loadFigmaApiToken(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveFigmaApiToken(token: string): void {
  try {
    const trimmed = token.trim();
    if (trimmed) localStorage.setItem(STORAGE_KEY, trimmed);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore quota / private mode
  }
}

export function maskFigmaToken(token: string): string {
  const t = token.trim();
  if (t.length <= 8) return t ? "••••••••" : "";
  return `${t.slice(0, 4)}…${t.slice(-4)}`;
}
