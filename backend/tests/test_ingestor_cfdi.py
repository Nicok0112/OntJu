from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestor import IngestorFiscalAutonomo


XML_INGRESO = b'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                  xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
                  Version="4.0" Fecha="2025-06-15T12:00:00"
                  SubTotal="100000.40" Descuento="0.00" Moneda="MXN"
                  TipoDeComprobante="I">
  <cfdi:Emisor Rfc="GOMA850412HDF" Nombre="ANA GOMEZ" RegimenFiscal="626"/>
  <cfdi:Receptor Rfc="XAXX010101000" Nombre="PUBLICO GENERAL" UsoCFDI="S01"/>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="11111111-1111-1111-1111-111111111111"/>
  </cfdi:Complemento>
</cfdi:Comprobante>'''

XML_EGRESO = b'''<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                  xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital"
                  Version="4.0" Fecha="2025-07-01T10:00:00"
                  SubTotal="10000.00" Descuento="0.00" Moneda="MXN"
                  TipoDeComprobante="E">
  <cfdi:Emisor Rfc="GOMA850412HDF" Nombre="ANA GOMEZ" RegimenFiscal="626"/>
  <cfdi:Receptor Rfc="XAXX010101000" Nombre="PUBLICO GENERAL" UsoCFDI="G02"/>
  <cfdi:Complemento>
    <tfd:TimbreFiscalDigital Version="1.1" UUID="22222222-2222-2222-2222-222222222222"/>
  </cfdi:Complemento>
</cfdi:Comprobante>'''


def test_deduplicacion_y_redondeo_art20():
    ingestor = IngestorFiscalAutonomo()
    resumen = ingestor.ingestar_lote_cfdi(
        rfc_objetivo="GOMA850412HDF",
        ejercicio_fiscal=2025,
        archivos_xml=[XML_INGRESO, XML_INGRESO, XML_EGRESO],
    )
    assert resumen.cfdis_procesados == 2
    assert resumen.cfdis_duplicados_ignorados == 1
    assert resumen.ingresos_netos_mxn == 90000
