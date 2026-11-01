import { DocumentCard } from "./components/DocumentCard.tsx";
import { UploadForm } from "./components/UploadForm.tsx";
import { useDocuments } from "./useDocuments.ts";

export function App() {
  const { documents, error, upload, clear } = useDocuments();

  return (
    <main className="app">
      <header className="app-header">
        <h1>Document Parser</h1>
        <p>Upload PDFs, pick a parser, and get per-page Markdown with a summary of each file.</p>
      </header>

      <UploadForm onUpload={upload} />

      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}

      {documents.length > 0 && (
        <section className="documents" aria-live="polite">
          <div className="documents-header">
            <h2>Documents</h2>
            <button type="button" className="ghost" onClick={clear}>
              Clear list
            </button>
          </div>
          {documents.map((document) => (
            <DocumentCard key={document.id} document={document} />
          ))}
        </section>
      )}
    </main>
  );
}
