import pandas as pd
from sqlalchemy import create_engine, text
import config

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        if not config.DB_URL:
            raise RuntimeError("Falta la variable de entorno PROYECCION_DB_URL")
        _engine = create_engine(config.DB_URL, pool_pre_ping=True)
    return _engine

SQL_DISPENSACION = text("""
SELECT PERIODO, CODIGO_ARTICULO AS CODIGO , MAX(DESCRIPCION) AS DESCRIPCION, MAX(PRESENTACION) AS PRESENTACION,
    MAX(`GRUPO`) AS `GRUPO`, SIGLA_COMERCIAL_CLIENTE, TIPO_SERVICIO,
    SUM(CANTIDAD_PRESCRITA) AS CONSUMO_TOTAL 
FROM DISPENSACION_ACUM
    WHERE PERIODO BETWEEN :desde AND :hasta
GROUP BY PERIODO, CODIGO_ARTICULO, SIGLA_COMERCIAL_CLIENTE, TIPO_SERVICIO
ORDER BY PERIODO ASC, CONSUMO_TOTAL DESC
""")

SQL_REMISIONES = text("""
SELECT PERIODO, CODIGO, MAX(DESCRIPCION) AS DESCRIPCION, MAX(PRESENTACION) AS PRESENTACION,
       SUM(CANTIDAD_PEDIDA_POR_EL_CLIENTE) AS CONSUMO_TOTAL_GENERAL
FROM REMISIONES_ACUM
WHERE PERIODO BETWEEN :desde AND :hasta
GROUP BY PERIODO, CODIGO
ORDER BY PERIODO ASC, CONSUMO_TOTAL_GENERAL DESC
""")

def consultar_dispensacion(desde, hasta):
    return pd.read_sql(SQL_DISPENSACION, get_engine(), params={'desde': desde, 'hasta': hasta})

def consultar_remisiones(desde, hasta):
    desde = desde.replace('_','-')
    hasta = hasta.replace('_','-')
    return pd.read_sql(SQL_REMISIONES, get_engine(), params={'desde': desde, 'hasta': hasta})

def periodos_cargados():
    eng = get_engine()
    disp = pd.read_sql(text("SELECT DISTINCT PERIODO FROM DISPENSACION_ACUM ORDER BY PERIODO"),eng)["PERIODO"].astype(str).tolist()
    rem = pd.read_sql(text("SELECT DISTINCT PERIODO FROM REMISIONES_ACUM ORDER BY PERIODO"), eng)["PERIODO"].astype(str).tolist()
    return {"dispensacion": disp, "remisiones": rem}