from datetime import date
from typing import Any, Dict, List, Optional
import clingo
from pydantic import BaseModel

from compiler import CompiladorJuridicoASP, HechoCliente
from schema import DocumentoNormativoCompilado, Operador


class AccionCorrectiva(BaseModel):
    operacion: str          # "RETIRAR_HECHO" | "AGREGAR_HECHO"
    sujeto: str
    propiedad: str
    valor: Any
    costo_operativo: int


class PlanContrafactual(BaseModel):
    meta_deseada: HechoCliente
    es_alcanzable: bool
    costo_total_minimo: Optional[int] = None
    acciones_requeridas: List[AccionCorrectiva] = []


class MotorAbductivoJuridico:
    def __init__(self):
        self.compilador = CompiladorJuridicoASP()

    def _generar_candidatos_adicion(
        self,
        documentos: List[DocumentoNormativoCompilado],
        meta: HechoCliente,
        hechos_actuales: List[HechoCliente],
        costos_adicion: Dict[str, int],
    ) -> List[HechoCliente]:
        existentes = {(h.sujeto, h.propiedad, str(h.valor)) for h in hechos_actuales}
        candidatos: List[HechoCliente] = []

        for doc in documentos:
            for regla in doc.reglas:
                if (
                    regla.consecuencia.propiedad == meta.propiedad
                    and str(regla.consecuencia.valor) == str(meta.valor)
                ):
                    for cond in regla.condiciones_and:
                        if (
                            cond.sujeto == regla.sujeto_activo
                            and cond.operador == Operador.IGUAL
                            and cond.propiedad in costos_adicion
                        ):
                            clave = (meta.sujeto, cond.propiedad, str(cond.valor))
                            if clave not in existentes:
                                candidatos.append(
                                    HechoCliente(
                                        sujeto=meta.sujeto,
                                        propiedad=cond.propiedad,
                                        valor=cond.valor,
                                    )
                                )
        return candidatos

    def calcular_ruta_minima(
        self,
        documentos: List[DocumentoNormativoCompilado],
        hechos_cliente: List[HechoCliente],
        meta: HechoCliente,
        costos_retiro: Dict[str, int],
        costos_adicion: Optional[Dict[str, int]] = None,
        fecha_evaluacion: Optional[date] = None,
    ) -> PlanContrafactual:
        fecha_eval = fecha_evaluacion or date.today()
        costos_add = costos_adicion or {}
        programa_reglas = self.compilador.compilar_documentos(documentos, fecha_eval)

        lineas_reglas = [
            l for l in programa_reglas.splitlines() if not l.startswith("#show ")
        ]

        asp: List[str] = [
            "% === BASE DE HECHOS OBSERVADOS ===",
        ]
        for h in hechos_cliente:
            s = self.compilador._id_asp(h.sujeto)
            p = f'"{h.propiedad}"'
            v = (
                self.compilador._id_asp(h.valor)
                if h.propiedad.endswith("De")
                else self.compilador._valor_asp(h.valor)
            )
            asp.append(f"hecho_base({s}, {p}, {v}).")

        asp.append("\n% === CANDIDATOS DE ADICIÓN (REQUISITOS FALTANTES) ===")
        for cand in self._generar_candidatos_adicion(
            documentos, meta, hechos_cliente, costos_add
        ):
            s = self.compilador._id_asp(cand.sujeto)
            p = f'"{cand.propiedad}"'
            v = self.compilador._valor_asp(cand.valor)
            asp.append(f"candidato_agregar({s}, {p}, {v}).")

        asp.append("\n% === TABLA DE COSTOS OPERATIVOS ===")
        for prop, costo in costos_retiro.items():
            asp.append(f'costo_retiro("{prop}", {costo}).')
        for prop, costo in costos_add.items():
            asp.append(f'costo_adicion("{prop}", {costo}).')

        asp.extend([
            "\n% === EXPLORACIÓN CONTRAFACTUAL ===",
            "{ retirar(S, P, V) } :- hecho_base(S, P, V), costo_retiro(P, _).",
            "{ agregar(S, P, V) } :- candidato_agregar(S, P, V), costo_adicion(P, _).",
            "hecho(S, P, V) :- hecho_base(S, P, V), not retirar(S, P, V).",
            "hecho(S, P, V) :- agregar(S, P, V).",
        ])

        asp.extend(lineas_reglas)

        m_s = self.compilador._id_asp(meta.sujeto)
        m_p = f'"{meta.propiedad}"'
        m_v = self.compilador._valor_asp(meta.valor)
        asp.extend([
            f":- not hecho({m_s}, {m_p}, {m_v}).",
            "#minimize { C, 1, S, P, V : retirar(S, P, V), costo_retiro(P, C);",
            "            C, 2, S, P, V : agregar(S, P, V), costo_adicion(P, C) }.",
            "#show retirar/3.",
            "#show agregar/3.",
        ])

        ctl = clingo.Control(["--warn=none"])
        ctl.add("base", [], "\n".join(asp))
        ctl.ground([("base", [])])

        mejor_modelo: List[clingo.Symbol] = []
        mejor_costo: Optional[int] = None
        satisfacible = False

        def on_model(model: clingo.Model):
            nonlocal mejor_modelo, mejor_costo, satisfacible
            satisfacible = True
            mejor_modelo = list(model.symbols(shown=True))
            if model.cost:
                mejor_costo = model.cost[0]

        ctl.solve(on_model=on_model)

        if not satisfacible:
            return PlanContrafactual(meta_deseada=meta, es_alcanzable=False)

        acciones: List[AccionCorrectiva] = []
        for sym in mejor_modelo:
            op = "RETIRAR_HECHO" if sym.name == "retirar" else "AGREGAR_HECHO"
            suj = str(sym.arguments[0]).strip('"')
            prop = sym.arguments[1].string
            val_sym = sym.arguments[2]
            val = (
                val_sym.string
                if val_sym.type == clingo.SymbolType.String
                else str(val_sym).strip('"')
            )
            costo = (
                costos_retiro[prop] if op == "RETIRAR_HECHO" else costos_add[prop]
            )
            acciones.append(
                AccionCorrectiva(
                    operacion=op,
                    sujeto=suj,
                    propiedad=prop,
                    valor=val,
                    costo_operativo=costo,
                )
            )

        return PlanContrafactual(
            meta_deseada=meta,
            es_alcanzable=True,
            costo_total_minimo=mejor_costo or 0,
            acciones_requeridas=acciones,
        )
