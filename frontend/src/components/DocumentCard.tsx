import { MarkdownView } from "./MarkdownView.tsx";

import type { DocumentDetail } from "../api.ts";

const STATUS_LABELS: Record<DocumentDetail["status"], string> = {
  queued: "Queued",
  parsing: "Parsing",
  summarizing: "Summarizing",
  done: "Done",
  failed: "Failed",
};

export function DocumentCard({ document }: { document: DocumentDetail }) {
  const inProgress = document.status !== "done" && document.status !== "failed";

  return (
    <article className="panel card">
      <header className="card-header">
        <div>
          <h2>{document.filename}</h2>
          <p className="meta">
            <span className="tag">{document.parser}</span>
            {document.page_count !== null && <span>{document.page_count} pages</span>}
          </p>
        </div>
        <span className={`status status-${document.status}`}>
          {inProgress && <span className="spinner" aria-hidden="true" />}
          {STATUS_LABELS[document.status]}
        </span>
      </header>

      {document.error && <p className="alert">{document.error}</p>}

      {document.status === "done" && (
        <section className="summary">
          <h3>Summary</h3>
          {document.summary ? (
            <div className="markdown">
              <MarkdownView>{document.summary}</MarkdownView>
            </div>
          ) : (
            <p className="note">{document.summary_error ?? "No summary"}</p>
          )}
        </section>
      )}

      {document.pages.length > 0 && (
        <section>
          <h3>Pages</h3>
          <div className="pages">
            {document.pages.map((page) => (
              <details key={page.number} className="page">
                <summary>
                  Page {page.number}
                  {!page.markdown.trim() && <span className="note"> · no text</span>}
                </summary>
                {page.markdown.trim() && (
                  <div className="markdown">
                    <MarkdownView>{page.markdown}</MarkdownView>
                  </div>
                )}
              </details>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
