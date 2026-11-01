import { useCallback, useEffect, useState } from "react";

import {
  type DocumentDetail,
  TERMINAL_STATUSES,
  fetchDocuments,
  statusEventsUrl,
  uploadDocuments,
} from "./api.ts";

const STORAGE_KEY = "docparser.documentIds";
const POLL_INTERVAL_MS = 2000;

function readStoredIds(): string[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(stored) ? stored.filter((id) => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function useDocuments() {
  const [ids, setIds] = useState<string[]>(readStoredIds);
  const [details, setDetails] = useState<Record<string, DocumentDetail>>({});
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (targetIds: string[]) => {
    if (targetIds.length === 0) return;
    try {
      const fresh = await fetchDocuments(targetIds);
      setDetails((previous) => ({
        ...previous,
        ...Object.fromEntries(fresh.map((document) => [document.id, document])),
      }));
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : String(refreshError));
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  }, [ids]);

  useEffect(() => {
    void refresh(readStoredIds());
  }, [refresh]);

  const activeIds = ids.filter((id) => !TERMINAL_STATUSES.has(details[id]?.status ?? "queued"));
  const activeKey = activeIds.join(",");

  useEffect(() => {
    if (!activeKey) return;
    const watched = activeKey.split(",");
    let pollTimer: number | undefined;
    const source = new EventSource(statusEventsUrl(watched));
    source.addEventListener("status", (event) => {
      const { id } = JSON.parse((event as MessageEvent<string>).data) as { id: string };
      void refresh([id]);
    });
    source.onerror = () => {
      source.close();
      pollTimer = window.setInterval(() => void refresh(watched), POLL_INTERVAL_MS);
    };
    return () => {
      source.close();
      window.clearInterval(pollTimer);
    };
  }, [activeKey, refresh]);

  const upload = useCallback(async (files: File[], parser: string) => {
    setError(null);
    const created = await uploadDocuments(files, parser);
    setDetails((previous) => ({
      ...previous,
      ...Object.fromEntries(created.map((document) => [document.id, { ...document, pages: [] }])),
    }));
    setIds((previous) => [...created.map((document) => document.id), ...previous]);
  }, []);

  const clear = useCallback(() => {
    setIds([]);
    setDetails({});
  }, []);

  const documents = ids.flatMap((id) => (details[id] ? [details[id]] : []));
  return { documents, error, upload, clear };
}
