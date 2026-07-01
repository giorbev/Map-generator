import cv2
import numpy as np

# Charger masques
rock = cv2.imread(r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks\mask_16_Rock_01.png", cv2.IMREAD_UNCHANGED)
slope = cv2.imread(r"h:\logiciel perso\Map generator\data\projects\Zbk_island\sources\slope.png", cv2.IMREAD_UNCHANGED)

# Resize slope à la taille de rock si nécessaire
if slope.shape != rock.shape:
    slope = cv2.resize(slope, (rock.shape[1], rock.shape[0]), interpolation=cv2.INTER_LINEAR)

# Normaliser slope 0-90°
if slope.dtype == np.uint16:
    slope_deg = slope.astype(np.float32) / 65535.0 * 90.0
else:
    slope_deg = slope.astype(np.float32) / 255.0 * 90.0

# Trouver pixels avec Rock > 10% (6553 en 16-bit)
rock_mask = rock > 6553

print(f"ANALYSE PENTES SURFACES ROCHEUSES (ZBK)")
print(f"=" * 60)
print(f"\nPixels avec Rock > 10% : {np.sum(rock_mask):,} ({np.sum(rock_mask)/rock.size*100:.1f}% de la carte)")

if np.sum(rock_mask) > 0:
    # Pentes des zones rocheuses
    rock_slopes = slope_deg[rock_mask]

    print(f"\nSTATISTIQUES PENTES (degrés) :")
    print(f"  Min        : {rock_slopes.min():.1f}°")
    print(f"  Max        : {rock_slopes.max():.1f}°")
    print(f"  Moyenne    : {rock_slopes.mean():.1f}°")
    print(f"  Médiane    : {np.median(rock_slopes):.1f}°")
    print(f"  P25        : {np.percentile(rock_slopes, 25):.1f}°")
    print(f"  P75        : {np.percentile(rock_slopes, 75):.1f}°")
    print(f"  P90        : {np.percentile(rock_slopes, 90):.1f}°")
    print(f"  P95        : {np.percentile(rock_slopes, 95):.1f}°")

    # Distribution par tranches
    print(f"\nDISTRIBUTION PAR TRANCHES :")
    ranges = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 90)]
    for min_s, max_s in ranges:
        count = np.sum((rock_slopes >= min_s) & (rock_slopes < max_s))
        pct = count / len(rock_slopes) * 100
        print(f"  {min_s:2d}° - {max_s:2d}° : {count:8,} pixels ({pct:5.1f}%)")

    # Comparer avec seuils actuels
    print(f"\nCOMPARAISON AVEC SEUILS ACTUELS :")
    print(f"  steep >= 30° (seuil actuel) : {np.sum(rock_slopes >= 30):,} pixels ({np.sum(rock_slopes >= 30)/len(rock_slopes)*100:.1f}%)")
    print(f"  moderate 20-30°             : {np.sum((rock_slopes >= 20) & (rock_slopes < 30)):,} pixels ({np.sum((rock_slopes >= 20) & (rock_slopes < 30))/len(rock_slopes)*100:.1f}%)")
    print(f"  gentle 9-20°                : {np.sum((rock_slopes >= 9) & (rock_slopes < 20)):,} pixels ({np.sum((rock_slopes >= 9) & (rock_slopes < 20))/len(rock_slopes)*100:.1f}%)")
    print(f"  flat < 9°                   : {np.sum(rock_slopes < 9):,} pixels ({np.sum(rock_slopes < 9)/len(rock_slopes)*100:.1f}%)")

    # Recommandation seuil
    print(f"\nRECOMMANDATION :")
    p50 = np.percentile(rock_slopes, 50)
    if p50 < 25:
        print(f"  La pente médiane des roches est {p50:.1f}° (< 25°)")
        print(f"  -> Le seuil steep >= 30° est TROP ÉLEVÉ")
        print(f"  -> Recommandation : steep >= {p50-5:.0f}° pour couvrir 75% des roches")
    else:
        print(f"  La pente médiane des roches est {p50:.1f}° (>= 25°)")
        print(f"  -> Le seuil steep >= 30° est correct")
else:
    print("\nAucun pixel avec Rock > 10%")
