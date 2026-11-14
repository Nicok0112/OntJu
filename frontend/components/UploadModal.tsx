"use client";

import React, { useState } from "react";
import { UploadCloud, FileText, FileCode, X, Loader2 } from "lucide-react";

interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  tenantId: string;
  rfcDefault: string;
  onSuccess: (mensaje: string) => Promise<void>;
}

export default function UploadModal({
  open,
  onClose,
  tenantId,
  rfcDefault,
  onSuccess,
}: UploadModalProps) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [rfcTitular, setRfcTitular] = useState(rfcDefault);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const esPdf = archivo?.name.toLowerCase().endsWith(".pdf");
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo) return;

    setCargando(true);
    setError(null);

    try {
      const formData = new FormData();
      let endpoint = "";

      if (esPdf) {
        formData.append("rfc_titular", rfcTitular.trim().toUpperCase());
        formData.append("archivo_pdf", archivo);
        endpoint = `${apiBase}/api/v1/despachos/${tenantId}/ingestar-pdf`;
      } else {
        formData.append("archivo", archivo);
        endpoint = `${apiBase}/api/v1/despachos/${tenantId}/ingestar-xml`;
      }

      const resp = await fetch(endpoint, { method: "POST", body: formData });
      if (!resp.ok) {
        const detalle = await resp.text();
        throw new Error(detalle || "No se pudo procesar el documento.");
      }

      await onSuccess(
        esPdf
          ? "Documento PDF analizado y reglas jurídicas recalculadas."
          : "Comprobante CFDI XML integrado al expediente."
      );
      setArchivo(null);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error inesperado al subir el archivo.");
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-base font-bold text-slate-100">Agregar evidencia al expediente</h2>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-800">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-700 bg-slate-950/60 p-6 text-center transition hover:border-indigo-500">
            {archivo ? (
              <>
                {esPdf ? (
                  <FileText className="h-9 w-9 text-amber-400" />
                ) : (
                  <FileCode className="h-9 w-9 text-indigo-400" />
                )}
                <span className="mt-2 text-sm font-semibold text-slate-100">{archivo.name}</span>
                <span className="mt-1 text-xs text-slate-400">
                  {esPdf
                    ? "Detectado: Documento jurídico / Constancia (PDF)"
                    : "Detectado: Comprobante Fiscal CFDI (XML / ZIP)"}
                </span>
              </>
            ) : (
              <>
                <UploadCloud className="h-9 w-9 text-indigo-400" />
                <span className="mt-2 text-sm font-medium text-slate-200">
                  Selecciona o arrastra un archivo XML, ZIP o PDF
                </span>
                <span className="mt-1 text-xs text-slate-400">
                  El sistema detecta automáticamente el formato
                </span>
              </>
            )}
            <input
              type="file"
              accept=".xml,.zip,.pdf"
              className="hidden"
              onChange={(e) => setArchivo(e.target.files?.[0] || null)}
            />
          </label>

          {esPdf && (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">
                RFC del contribuyente titular del documento
              </label>
              <input
                type="text"
                required
                value={rfcTitular}
                onChange={(e) => setRfcTitular(e.target.value)}
                placeholder="Ej. GOMA850412HDF"
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-rose-500/40 bg-rose-950/40 p-3 text-xs text-rose-200">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={!archivo || cargando}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {cargando && <Loader2 className="h-4 w-4 animate-spin" />}
              {cargando ? "Analizando documento..." : "Procesar y dictaminar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}