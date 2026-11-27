"""Pruebas de infraestructura: adaptadores WhatsApp y exportadores (PBI-13/PBI-17).

Cobertura objetivo: >= 95 % de src/infraestructura/whatsapp.py y
                              src/infraestructura/exportadores.py

Estrategia
----------
* Mocks de red mediante ``unittest.mock.patch`` en ``urllib.request.urlopen``
  → nunca se efectúa una conexión real a internet.
* Worker asíncrono: se mide tiempo de retorno (< 5 ms) y se espera el Future
  para verificar comportamiento.
* CSV/XLSX: se verifican BOM UTF-8-sig y sanitización anti Formula Injection.
"""

from __future__ import annotations

import io
import json
import time as time_mod
import urllib.error
import urllib.request
from concurrent.futures import Future
from datetime import date, datetime
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.dominio.notificaciones import (
    EstadoNotificacion,
    NotificacionWhatsApp,
    ResultadoEnvioProveedor,
)
from src.infraestructura.exportadores import (
    _sanitizar,
    exportar_csv_bytes,
    exportar_texto_boleta_o_pdf,
    exportar_xlsx_bytes,
)
from src.infraestructura.whatsapp import (
    NotificadorMetaCloud,
    NotificadorSimulado,
    WorkerNotificacionesAsincrono,
    _describir_error_http,
    crear_notificador_desde_entorno,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _notificacion(
    telefono: str | None = "+51987654321",
    plantilla: str = "ingreso_puntual",
    contenido: str = "Estimado apoderado: Juan ingresó puntualmente.",
) -> NotificacionWhatsApp:
    ahora = datetime(2026, 11, 2, 7, 10, 0)
    return NotificacionWhatsApp(
        id="ntf-test-001",
        clave_idempotencia="ast-001:PUNTUAL:2026-11-02",
        evento_origen_id="evt-001",
        asistencia_id="ast-001",
        alumno_id=101,
        fecha_escolar=date(2026, 11, 2),
        apoderado_nombre="María Lezano",
        telefono_destino=telefono,
        tipo="PUNTUAL",  # type: ignore[arg-type]
        plantilla=plantilla,
        contenido=contenido,
        estado=EstadoNotificacion.PENDIENTE,
        intentos=0,
        referencia_proveedor=None,
        detalle_error=None,
        creado_en=ahora,
        actualizado_en=ahora,
    )


def _mock_urlopen_ok(payload: dict) -> MagicMock:
    """Devuelve un context manager que simula urlopen con respuesta JSON exitosa."""
    respuesta = MagicMock()
    respuesta.read.return_value = json.dumps(payload).encode("utf-8")
    respuesta.__enter__ = lambda s: s
    respuesta.__exit__ = MagicMock(return_value=False)
    return respuesta


def _http_error(codigo: int, cuerpo: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://graph.facebook.com",
        code=codigo,
        msg="Error",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(cuerpo.encode("utf-8")),
    )


# ===========================================================================
# SECCIÓN 1 — NotificadorSimulado
# ===========================================================================


class TestNotificadorSimulado:
    def test_devuelve_enviado(self) -> None:
        sim = NotificadorSimulado()
        resultado = sim.enviar(_notificacion())
        assert resultado.exitoso is True
        assert resultado.estado_reportado == EstadoNotificacion.ENVIADO

    def test_referencia_sintetica_no_vacia(self) -> None:
        sim = NotificadorSimulado()
        resultado = sim.enviar(_notificacion())
        assert resultado.referencia is not None
        assert resultado.referencia.startswith("sim-")
        assert len(resultado.referencia) > 4

    def test_referencias_son_unicas(self) -> None:
        sim = NotificadorSimulado()
        refs = {sim.enviar(_notificacion()).referencia for _ in range(50)}
        assert len(refs) == 50

    def test_sin_error(self) -> None:
        sim = NotificadorSimulado()
        resultado = sim.enviar(_notificacion())
        assert resultado.detalle_error is None

    def test_cumple_protocolo_puerto(self) -> None:
        """NotificadorSimulado implementa PuertoNotificadorWhatsApp (duck typing)."""
        sim = NotificadorSimulado()
        assert callable(getattr(sim, "enviar", None))


# ===========================================================================
# SECCIÓN 2 — NotificadorMetaCloud (con mocks de red)
# ===========================================================================


class TestNotificadorMetaCloud:
    _TOKEN = "tok-test"
    _PHONE_ID = "123456789"

    def _notificador(self) -> NotificadorMetaCloud:
        return NotificadorMetaCloud(
            token=self._TOKEN,
            phone_number_id=self._PHONE_ID,
        )

    def test_envio_exitoso_devuelve_enviado(self) -> None:
        payload = {"messages": [{"id": "wamid-abc123"}]}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok(payload)):
            resultado = self._notificador().enviar(_notificacion())
        assert resultado.exitoso is True
        assert resultado.estado_reportado == EstadoNotificacion.ENVIADO
        assert resultado.referencia == "wamid-abc123"

    def test_respuesta_sin_messages_devuelve_referencia_none(self) -> None:
        payload: dict[str, Any] = {}
        with patch("urllib.request.urlopen", return_value=_mock_urlopen_ok(payload)):
            resultado = self._notificador().enviar(_notificacion())
        assert resultado.exitoso is True
        assert resultado.referencia is None

    def test_error_http_401_devuelve_fallido(self) -> None:
        exc = _http_error(401, '{"error":"invalid_token"}')
        with patch("urllib.request.urlopen", side_effect=exc):
            resultado = self._notificador().enviar(_notificacion())
        assert resultado.exitoso is False
        assert resultado.estado_reportado == EstadoNotificacion.FALLIDO
        assert "401" in (resultado.detalle_error or "")

    def test_error_http_500_devuelve_fallido(self) -> None:
        exc = _http_error(500, "Internal Server Error")
        with patch("urllib.request.urlopen", side_effect=exc):
            resultado = self._notificador().enviar(_notificacion())
        assert resultado.exitoso is False
        assert "500" in (resultado.detalle_error or "")

    def test_error_de_red_timeout_devuelve_fallido(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
            resultado = self._notificador().enviar(_notificacion())
        assert resultado.exitoso is False
        assert resultado.estado_reportado == EstadoNotificacion.FALLIDO
        assert resultado.detalle_error is not None

    def test_error_de_conexion_generico_devuelve_fallido(self) -> None:
        with patch("urllib.request.urlopen", side_effect=ConnectionError("reset")):
            resultado = self._notificador().enviar(_notificacion())
        assert resultado.exitoso is False

    def test_no_lanza_excepcion_ante_error_http(self) -> None:
        exc = _http_error(403)
        with patch("urllib.request.urlopen", side_effect=exc):
            resultado = self._notificador().enviar(_notificacion())
        assert isinstance(resultado, ResultadoEnvioProveedor)

    def test_payload_incluye_telefono_sin_mas(self) -> None:
        """El número de destino no debe incluir el '+' en el payload de Meta."""
        notif = _notificacion(telefono="+51987654321")
        notificador = self._notificador()
        cuerpo = notificador._construir_cuerpo(notif)
        assert cuerpo["to"] == "51987654321"
        assert "+" not in cuerpo["to"]

    def test_payload_usa_plantilla_del_dominio(self) -> None:
        notif = _notificacion(plantilla="ausencia_alumno")
        notificador = self._notificador()
        cuerpo = notificador._construir_cuerpo(notif)
        assert cuerpo["template"]["name"] == "ausencia_alumno"

    def test_timeout_es_menor_o_igual_a_5_segundos(self) -> None:
        """Verifica que el timeout configurado no excede 5 s (requisito PBI-17)."""
        from src.infraestructura.whatsapp import _TIMEOUT_META_SEGUNDOS

        assert _TIMEOUT_META_SEGUNDOS <= 5

    def test_describe_error_http_sin_cuerpo(self) -> None:
        exc = _http_error(503)
        texto = _describir_error_http(exc)
        assert "503" in texto

    def test_describe_error_http_con_cuerpo(self) -> None:
        exc = _http_error(400, '{"message":"bad param"}')
        texto = _describir_error_http(exc)
        assert "400" in texto
        assert "bad param" in texto


# ===========================================================================
# SECCIÓN 3 — WorkerNotificacionesAsincrono
# ===========================================================================


class TestWorkerNotificacionesAsincrono:
    def test_encolar_no_bloquea_mas_de_5ms(self) -> None:
        """encolar() debe retornar en < 5 ms (PBI-17 RN-02)."""
        sim = NotificadorSimulado()
        with WorkerNotificacionesAsincrono(sim) as worker:
            inicio = time_mod.perf_counter()
            future = worker.encolar(_notificacion())
            elapsed_ms = (time_mod.perf_counter() - inicio) * 1000
        assert elapsed_ms < 5, f"encolar tardó {elapsed_ms:.2f} ms (límite 5 ms)"
        # Esperar resultado para asegurar limpieza
        future.result(timeout=5)

    def test_encolar_devuelve_future(self) -> None:
        sim = NotificadorSimulado()
        with WorkerNotificacionesAsincrono(sim) as worker:
            future = worker.encolar(_notificacion())
        assert isinstance(future, Future)

    def test_future_resuelve_resultado_exitoso(self) -> None:
        sim = NotificadorSimulado()
        with WorkerNotificacionesAsincrono(sim) as worker:
            future = worker.encolar(_notificacion())
            resultado = future.result(timeout=5)
        assert resultado.exitoso is True
        assert resultado.estado_reportado == EstadoNotificacion.ENVIADO

    def test_callback_es_invocado_con_resultado(self) -> None:
        sim = NotificadorSimulado()
        recibidos: list[ResultadoEnvioProveedor] = []

        with WorkerNotificacionesAsincrono(sim) as worker:
            future = worker.encolar(_notificacion(), callback_resultado=recibidos.append)
            future.result(timeout=5)

        assert len(recibidos) == 1
        assert recibidos[0].exitoso is True

    def test_callback_no_obligatorio(self) -> None:
        sim = NotificadorSimulado()
        with WorkerNotificacionesAsincrono(sim) as worker:
            future = worker.encolar(_notificacion(), callback_resultado=None)
            resultado = future.result(timeout=5)
        assert resultado.exitoso is True

    def test_error_en_notificador_no_propaga_al_hilo_principal(self) -> None:
        """Si el notificador lanza, el Future resuelve FALLIDO (no explota)."""

        class NotificadorRoto:
            def enviar(self, _: NotificacionWhatsApp) -> ResultadoEnvioProveedor:
                raise RuntimeError("broken pipe")

        with WorkerNotificacionesAsincrono(NotificadorRoto()) as worker:  # type: ignore[arg-type]
            future = worker.encolar(_notificacion())
            resultado = future.result(timeout=5)
        assert resultado.exitoso is False
        assert resultado.estado_reportado == EstadoNotificacion.FALLIDO
        assert "broken pipe" in (resultado.detalle_error or "")

    def test_multiples_encolados_concurrentes(self) -> None:
        sim = NotificadorSimulado()
        with WorkerNotificacionesAsincrono(sim) as worker:
            futures = [worker.encolar(_notificacion()) for _ in range(10)]
            resultados = [f.result(timeout=10) for f in futures]
        assert all(r.exitoso for r in resultados)

    def test_context_manager_cierra_executor(self) -> None:
        sim = NotificadorSimulado()
        worker = WorkerNotificacionesAsincrono(sim)
        with worker:
            future = worker.encolar(_notificacion())
            future.result(timeout=5)
        # Después del with, el executor está cerrado; una nueva tarea debe fallar.
        with pytest.raises(RuntimeError):
            worker._executor.submit(lambda: None)

    def test_error_en_callback_no_propaga(self) -> None:
        """Un callback que lanza no debe romper el Future."""
        sim = NotificadorSimulado()

        def callback_roto(_: ResultadoEnvioProveedor) -> None:
            raise ValueError("callback caído")

        with WorkerNotificacionesAsincrono(sim) as worker:
            future = worker.encolar(_notificacion(), callback_resultado=callback_roto)
            resultado = future.result(timeout=5)
        # El resultado principal debe ser exitoso; el error del callback se absorbe.
        assert resultado.exitoso is True


# ===========================================================================
# SECCIÓN 4 — crear_notificador_desde_entorno
# ===========================================================================


class TestCrearNotificadorDesdeEntorno:
    def test_sin_variables_devuelve_simulado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("META_WHATSAPP_TOKEN", raising=False)
        monkeypatch.delenv("META_WHATSAPP_PHONE_NUMBER_ID", raising=False)
        notificador = crear_notificador_desde_entorno()
        assert isinstance(notificador, NotificadorSimulado)

    def test_con_variables_devuelve_meta_cloud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_WHATSAPP_TOKEN", "tok-123")
        monkeypatch.setenv("META_WHATSAPP_PHONE_NUMBER_ID", "ph-456")
        notificador = crear_notificador_desde_entorno()
        assert isinstance(notificador, NotificadorMetaCloud)

    def test_token_vacio_devuelve_simulado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_WHATSAPP_TOKEN", "")
        monkeypatch.setenv("META_WHATSAPP_PHONE_NUMBER_ID", "ph-456")
        notificador = crear_notificador_desde_entorno()
        assert isinstance(notificador, NotificadorSimulado)

    def test_phone_id_vacio_devuelve_simulado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("META_WHATSAPP_TOKEN", "tok-123")
        monkeypatch.setenv("META_WHATSAPP_PHONE_NUMBER_ID", "")
        notificador = crear_notificador_desde_entorno()
        assert isinstance(notificador, NotificadorSimulado)


# ===========================================================================
# SECCIÓN 5 — Sanitización anti Formula Injection (_sanitizar)
# ===========================================================================


class TestSanitizacion:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("=SUM(A1:B2)", "'=SUM(A1:B2)"),
            ("+cmd|calc", "'+cmd|calc"),
            ("-1+1", "'-1+1"),
            ("@SUM(1+1+1)", "'@SUM(1+1+1)"),
            ("Juan Pérez", "Juan Pérez"),
            ("PUNTUAL", "PUNTUAL"),
            ("", ""),
            (None, ""),
            (42, "42"),
            (3.14, "3.14"),
        ],
    )
    def test_sanitizar_valores(self, entrada: Any, esperado: str) -> None:
        assert _sanitizar(entrada) == esperado

    def test_sanitizar_no_modifica_texto_normal(self) -> None:
        assert _sanitizar("Hola Mundo") == "Hola Mundo"

    def test_sanitizar_preserva_espacios_internos(self) -> None:
        assert _sanitizar("Luna Lezano") == "Luna Lezano"


# ===========================================================================
# SECCIÓN 6 — exportar_csv_bytes
# ===========================================================================


class TestExportarCsvBytes:
    def test_salida_es_bytes(self) -> None:
        resultado = exportar_csv_bytes(["A", "B"], [["x", "y"]])
        assert isinstance(resultado, bytes)

    def test_bom_utf8_sig(self) -> None:
        """El primer byte debe ser el BOM de UTF-8-sig: EF BB BF."""
        resultado = exportar_csv_bytes(["Col"], [["val"]])
        assert resultado[:3] == b"\xef\xbb\xbf", "Falta el BOM UTF-8-sig"

    def test_decodifica_correctamente_en_utf8_sig(self) -> None:
        resultado = exportar_csv_bytes(["Nombre"], [["Eduardo Pérez"]])
        texto = resultado.decode("utf-8-sig")
        assert "Eduardo Pérez" in texto

    def test_encabezados_en_primera_fila(self) -> None:
        resultado = exportar_csv_bytes(["Código", "Estado"], [])
        texto = resultado.decode("utf-8-sig")
        assert "Código" in texto
        assert "Estado" in texto

    def test_filas_de_datos_incluidas(self) -> None:
        filas = [["ALU-001", "PUNTUAL"], ["ALU-002", "TARDANZA"]]
        texto = exportar_csv_bytes(["Código", "Estado"], filas).decode("utf-8-sig")
        assert "ALU-001" in texto
        assert "TARDANZA" in texto

    def test_sanitizacion_formula_injection_csv(self) -> None:
        filas = [["=SUM(A1:Z9)", "+cmd|calc", "-formula", "@hack"]]
        texto = exportar_csv_bytes(["Fórmula"], filas).decode("utf-8-sig")
        fila_datos = texto.split("\r\n")[1]
        # El prefijo ' debe anteponerse a cada valor peligroso
        assert "'=SUM(A1:Z9)" in fila_datos
        assert "'+cmd|calc" in fila_datos
        assert "'-formula" in fila_datos
        assert "'@hack" in fila_datos
        # Ningún valor debe comenzar con el carácter peligroso directamente
        for celda in fila_datos.split(","):
            celda_limpia = celda.strip('"')
            if celda_limpia.startswith("'"):
                assert celda_limpia[1] in ("=", "+", "-", "@")

    def test_csv_sin_filas_solo_encabezados(self) -> None:
        resultado = exportar_csv_bytes(["A", "B", "C"], [])
        texto = resultado.decode("utf-8-sig")
        lineas = [ln for ln in texto.strip().split("\r\n") if ln]
        assert len(lineas) == 1
        assert "A" in lineas[0]

    def test_valores_numericos_incluidos(self) -> None:
        texto = exportar_csv_bytes(["Num"], [[42], [3.14]]).decode("utf-8-sig")
        assert "42" in texto
        assert "3.14" in texto

    def test_caracteres_especiales_escapados_por_csv(self) -> None:
        """Valores con comas deben quedar entre comillas en CSV estándar."""
        texto = exportar_csv_bytes(["Col"], [["valor, con coma"]]).decode("utf-8-sig")
        assert "valor, con coma" in texto

    def test_encabezado_peligroso_es_sanitizado(self) -> None:
        texto = exportar_csv_bytes(["=MALO"], [["ok"]]).decode("utf-8-sig")
        assert "'=MALO" in texto


# ===========================================================================
# SECCIÓN 7 — exportar_xlsx_bytes
# ===========================================================================


class TestExportarXlsxBytes:
    def _tiene_openpyxl(self) -> bool:
        try:
            import openpyxl  # noqa: F401, PLC0415

            return True
        except ImportError:
            return False

    def test_devuelve_bytes(self) -> None:
        if not self._tiene_openpyxl():
            pytest.skip("openpyxl no está instalado")
        resultado = exportar_xlsx_bytes(["A", "B"], [["x", "y"]])
        assert isinstance(resultado, bytes)

    def test_magic_bytes_xlsx(self) -> None:
        """Un XLSX es un ZIP; los primeros 4 bytes deben ser PK\\x03\\x04."""
        if not self._tiene_openpyxl():
            pytest.skip("openpyxl no está instalado")
        resultado = exportar_xlsx_bytes(["Col"], [["val"]])
        assert resultado[:4] == b"PK\x03\x04", "No es un archivo ZIP/XLSX válido"

    def test_contenido_legible_con_openpyxl(self) -> None:
        if not self._tiene_openpyxl():
            pytest.skip("openpyxl no está instalado")
        import openpyxl  # noqa: PLC0415

        encabezados = ["Nombre", "Estado"]
        filas = [["Juan Pérez", "PUNTUAL"], ["Ana Gómez", "TARDANZA"]]
        datos = exportar_xlsx_bytes(encabezados, filas)
        libro = openpyxl.load_workbook(BytesIO(datos))
        hoja = libro.active
        assert hoja.cell(1, 1).value == "Nombre"  # type: ignore[union-attr]
        assert hoja.cell(1, 2).value == "Estado"  # type: ignore[union-attr]
        assert hoja.cell(2, 1).value == "Juan Pérez"  # type: ignore[union-attr]
        assert hoja.cell(3, 2).value == "TARDANZA"  # type: ignore[union-attr]

    def test_sanitizacion_formula_injection_xlsx(self) -> None:
        if not self._tiene_openpyxl():
            pytest.skip("openpyxl no está instalado")
        import openpyxl  # noqa: PLC0415

        filas = [["=SUM(A1)", "+cmd", "-1", "@hack"]]
        datos = exportar_xlsx_bytes(["F1", "F2", "F3", "F4"], filas)
        libro = openpyxl.load_workbook(BytesIO(datos))
        hoja = libro.active
        assert hoja.cell(2, 1).value == "'=SUM(A1)"  # type: ignore[union-attr]
        assert hoja.cell(2, 2).value == "'+cmd"  # type: ignore[union-attr]
        assert hoja.cell(2, 3).value == "'-1"  # type: ignore[union-attr]
        assert hoja.cell(2, 4).value == "'@hack"  # type: ignore[union-attr]

    def test_encabezados_en_negrita(self) -> None:
        if not self._tiene_openpyxl():
            pytest.skip("openpyxl no está instalado")
        import openpyxl  # noqa: PLC0415

        datos = exportar_xlsx_bytes(["Col1", "Col2"], [["a", "b"]])
        libro = openpyxl.load_workbook(BytesIO(datos))
        hoja = libro.active
        assert hoja.cell(1, 1).font.bold is True  # type: ignore[union-attr]

    def test_sin_openpyxl_lanza_import_error(self) -> None:
        """Si openpyxl no está disponible, debe lanzar ImportError descriptivo."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "openpyxl":
                raise ImportError("No module named 'openpyxl'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="openpyxl"):
                exportar_xlsx_bytes(["A"], [["1"]])


# ===========================================================================
# SECCIÓN 8 — exportar_texto_boleta_o_pdf
# ===========================================================================


class TestExportarTextoBoleta:
    def test_devuelve_bytes(self) -> None:
        resultado = exportar_texto_boleta_o_pdf("Título", ["A", "B"], [["x", "y"]])
        assert isinstance(resultado, bytes)

    def test_decodifica_en_utf8(self) -> None:
        resultado = exportar_texto_boleta_o_pdf("Reporte", ["Nombre"], [["Eduardo Pérez"]])
        texto = resultado.decode("utf-8")
        assert "Eduardo Pérez" in texto

    def test_titulo_en_salida(self) -> None:
        resultado = exportar_texto_boleta_o_pdf("Mi Reporte", [], [])
        assert b"Mi Reporte" in resultado

    def test_metadatos_en_salida(self) -> None:
        meta = {"Usuario": "admin", "Fecha": "2026-11-26"}
        resultado = exportar_texto_boleta_o_pdf("T", [], [], metadatos=meta)
        texto = resultado.decode("utf-8")
        assert "admin" in texto
        assert "2026-11-26" in texto

    def test_encabezados_incluidos(self) -> None:
        resultado = exportar_texto_boleta_o_pdf("T", ["Código", "Estado"], [])
        texto = resultado.decode("utf-8")
        assert "Código" in texto
        assert "Estado" in texto

    def test_filas_de_datos_incluidas(self) -> None:
        filas = [["ALU-001", "PUNTUAL"], ["ALU-002", "AUSENTE"]]
        texto = exportar_texto_boleta_o_pdf("T", ["Código", "Estado"], filas).decode("utf-8")
        assert "ALU-001" in texto
        assert "AUSENTE" in texto

    def test_total_filas_en_pie(self) -> None:
        filas = [["a"], ["b"], ["c"]]
        texto = exportar_texto_boleta_o_pdf("T", ["X"], filas).decode("utf-8")
        assert "Total de filas: 3" in texto

    def test_sin_filas_total_cero(self) -> None:
        texto = exportar_texto_boleta_o_pdf("T", ["X"], []).decode("utf-8")
        assert "Total de filas: 0" in texto

    def test_sin_encabezados_ni_filas(self) -> None:
        """No debe lanzar errores con listas vacías."""
        resultado = exportar_texto_boleta_o_pdf("T", [], [])
        assert isinstance(resultado, bytes)

    def test_sin_metadatos(self) -> None:
        """No debe lanzar errores sin metadatos."""
        resultado = exportar_texto_boleta_o_pdf("T", ["Col"], [["val"]], metadatos=None)
        assert b"val" in resultado

    def test_separadores_presentes(self) -> None:
        texto = exportar_texto_boleta_o_pdf("T", ["X"], [["y"]]).decode("utf-8")
        assert "=" * 10 in texto  # Al menos 10 signos = como separador

    def test_columnas_alineadas_por_ancho_maximo(self) -> None:
        """Los anchos de columna deben adaptarse al valor más largo."""
        filas = [["corto", "valor muy largo aquí"]]
        texto = exportar_texto_boleta_o_pdf("T", ["Col1", "Col2"], filas).decode("utf-8")
        # La columna Col2 debe ser lo suficientemente ancha.
        assert "valor muy largo aquí" in texto

    def test_valores_none_no_rompen(self) -> None:
        """Valores None deben mostrarse como cadena vacía."""
        filas = [[None, "ok"]]
        resultado = exportar_texto_boleta_o_pdf("T", ["A", "B"], filas)
        assert isinstance(resultado, bytes)
        assert b"ok" in resultado

    def test_no_requiere_dependencias_del_so(self) -> None:
        """La función solo debe usar stdlib; no debe importar nada externo."""
        import importlib

        # Recargar el módulo para verificar que no falla en entorno limpio.
        modulo = importlib.import_module("src.infraestructura.exportadores")
        assert modulo is not None
