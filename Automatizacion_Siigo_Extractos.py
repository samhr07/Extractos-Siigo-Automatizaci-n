import pandas as pd
import re

# ------------------------------------------------------------
# 1. DICCIONARIO DE EMPLEADOS CON SUS NÚMEROS
#    (Nequi: números de celular de 10 dígitos; Bancolombia: números de cuenta de 11 dígitos)
# ------------------------------------------------------------
EMPLEADOS = {
    "William": {"numero": "3182309554", "banco": "Nequi", "tipo": "celular"},
    "Diana": {"numero": "3133761278", "banco": "Nequi", "tipo": "celular"},
    "Mabel": {"numero": "3105477761", "banco": "Nequi", "tipo": "celular"},
    "Hugo": {
        "numero": "16132028650",  # Nota: tiene 11 dígitos, cuenta Bancolombia
        "banco": "Bancolombia",
        "tipo": "cuenta",
    },
    "Natalia": {
        "numero": "10065329940",  # 11 dígitos
        "banco": "Bancolombia",
        "tipo": "cuenta",
    },
}


# ------------------------------------------------------------
# 2. FUNCIÓN PARA IDENTIFICAR EL EMPLEADO A PARTIR DE LA DESCRIPCIÓN
# ------------------------------------------------------------
def identificar_empleado(descripcion, monto, banco_origen=None):
    """
    Busca en la descripción si aparece algún número de empleado (celular o cuenta).
    Retorna el nombre del empleado si encuentra coincidencia, o None si no.
    Además, se fija en el banco_origen para filtrar (opcional).
    """
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return None

    desc_lower = descripcion.lower()

    # Recorremos todos los empleados
    for nombre, datos in EMPLEADOS.items():
        numero = datos["numero"]
        # Opcional: filtrar por banco_origen si se proporciona
        if banco_origen and datos["banco"].lower() != banco_origen.lower():
            continue  # Si el banco no coincide, saltamos

        # Buscar el número en la descripción (puede estar con o sin espacios, guiones, etc.)
        # Normalizamos: eliminamos espacios, guiones, puntos del número en la descripción
        desc_limpia = re.sub(r"[\s\-\.]", "", desc_lower)
        numero_limpio = numero  # ya está sin espacios

        # Búsqueda directa
        if numero_limpio in desc_limpia:
            return nombre

        # También buscamos el nombre del empleado (por si acaso)
        if nombre.lower() in desc_lower:
            return nombre

    return None


# ------------------------------------------------------------
# 3. APLICACIÓN AL DATAFRAME
# ------------------------------------------------------------
# Suponemos que df tiene columnas: 'descripcion', 'monto', 'fecha' y 'banco_origen' (opcional)
# Si no tienes 'banco_origen', puedes omitirlo en la llamada.

# Aplicar identificación
df["empleado"] = df.apply(
    lambda row: identificar_empleado(
        row["descripcion"],
        row["monto"],
        row.get("banco_origen", None),  # Si no existe, pasa None
    ),
    axis=1,
)

# Marcar como nómina solo si el monto es negativo (egreso) y se encontró empleado
df["categoria"] = df.apply(
    lambda row: (
        "Nómina"
        if (row["empleado"] is not None and row["monto"] < 0)
        else row.get("categoria", "Otros")
    ),
    axis=1,
)

# ------------------------------------------------------------
# 4. GENERAR INFORME DE NÓMINA
# ------------------------------------------------------------
# Filtrar solo transacciones de nómina (egresos)
nomina_df = df[(df["categoria"] == "Nómina") & (df["monto"] < 0)].copy()
nomina_df["monto_abs"] = nomina_df["monto"].abs()  # Convertir a positivo para análisis

if not nomina_df.empty:
    # Agrupar por empleado
    reporte_nomina = (
        nomina_df.groupby("empleado")
        .agg(
            total_pagado=("monto_abs", "sum"),
            num_pagos=("monto_abs", "count"),
            promedio_pago=("monto_abs", "mean"),
            ultimo_pago=("fecha", "max"),
            primer_pago=("fecha", "min"),
        )
        .reset_index()
        .sort_values("total_pagado", ascending=False)
    )

    print("📋 INFORME DE NÓMINA (Pagos identificados)")
    print("==========================================")
    print(reporte_nomina.to_string(index=False))

    # Exportar a Excel
    with pd.ExcelWriter("reporte_nomina.xlsx") as writer:
        reporte_nomina.to_excel(writer, sheet_name="Resumen Nómina", index=False)
        # Detalle de cada pago
        nomina_df[
            ["fecha", "descripcion", "monto", "empleado", "banco_origen"]
        ].to_excel(writer, sheet_name="Detalle Pagos", index=False)

    # ------------------------------------------------------------
    # 5. OPCIONAL: CONCILIACIÓN CON SALARIOS ESPERADOS (si tienes un archivo)
    # Si tienes un archivo con los salarios base (ej. Excel con columnas: empleado, salario_mensual),
    # puedes comparar.
    # ------------------------------------------------------------
    # Ejemplo de carga de salarios esperados (descomentar si existe)
    # salarios_esperados = pd.read_excel('salarios_esperados.xlsx')
    # comparativa = reporte_nomina.merge(salarios_esperados, on='empleado', how='outer')
    # comparativa['diferencia'] = comparativa['total_pagado'] - comparativa['salario_mensual']
    # print("\n🔍 Comparativa con salarios esperados:")
    # print(comparativa[['empleado', 'total_pagado', 'salario_mensual', 'diferencia']])

else:
    print("⚠️ No se encontraron pagos de nómina en el período.")

# ------------------------------------------------------------
# 6. ADICIONAL: VISUALIZAR LAS TRANSACCIONES IDENTIFICADAS
# ------------------------------------------------------------
# Mostrar las primeras filas identificadas
print("\n📌 Ejemplos de pagos de nómina identificados:")
print(
    nomina_df[["fecha", "descripcion", "monto", "empleado"]]
    .head(10)
    .to_string(index=False)
)
