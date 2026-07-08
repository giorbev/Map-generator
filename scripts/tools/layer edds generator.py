from pathlib import Path
import struct, numpy as np

# === À ADAPTER ===
EDITOR_DIR = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData")

# DEBUG
print(f"Chemin: {EDITOR_DIR}")
print(f"Existe: {EDITOR_DIR.exists()}")
if EDITOR_DIR.exists():
    all_files = list(EDITOR_DIR.iterdir())
    print(f"Nb fichiers dans le dossier: {len(all_files)}")
    print(f"5 premiers: {[f.name for f in all_files[:5]]}")
    layers = list(EDITOR_DIR.glob("Terrain_*_layer.dds"))
    print(f"layer.dds trouvés: {len(layers)}")
    if layers:
        print(f"exemple: {layers[0].name}")
else:
    print("DOSSIER INTROUVABLE — vérifier le chemin")

input("Appuie sur Entrée pour continuer ou Ctrl+C pour arrêter...")

TILES_MANQUANTS = [
    20, 21, 53, 84, 85, 114, 115, 116, 117,
    146, 147, 148, 149, 150, 178, 181, 182, 1022, 1023
]

TEMPLATE = next(EDITOR_DIR.glob("Terrain_*_layer.dds"))
ref_hdr = open(TEMPLATE, "rb").read()[:148]
print(f"\nTemplate utilisé: {TEMPLATE.name}")

for tid in TILES_MANQUANTS:
    out = EDITOR_DIR / f"Terrain_{tid}_layer.dds"
    if out.exists():
        print(f"EXISTE DÉJÀ: {out.name} — ignoré")
        continue

    data = bytearray(ref_hdr)
    m0 = np.zeros((512, 512), dtype=np.uint32)
    data += m0.tobytes()
    data += np.ascontiguousarray(m0[::2, ::2]).tobytes()
    for lvl in range(2, 10):
        s = max(1, 512 >> lvl)
        data += bytes(s * s * 4)

    open(out, "wb").write(data)
    print(f"OK: Terrain_{tid}_layer.dds ({len(data)} octets)")

print("\nTerminé.")
input("Appuie sur Entrée pour fermer...")
