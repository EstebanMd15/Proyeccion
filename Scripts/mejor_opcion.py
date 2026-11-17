"""Mejor Opcion de Compra.

Cruza la Proyeccion con la Lista de Precios (LP) de proveedores y entrega, por
codigo Mantis, las 3 opciones de compra mas baratas con las cantidades a pedir en
los 2 escenarios de la hoja Todo REST CEDI de la Proyeccion (sin CEDI y sin CEDI +
Pend Total). NEPS-REM y FOMAG van en una sola fila con la necesidad sumada (y su
detalle en columnas aparte).

Reglas:
  - Costo que se compara: Costo Negociacion (por unidad, sin IVA, sin descuentos).
  - Equivalentes = mismo Codigo_Molecula. La necesidad de todos los codigos de la
    molecula se suma y se carga a la opcion mas barata, sin importar categoria.
  - FOMAG solo se compra a codigos habilitados por el contrato vigente
    (codigos_fomag_desde_archivo). Lo de NEPS-REM puede ir a cualquier equivalente.
  - No se compran codigos Descontinuados ni con Invima Vencido, Desistido, Negado,
    Cancelado o Abandono (su necesidad pasa a un equivalente).
  - No hay desempate automatico: la columna Empate de cada opcion lista los otros
    codigos/proveedores con el mismo costo (a igual costo se respeta el orden de la LP).
  - La cantidad se ajusta a la Cantidad Pastillas del codigo de cada opcion
    (no se usa el Embalaje de la LP ni se excluye por Bloqueo para Compra).
  - Si la opcion 1 de NEPS-REM y la de FOMAG no coinciden (codigo + proveedor), o
    una de las dos lineas no tiene opcion, la molecula sale en 2 filas, una por linea.
  - En la fila unificada, si una opcion 2 o 3 no esta en el contrato FOMAG, su cantidad
    solo cubre NEPS-REM y la columna Cubre FOMAG queda en NO.
  - El redondeo por empaque se hace sobre el total (NEPS-REM + FOMAG).
  - Pendientes FOMAG (escenario sin CEDI + Pend): pendientes de dispensacion netos
    x (Pendientes_FOMAG / Pendientes_Dispensacion); los comerciales van a NEPS-REM.
"""
import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from Scripts.processor import ProyeccionProcessor

INVIMA_EXCLUIDOS = {'VENCIDO', 'DESISTIDO', 'NEGADO', 'CANCELADO', 'ABANDONO'}
N_OPCIONES = 3
# (etiqueta corta en el Excel, clave interna)
ESCENARIOS = [('Cant. sin CEDI', 'E1'), ('Cant. sin CEDI + Pend', 'E2')]
COLOR_BASE = 'D9D9D9'
COLORES_OPCION = {1: 'C6EFCE', 2: 'DDEBF7', 3: 'FFF2CC'}


def _cod(serie):
    return serie.astype(str).str.strip().str.replace(r'\.0$', '', regex=True)


def _num(df, col):
    if col not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[col], errors='coerce').fillna(0)


def lp_desde_archivo(df):
    """Normaliza la LP: una fila por codigo + proveedor con costo > 0."""
    lp = df.copy()
    lp.columns = lp.columns.astype(str).str.strip()
    lp['Codigo Articulo'] = _cod(lp['Codigo Articulo'])
    lp['Nit'] = _cod(lp['Nit'])
    lp['Costo Negociacion'] = _num(lp, 'Costo Negociacion')
    lp['Plazo'] = _num(lp, 'Plazo')
    lp['Cod Proveedor'] = lp['Cod Proveedor'].fillna('').astype(str).str.strip() if 'Cod Proveedor' in lp else ''
    lp['Cod Proveedor'] = lp['Cod Proveedor'].replace({'nan': ''}).str.replace(r'\.0$', '', regex=True)
    lp['Nombre Completo'] = lp['Nombre Completo'].astype(str).str.strip()
    lp = lp[lp['Codigo Articulo'].str.upper().str.startswith('M') & (lp['Costo Negociacion'] > 0)]
    lp = lp.sort_values('Costo Negociacion', kind='stable').drop_duplicates(['Codigo Articulo', 'Nit'])
    return lp[['Codigo Articulo', 'Nit', 'Nombre Completo', 'Cod Proveedor', 'Costo Negociacion', 'Plazo']]


def _molecula(df):
    """Molecula de cada fila; sin Codigo_Molecula el codigo queda como su propia molecula."""
    cod = _cod(df['Codigo'])
    mol = _cod(df['Codigo_Molecula'])
    sin_mol = df['Codigo_Molecula'].isna() | mol.isin(['', '0', 'nan'])
    return pd.Series(np.where(sin_mol, 'COD-' + cod, mol), index=df.index)


def necesidades_desde_proyeccion(df_cedi):
    """Necesidad por codigo y linea en los 2 escenarios de la hoja Todo REST CEDI.
    E1 = Cantidad a Pedir sin CEDI, E2 = Cant. a Pedir sin CEDI + Pend Total.
    FOMAG en E2 = FOMAG sin CEDI + la parte FOMAG de los pendientes de dispensacion netos."""
    c = df_cedi.copy()
    n = pd.DataFrame({'Codigo': _cod(c['Codigo']), 'Molecula': _molecula(c),
                      'Rotacion': c['Rotacion'].fillna('B').astype(str)})
    n['E1'] = _num(c, 'Cantidad a Pedir sin CEDI')
    n['E2'] = _num(c, 'Cant. a Pedir sin CEDI + Pend Total')
    n['F1'] = _num(c, 'Pedir_FOMAG_Evento sin CEDI')
    extra_disp = (_num(c, 'Cantidad a Pedir + Pend Disp sin CEDI') - n['E1']).clip(lower=0)
    pend_disp = _num(c, 'Pendientes_Dispensacion')
    pend_fomag = _num(c, 'Pendientes_FOMAG')
    parte = (pend_fomag / pend_disp.where(pend_disp > 0)).fillna(0).clip(0, 1)
    n['F2'] = n['F1'] + (extra_disp * parte).round()

    filas = []
    for i in (1, 2):
        n[f'FOMAG_{i}'] = np.minimum(n[f'F{i}'], n[f'E{i}']).clip(lower=0)
        n[f'NEPS_{i}'] = (n[f'E{i}'] - n[f'FOMAG_{i}']).clip(lower=0)
    for linea, pref in (('NEPS-REM', 'NEPS'), ('FOMAG', 'FOMAG')):
        f = n[['Codigo', 'Molecula', 'Rotacion']].copy()
        f['Linea'] = linea
        for i in (1, 2):
            f[f'E{i}'] = n[f'{pref}_{i}']
        filas.append(f)
    nec = pd.concat(filas, ignore_index=True)
    return nec[nec[['E1', 'E2']].sum(axis=1) > 0]


def candidatos(lp, maestro, mol_map, codigos_fomag):
    """Precios de la LP de codigos comprables, con su molecula y si pueden recibir FOMAG."""
    m = maestro.copy()
    m['Codigo'] = _cod(m['Codigo'])
    descont = m['Descontinuado'].astype(str).str.strip().str.upper().eq('SI')
    invima = m['Estado Invima'].astype(str).str.strip().str.upper().isin(INVIMA_EXCLUIDOS)
    m = m[~descont & ~invima].drop_duplicates('Codigo')
    m = m[['Codigo', 'Nombre', 'Cantidad Pastillas']]

    cand = lp.merge(m, left_on='Codigo Articulo', right_on='Codigo', how='inner')
    cand['Molecula'] = cand['Codigo'].map(mol_map)
    cand = cand[cand['Molecula'].notna()]
    cand['FOMAG_OK'] = cand['Codigo'].isin(codigos_fomag)
    return cand.sort_values('Costo Negociacion', kind='stable').reset_index(drop=True)


def _empates(opciones, todos):
    """Para cada opcion, los otros codigo - proveedor con el mismo costo."""
    out = []
    for _, o in opciones.iterrows():
        mismos = todos[(todos['Costo Negociacion'] == o['Costo Negociacion']) &
                       ~((todos['Codigo'] == o['Codigo']) & (todos['Nit'] == o['Nit']))]
        out.append('; '.join(mismos['Codigo'] + ' - ' + mismos['Nombre Completo']))
    return out


def _fila(g, c, nombres):
    """Una fila del archivo. g = necesidades (NEPS-REM y/o FOMAG) que van en la fila,
    c = candidatos de la molecula ya ordenados por costo."""
    por_cod = (g.groupby('Codigo', sort=False)
                .agg(E1=('E1', 'sum'), E2=('E2', 'sum'), Rotacion=('Rotacion', 'first'))
                .sort_values(['E2', 'E1'], ascending=False, kind='stable'))
    top = por_cod.iloc[0]
    neps, fomag = g[g['Linea'] == 'NEPS-REM'], g[g['Linea'] == 'FOMAG']
    ops = c.head(N_OPCIONES)
    empates = _empates(ops, c)

    cod_fila = ops.iloc[0]['Codigo'] if len(ops) else por_cod.index[0]
    fila = {'Código Mantis': cod_fila, 'Nombre': nombres.get(cod_fila, ''),
            'Códigos agrupados': ', '.join(por_cod.index)}
    for etiqueta, e in (('sin CEDI', 'E1'), ('sin CEDI + Pend', 'E2')):
        fila[f'Nec. NEPS-REM {etiqueta}'] = neps[e].sum()
        fila[f'Nec. FOMAG {etiqueta}'] = fomag[e].sum()
        fila[f'Nec. {etiqueta}'] = neps[e].sum() + fomag[e].sum()
    fila['_rot'] = top['Rotacion']
    fila['Estado'] = 'SIN LP' if len(ops) == 0 else (
        'OK' if len(ops) == N_OPCIONES else f'{len(ops)} OPCI{"ÓN" if len(ops) == 1 else "ONES"}')
    hay_fomag = fomag[['E1', 'E2']].to_numpy().sum() > 0
    for k in range(1, N_OPCIONES + 1):
        o = ops.iloc[k - 1] if k <= len(ops) else None
        cubre = o is not None and bool(o['FOMAG_OK'])
        fila[f'_pas{k}'] = o['Cantidad Pastillas'] if o is not None else 0
        fila[(k, 'Código Mantis')] = o['Codigo'] if o is not None else ''
        fila[(k, 'Nombre')] = o['Nombre'] if o is not None else ''
        fila[(k, 'NIT')] = o['Nit'] if o is not None else ''
        fila[(k, 'Proveedor')] = o['Nombre Completo'] if o is not None else ''
        fila[(k, 'Cod Proveedor')] = o['Cod Proveedor'] if o is not None else ''
        fila[(k, 'Costo Negociación')] = o['Costo Negociacion'] if o is not None else np.nan
        fila[(k, 'Plazo')] = o['Plazo'] if o is not None else np.nan
        fila[(k, 'Empate')] = empates[k - 1] if o is not None else ''
        fila[(k, 'Cubre FOMAG')] = ('SI' if cubre else 'NO') if (o is not None and hay_fomag) else ''
        # Necesidad que cubre la opcion: la parte FOMAG solo si el codigo esta en el contrato
        for e in ('E1', 'E2'):
            fila[f'_base{k}{e}'] = neps[e].sum() + (fomag[e].sum() if cubre else 0)
    return fila


def calcular_mejor_opcion(nec, cand, nombres):
    """Una fila por molecula con la necesidad de NEPS-REM + FOMAG sumada y las 3 mejores
    opciones de compra. Si la opcion 1 de NEPS-REM y la de FOMAG no son el mismo codigo y
    proveedor (o una linea no tiene opcion), la molecula sale en 2 filas, una por linea."""
    por_mol = {k: g for k, g in cand.groupby('Molecula', sort=False)}
    vacia = cand.iloc[0:0]
    filas = []
    for mol, gm in nec.groupby('Molecula', sort=False):
        c_todos = por_mol.get(mol, vacia)
        c_fomag = c_todos[c_todos['FOMAG_OK']]
        neps, fomag = gm[gm['Linea'] == 'NEPS-REM'], gm[gm['Linea'] == 'FOMAG']
        if len(neps) and len(fomag):
            clave = lambda c: (c.iloc[0]['Codigo'], c.iloc[0]['Nit']) if len(c) else None
            if clave(c_todos) == clave(c_fomag):
                filas.append(_fila(gm, c_todos, nombres))
            else:
                filas.append(_fila(neps, c_todos, nombres))
                filas.append(_fila(fomag, c_fomag, nombres))
        elif len(neps):
            filas.append(_fila(neps, c_todos, nombres))
        else:
            filas.append(_fila(fomag, c_fomag, nombres))

    out = pd.DataFrame(filas)
    if out.empty:
        return out
    # Cantidades: la necesidad total que cubre cada opcion, ajustada al empaque de su codigo
    for k in range(1, N_OPCIONES + 1):
        hay = out[(k, 'Código Mantis')].ne('')
        costo = out[(k, 'Costo Negociación')].fillna(0)
        for etiqueta, e in ESCENARIOS:
            cant = ProyeccionProcessor.redondear_por_empaque(out[f'_base{k}{e}'], out[f'_pas{k}'], out['_rot'])
            cant = np.where(hay, cant, np.nan)
            out[(k, etiqueta)] = cant
            out[(k, f'Valor {etiqueta}')] = np.where(hay, cant * costo, np.nan).round(2)
    aux = [c for c in out.columns if isinstance(c, str) and c.startswith('_')]
    out = out.drop(columns=aux)
    orden_estado = {'OK': 0, '2 OPCIONES': 1, '1 OPCIÓN': 2, 'SIN LP': 3}
    out['_o'] = out['Estado'].map(orden_estado)
    out = out.sort_values(['_o', 'Código Mantis'], kind='stable').drop(columns='_o').reset_index(drop=True)
    return out


def exportar(out, ruta):
    """Una sola hoja: fila 1 = titulo de cada opcion, fila 2 = encabezados."""
    base = [c for c in out.columns if not isinstance(c, tuple)]
    estado = base.pop(base.index('Estado'))
    base.append(estado)
    cols_op = {k: [c for c in out.columns if isinstance(c, tuple) and c[0] == k] for k in range(1, N_OPCIONES + 1)}
    orden = base + [c for k in cols_op for c in cols_op[k]]
    df = out[orden].copy()
    df.columns = [c if not isinstance(c, tuple) else f'Op{c[0]} {c[1]}' for c in orden]

    with pd.ExcelWriter(ruta, engine='openpyxl') as w:
        df.to_excel(w, sheet_name='Mejor Opcion', index=False, startrow=1)
        ws = w.sheets['Mejor Opcion']
        negrita = Font(bold=True)
        centro = Alignment(horizontal='center', vertical='center', wrap_text=True)
        col = 1
        bloques = [('DATOS DEL PEDIDO', len(base), COLOR_BASE)] + \
                  [(f'OPCIÓN {k}' + (' (MEJOR OPCIÓN)' if k == 1 else ''), len(cols_op[k]), COLORES_OPCION[k])
                   for k in cols_op]
        for titulo, ancho, color in bloques:
            relleno = PatternFill('solid', fgColor=color)
            ws.cell(row=1, column=col, value=titulo)
            ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + ancho - 1)
            for j in range(col, col + ancho):
                for r in (1, 2):
                    cel = ws.cell(row=r, column=j)
                    cel.fill, cel.font, cel.alignment = relleno, negrita, centro
            col += ancho

        for j, nombre in enumerate(df.columns, start=1):
            letra = get_column_letter(j)
            if any(p in nombre for p in ('Nec.', 'Cant.', 'Valor', 'Costo', 'Plazo')):
                for cel in ws[letra][2:]:
                    cel.number_format = '#,##0'
                ws.column_dimensions[letra].width = 14
            elif 'Nombre' in nombre or 'Proveedor' in nombre or 'Empate' in nombre or 'agrupados' in nombre:
                ws.column_dimensions[letra].width = 38
            else:
                ws.column_dimensions[letra].width = 13
        ws.row_dimensions[2].height = 32
        ws.freeze_panes = ws.cell(row=3, column=3)
        ws.auto_filter.ref = f'A2:{get_column_letter(len(df.columns))}{len(df) + 2}'
    return ruta


def generar_mejor_opcion(df_cedi, df_maestro, df_lp, codigos_fomag, ruta):
    """df_cedi = hoja Todo REST CEDI de la Proyeccion."""
    nec = necesidades_desde_proyeccion(df_cedi)
    # Molecula de TODOS los codigos de la Proyeccion (tambien los que no tienen necesidad)
    mol_map = pd.Series(_molecula(df_cedi).to_numpy(), index=_cod(df_cedi['Codigo']))
    mol_map = mol_map[~mol_map.index.duplicated()]

    lp = lp_desde_archivo(df_lp)
    cand = candidatos(lp, df_maestro, mol_map, codigos_fomag)
    nombres = dict(zip(_cod(df_maestro['Codigo']), df_maestro['Nombre'].astype(str)))
    out = calcular_mejor_opcion(nec, cand, nombres)
    exportar(out, ruta)
    return out
