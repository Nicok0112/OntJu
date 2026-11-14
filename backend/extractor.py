import os
from typing import List, Optional, Set
from google import genai
from google.genai import types
from pydantic import BaseModel

from schema import DocumentoNormativoCompilado


class ResultadoExtraccion(BaseModel):
    documento: DocumentoNormativoCompilado
    predicados_nuevos: List[str]
    intentos_realizados: int


class ExtractorNormativoAutonomo:
    def __init__(self, modelo: str = "gemini-2.5-pro", vocabulario_base: Optional[Set[str]] = None):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.modelo = modelo
        self.vocabulario_base = vocabulario_base or {
            "rdf:type",
            "fiscal:actividad",
            "fiscal:ingresosEjercicioAnterior",
            "fiscal:excluidoRESICO",
            "fiscal:elegibleRegimen",
            "corporativo:esSocioDe",
            "corporativo:tipoSociedad",
            "corporativo:soloSociosPersonasFisicas",
            "corporativo:esBeneficiarioControladorDe",
            "pld:giroActividad",
            "pld:montoSinIvaMXN",
            "pld:montoTotalConIvaMXN",
            "pld:formaPagoSAT",
            "pld:requiereIdentificacionKYC",
            "pld:requiereAvisoUIF",
            "pld:operacionProhibidaEfectivo",
        }

    def obtener_vocabulario_activo(self) -> Set[str]:
        return set(self.vocabulario_base)

    def _construir_system_prompt(self, vocabulario: Set[str]) -> str:
        lista_preds = "\n".join(f"  - {p}" for p in sorted(vocabulario))
        return f"""Eres un compilador jurídico-formal especializado en el sistema legal mexicano.
Tu tarea es traducir artículos de leyes mexicanas a un Árbol de Sintaxis Abstracta (AST) lógico-deóntico.

REGLAS ESTRICTAS DE TRADUCCIÓN:
1. ATOMIZACIÓN: Descompón cada párrafo, fracción o hipótesis normativa en reglas independientes dentro de `reglas`.
2. DERROTABILIDAD (Excepciones):
   - Si una oración dice "No podrán aplicar...", "Quedan exceptuados..." o "Se perderá el derecho cuando...", crea una regla separada con modalidad PROHIBITION o EXEMPTION y coloca el ID de la regla general en `anula_reglas`.
   - Si una excepción tiene una contra-excepción ("salvo que...", "a menos que se trate de..."), crea una tercera regla que anule a la regla de exclusión.
3. SEGURIDAD DE VARIABLES (Obligatorio):
   - Toda variable debe iniciar con '?' (ej. ?p, ?pm, ?contrato).
   - Toda variable usada en `consecuencia` o en `excepciones_unless` DEBE haber sido declarada previamente en `condiciones_and`.
4. REUTILIZACIÓN DE ONTOLOGÍA:
   - Usa prioritariamente estos predicados ya existentes en el grafo:
{lista_preds}
   - Solo crea un predicado nuevo (formato `dominio:nombreCamelCase`) si ningún predicado existente expresa el concepto jurídico.
5. TRAZABILIDAD: No inventes datos fuera del texto proporcionado. Usa unidades estándar (MXN, UMA, DIAS, PORCENTAJE)."""

    def _validar_integridad_semantica(
        self, doc: DocumentoNormativoCompilado, ids_existentes_en_grafo: Set[str]
    ) -> List[str]:
        """
        Aduana determinista: atrapa errores lógicos antes de compilar a Clingo/RDF.
        """
        errores = []
        ids_locales = {r.rule_id for r in doc.reglas}
        ids_totales = ids_locales.union(ids_existentes_en_grafo)

        for regla in doc.reglas:
            # 1. Verificar que los IDs en `anula_reglas` realmente existan
            for target_id in regla.anula_reglas:
                if target_id not in ids_totales:
                    errores.append(
                        f"Regla '{regla.rule_id}' intenta anular '{target_id}', pero ese rule_id no existe."
                    )

            # 2. Verificar seguridad de variables (Datalog/ASP Safety)
            vars_en_cuerpo = set()
            for cond in regla.condiciones_and:
                if cond.sujeto.startswith("?"):
                    vars_en_cuerpo.add(cond.sujeto)
                if isinstance(cond.valor, str) and cond.valor.startswith("?"):
                    vars_en_cuerpo.add(cond.valor)

            if not regla.consecuencia.sujeto.startswith("?"):
                errores.append(
                    f"Regla '{regla.rule_id}': el sujeto de la consecuencia debe ser una variable '?'."
                )
            elif regla.consecuencia.sujeto not in vars_en_cuerpo:
                errores.append(
                    f"Regla '{regla.rule_id}': variable insegura '{regla.consecuencia.sujeto}' en consecuencia (no aparece en condiciones_and)."
                )

            # 3. Verificar coherencia temporal
            if doc.fuente.vigente_hasta and doc.fuente.vigente_hasta < doc.fuente.vigente_desde:
                errores.append("La fecha vigente_hasta es anterior a vigente_desde.")

        return errores

    def extraer_articulo(
        self,
        texto_crudo: str,
        metadatos_dof: str,
        ids_existentes: Optional[Set[str]] = None,
        max_reintentos: int = 2,
    ) -> ResultadoExtraccion:
        vocabulario = self.obtener_vocabulario_activo()
        system_prompt = self._construir_system_prompt(vocabulario)
        historial_contenido = [
            f"METADATOS DE PUBLICACIÓN:\n{metadatos_dof}\n\nTEXTO NORMATIVO:\n{texto_crudo}"
        ]

        for intento in range(1, max_reintentos + 2):
            response = self.client.models.generate_content(
                model=self.modelo,
                contents=historial_contenido,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=DocumentoNormativoCompilado,
                    temperature=0.0,
                ),
            )

            doc_compilado: DocumentoNormativoCompilado = response.parsed
            errores_logicos = self._validar_integridad_semantica(
                doc_compilado, ids_existentes_en_grafo=ids_existentes or set()
            )

            if not errores_logicos:
                preds_extraidos = {
                    p.propiedad
                    for r in doc_compilado.reglas
                    for p in (*r.condiciones_and, *r.excepciones_unless, r.consecuencia)
                }
                nuevos = sorted(list(preds_extraidos - vocabulario))
                self.vocabulario_base.update(nuevos)

                return ResultadoExtraccion(
                    documento=doc_compilado,
                    predicados_nuevos=nuevos,
                    intentos_realizados=intento,
                )

            reporte_error = "\n".join(f"- {e}" for e in errores_logicos)
            historial_contenido.append(response.text)
            historial_contenido.append(
                f"ERROR DE VALIDACIÓN LÓGICA EN TU SALIDA:\n{reporte_error}\n"
                "Corrige el JSON manteniendo intactas las reglas válidas."
            )

        raise ValueError(f"No se pudo obtener un AST lógicamente válido tras {max_reintentos} reintentos.")

