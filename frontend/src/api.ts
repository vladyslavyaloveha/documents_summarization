export type DocumentStatus = "queued" | "parsing" | "summarizing" | "done" | "failed";

export interface Page {
  number: number;
  markdown: string;
}

export interface Document {
  id: string;
  filename: string;
  parser: string;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  summary: string | null;
  summary_error: string | null;
  language: string | null;
  mixed_languages: string | null;
  created_at: string;
}

export interface DocumentDetail extends Document {
  pages: Page[];
}

export const TERMINAL_STATUSES: ReadonlySet<DocumentStatus> = new Set(["done", "failed"]);

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (HTTP ${response.status})`);
  }
  return (await response.json()) as T;
}

export function fetchParsers(): Promise<string[]> {
  return request<string[]>("/api/parsers");
}

export function uploadDocuments(files: File[], parser: string): Promise<Document[]> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("parser", parser);
  return request<Document[]>("/api/documents", { method: "POST", body: form });
}

export function fetchDocuments(ids: string[]): Promise<DocumentDetail[]> {
  return request<DocumentDetail[]>(`/api/documents?ids=${ids.join(",")}`);
}

export function statusEventsUrl(ids: string[]): string {
  return `/api/events?ids=${ids.join(",")}`;
}
