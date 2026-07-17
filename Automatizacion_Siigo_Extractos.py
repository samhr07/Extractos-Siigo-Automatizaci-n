import pandas as pd
import re

# ------------------------------------------------------------
# 1. CONFIGURACIÓN
# ------------------------------------------------------------
TASA_GMF = 0.004  # 4x1000 (0.4%)
UMBRAL_DISCREPANCIA = 0.50  # Si la diferencia supera $0.50, generamos alerta


# ------------------------------------------------------------
# 2. FUNCIONES DE DETECCIÓN Y CÁLCULO
# ------------------------------------------------------------
def es_transaccion_gmf(descripcion):
    """
    Detecta si una transacción es un cargo por GMF basado en palabras clave.
    """
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return False
    desc_lower = descripcion.lower()
    patrones_gmf = [r"4x1000", r"4\s*x\s*1000", r"gmf", r"gravamen", r"impuesto\s*4"]
    for patron in patrones_gmf:
        if re.search(patron, desc_lower):
            return True
    return False


def calcular_gmf_esperado(monto_retiro):
    """
    Calcula el GMF esperado (0.4%) sobre un monto de retiro.
    El resultado se redondea a 2 decimales.
    """
    if monto_retiro >= 0:
        return 0.0  # Solo aplica a retiros (montos negativos)
    # Tomamos el valor absoluto y aplicamos tasa
    return round(abs(monto_retiro) * TASA_GMF, 2)


def extraer_gmf_real(descripcion):
    """
    Intenta extraer el monto del GMF directamente de la descripción.
    Busca patrones como: "GMF $X.XX" o "4x1000 $X.XX"
    """
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return None
    desc_lower = descripcion.lower()
    # Patrones: número con punto decimal precedido de $ o GMF
    patrones = [
        r"(?:gmf|4x1000|gravamen).*?(\d+\.\d{2})",
        r"(?:valor|monto).*?(\d+\.\d{2})",  # menos preciso, pero captura
    ]
    for patron in patrones:
        match = re.search(patron, desc_lower)
        if match:
            return float(match.group(1))
    return None


def clasificar_y_calcular_gmf(row):
    """
    Aplica la lógica completa a cada transacción.
    Retorna un diccionario con:
    - es_gmf: bool
    - gmf_real: float (extraído de descripción) o None
    - gmf_esperado: float (calculado)
    - diferencia: float
    """
    monto = row["monto"]
    descripcion = row.get("descripcion", "")

    # Solo procesamos egresos (retiros)
    if monto >= 0:
        return {
            "es_gmf": False,
            "gmf_real": None,
            "gmf_esperado": None,
            "diferencia": None,
        }

    # Calcular GMF esperado
    gmf_esperado = calcular_gmf_esperado(monto)

    # Detectar si la descripción indica GMF
    es_gmf = es_transaccion_gmf(descripcion)

    # Intentar extraer GMF real
    gmf_real = extraer_gmf_real(descripcion) if es_gmf else None

    # Si es GMF pero no se extrajo el monto, podemos usar el esperado como real (para alerta)
    if es_gmf and gmf_real is None:
        gmf_real = gmf_esperado

    # Calcular diferencia (solo si ambos existen)
    if gmf_real is not None and gmf_esperado is not None:
        diferencia = round(gmf_real - gmf_esperado, 2)
    else:
        diferencia = None

    return {
        "es_gmf": es_gmf,
        "gmf_real": gmf_real,
        "gmf_esperado": gmf_esperado,
        "diferencia": diferencia,
    }


# ------------------------------------------------------------
# 3. APLICACIÓN AL DATAFRAME
# ------------------------------------------------------------
# Suponemos que df tiene columnas: 'descripcion' y 'monto'
# df = pd.read_csv('tus_extractos.csv')  # <-- Descomenta y ajusta

# Aplicar función a cada fila
resultados_gmf = df.apply(clasificar_y_calcular_gmf, axis=1)
df_gmf = pd.DataFrame(resultados_gmf.tolist(), index=df.index)

# Unir al DataFrame original
df = pd.concat([df, df_gmf], axis=1)

# ------------------------------------------------------------
# 4. CLASIFICACIÓN AUTOMÁTICA COMO IMPUESTO
#    (Consistente con el punto #1)
# ------------------------------------------------------------
# Si es GMF (real o detectado) y ya tiene categoría, la reemplazamos por "Impuestos"
mask_gmf = df["es_gmf"] == True
df.loc[mask_gmf, "categoria"] = "Impuestos"
# Si no estaba como GMF pero el gmf_esperado > 0 y la descripción tiene palabras clave, también
mask_por_calculo = (df["gmf_esperado"] > 0) & (
    df["descripcion"].str.contains("4x1000|gmf|gravamen", case=False, na=False)
)
df.loc[mask_por_calculo, "categoria"] = "Impuestos"

# ------------------------------------------------------------
# 5. GENERAR ALERTAS POR DISCREPANCIAS
# ------------------------------------------------------------
discrepancias = df[
    (df["diferencia"].notna()) & (abs(df["diferencia"]) > UMBRAL_DISCREPANCIA)
].copy()

if not discrepancias.empty:
    print("⚠️ ALERTA: Discrepancias en GMF detectadas (diferencia > $0.50)")
    print("============================================================")
    print(
        discrepancias[
            ["fecha", "descripcion", "monto", "gmf_real", "gmf_esperado", "diferencia"]
        ].to_string(index=False)
    )

    # Guardar reporte detallado
    with pd.ExcelWriter("alertas_gmf.xlsx") as writer:
        discrepancias[
            [
                "fecha",
                "descripcion",
                "monto",
                "gmf_real",
                "gmf_esperado",
                "diferencia",
                "categoria",
            ]
        ].to_excel(writer, sheet_name="Discrepancias GMF", index=False)
        # También guardamos todas las transacciones de GMF para referencia
        df[df["es_gmf"] | mask_por_calculo][
            ["fecha", "descripcion", "monto", "gmf_real", "gmf_esperado", "diferencia"]
        ].to_excel(writer, sheet_name="Todos los GMF", index=False)
    print(f"✅ Reporte de discrepancias guardado en 'alertas_gmf.xlsx'")
else:
    print("✅ No se encontraron discrepancias significativas en el GMF.")

# ------------------------------------------------------------
# 6. VISUALIZACIÓN RÁPIDA (Opcional)
# ------------------------------------------------------------
print("\n📊 Resumen de cargos por GMF (calculados vs reales)")
resumen_gmf = df[df["gmf_esperado"] > 0].copy()
if not resumen_gmf.empty:
    resumen_gmf["gmf_calculado_total"] = resumen_gmf["gmf_esperado"].sum()
    resumen_gmf["gmf_real_total"] = (
        resumen_gmf["gmf_real"].fillna(resumen_gmf["gmf_esperado"]).sum()
    )
    print(
        f"Total GMF calculado (0.4% sobre retiros): ${resumen_gmf['gmf_esperado'].sum():.2f}"
    )
    print(
        f"Total GMF real (según extractos):       ${resumen_gmf['gmf_real'].fillna(resumen_gmf['gmf_esperado']).sum():.2f}"
    )
    print(
        f"Diferencia total:                        ${(resumen_gmf['gmf_real'].fillna(resumen_gmf['gmf_esperado']).sum() - resumen_gmf['gmf_esperado'].sum()):.2f}"
    )
