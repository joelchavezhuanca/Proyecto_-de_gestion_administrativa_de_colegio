"""Casos de uso de la aplicación web.

Coordinan el dominio existente con los repositorios. No contienen SQL ni
reglas de negocio duplicadas: las decisiones (tardanzas, permisos, estados,
cierre) pertenecen a ``src/dominio``.
"""

import time as reloj
from datetime import date, datetime, time

from src.dominio.aforo import (
    CierreYaEjecutadoException,
    EventoCierreDiario,
    MetricasAforo,
    PermisoAforoException,
    ServicioAforo,
)
from src.dominio.asistencia import (
    Alumno,
    AsistenciaException,
    EstadoAsistencia,
    MetodoRegistro,
    ResultadoRegistroAsistencia,
    UsuarioOperador,
    registrar_asistencia_unificada,
    validar_formato_dni,
)
from src.dominio.asistencia import (
    RolUsuario as RolAsistencia,
)
from src.dominio.justificaciones import (
    CategoriaJustificacion,
    Justificacion,
    JustificacionException,
    ServicioJustificaciones,
)
from src.dominio.usuarios import (
    EstadoUsuario,
    RolUsuario,
    ServicioAutenticacionYPermisos,
    ServicioGestionUsuarios,
    SesionUsuario,
    Usuario,
    UsuarioException,
)
from src.infraestructura.repositorios import RepositorioColegio
from src.presentacion.tiempo import hora_institucional


class ServicioAplicacionColegio:
    """Fachada de casos de uso para Flask."""

    def __init__(self, repositorio: RepositorioColegio, reloj_institucional=hora_institucional):
        self.repo = repositorio
        self._reloj = reloj_institucional

    def ahora(self) -> datetime:
        return self._reloj()

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------
    def autenticar(self, username: str, password: str) -> SesionUsuario:
        usuarios = self.repo.listar_usuarios()
        return ServicioAutenticacionYPermisos.iniciar_sesion(
            username,
            password,
            usuarios,
            fecha_hora=self.ahora(),
        )

    # ------------------------------------------------------------------
    # Asistencia (PBI-01)
    # ------------------------------------------------------------------
    @staticmethod
    def _operador(usuario: Usuario) -> UsuarioOperador:
        return UsuarioOperador(
            id=usuario.id,
            username=usuario.username,
            rol=RolAsistencia(usuario.rol.value),
            activo=usuario.estado == EstadoUsuario.ACTIVO,
        )

    def _resolver_alumno(
        self,
        metodo: MetodoRegistro,
        identificador: str,
        alumno_id: int | None,
    ) -> tuple[Alumno | None, str | None, str | None]:
        identificador = (identificador or "").strip()
        if metodo == MetodoRegistro.CARNET:
            if not identificador:
                from src.dominio.asistencia import AlumnoNoEncontradoException

                raise AlumnoNoEncontradoException("Ingrese el código del carnet.")
            return self.repo.obtener_alumno_por_carnet(identificador), identificador, None

        if metodo == MetodoRegistro.MANUAL_DNI:
            validar_formato_dni(identificador)
            return self.repo.obtener_alumno_por_dni(identificador), None, identificador

        if metodo == MetodoRegistro.MANUAL_BUSQUEDA:
            if alumno_id is None:
                from src.dominio.asistencia import AlumnoNoEncontradoException

                raise AlumnoNoEncontradoException("Seleccione un alumno de la búsqueda.")
            return self.repo.obtener_alumno(alumno_id), None, None

        raise MetodoRegistroInvalido("El método de registro seleccionado no es válido.")

    def registrar_asistencia(
        self,
        usuario: Usuario,
        metodo: str,
        identificador: str = "",
        alumno_id: int | None = None,
        motivo: str | None = None,
    ) -> tuple[ResultadoRegistroAsistencia, int]:
        inicio = reloj.perf_counter()
        try:
            metodo_enum = MetodoRegistro(metodo)
        except ValueError as error:
            raise MetodoRegistroInvalido(
                "El método de registro seleccionado no es válido."
            ) from error

        operador = self._operador(usuario)
        alumno, codigo_carnet, dni_manual = self._resolver_alumno(
            metodo_enum, identificador, alumno_id
        )
        ahora = self.ahora()
        fecha_escolar = ahora.date()
        existente = (
            self.repo.obtener_asistencia(alumno.id, fecha_escolar)
            if alumno is not None
            else None
        )

        resultado = registrar_asistencia_unificada(
            operador=operador,
            alumno=alumno,
            metodo=metodo_enum,
            hora_servidor=ahora.time().replace(microsecond=0),
            fecha_escolar=fecha_escolar,
            asistencia_existente=existente,
            motivo_correccion=motivo,
            codigo_carnet=codigo_carnet,
            dni_manual=dni_manual,
            timestamp_servidor=ahora,
        )

        self.repo.guardar_asistencia(resultado.asistencia)
        evento = resultado.auditoria
        self.repo.registrar_auditoria(
            evento_id=evento.id,
            fecha_hora=evento.fecha_hora,
            usuario_id=evento.usuario_id,
            username=operador.username,
            rol=evento.rol.value,
            operacion=evento.operacion,
            entidad="ASISTENCIA",
            entidad_id=resultado.asistencia.id,
            detalle={
                "alumno_id": evento.alumno_id,
                "estado_anterior": evento.estado_anterior.value if evento.estado_anterior else None,
                "estado_nuevo": evento.estado_nuevo.value,
                "metodo": evento.metodo.value,
                "motivo": evento.motivo,
            },
        )
        milisegundos = int((reloj.perf_counter() - inicio) * 1000)
        return resultado, milisegundos

    def buscar_alumnos(self, criterio: str) -> list[Alumno]:
        return self.repo.buscar_alumnos(criterio)

    # ------------------------------------------------------------------
    # Dashboard de aforo (PBI-03)
    # ------------------------------------------------------------------
    def obtener_metricas(
        self,
        usuario: Usuario,
        fecha_escolar: date | None = None,
        nivel: str | None = None,
        grado: str | None = None,
        seccion: str | None = None,
    ) -> MetricasAforo:
        operador = self._operador(usuario)
        fecha = fecha_escolar or self.ahora().date()

        alumnos = self.repo.listar_alumnos()
        filtrados = [
            alumno
            for alumno in alumnos
            if (not nivel or alumno.nivel == nivel)
            and (not grado or alumno.grado == grado)
            and (not seccion or alumno.seccion == seccion)
        ]
        ids = {alumno.id for alumno in filtrados}
        asistencias = self.repo.listar_asistencias(fecha, estudiante_ids=ids)
        hora_cierre = self.repo.obtener_hora_cierre()

        return ServicioAforo.calcular_metricas(
            operador=operador,
            alumnos=filtrados,
            asistencias_dia=asistencias,
            fecha_escolar=fecha,
            hora_consulta=self.ahora().time().replace(microsecond=0),
            hora_cierre=hora_cierre,
        )

    def configurar_hora_cierre(self, usuario: Usuario, hora_texto: str) -> time:
        operador = self._operador(usuario)
        try:
            nueva_hora = time.fromisoformat(hora_texto)
        except ValueError as error:
            raise PermisoAforoException("La hora de cierre debe tener el formato HH:MM.") from error

        hora_validada = ServicioAforo.configurar_hora_cierre(operador, nueva_hora)
        self.repo.guardar_config("hora_cierre", hora_validada.strftime("%H:%M"))
        self.repo.registrar_auditoria(
            evento_id=f"aud-hora-{reloj.time_ns()}",
            fecha_hora=self.ahora(),
            usuario_id=usuario.id,
            username=usuario.username,
            rol=usuario.rol.value,
            operacion="CONFIGURAR_HORA_CIERRE",
            entidad="CONFIGURACION",
            entidad_id="hora_cierre",
            detalle={"hora_nueva": hora_validada.strftime("%H:%M")},
        )
        return hora_validada

    def ejecutar_cierre(
        self, usuario: Usuario, fecha_escolar: date | None = None
    ) -> EventoCierreDiario:
        operador = self._operador(usuario)
        # Decisión documentada: el cierre marca ausencias irreversibles y se
        # reserva al rol ADMIN, igual que la configuración de la hora (RN-17).
        if operador.rol != RolAsistencia.ADMIN:
            raise PermisoAforoException(
                "Únicamente el rol ADMIN puede ejecutar el cierre escolar diario."
            )

        fecha = fecha_escolar or self.ahora().date()
        if self.repo.existe_cierre(fecha):
            raise CierreYaEjecutadoException(
                f"El cierre de la jornada {fecha.isoformat()} ya fue ejecutado."
            )

        alumnos = self.repo.listar_alumnos()
        asistencias = self.repo.listar_asistencias(fecha)
        nuevas, evento = ServicioAforo.ejecutar_cierre_automatico(
            operador_o_sistema=operador,
            alumnos=alumnos,
            asistencias_existentes=asistencias,
            fecha_escolar=fecha,
            hora_cierre=self.repo.obtener_hora_cierre(),
        )
        for registro in nuevas:
            self.repo.guardar_asistencia(registro)

        self.repo.registrar_cierre(evento, ejecutado_por=usuario.id)
        self.repo.registrar_auditoria(
            evento_id=evento.id,
            fecha_hora=self.ahora(),
            usuario_id=usuario.id,
            username=usuario.username,
            rol=usuario.rol.value,
            operacion="CIERRE_ESCOLAR_DIARIO",
            entidad="CIERRE",
            entidad_id=fecha.isoformat(),
            detalle={
                "total_ausentes_marcados": evento.total_ausentes_marcados,
                "alumnos_ids": evento.alumnos_ids_afectados,
            },
        )
        return evento

    # ------------------------------------------------------------------
    # Justificaciones (PBI-04)
    # ------------------------------------------------------------------
    def listar_justificables(self, fecha: date) -> list[dict[str, object]]:
        alumnos = {alumno.id: alumno for alumno in self.repo.listar_alumnos()}
        asistencias = [
            asistencia
            for asistencia in self.repo.listar_asistencias(fecha)
            if asistencia.estado in (EstadoAsistencia.AUSENTE, EstadoAsistencia.TARDANZA)
        ]
        return [
            {
                "asistencia": asistencia,
                "alumno": alumnos.get(asistencia.alumno_id),
                "ya_justificada": self.repo.existe_justificacion_activa(asistencia.id),
            }
            for asistencia in asistencias
        ]

    def listar_justificaciones(self, fecha: date) -> list[dict[str, object]]:
        alumnos = {alumno.id: alumno for alumno in self.repo.listar_alumnos()}
        return [
            {"justificacion": justificacion, "alumno": alumnos.get(justificacion.alumno_id)}
            for justificacion in self.repo.listar_justificaciones(fecha)
        ]

    def registrar_justificacion(
        self,
        usuario: Usuario,
        asistencia_id: str,
        categoria: str,
        fecha_solicitud: date,
        motivo: str,
        documento_adjunto: str | None = None,
    ) -> Justificacion:
        operador = self._operador(usuario)
        motivo = (motivo or "").strip()
        if len(motivo) < 10:
            raise JustificacionException(
                "El motivo debe tener al menos 10 caracteres para sustentar la justificación."
            )

        asistencia = self.repo.obtener_asistencia_por_id(asistencia_id)
        if asistencia is None:
            raise JustificacionException("La asistencia seleccionada no existe.")

        alumno = self.repo.obtener_alumno(asistencia.alumno_id)
        if alumno is None:
            raise JustificacionException("El alumno asociado a la asistencia no existe.")

        periodo = self.repo.periodo_por_fecha(asistencia.fecha_escolar)
        if periodo is None:
            raise JustificacionException(
                "No existe un período académico configurado para la fecha de la asistencia."
            )

        try:
            categoria_enum = CategoriaJustificacion(categoria)
        except ValueError as error:
            raise JustificacionException("La categoría seleccionada no es válida.") from error

        resultado = ServicioJustificaciones.registrar_y_aprobar_justificacion(
            operador=operador,
            alumno=alumno,
            asistencia=asistencia,
            fecha_solicitud=fecha_solicitud,
            fecha_actual=self.ahora().date(),
            categoria=categoria_enum,
            motivo=motivo,
            periodo=periodo,
            documento_adjunto=documento_adjunto or None,
        )

        self.repo.insertar_justificacion(resultado.justificacion)
        self.repo.guardar_asistencia(resultado.asistencia_actualizada)
        self.repo.registrar_auditoria(
            evento_id=resultado.auditoria_id,
            fecha_hora=self.ahora(),
            usuario_id=usuario.id,
            username=usuario.username,
            rol=usuario.rol.value,
            operacion="REGISTRAR_JUSTIFICACION",
            entidad="JUSTIFICACION",
            entidad_id=resultado.justificacion.id,
            detalle={
                "asistencia_id": asistencia.id,
                "alumno_id": alumno.id,
                "categoria": categoria_enum.value,
                "estado_anterior": asistencia.estado.value,
                "estado_nuevo": EstadoAsistencia.JUSTIFICADO.value,
            },
        )
        return resultado.justificacion

    def anular_justificacion(self, usuario: Usuario, codigo: str) -> Justificacion:
        operador = self._operador(usuario)
        justificacion = self.repo.obtener_justificacion(codigo)
        if justificacion is None:
            raise JustificacionException("La justificación indicada no existe.")

        asistencia = self.repo.obtener_asistencia_por_id(justificacion.asistencia_id)
        if asistencia is None:
            raise JustificacionException("La asistencia asociada ya no existe.")

        restaurada = ServicioJustificaciones.anular_justificacion(
            operador=operador,
            justificacion=justificacion,
            asistencia=asistencia,
        )
        self.repo.guardar_asistencia(restaurada)
        self.repo.marcar_justificacion_anulada(codigo)
        self.repo.registrar_auditoria(
            evento_id=f"aud-anul-{reloj.time_ns()}",
            fecha_hora=self.ahora(),
            usuario_id=usuario.id,
            username=usuario.username,
            rol=usuario.rol.value,
            operacion="ANULAR_JUSTIFICACION",
            entidad="JUSTIFICACION",
            entidad_id=codigo,
            detalle={
                "asistencia_id": asistencia.id,
                "estado_restaurado": restaurada.estado.value,
            },
        )
        return justificacion

    # ------------------------------------------------------------------
    # Gestión de usuarios (PBI-02 / PBI-15)
    # ------------------------------------------------------------------
    def listar_usuarios(
        self,
        nombre: str | None = None,
        username: str | None = None,
        rol: str | None = None,
        estado: str | None = None,
    ) -> list[Usuario]:
        rol_enum = RolUsuario(rol) if rol else None
        estado_enum = EstadoUsuario(estado) if estado else None
        return ServicioGestionUsuarios.filtrar_usuarios(
            self.repo.listar_usuarios(),
            nombre=nombre or None,
            username=username or None,
            rol=rol_enum,
            estado=estado_enum,
        )

    @staticmethod
    def _validar_password_web(password: str) -> None:
        """Política de la interfaz (mínimo 8, letras y números)."""
        if not password or len(password) < 8:
            raise UsuarioException("La contraseña debe tener al menos 8 caracteres.")
        if password.isalpha() or password.isdigit():
            raise UsuarioException("La contraseña debe combinar letras y números.")

    def crear_usuario(
        self,
        admin: Usuario,
        username: str,
        password: str,
        nombre_completo: str,
        rol: str,
    ) -> Usuario:
        self._validar_password_web(password)
        try:
            rol_enum = RolUsuario(rol)
        except ValueError as error:
            raise UsuarioException("El rol seleccionado no es oficial.") from error

        nuevo, evento = ServicioGestionUsuarios.crear_usuario(
            operador=admin,
            username=username,
            password_plana=password,
            nombre_completo=nombre_completo,
            rol=rol_enum,
            usuarios_existentes=self.repo.listar_usuarios(),
            fecha_hora=self.ahora(),
        )
        creado = self.repo.insertar_usuario(nuevo)
        self.repo.registrar_auditoria(
            evento_id=evento.id,
            fecha_hora=evento.fecha_hora,
            usuario_id=evento.admin_id,
            username=evento.admin_username,
            rol=admin.rol.value,
            operacion=evento.operacion,
            entidad="USUARIO",
            entidad_id=str(creado.id),
            detalle=evento.detalle,
        )
        return creado

    def modificar_usuario(
        self,
        admin: Usuario,
        usuario_id: int,
        nombre_completo: str | None,
        rol: str | None,
    ) -> Usuario:
        target = self.repo.obtener_usuario(usuario_id)
        if target is None:
            raise UsuarioException("La cuenta indicada no existe.")
        try:
            rol_enum = RolUsuario(rol) if rol else None
        except ValueError as error:
            raise UsuarioException("El rol seleccionado no es oficial.") from error

        modificado, evento = ServicioGestionUsuarios.modificar_usuario(
            operador=admin,
            usuario_target=target,
            nuevo_nombre=nombre_completo,
            nuevo_rol=rol_enum,
            fecha_hora=self.ahora(),
        )
        actualizado = self.repo.actualizar_usuario(modificado)
        self.repo.registrar_auditoria(
            evento_id=evento.id,
            fecha_hora=evento.fecha_hora,
            usuario_id=evento.admin_id,
            username=evento.admin_username,
            rol=admin.rol.value,
            operacion=evento.operacion,
            entidad="USUARIO",
            entidad_id=str(usuario_id),
            detalle=evento.detalle,
        )
        return actualizado

    def cambiar_estado_usuario(self, admin: Usuario, usuario_id: int, nuevo_estado: str) -> Usuario:
        target = self.repo.obtener_usuario(usuario_id)
        if target is None:
            raise UsuarioException("La cuenta indicada no existe.")
        try:
            estado_enum = EstadoUsuario(nuevo_estado)
        except ValueError as error:
            raise UsuarioException("El estado seleccionado no es válido.") from error

        actualizado, evento = ServicioGestionUsuarios.cambiar_estado(
            operador=admin,
            usuario_target=target,
            nuevo_estado=estado_enum,
            fecha_hora=self.ahora(),
        )
        guardado = self.repo.actualizar_usuario(actualizado)
        self.repo.registrar_auditoria(
            evento_id=evento.id,
            fecha_hora=evento.fecha_hora,
            usuario_id=evento.admin_id,
            username=evento.admin_username,
            rol=admin.rol.value,
            operacion=evento.operacion,
            entidad="USUARIO",
            entidad_id=str(usuario_id),
            detalle=evento.detalle,
        )
        return guardado

    def restablecer_password(self, admin: Usuario, usuario_id: int, password: str) -> Usuario:
        self._validar_password_web(password)
        target = self.repo.obtener_usuario(usuario_id)
        if target is None:
            raise UsuarioException("La cuenta indicada no existe.")

        actualizado, evento = ServicioGestionUsuarios.restablecer_password(
            operador=admin,
            usuario_target=target,
            nueva_password_plana=password,
            fecha_hora=self.ahora(),
        )
        guardado = self.repo.actualizar_usuario(actualizado)
        self.repo.registrar_auditoria(
            evento_id=evento.id,
            fecha_hora=evento.fecha_hora,
            usuario_id=evento.admin_id,
            username=evento.admin_username,
            rol=admin.rol.value,
            operacion=evento.operacion,
            entidad="USUARIO",
            entidad_id=str(usuario_id),
            detalle=evento.detalle,
        )
        return guardado


class MetodoRegistroInvalido(AsistenciaException):
    """Entrada web inválida para el método de registro de asistencia."""
