"""
BePharma Site Resolver V3
Registro interno → LinkedIn (opcional, controlado) → DDG
Compatible 1:1 con resolve_sites_post actual
"""

import os
import re
import random
import asyncio
import pandas as pd
import aiohttp
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import urlparse
from ddgs import DDGS
from rapidfuzz import fuzz
import tldextract
from bs4 import BeautifulSoup

# =============================================================================
# FUNCIONES AUXILIARES BÁSICAS
# =============================================================================

def normalize_company_name(name: str) -> str:
    """Normaliza nombre de empresa para comparación."""
    if not isinstance(name, str):
        try:
            name = str(name)
        except:
            return ""
    name = name.strip().lower()
    if name in ("nan", "none", "", "null"):
        return ""
    legal_suffixes = [
        r"\bs\.?a\.? de c\.?v\.?\b", r"\bs\.?a\.?\b", r"\bs\. de r\.?l\.?\b",
        r"\bltda\.?\b", r"\bgmbh\b", r"\binc\.?\b", r"\bcorp\.?\b", r"\bco\.?\b",
        r"\bcompany\b", r"\bsasu\b", r"\bsas\b", r"\bs\.?l\.?\b", r"\bs\.?r\.?l\.?\b"
    ]
    for pattern in legal_suffixes:
        name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_domain(url: str) -> str:
    """Extrae dominio limpio de una URL."""
    try:
        if not url:
            return ""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        parsed = urlparse(url)
        hostname = parsed.netloc.lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        ext = tldextract.extract(hostname)
        if not ext.domain:
            return hostname
        domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
        return domain
    except Exception:
        return ""


def is_blocked_domain(domain: str) -> bool:
    """Verifica si un dominio pertenece a redes o directorios bloqueados."""
    if not domain:
        return True
    domain = domain.lower()
    blocked = [
        "linkedin.com","facebook.com","instagram.com","twitter.com","x.com",
        "youtube.com","crunchbase.com","zoominfo.com","bloomberg.com",
        "indeed.com","computrabajo.com","wikipedia.org","wikihow.com",
        "amazon.com","ebay.com","mercadolibre.com","shopify.com",
        "blogspot.com","wordpress.com","wix.com","weebly.com",
        "squarespace.com","godaddy.com","tumblr.com"
    ]
    for b in blocked:
        if b in domain:
            return True
    return False

# =============================================================================
# VALIDADOR DE CONTENIDO
# =============================================================================

class ContentValidator:
    """Valida contenido HTML para detectar sitios corporativos reales."""
    OFFICIAL_INDICATORS = ["productos","servicios","nosotros","contacto","quienes somos",
                           "empresa","fabricación","manufactura","laboratorio","about us",
                           "company","manufacturing","about","contact"]
    ANTI_PATTERNS = ["directorio","directory","listing","perfil de empresa",
                     "company profile","marketplace","tienda online"]

    @staticmethod
    def extract_text_content(html: str) -> str:
        try:
            soup = BeautifulSoup(html, "lxml")
            for s in soup(["script","style"]): s.decompose()
            text = soup.get_text(separator=" ", strip=True)
            return re.sub(r"\s+", " ", text.lower())[:5000]
        except:
            return ""

    @classmethod
    def validate_content(cls, html: str, title: str) -> Dict[str, any]:
        text = cls.extract_text_content(html)
        title_lower = title.lower()
        reasons, confidence = [], 50.0
        if any(p in text or p in title_lower for p in cls.ANTI_PATTERNS):
            return {"is_valid": False, "confidence": 10.0, "reasons": ["Detectado patrón tipo directorio"]}
        indicators = sum(1 for i in cls.OFFICIAL_INDICATORS if i in text)
        if indicators >= 3:
            confidence += 20; reasons.append(f"{indicators} indicadores corporativos")
        elif indicators == 0:
            confidence -= 15; reasons.append("Sin indicadores oficiales")
        if len(text) < 200:
            confidence -= 15; reasons.append("Contenido muy corto")
        elif len(text) > 1000:
            confidence += 10; reasons.append("Contenido sustancial")
        return {"is_valid": confidence >= 50, "confidence": min(100, confidence), "reasons": reasons}

# =============================================================================
# FETCHER HTTP ROBUSTO
# =============================================================================

class RobustFetcher:
    def __init__(self, timeout: int = 15, max_retries: int = 2):
        self.timeout, self.max_retries = timeout, max_retries

    async def fetch_with_validation(self, session: aiohttp.ClientSession, url: str) -> Dict:
        for attempt in range(self.max_retries + 1):
            try:
                async with session.get(url, timeout=self.timeout, ssl=False) as r:
                    if r.status not in (200,301,302): continue
                    html = await r.text(errors="ignore")
                    soup = BeautifulSoup(html, "lxml")
                    title = (soup.title.string or "").strip() if soup.title else ""
                    return {
                        "success": True,
                        "status": r.status,
                        "final_url": str(r.url),
                        "title": title,
                        "content_validation": ContentValidator.validate_content(html, title)
                    }
            except:
                await asyncio.sleep(1.5)
        return {"success": False, "status": 0, "final_url": url,
                "title": "", "content_validation": {"is_valid": False, "confidence": 0, "reasons": ["timeout"]}}

# =============================================================================
# REGISTRO INTERNO
# =============================================================================

REGISTRY_FILE = Path("/project/data/registry/sites_master.csv")
REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)

class RegistryManager:
    def __init__(self):
        if not REGISTRY_FILE.exists():
            pd.DataFrame(columns=[
                "nombre_empresa_normalizado","pais","sitio_web",
                "website_confidence","website_source","last_checked_at"
            ]).to_csv(REGISTRY_FILE, index=False, encoding="utf-8-sig")

    def lookup(self, name: str, country: str) -> Optional[Dict]:
        n = normalize_company_name(name)
        try:
            df = pd.read_csv(REGISTRY_FILE, encoding="utf-8-sig")
            res = df[(df["nombre_empresa_normalizado"] == n) & (df["pais"].str.lower() == country.lower())]
            return res.iloc[0].to_dict() if not res.empty else None
        except: return None

    def upsert(self, data: Dict):
        n, p = normalize_company_name(data.get("nombre_empresa","")), str(data.get("pais",""))
        try: df = pd.read_csv(REGISTRY_FILE, encoding="utf-8-sig")
        except: df = pd.DataFrame(columns=[
            "nombre_empresa_normalizado","pais","sitio_web",
            "website_confidence","website_source","last_checked_at"
        ])
        mask = (df["nombre_empresa_normalizado"] == n) & (df["pais"] == p)
        row = {"nombre_empresa_normalizado": n, "pais": p,
               "sitio_web": data.get("sitio_web",""),
               "website_confidence": data.get("website_confidence",0.0),
               "website_source": data.get("website_source",""),
               "last_checked_at": data.get("last_checked_at","")}
        if mask.any(): df.loc[mask,:] = pd.DataFrame([row]).values
        else: df.loc[len(df)] = row
        df.to_csv(REGISTRY_FILE, index=False, encoding="utf-8-sig")

# =============================================================================
# LINKEDIN (Opcional)
# =============================================================================

class LinkedinResolver:
    def __init__(self):
        self.enabled = os.getenv("USE_LINKEDIN","false").lower() in ("1","true","yes")
        self.cookie = os.getenv("LINKEDIN_LI_AT","")
        self.max_per_day = int(os.getenv("MAX_LINKEDIN_PER_DAY","40"))
        self.count = 0

    async def get_website(self, session: aiohttp.ClientSession, company_name: str) -> Optional[str]:
        if not self.enabled or not self.cookie or self.count >= self.max_per_day:
            return None
        slug = normalize_company_name(company_name).replace(" ","-")
        url = f"https://www.linkedin.com/company/{slug}/about/"
        try:
            async with session.get(url, headers={"User-Agent":"Mozilla/5.0"}, cookies={"li_at":self.cookie}) as r:
                if r.status != 200: return None
                html = await r.text(errors="ignore")
                match = re.search(r'"website"\s*:\s*"([^"]+)"', html)
                if match:
                    self.count += 1
                    site = match.group(1)
                    domain = extract_domain(site)
                    if domain and not is_blocked_domain(domain):
                        return f"https://{domain}"
        except:
            return None
        return None

# =============================================================================
# DDG CANDIDATES
# =============================================================================

class CandidateFinder:
    def __init__(self): self.ddg = DDGS()
    def find(self, name: str, country: str) -> List[str]:
        query = f'"{name}" {country} ("sitio oficial" OR website OR "official site") pharma OR laboratorio -linkedin -facebook -pdf'
        results, seen = [], set()
        try:
            for r in self.ddg.text(query, max_results=10):
                url = (r.get("href") or r.get("url") or "").strip()
                d = extract_domain(url)
                if d and not is_blocked_domain(d) and d not in seen:
                    results.append(f"https://{d}"); seen.add(d)
        except: pass
        return results

# =============================================================================
# RESOLVER PRINCIPAL
# =============================================================================

async def resolve_official_site(session: aiohttp.ClientSession, ddg, company_name: str, country: str, hinted_url: str = "") -> Dict:
    registry, li, finder, fetcher = RegistryManager(), LinkedinResolver(), CandidateFinder(), RobustFetcher()
    nname = normalize_company_name(company_name)

    # 1️⃣ Registro
    cached = registry.lookup(company_name, country)
    if cached and cached.get("sitio_web"):
        return {"sitio_web": cached["sitio_web"], "website_status": 200,
                "homepage_title": "", "website_confidence": float(cached.get("website_confidence",85.0)),
                "website_source": "registry", "validation_reasons": "Recuperado del registro interno"}

    # 2️⃣ LinkedIn
    if li.enabled:
        site = await li.get_website(session, company_name)
        if site:
            res = await fetcher.fetch_with_validation(session, site)
            if res["success"] and res["content_validation"]["is_valid"]:
                title_score = fuzz.token_set_ratio(nname, normalize_company_name(res["title"]))
                conf = res["content_validation"]["confidence"] + (20 if title_score>=80 else 10)
                out = {"sitio_web": f"https://{extract_domain(res['final_url'])}",
                       "website_status": res["status"], "homepage_title": res["title"][:200],
                       "website_confidence": round(conf,1), "website_source": "linkedin",
                       "validation_reasons": "; ".join(res["content_validation"]["reasons"])}
                registry.upsert({**out,"nombre_empresa":company_name,"pais":country,"last_checked_at":pd.Timestamp.now()})
                return out

    # 3️⃣ DDG
    candidates = []
    if hinted_url:
        d = extract_domain(hinted_url)
        if d and not is_blocked_domain(d): candidates.append(f"https://{d}")
    candidates.extend(finder.find(company_name, country))
    for url in candidates:
        res = await fetcher.fetch_with_validation(session, url)
        if not res["success"] or not res["content_validation"]["is_valid"]: continue
        title_score = fuzz.token_set_ratio(nname, normalize_company_name(res["title"]))
        conf = res["content_validation"]["confidence"] + (15 if title_score>=80 else 5)
        if conf >= 60:
            out = {"sitio_web": f"https://{extract_domain(res['final_url'])}",
                   "website_status": res["status"], "homepage_title": res["title"][:200],
                   "website_confidence": round(conf,1), "website_source": "ddg",
                   "validation_reasons": "; ".join(res["content_validation"]["reasons"])}
            registry.upsert({**out,"nombre_empresa":company_name,"pais":country,"last_checked_at":pd.Timestamp.now()})
            return out

    # 4️⃣ Falla
    return {"sitio_web": "", "website_status": 0, "homepage_title": "",
            "website_confidence": 0.0, "website_source": "failed",
            "validation_reasons": "No se encontró sitio válido"}
