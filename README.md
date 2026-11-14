# LexEngine MX — Motor Ontológico Jurídico Neuro-Simbólico

Plataforma B2B SaaS para auditoría normativa automatizada, diagnóstico de elegibilidad fiscal (RESICO / LISR), prevención de lavado de dinero (LFPIORPI), análisis de Beneficiario Controlador (Art. 32-B Quáter CFF) y simulación contrafactual sobre el sistema jurídico mexicano.

## Arquitectura

- **Meta-Ontología (`backend/schema.py`):** Contrato Pydantic v2 / AST lógico-deóntico con soporte para modalidad deóntica, dualidad de Hohfeld, vigencia temporal y derrotabilidad.
- **Compilador Determinista (`backend/compiler.py`):** Traduce reglas jurídicas a **Answer Set Programming (Clingo)** con negación por defecto (`not`) para resolver excepciones y contra-excepciones sin inconsistencias.
- **Extractor Normativo (`backend/extractor.py`):** Pipeline con Gemini Structured Outputs + anclaje de vocabulario + validación de seguridad de variables.
- **Ingestor Fiscal (`backend/ingestor.py`):** Procesamiento determinista de lotes XML/ZIP de **CFDI 4.0** (redondeo Art. 20 CFF, notas de crédito, conversión de divisas, deduplicación por UUID) y extracción estructurada desde PDFs (CSF / Actas Constitutivas).
- **Extensiones Matemáticas (`backend/math_engines/`):**
  - `abduction.py`: Razonamiento contrafactual (`#minimize` en Clingo) para hallar la ruta mínima de regularización legal.
  - `ownership_algebra.py`: Clausura transitiva matricial $T = A(I - A)^{-1}$ en NumPy para detectar control efectivo multinivel y participaciones cruzadas.
- **Worker Autónomo (`backend/worker.py`):** Vigilancia diaria programada sobre el SIDOF / Diario Oficial de la Federación con versionado temporal y análisis de impacto retroactivo.
- **Frontend Explicable (`frontend/`):** Dashboard en Next.js + TypeScript + React Flow para inspeccionar el grafo de hechos declarados vs. inferidos y generar dictámenes imprimibles en PDF.

## Arranque Rápido

### Opción 1: Docker Compose (Recomendado)
```bash
cp .env.example .env
# Edita .env y agrega tu GEMINI_API_KEY
docker-compose up --build
```
- Frontend: `http://localhost:3000`
- API & Swagger Docs: `http://localhost:8000/docs`

### Opción 2: Ejecución Local Manual

**1. Backend (Python 3.11+):**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
export GEMINI_API_KEY="tu_api_key"
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

**2. Frontend (Node.js 20+):**
```bash
cd frontend
npm install
npm run dev
```

**3. Ejecutar Suite de Pruebas:**
```bash
cd backend
pytest -v
```
