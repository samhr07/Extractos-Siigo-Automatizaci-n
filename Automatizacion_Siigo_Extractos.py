import time
import json
import os
import hashlib
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


# ------------------------------------------------------------
# CONFIGURACIÓN (ampliada y corregida)
# ------------------------------------------------------------
class ConfiguracionAutomatizacion:
    # Credenciales Siigo
    siigo_username: str = "TU_USERNAME_API"
    siigo_access_key: str = "TU_ACCESS_KEY"
    siigo_partner_id: str = "MiScriptConciliacion"

    # Datos bancarios (simplificados para el ejemplo)
    # ... (mantén los que ya tenías)

    # Parámetros de control
    delay_bancos_segundos: int = 15
    timeout_siigo: int = 120
    max_retries: int = 3
    directorio_pdfs: str = "./extractos_manuales/"


config = ConfiguracionAutomatizacion()


# ------------------------------------------------------------
# 1. AUTENTICACIÓN Y TOKEN JWT
# ------------------------------------------------------------
def obtener_token_siigo(username: str, access_key: str) -> str:
    """Obtiene token JWT de Siigo y lo devuelve."""
    url = "https://api.siigo.com/v1/auth"
    payload = {"username": username, "access_key": access_key}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise ValueError("Token no recibido")
        return token
    except Exception as e:
        raise RuntimeError(f"Error autenticando con Siigo: {e}")


# ------------------------------------------------------------
# 2. FUNCIÓN DE REINTENTO CON BACKOFF (para rate limits 429)
# ------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(requests.exceptions.HTTPError),
)
def request_con_retry(method, url, headers=None, json=None, params=None, timeout=120):
    """Realiza petición HTTP con reintentos automáticos en caso de 429 o 5xx."""
    headers = headers or {}
    resp = requests.request(
        method, url, headers=headers, json=json, params=params, timeout=timeout
    )

    if resp.status_code == 429:
        # Si la API devuelve Retry-After, usamos ese tiempo
        retry_after = int(resp.headers.get("Retry-After", 5))
        time.sleep(retry_after)
        resp.raise_for_status()  # Forzamos reintento
    elif resp.status_code >= 500:
        resp.raise_for_status()  # Reintentará por tenacity
    else:
        resp.raise_for_status()
    return resp


# ------------------------------------------------------------
# 3. OBTENER FACTURAS ELECTRÓNICAS (pendientes de pago)
# ------------------------------------------------------------
def obtener_facturas_pendientes(
    token: str, partner_id: str, customer_id: Optional[str] = None
) -> List[Dict]:
    """Obtiene facturas emitidas (o recibidas) que estén pendientes de pago."""
    headers = {"Authorization": f"Bearer {token}", "Partner-Id": partner_id}
    params = {"status": "issued", "limit": 100}  # Ajusta según necesidad
    if customer_id:
        params["customer"] = customer_id

    url = "https://api.siigo.com/v1/invoices"
    try:
        resp = request_con_retry(
            "GET", url, headers=headers, params=params, timeout=config.timeout_siigo
        )
        facturas = resp.json()
        # Filtramos solo las que están pendientes (campo 'paid' o 'status' según la API)
        # En la API de Siigo, el campo 'paid' es booleano; también 'status' puede ser 'issued'/'paid'
        pendientes = [f for f in facturas if not f.get("paid", False)]
        return pendientes
    except Exception as e:
        print(f"❌ Error obteniendo facturas pendientes: {e}")
        return []


# ------------------------------------------------------------
# 4. CONCILIACIÓN: CRUZAR MOVIMIENTOS BANCARIOS CON FACTURAS
# ------------------------------------------------------------
def conciliar_facturas(movimientos: pd.DataFrame, facturas: List[Dict]) -> pd.DataFrame:
    """
    Cruza los movimientos bancarios (egresos/ingresos) con las facturas pendientes.
    Retorna un DataFrame con el resultado de la conciliación.
    """
    # Asegurar que tenemos las columnas necesarias en movimientos: fecha, monto, nit_cliente, descripcion
    # Si no tienes NIT, puedes usar coincidencia difusa por nombre (pero asumimos que tienes NIT)
    resultados = []

    for _, mov in movimientos.iterrows():
        # Solo nos interesan los egresos (pagos a proveedores) o ingresos (cobros a clientes)
        # Para este ejemplo, asumimos que queremos conciliar tanto pagos como cobros
        monto_abs = abs(mov["monto"])
        fecha_mov = mov["fecha"]
        nit = mov.get("nit_cliente", None)  # Si no hay NIT, podemos intentar con nombre

        # Buscar factura que coincida en NIT, monto aprox y fecha cercana
        factura_match = None
        mejor_similitud = 0

        for fact in facturas:
            # Extraer datos de la factura
            nit_fact = fact.get("customer", {}).get("identification", "")
            monto_fact = float(fact.get("total", 0))
            fecha_fact = datetime.strptime(
                fact.get("date", "1970-01-01"), "%Y-%m-%d"
            ).date()
            # Permitir diferencia de ±5 días
            if abs((fecha_mov - fecha_fact).days) > 5:
                continue
            # Comparar montos con tolerancia del 1%
            if abs(monto_fact - monto_abs) / max(monto_abs, 1) > 0.01:
                continue
            # Si tenemos NIT, comparamos exacto
            if nit and nit_fact and nit == nit_fact:
                factura_match = fact
                break
            # Si no, usar coincidencia difusa en nombre (aquí simplificamos)
            # Podrías usar fuzzywuzzy para mejorar
            # ...

        if factura_match:
            # Marcar como conciliado
            resultados.append(
                {
                    "movimiento": mov.to_dict(),
                    "factura_id": factura_match.get("id"),
                    "factura_numero": factura_match.get("number"),
                    "conciliado": True,
                }
            )
        else:
            resultados.append(
                {"movimiento": mov.to_dict(), "factura_id": None, "conciliado": False}
            )

    return pd.DataFrame(resultados)


# ------------------------------------------------------------
# 5. MARCAR FACTURA COMO PAGADA EN SIIGO (PATCH)
# ------------------------------------------------------------
def marcar_factura_pagada(
    token: str, partner_id: str, factura_id: str, fecha_pago: str, idempotency_key: str
) -> bool:
    """Actualiza una factura para marcarla como pagada."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Partner-Id": partner_id,
        "Idempotency-Key": idempotency_key,
    }
    payload = {"paid": True, "payment_date": fecha_pago}  # YYYY-MM-DD
    url = f"https://api.siigo.com/v1/invoices/{factura_id}"
    try:
        resp = request_con_retry(
            "PATCH", url, headers=headers, json=payload, timeout=config.timeout_siigo
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"❌ Error marcando factura {factura_id} como pagada: {e}")
        return False


# ------------------------------------------------------------
# 6. FLUJO PRINCIPAL DE CONCILIACIÓN
# ------------------------------------------------------------
def ejecutar_conciliacion(
    movimientos: pd.DataFrame, config: ConfiguracionAutomatizacion
) -> Dict:
    """
    Orquesta la conciliación: obtiene token, facturas, cruza y actualiza.
    Retorna un resumen con estadísticas.
    """
    # 1. Obtener token
    token = obtener_token_siigo(config.siigo_username, config.siigo_access_key)

    # 2. Obtener facturas pendientes
    facturas = obtener_facturas_pendientes(token, config.siigo_partner_id)
    print(f"📄 Facturas pendientes obtenidas: {len(facturas)}")

    # 3. Conciliar movimientos
    conciliacion_df = conciliar_facturas(movimientos, facturas)

    # 4. Actualizar facturas conciliadas
    actualizadas = 0
    for _, row in conciliacion_df.iterrows():
        if row["conciliado"] and row["factura_id"]:
            factura_id = row["factura_id"]
            fecha_mov = row["movimiento"]["fecha"].strftime("%Y-%m-%d")
            # Generar clave de idempotencia única
            idempotency_key = hashlib.sha256(
                f"{factura_id}{fecha_mov}".encode()
            ).hexdigest()[:30]
            ok = marcar_factura_pagada(
                token, config.siigo_partner_id, factura_id, fecha_mov, idempotency_key
            )
            if ok:
                actualizadas += 1
                print(f"✅ Factura {factura_id} marcada como pagada.")
            else:
                print(f"⚠️ Falló actualización de factura {factura_id}")

    # 5. Resumen
    resumen = {
        "total_movimientos": len(movimientos),
        "facturas_pendientes": len(facturas),
        "conciliaciones_exitosas": conciliacion_df["conciliado"].sum(),
        "facturas_actualizadas": actualizadas,
    }
    return resumen


# ------------------------------------------------------------
# 7. EJEMPLO DE USO (INTEGRADO CON TU CÓDIGO EXISTENTE)
# ------------------------------------------------------------
if __name__ == "__main__":
    # Simulación: cargar movimientos desde extractos (debes tener tu df)
    # Suponiendo que ya tienes un DataFrame con los movimientos bancarios
    # df_movimientos = cargar_tus_extractos()  # <-- tu función de extracción

    # Si no tienes, creamos un ejemplo rápido
    df_movimientos = pd.DataFrame(
        {
            "fecha": [datetime(2026, 7, 10), datetime(2026, 7, 12)],
            "monto": [-1500000, -2500000],
            "nit_cliente": ["800123456-0", "900987654-1"],
            "descripcion": ["Pago factura 123", "Pago factura 456"],
        }
    )

    # Ejecutar conciliación
    resumen = ejecutar_conciliacion(df_movimientos, config)

    # Imprimir reporte
    print("\n📊 RESUMEN DE CONCILIACIÓN")
    print("==========================")
    for k, v in resumen.items():
        print(f"{k}: {v}")

    # Generar archivo Excel con detalle de conciliación
    # (puedes guardar el DataFrame de conciliación)
