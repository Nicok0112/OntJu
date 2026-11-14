from typing import List, Tuple
from pydantic import BaseModel, Field
from compiler import HechoCliente


class AcreedorAlimentario(BaseModel):
    acreedor_id: str
    peso_necesidad: float = Field(
        default=1.0,
        gt=0,
        description="Ponderación de necesidad (1.0 estándar, 1.5 discapacidad o gastos médicos especiales)",
    )


class ResultadoProrrateo(BaseModel):
    acreedor_id: str
    monto_mensual_mxn: int
    porcentaje_ingreso: int


class CalculadorPensionAlimenticia:
    def prorratear(
        self,
        deudor_id: str,
        ingreso_neto_mxn: int,
        porcentaje_embargable: float,
        acreedores: List[AcreedorAlimentario],
    ) -> Tuple[List[ResultadoProrrateo], List[HechoCliente]]:
        if not acreedores or ingreso_neto_mxn <= 0:
            return [], []

        bolsa_total = ingreso_neto_mxn * (porcentaje_embargable / 100.0)
        suma_pesos = sum(a.peso_necesidad for a in acreedores)

        resultados: List[ResultadoProrrateo] = []
        hechos_grafo: List[HechoCliente] = []

        for acr in acreedores:
            proporcion = acr.peso_necesidad / suma_pesos
            monto = int(round(bolsa_total * proporcion))
            pct = int(round((monto / ingreso_neto_mxn) * 100))

            resultados.append(
                ResultadoProrrateo(
                    acreedor_id=acr.acreedor_id,
                    monto_mensual_mxn=monto,
                    porcentaje_ingreso=pct,
                )
            )
            hechos_grafo.extend([
                HechoCliente(
                    sujeto=deudor_id.lower(),
                    propiedad="familiar:pensionAsignadaA",
                    valor=acr.acreedor_id.lower(),
                ),
                HechoCliente(
                    sujeto=acr.acreedor_id.lower(),
                    propiedad="familiar:pensionMensualMXN",
                    valor=monto,
                ),
            ])

        return resultados, hechos_grafo