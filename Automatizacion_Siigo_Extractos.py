import time
import json
import os
import hashlib
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from thefuzz import process, fuzz  # <-- Nueva dependencia

# ------------------------------------------------------------
# CONFIGURACIÓN (ampliada con tipos de factura)
# ------------------------------------------------------------
class ConfiguracionAutomatizacion:
    # Credenciales Siigo
    siigo_username: str = "TU_USERNAME_API"
    siigo_access_key: str = "TU_ACCESS_KEY"
    siigo_partner_id: str = "MiScriptConciliacion"
    
    # Datos bancarios (mantén los que ya tenías)
    # ...
    
    # Parámetros de control
    delay_bancos_segundos: int = 15
    timeout_siigo: int = 120
    max_retries: int = 3
    directorio_pdfs: str = "./extractos_manuales/"
    
    # Tipos de factura a conciliar (según catálogo de Siigo)
    # 'FV' = Factura de Venta (emitida a cliente) -> para ingresos
    # 'FC' = Factura de Compra (recibida de proveedor) -> para egresos
    tipos_factura_emitidas: List[str] = ["FV"]   # Ventas
    tipos_factura_recibidas: List[str] = ["FC"]  # Compras
    
config = ConfiguracionAutomatizacion()

# ------------------------------------------------------------
# 1. AUTENTICACIÓN (sin cambios)
# ------------------------------------------------------------
def obtener_token_siigo(username: str, access_key: str) -> str:
    # ... (igual que antes)
    pass

# ------------------------------------------------------------
# 2. FUNCIÓN DE REINTENTO (sin cambios)
# ------------------------------------------------------------
@retry(...)
def request_con_retry(...):
    # ... (igual que antes)
    pass

# ------------------------------------------------------------
# 3. (NUEVA) OBTENER FACTURAS POR TIPO (emitidas y/o recibidas)
# ------------------------------------------------------------
def obtener_facturas_pendientes(
    token: str, 
    partner_id: str, 
    tipos_documento: List[str] = ["FV", "FC"],  # Por defecto ambas
    customer_id: Optional[str] = None,
    proveedor_id: Optional[str] = None
) -> List[Dict]:
    """
    Obtiene facturas pendientes de pago (paid=False) de los tipos especificados.
    - tipos_documento: lista de códigos (ej. 'FV' para ventas, 'FC' para compras).
    - customer_id: filtrar por cliente (para facturas emitidas).
    - proveedor_id: filtrar por proveedor (para facturas recibidas).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Partner-Id": partner_id
    }
    facturas_todas = []
    
    # La API de Siigo permite filtrar por 'type' (código del documento)
    # También podemos obtener todas y luego filtrar por paid=False y type
    url = "https://api.siigo.com/v1/invoices"
    params = {"limit": 200}  # Ajusta según necesidad
    if customer_id:
        params["customer"] = customer_id
    # Nota: la API no tiene filtro directo por 'type' en todos los casos, 
    # así que obtenemos todas y filtramos en memoria.
    
    try:
        resp = request_con_retry("GET", url, headers=headers, params=params, timeout=config.timeout_siigo)
        facturas = resp.json()
        # Filtrar por tipo de documento y pendientes
        pendientes = []
        for f in facturas:
            tipo = f.get('document_type', {}).get('id')  # o 'type' según la respuesta
            # Si no viene 'id', intentar con 'document_type' u otro campo
            # En la API de Siigo, el objeto 'document_type' tiene un campo 'code'
            tipo_code = f.get('document_type', {}).get('code', '')
            if tipo_code in tipos_documento and not f.get('paid', False):
                pendientes.append(f)
        return pendientes
    except Exception as e:
        print(f"❌ Error obteniendo facturas pendientes: {e}")
        return []

# ------------------------------------------------------------
# 4. (NUEVA) COINCIDENCIA DIFUSA POR NOMBRE
# ------------------------------------------------------------
def coincidencia_difusa_nombre(descripcion: str, lista_nombres: List[str], umbral: int = 70) -> Tuple[Optional[str], int]:
    """
    Busca el nombre más parecido en la lista usando fuzzy matching.
    Retorna (nombre_match, puntaje) o (None, 0) si no supera el umbral.
    """
    if not descripcion or not lista_nombres:
        return None, 0
    # Extraer el mejor match usando partial_ratio (funciona bien con subcadenas)
    match = process.extractOne(descripcion, lista_nombres, scorer=fuzz.partial_ratio)
    if match and match[1] >= umbral:
        return match[0], match[1]
    return None, 0

# ------------------------------------------------------------
# 5. (MODIFICADA) CONCILIACIÓN CON COINCIDENCIA DIFUSA Y AMBOS TIPOS
# ------------------------------------------------------------
def conciliar_facturas(
    movimientos: pd.DataFrame, 
    facturas_emitidas: List[Dict],
    facturas_recibidas: List[Dict]
) -> pd.DataFrame:
    """
    Cruza movimientos bancarios con facturas emitidas (ingresos) y recibidas (egresos).
    - Para ingresos (monto > 0): busca en facturas_emitidas (clientes).
    - Para egresos (monto < 0): busca en facturas_recibidas (proveedores).
    Usa coincidencia exacta por NIT y, si falla, coincidencia difusa por nombre.
    """
    resultados = []
    
    # Preparamos listas de nombres para coincidencia difusa
    nombres_clientes = [f.get('customer', {}).get('name', '') for f in facturas_emitidas if f.get('customer', {}).get('name')]
    nombres_proveedores = [f.get('provider', {}).get('name', '') for f in facturas_recibidas if f.get('provider', {}).get('name')]
    
    for _, mov in movimientos.iterrows():
        fecha_mov = mov['fecha']
        monto_abs = abs(mov['monto'])
        es_ingreso = mov['monto'] > 0
        descripcion = mov.get('descripcion', '')
        nit = mov.get('nit_cliente', None)  # Puede ser NIT del cliente o proveedor
        
        # Determinar el conjunto de facturas a buscar
        facturas_candidatas = facturas_emitidas if es_ingreso else facturas_recibidas
        lista_nombres = nombres_clientes if es_ingreso else nombres_proveedores
        
        factura_match = None
        mejor_similitud = 0
        
        # Intentar coincidencia exacta por NIT primero
        for fact in facturas_candidatas:
            # Obtener identificación (NIT) según el rol
            if es_ingreso:
                nit_fact = fact.get('customer', {}).get('identification', '')
            else:
                nit_fact = fact.get('provider', {}).get('identification', '')
            
            monto_fact = float(fact.get('total', 0))
            fecha_fact = datetime.strptime(fact.get('date', '1970-01-01'), '%Y-%m-%d').date()
            
            # Verificar fecha (±5 días)
            if abs((fecha_mov - fecha_fact).days) > 5:
                continue
            # Verificar monto (±1%)
            if abs(monto_fact - monto_abs) / max(monto_abs, 1) > 0.01:
                continue
            # Si tenemos NIT y coincide exactamente, ganamos
            if nit and nit_fact and nit == nit_fact:
                factura_match = fact
                break
        
        # Si no hubo match exacto por NIT, intentar fuzzy por nombre
        if not factura_match and lista_nombres:
            # Buscar en la descripción del movimiento un nombre parecido
            nombre_match, score = coincidencia_difusa_nombre(descripcion, lista_nombres)
            if nombre_match and score >= 70:
                # Encontrar la factura que corresponde a ese nombre
                for fact in facturas_candidatas:
                    if es_ingreso:
                        nombre_fact = fact.get('customer', {}).get('name', '')
                    else:
                        nombre_fact = fact.get('provider', {}).get('name', '')
                    if nombre_fact == nombre_match:
                        # Verificar monto y fecha (ya lo hicimos antes, pero repetimos por seguridad)
                        monto_fact = float(fact.get('total', 0))
                        fecha_fact = datetime.strptime(fact.get('date', '1970-01-01'), '%Y-%m-%d').date()
                        if (abs((fecha_mov - fecha_fact).days) <= 5 and 
                            abs(monto_fact - monto_abs) / max(monto_abs, 1) <= 0.01):
                            factura_match = fact
                            break
        
        # Registrar resultado
        if factura_match:
            resultados.append({
                'movimiento': mov.to_dict(),
                'factura_id': factura_match.get('id'),
                'factura_numero': factura_match.get('number'),
                'factura_tipo': factura_match.get('document_type', {}).get('code', ''),
                'nombre_contraparte': factura_match.get('customer' if es_ingreso else 'provider', {}).get('name', ''),
                'conciliado': True,
                'metodo_match': 'NIT' if (nit and nit == factura_match.get('customer' if es_ingreso else 'provider', {}).get('identification', '')) else 'Nombre'
            })
        else:
            resultados.append({
                'movimiento': mov.to_dict(),
                'factura_id': None,
                'factura_numero': None,
                'factura_tipo': None,
                'nombre_contraparte': None,
                'conciliado': False,
                'metodo_match': None
            })
    
    return pd.DataFrame(resultados)

# ------------------------------------------------------------
# 6. (NUEVA) GENERAR EXCEL CON DETALLE DE CONCILIACIÓN
# ------------------------------------------------------------
def generar_reporte_excel(conciliacion_df: pd.DataFrame, nombre_archivo: str = "reporte_conciliacion.xlsx"):
    """
    Exporta el DataFrame de conciliación a Excel con formato.
    Incluye: hoja 'Conciliadas', hoja 'No Conciliadas', y hoja 'Resumen'.
    """
    with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
        # 1. Hoja con todas las conciliadas
        conciliadas = conciliacion_df[conciliacion_df['conciliado'] == True].copy()
        if not conciliadas.empty:
            # Expandir el diccionario 'movimiento' en columnas
            mov_expand = conciliadas['movimiento'].apply(pd.Series)
            conciliadas_export = pd.concat([
                mov_expand[['fecha', 'descripcion', 'monto', 'nit_cliente']],
                conciliadas[['factura_numero', 'factura_tipo', 'nombre_contraparte', 'metodo_match']]
            ], axis=1)
            conciliadas_export.to_excel(writer, sheet_name='Conciliadas', index=False)
        else:
            pd.DataFrame({'Mensaje': ['No hay conciliaciones']}).to_excel(writer, sheet_name='Conciliadas', index=False)
        
        # 2. Hoja con las no conciliadas (para revisión humana)
        no_conciliadas = conciliacion_df[conciliacion_df['conciliado'] == False].copy()
        if not no_conciliadas.empty:
            mov_expand = no_conciliadas['movimiento'].apply(pd.Series)
            no_conciliadas_export = mov_expand[['fecha', 'descripcion', 'monto', 'nit_cliente']]
            no_conciliadas_export.to_excel(writer, sheet_name='No_Conciliadas', index=False)
        else:
            pd.DataFrame({'Mensaje': ['Todas las transacciones fueron conciliadas']}).to_excel(writer, sheet_name='No_Conciliadas', index=False)
        
        # 3. Hoja de resumen estadístico
        resumen = {
            'Total movimientos': len(conciliacion_df),
            'Conciliadas': conciliacion_df['conciliado'].sum(),
            'No conciliadas': len(conciliacion_df) - conciliacion_df['conciliado'].sum(),
            'Porcentaje conciliación': f"{conciliacion_df['conciliado'].mean() * 100:.2f}%"
        }
        pd.DataFrame([resumen]).to_excel(writer, sheet_name='Resumen', index=False)
    
    print(f"📊 Reporte de conciliación guardado en: {nombre_archivo}")

# ------------------------------------------------------------
# 7. (MODIFICADA) FLUJO PRINCIPAL DE CONCILIACIÓN
# ------------------------------------------------------------
def ejecutar_conciliacion(movimientos: pd.DataFrame, config: ConfiguracionAutomatizacion) -> Dict:
    """
    Orquesta la conciliación: obtiene token, facturas (emitidas y recibidas), cruza,
    actualiza facturas y genera Excel.
    """
    # 1. Obtener token
    token = obtener_token_siigo(config.siigo_username, config.siigo_access_key)
    
    # 2. Obtener facturas pendientes de venta (emitidas) y compra (recibidas)
    facturas_emitidas = obtener_facturas_pendientes(
        token, 
        config.siigo_partner_id, 
        tipos_documento=config.tipos_factura_emitidas
    )
    facturas_recibidas = obtener_facturas_pendientes(
        token, 
        config.siigo_partner_id, 
        tipos_documento=config.tipos_factura_recibidas
    )
    print(f"📄 Facturas pendientes emitidas (ventas): {len(facturas_emitidas)}")
    print(f"📄 Facturas pendientes recibidas (compras): {len(facturas_recibidas)}")
    
    # 3. Conciliar movimientos con ambos conjuntos
    conciliacion_df = conciliar_facturas(movimientos, facturas_emitidas, facturas_recibidas)
    
    # 4. Actualizar facturas conciliadas (marcar como pagadas)
    actualizadas = 0
    for _, row in conciliacion_df.iterrows():
        if row['conciliado'] and row['factura_id']:
            factura_id = row['factura_id']
            fecha_mov = row['movimiento']['fecha'].strftime('%Y-%m-%d')
            idempotency_key = hashlib.sha256(f"{factura_id}{fecha_mov}".encode()).hexdigest()[:30]
            ok = marcar_factura_pagada(token, config.siigo_partner_id, factura_id, fecha_mov, idempotency_key)
            if ok:
                actualizadas += 1
                print(f"✅ Factura {factura_id} marcada como pagada.")
            else:
                print(f"⚠️ Falló actualización de factura {factura_id}")
    
    # 5. Generar Excel con detalle
    generar_reporte_excel(conciliacion_df, f"reporte_conciliacion_{datetime.now().strftime('%Y%m%d')}.xlsx")
    
    # 6. Resumen final
    resumen = {
        'total_movimientos': len(movimientos),
        'facturas_pendientes_emitidas': len(facturas_emitidas),
        'facturas_pendientes_recibidas': len(facturas_recibidas),
        'conciliaciones_exitosas': conciliacion_df['conciliado'].sum(),
        'facturas_actualizadas': actualizadas,
        'tasa_conciliacion': f"{conciliacion_df['conciliado'].mean() * 100:.2f}%"
    }
    return resumen

# ------------------------------------------------------------
# 8. MARCAR FACTURA PAGADA (sin cambios, pero la incluyo por completitud)
# ------------------------------------------------------------
def marcar_factura_pagada(token: str, partner_id: str, factura_id: str, fecha_pago: str, idempotency_key: str) -> bool:
    # ... (igual que antes)
    pass

# ------------------------------------------------------------
# EJEMPLO DE USO
# ------------------------------------------------------------
if __name__ == "__main__":
    # Simulación de movimientos (ingresos y egresos)
    df_movimientos = pd.DataFrame({
        'fecha': [datetime(2026, 7, 10), datetime(2026, 7, 12), datetime(2026, 7, 15)],
        'monto': [-1500000, 2500000, -800000],  # Egreso, ingreso, egreso
        'nit_cliente': ['800123456-0', '900987654-1', None],
        'descripcion': ['Pago factura 123 - Protoquímica', 'Pago de Frutesa', 'Compra en Tecna']
    })
    
    resumen = ejecutar_conciliacion(df_movimientos, config)
    print("\n📊 RESUMEN DE CONCILIACIÓN")
    for k, v in resumen.items():
        print(f"{k}: {v}")