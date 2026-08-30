"""Vérifier la supertexture de la tuile 1015"""

from pathlib import Path
import numpy as np

supertex = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData\Terrain_1015_supertexture.dds')

if not supertex.exists():
    print("Supertexture introuvable")
    exit(1)

# Lire supertexture (BGRA8 512x512, header 148 bytes)
with open(supertex, 'rb') as f:
    f.seek(148)
    data = f.read()

# Decoder
img = np.frombuffer(data, dtype=np.uint8).reshape(512, 512, 4)

# Extraire RGB
rgb = img[:, :, :3]

print('='*80)
print('SUPERTEXTURE TUILE 1015')
print('='*80)
print()
print(f'Dimensions: {rgb.shape}')
print(f'Min RGB: {rgb.min()}')
print(f'Max RGB: {rgb.max()}')
print(f'Moyenne RGB: {rgb.mean():.1f}')
print()

# Compter pixels noirs (RGB < 10)
black_pixels = np.sum(np.all(rgb < 10, axis=2))
total_pixels = 512 * 512
black_percent = (black_pixels / total_pixels) * 100

print(f'Pixels noirs (RGB<10): {black_pixels:,} / {total_pixels:,} ({black_percent:.1f}%)')
print()

if black_percent > 90:
    print('⚠️ TUILE QUASI-NOIRE (>90% noir)')
elif black_percent > 50:
    print('⚠️ TUILE MAJORITAIREMENT NOIRE (>50% noir)')
else:
    print('✅ Tuile normale (pas majoritairement noire)')
