import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import os, json, asyncio, time, argparse, re, unicodedata, hashlib, random
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
from ddgs import DDGS
from langchain_groq import ChatGroq
import aiohttp
import nest_asyncio
from src.utils.site_resolver import extract_domain as domain_from_url

nest_asyncio.apply()

# --------------------------- Helpers ---------------------------

def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s-]+", "_", s)

def clean_text(txt):
    return str(txt).replace("\n", " ").strip() if pd.notna(txt) else ""

def safe_json_loads(text):
    try:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except Exception:
        return None

def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9 ]", " ", s).lower()
    s = re.sub(r"\s+", " ", s).strip()
    for w in ["sa de cv","sa","s a","s de rl","s de r l","sl","srl","ltda","ltd","inc","corp","co","company","gmbh","sasu","sas"]:
        s = re.sub(rf"\b{w}\b"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def hash_query(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

# --------------------------- Args ---------------------------

parser = argparse.ArgumentParser(description="BePharma - Descubrimiento de empresas (sin sitios web)")
parser.add_argument("--input", default="/project/data/raw/icp_targets.csv")
parser.add_argument("--output-dir", default="/project/data/processed")
parser.add_argument("--log-dir", default="/project/data/logs")
parser.add_argument("--country", default="", help="Filtrar por país (opcional)")
parser.add_argument("--token-limit", type=int, default=100_000)
parser.add_argument("--token-reserve-contacts", type=int, default=20_000)
parser.add_argument("--daily-limit-combos", type=int, default=40)
parser.add_argument("--batch-size", type=int, default=20)
parser.add_argument("--model", default="llama-3.3-70b-versatile")
parser.add_argument("--ddg-max", type=int, default=12)
args = parser.parse_args()

COUNTRY_NAME = args.country.strip()
COUNTRY_SLUG = slug(COUNTRY_NAME) if COUNTRY_NAME else ""
INPUT_FILE = args.input
OUTPUT_DIR = args.output_dir if not COUNTRY_SLUG else os.path.join(args.output_dir, COUNTRY_SLUG)
LOG_DIR = args.log_dir if not COUNTRY_SLUG else os.path.join(args.log_dir, COUNTRY_SLUG)
CACHE_DIR = "/project/data/cache/groq"
REG_DIR = "/project/data/registry"

for p in [OUTPUT_DIR, LOG_DIR, CACHE_DIR, REG_DIR]:
    os.makedirs(p, exist_ok=True)

MODEL = args.model
BATCH_SIZE = max(1, args.batch_size)
DAILY_LIMIT_COMBOS = args.daily_limit_combos if args.daily_limit_combos > 0 else None
TOKEN_LIMIT = args.token_limit
TOKEN_RESERVE_CONTACTS = args.token_reserve_contacts
TOKEN_WORK_LIMIT = TOKEN_LIMIT - TOKEN_RESERVE_CONTACTS
used_tokens = 0
estimated_tokens_per_prompt = 1400

# --------------------------- Concurrencia ---------------------------

_llm_semaphore = asyncio.Semaphore(int(os.getenv("GROQ_CONCURRENCY", "2")))

# --------------------------- Cliente Groq ---------------------------

llm = ChatGroq(model=MODEL, temperature=0.1)

PROMPT = """
Eres analista senior en BePharma. Recibirás resultados web (título, descripción, URL)
para el giro "{giro}" en "{pais}". Devuelve SOLO empresas que cumplan:

1️⃣ Fabricantes de medicamentos de uso humano (Rx, OTC, genéricos)
2️⃣ Fabricantes de suplementos/vitamínicos/nutracéuticos/dermocosméticos
3️⃣ CDMO/CMO farmacéuticos (fabricación por contrato, NO investigación)

EXCLUIR:
- CRO, ensayos clínicos, investigación, diagnóstico o dispositivos médicos puros
- Consultorías, brokers, RRHH, marketing, hospitales o clínicas
- Directorios o redes sociales

Devuelve JSON:
[
  {{
    "nombre_empresa": "",
    "pais": "{pais}",
    "giro": "{giro}",
    "fuente": "",
    "sector_principal": "",
    "indicadores_exportacion": ""
  }}
]
"""

# --------------------------- Búsqueda DDG ---------------------------

def _norm_query_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()

async def search_ddg(query, region_hint=None, max_results=12):
    results = []
    try:
        kwargs = {"max_results": max_results, "safe": False}
        if region_hint:
            kwargs["region"] = region_hint
        for r in DDGS().text(_norm_query_text(query), **kwargs):
            title = r.get("title") or ""
            body = r.get("body") or ""
            url = r.get("href") or r.get("url") or ""
            if url:
                results.append({"title": title, "body": body, "url": url})
    except Exception as e:
        print("⚠️ Error DDG:", e)
    unique = {}
    for r in results:
        d = domain_from_url(r["url"])
        if d and d not in unique:
            unique[d] = r
    return list(unique.values())

def build_queries(pais, giro):
    base_terms = [
        "fabricante medicamentos",
        "laboratorio farmacéutico",
        "producción farmacéutica",
        "fabricante suplementos",
        "fabricante nutracéuticos",
        "CDMO farmacéutica",
        "fabricante genéricos",
    ]
    minus = (
        '-"equipos médicos" -"hospital" -"clínica" -"diagnóstico" -"consultoría" '
        '-"broker" -"ensayos clínicos" -"investigación clínica" -"fase I" -"fase II" -"fase III" -"fase IV"'
    )
    region = None
    if "mex" in pais.lower(): region = "mx-es"
    elif "ecuador" in pais.lower(): region = "ec-es"
    return [f'{term} "{pais}" "{giro}" {minus}' for term in base_terms], region

# --------------------------- LLM ---------------------------

class RateLimitError(Exception): pass

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=2, max=60),
    retry=retry_if_exception_type((RateLimitError, aiohttp.ClientError, TimeoutError))
)
async def _invoke_llm(prompt_input):
    global used_tokens
    async with _llm_semaphore:
        await asyncio.sleep(random.uniform(0.05, 0.3))
        try:
            resp = llm.invoke(prompt_input)
            used_tokens += int(len(prompt_input.split()) * 0.9)
            return (resp.content or "").strip()
        except Exception as e:
            s = str(e)
            if "429" in s or "rate" in s.lower():
                raise RateLimitError(s)
            raise

async def analyze_with_llm(pais, giro, results, cache_key):
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    prompt = PROMPT.format(giro=giro, pais=pais) + "\n" + json.dumps(results, ensure_ascii=False)
    if used_tokens + estimated_tokens_per_prompt >= TOKEN_WORK_LIMIT:
        print("⏸️ Límite tokens alcanzado.")
        return []
    content = await _invoke_llm(prompt)
    data = safe_json_loads(content)
    if isinstance(data, list):
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    return []

# --------------------------- Proceso principal ---------------------------

async def process_combination(i, pais, giro):
    print(f"\n🔎 [{i}] {pais} | {giro}")
    queries, region = build_queries(pais, giro)
    ddg_results = []
    for q in queries:
        ddg_results.extend(await search_ddg(q, region, max_results=args.ddg_max))
    if not ddg_results:
        print("⚠️ Sin resultados DDG.")
        return []
    payload = {"pais": pais, "giro": giro, "domains": [domain_from_url(r['url']) for r in ddg_results]}
    cache_key = f"{slug(pais)}_{slug(giro)}_{hash_query(payload)}"
    data = await analyze_with_llm(pais, giro, ddg_results, cache_key)
    if not data:
        print("⚠️ LLM no devolvió datos.")
        return []
    print(f"✅ {len(data)} empresas detectadas por LLM.")
    return data

# --------------------------- Main ---------------------------

async def main():
    print("📘 Iniciando búsqueda BePharma (fase 1: descubrimiento sin webs)...")
    df = pd.read_csv(INPUT_FILE, encoding="utf-8-sig")
    df = df[df["country"].notna() & df["giro"].notna()]
    if COUNTRY_NAME:
        df = df[df["country"].str.contains(COUNTRY_NAME, case=False)]
    results = []
    processed = 0
    for i, row in df.iterrows():
        pais, giro = clean_text(row.country), clean_text(row.giro)
        skip_words = ["consultoría", "consultoria", "asesoría", "asesoria", "broker", "rrhh", "reclutamiento", "agencia", "clínica", "hospital", "diagnóstico", "diagnostico"]
        if any(sw in giro.lower() for sw in skip_words): 
            print(f"⏭️  {giro} omitido (fuera de alcance)")
            continue
        rows = await process_combination(i + 1, pais, giro)
        results.extend(rows)
        processed += 1
        if DAILY_LIMIT_COMBOS and processed >= DAILY_LIMIT_COMBOS:
            break
    if results:
        out_path = os.path.join(OUTPUT_DIR, "empresas_raw.csv")
        pd.DataFrame(results).to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"✅ Guardado: {out_path} ({len(results)} empresas)")
    else:
        print("⚠️ No se obtuvieron resultados nuevos.")
    log_path = os.path.join(LOG_DIR, "daily_token_usage.json")
    json.dump({
        "used_tokens": used_tokens,
        "token_limit": TOKEN_LIMIT,
        "token_work_limit": TOKEN_WORK_LIMIT,
        "country": COUNTRY_NAME or "MIX",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }, open(log_path, "w", encoding="utf-8"), indent=2)
    print(f"🧾 Log guardado en {log_path}")

if __name__ == "__main__":
    asyncio.run(main())
