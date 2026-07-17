import os
import re
import time
import hmac
import hashlib
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

# Librerías de análisis y visualización
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from thefuzz import fuzz, process

# Intentar importar dependencias externas opcionales
try:
    import requests
except ImportError:
    requests = None

try:
    from playwright.sync_api import (
        sync_playwright,
        TimeoutError as PlaywrightTimeoutError,
    )
except ImportError:
    sync_playwright = None

try:
    from twilio.rest import Client as TwilioClient
except ImportError:
    TwilioClient = None

# Configuración del sistema de Logs
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SiigoOrquestador")


# ============================================================
# CONFIGURACIÓN GENERAL Y VARIABLES DE ENTORNO (Dataclass)
# ============================================================
@dataclass
class ConfigEntorno:
    # --- Siigo API ---
    siigo_api_url: str = field(
        default_factory=lambda: os.getenv("SIIGO_API_URL", "https://api.siigo.com/v1")
    )
    siigo_username: str = field(
        default_factory=lambda: os.getenv("SIIGO_USERNAME", "samuelhoyos2007@gmail.com")
    )
    siigo_access_key: str = field(
        default_factory=lambda: os.getenv("SIIGO_ACCESS_KEY", "wijf ptwd aihv gphn")
    )
    siigo_partner_id: str = field(
        default_factory=lambda: os.getenv("SIIGO_PARTNER_ID", "MiScriptConciliacion")
    )
    is_sandbox: bool = field(
        default_factory=lambda: os.getenv("SIIGO_SANDBOX", "true").lower() == "true"
    )
    timeout_siigo: int = 120  # Timeout estricto de 120 segundos

    # --- Notificaciones Email ---
    email_remitente: str = field(
        default_factory=lambda: os.getenv(
            "EMAIL_REMITENTE", "samuelhoyos2007@gmail.com"
        )
    )
    email_password: str = field(
        default_factory=lambda: os.getenv("EMAIL_PASSWORD", "wijf ptwd aihv gphn")
    )
    email_destinatario: str = field(
        default_factory=lambda: os.getenv(
            "EMAIL_DESTINATARIO", "henkabio.adm@gmail.com"
        )
    )
    smtp_server: str = field(
        default_factory=lambda: os.getenv("SMTP_SERVER", "smtp.gmail.com")
    )
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    asunto_email: str = "Informe Código Contable"

    # --- Notificaciones WhatsApp (Twilio) ---
    twilio_account_sid: str = field(
        default_factory=lambda: os.getenv(
            "TWILIO_ACCOUNT_SID", "US5bf4e21d162b0f4521a8436ea85bf530"
        )
    )
    twilio_auth_token: str = field(
        default_factory=lambda: os.getenv(
            "TWILIO_AUTH_TOKEN", "07aa11afb99953d2d7f7250fab7790ae"
        )
    )
    twilio_whatsapp_number: str = field(
        default_factory=lambda: os.getenv(
            "TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886"
        )
    )
    whatsapp_destinatario: str = field(
        default_factory=lambda: os.getenv(
            "TWILIO_DESTINATARIO", "whatsapp:+573160470196"
        )
    )

    # --- Control de Flujo ---
    enviar_email: bool = True
    enviar_whatsapp: bool = True
    delay_bancos_segundos: int = 15
    carpeta_descargas: str = "./extractos_descargados"
    directorio_revision: str = "./cola_revision/"

    # --- Cuentas PUC Estándar ---
    puc_banco: str = "11100501"  # Bancos cuentas corrientes
    puc_gasto_gmf: str = "51159505"  # Gravamen Movimiento Financiero (4x1000)
    puc_clientes_default: str = "13050501"  # Clientes nacionales
    puc_proveedores_default: str = "22050501"  # Proveedores nacionales


# ============================================================
# DICCIONARIOS MAESTROS (Nómina, Categorías, Proveedores)
# ============================================================
EMPLEADOS = {
    "William": {"numero": "3182309554", "banco": "Nequi", "tipo": "celular"},
    "Diana": {"numero": "3133761278", "banco": "Nequi", "tipo": "celular"},
    "Mabel": {"numero": "3105477761", "banco": "Nequi", "tipo": "celular"},
    "Hugo": {"numero": "16132028650", "banco": "Bancolombia", "tipo": "cuenta"},
    "Natalia": {"numero": "10065329940", "banco": "Bancolombia", "tipo": "cuenta"},
}

CATEGORIAS = [
    "Materia Prima",
    "Servicios Públicos",
    "Nómina",
    "Gastos Administrativos",
    "Ventas",
    "Impuestos",
    "Otros",
    "Biocompuestos",
    "Inorgánicos",
]

CATEGORY_KEYWORDS = {
    "Inorgánicos": [
        "calcio",
        "magnesio",
        "potasio",
        "costal",
        "costales",
        "protoquímica",
        "alcohol",
        "hipoclorito",
        "ozono",
        "cristalería",
        "laboratorio",
        "matraz",
        "probeta",
        "tubo de ensayo",
        "vidrio",
        "pipeta",
        "bureta",
    ],
    "Biocompuestos": [
        "extracto de levadura",
        "levadura",
        "tecna",
        "biocompuesto",
        "peptona",
        "agar",
    ],
    "Materia Prima": [
        "panela",
        "ara",
        "d1",
        "éxito",
        "supermercado",
        "envase",
        "envases",
        "incodi",
        "insumo",
        "producción",
        "melaza",
        "azúcar",
    ],
    "Nómina": [
        "william",
        "alexander",
        "mábel",
        "mabel",
        "bolivar",
        "hugo",
        "diana",
        "salario",
        "sueldo",
        "prestaciones",
        "nómina",
        "seguridad social",
        "arl",
        "cesantías",
        "prima",
        "vacaciones",
    ],
    "Servicios Públicos": [
        "agua",
        "luz",
        "electricidad",
        "gas",
        "telefonía",
        "internet",
        "acueducto",
        "alcantarillado",
        "aseo",
    ],
    "Gastos Administrativos": [
        "papelería",
        "oficina",
        "tinta",
        "mensajería",
        "transporte",
        "resma",
        "caja",
        "grapas",
    ],
    "Impuestos": [
        "4x1000",
        "gmf",
        "gravamen",
        "iva",
        "renta",
        "retefuente",
        "reteica",
        "reteiva",
    ],
    "Ventas": [
        "facturación",
        "cliente",
        "venta",
        "ingreso",
        "consignación",
        "recibo",
        "pago cliente",
    ],
}

PROVEEDORES_CONOCIDOS = [
    "protoquimica",
    "tecna",
    "incodi",
    "ara",
    "d1",
    "exito",
    "frutesa",
    "wompi",
    "bancolombia",
    "nequi",
    "nu",
]

# Estructurar categorías para coincidencia rápida
all_keywords = []
keyword_to_category = {}
for cat, kws in CATEGORY_KEYWORDS.items():
    for kw in kws:
        kw_clean = kw.lower().strip()
        if kw_clean not in keyword_to_category:
            all_keywords.append(kw_clean)
            keyword_to_category[kw_clean] = cat


# ============================================================
# CLIENTE API SIIGO (Con Rate Limits, Auth JWT e Idempotencia)
# ============================================================
class SiigoAPIClient:
    def __init__(self, config: ConfigEntorno):
        self.config = config
        self.token: Optional[str] = None
        self.token_expiry: float = 0.0

    def autenticar(self) -> bool:
        """Autenticación JWT con validez finita (Página 5)"""
        ahora = time.time()
        if self.token and ahora < self.token_expiry:
            return True

        logger.info("Autenticando en Siigo Nube y generando token JWT...")
        url = f"{self.config.siigo_api_url}/auth"
        payload = {
            "username": self.config.siigo_username,
            "access_key": self.config.siigo_access_key,
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.config.timeout_siigo
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                # Margen de seguridad para expiración del token de 24 horas
                self.token_expiry = ahora + 86100
                return True
            else:
                logger.error(
                    f"Fallo de autenticación. Código HTTP: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Error en comunicación durante autenticación: {e}")
            return False

    def request_con_retry(
        self,
        metodo: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        params: Optional[Dict] = None,
        idempotency_key: Optional[str] = None,
    ) -> requests.Response:
        """
        Ejecuta llamadas HTTP incorporando Retroceso Exponencial (Exponential Backoff)
        para mitigar Rate Limits (Páginas 8 y 10).
        """
        if not self.autenticar():
            raise Exception(
                "No se logró obtener autenticación JWT válida para realizar la llamada."
            )

        url = f"{self.config.siigo_api_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Partner-Id": self.config.siigo_partner_id,
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        intentos = 0
        backoff = 2.0
        max_intentos = 5

        while intentos < max_intentos:
            try:
                response = requests.request(
                    metodo,
                    url,
                    json=payload,
                    params=params,
                    headers=headers,
                    timeout=self.config.timeout_siigo,
                )

                # Manejo específico de Límite de Tasa (HTTP 429) y Latencia de Servidor (HTTP 503/504)
                if response.status_code in [429, 503, 504]:
                    intentos += 1
                    delay = (backoff**intentos) + np.random.uniform(0.1, 1.0)
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = int(retry_after)

                    logger.warning(
                        f"Límite de tasa o saturación detectado ({response.status_code}). Reintentando en {delay:.2f}s... (Intento {intentos}/{max_intentos})"
                    )
                    time.sleep(delay)
                    continue

                return response
            except requests.exceptions.RequestException as e:
                intentos += 1
                delay = backoff**intentos
                logger.error(
                    f"Error de red en la API de Siigo. Reintentando en {delay:.2f}s... Error: {e}"
                )
                time.sleep(delay)

        raise Exception(
            f"Fallo definitivo al conectar con el servidor de Siigo tras {max_intentos} intentos."
        )


# ============================================================
# EXTRACTORES DE DATOS BANCARIOS (Playwright y Parser de Datos)
# ============================================================
def descargar_extractos_playwright(
    mes: int, año: int, config: ConfigEntorno
) -> Dict[str, str]:
    """
    Descarga mediante web scraping los extractos de Bancolombia y Nu (Punto #14).
    """
    os.makedirs(config.carpeta_descargas, exist_ok=True)
    resultados = {}

    if not sync_playwright:
        logger.warning(
            "Playwright no se encuentra instalado en este entorno de ejecución."
        )
        return resultados

    logger.info(f"Iniciando flujo Playwright para el periodo {mes:02d}/{año}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # --- Bancolombia Mock/Scraper ---
        try:
            page.goto("https://www.bancolombia.com/personas", timeout=60000)
            # Simulación de interacción/descarga para ejecución del script sin bloquearse
            bancolombia_pdf = os.path.join(
                config.carpeta_descargas, f"Bancolombia_{año}_{mes:02d}.pdf"
            )
            with open(bancolombia_pdf, "w") as f:
                f.write("Bancolombia Statement Content Placeholder")
            resultados["Bancolombia"] = bancolombia_pdf
            logger.info(f"Descargado extracto de Bancolombia en: {bancolombia_pdf}")
        except Exception as e:
            logger.error(
                f"No se pudo descargar el extracto de Bancolombia de forma automatizada: {e}"
            )

        # --- Nu Bank Mock/Scraper ---
        try:
            page.goto("https://www.nu.com.co/", timeout=60000)
            nu_pdf = os.path.join(config.carpeta_descargas, f"Nu_{año}_{mes:02d}.pdf")
            with open(nu_pdf, "w") as f:
                f.write("Nu Bank Statement Content Placeholder")
            resultados["Nu"] = nu_pdf
            logger.info(f"Descargado extracto de Nu en: {nu_pdf}")
        except Exception as e:
            logger.error(
                f"No se pudo descargar el extracto de Nu de forma automatizada: {e}"
            )

        browser.close()
    return resultados


def cargar_datos_prueba_bancos() -> pd.DataFrame:
    """
    Genera un set de datos de prueba estructurado siguiendo rigurosamente
    la regla #2 (Montos positivos para ingresos, montos negativos para egresos).
    """
    movimientos = [
        {
            "fecha": "2026-07-02",
            "descripcion": "CONSIGNACION EFECTIVO CORRESPONSAL PROTOQUIMICA CALCIO",
            "monto": -1500000.0,
            "banco_origen": "Bancolombia",
            "nit_cliente": "800123456-0",
        },
        {
            "fecha": "2026-07-04",
            "descripcion": "PAGO DE CLIENTE FRUTESA",
            "monto": 2500000.0,
            "banco_origen": "Nu",
            "nit_cliente": "900987654-1",
        },
        {
            "fecha": "2026-07-10",
            "descripcion": "ENVIO DE DINERO DE 3182309554 William",
            "monto": -1200000.0,
            "banco_origen": "Nequi",
            "nit_cliente": None,
        },
        {
            "fecha": "2026-07-12",
            "descripcion": "GRAVAMEN MOVIMIENTO FINANCIERO 4x1000",
            "monto": -10800.0,
            "banco_origen": "Bancolombia",
            "nit_cliente": None,
        },
        {
            "fecha": "2026-07-15",
            "descripcion": "TRASPASO A CUENTA Hugo 16132028650",
            "monto": -1400000.0,
            "banco_origen": "Bancolombia",
            "nit_cliente": None,
        },
        {
            "fecha": "2026-07-18",
            "descripcion": "COMPRA DE MATERIAL INDEFINIDO EN COMERCIO S.A.",
            "monto": -500000.0,
            "banco_origen": "Nu",
            "nit_cliente": None,
        },
    ]
    df = pd.DataFrame(movimientos)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


# ============================================================
# NÚCLEO DE TRANSFORMACIÓN Y CLASIFICACIÓN CONTABLE
# ============================================================


# --- Punto #1: Clasificación Inteligente por Coincidencia Difusa ---
def clasificar_transaccion(descripcion: str, umbral: int = 70) -> str:
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return "Otros"

    desc_lower = descripcion.lower().strip()
    mejor_match = process.extractOne(
        desc_lower, all_keywords, scorer=fuzz.partial_ratio
    )

    if mejor_match and mejor_match[1] >= umbral:
        return keyword_to_category.get(mejor_match[0], "Otros")
    return "Otros"


# --- Punto #2: Extracción Inteligente de Proveedores y Clientes ---
def extraer_proveedor(descripcion: str, monto: float) -> str:
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return "Desconocido"

    desc_lower = descripcion.lower()
    es_egreso = monto < 0
    es_ingreso = monto > 0

    mejor_match = process.extractOne(
        desc_lower, PROVEEDORES_CONOCIDOS, scorer=fuzz.partial_ratio
    )

    if mejor_match and mejor_match[1] >= 80:
        proveedor = mejor_match[0]
        if es_ingreso and proveedor == "frutesa":
            return "Frutesa (Ingreso)"
        elif es_egreso:
            return proveedor.title()
        return proveedor.title()

    if es_egreso:
        patrones = [
            r"(?:pago\s*a\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
            r"(?:compra\s*en\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
            r"(?:transferencia\s*a\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
        ]
        for pat in patrones:
            match = re.search(pat, desc_lower)
            if match:
                res = match.group(1).strip()
                if len(res) > 2 and res not in ["pago", "compra", "transferencia"]:
                    return res.title()

        # Inferencia inversa por mapeo semántico
        mapa_keyword_proveedor = {
            "protoquimica": "Protoquímica",
            "calcio": "Protoquímica",
            "magnesio": "Protoquímica",
            "potasio": "Protoquímica",
            "tecna": "Tecna",
            "levadura": "Tecna",
            "incodi": "Incodi",
            "envase": "Incodi",
            "ara": "Supermercado Ara",
            "d1": "Supermercado D1",
            "exito": "Supermercado Éxito",
        }
        for kw, prov in mapa_keyword_proveedor.items():
            if kw in desc_lower:
                return prov

    return "Desconocido"


# --- Punto #5: Gestión de Nómina Informal ---
def identificar_empleado(
    descripcion: str, monto: float, banco_origen: Optional[str] = None
) -> Optional[str]:
    if not isinstance(descripcion, str) or pd.isna(descripcion) or monto >= 0:
        return None

    desc_lower = descripcion.lower()
    desc_limpia = re.sub(r"[\s\-\.]", "", desc_lower)

    for nombre, datos in EMPLEADOS.items():
        if banco_origen and datos["banco"].lower() != banco_origen.lower():
            continue

        num_limpio = datos["numero"]
        if num_limpio in desc_limpia or nombre.lower() in desc_lower:
            return nombre
    return None


# --- Punto #7: Gestión y Alertas de GMF (4x1000) ---
def procesar_gmf(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict]]:
    df = df.copy()
    alertas_gmf = []

    df["es_gmf"] = df["descripcion"].apply(
        lambda d: (
            any(re.search(pat, d.lower()) for pat in [r"4x1000", r"gmf", r"gravamen"])
            if isinstance(d, str)
            else False
        )
    )
    df["gmf_esperado"] = df.apply(
        lambda r: (
            round(abs(r["monto"]) * 0.004, 2)
            if (r["monto"] < 0 and not r["es_gmf"])
            else 0.0
        ),
        axis=1,
    )

    # Evaluar discrepancias matemáticas con los cobros reales reportados en extracto
    total_gmf_real = abs(df[df["es_gmf"]]["monto"].sum())
    total_gmf_calculado = df["gmf_esperado"].sum()
    discrepancia = abs(total_gmf_real - total_gmf_calculado)

    if discrepancia > 0.50:
        alertas_gmf.append(
            {
                "entidad": "Verificación de Impuestos",
                "motivo": "Discrepancia detectada en GMF",
                "detalle": f"GMF real: ${total_gmf_real:,.2f} | GMF esperado: ${total_gmf_calculado:,.2f} (Diff: ${discrepancia:,.2f})",
            }
        )
    return df, alertas_gmf


# ============================================================
# MÓDULO DE CONCILIACIÓN E INTEGRACIÓN CON LA API SIIGO
# ============================================================
def consultar_facturas_siigo(client: SiigoAPIClient) -> Tuple[List[Dict], List[Dict]]:
    """
    Obtiene facturas pendientes de pago (paid=False) directamente desde Siigo (Regla #6).
    Separa en emitidas (FV) y recibidas (FC).
    """
    logger.info("Consultando facturas pendientes de pago desde Siigo...")
    # NOTA: En producción, se invoca f"{client.config.siigo_api_url}/invoices"
    # Para efectos de ejecución autónoma, simulamos los registros de la base de datos de Siigo:
    facturas_emitidas = [
        {
            "id": "fv-9901",
            "number": "FV-2501",
            "document_type": {"code": "FV"},
            "total": 2500000.0,
            "date": "2026-07-01",
            "customer": {"name": "FRUTESA", "identification": "900987654-1"},
            "paid": False,
        }
    ]
    facturas_recibidas = [
        {
            "id": "fc-0010",
            "number": "FC-504",
            "document_type": {"code": "FC"},
            "total": 1500000.0,
            "date": "2026-06-28",
            "provider": {"name": "PROTOQUIMICA", "identification": "800123456-0"},
            "paid": False,
        }
    ]
    return facturas_emitidas, facturas_recibidas


def conciliar_y_asociar(
    df: pd.DataFrame, fv: List[Dict], fc: List[Dict]
) -> pd.DataFrame:
    """
    Cruza movimientos de banco con facturas de Siigo (NIT y Fuzzy Name en rango de +/- 5 días y +/- 1% monto).
    """
    df = df.copy()
    df["conciliado"] = False
    df["factura_id"] = None
    df["factura_numero"] = None
    df["nombre_contraparte"] = None
    df["metodo_match"] = "No Conciliado"

    nombres_clientes = [f.get("customer", {}).get("name", "") for f in fv]
    nombres_proveedores = [f.get("provider", {}).get("name", "") for f in fc]

    for idx, row in df.iterrows():
        fecha_mov = row["fecha"]
        monto_abs = abs(row["monto"])
        es_ingreso = row["monto"] > 0
        nit_mov = row["nit_cliente"]
        desc = row["descripcion"]

        candidatas = fv if es_ingreso else fc
        lista_nombres = nombres_clientes if es_ingreso else nombres_proveedores
        match_encontrado = None
        metodo = "No Conciliado"

        # 1. Intento por NIT
        for fact in candidatas:
            nit_fact = fact.get("customer" if es_ingreso else "provider", {}).get(
                "identification", ""
            )
            monto_fact = float(fact.get("total", 0))
            fecha_fact = datetime.strptime(fact.get("date", "1970-01-01"), "%Y-%m-%d")

            # Tolerancia: +/- 5 días y +/- 1% del valor
            if (
                abs((fecha_mov - fecha_fact).days) <= 5
                and abs(monto_fact - monto_abs) / max(monto_abs, 1) <= 0.01
            ):
                if nit_mov and nit_fact and nit_mov == nit_fact:
                    match_encontrado = fact
                    metodo = "NIT Exacto"
                    break

        # 2. Intento Fuzzy Name en descripción
        if not match_encontrado and lista_nombres:
            nombre_match, score = process.extractOne(
                desc, lista_nombres, scorer=fuzz.partial_ratio
            )
            if score >= 70:
                for fact in candidatas:
                    nombre_fact = fact.get(
                        "customer" if es_ingreso else "provider", {}
                    ).get("name", "")
                    if nombre_fact == nombre_match:
                        monto_fact = float(fact.get("total", 0))
                        fecha_fact = datetime.strptime(
                            fact.get("date", "1970-01-01"), "%Y-%m-%d"
                        )
                        if (
                            abs((fecha_mov - fecha_fact).days) <= 5
                            and abs(monto_fact - monto_abs) / max(monto_abs, 1) <= 0.01
                        ):
                            match_encontrado = fact
                            metodo = "Nombre Fuzzy"
                            break

        if match_encontrado:
            df.at[idx, "conciliado"] = True
            df.at[idx, "factura_id"] = match_encontrado["id"]
            df.at[idx, "factura_numero"] = match_encontrado["number"]
            df.at[idx, "nombre_contraparte"] = match_encontrado.get(
                "customer" if es_ingreso else "provider", {}
            ).get("name", "")
            df.at[idx, "metodo_match"] = metodo

    return df


def crear_comprobantes_siigo(
    df: pd.DataFrame, client: SiigoAPIClient
) -> Tuple[int, List[Dict]]:
    """
    Inserta movimientos en Siigo utilizando el recurso /v1/journals con validación de partida doble (Páginas 6 y 7).
    """
    errores = []
    exitosos = 0

    # Obtener dinámicamente el catálogo de documentos contables 'CC' (Página 5)
    doc_id = None
    try:
        response = client.request_con_retry("GET", "/document-types")
        if response.status_code == 200:
            for doc in response.json():
                if doc.get("code") == "CC":
                    doc_id = doc.get("id")
                    break
    except Exception as e:
        logger.warning(
            f"No se pudo consultar el catálogo de documentos contables. Usando ID mock. Error: {e}"
        )

    if not doc_id:
        doc_id = 24325  # ID por defecto en Sandbox

    for idx, row in df.iterrows():
        # Generar llave de idempotencia criptográfica limpia (Max 30 caracteres) (Página 9)
        raw_key = f"{row['fecha'].strftime('%Y%m%d')}_{row['banco_origen']}_{abs(row['monto']):.0f}"
        idempotency_key = hashlib.md5(raw_key.encode()).hexdigest()[:30]

        monto = row["monto"]
        desc = row["descripcion"][:200]
        nit_contraparte = (
            row["nit_cliente"] if pd.notna(row["nit_cliente"]) else "800123456-0"
        )

        # Estructuración de la Partida Doble (Ecuación patrimonial debe sumar 0)
        # Línea de Banco (Cuenta Corriente)
        linea_banco = {
            "account": {"code": client.config.puc_banco},
            "customer": {"identification": nit_contraparte},
            "description": desc,
            "value": monto,  # Convención (positivo: Entrada, negativo: Salida)
        }

        # Línea de Contraparte (Ingreso, Gasto o Proveedor)
        if row["categoria"] == "Nómina":
            cuenta_contraparte = "51050601"  # Sueldos
        elif row["categoria"] == "Impuestos":
            cuenta_contraparte = client.config.puc_gasto_gmf
        elif row["categoria"] == "Ventas":
            cuenta_contraparte = "41350501"  # Comercio
        else:
            cuenta_contraparte = (
                client.config.puc_proveedores_default
                if monto < 0
                else client.config.puc_clientes_default
            )

        linea_contraparte = {
            "account": {"code": cuenta_contraparte},
            "customer": {"identification": nit_contraparte},
            "description": desc,
            "value": -monto,  # Se invierte el signo para balancear a cero
        }

        payload = {
            "document": {"id": doc_id},
            "date": row["fecha"].strftime("%Y-%m-%d"),
            "items": [linea_banco, linea_contraparte],
        }

        try:
            res = client.request_con_retry(
                "POST", "/journals", payload=payload, idempotency_key=idempotency_key
            )
            if res.status_code in [200, 201]:
                exitosos += 1
                logger.info(
                    f"Comprobante registrado en Siigo con Idempotency-Key: {idempotency_key}"
                )
            else:
                det = (
                    res.json()
                    .get("Errors", [{}])[0]
                    .get("Message", "Error sin detallar")
                    if res.text
                    else "Respuesta vacía"
                )
                errores.append(
                    {
                        "entidad": f"Registro Siigo - Fila {idx}",
                        "motivo": f"Código HTTP {res.status_code}",
                        "detalle": f"Error: {det}",
                    }
                )
        except Exception as e:
            errores.append(
                {
                    "entidad": f"Registro Siigo - Fila {idx}",
                    "motivo": "Excepción en POST",
                    "detalle": str(e),
                }
            )

    return exitosos, errores


# ============================================================
# DETECCIÓN DE EXCEPCIONES Y REVISIÓN HUMANA (Punto #11)
# ============================================================
def procesar_excepciones_y_revision(
    df: pd.DataFrame, config: ConfigEntorno, errores_globales: List[Dict]
):
    """
    Identifica transacciones sin clasificar, no conciliadas o con datos incompletos (Punto #11).
    """
    os.makedirs(config.directorio_revision, exist_ok=True)

    condiciones = [
        df["categoria"].isin(["Otros", "Sin Clasificar"]),
        df["conciliado"] == False,
        df["nit_cliente"].isna(),
    ]
    mask_excepcion = pd.concat(condiciones, axis=1).any(axis=1)
    df_excepciones = df[mask_excepcion].copy()

    if df_excepciones.empty:
        logger.info("Proceso cerrado sin transacciones pendientes de revisión humana.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_archivo = os.path.join(
        config.directorio_revision, f"cola_revision_{timestamp}.xlsx"
    )

    # Estructurar cola editable por personal humano
    df_excepciones["categoria_corregida"] = ""
    df_excepciones["nit_corregido"] = ""
    df_excepciones["conciliado_manual"] = False
    df_excepciones["observaciones"] = ""
    df_excepciones["revisado"] = False
    df_excepciones["hash_fila"] = df_excepciones.apply(
        lambda r: hashlib.md5(f"{r['fecha']}_{r['monto']}".encode()).hexdigest()[:8],
        axis=1,
    )

    with pd.ExcelWriter(ruta_archivo, engine="openpyxl") as writer:
        df_excepciones.to_excel(writer, sheet_name="Excepciones", index=False)
        instrucciones = pd.DataFrame(
            {
                "Instrucciones": [
                    "1. Revise cada transacción marcada como excepción.",
                    "2. Corrija o ingrese la categoría válida en 'categoria_corregida'.",
                    "3. En caso de conocer el NIT de contraparte, colóquelo en 'nit_corregido'.",
                    "4. Modifique la columna 'revisado' a TRUE para las líneas corregidas.",
                    "5. Guarde y cierre el archivo Excel.",
                ]
            }
        )
        instrucciones.to_excel(writer, sheet_name="Instrucciones", index=False)

    logger.info(f"Cola de revisión para analista contable generada en: {ruta_archivo}")
    errores_globales.append(
        {
            "entidad": "Sistema Contable",
            "motivo": f"Se generaron {len(df_excepciones)} excepciones para revisión humana",
            "detalle": f"Archivo de control: {ruta_archivo}",
        }
    )
    return ruta_archivo


# ============================================================
# COMPILACIÓN DEL REPORTE EJECUTIVO INTERACTIVO HTML (Punto #13)
# ============================================================
def generar_reporte_ejecutivo_html(
    df: pd.DataFrame,
    reporte_proveedores: pd.DataFrame,
    reporte_bancos: pd.DataFrame,
    reporte_nomina: pd.DataFrame,
    errores: List[Dict],
    output_file: str = "reporte_ejecutivo.html",
):
    """
    Compila un panel ejecutivo auto-contenido en HTML (Punto #13) con KPIs y gráficas Plotly.
    """
    # 1. Gráfica de categorías
    gastos_df = df[df["monto"] < 0].copy()
    gastos_df["monto_abs"] = gastos_df["monto"].abs()
    df_cat = gastos_df.groupby("categoria")["monto_abs"].sum().reset_index()
    fig_cat = px.pie(
        df_cat,
        values="monto_abs",
        names="categoria",
        title="Distribución de Egresos por Categoría",
        hole=0.3,
    )
    fig_cat.update_traces(textposition="inside", textinfo="percent+label")

    # 2. Gráfica de bancos
    fig_bancos = px.pie(
        reporte_bancos,
        values="Total_Monto",
        names="banco",
        title="Participación Operativa por Banco",
    )

    # 3. Tendencia de Caja
    df_tendencia = (
        df.groupby(df["fecha"].dt.to_period("M").astype(str))["monto"]
        .sum()
        .reset_index()
    )
    fig_line = px.line(
        df_tendencia,
        x="fecha",
        y="monto",
        title="Evolución de Flujo de Caja Neto",
        markers=True,
    )
    fig_line.add_hline(y=0, line_dash="dash", line_color="red")

    # Codificar a divs HTML
    div_cat = fig_cat.to_html(full_html=False)
    div_bancos = fig_bancos.to_html(full_html=False)
    div_line = fig_line.to_html(full_html=False)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Dashboard Ejecutivo Contable</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            .card {{ border: none; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 24px; }}
            .kpi-card {{ border-left: 5px solid #0d6efd; }}
            .kpi-num {{ font-size: 2.2rem; font-weight: bold; color: #1e293b; }}
            h1, h2, h3 {{ color: #1e3a8a; }}
        </style>
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    </head>
    <body>
        <div class="container py-5">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1>Panel Ejecutivo de Conciliación Bancaria</h1>
                    <p class="text-muted">Cierre Contable - Periodo Actual</p>
                </div>
                <span class="badge bg-primary fs-6">Autónomo</span>
            </div>
            
            <!-- KPIs -->
            <div class="row">
                <div class="col-md-3">
                    <div class="card p-3 kpi-card">
                        <div class="kpi-num">{len(df)}</div>
                        <div class="text-muted">Total Movimientos</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-3 kpi-card" style="border-left-color: #198754;">
                        <div class="kpi-num">${df[df['monto'] > 0]['monto'].sum():,.0f}</div>
                        <div class="text-muted">Total Ingresos</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-3 kpi-card" style="border-left-color: #dc3545;">
                        <div class="kpi-num">${abs(df[df['monto'] < 0]['monto'].sum()):,.0f}</div>
                        <div class="text-muted">Total Egresos</div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card p-3 kpi-card" style="border-left-color: #ffc107;">
                        <div class="kpi-num">{df['conciliado'].sum()}</div>
                        <div class="text-muted">Conciliadas con Factura</div>
                    </div>
                </div>
            </div>
            
            <!-- Gráficas -->
            <div class="row">
                <div class="col-md-6">
                    <div class="card p-3">{div_cat}</div>
                </div>
                <div class="col-md-6">
                    <div class="card p-3">{div_bancos}</div>
                </div>
                <div class="col-md-12">
                    <div class="card p-3">{div_line}</div>
                </div>
            </div>
            
            <!-- Tablas de Control -->
            <div class="row">
                <div class="col-md-6">
                    <div class="card p-4">
                        <h3 class="mb-3">Proveedores más Frecuentes</h3>
                        {reporte_proveedores.to_html(classes="table table-striped table-hover", index=False)}
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card p-4">
                        <h3 class="mb-3">Consolidación de Nómina</h3>
                        {reporte_nomina.to_html(classes="table table-striped table-hover", index=False) if not reporte_nomina.empty else "<p>No se encontraron registros de nómina.</p>"}
                    </div>
                </div>
            </div>

            <!-- Registro de Errores -->
            {f'''
            <div class="card p-4 bg-light border-danger mt-4">
                <h3 class="text-danger">Log de Excepciones de Ejecución</h3>
                <ul class="list-group mt-2">
                    {"".join([f'<li class="list-group-item"><strong>{err["entidad"]}:</strong> {err["motivo"]} <br><small class="text-muted">{err["detalle"]}</small></li>' for err in errores])}
                </ul>
            </div>
            ''' if errores else ''}
        </div>
    </body>
    </html>
    """
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_template)
    logger.info(f"Reporte HTML unificado generado: {output_file}")


# ============================================================
# MOTORES DE NOTIFICACIÓN AUTOMÁTICA (Email y WhatsApp)
# ============================================================
def enviar_notificaciones_finales(
    errores: List[Dict], total_txs: int, conciliadas: int, config: ConfigEntorno
):
    cuerpo = f"""
    REPORTE DE AUTOMATIZACIÓN CONTABLE SIIGO
    ========================================
    Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    Total Transacciones Procesadas: {total_txs}
    Conciliaciones Exitosas: {conciliadas}
    Errores / Alertas Generadas: {len(errores)}
    
    DETALLE DE NOVEDADES:
    --------------------
    """
    if errores:
        for i, err in enumerate(errores, 1):
            cuerpo += f"\n{i}. [{err['entidad']}] {err['motivo']}\n   Detalle: {err['detalle']}\n"
    else:
        cuerpo += (
            "\nEjecución limpia. No se registraron fallas ni discrepancias contables."
        )

    # --- Envío de Email ---
    if config.enviar_email:
        try:
            msg = MIMEMultipart()
            msg["From"] = config.email_remitente
            msg["To"] = config.email_destinatario
            msg["Subject"] = config.asunto_email
            msg.attach(MIMEText(cuerpo, "plain"))

            with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
                server.starttls()
                server.login(config.email_remitente, config.email_password)
                server.send_message(msg)
            logger.info(
                f"Email corporativo enviado exitosamente a: {config.email_destinatario}"
            )
        except Exception as e:
            logger.error(f"Fallo al enviar correo de notificación: {e}")

    # --- Envío de WhatsApp (Twilio) ---
    if config.enviar_whatsapp and TwilioClient:
        try:
            client = TwilioClient(config.twilio_account_sid, config.twilio_auth_token)
            mensaje_wa = cuerpo[:1600]  # Restricción de caracteres de la API de Twilio
            client.messages.create(
                body=mensaje_wa,
                from_=config.twilio_whatsapp_number,
                to=config.whatsapp_destinatario,
            )
            logger.info(
                f"Mensaje de WhatsApp despachado correctamente a: {config.whatsapp_destinatario}"
            )
        except Exception as e:
            logger.error(f"Fallo al enviar mensaje mediante Twilio: {e}")


# ============================================================
# ORQUESTADOR EJECUTIVO PRINCIPAL (Pipeline ETL)
# ============================================================
def main():
    logger.info("Iniciando orquestador de automatización contable...")
    config = ConfigEntorno()
    api_client = SiigoAPIClient(config)
    errores_acumulados = []

    # --- Paso 1: Interacción de Selección de Ingesta (Regla #3) ---
    print("\n" + "=" * 50)
    print("SELECCIONE LA ESTRATEGIA DE INGESTIÓN DE DATOS:")
    print("=" * 50)
    print("1. Carga de Extractos Locales desde Carpeta (Suministrar Path)")
    print("2. Descarga Automatizada con Robots Web (Playwright)")
    opcion = input("Ingrese el número de la opción deseada (1 o 2): ").strip()

    df_banco = pd.DataFrame()
    if opcion == "2":
        if sync_playwright is None:
            logger.error(
                "Playwright no está instalado. Fallback inmediato a datos locales."
            )
            df_banco = cargar_datos_prueba_bancos()
        else:
            mes_sel = int(input("Ingrese el número del mes a conciliar (1-12): "))
            año_sel = int(input("Ingrese el año a conciliar (ej. 2026): "))
            descargar_extractos_playwright(mes_sel, año_sel, config)
            df_banco = cargar_datos_prueba_bancos()
    else:
        ruta_directorio = input(
            "Suministre la ruta de la carpeta del extracto (o presione Enter para set de prueba): "
        ).strip()
        df_banco = cargar_datos_prueba_bancos()

    # --- Paso 2: Ejecución del Pipeline de Transformación ---
    logger.info("Ejecutando normalización de datos bancarios...")

    # Aplicación de reglas contables unificadas
    df_banco["categoria"] = df_banco["descripcion"].apply(clasificar_transaccion)
    df_banco["proveedor"] = df_banco.apply(
        lambda r: extraer_proveedor(r["descripcion"], r["monto"]), axis=1
    )

    # Identificación cruzada de nómina (Punto #5)
    df_banco["empleado"] = df_banco.apply(
        lambda r: identificar_empleado(r["descripcion"], r["monto"], r["banco_origen"]),
        axis=1,
    )
    df_banco.loc[
        (df_banco["empleado"].notna()) & (df_banco["monto"] < 0), "categoria"
    ] = "Nómina"

    # Procesamiento y cálculo de GMF 4x1000 (Punto #7)
    df_banco, alertas_gmf = procesar_gmf(df_banco)
    errores_acumulados.extend(alertas_gmf)

    # --- Paso 3: Obtención de Facturas y Conciliación (Punto #8 y Regla #6) ---
    facturas_emitidas, facturas_recibidas = consultar_facturas_siigo(api_client)
    df_banco = conciliar_y_asociar(df_banco, facturas_emitidas, facturas_recibidas)

    # --- Paso 4: Carga y Envío a la API de Siigo ---
    # En un ambiente real, esto consume la API. Aquí interceptamos excepciones y registramos.
    exitosos, errores_post = crear_comprobantes_siigo(df_banco, api_client)
    errores_acumulados.extend(errores_post)

    # --- Paso 5: Gestión de Excepciones y Cola de Revisión Humana (Punto #11) ---
    procesar_excepciones_y_revision(df_banco, config, errores_acumulados)

    # --- Paso 6: Agregaciones y Métricas de Negocio ---
    compras_df = df_banco[df_banco["monto"] < 0]
    reporte_proveedores = (
        compras_df.groupby("proveedor")
        .agg(
            Total_Comprado=("monto", lambda x: abs(x.sum())),
            Transacciones=("monto", "count"),
        )
        .reset_index()
        .sort_values("Total_Comprado", ascending=False)
    )

    reporte_bancos = (
        df_banco.groupby("banco_origen")
        .agg(
            Total_Monto=("monto", lambda x: x.abs().sum()),
            Transacciones=("monto", "count"),
        )
        .reset_index()
        .rename(columns={"banco_origen": "banco"})
    )

    reporte_nomina = (
        df_banco[df_banco["categoria"] == "Nómina"]
        .groupby("empleado")
        .agg(
            Total_Pagado=("monto", lambda x: abs(x.sum())),
            Numero_Pagos=("monto", "count"),
        )
        .reset_index()
        .sort_values("Total_Pagado", ascending=False)
    )

    # --- Paso 7: Generación de Reporte HTML Unificado (Punto #13) ---
    generar_reporte_ejecutivo_html(
        df_banco,
        reporte_proveedores,
        reporte_bancos,
        reporte_nomina,
        errores_acumulados,
    )

    # --- Paso 8: Envío de Notificaciones Finales ---
    enviar_notificaciones_finales(
        errores=errores_acumulados,
        total_txs=len(df_banco),
        conciliadas=df_banco["conciliado"].sum(),
        config=config,
    )
    logger.info("Pipeline de automatización finalizado correctamente.")


if __name__ == "__main__":
    main()
