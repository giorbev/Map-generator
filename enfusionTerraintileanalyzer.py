import struct
from pathlib import Path
import numpy as np

# --- CONFIGURATION DU CHEMIN ---
TERRAIN_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
TILE_ID = 737
BX, BY = 2, 2  # Ton bloc d'érosion ciblé [2x2]
BLOCK_PIXEL_RES = 128

# Ton ordre officiel de textures extrait du Terrain Tools / terrain_materials_list.txt
# (Ajuste l'ordre exact si nécessaire selon ton fichier texte !)
TEXTURES_MAPPING = {
    0: "Grass_03 (Base L0)",
    1: "Debris_Rock_01 (L1 / Canal R)",
    2: "Rock_01 (L2)",
    3: "Dirt_03 (L3)",
    4: "zi_MountainGrass_04 (L4)",
    5: "Canal_L5",
    6: "Canal_L6"
}

def analyze_block_weights():
    dds_path = TERRAIN_PATH / ".EditorData" / f"Terrain_{TILE_ID}_layer.dds"
    if not dds_path.exists():
        print(f"❌ Fichier introuvable : {dds_path}")
        return

    # 1. Lecture brute du fichier DDS d'Enfusion
    data = dds_path.read_bytes()
    width = struct.unpack_from('<I', data, 16)[0]
    height = struct.unpack_from('<I', data, 12)[0]

    # Sauter le header de 148 octets pour attraper les pixels (BGRA 32-bits)
    pixel_data = data[148 : 148 + width * height * 4]
    img = np.frombuffer(pixel_data, dtype=np.uint8).reshape((height, width, 4))

    # 2. Slicing et isolation de ton bloc [2x2]
    r_start, r_end = BY * BLOCK_PIXEL_RES, (BY * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
    c_start, c_end = BX * BLOCK_PIXEL_RES, (BX * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
    block_pixels = img[r_start:r_end, c_start:c_end]

    print(f"===============================================================================")
    print(f" ANALYSE BINAIRE DU BLOC LOCAL [{BX}x{BY}] - TUILE {TILE_ID}")
    print(f"===============================================================================\n")

    # 3. Extraction et conversion des canaux 5-bits d'Enfusion
    # On rassemble les octets pour décoder les paquets de bits (poids de 0 à 31)
    # Le canal Rouge (index 2) contient les bits liés à l'érosion

    weights = {}

    # Canal Rouge (R) -> Gère ton érosion Debris_Rock_01 (Plafonné à 15 max)
    weights[1] = block_pixels[:, :, 2] & 0x1F  # Masque des 5 premiers bits

    # Canal Vert (V) -> Souvent lié à Rock_01
    weights[2] = block_pixels[:, :, 1] & 0x1F

    # Canal Bleu (B) -> Lié à Grass_03 ou Dirt
    weights[3] = block_pixels[:, :, 0] & 0x1F

    # Canal Spécifique Poids Fort -> zi_MountainGrass_04
    # Enfusion décale souvent les textures secondaires sur les bits restants
    weights[4] = (block_pixels[:, :, 0] >> 5) | ((block_pixels[:, :, 1] >> 5) << 3)

    # 4. Calcul de la couche de base automatique (L0) par soustraction
    # Total max Enfusion = 31
    total_autres = np.zeros((BLOCK_PIXEL_RES, BLOCK_PIXEL_RES), dtype=np.float32)
    for k in [1, 2, 3, 4]:
        total_autres += weights[k]

    weights[0] = np.clip(31.0 - total_autres, 0, 31)

    # 5. Affichage des résultats
    print("Texture détectée | Poids Moyen (0-31) | Taux de présence moyen")
    print("-" * 75)

    for i in range(5):
        w_data = weights[i]
        mean_weight = w_data.mean()

        # Conversion en pourcentage réel pour l'UI (sur une base de 31)
        pct = (mean_weight / 31.0) * 100

        # Barre visuelle
        bar_size = int(pct / 2)
        bar = "█" * bar_size if bar_size > 0 else ""

        name = TEXTURES_MAPPING.get(i, f"Canal_L{i}")
        print(f" ├─ {name:<30} : Moyenne: {mean_weight:>4.1f}/31 ... Taux: {pct:>5.1f}%  {bar}")

    print("===============================================================================")

if __name__ == "__main__":
    analyze_block_weights()
