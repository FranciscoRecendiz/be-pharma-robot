import os
import pandas as pd
from itertools import product

# --- CONFIGURACIÓN ---
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
INPUT_FILE = os.path.join(BASE_DIR, "data", "external", "lista de empresas que han participado.xlsx")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "raw", "icp_targets.csv")

# --- LECTURA DEL HISTÓRICO ---
print("📘 Leyendo archivo histórico...")
df = pd.read_excel(INPUT_FILE)

# Normaliza nombres de columnas
df.columns = [c.strip().upper() for c in df.columns]

if "GIRO" not in df.columns:
    raise ValueError("No se encontró la columna 'GIRO' en el archivo histórico.")

# Limpieza básica
df["GIRO"] = df["GIRO"].astype(str).str.lower().str.strip()
giros_unicos = sorted(set(df["GIRO"].dropna()))

print(f"✅ Giros detectados ({len(giros_unicos)}):")
for g in giros_unicos:
    print(f"  - {g}")

# Países LATAM
LATAM_COUNTRIES = [
    "México", "Argentina", "Brasil", "Chile", "Colombia", "Perú",
    "Uruguay", "Paraguay", "Bolivia", "Ecuador", "Venezuela",
    "Costa Rica", "Panamá", "Guatemala", "El Salvador", "Honduras",
    "Nicaragua", "República Dominicana", "Cuba",
    "Guyana", "Surinam", "Guayana Francesa"
]

# --- GENERACIÓN DE TARGETS ---
targets = list(product(LATAM_COUNTRIES, giros_unicos))
df_targets = pd.DataFrame(targets, columns=["country", "giro"])

# Crear carpeta si no existe
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
df_targets.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

print(f"\n✅ Archivo generado: {OUTPUT_FILE}")
print(f"Total combinaciones: {len(df_targets)} ({len(LATAM_COUNTRIES)} países × {len(giros_unicos)} giros)")
