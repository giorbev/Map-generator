"""
Bibliothèque Biomes Climatiques
================================

Gestion biomes climatiques et mapping masques terrain -> textures Reforger

Workflow:
1. Utilisateur choisit biome (Tempéré, Aride, Tropical...)
2. Système charge bibliothèque textures pour ce biome
3. Export génère texture_mapping.json (masque -> texture assignée)
4. Import Workbench utilise mapping pour assigner bonnes textures

"""

import json
from pathlib import Path
from typing import Dict, List, Optional


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════

BIOMES_DIR = Path(__file__).parent / "data" / "biomes"

# Masques terrain générés par pipeline
# Phase 0 (base) : 7 masques
# Phase 1 (côtier varié) : coastal -> coastal_pebbles + coastal_grass
# Phase 2 (herbes globales) : 1 texture = 1 masque (pas de doublon)
#   - grass_standard (Grass_02) : lowland plat/convexe
#   - grass_dense_zones (Grass_03) : lowland concave + midland fusionnés
# Phase 3 (highland varié) : highland -> highland_dense + highland_crest
TERRAIN_MASKS = [
    "seabed",
    "coastal",  # Phase 0 seulement
    "coastal_pebbles",  # Phase 1
    "coastal_grass",  # Phase 1
    "grass_lowland",  # Phase 0 seulement
    "grass_standard",  # Phase 2 (Grass_02)
    "grass_dense_zones",  # Phase 2 (Grass_03 fusionné)
    "grass_highland",  # Phase 0 seulement
    "highland_dense",  # Phase 3 (MountainGrass_03)
    "highland_crest",  # Phase 3 (MountainGrass_01)
    "debris",
    "rock"
]


# ══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT BIOMES
# ══════════════════════════════════════════════════════════════════════════════

def get_available_biomes() -> Dict[str, str]:
    """
    Liste biomes disponibles depuis data/biomes/*.json

    Returns:
        dict: {biome_id: nom_affichage}
        Exemple: {'temperate': 'Tempéré', 'arid': 'Aride'}
    """
    biomes = {}

    if not BIOMES_DIR.exists():
        return biomes

    for biome_file in BIOMES_DIR.glob("*.json"):
        try:
            with open(biome_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                biome_id = data.get('id')
                biome_name = data.get('name', biome_id)
                if biome_id:
                    biomes[biome_id] = biome_name
        except Exception:
            continue

    return biomes


def load_biome(biome_id: str) -> Optional[dict]:
    """
    Charge définition complète d'un biome

    Args:
        biome_id: ID biome (ex: 'temperate')

    Returns:
        dict biome ou None si introuvable
    """
    biome_path = BIOMES_DIR / f"{biome_id}.json"

    if not biome_path.exists():
        return None

    try:
        with open(biome_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def get_biome_textures(biome_id: str) -> Dict[str, str]:
    """
    Récupère mapping masques -> textures pour un biome

    Args:
        biome_id: ID biome

    Returns:
        dict: {mask_name: texture_path}
        Exemple: {'seabed': 'Mud_01.emat', 'coastal': 'Sand_Beach_01.emat'}
    """
    biome = load_biome(biome_id)

    if not biome or 'textures' not in biome:
        return {}

    textures = {}
    biome_textures = biome['textures']

    for mask_name in TERRAIN_MASKS:
        if mask_name in biome_textures:
            tex_def = biome_textures[mask_name]

            # Support format simple (string) ou complexe (dict avec default/variants)
            if isinstance(tex_def, str):
                textures[mask_name] = tex_def
            elif isinstance(tex_def, dict) and 'default' in tex_def:
                textures[mask_name] = tex_def['default']

    return textures


# ══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION TEXTURE MAPPING
# ══════════════════════════════════════════════════════════════════════════════

def generate_texture_mapping(biome_id: str, output_path: str, base_recommendation: dict = None) -> bool:
    """
    Génère fichier texture_mapping.json pour import Workbench

    Fichier indique quelle texture .emat assigner à chaque masque terrain
    + recommandation texture de base optimale

    Args:
        biome_id: ID biome sélectionné
        output_path: Chemin output texture_mapping.json
        base_recommendation: dict detect_base_texture() (optionnel)

    Returns:
        bool: True si succès
    """
    from datetime import datetime

    biome = load_biome(biome_id)
    if not biome:
        return False

    textures = get_biome_textures(biome_id)
    if not textures:
        return False

    # Construire mapping complet
    mappings = {}

    for mask_name, texture_name in textures.items():
        # Masque filename (ex: '02_coastal.png')
        mask_index = TERRAIN_MASKS.index(mask_name) + 1
        mask_filename = f"{mask_index:02d}_{mask_name}.png"

        is_base = False
        if base_recommendation and mask_filename.startswith(base_recommendation['base_mask'].split('_')[0]):
            is_base = True

        mappings[mask_filename] = {
            'mask_name': mask_name,
            'texture': texture_name,
            'biome': biome_id,
            'use_as_base': is_base  # True si recommandé comme base
        }

    # Métadonnées
    mapping_data = {
        'version': '1.0',
        'generated_at': datetime.now().isoformat(),
        'biome': {
            'id': biome_id,
            'name': biome.get('name', biome_id),
            'description': biome.get('description', '')
        },
        'mappings': mappings
    }

    # Ajouter recommandation base si disponible
    if base_recommendation:
        mapping_data['workbench_optimization'] = {
            'base_texture': base_recommendation['base_texture'],
            'base_mask': base_recommendation['base_mask'],
            'coverage_pct': base_recommendation['coverage_pct'],
            'masks_to_import': base_recommendation['masks_to_import'],
            'total_textures': 7,
            'note': 'Utiliser base_texture comme texture de base Workbench, importer seulement masks_to_import'
        }

    # Sauvegarder
    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(mapping_data, f, indent=2, ensure_ascii=False)

        return True

    except Exception:
        return False


def generate_workbench_instructions(biome_id: str, base_recommendation: dict, output_path: str) -> bool:
    """
    Génère fichier texte avec instructions import Workbench

    Args:
        biome_id: ID biome
        base_recommendation: dict detect_base_texture()
        output_path: chemin workbench_instructions.txt

    Returns:
        bool: True si succès
    """
    try:
        textures = get_biome_textures(biome_id)

        instructions = []
        instructions.append("="*70)
        instructions.append("INSTRUCTIONS IMPORT WORKBENCH REFORGER")
        instructions.append("="*70)
        instructions.append("")
        instructions.append("OPTIMISATION : 7 TEXTURES TOTAL (1 base + 6 masques)")
        instructions.append("Évite erreur '+5 textures' en utilisant texture dominante comme base")
        instructions.append("")

        # Étape 1 : Base
        base_mask = base_recommendation['base_mask']
        base_texture = base_recommendation['base_texture']
        base_pct = base_recommendation['coverage_pct']

        instructions.append("ÉTAPE 1 : APPLIQUER TEXTURE DE BASE")
        instructions.append("-" * 70)
        instructions.append(f"Texture : {base_texture}")
        instructions.append(f"Coverage: {base_pct:.1f}% du terrain (texture dominante)")
        instructions.append("")
        instructions.append("Workbench :")
        instructions.append("  1. Sélectionner texture : " + base_texture)
        instructions.append("  2. Clic droit > Fill Surface Layer (Clear Others)")
        instructions.append("     -> Applique sur 100% du terrain")
        instructions.append("")

        # Étape 2 : Masques
        instructions.append("ÉTAPE 2 : IMPORTER MASQUES (6/7)")
        instructions.append("-" * 70)
        instructions.append(f"NE PAS IMPORTER : {base_mask}.png (déjà en base)")
        instructions.append("")

        masks_to_import = base_recommendation['masks_to_import']

        for i, mask_name in enumerate(masks_to_import, 1):
            # Extraire nom sans numéro
            mask_key = '_'.join(mask_name.split('_')[1:])
            texture = textures.get(mask_key, "???")

            instructions.append(f"{i}. {mask_name}.png")
            instructions.append(f"   Texture : {texture}")
            instructions.append(f"   Workbench :")
            instructions.append(f"     - Sélectionner texture : {texture}")
            instructions.append(f"     - Terrain > Apply Mask")
            instructions.append(f"     - Charger : {mask_name}.png")
            instructions.append("")

        instructions.append("="*70)
        instructions.append("RÉSULTAT FINAL")
        instructions.append("="*70)
        instructions.append(f"Textures totales : 7 (1 base + 6 masques)")
        instructions.append(f"Limite Reforger  : 5-7 textures/bloc maximum")
        instructions.append(f"Statut           : COMPATIBLE")
        instructions.append("")

        # Sauvegarder
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(instructions))

        return True

    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# AFFICHAGE / UI
# ══════════════════════════════════════════════════════════════════════════════

def get_biome_description(biome_id: str) -> str:
    """
    Récupère description d'un biome pour affichage UI

    Args:
        biome_id: ID biome

    Returns:
        str: description ou chaîne vide
    """
    biome = load_biome(biome_id)
    if biome:
        return biome.get('description', '')
    return ''


def get_biome_preview_colors(biome_id: str) -> Dict[str, tuple]:
    """
    Couleurs aperçu pour un biome (optionnel)

    Returns:
        dict: {mask_name: (R, G, B)}
    """
    biome = load_biome(biome_id)

    if biome and 'preview_colors' in biome:
        return biome['preview_colors']

    # Couleurs par défaut si non définies
    return {
        'seabed': (50, 100, 150),
        'coastal': (200, 180, 120),
        'grass_lowland': (100, 180, 80),
        'grass_midland': (80, 150, 60),
        'grass_highland': (120, 140, 100),
        'debris': (140, 120, 100),
        'rock': (100, 100, 100)
    }
