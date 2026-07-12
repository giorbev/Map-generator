"""
BCR Mixer - Mélange de 2 BaseColor+Roughness maps pour Arma Reforger

Permet de créer un BCR qui combine :
- Roche (base)
- Dirt/Mousse/Lichen (overlay)

Selon différentes méthodes de blend.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Literal
from PIL import Image
import struct
import lz4.block

# Importer les fonctions du decoder existant
from edds_decoder import (
    decode_edds_texture,
    compress_lz4_chained,
    decompress_lz4_chained
)


BlendMode = Literal['alpha', 'mask', 'height', 'multiply', 'overlay', 'mix']


class BCRTexture:
    """
    Représente une texture BCR décodée

    Attributes:
        basecolor: (H, W, 3) float32 [0, 1] - RGB
        roughness: (H, W) float32 [0, 1] - Alpha
    """

    def __init__(self, basecolor: np.ndarray, roughness: np.ndarray):
        self.basecolor = basecolor  # RGB float32 [0, 1]
        self.roughness = roughness  # Alpha float32 [0, 1]
        self.height, self.width = basecolor.shape[:2]

    @classmethod
    def from_edds(cls, edds_path: Path) -> Optional['BCRTexture']:
        """
        Charge un BCR depuis un fichier EDDS
        """
        bcr_data = decode_edds_texture(edds_path, target_mip=0)

        if bcr_data is None:
            print(f"❌ Échec lecture {edds_path.name}")
            return None

        if bcr_data.ndim != 3 or bcr_data.shape[2] not in [3, 4]:
            print(f"❌ Format invalide : {bcr_data.shape}")
            return None

        # Extraire RGB
        basecolor = bcr_data[:, :, :3].astype(np.float32) / 255.0

        # Extraire Alpha (Roughness)
        if bcr_data.shape[2] == 4:
            roughness = bcr_data[:, :, 3].astype(np.float32) / 255.0
        else:
            # Pas d'alpha, créer un roughness par défaut
            roughness = np.ones((basecolor.shape[0], basecolor.shape[1]), dtype=np.float32) * 0.5
            print(f"⚠️  Pas de canal alpha, roughness = 0.5 par défaut")

        print(f"✅ BCR chargé : {basecolor.shape[:2]}, roughness {roughness.shape}")

        return cls(basecolor, roughness)

    @classmethod
    def from_png(cls, color_path: Path, roughness_path: Optional[Path] = None) -> Optional['BCRTexture']:
        """
        Charge un BCR depuis des fichiers PNG séparés

        Args:
            color_path: Chemin vers BaseColor RGB
            roughness_path: (Optionnel) Chemin vers Roughness grayscale
        """
        # Charger color
        try:
            color_img = Image.open(color_path).convert('RGB')
            basecolor = np.array(color_img).astype(np.float32) / 255.0
            print(f"✅ Color chargé : {basecolor.shape}")
        except Exception as e:
            print(f"❌ Erreur chargement color : {e}")
            return None

        # Charger roughness
        if roughness_path and roughness_path.exists():
            try:
                rough_img = Image.open(roughness_path).convert('L')
                roughness = np.array(rough_img).astype(np.float32) / 255.0
                print(f"✅ Roughness chargé : {roughness.shape}")
            except Exception as e:
                print(f"❌ Erreur chargement roughness : {e}")
                return None
        else:
            # Roughness par défaut
            roughness = np.ones((basecolor.shape[0], basecolor.shape[1]), dtype=np.float32) * 0.5
            print(f"⚠️  Roughness par défaut (0.5)")

        return cls(basecolor, roughness)

    def to_rgba(self) -> np.ndarray:
        """
        Convertit en RGBA uint8 (RGB + Roughness dans Alpha)

        Returns:
            (H, W, 4) uint8
        """
        rgba = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        rgba[:, :, :3] = (self.basecolor * 255).astype(np.uint8)
        rgba[:, :, 3] = (self.roughness * 255).astype(np.uint8)
        return rgba

    def save_png(self, color_path: Path, roughness_path: Optional[Path] = None):
        """
        Sauvegarde en PNG séparés
        """
        # Sauvegarder color
        color_uint8 = (self.basecolor * 255).astype(np.uint8)
        color_img = Image.fromarray(color_uint8, mode='RGB')
        color_img.save(color_path)
        print(f"💾 Color sauvegardé : {color_path}")

        # Sauvegarder roughness
        if roughness_path:
            rough_uint8 = (self.roughness * 255).astype(np.uint8)
            rough_img = Image.fromarray(rough_uint8, mode='L')
            rough_img.save(roughness_path)
            print(f"💾 Roughness sauvegardé : {roughness_path}")

    def save_edds(self, edds_path: Path) -> bool:
        """
        Sauvegarde en format EDDS

        Note : Nécessite d'implémenter l'encodeur EDDS complet
        Pour l'instant, sauvegarde en DDS standard non-compressé
        """
        # Convertir en RGBA uint8
        rgba = self.to_rgba()

        # Créer header DDS
        header = create_dds_header(self.width, self.height, mipcount=1, format_rgba8=True)

        # Écrire fichier
        try:
            with open(edds_path, 'wb') as f:
                f.write(header)
                f.write(rgba.tobytes())
            print(f"💾 BCR sauvegardé (DDS) : {edds_path}")
            return True
        except Exception as e:
            print(f"❌ Erreur sauvegarde : {e}")
            return False


def create_dds_header(width: int, height: int, mipcount: int = 1, format_rgba8: bool = True) -> bytes:
    """
    Crée un header DDS basique (128 bytes)
    """
    header = bytearray(128)

    # Magic "DDS "
    header[0:4] = b'DDS '

    # Size (toujours 124)
    struct.pack_into('<I', header, 4, 124)

    # Flags
    struct.pack_into('<I', header, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000)

    # Height, Width
    struct.pack_into('<I', header, 12, height)
    struct.pack_into('<I', header, 16, width)

    # Pitch (RGBA8 = 4 bytes par pixel)
    struct.pack_into('<I', header, 20, width * 4)

    # Depth
    struct.pack_into('<I', header, 24, 1)

    # MipMapCount
    struct.pack_into('<I', header, 28, mipcount)

    # PixelFormat (offset 76, 32 bytes)
    struct.pack_into('<I', header, 76, 32)  # Size

    if format_rgba8:
        # RGBA8
        struct.pack_into('<I', header, 80, 0x00000041)  # DDPF_RGB | DDPF_ALPHAPIXELS
        struct.pack_into('<I', header, 84, 0)  # FourCC (vide pour RGB)
        struct.pack_into('<I', header, 88, 32)  # RGBBitCount
        struct.pack_into('<I', header, 92, 0x000000FF)  # RBitMask
        struct.pack_into('<I', header, 96, 0x0000FF00)  # GBitMask
        struct.pack_into('<I', header, 100, 0x00FF0000)  # BBitMask
        struct.pack_into('<I', header, 104, 0xFF000000)  # ABitMask

    # Caps
    struct.pack_into('<I', header, 108, 0x1000)

    return bytes(header)


# ============================================================================
# FONCTIONS DE BLEND
# ============================================================================

def blend_alpha(base: BCRTexture, overlay: BCRTexture, alpha: float = 0.5) -> BCRTexture:
    """
    Blend simple avec alpha constant

    result = base * (1-alpha) + overlay * alpha

    Args:
        base: Texture de base (roche)
        overlay: Texture overlay (dirt/mousse)
        alpha: Opacité overlay [0, 1] (0=base only, 1=overlay only)
    """
    # Vérifier dimensions
    if base.basecolor.shape != overlay.basecolor.shape:
        print(f"❌ Dimensions incompatibles : {base.basecolor.shape} vs {overlay.basecolor.shape}")
        return base

    # Blend basecolor
    blended_color = base.basecolor * (1 - alpha) + overlay.basecolor * alpha

    # Blend roughness
    blended_rough = base.roughness * (1 - alpha) + overlay.roughness * alpha

    print(f"✅ Blend alpha={alpha}")

    return BCRTexture(blended_color, blended_rough)


def blend_mask(base: BCRTexture, overlay: BCRTexture, mask: np.ndarray) -> BCRTexture:
    """
    Blend avec masque spatial

    result = base * (1-mask) + overlay * mask

    Args:
        base: Texture de base (roche)
        overlay: Texture overlay (dirt/mousse)
        mask: (H, W) float32 [0, 1] - 0=base, 1=overlay
    """
    # Vérifier dimensions
    if base.basecolor.shape[:2] != mask.shape:
        print(f"❌ Dimensions mask incompatibles : {base.basecolor.shape[:2]} vs {mask.shape}")
        return base

    # Broadcast mask pour RGB
    mask_rgb = mask[:, :, np.newaxis]

    # Blend basecolor
    blended_color = base.basecolor * (1 - mask_rgb) + overlay.basecolor * mask_rgb

    # Blend roughness
    blended_rough = base.roughness * (1 - mask) + overlay.roughness * mask

    print(f"✅ Blend mask (usage overlay : {(mask > 0.5).sum() / mask.size * 100:.1f}%)")

    return BCRTexture(blended_color, blended_rough)


def blend_height(base: BCRTexture, overlay: BCRTexture,
                 base_height: np.ndarray, overlay_height: np.ndarray,
                 contrast: float = 0.5) -> BCRTexture:
    """
    Blend basé sur heightmap (comme terrain)

    Les pixels les plus hauts de chaque texture "gagnent"

    Args:
        base: Texture de base
        overlay: Texture overlay
        base_height: (H, W) float32 [0, 1] - hauteur relative base
        overlay_height: (H, W) float32 [0, 1] - hauteur relative overlay
        contrast: Contraste du blend [0, 1] (0=soft, 1=hard)
    """
    # Calculer différence de hauteur
    height_diff = overlay_height - base_height

    # Convertir en masque avec contraste
    # Sigmoid : 1 / (1 + exp(-k * x))
    k = 10 * (contrast + 0.1)  # Facteur de contraste
    mask = 1.0 / (1.0 + np.exp(-k * height_diff))

    # Utiliser blend_mask
    return blend_mask(base, overlay, mask)


def blend_multiply(base: BCRTexture, overlay: BCRTexture, strength: float = 1.0) -> BCRTexture:
    """
    Blend multiplicatif (darkening)

    result_color = base * overlay
    result_rough = base + overlay * strength

    Utile pour appliquer saleté/AO
    """
    # Multiply basecolor
    blended_color = base.basecolor * overlay.basecolor

    # Additive roughness (dirt adds roughness)
    blended_rough = np.clip(base.roughness + overlay.roughness * strength, 0, 1)

    print(f"✅ Blend multiply (strength={strength})")

    return BCRTexture(blended_color, blended_rough)


def blend_overlay_photoshop(base: BCRTexture, overlay: BCRTexture, opacity: float = 0.5) -> BCRTexture:
    """
    Blend mode "Overlay" de Photoshop

    Si base < 0.5 : result = 2 * base * overlay
    Si base >= 0.5 : result = 1 - 2 * (1-base) * (1-overlay)
    """
    # Calculer overlay pour chaque canal
    mask_dark = base.basecolor < 0.5

    blended_color = np.where(
        mask_dark,
        2 * base.basecolor * overlay.basecolor,
        1 - 2 * (1 - base.basecolor) * (1 - overlay.basecolor)
    )

    # Mix avec opacity
    blended_color = base.basecolor * (1 - opacity) + blended_color * opacity

    # Roughness simple blend
    blended_rough = base.roughness * (1 - opacity) + overlay.roughness * opacity

    print(f"✅ Blend overlay mode (opacity={opacity})")

    return BCRTexture(blended_color, blended_rough)


def generate_dirt_mask(width: int, height: int,
                       density: float = 0.3,
                       noise_scale: float = 10.0,
                       seed: int = 42) -> np.ndarray:
    """
    Génère un masque procédural pour dirt/mousse

    Utilise Perlin noise ou simplex noise

    Args:
        width, height: Dimensions
        density: Densité générale [0, 1] (0=aucun, 1=partout)
        noise_scale: Échelle du bruit (petit=gros blobs, grand=détails fins)
        seed: Seed aléatoire

    Returns:
        (H, W) float32 [0, 1]
    """
    # Pour simplicité, utiliser du bruit aléatoire simple
    # Dans un vrai cas, utiliser opensimplex ou perlin

    np.random.seed(seed)

    # Générer bruit de base
    noise = np.random.rand(height, width).astype(np.float32)

    # Appliquer blur pour smoother (simulation de Perlin grossier)
    from scipy.ndimage import gaussian_filter
    noise = gaussian_filter(noise, sigma=noise_scale)

    # Normaliser [0, 1]
    noise = (noise - noise.min()) / (noise.max() - noise.min())

    # Appliquer densité (threshold + remapping)
    threshold = 1.0 - density
    mask = np.clip((noise - threshold) / (1.0 - threshold), 0, 1)

    print(f"✅ Masque dirt généré : {mask.shape}, couverture={mask.mean():.1%}")

    return mask


# ============================================================================
# EXEMPLES D'UTILISATION
# ============================================================================

def example_simple_blend():
    """
    Exemple 1 : Blend simple alpha 50/50
    """
    print("\n" + "="*70)
    print("EXEMPLE 1 : Blend Simple Alpha 50/50")
    print("="*70)

    base_dir = Path(r"H:\mod_enfusion\Arma Reforger_copie\addons\data\data003\Assets\Rocks\Granite\Data")

    # Charger base (roche)
    base_bcr = BCRTexture.from_edds(base_dir / "Granite_01_BCR.edds")

    # Charger overlay (mousse)
    overlay_bcr = BCRTexture.from_edds(base_dir / "Granite_moss_02_BCR.edds")

    if base_bcr and overlay_bcr:
        # Blend 50/50
        result = blend_alpha(base_bcr, overlay_bcr, alpha=0.5)

        # Sauvegarder
        result.save_png(
            Path("output_mixed_alpha50.png"),
            Path("output_mixed_alpha50_roughness.png")
        )

        print("\n✅ Résultat sauvegardé")


def example_mask_blend():
    """
    Exemple 2 : Blend avec masque procédural
    """
    print("\n" + "="*70)
    print("EXEMPLE 2 : Blend avec Masque Procédural")
    print("="*70)

    base_dir = Path(r"H:\mod_enfusion\Arma Reforger_copie\addons\data\data003\Assets\Rocks\Granite\Data")

    # Charger textures
    base_bcr = BCRTexture.from_edds(base_dir / "Granite_01_BCR.edds")
    overlay_bcr = BCRTexture.from_edds(base_dir / "Granite_moss_02_BCR.edds")

    if base_bcr and overlay_bcr:
        # Générer masque procédural
        mask = generate_dirt_mask(
            base_bcr.width,
            base_bcr.height,
            density=0.4,      # 40% couvert de mousse
            noise_scale=15.0, # Blobs de taille moyenne
            seed=123
        )

        # Sauvegarder masque
        mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode='L')
        mask_img.save("output_dirt_mask.png")
        print("💾 Masque sauvegardé")

        # Blend avec masque
        result = blend_mask(base_bcr, overlay_bcr, mask)

        # Sauvegarder résultat
        result.save_png(
            Path("output_mixed_mask.png"),
            Path("output_mixed_mask_roughness.png")
        )

        print("\n✅ Résultat avec masque sauvegardé")


def example_multiply_ao():
    """
    Exemple 3 : Appliquer AO multiplicatif (darkening)
    """
    print("\n" + "="*70)
    print("EXEMPLE 3 : Application AO Multiplicatif")
    print("="*70)

    base_dir = Path(r"H:\mod_enfusion\Arma Reforger_copie\addons\data\data003\Assets\Rocks\Granite\Data")

    # Charger base
    base_bcr = BCRTexture.from_edds(base_dir / "Granite_01_BCR.edds")

    if not base_bcr:
        return

    # Charger MCR pour extraire AO
    from edds_decoder import decode_edds_texture

    mcr_data = decode_edds_texture(base_dir / "GraniteCliff_01_MCR.edds", target_mip=0)

    if mcr_data is not None and mcr_data.ndim == 3:
        # Canal B = AO (selon observation)
        ao = mcr_data[:, :, 2].astype(np.float32) / 255.0

        # Créer BCR "fake" pour multiply (AO en RGB, roughness 0)
        ao_rgb = np.stack([ao, ao, ao], axis=-1)
        ao_bcr = BCRTexture(ao_rgb, np.zeros_like(ao))

        # Multiply
        result = blend_multiply(base_bcr, ao_bcr, strength=0.5)

        # Sauvegarder
        result.save_png(
            Path("output_with_ao.png"),
            Path("output_with_ao_roughness.png")
        )

        print("\n✅ AO appliqué et sauvegardé")


def example_custom_from_png():
    """
    Exemple 4 : Créer un BCR custom depuis vos propres PNG
    """
    print("\n" + "="*70)
    print("EXEMPLE 4 : Créer BCR Custom depuis PNG")
    print("="*70)

    # Supposons que vous avez :
    # - rock_color.png (RGB)
    # - rock_roughness.png (Grayscale)
    # - moss_color.png (RGB)
    # - moss_roughness.png (Grayscale)

    # Pour la démo, utiliser les BCR existants
    base_dir = Path(r"H:\mod_enfusion\Arma Reforger_copie\addons\data\data003\Assets\Rocks\Granite\Data")

    base_bcr = BCRTexture.from_edds(base_dir / "Granite_01_BCR.edds")
    overlay_bcr = BCRTexture.from_edds(base_dir / "Granite_moss_02_BCR.edds")

    if base_bcr and overlay_bcr:
        # Exporter en PNG pour édition externe
        base_bcr.save_png(
            Path("temp_rock_color.png"),
            Path("temp_rock_roughness.png")
        )

        overlay_bcr.save_png(
            Path("temp_moss_color.png"),
            Path("temp_moss_roughness.png")
        )

        print("\n💡 Vous pouvez maintenant éditer ces PNG dans Photoshop/GIMP")
        print("💡 Puis les recharger avec BCRTexture.from_png()")

        # Exemple de rechargement
        # edited_base = BCRTexture.from_png(
        #     Path("edited_rock_color.png"),
        #     Path("edited_rock_roughness.png")
        # )


def example_height_blend():
    """
    Exemple 5 : Blend basé sur heightmap (avancé)
    """
    print("\n" + "="*70)
    print("EXEMPLE 5 : Blend Height-Based")
    print("="*70)

    base_dir = Path(r"H:\mod_enfusion\Arma Reforger_copie\addons\data\data003\Assets\Rocks\Granite\Data")

    base_bcr = BCRTexture.from_edds(base_dir / "Granite_01_BCR.edds")
    overlay_bcr = BCRTexture.from_edds(base_dir / "Granite_moss_02_BCR.edds")

    if base_bcr and overlay_bcr:
        # Simuler heightmaps depuis roughness (approximation)
        # Dans un vrai cas, utiliser de vraies height maps
        base_height = 1.0 - base_bcr.roughness  # Plus lisse = plus haut
        overlay_height = overlay_bcr.roughness * 0.5  # Mousse plus basse

        # Blend
        result = blend_height(
            base_bcr,
            overlay_bcr,
            base_height,
            overlay_height,
            contrast=0.7
        )

        # Sauvegarder
        result.save_png(
            Path("output_height_blend.png"),
            Path("output_height_blend_roughness.png")
        )

        print("\n✅ Height blend sauvegardé")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys

    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    BCR MIXER - Arma Reforger                         ║
║                  Mélange de BaseColor+Roughness                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    # Vérifier que scipy est disponible (pour gaussian_filter)
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError:
        print("⚠️  scipy non installé, certaines fonctions seront limitées")
        print("   Installer avec : pip install scipy")

    # Menu
    print("\nExemples disponibles :")
    print("  1. Blend simple alpha 50/50")
    print("  2. Blend avec masque procédural")
    print("  3. Application AO multiplicatif")
    print("  4. Créer BCR custom depuis PNG")
    print("  5. Blend height-based (avancé)")
    print("  0. Tous les exemples")

    choice = input("\nChoisir un exemple (0-5) : ").strip()

    if choice == '1':
        example_simple_blend()
    elif choice == '2':
        example_mask_blend()
    elif choice == '3':
        example_multiply_ao()
    elif choice == '4':
        example_custom_from_png()
    elif choice == '5':
        example_height_blend()
    elif choice == '0':
        example_simple_blend()
        example_mask_blend()
        example_multiply_ao()
        example_custom_from_png()
        example_height_blend()
    else:
        print("❌ Choix invalide")
        sys.exit(1)

    print("\n" + "="*70)
    print("✅ Terminé !")
    print("="*70)
