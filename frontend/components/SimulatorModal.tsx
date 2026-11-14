"use client";

import React, { useState } from "react";
import { Calculator, GitBranch, Play, Plus, Trash2, X } from "lucide-react";
import type {
  BeneficiarioControladorDetectado,
  PlanContrafactual,
} from "@/types/lexengine";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  apiBase: string;
  tenantId: string;
  defaultSujeto: string;
  onGrafoActualizado: () => Promise<void>;
}

export function SimulatorModal({
  isOpen,
  onClose,
  apiBase,
  tenantId,
  defaultSujeto,
  onGrafoActualizado,
}: Props) {
  const [tab, setTab] = useState<"abduction" | "ownership">("abduction");

  // Estado Simulador Contrafactual
  const [sujetoMeta, setSujetoMeta] = useState(defaultSujeto);
  const [propMeta, setPropMeta] = useState("fiscal:elegibleRegimen");
  const [valMeta, setValMeta] = useState("RESICO");
  const [plan, setPlan] = useState<PlanContrafactual | null>(null);
  const [loadingSim, setLoadingSim] = useState(false);

  // Estado Álgebra Societaria
  const [relaciones, setRelaciones] = useState([
    { socio_id: "ana", sociedad_id: "holding_mx_sa", porcentaje_directo: 40, socio_es_persona_fisica: true },
    { socio_id: "holding_mx_sa", sociedad_id: "operadora_norte_sa", porcentaje_directo: 50, socio_es_persona_fisica: false },
    { socio_id: "operadora_norte_sa", sociedad_id: "holding_mx_sa", porcentaje_directo: 10, socio_es_persona_fisica: false },
  ]);
  const [beneficiarios, setBeneficiarios] = useState<BeneficiarioControladorDetectado[]>([]);

  if (!isOpen) return null;

  const ejecutarAbduccion = async () => {
    setLoadingSim(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/despachos/${tenantId}/simular-regularizacion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meta: { sujeto: sujetoMeta, propiedad: propMeta, valor: valMeta },
        }),
      });
      if (res.ok) {
        setPlan(await res.json());
      }
    } finally {
      setLoadingSim(false);
    }
  };

  const ejecutarAlgebraSocietaria = async () => {
    setLoadingSim(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/despachos/${tenantId}/beneficiario-controlador`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(relaciones),
      });
      if (res.ok) {
        setBeneficiarios(await res.json());
        await onGrafoActualizado();
      }
    } finally {
      setLoadingSim(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 text-slate-100 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setTab("abduction")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                tab === "abduction"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:bg-slate-800"
              }`}
            >
              <Calculator className="w-3.5 h-3.5" />
              Simulador Contrafactual (ASP)
            </button>
            <button
              onClick={() => setTab("ownership")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                tab === "ownership"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:bg-slate-800"
              }`}
            >
              <GitBranch className="w-3.5 h-3.5" />
              Beneficiario Controlador T=A(I-A)⁻¹
            </button>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 text-xs space-y-4">
          {tab === "abduction" ? (
            <>
              <p className="text-slate-400">
                Calcula la ruta de intervención legal de menor costo operativo para que una entidad alcance un estatus jurídico deseado.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <input
                  value={sujetoMeta}
                  onChange={(e) => setSujetoMeta(e.target.value)}
                  placeholder="Sujeto (ej. rfc_...)"
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono"
                />
                <input
                  value={propMeta}
                  onChange={(e) => setPropMeta(e.target.value)}
                  placeholder="Propiedad"
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono"
                />
                <input
                  value={valMeta}
                  onChange={(e) => setValMeta(e.target.value)}
                  placeholder="Valor meta"
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono"
                />
              </div>
              <button
                onClick={ejecutarAbduccion}
                disabled={loadingSim}
                className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-500 transition"
              >
                <Play className="w-3.5 h-3.5" />
                {loadingSim ? "Optimizando modelo..." : "Calcular Ruta Mínima"}
              </button>

              {plan && (
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 space-y-2">
                  <div className="flex justify-between font-semibold">
                    <span>
                      Estado:{" "}
                      {plan.es_alcanzable ? (
                        <span className="text-emerald-400">Alcanzable</span>
                      ) : (
                        <span className="text-rose-400">No alcanzable (restricción histórica)</span>
                      )}
                    </span>
                    {plan.costo_total_minimo !== null && (
                      <span className="font-mono text-indigo-300">
                        Costo mínimo: {plan.costo_total_minimo} pts
                      </span>
                    )}
                  </div>
                  {plan.acciones_requeridas.length === 0 && plan.es_alcanzable ? (
                    <p className="text-slate-400">El sujeto ya cumple la meta sin cambios adicionales.</p>
                  ) : (
                    plan.acciones_requeridas.map((acc, i) => (
                      <div
                        key={i}
                        className="rounded border border-amber-500/30 bg-amber-950/20 px-3 py-2 font-mono text-amber-200"
                      >
                        [{acc.operacion}] {acc.sujeto} → {acc.propiedad} = {String(acc.valor)} (costo: {acc.costo_operativo})
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              <p className="text-slate-400">
                Resuelve cadenas corporativas multinivel y participaciones cruzadas bajo el umbral del 15% (Art. 32-B Quáter CFF).
              </p>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {relaciones.map((rel, idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                    <input
                      value={rel.socio_id}
                      onChange={(e) => {
                        const copy = [...relaciones];
                        copy[idx].socio_id = e.target.value;
                        setRelaciones(copy);
                      }}
                      className="col-span-4 rounded border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono"
                      placeholder="Socio"
                    />
                    <input
                      value={rel.sociedad_id}
                      onChange={(e) => {
                        const copy = [...relaciones];
                        copy[idx].sociedad_id = e.target.value;
                        setRelaciones(copy);
                      }}
                      className="col-span-4 rounded border border-slate-700 bg-slate-950 px-2.5 py-1.5 font-mono"
                      placeholder="Sociedad"
                    />
                    <input
                      type="number"
                      value={rel.porcentaje_directo}
                      onChange={(e) => {
                        const copy = [...relaciones];
                        copy[idx].porcentaje_directo = Number(e.target.value);
                        setRelaciones(copy);
                      }}
                      className="col-span-2 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono"
                    />
                    <label className="col-span-1 flex items-center justify-center text-[10px] text-slate-400" title="Persona Física">
                      <input
                        type="checkbox"
                        checked={rel.socio_es_persona_fisica}
                        onChange={(e) => {
                          const copy = [...relaciones];
                          copy[idx].socio_es_persona_fisica = e.target.checked;
                          setRelaciones(copy);
                        }}
                      />
                      PF
                    </label>
                    <button
                      onClick={() => setRelaciones(relaciones.filter((_, i) => i !== idx))}
                      className="col-span-1 text-rose-400 hover:text-rose-300 flex justify-center"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() =>
                    setRelaciones([
                      ...relaciones,
                      { socio_id: "", sociedad_id: "", porcentaje_directo: 10, socio_es_persona_fisica: true },
                    ])
                  }
                  className="flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 hover:bg-slate-800"
                >
                  <Plus className="w-3.5 h-3.5" /> Fila
                </button>
                <button
                  onClick={ejecutarAlgebraSocietaria}
                  disabled={loadingSim}
                  className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-1.5 font-semibold text-white hover:bg-indigo-500"
                >
                  <Play className="w-3.5 h-3.5" /> Calcular Control Efectivo
                </button>
              </div>

              {beneficiarios.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 space-y-1.5">
                  {beneficiarios.map((b, i) => (
                    <div
                      key={i}
                      className={`flex justify-between rounded px-3 py-1.5 font-mono ${
                        b.supera_umbral_legal
                          ? "bg-rose-950/40 border border-rose-500/40 text-rose-200"
                          : "bg-slate-900 text-slate-300"
                      }`}
                    >
                      <span>
                        {b.persona_fisica_id} → {b.sociedad_objetivo_id}
                      </span>
                      <span>
                        Total: <strong>{b.porcentaje_total_efectivo}%</strong> (Dir: {b.porcentaje_directo}% | Ind: {b.porcentaje_indirecto}%)
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
