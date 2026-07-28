"""
Comparador V1 vs V2.

  V1 = criterio_rotacion='formulas' -> Pareto sobre 'Formulas_Ponderadas' (LEGACY)
  V2 = criterio_rotacion='volumen'  -> Pareto sobre 'Consumo_Acum'        (VIGENTE)

Corre los dos criterios sobre exactamente los mismos datos, imprime la
comparacion y exporta un Excel con ambos resultados lado a lado.

Sirve para auditar / justificar el cambio de criterio. El pipeline productivo
(main.py) corre siempre con 'volumen'.

Uso:
    python comparar_v1_v2.py
"""
import re
from datetime import date, datetime

import pandas as pd
import numpy as np

from config import (RUTA_MAESTRO, RUTA_DISPENSACION, RUTA_REMISIONES,
                    RUTA_STOCK_BODEGA, RUTA_STOCK_PUNTOS, RUTA_MOLECULAS)
from processor import ProyeccionProcessor

_CHARS_ILEGALES = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
LIN = "=" * 96


def _limpiar_df(df):
    """Quita caracteres de control que openpyxl no acepta."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        df[col] = df[col].astype(str).str.replace(_CHARS_ILEGALES, '', regex=True)
    return df


def cargar_datos():
    return {
        'maestro': pd.read_excel(RUTA_MAESTRO),
        'consumo_dispensacion': pd.read_excel(RUTA_DISPENSACION),
        'consumo_remisiones': pd.read_excel(RUTA_REMISIONES),
        'stock_bodega': pd.read_excel(RUTA_STOCK_BODEGA),
        'stock_puntos': pd.read_excel(RUTA_STOCK_PUNTOS),
        'molecula_compra': pd.read_excel(RUTA_MOLECULAS),
    }


def correr(datos, criterio):
    """
    Instancia el procesador con COPIAS de los datos.
    Es obligatorio copiar: limpiar_datos() renombra columnas in-place, asi que
    reutilizar los mismos DataFrames reventaria la segunda corrida.
    """
    p = ProyeccionProcessor(
        datos['maestro'].copy(deep=True),
        datos['consumo_dispensacion'].copy(deep=True),
        datos['consumo_remisiones'].copy(deep=True),
        datos['stock_bodega'].copy(deep=True),
        datos['stock_puntos'].copy(deep=True),
        datos['molecula_compra'].copy(deep=True),
        criterio_rotacion=criterio,
    )
    p.procesar()
    return p


# ====================================================================== reportes
def comparar_distribucion(v1, v2):
    print("\n" + LIN)
    print("  1. DISTRIBUCION DE ROTACION (nivel producto)".center(96))
    print(LIN)

    tabla = pd.DataFrame({
        'V1 (Formulas)': v1.maestro_consumo['Rotacion'].value_counts(),
        'V2 (Volumen)': v2.maestro_consumo['Rotacion'].value_counts(),
    }).reindex(['A', 'M', 'B']).fillna(0).astype(int)

    tabla['Dif'] = tabla['V2 (Volumen)'] - tabla['V1 (Formulas)']
    tabla.loc['TOTAL'] = tabla.sum()
    print(tabla.to_string())

    # Cuanto consumo concentra cada letra (test de Pareto)
    print("\n  Test de Pareto - % del consumo total que concentra cada letra:")
    for nombre, p in [('V1', v1), ('V2', v2)]:
        df = p.maestro_consumo
        tot = df['Consumo_Acum'].sum()
        partes = []
        for cat in ['A', 'M', 'B']:
            c = df.loc[df['Rotacion'] == cat, 'Consumo_Acum'].sum()
            n = int((df['Rotacion'] == cat).sum())
            partes.append(f"{cat}: {n:>5,} prod / {c / tot * 100:>5.1f}% consumo")
        print(f"    {nombre}  |  " + "   |  ".join(partes))
    print("\n  (Un Pareto sano espera pocos productos 'A' concentrando ~80% del consumo)")


def comparar_pedido(v1, v2):
    print("\n" + LIN)
    print("  2. CANTIDAD A PEDIR".center(96))
    print(LIN)

    filas = []
    for nombre, p in [('V1 (Formulas)', v1), ('V2 (Volumen)', v2)]:
        prod = p.maestro_consumo
        mol = p.pedido_molecula
        filas.append({
            'Variante': nombre,
            'Unids a pedir (producto)': prod['Cantidad_a_Pedir'].sum(),
            'Productos con pedido': int((prod['Cantidad_a_Pedir'] > 0).sum()),
            'Unids a pedir (molecula)': mol['Cantidad_a_Pedir'].sum(),
        })
    comp = pd.DataFrame(filas).set_index('Variante')
    print(comp.to_string(float_format=lambda x: f'{x:,.0f}'))

    b1 = v1.maestro_consumo['Cantidad_a_Pedir'].sum()
    b2 = v2.maestro_consumo['Cantidad_a_Pedir'].sum()
    print(f"\n  Delta V2 - V1: {b2 - b1:+,.0f} unidades ({(b2 / b1 - 1) * 100:+.1f}%)"
          if b1 else "\n  V1 no genero pedido.")


def comparar_cambios(v1, v2):
    print("\n" + LIN)
    print("  3. QUE PRODUCTOS CAMBIAN".center(96))
    print(LIN)

    m = pd.merge(
        v1.maestro_consumo[['Codigo', 'Nombre', 'Consumo_Acum', 'Stock_Total',
                            'Rotacion', 'Cantidad_a_Pedir']],
        v2.maestro_consumo[['Codigo', 'Rotacion', 'Cantidad_a_Pedir']],
        on='Codigo', how='outer', suffixes=('_V1', '_V2')
    )
    m['Delta_Pedido'] = m['Cantidad_a_Pedir_V2'] - m['Cantidad_a_Pedir_V1']

    cambian = m['Rotacion_V1'] != m['Rotacion_V2']
    print(f"  Cambian de letra: {cambian.sum():,} de {len(m):,} productos "
          f"({cambian.sum() / len(m) * 100:.1f}%)")

    print("\n  Matriz de transicion  V1 (filas) -> V2 (columnas):")
    print(pd.crosstab(m['Rotacion_V1'], m['Rotacion_V2'])
          .reindex(index=['A', 'M', 'B'], columns=['A', 'M', 'B'])
          .fillna(0).astype(int).to_string())

    cols = ['Codigo', 'Nombre', 'Consumo_Acum', 'Stock_Total',
            'Rotacion_V1', 'Rotacion_V2', 'Cantidad_a_Pedir_V1',
            'Cantidad_a_Pedir_V2', 'Delta_Pedido']

    def _mostrar(titulo, sub):
        print(f"\n  {titulo}")
        if sub.empty:
            print("    (ninguno)")
            return
        out = sub[cols].copy()
        out['Nombre'] = out['Nombre'].astype(str).str.slice(0, 40)
        print(out.to_string(index=False))

    _mostrar("SUBEN de B a A  (V1 los subestimaba: alto volumen mal clasificado)",
             m[(m['Rotacion_V1'] == 'B') & (m['Rotacion_V2'] == 'A')]
             .sort_values('Consumo_Acum', ascending=False).head(10))

    _mostrar("BAJAN de A a B  (V1 los sobreestimaba: bajo volumen mal clasificado)",
             m[(m['Rotacion_V1'] == 'A') & (m['Rotacion_V2'] == 'B')]
             .sort_values('Consumo_Acum', ascending=False).head(10))

    _mostrar("MAYOR aumento de pedido en V2",
             m.sort_values('Delta_Pedido', ascending=False).head(10))

    _mostrar("MAYOR reduccion de pedido en V2",
             m.sort_values('Delta_Pedido').head(10))

    return m


def exportar(v1, v2, comparativo, ruta=None):
    if ruta is None:
        ruta = f'Comparacion_V1_vs_V2_{date.today():%Y-%m-%d}.xlsx'

    cols_prod = [
        'Codigo', 'Nombre', 'Codigo_Molecula', 'Molecula',
        'Consumo_NEPS_Capita', 'Consumo_NEPS_Evento', 'Consumo_FOMAG_Evento',
        'Consumo_Remisiones', 'Consumo_Sin_Clasificar', 'Consumo_Acum', 'Consumo_Molecula',
        'Stock_Bodega_Principal', 'Stock_Puntos_Dispensacion', 'Stock_Total',
        'Formulas_Ponderadas', 'Rotacion', 'Demanda_Mensual', 'Cobertura_Meses',
        'Stock_Seguridad', 'Stock_Objetivo', 'Cantidad_a_Pedir',
    ]
    cols_mol = [
        'Codigo_Molecula', 'Molecula', 'N_Productos', 'Rotacion',
        'Consumo_Molecula', 'Formulas_Ponderadas', 'Stock_Total',
        'Demanda_Mensual', 'Cobertura_Meses', 'Stock_Seguridad',
        'Stock_Objetivo', 'Cantidad_a_Pedir',
    ]

    def _sel(df, cols):
        return _limpiar_df(df[[c for c in cols if c in df.columns]])

    try:
        _escribir(ruta, v1, v2, comparativo, _sel, cols_prod, cols_mol)
    except PermissionError:
        # El archivo suele quedar bloqueado si esta abierto en Excel
        alterna = f'Comparacion_V1_vs_V2_{date.today():%Y-%m-%d}_{datetime.now():%H%M%S}.xlsx'
        print(f"\n[!] '{ruta}' esta abierto o bloqueado. Escribiendo en '{alterna}'.")
        _escribir(alterna, v1, v2, comparativo, _sel, cols_prod, cols_mol)
        ruta = alterna

    print(f"\n[OK] Exportado: {ruta}")
    return ruta


def _escribir(ruta, v1, v2, comparativo, _sel, cols_prod, cols_mol):
    with pd.ExcelWriter(ruta, engine='openpyxl') as writer:
        _limpiar_df(comparativo).to_excel(writer, sheet_name='Comparativo', index=False)
        _sel(v1.maestro_consumo, cols_prod).to_excel(writer, sheet_name='V1_Productos', index=False)
        _sel(v2.maestro_consumo, cols_prod).to_excel(writer, sheet_name='V2_Productos', index=False)
        _sel(v1.pedido_molecula, cols_mol).to_excel(writer, sheet_name='V1_Molecula', index=False)
        _sel(v2.pedido_molecula, cols_mol).to_excel(writer, sheet_name='V2_Molecula', index=False)

        for sheet in writer.sheets.values():
            sheet.freeze_panes = 'A2'
            if sheet.max_row > 1:
                sheet.auto_filter.ref = f'A1:{sheet.cell(1, sheet.max_column).coordinate}'
            for col in sheet.columns:
                ancho = max((len(str(c.value)) if c.value is not None else 0
                             for c in col), default=8)
                sheet.column_dimensions[col[0].column_letter].width = min(ancho + 2, 45)


def main():
    print("Cargando datos...")
    datos = cargar_datos()

    print("Corriendo V1 (rotacion por Formulas_Ponderadas)...")
    v1 = correr(datos, criterio='formulas')

    print("Corriendo V2 (rotacion por Consumo_Acum)...")
    v2 = correr(datos, criterio='volumen')

    comparar_distribucion(v1, v2)
    comparar_pedido(v1, v2)
    comparativo = comparar_cambios(v1, v2)
    exportar(v1, v2, comparativo)
    print(LIN + "\n")


if __name__ == '__main__':
    main()
