"use client";

import React from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { User, Building2, FileText, AlertTriangle, CheckCircle2 } from "lucide-react";
import {
  formatearNombreEntidad,
  limpiarPropiedad,
  formatearValor,
} from "@/lib/humanizer";

export type EntityNodeData = {
  label: string;
  atributos?: Record<string, { valor: unknown; inferido?: boolean }>;
};

export type EntityFlowNode = Node<EntityNodeData, "entityNode">;

export default function EntityNode({ data, selected }: NodeProps<EntityFlowNode>) {
  const { titulo, tipo } = formatearNombreEntidad(data.label);
  const entradas = Object.entries(data.atributos || {});

  const tieneAlerta = entradas.some(
    ([k, v]) =>
      (k.toLowerCase().includes("excluido") ||
        k.toLowerCase().includes("suspendida") ||
        k.toLowerCase().includes("bloqueo")) &&
      v.valor === true
  );

  const Icono =
    tipo === "Persona Física"
      ? User
      : tipo === "Persona Moral"
      ? Building2
      : FileText;

  return (
    <div
      className={`min-w-[250px] max-w-[300px] rounded-xl border-2 bg-slate-900/95 p-4 shadow-xl transition-all ${
        tieneAlerta
          ? "border-rose-500 shadow-rose-950/50"
          : selected
          ? "border-indigo-400 shadow-indigo-950/40"
          : "border-slate-700 hover:border-slate-500"
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-indigo-400 !w-3 !h-3" />

      {/* Encabezado de la tarjeta */}
      <div className="flex items-start justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex items-center gap-2.5">
          <div
            className={`rounded-lg p-2 ${
              tieneAlerta
                ? "bg-rose-500/20 text-rose-400"
                : "bg-indigo-500/20 text-indigo-300"
            }`}
          >
            <Icono className="h-4 w-4" />
          </div>
          <div>
            <span className="block text-[11px] font-medium uppercase tracking-wider text-slate-400">
              {tipo}
            </span>
            <h3 className="text-sm font-bold text-slate-100">{titulo}</h3>
          </div>
        </div>

        {tieneAlerta ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/20 px-2 py-0.5 text-[11px] font-semibold text-rose-300">
            <AlertTriangle className="h-3 w-3" /> Alerta
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
            <CheckCircle2 className="h-3 w-3" /> Activo
          </span>
        )}
      </div>

      {/* Atributos en español */}
      {entradas.length > 0 ? (
        <dl className="mt-3 space-y-1.5 text-xs">
          {entradas.map(([prop, info]) => {
            const esCritico = info.valor === true && prop.toLowerCase().includes("excluido");
            return (
              <div
                key={prop}
                className="flex items-center justify-between gap-2 rounded-md bg-slate-800/70 px-2.5 py-1.5"
              >
                <dt className="text-slate-300">{limpiarPropiedad(prop)}</dt>
                <dd
                  className={`font-semibold ${
                    esCritico
                      ? "text-rose-400"
                      : info.inferido
                      ? "text-emerald-400"
                      : "text-slate-100"
                  }`}
                >
                  {formatearValor(info.valor)}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : (
        <p className="mt-2.5 text-xs text-slate-400">Entidad vinculada en el expediente</p>
      )}

      <Handle type="source" position={Position.Right} className="!bg-indigo-400 !w-3 !h-3" />
    </div>
  );
}