from fastapi.responses import StreamingResponse
import io

def respuesta_excel(contenido, nombre):
    return StreamingResponse(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition":f'attachment; filename="{nombre}"'})

def respuesta_excel_df(df, nombre):
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return respuesta_excel(buffer, nombre)