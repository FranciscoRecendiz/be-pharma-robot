import os
import pandas as pd
import re
from pathlib import Path
from unidecode import unidecode # Importamos unidecode

# Selecciona el archivo que generó el parser
input_csv = Path("data/staging/pharma_cleaned.csv")

if not input_csv.exists():
    raise FileNotFoundError(f"❌ No se encontró el archivo: {input_csv}")

print(f"Cargando {input_csv}...")
df = pd.read_csv(input_csv)

# Crear carpeta raíz para CRM
root = Path("CRM_EMPRESAS")
root.mkdir(exist_ok=True)

def limpiar_nombre(nombre):
    """
    Limpia y normaliza un nombre para usarlo 
    como un nombre de carpeta seguro.
    """
    nombre = str(nombre)
    
    # 1. Normalizar acentos (ej. "Aché" -> "Ache")
    nombre = unidecode(nombre)
    
    # 2. Convertir a minúsculas
    nombre = nombre.lower()
    
    # 3. Remover URLs
    nombre = re.sub(r'https?://\S+|www\.\S+', '', nombre)
    
    # 4. Quitar caracteres no-alfanuméricos (dejar letras, números, espacios, guiones)
    # \w incluye letras, números y guion bajo
    nombre = re.sub(r'[^\w\s\-]', '', nombre)
    
    # 5. Reemplazar espacios y guiones repetidos por un solo guion bajo
    nombre = re.sub(r'[\s\-]+', '_', nombre)
    
    # 6. Quitar guiones bajos al inicio o final
    # 7. Limitar longitud
    return nombre.strip("_")[:60]

print("Procesando empresas y creando carpetas...")
empresas_procesadas = 0

# Iteramos sobre los nombres únicos de empresas (sin NaNs)
for empresa in df["empresa"].dropna().unique():
    
    folder_name = limpiar_nombre(empresa)
    
    # 3. Omitir si el nombre resultante está vacío
    if not folder_name:
        print(f"  -> Omitiendo empresa con nombre inválido: '{empresa}'")
        continue

    folder_path = root / folder_name
    folder_path.mkdir(exist_ok=True)
    
    # --- ¡LA PARTE NUEVA Y MÁS ÚTIL! ---
    # 1. Filtrar el dataframe original por la empresa actual
    contactos_df = df[df["empresa"] == empresa]
    
    # 2. Definir la ruta de guardado
    # Usamos f"{folder_name}_contactos.csv" para claridad
    save_file = folder_path / f"contactos_{folder_name}.csv"
    
    # 3. Guardar el CSV filtrado dentro de su carpeta
    contactos_df.to_csv(save_file, index=False)
    
    empresas_procesadas += 1

print(f"\n✅ ¡Proceso completado!")
print(f"  -> Se crearon y llenaron {empresas_procesadas} carpetas en: {root.resolve()}")