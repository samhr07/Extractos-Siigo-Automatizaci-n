import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import FuncFormatter

# ------------------------------------------------------------
# 1. CONFIGURACIÓN DEL INFORME
# ------------------------------------------------------------
# Asumimos que df tiene columnas: 'banco', 'monto', 'fecha', 'descripcion' (opcional)
# 'banco' debe ser una cadena con el nombre del banco: "Bancolombia", "Nequi", "Nu", "Davivienda", etc.


# ------------------------------------------------------------
# 2. FUNCIÓN PARA GENERAR INFORME DE BANCOS
# ------------------------------------------------------------
def generar_informe_bancos(df):
    """
    Genera un informe detallado de transacciones por banco.
    Retorna un DataFrame con el resumen y guarda gráficos.
    """
    # Copia para no modificar el original
    data = df.copy()

    # Asegurar que la columna banco esté en mayúscula primera letra para uniformidad
    data["banco"] = data["banco"].str.title()

    # Identificar ingresos y egresos
    data["tipo"] = data["monto"].apply(lambda x: "Ingreso" if x > 0 else "Egreso")
    data["monto_abs"] = data["monto"].abs()

    # ------------------------------------------------------------
    # 2.1. Resumen general por banco (todas las transacciones)
    # ------------------------------------------------------------
    resumen_general = (
        data.groupby("banco")
        .agg(
            total_transacciones=("monto", "count"),
            total_monto=("monto_abs", "sum"),
            monto_promedio=("monto_abs", "mean"),
        )
        .reset_index()
        .sort_values("total_monto", ascending=False)
    )

    # Calcular participación porcentual
    total_monto_general = resumen_general["total_monto"].sum()
    resumen_general["%_participacion_monto"] = (
        resumen_general["total_monto"] / total_monto_general * 100
    ).round(2)
    resumen_general["%_participacion_transacciones"] = (
        resumen_general["total_transacciones"]
        / resumen_general["total_transacciones"].sum()
        * 100
    ).round(2)

    # ------------------------------------------------------------
    # 2.2. Desglose por tipo (Ingreso/Egreso)
    # ------------------------------------------------------------
    resumen_por_tipo = (
        data.groupby(["banco", "tipo"])
        .agg(total_monto=("monto_abs", "sum"), transacciones=("monto", "count"))
        .reset_index()
    )

    # Pivot para tener una tabla ancha (más fácil de leer)
    pivot_monto = resumen_por_tipo.pivot(
        index="banco", columns="tipo", values="total_monto"
    ).fillna(0)
    pivot_transacciones = resumen_por_tipo.pivot(
        index="banco", columns="tipo", values="transacciones"
    ).fillna(0)

    # Calcular ratio ingreso/egreso por banco (monto)
    pivot_monto["ratio_ingreso_egreso"] = pivot_monto["Ingreso"] / pivot_monto[
        "Egreso"
    ].replace(
        0, 1
    )  # evitar división por cero

    # ------------------------------------------------------------
    # 2.3. Crear gráficos
    # ------------------------------------------------------------
    # Configuración de estilo
    sns.set_style("whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(
        "📊 Informe de Transacciones por Banco", fontsize=16, fontweight="bold"
    )

    # Gráfico 1: Distribución de montos por banco (pastel)
    ax1 = axes[0, 0]
    colores = sns.color_palette("Set3", len(resumen_general))
    wedges, texts, autotexts = ax1.pie(
        resumen_general["total_monto"],
        labels=resumen_general["banco"],
        autopct=lambda p: f"{p:.1f}%",
        startangle=90,
        colors=colores,
        explode=[0.02] * len(resumen_general),
        shadow=True,
    )
    ax1.set_title("Distribución de Montos por Banco")

    # Gráfico 2: Número de transacciones por banco (barras)
    ax2 = axes[0, 1]
    sns.barplot(
        data=resumen_general,
        x="banco",
        y="total_transacciones",
        palette="viridis",
        ax=ax2,
    )
    ax2.set_title("Número de Transacciones por Banco")
    ax2.set_ylabel("Número de transacciones")
    ax2.set_xlabel("Banco")
    for p in ax2.patches:
        ax2.annotate(
            f"{int(p.get_height())}",
            (p.get_x() + p.get_width() / 2.0, p.get_height() + 0.5),
            ha="center",
            va="bottom",
            fontsize=10,
        )

    # Gráfico 3: Monto promedio por banco (barras horizontales)
    ax3 = axes[1, 0]
    resumen_general_sorted = resumen_general.sort_values(
        "monto_promedio", ascending=True
    )
    sns.barplot(
        data=resumen_general_sorted,
        y="banco",
        x="monto_promedio",
        palette="coolwarm",
        ax=ax3,
    )
    ax3.set_title("Monto Promedio por Transacción")
    ax3.set_xlabel("Monto promedio (COP)")
    ax3.set_ylabel("Banco")
    ax3.xaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Gráfico 4: Ingresos vs Egresos por banco (barras agrupadas)
    ax4 = axes[1, 1]
    # Preparar datos para barras agrupadas
    pivot_monto_plot = pivot_monto[["Ingreso", "Egreso"]].fillna(0)
    pivot_monto_plot.plot(kind="bar", ax=ax4, color=["green", "red"], alpha=0.7)
    ax4.set_title("Montos de Ingresos vs Egresos por Banco")
    ax4.set_ylabel("Monto total (COP)")
    ax4.set_xlabel("Banco")
    ax4.legend(title="Tipo")
    ax4.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax4.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig("informe_bancos.png", dpi=150, bbox_inches="tight")
    plt.show()

    # ------------------------------------------------------------
    # 2.4. Exportar a Excel con múltiples hojas
    # ------------------------------------------------------------
    with pd.ExcelWriter("informe_bancos.xlsx") as writer:
        resumen_general.to_excel(writer, sheet_name="Resumen General", index=False)
        pivot_monto.to_excel(writer, sheet_name="Ingresos vs Egresos (Monto)")
        pivot_transacciones.to_excel(writer, sheet_name="Ingresos vs Egresos (Nº)")
        # Hoja adicional con el detalle de cada transacción (opcional)
        data[["fecha", "banco", "descripcion", "monto", "tipo"]].to_excel(
            writer, sheet_name="Detalle Transacciones", index=False
        )

    # ------------------------------------------------------------
    # 2.5. Imprimir resumen en consola
    # ------------------------------------------------------------
    print("🏦 INFORME DE BANCOS DE TRANSACCIÓN")
    print("===================================")
    print(resumen_general.to_string(index=False))
    print("\n📊 Distribución de Ingresos vs Egresos (por monto):")
    print(
        pivot_monto[["Ingreso", "Egreso", "ratio_ingreso_egreso"]].round(2).to_string()
    )

    return resumen_general, pivot_monto


# ------------------------------------------------------------
# 3. EJEMPLO DE USO (ASUMIENDO QUE TIENES df CON COLUMNA 'banco')
# ------------------------------------------------------------
# df = pd.read_csv('tus_extractos.csv')  # <-- descomenta y ajusta
# resumen, pivot = generar_informe_bancos(df)


# ------------------------------------------------------------
# 4. (OPCIONAL) FUNCIÓN PARA INFERIR BANCO A PARTIR DE DESCRIPCIÓN
#    Útil si no tienes la columna 'banco' y quieres asignarla automáticamente
# ------------------------------------------------------------
def inferir_banco(descripcion):
    """
    Infiere el banco a partir de la descripción de la transacción.
    Retorna el nombre del banco o 'Otro'.
    """
    desc_lower = str(descripcion).lower()
    if "bancolombia" in desc_lower:
        return "Bancolombia"
    elif "nequi" in desc_lower:
        return "Nequi"
    elif "nu" in desc_lower or "nubank" in desc_lower:
        return "Nu"
    elif "davivienda" in desc_lower:
        return "Davivienda"
    else:
        return "Otro"


# Ejemplo de cómo asignar 'banco' si no existe
# if 'banco' not in df.columns:
#     df['banco'] = df['descripcion'].apply(inferir_banco)
#     print("✅ Columna 'banco' inferida automáticamente.")
