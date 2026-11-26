from Scripts.config import CONTRATO_FOMAG_VIGENTE

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
