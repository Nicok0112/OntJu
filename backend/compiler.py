from datetime import date
from typing import Any, Dict, List, Optional, Tuple
import clingo
from pydantic import BaseModel

from schema import (
    DocumentoNormativoCompilado,
    Operador,
    PredicadoAtomico,
    ReglaJuridica,
)


class HechoCliente(BaseModel):
    sujeto: str       # Ej. "rfc_jup900101abc"
    propiedad: str    # Ej. "fiscal:ingresosEjercicioAnterior"
    valor: Any        # Ej. 2800000, "EMPRESARIAL", True, o ID de otro nodo


class ReglaAplicadaInfo(BaseModel):
    rule_id: str
    sujeto: str
    cita_legal: str
    descripcion: str
    modalidad: str


class EventoDisparado(BaseModel):
    evento: str
    sujeto: str
    rule_id: str


class DictamenJuridico(BaseModel):
    fecha_evaluacion: date
    hechos_inferidos: List[HechoCliente]
    reglas_activadas: List[ReglaAplicadaInfo]
    reglas_derrotadas: List[Tuple[str, str]]  # (rule_id, sujeto)
    eventos_automatizacion: List[EventoDisparado]
    codigo_asp_generado: Optional[str] = None


class CompiladorJuridicoASP:
    def __init__(self):
        self.catalogo_reglas: Dict[str, Tuple[ReglaJuridica, str]] = {}

    @staticmethod
    def _var_asp(var_str: str) -> str:
        """Convierte '?pm' -> 'PM' (variable en Clingo)."""
        return var_str.lstrip("?").upper().replace("-", "_")

    @staticmethod
    def _id_asp(identificador: str) -> str:
        """Convierte 'rfc_juan' -> 'rfc_juan' (átomo constante en Clingo)."""
        limpio = identificador.lower().replace("-", "_").replace(" ", "_")
        return f'"{identificador}"' if not limpio or not limpio[0].isalpha() else limpio

    @staticmethod
    def _valor_asp(val: Any) -> str:
        """Formatea valores literales de Python a sintaxis válida de Clingo."""
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            return str(int(round(val * 10000)))
        if isinstance(val, str):
            if val.startswith("?"):
                return CompiladorJuridicoASP._var_asp(val)
            escapado = val.replace('"', '\\"')
            return f'"{escapado}"'
        raise ValueError(f"Tipo de dato no soportado en AST: {type(val)}")

    def _compilar_predicado(
        self,
        pred: PredicadoAtomico,
        rule_id: str,
        idx: int,
        es_excepcion: bool = False,
    ) -> Tuple[str, List[str]]:
        s_asp = self._var_asp(pred.sujeto)
        prop_asp = f'"{pred.propiedad}"'
        tag = f"{rule_id}_{'exc' if es_excepcion else 'cond'}_{idx}".lower().replace("-", "_")
        v_tmp = f"V_{tag.upper()}"
        auxiliares: List[str] = []

        if pred.operador == Operador.IGUAL:
            val_asp = self._valor_asp(pred.valor)
            atomo = f"hecho({s_asp}, {prop_asp}, {val_asp})"
            return (f"not {atomo}" if es_excepcion else atomo), auxiliares

        if pred.operador == Operador.EXISTE_RELACION:
            target_asp = self._valor_asp(pred.valor)
            if not es_excepcion:
                return f"hecho({s_asp}, {prop_asp}, {target_asp})", auxiliares
            aux_pred = f"aux_rel_{tag}({s_asp})"
            auxiliares.append(f"{aux_pred} :- hecho({s_asp}, {prop_asp}, _).")
            return f"not {aux_pred}", auxiliares

        if pred.operador in (Operador.MENOR_IGUAL, Operador.MAYOR_IGUAL, Operador.DIFERENTE):
            val_asp = self._valor_asp(pred.valor)
            op = pred.operador.value
            if not es_excepcion:
                expr = f"hecho({s_asp}, {prop_asp}, {v_tmp}), {v_tmp} {op} {val_asp}"
                return expr, auxiliares
            aux_pred = f"aux_cmp_{tag}({s_asp})"
            auxiliares.append(
                f"{aux_pred} :- hecho({s_asp}, {prop_asp}, {v_tmp}), {v_tmp} {op} {val_asp}."
            )
            return f"not {aux_pred}", auxiliares

        if pred.operador in (Operador.EN_LISTA, Operador.NO_EN_LISTA):
            if not isinstance(pred.valor, list):
                raise ValueError(f"Operador {pred.operador} requiere una lista en {rule_id}")
            lista_pred = f"lista_{tag}"
            for item in pred.valor:
                auxiliares.append(f"{lista_pred}({self._valor_asp(item)}).")

            match_pred = f"aux_in_{tag}({s_asp})"
            auxiliares.append(
                f"{match_pred} :- hecho({s_asp}, {prop_asp}, {v_tmp}), {lista_pred}({v_tmp})."
            )

            debe_estar = pred.operador == Operador.EN_LISTA
            if es_excepcion:
                debe_estar = not debe_estar

            if debe_estar:
                return match_pred, auxiliares
            return f"hecho({s_asp}, {prop_asp}, _), not {match_pred}", auxiliares

        raise ValueError(f"Operador no soportado: {pred.operador}")

    def compilar_documentos(
        self,
        documentos: List[DocumentoNormativoCompilado],
        fecha_evaluacion: date,
    ) -> str:
        self.catalogo_reglas.clear()
        lineas_asp: List[str] = [
            "% === PROGRAMA LÓGICO GENERADO AUTOMÁTICAMENTE ===",
            f"% Fecha de vigencia evaluada: {fecha_evaluacion.isoformat()}",
            "",
        ]

        sujetos_por_regla: Dict[str, str] = {}
        reglas_vigentes: List[Tuple[ReglaJuridica, str]] = []

        for doc in documentos:
            f = doc.fuente
            if f.vigente_desde > fecha_evaluacion:
                continue
            if f.vigente_hasta and f.vigente_hasta < fecha_evaluacion:
                continue

            cita = f"{f.ordenamiento} Art. {f.articulo}" + (f" Fracc. {f.fraccion}" if f.fraccion else "")
            for regla in doc.reglas:
                reglas_vigentes.append((regla, cita))
                sujetos_por_regla[regla.rule_id] = regla.sujeto_activo
                self.catalogo_reglas[regla.rule_id] = (regla, cita)

        for regla, cita in reglas_vigentes:
            lineas_asp.append(f"% [{cita}] {regla.descripcion}")
            rid_asp = f'"{regla.rule_id}"'
            s_activo_asp = self._var_asp(regla.sujeto_activo)
            cuerpo: List[str] = []

            for idx, cond in enumerate(regla.condiciones_and):
                expr, aux = self._compilar_predicado(cond, regla.rule_id, idx, es_excepcion=False)
                lineas_asp.extend(aux)
                cuerpo.append(expr)

            for idx, exc in enumerate(regla.excepciones_unless):
                expr, aux = self._compilar_predicado(exc, regla.rule_id, idx, es_excepcion=True)
                lineas_asp.extend(aux)
                cuerpo.append(expr)

            cuerpo_str = ", ".join(cuerpo)

            lineas_asp.append(f"aplicable({rid_asp}, {s_activo_asp}) :- {cuerpo_str}.")
            lineas_asp.append(
                f"activa({rid_asp}, {s_activo_asp}) :- "
                f"aplicable({rid_asp}, {s_activo_asp}), not derrotada({rid_asp}, {s_activo_asp})."
            )

            for target_id in regla.anula_reglas:
                target_asp = f'"{target_id}"'
                if sujetos_por_regla.get(target_id) == regla.sujeto_activo:
                    lineas_asp.append(
                        f"derrotada({target_asp}, {s_activo_asp}) :- aplicable({rid_asp}, {s_activo_asp})."
                    )
                else:
                    lineas_asp.append(
                        f"derrotada({target_asp}, S_TARGET) :- "
                        f"aplicable({rid_asp}, _), aplicable({target_asp}, S_TARGET)."
                    )

            cons = regla.consecuencia
            cons_suj = self._var_asp(cons.sujeto)
            cons_prop = f'"{cons.propiedad}"'
            cons_val = self._valor_asp(cons.valor)
            lineas_asp.append(
                f"hecho({cons_suj}, {cons_prop}, {cons_val}) :- activa({rid_asp}, {s_activo_asp})."
            )
            lineas_asp.append(
                f"inferido({cons_suj}, {cons_prop}, {cons_val}) :- activa({rid_asp}, {s_activo_asp})."
            )

            if regla.evento_automatizacion:
                ev_asp = f'"{regla.evento_automatizacion}"'
                lineas_asp.append(
                    f"evento({ev_asp}, {s_activo_asp}, {rid_asp}) :- activa({rid_asp}, {s_activo_asp})."
                )

            lineas_asp.append("")

        lineas_asp.extend([
            "#show activa/2.",
            "#show derrotada/2.",
            "#show inferido/3.",
            "#show evento/3.",
        ])
        return "\n".join(lineas_asp)

    def evaluar_caso(
        self,
        documentos: List[DocumentoNormativoCompilado],
        hechos_cliente: List[HechoCliente],
        fecha_evaluacion: Optional[date] = None,
        incluir_codigo: bool = False,
    ) -> DictamenJuridico:
        fecha_eval = fecha_evaluacion or date.today()
        programa_reglas = self.compilar_documentos(documentos, fecha_eval)

        hechos_asp = ["% === HECHOS DEL CLIENTE (ABOX) ==="]
        for h in hechos_cliente:
            s = self._id_asp(h.sujeto)
            p = f'"{h.propiedad}"'
            v = self._id_asp(h.valor) if h.propiedad.endswith("De") else self._valor_asp(h.valor)
            hechos_asp.append(f"hecho({s}, {p}, {v}).")

        programa_completo = "\n".join(hechos_asp) + "\n\n" + programa_reglas

        ctl = clingo.Control(["--warn=none"])
        ctl.add("base", [], programa_completo)
        ctl.ground([("base", [])])

        simbolos_resultado: List[clingo.Symbol] = []
        ctl.solve(on_model=lambda m: simbolos_resultado.extend(m.symbols(shown=True)))

        reglas_activadas: List[ReglaAplicadaInfo] = []
        reglas_derrotadas: List[Tuple[str, str]] = []
        hechos_inferidos: List[HechoCliente] = []
        eventos: List[EventoDisparado] = []

        for sym in simbolos_resultado:
            nombre = sym.name
            args = sym.arguments

            if nombre == "activa":
                rid = args[0].string
                suj = str(args[1]).strip('"')
                regla_obj, cita = self.catalogo_reglas[rid]
                reglas_activadas.append(
                    ReglaAplicadaInfo(
                        rule_id=rid,
                        sujeto=suj,
                        cita_legal=cita,
                        descripcion=regla_obj.descripcion,
                        modalidad=regla_obj.modalidad.value,
                    )
                )
            elif nombre == "derrotada":
                reglas_derrotadas.append((args[0].string, str(args[1]).strip('"')))
            elif nombre == "inferido":
                val_sym = args[2]
                val_py: Any = val_sym.string if val_sym.type == clingo.SymbolType.String else str(val_sym)
                if val_py == "true":
                    val_py = True
                elif val_py == "false":
                    val_py = False
                hechos_inferidos.append(
                    HechoCliente(
                        sujeto=str(args[0]).strip('"'),
                        propiedad=args[1].string,
                        valor=val_py,
                    )
                )
            elif nombre == "evento":
                eventos.append(
                    EventoDisparado(
                        evento=args[0].string,
                        sujeto=str(args[1]).strip('"'),
                        rule_id=args[2].string,
                    )
                )

        return DictamenJuridico(
            fecha_evaluacion=fecha_eval,
            hechos_inferidos=hechos_inferidos,
            reglas_activadas=reglas_activadas,
            reglas_derrotadas=reglas_derrotadas,
            eventos_automatizacion=eventos,
            codigo_asp_generado=programa_completo if incluir_codigo else None,
        )

