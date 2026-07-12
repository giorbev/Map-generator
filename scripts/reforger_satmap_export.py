"""
Reforger Satmap Export — Phase 1: Catalogue de textures

Gère le catalogue des surfaces .emat (vanilla + custom) et leur résolution
vers les PNG middle BCR pour l'export masques.

Workflow:
1. Scanner texturesArmaReforger/ (vanilla + customs)
2. Résoudre chaque .emat → middle PNG + couleur moyenne
3. Croisement avec .terr du monde pour validation
4. Export masques globaux par surface (Phase 2 — non implémenté)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from PIL import Image


# ── Chemins des ressources ──────────────────────────────────────────────────

CATALOG_ROOT = Path("data/Textures_ArmaReforger")
CATALOG_FILE = CATALOG_ROOT / "catalog.json"

VANILLA_TEXTURES_DIR = CATALOG_ROOT / "Vanilla" / "textures"
VANILLA_EMAT_DIR = CATALOG_ROOT / "Vanilla"

CUSTOM_TEXTURES_DIR = CATALOG_ROOT / "Customs" / "Textures"
CUSTOM_EMAT_DIR = CATALOG_ROOT / "Customs"

TEXTURE_MAPPING_FILE = CATALOG_ROOT / "texture_mapping.json"

# Couleur fallback pour surfaces inconnues (magenta debug)
FALLBACK_COLOR = [255, 0, 255]


# ── Chargement du mapping manuel ────────────────────────────────────────────

def load_texture_mapping() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Charge le mapping manuel .emat -> PNG middle BCR + couleurs manuelles.

    Returns:
        (mappings, manual_colors)
        mappings: {emat_name: png_filename}
        manual_colors: {emat_name: "#RRGGBB"}
    """
    if not TEXTURE_MAPPING_FILE.exists():
        return {}, {}
    try:
        import json
        data = json.loads(TEXTURE_MAPPING_FILE.read_text(encoding="utf-8"))
        return data.get("mappings", {}), data.get("manual_colors", {})
    except Exception:
        return {}, {}


def hex_to_rgb(hex_color: str) -> List[int]:
    """Convertit #RRGGBB -> [R, G, B]."""
    hex_color = hex_color.lstrip('#')
    return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]


# ── Utilitaires ──────────────────────────────────────────────────────────────

def normalize_stem(emat_name: str) -> str:
    """
    Normalise un nom .emat en stem minuscule sans extension.

    Examples:
        "Grass_01.emat" → "grass_01"
        "ZI_CropField_01.emat" → "zi_cropfield_01"
    """
    stem = Path(emat_name).stem.lower()
    return stem


def compute_avg_color(png_path: Path) -> List[int]:
    """
    Calcule la couleur moyenne RGB d'un PNG.

    Returns:
        [R, G, B] int dans [0, 255]

    Raises:
        FileNotFoundError si le PNG n'existe pas
    """
    try:
        img = Image.open(png_path).convert("RGB")
        arr = np.array(img, dtype=np.float32)
        avg = arr.mean(axis=(0, 1))
        return [int(round(c)) for c in avg]
    except Exception as e:
        raise FileNotFoundError(f"Impossible de lire {png_path}: {e}")


def find_matching_png(stem: str, search_dir: Path) -> Optional[Path]:
    """
    Cherche un PNG/JPG middle BCR par stem (insensible à la casse) dans search_dir.

    Patterns supportés :
    - Grass_01.png (exact)
    - Grass_01_Middle_BCR.jpg (Reforger)
    - Grass_Middle_01_BCR.jpg (variante)

    Returns:
        Path du PNG/JPG trouvé, ou None
    """
    if not search_dir.exists():
        return None

    stem_lower = stem.lower()

    # Pattern 1 : exact match (Grass_01.png)
    for ext in [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"]:
        candidate = search_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate

    # Pattern 2 : _Middle_BCR (Grass_01_Middle_BCR.jpg)
    for ext in [".jpg", ".JPG", ".png", ".PNG"]:
        candidate = search_dir / f"{stem}_Middle_BCR{ext}"
        if candidate.exists():
            return candidate

    # Pattern 3 : inversé (Grass_Middle_01_BCR.jpg)
    # Ex: MountainGrass_01 -> Grass_Mountain_01_Middle_BCR
    parts = stem.split("_")
    if len(parts) >= 2:
        # Essayer réarrangement
        for i in range(len(parts)):
            for j in range(i+1, len(parts)+1):
                reordered = "_".join(parts[i:j] + parts[:i] + parts[j:])
                for ext in [".jpg", ".JPG", ".png", ".PNG"]:
                    candidate = search_dir / f"{reordered}_Middle_BCR{ext}"
                    if candidate.exists():
                        return candidate

    # Pattern 4 : recherche fuzzy par glob
    for img in search_dir.glob("*"):
        if not img.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            continue
        img_stem = img.stem.lower().replace("_middle_bcr", "").replace("_middle", "")
        if stem_lower in img_stem or img_stem in stem_lower:
            return img

    return None


# ── Gestion du catalogue ─────────────────────────────────────────────────────

class TextureCatalog:
    """
    Catalogue des surfaces .emat Reforger (vanilla + custom).

    Structure JSON par entrée:
    {
      "ZI_CropField_01.emat": {
        "provenance": "custom",
        "parent": "CropField_01.emat",
        "middle_bcr": null,
        "avg_color": null,
        "tint": null,
        "role": "champ",
        "resolved": "convention",
        "resolved_date": "2026-07-03"
      }
    }

    resolved ∈ manual | auto | convention | fallback
    """

    def __init__(self, catalog_path: Path = CATALOG_FILE):
        self.catalog_path = catalog_path
        self.data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Charge le catalogue depuis JSON (s'il existe)."""
        if self.catalog_path.exists():
            try:
                with open(self.catalog_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[WARNING] Impossible de charger {self.catalog_path}: {e}")
                self.data = {}
        else:
            self.data = {}

    def save(self) -> None:
        """Sauvegarde le catalogue en JSON."""
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.catalog_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_entry(self, emat_name: str) -> Optional[dict]:
        """Récupère une entrée du catalogue (None si absente)."""
        return self.data.get(emat_name)

    def set_entry(self, emat_name: str, entry: dict) -> None:
        """Ajoute/met à jour une entrée du catalogue."""
        self.data[emat_name] = entry

    def iter_entries(self):
        """Itère sur (emat_name, entry)."""
        return self.data.items()


# ── Scanner vanilla ──────────────────────────────────────────────────────────

def scan_vanilla_textures() -> Dict[str, dict]:
    """
    Scanner les textures vanilla et générer les entrées du catalogue.

    Returns:
        {emat_name: entry} pour chaque .emat trouvé dans vanilla/emat/

    Toutes les entrées vanilla sont marquées resolved="manual" (jamais
    modifiées par un re-scan).
    """
    entries = {}

    if not VANILLA_EMAT_DIR.exists():
        print(f"[WARNING] Dossier vanilla/emat absent : {VANILLA_EMAT_DIR}")
        return entries

    # Charger mapping manuel + couleurs manuelles
    mapping, manual_colors = load_texture_mapping()

    for emat_file in VANILLA_EMAT_DIR.glob("*.emat"):
        emat_name = emat_file.name
        stem = emat_file.stem

        # Chercher PNG : d'abord mapping manuel, puis auto
        png_path = None
        if emat_name in mapping:
            mapped_png = VANILLA_TEXTURES_DIR / mapping[emat_name]
            if mapped_png.exists():
                png_path = mapped_png

        if not png_path:
            png_path = find_matching_png(stem, VANILLA_TEXTURES_DIR)

        # Couleur : priorité couleur manuelle > calcul PNG > fallback
        if emat_name in manual_colors:
            avg_color = hex_to_rgb(manual_colors[emat_name])
            middle_rel = png_path.relative_to(CATALOG_ROOT).as_posix() if png_path else None
        elif png_path:
            try:
                avg_color = compute_avg_color(png_path)
                middle_rel = png_path.relative_to(CATALOG_ROOT).as_posix()
            except Exception as e:
                print(f"[WARNING] Erreur calcul couleur {emat_name}: {e}")
                avg_color = FALLBACK_COLOR
                middle_rel = None
        else:
            avg_color = FALLBACK_COLOR
            middle_rel = None

        # Déduire rôle depuis _MAT_STEM_TO_ROLE
        from reforger_texture_budget import _MAT_STEM_TO_ROLE, _MAT_STEM_ORDER
        role = None
        for pattern in _MAT_STEM_ORDER:
            if pattern.lower() in stem.lower():
                role = _MAT_STEM_TO_ROLE[pattern]
                break

        entries[emat_name] = {
            "provenance": "vanilla",
            "parent": None,
            "middle_bcr": middle_rel,
            "avg_color": avg_color,
            "tint": None,
            "role": role,
            "resolved": "manual",
            "resolved_date": datetime.now().strftime("%Y-%m-%d"),
        }

    return entries


# ── Scanner customs ──────────────────────────────────────────────────────────

def scan_custom_textures(vanilla_catalog: Dict[str, dict]) -> Dict[str, dict]:
    """
    Scanner les textures custom et résoudre par convention zi_.

    Convention:
    - zi_X.emat → chercher X.emat dans vanilla_catalog
      - Trouvé → héritage : copier middle_bcr + avg_color du parent
      - Non trouvé → création : chercher PNG dans customs/textures/

    Args:
        vanilla_catalog: entrées vanilla déjà scannées

    Returns:
        {emat_name: entry} pour chaque .emat custom
    """
    entries = {}

    if not CUSTOM_EMAT_DIR.exists():
        print(f"[INFO] Dossier customs/emat absent : {CUSTOM_EMAT_DIR}")
        return entries

    # Charger mapping manuel + couleurs manuelles
    mapping, manual_colors = load_texture_mapping()

    # Index vanilla par stem normalisé pour matching insensible casse
    vanilla_by_stem = {
        normalize_stem(name): (name, entry)
        for name, entry in vanilla_catalog.items()
    }

    for emat_file in CUSTOM_EMAT_DIR.glob("*.emat"):
        emat_name = emat_file.name
        stem = emat_file.stem

        # Convention zi_
        if stem.lower().startswith("zi_"):
            # Retirer préfixe
            base_stem = stem[3:]
            base_norm = base_stem.lower()

            # Chercher parent vanilla
            if base_norm in vanilla_by_stem:
                parent_name, parent_entry = vanilla_by_stem[base_norm]

                # Héritage
                entries[emat_name] = {
                    "provenance": "custom",
                    "parent": parent_name,
                    "middle_bcr": parent_entry["middle_bcr"],
                    "avg_color": parent_entry["avg_color"],
                    "tint": None,
                    "role": parent_entry.get("role"),
                    "resolved": "convention",
                    "resolved_date": datetime.now().strftime("%Y-%m-%d"),
                }
            else:
                # Création custom — chercher PNG (mapping ou auto)
                png_path = None

                # Mapping : chercher d'abord dans Vanilla, puis Customs
                if emat_name in mapping:
                    # Essayer Vanilla d'abord
                    mapped_vanilla = VANILLA_TEXTURES_DIR / mapping[emat_name]
                    if mapped_vanilla.exists():
                        png_path = mapped_vanilla
                    else:
                        # Sinon Customs
                        mapped_custom = CUSTOM_TEXTURES_DIR / mapping[emat_name]
                        if mapped_custom.exists():
                            png_path = mapped_custom

                if not png_path:
                    png_path = find_matching_png(stem, CUSTOM_TEXTURES_DIR)

                # Couleur : priorité manuelle > PNG > fallback
                if emat_name in manual_colors:
                    avg_color = hex_to_rgb(manual_colors[emat_name])
                    middle_rel = png_path.relative_to(CATALOG_ROOT).as_posix() if png_path else None
                elif png_path:
                    try:
                        avg_color = compute_avg_color(png_path)
                        middle_rel = png_path.relative_to(CATALOG_ROOT).as_posix()
                    except Exception as e:
                        print(f"[WARNING] Erreur calcul couleur {emat_name}: {e}")
                        avg_color = FALLBACK_COLOR
                        middle_rel = None
                else:
                    avg_color = FALLBACK_COLOR
                    middle_rel = None

                # Déduire rôle
                from reforger_texture_budget import _MAT_STEM_TO_ROLE, _MAT_STEM_ORDER
                role = None
                for pattern in _MAT_STEM_ORDER:
                    if pattern.lower() in stem.lower():
                        role = _MAT_STEM_TO_ROLE[pattern]
                        break

                entries[emat_name] = {
                    "provenance": "custom",
                    "parent": None,
                    "middle_bcr": middle_rel,
                    "avg_color": avg_color,
                    "tint": None,
                    "role": role,
                    "resolved": "convention",
                    "resolved_date": datetime.now().strftime("%Y-%m-%d"),
                }
        else:
            # Pas de convention zi_ → traiter comme création
            png_path = find_matching_png(stem, CUSTOM_TEXTURES_DIR)

            if png_path:
                try:
                    avg_color = compute_avg_color(png_path)
                    middle_rel = png_path.relative_to(CATALOG_ROOT).as_posix()
                except Exception as e:
                    print(f"[WARNING] Erreur calcul couleur {emat_name}: {e}")
                    avg_color = FALLBACK_COLOR
                    middle_rel = None
            else:
                avg_color = FALLBACK_COLOR
                middle_rel = None

            from reforger_texture_budget import _MAT_STEM_TO_ROLE, _MAT_STEM_ORDER
            role = None
            for pattern in _MAT_STEM_ORDER:
                if pattern.lower() in stem.lower():
                    role = _MAT_STEM_TO_ROLE[pattern]
                    break

            entries[emat_name] = {
                "provenance": "custom",
                "parent": None,
                "middle_bcr": middle_rel,
                "avg_color": avg_color,
                "tint": None,
                "role": role,
                "resolved": "auto",
                "resolved_date": datetime.now().strftime("%Y-%m-%d"),
            }

    return entries


# ── Build catalog ────────────────────────────────────────────────────────────

def build_catalog(preserve_manual: bool = True) -> Tuple[TextureCatalog, dict]:
    """
    Reconstruit le catalogue depuis les dossiers vanilla + customs.

    Args:
        preserve_manual: si True, préserve les entrées resolved="manual"
                        et les champs tint non nuls

    Returns:
        (catalog, report)

        report = {
            "total": int,
            "vanilla": int,
            "custom": int,
            "convention": int,
            "fallback": int,
            "zi_resolved": List[str],
            "fallback_list": List[str],
        }
    """
    catalog = TextureCatalog()
    old_data = catalog.data.copy() if preserve_manual else {}

    # Scanner vanilla
    vanilla_entries = scan_vanilla_textures()

    # Scanner customs
    custom_entries = scan_custom_textures(vanilla_entries)

    # Fusionner
    new_data = {}
    new_data.update(vanilla_entries)
    new_data.update(custom_entries)

    # Préserver manual + tint
    if preserve_manual:
        for emat_name, old_entry in old_data.items():
            if emat_name not in new_data:
                # Entrée supprimée des dossiers → garder si manual
                if old_entry.get("resolved") == "manual":
                    new_data[emat_name] = old_entry
            else:
                # Entrée existante → préserver manual/tint
                new_entry = new_data[emat_name]
                if old_entry.get("resolved") == "manual":
                    new_data[emat_name] = old_entry
                elif old_entry.get("tint") is not None:
                    new_entry["tint"] = old_entry["tint"]

    catalog.data = new_data

    # Rapport
    zi_resolved = [
        name for name, entry in new_data.items()
        if entry.get("provenance") == "custom"
        and entry.get("resolved") == "convention"
        and entry.get("parent") is not None
    ]

    fallback_list = [
        name for name, entry in new_data.items()
        if entry.get("avg_color") == FALLBACK_COLOR
    ]

    report = {
        "total": len(new_data),
        "vanilla": sum(1 for e in new_data.values() if e.get("provenance") == "vanilla"),
        "custom": sum(1 for e in new_data.values() if e.get("provenance") == "custom"),
        "convention": sum(1 for e in new_data.values() if e.get("resolved") == "convention"),
        "fallback": len(fallback_list),
        "zi_resolved": zi_resolved,
        "fallback_list": fallback_list,
    }

    return catalog, report


# ── Croisement avec .terr ────────────────────────────────────────────────────

def verify_catalog_against_terr(
    catalog: TextureCatalog,
    terr_path: str,
) -> dict:
    """
    Croise le catalogue avec les surfaces référencées dans le .terr du monde.

    Args:
        catalog: catalogue chargé
        terr_path: chemin vers le fichier .terr

    Returns:
        {
            "terr_materials": List[str],
            "missing": List[str],
            "coverage": float,  # % de surfaces couvertes
            "catalog_keys": List[str],  # Debug : clés du catalogue
        }
    """
    from reforger_texture_budget import parse_terr_materials

    # Nettoyer le chemin : retirer guillemets, espaces superflus
    terr_path = terr_path.strip().strip('"').strip("'")

    try:
        terr_materials = parse_terr_materials(terr_path)
    except Exception as e:
        return {
            "error": f"Impossible de lire {terr_path}: {e}",
            "terr_materials": [],
            "missing": [],
            "coverage": 0.0,
            "catalog_keys": [],
        }

    # Debug : récupérer les clés du catalogue
    catalog_keys = list(catalog.data.keys())

    # Vérifier présence dans catalogue
    # Essayer matching exact puis insensible à la casse
    missing = []
    for mat in terr_materials:
        # Exact match
        if catalog.get_entry(mat):
            continue

        # Insensible à la casse
        mat_lower = mat.lower()
        found = False
        for cat_key in catalog_keys:
            if cat_key.lower() == mat_lower:
                found = True
                break

        if not found:
            missing.append(mat)

    coverage = 0.0 if not terr_materials else (
        (len(terr_materials) - len(missing)) / len(terr_materials) * 100
    )

    return {
        "terr_materials": terr_materials,
        "missing": missing,
        "coverage": coverage,
        "catalog_keys": catalog_keys,  # Debug
    }


# ── Export rapport ───────────────────────────────────────────────────────────

def export_catalog_report(
    catalog: TextureCatalog,
    build_report: dict,
    terr_report: Optional[dict],
    output_path: Path,
) -> None:
    """
    Exporte un rapport texte du scan du catalogue.

    Args:
        catalog: catalogue construit
        build_report: rapport build_catalog()
        terr_report: rapport verify_catalog_against_terr() ou None
        output_path: fichier .txt de sortie
    """
    lines = []
    lines.append("=" * 80)
    lines.append("RAPPORT DE SCAN DU CATALOGUE DE TEXTURES REFORGER")
    lines.append("=" * 80)
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    lines.append("── RÉSUMÉ ──")
    lines.append(f"Total entrées:    {build_report['total']}")
    lines.append(f"  Vanilla:        {build_report['vanilla']}")
    lines.append(f"  Custom:         {build_report['custom']}")
    lines.append(f"  Convention zi_: {build_report['convention']}")
    lines.append(f"  Fallback:       {build_report['fallback']}")
    lines.append("")

    if build_report['zi_resolved']:
        lines.append(f"── ZI_ RÉSOLUS PAR CONVENTION ({len(build_report['zi_resolved'])}) ──")
        for name in sorted(build_report['zi_resolved']):
            entry = catalog.get_entry(name)
            parent = entry.get('parent', '???')
            lines.append(f"  {name} → {parent}")
        lines.append("")

    if build_report['fallback_list']:
        lines.append(f"── ENTRÉES EN FALLBACK (MAGENTA) ({len(build_report['fallback_list'])}) ──")
        for name in sorted(build_report['fallback_list']):
            lines.append(f"  {name}")
        lines.append("")

    if terr_report:
        lines.append("── CROISEMENT AVEC .TERR DU MONDE ──")
        if "error" in terr_report:
            lines.append(f"ERREUR: {terr_report['error']}")
        else:
            lines.append(f"Surfaces dans .terr:    {len(terr_report['terr_materials'])}")
            lines.append(f"Couverture catalogue:   {terr_report['coverage']:.1f}%")
            if terr_report['missing']:
                lines.append(f"\nSurfaces MANQUANTES dans le catalogue ({len(terr_report['missing'])}):")
                for mat in sorted(terr_report['missing']):
                    lines.append(f"  {mat}")
        lines.append("")

    lines.append("=" * 80)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
