
const DICCIONARIO_RELACIONES: Record<string, string> = {
  esSocioDe: "Es socio / accionista de",
  esBeneficiarioControladorDe: "Beneficiario controlador de",
  deudorAlimentarioDe: "Deudor alimentario de",
  esHijoDe: "Es hijo(a) de",
  emisorDe: "Emisor de CFDI",
  receptorDe: "Receptor de CFDI",
  pensionAsignadaA: "Pensión asignada a",
};

const DICCIONARIO_ATRIBUTOS: Record<string, string> = {
  excluidoRESICO: "Excluido de RESICO",
  tieneDiscapacidad: "Tiene discapacidad",
subsistePorEstudiosODiscapacidad: "Subsiste por estudios o discapacidad",
pensionMensualMXN: "Pensión mensual (MXN)",
  tipoSociedad: "Tipo de sociedad",
  porcentajeControlEfectivo: "Control efectivo (%)",
  ingresosEjercicioAnterior: "Ingresos ejercicio anterior",
  regimenFiscal: "Régimen fiscal",
  actividad: "Actividad económica",
  edadAnios: "Edad (años)",
  estudiaGradoAcorde: "Estudia grado acorde",
  obligacionSuspendida: "Obligación suspendida",
};

const DICCIONARIO_EVENTOS: Record<
  string,
  { titulo: string; accionSugerida: string; severidad: "critica" | "preventiva" }
> = {
  ALERTA_CAUSAL_SALIDA_RESICO: {
    titulo: "Incompatibilidad con RESICO detectada",
    accionSugerida:
      "El contribuyente no puede tributar en el Régimen Simplificado de Confianza mientras mantenga participación como socio o accionista en una persona moral.",
    severidad: "critica",
  },
  NOTIFICAR_OBLIGACION_ALIMENTARIA: {
    titulo: "Obligación alimentaria vigente",
    accionSugerida: "Existe vínculo filial activo que exige ministración de alimentos.",
    severidad: "preventiva",
  },
  ALERTA_CAUSAL_CESE_ALIMENTOS: {
    titulo: "Causal de cese de pensión alimenticia",
    accionSugerida: "El acreedor alcanzó la mayoría de edad sin causal de subsistencia activa.",
    severidad: "critica",
  },
};

const DICCIONARIO_REGLAS: Record<string, string> = {
  LISR_113E_ELEGIBILIDAD: "Elegibilidad General RESICO (Art. 113-E)",
  LISR_113E_EXCLUSION_SOCIO: "Exclusión por ser Socio de Persona Moral (Art. 113-E Fracc. I)",
  FAM_303_OBLIGACION_ALIMENTOS: "Obligación Alimentaria entre Padres e Hijos (Art. 303)",
  FAM_CONTRAEXCEPCION_ESTUDIOS: "Contra-excepción por Estudios Acordes (Art. 320 CC)",
FAM_CONTRAEXCEPCION_DISCAPACIDAD: "Contra-excepción por Discapacidad (Art. 320 CC)",
  FAM_320_CESE_MAYORIA_EDAD: "Cese por Mayoría de Edad (Art. 320 Fracc. II)",
};

export function limpiarPropiedad(raw: string): string {
  const sinPrefijo = raw.includes(":") ? raw.split(":")[1] : raw;
  return (
    DICCIONARIO_RELACIONES[sinPrefijo] ||
    DICCIONARIO_ATRIBUTOS[sinPrefijo] ||
    sinPrefijo.replace(/([A-Z])/g, " $1").replace(/^./, (s) => s.toUpperCase())
  );
}

export function formatearValor(valor: unknown): string {
  if (typeof valor === "boolean") return valor ? "Sí" : "No";
  if (typeof valor === "number") return valor.toLocaleString("es-MX");
  if (typeof valor === "string") {
    return valor.replace(/_/g, " ");
  }
  return String(valor);
}

export function formatearNombreEntidad(id: string): {
  titulo: string;
  tipo: "Persona Física" | "Persona Moral" | "Entidad / Documento";
} {
  const limpio = id.replace(/^rfc_/i, "").toUpperCase();
  if (/^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$/.test(limpio)) {
    return { titulo: limpio, tipo: "Persona Física" };
  }
  if (/^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$/.test(limpio)) {
    return { titulo: limpio, tipo: "Persona Moral" };
  }
  return {
    titulo: id.replace(/_/g, " ").toUpperCase(),
    tipo: "Entidad / Documento",
  };
}

export function traducirEvento(eventoId: string) {
  return (
    DICCIONARIO_EVENTOS[eventoId] || {
      titulo: eventoId.replace(/_/g, " "),
      accionSugerida: "Revise el fundamento jurídico aplicado en este expediente.",
      severidad:
        eventoId.startsWith("BLOQUEAR_") || eventoId.startsWith("ALERTA_")
          ? ("critica" as const)
          : ("preventiva" as const),
    }
  );
}

export function traducirRegla(ruleId: string): string {
  return DICCIONARIO_REGLAS[ruleId] || ruleId.replace(/_/g, " ");
}