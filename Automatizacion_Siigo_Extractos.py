import time
import json
import os
from dataclasses import dataclass
from datetime import datetime


# 1. Recopilación de datos personales y parámetros fijos
@dataclass
class ConfiguracionAutomatizacion:
    # --- Credenciales Siigo ---
    siigo_username: str = ""  # Coloca aquí tu Usuario API Siigo
    siigo_access_key: str = ""  # Coloca aquí tu API Key (Access Key) de Siigo
    siigo_partner_id: str = "ScriptAutomatizacion"  # Coloca aquí el Partner-Id

    # --- Credenciales y Datos Bancarios ---
    nequi_numero: str = ""  # Coloca aquí tu número de Nequi
    nequi_clave: str = ""  # Coloca aquí tu clave de Nequi
    nu_numero: str = ""  # Coloca aquí tu número de cuenta/tarjeta Nu
    nu_clave: str = ""  # Coloca aquí tu clave de Nu
    bancolombia_numero: str = ""  # Coloca aquí tu número de cuenta Bancolombia
    bancolombia_usuario: str = (
        ""  # Coloca aquí tu usuario de la sucursal virtual Bancolombia
    )
    bancolombia_clave: str = ""  # Coloca aquí tu clave de Bancolombia

    # --- Parámetros de Control y Tiempos de Espera ---
    delay_bancos_segundos: int = (
        15  # Variable temporal de espera para peticiones a bancos (Scraping/API)
    )
    delay_siigo_segundos: int = 120  # Tiempo de espera (timeout) recomendado para Siigo
    directorio_pdfs: str = (
        "./extractos_manuales/"  # Carpeta donde se buscarán los PDFs en caso manual
    )


config = ConfiguracionAutomatizacion()


# 2. Definiciones de solicitud y procesamiento manual
def procesar_pdf_manual(entidad: str, fecha: str, config: ConfiguracionAutomatizacion):
    """
    Definición para introducir PDFs manualmente por fallo de sistema o elección del usuario.
    """
    print(
        f"[*] Iniciando procesamiento manual por PDF para {entidad} - Periodo: {fecha}"
    )
    ruta_archivo = os.path.join(config.directorio_pdfs, f"{entidad}_{fecha}.pdf")

    if not os.path.exists(ruta_archivo):
        return {
            "estado": "fallo",
            "motivo": f"Archivo no encontrado en {ruta_archivo}",
            "entidad": entidad,
        }

    # Aquí iría la lógica de extracción OCR o lectura de texto del PDF (ej. con pdfplumber)
    time.sleep(2)  # Simulando tiempo de lectura
    print(f"[+] PDF de {entidad} procesado con éxito.")

    return {
        "estado": "exito",
        "datos": [f"Movimientos extraidos de PDF de {entidad}"],
        "entidad": entidad,
    }


def solicitar_datos_bancarios(
    entidad: str, metodo: str, fecha: str, config: ConfiguracionAutomatizacion
):
    """
    Definición encargada de solicitar la información a los bancos respetando delays.
    """
    if metodo == "pdf":
        return procesar_pdf_manual(entidad, fecha, config)

    print(f"[*] Solicitando datos virtualmente a {entidad} para la fecha {fecha}...")
    # Respetando tiempos de espera para no saturar orígenes (Scraping o API)
    time.sleep(config.delay_bancos_segundos)

    # Aquí iría la lógica de requests o playwright según la entidad
    # Simularemos una respuesta exitosa
    print(f"[+] Datos virtuales de {entidad} obtenidos.")
    return {
        "estado": "exito",
        "datos": [f"Movimientos virtuales de {entidad}"],
        "entidad": entidad,
    }


def solicitar_datos_siigo(config: ConfiguracionAutomatizacion):
    """
    Definición para solicitar catálogos o validar conexión general con Siigo.
    """
    print(f"[*] Conectando con Siigo Nube usando usuario: {config.siigo_username}...")
    time.sleep(2)  # Delay temporal básico para conexión
    return True


# 3. Lógica principal de subida e informes
def generar_informe_txt(fallos: list, fecha: str):
    """
    Genera un informe TXT notificando qué extractos no se pudieron subir.
    """
    nombre_archivo = f"Informe_Fallos_Siigo_{fecha}.txt"
    with open(nombre_archivo, "w") as archivo:
        archivo.write(f"--- REPORTE DE FALLOS AUTOMATIZACIÓN {fecha} ---\n\n")
        if not fallos:
            archivo.write("Todos los extractos se subieron con éxito.\n")
        else:
            for fallo in fallos:
                archivo.write(
                    f"Entidad: {fallo['entidad']} | Motivo: {fallo['motivo']}\n"
                )
    print(f"[-] Reporte de fallos generado en: {nombre_archivo}")


def subir_a_siigo(resultados_bancos: list, config: ConfiguracionAutomatizacion):
    """
    Sube los extractos de forma automática a Siigo, previniendo duplicados.
    """
    fallos = []
    solicitar_datos_siigo(config)  # Verifica conexión

    for resultado in resultados_bancos:
        entidad = resultado["entidad"]

        if resultado["estado"] != "exito":
            fallos.append(resultado)
            continue

        print(f"[*] Preparando subida a Siigo para los datos de {entidad}...")

        # Generamos una Idempotency-Key única por mes y banco para evitar reinscribir extractos (Duplicidad)
        llave_idempotencia = f"{entidad}{fecha_formateada}X"

        try:
            # Aquí iría el request POST a la API de Siigo usando requests
            # headers = {"Idempotency-Key": llave_idempotencia, "Authorization": "Bearer ..."}
            # timeout = config.delay_siigo_segundos

            print(
                f"[+] Extracto de {entidad} inscrito con éxito en Siigo. (Llave Idempotencia: {llave_idempotencia})"
            )
        except Exception as e:
            fallos.append({"estado": "fallo", "motivo": str(e), "entidad": entidad})

    return fallos


# --- EJECUCIÓN PRINCIPAL DEL SCRIPT ---
if __name__ == "__main__":
    print("=== ASISTENTE DE AUTOMATIZACIÓN CONTABLE ===")

    # Variable fecha con formato YYYY-MM
    fecha_formateada = input(
        "Ingresa la fecha del extracto a solicitar (Formato YYYY-MM, ej. 2026-06): "
    ).strip()

    # Preguntas con IF para decidir el método de extracción (Virtual o PDF)
    metodo_bancolombia = (
        input("¿Solicitar Bancolombia de forma 'virtual' o por 'pdf'?: ")
        .strip()
        .lower()
    )
    metodo_nequi = (
        input("¿Solicitar Nequi de forma 'virtual' o por 'pdf'?: ").strip().lower()
    )

    # Nu se solicita por defecto en PDF al no tener API abierta documentada
    metodo_nu = "pdf"

    print("\nIniciando recolección de datos...")

    resultados = []

    # Condicionales de ejecución por entidad
    if metodo_bancolombia in ["virtual", "pdf"]:
        res_bc = solicitar_datos_bancarios(
            "Bancolombia", metodo_bancolombia, fecha_formateada, config
        )
        resultados.append(res_bc)

    if metodo_nequi in ["virtual", "pdf"]:
        res_nq = solicitar_datos_bancarios(
            "Nequi", metodo_nequi, fecha_formateada, config
        )
        resultados.append(res_nq)

    # Extracción de Nu
    res_nu = solicitar_datos_bancarios("Nu", metodo_nu, fecha_formateada, config)
    resultados.append(res_nu)

    print("\nIniciando sincronización con Siigo...")
    lista_de_fallos = subir_a_siigo(resultados, config)

    # Generar informe TXT final
    generar_informe_txt(lista_de_fallos, fecha_formateada)
    print("\nProceso finalizado.")
