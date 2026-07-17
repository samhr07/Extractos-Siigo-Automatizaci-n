import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime
import json


# ------------------------------------------------------------
# 1. FUNCIÓN PRINCIPAL: GENERAR REPORTE HTML COMPLETO
# ------------------------------------------------------------
def generar_reporte_html(
    movimientos_df: pd.DataFrame,
    proveedores_report: pd.DataFrame,
    banco_report: pd.DataFrame,
    nomina_report: pd.DataFrame = None,
    conciliacion_df: pd.DataFrame = None,
    errores: list = None,
    resumen: dict = None,
    nombre_archivo: str = "reporte_ejecutivo.html",
):
    """
    Genera un informe ejecutivo en HTML con gráficas, tablas y logs de errores.
    """
    if errores is None:
        errores = []
    if resumen is None:
        resumen = {}

    # --- Preparar datos para gráficas ---

    # 1. Gráfica de gastos por categoría (usando columna 'categoria' del punto #1)
    gastos_df = movimientos_df[movimientos_df["monto"] < 0].copy()
    gastos_df["monto_abs"] = gastos_df["monto"].abs()
    gastos_categoria = gastos_df.groupby("categoria")["monto_abs"].sum().reset_index()
    gastos_categoria = gastos_categoria.sort_values("monto_abs", ascending=False)

    fig_categoria = px.pie(
        gastos_categoria,
        values="monto_abs",
        names="categoria",
        title="Distribución de Gastos por Categoría",
        color_discrete_sequence=px.colors.qualitative.Set3,
        hole=0.3,
    )
    fig_categoria.update_traces(textposition="inside", textinfo="percent+label")

    # 2. Gráfica de proveedores (top 10)
    top_proveedores = proveedores_report.head(10)
    fig_proveedores = px.bar(
        top_proveedores,
        x="proveedor",
        y="total_comprado",
        title="Top 10 Proveedores por Monto",
        labels={"total_comprado": "Total Comprado ($)", "proveedor": "Proveedor"},
        color="total_comprado",
        color_continuous_scale="Blues",
    )
    fig_proveedores.update_layout(xaxis_tickangle=-45)

    # 3. Gráfica de bancos
    fig_bancos = px.pie(
        banco_report,
        values="total_monto",
        names="banco_origen",
        title="Distribución de Movimientos por Banco",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_bancos.update_traces(textposition="inside", textinfo="percent+label")

    # 4. Gráfica de tendencia histórica (si existe columna 'mes' o agrupamos por fecha)
    if "fecha" in movimientos_df.columns and not movimientos_df.empty:
        # Agrupar por mes (asumiendo que fecha es datetime)
        movimientos_df["mes"] = movimientos_df["fecha"].dt.to_period("M").astype(str)
        tendencia = movimientos_df.groupby("mes")["monto"].sum().reset_index()
        tendencia = tendencia.sort_values("mes")

        fig_tendencia = px.line(
            tendencia,
            x="mes",
            y="monto",
            title="Evolución del Flujo de Caja Mensual",
            labels={"monto": "Flujo Neto ($)", "mes": "Mes"},
            markers=True,
        )
        fig_tendencia.add_hline(y=0, line_dash="dash", line_color="red")
    else:
        # Si no hay datos históricos, crear una gráfica vacía con mensaje
        fig_tendencia = go.Figure()
        fig_tendencia.add_annotation(
            text="No hay datos históricos suficientes para mostrar tendencia",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14),
        )
        fig_tendencia.update_layout(title="Evolución del Flujo de Caja Mensual")

    # 5. (Opcional) Gráfica de conciliación (si existe)
    if conciliacion_df is not None and not conciliacion_df.empty:
        conciliado_count = conciliacion_df["conciliado"].value_counts()
        fig_conciliacion = px.bar(
            x=["No Conciliadas", "Conciliadas"],
            y=[conciliado_count.get(False, 0), conciliado_count.get(True, 0)],
            title="Estado de Conciliación",
            labels={"x": "Estado", "y": "Número de Transacciones"},
            color=["No Conciliadas", "Conciliadas"],
            color_discrete_sequence=["#EF553B", "#00CC96"],
        )
    else:
        fig_conciliacion = go.Figure()
        fig_conciliacion.add_annotation(
            text="No hay datos de conciliación disponibles",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(size=14),
        )
        fig_conciliacion.update_layout(title="Estado de Conciliación")

    # --- Convertir gráficas a HTML (divs) ---
    html_categoria = fig_categoria.to_html(full_html=False)
    html_proveedores = fig_proveedores.to_html(full_html=False)
    html_bancos = fig_bancos.to_html(full_html=False)
    html_tendencia = fig_tendencia.to_html(full_html=False)
    html_conciliacion = fig_conciliacion.to_html(full_html=False)

    # --- Generar tablas en HTML ---
    def dataframe_to_html(df, max_rows=15):
        if df is None or df.empty:
            return "<p><em>No hay datos disponibles</em></p>"
        # Limitar filas para no hacer el HTML pesado
        if len(df) > max_rows:
            df = df.head(max_rows)
            nota = f"<p><small>Mostrando {max_rows} de {len(df)} registros</small></p>"
        else:
            nota = ""
        return df.to_html(classes="table table-striped", index=False) + nota

    # --- Construir HTML final ---
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reporte Ejecutivo - Automatización Contable</title>
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f4f6f9;
                padding: 20px;
                color: #333;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            }}
            h1 {{
                color: #1a3c6e;
                border-bottom: 3px solid #1a3c6e;
                padding-bottom: 10px;
                margin-bottom: 20px;
                font-weight: 600;
            }}
            h2 {{
                color: #2c3e50;
                margin-top: 30px;
                margin-bottom: 15px;
                padding-bottom: 8px;
                border-bottom: 2px solid #eaeef2;
            }}
            .kpi-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 20px 0 30px 0;
            }}
            .kpi-card {{
                background: #f8fafc;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                border-left: 5px solid #1a3c6e;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }}
            .kpi-card .numero {{
                font-size: 28px;
                font-weight: 700;
                color: #1a3c6e;
            }}
            .kpi-card .etiqueta {{
                font-size: 14px;
                color: #6c7a8a;
                margin-top: 5px;
            }}
            .chart-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 25px;
                margin: 20px 0;
            }}
            .chart-box {{
                background: #ffffff;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.06);
                border: 1px solid #e9edf2;
            }}
            .chart-box.full-width {{
                grid-column: 1 / -1;
            }}
            .table-container {{
                overflow-x: auto;
                margin: 15px 0;
                background: #fafbfc;
                padding: 15px;
                border-radius: 8px;
                border: 1px solid #e9edf2;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            table th {{
                background: #1a3c6e;
                color: white;
                padding: 10px 12px;
                text-align: left;
            }}
            table td {{
                padding: 8px 12px;
                border-bottom: 1px solid #e9edf2;
            }}
            table tr:hover {{
                background: #f1f4f8;
            }}
            .error-log {{
                background: #fef6f6;
                border-left: 5px solid #e74c3c;
                padding: 15px 20px;
                margin: 20px 0;
                border-radius: 6px;
            }}
            .error-log .error-item {{
                padding: 8px 0;
                border-bottom: 1px solid #f0d6d6;
            }}
            .error-log .error-item:last-child {{
                border-bottom: none;
            }}
            .error-log strong {{
                color: #c0392b;
            }}
            .footer {{
                margin-top: 30px;
                text-align: center;
                font-size: 12px;
                color: #95a5a6;
                border-top: 1px solid #eaeef2;
                padding-top: 20px;
            }}
            @media (max-width: 768px) {{
                .chart-grid {{
                    grid-template-columns: 1fr;
                }}
                .container {{
                    padding: 15px;
                }}
            }}
        </style>
        <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h1>📊 Reporte Ejecutivo - Automatización Contable</h1>
            <p style="color: #6c7a8a; margin-bottom: 20px;">
                Generado el {datetime.now().strftime('%d de %B de %Y a las %H:%M')}
            </p>
            
            <!-- KPIs -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="numero">{resumen.get('total_movimientos', len(movimientos_df))}</div>
                    <div class="etiqueta">Total Transacciones</div>
                </div>
                <div class="kpi-card">
                    <div class="numero">${resumen.get('total_gastos', gastos_df['monto_abs'].sum() if not gastos_df.empty else 0):,.0f}</div>
                    <div class="etiqueta">Total Gastos</div>
                </div>
                <div class="kpi-card">
                    <div class="numero">{resumen.get('conciliaciones_exitosas', 0)}</div>
                    <div class="etiqueta">Transacciones Conciliadas</div>
                </div>
                <div class="kpi-card" style="border-left-color: {'#27ae60' if not errores else '#e74c3c'};">
                    <div class="numero">{len(errores)}</div>
                    <div class="etiqueta">{'✅ Sin Errores' if not errores else '⚠️ Errores Detectados'}</div>
                </div>
            </div>
            
            <!-- Gráficas -->
            <h2>📈 Análisis Gráfico</h2>
            <div class="chart-grid">
                <div class="chart-box">{html_categoria}</div>
                <div class="chart-box">{html_bancos}</div>
                <div class="chart-box full-width">{html_tendencia}</div>
                <div class="chart-box">{html_proveedores}</div>
                <div class="chart-box">{html_conciliacion}</div>
            </div>
            
            <!-- Tablas de Detalle -->
            <h2>📋 Tablas de Detalle</h2>
            
            <h3>🏢 Top Proveedores</h3>
            <div class="table-container">
                {dataframe_to_html(proveedores_report, max_rows=15)}
            </div>
            
            <h3>🏦 Distribución por Bancos</h3>
            <div class="table-container">
                {dataframe_to_html(banco_report, max_rows=10)}
            </div>
            
            {f'''<h3>👥 Resumen de Nómina</h3>
            <div class="table-container">
                {dataframe_to_html(nomina_report, max_rows=10)}
            </div>''' if nomina_report is not None and not nomina_report.empty else ''}
            
            {f'''<h3>🔗 Detalle de Conciliación</h3>
            <div class="table-container">
                {dataframe_to_html(conciliacion_df[conciliacion_df['conciliado'] == True].head(20), max_rows=20)}
            </div>''' if conciliacion_df is not None and not conciliacion_df.empty else ''}
            
            <!-- Errores (si los hay) -->
            {f'''
            <h2>⚠️ Log de Errores</h2>
            <div class="error-log">
                <p><strong>Se detectaron {len(errores)} error(es) durante la ejecución:</strong></p>
                {"".join([f'<div class="error-item"><strong>{e.get("entidad", "Desconocida")}:</strong> {e.get("motivo", "Sin descripción")} {f"<br><small>Detalle: {e.get('detalle', '')}</small>" if e.get("detalle") else ""}</div>' for e in errores])}
            </div>
            ''' if errores else ''}
            
            <div class="footer">
                Reporte generado automáticamente por el Script de Automatización Contable &bull; {datetime.now().year}
            </div>
        </div>
    </body>
    </html>
    """

    # Guardar archivo
    with open(nombre_archivo, "w", encoding="utf-8") as f:
        f.write(html_template)

    print(f"✅ Reporte HTML generado: {nombre_archivo}")
    return nombre_archivo
