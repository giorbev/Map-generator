"""
generate_catalog.py - Génération propre du catalog.json depuis les .emat

Lecture seule sur catalog.json existant.
Sortie : catalog_generated.json (nouveau fichier).

Étapes :
1. Parser tous les .emat avec gestion de l'héritage
2. Générer entrées complètes (middle_bcr, tiling_scale, tint_srgb, avg_color)
3. Recopier entrées legacy (pas de .emat correspondant)
4. Rapport markdown détaillé
"""

import re
import json
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from datetime import date

from catalog_config import get_catalog_path, TEXTURES_USER_DIR


def parse_emat_file(emat_path: Path) -> Dict[str, str]:
    """
    Parse un fichier .emat et extrait ses paramètres bruts.

    Returns:
        {
            "parent": str | None,
            "BCRMiddleMap": str | "ABSENT",
            "MiddleColor": str | "ABSENT",
            "Color": str | "ABSENT",
            "MiddleScaleUV": str | "ABSENT",
            "MiddleBCRBlend": str | "ABSENT",
            "DebugColor": str | "ABSENT"
        }
    """
    params = {
        "parent": None,
        "BCRMiddleMap": "ABSENT",
        "MiddleColor": "ABSENT",
        "Color": "ABSENT",
        "MiddleScaleUV": "ABSENT",
        "MiddleBCRBlend": "ABSENT",
        "DebugColor": "ABSENT"
    }

    try:
        content = emat_path.read_text(encoding='utf-8', errors='ignore')

        # Parent (héritage)
        # Format: TerrainMaterial : "{GUID}data/Terrains/.../Parent.emat" {
        parent_match = re.search(r'TerrainMaterial\s*:\s*"[^"]*?([^/\\]+\.emat)"\s*\{', content)
        if parent_match:
            params["parent"] = parent_match.group(1)

        # BCRMiddleMap
        bcr_match = re.search(r'BCRMiddleMap\s+"([^"]+)"', content)
        if bcr_match:
            full_path = bcr_match.group(1)
            # Extraire nom de fichier sans GUID ni chemin
            name = full_path.split('/')[-1].split('\\')[-1]
            # Retirer GUID {xxx}
            name = re.sub(r'\{[^}]+\}', '', name)
            # Retirer extension .edds
            name = name.rsplit('.', 1)[0] if '.' in name else name
            params["BCRMiddleMap"] = name.strip()

        # MiddleColor (SANS guillemets, début de ligne après espaces)
        # Format: " MiddleColor 0.144 0.103 0.07 1"
        mc_match = re.search(r'^\s*MiddleColor\s+([\d\s.]+)', content, re.MULTILINE)
        if mc_match:
            params["MiddleColor"] = mc_match.group(1).strip()

        # Color (SANS guillemets, début de ligne, ne pas matcher MiddleColor/DebugColor)
        # Format: " Color 0.913 0.913 0.913 1"
        c_match = re.search(r'^\s*Color\s+([\d\s.]+)', content, re.MULTILINE)
        if c_match:
            params["Color"] = c_match.group(1).strip()

        # MiddleScaleUV (SANS guillemets)
        # Format: " MiddleScaleUV 75"
        scale_match = re.search(r'^\s*MiddleScaleUV\s+([\d.]+)', content, re.MULTILINE)
        if scale_match:
            params["MiddleScaleUV"] = scale_match.group(1).strip()

        # MiddleBCRBlend (SANS guillemets)
        blend_match = re.search(r'^\s*MiddleBCRBlend\s+([\d.]+)', content, re.MULTILINE)
        if blend_match:
            params["MiddleBCRBlend"] = blend_match.group(1).strip()

        # DebugColor (SANS guillemets)
        debug_match = re.search(r'^\s*DebugColor\s+([\d\s.]+)', content, re.MULTILINE)
        if debug_match:
            params["DebugColor"] = debug_match.group(1).strip()

    except Exception as e:
        params["_error"] = str(e)

    return params


def resolve_inheritance(emat_name: str, emat_dir: Path, cache: Dict[str, Dict]) -> Dict[str, str]:
    """
    Résout la chaîne d'héritage d'un .emat.

    Args:
        emat_name: nom du fichier .emat (avec extension)
        emat_dir: dossier contenant les .emat
        cache: {emat_name: params_resolved} pour éviter re-parsing

    Returns:
        Paramètres résolus (enfant écrase parent)
    """
    # Déjà en cache
    if emat_name in cache:
        return cache[emat_name]

    emat_path = emat_dir / emat_name
    if not emat_path.exists():
        # .emat introuvable
        cache[emat_name] = {"_missing": True}
        return cache[emat_name]

    # Parser le fichier
    params = parse_emat_file(emat_path)

    # Si a un parent, résoudre le parent d'abord
    if params["parent"]:
        parent_params = resolve_inheritance(params["parent"], emat_dir, cache)

        # Fusionner : parent puis enfant (enfant écrase)
        resolved = parent_params.copy()
        for key, value in params.items():
            if key != "parent" and value != "ABSENT":
                resolved[key] = value

        # Garder trace du parent
        resolved["_parent_chain"] = parent_params.get("_parent_chain", []) + [params["parent"]]

        cache[emat_name] = resolved
        return resolved

    # Pas de parent
    cache[emat_name] = params
    return params


def parse_color_value(value_str: str) -> np.ndarray:
    """
    Parse une valeur de couleur Enfusion.

    Format: "R G B" | "R G B A" (valeurs linéaires 0-1)

    Returns:
        np.array([R, G, B], dtype=float) en linéaire 0-1
    """
    if value_str == "ABSENT":
        return np.array([1.0, 1.0, 1.0], dtype=float)

    try:
        parts = value_str.split()
        rgb = [float(parts[0]), float(parts[1]), float(parts[2])]
        return np.array(rgb, dtype=float)
    except:
        return np.array([1.0, 1.0, 1.0], dtype=float)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """
    Convertit linéaire → sRGB (composante par composante).

    Args:
        linear: np.array([R, G, B], dtype=float) en 0-1

    Returns:
        np.array([R, G, B], dtype=uint8) en 0-255
    """
    # Formule sRGB standard
    srgb = np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055
    )

    # Clip et arrondir
    srgb = np.clip(srgb, 0.0, 1.0)
    return np.round(srgb * 255.0).astype(np.uint8)


def compute_tint_srgb(middle_color_str: str, color_str: str) -> List[int]:
    """
    Calcul du tint sRGB depuis MiddleColor × Color.

    Args:
        middle_color_str: valeur MiddleColor du .emat ("R G B" linéaire)
        color_str: valeur Color du .emat ("R G B" linéaire)

    Returns:
        [R, G, B] en sRGB 0-255
    """
    middle_color = parse_color_value(middle_color_str)
    color = parse_color_value(color_str)

    # Produit composante par composante
    tint_linear = middle_color * color

    # Conversion sRGB
    tint_srgb = linear_to_srgb(tint_linear)

    return tint_srgb.tolist()


def compute_avg_color(middle_path: Path, tint_srgb: List[int]) -> List[int]:
    """
    Calcule la couleur moyenne du middle × tint.

    Args:
        middle_path: chemin vers le fichier middle (PNG/JPG)
        tint_srgb: [R, G, B] en sRGB 0-255

    Returns:
        [R, G, B] moyenne en sRGB 0-255
    """
    try:
        # Charger image
        img = cv2.imread(str(middle_path))
        if img is None:
            return [128, 128, 128]  # Gris par défaut

        # Appliquer tint
        tint_bgr = np.array([tint_srgb[2], tint_srgb[1], tint_srgb[0]], dtype=float) / 255.0
        img_tinted = img * tint_bgr

        # Moyenne
        avg_bgr = img_tinted.mean(axis=(0, 1))
        avg_rgb = [int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0])]

        return avg_rgb

    except Exception:
        return [128, 128, 128]


def find_middle_file(middle_name: str, middles_dir: Path) -> Optional[Path]:
    """
    Cherche le fichier middle avec extensions .jpg ou .png.

    Args:
        middle_name: nom sans extension (ex: "Dirt_01_Middle_BCR")

    Returns:
        Path du fichier trouvé ou None
    """
    if middle_name == "ABSENT":
        return None

    for ext in ['.jpg', '.png', '.jpeg', '.JPG', '.PNG']:
        middle_path = middles_dir / (middle_name + ext)
        if middle_path.exists():
            return middle_path

    return None


def main():
    print("=" * 80)
    print("GÉNÉRATION CATALOG.JSON DEPUIS .EMAT")
    print("Lecture seule - Sortie : catalog_generated.json")
    print("=" * 80)
    print()

    # Chemins (via catalog_config)
    emat_dir = TEXTURES_USER_DIR / "emat"
    middles_dir = TEXTURES_USER_DIR / "texture_Middle"
    catalog_path = get_catalog_path()
    output_path = catalog_path.parent / "catalog_generated.json"

    print("📂 CHEMINS ABSOLUS :")
    print(f"  emat_dir     : {emat_dir.absolute()}")
    print(f"  middles_dir  : {middles_dir.absolute()}")
    print(f"  catalog      : {catalog_path.absolute()} (lecture seule)")
    print(f"  sortie       : {output_path.absolute()}")
    print()

    # Vérifications
    if not emat_dir.exists():
        print("❌ emat_dir introuvable")
        return 1

    if not middles_dir.exists():
        print("❌ middles_dir introuvable")
        return 1

    if not catalog_path.exists():
        print("❌ catalog introuvable")
        return 1

    # Charger catalogue existant
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog_old = json.load(f)

    print(f"✅ Catalogue actuel chargé : {len(catalog_old)} entrées")
    print()

    # Lister tous les .emat
    emat_files = sorted([f for f in emat_dir.iterdir() if f.suffix == ".emat"])
    print(f"✅ {len(emat_files)} fichiers .emat trouvés")
    print()

    print("🔄 Analyse en cours...")
    print()

    # DIAGNOSTIC — Test parsing ForestConiferous_01_Base.emat
    test_emat = emat_dir / "ForestConiferous_01_Base.emat"
    if test_emat.exists():
        print("=" * 80)
        print("🔍 DIAGNOSTIC PARSING — ForestConiferous_01_Base.emat")
        print(f"Chemin absolu : {test_emat.absolute()}")
        print()

        # Contenu brut (25 premières lignes)
        content_lines = test_emat.read_text(encoding='utf-8', errors='ignore').split('\n')
        print("Contenu brut (25 premières lignes) :")
        for i, line in enumerate(content_lines[:25], 1):
            print(f"{i:2d}: {repr(line)}")
        print()

        # Parsing
        params_parsed = parse_emat_file(test_emat)
        print("Résultat parsing (avant héritage) :")
        for k, v in params_parsed.items():
            print(f"  {k:20s} = {repr(v)}")
        print()

        # Calcul tint
        if params_parsed["MiddleColor"] != "ABSENT" and params_parsed["Color"] != "ABSENT":
            tint_calc = compute_tint_srgb(params_parsed["MiddleColor"], params_parsed["Color"])
            print(f"Tint calculé : {tint_calc}")
            print("Attendu      : [101, 86, 71]")
        print()

        # Tiling
        if params_parsed["MiddleScaleUV"] != "ABSENT":
            print(f"Tiling lu    : {params_parsed['MiddleScaleUV']}")
            print("Attendu      : 75")
        print()
        print("=" * 80)
        print()

    # Cache pour résolution héritage
    inheritance_cache = {}

    # Nouveau catalogue
    catalog_new = {}

    # Stats
    stats = {
        "emat_processed": 0,
        "legacy_kept": 0,
        "middle_missing": [],
        "parent_missing": [],
        "emat_names": set()
    }

    # ÉTAPE 1-2 : Parser chaque .emat et générer entrée
    for emat_path in emat_files:
        emat_name = emat_path.name
        stats["emat_names"].add(emat_name)

        # Résoudre héritage
        params = resolve_inheritance(emat_name, emat_dir, inheritance_cache)

        # Vérifier si parent introuvable
        if "_parent_chain" in params:
            for parent_name in params["_parent_chain"]:
                parent_path = emat_dir / parent_name
                if not parent_path.exists():
                    stats["parent_missing"].append(f"{emat_name} → {parent_name}")

        # Construire entrée
        entry = {}

        # middle_bcr
        bcr_name = params.get("BCRMiddleMap", "ABSENT")
        if bcr_name != "ABSENT":
            # Remplacer extension .edds par .png
            middle_bcr = bcr_name + ".png"

            # Vérifier existence dans texture_Middle/
            middle_path = find_middle_file(bcr_name, middles_dir)
            if middle_path:
                # Utiliser extension réelle trouvée
                middle_bcr = middle_path.name
            else:
                # Fichier manquant
                stats["middle_missing"].append(f"{emat_name} → {bcr_name}")
        else:
            middle_bcr = None
            middle_path = None

        # tiling_scale
        scale_str = params.get("MiddleScaleUV", "ABSENT")
        if scale_str != "ABSENT":
            try:
                # Prendre premier nombre (format "X Y")
                tiling_scale = float(scale_str.split()[0])
            except:
                tiling_scale = 100.0
        else:
            tiling_scale = 100.0  # Valeur par défaut moteur Workbench

        # tint_srgb
        middle_color_str = params.get("MiddleColor", "ABSENT")
        color_str = params.get("Color", "ABSENT")
        tint_srgb = compute_tint_srgb(middle_color_str, color_str)

        # avg_color
        if middle_path and middle_path.exists():
            avg_color = compute_avg_color(middle_path, tint_srgb)
        else:
            avg_color = [128, 128, 128]

        # Construire entrée avec TOUS les champs du schéma
        entry = {
            "provenance": "vanilla",
            "parent": params.get("_parent_chain", [])[-1] if "_parent_chain" in params else None,
            "middle_bcr": middle_bcr,
            "avg_color": avg_color,
            "tint": tint_srgb,  # Ancien champ (même valeur que tint_srgb)
            "role": "auto_generated",  # Rôle générique
            "resolved": "auto",
            "resolved_date": str(date.today()),
            "tiling_scale": tiling_scale,
            "tint_srgb": tint_srgb
        }

        # Ajouter champs info supplémentaires (source, raw values)
        entry["source"] = "emat"
        entry["middle_color_raw"] = middle_color_str
        entry["color_raw"] = color_str

        catalog_new[emat_name] = entry
        stats["emat_processed"] += 1

    # ÉTAPE 3 : Recopier entrées legacy
    for key, entry in catalog_old.items():
        if key not in stats["emat_names"]:
            # Pas de .emat correspondant → legacy
            entry_copy = entry.copy()
            entry_copy["source"] = "legacy"
            catalog_new[key] = entry_copy
            stats["legacy_kept"] += 1

    # Écrire catalog_generated.json
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog_new, f, indent=2, ensure_ascii=False)

    print(f"✅ Catalogue généré : {output_path.absolute()}")
    print()

    # ÉTAPE 4 : Rapport markdown (à côté du catalog)
    report_path = catalog_path.parent / "RAPPORT_CATALOG_GENERATION.md"

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 📊 RAPPORT GÉNÉRATION CATALOG.JSON\\n\\n")
        f.write(f"**Date :** {date.today()}\\n")
        f.write(f"**Sortie :** {output_path.name}\\n\\n")

        # Chemins absolus en tête
        f.write("## 📂 CHEMINS ABSOLUS\\n\\n")
        f.write("```\\n")
        f.write(f"emat_dir     : {emat_dir.absolute()}\\n")
        f.write(f"middles_dir  : {middles_dir.absolute()}\\n")
        f.write(f"catalog      : {catalog_path.absolute()}\\n")
        f.write(f"sortie       : {output_path.absolute()}\\n")
        f.write("```\\n\\n")

        f.write("---\\n\\n")

        # Récap
        f.write("## 📊 RÉCAPITULATIF\\n\\n")
        f.write("```\\n")
        f.write(f"Entrées .emat générées  : {stats['emat_processed']}\\n")
        f.write(f"Entrées legacy gardées  : {stats['legacy_kept']}\\n")
        f.write(f"Total catalogue nouveau : {len(catalog_new)}\\n")
        f.write("\\n")
        f.write(f"Middles manquants       : {len(stats['middle_missing'])}\\n")
        f.write(f"Parents introuvables    : {len(stats['parent_missing'])}\\n")
        f.write("```\\n\\n")

        # Middles manquants
        f.write("---\\n\\n")
        f.write("## ❌ MIDDLES MANQUANTS\\n\\n")

        if stats["middle_missing"]:
            for item in sorted(stats["middle_missing"]):
                f.write(f"- {item}\\n")
            f.write("\\n")
        else:
            f.write("✅ Aucun middle manquant\\n\\n")

        # Parents introuvables
        f.write("---\\n\\n")
        f.write("## ⚠️  PARENTS INTROUVABLES\\n\\n")

        if stats["parent_missing"]:
            for item in sorted(set(stats["parent_missing"])):
                f.write(f"- {item}\\n")
            f.write("\\n")
        else:
            f.write("✅ Tous les parents trouvés\\n\\n")

        # Diff vs catalog.json actuel
        f.write("---\\n\\n")
        f.write("## 🔄 DIFF vs CATALOG.JSON ACTUEL\\n\\n")

        # Entrées ajoutées
        added = set(catalog_new.keys()) - set(catalog_old.keys())
        if added:
            f.write(f"### ➕ Entrées ajoutées ({len(added)})\\n\\n")
            for key in sorted(added):
                f.write(f"- {key}\\n")
            f.write("\\n")

        # Entrées supprimées
        removed = set(catalog_old.keys()) - set(catalog_new.keys())
        if removed:
            f.write(f"### ➖ Entrées supprimées ({len(removed)})\\n\\n")
            for key in sorted(removed):
                f.write(f"- {key}\\n")
            f.write("\\n")

        # Entrées modifiées
        modified = []
        for key in catalog_new.keys():
            if key in catalog_old:
                old_entry = catalog_old[key]
                new_entry = catalog_new[key]

                # Comparer champs importants
                changes = []
                for field in ["middle_bcr", "tint_srgb", "avg_color", "tiling_scale"]:
                    old_val = old_entry.get(field)
                    new_val = new_entry.get(field)
                    if old_val != new_val:
                        changes.append((field, old_val, new_val))

                if changes:
                    modified.append((key, changes))

        f.write(f"### 🔄 Entrées modifiées ({len(modified)})\\n\\n")

        # Focus sur Dirt_*, Forest*, SulfurStream, Grass_03
        priority = ["Dirt_01.emat", "Dirt_02.emat", "Dirt_03.emat",
                   "ForestConiferous_01_Base.emat", "ForestConiferous_02.emat",
                   "ForestDeciduous_01_Base.emat", "ForestDeciduous_02.emat",
                   "SulfurStream_01_bed.emat", "Grass_03_default.emat"]

        # Priority first
        for key in priority:
            for mod_key, changes in modified:
                if mod_key == key:
                    f.write(f"#### {mod_key} ⭐\\n\\n")
                    for field, old_val, new_val in changes:
                        f.write(f"- **{field}** : `{old_val}` → `{new_val}`\\n")
                    f.write("\\n")

        # Autres
        for mod_key, changes in modified:
            if mod_key not in priority:
                f.write(f"#### {mod_key}\\n\\n")
                for field, old_val, new_val in changes:
                    f.write(f"- **{field}** : `{old_val}` → `{new_val}`\\n")
                f.write("\\n")

    print(f"✅ Rapport généré : {report_path.absolute()}")
    print()
    print("=" * 80)
    print("FIN DE LA GÉNÉRATION")
    print("=" * 80)

    return 0


def run_generate_catalog() -> dict:
    """
    Fonction wrapper pour appeler la génération depuis l'app (sans sys.exit).

    Returns:
        {
            "ok": bool,
            "catalog_generated_path": str,
            "report_path": str,
            "entries_count": int,
            "diff_summary": {
                "added": int,
                "removed": int,
                "modified": int
            },
            "error": str (si ok=False)
        }
    """
    try:
        # Chemins (via catalog_config)
        emat_dir = TEXTURES_USER_DIR / "emat"
        middles_dir = TEXTURES_USER_DIR / "texture_Middle"
        catalog_path = get_catalog_path()
        output_path = catalog_path.parent / "catalog_generated.json"
        report_path = catalog_path.parent / "RAPPORT_CATALOG_GENERATION.md"

        # Vérifications
        if not emat_dir.exists():
            return {"ok": False, "error": f"emat_dir introuvable : {emat_dir}"}

        if not middles_dir.exists():
            return {"ok": False, "error": f"middles_dir introuvable : {middles_dir}"}

        if not catalog_path.exists():
            return {"ok": False, "error": f"catalog introuvable : {catalog_path}"}

        # Charger catalogue existant
        with open(catalog_path, 'r', encoding='utf-8') as f:
            catalog_old = json.load(f)

        # Lister tous les .emat
        emat_files = sorted([f for f in emat_dir.iterdir() if f.suffix == ".emat"])

        # Cache pour résolution héritage
        inheritance_cache = {}

        # Nouveau catalogue
        catalog_new = {}

        # Stats
        stats = {
            "emat_processed": 0,
            "legacy_kept": 0,
            "middle_missing": [],
            "parent_missing": [],
            "emat_names": set()
        }

        # ÉTAPE 1-2 : Parser chaque .emat et générer entrée
        for emat_path in emat_files:
            emat_name = emat_path.name
            stats["emat_names"].add(emat_name)

            # Résoudre héritage
            params = resolve_inheritance(emat_name, emat_dir, inheritance_cache)

            # Vérifier si parent introuvable
            if "_parent_chain" in params:
                for parent_name in params["_parent_chain"]:
                    parent_path = emat_dir / parent_name
                    if not parent_path.exists():
                        stats["parent_missing"].append(f"{emat_name} → {parent_name}")

            # Construire entrée
            entry = {}

            # middle_bcr
            bcr_name = params.get("BCRMiddleMap", "ABSENT")
            if bcr_name != "ABSENT":
                # Remplacer extension .edds par .png
                middle_bcr = bcr_name + ".png"

                # Vérifier existence dans texture_Middle/
                middle_path = find_middle_file(bcr_name, middles_dir)
                if middle_path:
                    # Utiliser extension réelle trouvée
                    middle_bcr = middle_path.name
                else:
                    # Fichier manquant
                    stats["middle_missing"].append(f"{emat_name} → {bcr_name}")
            else:
                middle_bcr = None
                middle_path = None

            # tiling_scale
            scale_str = params.get("MiddleScaleUV", "ABSENT")
            if scale_str != "ABSENT":
                try:
                    # Prendre premier nombre (format "X Y")
                    tiling_scale = float(scale_str.split()[0])
                except:
                    tiling_scale = 100.0
            else:
                tiling_scale = 100.0  # Valeur par défaut moteur Workbench

            # tint_srgb
            middle_color_str = params.get("MiddleColor", "ABSENT")
            color_str = params.get("Color", "ABSENT")
            tint_srgb = compute_tint_srgb(middle_color_str, color_str)

            # avg_color
            if middle_path and middle_path.exists():
                avg_color = compute_avg_color(middle_path, tint_srgb)
            else:
                avg_color = [128, 128, 128]

            # Construire entrée avec TOUS les champs du schéma
            entry = {
                "provenance": "vanilla",
                "parent": params.get("_parent_chain", [])[-1] if "_parent_chain" in params else None,
                "middle_bcr": middle_bcr,
                "avg_color": avg_color,
                "tint": tint_srgb,  # Ancien champ (même valeur que tint_srgb)
                "role": "auto_generated",  # Rôle générique
                "resolved": "auto",
                "resolved_date": str(date.today()),
                "tiling_scale": tiling_scale,
                "tint_srgb": tint_srgb
            }

            # Ajouter champs info supplémentaires (source, raw values)
            entry["source"] = "emat"
            entry["middle_color_raw"] = middle_color_str
            entry["color_raw"] = color_str

            catalog_new[emat_name] = entry
            stats["emat_processed"] += 1

        # ÉTAPE 3 : Recopier entrées legacy
        for key, entry in catalog_old.items():
            if key not in stats["emat_names"]:
                # Pas de .emat correspondant → legacy
                entry_copy = entry.copy()
                entry_copy["source"] = "legacy"
                catalog_new[key] = entry_copy
                stats["legacy_kept"] += 1

        # Écrire catalog_generated.json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(catalog_new, f, indent=2, ensure_ascii=False)

        # ÉTAPE 4 : Rapport markdown
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# 📊 RAPPORT GÉNÉRATION CATALOG.JSON\\n\\n")
            f.write(f"**Date :** {date.today()}\\n")
            f.write(f"**Sortie :** {output_path.name}\\n\\n")

            # Chemins absolus en tête
            f.write("## 📂 CHEMINS ABSOLUS\\n\\n")
            f.write("```\\n")
            f.write(f"emat_dir     : {emat_dir.absolute()}\\n")
            f.write(f"middles_dir  : {middles_dir.absolute()}\\n")
            f.write(f"catalog      : {catalog_path.absolute()}\\n")
            f.write(f"sortie       : {output_path.absolute()}\\n")
            f.write("```\\n\\n")

            f.write("---\\n\\n")

            # Récap
            f.write("## 📊 RÉCAPITULATIF\\n\\n")
            f.write("```\\n")
            f.write(f"Entrées .emat générées  : {stats['emat_processed']}\\n")
            f.write(f"Entrées legacy gardées  : {stats['legacy_kept']}\\n")
            f.write(f"Total catalogue nouveau : {len(catalog_new)}\\n")
            f.write("\\n")
            f.write(f"Middles manquants       : {len(stats['middle_missing'])}\\n")
            f.write(f"Parents introuvables    : {len(stats['parent_missing'])}\\n")
            f.write("```\\n\\n")

            # Middles manquants
            f.write("---\\n\\n")
            f.write("## ❌ MIDDLES MANQUANTS\\n\\n")

            if stats["middle_missing"]:
                for item in sorted(stats["middle_missing"]):
                    f.write(f"- {item}\\n")
                f.write("\\n")
            else:
                f.write("✅ Aucun middle manquant\\n\\n")

            # Parents introuvables
            f.write("---\\n\\n")
            f.write("## ⚠️  PARENTS INTROUVABLES\\n\\n")

            if stats["parent_missing"]:
                for item in sorted(set(stats["parent_missing"])):
                    f.write(f"- {item}\\n")
                f.write("\\n")
            else:
                f.write("✅ Tous les parents trouvés\\n\\n")

            # Diff vs catalog.json actuel
            f.write("---\\n\\n")
            f.write("## 🔄 DIFF vs CATALOG.JSON ACTUEL\\n\\n")

            # Entrées ajoutées
            added = set(catalog_new.keys()) - set(catalog_old.keys())
            if added:
                f.write(f"### ➕ Entrées ajoutées ({len(added)})\\n\\n")
                for key in sorted(added):
                    f.write(f"- {key}\\n")
                f.write("\\n")

            # Entrées supprimées
            removed = set(catalog_old.keys()) - set(catalog_new.keys())
            if removed:
                f.write(f"### ➖ Entrées supprimées ({len(removed)})\\n\\n")
                for key in sorted(removed):
                    f.write(f"- {key}\\n")
                f.write("\\n")

            # Entrées modifiées
            modified = []
            for key in catalog_new.keys():
                if key in catalog_old:
                    old_entry = catalog_old[key]
                    new_entry = catalog_new[key]

                    # Comparer champs importants
                    changes = []
                    for field in ["middle_bcr", "tint_srgb", "avg_color", "tiling_scale"]:
                        old_val = old_entry.get(field)
                        new_val = new_entry.get(field)
                        if old_val != new_val:
                            changes.append((field, old_val, new_val))

                    if changes:
                        modified.append((key, changes))

            f.write(f"### 🔄 Entrées modifiées ({len(modified)})\\n\\n")

            # Focus sur Dirt_*, Forest*, SulfurStream, Grass_03
            priority = ["Dirt_01.emat", "Dirt_02.emat", "Dirt_03.emat",
                       "ForestConiferous_01_Base.emat", "ForestConiferous_02.emat",
                       "ForestDeciduous_01_Base.emat", "ForestDeciduous_02.emat",
                       "SulfurStream_01_bed.emat", "Grass_03_default.emat"]

            # Priority first
            for key in priority:
                for mod_key, changes in modified:
                    if mod_key == key:
                        f.write(f"#### {mod_key} ⭐\\n\\n")
                        for field, old_val, new_val in changes:
                            f.write(f"- **{field}** : `{old_val}` → `{new_val}`\\n")
                        f.write("\\n")

            # Autres
            for mod_key, changes in modified:
                if mod_key not in priority:
                    f.write(f"#### {mod_key}\\n\\n")
                    for field, old_val, new_val in changes:
                        f.write(f"- **{field}** : `{old_val}` → `{new_val}`\\n")
                    f.write("\\n")

        # Calculer résumé diff
        added_count = len(set(catalog_new.keys()) - set(catalog_old.keys()))
        removed_count = len(set(catalog_old.keys()) - set(catalog_new.keys()))
        modified_count = 0
        for key in catalog_new.keys():
            if key in catalog_old:
                old_entry = catalog_old[key]
                new_entry = catalog_new[key]
                for field in ["middle_bcr", "tint_srgb", "avg_color", "tiling_scale"]:
                    if old_entry.get(field) != new_entry.get(field):
                        modified_count += 1
                        break

        return {
            "ok": True,
            "catalog_generated_path": str(output_path.absolute()),
            "report_path": str(report_path.absolute()),
            "entries_count": len(catalog_new),
            "diff_summary": {
                "added": added_count,
                "removed": removed_count,
                "modified": modified_count
            }
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import sys
    sys.exit(main())
