import io
from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.templating import Jinja2Templates
from datetime import date
from fastapi.responses import StreamingResponse, JSONResponse
from main import cargar_datos, exportar_excel
from processor import ProyeccionProcessor
from fastapi.staticfiles import StaticFiles
import uuid
app = FastAPI()
resultados = {}
MAX_RESULTADOS = 20   # dashboards guardados en memoria; al pasarse se descartan los mas viejos
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


    df = proc.maestro_consumo

    # Cada tarjeta es un modelo distinto con SUS columnas (valorizado y unidades).
    # Se calcula tanto el resumen (tarjeta) como la tabla de proveedores de cada uno,
    # para que al hacer clic en una tarjeta la tabla muestre ese modelo.
    modelos = [
        ("Restando CEDI y PUNTOS", "Valorizado Ult Costo",           "Valorizado Promedio",           "Cantidad a Pedir"),
        ("Solo restando CEDI",     "Valorizado Ult Costo sin CEDI",  "Valorizado Promedio sin CEDI",  "Cantidad a Pedir sin CEDI"),
        ("Solo restando PUNTOS",   "Valorizado Ult Costo sin PUNTOS","Valorizado Promedio sin PUNTOS","Cantidad a Pedir sin PUNTOS"),
    ]

    tarjetas = []
    proveedores = []   # una tabla de proveedores por modelo, en el mismo orden que las tarjetas
    for titulo, col_ult, col_prom, col_und in modelos:
        tarjetas.append({
            "titulo": titulo,
            "ult": f"{df[col_ult].sum():,.0f}",
            "prom": f"{df[col_prom].sum():,.0f}",
            "und": f"{int(df[col_und].sum()):,}",
        })
        top = (df.groupby("Proveedor")
               .agg(costo=(col_ult, "sum"), unidades=(col_und, "sum"))
               .sort_values("costo", ascending=False))
        top = top[top["costo"] > 0]   # ocultar proveedores sin compra en este modelo
        proveedores.append([
            {"Proveedor": prov,
             "costo": f"{fila.costo:,.0f}",
             "unidades": f"{int(fila.unidades):,}"}
            for prov, fila in top.iterrows()
        ])
    download_id = uuid.uuid4().hex
    resultados[download_id] = {
        "excel": buffer.getvalue(),
        "tarjetas": tarjetas,
        "proveedores": proveedores,
    }
    # No dejar crecer la memoria sin limite: descartar los dashboards mas viejos.
    while len(resultados) > MAX_RESULTADOS:
        resultados.pop(next(iter(resultados)))
    return JSONResponse({"id": download_id})

@app.get("/dashboard/{download_id}")
def dashboard(request: Request, download_id: str):
    data = resultados.get(download_id)
    if data is None:
        return templates.TemplateResponse(request, "index.html", {
            "error": "Ese dashboard ya no está disponible (se reinició el servidor). Genera la proyección de nuevo."
        })
    return templates.TemplateResponse(request, "resultado.html", {
        "tarjetas": data["tarjetas"],
        "proveedores": data["proveedores"],
        "download_id": download_id,
    })
@app.get("/descargar/{download_id}")
def descargar(download_id: str):
    data = resultados.get(download_id)
    if data is None:
        return JSONResponse({"error": "Archivo no disponible. Genera la proyección de nuevo."}, status_code=404)
    return StreamingResponse(
        io.BytesIO(data["excel"]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Proyeccion-{date.today():%Y-%m-%d}.xlsx"'},

    )