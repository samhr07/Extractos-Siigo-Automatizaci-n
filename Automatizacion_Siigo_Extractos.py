import os
import time
import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ============================================================
# 1. CONFIGURACIÓN DE CREDENCIALES (COMPLETAR AQUÍ)
# ============================================================

# --- BANCOLOMBIA ---
BANCOLOMBIA_USUARIO = ""  # <-- Coloca tu usuario de la Sucursal Virtual Personas
BANCOLOMBIA_CLAVE = ""  # <-- Coloca tu contraseña de la Sucursal Virtual Personas
BANCOLOMBIA_NUMERO_CUENTA = ""  # <-- Número de cuenta (opcional, para filtrar)

# --- NU (NUBANK) ---
NU_CORREO = ""  # <-- Correo registrado en Nu
NU_CLAVE = ""  # <-- Clave de acceso a la app/web de Nu
NU_NUMERO_TARJETA = ""  # <-- Número de tarjeta o cuenta (si aplica)

# --- CONFIGURACIÓN GENERAL ---
CARPETA_DESCARGA = "./extractos_descargados"  # Carpeta donde se guardarán los PDFs
HEADLESS = False  # True = sin ventana visible (para servidores), False = visible (para depuración)
TIMEOUT = 60000  # Tiempo de espera máximo en milisegundos (60 segundos)

# Crear carpeta de descargas si no existe
os.makedirs(CARPETA_DESCARGA, exist_ok=True)

# ============================================================
# 2. FUNCIÓN PARA DESCARGAR EXTRACTO DE BANCOLOMBIA
# ============================================================


def descargar_extracto_bancolombia(mes: int, año: int, formato: str = "pdf"):
    """
    Descarga el extracto de Bancolombia para el mes y año especificados.

    Args:
        mes (int): Número del mes (1-12)
        año (int): Año (ej. 2026)
        formato (str): 'pdf' o 'excel' (si está disponible)

    Returns:
        str: Ruta del archivo descargado, o None si falló.
    """
    print(f"[*] Iniciando descarga de extracto Bancolombia - {mes:02d}/{año}")

    with sync_playwright() as p:
        # Lanzar navegador (Chromium)
        browser = p.chromium.launch(headless=HEADLESS, args=["--start-maximized"])
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()

        try:
            # --- PASO 1: Ir a la Sucursal Virtual Personas ---
            page.goto("https://www.bancolombia.com/personas", timeout=TIMEOUT)
            page.wait_for_load_state("networkidle")

            # --- PASO 2: Hacer clic en "Iniciar sesión" ---
            # (El selector puede cambiar, ajustar según sea necesario)
            page.click("text=Iniciar sesión")
            page.wait_for_load_state("networkidle")

            # --- PASO 3: Ingresar usuario y clave ---
            # Esperar a que cargue el formulario de login
            page.wait_for_selector("#usuario", timeout=TIMEOUT)
            page.fill("#usuario", BANCOLOMBIA_USUARIO)
            page.fill("#password", BANCOLOMBIA_CLAVE)

            # --- PASO 4: Enviar formulario ---
            page.click("#login-button")
            page.wait_for_load_state("networkidle")

            # --- PASO 5: Navegar a la sección de extractos ---
            # Puede variar según la interfaz; estos son selectores típicos
            # Intentar con diferentes opciones
            try:
                page.click("text=Extractos")
            except:
                try:
                    page.click("text=Documentos")
                    page.click("text=Extractos")
                except:
                    page.goto("https://www.bancolombia.com/personas/extractos")

            page.wait_for_load_state("networkidle")

            # --- PASO 6: Seleccionar mes y año ---
            # Seleccionar el mes
            page.select_option("#mes", str(mes))
            # Seleccionar el año
            page.select_option("#anio", str(año))

            # Si hay que seleccionar cuenta específica
            if BANCOLOMBIA_NUMERO_CUENTA:
                try:
                    page.select_option("#cuenta", BANCOLOMBIA_NUMERO_CUENTA)
                except:
                    pass  # Si no se requiere, continuar

            # --- PASO 7: Descargar el extracto ---
            # Esperar a que el botón de descarga esté disponible
            page.wait_for_selector("#descargar", timeout=TIMEOUT)

            # Configurar la descarga
            with page.expect_download() as download_info:
                page.click("#descargar")

            download = download_info.value
            # Guardar el archivo en la carpeta destino
            extension = "pdf" if formato == "pdf" else "xlsx"
            nombre_archivo = f"Bancolombia_{año}_{mes:02d}.{extension}"
            ruta_destino = os.path.join(CARPETA_DESCARGA, nombre_archivo)
            download.save_as(ruta_destino)

            print(f"[+] Extracto de Bancolombia descargado: {ruta_destino}")
            browser.close()
            return ruta_destino

        except PlaywrightTimeoutError as e:
            print(f"[-] Error de tiempo de espera en Bancolombia: {e}")
            browser.close()
            return None
        except Exception as e:
            print(f"[-] Error inesperado en Bancolombia: {e}")
            browser.close()
            return None


# ============================================================
# 3. FUNCIÓN PARA DESCARGAR EXTRACTO DE NU (NUBANK)
# ============================================================


def descargar_extracto_nu(mes: int, año: int):
    """
    Descarga el extracto de Nu para el mes y año especificados.

    NOTA: Nu NO tiene una API pública para descarga automatizada de extractos.
    Esta función intenta acceder a la versión web de Nu y descargar el PDF.
    Si falla, se recomienda usar la exportación manual desde la app.

    Args:
        mes (int): Número del mes (1-12)
        año (int): Año (ej. 2026)

    Returns:
        str: Ruta del archivo descargado, o None si falló.
    """
    print(f"[*] Iniciando descarga de extracto Nu - {mes:02d}/{año}")
    print(
        "[!] Advertencia: Nu no tiene API pública. La descarga automatizada puede fallar."
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--start-maximized"])
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()

        try:
            # --- PASO 1: Ir al portal web de Nu ---
            page.goto("https://www.nu.com.co/", timeout=TIMEOUT)
            page.wait_for_load_state("networkidle")

            # --- PASO 2: Buscar el enlace de inicio de sesión ---
            # Nu redirige a la app o a la web según el dispositivo
            # Intentar encontrar el botón de "Ingresar"
            try:
                page.click("text=Ingresar")
            except:
                try:
                    page.click("text=Iniciar sesión")
                except:
                    # Si no se encuentra, intentar ir directamente a la URL de login
                    page.goto("https://www.nu.com.co/login")

            page.wait_for_load_state("networkidle")

            # --- PASO 3: Ingresar correo y clave ---
            page.wait_for_selector("input[type='email']", timeout=TIMEOUT)
            page.fill("input[type='email']", NU_CORREO)
            page.fill("input[type='password']", NU_CLAVE)

            # --- PASO 4: Enviar formulario ---
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")

            # --- PASO 5: Navegar a extractos ---
            # La interfaz de Nu cambia frecuentemente. Estos son intentos genéricos.
            try:
                page.click("text=Extractos")
            except:
                try:
                    page.click("text=Movimientos")
                except:
                    page.goto("https://www.nu.com.co/extractos")

            page.wait_for_load_state("networkidle")

            # --- PASO 6: Seleccionar período ---
            # Nu suele tener un selector de mes/año
            try:
                page.select_option("#mes", str(mes))
                page.select_option("#anio", str(año))
            except:
                # Si no hay selectores, buscar botones de navegación
                pass

            # --- PASO 7: Descargar PDF ---
            # Buscar botón de descarga
            try:
                with page.expect_download() as download_info:
                    page.click("text=Descargar PDF")
                download = download_info.value
                nombre_archivo = f"Nu_{año}_{mes:02d}.pdf"
                ruta_destino = os.path.join(CARPETA_DESCARGA, nombre_archivo)
                download.save_as(ruta_destino)
                print(f"[+] Extracto de Nu descargado: {ruta_destino}")
                browser.close()
                return ruta_destino
            except:
                print("[-] No se encontró el botón de descarga PDF.")
                print(
                    "[!] Sugerencia: Exporta el extracto manualmente desde la app Nu."
                )
                browser.close()
                return None

        except PlaywrightTimeoutError as e:
            print(f"[-] Error de tiempo de espera en Nu: {e}")
            browser.close()
            return None
        except Exception as e:
            print(f"[-] Error inesperado en Nu: {e}")
            browser.close()
            return None


# ============================================================
# 4. FUNCIÓN PARA DESCARGAR EXTRACTO DE NEQUI (OPCIONAL)
# ============================================================


def descargar_extracto_nequi(mes: int, año: int):
    """
    Descarga el extracto de Nequi para el mes y año especificados.

    Nequi tiene una API B2B (Conecta Nequi) pero requiere credenciales corporativas.
    Esta función intenta usar la versión web.

    Args:
        mes (int): Número del mes (1-12)
        año (int): Año (ej. 2026)

    Returns:
        str: Ruta del archivo descargado, o None si falló.
    """
    print(f"[*] Iniciando descarga de extracto Nequi - {mes:02d}/{año}")
    print(
        "[!] Advertencia: Nequi no tiene API pública para consumidores. La descarga automatizada puede fallar."
    )

    # Nequi no tiene una interfaz web completa para consumidores (solo app móvil).
    # Esta función es un placeholder. Se recomienda usar la exportación manual
    # o el portal Conecta Nequi si se tienen credenciales B2B.

    print("[!] Nequi: La descarga automatizada no está disponible para consumidores.")
    print("[!] Sugerencia: Usa el portal 'Conecta Nequi' si tienes credenciales B2B,")
    print("    o descarga manualmente desde la app.")
    return None


# ============================================================
# 5. FUNCIÓN PRINCIPAL: DESCARGAR TODOS LOS EXTRACTOS
# ============================================================


def descargar_extractos(mes: int, año: int, bancos: list = None):
    """
    Descarga extractos de los bancos especificados para un mes y año dados.

    Args:
        mes (int): Número del mes (1-12)
        año (int): Año (ej. 2026)
        bancos (list): Lista de bancos a descargar ['Bancolombia', 'Nu', 'Nequi']
                       Si es None, descarga todos.

    Returns:
        dict: Diccionario con las rutas de los archivos descargados.
    """
    if bancos is None:
        bancos = ["Bancolombia", "Nu", "Nequi"]

    resultados = {}

    if "Bancolombia" in bancos:
        ruta = descargar_extracto_bancolombia(mes, año)
        resultados["Bancolombia"] = ruta

    if "Nu" in bancos:
        ruta = descargar_extracto_nu(mes, año)
        resultados["Nu"] = ruta

    if "Nequi" in bancos:
        ruta = descargar_extracto_nequi(mes, año)
        resultados["Nequi"] = ruta

    return resultados


# ============================================================
# 6. EJEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    # --- CONFIGURAR CREDENCIALES (COMPLETAR ANTES DE EJECUTAR) ---
    BANCOLOMBIA_USUARIO = "tu_usuario"  # <-- COMPLETAR
    BANCOLOMBIA_CLAVE = "tu_clave"  # <-- COMPLETAR
    NU_CORREO = "tu_correo@ejemplo.com"  # <-- COMPLETAR
    NU_CLAVE = "tu_clave_nu"  # <-- COMPLETAR

    # --- EJECUTAR DESCARGA ---
    mes_actual = 7
    año_actual = 2026

    print("=" * 60)
    print("AUTOMATIZACIÓN DE DESCARGA DE EXTRACTOS BANCARIOS")
    print("=" * 60)

    # Descargar extractos
    resultados = descargar_extractos(mes_actual, año_actual, ["Bancolombia", "Nu"])

    # Mostrar resultados
    print("\n" + "=" * 60)
    print("RESULTADOS DE LA DESCARGA")
    print("=" * 60)
    for banco, ruta in resultados.items():
        if ruta:
            print(f"✅ {banco}: {ruta}")
        else:
            print(f"❌ {banco}: Falló la descarga")
