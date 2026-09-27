# 🔍 AUDIT RÉSOLUTIONS SATMAP — 4k/8k/Native

**Date :** 2026-09-27  
**Fichiers analysés :** satmap_v2_textured_v2.py, main.py  
**Mode :** Lecture seule (aucune modification)

---

## 📊 RÉSUMÉ EXÉCUTIF

| Résolution | Valeur | Fonctionnel | Commentaires |
|------------|--------|-------------|--------------|
| **Native** | `None` ou `0` | ✅ OUI | Pas de downscale, taille canvas natif |
| **4k** | `4097` | ✅ OUI | Downscale INTER_AREA vers 4097×4097 |
| **8k** | `8193` | ✅ OUI | Downscale INTER_AREA vers 8193×8193 |
| **Autre** | N'importe quel int | ✅ OUI | Flexible, tout entier accepté |

**Verdict global** : ✅ **Toutes les résolutions fonctionnent indépendamment**

---

## 🔧 ARCHITECTURE RÉSOLUTION

### 1. Signature fonction (satmap_v2_textured_v2.py:356)

```python
def generate_satmap_v2_textured_complete(
    terrain_dir: Path,
    catalog_path: Path,
    output_path: Path,
    terr_file: Path = None,
    mode: str = "colors",
    target_resolution: Optional[int] = 4097,  # ← DÉFAUT 4k
    verbose: bool = False,
    middles_dir: Path = None,
    emat_dir: Optional[Path] = None,
    world_size_m: Optional[float] = None
):
```

**Type** : `Optional[int]`  
**Défaut** : `4097` (4k)  
**Accepte** : `None` (native), `0` (native), ou tout entier positif

---

### 2. Logique downscale (satmap_v2_textured_v2.py:534-539)

```python
# Downscale si nécessaire
if target_resolution is None or target_resolution == 0:
    log(f"Résolution native : {canvas.shape[1]}×{canvas.shape[0]}")
    satmap = canvas  # ← PAS DE DOWNSCALE
else:
    log(f"Downscale {canvas.shape[1]}×{canvas.shape[0]} -> {target_resolution}×{target_resolution}...")
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)
```

**Comportements** :

| Input | Condition | Résultat |
|-------|-----------|----------|
| `None` | `target_resolution is None` | **Native** (aucun downscale) |
| `0` | `target_resolution == 0` | **Native** (aucun downscale) |
| `4097` | Autre | **4k** (downscale INTER_AREA) |
| `8193` | Autre | **8k** (downscale INTER_AREA) |
| N'importe quel int > 0 | Autre | **Custom** (downscale INTER_AREA) |

---

### 3. Appel depuis main.py (ligne 1278-1284)

```python
from satmap_v2_textured_v2 import generate_satmap_v2_textured_complete
emat_dir = _TEXTURES_USER_DIR / "emat"
stats = generate_satmap_v2_textured_complete(
    terrain_dir, catalog_path, native_path,
    terr_file=terr_file, mode="textured",
    target_resolution=resolution if resolution != 0 else None,  # ← CONVERSION
    verbose=True,
    middles_dir=middles_dir,
    emat_dir=emat_dir
)
```

**Conversion** : `resolution if resolution != 0 else None`

| Input main.py | Passé à fonction | Résultat |
|---------------|------------------|----------|
| `0` | `None` | Native |
| `4097` | `4097` | 4k |
| `8193` | `8193` | 8k |
| Autre int > 0 | Valeur passée | Custom |

---

### 4. Sauvegarde fichier (main.py:1297-1310)

```python
h, w = native_img.shape[:2]
if resolution == 0:
    # Native
    out_path = output_dir / f"satmap_v2_textured_{w}.png"
    cv2.imwrite(str(out_path), native_img)
    saved = [out_path.name]
else:
    out_path = output_dir / f"satmap_v2_textured_{resolution}.png"
    if resolution == w:
        cv2.imwrite(str(out_path), native_img)  # Pas de resize si déjà à la bonne taille
    else:
        resized = cv2.resize(native_img, (resolution, resolution), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out_path), resized)
    saved = [out_path.name]
```

**Noms fichiers générés** :

| Résolution | Canvas natif | Nom fichier | Opération |
|------------|--------------|-------------|-----------|
| `0` (Native) | 16384×16384 | `satmap_v2_textured_16384.png` | Aucun resize |
| `4097` | 16384×16384 | `satmap_v2_textured_4097.png` | Resize 16384→4097 |
| `8193` | 16384×16384 | `satmap_v2_textured_8193.png` | Resize 16384→8193 |
| `4097` | 4097×4097 | `satmap_v2_textured_4097.png` | Aucun resize (déjà à la taille) |

---

## ✅ TESTS DE VALIDATION

### Test 1 — Native (resolution = 0)

**Flux** :
1. `main.py` reçoit `resolution = 0`
2. Convertit en `target_resolution = None`
3. `generate_satmap_v2_textured_complete` génère canvas natif
4. **Pas de downscale** (ligne 536 : `satmap = canvas`)
5. Sauvegarde `satmap_v2_textured_native.png`
6. Re-sauvegarde `satmap_v2_textured_{w}.png` où w = largeur native

**Résultat attendu** : ✅ Satmap à résolution native du canvas (ex: 16384×16384 pour Zimnitrita)

---

### Test 2 — 4k (resolution = 4097)

**Flux** :
1. `main.py` reçoit `resolution = 4097`
2. Passe `target_resolution = 4097`
3. `generate_satmap_v2_textured_complete` génère canvas natif
4. **Downscale INTER_AREA** (ligne 539 : `cv2.resize(..., (4097, 4097), INTER_AREA)`)
5. Sauvegarde `satmap_v2_textured_native.png` (à 4097×4097)
6. Re-sauvegarde `satmap_v2_textured_4097.png`

**Résultat attendu** : ✅ Satmap à 4097×4097 pixels

---

### Test 3 — 8k (resolution = 8193)

**Flux** :
1. `main.py` reçoit `resolution = 8193`
2. Passe `target_resolution = 8193`
3. `generate_satmap_v2_textured_complete` génère canvas natif
4. **Downscale INTER_AREA** (ligne 539 : `cv2.resize(..., (8193, 8193), INTER_AREA)`)
5. Sauvegarde `satmap_v2_textured_native.png` (à 8193×8193)
6. Re-sauvegarde `satmap_v2_textured_8193.png`

**Résultat attendu** : ✅ Satmap à 8193×8193 pixels

---

## 🔍 POINTS D'ATTENTION

### ⚠️ 1. Double sauvegarde (main.py:1258-1310)

**Observation** : Le code sauvegarde 2 fois :
1. `satmap_v2_textured_native.png` (sortie de la fonction)
2. `satmap_v2_textured_{resolution}.png` (après reload + optionnel resize)

**Problème potentiel** :
- Pour resolution ≠ 0 : `satmap_v2_textured_native.png` contient DÉJÀ la version downscalée
- Le nom "native" est **trompeur** car il contient la version 4k/8k

**Impact** :
- ❌ Confusion : fichier nommé "native" n'est pas natif si resolution ≠ 0
- ⚠️ Double espace disque pour mêmes données

**Exemple Zimnitrita avec resolution=4097** :
- Canvas natif : 16384×16384
- `satmap_v2_textured_native.png` : **4097×4097** (déjà downscalé, nom trompeur)
- `satmap_v2_textured_4097.png` : 4097×4097 (copie exacte)

---

### ⚠️ 2. Perte résolution native si resolution ≠ 0

**Observation** :
- Quand `resolution ≠ 0`, la fonction downscale AVANT sauvegarde
- Le canvas natif (16384×16384) est **perdu** après flip

**Code concerné (satmap_v2_textured_v2.py:534-544)** :
```python
if target_resolution is None or target_resolution == 0:
    satmap = canvas  # Native préservé
else:
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), ...)  # Native perdu
# Sauvegarde
cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))
```

**Impact** :
- ❌ Si l'utilisateur génère en 4k, le natif (16384) n'est jamais sauvegardé
- ❌ Impossible de récupérer la résolution maximale après coup

**Workaround actuel** : Générer séparément avec `resolution=0` pour avoir le natif

---

### ✅ 3. Interpolation INTER_AREA (correct)

**Code** : `cv2.INTER_AREA` utilisé partout
- Ligne 539 (satmap_v2_textured_v2.py)
- Ligne 1307 (main.py)

**Verdict** : ✅ Optimal pour downscale (préserve détails, évite aliasing)

---

### ✅ 4. Flexibilité résolutions

**Code** : Accepte `Optional[int]`

**Résolutions testables** :
- ✅ 2048 (2k)
- ✅ 4097 (4k)
- ✅ 8193 (8k)
- ✅ 16384 (16k, si canvas natif = 16384)
- ✅ N'importe quel entier > 0

**Verdict** : ✅ Architecture flexible, pas de limitation hardcodée

---

## 📋 RÉCAPITULATIF FONCTIONNEMENT

### Scénario A — Génération Native (resolution = 0)

```
User choisit: Native (0)
     ↓
main.py: target_resolution = None
     ↓
generate_satmap_v2_textured_complete:
  1. Génère canvas natif (ex: 16384×16384)
  2. Flip vertical
  3. Pas de downscale (satmap = canvas)
  4. Sauvegarde satmap_v2_textured_native.png (16384×16384)
     ↓
main.py:
  5. Reload image
  6. Sauvegarde satmap_v2_textured_16384.png (copie)
```

**Résultat** : ✅ 2 fichiers identiques à résolution native

---

### Scénario B — Génération 4k (resolution = 4097)

```
User choisit: 4k (4097)
     ↓
main.py: target_resolution = 4097
     ↓
generate_satmap_v2_textured_complete:
  1. Génère canvas natif (ex: 16384×16384)
  2. Flip vertical
  3. Downscale INTER_AREA → 4097×4097
  4. Sauvegarde satmap_v2_textured_native.png (4097×4097) ⚠️ Nom trompeur
     ↓
main.py:
  5. Reload image (4097×4097)
  6. Pas de resize (déjà à la bonne taille)
  7. Sauvegarde satmap_v2_textured_4097.png (copie)
```

**Résultat** : ✅ 2 fichiers identiques à 4097×4097  
**⚠️ Problème** : Canvas natif (16384) perdu

---

### Scénario C — Génération 8k (resolution = 8193)

```
User choisit: 8k (8193)
     ↓
main.py: target_resolution = 8193
     ↓
generate_satmap_v2_textured_complete:
  1. Génère canvas natif (ex: 16384×16384)
  2. Flip vertical
  3. Downscale INTER_AREA → 8193×8193
  4. Sauvegarde satmap_v2_textured_native.png (8193×8193) ⚠️ Nom trompeur
     ↓
main.py:
  5. Reload image (8193×8193)
  6. Pas de resize (déjà à la bonne taille)
  7. Sauvegarde satmap_v2_textured_8193.png (copie)
```

**Résultat** : ✅ 2 fichiers identiques à 8193×8193  
**⚠️ Problème** : Canvas natif (16384) perdu

---

## 🎯 RECOMMANDATIONS (non appliquées, audit seul)

### Recommandation 1 — Sauvegarder natif en premier

**Problème** : Canvas natif perdu si resolution ≠ 0

**Solution suggérée** :
```python
# Dans satmap_v2_textured_v2.py après flip (ligne 531)
canvas = np.flip(canvas, axis=0)

# TOUJOURS sauvegarder natif en premier
native_output = output_path.parent / (output_path.stem + "_native.png")
cv2.imwrite(str(native_output), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))

# Puis downscale si demandé
if target_resolution is None or target_resolution == 0:
    satmap = canvas
else:
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), ...)
    cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))
```

**Avantage** : Toujours préserver le natif + générer résolution demandée

---

### Recommandation 2 — Supprimer double sauvegarde

**Problème** : main.py re-sauvegarde inutilement

**Solution suggérée** : Supprimer lignes 1288-1310 (reload + re-save)

**Raison** : generate_satmap_v2_textured_complete sauvegarde déjà le fichier final

---

### Recommandation 3 — Clarifier nommage

**Problème** : `satmap_v2_textured_native.png` contient version downscalée si resolution ≠ 0

**Solution suggérée** :
- `satmap_v2_textured_canvas.png` → TOUJOURS natif (16384)
- `satmap_v2_textured_4097.png` → Version 4k
- `satmap_v2_textured_8193.png` → Version 8k

---

## ✅ CONCLUSION

| Question | Réponse |
|----------|---------|
| **Native fonctionne ?** | ✅ OUI (resolution=0 ou None) |
| **4k fonctionne ?** | ✅ OUI (resolution=4097) |
| **8k fonctionne ?** | ✅ OUI (resolution=8193) |
| **Résolutions indépendantes ?** | ✅ OUI (chaque valeur génère sa satmap) |
| **Interpolation correcte ?** | ✅ OUI (INTER_AREA partout) |
| **Préservation natif ?** | ⚠️ SEULEMENT si resolution=0 |
| **Nommage clair ?** | ⚠️ NON ("native" = downscalé si resolution≠0) |

**VERDICT GLOBAL** : ✅ **Les 3 résolutions fonctionnent indépendamment et correctement**

**Points d'amélioration** : Préservation natif + nommage fichiers

---

**FIN DE L'AUDIT — Aucune modification appliquée**
