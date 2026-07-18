import struct
from pathlib import Path
import numpy as np

# Import du parser LRS2 existant
import sys
sys.path.append(str(Path(__file__).parent))
from lrs2_parser import load_lrs2_from_ttile
from terrain_terr_reader import read_mats_from_terr

# --- CONFIGURATION DU MONDE ---
TERRAIN_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
BLOCK_PIXEL_RES = 128    # Taille d'un bloc en pixels (128x128)
TILE_PIXEL_RES = 512     # Taille d'une tuile en pixels (512x512)
BLOCKS_PER_TILE = TILE_PIXEL_RES // BLOCK_PIXEL_RES  # 4 blocs par tuile

# Nombre de tuiles en largeur sur ta carte (Zimnitrita)
# Utilisé pour convertir les coordonnées (X,Y) en ID unique (ex: 1,22 -> 737)
MAP_TILE_WIDTH = 32

def analyze_targeted_block():
    print("--- Analyseur de Calque Enfusion (Multi-Tuiles & Blocs) ---")

    # 1. Saisie de la tuile (Accepte "1,22" OU "737")
    tile_input = input("1. Entrez l'ID de la tuile OU ses coordonnées X,Y (ex: 737 ou 1,22) : ").strip()

    if "," in tile_input:
        try:
            tx_str, ty_str = tile_input.split(",")
            tile_x = int(tx_str.strip())
            tile_y = int(ty_str.strip())
            tile_id = (tile_y * MAP_TILE_WIDTH) + tile_x
        except ValueError:
            print("❌ Format de coordonnées de tuile incorrect.")
            return
    else:
        try:
            tile_id = int(tile_input)
            # Calcul inverse pour retrouver X et Y à partir de l'ID
            tile_x = tile_id % MAP_TILE_WIDTH
            tile_y = tile_id // MAP_TILE_WIDTH
        except ValueError:
            print("❌ ID de tuile invalide. Entrez un nombre entier.")
            return

    # 2. Saisie des coordonnées du bloc global
    block_input = input("2. Entrez les coordonnées GLOBALES du bloc (ex: 7,89) : ").strip()
    try:
        bx_str, by_str = block_input.split(",")
        block_x = int(bx_str.strip())
        block_y = int(by_str.strip())
    except ValueError:
        print("❌ Format de bloc incorrect. Utilisez le format : X,Y")
        return

    # 3. Calcul de la position LOCALE du bloc à l'intérieur de la tuile (0 à 3)
    local_bx = block_x % BLOCKS_PER_TILE
    local_by = block_y % BLOCKS_PER_TILE

    print(f"\n⚙️ Ciblage en cours...")
    print(f"  ├─ Tuile identifiée  : ID {tile_id} (Coordonnées de la tuile : [{tile_x}, {tile_y}])")
    print(f"  └─ Bloc à extraire   : Local [X:{local_bx}, Y:{local_by}] (Bloc global : [{block_x},{block_y}])")

    # 4. Résolution du fichier de calque (.dds)
    editor_dir = TERRAIN_PATH / ".EditorData"

    # On teste d'abord le format par ID (Terrain_737_layer.dds)
    dds_path = editor_dir / f"Terrain_{tile_id}_layer.dds"

    # Si introuvable, on tente le format par coordonnées (Terrain_1_22_layer.dds)
    if not dds_path.exists():
        dds_path = editor_dir / f"Terrain_{tile_x}_{tile_y}_layer.dds"

    if not dds_path.exists():
        print(f"\n❌ Fichier de calque introuvable dans le dossier .EditorData.")
        print(f"   Vérifié sans succès : 'Terrain_{tile_id}_layer.dds' et 'Terrain_{tile_x}_{tile_y}_layer.dds'")
        return

    print(f"📖 Fichier chargé avec succès : {dds_path.name}")

    # 4b. Lecture du mapping LOCAL des matériaux depuis .ttile (LRS2)
    ttile_path = TERRAIN_PATH / ".Data" / f"Terrain_{tile_id}.ttile"
    if not ttile_path.exists():
        ttile_path = TERRAIN_PATH / ".Data" / f"Terrain_{tile_x}_{tile_y}.ttile"

    if not ttile_path.exists():
        print(f"\n❌ Fichier .ttile introuvable pour lire le mapping des matériaux.")
        return

    # Charger la liste globale des matériaux
    terr_path = TERRAIN_PATH / "Terrain.terr"
    if not terr_path.exists():
        print(f"\n❌ Fichier Terrain.terr introuvable.")
        return

    # Lire mapping global
    global_mats = read_mats_from_terr(terr_path)
    global_names = [m["name"] for m in global_mats]

    # Lire LRS2 pour obtenir le mapping LOCAL de cette tuile
    lrs2_data = load_lrs2_from_ttile(ttile_path)

    # Créer le mapping dynamique pour cette tuile
    # Le bloc ciblé nous donnera ses mat_ids
    block_key = (local_bx, local_by)
    if block_key not in lrs2_data:
        print(f"\n⚠️ Aucune palette de matériaux trouvée pour ce bloc dans le LRS2.")
        print(f"   Le bloc est probablement vide (100% texture de base).")
        # Fallback : utiliser les 7 premiers matériaux
        block_mat_ids = list(range(7))
    else:
        block_mat_ids = lrs2_data[block_key]

    # Construire le mapping local
    TEXTURES_MAPPING = {}
    for idx, mat_id in enumerate(block_mat_ids[:7]):  # Max 7 textures (L0-L6)
        if mat_id < len(global_names):
            mat_name = global_names[mat_id]
            label = f"(Base L0)" if idx == 0 else f"(L{idx})"
            TEXTURES_MAPPING[idx] = f"{mat_name} {label}"
        else:
            TEXTURES_MAPPING[idx] = f"Mat_ID_{mat_id} (L{idx})"

    print(f"📋 Mapping local du bloc :")
    for idx, name in TEXTURES_MAPPING.items():
        if idx < len(block_mat_ids):
            print(f"   L{idx} → {name}")

    # 5. Lecture des données binaires du DDS (FORMAT R32_UINT)
    data = dds_path.read_bytes()
    width = struct.unpack_from('<I', data, 16)[0]
    height = struct.unpack_from('<I', data, 12)[0]

    # Isolation des pixels (Header DDS Enfusion = 148 octets)
    pixel_data = data[148 : 148 + width * height * 4]

    # Lire en uint32 (R32_UINT = 1 canal de 32 bits, pas RGBA)
    img = np.frombuffer(pixel_data, dtype=np.uint32).reshape((height, width))

    # Découpe (Slicing) du sous-bloc de 128x128 pixels
    r_start, r_end = local_by * BLOCK_PIXEL_RES, (local_by * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
    c_start, c_end = local_bx * BLOCK_PIXEL_RES, (local_bx * BLOCK_PIXEL_RES) + BLOCK_PIXEL_RES
    block_pixels = img[r_start:r_end, c_start:c_end]

    # 6. Extraction binaire des poids (Bit-packing 5 bits par canal)
    print(f"\n===============================================================================")
    print(f" ANALYSE DES TEXTURES : TUILE {tile_id} [{tile_x},{tile_y}] ➔ BLOC GLOBAL [{block_x},{block_y}]")
    print(f"===============================================================================\n")

    weights = {}
    # Extraction des poids selon le schéma Enfusion (bits 0-4, 5-9, 10-14, etc.)
    weights[1] = (block_pixels >>  0) & 0x1F  # w1 : bits 0-4
    weights[2] = (block_pixels >>  5) & 0x1F  # w2 : bits 5-9
    weights[3] = (block_pixels >> 10) & 0x1F  # w3 : bits 10-14
    weights[4] = (block_pixels >> 15) & 0x1F  # w4 : bits 15-19
    weights[5] = (block_pixels >> 20) & 0x1F  # w5 : bits 20-24
    weights[6] = (block_pixels >> 25) & 0x1F  # w6 : bits 25-29

    # Calcul de la couche de base automatique L0 par soustraction (Max = 31)
    total_autres = np.zeros((BLOCK_PIXEL_RES, BLOCK_PIXEL_RES), dtype=np.float32)
    for k in [1, 2, 3, 4, 5, 6]:
        total_autres += weights[k]

    weights[0] = np.clip(31.0 - total_autres, 0, 31)

    # 7. Affichage des résultats
    print("Texture détectée | Poids Moyen (0-31) | Taux de présence moyen")
    print("-" * 75)

    for i in range(7):  # Afficher L0 à L6
        w_data = weights[i]
        mean_weight = w_data.mean()
        pct = (mean_weight / 31.0) * 100
        bar = "█" * int(pct / 2)
        name = TEXTURES_MAPPING.get(i, f"Canal_L{i}")
        print(f" ├─ {name:<30} : Moyenne: {mean_weight:>4.1f}/31 ... Taux: {pct:>5.1f}%  {bar}")

    print("===============================================================================")

if __name__ == "__main__":
    analyze_targeted_block()
