import os
import gspread


CALIDAD_ID_SHEETS = os.environ.get("CALIDAD_SHEET_ID")
CALIDAD_CRENDENCIALES = os.environ.get("CALIDAD_CREDENCIALES")
cliente = None

def get_cliente():
    global cliente
    if cliente is None:
        if not CALIDAD_ID_SHEETS or not CALIDAD_CRENDENCIALES:
            raise RuntimeError("Falta la variable de entorno Credenciales y Calidad Sheets ID")
        cliente = gspread.service_account(filename=CALIDAD_CRENDENCIALES).open_by_key(CALIDAD_ID_SHEETS)
    return cliente
libro = get_cliente()
print(libro.title)

for libro1 in libro.worksheets():
    print(libro1.title)

print(libro.worksheet("BD_LECTURAS").row_values(1))