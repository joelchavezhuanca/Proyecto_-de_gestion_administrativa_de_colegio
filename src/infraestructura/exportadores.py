"""Exportadores de datos tabulares para PBI-13 (listas de asistencia).

Funciones exportadas
--------------------
* ``exportar_csv_bytes``   → CSV UTF-8-sig (BOM para Excel en Windows).
* ``exportar_xlsx_bytes``  → XLSX mediante ``openpyxl`` (ver dependencia abajo).
* ``exportar_texto_boleta_o_pdf`` → texto plano estructurado como boleta/reporte,
  sin dependencias del sistema operativo; compatible con CI en Ubuntu y Windows.

Seguridad (RN-05 — Formula Injection)
--------------------------------------
Cualquier celda de texto que comience por ``=``, ``+``, ``-`` o ``@`` se
prefija con ``'`` (apóstrofo) antes de emitirse a CSV o XLSX, neutralizando
la inyección de fórmulas en Excel / LibreOffice Calc.

Dependencia opcional
---------------------
``openpyxl >= 3.1`` debe estar declarada en ``requirements.txt`` para que
``exportar_xlsx_bytes`` funcione.  Si el paquete no está instalado, la función
lanza ``ImportError`` con un mensaje descriptivo.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from typing import Any

# Caracteres de inicio que activan Formula Injection en hojas de cálculo.
_PREFIJOS_PELIGROSOS = ("=", "+", "-", "@")


# ---------------------------------------------------------------------------
# Sanitización anti Formula Injection (RN-05)
# ---------------------------------------------------------------------------


def _sanitizar(valor: Any) -> str:
    """Convierte *valor* a cadena y neutraliza prefijos peligrosos.

    Si la representación textual comienza por ``=``, ``+``, ``-`` o ``@``
    se antepone ``'`` para evitar que hojas de cálculo lo interpreten como
    una fórmula.
    """
    texto = str(valor) if valor is not None else ""
    if texto and texto[0] in _PREFIJOS_PELIGROSOS:
        return f"'{texto}"
    return texto


# ---------------------------------------------------------------------------
# CSV con BOM UTF-8-sig (RN-03)
# ---------------------------------------------------------------------------


def exportar_csv_bytes(
    encabezados: Sequence[str],
    filas: Sequence[Sequence[object]],
) -> bytes:
    """Genera un CSV en codificación ``utf-8-sig`` (BOM para Excel en Windows).

    Parámetros
    ----------
    encabezados:
        Nombres de las columnas.
    filas:
        Secuencia de filas; cada fila es una secuencia de valores.

    Devuelve
    --------
    ``bytes`` con el contenido del CSV listo para ser servido como descarga.

    Ejemplo
    -------
    ::

        datos = exportar_csv_bytes(
            encabezados=["Nombre", "Estado"],
            filas=[["Juan Pérez", "PUNTUAL"]],
        )
        Path("asistencia.csv").write_bytes(datos)
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\r\n")
    escritor.writerow([_sanitizar(h) for h in encabezados])
    for fila in filas:
        escritor.writerow([_sanitizar(v) for v in fila])
    return buffer.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------------
# XLSX mediante openpyxl (RN-03)
# ---------------------------------------------------------------------------


def exportar_xlsx_bytes(
    encabezados: Sequence[str],
    filas: Sequence[Sequence[object]],
) -> bytes:
    """Genera un archivo XLSX usando ``openpyxl``.

    Requiere ``openpyxl >= 3.1`` instalado.  Si no está disponible lanza
    ``ImportError`` con instrucciones para agregarlo a ``requirements.txt``.

    Parámetros
    ----------
    encabezados:
        Nombres de las columnas (primera fila, en negrita).
    filas:
        Secuencia de filas de datos.

    Devuelve
    --------
    ``bytes`` con el contenido XLSX listo para ser servido como descarga.

    Dependencia
    -----------
    Agrega ``openpyxl>=3.1`` en ``requirements.txt`` del proyecto::

        openpyxl>=3.1
    """
    try:
        import openpyxl  # noqa: PLC0415
        from openpyxl.styles import Font  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "exportar_xlsx_bytes requiere 'openpyxl>=3.1'. "
            "Agrégala en requirements.txt: openpyxl>=3.1"
        ) from exc

    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Asistencia"  # type: ignore[union-attr]

    # Encabezados en negrita con sanitización.
    cabecera_sanitizada = [_sanitizar(h) for h in encabezados]
    hoja.append(cabecera_sanitizada)  # type: ignore[union-attr]
    negrita = Font(bold=True)
    for celda in hoja[1]:  # type: ignore[index]
        celda.font = negrita

    # Filas de datos.
    for fila in filas:
        hoja.append([_sanitizar(v) for v in fila])  # type: ignore[union-attr]

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Boleta / reporte en texto plano (ligero, sin deps del SO)
# ---------------------------------------------------------------------------


def exportar_texto_boleta_o_pdf(
    titulo: str,
    encabezados: Sequence[str],
    filas: Sequence[Sequence[object]],
    metadatos: dict[str, str] | None = None,
) -> bytes:
    """Genera un reporte en texto plano estructurado como boleta.

    Diseñado para ser ligero y sin dependencias del sistema operativo:
    funciona igual en Ubuntu y Windows sin instalar nada adicional.
    El texto resultante puede imprimirse directamente, enviarse por correo
    o convertirse a PDF con cualquier herramienta externa.

    Parámetros
    ----------
    titulo:
        Título del reporte (ej.: "Lista de Asistencia — Primaria 3ro A").
    encabezados:
        Nombres de las columnas.
    filas:
        Secuencia de filas de datos.
    metadatos:
        Diccionario opcional con pares clave/valor para el encabezado del
        documento (usuario exportador, fecha, filtros aplicados, etc.).

    Devuelve
    --------
    ``bytes`` UTF-8 con el reporte de texto.

    Ejemplo de salida
    -----------------
    ::

        ============================================================
        Lista de Asistencia — Primaria 3ro A
        ============================================================
        Usuario : admin
        Fecha   : 2026-11-26
        ============================================================
        Nombre              | Estado    | Fecha
        --------------------+-----------+----------
        Juan Pérez          | PUNTUAL   | 02/11/2026
        ============================================================
        Total de filas: 1
    """
    ancho = 70
    separador = "=" * ancho
    lineas: list[str] = []

    # Título y metadatos.
    lineas.append(separador)
    lineas.append(titulo)
    lineas.append(separador)

    if metadatos:
        ancho_clave = max((len(k) for k in metadatos), default=8)
        for clave, valor in metadatos.items():
            lineas.append(f"{clave:<{ancho_clave}} : {valor}")
        lineas.append(separador)

    if not encabezados:
        lineas.append("(sin datos)")
    else:
        # Calcular anchos de columna.
        anchos_col = [len(str(h)) for h in encabezados]
        for fila in filas:
            for i, v in enumerate(fila):
                if i < len(anchos_col):
                    anchos_col[i] = max(anchos_col[i], len(str(v) if v is not None else ""))

        def _formatear_fila(valores: Sequence[object]) -> str:
            partes = []
            for i, col_ancho in enumerate(anchos_col):
                v = str(valores[i]) if i < len(valores) and valores[i] is not None else ""
                partes.append(f"{v:<{col_ancho}}")
            return " | ".join(partes)

        # Fila de encabezados.
        lineas.append(_formatear_fila(encabezados))
        divisor = "-+-".join("-" * a for a in anchos_col)
        lineas.append(divisor)

        # Filas de datos.
        for fila in filas:
            lineas.append(_formatear_fila(fila))

    lineas.append(separador)
    lineas.append(f"Total de filas: {len(filas)}")

    return "\n".join(lineas).encode("utf-8")
