# 🐛 RAPPORT BUG — satmap_fond_512.png non générée

**Date :** 2024-09-24  
**Erreur :** `⚠️ satmap_fond_512 non générée : name 'dem' is not defined`

---

## 1️⃣ OÙ satmap_fond_512 EST GÉNÉRÉ

### Fichier
**satmap_v2_textured_v2.py** (et **satmap_v2_textured.py** — même bug)

### Fonction
`generate_satmap_v2_textured_complete()` — lignes 302-520

### Code défectueux (lignes 485-501)

```python
# Générer automatiquement satmap_fond_512.png (terre/eau depuis heightmap)
try:
    import cv2 as _cv2
    dem_norm = dem  # ❌ ERREUR : 'dem' n'est JAMAIS défini
    water_thresh = float(np.percentile(dem_norm[dem_norm > dem_norm.min()], 10))
    fond = np.where(
        dem_norm < water_thresh,
        np.array([45, 30, 20], dtype=np.uint8),   # eau — BGR bleu foncé
        np.array([35, 55, 40], dtype=np.uint8)    # terre — BGR vert foncé
    ).astype(np.uint8)
    fond_512 = _cv2.resize(fond, (512, 512), interpolation=_cv2.INTER_AREA)
    fond_path = output_path.parent.parent.parent / "inputs" / "satmap_fond_512.png"
    fond_path.parent.mkdir(parents=True, exist_ok=True)
    _cv2.imwrite(str(fond_path), fond_512)
    log(f"✅ satmap_fond_512.png générée → {fond_path}")
except Exception as e:
    log(f"⚠️ satmap_fond_512 non générée : {e}")
```

### Explication du rôle de 'dem'

**dem** devait contenir :
- **Heightmap** (Digital Elevation Model) : grille 2D des altitudes du terrain
- **Format attendu** : numpy array 2D (hauteur × largeur) avec valeurs d'élévation
- **Utilisation** : 
  1. Calculer seuil eau (percentile 10% des altitudes)
  2. Distinguer eau (altitude < seuil) vs terre (altitude ≥ seuil)
  3. Générer image fond 2 couleurs (bleu eau / vert terre)

**Problème** : `dem` n'est jamais chargé, défini, ni passé en paramètre à la fonction.

---

## 2️⃣ OÙ satmap_fond_512.png EST UTILISÉ

### Fichier : main.py

**Ligne 606-613** — Fonction `get_satmap_fond()`

```python
def get_satmap_fond(self) -> dict:
    """Récupère l'image de fond satmap encodée en base64."""
    if not _session["current_project_path"]:
        return {"ok": False}
    try:
        import base64
        proj = Path(_session["current_project_path"])
        # Chercher satmap_fond_512.png ou satmap dans inputs/
        candidates = [
            proj / "inputs" / "satmap_fond_512.png",
            proj / "inputs" / "satmap_fond_512.jpg",
        ]
        for c in candidates:
            if c.exists():
                ext = c.suffix.lower().replace(".", "")
                b64 = base64.b64encode(c.read_bytes()).decode()
                return {"ok": True, "b64": b64, "ext": ext}
        return {"ok": False, "reason": "no_satmap"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

### Rôle
**Image de fond pour l'interface utilisateur** — Affichage satmap simplifiée (terre/eau) en arrière-plan de l'aperçu.

**Optionnel** : L'absence de ce fichier ne bloque PAS le fonctionnement principal (génération satmap complète).

---

## 3️⃣ HISTORIQUE GIT — Depuis quand ?

### Commit d'introduction

```bash
git log -S "dem" --oneline -- satmap_v2_textured_v2.py
```

**Résultat** :
```
3ef1f21 feat: architecture utilisateur pour textures et amélioration satmap v2
```

### Analyse du commit

Le code a été **ajouté directement avec le bug** dans le commit `3ef1f21`.

**Contenu du commit** :
```diff
+    # Générer automatiquement satmap_fond_512.png (terre/eau depuis heightmap)
+    try:
+        import cv2 as _cv2
+        dem_norm = dem  # dem déjà chargé en mémoire  ← FAUX
```

**Commentaire trompeur** : `# dem déjà chargé en mémoire` suggère que `dem` devrait exister, mais ce n'est jamais le cas.

**Conclusion** : Bug présent **dès l'introduction** de cette fonctionnalité. La variable `dem` n'a jamais été correctement intégrée au code.

---

## 4️⃣ PROPOSITION DE CORRECTION MINIMALE

### ⚠️ AUCUNE MODIFICATION APPLIQUÉE (analyse seule)

### Option A — Désactiver la génération (correction immédiate)

**Fichiers à modifier** :
- `satmap_v2_textured_v2.py` lignes 485-501
- `satmap_v2_textured.py` lignes 449-465

**Modification** :
```python
# AVANT (lignes 485-501)
# Générer automatiquement satmap_fond_512.png (terre/eau depuis heightmap)
try:
    import cv2 as _cv2
    dem_norm = dem  # ...
    # ... code génération ...
except Exception as e:
    log(f"⚠️ satmap_fond_512 non générée : {e}")

# APRÈS
# Générer automatiquement satmap_fond_512.png (terre/eau depuis heightmap)
# DÉSACTIVÉ : heightmap (dem) non disponible dans cette fonction
# Pour réactiver : charger heightmap depuis terrain_dir ou passer en paramètre
# try:
#     ...
# except Exception as e:
#     log(f"⚠️ satmap_fond_512 non générée : {e}")
```

**Avantage** : Supprime l'erreur immédiatement  
**Inconvénient** : Perd la fonctionnalité (image de fond non générée)

---

### Option B — Générer depuis satmap complète (workaround)

**Fichiers à modifier** :
- `satmap_v2_textured_v2.py` lignes 485-501
- `satmap_v2_textured.py` lignes 449-465

**Modification** :
```python
# Générer automatiquement satmap_fond_512.png (fond simplifié depuis satmap)
try:
    import cv2 as _cv2
    
    # Utiliser la satmap complète comme base (déjà calculée)
    satmap_bgr = cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR)
    
    # Réduire à 512x512 et simplifier (blur pour effet "fond")
    fond_512 = _cv2.resize(satmap_bgr, (512, 512), interpolation=_cv2.INTER_AREA)
    fond_512 = _cv2.GaussianBlur(fond_512, (15, 15), 0)  # Adoucir pour effet fond
    
    fond_path = output_path.parent.parent.parent / "inputs" / "satmap_fond_512.png"
    fond_path.parent.mkdir(parents=True, exist_ok=True)
    _cv2.imwrite(str(fond_path), fond_512)
    log(f"✅ satmap_fond_512.png générée → {fond_path}")
except Exception as e:
    log(f"⚠️ satmap_fond_512 non générée : {e}")
```

**Avantage** : Génère une image de fond réaliste (basée sur la vraie satmap)  
**Inconvénient** : Perd la distinction terre/eau basée sur altitude (mais garde les vraies textures)

---

### Option C — Charger vraie heightmap (solution complète)

**Fichiers à modifier** :
- `satmap_v2_textured_v2.py` signature fonction ligne 302 + lignes 485-501
- `satmap_v2_textured.py` idem
- `main.py` appel à generate_satmap_v2_textured_complete

**Modification 1** — Ajouter paramètre heightmap_path :
```python
def generate_satmap_v2_textured_complete(
    terrain_dir: Path,
    catalog_path: Path,
    output_path: Path,
    terr_file: Path = None,
    mode: str = "colors",
    target_resolution: Optional[int] = 4097,
    verbose: bool = False,
    middles_dir: Path = None,
    emat_dir: Optional[Path] = None,
    heightmap_path: Optional[Path] = None  # ← NOUVEAU
):
```

**Modification 2** — Charger heightmap si fournie :
```python
# Après ligne 365 (après chargement surfaces)
dem = None
if heightmap_path and heightmap_path.exists():
    if heightmap_path.suffix.lower() == '.asc':
        # Format ESRI ASCII Grid
        with open(heightmap_path, 'r') as f:
            for _ in range(6):  # Skip headers
                f.readline()
            dem = np.loadtxt(f)
    else:
        # Format image (PNG/JPG)
        dem = cv2.imread(str(heightmap_path), cv2.IMREAD_GRAYSCALE)
    log(f"Heightmap chargée : {heightmap_path.name} ({dem.shape})")
```

**Modification 3** — Vérifier existence avant utilisation :
```python
# Ligne 485
# Générer automatiquement satmap_fond_512.png (terre/eau depuis heightmap)
if dem is not None:  # ← AJOUT CONDITION
    try:
        import cv2 as _cv2
        dem_norm = dem  # Maintenant défini
        # ... reste du code ...
    except Exception as e:
        log(f"⚠️ satmap_fond_512 non générée : {e}")
else:
    log(f"ℹ️ satmap_fond_512 non générée : heightmap non fournie")
```

**Avantage** : Solution complète, fonctionnalité comme prévu initialement  
**Inconvénient** : Nécessite fournir heightmap (pas toujours disponible dans projets Reforger)

---

### 📋 FONCTIONS À NE PAS TOUCHER

**NE PAS MODIFIER** (risque de casser génération satmap principale) :
- `render_textured_block()` (lignes 184-299)
- `get_material_middle()` (lignes 78-177)
- `get_material_color()` (lignes 51-75)
- `load_catalog()` (lignes 46-49)
- Toute la boucle de traitement des tuiles (lignes 400-480)
- Post-processing pixels noirs (lignes 503-520)

**MODIFIER UNIQUEMENT** :
- Bloc try/except lignes 485-501 (génération satmap_fond_512)
- Optionnellement : signature fonction ligne 302 (si Option C)

---

## 📊 RÉCAPITULATIF

| Aspect | Statut |
|--------|--------|
| **Bug identifié** | ✅ Variable `dem` non définie, utilisée ligne 488 |
| **Impact** | ⚠️ Mineur — satmap_fond_512.png non générée, mais satmap principale OK |
| **Depuis quand** | 🕐 Commit `3ef1f21` (bug dès l'introduction) |
| **Fichiers affectés** | 📁 `satmap_v2_textured_v2.py`, `satmap_v2_textured.py` |
| **Correction recommandée** | 🔧 Option B (workaround depuis satmap) ou Option A (désactiver) |
| **Correction complète** | 🏗️ Option C (charger heightmap) — nécessite heightmap disponible |

---

**FIN DU RAPPORT**
