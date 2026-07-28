"""
OBSOLETO - conservado solo por compatibilidad.

La logica de la V2 (rotacion por volumen de consumo) ya quedo integrada en
processor.ProyeccionProcessor y es el comportamiento por defecto.

Usa directamente:
    from processor import ProyeccionProcessor
    p = ProyeccionProcessor(...)                          # volumen (default)
    p = ProyeccionProcessor(..., criterio_rotacion='formulas')  # legacy

Este archivo se puede borrar.
"""
from processor import ProyeccionProcessor


class ProyeccionProcessorV2(ProyeccionProcessor):
    """Alias historico: ProyeccionProcessor ya usa el criterio de volumen."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('criterio_rotacion', 'volumen')
        super().__init__(*args, **kwargs)
