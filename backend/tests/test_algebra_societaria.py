from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from math_engines.ownership_algebra import AnalizadorPropiedadEfectiva, ParticipacionSocietaria


def test_participacion_indirecta_y_ciclica():
    relaciones = [
        ParticipacionSocietaria(socio_id="ana", sociedad_id="holding_sa", porcentaje_directo=40.0, socio_es_persona_fisica=True),
        ParticipacionSocietaria(socio_id="holding_sa", sociedad_id="operadora_sa", porcentaje_directo=50.0, socio_es_persona_fisica=False),
        ParticipacionSocietaria(socio_id="operadora_sa", sociedad_id="holding_sa", porcentaje_directo=10.0, socio_es_persona_fisica=False),
    ]
    analizador = AnalizadorPropiedadEfectiva(umbral_control_pct=15.0)
    detectados, hechos = analizador.calcular_beneficiarios_controladores(relaciones)

    mapa = {d.sociedad_objetivo_id: d for d in detectados}
    # 0.40 * 0.50 / (1 - 0.50 * 0.10) = 0.20 / 0.95 = 21.05%
    assert mapa["operadora_sa"].porcentaje_total_efectivo == 21.05
    assert mapa["operadora_sa"].supera_umbral_legal is True
    assert len(hechos) == 4
