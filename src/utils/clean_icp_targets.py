import os
import re
import pandas as pd

# 📁 Ruta base
BASE_PATH = "/project/data/raw"

# 🧾 Palabras o raíces a eliminar (sin acentos, minúsculas)
EXCLUDE_PATTERNS = [
    # sectores no farmacéuticos
    r"\bveterinari", r"\banimal", r"\bmascot",
    r"\balimento", r"\bfood", r"\bnutric", r"\bherbolar", r"\bagro",
    # cosmética y belleza
    r"\bcosmet", r"\bbelleza", r"\bspa", r"\bperfume", r"\bestética", r"\bestetica",
    # envases y maquinaria
    r"\bmaquin", r"\bequip", r"\bpackag", r"\benvas", r"\bembala",
    # logística, distribución o transporte
    r"\blogist", r"\btransp", r"\bdistrib", r"\bimport", r"\bexport",
    # consultorías y servicios no productivos
    r"\bconsult", r"\bservicio", r"\bmarketing", r"\bpublicid", r"\bpromoc",
    r"\bmercadotec", r"\brh", r"\brrhh", r"\breclut", r"\bagencia",
    # hospitales y diagnóstico
    r"\bhospital", r"\bclin", r"\bdiagn", r"\blaboratorio clínico", r"\bensayo",
    # investigación y CRO
    r"\binvestig", r"\bcro", r"\bensayos", r"\bbiotecnolog", r"\bgenomic",
    # otros irrelevantes
    r"\bbroker", r"\bdistribuidor", r"\bcomercializador", r"\bplataforma",
    r"\bportal", r"\bdirectorio", r"\bmarketplace", r"\bsoftware", r"\bapp"
]

def normalize_text(text: str) -> str:
    """Normaliza acentos y pasa a minúsculas."""
    import unicodedata
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text.lower()

def should_exclude(text: str) -> bool:
    """Devuelve True si el giro contiene alguna palabra o raíz prohibida."""
    t = normalize_text(text)
    return any(re.search(pattern, t) for pattern in EXCLUDE_PATTERNS)

def clean_file(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    before = len(df)
    df = df[df["giro"].notna()]
    df = df[~df["giro"].apply(should_exclude)]
    df = df[df["giro"].str.strip() != ""]
    after = len(df)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"✅ Limpio: {os.path.basename(path)} ({before} → {after} filas)")
    return df

def combine_cleaned_files():
    print("\n📘 Combinando CSV limpios en icp_targets.csv...")
    all_dfs = []
    for file in sorted(os.listdir(BASE_PATH)):
        if file.startswith("icp_targets_") and file.endswith(".csv") and file != "icp_targets.csv":
            path = os.path.join(BASE_PATH, file)
            df = pd.read_csv(path, encoding="utf-8-sig")
            df["source_file"] = file
            all_dfs.append(df)
    if not all_dfs:
        print("⚠️ No hay archivos limpios para combinar.")
        return
    master_df = pd.concat(all_dfs, ignore_index=True)
    master_df = master_df.drop_duplicates(subset=["country", "giro"], keep="first")
    master_path = os.path.join(BASE_PATH, "icp_targets.csv")
    master_df.to_csv(master_path, index=False, encoding="utf-8-sig")
    print(f"✅ Archivo maestro actualizado: {master_path} ({len(master_df)} filas)")

def main():
    print("🧼 Iniciando limpieza avanzada de ICPs...")
    for file in sorted(os.listdir(BASE_PATH)):
        if file.startswith("icp_targets_") and file.endswith(".csv") and file != "icp_targets.csv":
            clean_file(os.path.join(BASE_PATH, file))
    combine_cleaned_files()

if __name__ == "__main__":
    main()

