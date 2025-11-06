# ===============================================================
# BePharma Data Resolver PRO v3.3 — Consolidación definitiva
# pipelines/resolve_sites_posts_pro.py
# ===============================================================
# - Deduplica por nombre normalizado + dominio + país
# - Consolida giros múltiples en un solo registro
# - Limpia URLs y mantiene trazabilidad
# ===============================================================

import pandas as pd
import re, unicodedata
from urllib.parse import urlparse
import tldextract
from pathlib import Path
import argparse, json, time

# ===============================================================
# NORMALIZADORES
# ===============================================================

def normalize_name(name: str):
    """Limpia y normaliza el nombre de empresa"""
    if not isinstance(name, str): return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\b(sa|srl|ltda|inc|corp|company|pharma|farmaceutic|farmaceutico|laboratorio|labs?|industria|grupo|holding|cooperativa|enterprise|enterprises|c\.a|ca)\b", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def normalize_url(url: str):
    """Extrae y estandariza el dominio"""
    if not isinstance(url, str) or not url.strip():
        return ""
    url = url.strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        u = urlparse(url)
        ext = tldextract.extract(u.netloc)
        if not ext.domain or not ext.suffix:
            return u.netloc.replace("www.", "")
        return f"{ext.domain}.{ext.suffix}"
    except Exception:
        return ""

# ===============================================================
# RESOLVER PRINCIPAL
# ===============================================================

def resolver(df: pd.DataFrame):
    print(f"🧩 Filas iniciales: {len(df)}")

    # 1️⃣ Limpieza básica
    df = df.rename(columns={
        "nombre_empresa": "empresa",
        "pais": "pais",
        "giro": "giro",
        "fuente": "url"
    })
    for col in ["empresa", "pais", "giro", "url"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    # 4️⃣ Agrupación y consolidación
    grouped = (
        df.groupby(["empresa", "pais"])
        .agg({
            "empresa": lambda x: sorted(set(x), key=len)[0],  # nombre más corto (menos ruido)
            "giro": lambda x: "; ".join(sorted(set([i for i in x if i.strip()]))),
            "url": lambda x: sorted(set(x))[0]
        })
        .reset_index(drop=True)
    )

    # 5️⃣ Eliminación de duplicados residuales por dominio + país
    grouped = grouped.sort_values("empresa").drop_duplicates(subset=["pais"], keep="first")

    print(f"✅ Empresas únicas: {len(grouped)}")

    # 6️⃣ Orden final y columnas limpias
    grouped = grouped[["empresa", "pais", "giro", "url"]]
    grouped = grouped.sort_values(["pais", "empresa"]).reset_index(drop=True)
    return grouped

# ===============================================================
# MAIN EXECUTION
# ===============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Ruta al archivo de entrada (CSV original)")
    parser.add_argument("--output-dir", default="/project/data/cleaned", help="Carpeta destino")
    args = parser.parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.input, encoding="utf-8-sig")
    cleaned = resolver(df)

    out_path = Path(args.output_dir) / ("cleaned_" + Path(args.input).stem + ".csv")
    cleaned.to_csv(out_path, index=False, encoding="utf-8-sig")

    log = {
        "input_rows": len(df),
        "unique_rows": len(cleaned),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "input_file": str(Path(args.input).name),
        "output_file": str(out_path)
    }
    Path(args.output_dir, "log_resolver.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))

    print(f"\n📁 Guardado final: {out_path}")
    print(f"📊 Total: {len(cleaned)} empresas únicas consolidadas\n")

if __name__ == "__main__":
    main()
