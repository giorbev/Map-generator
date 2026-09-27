# ÉTAPE 0 — ANALYSE FICHIERS SATMAP (LECTURE SEULE)

**Date** : 2026-09-27  
**Contexte** : Suite AUDIT_RESOLUTIONS_SATMAP.md — Préparation corrections 3 problèmes

---

## 📍 POINTS D'ÉCRITURE (DOUBLE SAUVEGARDE)

### Point 1 — satmap_v2_textured_v2.py

**Fichier** : [satmap_v2_textured_v2.py:544](satmap_v2_textured_v2.py#L544)  
**Fonction** : `generate_satmap_v2_textured_complete`  
**Code** :
```python
# Ligne 544
cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))
```

**Description** : Première sauvegarde du fichier satmap  
**Nom fichier** : Passé en paramètre `output_path` depuis main.py (voir Point 2)

---

### Point 2 — main.py (TRIPLE écriture)

**Fichier** : [main.py](main.py)  
**Fonction** : `generate_satmap_v2`  

#### 2a. Appel fonction (ligne 1259)
```python
# Ligne 1259 — Définition du chemin
native_path = output_dir / "satmap_v2_textured_native.png"

# Lignes 1278-1284 — Appel fonction qui écrit Point 1
stats = generate_satmap_v2_textured_complete(
    terrain_dir, catalog_path, native_path,  # ← output_path = native_path
    ...
)
```

**Résultat Point 1** : Écriture de `satmap_v2_textured_native.png`

#### 2b. Re-sauvegarde Native (lignes 1299-1301)
```python
if resolution == 0:
    # Native
    out_path = output_dir / f"satmap_v2_textured_{w}.png"  # w = largeur canvas
    _cv2_sat.imwrite(str(out_path), native_img)
    saved = [out_path.name]
```

**Résultat Point 2b** : Écriture de `satmap_v2_textured_{w}.png` (ex: `satmap_v2_textured_16384.png`)  
**Problème** : Double sauvegarde (recharge depuis native_path puis re-écrit)

#### 2c. Re-sauvegarde Downscale (lignes 1303-1309)
```python
else:
    out_path = output_dir / f"satmap_v2_textured_{resolution}.png"
    if resolution == w:
        _cv2_sat.imwrite(str(out_path), native_img)
    else:
        resized = _cv2_sat.resize(native_img, (resolution, resolution), interpolation=_cv2_sat.INTER_AREA)
        _cv2_sat.imwrite(str(out_path), resized)
```

**Résultat Point 2c** : Écriture de `satmap_v2_textured_{resolution}.png` (ex: `satmap_v2_textured_4097.png`)  
**Problème** : Triple sauvegarde totale (native.png + resolution.png, tous deux depuis native_path)

---

## 📂 CONSOMMATEURS DES FICHIERS SATMAP

### Fichiers actifs du projet (non-backup)

#### 1. main.py

**Ligne 190** — Template nouveau projet :
```python
"satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",
```
**Usage** : Valeur par défaut dans project.json lors de la création d'un nouveau projet

**Ligne 1259** — Génération satmap :
```python
native_path = output_dir / "satmap_v2_textured_native.png"
```
**Usage** : Chemin temporaire pour la sauvegarde native (Point 1 écriture)

**Lignes 1299, 1303** — Chemins finaux :
```python
# Resolution 0 (native)
out_path = output_dir / f"satmap_v2_textured_{w}.png"

# Resolution ≠ 0 (4k/8k)
out_path = output_dir / f"satmap_v2_textured_{resolution}.png"
```
**Usage** : Chemins des fichiers finaux (Points 2b, 2c écriture)

---

#### 2. main1.py

**Ligne 133** — Template nouveau projet :
```python
"satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",
```
**Usage** : Identique à main.py (fichier possiblement obsolète ?)

---

#### 3. data/projects/*/project.json

**Normandie/project.json:38** :
```json
"satmap_v2": "outputs/generated/satmap_v2_textured_4097.png"
```

**Zimnitrita/project.json:431** :
```json
"satmap_v2": "outputs\\generated\\satmap_v2_textured_4097.png"
```

**Usage** : Référence au fichier satmap dans la configuration du projet  
**Note** : Valeur par défaut créée lors de la création du projet (depuis main.py:190)

---

#### 4. data/projects/Zimnitrita/outputs/satmap/classification.json

**Ligne 2** :
```json
"input": "H:\\logiciel perso\\Map generator\\data\\projects\\Zimnitrita\\generated\\satmap_v2\\satmap_v2_textured_4097.png"
```

**Usage** : Référence au fichier satmap dans les résultats de classification  
**Note** : Généré automatiquement par un outil de classification

---

## 🔍 NOMS DE FICHIERS GÉNÉRÉS

### Scénario actuel

| Resolution | Point 1 (fonction) | Point 2 (main.py) | Total fichiers |
|------------|-------------------|-------------------|----------------|
| **0 (Native)** | `satmap_v2_textured_native.png` (16384×16384) | `satmap_v2_textured_16384.png` (copie) | **2 fichiers** identiques |
| **4097 (4k)** | `satmap_v2_textured_native.png` (4097×4097, déjà downscalé ⚠️) | `satmap_v2_textured_4097.png` (copie) | **2 fichiers** identiques |
| **8193 (8k)** | `satmap_v2_textured_native.png` (8193×8193, déjà downscalé ⚠️) | `satmap_v2_textured_8193.png` (copie) | **2 fichiers** identiques |

**Problèmes** :
- ❌ `satmap_v2_textured_native.png` = downscalé si resolution ≠ 0 (nom trompeur)
- ❌ Double sauvegarde (2 fichiers identiques)
- ❌ Canvas natif 16384×16384 perdu si resolution ≠ 0

---

## 🎯 CORRECTIONS REQUISES

### Correction 1 — Canvas natif toujours sauvegardé

**Objectif** : Sauvegarder le canvas 16384×16384 (après flip) AVANT tout downscale

**Fichiers à modifier** :
- [satmap_v2_textured_v2.py](satmap_v2_textured_v2.py) (fonction `generate_satmap_v2_textured_complete`)

**Action** :
- Après ligne 531 (flip) : sauvegarder canvas → `satmap_v2_textured_{canvas_width}.png`
- Puis downscale si demandé → `satmap_v2_textured_{target_resolution}.png`

---

### Correction 2 — Nommage clair

**Objectif** : Chaque fichier porte sa vraie résolution

**Nouveau nommage** :

| Resolution | Fichier canvas natif | Fichier downscale |
|------------|---------------------|-------------------|
| **0 (Native)** | `satmap_v2_textured_16384.png` | (aucun) |
| **4097 (4k)** | `satmap_v2_textured_16384.png` | `satmap_v2_textured_4097.png` |
| **8193 (8k)** | `satmap_v2_textured_16384.png` | `satmap_v2_textured_8193.png` |

**Fichiers à modifier** :
- [satmap_v2_textured_v2.py](satmap_v2_textured_v2.py) (nommage sauvegarde)
- [main.py:190](main.py#L190) (template project.json — changer défaut vers `satmap_v2_textured_16384.png` ?)
- [main1.py:133](main1.py#L133) (si fichier actif)
- **PAS toucher** : data/projects/*/project.json (existants, laissés tels quels)
- **PAS toucher** : classification.json (généré automatiquement)

---

### Correction 3 — Suppression double sauvegarde

**Objectif** : Une seule écriture par fichier, dans la fonction de génération

**Fichiers à modifier** :
- [main.py:1288-1310](main.py#L1288-L1310) — **SUPPRIMER** le bloc reload + re-save

**Code à supprimer** :
```python
# Lignes 1288-1310
# Downscaler vers les résolutions cibles
import cv2 as _cv2_sat
native_img = _cv2_sat.imread(str(native_path))
saved = []

if native_img is None:
    return {"ok": False, "error": f"Impossible de lire l'image native : {native_path}"}

h, w = native_img.shape[:2]
if resolution == 0:
    # Native
    out_path = output_dir / f"satmap_v2_textured_{w}.png"
    _cv2_sat.imwrite(str(out_path), native_img)
    saved = [out_path.name]
else:
    out_path = output_dir / f"satmap_v2_textured_{resolution}.png"
    if resolution == w:
        _cv2_sat.imwrite(str(out_path), native_img)
    else:
        resized = _cv2_sat.resize(native_img, (resolution, resolution), interpolation=_cv2_sat.INTER_AREA)
        _cv2_sat.imwrite(str(out_path), resized)
    saved = [out_path.name]
    self._log(f"[SATMAP] Sauvegardé : {out_path.name}")
```

**Nouveau comportement** :
- La fonction `generate_satmap_v2_textured_complete` retourne les chemins des fichiers créés
- main.py lit directement ces chemins pour le thumbnail et le retour API

---

## 📊 RÉSUMÉ

### Points d'écriture identifiés

| Point | Fichier | Fonction | Ligne | Action |
|-------|---------|----------|-------|--------|
| **1** | satmap_v2_textured_v2.py | `generate_satmap_v2_textured_complete` | 544 | **MODIFIER** — 2 sauvegardes (canvas + downscale) |
| **2a** | main.py | `generate_satmap_v2` | 1259 | **SUPPRIMER** — définition `native_path` |
| **2b** | main.py | `generate_satmap_v2` | 1299-1301 | **SUPPRIMER** — re-sauvegarde native |
| **2c** | main.py | `generate_satmap_v2` | 1303-1309 | **SUPPRIMER** — re-sauvegarde downscale |

### Consommateurs identifiés

| Fichier | Ligne | Type | Action ÉTAPE 1 |
|---------|-------|------|----------------|
| main.py | 190 | Template project.json | **MODIFIER** si changement défaut |
| main.py | 1259 | Chemin native temporaire | **SUPPRIMER** |
| main.py | 1299, 1303 | Chemins finaux | **SUPPRIMER** (remplacés par retour fonction) |
| main1.py | 133 | Template project.json | **VÉRIFIER** si fichier actif → modifier |
| data/projects/*/project.json | 38, 431 | Config projet | **NE PAS TOUCHER** (existants) |
| classification.json | 2 | Résultat classification | **NE PAS TOUCHER** (auto-généré) |

---

**✅ ANALYSE TERMINÉE — En attente validation pour ÉTAPE 1**
