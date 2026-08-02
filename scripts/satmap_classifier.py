"""
satmap_classifier.py — Classification interactive de satmap par couleurs K-means

Usage:
    python satmap_classifier.py

Une boîte de dialogue s'ouvre pour choisir la satmap.
"""

import sys
import json
import numpy as np
from pathlib import Path
from PIL import Image
import cv2
from sklearn.cluster import MiniBatchKMeans
import tkinter as tk
from tkinter import filedialog

# ============================================================
# CONFIG
# ============================================================
N_CLUSTERS   = 20
SCALE        = 0.25
CATALOG_PATH = Path(__file__).parent / "data" / "Textures_ArmaReforger" / "catalog.json"
CLASSES      = ["eau", "foret", "champ", "urbain", "route", "autre", "ignorer"]

# ============================================================
# SÉLECTION FICHIER
# ============================================================
def pick_file():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Choisir la satmap",
        filetypes=[("Images", "*.tif *.tiff *.png *.jpg *.jpeg"), ("Tous", "*.*")]
    )
    root.destroy()
    return Path(path) if path else None

def pick_output_dir():
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askdirectory(title="Choisir le dossier de sortie")
    root.destroy()
    return Path(path) if path else None

# ============================================================
# K-MEANS
# ============================================================
def run_kmeans(arr_rgb, n_clusters):
    pixels = arr_rgb.reshape(-1, 3).astype(np.float32)
    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42,
                         n_init=5, batch_size=10000)
    km.fit(pixels)
    centers = km.cluster_centers_.astype(np.uint8)
    labels  = km.labels_.reshape(arr_rgb.shape[:2])
    counts  = np.bincount(km.labels_, minlength=n_clusters)
    order   = np.argsort(counts)[::-1]
    return centers, labels, counts, order

# ============================================================
# CLASSIFICATION AUTOMATIQUE
# ============================================================
def auto_classify(r, g, b):
    lum   = (int(r) + int(g) + int(b)) / 3.0
    max_c = max(int(r), int(g), int(b))
    min_c = min(int(r), int(g), int(b))
    sat   = (max_c - min_c) / max(max_c, 1)

    if int(b) > int(r) + 10 and int(b) > int(g) - 15:
        return "eau"
    if lum > 110 and sat < 0.12:
        return "urbain"
    if lum > 80 and sat < 0.20 and int(r) > 70 and abs(int(r)-int(g)) < 35:
        return "champ"
    if int(g) > int(r) + 5 and lum < 90:
        return "foret"
    if lum > 60 and int(g) > int(r) - 10:
        return "champ"
    return "autre"

# ============================================================
# CLASSIFICATION INTERACTIVE
# ============================================================
def interactive_classify(centers, counts, order):
    classes_map = {}
    total = counts.sum()

    print("\n" + "="*65)
    print("CLASSIFICATION DES FAMILLES DE COULEURS")
    print("="*65)
    print(f"Classes : {', '.join(CLASSES)}")
    print("Entrée = accepter suggestion | tapez la classe pour changer")
    print("="*65 + "\n")

    for rank, i in enumerate(order):
        r, g, b   = centers[i]
        pct        = counts[i] / total * 100
        suggestion = auto_classify(r, g, b)

        try:
            block = f"\033[48;2;{r};{g};{b}m   \033[0m"
        except Exception:
            block = "   "

        prompt = (f"  [{rank+1:2d}/{len(order)}] {block} "
                  f"#{r:02X}{g:02X}{b:02X} "
                  f"RGB({r:3d},{g:3d},{b:3d}) "
                  f"{pct:5.1f}%  "
                  f"[{suggestion}] > ")

        while True:
            try:
                answer = input(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nInterrompu.")
                sys.exit(0)

            if answer == "":
                answer = suggestion

            if answer in CLASSES:
                classes_map[i] = answer
                break
            else:
                print(f"    ⚠ Classes valides : {', '.join(CLASSES)}")

    return classes_map

# ============================================================
# GÉNÉRATION MASKS
# ============================================================
def generate_masks(labels_full, classes_map, output_dir, W, H):
    print(f"\n💾 Génération masks...")
    for classe in CLASSES:
        if classe == "ignorer":
            continue
        ids = [cid for cid, cl in classes_map.items() if cl == classe]
        if not ids:
            continue
        mask = np.zeros((H, W), dtype=np.uint8)
        for cid in ids:
            mask[labels_full == cid] = 255

        # Post-traitement adapté par classe
        if classe == "champ":
            # Champs : close agressif pour remplir les trous internes
            # puis suppression des petites composantes (bruit)
            k_close = np.ones((15, 15), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close, iterations=3)
            k_open = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open, iterations=1)
            # Supprimer composantes < 800px
            n_lab, lab_img, stats, _ = cv2.connectedComponentsWithStats(mask)
            mask_clean = np.zeros_like(mask)
            for i in range(1, n_lab):
                if stats[i, cv2.CC_STAT_AREA] >= 800:
                    mask_clean[lab_img == i] = 255
            mask = mask_clean

        elif classe == "eau":
            # Eau : close pour boucher les trous côtiers, garder grandes zones
            k = np.ones((9, 9), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=3)
            n_lab, lab_img, stats, _ = cv2.connectedComponentsWithStats(mask)
            mask_clean = np.zeros_like(mask)
            for i in range(1, n_lab):
                if stats[i, cv2.CC_STAT_AREA] >= 2000:
                    mask_clean[lab_img == i] = 255
            mask = mask_clean

        elif classe == "foret":
            # Forêt : close modéré
            k = np.ones((7, 7), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)

        elif classe == "urbain":
            # Urbain : close léger, garder petites zones (villages)
            k = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
            n_lab, lab_img, stats, _ = cv2.connectedComponentsWithStats(mask)
            mask_clean = np.zeros_like(mask)
            for i in range(1, n_lab):
                if stats[i, cv2.CC_STAT_AREA] >= 200:
                    mask_clean[lab_img == i] = 255
            mask = mask_clean

        else:
            # Autre/route : nettoyage basique
            k = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)

        out = output_dir / f"mask_{classe}.png"
        Image.fromarray(mask).save(out)
        print(f"  ✅ mask_{classe}.png  ({(mask>0).mean()*100:.1f}%)")

# ============================================================
# SATMAP MIDDLE REFORGER
# ============================================================
def generate_satmap_middle(labels_full, centers, classes_map, output_dir, W, H):
    if not CATALOG_PATH.exists():
        print(f"  ⚠ Catalogue non trouvé : {CATALOG_PATH}")
        return

    with open(CATALOG_PATH) as f:
        cat = json.load(f)

    EXCLUDE = {"default.emat","Debris_Coal_01.emat","Debris_Coal_02.emat",
               "Debris_Coal_03.emat","ZI_Ground_Sport_01.emat"}
    mat_names, mat_colors = [], []
    for name, entry in cat.items():
        if name in EXCLUDE: continue
        avg = entry.get("avg_color")
        if not avg or avg[:3] == [0,0,0]: continue
        mat_names.append(name.replace(".emat",""))
        mat_colors.append(avg[:3])

    mat_colors = np.array(mat_colors, dtype=np.float32)
    mat_lab    = cv2.cvtColor(
        mat_colors.astype(np.uint8).reshape(1,-1,3),
        cv2.COLOR_RGB2LAB).reshape(-1,3).astype(float)
    centers_lab = cv2.cvtColor(
        centers.reshape(1,-1,3),
        cv2.COLOR_RGB2LAB).reshape(-1,3).astype(float)

    recon = np.zeros((H, W, 3), dtype=np.uint8)
    print(f"\n🗺 Matching → matériaux Reforger :")
    for cid in range(len(centers)):
        if classes_map.get(cid) == "ignorer":
            continue
        dists = np.sqrt(((mat_lab - centers_lab[cid])**2).sum(axis=1))
        best  = np.argmin(dists)
        r,g,b = centers[cid]
        print(f"  #{r:02X}{g:02X}{b:02X} [{classes_map.get(cid,'?')}]"
              f" → {mat_names[best]}  (ΔE={dists[best]:.1f})")
        recon[labels_full == cid] = mat_colors[best].astype(np.uint8)

    Image.fromarray(recon).save(output_dir / "satmap_middle_reforger.png")
    print(f"  ✅ satmap_middle_reforger.png")

# ============================================================
# MODE 3 — OSM (OpenStreetMap)
# ============================================================
def get_bbox_from_source(input_path, W, H):
    """
    Récupère la bounding box depuis :
    1. Nom de fichier (format N49_19_W1_12_-N49_25_W0_47)
    2. Métadonnées GeoTIFF (gdal)
    3. Saisie manuelle
    Retourne (north, south, west, east) ou None si annulé.
    """
    import re
    name = Path(str(input_path).replace('\\', '/')).stem
    print(f"  [DEBUG] Nom fichier parsé : '{name}'")

    # Priorité 1 : nom de fichier (accepte _ ou ° et ')
    m = re.findall(r'[Nn](\d+)[_°](\d+)[\'_][EeWw](\d+)[_°](\d+)', name)
    print(f"  [DEBUG] Groupes trouvés : {m}")
    if len(m) >= 2:
        lat1 = int(m[0][0]) + int(m[0][1])/60
        lon1 = int(m[0][2]) + int(m[0][3])/60
        lat2 = int(m[1][0]) + int(m[1][1])/60
        lon2 = int(m[1][2]) + int(m[1][3])/60
        if 'W' in name.upper():
            lon1, lon2 = -lon1, -lon2
        north = max(lat1, lat2)
        south = min(lat1, lat2)
        west  = min(lon1, lon2)
        east  = max(lon1, lon2)
        print(f"  Coordonnées depuis nom de fichier :")
        print(f"  N={north:.4f}  S={south:.4f}  W={west:.4f}  E={east:.4f}")
        return north, south, west, east

    # Priorité 2 : GeoTIFF
    try:
        from osgeo import gdal
        ds = gdal.Open(str(input_path))
        if ds:
            gt = ds.GetGeoTransform()
            west  = gt[0]
            north = gt[3]
            east  = west + gt[1] * W
            south = north + gt[5] * H
            print(f"  Coordonnées depuis GeoTIFF :")
            print(f"  N={north:.4f}  S={south:.4f}  W={west:.4f}  E={east:.4f}")
            return north, south, west, east
    except Exception:
        pass

    # Priorité 3 : saisie manuelle
    print("  Coordonnées non trouvées — saisie manuelle :")
    try:
        north = float(input("  Nord (lat max) > "))
        south = float(input("  Sud  (lat min) > "))
        west  = float(input("  Ouest (lon min, négatif si W) > "))
        east  = float(input("  Est   (lon max, négatif si W) > "))
        return north, south, west, east
    except (ValueError, EOFError, KeyboardInterrupt):
        return None


def osm_mode(output_dir, input_path):
    """Mode 3 — Télécharge routes, zones urbaines et bâtiments depuis OSM."""
    try:
        import osmnx as ox
    except ImportError:
        print("❌ osmnx non installé. Lance : pip install osmnx")
        return

    from PIL import Image, ImageDraw

    img = Image.open(input_path).convert("RGB")
    W, H = img.size

    print(f"\n📐 Dimensions satmap : {W}×{H} px")
    result = get_bbox_from_source(input_path, W, H)
    if result is None:
        print("Annulé.")
        return

    north, south, west, east = result
    bbox = (west, south, east, north)  # format osmnx (left,bottom,right,top)

    def geo_to_px(lat, lon):
        x = int((lon - west)  / (east  - west)  * W)
        y = int((north - lat) / (north - south) * H)
        return max(0, min(W-1, x)), max(0, min(H-1, y))

    def draw_polygons(geoms, draw, fill=255):
        for geom in geoms:
            if geom is None: continue
            polys = [geom] if geom.geom_type == 'Polygon' else \
                    list(geom.geoms) if geom.geom_type == 'MultiPolygon' else []
            for poly in polys:
                pts = [geo_to_px(lat, lon) for lon, lat in poly.exterior.coords]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=fill)

    import numpy as np
    arr = np.array(img)

    # --- ROUTES ---
    print("\n🛣️ Téléchargement routes OSM...")
    try:
        G = ox.graph_from_bbox(bbox=bbox, network_type='drive', retain_all=False)
        edges = ox.graph_to_gdfs(G, nodes=False)
        print(f"  {len(edges)} segments de routes")

        mask_routes = Image.new("L", (W, H), 0)
        draw_r = ImageDraw.Draw(mask_routes)

        for _, edge in edges.iterrows():
            coords = list(edge.geometry.coords)
            pixels = [geo_to_px(lat, lon) for lon, lat in coords]
            highway = edge.get('highway', 'unclassified')
            if isinstance(highway, list): highway = highway[0]
            thick = 10 if highway in ['motorway','trunk','primary'] else \
                     6 if highway in ['secondary','tertiary'] else \
                     4 if highway in ['residential','unclassified'] else 2
            for i in range(len(pixels)-1):
                draw_r.line([pixels[i], pixels[i+1]], fill=255, width=thick)

        mask_routes.save(output_dir / "mask_routes_osm.png")
        arr[np.array(mask_routes) > 0] = [255, 220, 0]
        print(f"  ✅ mask_routes_osm.png")
    except Exception as e:
        print(f"  ⚠ Routes : {e}")

    # --- ZONES URBAINES ---
    print("\n🏘️ Téléchargement zones urbaines OSM...")
    try:
        tags_urban = {'landuse': ['residential','commercial','industrial','retail']}
        urban = ox.features_from_bbox(bbox=bbox, tags=tags_urban)
        print(f"  {len(urban)} zones urbaines")

        mask_urban = Image.new("L", (W, H), 0)
        draw_u = ImageDraw.Draw(mask_urban)
        draw_polygons(urban.geometry.tolist(), draw_u)

        mask_urban.save(output_dir / "mask_urbain_osm.png")
        arr[np.array(mask_urban) > 0] = [255, 80, 80]
        print(f"  ✅ mask_urbain_osm.png")
    except Exception as e:
        print(f"  ⚠ Zones urbaines : {e}")

    # --- BÂTIMENTS ---
    print("\n🏠 Téléchargement bâtiments OSM...")
    try:
        tags_build = {'building': True}
        buildings = ox.features_from_bbox(bbox=bbox, tags=tags_build)
        print(f"  {len(buildings)} bâtiments")

        mask_build = Image.new("L", (W, H), 0)
        draw_b = ImageDraw.Draw(mask_build)
        draw_polygons(buildings.geometry.tolist(), draw_b)

        mask_build.save(output_dir / "mask_batiments_osm.png")
        arr[np.array(mask_build) > 0] = [255, 160, 40]
        print(f"  ✅ mask_batiments_osm.png")
    except Exception as e:
        print(f"  ⚠ Bâtiments : {e}")

    # --- APERÇU ---
    ratio = 1200 / W
    h_s = int(H * ratio)
    Image.fromarray(arr).resize((1200, h_s), Image.LANCZOS).save(
        output_dir / "osm_overlay.jpg", quality=88)
    print(f"\n✅ osm_overlay.jpg  (routes=jaune, urbain=rouge, bâtiments=orange)")
    print(f"✅ Terminé → {output_dir}")


# ============================================================
# MAIN
# ============================================================
def kmeans_mode(input_path, output_dir):
    """Mode 1 — Classification K-means interactive."""
    # Chargement
    print(f"\n📂 Chargement image...")
    img = Image.open(input_path).convert("RGB")
    W, H = img.size
    print(f"   {W}×{H} px")

    # Réduction pour K-means
    Ws = max(100, int(W * SCALE))
    Hs = max(100, int(H * SCALE))
    small = np.array(img.resize((Ws, Hs), Image.LANCZOS))
    print(f"   Réduite à {Ws}×{Hs} pour K-means")

    # K-means
    print(f"\n🎨 K-means ({N_CLUSTERS} familles)...")
    centers, labels_small, counts, order = run_kmeans(small, N_CLUSTERS)
    print(f"   ✅ {N_CLUSTERS} familles trouvées")

    # Aperçu
    seg     = centers[labels_small]
    compare = np.hstack([small, seg])
    Image.fromarray(compare).save(output_dir / "apercu_kmeans.jpg", quality=88)
    print(f"   📸 apercu_kmeans.jpg — ouvre ce fichier pour voir les familles")

    # Classification interactive
    classes_map = interactive_classify(centers, counts, order)

    # Upscale labels
    print(f"\n⬆ Upscale labels → {W}×{H}...")
    labels_full = np.array(
        Image.fromarray(labels_small.astype(np.uint8)).resize((W, H), Image.NEAREST)
    )

    # Masks
    generate_masks(labels_full, classes_map, output_dir, W, H)

    # Satmap middle
    generate_satmap_middle(labels_full, centers, classes_map, output_dir, W, H)

    # Sauvegarder classification
    save = {
        "input"          : str(input_path),
        "clusters"       : N_CLUSTERS,
        "classification" : {str(k): v for k, v in classes_map.items()},
        "centers"        : centers.tolist()
    }
    with open(output_dir / "classification.json", "w") as f:
        json.dump(save, f, indent=2)
    print(f"\n✅ Classification sauvée → classification.json")


def main():
    print("="*65)
    print("SATMAP CLASSIFIER — Modes de traitement")
    print("="*65)
    print("\n[1] Analyse complète (K-means + rapport palette + classification)")
    print("[2] Reuse — satmap middle depuis masks Photoshop existants")
    print("[3] OSM — Télécharger routes + zones urbaines + bâtiments")
    print("\n" + "="*65)

    while True:
        try:
            mode = input("\nChoisir le mode [1-3] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAnnulé.")
            sys.exit(0)

        if mode in ["1", "2", "3"]:
            break
        print("⚠ Choisir 1, 2 ou 3")

    if mode == "3":
        print("\nChoisir la satmap source (pour les coordonnées)...")
        input_path = pick_file()
        if not input_path:
            print("Annulé.")
            sys.exit(0)
        print("Choisir le dossier de sortie...")
        output_dir = pick_output_dir()
        if not output_dir:
            output_dir = Path(input_path).parent / "osm_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        osm_mode(output_dir, input_path)
        input("\nAppuyer sur Entrée pour quitter...")
        return

    # Choisir satmap
    print("\nChoisir la satmap source...")
    input_path = pick_file()
    if not input_path:
        print("Annulé.")
        sys.exit(0)
    print(f"Satmap : {input_path.name}")

    # Choisir dossier sortie
    print("Choisir le dossier de sortie...")
    output_dir = pick_output_dir()
    if not output_dir:
        output_dir = input_path.parent / "satmap_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Sortie  : {output_dir}")

    # Lancer le mode sélectionné
    if mode == "1":
        kmeans_mode(input_path, output_dir)
    elif mode == "2":
        print("\n⚠ Mode 2 non implémenté pour le moment.")
        input("\nAppuyer sur Entrée pour quitter...")
        return

    print(f"\n{'='*65}")
    print(f"✅ Terminé → {output_dir}")
    input("\nAppuyer sur Entrée pour quitter...")

if __name__ == "__main__":
    main()
