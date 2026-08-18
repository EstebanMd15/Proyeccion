import io
from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.templating import Jinja2Templates
from datetime import date
from fastapi.responses import StreamingResponse
from main import cargar_datos, exportar_excel
from processor import ProyeccionProcessor
from fastapi.staticfiles import StaticFiles
import uuid
app = FastAPI()
resultados = {}
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.post("/generar")
def generar(request: Request,
        maestro: UploadFile | None = File(None),
        dispensacion: UploadFile | None = File(None),
        remisiones: UploadFile | None = File(None),
        stock_bodega: UploadFile | None = File(None),
        stock_puntos: UploadFile | None= File(None),
        moleculas: UploadFile | None = File(None),
        cob_disp_a: int = Form(...),
        cob_disp_m: int = Form(...),
        cob_disp_b: int = Form(...),
        lead_disp: int = Form(...),
        seg_disp: int = Form(...),
        cob_rem_a: int = Form(...),
        cob_rem_m: int = Form(...),
        cob_rem_b: int = Form(...),
        lead_rem: int = Form(...),
        seg_rem: int = Form(...),
        umbral_a: int = Form(...),
        umbral_m: int = Form(...),
        accion: str = Form(...),

):
    archivos = {
        "Maestro": maestro,
        "Dispensación": dispensacion,
        "Remisiones": remisiones,
        "Bodega (CEDI)": stock_bodega,
        "Puntos": stock_puntos,
        "Moléculas": moleculas,
    }
    faltantes = [nombre for nombre, f in archivos.items() if f is None or not f.filename]
    if faltantes:
        return templates.TemplateResponse(request, "index.html", {
            "error": "Faltan estos archivos: " + ", ".join(faltantes),
        })
    cobertura_dias_DISP = {"A": cob_disp_a, "M": cob_disp_m, "B": cob_disp_b}
    cobertura_dias_REM = {"A": cob_rem_a, "M": cob_rem_m, "B": cob_rem_b}
    datos = cargar_datos(
        maestro.file, dispensacion.file, remisiones.file, stock_bodega.file,
        stock_puntos.file, moleculas.file,
    )
    proc = ProyeccionProcessor(
        *datos,
        cobertura_dias_DISP=cobertura_dias_DISP,
        lead_time_dias_DISP=lead_disp,
        dias_seguridad_DISP=seg_disp,
        cobertura_dias_REMI=cobertura_dias_REM,
        lead_time_dias_REMI=lead_rem,
        dias_seguridad_REMI=seg_rem,
        umbral_A=umbral_a,
        umbral_M=umbral_m,
    )
    proc.procesar()

    buffer = io.BytesIO()
    exportar_excel(proc, buffer=buffer)

    if accion == "descargar":
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="Proyeccion-{date.today():%Y-%m-%d}.xlsx"'},
        )

    download_id = uuid.uuid4().hex
    resultados[download_id] = buffer.getvalue()

    df = proc.maestro_consumo

    tarjetas = [
        {"titulo": "Restando CEDI y PUNTOS",
         "ult": f"{df['Valorizado Ult Costo'].sum():,.0f}",
         "prom": f"{df['Valorizado Promedio'].sum():,.0f}",
         "und": f"{int(df['Cantidad a Pedir'].sum()):,}"},
        {"titulo": "Solo restando CEDI",
         "ult": f"{df['Valorizado Ult Costo sin CEDI'].sum():,.0f}",
         "prom": f"{df['Valorizado Promedio sin CEDI'].sum():,.0f}",
         "und": f"{int(df['Cantidad a Pedir sin CEDI'].sum()):,}"},
        {"titulo": "Solo restando PUNTOS",
         "ult": f"{df['Valorizado Ult Costo sin PUNTOS'].sum():,.0f}",
         "prom": f"{df['Valorizado Promedio sin PUNTOS'].sum():,.0f}",
         "und": f"{int(df['Cantidad a Pedir sin PUNTOS'].sum()):,}",}
    ]
    top = (df.groupby("Proveedor")
           .agg(costo=("Valorizado Ult Costo", "sum"),
                unidades=("Cantidad a Pedir", "sum"),)
           .sort_values("costo", ascending=False))
    top15 = [{"Proveedor": prov,
              "costo": f"{fila.costo:,.0f}",
              "unidades": f"{int(fila.unidades):,}"}
             for prov, fila in top.iterrows()]

    return templates.TemplateResponse(request, "resultado.html", {
        "tarjetas": tarjetas,
        "top15": top15,
        "download_id": download_id,
    })

@app.get("/descargar/{download_id}")
def descargar(download_id: str):
    return StreamingResponse(
        io.BytesIO(resultados[download_id]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Proyección-{date.today():%Y-%m-%d}.xlsx"'}
    )