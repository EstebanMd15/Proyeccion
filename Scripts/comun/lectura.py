import io
import pandas as pd

def leer_con_encabezado(ruta, col_clave, max_filas=10, **kwargs):
    filas_encabezado = None
    preview = pd.read_excel(ruta, header=None, nrows=max_filas)
    for i in range(len(preview)):
        valores_fila = preview.iloc[i].astype(str).str.strip().values
        if col_clave in valores_fila:
            filas_encabezado = i
            break
    if filas_encabezado is None:
        raise ValueError(f"No encontre '{col_clave}' en las primeras {max_filas} filas de {ruta}.")
    df = pd.read_excel(ruta, skiprows=filas_encabezado, **kwargs)

    if str(df.columns[0]).startswith('Unnamed') and df.iloc[:, 0].isna().all():
        df = df.drop(columns=df.columns[0])
    return df

def leer_csv_pipe(ruta, col_clave, cols=None, max_filas=10, encoding='latin-1'):
    if isinstance(ruta, (str, bytes)) or hasattr(ruta, '__fspath__'):
        with open(ruta, 'rb') as fh:
            crudo = fh.read()
    else:
        crudo = ruta.read()
    texto = crudo.decode(encoding)

    lineas = texto.splitlines()[:max_filas]
    fila_encabezado = next((i for i, l in enumerate(lineas)
                            if col_clave in [c.strip() for c in l.split('|')]), None)
    if fila_encabezado is None:
        raise ValueError(f"No encontre '{col_clave}' en las primeras {max_filas} filas del archivo.")
    n_campos = len(lineas[fila_encabezado].split('|'))

    df = pd.read_csv(io.StringIO(texto), sep='|', skiprows=fila_encabezado, dtype=str,
                     engine='python', on_bad_lines=lambda campos: campos[:n_campos])
    df.columns = df.columns.str.strip()
    if cols:
        df = df[cols]
    return df.apply(lambda s: s.str.strip())