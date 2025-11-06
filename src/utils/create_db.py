import sqlite3
from pathlib import Path

# Define la ruta de la base de datos
DB_PATH = Path(__file__).parent.parent.parent / "data" / "processed" / "prospects.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True) # Crea las carpetas data/processed

def create_database():
    try:
        print(f"Creando base de datos en: {DB_PATH.resolve()}")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # SQL para crear tu tabla de prospectos
        # Ajustamos los campos a lo que nuestra IA "gratis" puede encontrar
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS prospectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            nombre_empresa TEXT NOT NULL,
            sitio_web TEXT,
            linkedin_empresa TEXT,
            pais TEXT,
            giro_icp TEXT,
            nombre_contacto TEXT,
            cargo_contacto TEXT,
            linkedin_contacto TEXT, -- El perfil de LinkedIn que encontramos
            fuente TEXT DEFAULT 'agente-v1-groq',
            estado TEXT DEFAULT 'nuevo',
            UNIQUE(nombre_empresa, nombre_contacto) -- Evitar duplicados simples
        );
        """)
        
        conn.commit()
        conn.close()
        print("✅ Base de datos y tabla 'prospectos' creadas con éxito.")

    except Exception as e:
        print(f"❌ Error creando la base de datos: {e}")

if __name__ == "__main__":
    create_database()