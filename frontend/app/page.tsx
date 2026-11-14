"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Edge,
  MarkerType,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Scale,
  Plus,
  Sparkles,
  RefreshCw,
  FileDown,
  ShieldAlert,
  CheckCircle2,
  BookOpen,
  ChevronDown,
  Filter,
} from "lucide-react";

import EntityNode, { type EntityFlowNode } from "@/components/EntityNode";
import UploadModal from "@/components/UploadModal";
import SimulatorModal from "@/components/SimulatorModal";
import {
  limpiarPropiedad,
  traducirEvento,
  traducirRegla,
  formatearValor,
} from "@/lib/humanizer";

const nodeTypes = { entityNode: EntityNode };

/** Distribuye los nodos en columnas de izquierda a derecha según sus conexiones */
function acomodarHorizontalmente(nodes: Node[], edges: Edge[]): Node[] {
  const tieneEntrada = new Set(edges.map((e) => e.target));
  const raices = nodes.filter((n) => !tieneEntrada.has(n.id));
  const nivelPorId = new Map<string, number>();

  raices.forEach((r) => nivelPorId.set(r.id, 0));
  for (let i = 0; i < nodes.length; i++) {
    edges.forEach((e) => {
      const nivelOrigen = nivelPorId.get(e.source) ?? 0;
      const nivelActual = nivelPorId.get(e.target) ?? 0;
      if (nivelOrigen + 1 > nivelActual) {
        nivelPorId.set(e.target, nivelOrigen + 1);
      }
    });
  }

  const conteoPorColumna = new Map<number, number>();
  return nodes.map((n) => {
    const col = nivelPorId.get(n.id) ?? 0;
    const fila = conteoPorColumna.get(col) ?? 0;
    conteoPorColumna.set(col, fila + 1);

    return {
      ...n,
      position: { x: 60 + col * 380, y: 60 + fila * 190 },
    };
  });
}

export default function LexEngineDashboard() {
  const [tenantId, setTenantId] = useState("despacho_cdmx");
  const [rfcActivo, setRfcActivo] = useState("GOMA850412HDF");
  const [ejercicio, setEjercicio] = useState("2025");
  const [soloExpedienteActivo, setSoloExpedienteActivo] = useState(true);

  const [rawNodes, setRawNodes] = useState<Node<EntityNodeData>[]>([]);
  const [rawEdges, setRawEdges] = useState<Edge[]>([]);
  const [dictamen, setDictamen] = useState<any>(null);
  const [nodoSeleccionado, setNodoSeleccionado] = useState<Node<EntityNodeData> | null>(null);

  const [modalUpload, setModalUpload] = useState(false);
  const [modalSimulador, setModalSimulador] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const cargarExpediente = useCallback(async () => {
    try {
      const [resGrafo, resEval] = await Promise.all([
        fetch(`${apiBase}/api/v1/despachos/${tenantId}/grafo`),
        fetch(`${apiBase}/api/v1/despachos/${tenantId}/evaluar`, { method: "POST" }),
      ]);

      if (resGrafo.ok) {
        const grafo = await resGrafo.json();
        const nodosFormateados: EntityFlowNode[] = (grafo.nodes || []).map((n: any) => ({
          id: n.id,
          type: "entityNode",
          position: { x: 0, y: 0 },
          data: {
            label: n.data?.label || n.id,
            atributos: n.data?.atributos || {},
          },
        }));

        const aristasFormateadas: Edge[] = (grafo.edges || []).map((e: any) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          label: limpiarPropiedad(e.label || ""),
          animated: true,
          style: { stroke: "#818cf8", strokeWidth: 2 },
          labelStyle: { fill: "#e2e8f0", fontWeight: 600, fontSize: 12 },
          labelBgStyle: { fill: "#0f172a", fillOpacity: 0.9 },
          markerEnd: { type: MarkerType.ArrowClosed, color: "#818cf8" },
        }));

        setRawNodes(nodosFormateados);
        setRawEdges(aristasFormateadas);
      }

      if (resEval.ok) {
        setDictamen(await resEval.json());
      }
    } catch (err) {
      console.error("Error cargando expediente:", err);
    }
  }, [apiBase, tenantId]);

  useEffect(() => {
    cargarExpediente();
  }, [cargarExpediente]);

  // Filtra los nodos conectados al RFC activo para evitar ruido visual de otros casos
  const { nodes, edges } = useMemo(() => {
    if (!soloExpedienteActivo || !rfcActivo.trim()) {
      return { nodes: acomodarHorizontalmente(rawNodes, rawEdges), edges: rawEdges };
    }

    const objetivo = rfcActivo.trim().toLowerCase();
    const relacionados = new Set<string>();

    rawNodes.forEach((n) => {
      if (n.id.toLowerCase().includes(objetivo)) relacionados.add(n.id);
    });

    rawEdges.forEach((e) => {
      if (relacionados.has(e.source)) relacionados.add(e.target);
      if (relacionados.has(e.target)) relacionados.add(e.source);
    });

    const filtradosN =
      relacionados.size > 0 ? rawNodes.filter((n) => relacionados.has(n.id)) : rawNodes;
    const filtradosE =
      relacionados.size > 0
        ? rawEdges.filter((e) => relacionados.has(e.source) && relacionados.has(e.target))
        : rawEdges;

    return {
      nodes: acomodarHorizontalmente(filtradosN, filtradosE),
      edges: filtradosE,
    };
  }, [rawNodes, rawEdges, soloExpedienteActivo, rfcActivo]);

  const eventosCriticos: string[] = dictamen?.eventos_disparados || [];
  const reglasAplicadas: any[] = dictamen?.reglas_aplicadas || [];
  const reglasDerrotadas: string[] = dictamen?.reglas_derrotadas || [];
  const tieneRiesgo = eventosCriticos.some(
    (ev) => ev.startsWith("ALERTA_") || ev.startsWith("BLOQUEAR_")
  );

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-100">
      {/* Barra superior con jerarquía clara */}
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-slate-800 bg-slate-900/90 px-6 py-3">
        <div className="flex items-center gap-3 self-center">
          <div className="rounded-xl bg-indigo-600 p-2.5 shadow-lg shadow-indigo-950">
            <Scale className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white">LexEngine MX</h1>
            <p className="text-xs text-slate-400">Dictaminación Jurídica y Fiscal Asistida</p>
          </div>
        </div>

        {/* Filtros con etiquetas explícitas */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-[11px] font-medium text-slate-400">Despacho</label>
            <input
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              className="w-36 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium text-slate-400">
              Expediente / RFC
            </label>
            <input
              value={rfcActivo}
              onChange={(e) => setRfcActivo(e.target.value)}
              className="w-40 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs font-semibold uppercase text-slate-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium text-slate-400">Ejercicio</label>
            <input
              type="number"
              value={ejercicio}
              onChange={(e) => setEjercicio(e.target.value)}
              className="w-20 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-100"
            />
          </div>
        </div>

        {/* Acciones principales */}
        <div className="flex items-center gap-2 self-center">
          <button
            onClick={() => setModalUpload(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-md hover:bg-indigo-500"
          >
            <Plus className="h-4 w-4" /> Subir Documentos
          </button>

          <button
            onClick={() => setModalSimulador(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
          >
            <Sparkles className="h-4 w-4 text-amber-400" /> Simular Solución
          </button>

          <a
            href={`${apiBase}/api/v1/despachos/${tenantId}/reporte-pdf`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-700/60 bg-emerald-950/40 px-3.5 py-2 text-xs font-medium text-emerald-300 hover:bg-emerald-900/50"
          >
            <FileDown className="h-4 w-4" /> Exportar Dictamen
          </a>

          <button
            onClick={async () => {
              await fetch(`${apiBase}/api/v1/dof/vigilar`, { method: "POST" });
              setBanner("Vigilancia del Diario Oficial de la Federación actualizada.");
            }}
            title="Sincronizar reformas del DOF"
            className="rounded-lg border border-slate-700 bg-slate-800 p-2 text-slate-300 hover:bg-slate-700"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* Banner de confirmación */}
      {banner && (
        <div className="flex items-center justify-between border-b border-indigo-500/30 bg-indigo-950/60 px-6 py-2 text-xs text-indigo-200">
          <span>{banner}</span>
          <button onClick={() => setBanner(null)} className="font-semibold hover:underline">
            Cerrar
          </button>
        </div>
      )}

      {/* Área de trabajo principal */}
      <div className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-12">
        {/* Mapa visual del expediente (8 columnas) */}
        <main className="relative lg:col-span-8">
          <div className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-2 text-xs shadow-lg">
            <Filter className="h-3.5 w-3.5 text-indigo-400" />
            <label className="flex cursor-pointer items-center gap-2 text-slate-200">
              <input
                type="checkbox"
                checked={soloExpedienteActivo}
                onChange={(e) => setSoloExpedienteActivo(e.target.checked)}
                className="rounded border-slate-600 accent-indigo-600"
              />
              Mostrar solo entidades de <strong>{rfcActivo.toUpperCase()}</strong>
            </label>
          </div>

          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={(_, node) => setNodoSeleccionado(node)}
            fitView
          >
            <Background color="#1e293b" gap={20} />
            <Controls />
          </ReactFlow>
        </main>

        {/* Panel Derecho: Nivel 1 Ejecutivo + Nivel 2 Auditoría (4 columnas) */}
        <aside className="flex flex-col gap-4 overflow-y-auto border-l border-slate-800 bg-slate-900/60 p-5 lg:col-span-4">
          {/* NIVEL 1: DICTAMEN EJECUTIVO EN ESPAÑOL */}
          <section
            className={`rounded-2xl border p-4 shadow-lg ${
              tieneRiesgo
                ? "border-rose-500/50 bg-rose-950/25"
                : "border-emerald-500/40 bg-emerald-950/20"
            }`}
          >
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider">
              {tieneRiesgo ? (
                <>
                  <ShieldAlert className="h-4 w-4 text-rose-400" />
                  <span className="text-rose-300">Dictamen Ejecutivo: Riesgo / Exclusión</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span className="text-emerald-300">Dictamen Ejecutivo: Cumplimiento</span>
                </>
              )}
            </div>

            {eventosCriticos.length > 0 ? (
              <div className="mt-3 space-y-3">
                {eventosCriticos.map((ev) => {
                  const info = traducirEvento(ev);
                  return (
                    <div key={ev} className="space-y-1.5">
                      <h2 className="text-sm font-bold text-white">{info.titulo}</h2>
                      <p className="text-xs leading-relaxed text-slate-300">
                        {info.accionSugerida}
                      </p>
                    </div>
                  );
                })}

                <button
                  onClick={() => setModalSimulador(true)}
                  className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-rose-500"
                >
                  <Sparkles className="h-4 w-4" /> ¿Cómo resolver esta exclusión?
                </button>
              </div>
            ) : (
              <p className="mt-2 text-xs leading-relaxed text-slate-300">
                No se detectaron causales de exclusión ni alertas críticas para el expediente{" "}
                <strong>{rfcActivo.toUpperCase()}</strong>.
              </p>
            )}
          </section>

          {/* FUNDAMENTO LEGAL CLARO */}
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-300">
              <BookOpen className="h-4 w-4" />
              <span>Fundamento Legal Aplicado ({reglasAplicadas.length})</span>
            </div>

            <div className="mt-3 space-y-2.5">
              {reglasAplicadas.map((regla, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-slate-800 bg-slate-950/70 p-3 text-xs"
                >
                  <span className="inline-block rounded bg-indigo-500/20 px-2 py-0.5 text-[11px] font-semibold text-indigo-300">
                    {regla.ordenamiento} Art. {regla.articulo}
                    {regla.fraccion ? ` Fracc. ${regla.fraccion}` : ""}
                  </span>
                  <p className="mt-1.5 font-medium text-slate-100">{regla.descripcion}</p>
                </div>
              ))}
              {reglasAplicadas.length === 0 && (
                <p className="text-xs text-slate-400">
                  Sube un documento XML o PDF para evaluar las normas aplicables.
                </p>
              )}
            </div>
          </section>

          {/* NIVEL 2: DIVULGACIÓN PROGRESIVA (AUDITORÍA TÉCNICA ASP / RDF) */}
          <details className="group rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <summary className="flex cursor-pointer list-none items-center justify-between text-xs font-semibold text-slate-400 hover:text-slate-200">
              <span>Ver trazabilidad técnica (Reglas ASP e Inspector RDF)</span>
              <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
            </summary>

            <div className="mt-3 space-y-3 border-t border-slate-800 pt-3 text-xs">
              {reglasDerrotadas.length > 0 && (
                <div>
                  <span className="font-semibold text-amber-300">
                    Reglas generales derrotadas por excepción:
                  </span>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-slate-300">
                    {reglasDerrotadas.map((r) => (
                      <li key={r}>{traducirRegla(r)}</li>
                    ))}
                  </ul>
                </div>
              )}

              {nodoSeleccionado && (
                <div>
                  <span className="font-semibold text-indigo-300">
                    Propiedades de {nodoSeleccionado.id}:
                  </span>
                  <div className="mt-1.5 space-y-1">
                    {Object.entries(nodoSeleccionado.data.atributos || {}).map(([k, v]) => (
                      <div
                        key={k}
                        className="flex justify-between rounded bg-slate-950 px-2 py-1 font-mono text-[11px]"
                      >
                        <span className="text-slate-400">{k}</span>
                        <span className="text-emerald-300">
                          {formatearValor(v.valor)} {v.inferido ? "(inferido)" : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </details>
        </aside>
      </div>

      {/* Modales */}
      <UploadModal
        open={modalUpload}
        onClose={() => setModalUpload(false)}
        tenantId={tenantId}
        rfcDefault={rfcActivo}
        onSuccess={async (msg) => {
          setBanner(msg);
          await cargarExpediente();
        }}
      />

      {modalSimulador && (
        <SimulatorModal
          open={modalSimulador}
          onClose={() => setModalSimulador(false)}
          tenantId={tenantId}
          onGrafoActualizado={cargarExpediente}
        />
      )}
    </div>
  );
}