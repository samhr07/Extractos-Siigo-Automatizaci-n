import pandas as pd
from thefuzz import process, fuzz

# ------------------------------------------------------------
# 1. DEFINICIÓN DE CATEGORÍAS (expansión solicitada)
# ------------------------------------------------------------
CATEGORIAS = [
    "Materia Prima",
    "Servicios Públicos",  # Agua, luz, gas, etc.
    "Nómina",
    "Gastos Administrativos",  # Papelería, mensajería, oficina
    "Ventas",  # Ingresos por consignaciones
    "Impuestos",  # GMF, 4x1000, Retefuente
    "Otros",  # Catch-all por defecto
    "Biocompuestos",  # Extracto de levadura, etc.
    "Inorgánicos",  # Calcio, magnesio, hipoclorito, ozono, cristalería
]

# ------------------------------------------------------------
# 2. DICCIONARIO DE PALABRAS CLAVE POR CATEGORÍA
#    (Todas en minúsculas para facilitar la búsqueda)
# ------------------------------------------------------------
CATEGORY_KEYWORDS = {
    # --- INORGÁNICOS (Minerales, químicos de desinfección y vidriería) ---
    "Inorgánicos": [
        "calcio",
        "magnesio",
        "potasio",
        "costal",
        "costales",  # Relacionado con la presentación de estos
        "protoquímica",  # Proveedor de estos insumos
        "alcohol",
        "hipoclorito",
        "ozono",  # Solicitado explícitamente para desinfección
        "cristalería",
        "laboratorio",
        "matraz",
        "probeta",
        "tubo de ensayo",
        "vidrio",
        "pipeta",
        "bureta",
    ],
    # --- BIOCOMPUESTOS (Levaduras y derivados biológicos) ---
    "Biocompuestos": [
        "extracto de levadura",
        "levadura",
        "tecna",  # Proveedor específico de levadura
        "biocompuesto",
        "peptona",  # (Común en medios de cultivo)
        "agar",  # (Común en microbiología)
    ],
    # --- MATERIA PRIMA (Insumos generales de producción) ---
    "Materia Prima": [
        "panela",
        "ara",
        "d1",
        "éxito",  # Supermercados
        "supermercado",
        "envase",
        "envases",
        "incodi",  # Proveedor de envases
        "insumo",
        "producción",
        "melaza",
        "azúcar",  # Posibles otros insumos
    ],
    # --- NÓMINA (Empleados y prestaciones) ---
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
    # --- SERVICIOS PÚBLICOS ---
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
    # --- GASTOS ADMINISTRATIVOS ---
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
    # --- IMPUESTOS ---
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
    # --- VENTAS (Ingresos) ---
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

# ------------------------------------------------------------
# 3. PREPARACIÓN DE LA ESTRUCTURA PARA BÚSQUEDA RÁPIDA
# ------------------------------------------------------------
# Aplanamos todas las palabras clave y mapeamos a su categoría
all_keywords = []
keyword_to_category = {}

for categoria, lista_palabras in CATEGORY_KEYWORDS.items():
    for palabra in lista_palabras:
        kw_lower = palabra.lower().strip()
        if kw_lower not in keyword_to_category:  # Evita duplicados
            all_keywords.append(kw_lower)
            keyword_to_category[kw_lower] = categoria


# ------------------------------------------------------------
# 4. FUNCIÓN DE CLASIFICACIÓN CON COINCIDENCIA DIFUSA (FUZZY)
# ------------------------------------------------------------
def clasificar_transaccion(descripcion, umbral=80):
    """
    Clasifica una descripción usando fuzzy matching (coincidencia difusa).
    Retorna la categoría si encuentra una keyword con similitud >= umbral.
    Si no, retorna "Otros".

    Args:
        descripcion (str): Texto de la transacción (ej. "PAGO A PROTOQUIMICA CALCIO").
        umbral (int): Porcentaje mínimo de similitud (0-100). Recomendado 80.
    """
    # Validación de entrada
    if not isinstance(descripcion, str) or pd.isna(descripcion):
        return "Otros"

    desc_lower = descripcion.lower()

    # Extraer la mejor coincidencia usando partial_ratio (bueno para subcadenas)
    # Ej: "PROTOQUIMICA" se encuentra dentro de "PAGO A PROTOQUIMICA CALCIO"
    mejor_match = process.extractOne(
        desc_lower, all_keywords, scorer=fuzz.partial_ratio
    )

    # Si hay match y supera el umbral, asignamos la categoría
    if mejor_match and mejor_match[1] >= umbral:
        keyword_encontrada = mejor_match[0]
        return keyword_to_category.get(keyword_encontrada, "Otros")
    else:
        return "Otros"


# ------------------------------------------------------------
# 5. APLICACIÓN AL DATAFRAME (EJEMPLO)
# ------------------------------------------------------------
# ASUNTO: Suponemos que tienes un DataFrame `df` con una columna 'descripcion'
# df = pd.read_csv('tus_extractos.csv')  # <-- Descomenta y ajusta según tu fuente

# Aplicar la clasificación a cada fila
# df['categoria'] = df['descripcion'].apply(clasificar_transaccion)

# Visualizar la distribución para validar que todo funciona
# print("Distribución de categorías asignadas:")
# print(df['categoria'].value_counts())

# Exportar resultados si deseas revisar manualmente
# df[['fecha', 'descripcion', 'monto', 'categoria']].to_excel('extractos_clasificados.xlsx', index=False)
