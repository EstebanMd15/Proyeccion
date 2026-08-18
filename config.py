# ==================================================================
#  RUTAS DE LOS ARCHIVOS DE ENTRADA
#  Cambia la ruta cuando llegue un archivo nuevo (respeta las comillas).
# ==================================================================
RUTA_MAESTRO = 'Datos/Maestras/BD 14-08-2026.xls'
RUTA_DISPENSACION = 'Datos/Dispensacion/Rotacion_Dispensacion_A_Julio.xlsx'
RUTA_REMISIONES = 'Datos/Remisiones/Rotacion_Remisiones_A_Julio.xlsx'
RUTA_STOCK_BODEGA = 'Datos/Valorizados/Valorizado_CEDI_14-08-2026.xls'
RUTA_STOCK_PUNTOS = 'Datos/Valorizado_Puntos/Valorizado_Puntos_14-08-2026.xls'
RUTA_MOLECULAS = 'Datos/Molecula_Compra/Molecula_Compra_14-08-2026.xlsx'

COBERTURA_DIAS_DISP = {'A': 30, 'M': 30, 'B': 30,}
LEAD_TIME_DIAS_DISP = 30
DIAS_SEGURIDAD_DISP = 5

COBERTURA_DIAS_REMI = {'A': 30, 'M': 30, 'B': 30,}
LEAD_TIME_DIAS_REMI = 30
DIAS_SEGURIDAD_REMI = 5

# --- Umbrales de la clasificacion de rotacion ABC (metodo de Pareto), en %.
#         A = productos que acumulan hasta UMBRAL_A % del consumo total
#         M = hasta UMBRAL_M %      B = todo el resto
UMBRAL_A = 80
UMBRAL_M = 95

# --- Criterio de rotacion:  'volumen' (recomendado)  o  'formulas' (obsoleto).
CRITERIO_ROTACION = 'volumen'

# --- Codigos que NO son productos y se excluyen de toda la proyeccion.
#         PREFIJOS = se excluye todo codigo que EMPIECE por alguno de estos.
#         EXACTOS  = se excluye el codigo completo, tal cual.
CODIGOS_EXCLUIDOS_PREFIJOS = ('CONT',)
CODIGOS_EXCLUIDOS_EXACTOS = ('M99999',)
