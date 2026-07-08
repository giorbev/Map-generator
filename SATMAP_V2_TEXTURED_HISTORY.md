# `satmap_v2_textured.py` — Historique de construction
> Extrait de la conversation QTRE/TMAT — Messages 1 à 894 (3–6 juillet 2026)

---

## Naissance du fichier
**Messages ~408–410 — 5 juillet 2026, ~07h54**

Créé lors d'une refonte complète du pipeline satmap. L'ancien système (QTRE) avait un angle mort : les blocs terrain avec 6–7 textures simultanées (~6,4 % de la map) n'étaient pas couverts. La solution : lire directement les fichiers `Terrain_N_layer.dds` (poids GPU) et les chunks `LRS2` dans les `.ttile` (liste des matériaux par bloc).

### Modules créés en parallèle

| Module | Rôle |
|--------|------|
| `layer_dds_reader.py` | Lecture `.dds` R32_UINT depuis `.EditorData` |
| `lrs2_parser.py` | Parser chunk LRS2 (little-endian) |
| `terrain_materials_parser.py` | Parser `terrain_materials_list.txt` (ordre exact LRS2) |
| `emat_scanner_simple.py` | Scanner `.emat` simplifié (1 dossier) |
| `satmap_v2_textured.py` | **Générateur satmap v2.0** |
| `satmap_verifiers.py` | Vérificateurs au démarrage (layers + matériaux) |

### Contenu initial (~460 lignes)

- Fonction principale `generate_satmap_v2_textured_complete()`
- **Mode "colors"** : rendu rapide par couleurs unies (`tint_srgb`)
- **Mode "textured"** : rendu qualitatif avec textures middle BCR + tiling + tint
- Cache textures en mémoire
- Fallback `Dirt_01` pour textures forest manquantes
- Paramètre `verbose=False` (logs conditionnels pour Streamlit)

### Pipeline complet au départ

```
1. Scanner .emat (UNE FOIS)
   ├─ 66 fichiers .emat dans data/Textures_ArmaReforger/emat/
   ├─ Extraction : middle_bcr, tiling_scale, tint_srgb
   └─ catalog.json enrichi

2. Génération satmap
   ├─ Charger terrain_materials_list.txt (55 surfaces, ordre exact LRS2)
   ├─ Charger catalog.json (paramètres textures)
   ├─ Pour chaque tuile (1005) :
   │   ├─ Lire Terrain_N_layer.dds (.EditorData) → Poids GPU uint32
   │   ├─ Parser Terrain_N.ttile (.Data)         → LRS2 matériaux
   │   └─ Pour chaque bloc (4×4) :
   │       └─ Blender 1–7 textures avec poids
   └─ Downscale 16k → 4k → Satmap finale
```

---

## Bugs corrigés (5 juillet 2026)

### Bug 1 — Crash à l'import Streamlit
**Messages 437–440**

`sys.stdout = io.TextIOWrapper(...)` en tête de fichier crashait dès que Streamlit importait le module.

**Fix :** Suppression de la ligne + remplacement de tous les `print()` par une fonction `log(msg, verbose)` conditionnelle.

---

### Bug 2 — Satmap entièrement noire
**Messages 451–463**

Le parser LRS2 utilisait le mauvais endianness.

```
n (big-endian)    = 768  ← absurde
n (little-endian) = 3    ← correct
```

**Fix :** Parser LRS2 corrigé en **little-endian** (`struct.unpack_from('<H', ...)`).

---

### Bug 3 — Une seule tuile générée, reste noir
**Messages 465–473**

Le chunk LRS2 stocke des index **globaux** à la map entière, pas locaux à la tuile.

```
Tuile 0 : index = 0  → Bloc (0, 0) ✅
Tuile 1 : index = 4  → Bloc (4, 0) ❌ hors limites 0–3 !
Tuile 2 : index = 8  → Bloc (8, 0) ❌
```

**Fix :** Conversion index global → local : `bx_local = bx_global % 4`

---

### Bug 4 — Couleurs toutes blanches
**Messages 487–558**

Le scanner `.emat` cherchait `MiddleColor` mais les fichiers utilisent `Color` ou `Diffuse`. Résultat : `tint_srgb = (1, 1, 1, 1)` = blanc pour la majorité des surfaces.

De plus, le code utilisait `avg_color` en priorité au lieu de `tint_srgb`.

**Fix :** Priorité changée → `tint_srgb` calculé selon la méthode TilW :
```python
color_m = MiddleColor  # RGBA linéaire
color_d = Color        # RGBA linéaire
color = linear_to_srgb(color_m * color_d)
```

---

### Bug 5 — 17 tuiles toujours noires (zones hors-map)
**Messages 560–562**

Certaines tuiles n'ont pas de fichier `layer.dds` (zones hors limites jouables).

**Fix :** Ajout d'un **fallback supertexture** : si `layer.dds` absent, utiliser `Terrain_N_supertexture.dds` (satmap baked par Workbench).

---

### Bug 6 — Artefacts géométriques (blocs pixelisés)
**Messages 839–841 — 6 juillet 2026, ~10h27**

La palette de matériaux était appliquée au niveau de la **tuile entière**, alors qu'elle est **locale à chaque bloc**. Les poids `w0–w6` d'un bloc correspondent aux `mat_ids[0–6]` *de ce bloc uniquement*.

**Fix :** Recalcul de la palette pour chaque bloc individuellement.

---

## Améliorations intégrées (6 juillet 2026)

### Correction de contraste automatique
**Messages 882–887 — ~11h22**

Ajout d'une courbe de contraste modérée après le downscale, ciblant une luminosité moyenne ~120/255 :

```python
# Correction courbe de contraste (modérée)
satmap_f = satmap.astype(np.float32) / 255.0
satmap_f = np.clip(satmap_f * 1.25 + 0.04, 0, 1)
satmap_f = np.power(satmap_f, 0.78)
satmap = np.clip(satmap_f * 255, 0, 255).astype(np.uint8)
```

> ⚠️ **Revertée au message 894** — supprimée à la demande (sortie brute préférée).

---

### Vérificateurs au démarrage
**Messages 888–892 — ~11h30**

Intégration de `satmap_verifiers.py` dans `generate_satmap_v2_textured_complete()`, appelée avant toute génération :

**1. `check_missing_layers(editor_data_dir, data_dir)`**
- Scanne toutes les tuiles `.ttile`
- Pour chaque tuile sans `layer.dds` :
  - Si `.edds` présent → reconstruit via `rebuild_editor_layer()`
  - Sinon → génère un layer vide uniforme
- Log : `N OK | N reconstruits | N générés vides`

**2. `check_material_table(surfaces_list, catalog)`**
- Vérifie que chaque surface a un `tint_srgb`
- Log les matériaux absents du catalogue
- Ne bloque pas la génération (warning seulement)

---

## État au message 894
**6 juillet 2026, 11h43**

| Indicateur | Valeur |
|---|---|
| Layers présents | **1024 / 1024** ✅ |
| Blocs couverts | **100 %** (1–7 textures) ✅ |
| Couleurs | `tint_srgb` (méthode TilW) ✅ |
| Palette par bloc | Locale ✅ |
| Vérificateurs | Intégrés ✅ |
| Correction contraste | Revertée (sortie brute) |
| Warnings restants | 3 matériaux sans tint (`zi_MountainGrass_02.emat` absent du catalogue) |

---

## Format `layer.dds` (rappel)

```
Image R32_UINT, 512×512 pixels
Chaque pixel encode 7 poids sur 5 bits :
  bits  0–4  : w1
  bits  5–9  : w2
  bits 10–14 : w3
  bits 15–19 : w4
  bits 20–24 : w5
  bits 25–29 : w6
  w0 = 31 − (w1+w2+…+w6)   ← calculé, implicite

extract_all_weights() retourne (512, 512, 7)
  canal 0 = w0 (déjà calculé)
  canaux 1–6 = w1..w6
```
