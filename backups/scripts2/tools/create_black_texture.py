"""
Créer une texture noire 1024x1024 pour default.emat
"""

import sys
import io
from PIL import Image
from pathlib import Path

# Force UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Créer image noire 1024x1024
black_texture = Image.new('RGB', (1024, 1024), (0, 0, 0))

# Sauvegarder dans Vanilla/textures
output_path = Path("data/Textures_ArmaReforger/Vanilla/textures/default_black_BCR.jpg")
output_path.parent.mkdir(parents=True, exist_ok=True)

black_texture.save(output_path, quality=95)

print(f"✓ Texture noire créée : {output_path}")
print(f"  Taille : 1024×1024 px")
print(f"  Couleur : RGB(0, 0, 0)")
