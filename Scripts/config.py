import os

RUTA_MAESTRO = 'Datos/Maestras/ListaArticulos_31-08-2026.xls'
RUTA_DISPENSACION = 'Datos/Dispensacion/ROTACION CON AGOSTO - PRUEBA.xlsx'
RUTA_REMISIONES = 'Datos/Remisiones/Rotacion_Remisiones_A_Julio.xlsx'
RUTA_STOCK_BODEGA = 'Datos/Valorizados/Valorizado_CEDI_21-08-2026.xls'
RUTA_STOCK_PUNTOS = 'Datos/Valorizado_Puntos/Valorizado_Puntos_21-08-2026.xls'
RUTA_MOLECULAS = 'Datos/Molecula_Compra/Molecula_Compra_14-08-2026.xlsx'
DB_URL = os.environ.get("PROYECCION_DB_URL")

APARTAR_ULTIMO_MES_VISUAL = True

COBERTURA_DIAS_DISP = {'A': 30, 'M': 30, 'B': 25,}
LEAD_TIME_DIAS_DISP = 6
DIAS_SEGURIDAD_DISP = 6

COBERTURA_DIAS_REMI = {'A': 40, 'M': 30, 'B': 30,}
LEAD_TIME_DIAS_REMI = 20
DIAS_SEGURIDAD_REMI = 20

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
CODIGOS_EXCLUIDOS_PREFIJOS = ('CONT','PR',)
CODIGOS_EXCLUIDOS_EXACTOS = ('M99999',)
CODIGOS_MATRIZ_RIESGO = ('M01856', 'M00658', 'M00743', 'M00555', 'M02769', 'M02872', 'M00358', 'M01880', 'M00955',
                         'M01979', 'M01023', 'M02431' 'N00081', 'M00439', 'M03133', 'M02712', 'M00730', 'M00731',
                         'N00002', 'M01070', 'M04052', 'M00149', 'M02418', 'DM00208', 'M01606', 'M00826', 'M03715',
                         'M01245', 'M00147', 'M01434', 'DM01472', 'DM00519', 'M00148', 'M03680', 'N00024','N00025')
TEXTO_MATRIZ = ('CODIGO MATRIZ DE RIESGO')

BODEGAS_ABASTECIMIENTO = {
    '280': 'DISP. MENNAR 1',
    '284': 'DISP. MENNAR SANTANDER 1',
    '288': 'DISP. MENNAR PUERTO TEJADA 1',
    '292': 'DISP. MENNAR BOLIVAR 1',
    '296': 'DISP. MENNAR GUAPI 1',
    '300': 'DISP. MENNAR TIMBIQUI 1',
    '304': 'DISP. MENNAR MIRANDA 1',
    '308': 'DISP. MENNAR EL TAMBO 1',
    '312': 'DISP. MENNAR TIMBIO 1',
    '316': 'DISP. MENNAR PIENDAMO 1',
    '320': 'DISP. MENNAR ARGELIA 1',
    '324': 'DISP. MENNAR MORALES 1',
    '328': 'DISP. MENNAR PATIA 1',
    '332': 'DISP. MENNAR CALOTO 1',
    '336': 'DISP. MENNAR VILLA RICA 1',
    '340': 'DISP. MENNAR CORINTO 1',
    '344': 'DISP. MENNAR ROSAS 1',
    '348': 'DISP. MENNAR LA VEGA 1',
    '352': 'DISP. MENNAR SOTARA 1',
    '357': 'DISP. MENNAR LA SIERRA 1',
    '365': 'DISP. MENNAR GUACHENE 1',
    '369': 'DISP. MENNAR SILVIA 1',
    '373': 'DISP. MENNAR SUAREZ 1',
    '377': 'DISP. MENNAR PADILLA 1',
    '381': 'DISP. MENNAR CAJIBIO 1',
    '385': 'DISP. MENNAR MERCADERES 1',
    '389': 'DISP. MENNAR TOTORO 1',
    '395': 'DISP. MENNAR ALMAGUER 1',
    '404': 'DISP. MENNAR BALBOA 1',
    '409': 'DISP. MENNAR BUENOS AIRES 1',
    '413': 'DISP. MENNAR FLORENCIA 1',
    '417': 'DISP. MENNAR INZA 1',
    '421': 'DISP. MENNAR JAMBALO 1',
    '429': 'DISP. MENNAR PAEZ 1',
    '437': 'DISP. MENNAR SAN SEBASTIAN 1',
    '441': 'DISP. MENNAR SUCRE 1',
    '445': 'DISP. MENNAR SANTA ROSA 1',
    '465': 'DISP. MENNAR TORIBIO 1',
    '469': 'DISP. MENNAR CALDONO 2',
    '475': 'DISP. MENNAR 4',
    '486': 'DISP. MENNAR PIAMONTE 1',
    '509': 'DISP. MENNAR 5',
    '524': 'DISP. MENNAR 2',
}

ZONAS_ABASTECIMIENTO = {
    'ZONA 1': [
        '524','308','413','365','357',
        '437','284','352','389','336',
        '433',
    ],
    'ZONA 2': [
        '475','381','332','296','421',
        '385','324','316','288','344',
        '445',
    ],
    'ZONA 3': [
        '509','395','320','292','409',
        '469','340','304','369','373',
        '300',
    ],
    'ZONA 4': [
        '280','404','417','348','377',
        '429','328','486','441','312',
        '465',
    ]
}