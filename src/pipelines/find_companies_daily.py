#!/usr/bin/env python3
"""
██████╗ ███████╗██████╗ ██╗  ██╗ █████╗ ██████╗ ███╗   ███╗ █████╗ 
██╔══██╗██╔════╝██╔══██╗██║  ██║██╔══██╗██╔══██╗████╗ ████║██╔══██╗
██████╔╝█████╗  ██████╔╝███████║███████║██████╔╝██╔████╔██║███████║
██╔══██╗██╔══╝  ██╔═══╝ ██╔══██║██╔══██║██╔══██╗██║╚██╔╝██║██╔══██║
██████╔╝███████╗██║     ██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║
╚═════╝ ╚══════╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝
                                                                     
Discovery Engine V4 - ULTIMATE EDITION
- Búsqueda híbrida (DDG multi-query + fallbacks)
- Validación 360° de nombres reales vs genéricos
- Anti-duplicados con 4 capas de filtrado
- Recovery automático de errores LLM
- Cache inteligente con invalidación
- Guardado incremental ultra-seguro
"""

import os
import sys
import json
import asyncio
import time
import argparse
import re
import unicodedata
import hashlib
import random
import ast
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, asdict, field
from collections import defaultdict, Counter
from datetime import datetime

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
from ddgs import DDGS
from langchain_groq import ChatGroq
import aiohttp
import nest_asyncio
from rapidfuzz import fuzz
import tldextract
from urllib.parse import urlparse

nest_asyncio.apply()

# =============================================================================
# CONFIGURACIÓN GLOBAL
# =============================================================================

class Config:
    """Configuración centralizada"""
    
    # Modelos y límites
    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    MIN_CONFIDENCE = 60
    MIN_NAME_LENGTH = 3
    MAX_NAME_LENGTH = 100
    SIMILARITY_THRESHOLD = 85
    
    # Búsqueda
    DDG_MAX_RESULTS = 20
    DDG_STRATEGIES = 8
    DDG_TIMEOUT = 30
    
    # Concurrencia
    LLM_CONCURRENCY = 2
    SEARCH_CONCURRENCY = 3
    
    # Cache
    CACHE_TTL_DAYS = 30
    CACHE_ENABLED = True
    
    # Nombres genéricos a rechazar (CRÍTICO)
    GENERIC_NAME_PATTERNS = [
        r"^empresa\s+[a-z]{1,3}$",
        r"^nombre\s+(de\s+)?empresa$",
        r"^[a-z]{1,3}\s+pharma$",
        r"^laboratorio\s+[a-z]{1,3}$",
        r"^fabricante\s+[a-z]{1,3}$",
        r"^company\s+[a-z]{1,3}$",
        r"^manufacturer\s+[a-z]{1,3}$",
        r"^ejemplo",
        r"^example",
        r"^test",
        r"^demo",
        r"^placeholder",
        r"^\[.*\]$",  # [Nombre de empresa]
        r"^sin\s+nombre",
        r"^nombre\s+pendiente",
        r"^por\s+definir",
        r"^n\/a$",
        r"^tbd$",
    ]
    
    # Dominios a bloquear (expandido)
    BLOCKED_DOMAINS = {
        # Redes sociales
        "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
        "youtube.com", "tiktok.com", "pinterest.com", "snapchat.com",
        
        # Directorios
        "crunchbase.com", "bloomberg.com", "zoominfo.com", "glassdoor.com",
        "indeed.com", "computrabajo.com", "yellowpages.com", "kompass.com",
        "hotfrog.com", "yelp.com", "foursquare.com", "trustpilot.com",
        "paginas-amarillas.mx", "seccion-amarilla.com.mx", "angi.com",
        
        # Info agregadores
        "wikipedia.org", "wikidata.org", "wikihow.org", "britannica.com",
        "answers.com", "quora.com", "reddit.com", "stackoverflow.com",
        
        # Marketplaces
        "amazon.com", "ebay.com", "mercadolibre.com", "aliexpress.com",
        "alibaba.com", "indiamart.com", "made-in-china.com",
        
        # Otros
        "google.com", "bing.com", "yahoo.com", "msn.com",
        "blogspot.com", "wordpress.com", "wix.com", "weebly.com",
    }
    
    # Keywords de exclusión en giros
    EXCLUDED_GIRO_KEYWORDS = [
        "consultoría", "consultoria", "asesoría", "asesoria",
        "broker", "rrhh", "reclutamiento", "staffing",
        "agencia", "marketing", "publicidad",
        "clínica", "hospital", "diagnóstico", "diagnostico",
        "equipos médicos", "medical devices", "instrumental",
        "CRO", "ensayos clínicos", "clinical trials",
        "research only", "investigación pura"
    ]

# =============================================================================
# UTILIDADES DE NORMALIZACIÓN
# =============================================================================

def normalize_company_name(name: str, aggressive: bool = True) -> str:
    """
    Normalización agresiva de nombres
    
    Args:
        name: Nombre original
        aggressive: Si True, remueve más sufijos (para matching)
    
    Returns:
        Nombre normalizado
    """
    if not isinstance(name, str) or not name.strip():
        return ""
    
    # Normaliza unicode
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    
    # Remueve sufijos legales
    legal_suffixes = [
        r"\bs\.?\s*a\.?\s+de\s+c\.?\s*v\.?\b",
        r"\bs\.?\s*a\.?\b",
        r"\bs\.?\s+de\s+r\.?\s*l\.?\b",
        r"\bltda\.?\b",
        r"\bs\.?\s*r\.?\s*l\.?\b",
        r"\bs\.?\s*l\.?\b",
        r"\bgmbh\b",
        r"\binc\.?\b",
        r"\bcorp\.?\b",
        r"\bco\.?\b",
        r"\bcompany\b",
        r"\blimited\b",
        r"\bltd\.?\b",
    ]
    
    for pattern in legal_suffixes:
        name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    
    if aggressive:
        # Remueve términos genéricos de pharma
        generic_pharma = [
            r"\blaboratorios?\b",
            r"\blaboratory\b",
            r"\bpharma\b",
            r"\bpharmaceuticals?\b",
            r"\bfarmaceutica\b",
            r"\bfarmaceutico\b",
            r"\bindustria\b",
            r"\bgrupo\b",
            r"\bholding\b",
        ]
        
        for pattern in generic_pharma:
            name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    
    # Limpia caracteres especiales y espacios múltiples
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    
    return name

def extract_domain(url: str) -> str:
    """Extrae dominio limpio de URL"""
    if not isinstance(url, str) or not url.strip():
        return ""
    
    try:
        url = url.strip().lower()
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        parsed = urlparse(url)
        hostname = parsed.netloc
        
        # Remueve www
        if hostname.startswith("www."):
            hostname = hostname[4:]
        
        # Usa tldextract para mejor parsing
        ext = tldextract.extract(hostname)
        
        if not ext.domain or not ext.suffix:
            return hostname
        
        return f"{ext.domain}.{ext.suffix}"
    
    except Exception:
        return ""

def slug(s: str) -> str:
    """Slug para archivos"""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s-]+", "_", s)

def hash_data(data: dict) -> str:
    """Hash para cache keys"""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

# =============================================================================
# VALIDADORES DE CALIDAD
# =============================================================================

class NameValidator:
    """Validador de nombres de empresa"""
    
    @staticmethod
    def is_generic(name: str) -> Tuple[bool, Optional[str]]:
        """
        Detecta nombres genéricos/placeholder
        
        Returns:
            (is_generic: bool, reason: Optional[str])
        """
        if not name or len(name) < Config.MIN_NAME_LENGTH:
            return True, "Nombre muy corto"
        
        if len(name) > Config.MAX_NAME_LENGTH:
            return True, "Nombre muy largo (posible descripción)"
        
        name_lower = name.lower().strip()
        
        # Check contra patrones genéricos
        for pattern in Config.GENERIC_NAME_PATTERNS:
            if re.search(pattern, name_lower):
                return True, f"Patrón genérico: {pattern}"
        
        # Check si tiene solo números
        if re.match(r"^[\d\s]+$", name_lower):
            return True, "Solo números"
        
        # Check si es demasiado corto después de normalizar
        normalized = normalize_company_name(name, aggressive=True)
        if len(normalized) < 3:
            return True, "Muy corto después de normalizar"
        
        # Check si contiene palabras clave de placeholder
        placeholder_words = [
            "ejemplo", "example", "test", "demo", "sample",
            "prueba", "placeholder", "tbd", "pending",
            "sin nombre", "nombre pendiente"
        ]
        
        if any(word in name_lower for word in placeholder_words):
            return True, "Contiene palabra placeholder"
        
        return False, None
    
    @staticmethod
    def extract_real_name_from_title(title: str, url: str) -> Optional[str]:
        """
        Intenta extraer nombre real del título de página o URL
        Útil cuando LLM da nombres genéricos
        """
        if not title:
            return None
        
        # Limpia el título
        title = title.strip()
        
        # Patrones comunes en títulos de empresas pharma
        patterns = [
            r"^([A-Z][A-Za-z\s&]+)(?:\s*[-|:]|\s*$)",  # "LIOMONT - Inicio"
            r"^([A-Z][A-Za-z\s&]+(?:Pharma|Lab|Laboratories?))",  # "LIOMONT Pharma"
            r"(?:Laboratorios?\s+)([A-Z][A-Za-z\s&]+)",  # "Laboratorios LIOMONT"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                candidate = match.group(1).strip()
                
                # Valida que no sea genérico
                is_gen, _ = NameValidator.is_generic(candidate)
                if not is_gen and len(candidate) >= 3:
                    return candidate
        
        # Fallback: extrae del dominio
        domain = extract_domain(url)
        if domain:
            # Ej: "liomont.com" → "LIOMONT"
            ext = tldextract.extract(domain)
            if ext.domain and len(ext.domain) >= 3:
                return ext.domain.upper()
        
        return None

# =============================================================================
# MODELO DE DATOS
# =============================================================================

@dataclass
class Company:
    """Modelo de empresa"""
    nombre_empresa: str
    pais: str
    giro: str
    fuente: str
    sector_principal: str = ""
    indicadores_exportacion: str = ""
    confidence_score: float = 0.0
    
    # Metadata interna
    normalized_name: str = field(default="", init=False)
    source_domain: str = field(default="", init=False)
    search_strategy: str = ""
    page_title: str = ""
    is_validated: bool = False
    validation_reason: str = ""
    
    def __post_init__(self):
        """Post-procesamiento después de __init__"""
        self.normalized_name = normalize_company_name(self.nombre_empresa, aggressive=True)
        self.source_domain = extract_domain(self.fuente)
        
        # Validación automática de nombre
        is_generic, reason = NameValidator.is_generic(self.nombre_empresa)
        
        if is_generic:
            self.is_validated = False
            self.validation_reason = reason or "Nombre genérico"
            
            # Intenta extraer nombre real del título
            if self.page_title:
                real_name = NameValidator.extract_real_name_from_title(
                    self.page_title,
                    self.fuente
                )
                
                if real_name:
                    self.nombre_empresa = real_name
                    self.normalized_name = normalize_company_name(real_name, aggressive=True)
                    self.is_validated = True
                    self.validation_reason = "Extraído de título"
        else:
            self.is_validated = True
            self.validation_reason = "OK"
    
    def to_dict(self) -> Dict:
        """Convierte a diccionario (solo campos públicos)"""
        return {
            "nombre_empresa": self.nombre_empresa,
            "pais": self.pais,
            "giro": self.giro,
            "fuente": self.fuente,
            "sector_principal": self.sector_principal,
            "indicadores_exportacion": self.indicadores_exportacion,
            "confidence_score": self.confidence_score,
            "search_strategy": self.search_strategy,
            "is_validated": self.is_validated,
            "validation_reason": self.validation_reason
        }

# =============================================================================
# ANTI-DUPLICADOS AVANZADO (4 CAPAS)
# =============================================================================

class DeduplicationEngine:
    """Motor de deduplicación con 4 capas de filtrado"""
    
    def __init__(self, similarity_threshold: int = Config.SIMILARITY_THRESHOLD):
        self.similarity_threshold = similarity_threshold
        
        # Registries
        self.seen_exact: Set[Tuple[str, str]] = set()  # (normalized_name, country)
        self.seen_domains: Dict[str, Company] = {}  # domain -> first company
        self.seen_fuzzy: Dict[str, List[Company]] = defaultdict(list)  # country -> [companies]
        self.seen_urls: Set[str] = set()  # URLs exactas
        
        # Stats
        self.stats = Counter()
    
    def is_duplicate(self, company: Company) -> Tuple[bool, Optional[str]]:
        """
        Verifica duplicación con 4 capas
        
        Returns:
            (is_duplicate: bool, reason: Optional[str])
        """
        
        # ❌ Capa 1: Validación de nombre
        if not company.is_validated:
            self.stats["rejected_invalid_name"] += 1
            return True, f"Nombre inválido: {company.validation_reason}"
        
        # ❌ Capa 2: Nombre exacto normalizado
        exact_key = (company.normalized_name, company.pais)
        if exact_key in self.seen_exact:
            self.stats["duplicates_exact_name"] += 1
            return True, "Nombre exacto duplicado"
        
        # ❌ Capa 3: Mismo dominio
        if company.source_domain:
            # Check si ya vimos este dominio en este país
            domain_key = f"{company.source_domain}:{company.pais}"
            
            if domain_key in self.seen_domains:
                existing = self.seen_domains[domain_key]
                self.stats["duplicates_same_domain"] += 1
                return True, f"Mismo dominio que '{existing.nombre_empresa}'"
        
        # ❌ Capa 4: Fuzzy matching (solo nombres largos)
        if len(company.normalized_name) >= 5:
            for seen_company in self.seen_fuzzy[company.pais]:
                similarity = fuzz.token_set_ratio(
                    company.normalized_name,
                    seen_company.normalized_name
                )
                
                if similarity >= self.similarity_threshold:
                    self.stats["duplicates_fuzzy"] += 1
                    return True, f"Similar ({similarity}%) a '{seen_company.nombre_empresa}'"
        
        # ✅ No es duplicado
        return False, None
    
    def register(self, company: Company):
        """Registra empresa como vista"""
        # Exact name
        self.seen_exact.add((company.normalized_name, company.pais))
        
        # Domain
        if company.source_domain:
            domain_key = f"{company.source_domain}:{company.pais}"
            if domain_key not in self.seen_domains:
                self.seen_domains[domain_key] = company
        
        # Fuzzy pool
        self.seen_fuzzy[company.pais].append(company)
        
        # URL exacta
        if company.fuente:
            self.seen_urls.add(company.fuente.lower())
        
        self.stats["registered"] += 1
    
    def get_stats(self) -> Dict:
        """Estadísticas"""
        return dict(self.stats)

# =============================================================================
# BÚSQUEDA HÍBRIDA MULTI-ESTRATEGIA
# =============================================================================

class HybridSearchEngine:
    """Motor de búsqueda híbrido con 8+ estrategias"""
    
    def __init__(self, max_results_per_strategy: int = Config.DDG_MAX_RESULTS):
        self.max_results = max_results_per_strategy
        self.ddg = DDGS()
        self.stats = Counter()
    
    def get_region_code(self, country: str) -> Optional[str]:
        """Mapea país a región DDG"""
        country_lower = country.lower()
        
        mapping = {
            "mexico": "mx-es", "méxico": "mx-es",
            "cuba": "cu-es", "argentina": "ar-es",
            "chile": "cl-es", "colombia": "co-es",
            "peru": "pe-es", "perú": "pe-es",
            "ecuador": "ec-es", "uruguay": "uy-es",
            "bolivia": "bo-es", "paraguay": "py-es",
            "venezuela": "ve-es", "españa": "es-es",
            "spain": "es-es", "brasil": "pt-br",
            "brazil": "pt-br",
        }
        
        for key, code in mapping.items():
            if key in country_lower:
                return code
        
        return None
    
    def build_search_strategies(self, country: str, giro: str) -> List[Dict]:
        """
        Construye 8+ estrategias de búsqueda
        
        Returns:
            List[{"name": str, "query": str, "priority": int, "region": str}]
        """
        region = self.get_region_code(country)
        
        # Exclusiones universales
        exclusions = (
            '-linkedin -facebook -instagram -wikipedia -crunchbase '
            '-directorio -directory -kompass -yellowpages -hotfrog '
            '-hospital -clínica -diagnóstico -broker -consultoría '
            '-"ensayos clínicos" -"clinical trials" -CRO -blog -pdf '
            '-recruitment -hiring -jobs -careers'
        )
        
        strategies = []
        
        # 1️⃣ Búsqueda directa con giro específico
        strategies.append({
            "name": "direct_giro",
            "query": f'"{giro}" "{country}" fabricante OR manufacturer {exclusions}',
            "priority": 1,
            "region": region
        })
        
        # 2️⃣ Términos pharma generales
        pharma_terms = [
            ("fabricante medicamentos", "drug_manufacturer"),
            ("laboratorio farmacéutico", "pharma_lab"),
            ("pharmaceutical manufacturer", "pharma_mfg_en"),
            ("fabricante genéricos", "generics_mfg"),
            ("generic manufacturer", "generics_en"),
        ]
        
        for term, slug_name in pharma_terms:
            strategies.append({
                "name": f"pharma_{slug_name}",
                "query": f'{term} "{country}" {exclusions}',
                "priority": 2,
                "region": region
            })
        
        # 3️⃣ CDMO/CMO específico
        strategies.append({
            "name": "cdmo_cmo",
            "query": f'("CDMO" OR "CMO" OR "contract manufacturing") pharmaceutical "{country}" {exclusions}',
            "priority": 2,
            "region": region
        })
        
        # 4️⃣ Suplementos (si aplica)
        if any(kw in giro.lower() for kw in ["suplemento", "nutraceut", "vitamin", "dietary"]):
            strategies.append({
                "name": "supplements",
                "query": f'("fabricante suplementos" OR "dietary supplements manufacturer") "{country}" {exclusions}',
                "priority": 2,
                "region": region
            })
        
        # 5️⃣ Certificaciones GMP
        strategies.append({
            "name": "gmp_certified",
            "query": f'(GMP OR "buenas prácticas") pharmaceutical certified "{country}" {exclusions}',
            "priority": 3,
            "region": region
        })
        
        # 6️⃣ Exportadores
        strategies.append({
            "name": "exporters",
            "query": f'("exportador medicamentos" OR "pharmaceutical exporter") "{country}" {exclusions}',
            "priority": 3,
            "region": region
        })
        
        # 7️⃣ Asociaciones farmacéuticas
        strategies.append({
            "name": "associations",
            "query": f'("cámara farmacéutica" OR "pharmaceutical association" OR "ANIFAM" OR "AFIDRO") "{country}" {exclusions}',
            "priority": 4,
            "region": region
        })
        
        # 8️⃣ Ferias internacionales (CPhI, DCAT)
        strategies.append({
            "name": "trade_shows",
            "query": f'("CPhI" OR "DCAT" OR "Pharmapack") exhibitor "{country}" {exclusions}',
            "priority": 4,
            "region": region
        })
        
        return strategies
    
    async def execute_strategy(self, strategy: Dict) -> List[Dict]:
        """Ejecuta una estrategia de búsqueda"""
        try:
            kwargs = {
                "max_results": self.max_results,
                "safesearch": "off",
                "timeout": Config.DDG_TIMEOUT
            }
            
            if strategy.get("region"):
                kwargs["region"] = strategy["region"]
            
            results = []
            seen_domains = set()
            
            for result in self.ddg.text(strategy["query"], **kwargs):
                url = (result.get("href") or result.get("url") or "").strip()
                
                if not url:
                    continue
                
                domain = extract_domain(url)
                
                # Dedupe por dominio
                if not domain or domain in seen_domains:
                    continue
                
                # Skip dominios bloqueados
                if domain in Config.BLOCKED_DOMAINS:
                    continue
                
                seen_domains.add(domain)
                
                results.append({
                    "title": result.get("title", ""),
                    "body": result.get("body", "")[:500],
                    "url": url,
                    "domain": domain,
                    "strategy": strategy["name"],
                    "priority": strategy["priority"]
                })
            
            self.stats[f"strategy_{strategy['name']}"] += len(results)
            print(f"   └─ {strategy['name']:<20} {len(results):>3} resultados")
            
            return results
        
        except Exception as e:
            print(f"   └─ ⚠️ {strategy['name']}: {str(e)[:50]}")
            self.stats["errors"] += 1
            return []
    
    async def search_all_strategies(
        self,
        country: str,
        giro: str
    ) -> List[Dict]:
        """
        Ejecuta todas las estrategias en paralelo con límite
        
        Returns:
            Lista de resultados únicos por dominio
        """
        print(f"\n🔍 Búsqueda híbrida: {country} | {giro}")
        
        strategies = self.build_search_strategies(country, giro)
        
        # Ejecuta con concurrencia limitada
        semaphore = asyncio.Semaphore(Config.SEARCH_CONCURRENCY)
        
        async def execute_with_limit(strat):
            async with semaphore:
                await asyncio.sleep(random.uniform(0.5, 2.0))  # Jitter anti-rate-limit
                return await self.execute_strategy(strat)
        
        tasks = [execute_with_limit(s) for s in strategies]
        results_per_strategy = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combina resultados
        all_results = []
        for strategy_results in results_per_strategy:
            if isinstance(strategy_results, Exception):
                self.stats["errors"] += 1
                continue
            all_results.extend(strategy_results)
        
        # Dedupe por dominio (mantiene el de mayor prioridad)
        unique_by_domain = {}
        for result in all_results:
            domain = result["domain"]
            
            if domain not in unique_by_domain:
                unique_by_domain[domain] = result
            elif result["priority"] < unique_by_domain[domain]["priority"]:
                # Menor priority number = mayor prioridad
                unique_by_domain[domain] = result
        
        # Ordena por prioridad
        unique_results = sorted(
            unique_by_domain.values(),
            key=lambda x: x["priority"]
        )
        
        self.stats["total_results"] += len(unique_results)
        self.stats["total_raw_results"] += len(all_results)
        
        print(f"   ✅ {len(unique_results)} únicos (de {len(all_results)} totales)\n")
        
        return unique_results

# =============================================================================
# ANALIZADOR LLM CON RECOVERY
# =============================================================================

class RobustLLMAnalyzer:
    """Analizador LLM con recovery avanzado"""
    
    PROMPT_TEMPLATE = """Eres un analista senior de inteligencia farmacéutica en BePharma.

Analiza estos resultados web para "{giro}" en "{pais}".

CRITERIOS INCLUSIÓN (SOLO si fabrican o producen):
✅ Medicamentos Rx/OTC/genéricos/innovadores
✅ Biotecnológicos/biológicos
✅ Suplementos/vitamínicos/nutracéuticos/dermocosméticos
✅ CDMO/CMO farmacéuticos (fabricación por contrato)
✅ APIs (Active Pharmaceutical Ingredients)

CRITERIOS EXCLUSIÓN ESTRICTA:
❌ CRO (investigación pura sin fabricación)
❌ Equipos/dispositivos médicos (excepto si también fabrican medicamentos)
❌ Diagnóstico in-vitro
❌ Consultorías, brokers, distribuidores puros
❌ Hospitales, clínicas, farmacias
❌ Directorios, agregadores

🔴 CRÍTICO - NOMBRES:
- USA EL NOMBRE REAL de la empresa del título o contenido
- NUNCA uses "Empresa ABC", "Nombre Empresa", "Laboratorio XYZ"
- Si no encuentras nombre real, omite esa empresa del JSON

RESULTADOS WEB:
{results_json}

Devuelve JSON válido (sin markdown):
[
  {{
    "nombre_empresa": "Nombre Real Completo",
    "pais": "{pais}",
    "giro": "{giro}",
    "fuente": "https://empresa.com",
    "sector_principal": "Medicamentos genéricos",
    "indicadores_exportacion": "Exporta a 10 países, CPhI 2023",
    "confidence_score": 85
  }}
]

SOLO incluye empresas con nombre real (confidence_score >= 50).
Si NO hay empresas válidas, devuelve: []
"""
    
    def __init__(self, model: str = Config.DEFAULT_MODEL):
        self.llm = ChatGroq(model=model, temperature=0.1)
        self.semaphore = asyncio.Semaphore(Config.LLM_CONCURRENCY)
        self.stats = Counter()
    
    @retry(
        stop=stop_after_attempt(6),
        wait=wait_exponential_jitter(initial=2, max=120),
        retry=retry_if_exception_type((aiohttp.ClientError, TimeoutError))
    )
    async def analyze(
        self,
        country: str,
        giro: str,
        search_results: List[Dict]
    ) -> List[Company]:
        """Analiza resultados con LLM y recovery robusto"""
        
        async with self.semaphore:
            # Anti-rate-limit jitter
            await asyncio.sleep(random.uniform(0.2, 0.8))
            
            try:
                # Prepara datos para prompt (con títulos para extracción de nombres)
                results_for_prompt = []
                for r in search_results[:30]:  # Limita a 30 para tokens
                    results_for_prompt.append({
                        "title": r["title"],
                        "description": r["body"],
                        "url": r["url"]
                    })
                
                results_json = json.dumps(results_for_prompt, ensure_ascii=False, indent=2)
                
                prompt = self.PROMPT_TEMPLATE.format(
                    giro=giro,
                    pais=country,
                    results_json=results_json
                )
                
                # Invoca LLM
                response = await asyncio.to_thread(self.llm.invoke, prompt)
                content = (response.content or "").strip()
                
                # Parse con recovery multi-nivel
                data = self._parse_json_response(content)
                
                if not isinstance(data, list):
                    self.stats["llm_invalid_response"] += 1
                    print(f"   ⚠️ LLM no devolvió lista válida")
                    return []
                
                # Convierte a Company objects
                companies = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    
                    # Valida campos mínimos
                    if not item.get("nombre_empresa") or not item.get("fuente"):
                        self.stats["llm_missing_fields"] += 1
                        continue
                    
                    # Busca título de página en search_results
                    page_title = ""
                    item_url = item.get("fuente", "")
                    for sr in search_results:
                        if sr["url"] == item_url:
                            page_title = sr["title"]
                            break
                    
                    company = Company(
                        nombre_empresa=str(item.get("nombre_empresa", "")).strip(),
                        pais=str(item.get("pais", country)).strip(),
                        giro=str(item.get("giro", giro)).strip(),
                        fuente=str(item.get("fuente", "")).strip(),
                        sector_principal=str(item.get("sector_principal", "")).strip(),
                        indicadores_exportacion=str(item.get("indicadores_exportacion", "")).strip(),
                        confidence_score=float(item.get("confidence_score", 50)),
                        page_title=page_title,
                        search_strategy="llm_analysis"
                    )
                    
                    # Solo acepta con confidence >= MIN
                    if company.confidence_score >= Config.MIN_CONFIDENCE:
                        companies.append(company)
                    else:
                        self.stats["llm_low_confidence"] += 1
                
                self.stats["llm_success"] += 1
                self.stats["companies_extracted"] += len(companies)
                
                return companies
            
            except Exception as e:
                error_str = str(e)
                
                # Detecta rate limits
                if "429" in error_str or "rate" in error_str.lower():
                    self.stats["llm_rate_limit"] += 1
                    print(f"   ⚠️ Rate limit, reintentando...")
                    await asyncio.sleep(10)
                    raise aiohttp.ClientError(error_str)
                
                self.stats["llm_error"] += 1
                print(f"   ❌ Error LLM: {str(e)[:100]}")
                return []
    
    def _parse_json_response(self, content: str) -> Optional[List]:
        """Parse robusto con múltiples estrategias"""
        
        # Estrategia 1: JSON directo
        try:
            return json.loads(content)
        except:
            pass
        
        # Estrategia 2: Extrae entre corchetes
        try:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1:
                return json.loads(content[start:end+1])
        except:
            pass
        
        # Estrategia 3: Remueve markdown
        try:
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content)
            return json.loads(content)
        except:
            pass
        
        # Estrategia 4: Reemplaza comillas simples
        try:
            content = content.replace("'", '"')
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end != -1:
                return json.loads(content[start:end+1])
        except:
            pass
        
        # Estrategia 5: ast.literal_eval (último recurso)
        try:
            return ast.literal_eval(content)
        except:
            pass
        
        self.stats["parse_failures"] += 1
        return None
    
    def get_stats(self) -> Dict:
        """Estadísticas"""
        return dict(self.stats)

# =============================================================================
# CACHE MANAGER
# =============================================================================

class CacheManager:
    """Gestor de cache inteligente"""
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stats = Counter()
    
    def get_cache_key(self, country: str, giro: str, domains: List[str]) -> str:
        """Genera key único para combinación"""
        data = {
            "country": country,
            "giro": giro,
            "domains": sorted(set(domains)),
            "version": "v4"  # Invalida cache de versiones anteriores
        }
        return hash_data(data)
    
    def load(self, cache_key: str) -> Optional[List[Dict]]:
        """Carga desde cache si válido"""
        if not Config.CACHE_ENABLED:
            return None
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            self.stats["miss"] += 1
            return None
        
        try:
            # Check edad
            age_days = (time.time() - cache_file.stat().st_mtime) / 86400
            
            if age_days > Config.CACHE_TTL_DAYS:
                self.stats["expired"] += 1
                return None
            
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.stats["hit"] += 1
            print(f"   📦 Cache hit (edad: {age_days:.1f} días)")
            
            return data
        
        except Exception as e:
            self.stats["errors"] += 1
            print(f"   ⚠️ Error leyendo cache: {e}")
            return None
    
    def save(self, cache_key: str, data: List[Dict]):
        """Guarda en cache"""
        if not Config.CACHE_ENABLED:
            return
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.stats["saved"] += 1
        
        except Exception as e:
            self.stats["save_errors"] += 1
            print(f"   ⚠️ Error guardando cache: {e}")
    
    def get_stats(self) -> Dict:
        """Estadísticas"""
        return dict(self.stats)

# =============================================================================
# ORQUESTADOR PRINCIPAL
# =============================================================================

class UltimateDiscoveryOrchestrator:
    """Orquestador maestro del discovery engine V4"""
    
    def __init__(self, args):
        self.args = args
        
        # Componentes
        self.search_engine = HybridSearchEngine(max_results_per_strategy=args.ddg_max)
        self.llm_analyzer = RobustLLMAnalyzer(model=args.model)
        self.dedup_engine = DeduplicationEngine()
        self.cache_manager = CacheManager(Path(args.cache_dir))
        
        # Stats globales
        self.global_stats = Counter()
        self.start_time = time.time()
    
    async def process_combination(
        self,
        country: str,
        giro: str
    ) -> List[Company]:
        """Procesa una combinación país-giro"""
        
        self.global_stats["combinations_processed"] += 1
        
        # 1️⃣ Búsqueda híbrida multi-estrategia
        search_results = await self.search_engine.search_all_strategies(country, giro)
        
        if not search_results:
            self.global_stats["combinations_no_results"] += 1
            print(f"   ⚠️ Sin resultados de búsqueda\n")
            return []
        
        # 2️⃣ Check cache
        domains = [r["domain"] for r in search_results]
        cache_key = self.cache_manager.get_cache_key(country, giro, domains)
        
        cached_data = self.cache_manager.load(cache_key)
        
        if cached_data:
            # Reconstruye desde cache
            companies = [
                Company(
                    nombre_empresa=item["nombre_empresa"],
                    pais=item["pais"],
                    giro=item["giro"],
                    fuente=item["fuente"],
                    sector_principal=item.get("sector_principal", ""),
                    indicadores_exportacion=item.get("indicadores_exportacion", ""),
                    confidence_score=item.get("confidence_score", 50),
                    page_title=item.get("page_title", ""),
                    search_strategy=item.get("search_strategy", "cached")
                )
                for item in cached_data
            ]
            
            self.global_stats["cache_hits"] += 1
        
        else:
            # 3️⃣ Análisis con LLM
            companies = await self.llm_analyzer.analyze(country, giro, search_results)
            
            # Guarda en cache (solo las validadas)
            valid_for_cache = [c.to_dict() for c in companies if c.is_validated]
            if valid_for_cache:
                self.cache_manager.save(cache_key, valid_for_cache)
        
        if not companies:
            self.global_stats["combinations_no_companies"] += 1
            print(f"   ℹ️ LLM no identificó empresas válidas\n")
            return []
        
        # 4️⃣ Deduplicación avanzada
        unique_companies = []
        
        for company in companies:
            is_dup, reason = self.dedup_engine.is_duplicate(company)
            
            if is_dup:
                self.global_stats["duplicates_filtered"] += 1
                print(f"   ⏭️ Duplicado: {company.nombre_empresa[:40]} ({reason})")
                continue
            
            unique_companies.append(company)
            self.dedup_engine.register(company)
        
        self.global_stats["companies_accepted"] += len(unique_companies)
        
        if unique_companies:
            print(f"   ✅ {len(unique_companies)} empresas únicas (de {len(companies)} candidatas)")
        
        print()  # Línea en blanco
        
        return unique_companies
    
    def print_progress(self, batch_num: int, total_batches: int, all_companies: List[Company]):
        """Imprime progreso detallado"""
        elapsed = time.time() - self.start_time
        
        print(f"\n{'='*80}")
        print(f"📊 PROGRESO - Batch {batch_num}/{total_batches}")
        print(f"{'='*80}")
        print(f"⏱️  Tiempo transcurrido:     {elapsed/60:.1f} min")
        print(f"🔍 Combinaciones procesadas: {self.global_stats['combinations_processed']}")
        print(f"📦 Cache hits:               {self.global_stats['cache_hits']}")
        print(f"✅ Empresas aceptadas:       {len(all_companies)}")
        print(f"⏭️  Duplicados filtrados:     {self.global_stats['duplicates_filtered']}")
        
        if all_companies:
            # Distribución por país
            by_country = Counter(c.pais for c in all_companies)
            print(f"\n📍 Por país:")
            for country, count in by_country.most_common(5):
                print(f"   {country:<25} {count:>4}")
        
        print(f"{'='*80}\n")
    
    def print_final_stats(self, all_companies: List[Company]):
        """Imprime estadísticas finales"""
        elapsed = time.time() - self.start_time
        
        print(f"\n{'='*80}")
        print(f"🎯 ESTADÍSTICAS FINALES")
        print(f"{'='*80}")
        print(f"⏱️  Tiempo total:            {elapsed/60:.1f} minutos")
        print(f"🔍 Combinaciones procesadas: {self.global_stats['combinations_processed']}")
        print(f"✅ Empresas encontradas:     {len(all_companies)}")
        print(f"⏭️  Duplicados filtrados:     {self.global_stats['duplicates_filtered']}")
        print(f"📦 Cache hits:               {self.global_stats['cache_hits']}")
        
        # Deduplicación stats
        dedup_stats = self.dedup_engine.get_stats()
        print(f"\n🔍 Deduplicación:")
        print(f"   Empresas registradas:     {dedup_stats.get('registered', 0)}")
        print(f"   Nombres inválidos:        {dedup_stats.get('rejected_invalid_name', 0)}")
        print(f"   Duplicados exactos:       {dedup_stats.get('duplicates_exact_name', 0)}")
        print(f"   Duplicados por dominio:   {dedup_stats.get('duplicates_same_domain', 0)}")
        print(f"   Duplicados fuzzy:         {dedup_stats.get('duplicates_fuzzy', 0)}")
        
        # Search stats
        search_stats = self.search_engine.stats
        print(f"\n🔎 Búsqueda:")
        print(f"   Resultados totales:       {search_stats.get('total_results', 0)}")
        print(f"   Resultados crudos:        {search_stats.get('total_raw_results', 0)}")
        print(f"   Errores:                  {search_stats.get('errors', 0)}")
        
        # LLM stats
        llm_stats = self.llm_analyzer.get_stats()
        print(f"\n🤖 LLM:")
        print(f"   Llamadas exitosas:        {llm_stats.get('llm_success', 0)}")
        print(f"   Empresas extraídas:       {llm_stats.get('companies_extracted', 0)}")
        print(f"   Respuestas inválidas:     {llm_stats.get('llm_invalid_response', 0)}")
        print(f"   Rate limits:              {llm_stats.get('llm_rate_limit', 0)}")
        print(f"   Errores:                  {llm_stats.get('llm_error', 0)}")
        
        # Cache stats
        cache_stats = self.cache_manager.get_stats()
        print(f"\n💾 Cache:")
        print(f"   Hits:                     {cache_stats.get('hit', 0)}")
        print(f"   Misses:                   {cache_stats.get('miss', 0)}")
        print(f"   Expirados:                {cache_stats.get('expired', 0)}")
        print(f"   Guardados:                {cache_stats.get('saved', 0)}")
        
        if all_companies:
            # Distribución de confidence
            print(f"\n📊 Confidence:")
            confidences = [c.confidence_score for c in all_companies]
            avg_conf = sum(confidences) / len(confidences)
            print(f"   Promedio:                 {avg_conf:.1f}%")
            
            ranges = [
                (90, 100, "90-100% (Excelente)"),
                (80, 90, "80-89% (Muy bueno)"),
                (70, 80, "70-79% (Bueno)"),
                (60, 70, "60-69% (Aceptable)")
            ]
            
            for min_c, max_c, label in ranges:
                count = sum(1 for c in confidences if min_c <= c < max_c)
                pct = count / len(confidences) * 100
                print(f"   {label:<25} {count:>4} ({pct:>5.1f}%)")
            
            # Top empresas
            print(f"\n🏆 Top 10 por confidence:")
            sorted_companies = sorted(all_companies, key=lambda x: x.confidence_score, reverse=True)
            for i, company in enumerate(sorted_companies[:10], 1):
                name_short = company.nombre_empresa[:35] + "..." if len(company.nombre_empresa) > 35 else company.nombre_empresa
                print(f"   {i:2}. {name_short:<38} {company.confidence_score:.0f}% | {company.pais}")
        
        print(f"{'='*80}\n")

# =============================================================================
# GUARDADO INCREMENTAL ULTRA-SEGURO
# =============================================================================

def save_incremental(companies: List[Company], output_dir: Path, suffix: str = "partial"):
    """Guardado incremental ultra-seguro con backups"""
    try:
        if not companies:
            return
        
        # Convierte a DataFrame
        df = pd.DataFrame([c.to_dict() for c in companies])
        
        # Archivo de salida
        output_file = output_dir / f"empresas_raw_{suffix}.csv"
        
        # Backup del anterior si existe
        if output_file.exists():
            backup_file = output_dir / f"empresas_raw_{suffix}_backup.csv"
            output_file.rename(backup_file)
        
        # Guarda nuevo
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        
        print(f"💾 Guardado incremental: {len(companies)} empresas → {output_file.name}")
    
    except Exception as e:
        print(f"❌ Error en guardado incremental: {e}")

# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="BePharma Discovery Engine V4 - ULTIMATE EDITION",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:

  # Ejecución estándar
  python discovery_engine_v4_ultimate.py

  # Solo un país
  python discovery_engine_v4_ultimate.py --country Mexico

  # Alta cobertura (más resultados por estrategia)
  python discovery_engine_v4_ultimate.py --ddg-max 25

  # Alta calidad (solo confidence >70%)
  python discovery_engine_v4_ultimate.py --min-confidence 70
        """
    )
    
    parser.add_argument("--input", default="/project/data/raw/icp_targets.csv")
    parser.add_argument("--output-dir", default="/project/data/processed")
    parser.add_argument("--log-dir", default="/project/data/logs")
    parser.add_argument("--cache-dir", default="/project/data/cache/groq_v4")
    parser.add_argument("--country", default="", help="Filtrar por país")
    parser.add_argument("--daily-limit-combos", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--ddg-max", type=int, default=20)
    parser.add_argument("--min-confidence", type=int, default=60)
    parser.add_argument("--model", default=Config.DEFAULT_MODEL)
    parser.add_argument("--no-cache", action="store_true", help="Deshabilita cache")
    
    return parser.parse_args()


async def main():
    """Función principal"""
    args = parse_args()
    
    # Deshabilita cache si se solicita
    if args.no_cache:
        Config.CACHE_ENABLED = False
    
    # Setup directorios
    country_slug = slug(args.country) if args.country else ""
    output_dir = Path(args.output_dir) / country_slug if country_slug else Path(args.output_dir)
    log_dir = Path(args.log_dir) / country_slug if country_slug else Path(args.log_dir)
    cache_dir = Path(args.cache_dir)
    
    for directory in [output_dir, log_dir, cache_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Banner
    print(f"\n{'='*80}")
    print("🚀 BePharma Discovery Engine V4 - ULTIMATE EDITION")
    print(f"{'='*80}")
    print(f"País:                  {args.country or 'TODOS'}")
    print(f"Límite combos:         {args.daily_limit_combos}")
    print(f"Min confidence:        {args.min_confidence}%")
    print(f"DDG resultados/query:  {args.ddg_max}")
    print(f"Modelo LLM:            {args.model}")
    print(f"Cache:                 {'DESHABILITADO' if args.no_cache else 'HABILITADO'}")
    print(f"{'='*80}\n")
    
    # Carga ICP
    print(f"📂 Cargando ICP desde: {args.input}")
    df = pd.read_csv(args.input, encoding="utf-8-sig")
    
    # Limpieza
    df = df[df["country"].notna() & df["giro"].notna()]
    df["country"] = df["country"].astype(str).str.strip()
    df["giro"] = df["giro"].astype(str).str.strip()
    
    # Filtro por país
    if args.country:
        df = df[df["country"].str.contains(args.country, case=False, na=False)]
        if df.empty:
            print(f"❌ No hay datos para: {args.country}")
            return
    
    # Filtro de giros excluidos
    df["excluded"] = df["giro"].str.lower().apply(
        lambda x: any(kw in str(x).lower() for kw in Config.EXCLUDED_GIRO_KEYWORDS)
    )
    
    df_filtered = df[~df["excluded"]].copy()
    
    if len(df) > len(df_filtered):
        print(f"⏭️  {len(df) - len(df_filtered)} giros excluidos (fuera de alcance)")
    
    print(f"✅ {len(df_filtered)} combinaciones válidas\n")
    
    # Mezcla aleatoria
    df_filtered = df_filtered.sample(frac=1, random_state=int(time.time()) % 10000).reset_index(drop=True)
    
    # Limita
    if args.daily_limit_combos > 0:
        df_filtered = df_filtered.head(args.daily_limit_combos)
        print(f"📊 Procesando {len(df_filtered)} combinaciones (límite diario)\n")
    
    # Inicializa orchestrator
    orchestrator = UltimateDiscoveryOrchestrator(args)
    
    # Procesa en batches
    all_companies = []
    batch_size = args.batch_size
    total_batches = (len(df_filtered) + batch_size - 1) // batch_size
    
    for batch_num in range(0, len(df_filtered), batch_size):
        batch_df = df_filtered.iloc[batch_num:batch_num+batch_size]
        current_batch = (batch_num // batch_size) + 1
        
        print(f"\n{'='*80}")
        print(f"📦 BATCH {current_batch}/{total_batches}")
        print(f"{'='*80}\n")
        
        tasks = []
        for _, row in batch_df.iterrows():
            country = str(row["country"]).strip()
            giro = str(row["giro"]).strip()
            
            task = orchestrator.process_combination(country, giro)
            tasks.append(task)
        
        # Ejecuta batch
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Procesa resultados
        for result in batch_results:
            if isinstance(result, Exception):
                print(f"❌ Error en batch: {result}")
                continue
            
            if isinstance(result, list):
                all_companies.extend(result)
        
        # Guardado incremental
        if all_companies:
            save_incremental(all_companies, output_dir, suffix="partial")
        
        # Progreso
        orchestrator.print_progress(current_batch, total_batches, all_companies)
        
        # Pausa entre batches
        if batch_num + batch_size < len(df_filtered):
            pause = 3
            print(f"⏸️  Pausa de {pause}s...")
            await asyncio.sleep(pause)
    
    # Resultados finales
    print(f"\n{'='*80}")
    print("🎯 CONSOLIDANDO RESULTADOS FINALES")
    print(f"{'='*80}\n")
    
    if not all_companies:
        print("⚠️ No se encontraron empresas")
        orchestrator.print_final_stats([])
        return
    
    # DataFrame final
    final_df = pd.DataFrame([c.to_dict() for c in all_companies])
    
    # Ordena por confidence
    final_df = final_df.sort_values("confidence_score", ascending=False).reset_index(drop=True)
    
    # Guarda
    output_file = output_dir / "empresas_raw.csv"
    final_df.to_csv(output_file, index=False, encoding="utf-8-sig")
    
    print(f"✅ {len(final_df)} empresas guardadas en:")
    print(f"   {output_file}\n")
    
    # Stats finales
    orchestrator.print_final_stats(all_companies)
    
    # Guarda log detallado
    log_data = {
        "execution_time": datetime.now().isoformat(),
        "duration_minutes": round((time.time() - orchestrator.start_time) / 60, 2),
        "config": {
            "country": args.country or "ALL",
            "daily_limit_combos": args.daily_limit_combos,
            "min_confidence": args.min_confidence,
            "ddg_max": args.ddg_max,
            "model": args.model,
            "cache_enabled": Config.CACHE_ENABLED
        },
        "global_stats": dict(orchestrator.global_stats),
        "dedup_stats": orchestrator.dedup_engine.get_stats(),
        "search_stats": dict(orchestrator.search_engine.stats),
        "llm_stats": orchestrator.llm_analyzer.get_stats(),
        "cache_stats": orchestrator.cache_manager.get_stats(),
        "results": {
            "total_companies": len(final_df),
            "avg_confidence": float(final_df["confidence_score"].mean()) if not final_df.empty else 0,
            "by_country": final_df["pais"].value_counts().to_dict() if not final_df.empty else {},
            "by_sector": final_df["sector_principal"].value_counts().head(10).to_dict() if not final_df.empty else {}
        }
    }
    
    log_file = log_dir / f"discovery_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
    
    print(f"📋 Log detallado: {log_file}")
    print(f"\n{'='*80}")
    print("✅ PROCESO COMPLETADO EXITOSAMENTE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Proceso interrumpido por usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error crítico: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)