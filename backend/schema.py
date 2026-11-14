from datetime import date
from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class JerarquiaNormativa(str, Enum):
    CONSTITUCION = "01_CONSTITUCION"
    TRATADO_DDHH = "02_TRATADO_DDHH"
    LEY_GENERAL = "03_LEY_GENERAL"
    LEY_FEDERAL = "04_LEY_FEDERAL"
    CODIGO = "05_CODIGO"
    REGLAMENTO = "06_REGLAMENTO"
    MISCELANEA = "07_MISCELANEA"


class ModalidadDeontica(str, Enum):
    OBLIGACION = "OBLIGATION"         # Debe hacer X
    PROHIBICION = "PROHIBITION"       # No debe hacer X
    PERMISION = "PERMISSION"          # Puede hacer X
    EXENCION = "EXEMPTION"            # Queda liberado de X
    CALIFICACION = "QUALIFICATION"    # Adquiere estatus jurídico X (ej. ser sujeto de un régimen)


class Operador(str, Enum):
    IGUAL = "=="
    DIFERENTE = "!="
    MENOR_IGUAL = "<="
    MAYOR_IGUAL = ">="
    EN_LISTA = "IN"
    NO_EN_LISTA = "NOT_IN"
    EXISTE_RELACION = "EXISTS"


class FuenteNormativa(BaseModel):
    ordenamiento: str = Field(..., description="Siglas de la ley, ej. LISR, CFF, LFT, LFPIORPI")
    articulo: str = Field(..., description="Número de artículo, ej. 113-E")
    fraccion: Optional[str] = Field(None, description="Fracción o párrafo específico")
    jerarquia: JerarquiaNormativa
    jurisdiccion: str = Field("FEDERAL", description="FEDERAL o código de entidad federativa")
    vigente_desde: date
    vigente_hasta: Optional[date] = None


class PredicadoAtomico(BaseModel):
    sujeto: str = Field(..., description="Variable lógica, ej. '?contribuyente'")
    propiedad: str = Field(..., description="URI de la propiedad ontológica, ej. 'fiscal:ingresosAnuales'")
    operador: Operador
    valor: Union[str, int, float, bool, List[str]]
    unidad: Optional[str] = Field(None, description="Ej. 'MXN', 'UMA', 'DIAS'")


class ReglaJuridica(BaseModel):
    rule_id: str = Field(..., description="Identificador único, ej. LISR_113E_R1")
    descripcion: str = Field(..., description="Resumen en lenguaje natural de la regla")
    modalidad: ModalidadDeontica

    # Dualidad de Hohfeld (Quién tiene el deber/derecho y frente a quién)
    sujeto_activo: str = Field(..., description="Variable del sujeto regulado, ej. '?contribuyente'")
    sujeto_pasivo: Optional[str] = Field(None, description="Contraparte o autoridad, ej. '?sat'")

    # Antecedente (IF): Todas estas condiciones deben cumplirse
    condiciones_and: List[PredicadoAtomico] = Field(default_factory=list)

    # Derrotabilidad (UNLESS): Si alguna ocurre, la regla se bloquea localmente
    excepciones_unless: List[PredicadoAtomico] = Field(default_factory=list)

    # Consecuente (THEN): Hecho o deber jurídico que el motor infiere
    consecuencia: PredicadoAtomico

    # Precedencia entre reglas (Resolución de antinomias y contra-excepciones)
    anula_reglas: List[str] = Field(default_factory=list, description="IDs de reglas que esta norma derrota")
    evento_automatizacion: Optional[str] = Field(None, description="Webhook o acción a disparar si se activa")


class DocumentoNormativoCompilado(BaseModel):
    fuente: FuenteNormativa
    reglas: List[ReglaJuridica]

