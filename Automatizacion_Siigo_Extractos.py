import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import os
import json

# ------------------------------------------------------------
# 0. CONFIGURACIÓN INICIAL
# ------------------------------------------------------------
# Definir la canasta de productos para calcular inflación (basado en tus insumos clave)
CANASTA_INFLACION = [
    "calcio",  # Inorgánico
    "extracto levadura",  # Biocompuesto
    "panela",  # Materia prima
    "envase",  # Envases
    "salario",  # Para medir inflación salarial (se tomará el promedio de nómina)
]

# Ruta donde se guardarán los históricos (usaremos CSV para simplicidad)
HISTORICO_FILE = "historico_mensual.csv"
PRECIOS_FILE = "historico_precios.csv"


# ------------------------------------------------------------
# 1. CARGA O CREACIÓN DE HISTÓRICOS
# ------------------------------------------------------------
def cargar_historico():
    """Carga el histórico mensual de gastos por categoría desde CSV."""
    if os.path.exists(HISTORICO_FILE):
        return pd.read_csv(HISTORICO_FILE, parse_dates=["mes"])
    else:
        # Crear DataFrame vacío con columnas esperadas
        return pd.DataFrame(
            columns=["mes", "categoria", "total_monto", "num_transacciones"]
        )


def guardar_historico(df_historico):
    """Guarda el histórico mensual."""
    df_historico.to_csv(HISTORICO_FILE, index=False)


def cargar_precios_historicos():
    """Carga el histórico de precios de productos (para inflación)."""
    if os.path.exists(PRECIOS_FILE):
        return pd.read_csv(PRECIOS_FILE, parse_dates=["fecha"])
    else:
        return pd.DataFrame(columns=["producto", "fecha", "precio_unitario"])


def guardar_precios_historicos(df_precios):
    df_precios.to_csv(PRECIOS_FILE, index=False)


# ------------------------------------------------------------
# 2. ACTUALIZAR HISTÓRICO CON EL MES ACTUAL
# ------------------------------------------------------------
def actualizar_historico(df, mes_actual, año_actual):
    """
    Toma el DataFrame de transacciones del mes actual (con columna 'categoria' y 'monto'),
    calcula totales por categoría y los agrega al histórico.
    """
    # Crear columna de mes (primer día del mes)
    df["mes"] = pd.to_datetime(f"{año_actual}-{mes_actual:02d}-01")

    # Filtrar egresos (gastos) para el histórico de gastos
    gastos_df = df[df["monto"] < 0].copy()
    gastos_df["monto_abs"] = gastos_df["monto"].abs()

    # Agrupar por categoría
    resumen_mes = (
        gastos_df.groupby("categoria")
        .agg(total_monto=("monto_abs", "sum"), num_transacciones=("monto_abs", "count"))
        .reset_index()
    )
    resumen_mes["mes"] = df["mes"].iloc[0]  # asignar el mes

    # Cargar histórico existente
    historico = cargar_historico()

    # Eliminar registros del mismo mes (si ya existen) para evitar duplicados
    historico = historico[~(historico["mes"] == resumen_mes["mes"].iloc[0])]

    # Concatenar
    historico = pd.concat([historico, resumen_mes], ignore_index=True)

    # Guardar
    guardar_historico(historico)
    return historico


# ------------------------------------------------------------
# 3. ACTUALIZAR PRECIOS HISTÓRICOS (para inflación)
# ------------------------------------------------------------
def actualizar_precios(df):
    """
    Extrae precios unitarios de las transacciones de compra para productos de la canasta.
    Para simplificar, asumimos que cada compra tiene una cantidad = 1 unidad (si no hay dato).
    En realidad, necesitarías tener cantidad o precio unitario en el extracto.
    Como no lo tenemos, usaremos el monto total de la compra como precio de referencia
    para productos que aparecen en la canasta.
    """
    # Filtramos transacciones de compra (egresos) que contengan palabras de la canasta
    precios_df = cargar_precios_historicos()

    for producto in CANASTA_INFLACION:
        # Buscar en descripción (si existe)
        if producto == "salario":
            # Para salario, tomamos el promedio de los pagos de nómina del mes
            nomina_df = df[(df["categoria"] == "Nómina") & (df["monto"] < 0)]
            if not nomina_df.empty:
                # Promedio de pago por empleado (asumiendo que cada pago es un salario individual)
                # O también podríamos tomar el total pagado en nómina dividido por número de empleados
                salario_promedio = nomina_df["monto"].abs().mean()
                # Guardar como precio unitario para el mes actual
                nuevo_registro = pd.DataFrame(
                    {
                        "producto": ["salario"],
                        "fecha": [pd.Timestamp.now().replace(day=1)],
                        "precio_unitario": [salario_promedio],
                    }
                )
                precios_df = pd.concat([precios_df, nuevo_registro], ignore_index=True)
        else:
            # Buscar transacciones que contengan el producto en la descripción
            # Usamos el diccionario de palabras clave de puntos anteriores
            # Asumimos que el producto puede estar en la descripción
            patron = producto
            compras_producto = df[
                (df["monto"] < 0)
                & (df["descripcion"].str.contains(patron, case=False, na=False))
            ]
            if not compras_producto.empty:
                # Tomamos el precio unitario promedio (monto absoluto / cantidad)
                # Como no tenemos cantidad, asumimos 1 unidad por transacción
                # Si tienes cantidad, puedes ajustar aquí
                precio_promedio = compras_producto["monto"].abs().mean()
                nuevo_registro = pd.DataFrame(
                    {
                        "producto": [producto],
                        "fecha": [pd.Timestamp.now().replace(day=1)],
                        "precio_unitario": [precio_promedio],
                    }
                )
                precios_df = pd.concat([precios_df, nuevo_registro], ignore_index=True)

    # Eliminar duplicados (mismo producto y misma fecha)
    precios_df = precios_df.drop_duplicates(subset=["producto", "fecha"])
    guardar_precios_historicos(precios_df)
    return precios_df


# ------------------------------------------------------------
# 4. CALCULAR INFLACIÓN ESTIMADA SEMESTRAL
# ------------------------------------------------------------
def calcular_inflacion(precios_df, fecha_inicio=None, fecha_fin=None):
    """
    Calcula la inflación estimada para la canasta de productos entre el semestre actual
    y el semestre anterior (cada 6 meses).
    Retorna un DataFrame con producto, precio_semestre_anterior, precio_semestre_actual, inflacion_porcentual.
    """
    if precios_df.empty:
        return pd.DataFrame()

    # Asegurar que fecha sea datetime
    precios_df["fecha"] = pd.to_datetime(precios_df["fecha"])

    # Agrupar por semestre (año-semestre)
    precios_df["semestre"] = (
        precios_df["fecha"].dt.to_period("Q-DEC").dt.quarter
    )  # 1 o 2 trimestre, pero mejor usar semestre
    # Calcular semestre como (año*2 + (trimestre-1)//2 + 1) o más simple:
    precios_df["semestre_key"] = precios_df["fecha"].dt.year * 10 + precios_df[
        "fecha"
    ].dt.quarter.apply(lambda q: 1 if q <= 2 else 2)

    # Tomar el último precio de cada producto por semestre
    ultimos_precios = (
        precios_df.sort_values("fecha")
        .groupby(["producto", "semestre_key"])
        .last()
        .reset_index()
    )

    # Obtener los dos últimos semestres
    semestres_ordenados = sorted(ultimos_precios["semestre_key"].unique())
    if len(semestres_ordenados) < 2:
        return pd.DataFrame()  # No hay suficientes datos

    semestre_actual = semestres_ordenados[-1]
    semestre_anterior = (
        semestres_ordenados[-2] if len(semestres_ordenados) >= 2 else None
    )

    if semestre_anterior is None:
        return pd.DataFrame()

    # Filtrar precios para ambos semestres
    precios_anterior = ultimos_precios[
        ultimos_precios["semestre_key"] == semestre_anterior
    ]
    precios_actual = ultimos_precios[ultimos_precios["semestre_key"] == semestre_actual]

    # Merge para calcular inflación
    inflacion_df = pd.merge(
        precios_anterior[["producto", "precio_unitario"]],
        precios_actual[["producto", "precio_unitario"]],
        on="producto",
        suffixes=("_anterior", "_actual"),
    )

    inflacion_df["inflacion_porcentual"] = (
        (
            inflacion_df["precio_unitario_actual"]
            - inflacion_df["precio_unitario_anterior"]
        )
        / inflacion_df["precio_unitario_anterior"]
        * 100
    )

    # Inflación promedio de la canasta
    inflacion_promedio = inflacion_df["inflacion_porcentual"].mean()

    return inflacion_df, inflacion_promedio


# ------------------------------------------------------------
# 5. GENERAR DASHBOARD Y REPORTES
# ------------------------------------------------------------
def generar_dashboard(historico, df_mes_actual, inflacion_promedio=None):
    """
    Genera gráficos interactivos con Plotly y exporta a HTML y Excel.
    """
    # 5.1. Evolución de gastos por categoría (líneas)
    # Agrupar histórico por mes y categoría
    evolucion = (
        historico.groupby(["mes", "categoria"])
        .agg({"total_monto": "sum"})
        .reset_index()
    )

    fig1 = px.line(
        evolucion,
        x="mes",
        y="total_monto",
        color="categoria",
        title="Evolución de Gastos por Categoría (Mensual)",
        labels={
            "mes": "Mes",
            "total_monto": "Monto Total ($)",
            "categoria": "Categoría",
        },
    )

    # 5.2. Distribución de gastos del mes actual (pastel)
    gastos_mes = df_mes_actual[df_mes_actual["monto"] < 0].copy()
    gastos_mes["monto_abs"] = gastos_mes["monto"].abs()
    distribucion_mes = gastos_mes.groupby("categoria")["monto_abs"].sum().reset_index()
    fig2 = px.pie(
        distribucion_mes,
        values="monto_abs",
        names="categoria",
        title=f'Distribución de Gastos - {df_mes_actual["fecha"].iloc[0].strftime("%B %Y")}',
    )

    # 5.3. Comparativa ingresos vs gastos (barras apiladas mensuales)
    # Necesitamos también los ingresos por mes
    # Para simplificar, si df_mes_actual tiene ingresos, los agrupamos
    ingresos_mes = df_mes_actual[df_mes_actual["monto"] > 0].copy()
    if not ingresos_mes.empty:
        total_ingresos_mes = ingresos_mes["monto"].sum()
    else:
        total_ingresos_mes = 0
    total_gastos_mes = gastos_mes["monto_abs"].sum() if not gastos_mes.empty else 0

    # Para el histórico, agrupamos ingresos y gastos por mes (necesitaríamos tener ingresos en histórico)
    # Por ahora solo mostramos el mes actual
    fig3 = go.Figure(
        data=[
            go.Bar(
                name="Ingresos",
                x=[df_mes_actual["fecha"].iloc[0].strftime("%B %Y")],
                y=[total_ingresos_mes],
            ),
            go.Bar(
                name="Gastos",
                x=[df_mes_actual["fecha"].iloc[0].strftime("%B %Y")],
                y=[total_gastos_mes],
            ),
        ]
    )
    fig3.update_layout(title="Ingresos vs Gastos del Mes Actual", barmode="group")

    # 5.4. Tendencia de inflación (si tenemos datos)
    if inflacion_promedio is not None:
        fig4 = go.Figure()
        # Simulamos una línea de inflación mensual (asumiendo que la inflación semestral se aplica uniformemente)
        # Por ahora solo mostramos el valor actual como anotación
        fig4.add_annotation(
            text=f"Inflación estimada semestral: {inflacion_promedio:.2f}%",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=20),
        )
        fig4.update_layout(title="Inflación Estimada (Canasta de Insumos)")
    else:
        fig4 = go.Figure()
        fig4.add_annotation(
            text="No hay datos suficientes para calcular inflación",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
        fig4.update_layout(title="Inflación Estimada")

    # Guardar gráficos en HTML
    fig1.write_html("dashboard_evolucion_gastos.html")
    fig2.write_html("dashboard_distribucion_mes.html")
    fig3.write_html("dashboard_ingresos_gastos.html")
    fig4.write_html("dashboard_inflacion.html")

    # 5.5. Exportar a Excel con múltiples hojas
    with pd.ExcelWriter("reporte_ejecutivo.xlsx") as writer:
        # Histórico por categoría
        historico_export = historico.pivot_table(
            index="mes", columns="categoria", values="total_monto", aggfunc="sum"
        )
        historico_export.to_excel(writer, sheet_name="Histórico por Categoría")

        # Resumen del mes actual
        resumen_mes = (
            df_mes_actual.groupby("categoria")
            .agg(
                total_gasto=("monto", lambda x: abs(x[x < 0].sum())),
                total_ingreso=("monto", lambda x: x[x > 0].sum()),
                num_transacciones=("monto", "count"),
            )
            .reset_index()
        )
        resumen_mes.to_excel(writer, sheet_name="Resumen Mes Actual", index=False)

        # Si tenemos inflación
        if inflacion_promedio is not None:
            inflacion_df, _ = calcular_inflacion(cargar_precios_historicos())
            inflacion_df.to_excel(writer, sheet_name="Inflación Estimada", index=False)

    print("✅ Dashboards generados: HTMLs y reporte Excel.")
    return fig1, fig2, fig3, fig4


# ------------------------------------------------------------
# 6. FLUJO PRINCIPAL (EJEMPLO DE USO)
# ------------------------------------------------------------
# Suponiendo que ya tienes el DataFrame 'df' con las transacciones del mes actual
# df = pd.read_csv('extractos_mes.csv')

# Asegurar que df tiene columna 'fecha' (datetime)
# df['fecha'] = pd.to_datetime(df['fecha'])

# Obtener mes y año actual
mes_actual = df["fecha"].dt.month.iloc[0]
año_actual = df["fecha"].dt.year.iloc[0]

# 1. Actualizar histórico de gastos por categoría
historico = actualizar_historico(df, mes_actual, año_actual)

# 2. Actualizar precios históricos (para inflación)
precios_hist = actualizar_precios(df)

# 3. Calcular inflación semestral
inflacion_df, inflacion_promedio = calcular_inflacion(precios_hist)
if inflacion_promedio is not None:
    print(f"📈 Inflación estimada semestral (canasta): {inflacion_promedio:.2f}%")
else:
    print("⚠️ No hay datos suficientes para calcular inflación.")

# 4. Generar dashboard y reportes
figs = generar_dashboard(historico, df, inflacion_promedio)
