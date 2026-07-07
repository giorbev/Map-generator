"""
Vérificateurs pour le générateur satmap v2.0
"""

from pathlib import Path
from typing import List, Dict, Tuple
import struct
import numpy as np


def generate_empty_layer(output_path: Path, editor_data_dir: Path) -> bool:
    """
    Génère un fichier layer.dds vide (SeaBed uniforme)

    Args:
        output_path: Chemin du fichier layer.dds à créer
        editor_data_dir: Dossier .EditorData pour trouver un template

    Returns:
        True si succès, False sinon
    """
    try:
        # Chercher un template existant pour copier le header
        templates = list(editor_data_dir.glob("Terrain_*_layer.dds"))
        if not templates:
            print(f"    ERREUR: Aucun template layer.dds trouvé dans {editor_data_dir}")
            return False

        # Lire header du template (148 bytes)
        with open(templates[0], "rb") as f:
            ref_hdr = f.read(148)

        # Créer données vides (valeur 0x00000000 = 100% w0 = SeaBed/Grass par défaut)
        data = bytearray(ref_hdr)

        # Mipmap 0 : 512×512
        m0 = np.zeros((512, 512), dtype=np.uint32)
        data += m0.tobytes()

        # Mipmap 1 : 256×256
        data += np.ascontiguousarray(m0[::2, ::2]).tobytes()

        # Mipmaps 2-9
        for lvl in range(2, 10):
            s = max(1, 512 >> lvl)
            data += bytes(s * s * 4)

        # Écrire fichier
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)

        return True

    except Exception as e:
        print(f"    ERREUR génération layer vide: {e}")
        return False


def rebuild_editor_layer(edds_path: Path, output_path: Path) -> bool:
    """
    Reconstruit un layer.dds depuis un fichier .edds runtime

    Args:
        edds_path: Chemin du fichier .edds source
        output_path: Chemin du fichier layer.dds à créer

    Returns:
        True si succès, False sinon
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from edds_decoder import decode_edds_layer
        import numpy as np

        # Décoder l'EDDS
        layer_img = decode_edds_layer(edds_path)
        if layer_img is None:
            print(f"    ERREUR: impossible de décoder {edds_path.name}")
            return False

        # Template header depuis un layer.dds existant
        template = next(output_path.parent.glob("Terrain_*_layer.dds"), None)
        if template is None:
            print(f"    ERREUR: aucun template header trouvé")
            return False

        # Lire header DDS (128 bytes)
        ref_hdr = open(template, "rb").read(128)

        # Écrire DDS avec header + données + mipmaps
        h, w = layer_img.shape
        data = bytearray(ref_hdr)
        data += layer_img.astype(np.uint32).tobytes()
        # Mipmap niveau 1 (256x256)
        data += np.ascontiguousarray(layer_img[::2, ::2]).astype(np.uint32).tobytes()

        open(output_path, "wb").write(data)
        print(f"    OK reconstruit depuis EDDS : {output_path.name}")
        return True

    except Exception as e:
        print(f"    ERREUR reconstruction EDDS: {e}")
        return False


def check_missing_layers(editor_data_dir: Path, data_dir: Path) -> List[int]:
    """
    Vérifie et corrige les fichiers layer.dds manquants

    Args:
        editor_data_dir: Dossier .EditorData
        data_dir: Dossier .Data

    Returns:
        Liste des tile_id traités
    """
    # Trouver tous les .ttile (sauf variantes)
    ttiles = sorted(data_dir.glob("Terrain_*.ttile"))
    ttiles = [f for f in ttiles if not any(x in f.name for x in ["_layer", "_normal", "_supertexture"])]

    missing, rebuilt, generated = [], [], []

    for ttile in ttiles:
        # Extraire numéro de tuile
        try:
            tid = int(ttile.stem.split("_")[1])
        except (IndexError, ValueError):
            continue

        layer_dds = editor_data_dir / f"Terrain_{tid}_layer.dds"

        if layer_dds.exists():
            continue

        # Layer manquant !
        missing.append(tid)

        # Tenter reconstruction depuis EDDS runtime
        layer_edds = data_dir / f"Terrain_{tid}_layer.edds"

        if layer_edds.exists():
            if rebuild_editor_layer(layer_edds, layer_dds):
                rebuilt.append(tid)
        else:
            # Générer layer vide
            if generate_empty_layer(layer_dds, editor_data_dir):
                generated.append(tid)

    # Rapport
    print(f"Layers : {len(ttiles) - len(missing)} OK | {len(rebuilt)} reconstruits | {len(generated)} générés vides")
    if missing:
        print(f"  Tuiles traitées : {missing}")

    return missing


def check_material_table(surfaces_list: List[str], catalog: Dict) -> List[str]:
    """
    Vérifie que tous les matériaux ont une couleur dans le catalogue

    Args:
        surfaces_list: Liste des surfaces (ordre = ID moteur)
        catalog: Catalogue enrichi

    Returns:
        Liste des messages d'erreur
    """
    issues = []

    for i, name in enumerate(surfaces_list):
        if name not in catalog:
            issues.append(f"  id {i:3} {name} — ABSENT du catalogue")
        elif not catalog[name].get('tint_srgb') and not catalog[name].get('avg_color'):
            issues.append(f"  id {i:3} {name} — pas de tint_srgb ni avg_color")

    # Rapport
    if issues:
        print(f"ATTENTION : {len(issues)} matériaux sans couleur :")
        for line in issues[:10]:  # Limiter à 10 pour ne pas polluer
            print(line)
        if len(issues) > 10:
            print(f"  ... et {len(issues) - 10} autres")
    else:
        print(f"Table matériaux : {len(surfaces_list)} entrées, toutes colorisées OK")

    return issues


def verify_environment(
    editor_data_dir: Path,
    data_dir: Path,
    surfaces_list: List[str],
    catalog: Dict
) -> Tuple[List[int], List[str]]:
    """
    Vérifie l'environnement avant génération satmap

    Args:
        editor_data_dir: Dossier .EditorData
        data_dir: Dossier .Data
        surfaces_list: Liste des surfaces
        catalog: Catalogue enrichi

    Returns:
        (layers_manquants, problemes_materiaux)
    """
    print()
    print("="*80)
    print("VERIFICATION ENVIRONNEMENT")
    print("="*80)
    print()

    # 1. Vérifier layers
    print("### 1. VERIFICATION LAYERS ###")
    missing_layers = check_missing_layers(editor_data_dir, data_dir)
    print()

    # 2. Vérifier table matériaux
    print("### 2. VERIFICATION TABLE MATERIAUX ###")
    material_issues = check_material_table(surfaces_list, catalog)
    print()

    print("="*80)
    print()

    return missing_layers, material_issues
