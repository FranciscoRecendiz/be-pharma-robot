import os
import pandas as pd
from pathlib import Path

def clean_string(x):
    if pd.isna(x): return None
    return str(x).strip()

def parse_pharma_excel(filepath):
    df = pd.read_excel(filepath, dtype=str, header=2)

    col_map = {
        "Empresa": "empresa",
        "Giro": "giro",
        "Nombre": "nombre",
        "Cargo": "cargo",
        "e-mail": "email",
        "Teléfono": "telefono",
        "Telefono empresa": "telefono_empresa",
        "Página web": "web_empresa",
        "Comentarios sobre persona": "notas_persona",
        "Comentarios Empresa": "notas_empresa",
        "Seguimiento de la persona 2025": "seguimiento",
        "Comentarios historicos": "notas_historico",
        "LKD": "linkedin"
    }

    df = df.rename(columns=col_map)
    columnas_validas = [col for col in col_map.values() if col in df.columns]
    df = df[columnas_validas]

    # Limpiar strings
    for col in df.columns:
        df[col] = df[col].apply(clean_string)

    # Rellenar empresa cuando quede abajo vacía
    df["empresa"] = df["empresa"].ffill()

    # Borrar filas sin nombre ni email
    df = df[df["nombre"].notna() | df["email"].notna()]

    # Extraer dominio de email
    df["email_domain"] = df["email"].str.extract(r"@([\w\.-]+)")

    return df

def parse_multiple_files(folder="data/raw"):
    folder = Path(folder)
    result = pd.DataFrame()

    for file in folder.glob("*.xlsx"):
        print(f"✅ Procesando: {file.name}")
        temp = parse_pharma_excel(file)
        temp["fuente"] = file.name
        result = pd.concat([result, temp], ignore_index=True)

    save_path = Path("data/staging/pharma_cleaned.csv")
    result.to_csv(save_path, index=False)
    print(f"\n📁 Archivo final generado: {save_path}")
    return result

if __name__ == "__main__":
    parse_multiple_files()

