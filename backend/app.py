from contextlib import asynccontextmanager
from datetime import date
import io
import re
from uuid import uuid4
import logging
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
import zipfile
import unicodedata
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pyoxigraph import Literal, NamedNode, Quad, Store

from compiler import CompiladorJuridicoASP, DictamenJuridico, HechoCliente
from extractor import ExtractorNormativoAutonomo
from ingestor import IngestorFiscalAutonomo
from math_engines.abduction import MotorAbductivoJuridico, PlanContrafactual
from math_engines.ownership_algebra import (
    AnalizadorPropiedadEfectiva,
    BeneficiarioControladorDetectado,
    ParticipacionSocietaria,
)
from math_engines.pension_calculator import (
    AcreedorAlimentario,
    CalculadorPensionAlimenticia,
)
from schema import DocumentoNormativoCompilado
from worker import VigilanteDOFAutonomo, iniciar_worker_dof, scheduler

logger = logging.getLogger("lexengine.api")

BASE_NS = "https://ontologia.legal.mx/ns/"
PREFIX_MAP = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "legal": f"{BASE_NS}legal#",
    "fiscal": f"{BASE_NS}fiscal#",
    "corporativo": f"{BASE_NS}corporativo#",
    "laboral": f"{BASE_NS}laboral#",
    "pld": f"{BASE_NS}pld#",
    "entidad": f"{BASE_NS}entidad/",
}
XSD_INT = NamedNode("http://www.w3.org/2001/XMLSchema#integer")
XSD_BOOL = NamedNode("http://www.w3.org/2001/XMLSchema#boolean")

calculador_pension = CalculadorPensionAlimenticia()


class SolicitudProrrateoPension(BaseModel):
    deudor_id: str
    ingreso_neto_mxn: int
    porcentaje_embargable: float = 40.0
    acreedores: List[AcreedorAlimentario]

class MotorOntologicoStore:
    """Capa de persistencia RDF sobre Oxigraph con aislamiento multi-tenant."""

    def __init__(self, db_path: str = "./data/oxigraph_db"):
        Path(db_path).mkdir(parents=True, exist_ok=True)
        self.store = Store(db_path)
        self.tbox_graph = NamedNode("urn:legal:tbox")

    @staticmethod
    def _to_uri(curie_o_id: str) -> NamedNode:
        if curie_o_id.startswith("http://") or curie_o_id.startswith("https://"):
            return NamedNode(curie_o_id)
        if ":" in curie_o_id:
            prefijo, local = curie_o_id.split(":", 1)
            if prefijo in PREFIX_MAP:
                return NamedNode(f"{PREFIX_MAP[prefijo]}{local}")
        return NamedNode(f"{PREFIX_MAP['entidad']}{curie_o_id}")

    @staticmethod
    def _from_uri(uri: str) -> str:
        for prefijo, base in PREFIX_MAP.items():
            if uri.startswith(base):
                local = uri[len(base):]
                return local if prefijo == "entidad" else f"{prefijo}:{local}"
        return uri

    def _valor_a_termino_rdf(self, propiedad: str, valor: Any):
        if isinstance(valor, bool):
            return Literal("true" if valor else "false", datatype=XSD_BOOL)
        if isinstance(valor, int):
            return Literal(str(valor), datatype=XSD_INT)
        if isinstance(valor, str):
            if propiedad == "rdf:type" or propiedad.endswith("De") or valor.startswith("rfc_"):
                return self._to_uri(valor)
            return Literal(valor)
        return Literal(str(valor))

    def _termino_rdf_a_valor(self, term) -> Any:
        if isinstance(term, NamedNode):
            return self._from_uri(term.value)
        if isinstance(term, Literal):
            if term.datatype == XSD_INT:
                return int(term.value)
            if term.datatype == XSD_BOOL:
                return term.value.lower() == "true"
            return term.value
        return str(term)

    def _slug(texto: str) -> str:
        texto = unicodedata.normalize("NFKD", str(texto))
        texto = texto.encode("ascii", "ignore").decode("ascii")  # quita acentos
        texto = re.sub(r"[^A-Za-z0-9_.-]+", "-", texto).strip("-")
        return texto.lower()

    def guardar_cartucho_normativo(self, doc: DocumentoNormativoCompilado) -> str:
        cartucho_id = f"{doc.fuente.ordenamiento}_{doc.fuente.articulo}".replace("-", "_").replace("/", "_")
        cartucho_uri = NamedNode(f"{BASE_NS}cartucho/{quote(str(cartucho_id), safe='')}")

        self.store.update(
            f"DELETE WHERE {{ GRAPH <{self.tbox_graph.value}> {{ <{cartucho_uri.value}> <{BASE_NS}meta#astJson> ?old }} }}"
        )
        self.store.add(
            Quad(
                cartucho_uri,
                NamedNode(f"{BASE_NS}meta#astJson"),
                Literal(doc.model_dump_json()),
                self.tbox_graph,
            )
        )
        for regla in doc.reglas:
            r_uri = NamedNode(f"{BASE_NS}regla/{regla.rule_id}")
            self.store.add(Quad(r_uri, self._to_uri("rdf:type"), self._to_uri("legal:ReglaJuridica"), self.tbox_graph))
            self.store.add(Quad(r_uri, NamedNode(f"{BASE_NS}meta#modalidad"), Literal(regla.modalidad.value), self.tbox_graph))
            self.store.add(Quad(r_uri, NamedNode(f"{BASE_NS}meta#descripcion"), Literal(regla.descripcion), self.tbox_graph))

        return cartucho_id

    def obtener_cartuchos_activos(self) -> List[DocumentoNormativoCompilado]:
        query = f"""
        SELECT ?json WHERE {{
            GRAPH <{self.tbox_graph.value}> {{
                ?c <{BASE_NS}meta#astJson> ?json .
            }}
        }}
        """
        documentos = []
        for row in self.store.query(query):
            documentos.append(DocumentoNormativoCompilado.model_validate_json(row["json"].value))
        return documentos

    def guardar_hechos_tenant(self, tenant_id: str, hechos: List[HechoCliente], es_inferido: bool = False):
        sufijo = "inferred" if es_inferido else "facts"
        grafo = NamedNode(f"urn:tenant:{tenant_id}:{sufijo}")
        for h in hechos:
            s = self._to_uri(h.sujeto)
            p = self._to_uri(h.propiedad)
            o = self._valor_a_termino_rdf(h.propiedad, h.valor)
            self.store.add(Quad(s, p, o, grafo))

    def limpiar_inferencias_tenant(self, tenant_id: str):
        grafo_inf = f"urn:tenant:{tenant_id}:inferred"
        self.store.update(f"CLEAR SILENT GRAPH <{grafo_inf}>")

    def obtener_hechos_tenant(self, tenant_id: str) -> List[HechoCliente]:
        grafo_facts = f"urn:tenant:{tenant_id}:facts"
        query = f"SELECT ?s ?p ?o WHERE {{ GRAPH <{grafo_facts}> {{ ?s ?p ?o . }} }}"
        hechos = []
        for row in self.store.query(query):
            hechos.append(
                HechoCliente(
                    sujeto=self._from_uri(row["s"].value),
                    propiedad=self._from_uri(row["p"].value),
                    valor=self._termino_rdf_a_valor(row["o"]),
                )
            )
        return hechos

    def listar_tenants_activos(self) -> List[str]:
        query = "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }"
        tenants = set()
        for row in self.store.query(query):
            g_uri = row["g"].value
            if g_uri.startswith("urn:tenant:") and g_uri.endswith(":facts"):
                tenants.add(g_uri.split(":")[2])
        return sorted(list(tenants))

    def exportar_grafo_visual(self, tenant_id: str) -> Dict[str, Any]:
        nodos: Dict[str, Dict[str, Any]] = {}
        aristas: List[Dict[str, Any]] = []

        for tipo, sufijo in [("declarado", "facts"), ("inferido", "inferred")]:
            g_uri = f"urn:tenant:{tenant_id}:{sufijo}"
            query = f"SELECT ?s ?p ?o WHERE {{ GRAPH <{g_uri}> {{ ?s ?p ?o }} }}"
            for idx, row in enumerate(self.store.query(query)):
                s_id = self._from_uri(row["s"].value)
                p_label = self._from_uri(row["p"].value)
                o_val = self._termino_rdf_a_valor(row["o"])

                nodos.setdefault(s_id, {"id": s_id, "label": s_id, "atributos": {}})

                if isinstance(row["o"], NamedNode) and row["p"].value != f"{PREFIX_MAP['rdf']}type":
                    o_id = str(o_val)
                    nodos.setdefault(o_id, {"id": o_id, "label": o_id, "atributos": {}})
                    aristas.append({
                        "id": f"{tipo}_{idx}_{s_id}_{o_id}",
                        "source": s_id,
                        "target": o_id,
                        "label": p_label,
                        "origen": tipo,
                    })
                else:
                    nodos[s_id]["atributos"][p_label] = {"valor": o_val, "origen": tipo}

        return {"tenant_id": tenant_id, "nodes": list(nodos.values()), "edges": aristas}


db = MotorOntologicoStore()
motor_asp = CompiladorJuridicoASP()
ingestor_sat = IngestorFiscalAutonomo()
motor_abductivo = MotorAbductivoJuridico()
analizador_bc = AnalizadorPropiedadEfectiva(umbral_control_pct=15.0)


def ejecutar_ciclo_reactivo(tenant_id: str, fecha_eval: Optional[date] = None) -> DictamenJuridico:
    cartuchos = db.obtener_cartuchos_activos()
    hechos = db.obtener_hechos_tenant(tenant_id)

    if not cartuchos or not hechos:
        return DictamenJuridico(
            fecha_evaluacion=fecha_eval or date.today(),
            hechos_inferidos=[],
            reglas_activadas=[],
            reglas_derrotadas=[],
            eventos_automatizacion=[],
        )

    dictamen = motor_asp.evaluar_caso(
        documentos=cartuchos,
        hechos_cliente=hechos,
        fecha_evaluacion=fecha_eval,
    )

    db.limpiar_inferencias_tenant(tenant_id)
    db.guardar_hechos_tenant(tenant_id, dictamen.hechos_inferidos, es_inferido=True)
    return dictamen


vigilante_dof = VigilanteDOFAutonomo(db, BASE_NS, ejecutar_ciclo_reactivo)


def _cargar_cartuchos_iniciales():
    carpeta = Path(__file__).parent / "cartuchos"
    if not carpeta.exists():
        return
    for archivo in sorted(carpeta.glob("*.json")):
        doc = DocumentoNormativoCompilado.model_validate_json(archivo.read_text(encoding="utf-8"))
        cid = db.guardar_cartucho_normativo(doc)
        logger.info(f"Cartucho normativo cargado: {cid}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _cargar_cartuchos_iniciales()
    iniciar_worker_dof(vigilante_dof)
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(
    title="LexEngine MX — Motor Ontológico Jurídico",
    version="1.0.0",
    description="API neuro-simbólica para auditoría y cumplimiento normativo automatizado.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SolicitudTextoNormativo(BaseModel):
    texto_crudo: str
    metadatos_dof: str
    reevaluar_despachos: bool = True


class SolicitudSimulacion(BaseModel):
    meta: HechoCliente
    costos_retiro: Dict[str, int] = {
        "corporativo:esSocioDe": 10,
        "fiscal:actividad": 3,
    }
    costos_adicion: Dict[str, int] = {
        "fiscal:actividad": 2,
    }


@app.get("/api/v1/health")
def health_check():
    return {
        "status": "ok",
        "cartuchos_activos": len(db.obtener_cartuchos_activos()),
        "tenants_activos": db.listar_tenants_activos(),
    }


@app.post("/api/v1/normas/compilar-texto")
def compilar_norma_desde_texto(payload: SolicitudTextoNormativo):
    extractor = ExtractorNormativoAutonomo()
    resultado = extractor.extraer_articulo(payload.texto_crudo, payload.metadatos_dof)
    cartucho_id = db.guardar_cartucho_normativo(resultado.documento)

    alertas_globales = {}
    if payload.reevaluar_despachos:
        for tid in db.listar_tenants_activos():
            dictamen = ejecutar_ciclo_reactivo(tid)
            if dictamen.eventos_automatizacion:
                alertas_globales[tid] = dictamen.eventos_automatizacion

    return {
        "cartucho_id": cartucho_id,
        "predicados_nuevos_descubiertos": resultado.predicados_nuevos,
        "reglas_compiladas": len(resultado.documento.reglas),
        "eventos_disparados_por_reforma": alertas_globales,
    }

@app.post("/api/v1/despachos/{tenant_id}/calcular-pension")
def calcular_pension_y_evaluar(tenant_id: str, payload: SolicitudProrrateoPension):
    resultados, hechos_nuevos = calculador_pension.prorratear(
        deudor_id=payload.deudor_id,
        ingreso_neto_mxn=payload.ingreso_neto_mxn,
        porcentaje_embargable=payload.porcentaje_embargable,
        acreedores=payload.acreedores,
    )
    if hechos_nuevos:
        db.guardar_hechos_tenant(tenant_id, hechos_nuevos, es_inferido=False)
    dictamen = ejecutar_ciclo_reactivo(tenant_id)
    return {
        "prorrateo": resultados,
        "dictamen_juridico": dictamen,
    }


@app.post("/api/v1/normas/cargar-json")
def cargar_cartucho_precompilado(documento: DocumentoNormativoCompilado):
    cartucho_id = db.guardar_cartucho_normativo(documento)
    return {"status": "ok", "cartucho_id": cartucho_id}


@app.post("/api/v1/worker/ejecutar-vigilancia-dof")
def forzar_barrido_dof(fecha: Optional[date] = None):
    return vigilante_dof.ejecutar_vigilancia_diaria(fecha_objetivo=fecha)


@app.post("/api/v1/despachos/{tenant_id}/ingestar-sat")
async def ingestar_cfdi_y_evaluar(
    tenant_id: str,
    rfc: str = Form(...),
    ejercicio_fiscal: int = Form(...),
    es_ejercicio_anterior: bool = Form(True),
    archivos: List[UploadFile] = File(...),
):
    xmls_bytes: List[bytes] = []
    for archivo in archivos:
        contenido = await archivo.read()
        nombre = (archivo.filename or "").lower()
        if nombre.endswith(".xml"):
            xmls_bytes.append(contenido)
        elif nombre.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(contenido), "r") as zf:
                for entry in zf.namelist():
                    if entry.lower().endswith(".xml"):
                        xmls_bytes.append(zf.read(entry))

    if not xmls_bytes:
        raise HTTPException(status_code=400, detail="No se encontraron archivos XML válidos.")

    resumen = ingestor_sat.ingestar_lote_cfdi(
        rfc_objetivo=rfc,
        ejercicio_fiscal=ejercicio_fiscal,
        archivos_xml=xmls_bytes,
        es_ejercicio_anterior=es_ejercicio_anterior,
    )
    db.guardar_hechos_tenant(tenant_id, resumen.hechos_generados, es_inferido=False)
    dictamen = ejecutar_ciclo_reactivo(tenant_id)

    return {
        "resumen_fiscal": resumen,
        "dictamen_juridico": dictamen,
    }


@app.post("/api/v1/despachos/{tenant_id}/ingestar-pdf")
async def ingestar_pdf_corporativo_y_evaluar(
    tenant_id: str,
    rfc_titular: str = Form(...),
    archivo_pdf: UploadFile = File(...),
):
    contenido = await archivo_pdf.read()
    tmp_path = Path(tempfile.gettempdir()) / f"lexengine_{uuid4().hex}.pdf"

    try:
        tmp_path.write_bytes(contenido)
        hechos_pdf = ingestor_sat.ingestar_documento_pdf(tmp_path, rfc_titular)
    finally:
        tmp_path.unlink(missing_ok=True)

    db.guardar_hechos_tenant(tenant_id, hechos_pdf, es_inferido=False)
    dictamen = ejecutar_ciclo_reactivo(tenant_id)

    return {
        "hechos_extraidos": hechos_pdf,
        "dictamen_juridico": dictamen,
        "legal": f"{BASE_NS}legal#",
        "meta": f"{BASE_NS}meta#",
        "fiscal": f"{BASE_NS}fiscal#",
        "corporativo": f"{BASE_NS}corporativo#",
        "laboral": f"{BASE_NS}laboral#",
        "pld": f"{BASE_NS}pld#",
        "familiar": f"{BASE_NS}familiar#",
    }


@app.post(
    "/api/v1/despachos/{tenant_id}/simular-regularizacion",
    response_model=PlanContrafactual,
)
def simular_ruta_regularizacion(tenant_id: str, payload: SolicitudSimulacion):
    cartuchos = db.obtener_cartuchos_activos()
    hechos = db.obtener_hechos_tenant(tenant_id)
    return motor_abductivo.calcular_ruta_minima(
        documentos=cartuchos,
        hechos_cliente=hechos,
        meta=payload.meta,
        costos_retiro=payload.costos_retiro,
        costos_adicion=payload.costos_adicion,
    )


@app.post(
    "/api/v1/despachos/{tenant_id}/beneficiario-controlador",
    response_model=List[BeneficiarioControladorDetectado],
)
def analizar_cadena_corporativa(
    tenant_id: str, relaciones: List[ParticipacionSocietaria]
):
    try:
        detectados, hechos_bc = analizador_bc.calcular_beneficiarios_controladores(relaciones)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if hechos_bc:
        db.guardar_hechos_tenant(tenant_id, hechos_bc, es_inferido=False)
        ejecutar_ciclo_reactivo(tenant_id)
    return detectados


@app.get("/api/v1/despachos/{tenant_id}/grafo")
def obtener_grafo_explicabilidad(tenant_id: str):
    return db.exportar_grafo_visual(tenant_id)

