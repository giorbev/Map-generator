"""
mask_utils.py — Utilitaires traitement masques terrain
"""
import numpy as np
import cv2
from pathlib import Path


def convert_float32_to_uint16(input_path, output_path=None):
    """Convertit une image float32 en uint16 PNG normalisé."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise ValueError(f"Fichier introuvable: {input_path}")

    try:
        img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            img_bytes = np.fromfile(str(input_path), dtype=np.uint8)
            img = cv2.imdecode(img_bytes, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Impossible de lire: {input_path}")
    except Exception as exc:
        raise ValueError(f"Erreur de lecture: {exc}")

    # Déjà en uint16 ou uint8 → retour direct sans conversion
    if img.dtype != np.float32:
        print(f"[INFO] {input_path.name} déjà en {img.dtype}, retour direct")
        return img, str(input_path)

    # RGB/RGBA → niveaux de gris
    if img.ndim == 3:
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError(f"Format non supporté: {img.shape[2]} canaux")

    # Normalisation float32 → uint16
    img_min, img_max = float(np.min(img)), float(np.max(img))
    if img_max > img_min:
        img_normalized = (img - img_min) / (img_max - img_min)
    else:
        img_normalized = np.zeros_like(img)

    img_uint16 = np.clip(np.round(img_normalized * 65535.0), 0, 65535).astype(np.uint16)

    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_uint16.png"
    else:
        output_path = Path(output_path)

    ok = cv2.imwrite(str(output_path), img_uint16)
    if not ok:
        raise ValueError(f"Impossible d'écrire: {output_path}")

    print(f"[OK] {input_path.name} → {output_path.name} | plage [{img_min:.4f}, {img_max:.4f}]")
    return img_uint16, str(output_path)


def scan_gaea_folder(gaea_dir: Path) -> dict:
    """
    Scanne le dossier gaea/ et retourne les PNG disponibles.
    Convertit automatiquement les float32 en uint16.

    Returns:
        dict: {
            "png_files": [str, ...],   # noms des fichiers PNG
            "converted": [str, ...],   # fichiers convertis depuis float32
            "errors": [str, ...]       # erreurs éventuelles
        }
    """
    if not gaea_dir.exists():
        return {"png_files": [], "converted": [], "errors": []}

    png_files = sorted(gaea_dir.glob("*.png")) + sorted(gaea_dir.glob("*.tif"))
    result = {"png_files": [], "converted": [], "errors": []}

    for f in png_files:
        try:
            img_check = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
            if img_check is not None and img_check.dtype == np.float32:
                # Conversion automatique
                _, out_path = convert_float32_to_uint16(f)
                result["converted"].append(f.name)
                result["png_files"].append(Path(out_path).name)
            else:
                result["png_files"].append(f.name)
        except Exception as e:
            result["errors"].append(f"{f.name}: {e}")

    return result


# Profils de traitement pour chaque type de masque
MASK_PROFILES = {
    "slope": {
        "description": "Masque de pente (roche)",
        "invert": False,
        "apply_slope_ramp": True,
        "apply_exclusion": True,
        "blur": True,
    },
    "flow": {
        "description": "Masque de flow (érosion/talwegs)",
        "invert": False,
        "apply_slope_ramp": False,
        "apply_exclusion": True,
        "blur": True,
    },
    "deposit": {
        "description": "Masque de dépôt (alluvions)",
        "invert": False,
        "apply_slope_ramp": False,
        "apply_exclusion": True,
        "blur": True,
    },
}


def load_and_normalize_mask(mask_path: Path, target_size: tuple) -> np.ndarray:
    """
    Charge un masque et le normalise en float32 [0, 1].

    Args:
        mask_path: Chemin vers le fichier masque
        target_size: Tuple (width, height) pour le redimensionnement

    Returns:
        Masque normalisé en float32 [0, 1]
    """
    if not mask_path.exists():
        raise FileNotFoundError(f"Masque introuvable : {mask_path}")

    # Charger l'image
    img = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Impossible de charger : {mask_path}")

    # Convertir en grayscale si nécessaire
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Redimensionner
    if img.shape[:2] != target_size:
        img = cv2.resize(img, target_size, interpolation=cv2.INTER_LINEAR)

    # Normaliser en float32 [0, 1]
    if img.dtype == np.uint16:
        img_f = img.astype(np.float32) / 65535.0
    elif img.dtype == np.uint8:
        img_f = img.astype(np.float32) / 255.0
    elif img.dtype == np.float32:
        # Déjà float, normaliser par min/max
        img_min, img_max = img.min(), img.max()
        if img_max > img_min:
            img_f = (img - img_min) / (img_max - img_min)
        else:
            img_f = np.zeros_like(img, dtype=np.float32)
    else:
        raise ValueError(f"Type non supporté : {img.dtype}")

    return img_f


def apply_mask_profile(
    mask: np.ndarray,
    mask_type: str = "slope",
    slope_ramp: np.ndarray = None,
    excl_mask: np.ndarray = None,
    blur_radius: int = 8
) -> np.ndarray:
    """
    Applique un profil de traitement à un masque selon son type.

    Args:
        mask: Masque float32 [0, 1]
        mask_type: Type de masque ("slope", "flow", "deposit")
        slope_ramp: Rampe de pente optionnelle (pour type "slope")
        excl_mask: Masque d'exclusion optionnel (1=actif, 0=protégé)
        blur_radius: Rayon du blur en pixels

    Returns:
        Masque traité float32 [0, 1]
    """
    if mask_type not in MASK_PROFILES:
        raise ValueError(f"Type de masque inconnu : {mask_type}")

    profile = MASK_PROFILES[mask_type]
    result = mask.copy()

    # Inversion si nécessaire
    if profile.get("invert"):
        result = 1.0 - result

    # Application de la rampe de pente (uniquement pour slope)
    if profile.get("apply_slope_ramp") and slope_ramp is not None:
        result = result * slope_ramp

    # Application du masque d'exclusion
    if profile.get("apply_exclusion") and excl_mask is not None:
        result = result * excl_mask

    # Blur
    if profile.get("blur") and blur_radius > 0:
        kernel_size = blur_radius * 2 + 1
        result = cv2.GaussianBlur(result, (kernel_size, kernel_size), 0)

    # Clip pour sécurité
    result = np.clip(result, 0.0, 1.0)

    return result
