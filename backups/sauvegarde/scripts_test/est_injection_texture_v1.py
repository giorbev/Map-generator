import numpy as np
import os

# --- CHEMIN ABSOLU DIRECT ---
DOSSIER_EDITORDATA = r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData"
NOM_FICHIER = "Terrain_449_layer.dds"
chemin_complet_dds = os.path.join(DOSSIER_EDITORDATA, NOM_FICHIER)

# --- CONFIGURATION DU BLOC CIBLE ---
# Coordonnées GLOBALES du bloc (depuis l'analyseur)
BLOCK_GLOBAL_X, BLOCK_GLOBAL_Y = 7, 57

# Calcul des coordonnées LOCALES dans la tuile (0-3)
BLOCKS_PER_TILE = 4
BLOCK_LOCAL_X = BLOCK_GLOBAL_X % BLOCKS_PER_TILE
BLOCK_LOCAL_Y = BLOCK_GLOBAL_Y % BLOCKS_PER_TILE

# Calcul de la position pixel du bloc (128×128)
BLOCK_SIZE = 128
X_START = BLOCK_LOCAL_X * BLOCK_SIZE
Y_START = BLOCK_LOCAL_Y * BLOCK_SIZE

print("================================================================")
print(f"🔧 TEST REMPLACEMENT TEXTURE : BLOC GLOBAL [{BLOCK_GLOBAL_X},{BLOCK_GLOBAL_Y}]")
print("================================================================")
print(f"🔍 Fichier cible : {chemin_complet_dds}")
print(f"📍 Bloc local dans tuile : [{BLOCK_LOCAL_X},{BLOCK_LOCAL_Y}]")
print(f"📐 Position pixel : X={X_START}, Y={Y_START} (bloc {BLOCK_SIZE}×{BLOCK_SIZE})")
print(f"🔄 Action : MountainGrass_01 (L0) → Debris_Rock_01 (L1)")
print("================================================================")

if not os.path.exists(chemin_complet_dds):
    print(f"❌ Erreur : Le fichier '{NOM_FICHIER}' est introuvable à cet endroit.")
    print("Vérifie que tu as bien généré ou sauvegardé cette tuile au moins une fois via l'UI.")
    exit()

# --- SPÉCIFICATIONS ENFUSION DU CALQUE ---
HEADER_SIZE = 148
WIDTH, HEIGHT = 512, 512
MIPMAP0_SIZE = WIDTH * HEIGHT * 4  # 512×512 pixels × 4 octets (uint32) = 1 048 576 octets

# 1. Lecture binaire du fichier officiel
with open(chemin_complet_dds, "rb") as f:
    header = f.read(HEADER_SIZE)
    raw_mipmap0 = f.read(MIPMAP0_SIZE)  # Lire uniquement le mipmap principal
    raw_mipmaps_rest = f.read()  # Lire le reste (mipmaps 1-9)

# 2. Conversion en matrice NumPy 32-bits (Lignes, Colonnes)
pixel_matrix = np.frombuffer(raw_mipmap0, dtype=np.uint32).copy()
pixel_matrix = pixel_matrix.reshape((HEIGHT, WIDTH))

# 3. Sauvegarde automatique de sécurité (Back-up)
chemin_backup = chemin_complet_dds + ".backup"
if not os.path.exists(chemin_backup):
    with open(chemin_backup, "wb") as f:
        f.write(header + raw_mipmap0 + raw_mipmaps_rest)
    print(f"💾 Sauvegarde originale créée avec succès : {NOM_FICHIER}.backup")
else:
    print("ℹ️ Note : Un fichier de sauvegarde (.backup) existe déjà, l'original est à l'abri.")

# 4. INJECTION BINAIRE : FORCER L0 À 100%
# Pour obtenir w0 = 31, on met tous les autres poids (w1-w6) à 0
# w0 = 31 - (w1 + w2 + ... + w6) = 31 - 0 = 31
VALEUR_RESET = 0  # Tous les poids explicites à 0 → w0 = 31

# Injection sur tout le bloc 128×128 (Format NumPy : [Y_Lignes, X_Colonnes])
pixel_matrix[Y_START : Y_START + BLOCK_SIZE, X_START : X_START + BLOCK_SIZE] = VALEUR_RESET

# 5. RÉ-ÉCRITURE SUR LE FICHIER DIRECTEMENT LU PAR LE WORKBENCH
with open(chemin_complet_dds, "wb") as f:
    f.write(header)                   # Injection du header d'origine de 148 octets
    f.write(pixel_matrix.tobytes())   # Injection du mipmap 0 modifié
    f.write(raw_mipmaps_rest)         # Préservation des mipmaps 1-9

print("================================================================")
print(f"✅ Injection binaire terminée avec succès !")
print(f"📦 Bloc {BLOCK_SIZE}×{BLOCK_SIZE} pixels modifié")
print(f"📍 Position : X={X_START}, Y={Y_START}")
print(f"")
print(f"👉 PROCHAINE ÉTAPE :")
print(f"   1. Ouvre le World Editor")
print(f"   2. Charge la tuile 449")
print(f"   3. Vérifie que le bloc [{BLOCK_GLOBAL_X},{BLOCK_GLOBAL_Y}] affiche")
print(f"      Debris_Rock_01 au lieu de MountainGrass_01 !")
print("================================================================")
