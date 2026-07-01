"""
Script d'application automatique des corrections prioritaires
au fichier pipeline_phases_fixed.py
"""

import re
from pathlib import Path

# Lire fichier source
source_path = Path("pipeline_phases_fixed.py")
output_path = Path("pipeline_phases_corrected.py")

with open(source_path, 'r', encoding='utf-8') as f:
    content = f.read()

print("Application des corrections prioritaires...")

# ══════════════════════════════════════════════════════════════════════════
# CORRECTION 1 : Inverser logique dirt_erosion vs debris_rock
# ══════════════════════════════════════════════════════════════════════════

print("  [1] Inversion logique erosion (dirt=concave, debris=convexe)...")

# Chercher la section érosion et inverser les commentaires/logique
old_erosion = """        # dirt_erosion = pente modérée × convexe (érosion active)
        masks['09_dirt_erosion'] = moderate_slope_mask * np.clip(curv_factor, 0.0, 1.0)

        # debris_rock = pente modérée × concave (accumulation débris)
        masks['10_debris_rock'] = moderate_slope_mask * np.clip(-curv_factor, 0.0, 1.0)"""

new_erosion = """        # dirt_erosion = pente modérée × CONCAVE (talwegs/creux)
        masks['09_dirt_erosion'] = moderate_slope_mask * np.clip(-curv_factor, 0.0, 1.0)

        # debris_rock = pente modérée × CONVEXE (accumulation sur convexité)
        masks['10_debris_rock'] = moderate_slope_mask * np.clip(curv_factor, 0.0, 1.0)"""

if old_erosion in content:
    content = content.replace(old_erosion, new_erosion)
    print("    [OK] Logique erosion inversee")
else:
    print("    [WARNING] Section erosion non trouvee")

# ══════════════════════════════════════════════════════════════════════════
# CORRECTION 2 : Coastal 60m fixe (chercher coastal_distance_max_m)
# ══════════════════════════════════════════════════════════════════════════

print("  [2] Coastal distance fixe a 60m...")

# Remplacer coastal_distance_max = params['coastal_distance_max_m']
content = re.sub(
    r"coastal_distance_max = params\['coastal_distance_max_m'\]",
    "coastal_distance_max = 60.0  # FIXE (correction prioritaire)",
    content
)

print("    [OK] Coastal distance = 60m")

# ══════════════════════════════════════════════════════════════════════════
# Sauvegarder
# ══════════════════════════════════════════════════════════════════════════

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n[OK] Fichier corrige genere: {output_path}")
print("\nNOTE: Les corrections completes (zones, normalisation, verifications)")
print("      necessitent une refonte plus profonde de la fonction.")
print("\nPour une version complete, utiliser le template dans CORRECTIONS_PIPELINE.md")
