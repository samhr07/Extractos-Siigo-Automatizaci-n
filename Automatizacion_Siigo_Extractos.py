import pandas as pd
import re
from thefuzz import process, fuzz

# ------------------------------------------------------------
# 1. LISTA DE PROVEEDORES CONOCIDOS (con variantes)
#    Se incluyen los que mencionaste + los que se infieren de la info anterior
# ------------------------------------------------------------
PROVEEDORES_CONOCIDOS = [
    "protoquimica",  # Calcio, magnesio, potasio
    "tecna",  # Extracto de levadura
    "incodi",  # Unidades de envase, cristalería
    "ara",  # Supermercado
    "d1",  # Supermercado
    "exito",  # Supermercado
    "frutesa",  # Cliente que paga quincenalmente (ingresos)
    "wompi",  # Pasarela de pagos (posible)
    "bancolombia",  # Comisiones bancarias
    "nequi",  # Comisiones
    "nu",  # Comisiones
]


# ------------------------------------------------------------
# 2. FUNCIÓN PRINCIPAL DE EXTRACCIÓN DE PROVEEDOR
# ------------------------------------------------------------
def extraer_proveedor(descripcion, monto):
    """
    Extrae el nombre del proveedor/lugar de compra a partir de la descripción.
    Para egresos (monto < 0) busca proveedores de compra.
    Para ingresos (monto > 0) detecta si es Frutesa u otro cliente.
    Retorna el nombre del proveedor o "Desconocido" si no encuentra.
    """
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return "Desconocido"

    desc_lower = descripcion.lower()
    es_egreso = monto < 0  # Monto negativo indica compra o gasto
    es_ingreso = monto > 0  # Monto positivo indica ingreso

    # ------------------------------------------------------------
    # A. ESTRATEGIA 1: Coincidencia difusa con proveedores conocidos
    # ------------------------------------------------------------
    # Buscamos el mejor match dentro de la lista de proveedores
    # Usamos partial_ratio para capturar "PROTOQUIMICA" dentro de "PAGO A PROTOQUIMICA"
    mejor_match = process.extractOne(
        desc_lower, PROVEEDORES_CONOCIDOS, scorer=fuzz.partial_ratio
    )

    if mejor_match and mejor_match[1] >= 80:
        proveedor = mejor_match[0]
        # Si es ingreso y el proveedor es "frutesa", lo dejamos; si es otro, podría ser cliente.
        if es_ingreso and proveedor != "frutesa":
            # Para ingresos, si no es Frutesa, podría ser otro cliente, pero para este informe
            # de compras solo nos interesa egresos. De todas formas, lo etiquetamos.
            return f"Cliente: {proveedor.title()}"
        elif es_egreso:
            # Para egresos, devolvemos el proveedor con formato título
            return proveedor.title()
        else:
            return proveedor.title()

    # ------------------------------------------------------------
    # B. ESTRATEGIA 2: Patrones comunes en descripciones de compras
    # ------------------------------------------------------------
    # Buscamos patrones como: "PAGO A ...", "COMPRA EN ...", "TRANSFERENCIA A ..."
    # Solo aplica a egresos (compras)
    if es_egreso:
        patrones = [
            r"(?:pago\s*a\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
            r"(?:compra\s*en\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
            r"(?:transferencia\s*a\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
            r"(?:pago\s*proveedor\s*)([a-záéíóúñ\s]+?)(?:\s*ref|\s*$|\.|,)",
        ]
        for patron in patrones:
            match = re.search(patron, desc_lower)
            if match:
                proveedor_extraido = match.group(1).strip()
                # Limpiamos posibles palabras sobrantes
                proveedor_extraido = re.sub(r"\s+ref\s+\d+", "", proveedor_extraido)
                if len(proveedor_extraido) > 2 and proveedor_extraido not in [
                    "pago",
                    "compra",
                    "transferencia",
                ]:
                    return proveedor_extraido.title()

    # ------------------------------------------------------------
    # C. ESTRATEGIA 3: Inferencia a partir de palabras clave (usando el diccionario del punto #1)
    #    Si la descripción contiene "extracto levadura", deducimos "Tecna"
    #    Si contiene "calcio", deducimos "Protoquímica", etc.
    # ------------------------------------------------------------
    if es_egreso:
        # Mapeo de palabras clave a proveedores (basado en la info que me diste)
        mapa_keyword_proveedor = {
            "protoquimica": "Protoquímica",
            "calcio": "Protoquímica",
            "magnesio": "Protoquímica",
            "potasio": "Protoquímica",
            "costal": "Protoquímica",
            "tecna": "Tecna",
            "levadura": "Tecna",
            "incodi": "Incodi",
            "envase": "Incodi",
            "cristalería": "Incodi",
            "ara": "Supermercado Ara",
            "d1": "Supermercado D1",
            "exito": "Supermercado Éxito",
            "panela": "Supermercado",
            "alcohol": "Proveedor Químico",
            "hipoclorito": "Proveedor Químico",
            "ozono": "Proveedor Químico",
        }
        for keyword, proveedor in mapa_keyword_proveedor.items():
            if keyword in desc_lower:
                return proveedor

    # ------------------------------------------------------------
    # D. ESTRATEGIA 4: Para ingresos, detectar Frutesa (si no se capturó antes)
    # ------------------------------------------------------------
    if es_ingreso and ("frutesa" in desc_lower or "frut" in desc_lower):
        return "Frutesa (Ingreso)"

    # ------------------------------------------------------------
    # E. Si no se pudo extraer nada
    # ------------------------------------------------------------
    return "Desconocido"


# ------------------------------------------------------------
# 3. APLICACIÓN AL DATAFRAME
# ------------------------------------------------------------
# Suponemos que df tiene columnas: 'descripcion' y 'monto'
# df = pd.read_csv('tus_extractos.csv')  # <-- Descomenta

# Aplicar extracción
df["proveedor"] = df.apply(
    lambda row: extraer_proveedor(row["descripcion"], row["monto"]), axis=1
)

# ------------------------------------------------------------
# 4. GENERAR INFORME DE LUGARES DE COMPRA (SOLO EGRESOS)
# ------------------------------------------------------------
# Filtramos solo las transacciones de egreso (compras)
compras_df = df[df["monto"] < 0].copy()

# Agrupamos por proveedor
reporte_proveedores = (
    compras_df.groupby("proveedor")
    .agg(
        total_comprado=("monto", lambda x: abs(x.sum())),  # Monto absoluto total
        num_compras=("monto", "count"),
        promedio_compra=("monto", lambda x: abs(x.mean())),
    )
    .reset_index()
    .sort_values("total_comprado", ascending=False)
)

# Agregamos columna de porcentaje sobre el total de compras
total_general = reporte_proveedores["total_comprado"].sum()
reporte_proveedores["%_participacion"] = (
    reporte_proveedores["total_comprado"] / total_general * 100
).round(2)

# ------------------------------------------------------------
# 5. VISUALIZACIÓN Y EXPORTACIÓN
# ------------------------------------------------------------
print("🏢 INFORME DE LUGARES DE COMPRA (PROVEEDORES)")
print("=============================================")
print(reporte_proveedores.to_string(index=False))

# Exportar a Excel para análisis
with pd.ExcelWriter("informe_proveedores.xlsx") as writer:
    reporte_proveedores.to_excel(writer, sheet_name="Proveedores", index=False)
    # Hoja adicional con todas las compras detalladas
    compras_df[["fecha", "descripcion", "monto", "proveedor"]].to_excel(
        writer, sheet_name="Detalle Compras", index=False
    )

# Además, si quieres ver proveedores en ingresos (ej. Frutesa)
ingresos_df = df[df["monto"] > 0].copy()
if not ingresos_df.empty:
    print("\n📈 CLIENTES QUE GENERAN INGRESOS:")
    clientes_report = (
        ingresos_df.groupby("proveedor")
        .agg(total_ingreso=("monto", "sum"), num_ingresos=("monto", "count"))
        .reset_index()
        .sort_values("total_ingreso", ascending=False)
    )
    print(clientes_report.to_string(index=False))
