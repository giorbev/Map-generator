# Satmap Export — Implémentation complète (Phases 1-3)

**Date** : 2026-07-03  
**Statut** : ✅ Phase 1-2-3 implémentées et testées

---

## 📦 Résumé des phases

| Phase | Fonctionnalité | Statut | Fichier principal |
|-------|---------------|--------|-------------------|
| **1** | Catalogue textures | ✅ Testé | [reforger_satmap_export.py](../reforger_satmap_export.py) |
| **2** | Export masques | ✅ Implémenté | [reforger_mask_export.py](../reforger_mask_export.py) |
| **3** | Validation | ✅ Implémenté | [reforger_mask_export.py](../reforger_mask_export.py) |

---

## Phase 1 : Catalogue de textures ✅

### Fonctionnalités

- ✅ Scanner `texturesArmaReforger/vanilla/` et `customs/`
- ✅ Convention `zi_` (héritage automatique)
- ✅ Résolution PNG middle BCR → couleur moyenne
- ✅ Croisement avec `.terr` du monde
- ✅ Préservation entrées `manual` et champs `tint`

### Fichiers

- **Module** : [reforger_satmap_export.py](../reforger_satmap_export.py)
- **Tests** : [test_satmap_catalog.py](../test_satmap_catalog.py) ✅ PASSÉS
- **Guide** : [SATMAP_GUIDE_UTILISATEUR.md](SATMAP_GUIDE_UTILISATEUR.md)
- **Données** : `texturesArmaReforger/catalog.json`

### UI (app.py)

**Onglet** : "🛰️ Satmap Export"

**Sections** :
1. Construction du catalogue (bouton "🔨 Scanner")
2. Croisement avec .terr (bouton "✓ Vérifier")
3. État du catalogue (tableau filtrable)

---

## Phase 2 : Export masques ✅

### Fonctionnalités

- ✅ Décodeurs QTRE variantes "poids complets" (pas argmax)
- ✅ Splat des poids dans canvas global par surface
- ✅ Export PNG 8-bit (0-255 = 0-100% couverture)
- ✅ Gestion résolutions hétérogènes (quadtree 128×128, array 32×32)
- ✅ Invariant somme=1 validé avec carte d'erreur
- ✅ Barre de progression tuile par tuile
- ✅ Manifest JSON (surfaces, résolution, warnings)

### Algorithme

```python
1. parse_terr_materials() → liste surfaces
2. Parse métadonnées terrain (.bterr) → dimensions
3. Allocation lazy : canvases[mat_id] float32 (H, W)
4. Pour chaque .ttile :
     Pour chaque bloc (bx, by, mat_ids, qtre) :
         weights = decode_qtre_block_weights(mat_ids, qtre, (128, 128))
         Pour chaque (mat_id, grid) :
             canvases[mat_id][y0:y1, x0:x1] = grid
5. Vérification somme = 1 → error_map
6. Export PNG par canvas : float32 [0-1] → uint8 [0-255]
```

### Décodeurs QTRE

| Fonction | Format | Résolution native | Retour |
|----------|--------|-------------------|--------|
| `decode_qtre_2mat_weights()` | Quadtree | 128×128 | `{mat0: grid, mat1: 1-grid}` |
| `decode_qtre_3mat_weights()` | Array 32×32×4 | 32×32 | `{mat0: w0, mat1: w1, mat2: w2}` |
| `decode_qtre_4mat_weights()` | Array 32×32×6 | 32×32 | `{mat0..4: w0..4}` |
| `decode_qtre_block_weights()` | Dispatcher | Unifié 128×128 | `{mat_id: grid}` |

**Rééchantillonnage** : `scipy.ndimage.zoom(..., order=0)` nearest pour 32→128

### Fichiers

- **Module** : [reforger_mask_export.py](../reforger_mask_export.py)
- **Tests** : [test_mask_export.py](../test_mask_export.py) ✅ PASSÉS

### UI (app.py)

**Section 4** : Export masques

**Inputs** :
- Dossier du monde (contient .terr, .bterr, .ttile)
- Dossier de sortie
- Checkbox "Flip Y" (si masques inversés)

**Bouton** : "📤 Exporter"

**Résultat** :
- `<out_dir>/masks/<timestamp>/<surface>.png` (un PNG par surface)
- `manifest.json` (métadonnées)
- Métriques : surfaces, résolution, warnings
- Carte d'erreur si invariant somme≠1 violé

---

## Phase 3 : Validation ✅

### Fonctionnalités

- ✅ Comparaison pixel-à-pixel avec export manuel Workbench
- ✅ Test automatique 4 orientations (flip X/Y)
- ✅ Rééchantillonnage si résolutions différentes
- ✅ Heatmap diff (×5 pour visibilité)
- ✅ Métriques : erreur moyenne, max, % identiques ±1

### Critères de succès

| Critère | Seuil | Signification |
|---------|-------|---------------|
| `pct_identical` | ≥ 99.9% | Match quasi-parfait |
| `max_error` | ≤ 2 (sur 255) | Erreur max acceptable |
| `mean_error` | < 0.1 | Décodage correct |

### Fichiers

- **Module** : [reforger_mask_export.py](../reforger_mask_export.py)
- **Fonction** : `compare_masks(reconstructed, reference)`

### UI (app.py)

**Section 5** : Validation

**Inputs** :
- Masque reconstruit (notre export)
- Masque référence (export manuel Workbench)

**Bouton** : "✓ Comparer"

**Résultat** :
- Meilleure orientation (flip X/Y détecté automatiquement)
- Métriques de différence
- Heatmap diff
- Verdict : Match parfait / partiel / incorrect

---

## 🔧 Réutilisation code existant

### Depuis reforger_texture_budget.py

✅ **`parse_terr_materials()`** — Liste surfaces  
✅ **`find_terr_files()`** — Recherche .terr  
✅ **`_iter_tmat_bmats()`** — Itération blocs TMAT/QTRE  
✅ **`_MAT_STEM_TO_ROLE`** — Mapping stem → rôle  

### Variantes créées (non destructives)

**Nouveaux décodeurs** dans [reforger_mask_export.py](../reforger_mask_export.py) :
- `decode_qtre_2mat_weights()` — retourne poids, pas argmax
- `decode_qtre_3mat_weights()` — retourne poids, pas argmax
- `decode_qtre_4mat_weights()` — retourne poids, pas argmax
- `decode_qtre_block_weights()` — dispatcher unifié

**Anciens décodeurs** dans [reforger_texture_budget.py](../reforger_texture_budget.py) :
- `_decode_qtre_2mat()` — argmax uniquement (INCHANGÉ)
- `_decode_qtre_3mat()` — argmax uniquement (INCHANGÉ)
- `_decode_qtre_4mat()` — argmax uniquement (INCHANGÉ)

➡️ **Pas de régression** : pipeline existant non affecté

---

## 📁 Structure finale

```
h:\logiciel perso\Map generator\
├── app.py                          # UI Streamlit (onglet Satmap ajouté)
├── reforger_texture_budget.py      # Module existant (INCHANGÉ)
├── reforger_satmap_export.py       # Phase 1 : Catalogue
├── reforger_mask_export.py         # Phase 2-3 : Export + Validation
├── test_satmap_catalog.py          # Tests Phase 1 ✅
├── test_mask_export.py             # Tests Phase 2-3 ✅
├── texturesArmaReforger/
│   ├── README.md
│   ├── catalog.json                # Généré par scanner
│   ├── vanilla/
│   │   ├── textures/               # PNG middle BCR vanilla
│   │   └── emat/                   # .emat vanilla
│   └── customs/
│       ├── textures/               # PNG middle BCR custom
│       └── emat/                   # .emat custom
├── Docs/
│   ├── SATMAP_EXPORT_PHASE1.md     # Doc Phase 1
│   ├── SATMAP_GUIDE_UTILISATEUR.md # Guide utilisateur
│   └── SATMAP_EXPORT_COMPLET.md    # Ce fichier
└── <projet>/
    ├── exports/
    │   └── masks/
    │       └── <timestamp>/
    │           ├── <surface>.png   # Masques exportés
    │           └── manifest.json   # Métadonnées
    └── reports/
        ├── catalog_scan.txt
        └── catalog_terr_verify.txt
```

---

## 🚀 Workflow complet

### 1. Préparer le catalogue (une seule fois)

1. Remplir `texturesArmaReforger/vanilla/` et `customs/`
2. Ouvrir **Map Generator Pro** (`streamlit run app.py`)
3. Onglet **"🛰️ Satmap Export"**
4. Section 1 : Cliquer **"🔨 Scanner"**
5. Section 2 : Vérifier contre le `.terr` de votre monde

### 2. Exporter les masques

1. Section 4 : Entrer le dossier de votre monde Reforger
   - Exemple : `I:/reforger_travail/MonMonde/Terrains/MonMonde`
2. Choisir dossier de sortie
3. Cliquer **"📤 Exporter"**
4. Attendre la barre de progression (peut être long sur grande carte)
5. Consulter warnings/erreurs éventuels

### 3. Valider le décodage (optionnel)

1. Exporter **UN** masque manuellement via Workbench (référence)
2. Section 5 : Fournir les 2 chemins (reconstruit + référence)
3. Cliquer **"✓ Comparer"**
4. Vérifier le verdict (Match parfait / partiel / incorrect)
5. Si flip détecté : cocher "Flip Y" et ré-exporter

---

## ⚙️ Métadonnées terrain (TODO)

**Actuellement** : valeurs par défaut hardcodées dans `parse_bterr_metadata()` :

```python
{
    "tiles_x": 1,
    "tiles_y": 1,
    "blocks_per_tile_x": 4,
    "blocks_per_tile_y": 4,
    "surface_res_px": 128,
}
```

**À implémenter** : parseur binaire `.bterr` pour lire :
- Nombre de tuiles X/Y
- Blocs par tuile X/Y
- Résolution masque par bloc

**Impact** : export actuel fonctionne si la carte = 1 tuile 4×4 blocs. Pour cartes multi-tuiles, le parseur `.bterr` est **requis**.

---

## 🐛 Cas limites gérés

✅ **Résolutions hétérogènes** : quadtree 128×128 et array 32×32 → rééchantillonnage nearest  
✅ **Surface de base implicite** : poids = 1 - somme(autres)  
✅ **Invariant somme=1** : carte d'erreur + warning si > 2/255  
✅ **Flip Y** : paramètre ajustable + détection auto en validation  
✅ **Blocs absents** : poids 0, pas d'erreur  
✅ **Surface hors catalogue** : export quand même + warning  
✅ **Allocation lazy** : canvas créé seulement si surface contribue  

---

## 📊 Résultats attendus

### Export réussi

- Un PNG 8-bit par surface peinte (0-255 = 0-100%)
- `manifest.json` avec liste des surfaces + résolution
- Warnings si surfaces hors catalogue
- Carte d'erreur si somme≠1 (debug QTRE)

### Validation réussie

- `pct_identical ≥ 99.9%`
- `max_error ≤ 2`
- Heatmap diff quasi noire (pas de différence visible)

➡️ **Critère de succès** : match pixel-perfect avec export manuel Workbench

---

## 🔄 Prochaines étapes (hors périmètre actuel)

- [ ] Parseur `.bterr` pour métadonnées terrain réelles
- [ ] Support cartes multi-tuiles (nécessite parseur `.bterr`)
- [ ] Onglet Satmap (composition masques × textures middle)
- [ ] Export atlas texture composite
- [ ] Import retour vers Workbench (écriture `.ttile`)

---

## 📚 Références

- [PIPELINE_V2_FLOW_FIX.md](PIPELINE_V2_FLOW_FIX.md) — Pipeline textures v2.0.0
- [reforger_texture_budget.py](../reforger_texture_budget.py) — Module QTRE existant
- [reforger_satmap_export.py](../reforger_satmap_export.py) — Phase 1 catalogue
- [reforger_mask_export.py](../reforger_mask_export.py) — Phase 2-3 export/validation
- [SATMAP_GUIDE_UTILISATEUR.md](SATMAP_GUIDE_UTILISATEUR.md) — Guide utilisateur
