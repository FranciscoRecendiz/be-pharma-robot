"""
Setup automático de estructura de proyecto para análisis de datos farmacéuticos
"""

import os

PROJECT_STRUCTURE = [
    "data/raw",
    "data/processed",
    "data/interim",
    "data/external",
    "notebooks",
    "src",
    "src/utils",
    "tests",
    "docs",
    "models",
    "reports"
]

FILES_TO_CREATE = [
    "src/__init__.py",
    "src/utils/__init__.py",
    "README.md",
    ".gitignore",
    "requirements.txt"
]

def create_structure():
    print("📂 Creando estructura del proyecto...\n")

    for folder in PROJECT_STRUCTURE:
        os.makedirs(folder, exist_ok=True)
        print(f"✅ Carpeta creada: {folder}")

    for file in FILES_TO_CREATE:
        if not os.path.exists(file):
            with open(file, "w", encoding="utf-8") as f:
                pass
        print(f"📝 Archivo asegurado: {file}")

    print("\n🎯 Setup completado. Ya puedes mover tus scripts dentro del folder src/")

if __name__ == "__main__":
    create_structure()
