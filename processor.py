import pandas as pd
import numpy as np

import config


class ProyeccionProcessor:

    # Codigos que no son productos reales y no deben entrar nunca a la proyeccion:
    # cuentas contables (copago, glosas, arrendamiento, servicios) y placeholders.
    # Los valores se diligencian en config.py (CODIGOS_EXCLUIDOS_*).
    PREFIJOS_EXCLUIDOS = getattr(config, 'CODIGOS_EXCLUIDOS_PREFIJOS', ('CONT',))
    CODIGOS_EXCLUIDOS = getattr(config, 'CODIGOS_EXCLUIDOS_EXACTOS', ('M99999',))

    # Contratos sobre los que se desglosa el pedido.
    # Mapea: columna de consumo historico -> columna de pedido resultante.
    # El orden define el orden de las columnas en la salida.
    SEGMENTOS_CONTRATO = {
        'Consumo_NEPS_Capita':  'Pedir_NEPS_Capita',
        'Consumo_NEPS_Evento':  'Pedir_NEPS_Evento',
        'Consumo_FOMAG_Evento': 'Pedir_FOMAG_Evento',
        'Consumo_Remisiones':   'Pedir_Remisiones',
    }

    # Columnas informativas del maestro. Ya llegan solas por el merge de
    # construir_base (que trae el maestro completo); se listan aqui unicamente
    # para mostrarlas y exportarlas. 'Grupo' es el laboratorio.
    COLS_MAESTRO_INFO = ('Grupo', 'Proveedor', 'Ultimo Costo', 'Costo Promedio')

    MESES_ES = {'01': 'Ene', '02': 'Feb', '03': 'Mar', '04': 'Abr',
                '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Ago',
                '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dic'}

    # Columnas de consumo que vienen del archivo de DISPENSACION.
    # Consumo_Remisiones viene de otro archivo y es otro negocio: por eso la
    # rotacion se calcula por separado para cada canal.
    COLS_CONSUMO_DISPENSACION = (
        'Consumo_NEPS_Capita',
        'Consumo_NEPS_Evento',
        'Consumo_FOMAG_Evento',
        'Consumo_Sin_Clasificar',
    )

    def __init__(self, maestro, consumo_dispensacion, consumo_remisiones, stock_bodega, stock_puntos, molecula_compra,
                 criterio_rotacion=None,):
        self.maestro = maestro
        self.consumo_dispensacion = consumo_dispensacion
        self.consumo_remisiones = consumo_remisiones
        self.stock_bodega = stock_bodega
        self.stock_puntos = stock_puntos
        self.molecula_compra = molecula_compra
        self.consumo_consolidado = None
        self.maestro_consumo = None

        # Parametros del motor: se diligencian en config.py. Un valor pasado al
        # constructor tiene prioridad (para pruebas puntuales).
        self.criterio_rotacion = criterio_rotacion or getattr(config, 'CRITERIO_ROTACION', 'volumen')
        self.cobertura_dias_DISP = getattr(config, 'COBERTURA_DIAS_DISP', {'A': 30, 'M': 30, 'B': 30})
        self.lead_time_dias_DISP = getattr(config, 'LEAD_TIME_DIAS_DISP', 30)
        self.dias_seguridad_DISP = getattr(config, 'DIAS_SEGURIDAD_DISP', 15)
        self.cobertura_dias_REMI = getattr(config, 'COBERTURA_DIAS_REMI', {'A': 30, 'M': 30, 'B': 30})
        self.lead_time_dias_REMI = getattr(config, 'LEAD_TIME_DIAS_REMI', 30)
        self.dias_seguridad_REMI = getattr(config, 'DIAS_SEGURIDAD_REMI', 15)
        self.umbral_A = getattr(config, 'UMBRAL_A', 80)
        self.umbral_M = getattr(config, 'UMBRAL_M', 95)

    def calcular_ponderados(self, consumo, col_periodo='PERIODO', col_codigo='Codigo', col_cantidad='Consumo_Dispensacion'):
        df = consumo.copy()

        periodos = sorted(df[col_periodo].unique())

        mes_reciente = periodos[-1]  #Junio
        mes_intermedio = periodos[-2] #Mayo
        mes_antiguo = periodos[-3] #Abril

        recent_group = df[df[col_periodo] == mes_reciente].groupby(col_codigo)[col_cantidad].sum() * 0.50
        intermediate_group = df[df[col_periodo] == mes_intermedio].groupby(col_codigo)[col_cantidad].sum() * 0.30
        old_group = df[df[col_periodo] == mes_antiguo].groupby(col_codigo)[col_cantidad].sum() * 0.20

        prom_ult_3m = recent_group.add(intermediate_group, fill_value=0).add(old_group, fill_value=0)

        cpm = prom_ult_3m.reset_index()
        cpm.rename(columns={col_cantidad: f'{col_cantidad}_ponderado'}, inplace=True)
        return cpm

    def clasificar_segmentos(self):
        # Normalizar textos a mayúsculas y quitar espacios
        sigla = self.consumo_dispensacion['SIGLA_COMERCIAL_CLIENTE'].astype(str).str.strip().str.upper()
        servicio = self.consumo_dispensacion['TIPO_SERVICIO'].astype(str).str.strip().str.upper()

        es_neps = sigla.str.contains('NUEVA EPS|NEPS', na=False)
        es_fomag = sigla.str.contains('FIDEICOMISOS PATRIMONIOS AUTONOMOS FIDUCIARIA LA PREVISORA S.A.|FOMAG',
                                      na=False)

        condiciones = [
            es_neps & servicio.str.contains('CAPITADO|CAPITA', na=False),
            es_neps & servicio.str.contains('POS|EVENTO|MIPRES|TUTELA', na=False),
            es_fomag,
        ]
        resultados = [
            'NEPS - CAPITA',
            'NEPS - EVENTO',
            'FOMAG - EVENTO',
        ]

        # El default NO es una categoria de negocio: significa "no se pudo clasificar".
        # Antes se llamaba 'COMERCIAL_DISP' y eso escondia las tutelas de Nueva EPS
        # (38.639 unidades) haciendolas pasar por consumo comercial. La auditoria
        # ahora avisa si vuelve a caer algo aqui (cliente o servicio nuevo).
        self.consumo_dispensacion['Segmento'] = np.select(condiciones, resultados, default='SIN_CLASIFICAR')

    def limpiar_datos(self):
        # Limpieza de strings
        self.maestro['Codigo'] = self.maestro['Codigo'].astype(str).str.strip()
        self.consumo_dispensacion['CODIGO'] = self.consumo_dispensacion['CODIGO'].astype(str).str.strip()
        self.consumo_remisiones['CODIGO'] = self.consumo_remisiones['CODIGO'].astype(str).str.strip()
        self.stock_bodega['Codigo Articulo'] = self.stock_bodega['Codigo Articulo'].astype(str).str.strip()
        self.stock_puntos['Codigo Articulo'] = self.stock_puntos['Codigo Articulo'].astype(str).str.strip()
        self.molecula_compra['Codigo Articulo'] = self.molecula_compra['Codigo Articulo'].astype(str).str.strip()

        # Renombrado de columnas
        self.molecula_compra.rename(columns={'Codigo Articulo': 'Codigo', 'Codigo Molecula': 'Codigo_Molecula'},
                                    inplace=True)
        self.stock_puntos.rename(columns={'Codigo Articulo': 'Codigo', 'Unidades': 'Stock_Puntos_Dispensacion'},
                                 inplace=True)
        self.stock_bodega.rename(columns={'Codigo Articulo': 'Codigo', 'Unidades': 'Stock_Bodega_Principal'},
                                 inplace=True)
        self.consumo_dispensacion.rename(columns={'CODIGO': 'Codigo', 'CONSUMO_TOTAL': 'Consumo_Dispensacion'},
                                         inplace=True)
        self.consumo_remisiones.rename(columns={'CODIGO': 'Codigo', 'CONSUMO_TOTAL_GENERAL': 'Consumo_Remisiones'},
                                       inplace=True)

        # Desduplicar catálogo maestro
        self.maestro = self.maestro.drop_duplicates(subset=['Codigo'], keep='first')

        # Excluir codigos que no son productos reales
        self.excluir_codigos()

        # Dejar ambos canales sobre el mismo rango de meses
        self.alinear_periodos()

    def alinear_periodos(self):
        """
        Recorta dispensacion y remisiones al rango de meses que AMBOS cubren.

        Los archivos no siempre traen los mismos meses: remisiones venia con un
        julio que dispensacion no tenia. Sin recortar, Consumo_Acum mezcla 7
        meses de un canal con 6 del otro y despues se divide entre
        meses_historico, inflando la demanda de ese canal.

        Se recorta por los extremos (no por interseccion) para no borrar un mes
        interior en el que un canal legitimamente no tuvo movimiento.

        De paso normaliza el separador: remisiones escribe '2026-01' y
        dispensacion '2026_01'; sin unificar no cruzan.
        """
        self.periodos_recortados = {}
        self.periodos_comunes = []

        fuentes = {'consumo_dispensacion': self.consumo_dispensacion,
                   'consumo_remisiones': self.consumo_remisiones}
        fuentes = {k: v for k, v in fuentes.items() if 'PERIODO' in v.columns}
        if not fuentes:
            return

        # Normalizar primero, si no los rangos no son comparables
        for nombre, df in fuentes.items():
            df['PERIODO'] = df['PERIODO'].astype(str).str.strip().str.replace('-', '_', regex=False)

        inicio = max(df['PERIODO'].min() for df in fuentes.values())
        fin = min(df['PERIODO'].max() for df in fuentes.values())

        for nombre, df in fuentes.items():
            dentro = df['PERIODO'].between(inicio, fin)
            n_fuera = int((~dentro).sum())
            if n_fuera:
                meses_fuera = sorted(df.loc[~dentro, 'PERIODO'].unique())
                self.periodos_recortados[nombre] = (n_fuera, meses_fuera)
                setattr(self, nombre, df[dentro].copy())

        self.periodos_comunes = sorted(
            getattr(self, 'consumo_dispensacion')['PERIODO'].unique()
            if 'PERIODO' in self.consumo_dispensacion.columns else []
        )

    def excluir_codigos(self):
        """
        Saca los codigos no-producto (PREFIJOS_EXCLUIDOS / CODIGOS_EXCLUIDOS) de
        TODAS las fuentes a la vez. Se filtra en todas y no solo en el maestro
        para que los cuadres de auditoria sigan comparando lo mismo contra lo mismo.
        """
        self.codigos_excluidos_detalle = {}

        fuentes = ['maestro', 'consumo_dispensacion', 'consumo_remisiones',
                   'stock_bodega', 'stock_puntos', 'molecula_compra']

        for nombre in fuentes:
            df = getattr(self, nombre)
            codigo = df['Codigo'].astype(str).str.strip().str.upper()
            excluir = codigo.str.startswith(self.PREFIJOS_EXCLUIDOS) | codigo.isin(self.CODIGOS_EXCLUIDOS)

            n = int(excluir.sum())
            if n:
                self.codigos_excluidos_detalle[nombre] = n
                setattr(self, nombre, df[~excluir].copy())

    def consolidar_consumos(self):
        disp_pivot = self.consumo_dispensacion.pivot_table(
            index='Codigo',
            columns='Segmento',
            values='Consumo_Dispensacion',
            aggfunc='sum',
            fill_value=0
        ).reset_index()

        disp_pivot.rename(columns={
            'NEPS - CAPITA': 'Consumo_NEPS_Capita',
            'NEPS - EVENTO': 'Consumo_NEPS_Evento',
            'FOMAG - EVENTO': 'Consumo_FOMAG_Evento',
            'SIN_CLASIFICAR': 'Consumo_Sin_Clasificar'
        }, inplace=True)

        cols_esperadas = ['Consumo_NEPS_Capita', 'Consumo_NEPS_Evento', 'Consumo_FOMAG_Evento',
                          'Consumo_Sin_Clasificar']
        for col in cols_esperadas:
            if col not in disp_pivot.columns:
                disp_pivot[col] = 0

        rem_agrupado = self.consumo_remisiones.groupby('Codigo')['Consumo_Remisiones'].sum().reset_index()
        stock_bodega_agrupado = self.stock_bodega.groupby('Codigo')['Stock_Bodega_Principal'].sum().reset_index()
        stock_puntos_agrupado = self.stock_puntos.groupby('Codigo')['Stock_Puntos_Dispensacion'].sum().reset_index()

        self.consumo_consolidado = pd.merge(disp_pivot, rem_agrupado, on='Codigo', how='outer')
        self.consumo_consolidado = pd.merge(self.consumo_consolidado, stock_bodega_agrupado, on='Codigo', how='outer')
        self.consumo_consolidado = pd.merge(self.consumo_consolidado, stock_puntos_agrupado, on='Codigo', how='outer')

        self.consumo_consolidado.fillna(0, inplace=True)

        # Remisiones es su propio canal y va aparte: no es dispensacion.
        # Consumo_Sin_Clasificar deberia ser siempre 0; se suma igual para no
        # perder consumo real si aparece un cliente o servicio no contemplado.
        self.consumo_consolidado['Consumo_Acum'] = (
            self.consumo_consolidado['Consumo_NEPS_Capita'] +
            self.consumo_consolidado['Consumo_NEPS_Evento'] +
            self.consumo_consolidado['Consumo_FOMAG_Evento'] +
            self.consumo_consolidado['Consumo_Remisiones'] +
            self.consumo_consolidado['Consumo_Sin_Clasificar']
        )

        self.consumo_consolidado['Stock_Total'] = (
            self.consumo_consolidado['Stock_Bodega_Principal'] +
            self.consumo_consolidado['Stock_Puntos_Dispensacion']
        )

    def construir_base(self):
        cols_a_traer = [
            'Codigo',
            'Consumo_NEPS_Capita',
            'Consumo_NEPS_Evento',
            'Consumo_FOMAG_Evento',
            'Consumo_Remisiones',
            'Consumo_Sin_Clasificar',
            'Consumo_Acum',
            'Stock_Bodega_Principal',
            'Stock_Puntos_Dispensacion',
            'Stock_Total'
        ]

        self.maestro_consumo = pd.merge(
            self.maestro,
            self.consumo_consolidado[cols_a_traer],
            on='Codigo',
            how='left'
        )

        cols_numericas = [c for c in cols_a_traer if c != 'Codigo']
        self.maestro_consumo[cols_numericas] = self.maestro_consumo[cols_numericas].fillna(0)

        # Demanda mensual 70/30 por canal (se usa para calcular el pedido)
        disp = self.demanda_disp_mensual.rename(columns={'Consumo_Dispensacion_ponderado': 'Demanda_Disp_Mensual'})
        rem = self.demanda_rem_mensual.rename(columns={'Consumo_Remisiones_ponderado': 'Demanda_Rem_Mensual'})
        self.maestro_consumo = pd.merge(self.maestro_consumo, disp, on='Codigo', how='left')
        self.maestro_consumo = pd.merge(self.maestro_consumo, rem, on='Codigo', how='left')
        self.maestro_consumo[['Demanda_Disp_Mensual', 'Demanda_Rem_Mensual']] = (
            self.maestro_consumo[['Demanda_Disp_Mensual', 'Demanda_Rem_Mensual']].fillna(0)
        )

    def calcular_consumo_mensual(self):
        """
        Consumo de cada producto mes a mes, en columnas separadas.

        Suma dispensacion + remisiones, para que el total mensual cuadre contra
        'Consumo_Acum'.

        OJO con dos trampas de los archivos de origen:
        1. Escriben el periodo distinto: dispensacion '2026_01', remisiones
           '2026-01'. Sin normalizar, el pivot crea columnas duplicadas.
        2. No cubren los mismos meses. Remisiones puede traer meses que
           dispensacion no tiene; esos meses quedan con solo un canal.

        Genera tres bloques de columnas (y guarda sus nombres):
          - self.cols_consumo_mensual_disp : dispensacion mes a mes (Consumo_Disp_*)
          - self.cols_consumo_mensual_rem  : remisiones mes a mes   (Consumo_Rem_*)
          - self.cols_consumo_mensual      : total mes a mes        (Consumo_*)
        """
        self.cols_consumo_mensual = []
        self.cols_consumo_mensual_disp = []
        self.cols_consumo_mensual_rem = []
        self.periodos_mensuales = []

        piezas_total = []
        for origen, col_valor, etiqueta, destino in [
            (self.consumo_dispensacion, 'Consumo_Dispensacion', 'Disp', 'cols_consumo_mensual_disp'),
            (self.consumo_remisiones, 'Consumo_Remisiones', 'Rem', 'cols_consumo_mensual_rem'),
        ]:
            if 'PERIODO' not in origen.columns or col_valor not in origen.columns:
                continue
            tmp = origen[['Codigo', 'PERIODO', col_valor]].copy()
            tmp['PERIODO'] = (tmp['PERIODO'].astype(str).str.strip()
                              .str.replace('-', '_', regex=False))
            tmp = tmp.rename(columns={col_valor: 'Consumo'})
            piezas_total.append(tmp)

            cols = self._pivotar_mensual(tmp, prefijo=f'Consumo_{etiqueta}_')
            setattr(self, destino, cols)

        if not piezas_total:
            return

        # Total mes a mes (dispensacion + remisiones)
        largo = pd.concat(piezas_total, ignore_index=True)
        self.cols_consumo_mensual = self._pivotar_mensual(largo, prefijo='Consumo_',
                                                          guardar_periodos=True)

    def _pivotar_mensual(self, largo, prefijo, guardar_periodos=False):
        """
        Pivotea un DataFrame largo (Codigo, PERIODO, Consumo) a columnas por mes,
        las nombra con `prefijo` + mes en español, y las une a maestro_consumo.
        Devuelve la lista de columnas creadas.
        """
        pivot = largo.pivot_table(index='Codigo', columns='PERIODO', values='Consumo',
                                  aggfunc='sum', fill_value=0)
        pivot = pivot.reindex(sorted(pivot.columns), axis=1)   # orden cronologico
        if guardar_periodos:
            self.periodos_mensuales = list(pivot.columns)

        pivot = pivot.rename(columns={
            p: f'{prefijo}{self.MESES_ES.get(str(p)[-2:], str(p)[-2:])}_{str(p)[:4]}'
            for p in pivot.columns
        }).reset_index()

        cols = [c for c in pivot.columns if c != 'Codigo']
        self.maestro_consumo = pd.merge(self.maestro_consumo, pivot, on='Codigo', how='left')
        self.maestro_consumo[cols] = self.maestro_consumo[cols].fillna(0)
        return cols

    def calcular_consumo_molecula(self):
        self.molecula_compra['Codigo'] = self.molecula_compra['Codigo'].astype(str).str.strip()

        self.maestro_consumo = pd.merge(
            self.maestro_consumo,
            self.molecula_compra[['Codigo', 'Codigo_Molecula', 'Molecula']],
            on='Codigo',
            how='left'
        )

        self.maestro_consumo['Consumo_Molecula'] = (
            self.maestro_consumo.groupby('Codigo_Molecula')['Consumo_Acum'].transform('sum')
        )

        self.maestro_consumo['Consumo_Molecula'] = self.maestro_consumo['Consumo_Molecula'].fillna(
            self.maestro_consumo['Consumo_Acum'])

        self.maestro_consumo['Codigo_Molecula'] = (
            self.maestro_consumo['Codigo_Molecula']
            .fillna(0)
            .astype(int)
            .astype(str)
        )

    @staticmethod
    def _pareto_abc(serie, umbral_A=80, umbral_M=95):
        """
        Clasificacion ABC de Pareto sobre una serie numerica.
        Devuelve una Serie de letras A/M/B alineada al index original:
            A -> acumulan hasta umbral_A % del total (default 80%)
            M -> hasta umbral_M % (default 95%)
            B -> el resto, y todo valor <= 0
        """
        orden = serie.sort_values(ascending=False)
        positivos = orden > 0
        total = orden[positivos].sum()

        pct_acum = pd.Series(0.0, index=orden.index)
        if total > 0:
            pct_acum[positivos] = orden[positivos].cumsum() / total * 100

        letra = pd.Series('B', index=orden.index)
        letra[positivos & (pct_acum <= umbral_A)] = 'A'
        letra[positivos & (pct_acum > umbral_A) & (pct_acum <= umbral_M)] = 'M'

        return letra.reindex(serie.index)

    # ==================================================================
    # Clasificacion de rotacion A / M / B por Pareto ABC.
    #
    # criterio='volumen' (VIGENTE): Pareto sobre 'Consumo_Acum', las unidades
    #   realmente consumidas en el historico.
    #
    # criterio='formulas' (LEGACY, no usar): Pareto sobre el conteo ponderado
    #   70/30 de renglones de dispensacion. El archivo de dispensacion viene
    #   pre-agregado por (PERIODO, CODIGO, CLIENTE, TIPO_SERVICIO), asi que ese
    #   conteo NO mide despachos: mide en cuantos segmentos aparece el producto
    #   y satura en ~6. Resultado: metia el 94.8% del consumo en la letra 'A',
    #   es decir no discriminaba nada. Se conserva unicamente para poder
    #   reproducir la comparacion historica (ver comparar_v1_v2.py).
    # ==================================================================
    def calcular_rotacion(self, umbral_A=None, umbral_M=None):
        umbral_A = self.umbral_A if umbral_A is None else umbral_A
        umbral_M = self.umbral_M if umbral_M is None else umbral_M
        if self.criterio_rotacion == 'formulas':
            df_formulas = self.consumo_dispensacion.copy()
            df_formulas['Formula_Count'] = 1
            rot = self.calcular_ponderados(df_formulas, col_cantidad='Formula_Count')
            rot.rename(columns={'Formula_Count_ponderado': 'Formulas_Ponderadas'}, inplace=True)

            self.maestro_consumo = pd.merge(
                self.maestro_consumo, rot, on='Codigo', how='left'
            )
            self.maestro_consumo['Formulas_Ponderadas'] = (
                self.maestro_consumo['Formulas_Ponderadas'].fillna(0)
            )
            base = self.maestro_consumo['Formulas_Ponderadas']
        else:
            base = self.maestro_consumo['Consumo_Acum']

        self.maestro_consumo['Rotacion'] = self._pareto_abc(base, umbral_A, umbral_M)

    def calcular_rotacion_por_canal(self, umbral_A=None, umbral_M=None):
        """
        Rotacion calculada de forma INDEPENDIENTE para cada canal.

        Dispensacion y remisiones son negocios distintos: un producto puede ser
        'A' en dispensacion y 'B' en remisiones. Un solo Pareto sobre el consumo
        total esconde esa diferencia, porque dispensacion pesa 4 veces mas que
        remisiones y termina mandando en la clasificacion.

        Cada canal se ordena contra SI MISMO: el 'A' de remisiones es el 80% del
        volumen de remisiones, no del total.

        Los productos sin movimiento en un canal quedan marcados '-' y no 'B',
        para no confundir "no se mueve por aqui" con "se mueve poco".

        No altera 'Rotacion' (la global), que es la que sigue mandando el pedido.
        """
        umbral_A = self.umbral_A if umbral_A is None else umbral_A
        umbral_M = self.umbral_M if umbral_M is None else umbral_M
        df = self.maestro_consumo

        cols_disp = [c for c in self.COLS_CONSUMO_DISPENSACION if c in df.columns]
        df['Consumo_Dispensacion_Total'] = df[cols_disp].sum(axis=1)

        for col_consumo, col_rotacion in [('Consumo_Dispensacion_Total', 'Rotacion_Dispensacion'),
                                          ('Consumo_Remisiones', 'Rotacion_Remisiones')]:
            if col_consumo not in df.columns:
                continue
            letra = self._pareto_abc(df[col_consumo], umbral_A, umbral_M)
            df[col_rotacion] = letra.where(df[col_consumo] > 0, '-')

    # ==================================================================
    # DESGLOSE DEL PEDIDO POR CONTRATO
    #
    # El inventario es UNO SOLO: no hay stock separado por contrato. Por eso
    # el pedido no se puede calcular de forma independiente por contrato, se
    # calcula completo y luego se REPARTE segun el peso historico de cada
    # contrato en el consumo del producto.
    #
    # (Da igual repartir el pedido que calcular cada contrato por separado
    # prorrateando tambien el stock: todas las formulas son lineales en el
    # consumo, asi que ambos caminos dan el mismo numero.)
    # ==================================================================
    @staticmethod
    def _prorratear_entero(total, pesos):
        """
        Reparte el entero `total` de cada fila entre varias columnas, en
        proporcion a `pesos`, garantizando que las partes sumen EXACTAMENTE
        el total (metodo de mayores residuos).

        total : Series de enteros     (n,)
        pesos : DataFrame de consumos (n, k)
        return: DataFrame de enteros  (n, k)
        """
        suma = pesos.sum(axis=1)
        sin_consumo = suma <= 0

        # Sin consumo historico no hay como repartir; esas filas quedan en cero
        # (su Cantidad_a_Pedir tambien es cero, porque Stock_Objetivo seria 0).
        share = pesos.div(suma.where(~sin_consumo), axis=0).fillna(0.0)

        exacto = share.mul(total, axis=0)
        piso = np.floor(exacto)

        # Unidades sueltas al truncar: siempre entre 0 y k-1
        sobrante = (total - piso.sum(axis=1)).round().astype('int64').to_numpy()
        sobrante = np.where(sin_consumo.to_numpy(), 0, sobrante)

        # Se entregan de a una, empezando por las fracciones mas grandes
        orden = np.argsort(-(exacto - piso).to_numpy(), axis=1, kind='stable')
        salida = piso.to_numpy()
        filas = np.arange(len(salida))
        for j in range(pesos.shape[1]):
            recibe = sobrante > j
            salida[filas[recibe], orden[recibe, j]] += 1

        return pd.DataFrame(salida.astype('int64'), index=pesos.index, columns=pesos.columns)

    @staticmethod
    def _valorizar(cantidad, ultimo_costo, costo_promedio):
        """
        Valor del pedido = cantidad * costo.
        El costo es 'Ultimo Costo'; si viene en 0 (o vacio) usa 'Costo Promedio'.
        """
        ultimo = pd.to_numeric(ultimo_costo, errors='coerce').fillna(0) if ultimo_costo is not None else 0
        prom = pd.to_numeric(costo_promedio, errors='coerce').fillna(0) if costo_promedio is not None else 0
        costo = ultimo.where(ultimo > 0, prom)
        return (cantidad * costo).round(2)

    def pedido_por_canal(self, df):
        """
        Calcula el pedido separando los DOS canales, porque tienen stock distinto:

          - Dispensacion (Capita + Evento + FOMAG): se surte de bodega principal
            + puntos (Stock_Total), porque el stock de los puntos si atiende la
            dispensacion en los puntos.
          - Remisiones: se surte SOLO de bodega principal. El stock de los puntos
            no alcanza al canal de remisiones.

        Bodega principal surte a ambos canales (opcion 'cada canal por separado':
        se resta en los dos, sin repartir).

        La cobertura, el lead time y el stock de seguridad son INDEPENDIENTES por
        canal (parametros *_DISP y *_REMI en config.py). Objetivo en dias, por canal:
            Objetivo = (demanda_canal / 30) * (cobertura_canal + lead_canal + seguridad_canal)

        Requiere en df: Rotacion, Demanda_Disp_Mensual, Demanda_Rem_Mensual,
        Stock_Total, Stock_Bodega_Principal y las columnas de consumo por contrato.

        Deja: Necesidad_Disp / Necesidad_Rem / Necesidad_Mensual,
        Pedir_Dispensacion_Total, los Pedir_ de cada contrato, Pedir_Remisiones y
        Cantidad_a_Pedir_Rest_Inv.
        """

        # --- Canal DISPENSACION: contra todo el stock (bodega + puntos) ---
        cobertura_disp = df['Rotacion'].map(self.cobertura_dias_DISP).fillna(max(self.cobertura_dias_DISP.values()))
        factor_disp = cobertura_disp + self.lead_time_dias_DISP + self.dias_seguridad_DISP
        objetivo_disp = (df['Demanda_Disp_Mensual'] / 30.0) * factor_disp
        pedir_disp = np.ceil((objetivo_disp - df['Stock_Total']).clip(lower=0)).astype('int64')
        df['Necesidad_Disp'] = objetivo_disp
        df['Pedir_Dispensacion_Total'] = pedir_disp

        # Repartir el pedido de dispensacion entre sus contratos, segun el consumo
        cols_disp = [c for c in self.SEGMENTOS_CONTRATO
                     if c in self.COLS_CONSUMO_DISPENSACION and c in df.columns]
        if cols_disp:
            partes = self._prorratear_entero(pedir_disp, df[cols_disp].clip(lower=0))
            for col in cols_disp:
                df[self.SEGMENTOS_CONTRATO[col]] = partes[col]

        # --- Canal REMISIONES: contra SOLO bodega principal ---
        cobertura_remi = df['Rotacion'].map(self.cobertura_dias_REMI).fillna(max(self.cobertura_dias_REMI.values()))
        factor_remi = cobertura_remi + self.lead_time_dias_REMI + self.dias_seguridad_REMI
        objetivo_remi = (df['Demanda_Rem_Mensual'] / 30.0) * factor_remi
        pedir_remi = np.ceil((objetivo_remi - df['Stock_Bodega_Principal']).clip(lower=0)).astype('int64')
        df['Necesidad_Rem'] = objetivo_remi
        df['Pedir_Remisiones'] = pedir_remi

        df['Necesidad_Mensual'] = df['Necesidad_Disp'] + df['Necesidad_Rem']
        df['Cantidad_a_Pedir_Rest_Inv'] = df['Pedir_Dispensacion_Total'] + df['Pedir_Remisiones']
        return df

    def calcular_pedido(self, umbral_A=None, umbral_M=None):
        # Los umbrales se diligencian en config.py. La cobertura, el lead time y
        # el stock de seguridad se resuelven POR CANAL dentro de pedido_por_canal.
        umbral_A = self.umbral_A if umbral_A is None else umbral_A
        umbral_M = self.umbral_M if umbral_M is None else umbral_M

        # Demanda total (informativa): suma de la de los dos canales.
        df = self.maestro_consumo
        df['Demanda_Mensual'] = df['Demanda_Disp_Mensual'] + df['Demanda_Rem_Mensual']
        df['Demanda_Diaria'] = df['Demanda_Mensual'] / 30.0

        # Pedido separado por canal: dispensacion vs bodega+puntos, remisiones vs
        # solo bodega principal. Deja Necesidad_Disp/Rem/Mensual y los Pedir_*.
        self.pedido_por_canal(df)

        # Valorizado y estado de compra (sobre el pedido TOTAL, sin importar canal)
        df['Valorizado Ult Costo'] = self._valorizar(df['Cantidad_a_Pedir_Rest_Inv'],
                                           df.get('Ultimo Costo'), df.get('Ultimo Costo'))
        df['Valorizado Promedio'] = self._valorizar(df['Cantidad_a_Pedir_Rest_Inv'],
                                             df.get('Costo Promedio'), df.get('Costo Promedio'))
        df['Valorizado Ult Costo Sin Rest Inv'] = self._valorizar(df['Necesidad_Mensual'],
                                                       df.get('Ultimo Costo'), df.get('Ultimo Costo'))
        df['Valorizado Promedio Sin Rest Inv'] = self._valorizar(df['Necesidad_Mensual'],
                                                       df.get('Costo Promedio'), df.get('Costo Promedio'))
        df['Estado'] = np.where(df['Cantidad_a_Pedir_Rest_Inv'] > 0, 'COMPRAR', 'NO COMPRAR')

        agregados = {
            'Consumo_Molecula': ('Consumo_Acum', 'sum'),
            'Stock_Total': ('Stock_Total', 'sum'),
            'Stock_Bodega_Principal': ('Stock_Bodega_Principal', 'sum'),
            'Demanda_Disp_Mensual': ('Demanda_Disp_Mensual', 'sum'),
            'Demanda_Rem_Mensual': ('Demanda_Rem_Mensual', 'sum'),
            'N_Productos': ('Codigo', 'count'),
        }
        if 'Formulas_Ponderadas' in df.columns:
            agregados['Formulas_Ponderadas'] = ('Formulas_Ponderadas', 'sum')

        # Consumo por contrato, para poder repartir tambien el pedido de molecula
        for col in self.SEGMENTOS_CONTRATO:
            if col in df.columns:
                agregados[col] = (col, 'sum')

        mol = df.groupby(['Codigo_Molecula', 'Molecula'], dropna=False).agg(**agregados).reset_index()

        # El Pareto de molecula usa el mismo criterio que el de producto
        col_pareto = 'Formulas_Ponderadas' if self.criterio_rotacion == 'formulas' else 'Consumo_Molecula'
        mol['Rotacion'] = self._pareto_abc(mol[col_pareto], umbral_A, umbral_M)

        mol['Demanda_Mensual'] = mol['Demanda_Disp_Mensual'] + mol['Demanda_Rem_Mensual']
        mol['Demanda_Diaria'] = mol['Demanda_Mensual'] / 30.0

        # Mismo criterio por canal que a nivel producto (deja Necesidad_* y Pedir_*)
        self.pedido_por_canal(mol)

        self.pedido_molecula = mol

    def procesar(self):
        self.limpiar_datos()
        self.clasificar_segmentos()
        # Demanda mensual ponderada 70/30 (ultimos 3 meses 70%, primeros 3 meses 30%),
        # calculada por canal porque cada uno alimenta su propio pedido.
        self.demanda_disp_mensual = self.calcular_ponderados(self.consumo_dispensacion)
        self.demanda_rem_mensual = self.calcular_ponderados(
            self.consumo_remisiones, col_cantidad='Consumo_Remisiones')
        self.consolidar_consumos()
        self.construir_base()
        self.calcular_consumo_mensual()
        self.calcular_consumo_molecula()
        self.calcular_rotacion()
        self.calcular_rotacion_por_canal()
        self.calcular_pedido()

    def imprimir_resumen_pedido(self):
        """Resumen del motor de pedido a nivel producto y molecula."""
        print("\n" + "=" * 70)
        print("                 MOTOR DE PEDIDO / PROYECCION                 ")
        print("=" * 70)

        prod = self.maestro_consumo
        a_pedir_prod = prod[prod['Cantidad_a_Pedir_Rest_Inv'] > 0]
        print(f"Productos que requieren pedido: {len(a_pedir_prod):,} de {len(prod):,}")
        print(f"Unidades totales a pedir (producto): {prod['Cantidad_a_Pedir_Rest_Inv'].sum():,.0f}")

        cols = ['Codigo', 'Nombre', 'Rotacion', 'Demanda_Mensual', 'Cobertura_Dias',
                'Stock_Total', 'Necesidad_Mensual', 'Cantidad_a_Pedir_Rest_Inv']
        cols = [c for c in cols if c in prod.columns]
        print("\nTOP 10 pedidos por producto:")
        print(prod.sort_values('Cantidad_a_Pedir_Rest_Inv', ascending=False)[cols].head(10).to_string(index=False))

        if hasattr(self, 'pedido_molecula'):
            mol = self.pedido_molecula
            print("\n" + "-" * 70)
            print(f"Moleculas que requieren pedido: {len(mol[mol['Cantidad_a_Pedir_Rest_Inv'] > 0]):,} de {len(mol):,}")
            cols_m = ['Codigo_Molecula', 'Molecula', 'N_Productos', 'Rotacion',
                      'Stock_Total', 'Necesidad_Mensual', 'Cantidad_a_Pedir_Rest_Inv']
            cols_m = [c for c in cols_m if c in mol.columns]
            print("\nTOP 10 pedidos por molecula:")
            print(mol.sort_values('Cantidad_a_Pedir_Rest_Inv', ascending=False)[cols_m].head(10).to_string(index=False))
        print("=" * 70 + "\n")

    def imprimir_resumen_consolidado(self):
        print("------ CONSUMO CONSOLIDADO -------")
        print(self.consumo_consolidado.head())
        print("\nTotal productos únicos con consumo:", len(self.consumo_consolidado))

    def imprimir_resumen_base(self):
        print("\n--- Base (Maestro + Consumo) Creada ---")
        print(f"\nTotal de registros en la Base maestro: {len(self.maestro_consumo)}")
        print(f"\nProductos con demanda > 0: {len(self.maestro_consumo[self.maestro_consumo['Consumo_Acum'] > 0])}")

        columnas_vistas = ['Codigo',
                      'Nombre',
                      'Codigo_Molecula',
                      'Molecula',
                      'Consumo_Molecula',
                      'Consumo_NEPS_Capita',
                      'Consumo_NEPS_Evento',
                      'Consumo_FOMAG_Evento',
                      'Consumo_Remisiones',
                      'Consumo_Acum',
                      'Formulas_Ponderadas',
                      *self.COLS_MAESTRO_INFO,
                      'Rotacion',
                      'Rotacion_Dispensacion',
                      'Rotacion_Remisiones',
                      'Stock_Bodega_Principal',
                      'Stock_Puntos_Dispensacion',
                      'Stock_Total',
                      'Cantidad_a_Pedir_Rest_Inv',
                      'Necesidad_Mensual',
                      *self.SEGMENTOS_CONTRATO.values()]
        cols_existentes = [col for col in columnas_vistas if col in self.maestro_consumo.columns]
        print(self.maestro_consumo[cols_existentes].head())

    def imprimir_resumen_molecula(self):
        print("\n" + "=" * 70)
        print("      VISTA COMPARATIVA: CONSUMO INDIVIDUAL VS CONSUMO MOLÉCULA")
        print("=" * 70)

        cols_vista = ['Codigo',
                      'Nombre',
                      'Codigo_Molecula',
                      'Molecula',
                      'Consumo_Molecula',
                      'Consumo_NEPS_Capita',
                      'Consumo_NEPS_Evento',
                      'Consumo_FOMAG_Evento',
                      'Consumo_Remisiones',
                      'Consumo_Acum',
                      'Formulas_Ponderadas',
                      *self.COLS_MAESTRO_INFO,
                      'Rotacion',
                      'Rotacion_Dispensacion',
                      'Rotacion_Remisiones',
                      'Stock_Bodega_Principal',
                      'Stock_Puntos_Dispensacion',
                      'Stock_Total',
                      'Cantidad_a_Pedir_Rest_Inv',
                      'Necesidad_Mensual',
                      *self.SEGMENTOS_CONTRATO.values()]

        cols_existentes = [c for c in cols_vista if c in self.maestro_consumo.columns]

        print(self.maestro_consumo[cols_existentes].head(20).to_string(index=False))
        print("=" * 70 + "\n")

    def imprimir_resumen_rotacion(self):
        """Resumen de la clasificacion de rotacion A/M/B."""
        print("\n" + "=" * 78)
        print(f"     CLASIFICACION DE ROTACION (A / M / B) - criterio: {self.criterio_rotacion}")
        print("=" * 78)
        if 'Rotacion' not in self.maestro_consumo.columns:
            print("[!] No se ha calculado la rotacion.")
            return

        df = self.maestro_consumo
        col_base = 'Formulas_Ponderadas' if self.criterio_rotacion == 'formulas' else 'Consumo_Acum'
        conteo = df['Rotacion'].value_counts()
        total_consumo = df['Consumo_Acum'].sum()

        for cat in ['A', 'M', 'B']:
            n = int(conteo.get(cat, 0))
            consumo_cat = df.loc[df['Rotacion'] == cat, 'Consumo_Acum'].sum()
            pct_prod = n / len(df) * 100 if len(df) else 0
            pct_cons = consumo_cat / total_consumo * 100 if total_consumo else 0
            print(f"  {cat}: {n:>5,} productos ({pct_prod:>5.1f}% del catalogo) "
                  f"-> {consumo_cat:>14,.0f} unids ({pct_cons:>5.1f}% del consumo)")

        print("-" * 78)
        print(f"TOP 10 por {col_base}:")
        cols = [c for c in ['Codigo', 'Nombre', col_base, 'Rotacion',
                            'Cobertura_Dias', 'Stock_Total', 'Cantidad_a_Pedir_Rest_Inv']
                if c in df.columns]
        top = df.sort_values(col_base, ascending=False)[cols].head(10).copy()
        if 'Nombre' in top.columns:
            top['Nombre'] = top['Nombre'].astype(str).str.slice(0, 42)
        print(top.to_string(index=False))
        print("=" * 78 + "\n")

    def imprimir_resumen_mensual(self):
        """Consumo mes a mes, con cuadre contra Consumo_Acum y aviso de meses incompletos."""
        print("\n" + "=" * 96)
        print("        CONSUMO MENSUAL POR PRODUCTO")
        print("=" * 96)

        cols = getattr(self, 'cols_consumo_mensual', [])
        if not cols:
            print("[!] No se calculo el consumo mensual.")
            return

        df = self.maestro_consumo

        # Que canal aporto cada mes: si falta uno, el mes esta incompleto
        def _periodos(origen, col):
            if 'PERIODO' not in origen.columns:
                return set()
            return set(origen['PERIODO'].astype(str).str.strip().str.replace('-', '_', regex=False))

        p_disp = _periodos(self.consumo_dispensacion, 'Consumo_Dispensacion')
        p_rem = _periodos(self.consumo_remisiones, 'Consumo_Remisiones')

        print(f"  {'Mes':<18}{'Consumo':>16}{'Productos':>12}   Canales con datos")
        print("  " + "-" * 92)
        for periodo, col in zip(self.periodos_mensuales, cols):
            total = df[col].sum()
            n = int((df[col] > 0).sum())
            canales = []
            if periodo in p_disp:
                canales.append('dispensacion')
            if periodo in p_rem:
                canales.append('remisiones')
            aviso = '' if len(canales) == 2 else '   <-- INCOMPLETO'
            print(f"  {col.replace('Consumo_', ''):<18}{total:>16,.0f}{n:>12,}   "
                  f"{' + '.join(canales)}{aviso}")

        suma_mensual = df[cols].sum().sum()
        acum = df['Consumo_Acum'].sum()
        print("  " + "-" * 92)
        print(f"  {'TOTAL':<18}{suma_mensual:>16,.0f}")
        if abs(suma_mensual - acum) < 1:
            print(f"\n  [OK] Cuadre: la suma de los meses coincide con Consumo_Acum ({acum:,.0f}).")
        else:
            print(f"\n  [X] Descuadre: meses {suma_mensual:,.0f} vs Consumo_Acum {acum:,.0f} "
                  f"(dif {suma_mensual - acum:+,.0f}).")

        print("-" * 96)
        print("  TOP 10 productos por consumo total, mes a mes:")
        vista = [c for c in ['Codigo', 'Nombre'] if c in df.columns] + cols
        top = df.sort_values('Consumo_Acum', ascending=False)[vista].head(10).copy()
        if 'Nombre' in top.columns:
            top['Nombre'] = top['Nombre'].astype(str).str.slice(0, 30)
        print(top.to_string(index=False, float_format=lambda x: f'{x:,.0f}'))
        print("=" * 96 + "\n")

    def imprimir_resumen_stock(self):
        """Stock separado: bodega principal (CEDI) vs total en puntos de dispensacion."""
        print("\n" + "=" * 86)
        print("        STOCK: BODEGA PRINCIPAL vs PUNTOS DE DISPENSACION")
        print("=" * 86)

        df = self.maestro_consumo
        bod = df['Stock_Bodega_Principal'].sum()
        pts = df['Stock_Puntos_Dispensacion'].sum()
        tot = bod + pts
        n_puntos = self.stock_puntos['Bodega'].nunique() if 'Bodega' in self.stock_puntos.columns else None

        print(f"  Bodega Principal (CEDI) : {bod:>14,.0f} unids ({bod / tot * 100 if tot else 0:>5.1f}%)  "
              f"| {int((df['Stock_Bodega_Principal'] > 0).sum()):>5,} codigos con existencia")
        print(f"  Puntos de Dispensacion  : {pts:>14,.0f} unids ({pts / tot * 100 if tot else 0:>5.1f}%)  "
              f"| {int((df['Stock_Puntos_Dispensacion'] > 0).sum()):>5,} codigos con existencia"
              + (f"  ({n_puntos} puntos)" if n_puntos else ""))
        print(f"  {'TOTAL':<23} : {tot:>14,.0f} unids")

        print("-" * 86)
        print("  Codigos SIN stock en bodega principal pero CON stock en puntos: "
              f"{int(((df['Stock_Bodega_Principal'] <= 0) & (df['Stock_Puntos_Dispensacion'] > 0)).sum()):,}")
        print("  Codigos CON stock en bodega principal pero SIN stock en puntos: "
              f"{int(((df['Stock_Bodega_Principal'] > 0) & (df['Stock_Puntos_Dispensacion'] <= 0)).sum()):,}")

        print("-" * 86)
        print("  TOP 10 por stock total:")
        cols = [c for c in ['Codigo', 'Nombre', 'Stock_Bodega_Principal',
                            'Stock_Puntos_Dispensacion', 'Stock_Total',
                            'Consumo_Acum', 'Cantidad_a_Pedir_Rest_Inv'] if c in df.columns]
        top = df.sort_values('Stock_Total', ascending=False)[cols].head(10).copy()
        top['Nombre'] = top['Nombre'].astype(str).str.slice(0, 38)
        print(top.to_string(index=False, float_format=lambda x: f'{x:,.0f}'))
        print("=" * 86 + "\n")

    def imprimir_resumen_rotacion_canal(self):
        """Rotacion de dispensacion vs remisiones, y cuanto se contradicen."""
        print("\n" + "=" * 86)
        print("        ROTACION POR CANAL: DISPENSACION vs REMISIONES")
        print("=" * 86)

        df = self.maestro_consumo
        if 'Rotacion_Dispensacion' not in df.columns or 'Rotacion_Remisiones' not in df.columns:
            print("[!] No se calculo la rotacion por canal.")
            return

        orden = ['A', 'M', 'B', '-']
        for canal, col_rot, col_cons in [
            ('DISPENSACION', 'Rotacion_Dispensacion', 'Consumo_Dispensacion_Total'),
            ('REMISIONES', 'Rotacion_Remisiones', 'Consumo_Remisiones'),
        ]:
            total = df[col_cons].sum()
            print(f"\n  {canal}  (consumo 6 meses: {total:,.0f} unidades)")
            for cat in orden:
                n = int((df[col_rot] == cat).sum())
                if not n:
                    continue
                cons = df.loc[df[col_rot] == cat, col_cons].sum()
                etq = 'sin movimiento' if cat == '-' else f'rotacion {cat}'
                print(f"    {etq:<16} {n:>5,} productos  ->  {cons:>14,.0f} unids "
                      f"({cons / total * 100 if total else 0:>5.1f}%)")

        print("\n" + "-" * 86)
        print("  CRUCE  (filas = dispensacion, columnas = remisiones)")
        cruce = pd.crosstab(df['Rotacion_Dispensacion'], df['Rotacion_Remisiones'])
        cruce = cruce.reindex(index=orden, columns=orden).fillna(0).astype(int)
        print(cruce.to_string())

        # Lo que motivo el requerimiento: productos que no coinciden entre canales
        ambos = df[(df['Rotacion_Dispensacion'] != '-') & (df['Rotacion_Remisiones'] != '-')]
        discrepan = ambos[ambos['Rotacion_Dispensacion'] != ambos['Rotacion_Remisiones']]
        print("-" * 86)
        print(f"  Productos que se mueven en AMBOS canales: {len(ambos):,}")
        print(f"  De esos, clasifican DISTINTO segun el canal: {len(discrepan):,} "
              f"({len(discrepan) / len(ambos) * 100 if len(ambos) else 0:.1f}%)")

        extremos = ambos[
            ((ambos['Rotacion_Dispensacion'] == 'A') & (ambos['Rotacion_Remisiones'] == 'B')) |
            ((ambos['Rotacion_Dispensacion'] == 'B') & (ambos['Rotacion_Remisiones'] == 'A'))
        ]
        if len(extremos):
            print(f"\n  Casos extremos (A en un canal, B en el otro): {len(extremos):,}")
            cols = [c for c in ['Codigo', 'Nombre', 'Consumo_Dispensacion_Total', 'Rotacion_Dispensacion',
                                'Consumo_Remisiones', 'Rotacion_Remisiones', 'Rotacion']
                    if c in df.columns]
            top = extremos.sort_values('Consumo_Dispensacion_Total', ascending=False)[cols].head(10).copy()
            top['Nombre'] = top['Nombre'].astype(str).str.slice(0, 34)
            print(top.to_string(index=False))
        print("=" * 86 + "\n")

    def imprimir_resumen_contratos(self):
        """Pedido desglosado por contrato, con verificacion de que las partes cuadren."""
        print("\n" + "=" * 88)
        print("           PEDIDO POR CONTRATO (Capita / Evento / FOMAG / Remisiones)")
        print("=" * 88)

        df = self.maestro_consumo
        cols_pedir = [c for c in self.SEGMENTOS_CONTRATO.values() if c in df.columns]
        if not cols_pedir:
            print("[!] No se calculo el desglose por contrato.")
            return

        total_ped = df['Cantidad_a_Pedir_Rest_Inv'].sum()
        total_cons = df['Consumo_Acum'].sum()

        filas = []
        for col_cons, col_ped in self.SEGMENTOS_CONTRATO.items():
            if col_ped not in df.columns:
                continue
            cons, ped = df[col_cons].sum(), df[col_ped].sum()
            filas.append({
                'Contrato': col_ped.replace('Pedir_', ''),
                'Consumo_6m': cons,
                '%_Cons': cons / total_cons * 100 if total_cons else 0,
                'A_Pedir': ped,
                '%_Pedido': ped / total_ped * 100 if total_ped else 0,
                'Productos': int((df[col_ped] > 0).sum()),
            })

        res = pd.DataFrame(filas)
        res.loc['TOTAL'] = {
            'Contrato': 'TOTAL', 'Consumo_6m': res['Consumo_6m'].sum(), '%_Cons': res['%_Cons'].sum(),
            'A_Pedir': res['A_Pedir'].sum(), '%_Pedido': res['%_Pedido'].sum(),
            'Productos': int((df['Cantidad_a_Pedir_Rest_Inv'] > 0).sum()),
        }
        print(res.to_string(index=False, formatters={
            'Consumo_6m': lambda x: f'{x:,.0f}',
            'A_Pedir': lambda x: f'{x:,.0f}',
            '%_Cons': lambda x: f'{x:5.1f}%',
            '%_Pedido': lambda x: f'{x:5.1f}%',
            'Productos': lambda x: f'{x:,}',
        }))

        # Verificacion: las partes deben sumar exactamente el total
        descuadre = int((df[cols_pedir].sum(axis=1) != df['Cantidad_a_Pedir_Rest_Inv']).sum())
        print("-" * 88)
        if descuadre == 0:
            print(f"[OK] Cuadre del desglose: los {len(cols_pedir)} contratos suman exactamente "
                  f"Cantidad_a_Pedir en los {len(df):,} productos.")
        else:
            print(f"[X] {descuadre:,} productos donde el desglose NO suma Cantidad_a_Pedir.")
        print("=" * 88 + "\n")

    def auditoria_integridad(self):
        print("\n" + "=" * 65)
        print("         AUDITORÍA DE INTEGRIDAD DE DATOS Y CONVENIOS        ")
        print("=" * 65)

        # 0. CÓDIGOS EXCLUIDOS POR NO SER PRODUCTOS REALES
        detalle = getattr(self, 'codigos_excluidos_detalle', {})
        patrones = ', '.join([f'{p}*' for p in self.PREFIJOS_EXCLUIDOS] + list(self.CODIGOS_EXCLUIDOS))
        if detalle:
            resumen = ' | '.join(f'{k}: {v}' for k, v in detalle.items())
            print(f"[OK] Códigos excluidos ({patrones}) -> {resumen}")
        else:
            print(f"[OK] Códigos excluidos ({patrones}): ninguno encontrado en las fuentes.")

        # 0b. ALINEAMIENTO DE PERÍODOS ENTRE CANALES
        comunes = getattr(self, 'periodos_comunes', [])
        recortes = getattr(self, 'periodos_recortados', {})
        if comunes:
            print(f"[OK] Períodos alineados: {len(comunes)} meses "
                  f"({comunes[0]} a {comunes[-1]}) en dispensación y remisiones.")
        if recortes:
            for fuente, (n, meses) in recortes.items():
                print(f"[!] {fuente}: se descartaron {n:,} filas fuera del rango común "
                      f"(meses: {', '.join(meses)}).")

        # 1. VERIFICACIÓN DE DUPLICADOS EN MAESTRO
        # Usamos .duplicated() para contar filas repetidas
        num_duplicados = self.maestro['Codigo'].duplicated().sum()
        if num_duplicados == 0:
            print("[OK] Base Maestra: Sin códigos duplicados.")
        else:
            print(f"[!] Base Maestra: Tiene {num_duplicados:,} códigos duplicados (revisar deduplicación).")

        # 2. CUADRE DISPENSACIÓN GLOBAL Y SEGMENTOS
        total_disp_original = self.consumo_dispensacion['Consumo_Dispensacion'].sum()

        # Sumamos los segmentos de dispensación en la base procesada.
        # Consumo_Sin_Clasificar entra al cuadre: si algo no se clasifico, debe
        # seguir contando, si no el descuadre lo escondería.
        cols_disp_procesadas = ['Consumo_NEPS_Capita', 'Consumo_NEPS_Evento', 'Consumo_FOMAG_Evento',
                                'Consumo_Sin_Clasificar']
        cols_disp_procesadas = [c for c in cols_disp_procesadas if c in self.maestro_consumo.columns]

        total_disp_procesado = self.maestro_consumo[cols_disp_procesadas].sum().sum()
        dif_disp = abs(total_disp_original - total_disp_procesado)

        if dif_disp == 0:
            print(f"[OK] Dispensación Total: Cuadre Exacto ({total_disp_original:,.0f} unidades)")
        else:
            print(f"[X] Dispensación NO cuadra. Orig: {total_disp_original:,.0f} | Proc: {total_disp_procesado:,.0f}")

        # 2b. NADA DEBE QUEDAR SIN CLASIFICAR
        sin_clasificar = self.maestro_consumo['Consumo_Sin_Clasificar'].sum() \
            if 'Consumo_Sin_Clasificar' in self.maestro_consumo.columns else 0
        if sin_clasificar == 0:
            print("[OK] Segmentación: todas las dispensaciones quedaron asignadas a un contrato.")
        else:
            combos = (self.consumo_dispensacion.loc[
                          self.consumo_dispensacion['Segmento'] == 'SIN_CLASIFICAR',
                          ['SIGLA_COMERCIAL_CLIENTE', 'TIPO_SERVICIO']]
                      .drop_duplicates().to_dict('records'))
            print(f"[X] {sin_clasificar:,.0f} unidades SIN CLASIFICAR (cliente/servicio no contemplado):")
            for c in combos[:10]:
                print(f"      - {c['SIGLA_COMERCIAL_CLIENTE']} / {c['TIPO_SERVICIO']}")

        # 3. CUADRE REMISIONES
        total_rem_original = self.consumo_remisiones['Consumo_Remisiones'].sum()
        total_rem_procesado = self.maestro_consumo['Consumo_Remisiones'].sum()

        if abs(total_rem_original - total_rem_procesado) == 0:
            print(f"[OK] Remisiones: Cuadre Exacto ({total_rem_original:,.0f} unidades)")
        else:
            print(f"[X] Remisiones NO cuadra. Orig: {total_rem_original:,.0f} | Proc: {total_rem_procesado:,.0f}")

        # 4. CUADRE STOCK (BODEGA Y PUNTOS)
        total_bod_original = self.stock_bodega['Stock_Bodega_Principal'].sum()
        total_bod_procesado = self.maestro_consumo['Stock_Bodega_Principal'].sum()

        total_pts_original = self.stock_puntos['Stock_Puntos_Dispensacion'].sum()
        total_pts_procesado = self.maestro_consumo['Stock_Puntos_Dispensacion'].sum()

        if abs(total_bod_original - total_bod_procesado) == 0:
            print(f"[OK] Stock Bodega Principal: Cuadre Exacto ({total_bod_original:,.0f} unidades)")
        else:
            print(f"[X] Stock Bodega Diferente. Orig: {total_bod_original:,.0f} | Proc: {total_bod_procesado:,.0f}")

        if abs(total_pts_original - total_pts_procesado) == 0:
            print(f"[OK] Stock Puntos Dispensación: Cuadre Exacto ({total_pts_original:,.0f} unidades)")
        else:
            print(f"[X] Stock Puntos Diferente. Orig: {total_pts_original:,.0f} | Proc: {total_pts_procesado:,.0f}")

        # 5. BÚSQUEDA DE PRODUCTOS HUÉRFANOS
        codigos_maestro = set(self.maestro['Codigo'])
        codigos_consumo = set(self.consumo_consolidado['Codigo'])
        huerfanos = codigos_consumo - codigos_maestro

        if len(huerfanos) == 0:
            print(f"[OK] Registro de Productos: 100% de productos mapeados con el Maestro.")
        else:
            print(f"[!] Alerta: Hay {len(huerfanos):,} productos con consumo/stock que NO existen en el Maestro.")

        # 6. TOP 5 PRODUCTOS DE MAYOR DEMANDA TOTAL
        print("-" * 65)
        print("TOP 5 PRODUCTOS CON MAYOR DEMANDA GLOBAL:")
        top_consumo = self.maestro_consumo.sort_values(by='Consumo_Acum', ascending=False)
        cols_top = ['Codigo', 'Nombre', 'Consumo_Acum', 'Consumo_Molecula']
        cols_existentes = [c for c in cols_top if c in top_consumo.columns]
        print(top_consumo[cols_existentes].head(5).to_string(index=False))
        print("=" * 65 + "\n")