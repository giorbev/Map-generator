"""
Analyse error rock.png - Zimnitrita
Quel type d'erreur exactement ?
"""
import numpy as np
from PIL import Image
from pathlib import Path

error_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\terrain_masks\error rock.png")
rock_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\terrain_masks\10_rock_walls.png")

print("="*70)
print("ANALYSE error rock.png")
print("="*70)

# Ouvrir error mask
error_img = Image.open(error_path)
error_arr = np.array(error_img)

print(f"\nResolution    : {error_img.size[0]} x {error_img.size[1]} px")
print(f"Mode          : {error_img.mode}")
print(f"Array shape   : {error_arr.shape}")
print(f"Array dtype   : {error_arr.dtype}")

# Stats valeurs
print(f"\nValeurs:")
print(f"  Min         : {np.min(error_arr)}")
print(f"  Max         : {np.max(error_arr)}")
print(f"  Unique vals : {np.unique(error_arr)}")

# Coverage erreur
if error_arr.dtype == np.uint8:
    # Mode L (grayscale 8-bit)
    error_pixels = np.sum(error_arr > 128)
else:
    # Mode RGB ou autre
    if len(error_arr.shape) == 3:
        # RGB : prendre channel rouge
        error_pixels = np.sum(error_arr[:,:,0] > 128)
    else:
        error_pixels = np.sum(error_arr > 128)

total_pixels = error_arr.size if len(error_arr.shape) == 2 else error_arr.shape[0] * error_arr.shape[1]
error_pct = (error_pixels / total_pixels) * 100

print(f"\nCoverage erreur:")
print(f"  Pixels erreur : {error_pixels:,}")
print(f"  Total pixels  : {total_pixels:,}")
print(f"  % erreur      : {error_pct:.2f}%")

# Interpréter
print(f"\n{'='*70}")
print("INTERPRETATION")
print(f"{'='*70}")

if error_pct == 0:
    print("Masque d'erreur VIDE (noir complet)")
    print("-> Workbench a juste cree un placeholder vide")
    print("-> Erreur pas liee au contenu du masque Rock")
elif error_pct == 100:
    print("Masque d'erreur PLEIN (blanc complet)")
    print("-> Toute la zone Rock a ete rejetee")
    print("-> Erreur globale (format, resolution, saturation)")
elif error_pct < 5:
    print(f"Erreur LOCALISEE ({error_pct:.2f}% du terrain)")
    print("-> Quelques zones Rock problematiques")
    print("-> Probablement conflit local texture ou geometrie")
else:
    print(f"Erreur PARTIELLE ({error_pct:.2f}% du terrain)")
    print("-> Une partie significative du Rock a ete rejetee")
    print("-> Probleme structurel masque ou budget texture")

# Comparer resolutions
rock_img = Image.open(rock_path)
print(f"\n{'='*70}")
print("COMPARAISON RESOLUTIONS")
print(f"{'='*70}")
print(f"error rock.png  : {error_img.size[0]} x {error_img.size[1]} px")
print(f"10_rock_walls   : {rock_img.size[0]} x {rock_img.size[1]} px")

if error_img.size != rock_img.size:
    print("\nRESOLUTIONS DIFFERENTES !")
    print("-> error rock.png est une VERSION REDUITE")
    print("-> Workbench a downscale pour visualisation erreur")
else:
    print("\nMeme resolution (masque erreur = masque source)")

print("\n" + "="*70)
print("CONCLUSION")
print("="*70)

if error_pct == 0:
    print("Masque erreur vide = Workbench a refuse TOUT le masque Rock")
    print("\nCauses probables:")
    print("  1. Budget texture sature (9 masques avant = trop)")
    print("  2. Texture Rock_01 deja en base (doublon)")
    print("  3. Nom fichier problematique (10_rock_walls.png)")
    print("  4. Limite Workbench atteinte (rare mais possible)")
elif error_pct == 100:
    print("Erreur complete = probleme format ou saturation globale")
elif error_pct > 0:
    print(f"{error_pct:.1f}% erreur = probleme partiel")
    print("Certaines zones Rock acceptees, d'autres rejetees")

print("\nProchaine etape: Verifier texture base Workbench")
print("="*70)
