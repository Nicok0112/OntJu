from typing import List, Set
import numpy as np
from pydantic import BaseModel, Field

from compiler import HechoCliente


class ParticipacionSocietaria(BaseModel):
    socio_id: str
    sociedad_id: str
    porcentaje_directo: float = Field(..., gt=0, le=100, description="Porcentaje de 0 a 100")
    socio_es_persona_fisica: bool = True


class BeneficiarioControladorDetectado(BaseModel):
    persona_fisica_id: str
    sociedad_objetivo_id: str
    porcentaje_directo: float
    porcentaje_indirecto: float
    porcentaje_total_efectivo: float
    supera_umbral_legal: bool


class AnalizadorPropiedadEfectiva:
    """
    Resuelve estructuras corporativas multinivel y participaciones cruzadas
    mediante la serie de Neumann T = A * (I - A)^(-1).
    """

    def __init__(self, umbral_control_pct: float = 15.0):
        self.umbral_control = umbral_control_pct / 100.0

    def calcular_beneficiarios_controladores(
        self, relaciones: List[ParticipacionSocietaria]
    ) -> tuple[List[BeneficiarioControladorDetectado], List[HechoCliente]]:
        if not relaciones:
            return [], []

        entidades: Set[str] = set()
        personas_fisicas: Set[str] = set()
        sociedades: Set[str] = set()

        for r in relaciones:
            entidades.add(r.socio_id)
            entidades.add(r.sociedad_id)
            sociedades.add(r.sociedad_id)
            if r.socio_es_persona_fisica:
                personas_fisicas.add(r.socio_id)
            else:
                sociedades.add(r.socio_id)

        nodos = sorted(list(entidades))
        idx = {nodo: i for i, nodo in enumerate(nodos)}
        n = len(nodos)

        A = np.zeros((n, n), dtype=np.float64)
        for r in relaciones:
            A[idx[r.socio_id], idx[r.sociedad_id]] += r.porcentaje_directo / 100.0

        if np.any(A.sum(axis=0) > 1.0001):
            raise ValueError(
                "Inconsistencia societaria: una persona moral tiene más del 100% de acciones asignadas."
            )

        I = np.eye(n, dtype=np.float64)
        T = np.linalg.solve(I - A, A)

        detectados: List[BeneficiarioControladorDetectado] = []
        hechos_grafo: List[HechoCliente] = []

        for pf in sorted(personas_fisicas):
            i = idx[pf]
            for soc in sorted(sociedades):
                j = idx[soc]
                total = float(T[i, j])
                if total <= 1e-6:
                    continue

                directo = float(A[i, j])
                indirecto = max(0.0, total - directo)
                es_beneficiario = total >= (self.umbral_control - 1e-6)

                detectados.append(
                    BeneficiarioControladorDetectado(
                        persona_fisica_id=pf,
                        sociedad_objetivo_id=soc,
                        porcentaje_directo=round(directo * 100, 2),
                        porcentaje_indirecto=round(indirecto * 100, 2),
                        porcentaje_total_efectivo=round(total * 100, 2),
                        supera_umbral_legal=es_beneficiario,
                    )
                )

                if es_beneficiario:
                    nodo_relacion = f"bc_{pf}_{soc}"
                    hechos_grafo.extend([
                        HechoCliente(
                            sujeto=pf,
                            propiedad="corporativo:esBeneficiarioControladorDe",
                            valor=soc,
                        ),
                        HechoCliente(
                            sujeto=nodo_relacion,
                            propiedad="corporativo:porcentajeControlEfectivo",
                            valor=int(round(total * 100)),
                        ),
                    ])

        return detectados, hechos_grafo
