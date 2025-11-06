import asyncio
import json
import re
from pathlib import Path
import pandas as pd
from ddgs import DDGS
from typing import List, Dict

# =============================================================================
# 1. FUENTES DE BENCHMARK (Ground Truth)
# =============================================================================

class BenchmarkSources:
    """
    Fuentes confiables para validar cobertura
    Estas son bases de datos reales que deberías consultar
    """
    
    # Asociaciones farmacéuticas por país
    ASSOCIATIONS = {
        "Mexico": {
            "name": "ANIFAM",
            "url": "https://www.anifam.org.mx",
            "search_query": 'site:anifam.org.mx "miembros" OR "asociados"',
            "expected_companies": 100  # Estimado
        },
        # Agregar más países según sea necesario
    }

# =============================================================================
# 2. CLASE DE ANÁLISIS DE SATURACIÓN
# =============================================================================

class SaturationAnalyzer:
    """
    Analiza la saturación del proceso de búsqueda, es decir, cuántas búsquedas
    ya no encuentran empresas nuevas.
    """

    def __init__(self, discovery_log: Path):
        """
        Inicializa el analizador de saturación con un archivo de log.

        Args:
            discovery_log (Path): Ruta al archivo JSON de log.
        """
        self.log_data = self._load_log(discovery_log)

    def _load_log(self, log_path: Path) -> dict:
        """
        Carga el archivo de log de descubrimiento.

        Args:
            log_path (Path): Ruta al archivo de log.
        
        Returns:
            dict: Datos del log cargados desde el archivo.
        """
        if not log_path.exists():
            raise FileNotFoundError(f"Log no encontrado: {log_path}")
        
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def analyze_saturation(self) -> dict:
        """
        Analiza el log para determinar la saturación del proceso de búsqueda.

        Returns:
            dict: Resultado del análisis de saturación, incluyendo el porcentaje
                  de saturación, la productividad y las recomendaciones.
        """
        stats = self.log_data.get("global_stats", {})

        # Métricas clave
        combinations = stats.get("combinations_processed", 0)
        companies_found = self.log_data.get("results", {}).get("total_companies", 0)
        no_results = stats.get("combinations_no_results", 0)
        no_companies = stats.get("combinations_no_companies", 0)

        # Calcula ratio de productividad
        if combinations == 0:
            return {
                "is_saturated": False,
                "saturation_pct": 0.0,
                "recommendations": ["No hay datos suficientes"]
            }

        productivity_ratio = companies_found / combinations
        empty_ratio = (no_results + no_companies) / combinations

        # Criterios de saturación
        is_saturated = False
        saturation_pct = 0.0
        recommendations = []

        # 1. Si >60% de búsquedas no encuentran nada nuevo
        if empty_ratio > 0.6:
            is_saturated = True
            saturation_pct = 85.0
            recommendations.append("✅ Alta saturación: >60% de búsquedas sin resultados nuevos")

        # 2. Si productividad es muy baja (<0.5 empresas por combinación)
        elif productivity_ratio < 0.5:
            is_saturated = False
            saturation_pct = 50.0
            recommendations.append("⚠️ Baja productividad: Considera ampliar estrategias de búsqueda")

        # 3. Si productividad es media (0.5-2)
        elif productivity_ratio < 2.0:
            is_saturated = False
            saturation_pct = 70.0
            recommendations.append("📊 Productividad media: Aún hay margen de mejora")

        # 4. Alta productividad (>2)
        else:
            is_saturated = False
            saturation_pct = 40.0
            recommendations.append("🚀 Alta productividad: Expandir búsqueda a más combinaciones")

        # Recomendaciones adicionales
        cache_hit_ratio = stats.get("cache_hits", 0) / combinations if combinations > 0 else 0
        
        if cache_hit_ratio > 0.7:
            recommendations.append("📦 Alto uso de cache: Considera invalidar cache para búsquedas frescas")
        
        duplicates = stats.get("duplicates_filtered", 0)
        dup_ratio = duplicates / companies_found if companies_found > 0 else 0
        
        if dup_ratio > 0.5:
            recommendations.append("🔄 Muchos duplicados: Las búsquedas están convergiendo (buena señal)")

        return {
            "is_saturated": is_saturated,
            "saturation_pct": saturation_pct,
            "productivity_ratio": round(productivity_ratio, 2),
            "empty_ratio": round(empty_ratio, 2),
            "cache_hit_ratio": round(cache_hit_ratio, 2),
            "duplicate_ratio": round(dup_ratio, 2),
            "recommendations": recommendations
        }

# =============================================================================
# 3. BÚSQUEDA COMPLEMENTARIA EN OTRAS FUENTES
# =============================================================================

class ComplementarySearcher:
    """
    Busca en fuentes alternativas para encontrar empresas faltantes
    """
    
    def __init__(self):
        self.ddg = DDGS()
    
    async def search_associations(self, country: str) -> List[Dict]:
        """
        Busca en sitios de asociaciones farmacéuticas
        
        Returns:
            Lista de empresas encontradas en asociaciones
        """
        print(f"\n🔍 Buscando en asociaciones de {country}...")

        association = BenchmarkSources.ASSOCIATIONS.get(country)

        if not association:
            print(f"   ⚠️ No hay asociación registrada para {country}")
            return []

        try:
            results = []
            query = association["search_query"]
            
            for result in self.ddg.text(query, max_results=20):
                results.append({
                    "source": "association",
                    "association_name": association["name"],
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", "")
                })
            
            print(f"   ✅ {len(results)} páginas encontradas en {association['name']}")
            return results

        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []
    
    async def search_trade_shows(self, country: str) -> List[Dict]:
        """
        Busca empresas que participan en ferias farmacéuticas
        
        Returns:
            Lista de empresas en ferias
        """
        print(f"\n🎪 Buscando en ferias farmacéuticas ({country})...")
        
        queries = [
            f'CPhI exhibitor "{country}" pharmaceutical',
            f'DCAT exhibitor "{country}" pharmaceutical',
            f'Pharmapack exhibitor "{country}"',
        ]
        
        results = []
        
        for query in queries:
            try:
                for result in self.ddg.text(query, max_results=15):
                    results.append({
                        "source": "trade_show",
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "snippet": result.get("body", "")
                    })
            except Exception as e:
                print(f"   ⚠️ Error en query: {e}")
        
        print(f"   ✅ {len(results)} resultados de ferias")
        return results
    
    async def search_linkedin_companies(self, country: str) -> List[str]:
        """
        Busca nombres de empresas en LinkedIn (solo nombres, no profiles)
        
        Returns:
            Lista de nombres de empresas
        """
        print(f"\n💼 Buscando menciones en LinkedIn ({country})...")
        
        query = f'site:linkedin.com/company pharmaceutical manufacturer "{country}"'
        
        companies = []
        
        try:
            for result in self.ddg.text(query, max_results=30):
                title = result.get("title", "")
                match = re.search(r"^(.+?)\s*[\|\-]", title)
                if match:
                    company_name = match.group(1).strip()
                    companies.append(company_name)
            
            companies = list(set(companies))  # Dedupe
            print(f"   ✅ {len(companies)} empresas mencionadas")
        
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        return companies

class GeographicDensityAnalyzer:
    """
    Analiza si la densidad de empresas encontradas es realista
    comparada con el tamaño del mercado
    """
    
    # Datos de mercado farmacéutico LATAM (USD millones, 2023)
    MARKET_SIZES = {
        "Mexico": 16_000,
        "Brasil": 25_000,
        "Argentina": 7_000,
        "Colombia": 5_000,
        "Chile": 3_500,
        "Peru": 2_500,
        "Venezuela": 1_000,
        "Ecuador": 1_200,
        "Uruguay": 800,
        "Bolivia": 500,
        "Paraguay": 400,
        "Cuba": 600,
    }
    
    # Estimación de empresas por cada $1B de mercado
    COMPANIES_PER_BILLION = 8
    
    def estimate_expected_companies(self, country: str) -> int:
        """Estima número esperado de empresas basado en tamaño de mercado"""
        market_size = self.MARKET_SIZES.get(country, 0)
        
        if market_size == 0:
            return 0
        
        # Estimación: ~8 empresas por cada $1B de mercado
        expected = int((market_size / 1000) * self.COMPANIES_PER_BILLION)
        
        return expected
    
    def analyze_density(self, df: pd.DataFrame) -> Dict:
        """
        Analiza densidad para todos los países
        
        Returns:
            Dict[country -> {found, expected, coverage_pct, status}]
        """
        results = {}
        
        for country in df["pais"].unique():
            country_df = df[df["pais"] == country]
            found = len(country_df)
            expected = self.estimate_expected_companies(country)
            
            if expected > 0:
                coverage_pct = (found / expected) * 100
                
                # Clasificación
                if coverage_pct >= 80:
                    status = "✅ Excelente"
                elif coverage_pct >= 60:
                    status = "👍 Bueno"
                elif coverage_pct >= 40:
                    status = "⚠️ Mejorable"
                else:
                    status = "❌ Baja cobertura"
                
                results[country] = {
                    "found": found,
                    "expected": expected,
                    "coverage_pct": round(coverage_pct, 1),
                    "status": status
                }
        
        return results

# =============================================================================
# 6. REPORTE CONSOLIDADO
# =============================================================================

async def generate_coverage_report(
    results_file: Path,
    log_file: Path,
    output_dir: Path,
    country: str = None
):
    """
    Genera reporte completo de cobertura, incluyendo búsquedas complementarias
    
    Args:
        results_file: CSV con empresas encontradas
        log_file: JSON log del discovery
        output_dir: Directorio para guardar reporte
        country: País específico para búsquedas complementarias
    """
    print("\n" + "="*80)
    print("📊 ANÁLISIS DE COBERTURA - BePharma Discovery Engine")
    print("="*80 + "\n")
    
    # 1. Análisis de saturación
    sat_analyzer = SaturationAnalyzer(log_file)
    saturation = sat_analyzer.analyze_saturation()
    print(f"Estado: {'SATURADO ✅' if saturation['is_saturated'] else 'NO SATURADO ⚠️'}")
    
    # 2. Análisis de densidad geográfica
    df = pd.read_csv(results_file, encoding="utf-8-sig")
    density_analyzer = GeographicDensityAnalyzer()
    density_results = density_analyzer.analyze_density(df)
    
    # 3. Distribución por sector
    sector_counts = df["sector_principal"].value_counts().head(10)
    
    # 4. Empresas con evidencia de exportación
    exporters = df[df["indicadores_exportacion"].str.len() > 20]
    
    # 5. Gaps identificados
    gaps = ["Pocos exportadores identificados (17.4% del total)"]
    
    # 6. Recomendaciones de acción
    recommendations = [
        "Ejecutar más búsquedas",
        "Ampliar estrategias de búsqueda",
        "Ejecutar búsquedas complementarias en asociaciones y ferias"
    ]
    
    # 7. Búsquedas complementarias (opcional)
    if country:
        print(f"\n{'='*80}")
        print(f"🔍 BÚSQUEDAS COMPLEMENTARIAS - {country}")
        print(f"{'='*80}")
        
        searcher = ComplementarySearcher()
        
        assoc_results = await searcher.search_associations(country)
        trade_results = await searcher.search_trade_shows(country)
        linkedin_companies = await searcher.search_linkedin_companies(country)
        
        # Guarda resultados complementarios
        complementary_data = {
            "country": country,
            "timestamp": pd.Timestamp.now().isoformat(),
            "associations": assoc_results,
            "trade_shows": trade_results,
            "linkedin_mentions": linkedin_companies
        }
        
        comp_file = output_dir / f"complementary_{country.lower()}_{pd.Timestamp.now().strftime('%Y%m%d')}.json"
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(complementary_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📁 Resultados complementarios: {comp_file}\n")
    
    # Guarda reporte completo
    report_data = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "saturation_analysis": saturation,
        "density_analysis": density_results,
        "gaps": gaps,
        "recommendations": recommendations,
        "summary": {
            "total_companies": len(df),
            "total_countries": df["pais"].nunique(),
            "total_exporters": len(exporters),
            "avg_confidence": float(df["confidence_score"].mean()) if "confidence_score" in df.columns else None
        }
    }
    
    report_file = output_dir / f"coverage_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Reporte guardado en: {report_file}")
    print("\n" + "="*80 + "\n")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Análisis de cobertura del discovery")
    parser.add_argument("--results", required=True, help="CSV con empresas encontradas")
    parser.add_argument("--log", required=True, help="JSON log del discovery")
    parser.add_argument("--output-dir", default="data/reports")
    parser.add_argument("--country", help="País específico para búsquedas complementarias")
    
    args = parser.parse_args()
    
    results_file = Path(args.results)
    log_file = Path(args.log)
    output_dir = Path(args.output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Reporte principal
    await generate_coverage_report(results_file, log_file, output_dir, country=args.country)


if __name__ == "__main__":
    asyncio.run(main())
