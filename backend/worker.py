import logging
import re
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Set
import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup
from pyoxigraph import Literal, NamedNode, Quad

from extractor import ExtractorNormativoAutonomo
from schema import DocumentoNormativoCompilado

logger = logging.getLogger("lexengine.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ORDENAMIENTOS_VIGILADOS: List[str] = [
    "ley del impuesto sobre la renta",
    "código fiscal de la federación",
    "resolución miscelánea fiscal",
    "prevención e identificación de operaciones con recursos de procedencia ilícita",
    "unidad de medida y actualización",
    "ley federal del trabajo",
]


class VigilanteDOFAutonomo:
    def __init__(
        self,
        store_db,
        base_ns: str,
        callback_reevaluar: Callable,
    ):
        self.db = store_db
        self.base_ns = base_ns
        self.ejecutar_ciclo_reactivo = callback_reevaluar
        self.dof_log_graph = NamedNode("urn:legal:dof_log")
        self.extractor = ExtractorNormativoAutonomo()
        self.http_client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            verify=False,  # Evita fallo por Hostname mismatch en www.dof.gob.mx
            headers={"User-Agent": "Mozilla/5.0 (compatible; LexEngineMX/1.0)"},
        )

    def _nota_ya_procesada(self, codigo_nota: str) -> bool:
        nota_uri = f"{self.base_ns}dof/nota_{codigo_nota}"
        query = f"ASK {{ GRAPH <{self.dof_log_graph.value}> {{ <{nota_uri}> ?p ?o }} }}"
        return bool(self.db.store.query(query))

    def _marcar_nota_procesada(self, codigo_nota: str, titulo: str, fecha_pub: date):
        nota_uri = NamedNode(f"{self.base_ns}dof/nota_{codigo_nota}")
        self.db.store.add(
            Quad(
                nota_uri,
                NamedNode(f"{self.base_ns}meta#titulo"),
                Literal(titulo[:300]),
                self.dof_log_graph,
            )
        )
        self.db.store.add(
            Quad(
                nota_uri,
                NamedNode(f"{self.base_ns}meta#fechaPublicacion"),
                Literal(fecha_pub.isoformat()),
                self.dof_log_graph,
            )
        )

    def _obtener_sumario_diario(self, fecha: date) -> List[Dict[str, str]]:
        fecha_sidof = fecha.strftime("%d-%m-%Y")
        url_api = f"https://sidof.segob.gob.mx/notas/{fecha_sidof}"
        notas: List[Dict[str, str]] = []

        try:
            resp = self.http_client.get(url_api)
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                data = resp.json()
                for item in data.get("Notas", []):
                    notas.append({
                        "codigo": str(item.get("codNota", "")).strip(),
                        "titulo": str(item.get("titulo", "")).strip(),
                    })
                if notas:
                    return notas
        except Exception as exc:
            logger.warning(f"API SIDOF no disponible ({exc}), usando respaldo HTML DOF.")

        url_html = (
            f"https://www.dof.gob.mx/index_detalle.php?"
            f"year={fecha.year}&month={fecha.month:02d}&day={fecha.day:02d}"
        )
        resp = self.http_client.get(url_html)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for enlace in soup.find_all("a", href=re.compile(r"nota_detalle\.php\?codigo=")):
            href = enlace.get("href", "")
            match = re.search(r"codigo=(\d+)", href)
            if match:
                notas.append({
                    "codigo": match.group(1),
                    "titulo": enlace.get_text(" ", strip=True),
                })
        return notas

    def _descargar_texto_decreto(self, codigo_nota: str, fecha: date) -> str:
        fecha_slash = fecha.strftime("%d/%m/%Y")
        url = f"https://www.dof.gob.mx/nota_detalle.php?codigo={codigo_nota}&fecha={fecha_slash}"
        resp = self.http_client.get(url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        contenedor = soup.find("div", id="DivDetalleNota") or soup.body
        for tag in contenedor(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        lineas = [l.strip() for l in contenedor.get_text("\n").splitlines() if l.strip()]
        return "\n".join(lineas)

    @staticmethod
    def _es_relevante(titulo: str) -> bool:
        t_lower = titulo.lower()
        return any(ley in t_lower for ley in ORDENAMIENTOS_VIGILADOS)

    def _cerrar_vigencia_version_anterior(self, nuevo_doc: DocumentoNormativoCompilado):
        cartuchos_actuales = self.db.obtener_cartuchos_activos()
        fecha_cierre = nuevo_doc.fuente.vigente_desde - timedelta(days=1)

        for antiguo in cartuchos_actuales:
            mismo_ordenamiento = (
                antiguo.fuente.ordenamiento.upper() == nuevo_doc.fuente.ordenamiento.upper()
            )
            mismo_articulo = antiguo.fuente.articulo == nuevo_doc.fuente.articulo
            esta_abierto = antiguo.fuente.vigente_hasta is None

            if mismo_ordenamiento and mismo_articulo and esta_abierto:
                antiguo.fuente.vigente_hasta = fecha_cierre
                cartucho_id = f"{antiguo.fuente.ordenamiento}_{antiguo.fuente.articulo}".replace("-", "_")
                cartucho_uri = f"{self.base_ns}cartucho/{cartucho_id}"
                self.db.store.update(
                    f"""
                    DELETE WHERE {{ GRAPH <{self.db.tbox_graph.value}> {{ <{cartucho_uri}> <{self.base_ns}meta#astJson> ?old }} }};
                    INSERT DATA {{ GRAPH <{self.db.tbox_graph.value}> {{ <{cartucho_uri}> <{self.base_ns}meta#astJson> {Literal(antiguo.model_dump_json())} }} }}
                    """
                )
                logger.info(
                    f"Vigencia cerrada para {cartucho_id} hasta {fecha_cierre.isoformat()} por reforma."
                )

    def ejecutar_vigilancia_diaria(self, fecha_objetivo: Optional[date] = None) -> Dict:
        fecha = fecha_objetivo or date.today()
        logger.info(f"Iniciando vigilancia normativa del DOF para {fecha.isoformat()}...")

        notas_dia = self._obtener_sumario_diario(fecha)
        reformas_compiladas: List[str] = []

        for nota in notas_dia:
            codigo = nota["codigo"]
            titulo = nota["titulo"]

            if not codigo or self._nota_ya_procesada(codigo):
                continue

            if not self._es_relevante(titulo):
                self._marcar_nota_procesada(codigo, titulo, fecha)
                continue

            logger.info(f"Publicación relevante detectada [DOF {codigo}]: {titulo}")
            texto_decreto = self._descargar_texto_decreto(codigo, fecha)

            metadatos = (
                f"Publicación DOF código {codigo} | Fecha de publicación: {fecha.isoformat()} | "
                f"Título: {titulo} | Jurisdicción: FEDERAL"
            )

            try:
                resultado = self.extractor.extraer_articulo(
                    texto_crudo=texto_decreto[:28000],
                    metadatos_dof=metadatos,
                )
                self._cerrar_vigencia_version_anterior(resultado.documento)
                cid = self.db.guardar_cartucho_normativo(resultado.documento)
                reformas_compiladas.append(cid)
                self._marcar_nota_procesada(codigo, titulo, fecha)
                logger.info(f"Cartucho '{cid}' actualizado automáticamente en la TBox.")
            except Exception as exc:
                logger.error(f"Fallo al compilar nota DOF {codigo}: {exc}")

        impactos_por_despacho: Dict[str, List[dict]] = {}
        if reformas_compiladas:
            for tenant_id in self.db.listar_tenants_activos():
                dictamen_previo = self.ejecutar_ciclo_reactivo(
                    tenant_id, fecha_eval=fecha - timedelta(days=1)
                )
                eventos_previos: Set[tuple] = {
                    (e.evento, e.sujeto, e.rule_id) for e in dictamen_previo.eventos_automatizacion
                }

                dictamen_nuevo = self.ejecutar_ciclo_reactivo(tenant_id, fecha_eval=fecha)
                eventos_nuevos: Set[tuple] = {
                    (e.evento, e.sujeto, e.rule_id) for e in dictamen_nuevo.eventos_automatizacion
                }

                delta_activados = eventos_nuevos - eventos_previos
                delta_revocados = eventos_previos - eventos_nuevos

                if delta_activados or delta_revocados:
                    impactos_por_despacho[tenant_id] = [
                        {
                            "tipo_cambio": "NUEVA_OBLIGACION_O_ALERTA",
                            "evento": ev,
                            "sujeto": suj,
                            "rule_id": rid,
                        }
                        for (ev, suj, rid) in delta_activados
                    ] + [
                        {
                            "tipo_cambio": "ESTATUS_PREVIO_REVOCADO",
                            "evento": ev,
                            "sujeto": suj,
                            "rule_id": rid,
                        }
                        for (ev, suj, rid) in delta_revocados
                    ]
                    self._despachar_notificacion_webhook(tenant_id, impactos_por_despacho[tenant_id])

        return {
            "fecha": fecha.isoformat(),
            "notas_revisadas": len(notas_dia),
            "cartuchos_actualizados": reformas_compiladas,
            "despachos_impactados": impactos_por_despacho,
        }

    def _despachar_notificacion_webhook(self, tenant_id: str, cambios: List[dict]):
        logger.warning(
            f"[ALERTA REFORMA DOF -> Despacho '{tenant_id}'] "
            f"{len(cambios)} cambio(s) de cumplimiento detectado(s): {cambios}"
        )


scheduler = BackgroundScheduler(timezone="America/Mexico_City")


def iniciar_worker_dof(vigilante: VigilanteDOFAutonomo):
    scheduler.add_job(
        vigilante.ejecutar_vigilancia_diaria,
        trigger="cron",
        day_of_week="mon-fri",
        hour=8,
        minute=30,
        id="vigilancia_diaria_dof",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Worker autónomo del DOF iniciado (Lun-Vie 08:30 AM America/Mexico_City).")


if __name__ == "__main__":
    from app import BASE_NS, db, ejecutar_ciclo_reactivo
    vigilante = VigilanteDOFAutonomo(db, BASE_NS, ejecutar_ciclo_reactivo)
    print(vigilante.ejecutar_vigilancia_diaria())

