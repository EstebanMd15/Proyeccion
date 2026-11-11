import uuid
from datetime import datetime, date, timedelta
from Scripts import config, sheets
import gspread
import pandas as pd
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/calidad")
templates = Jinja2Templates(directory="templates")

def evaluar(valor, rango):
    if valor is None:
        return "N/A"
    if valor < rango['min'] or valor > rango['max']:
        return "CRITICO"
    if valor <= rango['alerta_min'] or valor >= rango['alerta_max']:
        return "PREVENTIVO"
    return "CONFORME"

def estado_general(estados):
    if "CRITICO" in estados:
        return "CRITICO"
    if "PREVENTIVO" in estados:
        return "PREVENTIVO"
    return "CONFORME"

def jornada_actual(ahora):
    hora = ahora.time()
    for nombre, (inicio, fin) in config.CALIDAD_JORNADAS.items():
        if inicio <= hora <= fin:
            return nombre
    return None

def _o_na(valor):
    return "N/A" if valor is None else valor

def armar_lectura(datos, ahora):
    rangos = config.CALIDAD_RANGOS
    es_frio = datos["zona"] in config.CALIDAD_ZONAS_FRIO

    # 1) Evaluar cada medida según el tipo de zona
    if es_frio:
        cumple_nevera = evaluar(datos["temp_nevera"], rangos["nevera"])
        cumple_ambiente = "N/A"
        cumple_humedad = "N/A"
    else:
        cumple_nevera = "N/A"
        cumple_ambiente = evaluar(datos["temp_ambiente"], rangos["ambiente"])
        cumple_humedad = evaluar(datos["humedad"], rangos["humedad"])

    # 2) Estado general con los tres resultados
    estado = estado_general([cumple_nevera, cumple_ambiente, cumple_humedad])

    # 3) Diccionario con los nombres EXACTOS de los encabezados de BD_LECTURAS
    return {
        "ID": uuid.uuid4().hex[:8].upper(),
        "Código de Bodega": datos["codigo_bodega"],
        "Punto de Dispensación": config.CALIDAD_BODEGAS.get(datos["codigo_bodega"], ""),
        "Jornada": jornada_actual(ahora) or "Fuera de Horario",
        "Fecha": ahora.strftime("%Y-%m-%d"),
        "Hora": ahora.strftime("%H:%M"),
        "Zona": datos["zona"],
        "Municipio": "",
        "Responsable (Toma)": datos["responsable_toma"],
        "Responsable (Verifica)": datos["responsable_verifica"],
        "Temp. Nevera (°C)": _o_na(datos["temp_nevera"]) if es_frio else "N/A",
        "Temp. Ambiente (°C)": "N/A" if es_frio else _o_na(datos["temp_ambiente"]),
        "Humedad (%)": "N/A" if es_frio else _o_na(datos["humedad"]),
        "Cumple Nevera": cumple_nevera,
        "Cumple Ambiente": cumple_ambiente,
        "Cumple Humedad": cumple_humedad,
        "Estado": estado,
        "Verificación": datos["verificacion"],
        "Observaciones / Acciones correctivas": datos["observaciones"] or "N/A",
    }

def validar(codigo_bodega, zona, temp_nevera, temp_ambiente, humedad, ahora):
    if codigo_bodega not in config.CALIDAD_BODEGAS:
        return "El código de bodega no existe"
    if zona not in config.CALIDAD_ZONAS:
        return "Zona no válida"
    if zona in config.CALIDAD_ZONAS_FRIO:
        if temp_nevera is None:
            return "Para nevera / cuarto frío debe ingresar la temperatura."
    else:
        if temp_ambiente is None or humedad is None:
            return "Debe ingresar la temperatura ambiente y la humedad."
    if config.CALIDAD_VALIDAR_HORARIO and jornada_actual(ahora) is None:
        return "Fuera del horario de registro (9:00-10:00 y 15:00-16:00)."
    return None

def _pagina_registro(request, error=None, ok=None):
    return templates.TemplateResponse(request, "calidad_registro.html", {
        "seccion": "calidad",
        "zonas": config.CALIDAD_ZONAS,
        "bodegas": config.CALIDAD_BODEGAS,
        "error": error,
        "ok": ok,
        "zonas_frio": config.CALIDAD_ZONAS_FRIO,
        "rangos": config.CALIDAD_RANGOS,
    })

@router.get("/registro")
def registro_pagina(request: Request, ok: str | None = None):
    return _pagina_registro(request, ok=ok)

@router.post("/registro")
def registro_guardar(request: Request,
                     codigo_bodega:str = Form(...),
                     zona:str = Form(...),
                     temp_nevera: float | None = Form(None),
                     temp_ambiente: float | None = Form(None),
                     humedad: float | None = Form(None),
                     responsable_toma: str = Form(...),
                     responsable_verifica: str = Form(""),
                     verificacion:str = Form(""),
                     observaciones:str = Form("")):
    ahora = datetime.now()
    error = validar(codigo_bodega,zona,temp_nevera,temp_ambiente, humedad, ahora)
    if error:
        return _pagina_registro(request, error=error)

    lectura = armar_lectura({
        "codigo_bodega": codigo_bodega,
        "zona": zona,
        "temp_nevera": temp_nevera,
        "temp_ambiente": temp_ambiente,
        "humedad": humedad,
        "responsable_toma": responsable_toma,
        "responsable_verifica": responsable_verifica,
        "verificacion": verificacion,
        "observaciones": observaciones,
    }, ahora)
    try:
        sheets.agregar_lectura(lectura)
    except gspread.exceptions.APIError:
        return _pagina_registro(request, error="No se pudo guardar en Google Sheets, Intente de nuevo.")
    return RedirectResponse(f"/calidad/registro?ok={lectura['ID']}", status_code=303)

def resumen_dia(dia, equipos, hoy):
    filas = []
    for codigo, nombre in config.CALIDAD_BODEGAS.items():
        del_punto = dia[dia["Código de Bodega"] == codigo]
        fila = {"codigo": codigo, "punto": nombre}
        if equipos is None:
            fila["Equipos"] = "SIN DATOS"
        else:
            fila["Equipos"] = estado_equipos(equipos.get(fila["punto"]), hoy)
        for jornada in config.CALIDAD_JORNADAS:
            estados = del_punto.loc[del_punto["Jornada"] == jornada, "Estado"].tolist()
            fila[jornada] = estado_general(estados) if estados else "PENDIENTE"
        filas.append(fila)
    return filas

def contar(filas):
    conteo = {}
    for jornada in config.CALIDAD_JORNADAS:
        estados = [f[jornada] for f in filas]
        conteo[jornada] = {e: estados.count(e) for e in ("CONFORME", "PREVENTIVO", "CRITICO", "PENDIENTE")}
    return conteo

@router.get("/dashboard")
def dashboard(request: Request, fecha: date | None = None):
    fecha = fecha or date.today()
    error = None
    try:
        df = sheets.leer_lecturas()
    except gspread.exceptions.APIError:
        df = pd.DataFrame(columns=sheets._get_encabezados())
        df['Fecha'] = pd.to_datetime(df['Fecha'], format="%d/%m/%Y")
        error = "No se pudo leer Google Sheets, Intente de nuevo."
    dia = df[df["Fecha"].dt.date == fecha]
    try:
        df_eq = sheets.leer_equipos()
        equipos = {f["PUNTO DE SERVICIO"]: f for f in df_eq.to_dict("records")}
    except gspread.exceptions.APIError:
        equipos = None
        error = error or "No se pudo leer los equipos en Google Sheets."
    filas = resumen_dia(dia, equipos, fecha)
    alertas = dia[dia["Estado"] != "CONFORME"]

    return templates.TemplateResponse(request, "calidad_dashboard.html", {
        "seccion": "calidad",
        "fecha": fecha,
        "jornadas": list(config.CALIDAD_JORNADAS),
        "filas": filas,
        "conteo": contar(filas),
        "alertas": alertas.to_dict("records"),
        "error": error,
    })

def armar_equipos(codigo, form):
    """Form: datos del formularios. los campos se llaman ifual que los encabezados de la fila 2"""
    equipos = {"PUNTO DE SERVICIO": config.CALIDAD_BODEGAS[codigo]}
    registrado = False
    for tipo, cantidad in (("TERMOMETRO", config.CALIDAD_MAX_TERMOMETROS),
                           ("TERMOHIGRO", config.CALIDAD_MAX_TERMOHIGROMETROS)):
        for i in range(1, cantidad + 1):
            serie = form.get(f"{tipo}_SERIE_{i}", "").strip()
            calib = form.get(f"{tipo}_CALIB_{i}", "").strip()
            equipos[f"{tipo}_SERIE_{i}"] = serie or "N/R"
            equipos[f"{tipo}_CALIB_{i}"] = calib or "N/R"
            if serie:
                registrado = True
    equipos["REGISTRADO"] = "TRUE" if registrado else "FALSE"
    return equipos

def _para_formulario(fila):
    """Convierte una fila del sheet en valores para los <input>: 'N/A' = '' y fecha d/m/yyyy = yyyy/mm/dd."""
    valores = {}
    for clave, valor in fila.items():
        valor = str(valor)
        if valor == "N/R":
            valor = ""
        elif "_CALIB_" in clave and valor:
            fecha = pd.to_datetime(valor, format="%d/%m/%Y", errors="coerce")
            valor = "" if pd.isna(fecha) else fecha.strftime("%Y-%m-%d")
        valores[clave] = valor
    return valores

@router.get("/equipos")
def equipos_pagina(request: Request, codigo: str | None = None, ok: str | None = None):
    valores, registrado, error = {}, False, None
    if codigo in config.CALIDAD_BODEGAS:
        try:
            df = sheets.leer_equipos()
            del_punto = df[df["PUNTO DE SERVICIO"] == config.CALIDAD_BODEGAS[codigo]]
            if not del_punto.empty:
                fila = del_punto.iloc[0].to_dict()
                valores = _para_formulario(fila)
                registrado = str(fila.get("REGISTRADO")).upper() == "TRUE"
        except gspread.exceptions.APIError:
            error = "No se pudo leer Google Sheets, Intente de nuevo."
    return templates.TemplateResponse(request, "calidad_equipos.html", {
        "seccion": "calidad",
        "bodegas": config.CALIDAD_BODEGAS,
        "codigo": codigo,
        "valores": valores,
        "registrado": registrado,
        "max_termometros": config.CALIDAD_MAX_TERMOMETROS,
        "max_termohigros": config.CALIDAD_MAX_TERMOHIGROMETROS,
        "ok": ok,
        "error": error,
    })

@router.post("/equipos")
async def equipos_guardar(request: Request):
    form = await request.form()
    codigo = form.get("codigo_bodega", "")
    if codigo not in config.CALIDAD_BODEGAS:
        return RedirectResponse("/calidad/equipos", status_code=303)
    try:
        sheets.guardar_equipos(armar_equipos(codigo, form))
    except gspread.exceptions.APIError:
        return RedirectResponse(f"/calidad/equipos?codigo={codigo}&ok=error", status_code=303)
    return RedirectResponse(f"/calidad/equipos?codigo={codigo}&ok=1", status_code=303)

def estado_equipos(fila, hoy):
    if not fila or str(fila.get("REGISTRADO")).upper() != "TRUE":
        return "SIN REGISTRO"
    estados = []
    for clave, serie in fila.items():
        if "_SERIE_" not in clave or str(serie) in ("", "N/R"):   # No es una serie o el equipo no existe
            continue
        calib = str(fila.get(clave.replace("_SERIE_", "_CALIB_"), ""))
        fecha = pd.to_datetime(calib, format="%d/%m/%Y", errors="coerce")
        if pd.isna(fecha):
            estados.append("VENCIDO")
            continue
        vence = fecha.date() + timedelta(days=config.CALIDAD_VIGENCIA_CALIBRACION_DIAS)
        if vence < hoy:
            estados.append("VENCIDO")
        elif (vence - hoy).days <= config.CALIDAD_AVISO_CALIBRACION_DIAS:
            estados.append("POR VENCER")
        else:
            estados.append("AL DIA")
    for e in ("VENCIDO", "POR VENCER"):
        if e in estados:
            return e
    return "AL DIA"