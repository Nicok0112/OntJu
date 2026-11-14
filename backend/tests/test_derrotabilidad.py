from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compiler import CompiladorJuridicoASP, HechoCliente
from schema import DocumentoNormativoCompilado


def test_regla_excepcion_contraexcepcion_resico():
    cartucho_path = Path(__file__).resolve().parents[1] / "cartuchos" / "lisr_113e.json"
    cartucho = DocumentoNormativoCompilado.model_validate_json(cartucho_path.read_text(encoding="utf-8"))

    hechos = [
        # Ana: califica directo
        HechoCliente(sujeto="ana", propiedad="rdf:type", valor="legal:PersonaFisica"),
        HechoCliente(sujeto="ana", propiedad="fiscal:actividad", valor="PROFESIONAL"),
        HechoCliente(sujeto="ana", propiedad="fiscal:ingresosEjercicioAnterior", valor=1800000),
        # Carlos: socio de S.A. -> excluido
        HechoCliente(sujeto="carlos", propiedad="rdf:type", valor="legal:PersonaFisica"),
        HechoCliente(sujeto="carlos", propiedad="fiscal:actividad", valor="EMPRESARIAL"),
        HechoCliente(sujeto="carlos", propiedad="fiscal:ingresosEjercicioAnterior", valor=2100000),
        HechoCliente(sujeto="carlos", propiedad="corporativo:esSocioDe", valor="tech_sa"),
        HechoCliente(sujeto="tech_sa", propiedad="corporativo:tipoSociedad", valor="SOCIEDAD_ANONIMA"),
        # Sofía: socia de Cooperativa de Producción -> contra-excepción -> SÍ califica
        HechoCliente(sujeto="sofia", propiedad="rdf:type", valor="legal:PersonaFisica"),
        HechoCliente(sujeto="sofia", propiedad="fiscal:actividad", valor="EMPRESARIAL"),
        HechoCliente(sujeto="sofia", propiedad="fiscal:ingresosEjercicioAnterior", valor=1200000),
        HechoCliente(sujeto="sofia", propiedad="corporativo:esSocioDe", valor="coop_cafe"),
        HechoCliente(sujeto="coop_cafe", propiedad="corporativo:tipoSociedad", valor="SOCIEDAD_COOPERATIVA_PRODUCCION"),
        HechoCliente(sujeto="coop_cafe", propiedad="corporativo:soloSociosPersonasFisicas", valor=True),
    ]

    motor = CompiladorJuridicoASP()
    dictamen = motor.evaluar_caso([cartucho], hechos, fecha_evaluacion=date(2026, 5, 1))

    inferidos = {(h.sujeto, h.propiedad): h.valor for h in dictamen.hechos_inferidos}
    assert inferidos[("ana", "fiscal:elegibleRegimen")] == "RESICO"
    assert inferidos[("carlos", "fiscal:excluidoRESICO")] is True
    assert ("carlos", "fiscal:elegibleRegimen") not in inferidos
    assert inferidos[("sofia", "fiscal:elegibleRegimen")] == "RESICO"
