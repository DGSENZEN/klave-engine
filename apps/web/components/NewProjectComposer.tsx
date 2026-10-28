"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { CaretDown, CircleNotch, CloudArrowUp, FileText, Plus, X } from "@phosphor-icons/react";
import { previewDisciplinas, type DisciplinePreview } from "@/lib/api";
import { DEFAULT_MAX_FILE_BYTES, formatMegabytes, type DrawingUploadLimits } from "@/lib/uploads";
import { Badge, Button, Callout, Field, IconButton, Input } from "@/components/ui";

const FORM_ID = "nuevo-proyecto";
/** The drop zone / add button, focused when the composer is opened from the header. */
export const COMPOSER_PICK_ID = "nuevo-proyecto-elegir";

/** "PLANTA_CIMENTACION-01.dwg" → "Planta Cimentacion 01". */
function suggestName(file: File): string {
  const stem = file.name.replace(/\.(dwg|dxf)$/i, "").replace(/[_\-]+/g, " ").trim().toLowerCase();
  return stem.replace(/\s+/g, " ").replace(/(^|\s)\S/g, (c) => c.toUpperCase()).slice(0, 80);
}

/**
 * New project, inline above the list: the sheets of one obra (add, remove,
 * see what each one feeds), a name and a client. The home owns the file list
 * so a drop anywhere on the page lands here too.
 */
export function NewProjectComposer({
  title,
  files,
  limits,
  busy,
  error,
  onPick,
  onRemove,
  onCreate,
  onClose,
}: {
  title: string;
  files: File[];
  limits?: DrawingUploadLimits;
  busy: boolean;
  error: string | null;
  onPick: () => void;
  onRemove: (index: number) => void;
  onCreate: (name: string, client: string) => void;
  /** Absent when there is nothing else to show (first project). */
  onClose?: () => void;
}) {
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [client, setClient] = useState("");
  const [openFile, setOpenFile] = useState<string | null>(null);
  // Qué datos jala cada hoja: el ruteo real del motor, consultado por
  // nombre. Si la consulta falla, la lista simple sigue sirviendo.
  const [previews, setPreviews] = useState<Map<string, DisciplinePreview>>(new Map());
  const asked = useRef(new Set<string>());

  const fileNames = files.map((f) => f.name).join("\n");
  useEffect(() => {
    const missing = fileNames.split("\n").filter((n) => n && !asked.current.has(n));
    if (!missing.length) return;
    missing.forEach((n) => asked.current.add(n));
    let active = true;
    previewDisciplinas(missing)
      .then((rows) => {
        if (!active) return;
        setPreviews((current) => {
          const next = new Map(current);
          rows.forEach((row) => next.set(row.filename, row));
          return next;
        });
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [fileNames]);

  const shownName = nameEdited ? name : files[0] ? suggestName(files[0]) : "";
  const totalBytes = files.reduce((sum, f) => sum + f.size, 0);
  const maxFiles = limits?.max_files ?? 40;
  const maxFile = limits?.max_file_bytes ?? DEFAULT_MAX_FILE_BYTES;
  const ready = files.length > 0 && shownName.trim().length >= 2;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!busy && ready) onCreate(shownName.trim(), client.trim());
  }

  return (
    <section
      aria-labelledby="nuevo-proyecto-titulo"
      className="card rise-in mb-6 p-5"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 id="nuevo-proyecto-titulo" className="text-[0.95rem] font-semibold">
          {title}
        </h2>
        {onClose && (
          <IconButton aria-label="Cerrar nuevo proyecto" onClick={onClose} disabled={busy}>
            <X size={16} weight="bold" />
          </IconButton>
        )}
      </div>

      {files.length === 0 ? (
        <button
          type="button"
          id={COMPOSER_PICK_ID}
          onClick={onPick}
          className="group flex w-full flex-col items-center gap-2 rounded-lg border border-dashed border-border-strong px-6 py-10 text-center transition-colors hover:border-accent hover:bg-accent-soft"
        >
          <CloudArrowUp size={28} weight="duotone" className="text-muted transition-colors group-hover:text-accent" />
          <span className="text-sm font-medium">Elige o arrastra las hojas de una obra</span>
          <span className="text-xs text-muted">
            DWG o DXF · hasta {maxFiles} hojas · {formatMegabytes(maxFile)} por archivo
          </span>
        </button>
      ) : (
        <div>
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <span className="tabular text-sm text-muted">
              {files.length === 1 ? "1 hoja" : `${files.length} hojas`} · {formatMegabytes(totalBytes)}
            </span>
            <button
              type="button"
              id={COMPOSER_PICK_ID}
              onClick={onPick}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded text-sm font-medium text-accent hover:underline disabled:opacity-50"
            >
              <Plus size={13} weight="bold" /> Agregar hojas
            </button>
          </div>
          <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border">
            {files.map((file, index) => {
              const preview = previews.get(file.name);
              const open = openFile === file.name;
              return (
                <li key={`${index}-${file.name}`} className="text-sm">
                  <div className="flex items-center gap-1 pr-1.5">
                    <button
                      type="button"
                      onClick={() => setOpenFile(open ? null : file.name)}
                      aria-expanded={open}
                      className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-2"
                    >
                      <FileText size={14} className="shrink-0 text-muted" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">{file.name}</span>
                        {/* On phones the discipline moves under the name so the name keeps the row. */}
                        {preview && (
                          <span className={`block text-xs sm:hidden ${preview.structural ? "text-accent" : "text-muted"}`}>
                            {preview.label}
                          </span>
                        )}
                      </span>
                      <span className="tabular hidden shrink-0 text-xs text-faint sm:inline">
                        {formatMegabytes(file.size)}
                      </span>
                      {preview && (
                        <span className="hidden sm:inline-flex">
                          <Badge tone={preview.structural ? "accent" : "default"}>{preview.label}</Badge>
                        </span>
                      )}
                      <CaretDown
                        size={11}
                        className={`shrink-0 text-faint transition-transform ${open ? "" : "-rotate-90"}`}
                      />
                    </button>
                    <IconButton
                      aria-label={`Quitar ${file.name}`}
                      onClick={() => onRemove(index)}
                      disabled={busy}
                    >
                      <X size={13} weight="bold" />
                    </IconButton>
                  </div>
                  {open && (
                    <ul className="mb-2 ml-9 space-y-0.5 border-l border-border pl-3 text-xs text-muted">
                      {(preview?.jala ?? ["Consultando qué datos jala…"]).map((dato) => (
                        <li key={dato}>{dato}</li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <form id={FORM_ID} onSubmit={submit} className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Nombre del proyecto" htmlFor="project-name">
          <Input
            id="project-name"
            value={shownName}
            onChange={(e) => {
              setName(e.target.value);
              setNameEdited(true);
            }}
            placeholder="p. ej. Torre Marina 4"
            maxLength={120}
            required
            className="h-10 w-full"
          />
        </Field>
        <Field
          label="Cliente"
          htmlFor="project-client"
          aside={<span className="text-xs text-faint">Opcional</span>}
        >
          <Input
            id="project-client"
            value={client}
            onChange={(e) => setClient(e.target.value)}
            placeholder="Constructora, dependencia, particular…"
            maxLength={120}
            className="h-10 w-full"
          />
        </Field>
      </form>

      {error && (
        <div role="alert" className="mt-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">Las hojas se procesan juntas como una sola obra.</p>
        <div className="flex items-center gap-2">
          {onClose && (
            <Button variant="ghost" size="lg" onClick={onClose} disabled={busy}>
              Cancelar
            </Button>
          )}
          <Button
            type="submit"
            form={FORM_ID}
            variant="primary"
            size="lg"
            disabled={busy || !ready}
            aria-busy={busy}
          >
            {busy ? (
              <>
                <CircleNotch size={15} className="animate-spin" /> Subiendo…
              </>
            ) : (
              "Crear y procesar"
            )}
          </Button>
        </div>
      </div>
    </section>
  );
}
