import io
from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.templating import Jinja2Templates
from datetime import date
from fastapi.responses import StreamingResponse, JSONResponse
from Scripts.main import cargar_datos, exportar_excel, leer_con_encabezado, leer_csv_pipe
from Scripts.processor import ProyeccionProcessor
from fastapi.staticfiles import StaticFiles
import uuid
import pandas as pd
from Scripts import db, abastecimiento


app = FastAPI()
resultados = {}
MAX_RESULTADOS = 20   # dashboards guardados en memoria; al pasarse se descartan los mas viejos
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def _excel_response(df, filename):
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
@app.post("/generar")
def generar(request: Request,
        maestro: UploadFile | None = File(None),
        dispensacion: UploadFile | None = File(None),
        remisiones: UploadFile | None = File(None),
        stock_bodega: UploadFile | None = File(None),
        stock_puntos: UploadFile | None= File(None),
        moleculas: UploadFile | None = File(None),
        pend_disp: UploadFile | None = File(None),
        pend_com: UploadFile | None = File(None),
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
        return templates.TemplateResponse(request, "proyeccion.html", {
            "error": "Faltan estos archivos: " + ", ".join(faltantes),
        })
    cobertura_dias_DISP = {"A": cob_disp_a, "M": cob_disp_m, "B": cob_disp_b}
    cobertura_dias_REM = {"A": cob_rem_a, "M": cob_rem_m, "B": cob_rem_b}
    try:
        datos = cargar_datos(
            maestro.file, dispensacion.file, remisiones.file, stock_bodega.file,
            stock_puntos.file, moleculas.file,
            pend_disp.file if pend_disp and pend_disp.filename else None,
            pend_com.file if pend_com and pend_com.filename else None,
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
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": "No se pudo generar la proyeccion. Revisa que los archivos sean "
                                      "correctos y con el mismo rango de meses. (" + str(e) + ")"},
                            status_code=400)

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
        top = (df.groupby("Nombre Ult Proveedor")
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
        return templates.TemplateResponse(request, "proyeccion.html", {
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

@app.post("/abastecimiento/reparto")
def abastecimiento_reparto(
        consumo: UploadFile | None = File(None),
        cedi: UploadFile | None = File(None),
        proyeccion: UploadFile | None = File(None),
        transito: UploadFile | None = File(None),
        maestro: UploadFile | None = File(None),
        cto_fomag: UploadFile | None = File(None),):

    faltantes = [n for n, f in {"consumo": consumo, "cedi": cedi, "proyeccion": proyeccion,
                                "transito": transito, "maestro": maestro, 'cto_fomag': cto_fomag}.items()
                 if f is None or not f.filename]
    if faltantes:
        return JSONResponse({"error": "Faltan archivos: " + ", ".join(faltantes)}, status_code=400)
    try:
        df_consumo = pd.read_excel(consumo.file)
        df_cedi = leer_con_encabezado(cedi.file, 'Codigo Articulo')
        df_todo = pd.read_excel(proyeccion.file, sheet_name='Todo REST CEDI', skiprows=1)
        df_transito = leer_con_encabezado(transito.file, 'Codigo')
        df_maestro = leer_con_encabezado(maestro.file, 'Codigo')
        df_fomag = leer_csv_pipe(cto_fomag.file, 'Código Articulo', cols=['Nro. Contrato',
                                                                          'Código Articulo', 'Estado Referencia', 'Codigo Padre', 'Código Cum.1'])
        comerciales = abastecimiento.medicamentos_comerciales(df_maestro)
        mol_map = abastecimiento.molecula_por_codigo(df_todo)
        stock_cedi = abastecimiento.stock_cedi_desde_archivo(df_cedi)
        pedidos = abastecimiento.pedidos_canal_desde_proyeccion(df_todo)
        codigos_fomag = abastecimiento.codigos_fomag_desde_archivo(df_fomag, df_maestro, comerciales)
        trans = abastecimiento.transito_desde_archivo(df_transito)
        info = abastecimiento.info_producto_desde_maestro(df_maestro)

        buffer = io.BytesIO()
        abastecimiento.generar_abastecimiento(df_consumo, stock_cedi, pedidos,
                                              codigos_fomag, trans, info, buffer, mol_map, df_cedi, comerciales)
        buffer.seek(0)
    except Exception as e:
        return JSONResponse({"error": "No se pudo generar el reparto. Revisa que los archivos sean el Consumo, "
                                      "Valorizado CEDI, Proyección, Tránsito, Maestro y Contrato FOMAG. (" + str(e) + ")"},
                            status_code=400)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Abastecimiento-{date.today():%Y-%m-%d}.xlsx"'},
    )
@app.get("/compras")
def compras_pagina(request: Request):
    return templates.TemplateResponse(request, "compras.html", {"seccion":"compras"})
@app.get("/inventarios")
def inventarios_pagina(request: Request):
    return templates.TemplateResponse(request, "inventarios.html", {"seccion":"inventarios"})
@app.get("/abastecimiento/consumo")
def abastecimiento_consumo(desde: str, hasta: str):
    df = db.consultar_abastecimiento(desde, hasta)
    return _excel_response(df, "Consumo_Abastecimiento.xlsx")
@app.get("/abastecimiento")
def abastecimiento_pagina(request: Request):
    return templates.TemplateResponse(request, "abastecimiento_consumo.html", {"seccion": "inventarios"})
@app.get("/rotacion/dispensacion")
def rotacion_dispensacion(desde: str, hasta: str):
    df = db.consultar_dispensacion(desde, hasta)
    return _excel_response(df, "Rotacion_Dispensacion.xlsx")
@app.get("/rotacion/remisiones")
def rotacion_remisiones(desde: str, hasta: str):
    df = db.consultar_remisiones(desde, hasta)
    return _excel_response(df, "Rotacion_remisiones.xlsx")
@app.get("/reparto")
def reparto_pagina(request: Request):
    return templates.TemplateResponse(request, "reparto.html", {"seccion": "inventarios"})
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html")

@app.get("/proyeccion")
def proyeccion(request: Request):
    return templates.TemplateResponse(request, "proyeccion.html", {"seccion": "compras"})

@app.get("/consumos")
def consumos(request: Request):
    return templates.TemplateResponse(request, "consumos.html", {"seccion": "compras"})

@app.get("/rotacion/periodos")
def rotacion_periodos():
    return JSONResponse(db.periodos_cargados())