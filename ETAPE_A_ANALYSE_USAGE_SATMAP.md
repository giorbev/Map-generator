# ÉTAPE A — ANALYSE USAGE SATMAP (LECTURE SEULE)

**Date** : 2026-09-27  
**Objectif** : Vérifier dépendances avant passage à UN SEUL fichier par génération

---

## 📂 1. PROJECT.JSON — Référence satmap_v2

### Normandie/project.json:38

```json
"satmap_v2": "outputs/generated/satmap_v2_textured_4097.png"
```

### Zimnitrita/project.json:431

```json
"satmap_v2": "outputs\\generated\\satmap_v2_textured_4097.png"
```

**À QUOI ÇA SERT** :
- Chemin par défaut créé lors de la création du nouveau projet (depuis main.py:190)
- **NON mis à jour** après génération satmap
- **NON lu** par main.py pour afficher/utiliser la satmap
- **USAGE RÉEL** : Probablement affiché dans l'interface ou utilisé par d'autres outils externes

**CONCLUSION** :
- ✅ **Aucune dépendance critique** au nom exact `_4097.png`
- ⚠️ Si l'interface lit ce champ pour afficher la satmap, il faudra le mettre à jour après génération
- 💡 **Proposition** : Mettre à jour `project.json["paths"]["satmap_v2"]` après génération avec le nom réel du fichier créé

---

## 🔄 2. MAIN.PY — Usage du chemin après ligne 1310

**Code (lignes 1310-1333)** :

```python
# Ligne 1310
self._log(f"[SATMAP] Sauvegardé : {out_path.name}")

# Lignes 1312-1318 — Thumbnail pour UI
Image.MAX_IMAGE_PIXELS = None
img = Image.open(str(out_path))
img.thumbnail((800, 800), Image.LANCZOS)
buf = io.BytesIO()
img.convert("RGB").save(buf, format="JPEG", quality=80)
img_b64 = base64.b64encode(buf.getvalue()).decode()

# Lignes 1320-1333 — Retour API
output_path = out_path
self._log(f"[SATMAP] Satmap v2.0 générée : {', '.join(saved)}")
return {
    "ok": True,
    "filename": output_path.name,           # ← Nom fichier (ex: "satmap_v2_textured_4097.png")
    "output_path": str(output_path),        # ← Chemin complet
    "img_b64": img_b64,                     # ← Thumbnail base64 pour aperçu UI
    "ext": "jpeg",
    "stats": {
        "size": f"{w}x{h}",
        "missing_layers": stats.get("missing_layers", 0) if stats else 0,
        "material_issues": stats.get("material_issues", 0) if stats else 0,
    }
}
```

**USAGE** :
1. **Ligne 1314** : Charger l'image depuis `out_path` pour créer thumbnail
2. **Lignes 1324-1325** : Retourner `filename` (nom) et `output_path` (chemin complet) à l'interface
3. **Ligne 1326** : Retourner thumbnail base64 pour aperçu immédiat

**DÉPENDANCES** :
- ✅ `out_path` doit exister et être lisible
- ✅ Le nom peut changer (interface recevra le nouveau nom via `filename`)
- ❌ **AUCUNE écriture dans project.json** après génération

**CONCLUSION** :
- ✅ **Aucun blocage** : l'interface reçoit dynamiquement le nom du fichier créé
- 💡 **Amélioration possible** : Écrire `output_path.name` dans `project.json["paths"]["satmap_v2"]` après génération réussie

---

## ⚠️ 3. COMPORTEMENT ACTUEL — Resolution > taille native

**Code actuel (satmap_v2_textured_v2.py:534-539)** :

```python
# Downscale si nécessaire
if target_resolution is None or target_resolution == 0:
    log(f"Résolution native : {canvas.shape[1]}×{canvas.shape[0]}")
    satmap = canvas
else:
    log(f"Downscale {canvas.shape[1]}×{canvas.shape[0]} -> {target_resolution}×{target_resolution}...")
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)
```

**PROBLÈME** : ❌ **Aucune vérification si `target_resolution > canvas natif`**

**COMPORTEMENT ACTUEL** :
- Si `target_resolution = 8193` et canvas natif = `4096×4096`
- `cv2.resize(canvas, (8193, 8193), INTER_AREA)` → **UPSCALE** ❌
- Le fichier créé fait 8193×8193 mais c'est un upscale flou (perte qualité, pixels inventés)

**EXEMPLES** :

| Canvas natif | Resolution demandée | Comportement actuel | Comportement attendu |
|--------------|---------------------|---------------------|----------------------|
| 16384×16384 | 4097 | Downscale ✅ | Downscale ✅ |
| 16384×16384 | 8193 | Downscale ✅ | Downscale ✅ |
| 16384×16384 | 32768 | **UPSCALE** ❌ | Native + WARNING ✅ |
| 4096×4096 | 8193 | **UPSCALE** ❌ | Native + WARNING ✅ |
| 2048×2048 | 4097 | **UPSCALE** ❌ | Native + WARNING ✅ |

**CONCLUSION** :
- ❌ **BUG ACTUEL** : Upscale silencieux si resolution > natif
- ✅ **Correction requise** : Ajouter vérification + WARNING

---

## 🎯 4. ÉLÉMENTS QUI DÉPENDENT DU NOM

### Cas 1 — Nom hardcodé `_16384.png`

**Recherche** :
```bash
grep -r "_16384\.png" --include="*.py" --include="*.json"
```

**Résultat** : ❌ **AUCUN fichier actif** ne dépend du nom `_16384.png`

**Preuve** :
- main.py génère dynamiquement : `f"satmap_v2_textured_{w}.png"`
- project.json contient `_4097.png` (valeur par défaut, pas mise à jour)
- Aucune autre référence dans le code actif

---

### Cas 2 — Nom hardcodé `_4097.png` ou `_8193.png`

**Fichiers concernés** :
- main.py:190 — Template nouveau projet (valeur par défaut)
- project.json (Normandie, Zimnitrita) — Configs existantes

**Impact** :
- ✅ **Aucun blocage** : Ces valeurs sont des défauts, jamais lues dynamiquement
- ⚠️ Si l'interface affiche la satmap depuis `project.json["paths"]["satmap_v2"]`, elle pourrait afficher l'ancien fichier

---

### Cas 3 — Nom `satmap_v2_textured_native.png`

**Recherche actuelle** :
```python
# main.py:1259
native_path = output_dir / "satmap_v2_textured_native.png"
```

**Nouveau comportement** :
- Resolution 0 → `satmap_v2_textured_native.png` (inchangé ✅)
- Resolution < natif → `satmap_v2_textured_{resolution}.png` (nouveau nom)
- Resolution ≥ natif → `satmap_v2_textured_native.png` (nouveau comportement)

**Impact** :
- ✅ **Nom `native.png` CONSERVÉ** pour les cas 0 et ≥natif
- ✅ **Aucune dépendance externe** à ce nom

---

## 📋 5. CORRECTIONS MINIMALES PROPOSÉES

### Correction A — Gestion resolution ≥ native

**Fichier** : satmap_v2_textured_v2.py  
**Fonction** : `generate_satmap_v2_textured_complete`  
**Ligne** : 534-539

**Code actuel** :
```python
if target_resolution is None or target_resolution == 0:
    satmap = canvas
else:
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)
```

**Code corrigé** :
```python
canvas_width = canvas.shape[1]
canvas_height = canvas.shape[0]

if target_resolution is None or target_resolution == 0:
    # Mode native explicite
    log(f"Résolution native : {canvas_width}×{canvas_height}")
    satmap = canvas
    final_resolution = 0  # Marqueur "native"
elif target_resolution >= canvas_width:
    # Pas d'upscale : utiliser native
    log(f"⚠️ WARNING: Résolution demandée {target_resolution} ≥ native {canvas_width}, satmap native utilisée")
    satmap = canvas
    final_resolution = 0  # Marqueur "native"
else:
    # Downscale
    log(f"Downscale {canvas_width}×{canvas_height} -> {target_resolution}×{target_resolution}...")
    satmap = cv2.resize(canvas, (target_resolution, target_resolution), interpolation=cv2.INTER_AREA)
    final_resolution = target_resolution
```

---

### Correction B — Nommage fichier unique

**Fichier** : satmap_v2_textured_v2.py  
**Fonction** : `generate_satmap_v2_textured_complete`  
**Ligne** : 541-544

**Code actuel** :
```python
log(f"Sauvegarde : {output_path}")
output_path.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(output_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))
```

**Code corrigé** :
```python
# Nommage selon règle
if final_resolution == 0:
    # Native
    filename = "satmap_v2_textured_native.png"
else:
    # Downscale
    filename = f"satmap_v2_textured_{final_resolution}.png"

final_path = output_path.parent / filename
log(f"Sauvegarde : {final_path} ({satmap.shape[1]}×{satmap.shape[0]})")
final_path.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(final_path), cv2.cvtColor(satmap, cv2.COLOR_RGB2BGR))
```

**Retour** : Retourner `final_path` au lieu de `output_path`

---

### Correction C — Suppression re-sauvegarde main.py

**Fichier** : main.py  
**Fonction** : `generate_satmap_v2`  
**Lignes** : 1259, 1288-1310

**Code à supprimer** :
```python
# Ligne 1259
native_path = output_dir / "satmap_v2_textured_native.png"

# Lignes 1288-1310
# Downscaler vers les résolutions cibles
import cv2 as _cv2_sat
native_img = _cv2_sat.imread(str(native_path))
saved = []
...
```

**Code de remplacement** :
```python
# Après l'appel à generate_satmap_v2_textured_complete (ligne 1284)
# La fonction retourne maintenant le chemin du fichier créé

if not stats or "output_path" not in stats:
    return {"ok": False, "error": "Fichier satmap non généré"}

output_path = Path(stats["output_path"])
if not output_path.exists():
    return {"ok": False, "error": f"Fichier non trouvé : {output_path}"}

# Thumbnail (inchangé, utilise output_path au lieu de out_path)
Image.MAX_IMAGE_PIXELS = None
img = Image.open(str(output_path))
img.thumbnail((800, 800), Image.LANCZOS)
...
```

---

### Correction D — Mise à jour project.json (optionnel)

**Fichier** : main.py  
**Fonction** : `generate_satmap_v2`  
**Ligne** : Après 1333 (avant return)

**Code ajouté** :
```python
# Mettre à jour project.json avec le nom du fichier généré
try:
    proj = Path(_session["current_project_path"])
    proj_json = proj / "project.json"
    if proj_json.exists():
        with open(proj_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Chemin relatif au projet
        rel_path = output_path.relative_to(proj).as_posix()
        data["paths"]["satmap_v2"] = rel_path
        
        with open(proj_json, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        self._log(f"[SATMAP] project.json mis à jour : satmap_v2 = {rel_path}")
except Exception as e:
    # Non bloquant
    self._log(f"⚠️ Mise à jour project.json échouée : {e}")
```

---

## ✅ 6. CONCLUSION ÉTAPE A

### Blocages détectés

❌ **AUCUN blocage** — Passage à UN SEUL fichier possible

### Dépendances au nom

| Élément | Dépendance | Action |
|---------|------------|--------|
| project.json (défaut) | `_4097.png` | ✅ Aucune — valeur jamais lue |
| main.py retour API | Nom dynamique via `out_path.name` | ✅ Aucune — reçoit nouveau nom |
| Thumbnail UI | Lit depuis `out_path` | ✅ Aucune — nouveau chemin passé |
| Codes externes | Lecture project.json ? | ⚠️ Optionnel : mettre à jour après génération |

### Bugs détectés

| Bug | Impact | Correction |
|-----|--------|------------|
| ❌ Upscale silencieux si resolution > natif | Fichier upscalé (perte qualité) | Vérifier + WARNING + native |
| ❌ Double sauvegarde | Gaspillage disque + temps | Supprimer re-save main.py |
| ⚠️ project.json non mis à jour | Interface peut afficher ancien fichier | Optionnel : update après génération |

---

**✅ ÉTAPE A TERMINÉE — Aucun blocage, passage ÉTAPE B validé**

**CORRECTIONS MINIMALES** :
- Correction A : Gestion resolution ≥ native (OBLIGATOIRE)
- Correction B : Nommage fichier unique (OBLIGATOIRE)
- Correction C : Suppression re-sauvegarde (OBLIGATOIRE)
- Correction D : Mise à jour project.json (OPTIONNEL)
