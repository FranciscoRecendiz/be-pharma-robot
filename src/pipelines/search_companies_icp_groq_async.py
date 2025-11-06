import os, json, asyncio, pandas as pd, time
from tenacity import retry, stop_after_attempt, wait_fixed
from ddgs import DDGS
from langchain_groq import ChatGroq
import aiohttp
import nest_asyncio

nest_asyncio.apply()

# -------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------
INPUT_FILE = "/project/data/raw/icp_targets.csv"
OUTPUT_DIR = "/project/data/processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BATCH_SIZE = 20
MAX_RESULTS_PER_QUERY = 8
MODEL = "llama-3.3-70b-versatile"
TOKEN_LIMIT = 95000

used_tokens = 0

# -------------------------------------------
# CLIENTES
# -------------------------------------------
llm = ChatGroq(model=MODEL, temperature=0.1)
ddgs = DDGS()

PROMPT = """
Eres un analista experto en inteligencia comercial farmacéutica.

Recibes resultados web (título, descripción, URL) para el giro "{giro}" en "{pais}".

Filtra solo empresas que cumplan:
✅ Fabrican o distribuyen medicamentos de uso humano.
✅ Fabrican o distribuyen productos healthcare: dispositivos médicos, vitaminas, suplementos, productos dermatológicos.
✅ CDMO / CMO (contract manufacturing) válidos.
✅ proveedores de APIs o materias primas.
❌ Excluye empresas de consultoría, servicios, abogados, marketing, logística, recursos humanos o análisis clínicos.
❌ Excluye empresas de cannabis, CBD, marihuana o cáñamo.

Devuelve JSON con:
[
  {{
    "nombre_empresa": "",
    "pais": "",
    "giro": "",
    "sitio_web": "",
    "posible_contacto": "",
    "linkedin": "",
    "fuente": ""
  }}
]

Responde SOLO con JSON válido.
"""

# -------------------------------------------
# FUNCIONES AUXILIARES
# -------------------------------------------
def clean_text(txt):
    return str(txt).replace("\n", " ").strip() if pd.notna(txt) else ""

def safe_json_loads(text):
    try:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except:
        return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(3))
async def search_ddg(query):
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
    return results

@retry(stop=stop_after_attempt(2), wait=wait_fixed(5))
async def analyze_with_llm(pais, giro, results):
    global used_tokens
    prompt_input = PROMPT.format(giro=giro, pais=pais) + "\n" + json.dumps(results, ensure_ascii=False)
    used_tokens += len(prompt_input.split())
    if used_tokens > TOKEN_LIMIT:
        print("⏸️ Límite diario alcanzado. Esperando 12 horas...")
        await asyncio.sleep(12 * 3600)
        used_tokens = 0

    try:
        resp = llm.invoke(prompt_input)
        content = (resp.content or "").strip()
        if not content:
            return []
        data = safe_json_loads(content)
        if isinstance(data, list):
            for d in data:
                d["query_country"] = pais
                d["query_giro"] = giro
            return data
    except Exception as e:
        if "429" in str(e) or "rate_limit" in str(e).lower():
            print("⚠️ Rate limit alcanzado. Esperando 10 minutos...")
            await asyncio.sleep(600)
            return await analyze_with_llm(pais, giro, results)
        print(f"⚠️ Error LLM: {e}")
    return []

async def process_combination(session, i, pais, giro):
    query = f"empresas farmacéuticas fabricantes distribuidores {giro} {pais}"
    print(f"\n🔎 [{i}] {pais} | {giro}")
    results = await search_ddg(query)
    if not results:
        print("⚠️ Sin resultados web.")
        return []
    data = await analyze_with_llm(pais, giro, results)
    print(f"✅ {len(data)} empresas detectadas.")
    return data

# -------------------------------------------
# PROCESO PRINCIPAL
# -------------------------------------------
async def main():
    print("📘 Leyendo combinaciones ICP...")
    df_icp = pd.read_csv(INPUT_FILE)
    tasks, all_results = [], []
    async with aiohttp.ClientSession() as session:
        for i, row in df_icp.iterrows():
            pais, giro = clean_text(row.get("country")), clean_text(row.get("giro"))
            if not pais or pais.lower() == "nan": 
                continue
            tasks.append(process_combination(session, i+1, pais, giro))
            if len(tasks) >= BATCH_SIZE:
                batch = await asyncio.gather(*tasks)
                for b in batch: all_results.extend(b)
                if all_results:
                    df_out = pd.DataFrame(all_results)
                    partial_file = os.path.join(OUTPUT_DIR, f"prospects_partial_{int(time.time())}.csv")
                    df_out.to_csv(partial_file, index=False)
                    print(f"💾 Guardado parcial: {partial_file}")
                tasks = []
                await asyncio.sleep(3)
        if tasks:
            batch = await asyncio.gather(*tasks)
            for b in batch: all_results.extend(b)
    if all_results:
        df_out = pd.DataFrame(all_results)
        final_file = os.path.join(OUTPUT_DIR, "prospects_found_groq_filtered.csv")
        df_out.to_csv(final_file, index=False)
        print(f"\n✅ Archivo final guardado: {final_file}")
        print(f"Total empresas encontradas: {len(df_out)}")
    else:
        print("⚠️ No se encontraron resultados relevantes.")

if __name__ == "__main__":
    asyncio.run(main())

