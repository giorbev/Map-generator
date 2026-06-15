import cv2
import numpy as np

# Charger masque slope
slope = cv2.imread(r"h:\logiciel perso\Map generator\data\projects\Zbk_island\sources\slope.png", cv2.IMREAD_UNCHANGED)

# Normaliser slope 0-90°
if slope.dtype == np.uint16:
    slope_deg = slope.astype(np.float32) / 65535.0 * 90.0
else:
    slope_deg = slope.astype(np.float32) / 255.0 * 90.0

print(f"STATISTIQUES PENTES GLOBALES - ZBK ISLAND")
print(f"=" * 70)
print(f"\nTaille carte : {slope.shape[1]} x {slope.shape[0]} px")
print(f"Total pixels : {slope.size:,}")

print(f"\nSTATISTIQUES (degres) :")
print(f"  Min        : {slope_deg.min():.2f}°")
print(f"  Max        : {slope_deg.max():.2f}°")
print(f"  Moyenne    : {slope_deg.mean():.2f}°")
print(f"  Mediane    : {np.median(slope_deg):.2f}°")
print(f"  P10        : {np.percentile(slope_deg, 10):.2f}°")
print(f"  P25        : {np.percentile(slope_deg, 25):.2f}°")
print(f"  P50        : {np.percentile(slope_deg, 50):.2f}°")
print(f"  P75        : {np.percentile(slope_deg, 75):.2f}°")
print(f"  P90        : {np.percentile(slope_deg, 90):.2f}°")
print(f"  P95        : {np.percentile(slope_deg, 95):.2f}°")
print(f"  P99        : {np.percentile(slope_deg, 99):.2f}°")

print(f"\nDISTRIBUTION PAR TRANCHES :")
ranges = [
    (0, 5, "Tres plat"),
    (5, 10, "Plat"),
    (10, 15, "Legerement incline"),
    (15, 20, "Moderement incline"),
    (20, 25, "Incline"),
    (25, 30, "Fortement incline"),
    (30, 35, "Tres incline"),
    (35, 45, "Raide"),
    (45, 60, "Tres raide"),
    (60, 90, "Falaise")
]

for min_s, max_s, label in ranges:
    count = np.sum((slope_deg >= min_s) & (slope_deg < max_s))
    pct = count / slope.size * 100
    bar = "#" * int(pct / 2)
    print(f"  {min_s:2d} - {max_s:2d}° {label:20} : {count:10,} px ({pct:5.1f}%) {bar}")

print(f"\nCOMPARAISON AVEC SEUILS ACTUELS (slope_p90={np.percentile(slope_deg, 90):.2f}°) :")
flat_end = min(np.percentile(slope_deg, 90) * 0.36, 12.0)
print(f"  flat      <  {flat_end:.1f}° : {np.sum(slope_deg < flat_end):10,} px ({np.sum(slope_deg < flat_end)/slope.size*100:5.1f}%)")
print(f"  gentle    {flat_end:.1f} - 20° : {np.sum((slope_deg >= flat_end) & (slope_deg < 20)):10,} px ({np.sum((slope_deg >= flat_end) & (slope_deg < 20))/slope.size*100:5.1f}%)")
print(f"  moderate  20 - 35° : {np.sum((slope_deg >= 20) & (slope_deg < 35)):10,} px ({np.sum((slope_deg >= 20) & (slope_deg < 35))/slope.size*100:5.1f}%)")
print(f"  steep     >= 35°   : {np.sum(slope_deg >= 35):10,} px ({np.sum(slope_deg >= 35)/slope.size*100:5.1f}%)")

print(f"\nTYPE DE TERRAIN : ", end="")
mean_slope = slope_deg.mean()
if mean_slope < 5:
    print("TRES PLAT (plaines, deltas)")
elif mean_slope < 10:
    print("PLAT (collines douces)")
elif mean_slope < 15:
    print("VALLONNE (collines moderees)")
elif mean_slope < 20:
    print("MONTAGNEUX (relief prononce)")
else:
    print("TRES MONTAGNEUX (relief alpin)")
