import pandas as pd
import os
from datetime import datetime
import hashlib


# ------------------------------------------------------------
# CONFIGURACIÓN DE EXCEPCIONES
# ------------------------------------------------------------
class ConfiguracionExcepciones:
    # Ruta donde se guardarán los archivos de revisión
    directorio_revision: str = "./cola_revision/"
    # Umbral de confianza para clasificación (punto #1)
    umbral_clasificacion: int = 70
    # Archivo de configuración para reintentos
    archivo_reintentos: str = "reintentos_pendientes.xlsx"


config_exc = ConfiguracionExcepciones()


# ------------------------------------------------------------
# 1. DETECCIÓN DE EXCEPCIONES
# ------------------------------------------------------------
def detectar_excepciones(df: pd.DataFrame, reglas: dict = None) -> pd.DataFrame:
    """
    Identifica transacciones que requieren revisión humana.

    Criterios de excepción:
    - Categoría 'Otros' o 'Sin Clasificar' (punto #1)
    - No conciliadas con factura (punto #8)
    - Monto atípico (opcional)
    - Faltan datos críticos (NIT, descripción, etc.)

    Args:
        df: DataFrame con transacciones (debe tener columnas: 'categoria', 'conciliado', 'monto', etc.)
        reglas: Diccionario opcional con reglas adicionales.

    Returns:
        DataFrame con las transacciones que son excepción.
    """
    # Asegurar que las columnas existan
    condiciones = []

    # 1. Categoría no definida (del punto #1)
    if "categoria" in df.columns:
        condiciones.append(
            df["categoria"].isin(["Otros", "Sin Clasificar", "No Definida"])
        )

    # 2. No conciliadas con factura (del punto #8)
    if "conciliado" in df.columns:
        condiciones.append(df["conciliado"] == False)

    # 3. Monto extremo (opcional: fuera de 3 desviaciones estándar)
    if "monto" in df.columns:
        mean = df["monto"].mean()
        std = df["monto"].std()
        if std > 0:
            condiciones.append(
                (df["monto"] > mean + 3 * std) | (df["monto"] < mean - 3 * std)
            )

    # 4. Faltan datos críticos
    if "nit_cliente" in df.columns:
        condiciones.append(df["nit_cliente"].isna())
    if "descripcion" in df.columns:
        condiciones.append(df["descripcion"].str.len() < 5)

    # Combinar condiciones con OR (cualquier condición se considera excepción)
    if condiciones:
        mascara_excepcion = pd.concat(condiciones, axis=1).any(axis=1)
    else:
        mascara_excepcion = pd.Series([False] * len(df))

    return df[mascara_excepcion].copy()


# ------------------------------------------------------------
# 2. GENERAR ARCHIVO PARA REVISIÓN HUMANA (EXCEL)
# ------------------------------------------------------------
def generar_cola_revision(
    df_excepciones: pd.DataFrame, nombre_archivo: str = None, directorio: str = None
) -> str:
    """
    Exporta las excepciones a un archivo Excel editable.
    Incluye columnas adicionales para que el humano pueda corregir:
    - categoria_corregida
    - nit_corregido
    - conciliado_manual
    - observaciones

    Returns:
        Ruta del archivo generado.
    """
    if directorio is None:
        directorio = config_exc.directorio_revision

    # Crear directorio si no existe
    os.makedirs(directorio, exist_ok=True)

    if nombre_archivo is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"cola_revision_{timestamp}.xlsx"

    ruta_completa = os.path.join(directorio, nombre_archivo)

    # Copiar DataFrame y agregar columnas para corrección manual
    df_revision = df_excepciones.copy()

    # Añadir columnas vacías para que el humano llene
    df_revision["categoria_corregida"] = ""
    df_revision["nit_corregido"] = ""
    df_revision["conciliado_manual"] = False
    df_revision["observaciones"] = ""
    df_revision["revisado"] = False

    # Añadir un hash de la fila para trazabilidad
    df_revision["hash_fila"] = df_revision.apply(
        lambda row: hashlib.md5(str(row.to_dict()).encode()).hexdigest()[:8], axis=1
    )

    # Guardar a Excel
    with pd.ExcelWriter(ruta_completa, engine="openpyxl") as writer:
        df_revision.to_excel(writer, sheet_name="Excepciones", index=False)

        # Añadir hoja de instrucciones
        instrucciones = pd.DataFrame(
            {
                "Instrucciones": [
                    "1. Revisa cada transacción marcada como excepción.",
                    '2. Corrige la categoría en la columna "categoria_corregida".',
                    '3. Si conoces el NIT, escríbelo en "nit_corregido".',
                    '4. Marca "conciliado_manual" como TRUE si ya fue conciliado.',
                    "5. Añade observaciones si es necesario.",
                    '6. Marca "revisado" como TRUE cuando termines.',
                    "7. Guarda el archivo y ejecuta el script de reintento.",
                ]
            }
        )
        instrucciones.to_excel(writer, sheet_name="Instrucciones", index=False)

    print(f"📋 Cola de revisión generada en: {ruta_completa}")
    print(f"   Transacciones pendientes: {len(df_revision)}")
    return ruta_completa


# ------------------------------------------------------------
# 3. FUNCIÓN DE REINTENTO (PROCESAR CORRECCIONES HUMANAS)
# ------------------------------------------------------------
def procesar_reintentos(
    archivo_revision: str, df_original: pd.DataFrame, funcion_procesamiento: callable
) -> dict:
    """
    Lee el archivo Excel corregido por el humano y procesa las transacciones.

    Args:
        archivo_revision: Ruta del Excel con correcciones.
        df_original: DataFrame original con todas las transacciones.
        funcion_procesamiento: Función que recibe una fila corregida y la procesa
                               (ej. crea comprobante en Siigo, actualiza factura, etc.)

    Returns:
        Diccionario con estadísticas del reintento.
    """
    if not os.path.exists(archivo_revision):
        return {"error": f"Archivo no encontrado: {archivo_revision}"}

    # Cargar el archivo corregido
    df_revision = pd.read_excel(archivo_revision, sheet_name="Excepciones")

    # Filtrar solo las filas que fueron revisadas
    df_revisadas = df_revision[df_revision["revisado"] == True].copy()

    if df_revisadas.empty:
        return {
            "total_revisadas": 0,
            "procesadas": 0,
            "errores": 0,
            "mensaje": "No hay transacciones marcadas como revisadas.",
        }

    resultados = {
        "total_revisadas": len(df_revisadas),
        "procesadas": 0,
        "errores": 0,
        "detalle_errores": [],
    }

    # Procesar cada fila corregida
    for idx, row in df_revisadas.iterrows():
        try:
            # Buscar la transacción original (usando hash o algún identificador)
            # En este ejemplo, usamos el hash_fila
            hash_fila = row.get("hash_fila")
            if hash_fila:
                # Buscar en el DataFrame original (podrías tenerlo guardado)
                # Aquí simulamos que funcion_procesamiento recibe la fila corregida
                resultado = funcion_procesamiento(row)
                if resultado.get("exito", False):
                    resultados["procesadas"] += 1
                else:
                    resultados["errores"] += 1
                    resultados["detalle_errores"].append(
                        {
                            "fila": idx,
                            "error": resultado.get("mensaje", "Error desconocido"),
                        }
                    )
            else:
                # Si no hay hash, intentar por otros campos (fecha, monto, descripción)
                # Esto es menos robusto pero puede funcionar
                # ...
                pass
        except Exception as e:
            resultados["errores"] += 1
            resultados["detalle_errores"].append({"fila": idx, "error": str(e)})

    # Generar reporte del reintento
    generar_reporte_reintento(resultados, archivo_revision)

    return resultados


# ------------------------------------------------------------
# 4. GENERAR REPORTE DEL REINTENTO
# ------------------------------------------------------------
def generar_reporte_reintento(resultados: dict, archivo_original: str):
    """
    Genera un pequeño reporte en TXT con los resultados del reintento.
    """
    nombre_reporte = f"reporte_reintento_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(nombre_reporte, "w") as f:
        f.write("=== REPORTE DE REINTENTO ===\n")
        f.write(f"Archivo revisado: {archivo_original}\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(
            f"Total transacciones revisadas: {resultados.get('total_revisadas', 0)}\n"
        )
        f.write(f"Procesadas exitosamente: {resultados.get('procesadas', 0)}\n")
        f.write(f"Errores: {resultados.get('errores', 0)}\n")

        if resultados.get("detalle_errores"):
            f.write("\n--- DETALLE DE ERRORES ---\n")
            for err in resultados["detalle_errores"]:
                f.write(
                    f"Fila {err.get('fila', 'N/A')}: {err.get('error', 'Sin detalle')}\n"
                )

    print(f"📄 Reporte de reintento generado: {nombre_reporte}")


# ------------------------------------------------------------
# 5. FUNCIÓN DE PROCESAMIENTO DE UNA FILA CORREGIDA (EJEMPLO)
# ------------------------------------------------------------
def procesar_fila_corregida(fila_corregida: pd.Series, config: dict) -> dict:
    """
    Esta función recibe una fila corregida y la procesa.
    Debes adaptarla a tu lógica específica (crear comprobante, actualizar factura, etc.)
    """
    try:
        # Extraer datos corregidos
        categoria = fila_corregida.get("categoria_corregida", "")
        nit = fila_corregida.get("nit_corregido", "")
        conciliado = fila_corregida.get("conciliado_manual", False)

        # Aquí iría la lógica de:
        # - Actualizar la categoría en la base de datos local
        # - Si tiene NIT, buscar/crear el tercero en Siigo
        # - Si está conciliado manualmente, marcar la factura como pagada
        # - Reintentar la creación del comprobante en Siigo

        # Simulación:
        print(f"🔄 Procesando fila: {fila_corregida.get('hash_fila')}")
        print(f"   Categoría corregida: {categoria}")
        print(f"   NIT corregido: {nit}")

        # Ejemplo: Si la categoría ahora es válida, la procesamos
        if categoria and categoria != "Otros":
            # Llamar a la función de creación de comprobante (punto #3)
            # resultado = crear_comprobante_siigo(fila_corregida)
            return {"exito": True, "mensaje": "Procesado correctamente"}
        else:
            return {"exito": False, "mensaje": "Categoría no válida"}

    except Exception as e:
        return {"exito": False, "mensaje": str(e)}


# ------------------------------------------------------------
# 6. INTEGRACIÓN CON EL FLUJO PRINCIPAL (PUNTO #8 Y #10)
# ------------------------------------------------------------
def integrar_cola_revision(
    df: pd.DataFrame,
    errores_globales: list,
    resumen_global: dict,
    config_exc: ConfiguracionExcepciones = None,
) -> dict:
    """
    Función de integración que une el punto #11 con los puntos #8 y #10.

    Args:
        df: DataFrame con todas las transacciones procesadas.
        errores_globales: Lista de errores acumulados (del punto #10).
        resumen_global: Diccionario con el resumen del proceso.
        config_exc: Configuración de excepciones.

    Returns:
        Diccionario con el estado de la cola de revisión.
    """
    if config_exc is None:
        config_exc = ConfiguracionExcepciones()

    # 1. Detectar excepciones en el DataFrame (integración con #1 y #8)
    df_excepciones = detectar_excepciones(df)

    if df_excepciones.empty:
        print("✅ No se detectaron excepciones. Todo procesado correctamente.")
        return {"tiene_excepciones": False, "cantidad": 0, "archivo": None}

    # 2. Si hay excepciones, generar archivo de revisión
    print(
        f"⚠️ Se detectaron {len(df_excepciones)} excepciones. Generando cola de revisión..."
    )
    archivo_revision = generar_cola_revision(df_excepciones)

    # 3. Agregar a la lista de errores (para notificación #10)
    errores_globales.append(
        {
            "entidad": "Sistema",
            "motivo": f"Se generaron {len(df_excepciones)} excepciones para revisión humana",
            "detalle": f"Revisar archivo: {archivo_revision}",
        }
    )

    # 4. Actualizar el resumen global (para #10)
    resumen_global["excepciones_pendientes"] = len(df_excepciones)
    resumen_global["archivo_revision"] = archivo_revision

    # 5. Retornar información de la cola
    return {
        "tiene_excepciones": True,
        "cantidad": len(df_excepciones),
        "archivo": archivo_revision,
        "mensaje": f"Se generó cola de revisión con {len(df_excepciones)} transacciones",
    }


# ------------------------------------------------------------
# EJEMPLO DE USO INTEGRADO
# ------------------------------------------------------------
if __name__ == "__main__":
    # Simulación de DataFrame con transacciones (de los puntos #1 y #8)
    df_ejemplo = pd.DataFrame(
        {
            "fecha": ["2026-07-10", "2026-07-12", "2026-07-15"],
            "descripcion": [
                "Pago a Protoquímica",
                "Ingreso Frutesa",
                "Compra desconocida",
            ],
            "monto": [-1500000, 2500000, -800000],
            "categoria": ["Inorgánicos", "Ventas", "Otros"],  # <-- Una excepción
            "conciliado": [True, True, False],  # <-- Otra excepción
            "nit_cliente": ["800123456-0", "900987654-1", None],  # <-- Otra excepción
        }
    )

    # Inicializar listas globales (integración con #10)
    errores_globales = []
    resumen_global = {"total_movimientos": len(df_ejemplo)}

    # Ejecutar integración del punto #11
    resultado_cola = integrar_cola_revision(
        df_ejemplo, errores_globales, resumen_global
    )

    print("\n📊 Resultado de integración:")
    print(resultado_cola)

    # Verificar que los errores se hayan añadido (para #10)
    print("\n📋 Errores globales acumulados:")
    for err in errores_globales:
        print(f"  - {err.get('entidad')}: {err.get('motivo')}")

    print("\n📊 Resumen global actualizado:")
    print(resumen_global)
