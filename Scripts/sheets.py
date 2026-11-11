import time
import pandas as pd
import gspread

from Scripts import config

_libro = None
_encabezados = None
_cache = {
    "datos": None,
    "hora": 0,
}

def get_libro():
    global _libro
    if _libro is None:
        if not config.CALIDAD_ID_SHEETS:
            raise RuntimeError("Falta la variable de CALIDAD_ID_SHEETS")
        if not config.CALIDAD_CRENDENCIALES:
            raise RuntimeError("Falta la variable de CALIDAD_CREDENCIALES")

        cliente = gspread.service_account(filename=config.CALIDAD_CRENDENCIALES)
        _libro = cliente.open_by_key(config.CALIDAD_ID_SHEETS)
    return _libro

def _hoja(nombre):
    return get_libro().worksheet(nombre)

def _get_encabezados():
    global _encabezados
    if _encabezados is None:
        _encabezados = _hoja(config.CALIDAD_HOJA_LECTURAS).row_values(1)
    return _encabezados

def leer_lecturas():
    if _cache["datos"] is not None and (time.time() - _cache["hora"]) < config.CALIDAD_CACHE_SEGUNDOS:
        return _cache["datos"].copy()

    registros = _hoja(config.CALIDAD_HOJA_LECTURAS).get_all_records()
    df = pd.DataFrame(registros, columns=_get_encabezados())
    df["Código de Bodega"] = df['Código de Bodega'].astype(str)
    df['Fecha'] = pd.to_datetime(df["Fecha"], format="%d/%m/%Y", errors="coerce")

    _cache['datos'] = df
    _cache['hora'] = time.time()
    return df.copy()

def leer_equipos():
    hoja = _hoja(config.CALIDAD_HOJA_EQUIPOS)
    registros = hoja.get_all_records(head=2)
    return pd.DataFrame(registros, columns=hoja.row_values(2))

def agregar_lectura(lectura):
    fila = [lectura.get(encabezado, "") for encabezado in _get_encabezados()]
    _hoja(config.CALIDAD_HOJA_LECTURAS).append_row(fila, value_input_option="USER_ENTERED", table_range="A1")
    _cache['datos'] = None

def guardar_equipos(equipos):
    """Equipos: dic {encabezado de la fila 2: valor}. Actualiza la fila del punto o la agrega"""
    hoja = _hoja(config.CALIDAD_HOJA_EQUIPOS)
    encabezados = hoja.row_values(2)

    fila = [equipos.get(e, "") for e in encabezados]

    puntos = hoja.col_values(1)

    punto = equipos["PUNTO DE SERVICIO"]

    if punto in puntos[2:]:
        n = puntos.index(punto) + 1

        hoja.update(range_name=f"A{n}", values=[fila], value_input_option="USER_ENTERED")
    else:
        hoja.append_row(fila, value_input_option="USER_ENTERED", table_range="A3")