# Satmap Export — Corrections Session 2 (2026-07-03)

**Session** : Après RAZ à 0%  
**Statut** : ✅ Corrections appliquées et testées

---

## 🔧 Corrections appliquées

### 1. Chemins dossiers corrigés ✅

**Problème** : Dossiers avec majuscules (`Vanilla`, `Customs`) mais code cherchait minuscules

**Ancien** :
```python
VANILLA_EMAT_DIR = CATALOG_ROOT / "vanilla" / "emat"
CUSTOM_EMAT_DIR = CATALOG_ROOT / "customs" / "emat"
```

**Nouveau** :
```python
VANILLA_EMAT_DIR = CATALOG_ROOT / "Vanilla"  # .emat directement dans Vanilla/
CUSTOM_EMAT_DIR = CATALOG_ROOT / "Customs"   # .emat directement dans Customs/
VANILLA_TEXTURES_DIR = CATALOG_ROOT / "Vanilla" / "textures"
CUSTOM_TEXTURES_DIR = CATALOG_ROOT / "Customs" / "Textures"
```

**Structure réelle** :
```
data/Textures_ArmaReforger/
├── Vanilla/
│   ├── *.emat (52 fichiers)
│   └── textures/
│       └── *_Middle_BCR.jpg
└── Customs/
    ├── *.emat (8 fichiers ZI_)
    └── Textures/
```

---

### 2. Chemin .terr corrigé ✅

**Ancien exemple** : `I:/reforger_travail/Zimnitrita_map/Terrains/Zimnitrita/Zimnitrita.terr`  
**Nouveau exemple** : `I:/reforger_travail/Zimnitrita_map/World/Zimnitrita/Terrain/Terrain.terr`

**Format standard Reforger** : `<Projet>/World/<NomMonde>/Terrain/Terrain.terr`

⚠️ Le fichier s'appelle toujours **`Terrain.terr`** (pas le nom du monde)

**Modifié dans** :
- [app.py](../app.py) — Message d'aide UI
- [Docs/SATMAP_GUIDE_UTILISATEUR.md](SATMAP_GUIDE_UTILISATEUR.md)
- [data/Textures_ArmaReforger/README.md](../data/Textures_ArmaReforger/README.md)

---

### 3. Mapping manuel textures créé ✅

**Problème** : Noms `.emat` ≠ noms PNG middle BCR

**Exemples** :
- `Grass_02.emat` → `Grass_01_Middle_BCR.jpg` (même texture)
- `Cobblestone_01_Wave.emat` → `WaveCobblestone_01_Middle_BCR.jpg` (nom différent)
- Toutes les textures `Forest*` → `Dirt_01_Middle_BCR.jpg` (sol forêt)

**Solution** : Fichier [texture_mapping.json](../data/Textures_ArmaReforger/texture_mapping.json)

```json
{
  "mappings": {
    "Grass_02.emat": "Grass_01_Middle_BCR.jpg",
    "ForestClearing_Deciduous_01.emat": "Dirt_01_Middle_BCR.jpg",
    "Rock_01.emat": "Debris_Rock_01_Middle_BCR.jpg"
  },
  "manual_colors": {
    "SulfurStream_01_bed.emat": "#a47012"
  }
}
```

**Résultat** :
- ✅ **Avant** : 56/60 surfaces en fallback magenta
- ✅ **Après** : 4/60 surfaces en fallback (ZI customs sans PNG)

---

### 4. Support couleurs manuelles ajouté ✅

**Use case** : Textures custom avec couleur spécifique sans PNG middle

**Format** :
```json
{
  "manual_colors": {
    "SulfurStream_01_bed.emat": "#a47012"
  }
}
```

**Priorité couleur** :
1. Couleur manuelle (`manual_colors`)
2. Calcul depuis PNG middle
3. Fallback magenta

**Implémentation** :
- Fonction `hex_to_rgb()` pour conversion `#RRGGBB` → `[R, G, B]`
- `load_texture_mapping()` retourne `(mappings, manual_colors)`
- `scan_vanilla_textures()` applique couleur manuelle en priorité

**Exemple testé** :
```python
SulfurStream_01_bed.emat:
  avg_color: [164, 112, 18]  # = #a47012 ✅
  middle_bcr: Vanilla/textures/Dirt_01_Middle_BCR.jpg
```

---

### 5. Corrections de mapping utilisateur ✅

**Basées sur analyse des .emat réels** :

| .emat | Middle BCR corrigé | Raison |
|-------|-------------------|--------|
| Toutes `Forest*` | `Dirt_01_Middle_BCR.jpg` | Sol de forêt (pas ForestClearing) |
| `Rock_01.emat` | `Debris_Rock_01_Middle_BCR.jpg` | Roche = débris rocheux |
| `SulfurStream_01_bed.emat` | `Dirt_01_Middle_BCR.jpg` + `#a47012` | Lit de rivière sulfureuse |

**Total corrigé** : 14 textures Forest + 1 Rock + 1 SulfurStream = **16 corrections**

---

## 📊 Résultats finaux

### Scan du catalogue

```
✅ Scan terminé
   Total :      60
   Vanilla :    52
   Custom :     8
   Convention : 8 (héritage zi_)
   Fallback :   4 (ZI customs sans PNG)
```

### Surfaces résolues : 56/60 (93%)

**Fallback restants** (4) :
- `ZI_Crop_Field_03.emat`
- `ZI_Crop_Field_04.emat`
- `ZI_Crop_Field_Cut_01.emat`
- `ZI_Crop_Field_Cut_02.emat`

**Solutions** :
1. Ajouter PNG middle dans `Customs/Textures/`
2. Ou ajouter mapping vers PNG vanilla existant
3. Ou ajouter couleurs manuelles dans `manual_colors`

---

## 🧪 Tests validés

### Test 1 : Import module ✅
```bash
python test_satmap_catalog.py
```
Résultat : TOUS LES TESTS PASSÉS (6/6)

### Test 2 : Couleur manuelle ✅
```bash
python -c "import json; d=json.load(open('data/Textures_ArmaReforger/catalog.json')); \
  print(d['SulfurStream_01_bed.emat']['avg_color'])"
```
Résultat : `[164, 112, 18]` = `#a47012` ✅

### Test 3 : Mapping Forest ✅
```bash
python -c "import json; d=json.load(open('data/Textures_ArmaReforger/catalog.json')); \
  print(d['ForestClearing_Deciduous_01.emat']['middle_bcr'])"
```
Résultat : `Vanilla/textures/Dirt_01_Middle_BCR.jpg` ✅

---

## 📁 Fichiers modifiés

### Code source
- [reforger_satmap_export.py](../reforger_satmap_export.py)
  - Chemins dossiers corrigés (Vanilla, Customs)
  - Support couleurs manuelles (`hex_to_rgb()`)
  - `load_texture_mapping()` retourne `(mappings, manual_colors)`
  - Priorité couleur manuelle > PNG > fallback

### Données
- [texture_mapping.json](../data/Textures_ArmaReforger/texture_mapping.json) **(NOUVEAU)**
  - 56 mappings `.emat` → PNG middle BCR
  - 1 couleur manuelle (SulfurStream)
  - Corrections Forest, Rock, SulfurStream

### Documentation
- [app.py](../app.py) — Exemples chemin .terr
- [SATMAP_GUIDE_UTILISATEUR.md](SATMAP_GUIDE_UTILISATEUR.md) — Chemin .terr
- [data/Textures_ArmaReforger/README.md](../data/Textures_ArmaReforger/README.md) — Structure

---

## 🎯 Prochaines étapes

### Priorité 1 : Tester vérification .terr

Dans l'UI Streamlit :
1. Onglet "🛰️ Satmap Export"
2. Section 1 : Cliquer "🔨 Scanner" → 60 surfaces cataloguées
3. Section 2 : Entrer chemin `.terr` :
   ```
   I:/reforger_travail/Zimnitrita_map/World/Zimnitrita/Terrain/Terrain.terr
   ```
4. Cliquer "✓ Vérifier"

**Résultat attendu** : Toutes les surfaces du .terr trouvées dans le catalogue

### Priorité 2 : Résoudre les 4 fallback ZI

**Option A** : Ajouter PNG middle dans `Customs/Textures/`
```
ZI_Crop_Field_03_Middle_BCR.jpg
ZI_Crop_Field_04_Middle_BCR.jpg
ZI_Crop_Field_Cut_01_Middle_BCR.jpg
ZI_Crop_Field_Cut_02_Middle_BCR.jpg
```

**Option B** : Mapper vers PNG vanilla existants (déjà fait)
```json
"ZI_Crop_Field_03.emat": "Crop_Field_01_Middle_BCR.jpg"
```

**Option C** : Couleurs manuelles
```json
"manual_colors": {
  "ZI_Crop_Field_03.emat": "#8a7f5f"
}
```

### Priorité 3 : Export masques (Phase 2)

Une fois la vérification validée :
1. Section 4 : Export masques
2. Entrer dossier monde + dossier sortie
3. Cliquer "📤 Exporter"

---

## 📚 Références

- [SATMAP_EXPORT_COMPLET.md](SATMAP_EXPORT_COMPLET.md) — Doc technique phases 1-3
- [SATMAP_GUIDE_UTILISATEUR.md](SATMAP_GUIDE_UTILISATEUR.md) — Guide utilisateur
- [texture_mapping.json](../data/Textures_ArmaReforger/texture_mapping.json) — Mapping manuel
