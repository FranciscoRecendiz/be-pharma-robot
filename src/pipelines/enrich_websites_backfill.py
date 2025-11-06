import os, time, asyncio, pandas as pd, aiohttp
from ddgs import DDGS
from utils.site_resolver import resolve_official_site, domain_from_url

INPUT = "/project/data/processed/empresas_filtradas.csv"
OUTPUT = "/project/data/processed/empresas_filtradas_enriched.csv"
WEB_CONCURRENCY = int(os.getenv("WEB_CONCURRENCY", "8"))
_semaphore = asyncio.Semaphore(WEB_CONCURRENCY)

async def process_row(session, ddg, row):
    nombre = str(row.get("nombre_empresa","")).strip()
    pais   = str(row.get("pais","")).strip()
    hinted = str(row.get("sitio_web","")).strip() or str(row.get("fuente","")).strip()
    async with _semaphore:
        info = await resolve_official_site(session, ddg, nombre, pais, hinted)
    row["sitio_web"] = info["sitio_web"]
    row["website_status"] = info["website_status"]
    row["homepage_title"] = info["homepage_title"]
    row["website_confidence"] = info["website_confidence"]
    row["website_source"] = info["website_source"]
    row["last_checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return row

async def main():
    df = pd.read_csv(INPUT, encoding="utf-8-sig")
    ddg = DDGS()
    tasks = []
    async with aiohttp.ClientSession() as session:
        for _, row in df.iterrows():
            if not str(row.get("sitio_web","")).strip():  # solo sin web
                tasks.append(process_row(session, ddg, row))
        results = await asyncio.gather(*tasks, return_exceptions=False)
        if results:
            # fusiona resultados de vuelta
            upd = pd.DataFrame(results)
            df.update(upd)  # empata por índice
    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")
    print(f"✅ Backfill guardado en {OUTPUT}")

if __name__ == "__main__":
    asyncio.run(main())
