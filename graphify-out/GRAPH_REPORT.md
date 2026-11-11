# Graph Report - Proyeccion  (2026-11-11)

## Corpus Check
- 14 files · ~17,758 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 1, .toml 1, .css 1)

## Summary
- 244 nodes · 504 edges · 8 communities
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 38 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `03a63fa0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Motor de Abastecimiento (Reparto)
- Motor de Proyeccion de Compras
- API Web y Consultas BD
- Formularios Web y Dependencias
- main.py
- Paginas de Consumo y Navegacion
- Configuracion de Graphify
- calidad_temp.py

## God Nodes (most connected - your core abstractions)
1. `ProyeccionProcessor` - 34 edges
2. `generar_abastecimiento()` - 19 edges
3. `abastecimiento_reparto()` - 15 edges
4. `dashboard()` - 10 edges
5. `generar()` - 10 edges
6. `Proyeccion upload form` - 9 edges
7. `exportar()` - 8 edges
8. `cargar_datos()` - 8 edges
9. `exportar_excel()` - 8 edges
10. `Topbar navigation by seccion` - 8 edges

## Surprising Connections (you probably didn't know these)
- `openpyxl 3.1.5` --conceptually_related_to--> `Proyeccion upload form`  [INFERRED]
  requerimientos.txt → templates/proyeccion.html
- `xlrd 2.0.2` --conceptually_related_to--> `Proyeccion upload form`  [INFERRED]
  requerimientos.txt → templates/proyeccion.html
- `SQLAlchemy` --conceptually_related_to--> `GET /rotacion/periodos`  [INFERRED]
  requerimientos.txt → templates/abastecimiento_consumo.html
- `python-multipart` --conceptually_related_to--> `Proyeccion upload form`  [INFERRED]
  requerimientos.txt → templates/proyeccion.html
- `python-multipart` --conceptually_related_to--> `Reparto upload form`  [INFERRED]
  requerimientos.txt → templates/reparto.html

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Period selector and consumo download pages** — templates_abastecimiento_consumo, templates_consumos, templates_abastecimiento_consumo_endpoint_rotacion_periodos [EXTRACTED 1.00]
- **Generated Excel files feeding the reparto form** — templates_abastecimiento_consumo_descargarconsumoabastecimiento, templates_proyeccion_submit_handler, templates_reparto_archivos_requeridos, templates_reparto_endpoint_abastecimiento_reparto [INFERRED 0.85]
- **Module navigation from home to Compras and Inventarios sections** — templates_home, templates_compras, templates_inventarios, templates_base_topbar_nav [INFERRED 0.95]

## Communities (8 total, 0 thin omitted)

### Community 0 - "Motor de Abastecimiento (Reparto)"
Cohesion: 0.09
Nodes (34): asignar_lotes(), calcular_disponible(), calcular_pesos(), codigos_fomag_desde_archivo(), construir_matriz(), construir_matriz_transito(), construir_reservas(), cubrir_faltante_molecula() (+26 more)

### Community 1 - "Motor de Proyeccion de Compras"
Cohesion: 0.09
Nodes (3): main(), _valorizar_estado(), ProyeccionProcessor

### Community 2 - "API Web y Consultas BD"
Cohesion: 0.15
Nodes (20): consultar_abastecimiento(), consultar_dispensacion(), consultar_remisiones(), get_engine(), periodos_cargados(), abastecimiento_consumo(), abastecimiento_pagina(), compras_pagina() (+12 more)

### Community 3 - "Formularios Web y Dependencias"
Cohesion: 0.08
Nodes (33): fastapi, jinja2, openpyxl 3.1.5, pandas 3.0.3, PyMySQL, python-multipart, SQLAlchemy, streamlit 1.60.0 (+25 more)

### Community 4 - "main.py"
Cohesion: 0.18
Nodes (7): _cols_pendientes(), construir_hojas(), _descripcion_columna(), exportar_excel(), colorear_encabezados(), _escribir(), _limpiar_df()

### Community 5 - "Paginas de Consumo y Navegacion"
Cohesion: 0.21
Nodes (10): GET /rotacion/periodos, etiquetaPeriodo(), llenarSelect(), seccion template variable, Topbar navigation by seccion, etiquetaPeriodo(), llenarSelect(), poblarPorTipo() (+2 more)

### Community 6 - "Configuracion de Graphify"
Cohesion: 0.31
Nodes (3): graphify skill (.claude/skills/graphify/SKILL.md), /graphify trigger, graphify-out knowledge graph

### Community 7 - "calidad_temp.py"
Cohesion: 0.09
Nodes (24): armar_equipos(), armar_lectura(), contar(), dashboard(), equipos_guardar(), equipos_pagina(), estado_equipos(), estado_general() (+16 more)

## Ambiguous Edges - Review These
- `resultado.html` → `GET /dashboard/{id}`  [AMBIGUOUS]
  templates/proyeccion.html · relation: references

## Knowledge Gaps
- **10 isolated node(s):** `pandas 3.0.3`, `streamlit 1.60.0`, `GET /abastecimiento/consumo`, `GET /rotacion/{tipo}`, `Cobertura, lead time and seguridad parameters` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 50 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ProyeccionProcessor` connect `Motor de Proyeccion de Compras` to `API Web y Consultas BD`, `main.py`?**
  _High betweenness centrality (0.191) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `ProyeccionProcessor` (e.g. with `_valorizar_estado()` and `generar()`) actually correct?**
  _`ProyeccionProcessor` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pandas 3.0.3`, `streamlit 1.60.0`, `GET /abastecimiento/consumo` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Motor de Abastecimiento (Reparto)` be split into smaller, more focused modules?**
  _Cohesion score 0.09065679925994449 - nodes in this community are weakly interconnected._
- **Why does `dashboard()` connect `calidad_temp.py` to `Motor de Abastecimiento (Reparto)`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Should `Motor de Proyeccion de Compras` be split into smaller, more focused modules?**
  _Cohesion score 0.08658536585365853 - nodes in this community are weakly interconnected._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `resultado.html` and `GET /dashboard/{id}`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._