import streamlit as st, io
from main import cargar_datos, exportar_excel
from processor import ProyeccionProcessor
from datetime import date
from config import *

st.set_page_config("Proyección Compras", layout="wide")
st.title("Proyección Compras")
st.caption("Pagina web para generar la Proyección de Compras.")

with st.form("proyeccion"):
    maestro =st.file_uploader(label="Archivo Maestro", type=["xlsx", "xls"])
    dispensacion =st.file_uploader(label="Archivo Dispensacion", type=["xlsx", "xls"])
    remisiones = st.file_uploader(label="Archivo Remisiones", type=["xlsx", "xls"])
    stock_bodega = st.file_uploader(label="Archivo Stock Bodega", type=["xlsx", "xls"])
    stock_puntos = st.file_uploader(label="Archivo Stock Puntos", type=["xlsx", "xls"])
    moleculas = st.file_uploader(label="Archivo Moleculas", type=["xlsx", "xls"])
    cols_disp, cols_rem = st.columns(2)

    with cols_disp:
        st.subheader("Dispensación")
        cobertura_disp_A = st.number_input("Cobertura A (Dias)", min_value=0, value=30, step=1, key="cobertura_disp_A")
        cobertura_disp_B = st.number_input("Cobertura B (Dias)", min_value=0, value=30, step=1, key="cobertura_disp_B")
        cobertura_disp_M = st.number_input("Cobertura M (Dias)", min_value=0, value=30, step=1, key="cobertura_disp_M")
        cobertura_lead_time_disp = st.number_input("Cobertura Lead Time (Dias)", min_value=0, value=15, step=1, key="cobertura_lead_time_disp")
        cobertura_dias_seguridad_disp = st.number_input("Cobertura Dias Seguridad", min_value=0, value=20, step=1, key="cobertura_dias_seguridad_disp")

    with cols_rem:
        st.subheader("Remisiones")
        cobertura_rem_A = st.number_input("Cobertura A (Dias)", min_value=0, value=30, step=1, key="cobertura_rem_A")
        cobertura_rem_B = st.number_input("Cobertura B (Dias)", min_value=0, value=30, step=1, key="cobertura_rem_B")
        cobertura_rem_M = st.number_input("Cobertura M (Dias)", min_value=0, value=30, step=1, key="cobertura_rem_M")
        cobertura_lead_time_rem = st.number_input("Cobertura Lead Time (Dias)", min_value=0, value=15, step=1, key="cobertura_lead_time_rem")
        cobertura_dias_seguridad_rem = st.number_input("Cobertura Dias Seguridad", min_value=0, value=20, step=1, key="cobertura_dias_seguridad_rem")

    umbral_a = st.number_input("Umbral A (%)", max_value=100, value=80, step=1)
    umbral_m = st.number_input("Umbral M (%)", max_value=100, value=95, step=1)

    enviado = st.form_submit_button("Generar Proyección")

if enviado:
    if not all([maestro, dispensacion, remisiones, stock_bodega, stock_puntos, moleculas]):
        st.error("No se cargó algunos de los archivos requeridos"); st.stop()
    cobertura_disp = {"A": cobertura_disp_A, "B": cobertura_disp_B, "M": cobertura_disp_M}
    cobertura_rem = {"A": cobertura_rem_A, "B": cobertura_rem_B, "M": cobertura_rem_M}

    with st.spinner("Procesando Proyección..."):
        datos = cargar_datos(maestro, dispensacion, remisiones, stock_bodega, stock_puntos, moleculas)
        proces = ProyeccionProcessor(*datos, cobertura_dias_DISP=cobertura_disp, cobertura_dias_REMI=cobertura_rem,
                                     lead_time_dias_DISP=cobertura_lead_time_disp, lead_time_dias_REMI=cobertura_lead_time_rem,
                                     dias_seguridad_DISP=cobertura_dias_seguridad_disp, dias_seguridad_REMI=cobertura_dias_seguridad_rem,
                                     umbral_A=umbral_a, umbral_M=umbral_m)
        proces.procesar()
        buffer = io.BytesIO()
        exportar_excel(proces, buffer=buffer)

    st.session_state['excel'] = buffer.getvalue()
    st.success("Proyección generada. Disponible para descarga")

if 'excel' in st.session_state:
    st.download_button(
        label="Descargar Excel",
        data=st.session_state['excel'],
        file_name=f"Proyección_{date.today():%Y-%m-%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )