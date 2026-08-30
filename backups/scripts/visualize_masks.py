"""
visualize_masks.py — Visualisation superposée masks Zone A (WB) + Zone B (pipeline)
Sortie : image 4096×4096 PNG, 1 pixel = 1 bloc terrain (128×128 blocs total)

Usage:
    python visualize_masks.py

Config à adapter en haut du script.
"""

from pathlib import Path
from PIL import Image
import numpy as np
import json

# ─── CONFIG ────────────────────────────────────────────────────────────────────

# Dossier masks Zone B (pipeline, 4096×4096, nom = texture ex: seabed.png)
ZONE_B_DIR = Path(r"H:\logiciel perso\Map generator\exports_mask\latest")

# Dossier masks Zone A (WB export, 8000×8000)
ZONE_A_DIR = Path(r"H:\logiciel perso\Map generator\data\masks_zone_a")

# Masque exclusion Zone B (blanc = Zone B, noir = Zone A)
EXCLUSION_MASK = Path(r"H:\logiciel perso\Map generator\data\masque_exclusion_clean.png")

# project_mask_config.json (ordre priorité + texture par mask)
MASK_CONFIG = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\project_mask_config.json")

# surfaces.json (mat_id par texture)
SURFACES = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\surfaces.json")

# Seuil d'activation d'un mask sur un bloc (0-255, moyenne pixels du bloc)
THRESHOLD = 30

# Résolution sortie
OUT_SIZE = 4096   # 4096×4096 px
GRID = 128        # 128×128 blocs
PIX_PER_BLOC = OUT_SIZE // GRID  # 32 px par bloc

# ─── COULEURS PAR TEXTURE ──────────────────────────────────────────────────────

COLORS = {
    "SeaBed_01":                 (30,  100, 200),   # bleu foncé
    "Pebbles_02":                (180, 160, 120),   # beige côtier
    "Rock_01":                   (120, 100,  80),   # gris-brun
    "zi_MountainGrass_04":       (160, 140, 100),   # landes rocheuses
    "Dirt_03":                   (200, 120,  60),   # flow orange
    "Dirt_02":                   (170,  90,  40),   # deposit brun
    "MountainGrass_01":          (180, 210, 130),   # alpages vert clair
    "MountainGrass_03":          (140, 180, 100),   # landes plateau
    "Heather_01":                (160,  80, 160),   # maquis violet
    "ForestConiferous_01_Base":  ( 20,  80,  40),   # forêt conifères vert foncé
    "ForestDeciduous_01_Base":   ( 60, 140,  60),   # forêt feuillue vert moyen
    "Grass_02":                  (100, 200, 100),   # prairie humide
    "Grass_01_aut":              (200, 220, 100),   # prairie sèche
    "Grass_03":                  ( 80, 160,  80),   # défaut Zone B
    # Zone A extras (WB)
    "Dirt_01":                   (190, 140,  80),   # chemins dirt
    "Asphalt_01":                ( 80,  80,  80),   # routes
    "Concrete_01":               (140, 140, 140),   # béton
    "Concrete_02":               (160, 160, 160),
    "ForestDeciduous_02":        ( 40, 120,  50),
    "ForestConiferous_02":       ( 20,  60,  30),
    "Grass_01":                  (150, 210, 100),
    "Grass_02":                  (100, 200, 100),
    "Grass_03_coastal":          ( 60, 160, 120),
    "Rock_02":                   (100,  80,  60),
    "Pebbles_01":                (200, 180, 130),
    "MountainGrass_02":          (160, 200, 120),
    "Crop_Field_01":             (230, 200,  80),
    "Crop_Field_02":             (220, 190,  70),
    "ZI_Crop_Field_01":          (210, 180,  60),
    "ZI_Crop_Field_02":          (200, 170,  50),
    "ZI_Crop_Field_03":          (190, 160,  40),
    "ZI_Crop_Field_04":          (180, 150,  30),
    "ZI_Crop_Field_Cut_01":      (220, 200, 100),
    "ZI_Crop_Field_Cut_02":      (210, 190,  90),
    "BeachGrass_01":             (180, 210, 140),
    "Debris_Rock_01":            (110,  90,  70),
    "Cobblestone_01_Wave":       (130, 110,  90),
    "ForestPine_01_Base":        ( 30,  70,  40),
    "ForestClearing_Coniferous_01": (50, 100, 60),
    "ForestClearing_Deciduous_01":  (70, 130, 70),
    "ForestDeciduous_01_Base":   ( 60, 140,  60),
    "SulfurStream_01_bed":       (220, 200,  50),
    "Grass_03_default":          (120, 180,  90),   # GrassDef
    "DEFAULT":                   ( 50,  50,  50),   # non identifié
}


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def load_mask_gray(path: Path, target_size: int) -> np.ndarray:
    """Charge un mask, le convertit en niveaux de gris et le resize."""
    img = Image.open(path).convert("L")
    if img.size != (target_size, target_size):
        img = img.resize((target_size, target_size), Image.LANCZOS)
    return np.array(img, dtype=np.float32)


def bloc_mean(mask_arr: np.ndarray, bx: int, by: int) -> float:
    """Valeur moyenne du mask sur le bloc (bx, by) en coords 4096px."""
    # by=0 = bas de la map en Reforger → haut de l'image PNG (convention WB)
    # On flip Y pour que by=0 soit en bas
    by_img = (GRID - 1 - by)
    y0 = by_img * PIX_PER_BLOC
    x0 = bx * PIX_PER_BLOC
    region = mask_arr[y0:y0+PIX_PER_BLOC, x0:x0+PIX_PER_BLOC]
    return float(region.mean()) if region.size > 0 else 0.0


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("Chargement config...")
    with open(MASK_CONFIG) as f:
        cfg = json.load(f)
    with open(SURFACES) as f:
        surf = json.load(f)

    # Ordre de priorité Zone B depuis mask_config (ordre dict = ordre insertion)
    zone_b_order = list(cfg["mask_config"].items())  # [(mask_name, texture_name), ...]
    default_tex = cfg.get("default_mat", "Grass_03")

    print("Chargement masque exclusion...")
    excl = load_mask_gray(EXCLUSION_MASK, OUT_SIZE)
    # excl > 128 → Zone B

    print("Chargement masks Zone B...")
    zone_b_masks = {}
    for mask_name, tex_name in zone_b_order:
        # Chercher le fichier dans ZONE_B_DIR
        # Nom attendu : mask_seabed.png ou seabed.png ou SeaBed_01.png etc.
        candidates = [
            ZONE_B_DIR / f"{mask_name}.png",
            ZONE_B_DIR / f"{tex_name}.png",
            ZONE_B_DIR / f"{tex_name.lower()}.png",
        ]
        found = None
        for c in candidates:
            if c.exists():
                found = c
                break
        if found:
            zone_b_masks[mask_name] = (tex_name, load_mask_gray(found, OUT_SIZE))
            print(f"  ✓ {mask_name} → {tex_name} ({found.name})")
        else:
            print(f"  ✗ {mask_name} → {tex_name} (ABSENT)")

    print("Chargement masks Zone A (WB)...")
    zone_a_masks = []  # [(tex_name, arr), ...] dans l'ordre de priorité
    # Mapping noms fichiers WB → texture
    # On scanne le dossier et essaie de matcher avec les noms du surfaces.json
    surf_by_name = {v: k for k, v in surf["materials"].items()}  # id→name inversé
    if ZONE_A_DIR.exists():
        for f in sorted(ZONE_A_DIR.glob("*.png")):
            stem = f.stem.lower().replace("-", "_").replace(" ", "_")
            # Chercher la texture correspondante
            tex_match = None
            for tex_name in surf["materials"]:
                if tex_name.lower().replace("_", "") in stem.replace("_", ""):
                    tex_match = tex_name
                    break
                if stem in tex_name.lower():
                    tex_match = tex_name
                    break
            if tex_match is None:
                # Essai direct : dirt01 → Dirt_01
                tex_match = f.stem  # garder tel quel si pas de match
            arr = load_mask_gray(f, OUT_SIZE)
            zone_a_masks.append((tex_match, arr))
            print(f"  ✓ {f.name} → {tex_match}")
    else:
        print(f"  ZONE_A_DIR absent: {ZONE_A_DIR}")

    # Créer image de sortie RGB
    out = np.zeros((OUT_SIZE, OUT_SIZE, 3), dtype=np.uint8)
    # Fond = défaut
    def_color = COLORS.get(default_tex, COLORS["DEFAULT"])
    out[:, :] = def_color

    print("Génération image 4096×4096...")
    progress_step = GRID * GRID // 10

    for by in range(GRID):
        for bx in range(GRID):
            bloc_idx = by * GRID + bx

            # Zone A ou B ?
            excl_val = bloc_mean(excl, bx, by)
            is_zone_b = excl_val > 128

            # Couleur selon zone
            if is_zone_b:
                # Appliquer masks Zone B dans l'ordre de priorité
                tex = default_tex
                for mask_name, (tex_name, arr) in zone_b_masks.items():
                    if bloc_mean(arr, bx, by) >= THRESHOLD:
                        tex = tex_name
                        break
            else:
                # Appliquer masks Zone A dans l'ordre
                tex = default_tex
                for tex_name, arr in zone_a_masks:
                    if bloc_mean(arr, bx, by) >= THRESHOLD:
                        tex = tex_name
                        break

            color = COLORS.get(tex, COLORS["DEFAULT"])

            # Remplir le bloc dans l'image de sortie
            by_img = (GRID - 1 - by)
            y0 = by_img * PIX_PER_BLOC
            x0 = bx * PIX_PER_BLOC
            out[y0:y0+PIX_PER_BLOC, x0:x0+PIX_PER_BLOC] = color

        if by % 10 == 0:
            print(f"  {by}/{GRID} lignes...")

    # Ajouter grille tuiles (blanc, tous les 4 blocs = 128 px)
    TILE_PX = PIX_PER_BLOC * 4  # 128 px = 1 tuile
    for i in range(0, OUT_SIZE, TILE_PX):
        out[i, :] = (255, 255, 255)
        out[:, i] = (255, 255, 255)

    # Légende en bas (40 px de hauteur)
    # (simplifiée — liste des textures présentes)

    print("Sauvegarde...")
    img = Image.fromarray(out, "RGB")
    out_path = Path(r"H:\logiciel perso\Map generator\data\visualize_masks_output.png")
    img.save(out_path)
    print(f"✓ Sauvegardé : {out_path}")
    print(f"  Taille : {out_path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
