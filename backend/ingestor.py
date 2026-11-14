import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional, Set
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from compiler import HechoCliente


NS_SAT = {
    "cfdi": "http://www.sat.gob.mx/cfd/4",
    "tfd": "http://www.sat.gob.mx/TimbreFiscalDigital",
}

MAPA_REGIMEN_ACTIVIDAD: Dict[str, str] = {
    "606": "ARRENDAMIENTO",
    "612": "EMPRESARIAL",
    "621": "EMPRESARIAL",
    "625": "PLATAFORMAS_TECNOLOGICAS",
    "626": "EMPRESARIAL",
}

MAPA_REGIMEN_SOCIEDAD: Dict[str, str] = {
    "601": "SOCIEDAD_MERCANTIL",
    "603": "PERSONA_MORAL_NO_LUCRATIVA",
    "620": "SOCIEDAD_COOPERATIVA_PRODUCCION",
}


class ResumenIngestaCFDI(BaseModel):
    rfc_contribuyente: str
    ejercicio_fiscal: int
    cfdis_procesados: int
    cfdis_duplicados_ignorados: int
    ingresos_brutos_mxn: int
    notas_credito_mxn: int
    ingresos_netos_mxn: int
    hechos_generados: List[HechoCliente]


class _ListaHechosPDF(BaseModel):
    hechos: List[HechoCliente] = Field(
        description="Lista de hechos jurídicos extraídos del documento."
    )


class IngestorFiscalAutonomo:
    def __init__(self, gemini_api_key: Optional[str] = None):
        self.uuids_procesados: Set[str] = set()
        api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self.genai_client = genai.Client(api_key=api_key) if api_key else None

    @staticmethod
    def _redondeo_art20_cff(monto: Decimal) -> int:
        """
        Art. 20 CFF: Las contribuciones y sus accesorios se determinan en pesos enteros.
        De 1 a 50 centavos baja al peso anterior; de 51 a 99 sube al siguiente.
        """
        return int(monto.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _clasificar_personalidad_por_rfc(rfc: str) -> str:
        """En México: 13 caracteres = Persona Física; 12 caracteres = Persona Moral."""
        rfc_limpio = rfc.strip().upper()
        if len(rfc_limpio) == 13:
            return "legal:PersonaFisica"
        if len(rfc_limpio) == 12:
            return "legal:PersonaMoral"
        raise ValueError(f"Longitud de RFC inválida en el sistema mexicano: {rfc}")

    def _parsear_xml_individual(self, xml_bytes: bytes) -> Optional[dict]:
        root = ET.fromstring(xml_bytes)

        version = root.attrib.get("Version")
        if version != "4.0":
            return None

        tfd = root.find(".//tfd:TimbreFiscalDigital", NS_SAT)
        if tfd is None or "UUID" not in tfd.attrib:
            return None

        uuid = tfd.attrib["UUID"].strip().upper()
        if uuid in self.uuids_procesados:
            return {"duplicado": True, "uuid": uuid}
        self.uuids_procesados.add(uuid)

        fecha_str = root.attrib["Fecha"]
        anio = datetime.fromisoformat(fecha_str).year
        tipo_comprobante = root.attrib["TipoDeComprobante"]

        subtotal = Decimal(root.attrib.get("SubTotal", "0"))
        descuento = Decimal(root.attrib.get("Descuento", "0"))
        moneda = root.attrib.get("Moneda", "MXN")
        tipo_cambio = Decimal(root.attrib.get("TipoCambio", "1")) if moneda != "MXN" else Decimal("1")
        monto_mxn = (subtotal - descuento) * tipo_cambio

        emisor = root.find("cfdi:Emisor", NS_SAT)
        receptor = root.find("cfdi:Receptor", NS_SAT)

        return {
            "duplicado": False,
            "uuid": uuid,
            "anio": anio,
            "tipo": tipo_comprobante,
            "monto_mxn": monto_mxn,
            "emisor_rfc": emisor.attrib["Rfc"].strip().upper(),
            "emisor_regimen": emisor.attrib.get("RegimenFiscal", ""),
            "receptor_rfc": receptor.attrib["Rfc"].strip().upper(),
        }

    def ingestar_lote_cfdi(
        self,
        rfc_objetivo: str,
        ejercicio_fiscal: int,
        archivos_xml: List[bytes],
        es_ejercicio_anterior: bool = True,
    ) -> ResumenIngestaCFDI:
        rfc_obj = rfc_objetivo.strip().upper()
        sujeto_id = f"rfc_{rfc_obj.lower()}"

        ingresos_brutos = Decimal("0")
        notas_credito = Decimal("0")
        regimenes_detectados: Set[str] = set()
        procesados = 0
        duplicados = 0

        for xml_data in archivos_xml:
            parsed = self._parsear_xml_individual(xml_data)
            if not parsed:
                continue
            if parsed.get("duplicado"):
                duplicados += 1
                continue

            if parsed["emisor_rfc"] != rfc_obj or parsed["anio"] != ejercicio_fiscal:
                continue

            procesados += 1
            if parsed["emisor_regimen"]:
                regimenes_detectados.add(parsed["emisor_regimen"])

            if parsed["tipo"] == "I":
                ingresos_brutos += parsed["monto_mxn"]
            elif parsed["tipo"] == "E":
                notas_credito += parsed["monto_mxn"]

        ingresos_netos = max(Decimal("0"), ingresos_brutos - notas_credito)
        ingresos_enteros = self._redondeo_art20_cff(ingresos_netos)

        hechos: List[HechoCliente] = [
            HechoCliente(
                sujeto=sujeto_id,
                propiedad="rdf:type",
                valor=self._clasificar_personalidad_por_rfc(rfc_obj),
            )
        ]

        prop_ingresos = (
            "fiscal:ingresosEjercicioAnterior"
            if es_ejercicio_anterior
            else "fiscal:ingresosEjercicioActual"
        )
        hechos.append(
            HechoCliente(sujeto=sujeto_id, propiedad=prop_ingresos, valor=ingresos_enteros)
        )

        for reg in sorted(regimenes_detectados):
            hechos.append(
                HechoCliente(sujeto=sujeto_id, propiedad="fiscal:regimenSAT", valor=reg)
            )
            if reg in MAPA_REGIMEN_ACTIVIDAD:
                hechos.append(
                    HechoCliente(
                        sujeto=sujeto_id,
                        propiedad="fiscal:actividad",
                        valor=MAPA_REGIMEN_ACTIVIDAD[reg],
                    )
                )
            if reg in MAPA_REGIMEN_SOCIEDAD:
                hechos.append(
                    HechoCliente(
                        sujeto=sujeto_id,
                        propiedad="corporativo:tipoSociedad",
                        valor=MAPA_REGIMEN_SOCIEDAD[reg],
                    )
                )

        return ResumenIngestaCFDI(
            rfc_contribuyente=rfc_obj,
            ejercicio_fiscal=ejercicio_fiscal,
            cfdis_procesados=procesados,
            cfdis_duplicados_ignorados=duplicados,
            ingresos_brutos_mxn=self._redondeo_art20_cff(ingresos_brutos),
            notas_credito_mxn=self._redondeo_art20_cff(notas_credito),
            ingresos_netos_mxn=ingresos_enteros,
            hechos_generados=hechos,
        )

    def ingestar_documento_pdf(
                self, ruta_pdf: Path, rfc_titular: str
        ) -> List[HechoCliente]:
            if not self.genai_client:
                raise RuntimeError("Se requiere GEMINI_API_KEY para procesar PDFs.")

            sujeto_id = f"rfc_{rfc_titular.strip().lower()}"
            pdf_bytes = ruta_pdf.read_bytes()

            prompt = f"""Analiza este documento legal, fiscal o familiar mexicano vinculado al titular '{sujeto_id}'.
    Extrae únicamente hechos objetivos como tripletas usando estrictamente estas propiedades y tipos de dato:

    1. Si el documento es FISCAL o CORPORATIVO (Constancia de Situación Fiscal, Acta Constitutiva, Asamblea):
    - 'corporativo:esSocioDe': si '{sujeto_id}' es socio o accionista de una persona moral (sujeto = '{sujeto_id}', valor = ID limpio en minúsculas de la sociedad, ej. 'rfc_abc120101xyz').
    - 'corporativo:tipoSociedad': tipo de persona moral (ej. 'SOCIEDAD_ANONIMA', 'SOCIEDAD_COOPERATIVA_PRODUCCION', 'SOCIEDAD_CIVIL').
    - 'corporativo:soloSociosPersonasFisicas': booleano (true/false) si el acta indica que todos sus socios son personas físicas.
    - 'fiscal:obligacionActiva': clave o nombre de obligaciones fiscales registradas en su Constancia.

    2. Si el documento es de DERECHO FAMILIAR (Acta de Nacimiento, Constancia de Estudios, Certificado Médico):
    - 'familiar:esHijoDe': relación filial entre hijo y padre/madre (sujeto = primer nombre en minúsculas o RFC del hijo, ej. 'sofia'; valor = '{sujeto_id}').
    - 'familiar:edadAnios': edad cumplida del hijo en número entero (sujeto = ID del hijo, valor = entero, ej. 12 o 20).
    - 'familiar:estudiaGradoAcorde': booleano (true/false) si la constancia acredita estudios vigentes acordes a su edad (sujeto = ID del hijo, valor = true).
    - 'familiar:tieneDiscapacidad': booleano (true/false) si el certificado médico acredita discapacidad (sujeto = ID del hijo, valor = true)."""

            response = self.genai_client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_ListaHechosPDF,
                    temperature=0.0,
                ),
            )
            resultado: _ListaHechosPDF = response.parsed
            return resultado.hechos