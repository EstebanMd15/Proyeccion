import re
import pandas as pd

_CHARS_ILEGALES = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')


def limpiar_df(df):
    """Quitar caracteres de control que openpyxl rechaza."""
    df = df.copy()

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        df[col] = df[col].astype(str).str.replace(_CHARS_ILEGALES, '', regex=True)
    return df