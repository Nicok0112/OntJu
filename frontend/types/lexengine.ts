export interface AtributoNodo {
  valor: string | number | boolean;
  origen: "declarado" | "inferido";
}

export interface NodoGrafoRaw {
  id: string;
  label: string;
  atributos: Record<string, AtributoNodo>;
}

export interface AristaGrafoRaw {
  id: string;
  source: string;
  target: string;
  label: string;
  origen: "declarado" | "inferido";
}

export interface GrafoVisualResponse {
  tenant_id: string;
  nodes: NodoGrafoRaw[];
  edges: AristaGrafoRaw[];
}

export interface ReglaAplicadaInfo {
  rule_id: string;
  sujeto: string;
  cita_legal: string;
  descripcion: string;
  modalidad: "OBLIGATION" | "PROHIBITION" | "PERMISSION" | "EXEMPTION" | "QUALIFICATION";
}

export interface EventoDisparado {
  evento: string;
  sujeto: string;
  rule_id: string;
}

export interface DictamenJuridico {
  fecha_evaluacion: string;
  hechos_inferidos: Array<{ sujeto: string; propiedad: string; valor: unknown }>;
  reglas_activadas: ReglaAplicadaInfo[];
  reglas_derrotadas: Array<[string, string]>;
  eventos_automatizacion: EventoDisparado[];
}

export interface AccionCorrectiva {
  operacion: "RETIRAR_HECHO" | "AGREGAR_HECHO";
  sujeto: string;
  propiedad: string;
  valor: unknown;
  costo_operativo: number;
}

export interface PlanContrafactual {
  meta_deseada: { sujeto: string; propiedad: string; valor: unknown };
  es_alcanzable: boolean;
  costo_total_minimo: number | null;
  acciones_requeridas: AccionCorrectiva[];
}

export interface BeneficiarioControladorDetectado {
  persona_fisica_id: string;
  sociedad_objetivo_id: string;
  porcentaje_directo: number;
  porcentaje_indirecto: number;
  porcentaje_total_efectivo: number;
  supera_umbral_legal: boolean;
}
