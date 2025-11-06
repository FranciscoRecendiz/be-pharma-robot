import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain_core.prompts import ChatPromptTemplate

# --- 1. DEFINIR HERRAMIENTAS "SIN COSTO" ---

# Herramienta 1: Búsqueda en DuckDuckGo
search_tool = DuckDuckGoSearchRun(max_results=5)

# Herramienta 2: Scraper web simple
def scrape_website(url: str) -> str:
    """
    Toma una URL y devuelve el texto 'limpio' de la página o un error.
    Úsalo para validar el giro de una empresa o encontrar información de contacto.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Extraer texto de etiquetas comunes
            text = ' '.join(p.get_text() for p in soup.find_all(['p', 'h1', 'h2', 'h3', 'span', 'a']))
            return f"Contenido exitoso (primeros 1500 caracteres): {text[:1500]}"
        else:
            return f"Error: El sitio web devolvió el código de estado {response.status_code}"
    except Exception as e:
        return f"Error al intentar scrapear la URL {url}: {str(e)}"

# Crear la herramienta LangChain
from langchain.tools import Tool
scrape_tool = Tool(
    name="WebScraper",
    func=scrape_website,
    description="Útil para obtener el contenido de una página web dada una URL. Úsalo para validar el giro de una empresa."
)

tools = [search_tool, scrape_tool]

# --- 2. EL CEREBRO (Groq + Llama 3) ---
try:
    llm = ChatGroq(model="llama3-70b-8192", temperature=0)
    if not os.environ.get("GROQ_API_KEY"):
        raise EnvironmentError("GROQ_API_KEY no encontrada. Por favor, configúrala.")
except Exception as e:
    print(f"Error iniciando LLM de Groq: {e}")
    sys.exit(1)

# --- 3. EL PROMPT (LA MISIÓN) ---
prompt_template = """
Eres un agente de prospección B2B de élite. Hablas español.
Tu misión es encontrar empresas de la industria farmacéutica y contactos clave
(Decision Makers como Directores, Gerentes de Compras, CEOs)
para un evento de negociación B2B.

OBJETIVO ACTUAL:
País: {country}
Giro (ICP): {giro}
Debes encontrar 3 nuevas empresas que cumplan este perfil.

PROCESO DE RAZONAMIENTO:
1.  Usa 'duckduckgo_search' para encontrar listas de empresas del {giro} en {country}.
2.  Para cada empresa, usa 'WebScraper' para visitar su sitio web y validar que 
    realmente pertenece a la industria farmacéutica (ej. buscar palabras clave como 
    'farmacéutica', 'laboratorio', 'medical device', 'biotecnología').
3.  Una vez validada la empresa, usa 'duckduckgo_search' de nuevo para encontrar 
    un 'Decision Maker'. Ejemplo de búsqueda: "Director de Compras 'Nombre Empresa' site:linkedin.com"
4.  Extrae el nombre, cargo y la URL de LinkedIn del contacto.
5.  Formatea la salida como una lista de objetos JSON. Si no encuentras un dato, déjalo como null.

OUTPUT:
Responde SÓLO con una lista de objetos JSON. No añadas texto introductorio.

Ejemplo de salida:
[
  {{
    "nombre_empresa": "FarmaTest S.A.",
    "sitio_web": "farmatest.com.ar",
    "pais": "{country}",
    "giro_icp": "{giro}",
    "nombre_contacto": "Carlos Diaz",
    "cargo_contacto": "Director General",
    "linkedin_contacto": "linkedin.com/in/carlosdiazzz"
  }}
]
"""
prompt = ChatPromptTemplate.from_template(prompt_template)

# --- 4. CREAR Y EJECUTAR EL AGENTE ---
def run_agent(country, giro):
    try:
        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        mission_input = {"country": country, "giro": giro}

        # Formateamos el prompt final con las variables
        final_prompt = prompt_template.format(country=country, giro=giro)

        result = agent_executor.invoke({"input": final_prompt})

        # La salida 'output' del agente DEBE ser el string JSON
        return result['output']
    except Exception as e:
        return f'[{{"error": "Error durante la ejecución del agente: {str(e)}"}}]'

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python run_prospector_agent.py <pais> <giro>")
        sys.exit(1)

    country = sys.argv[1]
    giro = sys.argv[2]

    # print(f"Iniciando agente para: {country} - {giro}")
    results_json_string = run_agent(country, giro)

    # La salida estándar (print) será capturada por n8n
    print(results_json_string)
    