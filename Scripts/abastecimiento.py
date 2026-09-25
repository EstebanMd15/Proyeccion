from Scripts import config
import numpy as np
import pandas as pd

def ponderar_prescrita(df, col_periodo='PERIODO', col_codigo='CODIGO',
                       col_bodega='CODIGO BODEGA', col_cantidad='CONSUMO TOTAL'):
    df= df.copy()

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
    orden = (reparto.groupby(col_bodega)['Ponderado'].sum()
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

def exportar(matriz, matriz_transito, tabla_pesos, ruta):
    renombres = {cod: f'{cod} - {suc}' for cod, suc in config.BODEGAS_ABASTECIMIENTO.items()}
    with pd.ExcelWriter(ruta, engine='openpyxl') as writer:
        # Global
        matriz.rename(columns=renombres).to_excel(writer, sheet_name='Global', index=False)
        # Tránsito (código x bodega)
        matriz_transito.rename(columns=renombres).to_excel(writer, sheet_name='Tránsito', index=False)
        # Una hoja por zona
        for zona, bodegas in config.ZONAS_ABASTECIMIENTO.items():
            sub = matriz_por_zona(matriz, bodegas)
            sub.rename(columns=renombres).to_excel(writer, sheet_name=zona[:31], index=False)
        # Pesos
        tabla_pesos.to_excel(writer, sheet_name='Pesos', index=False)
    return ruta

def generar_abastecimiento(df_prescrita, pedidos, transito, info, ruta):
    pond = ponderar_prescrita(df_prescrita)              # pesos 50/30/20
    pesos = calcular_pesos(pond)
    rep = repartir(pesos, pedidos)                       # reparte la cantidad recibida
    rep = restar_transito(rep, transito)                 # descuenta el tránsito
    matriz = construir_matriz(rep)                       # matriz ancha (ordenada por consumo)
    matriz_transito = construir_matriz_transito(transito, matriz, info)   # hoja Tránsito (mismo orden)
    transito_total = transito.groupby('CODIGO')['Transito'].sum()   # total en tránsito por código
    matriz = enriquecer_matriz(matriz, info, transito_total)        # + info + comentario + Total Tránsito
    tabla = hoja_pesos(pond)
    return exportar(matriz, matriz_transito, tabla, ruta)

def pedidos_desde_maestro(maestro, col_codigo='Codigo', col_pedido='Cantidad a Pedir sin CEDI'):
    maestro = maestro.copy()
    m = maestro[maestro[col_pedido] > 0]
    claves = m[col_codigo].astype(str).str.strip()
    return dict(zip(claves, m[col_pedido]))

def recibidas_desde_archivo(df, col_codigo='Cód Artículo', col_cantidad='Und. Despachadas'):
    df = df.copy()
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', "", regex=True)
    #Sumar por código (por si hay varias linea de despacho del mismo
    serie = df.assign(_cod=cod).groupby('_cod')[col_cantidad].sum()
    # Trae solo las que tienen cantidad > 0
    serie = serie[serie > 0]
    return serie.to_dict()

def transito_desde_archivo(df, col_codigo='Codigo', col_bodega='código Bodega ',
                           col_cantidad='Unidades'):
    df = df.copy()
    # Normalizar código y bodega a texto (quita el .0 de Excel)
    cod = df[col_codigo].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    bod = df[col_bodega].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    # Sumar por código + bodega (varias lineas dell mismo código)
    tmp = df.assign(**{'CODIGO': cod, 'CODIGO BODEGA': bod})
    serie = tmp.groupby(['CODIGO', 'CODIGO BODEGA'])[col_cantidad].sum()
    serie = serie[serie > 0]
    return serie.reset_index(name='Transito')

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

def matriz_por_zona(matriz, bodegas_zona):
    todas = list(config.BODEGAS_ABASTECIMIENTO.keys())
    extras = ['Total control', 'Total Tránsito']
    fijas = [c for c in matriz.columns if c not in todas and c not in extras]
    cols_zona = [b for b in matriz.columns if b in set(bodegas_zona)]
    sub = matriz[fijas + cols_zona].copy()
    sub['Total zona'] = sub[cols_zona].sum(axis=1)
    sub['Total Tránsito'] = matriz['Total Tránsito']
    sub = sub[sub['Total zona'] > 0] # Solo trae las que tiene cantidad > 0
    return sub

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