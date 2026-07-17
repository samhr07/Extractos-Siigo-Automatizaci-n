import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from twilio.rest import Client


# ------------------------------------------------------------
# 1. CONFIGURACIÓN DE NOTIFICACIONES (con los datos proporcionados)
# ------------------------------------------------------------
class ConfiguracionNotificaciones:
    # --- EMAIL (Gmail) ---
    email_remitente: str = "samuelhoyos2007@gmail.com"  # Cambia por tu correo Gmail
    email_password: str = (
        "wijf ptwd aihv gphn"  # Contraseña de aplicación (16 caracteres)
    )
    email_destinatario: str = "henkabio.adm@gmail.com"  # Destinatario fijo
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    asunto_email: str = "Informe Código Contable"  # Asunto fijo

    # --- WHATSAPP (Twilio Sandbox) ---
    twilio_account_sid: str = (
        "US5bf4e21d162b0f4521a8436ea85bf530"  # User SID (el que compartiste)
    )
    twilio_auth_token: str = "07aa11afb99953d2d7f7250fab7790ae"  # Auth Token
    twilio_whatsapp_number: str = (
        "whatsapp:+14155238886"  # Número del sandbox de Twilio
    )
    # El destinatario debe estar registrado en el sandbox (enviar mensaje de unión)
    whatsapp_destinatario: str = "whatsapp:+573160470196"  # O +573502110083 (elige uno)

    # --- CONTROL DE ENVÍO ---
    enviar_email: bool = True
    enviar_whatsapp: bool = True


config_notif = ConfiguracionNotificaciones()


# ------------------------------------------------------------
# 2. FUNCIÓN PARA GENERAR DESCRIPCIÓN DE ERRORES (mejorada)
# ------------------------------------------------------------
def generar_descripcion_errores(errores: list, resumen: dict = None) -> str:
    """
    Genera un texto estructurado con la descripción de los errores ocurridos
    y un resumen de la ejecución.
    """
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not errores:
        return f"✅ Proceso completado sin errores.\n📅 Fecha: {ahora}"

    texto = "⚠️ SE DETECTARON ERRORES EN LA AUTOMATIZACIÓN\n"
    texto += "=" * 50 + "\n"
    texto += f"📅 Fecha: {ahora}\n"

    if resumen:
        texto += f"📊 Total transacciones procesadas: {resumen.get('total_movimientos', 'N/A')}\n"
        texto += f"✅ Conciliaciones exitosas: {resumen.get('conciliaciones_exitosas', 'N/A')}\n"
        texto += f"❌ Errores encontrados: {len(errores)}\n"

    texto += f"\n❌ DETALLE DE ERRORES:\n"
    texto += "-" * 40 + "\n"

    for i, error in enumerate(errores, 1):
        texto += f"\n{i}. {error.get('entidad', 'Desconocida')}\n"
        texto += f"   Motivo: {error.get('motivo', 'Sin descripción')}\n"
        if error.get("detalle"):
            texto += f"   Detalle: {error.get('detalle')}\n"

    return texto


# ------------------------------------------------------------
# 3. ENVÍO DE NOTIFICACIÓN POR EMAIL (Gmail)
# ------------------------------------------------------------
def enviar_email(asunto: str, cuerpo: str, config: ConfiguracionNotificaciones) -> bool:
    """
    Envía un correo electrónico usando Gmail SMTP.
    """
    if not config.enviar_email:
        return True

    try:
        # Crear mensaje
        msg = MIMEMultipart()
        msg["From"] = config.email_remitente
        msg["To"] = config.email_destinatario
        msg["Subject"] = asunto

        # Cuerpo del mensaje (texto plano)
        msg.attach(MIMEText(cuerpo, "plain"))

        # Conectar al servidor SMTP de Gmail
        with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
            server.starttls()  # Habilitar TLS
            server.login(config.email_remitente, config.email_password)
            server.send_message(msg)

        print(f"📧 Email enviado a {config.email_destinatario}")
        return True
    except Exception as e:
        print(f"❌ Error enviando email: {e}")
        return False


# ------------------------------------------------------------
# 4. ENVÍO DE NOTIFICACIÓN POR WHATSAPP (Twilio Sandbox)
# ------------------------------------------------------------
def enviar_whatsapp(mensaje: str, config: ConfiguracionNotificaciones) -> bool:
    """
    Envía un mensaje por WhatsApp usando el sandbox de Twilio.
    """
    if not config.enviar_whatsapp:
        return True

    try:
        client = Client(config.twilio_account_sid, config.twilio_auth_token)
        message = client.messages.create(
            body=mensaje[:1600],  # Twilio tiene límite de caracteres
            from_=config.twilio_whatsapp_number,
            to=config.whatsapp_destinatario,
        )
        print(
            f"💬 WhatsApp enviado a {config.whatsapp_destinatario} (SID: {message.sid})"
        )
        return True
    except Exception as e:
        print(f"❌ Error enviando WhatsApp: {e}")
        return False


# ------------------------------------------------------------
# 5. FUNCIÓN PRINCIPAL DE NOTIFICACIÓN (UNIFICADA)
# ------------------------------------------------------------
def enviar_notificacion(
    errores: list, resumen: dict = None, config: ConfiguracionNotificaciones = None
) -> dict:
    """
    Envía notificaciones por email (Gmail) y WhatsApp (Twilio) con el reporte de ejecución.
    Retorna un diccionario con el estado de cada envío.
    """
    if config is None:
        config = config_notif

    # Generar el cuerpo del mensaje
    cuerpo = generar_descripcion_errores(errores, resumen)

    # Añadir cabecera con información del proceso
    cuerpo_completo = "📋 REPORTE DE AUTOMATIZACIÓN CONTABLE\n"
    cuerpo_completo += "=" * 40 + "\n"
    cuerpo_completo += cuerpo

    resultados = {"email": False, "whatsapp": False}

    # Enviar email (con asunto fijo)
    if config.enviar_email:
        resultados["email"] = enviar_email(config.asunto_email, cuerpo_completo, config)

    # Enviar WhatsApp (con el mismo contenido, pero acortado si es necesario)
    if config.enviar_whatsapp:
        # Truncar a 1600 caracteres para WhatsApp
        mensaje_whatsapp = cuerpo_completo[:1600]
        resultados["whatsapp"] = enviar_whatsapp(mensaje_whatsapp, config)

    return resultados


# ------------------------------------------------------------
# 6. EJEMPLO DE USO (INTEGRADO CON TU CÓDIGO EXISTENTE)
# ------------------------------------------------------------
if __name__ == "__main__":
    # Simulación de errores y resumen
    errores_ejemplo = [
        {
            "entidad": "Bancolombia",
            "motivo": "Timeout en la conexión",
            "detalle": "La API no respondió en 120s",
        },
        {
            "entidad": "Nu",
            "motivo": "Archivo PDF no encontrado",
            "detalle": "No existe extracto_Nu_2026-07.pdf",
        },
    ]
    resumen_ejemplo = {"total_movimientos": 45, "conciliaciones_exitosas": 43}

    # Enviar notificaciones
    estado = enviar_notificacion(errores_ejemplo, resumen_ejemplo)
    print(f"\n📬 Estado de envíos: {estado}")
