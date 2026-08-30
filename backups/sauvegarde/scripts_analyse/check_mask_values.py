"""Vérification valeurs masques"""
import numpy as np
from PIL import Image
from pathlib import Path
import sys

masks_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/projects/Zbk_island/generated/terrain_masks")
mask_files = sorted(masks_dir.glob("*.png"))

print("="*60)
print("VERIFICATION VALEURS MASQUES")
print("="*60)

for mf in mask_files:
    img = Image.open(mf)
    arr = np.array(img, dtype=np.uint16)
    
    min_val = np.min(arr)
    max_val = np.max(arr)
    mean_val = np.mean(arr)
    unique_vals = len(np.unique(arr))
    active = np.sum(arr > 0)
    total = arr.size
    pct_active = (active / total) * 100
    
    print(f"\n{mf.name}")
    print(f"  Min: {min_val}  Max: {max_val}  Mean: {mean_val:.1f}")
    print(f"  Valeurs uniques: {unique_vals}")
    print(f"  Pixels actifs (>0): {active} ({pct_active:.2f}%)")
    
    if unique_vals <= 5:
        uniques = sorted(np.unique(arr))
        print(f"  Valeurs: {uniques}")
