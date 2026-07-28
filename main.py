import re
import pandas as pd
from datetime import date, datetime
from openpyxl.styles import Font, Alignment, PatternFill

from config import RUTA_MAESTRO, RUTA_DISPENSACION, RUTA_REMISIONES, RUTA_STOCK_BODEGA, RUTA_STOCK_PUNTOS, RUTA_MOLECULAS
from processor import ProyeccionProcessor

_CHARS_ILEGALES = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')

# Fila de procedencia: de donde sale cada columna. Se escribe encima de los
# titulos para que cualquiera entienda el origen del dato sin preguntar.
DESCRIPCIONES_COLUMNAS = {
    # --- identificacion (archivo Maestro / BD) ---
    'Codigo': 'Maestro (BD) - codigo del articulo',
    'Nombre': 'Maestro (BD) - nombre del articulo',
    'Grupo': 'Maestro (BD) - laboratorio',
    'Proveedor': 'Maestro (BD) - ultimo proveedor de compra',
    'Ultimo Costo': 'Maestro (BD) - ultimo costo de compra',
    'Costo Promedio': 'Maestro (BD) - costo promedio',
    'Codigo_Molecula': 'Archivo Molecula_Compra - codigo de molecula',
    'Molecula': 'Archivo Molecula_Compra - nombre de molecula',
    'N_Productos': 'Calculado - numero de productos en la molecula',
    # --- consumo por canal / contrato ---
    'Consumo_NEPS_Capita': 'Dispensacion - cliente NUEVA EPS + servicio CAPITADO',
    'Consumo_NEPS_Evento': 'Dispensacion - cliente NUEVA EPS + servicio POS / MIPRES / TUTELA',
    'Consumo_FOMAG_Evento': 'Dispensacion - cliente Fiduprevisora / FIDEICOMISOS (FOMAG)',
    'Consumo_Sin_Clasificar': 'Dispensacion - filas que no coincidieron con ninguna regla (deberia ser 0)',
    'Consumo_Remisiones': 'Archivo Remisiones - consumo total del periodo',
    'Consumo_Dispensacion_Total': 'Calculado - suma de los canales de dispensacion (Capita + Evento + FOMAG)',
    'Consumo_Molecula': 'Calculado - suma del Consumo_Acum de todos los productos de la molecula',
    'Consumo_Acum': 'Calculado - consumo total = dispensacion + remisiones (meses alineados)',
    # --- rotacion ---
    'Rotacion': 'Calculado - Pareto ABC sobre Consumo_Acum (A=80%, M=95%, B=resto)',
    'Rotacion_Dispensacion': 'Calculado - Pareto ABC solo sobre el consumo de dispensacion',
    'Rotacion_Remisiones': 'Calculado - Pareto ABC solo sobre el consumo de remisiones',
    # --- stock ---
    'Stock_Bodega_Principal': 'Valorizado CEDI - unidades en bodega principal',
    'Stock_Puntos_Dispensacion': 'Valorizado Puntos - suma de unidades de los puntos de dispensacion',
    'Stock_Total': 'Calculado - Stock_Bodega_Principal + Stock_Puntos_Dispensacion',
    # --- motor de pedido ---
    'Demanda_Mensual': 'Calculado - demanda mensual ponderada 70/30 (ult. 3 meses 70%, primeros 3 meses 30%)',
    'Demanda_Disp_Mensual': 'Calculado - demanda mensual 70/30 solo del canal dispensacion',
    'Demanda_Rem_Mensual': 'Calculado - demanda mensual 70/30 solo del canal remisiones',
    'Demanda_Diaria': 'Calculado - Demanda_Mensual / 30 (consumo promedio por dia)',
    'Cobertura_Dias': 'Parametro (config.py) - dias de cobertura segun la rotacion',
    'Stock_Seguridad': 'Calculado - demanda diaria x dias de seguridad',
    'Necesidad_Disp': 'Calculado - unidades objetivo del canal dispensacion (demanda_disp/30 x factor_disp, dias de config *_DISP)',
    'Necesidad_Rem': 'Calculado - unidades objetivo del canal remisiones (demanda_rem/30 x factor_remi, dias de config *_REMI)',
    'Necesidad_Mensual': 'Calculado - Necesidad_Disp + Necesidad_Rem (necesidad total del producto)',
    'Cantidad_a_Pedir_Rest_Inv': 'Calculado - Pedir_Dispensacion_Total + Pedir_Remisiones (cada canal con su stock)',
    'Pedir_Dispensacion_Total': 'Calculado - pedido del canal dispensacion vs stock total (bodega + puntos)',
    'Pedir_NEPS_Capita': 'Calculado - parte del pedido de dispensacion segun peso historico de Capita',
    'Pedir_NEPS_Evento': 'Calculado - parte del pedido de dispensacion segun peso historico de Evento',
    'Pedir_FOMAG_Evento': 'Calculado - parte del pedido de dispensacion segun peso historico de FOMAG',
    'Pedir_Remisiones': 'Calculado - pedido del canal remisiones vs SOLO bodega principal (sin puntos)',
    'Valorizado': 'Calculado - cantidad a pedir de ESTA hoja * Ultimo Costo (si es 0, usa Costo Promedio)',
    'Estado': 'Calculado - COMPRAR si hay cantidad a pedir en ESTA hoja, si no NO COMPRAR',
}


def _descripcion_columna(col):
    """Procedencia de una columna. Las columnas mensuales se resuelven por patron."""
    if col in DESCRIPCIONES_COLUMNAS:
        return DESCRIPCIONES_COLUMNAS[col]
    col = str(col)
    if re.match(r'Consumo_Disp_[A-Za-z]{3}_\d{4}$', col):
        return 'Dispensacion - consumo del mes'
    if re.match(r'Consumo_Rem_[A-Za-z]{3}_\d{4}$', col):
        return 'Remisiones - consumo del mes'
    if re.match(r'Consumo_[A-Za-z]{3}_\d{4}$', col):
        return 'Dispensacion + Remisiones - consumo del mes'
    return ''


def _limpiar_df(df):
    """Quita caracteres de control que openpyxl rechaza."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        df[col] = df[col].astype(str).str.replace(_CHARS_ILEGALES, '', regex=True)
    return df


def cargar_datos():
    maestro = pd.read_excel(RUTA_MAESTRO)
    molecula_compra = pd.read_excel(RUTA_MOLECULAS)
    consumo_dispensacion = pd.read_excel(RUTA_DISPENSACION)
    consumo_remisiones = pd.read_excel(RUTA_REMISIONES)
    stock_bodega = pd.read_excel(RUTA_STOCK_BODEGA)
    stock_puntos = pd.read_excel(RUTA_STOCK_PUNTOS)
    return maestro, consumo_dispensacion, consumo_remisiones, stock_bodega, stock_puntos, molecula_compra


def _valorizar_estado(sub, col_cantidad):
    """
    Sobrescribe 'Valorizado' y 'Estado' en `sub` usando el pedido de `col_cantidad`
    (asi cada hoja de canal valoriza SOLO su propio pedido). Reutiliza la misma
    logica de costo del processor (ultimo costo; si es 0, costo promedio).
    """
    sub['Valorizado'] = ProyeccionProcessor._valorizar(
        sub[col_cantidad], sub.get('Ultimo Costo'), sub.get('Costo Promedio'))
    sub['Estado'] = sub[col_cantidad].gt(0).map({True: 'COMPRAR', False: 'NO COMPRAR'})
    return sub


def construir_hojas(processor):
    """
    Arma las hojas del Excel.

    - Dispensacion: consumo y pedido del canal de dispensacion (Capita + Evento
      + FOMAG), solo productos con movimiento o pedido en ese canal.
    - Remisiones:   lo mismo para el canal de remisiones.
    - Todo:         la base completa, incluyendo el consumo mes a mes.
    """
    df = processor.maestro_consumo
    mensuales = list(getattr(processor, 'cols_consumo_mensual', []))
    mensuales_disp = list(getattr(processor, 'cols_consumo_mensual_disp', []))
    mensuales_rem = list(getattr(processor, 'cols_consumo_mensual_rem', []))
    pedir_contratos = list(processor.SEGMENTOS_CONTRATO.values())



    hojas = {}

    # ---------------------------------------------------------- DISPENSACION

    colsDisp =['Codigo', 'Nombre', 'Codigo_Molecula', 'Molecula','Nombre Comercial', 'Grupo', 'Proveedor',
            'Costo Promedio', 'Ultimo Costo', 'Consumo_NEPS_Capita','Consumo_NEPS_Evento',
            'Consumo_FOMAG_Evento', 'Consumo_Sin_Clasificar', 'Consumo_Dispensacion_Total',
            *mensuales_disp, 'Demanda_Disp_Mensual', 'Rotacion_Dispensacion', 'Stock_Bodega_Principal',
            'Stock_Puntos_Dispensacion', 'Stock_Total', 'Necesidad_Disp', 'Pedir_NEPS_Capita', 'Pedir_NEPS_Evento',
            'Pedir_FOMAG_Evento', 'Pedir_Dispensacion_Total', 'Estado', 'Valorizado Ult Costo', 'Valorizado Promedio']
    mask = (df.get('Consumo_Dispensacion_Total', 0) > 0) | (df.get('Pedir_Dispensacion_Total', 0) > 0)
    disp = (df.loc[mask, [c for c in colsDisp if c in df.columns]]
            .sort_values('Pedir_Dispensacion_Total', ascending=False).copy())
    _valorizar_estado(disp, 'Pedir_Dispensacion_Total')   # valorizado del canal dispensacion
    hojas['Dispensacion'] = disp

    # ------------------------------------------------------------ REMISIONES
    # Remisiones son clientes distintos: el stock de puntos NO les aplica (ni se
    # muestra ni interviene en el pedido). Solo bodega principal.
    colsRem = ['Codigo', 'Nombre', 'Codigo_Molecula', 'Molecula','Nombre Comercial', 'Grupo', 'Proveedor',
               'Costo Promedio', 'Ultimo Costo', *mensuales_rem, 'Consumo_Remisiones','Demanda_Rem_Mensual',
               'Rotacion_Remisiones','Stock_Bodega_Principal', 'Sotck_Bodega_Dispensacion', 'Stock_Total','Necesidad_Rem','Pedir_Remisiones',
               'Estado', 'Valorizado Ult Costo', 'Valorizado Promedio']
    mask = (df.get('Consumo_Remisiones', 0) > 0) | (df.get('Pedir_Remisiones', 0) > 0)
    rem = (df.loc[mask, [c for c in colsRem if c in df.columns]]
           .sort_values('Pedir_Remisiones', ascending=False).copy())
    _valorizar_estado(rem, 'Pedir_Remisiones')            # valorizado del canal remisiones
    hojas['Remisiones'] = rem

    # ------------------------------------------------------------------ TODO
    colsTodo = ['Codigo', 'Nombre', 'Codigo_Molecula', 'Molecula','Nombre Comercial', 'Grupo', 'Proveedor',
                'Costo Promedio', 'Ultimo Costo', 'Consumo_Molecula', 'Consumo_NEPS_Capita',
                'Consumo_NEPS_Evento', 'Consumo_FOMAG_Evento', 'Consumo_Dispensacion_Total',
                'Consumo_Remisiones', 'Consumo_Sin_Clasificar', *mensuales, 'Consumo_Acum',
                'Rotacion', 'Rotacion_Dispensacion', 'Rotacion_Remisiones','Demanda_Disp_Mensual',
                'Demanda_Rem_Mensual','Demanda_Mensual','Demanda_Diaria',
                'Necesidad_Disp','Necesidad_Rem','Necesidad_Mensual','Valorizado Promedio Sin Rest Inv','Valorizado Ult Costo Sin Rest Inv', 'Stock_Bodega_Principal',
                'Stock_Puntos_Dispensacion','Stock_Total','Cantidad_a_Pedir_Rest_Inv',
                'Valorizado Promedio','Valorizado Ult Costo','Pedir_NEPS_Capita', 'Pedir_NEPS_Evento','Pedir_FOMAG_Evento',
                'Pedir_Dispensacion_Total','Pedir_Remisiones','Estado']
    hojas['Todo'] = (df[[c for c in colsTodo if c in df.columns]]
                     .sort_values('Cantidad_a_Pedir_Rest_Inv', ascending=False))

    # -------------------------------------------------------------- MOLECULA
    cols = ['Codigo_Molecula', 'Molecula','Nombre Comercial', 'N_Productos', 'Rotacion',
            'Consumo_Molecula', 'Stock_Total', 'Demanda_Mensual', 'Demanda_Diaria', 'Cobertura_Dias',
            'Stock_Seguridad', 'Necesidad_Mensual',
            'Cantidad_a_Pedir_Rest_Inv', 'Pedir_Dispensacion_Total', *pedir_contratos]
    mol = processor.pedido_molecula
    hojas['Pedido_Molecula'] = (mol[[c for c in cols if c in mol.columns]]
                                .sort_values('Cantidad_a_Pedir_Rest_Inv', ascending=False))

    return hojas


def exportar_excel(processor, ruta=None):
    if ruta is None:
        ruta = f'Resultados_Proyeccion_{date.today():%Y-%m-%d}.xlsx'

    hojas = construir_hojas(processor)

    fuente_desc = Font(italic=True, size=8, color='555555')
    fuente_titulo = Font(bold=True)
    relleno_desc = PatternFill('solid', fgColor='FFF3E0')
    alineacion_desc = Alignment(wrap_text=True, vertical='top')

    def _escribir(destino):
        with pd.ExcelWriter(destino, engine='openpyxl') as writer:
            for nombre, sub in hojas.items():
                sub = _limpiar_df(sub)
                # startrow=1 deja libre la fila 1 para la procedencia;
                # los titulos quedan en la fila 2 y los datos desde la 3.
                sub.to_excel(writer, sheet_name=nombre[:31], index=False, startrow=1)
                ws = writer.sheets[nombre[:31]]

                for j, col in enumerate(sub.columns, start=1):
                    celda = ws.cell(row=1, column=j, value=_descripcion_columna(col))
                    celda.font = fuente_desc
                    celda.fill = relleno_desc
                    celda.alignment = alineacion_desc
                    ws.cell(row=2, column=j).font = fuente_titulo

                ws.freeze_panes = 'A3'                       # fija procedencia + titulos
                ws.row_dimensions[1].height = 60
                if ws.max_row > 2:
                    ws.auto_filter.ref = f'A2:{ws.cell(2, ws.max_column).coordinate}'

                # Ancho por columna, ignorando la fila de procedencia (es larga y
                # va con ajuste de texto); se mide sobre titulo + una muestra de datos.
                for j in range(1, ws.max_column + 1):
                    letra = ws.cell(row=2, column=j).column_letter
                    muestra = [ws.cell(row=r, column=j).value
                               for r in range(2, min(ws.max_row, 300) + 1)]
                    ancho = max((len(str(v)) for v in muestra if v is not None), default=8)
                    ws.column_dimensions[letra].width = min(max(ancho + 2, 12), 40)

    try:
        _escribir(ruta)
    except PermissionError:
        # El archivo queda bloqueado si esta abierto en Excel
        alterna = f'Resultados_Proyeccion_{date.today():%Y-%m-%d}_{datetime.now():%H%M%S}.xlsx'
        print(f"\n[!] '{ruta}' esta abierto o bloqueado. Escribiendo en '{alterna}'.")
        _escribir(alterna)
        ruta = alterna

    print(f'\n[OK] Exportado: {ruta}')
    for nombre, sub in hojas.items():
        print(f'       {nombre:<18} {len(sub):>6,} filas x {len(sub.columns):>2} columnas')
    return ruta


def main():
    maestro, consumo_dispensacion, consumo_remisiones, stock_bodega, stock_puntos, molecula_compra = cargar_datos()

    processor = ProyeccionProcessor(maestro, consumo_dispensacion, consumo_remisiones, stock_bodega, stock_puntos, molecula_compra)
    processor.procesar()

    processor.imprimir_resumen_consolidado()
    processor.imprimir_resumen_base()
    processor.auditoria_integridad()
    processor.imprimir_resumen_rotacion()
    processor.imprimir_resumen_rotacion_canal()
    processor.imprimir_resumen_mensual()
    processor.imprimir_resumen_stock()
    processor.imprimir_resumen_contratos()
    processor.imprimir_resumen_molecula()
    exportar_excel(processor)


if __name__ == '__main__':
    main()
