from Scripts import config
import numpy as np
import pandas as pd
import re

from openpyxl.styles import PatternFill
from Scripts.config import CONTRATO_FOMAG_VIGENTE

_CHARS_ILEGALES = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
COLORES_PUNTO = ['89A482', 'FFFF00', 'BDD7EE', 'C6E0B4', 'F8CBAD', '76C0EC']
COLORES_ESTADO = {'SE ENVIA': 'D9EAD3', 'NO SE ENVIA': 'FF9B9B', 'SIN STOCK': 'FFE699', 'SIN ROTACIÓN': 'D9D9D9'}
MESES_ES = {'01': 'Ene', '02': 'Feb', '03': 'Mar', '04': 'Abr', '05': 'May', '06': 'Jun',
            '07': 'Jul', '08': 'Ago', '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dic'}

def _limpiar(d):
    d = d.copy()
    for c in d.columns:
        if pd.api.types.is_numeric_dtype(d[c]) or pd.api.types.is_datetime64_any_dtype(d[c]):
            continue
        d[c] = d[c].astype(str).str.replace(_CHARS_ILEGALES, '', regex=True)
    return d

def ponderar_prescrita(df, col_periodo='PERIODO', col_codigo='CODIGO',
                       col_bodega='CODIGO BODEGA', col_cantidad='CONSUMO TOTAL',
                       codigos_fomag=None, col_cliente='SIGLA_COMERCIAL_CLIENTE',
                       sigla_fomag='FIDEICOMISOS'):
    df= df.copy()

    if codigos_fomag is not None:
        df = filtrar_fomag_sin_contrato(df, codigos_fomag, col_codigo=col_codigo)

    # 1. Normalizar la bodega a texto y filtrar solo lsa activas de config
    df[col_bodega] = df[col_bodega].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df[col_codigo] = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    activas = set(config.BODEGAS_ABASTECIMIENTO.keys())
    df = df[df[col_bodega].isin(activas)]

    #2. Los 3 meses (mismos que la proyeccion, si el df viene filtrado al rango)
    periodos = sorted(df[col_periodo].unique())
    if getattr(config, 'APARTAR_ULTIMO_MES_VISUAL', True):
        periodos = periodos[:-1]

    if len(periodos) < 3:
        raise ValueError(
            f"Se necesitan al menos 3 periodos tras apartar el mes visual; llegaron {len(periodos)}. "
            f"Genera el Consumo Abastecimiento con 4+ meses y verifica que las bodegas crucen con config."
        )
    
    mes_reciente, mes_intermedio, mes_antiguo = periodos[-1], periodos[-2], periodos[-3]

    # 2. Ponderar 50/30/20, pero agrupando por código + bodega
    llaves = [col_codigo, col_bodega]
    reciente = df[df[col_periodo]== mes_reciente].groupby(llaves)[col_cantidad].sum() * 0.50
    intermedio = df[df[col_periodo] == mes_intermedio].groupby(llaves)[col_cantidad].sum() * 0.30
    antiguo = df[df[col_periodo] == mes_antiguo].groupby(llaves)[col_cantidad].sum() * 0.20

    pond = reciente.add(intermedio, fill_value=0).add(antiguo, fill_value=0)

    pond = pond.reset_index()
    pond.rename(columns={col_cantidad: 'Ponderado'}, inplace=True)
    peso_mes = {mes_reciente: 0.50, mes_intermedio: 0.30, mes_antiguo: 0.20}
    fom = df[df[col_cliente].astype(str).str.upper().str.contains(sigla_fomag.upper(), na=False)]
    fom = fom.assign(Ponderado_Fomag=fom[col_cantidad] * fom[col_periodo].map(peso_mes))
    pond = pond.merge(fom.groupby(llaves, as_index=False)['Ponderado_Fomag'].sum(), on=llaves, how='left')
    pond['Ponderado_Fomag'] = pond['Ponderado_Fomag'].fillna(0)
    return pond

def calcular_pesos(pond, col_codigo='CODIGO'):
    pond = pond.copy()

    total_codigo = pond.groupby(col_codigo)['Ponderado'].transform('sum')
    pond['Peso'] = (pond['Ponderado'] / total_codigo).fillna(0)

    return pond

def repartir(pesos, pedidos, col_codigo='CODIGO'):
    pesos = pesos.copy()
    pesos['Unidades'] = 0

    for codigo, grupo in pesos.groupby(col_codigo):
        total = int(pedidos.get(codigo, 0))
        if total <= 0 or grupo['Peso'].sum() == 0:
            continue # Sin pedido o sin prescripcion -> queda en 0

        exacto = grupo['Peso'] * total
        piso = np.floor(exacto)
        und_sobran = int(total - piso.sum())

        #Las 'faltan' unidades van a las bodegas con mayor parte decimal
        idx_orden = (exacto - piso).sort_values(ascending=False).index
        piso.loc[idx_orden[:und_sobran]] += 1

        pesos.loc[grupo.index, 'Unidades'] = piso.astype(int).values

    return pesos

def construir_matriz(reparto, col_codigo='CODIGO', col_bodega='CODIGO BODEGA', col_valor='Unidades'):
    activas = list(config.BODEGAS_ABASTECIMIENTO.keys())
    # Orden de bodegas por MAYOR CONSUMO (Ponderado total, desc), solo activas
    orden = (reparto.groupby(col_bodega)[col_valor].sum()
             .reindex(activas).fillna(0)
             .sort_values(ascending=False).index.tolist())
    matriz = reparto.pivot_table(index=col_codigo, columns=col_bodega,
                                 values=col_valor, aggfunc='sum', fill_value=0)
    matriz = matriz.reindex(columns=orden, fill_value=0)   # <- ahora 'orden', no config keys
    matriz['Total control'] = matriz.sum(axis=1)
    matriz = matriz.reset_index()
    return matriz

def hoja_pesos(pond, col_bodega='CODIGO BODEGA'):
    #Sumar el ponderado de todos los códigos por bodega
    por_bodega = pond.groupby(col_bodega)['Ponderado'].sum()

    total_general = por_bodega.sum()

    tabla = por_bodega.reset_index()
    tabla['Sucursal'] = tabla[col_bodega].map(config.BODEGAS_ABASTECIMIENTO)
    tabla['% Global'] = (tabla['Ponderado'] / total_general * 100).round(2) if total_general else 0

    tabla = tabla.sort_values('% Global', ascending=False).reset_index(drop=True)

    return tabla[[col_bodega, 'Sucursal', 'Ponderado', '% Global']]

def calcular_disponible(stock_cedi, pedidos, demanda):
    df = pedidos.copy()

    df['Stock_CEDI'] = df['CODIGO'].map(stock_cedi).fillna(0)

    total_ped = df['Pedir_Disp'] + df['Pedir_Rem']
    df['Pct_Comercial'] = np.where(total_ped > 0, df['Pedir_Rem'] / total_ped, 0.0)
    df['Reserva_Comercial'] = np.ceil(df['Stock_CEDI'] * df['Pct_Comercial']).astype('int64')

    remanente = df['Stock_CEDI'] - df['Reserva_Comercial']

    df['Demanda'] = np.ceil(df['CODIGO'].map(demanda).fillna(0)).astype('int64')
    df['Disponible'] = np.minimum(remanente, df['Demanda']).astype('int64')
    df['Faltante'] = df['Demanda'] - df['Disponible']
    df['Colchon'] = (remanente - df['Disponible']).astype('int64')

    return df

def construir_reservas(disp, rep, info, col_codigo='CODIGO'):
    repartido = rep.groupby(col_codigo)['Unidades'].sum().rename('Repartido')
    r = disp.merge(repartido, on=col_codigo, how='left')
    r['Repartido'] = r['Repartido'].fillna(0).astype('int64')
    if 'Descripción' in info.columns:
        r = r.merge(info[[col_codigo, 'Descripción']], on=col_codigo, how='left')
    r['Pct_Comercial'] = (r['Pct_Comercial'] * 100).round(1)
    r = r.rename(columns={'Rotacion_Disp': 'Rotacion Disp', 'Stock_CEDI': 'Stock CEDI', 'Pct_Comercial': '% Comercial',
                          'Reserva_Comercial': 'Reserva Comercial', 'Demanda': 'Demanda Mensual',
                          'Cubre_Molecula': 'Cubre Molecula', 'Habilitado_FOMAG': 'Habilitado FOMAG'})
    cols = [col_codigo, 'Descripción', 'Rotacion Disp', 'Habilitado FOMAG', 'Stock CEDI', 'Pedir_Disp', 'Pedir_Rem',
            '% Comercial', 'Reserva Comercial', 'Demanda Mensual', 'Faltante', 'Cubre Molecula',
            'Disponible', 'Colchon', 'Repartido']
    return r[[c for c in cols if c in r.columns]].sort_values('Stock CEDI', ascending=False)

def _hoja_lotes(asignacion):
    """Da formato legible a la asignacion de lotes para la hoja Lotes."""
    if asignacion.empty:
        return asignacion
    h = asignacion.copy()
    h['Sucursal'] = h['CODIGO BODEGA'].map(config.BODEGAS_ABASTECIMIENTO)
    h['Vence'] = pd.to_datetime(h['Vence']).dt.strftime('%Y-%m-%d')
    cols = ['CODIGO', 'Descripcion', 'Laboratorio', 'CODIGO BODEGA', 'Sucursal',
            'Grupo', 'Lote', 'Vence', 'Unidades']
    h = h[[c for c in cols if c in h.columns]]
    return h.sort_values(['CODIGO', 'Grupo', 'Vence']).reset_index(drop=True)

def pintar_puntos(ws, bodegas):
    bodegas = [str(b) for b in bodegas]
    relleno = {}
    for celda in ws[1]:
        punto = next((t for t in str(celda.value).split() if t in bodegas), None)
        if punto is None:
            continue
        if punto not in relleno:
            color = COLORES_PUNTO[len(relleno) % len(COLORES_PUNTO)]
            relleno[punto] = PatternFill(fill_type='solid', start_color=color, end_color=color)
        celda.fill = relleno[punto]

def pintar_estado(ws):
    relleno = {e: PatternFill(fill_type='solid', start_color=c, end_color=c) for e,c in COLORES_ESTADO.items()}
    cols_estado = [c.column for c in ws[1] if str(c.value).startswith('Estado')]
    for col in cols_estado:
        for fila in range(2, ws.max_row +1):
            celda = ws.cell(row=fila, column=col)
            if celda.value in relleno:
                celda.fill = relleno[celda.value]

def hoja_consumos(df, codigos_fomag, info, col_periodo='PERIODO', col_codigo='CODIGO', col_bodega='CODIGO BODEGA',
                  col_cantidad='CONSUMO TOTAL', col_cliente='SIGLA_COMERCIAL_CLIENTE', sigla_fomag='FIDEICOMISOS'):
    df = filtrar_fomag_sin_contrato(df, codigos_fomag, col_codigo=col_codigo)
    df[col_bodega] = df[col_bodega].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df[col_codigo] = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df = df[df[col_bodega].isin(config.BODEGAS_ABASTECIMIENTO)]

    periodos = sorted(df[col_periodo].unique())
    visual = []
    if getattr(config, 'APARTAR_ULTIMO_MES_VISUAL', True):
        visual, periodos = periodos[-1:], periodos[:-1]
    meses = periodos[-3:]
    pesos_mes = dict(zip(meses, [0.20, 0.30, 0.50]))
    df = df[df[col_periodo].isin(meses + visual)]

    llaves = [col_codigo, col_bodega]
    h = (df.pivot_table(index=llaves, columns=col_periodo, values=col_cantidad, aggfunc='sum', fill_value=0).reindex(columns=meses + visual, fill_value=0))
    h['Demanda Mensual'] = sum(h[m] * pesos_mes[m] for m in meses)
    fom = df[df[col_cliente].astype(str).str.upper().str.contains(sigla_fomag.upper(), na=False)]
    fom = fom.assign(Pond=fom[col_cantidad] * fom[col_periodo].map(pesos_mes))
    h['Demanda FOMAG'] = fom.groupby(llaves)['Pond'].sum().reindex(h.index).fillna(0)
    h['Demanda NUEVA EPS'] = (h['Demanda Mensual'] - h['Demanda FOMAG']).clip(lower=0)
    etiquetas ={m: f'{MESES_ES.get(str(m)[-2:], str(m)[-2:])}_{str(m)[:4]}' for m in meses + visual}
    etiquetas.update({m: f'{etiquetas[m]} (visual)' for m in visual})
    h = h.round(1).rename(columns=etiquetas).reset_index()

    zona = {b: z for z, bodegas in config.ZONAS_ABASTECIMIENTO.items() for b in bodegas}
    h['Sucursal'] = h[col_bodega].map(config.BODEGAS_ABASTECIMIENTO)
    h['Zona'] = h[col_bodega].map(zona)
    h = h.merge(info[[col_codigo, 'Descripción']], on=col_codigo, how='left')
    cols = ([col_codigo, 'Descripción', col_bodega, 'Sucursal', 'Zona'] + [etiquetas[m] for m in meses + visual] +
    ['Demanda Mensual', 'Demanda NUEVA EPS', 'Demanda FOMAG'])
    return h[cols].sort_values([col_codigo, 'Demanda Mensual'], ascending=[True, False]).reset_index(drop=True)

def exportar(matriz, matriz_zonas, matriz_transito, necesidad, tabla_pesos,
             reservas, asignacion, consumos, ruta):
    renombres = {cod: f'{cod} - {suc}' for cod, suc in config.BODEGAS_ABASTECIMIENTO.items()}
    with pd.ExcelWriter(ruta, engine='openpyxl') as writer:
        _limpiar(reservas).to_excel(writer, sheet_name='Reservas', index=False)
        _limpiar(matriz).rename(columns=renombres).to_excel(writer, sheet_name='Global', index=False)
        _limpiar(matriz_transito).rename(columns=renombres).to_excel(writer, sheet_name='Tránsito', index=False)
        for zona, bodegas in config.ZONAS_ABASTECIMIENTO.items():
            sub = _limpiar(matriz_por_zona(matriz_zonas, matriz_transito, necesidad, bodegas))
            sub.rename(columns=renombres).to_excel(writer, sheet_name=zona[:31], index=False)
            pintar_puntos(writer.sheets[zona[:31]], bodegas)
            pintar_estado(writer.sheets[zona[:31]])
        _limpiar(_hoja_lotes(asignacion)).to_excel(writer, sheet_name='Lotes', index=False)
        _limpiar(consumos).to_excel(writer, sheet_name='Consumos', index=False)
        tabla_pesos.to_excel(writer, sheet_name='Pesos', index=False)
    return ruta

def transito_desde_archivo(df, col_codigo='Codigo', col_destino='Bodega Destino', col_cantidad='Unidades'):
    df = df.copy()
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    # El archivo trae la bodega destino por nombre; se convierte al código de config
    por_nombre = {' '.join(suc.upper().split()): c for c, suc in config.BODEGAS_ABASTECIMIENTO.items()}
    bod = df[col_destino].astype(str).str.upper().str.split().str.join(' ').map(por_nombre)
    tmp = df.assign(**{'CODIGO': cod, 'CODIGO BODEGA': bod}).dropna(subset=['CODIGO BODEGA'])
    serie = tmp.groupby(['CODIGO', 'CODIGO BODEGA'])[col_cantidad].sum()
    serie = serie[serie > 0]
    return serie.reset_index(name='Transito')

def molecula_por_codigo(df_todo, col_codigo='Codigo', col_mol='Codigo_Molecula'):
    c = df_todo[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    return pd.Series(df_todo[col_mol].astype(str).str.strip().values, index=c)

def cubrir_faltante_molecula(pesos, disp, mol_map, codigos_fomag, comerciales,
                             col_codigo='CODIGO', col_bodega='CODIGO BODEGA'):
    """Los códigos con stock y sin consumo propio cubren la demanda que le falta a su molécula.
    El faltante de FOMAG solo lo cubren códigos habilitados; los demás cubren el de Nueva EPS.
    Un medicamento COMERCIAL no habilitado no suple. Devuelve (pesos, disp)."""
    disp = disp.copy()
    disp['Cubre_Molecula'] = 0
    disp['Habilitado_FOMAG'] = np.where(disp[col_codigo].isin(codigos_fomag), 'Sí', 'No')
    mol = disp[col_codigo].map(mol_map)
    con_mol = mol.notna() & ~mol.isin(['nan', '0', ''])

    # Faltante por molécula x bodega, separado en FOMAG y el resto (dónde falta)
    tmp = pesos[[col_codigo, col_bodega, 'Ponderado', 'Ponderado_Fomag']].copy()
    d = disp.set_index(col_codigo)
    sin_cubrir = (d['Faltante'] / d['Demanda'].where(d['Demanda'] > 0)).reindex(tmp[col_codigo]).fillna(0).values
    tmp['Falta_Fomag'] = tmp['Ponderado_Fomag'] * sin_cubrir
    tmp['Falta_Otros'] = (tmp['Ponderado'] - tmp['Ponderado_Fomag']) * sin_cubrir
    tmp['MOL'] = tmp[col_codigo].map(mol_map)
    patron = (tmp[(tmp['Falta_Fomag'] + tmp['Falta_Otros']) > 0]
              .groupby(['MOL', col_bodega], as_index=False)[['Falta_Fomag', 'Falta_Otros']].sum())
    patron_por_molecula = {m: g for m, g in patron.groupby('MOL')}

    # Unidades que le faltan a cada molécula, repartidas entre FOMAG y el resto
    falta = disp[con_mol].groupby(mol[con_mol])['Faltante'].sum()
    falta_fomag, falta_otros = {}, {}
    for m, g in patron_por_molecula.items():
        total = int(falta.get(m, 0))
        otros = int(round(total * g['Falta_Otros'].sum() / (g['Falta_Fomag'].sum() + g['Falta_Otros'].sum())))
        falta_otros[m], falta_fomag[m] = otros, total - otros

    # Candidatos: sin demanda propia y con stock libre; primero el de mayor stock
    no_suplen = set(comerciales) - set(codigos_fomag)
    cand = disp[(disp['Demanda'] == 0) & (disp['Colchon'] > 0) & con_mol
                & ~disp[col_codigo].isin(no_suplen)].sort_values('Colchon', ascending=False)
    filas = []
    for idx, c in cand.iterrows():
        m = mol_map.get(c[col_codigo])
        if m not in patron_por_molecula:
            continue
        g = patron_por_molecula[m]
        habilitado = c[col_codigo] in codigos_fomag
        toma_fomag = int(min(c['Colchon'], falta_fomag[m])) if habilitado else 0
        toma_otros = int(min(c['Colchon'] - toma_fomag, falta_otros[m]))
        if toma_fomag + toma_otros <= 0:
            continue
        falta_fomag[m] -= toma_fomag
        falta_otros[m] -= toma_otros

        und = pd.Series(0.0, index=g.index)
        if toma_fomag:
            und += toma_fomag * g['Falta_Fomag'] / g['Falta_Fomag'].sum()
        if toma_otros:
            und += toma_otros * g['Falta_Otros'] / g['Falta_Otros'].sum()
        necesita = g['Falta_Otros'] + (g['Falta_Fomag'] if habilitado else 0)
        nuevas = pd.DataFrame({col_codigo: c[col_codigo], col_bodega: g[col_bodega].values,
                               'Ponderado': necesita.values, 'Ponderado_Fomag': 0.0,
                               'Peso': (und / und.sum()).values})
        filas.append(nuevas[nuevas['Ponderado'] > 0])
        disp.loc[idx, 'Cubre_Molecula'] = toma_fomag + toma_otros

    if filas:
        pesos = pd.concat([pesos] + filas, ignore_index=True)
    disp['Disponible'] += disp['Cubre_Molecula']
    disp['Colchon'] -= disp['Cubre_Molecula']
    return pesos, disp

def lotes_repartibles_desde_archivo(df, hoy=None, meses_minimos=0, col_codigo='Codigo Articulo', col_lote='Lote',
                                    col_venc='Fecha Lote', col_cantidad='Unidades', col_desc='Descripcion', col_lab='Grupo'):
    hoy = pd.Timestamp(hoy) if hoy is not None else pd.Timestamp.today().normalize()
    df = df.copy()
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    venc = pd.to_datetime(df[col_venc], errors='coerce')
    uni = pd.to_numeric(df[col_cantidad], errors='coerce').fillna(0)
    limite = hoy + pd.DateOffset(months=meses_minimos)

    ok = (venc.notna() & (venc >= limite) & (venc.dt.year >= hoy.year) & (uni > 0)
    & ~cod.str.upper().str.startswith('CONT'))
    out = pd.DataFrame({
        'CODIGO': cod[ok],
        'Descripcion': df[col_desc].astype(str).str.strip()[ok] if col_desc in df.columns else '',
        'Laboratorio': df[col_lab].astype(str).str.strip()[ok] if col_lab in df.columns else '',
        'Lote': df[col_lote].astype(str).str.strip()[ok],
        'Vence': venc[ok],
        'Unidades': uni[ok].astype('int64'),
    })
    return out.sort_values(['CODIGO', 'Vence']).reset_index(drop=True)

def asignar_lotes(rep, lotes, grupos_distancia, col_codigo='CODIGO', col_bodega='CODIGO BODEGA'):
    """Asigna lotes a las unidades repartidas, por vencimiento (FIFO) segun
    distancia: bodegas cercanas/alta rotacion reciben los vencimientos mas
    proximos; las lejanas los mas largos. Si no alcanza el lote vendible,
    recorta (opcion B). Devuelve filas CODIGO/BODEGA/Descripcion/Laboratorio/
    Lote/Vence/Grupo/Unidades."""
    rep = rep[rep['Unidades'] > 0].copy()
    rep['Grupo'] = rep[col_bodega].map(grupos_distancia).fillna(9).astype(int)
    lotes_por_cod = {c: g for c, g in lotes.groupby(col_codigo)}

    filas = []
    for cod, grp in rep.groupby(col_codigo):
        disp = lotes_por_cod.get(cod)
        if disp is None:
            continue   # sin lote vendible -> toda esa cantidad se recorta

        # Orden de bodegas: grupo de distancia (1->4), y dentro, mayor cantidad
        # (alta rotacion) primero. Asi las cercanas toman los vencimientos cortos.
        orden = grp.sort_values(['Grupo', 'Unidades'], ascending=[True, False])
        cola = disp.sort_values('Vence').to_dict('records')   # lotes por vencimiento asc
        restante = [r['Unidades'] for r in cola]
        i = 0
        for _, b in orden.iterrows():
            falta = int(b['Unidades'])
            while falta > 0 and i < len(cola):
                if restante[i] <= 0:
                    i += 1
                    continue
                toma = min(falta, restante[i])
                filas.append({col_codigo: cod, col_bodega: b[col_bodega],
                              'Descripcion': cola[i].get('Descripcion', ''),
                              'Laboratorio': cola[i].get('Laboratorio', ''),
                              'Lote': cola[i]['Lote'], 'Vence': cola[i]['Vence'],
                              'Grupo': b['Grupo'], 'Unidades': toma})
                falta -= toma
                restante[i] -= toma
            # si falta > 0 y se acabaron los lotes, esa bodega queda recortada
    return pd.DataFrame(filas)


def generar_abastecimiento(df_prescrita,stock_cedi, pedidos,
                           codigos_fomag, transito, info, ruta, mol_map, df_lotes, comerciales):

    pond = ponderar_prescrita(df_prescrita, codigos_fomag=codigos_fomag)  # pesos 50/30/20 con filtro de códigos de FOMAG
    pesos = calcular_pesos(pond)
    demanda = pond.groupby('CODIGO')['Ponderado'].sum()
    disp = calcular_disponible(stock_cedi, pedidos, demanda)
    pesos, disp = cubrir_faltante_molecula(pesos, disp, mol_map,codigos_fomag, comerciales)
    a_repartir = dict(zip(disp['CODIGO'], disp['Disponible']))
    rep = repartir(pesos, a_repartir)
    rep = restar_transito(rep, transito)                 # descuenta el tránsito
    lotes = lotes_repartibles_desde_archivo(df_lotes)
    asignacion = asignar_lotes(rep, lotes, config.GRUPOS_DISTANCIA_ABASTECIMIENTO)
    rep = asignacion.groupby(['CODIGO', 'CODIGO BODEGA'], as_index=False)['Unidades'].sum()
    matriz = construir_matriz(rep)                       # matriz ancha (ordenada por consumo)
    matriz_transito = construir_matriz_transito(transito, matriz, info)   # hoja Tránsito (mismo orden)
    transito_total = transito.groupby('CODIGO')['Transito'].sum()   # total en tránsito por código
    matriz = enriquecer_matriz(matriz, info, transito_total)        # + info + comentario + Total Tránsito
    rep_zonas = pd.concat([rep, transito[['CODIGO', 'CODIGO BODEGA']].assign(Unidades=0)], ignore_index=True)
    matriz_zonas = enriquecer_matriz(construir_matriz(rep_zonas), info, transito_total)
    necesidad = pesos.pivot_table(index='CODIGO', columns='CODIGO BODEGA', values='Ponderado', aggfunc='sum', fill_value=0)
    tabla = hoja_pesos(pond)
    reservas = construir_reservas(disp, rep, info)
    consumos = hoja_consumos(df_prescrita, codigos_fomag, info)
    return exportar(matriz, matriz_zonas, matriz_transito, necesidad, tabla, reservas, asignacion, consumos, ruta)

def stock_cedi_desde_archivo(df, col_codigo='Codigo Articulo', col_cantidad='Unidades'):
    """Stock total del CEDI por código, sumando todos los lotes del mismo código.
    Devuelve dict {codigo: unidades}, solo con unidades > 0."""
    df = df.copy()
    cod = df[col_codigo].astype(str).str.strip().replace(r'\.0$', '', regex=True)
    uni = pd.to_numeric(df[col_cantidad], errors='coerce').fillna(0)
    serie = uni.groupby(cod).sum()
    serie = serie[serie > 0]
    return serie.to_dict()

def restar_transito(rep, transito, col_valor='Unidades'):
    if transito is None or transito.empty:
        return rep
    rep = rep.merge(transito, on=['CODIGO', 'CODIGO BODEGA'], how='left')
    rep['Transito'] = rep['Transito'].fillna(0)
    rep[col_valor] = (rep[col_valor] - rep['Transito']).clip(lower=0)
    return rep.drop(columns='Transito')

def info_producto_desde_maestro(maestro, col_codigo='Codigo'):
    cols = ['Nombre', 'Presentación', 'Grupo', 'Pastillas', 'Nombre Comercial', 'Ultimo Costo']
    info = maestro[[col_codigo] + cols].copy()
    # Normalizar el código igual que en el motor y renombrarlo a CODIGO
    info[col_codigo] = info[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    info = info.rename(columns={col_codigo: 'CODIGO', 'Nombre': 'Descripción'})
    info = info.drop_duplicates(subset='CODIGO', keep='first')
    return info

def enriquecer_matriz(matriz, info, transito_total, col_codigo='CODIGO'):
    matriz = matriz.copy()
    # Comentario
    riesgo = set(config.CODIGOS_MATRIZ_RIESGO)
    matriz['Comentario'] = np.where(matriz[col_codigo].isin(riesgo), config.TEXTO_MATRIZ, '')
    # Total en tránsito por código (0 si no tiene)
    matriz['Total Tránsito'] = matriz[col_codigo].map(transito_total).fillna(0)
    # Pegar info de producto
    matriz = matriz.merge(info, on=col_codigo, how='left')
    # Reordenar: CODIGO, info, Comentario, Total Tránsito, bodegas..., Total control
    info_cols = [c for c in info.columns if c != col_codigo]
    bodegas = [c for c in matriz.columns
               if c not in info_cols + [col_codigo, 'Comentario', 'Total Tránsito', 'Total control']]
    orden = [col_codigo] + info_cols + ['Comentario'] + bodegas + ['Total control', 'Total Tránsito']
    return matriz[orden]

# def matriz_lotes_por_zona(matriz, asignacion, bodegas_zona, col_codigo='CODIGO', col_bodega='CODIGO BODEGA'):
#     """Hoja de zona con lotes: una fila por código + lote y una columna por bodega de la zona."""
#     todas = list(config.BODEGAS_ABASTECIMIENTO.keys())
#     extras = ['Total control', 'Total Tránsito']
#     fijas = [c for c in matriz.columns if c not in todas and c not in extras]
#     cols_zona = [b for b in matriz.columns if b in set(bodegas_zona)]
#     cols_final = fijas + ['Lote', 'Vence'] + cols_zona + ['Total zona', 'Total Tránsito']
#     if asignacion.empty:
#         return pd.DataFrame(columns=cols_final)
#
#     a = asignacion[asignacion[col_bodega].isin(cols_zona)]
#     lot = a.pivot_table(index=[col_codigo, 'Lote', 'Vence'], columns=col_bodega,
#                        values='Unidades', aggfunc='sum', fill_value=0)
#     lot = lot.reindex(columns=cols_zona, fill_value=0)
#     lot['Total zona'] = lot.sum(axis=1)
#     lot = lot.reset_index()
#
#     sub = matriz[fijas + ['Total Tránsito']].merge(lot, on=col_codigo, how='inner')
#     sub = sub.sort_values([col_codigo, 'Vence', 'Lote']).reset_index(drop=True)
#
#     # Transito por código: solo en la primera fila para que la columna se pueda sumar
#     sub.loc[sub.duplicated(col_codigo), 'Total Tránsito'] = 0
#     sub['Vence'] = pd.to_datetime(sub['Vence']).dt.strftime('%Y-%m-%d')
#
#     return sub[cols_final]

def matriz_por_zona(matriz, matriz_transito, necesidad, bodegas_zona, col_codigo='CODIGO'):
    todas = list(config.BODEGAS_ABASTECIMIENTO.keys())
    extras = ['Total control', 'Total Tránsito']
    fijas = [c for c in matriz.columns if c not in todas and c not in extras]
    cols_zona = [b for b in matriz.columns if b in set(bodegas_zona)]

    # Tránsito y necesidad de cada código en las bodegas de la zona, alineados a las filas de la matriz
    tr = (matriz_transito.set_index(col_codigo).reindex(columns=cols_zona)
          .reindex(matriz[col_codigo]).fillna(0).astype('int64'))
    tr.index = matriz.index
    nec = np.rint(necesidad.reindex(columns=cols_zona).reindex(matriz[col_codigo]).fillna(0)).astype('int64')
    nec.index = matriz.index

    partes = [matriz[fijas]]
    for b in cols_zona:
        # Se envía: hay cantidad por despachar. No se envía: si el transito ya cubre lo del punto
        estado = np.where(matriz[b] > 0, 'SE ENVIA', np.where(tr[b] > 0, 'NO SE ENVIA', np.where(nec[b] > 0, 'SIN STOCK', 'SIN ROTACIÓN')))
        partes.append(pd.DataFrame({f'Sugerido {b} - {config.BODEGAS_ABASTECIMIENTO[b]}': matriz[b], f'Transito {b}': tr[b], f'Necesidad {b}': nec[b],
                                    f'Estado {b}': estado}, index=matriz.index))
    sub = pd.concat(partes, axis=1)
    sub['Total Necesita'] = nec.sum(axis=1)
    sub['Total zona'] = matriz[cols_zona].sum(axis=1)
    sub['Total Tránsito'] = tr.sum(axis=1)
    return sub[(sub['Total zona'] > 0) | (sub['Total Tránsito'] > 0)]

def construir_matriz_transito(transito, matriz_ref, info, col_codigo='CODIGO', col_bodega='CODIGO BODEGA'):
    orden = [c for c in matriz_ref.columns if c in config.BODEGAS_ABASTECIMIENTO]
    mt = transito.pivot_table(index=col_codigo, columns=col_bodega,
                                values='Transito', aggfunc='sum', fill_value=0)
    mt = mt.reindex(columns=orden, fill_value=0)
    mt['Total Tránsito'] = mt.sum(axis=1)
    mt = mt.reset_index()
    mt = mt.merge(info, on=col_codigo, how='left')
    info_cols = [c for c in info.columns if c != col_codigo]
    bodegas = [c for c in mt.columns if c not in info_cols + [col_codigo, 'Total Tránsito']]
    orden_cols = [col_codigo] + info_cols + bodegas + ['Total Tránsito']
    return mt[orden_cols]

def pedidos_canal_desde_proyeccion(df, col_codigo='Codigo'):
    df = df.copy()
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    out = pd.DataFrame({
        'CODIGO': cod,
        'Pedir_Disp': pd.to_numeric(df['Pedir Dispensacion Total sin CEDI'],
                                    errors='coerce').fillna(0),
        'Pedir_Rem': pd.to_numeric(df['Pedir Remisiones sin CEDI'],
                                   errors='coerce').fillna(0),
        'Rotacion_Disp': df['Rotacion_Dispensacion'].astype(str).str.strip(),
    })
    return out.groupby('CODIGO', as_index=False).agg(
        Pedir_Disp=('Pedir_Disp', 'sum'), Pedir_Rem=('Pedir_Rem', 'sum'),
        Rotacion_Disp=('Rotacion_Disp', 'first'))

def _cum_y_expediente(seire):
    """Normaliza un CUM 'expediente-consecutivo' (sin ceros a la izquierda).
    Devuelve (cum, expediente); quedan vacios cuando el texto no es un CUM"""
    partes = seire.astype(str).str.strip().str.replace(' ','').str.extract(r'^0*(\d+)-0*(\d+)$')
    return partes[0] + '-' + partes[1], partes[0]

def medicamentos_comerciales(maestro, col_codigo='Codigo', col_categoria_M='Categoria Medicamento',
                             col_categoria='Categoria'):
    cod = maestro[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    cat = (maestro[col_categoria].astype(str).str.upper().str.contains('MEDICAMENTOS', na=False) &
           maestro[col_categoria_M].astype(str).str.upper().str.contains('COMERCIAL', na=False))
    return set(cod[cat])

def codigos_fomag_desde_archivo(df, maestro, comerciales, col_codigo='Código Articulo', col_estado='Estado Referencia',
                                col_contrato='Nro. Contrato', col_padre='Codigo Padre', col_cum='Código Cum.1'):
    """ Codigos que pueden recibir demanda FOMAG: los amarrados en el contrato vigente , los que tienen el mismo CUM,
    en tabletas/capsular el mismo expediente, un medicamento comercial solo entra si está amarrado."""
    df = df.copy()
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    activo = df[col_estado].astype(str).str.strip().str.upper().eq('A') if col_estado in df.columns else True
    cto_act = df[col_contrato].astype(str).str.strip().str.upper().eq(CONTRATO_FOMAG_VIGENTE) if col_contrato in df.columns else True
    vigente = df[activo & cto_act]
    amarrados = set(cod[activo & cto_act & cod.ne('') & ~cod.str.upper().str.startswith('SIN ARTICULO')])

    # CUM y expedientes contratados (el padre del contrato es el CUM)
    cums, expedientes = set(), set()
    for col in (col_padre, col_cum):
        if col in vigente.columns:
            cum, exp = _cum_y_expediente(vigente[col])
            cums |= set(cum.dropna())
            expedientes |= set(exp.dropna())

    cod_m = maestro['Codigo'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    cum_m, exp_m = _cum_y_expediente(maestro['Cum'])
    tableteria = maestro['Presentación'].astype(str).str.strip().str.upper().isin(['TABLETA', 'CAPSULA'])
    por_regla = (cum_m.isin(cums) | (tableteria & exp_m.isin(expedientes))) & ~cod_m.isin(comerciales)
    return amarrados | set(cod_m[por_regla])

def filtrar_fomag_sin_contrato(df, codigos_fomag, col_codigo='CODIGO', col_cliente='SIGLA_COMERCIAL_CLIENTE',
                               sigla_fomag='FIDEICOMISOS'):
    df =df.copy()
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    es_fomag = df[col_cliente].astype(str).str.upper().str.contains(sigla_fomag.upper(), na=False)
    sin_contrato = ~cod.isin(codigos_fomag)
    quitar = es_fomag & sin_contrato
    return df[~quitar].copy()

