from fastapi import APIRouter, Request, File, UploadFile
from fastapi.responses import JSONResponse

from Scripts.comun.lectura import leer_con_encabezado, leer_csv_pipe
from Scripts.comun.respuestas import respuesta_excel
from Scripts.mejor_opcion import motor
from Scripts.comun.plantillas import templates
from Scripts.comun.maestro import medicamentos_comerciales, codigos_fomag_desde_archivo

import pandas as pd
import io
from datetime import date


router = APIRouter()

@router.post("/compras/mejor-opcion")
def mejor_opcion_generar(
        proyeccion: UploadFile | None = File(None),
        maestro: UploadFile | None = File(None),
        lp: UploadFile | None = File(None),
        cto_fomag: UploadFile | None = File(None),):

    faltantes = [n for n, f in {"proyeccion": proyeccion, "maestro": maestro,
                                "lp": lp, "cto_fomag": cto_fomag}.items()
                 if f is None or not f.filename]
    if faltantes:
        return JSONResponse({"error": "Faltan archivos: " + ", ".join(faltantes)}, status_code=400)
    try:
        df_proyeccion = pd.read_excel(proyeccion.file, sheet_name="Todo REST CEDI", skiprows=1)
        df_maestro = leer_con_encabezado(maestro.file, "Codigo")
        df_lp = leer_con_encabezado(lp.file, 'Codigo Articulo')
        df_cto_fomag = leer_csv_pipe(cto_fomag.file, 'Código Articulo', cols=['Nro. Contrato',
                                                                              'Código Articulo', 'Estado Referencia', 'Codigo Padre', 'Código Cum.1'])

        comerciales = medicamentos_comerciales(df_maestro)
        codigos_fomag = codigos_fomag_desde_archivo(df_cto_fomag, df_maestro, comerciales)

        if 'Pendientes_FOMAG' not in df_proyeccion.columns:
            return JSONResponse({"error": "Genera una Proyección nueva, esta no trae los pendientes_FOMAG"},
                                status_code=400)

        buffer = io.BytesIO()
        motor.generar_mejor_opcion(df_proyeccion, df_maestro, df_lp, codigos_fomag, buffer)
        buffer.seek(0)
    except Exception as e:
        return JSONResponse({"error": "No se pudo generar el archivo 'Mejor Opción'. Revisa que los archivos sean, la proyección, "
                                      "el maestro, la lista de precio general y el contrato FOMAG. (" + str(e) + ")"}, status_code=400)
    return respuesta_excel(
        buffer,
        f"Mejor-Opcion-{date.today():%Y-%m-%d}.xlsx",
    )

@router.get("/mejor-opcion")
def mejor_opcion_pagina(request: Request):
    return templates.TemplateResponse(request, "mejor_opcion.html", {"seccion": "compras"})