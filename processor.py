import pandas as pd
import numpy as np

import config


class ProyeccionProcessor:

    PREFIJOS_EXCLUIDOS = getattr(config, 'CODIGOS_EXCLUIDOS_PREFIJOS', ('CONT',))
    CODIGOS_EXCLUIDOS = getattr(config, 'CODIGOS_EXCLUIDOS_EXACTOS', ('M99999',))

    SEGMENTOS_CONTRATO = {
        'Consumo_NEPS_Capita':  'Pedir_NEPS_Capita',
        'Consumo_NEPS_Evento':  'Pedir_NEPS_Evento',
        'Consumo_FOMAG_Evento': 'Pedir_FOMAG_Evento',
        'Consumo_Remisiones':   'Pedir_Remisiones',
    }

    COLS_MAESTRO_INFO = ('Grupo', 'Proveedor', 'Ultimo Costo', 'Costo Promedio')

    MESES_ES = {'01': 'Ene', '02': 'Feb', '03': 'Mar', '04': 'Abr',
                '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Ago',
                '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dic'}

    COLS_CONSUMO_DISPENSACION = (
        'Consumo_NEPS_Capita',
        'Consumo_NEPS_Evento',
        'Consumo_FOMAG_Evento',
        'Consumo_Sin_Clasificar',
    )

    def __init__(self, maestro, consumo_dispensacion, consumo_remisiones, stock_bodega, stock_puntos, molecula_compra,
                 criterio_rotacion=None, cobertura_dias_DISP = None, lead_time_dias_DISP = None, dias_seguridad_DISP = None,
                 cobertura_dias_REMI = None, lead_time_dias_REMI = None, dias_seguridad_REMI = None, umbral_A=None, umbral_M=None):
        self.maestro = maestro
        self.consumo_dispensacion = consumo_dispensacion
        self.consumo_remisiones = consumo_remisiones
        self.stock_bodega = stock_bodega
        self.stock_puntos = stock_puntos
        self.molecula_compra = molecula_compra
        self.consumo_consolidado = None
        self.maestro_consumo = None

        self.criterio_rotacion = criterio_rotacion or getattr(config, 'CRITERIO_ROTACION', 'volumen')
        self.cobertura_dias_DISP = cobertura_dias_DISP if cobertura_dias_DISP is not None else getattr(config, 'COBERTURA_DIAS_DISP', {'A': 30, 'M': 30, 'B': 30})
        self.lead_time_dias_DISP = lead_time_dias_DISP if lead_time_dias_DISP is not None else getattr(config, 'LEAD_TIME_DIAS_DISP', 30)
        self.dias_seguridad_DISP = dias_seguridad_DISP if dias_seguridad_DISP is not None else getattr(config, 'DIAS_SEGURIDAD_DISP', 15)
        self.cobertura_dias_REMI = cobertura_dias_REMI if cobertura_dias_REMI is not None else getattr(config, 'COBERTURA_DIAS_REMI', {'A': 30, 'M': 30, 'B': 30})
        self.lead_time_dias_REMI = lead_time_dias_REMI if lead_time_dias_REMI is not None else getattr(config, 'LEAD_TIME_DIAS_REMI', 30)
        self.dias_seguridad_REMI = dias_seguridad_REMI if dias_seguridad_REMI is not None else getattr(config, 'DIAS_SEGURIDAD_REMI', 15)
        self.umbral_A = umbral_A if umbral_A is not None else getattr(config, 'UMBRAL_A', 80)
        self.umbral_M = umbral_M if umbral_M is not None else getattr(config, 'UMBRAL_M', 95)

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
        self.molecula_compra.rename(columns={'Descripcion Molecula': 'Molecula'}, inplace=True)

        # Desduplicar catálogo maestro
        self.maestro = self.maestro.drop_duplicates(subset=['Codigo'], keep='first')

        # Desduplicar moléculas (el reporte nuevo trae una fila por bodega)
        self.molecula_compra = self.molecula_compra.drop_duplicates(subset=['Codigo'], keep='first')

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
    @staticmethod
    def _prorratear_entero(total, pesos):
        """
        Reparte el entero `total` de cada fila entre varias columnas, en
        proporcion a `pesos`, garantizando que las partes sumen EXACTAMENTE
        el total (metodo de mayores residuos).
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

    @staticmethod
    def redondear_por_empaque(cantidad, pastillas, rotacion):
        unidades = pd.to_numeric(cantidad, errors='coerce').fillna(0).to_numpy(dtype='float64')
        cantPas = pd.to_numeric(pastillas, errors='coerce').fillna(0).to_numpy(dtype='float64')
        rot = rotacion.astype(str).to_numpy()

        sin_empaque = cantPas < 2
        uni_seguro = np.where(sin_empaque,1.0, cantPas)

        piso = np.floor(unidades / uni_seguro) * uni_seguro
        techo = np.ceil(unidades / uni_seguro) * uni_seguro
        resto = unidades - piso

        hacia_arriba = np.isin(rot, ['A', 'M'])
        baja = resto < (uni_seguro / 2.0)

        res = np.where(hacia_arriba, techo, np.where(baja, piso, techo))
        res = np.where(sin_empaque, unidades, res)
        return res.round().astype('int64')

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

        df['Necesidad_Mensual'] = df['Necesidad_Disp'] + df['Necesidad_Rem']
        df['Cantidad_a_Pedir_Rest_Inv'] = df['Pedir_Dispensacion_Total'] + pedir_remi
        puntos = df['Stock_Total'] - df['Stock_Bodega_Principal']

        #Columna 1: Disp primero -> Comercial toma el restante (MODELO VIGENTE)
        bodega_sobrante_1 = np.minimum(df['Stock_Bodega_Principal'], df['Stock_Total'] - objetivo_disp).clip(lower=0)
        df['Bodega_Disponible_Comercial'] = bodega_sobrante_1
        pedir_com = np.ceil((objetivo_remi - bodega_sobrante_1).clip(lower=0)).astype('int64')
        df['Pedir_Remisiones'] = pedir_com
        df['Cantidad a Pedir'] = (pedir_disp + pedir_com).astype('int64')

        #Columna pedir sin CEDI
        pedir_disp_sinCEDI = np.ceil((df['Necesidad_Mensual'] - df['Stock_Bodega_Principal']).clip(lower=0)).astype('int64')
        df['Cantidad a Pedir sin CEDI'] = np.ceil(pedir_disp_sinCEDI).astype('int64')
        porcentaje_disp1 = ((objetivo_disp / df['Necesidad_Mensual'])).replace([np.inf, -np.inf], 0).fillna(0)
        porcentaje_remi1 = ((objetivo_remi / df['Necesidad_Mensual'])).replace([np.inf, -np.inf], 0).fillna(0)
        df['Pedir Remisiones sin CEDI'] = np.ceil(porcentaje_remi1 * pedir_disp_sinCEDI.clip(lower=0)).fillna(0).astype('int64')
        df['Pedir Dispensacion Total sin CEDI'] = np.ceil((porcentaje_disp1 * pedir_disp_sinCEDI).clip(lower=0)).fillna(0).astype('int64')
        if cols_disp:
            partes_sinCEDI = self._prorratear_entero(df['Pedir Dispensacion Total sin CEDI'], df[cols_disp].clip(lower=0))
            for col in cols_disp:
                df[self.SEGMENTOS_CONTRATO[col] + ' sin CEDI'] = partes_sinCEDI[col]

        #Columna pedir sin PUNTOS
        pedir_disp_sinPUNTOS = np.ceil((df['Necesidad_Mensual'] - puntos).clip(lower=0)).astype('int64')
        df['Cantidad a Pedir sin PUNTOS'] = np.ceil(pedir_disp_sinPUNTOS).astype('int64')
        porcentaje_disp = ((objetivo_disp / df['Necesidad_Mensual'])).replace([np.inf, -np.inf], 0).fillna(0)
        porcentaje_remi = ((objetivo_remi / df['Necesidad_Mensual'])).replace([np.inf, -np.inf], 0).fillna(0)
        df['Pedir Remisiones sin PUNTOS'] = np.ceil((porcentaje_remi * pedir_disp_sinPUNTOS).clip(lower=0)).fillna(0).astype('int64')
        df['Pedir Dispensacion Total sin PUNTOS'] = np.ceil((porcentaje_disp * pedir_disp_sinPUNTOS).clip(lower=0)).fillna(0).astype('int64')
        if cols_disp:
            partes_sinPUNTOS = self._prorratear_entero(df['Pedir Dispensacion Total sin PUNTOS'], df[cols_disp].clip(lower=0))
            for col in cols_disp:
                df[self.SEGMENTOS_CONTRATO[col] + ' sin PUNTOS'] = partes_sinPUNTOS[col]

        #Columnas sobrantes Dispe/Remi y Sobrante Total
        df['Sobrantes Disp'] = np.ceil(objetivo_disp - df['Stock_Total']).astype('int64')
        df['Sobrantes Remi'] = np.ceil(objetivo_remi - bodega_sobrante_1).astype('int64')
        df['Total Sobrantes'] = np.ceil(np.minimum(objetivo_disp, df['Stock_Total']) +
                                   np.minimum(objetivo_remi, bodega_sobrante_1) - df['Stock_Total']).astype('int64')

        # Sobrantes por escenario: netean contra el MISMO stock que usa el pedido
        # de cada hoja (positivo = falta; negativo = sobra stock). El Disp/Remi se
        # reparte con el mismo % del objetivo que usa el pedido de esa hoja.
        sobra_cedi = df['Necesidad_Mensual'] - df['Stock_Bodega_Principal']
        df['Sobrantes Disp sin CEDI'] = np.ceil(porcentaje_disp1 * sobra_cedi).astype('int64')
        df['Sobrantes Remi sin CEDI'] = np.ceil(porcentaje_remi1 * sobra_cedi).astype('int64')
        df['Total Sobrantes sin CEDI'] = np.ceil(sobra_cedi).astype('int64')

        sobra_pts = df['Necesidad_Mensual'] - puntos
        df['Sobrantes Disp sin PUNTOS'] = np.ceil(porcentaje_disp * sobra_pts).astype('int64')
        df['Sobrantes Remi sin PUNTOS'] = np.ceil(porcentaje_remi * sobra_pts).astype('int64')
        df['Total Sobrantes sin PUNTOS'] = np.ceil(sobra_pts).astype('int64')

        #Columna 2: Remi primero -> Dispensacion toma el restante
        bodega_sobrante_2 = (df['Stock_Bodega_Principal'] - objetivo_remi).clip(lower=0)
        pedir_disp_2 = np.ceil((objetivo_disp -(puntos + bodega_sobrante_2)).clip(lower=0))
        df['Cantidad_a_Pedir_RemPrimero'] = (pedir_disp_2 + pedir_remi).astype('int64')
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
        df['Valorizado Ult Costo'] = self._valorizar(df['Cantidad a Pedir'],
                                           df.get('Ultimo Costo'), df.get('Ultimo Costo'))
        df['Valorizado Promedio'] = self._valorizar(df['Cantidad a Pedir'],
                                             df.get('Costo Promedio'), df.get('Costo Promedio'))
        df['Valorizado Ult Costo Sin Rest Inv'] = self._valorizar(df['Necesidad_Mensual'],
                                                       df.get('Ultimo Costo'), df.get('Ultimo Costo'))
        df['Valorizado Promedio Sin Rest Inv'] = self._valorizar(df['Necesidad_Mensual'],
                                                       df.get('Costo Promedio'), df.get('Costo Promedio'))
        df['Valorizado Ult Costo sin CEDI'] = self._valorizar(df['Cantidad a Pedir sin CEDI'],
                                                              df.get('Ultimo Costo'), df.get('Ultimo Costo'))
        df['Valorizado Promedio sin CEDI'] = self._valorizar(df['Cantidad a Pedir sin CEDI'],
                                                             df.get('Costo Promedio'), df.get('Costo Promedio'))
        df['Valorizado Ult Costo sin PUNTOS'] = self._valorizar(df['Cantidad a Pedir sin PUNTOS'],
                                                                df.get('Ultimo Costo'), df.get('Ultimo Costo'))
        df['Valorizado Promedio sin PUNTOS'] = self._valorizar(df['Cantidad a Pedir sin PUNTOS'],
                                                               df.get('Costo Promedio'), df.get('Costo Promedio'))

        df['Estado'] = np.where(df['Cantidad a Pedir'] > 0, 'COMPRAR', 'NO COMPRAR')

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

    def aplicar_redondeo_empaque(self):
        df = self.maestro_consumo
        cantPas = df['Cant. Pastillas']

        variantes = [
            {  # hoja TODO (vigente)
                'segmentos':  ['Pedir_NEPS_Capita', 'Pedir_NEPS_Evento', 'Pedir_FOMAG_Evento'],
                'disp_total': 'Pedir_Dispensacion_Total',
                'remi':       'Pedir_Remisiones',
                'total':      'Cantidad a Pedir',
                'val_ult':    'Valorizado Ult Costo',
                'val_prom':   'Valorizado Promedio',
            },
            {  # hoja TODO REST CEDI
                'segmentos':  ['Pedir_NEPS_Capita sin CEDI', 'Pedir_NEPS_Evento sin CEDI', 'Pedir_FOMAG_Evento sin CEDI'],
                'disp_total': 'Pedir Dispensacion Total sin CEDI',
                'remi':       'Pedir Remisiones sin CEDI',
                'total':      'Cantidad a Pedir sin CEDI',
                'val_ult':    'Valorizado Ult Costo sin CEDI',
                'val_prom':   'Valorizado Promedio sin CEDI',
            },
            {  # hoja TODO REST PUNTOS
                'segmentos':  ['Pedir_NEPS_Capita sin PUNTOS', 'Pedir_NEPS_Evento sin PUNTOS', 'Pedir_FOMAG_Evento sin PUNTOS'],
                'disp_total': 'Pedir Dispensacion Total sin PUNTOS',
                'remi':       'Pedir Remisiones sin PUNTOS',
                'total':      'Cantidad a Pedir sin PUNTOS',
                'val_ult':    'Valorizado Ult Costo sin PUNTOS',
                'val_prom':   'Valorizado Promedio sin PUNTOS',
            },
        ]

        for v in variantes:
            # Dispensacion (segmentos + total de dispensacion) -> Rotacion_Dispensacion
            for col in v['segmentos'] + [v['disp_total']]:
                if col in df.columns:
                    df[col] = self.redondear_por_empaque(df[col], cantPas, df['Rotacion_Dispensacion'])

            # Remisiones -> Rotacion_Remisiones
            if v['remi'] in df.columns:
                df[v['remi']] = self.redondear_por_empaque(df[v['remi']], cantPas, df['Rotacion_Remisiones'])

            # Total = suma de las dos componentes ya redondeadas
            df[v['total']] = (df[v['disp_total']] + df[v['remi']]).astype('int64')

            # Revalorizar sobre el total redondeado
            df[v['val_ult']]  = self._valorizar(df[v['total']], df.get('Ultimo Costo'), df.get('Ultimo Costo'))
            df[v['val_prom']] = self._valorizar(df[v['total']], df.get('Costo Promedio'), df.get('Costo Promedio'))

        for col in ['Demanda_Disp_Mensual', 'Necesidad_Disp']:
            if col in df.columns:
                df[col] = self.redondear_por_empaque((df[col]), cantPas, df['Rotacion_Dispensacion'])
        for col in ['Demanda_Rem_Mensual', 'Necesidad_Rem']:
            if col in df.columns:
                df[col] = self.redondear_por_empaque(df[col], cantPas, df['Rotacion_Remisiones'])
        df['Demanda_Mensual'] = (df['Demanda_Disp_Mensual'] + df['Demanda_Rem_Mensual']).astype('int64')
        df['Necesidad_Mensual'] = (df['Necesidad_Disp'] + df['Necesidad_Rem']).astype('int64')
        
        df['Estado'] = np.where(df['Cantidad a Pedir'] > 0, 'COMPRAR', 'NO COMPRAR')


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
        self.aplicar_redondeo_empaque()


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

        total_ped = df['Cantidad a Pedir'].sum()
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
            'Productos': int((df['Cantidad a Pedir'] > 0).sum()),
        }
        print(res.to_string(index=False, formatters={
            'Consumo_6m': lambda x: f'{x:,.0f}',
            'A_Pedir': lambda x: f'{x:,.0f}',
            '%_Cons': lambda x: f'{x:5.1f}%',
            '%_Pedido': lambda x: f'{x:5.1f}%',
            'Productos': lambda x: f'{x:,}',
        }))

        # Verificacion: las partes deben sumar exactamente el total
        descuadre = int((df[cols_pedir].sum(axis=1) != df['Cantidad a Pedir']).sum())
        print("-" * 88)
        if descuadre == 0:
            print(f"[OK] Cuadre del desglose: los {len(cols_pedir)} contratos suman exactamente "
                  f"'Cantidad a Pedir' en los {len(df):,} productos.")
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

