import os, pandas as pd, json, asyncio, time
from ddgs import DDGS
from langchain_groq import ChatGroq
from tenacity import retry, stop_after_attempt, wait_fixed

# -------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------
INPUT_FILE = "/project/data/processed/empresas_filtradas.csv"
OUTPUT_FILE = "/project/data/processed/empresas_con_contactos.csv"
LOG_DIR = "/project/data/logs"
os.makedirs(LOG_DIR, exist_ok=True)

MODEL = "llama-3.3-70b-versatile"
BATCH_SIZE = 10
TOKEN_LIMIT = 100_000
TOKEN_RESERVE_SEARCH = 80_000   # reservado para etapa previa
TOKEN_WORK_LIMIT = TOKEN_LIMIT - TOKEN_RESERVE_SEARCH  # margen de contactos
used_tokens = 0

# estimado promedio de tokens por prompt (según cantidad de resultados)
estimated_tokens_per_prompt = 2_000

llm = ChatGroq(model=MODEL, temperature=0.1)
ddgs = DDGS()

PROMPT = """
Eres un experto en inteligencia comercial farmacéutica.
Dado el nombre de una empresa y su sitio web, encuentra personas clave:
- Directores o responsables de Licensing, Export, Business Development, Ventas o Dirección General.
- Busca nombres reales y perfiles de LinkedIn si existen.

Responde solo con JSON válido:
[
  {
    "nombre_empresa": "",
    "contacto_nombre": "",
    "cargo": "",
    "linkedin_url": "",
    "email": "",
    "sitio_web": ""
  }
]
"""

# -------------------------------------------
# FUNCIONES
# -------------------------------------------
def safe_json_loads(text):
    try:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except:
        return None

@retry(stop=stop_after_attempt(2), wait=wait_fixed(5))
async def analyze_with_llm(empresa, sitio, search_results):
    global used_tokens
    prompt_input = PROMPT + "\n" + json.dumps(search_results, ensure_ascii=False)
    token_estimate = len(prompt_input.split())

    # Control de tokens antes de invocar
    if used_tokens + token_estimate >= TOKEN_WORK_LIMIT:
        print(f"⏸️ Límite de tokens para contactos alcanzado ({used_tokens}). Deteniendo ejecución segura.")
        return []

    try:
        resp = llm.invoke(prompt_input)
        used_tokens += token_estimate
        content = (resp.content or "").strip()
        data = safe_json_loads(content)
        if isinstance(data, list):
            for d in data:
                d["nombre_empresa"] = empresa
                d["sitio_web"] = sitio
            return data
    except Exception as e:
        if "429" in str(e):
            print("⚠️ Rate limit Groq alcanzado. Esperando 10 minutos...")
            await asyncio.sleep(600)
            return await analyze_with_llm(empresa, sitio, search_results)
        print(f"⚠️ Error LLM ({empresa}): {e}")
    return []

async def process_contact(i, empresa, sitio):
    query = f'{empresa} site:linkedin.com (licensing OR "business development" OR director OR export OR sales)'
    print(f"\n🔎 [{i}] Buscando contactos para: {empresa}")
    search_results = []
    try:
        for r in ddgs.text(query, max_results=5):
            search_results.append({"title": r.get("title"), "body": r.get("body"), "url": r.get("url")})
    except Exception as e:
        print(f"⚠️ Error DDGS: {e}")

    if not search_results:
        print("⚠️ Sin resultados en LinkedIn.")
        return []

    return await analyze_with_llm(empresa, sitio, search_results)

# -------------------------------------------
# MAIN
# -------------------------------------------
async def main():
    print("📘 Iniciando extracción de contactos...")
    df = pd.read_csv(INPUT_FILE)
    results, tasks = [], []
    total_empresas = len(df)

    # Si ya existe archivo previo, cargar para evitar duplicados
    processed = set()
    if os.path.exists(OUTPUT_FILE):
        df_old = pd.read_csv(OUTPUT_FILE)
        processed = set(df_old["nombre_empresa"].dropna().tolist())
        print(f"🔄 Se detectaron {len(processed)} empresas ya procesadas, se omitirán.")

    start_time = time.time()
    for i, row in df.iterrows():
        empresa = str(row.get("nombre_empresa"))
        sitio = str(row.get("sitio_web", ""))
        if empresa in processed or pd.isna(empresa):
            continue

        if used_tokens >= TOKEN_WORK_LIMIT:
            print(f"🔒 Tokens usados: {used_tokens} — deteniendo búsqueda de contactos.")
            break

        tasks.append(process_contact(i+1, empresa, sitio))

        if len(tasks) >= BATCH_SIZE:
            batch_results = await asyncio.gather(*tasks)
            for br in batch_results:
                results.extend(br)
            # Guardado parcial incremental
            if results:
                pd.DataFrame(results).to_csv(OUTPUT_FILE, index=False)
                print(f"💾 Guardado parcial ({len(results)} contactos). Tokens usados: {used_tokens}")
            tasks, results = [], []

    # Procesar el último lote
    if tasks:
        batch_results = await asyncio.gather(*tasks)
        for br in batch_results:
            results.extend(br)

    if results:
        df_new = pd.DataFrame(results)
        if os.path.exists(OUTPUT_FILE):
            df_old = pd.read_csv(OUTPUT_FILE)
            df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=["nombre_empresa", "contacto_nombre"], keep="first")
        else:
            df_final = df_new
        df_final.to_csv(OUTPUT_FILE, index=False)
        print(f"✅ Archivo final actualizado: {OUTPUT_FILE}")
        print(f"Total contactos: {len(df_final)}")
    else:
        print("⚠️ No se obtuvieron nuevos contactos.")

    # Guardar log
    elapsed = round(time.time() - start_time, 2)
    log_path = os.path.join(LOG_DIR, "contacts_token_usage.json")
    log_data = {"used_tokens": used_tokens, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "runtime_sec": elapsed}
    with open(log_path, "w") as f:
        json.dump(log_data, f, indent=2)
    print(f"🧾 Registro guardado en {log_path}")

if __name__ == "__main__":
    asyncio.run(main())
