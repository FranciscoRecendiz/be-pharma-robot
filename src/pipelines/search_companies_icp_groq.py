# ===========================================
# 🤖 BePharma - Prospección Inteligente con Groq
# search_companies_icp_groq.py
# ===========================================

import os, time, json, pandas as pd
from ddgs import DDGS
from langchain_groq import ChatGroq

# -------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------
INPUT_FILE = "/project/data/raw/icp_targets.csv"
OUTPUT_FILE = "/project/data/processed/prospects_found_groq.csv"
os.makedirs("/project/data/processed", exist_ok=True)

LIMIT = 5   # Puedes subir a 50-100 luego
MAX_RESULTS_PER_QUERY = 8

# -------------------------------------------
# CLIENTES
# -------------------------------------------
ddgs = DDGS()
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.1)

# -------------------------------------------
# FUNCIONES AUXILIARES
# -------------------------------------------
def clean_text(txt):
    if not txt: return ""
    return str(txt).replace("\n", " ").strip()

def safe_json_loads(text):
    """Intenta parsear JSON, incluso si el modelo devuelve basura extra."""
    try:
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except Exception:
        return None

# -------------------------------------------
# PROMPT
# -------------------------------------------
PROMPT = """
Eres un analista de inteligencia del sector farmacéutico.

Recibes una lista de resultados web (título, descripción y URL) obtenidos con la búsqueda "{giro}" en "{pais}".

Tu tarea:
1. Identifica SOLO empresas reales del sector salud, farmacéutico, biotecnología, CDMO, dispositivos médicos o nutracéuticos.
2. Excluye universidades, blogs, noticias o gobiernos.
3. Si puedes, deduce el país, el giro (fabricante, distribuidor, CDMO, etc.) y el contacto o LinkedIn si se menciona.
4. Devuelve una lista **JSON válida** con los siguientes campos:
   - nombre_empresa
   - pais
   - giro
   - sitio_web
   - posible_contacto
   - linkedin
   - fuente (URL)
IMPORTANTE: responde SOLO con JSON. Nada de texto fuera del JSON.
"""

# -------------------------------------------
# PROCESAMIENTO PRINCIPAL
# -------------------------------------------
print("📘 Leyendo combinaciones ICP...")
df_icp = pd.read_csv(INPUT_FILE).head(LIMIT)
prospects = []

for i, row in df_icp.iterrows():
    country = clean_text(row.get("country"))
    giro = clean_text(row.get("giro"))
    if not country or not giro or country.lower() == "nan": 
        continue

    print(f"\n🔎 [{i+1}] {country} | {giro}")
    query = f"empresas farmacéuticas {giro} {country}"
    results = []

    try:
        for r in ddgs.text(query, max_results=MAX_RESULTS_PER_QUERY):
            results.append({
                "title": r.get("title"),
                "body": r.get("body"),
                "url": r.get("url")
            })
    except Exception as e:
        print(f"⚠️ Error DDGS: {e}")
        continue

    if not results:
        continue

    # Analizar con el LLM
    prompt_input = PROMPT.format(giro=giro, pais=country) + "\n" + json.dumps(results, ensure_ascii=False)
    try:
        resp = llm.invoke(prompt_input)
        content = (resp.content or "").strip()

        if not content:
            print("⚠️ Respuesta vacía del modelo.")
            continue

        data = safe_json_loads(content)
        if isinstance(data, list):
            for d in data:
                d["query_country"] = country
                d["query_giro"] = giro
                prospects.append(d)
            print(f"✅ {len(data)} empresas detectadas.")
        else:
            print("⚠️ No se pudo interpretar JSON válido.")

    except Exception as e:
        print(f"⚠️ Error LLM: {e}")
        continue

    time.sleep(2)

# -------------------------------------------
# GUARDAR RESULTADOS
# -------------------------------------------
if prospects:
    df_out = pd.DataFrame(prospects)
    df_out.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Archivo guardado: {OUTPUT_FILE}")
    print(f"Total empresas encontradas: {len(df_out)}")
else:
    print("⚠️ No se encontraron resultados relevantes.")
