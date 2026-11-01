import { type DragEvent, type FormEvent, useEffect, useRef, useState } from "react";

import { fetchParsers } from "../api.ts";

interface UploadFormProps {
  onUpload: (files: File[], parser: string) => Promise<void>;
}

const MAX_FILES = 5;
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const FALLBACK_PARSERS = ["pypdf"];

const PARSER_HINTS: Record<string, string> = {
  pypdf: "Fast text extraction",
  gemini: "LLM text extraction",
};

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadForm({ onUpload }: UploadFormProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [parsers, setParsers] = useState<string[] | null>(null);
  const [parser, setParser] = useState("pypdf");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parsersFailed, setParsersFailed] = useState(false);

  function loadParsers() {
    setParsersFailed(false);
    fetchParsers()
      .then(setParsers)
      .catch(() => {
        setParsers(FALLBACK_PARSERS);
        setParsersFailed(true);
      });
  }

  useEffect(loadParsers, []);

  function addFiles(added: File[]) {
    const known = new Set(files.map((file) => `${file.name}:${file.size}`));
    const unique = added.filter((file) => !known.has(`${file.name}:${file.size}`));
    const fresh = unique.filter((file) => file.size <= MAX_FILE_BYTES);
    const tooLarge = unique.length - fresh.length;
    const accepted = fresh.slice(0, Math.max(0, MAX_FILES - files.length));
    setFiles([...files, ...accepted]);
    const skipped = fresh.length - accepted.length;
    const problems = [
      tooLarge > 0 && `${tooLarge} over ${formatSize(MAX_FILE_BYTES)}`,
      skipped > 0 && `${skipped} over the ${MAX_FILES} files limit`,
    ].filter(Boolean);
    setError(problems.length > 0 ? `Not added: ${problems.join(", ")}` : null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function removeFile(index: number) {
    setFiles((previous) => previous.filter((_, position) => position !== index));
    setError(null);
  }

  function clearFiles() {
    setFiles([]);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (files.length === 0) return;
    setPending(true);
    setError(null);
    try {
      await onUpload(files, parser);
      clearFiles();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : String(uploadError));
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="panel upload" onSubmit={handleSubmit}>
      <label
        className={`dropzone${dragging ? " dropzone-active" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept="application/pdf,.pdf"
          multiple
          disabled={files.length >= MAX_FILES || pending}
          onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
        />
        <span className="dropzone-title">
          {files.length >= MAX_FILES
            ? "File limit reached"
            : "Drop PDF files here or click to choose"}
        </span>
        <span className="dropzone-hint">
          Up to {MAX_FILES} files, {formatSize(MAX_FILE_BYTES)} each
          {files.length > 0 && ` · ${files.length}/${MAX_FILES} selected`}
        </span>
      </label>

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.size}`}>
              <span className="file-name">{file.name}</span>
              <span className="file-size">{formatSize(file.size)}</span>
              <button
                type="button"
                className="remove"
                aria-label={`Remove ${file.name}`}
                onClick={() => removeFile(index)}
                disabled={pending}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <fieldset className="parser-choice">
        <legend>Parser</legend>
        <div className="segmented" aria-busy={parsers === null}>
          {(parsers ?? []).map((name) => (
            <label key={name} className={parser === name ? "selected" : undefined}>
              <input
                type="radio"
                name="parser"
                value={name}
                checked={parser === name}
                onChange={() => setParser(name)}
              />
              <span className="option-name">{name}</span>
              <span className="option-hint">{PARSER_HINTS[name] ?? ""}</span>
            </label>
          ))}
        </div>
        <p className="field-hint">Summary always goes through LLM.</p>
        {parsersFailed && (
          <p className="notice">
            Could not load the parser list, so only pypdf is shown.{" "}
            <button type="button" className="link" onClick={loadParsers}>
              Retry
            </button>
          </p>
        )}
      </fieldset>

      <div className="actions">
        {files.length > 0 && (
          <button type="button" className="ghost" onClick={clearFiles} disabled={pending}>
            Clear selection
          </button>
        )}
        <button type="submit" className="primary" disabled={pending || files.length === 0}>
          {pending
            ? "Uploading…"
            : files.length > 1
              ? `Upload ${files.length} files`
              : "Upload"}
        </button>
      </div>

      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
    </form>
  );
}
