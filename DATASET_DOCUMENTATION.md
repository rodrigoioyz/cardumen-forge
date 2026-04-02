# Dataset Técnico: Cardano Aiken Copilot
## Fine-Tuning Documentation — Qwen2.5-Coder-7B-Instruct

---

## 1. Metodología de Creación

### Pipeline de recolección en 2 fases

#### Fase 1 — Scraping y extracción de fuentes

- **Aiken stdlib (GitHub API):** Extracción directa de archivos `.ak` del repositorio `aiken-lang/stdlib` vía PyGithub 2.x. Parser custom para comentarios `///` (triple-slash doc-comments), que constituyen la documentación oficial embebida en el código fuente. 447 funciones documentadas → 915 ejemplos
- **Aiken docs:** Crawler HTTP sobre `aiken-lang.org` con rutas hardcodeadas (28 páginas). El sitio es JS-rendered parcialmente, por lo que se utilizó crawling estático con BeautifulSoup4 + markdownify → 112 ejemplos
- **Hydra docs:** Crawling del sitio Docusaurus de `hydra.family` — 35 páginas de documentación del protocolo L2 → 140 ejemplos
- **CIPs (Cardano Improvement Proposals):** GitHub API sobre `cardano-foundation/CIPs` — 134 documentos markdown incluyendo CIP-1694 (Conway governance), CIP-0057, CIP-0068 → 446 ejemplos
- **Design Patterns:** Repositorio `Anastasia-Labs/design-patterns` — 22 archivos con patrones de producción → 88 ejemplos
- **Hydra Plutus code:** 142 archivos de código del repositorio `input-output-hk/hydra` — contratos reales en uso → 368 ejemplos

#### Fase 2 — Transformación Q&A via Claude API

- Cada chunk de documentación/código fue enviado a Claude con `tool_use` forzado (`tool_choice: {type: "tool", name: "save_examples"}`) para garantizar JSON estructurado válido sin errores de parsing
- Modelo bulk: `claude-haiku-4-5-20251001` (stdlib, docs, CIPs básicos)
- Modelo complex: `claude-sonnet-4-6` (design patterns, código Hydra)
- Sistema de checkpoint en `data/processed/checkpoint.json` para ejecución resumible
- Output final: `data/processed/dataset.jsonl` con schema `{lang, instruction, input, output, source, topic}`

---

## 2. Taxonomía del Dataset — Buckets

| Bucket | Fuente principal | Ejemplos aprox. | Descripción |
|--------|-----------------|-----------------|-------------|
| **Generación de validators** | stdlib, design_patterns | ~400 | Escritura de `validator { fn spend/mint/withdraw }` con datum/redeemer tipados |
| **Explicación conceptual** | aiken_docs, CIPs | ~350 | eUTxO model, ScriptContext, diferencias con Plutus clásico |
| **Funciones stdlib** | aiken_stdlib | ~500 | Uso de `list`, `dict`, `option`, `math`, `bytearray` — cada función con ejemplos |
| **Gobernanza Conway/V3** | CIPs (CIP-1694, CIP-0069) | ~200 | DReps, comités constitucionales, voting procedures, certificates |
| **Protocolo Hydra L2** | hydra_docs, hydra_code | ~350 | Head lifecycle, off-chain transactions, snapshots, fanout |
| **Patrones de producción** | design_patterns | ~88 | Singleton pattern, stake validators, UTxO indexers, withdraw-zero trick |
| **Comparativa Plutus/Aiken** | aiken_docs, CIPs | ~180 | Migración de Plutus V2→Aiken, diferencias sintácticas, ejecución on-chain |

### Distribución por idioma

- **Inglés (EN):** 1,299 ejemplos — 62.8%
- **Español (ES):** 770 ejemplos — 37.2%
- **Total:** 2,069 ejemplos

### Distribución por fuente

| Fuente | Ejemplos |
|--------|----------|
| Aiken stdlib | 915 |
| CIPs | 446 |
| Hydra Plutus code | 368 |
| Hydra docs | 140 |
| Aiken docs | 112 |
| Design Patterns | 88 |
| **Total** | **2,069** |

---

## 3. Análisis de Densidad de Tokens

### Por qué este dataset presenta alta variabilidad en el loss

- **Heterogeneidad léxica extrema:** El dataset mezcla 3 registros distintos en el mismo batch — lenguaje natural explicativo (baja perplejidad), código Aiken tipado estricto (alta perplejidad por sintaxis poco frecuente), y especificaciones formales de CIPs (estilo técnico-legal)

- **Tokens raros de dominio:** Keywords de Aiken (`validator`, `when`, `expect`, `trace`, `ScriptContext`, `OutputReference`) tienen frecuencia prácticamente nula en el pretraining corpus del modelo base. El modelo los trata inicialmente como tokens OOV-funcionales, generando spikes de loss en los primeros steps

- **Longitud variable de outputs:** Los outputs van desde 1 línea (`redeemer == 42`) hasta validators completos de 80+ líneas con tipos custom. El padding masivo en secuencias cortas distorsiona el loss promedio por batch

- **Code-switching EN/ES:** El modelo debe aprender a responder en el idioma del instruction sin señal explícita — agrega varianza en los primeros epochs hasta que el patrón se estabiliza

- **Recomendación de training:** Usar `gradient_accumulation_steps=4` con batch efectivo de 16, monitorear `eval_loss` separado por fuente (stdlib vs CIPs vs code) para detectar overfitting parcial. Learning rate recomendado: `2e-4` con scheduler cosine y warmup de 50 steps

---

## 4. Propósito Estratégico

### Objetivo

Convertir `Qwen2.5-Coder-7B-Instruct` (modelo generalista de código) en un **Aiken Copilot** especializado en desarrollo de smart contracts para Cardano.

### Gap actual del modelo base

- Confunde sintaxis Aiken con Haskell (lenguaje más frecuente en pretraining con gramática similar)
- No conoce los `ScriptPurpose` variants correctos (`Spend`, `Mint`, `WithdrawFrom`, `Publish`)
- Inventa funciones stdlib inexistentes (`list.count`, `dict.get_int`)
- No maneja el paradigma eUTxO ni la estructura datum/redeemer/context
- Desconoce los CIPs activos y la gobernanza Conway (post Chang hardfork)

### Capacidades objetivo post fine-tuning

- Generar validators sintácticamente correctos que compilen con `aiken check`
- Conocer la stdlib completa (447 funciones documentadas en el dataset)
- Asistir en migración Plutus V2 → Aiken con traducción de patrones
- Responder consultas sobre CIPs activos incluyendo Conway governance (CIP-1694)
- Explicar el protocolo Hydra Head y sus primitivas on-chain
- Aplicar patrones de producción: singleton, stake validators, UTxO indexers
- Operar bilingüe EN/ES sin degradación de calidad técnica

### Stack técnico

| Componente | Tecnología |
|-----------|-----------|
| Modelo base | Qwen2.5-Coder-7B-Instruct |
| Método fine-tuning | QLoRA (r=16, alpha=32) |
| Framework | unsloth + TRL + PEFT |
| Hardware entrenamiento | Google Colab T4/A100 |
| Export | GGUF Q4_K_M (~4.4 GB) |
| Inferencia local | LM Studio, 6 GB VRAM |
| Temperatura inferencia | 0.1 (generación de código) |

---

## 5. Archivos del Proyecto

```
entrenamiento/
├── data/
│   ├── raw/
│   │   ├── aiken_stdlib.json          # 458 registros, 260.7 KB
│   │   ├── aiken_docs.json            # 28 páginas, 486 KB
│   │   ├── hydra_docs.json            # 35 páginas, 241 KB
│   │   ├── cips.json                  # 134 docs, 2.5 MB
│   │   ├── design_patterns.json       # 22 archivos, 178 KB
│   │   └── hydra_code.json            # 142 archivos, 562 KB
│   └── processed/
│       ├── dataset.jsonl              # 2,069 ejemplos finales
│       └── checkpoint.json            # Estado de procesamiento
├── scrape_aiken_stdlib_github.py      # Scraper GitHub API + parser ///
├── scrape_aiken_docs.py               # Crawler aiken-lang.org
├── scrape_hydra_docs.py               # Crawler hydra.family
├── scrape_github.py                   # Scraper CIPs + patterns + Hydra code
├── transform_phase2.py                # Transformación Q&A via Claude API
├── run_phase1.sh                      # Orquestador Fase 1
└── colab_finetune.ipynb               # Notebook entrenamiento Google Colab
```

---

*Generado: 2026-04-01 | Dataset v1.0 | Ejemplos: 2,069 | Idiomas: EN/ES*
