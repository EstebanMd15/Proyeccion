from fastapi import APIRouter, Request
from Scripts.comun.plantillas import templates

router = APIRouter()

@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html")

@router.get("/compras")
def compras_pagina(request: Request):
    return templates.TemplateResponse(request, "compras.html", {"seccion":"compras"})

@router.get("/inventarios")
def inventarios_pagina(request: Request):
    return templates.TemplateResponse(request, "inventarios.html", {"seccion":"inventarios"})