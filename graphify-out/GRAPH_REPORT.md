# Graph Report - Proyeccion  (2026-11-13)

## Corpus Check
- 15 files · ~19,221 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 3 file(s) not represented in the graph (top: (none) 1, .toml 1, .css 1)

## Summary
- 262 nodes · 548 edges · 9 communities (8 shown, 1 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 39 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ee4dccb0`
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
- mejor_opcion.py

## God Nodes (most connected - your core abstractions)
1. `ProyeccionProcessor` - 36 edges
2. `generar_abastecimiento()` - 19 edges
3. `abastecimiento_reparto()` - 15 edges
4. `dashboard()` - 10 edges
5. `generar()` - 10 edges
6. `generar_mejor_opcion()` - 9 edges
7. `Proyeccion upload form` - 9 edges
8. `exportar()` - 8 edges
9. `cargar_datos()` - 8 edges
10. `exportar_excel()` - 8 edges

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

## Communities (9 total, 1 thin omitted)

### Community 0 - "Motor de Abastecimiento (Reparto)"
Cohesion: 0.10
Nodes (31): asignar_lotes(), calcular_disponible(), calcular_pesos(), codigos_fomag_desde_archivo(), construir_matriz(), construir_matriz_transito(), construir_reservas(), cubrir_faltante_molecula() (+23 more)

### Community 2 - "API Web y Consultas BD"
Cohesion: 0.17
Nodes (19): consultar_abastecimiento(), consultar_dispensacion(), consultar_remisiones(), get_engine(), periodos_cargados(), abastecimiento_consumo(), abastecimiento_pagina(), compras_pagina() (+11 more)

### Community 3 - "Formularios Web y Dependencias"
Cohesion: 0.08
Nodes (33): fastapi, jinja2, openpyxl 3.1.5, pandas 3.0.3, PyMySQL, python-multipart, SQLAlchemy, streamlit 1.60.0 (+25 more)

### Community 4 - "main.py"
Cohesion: 0.13
Nodes (13): cargar_datos(), _cols_pendientes(), construir_hojas(), _descripcion_columna(), exportar_excel(), colorear_encabezados(), _escribir(), leer_con_encabezado() (+5 more)

### Community 5 - "Paginas de Consumo y Navegacion"
Cohesion: 0.21
Nodes (10): GET /rotacion/periodos, etiquetaPeriodo(), llenarSelect(), seccion template variable, Topbar navigation by seccion, etiquetaPeriodo(), llenarSelect(), poblarPorTipo() (+2 more)

### Community 6 - "Configuracion de Graphify"
Cohesion: 0.31
Nodes (3): graphify skill (.claude/skills/graphify/SKILL.md), /graphify trigger, graphify-out knowledge graph

### Community 7 - "calidad_temp.py"
Cohesion: 0.10
Nodes (24): armar_equipos(), armar_lectura(), contar(), dashboard(), equipos_guardar(), equipos_pagina(), estado_equipos(), estado_general() (+16 more)

### Community 8 - "mejor_opcion.py"
Cohesion: 0.18
Nodes (9): calcular_mejor_opcion(), candidatos(), _cod(), _empates(), exportar(), generar_mejor_opcion(), lp_desde_archivo(), necesidades_desde_proyeccion() (+1 more)

## Ambiguous Edges - Review These
- `resultado.html` → `GET /dashboard/{id}`  [AMBIGUOUS]
  templates/proyeccion.html · relation: references

## Knowledge Gaps
- **10 isolated node(s):** `pandas 3.0.3`, `streamlit 1.60.0`, `GET /abastecimiento/consumo`, `GET /rotacion/{tipo}`, `Cobertura, lead time and seguridad parameters` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 58 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ProyeccionProcessor` connect `Motor de Proyeccion de Compras` to `mejor_opcion.py`, `API Web y Consultas BD`, `main.py`?**
  _High betweenness centrality (0.190) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `ProyeccionProcessor` (e.g. with `_valorizar_estado()` and `calcular_mejor_opcion()`) actually correct?**
  _`ProyeccionProcessor` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pandas 3.0.3`, `streamlit 1.60.0`, `GET /abastecimiento/consumo` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Motor de Abastecimiento (Reparto)` be split into smaller, more focused modules?**
  _Cohesion score 0.09619450317124736 - nodes in this community are weakly interconnected._
- **Why does `dashboard()` connect `calidad_temp.py` to `Motor de Abastecimiento (Reparto)`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Should `Motor de Proyeccion de Compras` be split into smaller, more focused modules?**
  _Cohesion score 0.09103840682788052 - nodes in this community are weakly interconnected._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `resultado.html` and `GET /dashboard/{id}`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._