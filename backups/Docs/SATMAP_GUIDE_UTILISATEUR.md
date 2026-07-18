# Guide utilisateur — Satmap Export (Phase 1)

## 🎯 Objectif

Construire un catalogue des surfaces Reforger pour préparer l'export des masques depuis votre monde.

## 📋 Prérequis

### 1. Structure des dossiers de textures

Créez la structure suivante dans votre projet Map Generator :

```
h:\logiciel perso\Map generator\
└── texturesArmaReforger/
    ├── vanilla/
    │   ├── textures/     # PNG middle BCR des surfaces vanilla
    │   └── emat/         # Copies des .emat vanilla
    └── customs/
        ├── textures/     # PNG middle BCR de vos surfaces custom
        └── emat/         # Vos .emat custom (mod)
```

### 2. Remplir les dossiers

#### Vanilla (surfaces officielles Reforger)

**Source** : dossier d'installation Reforger  
`<ReforgerInstall>/ArmaReforger/resourceDatabase/Terrain/Surfaces/`

1. **Copiez** tous les `.emat` dans `texturesArmaReforger/vanilla/emat/`

2. **Exportez** les PNG middle BCR depuis le Workbench :
   - Ouvrir chaque surface dans le Workbench
   - Export de la texture BCR (base color roughness)
   - Sauvegarder dans `texturesArmaReforger/vanilla/textures/`
   - **Nom du PNG = nom du .emat** (ex: `Grass_01.png` pour `Grass_01.emat`)

#### Custom (vos surfaces de mod)

**Source** : votre mod/addon Reforger

1. **Copiez** tous vos `.emat` custom dans `texturesArmaReforger/customs/emat/`

2. **Convention zi_** (recommandée) :
   - Si votre surface hérite d'une vanilla, préfixez `zi_`
   - Exemple : `zi_Grass_01.emat` hérite automatiquement de `Grass_01.emat`
   - ✅ **Pas besoin de PNG** pour les héritages → couleur/PNG copiés du parent

3. **Créations custom** (pas d'héritage) :
   - Exportez le PNG middle BCR depuis le Workbench
   - Sauvegarder dans `texturesArmaReforger/customs/textures/`
   - **Nom du PNG = nom du .emat** (ex: `zi_MonSol.png` pour `zi_MonSol.emat`)

## 🚀 Utilisation dans l'application

### Étape 1 : Scanner les textures

1. Ouvrez **Map Generator Pro** (`streamlit run app.py`)
2. Chargez un projet (ou travaillez sans projet)
3. Allez dans l'onglet **"🛰️ Satmap Export"**
4. Section **"1. Construction du catalogue"**
5. Cliquez sur **"🔨 Scanner"**

**Résultat** :
- Catalogue construit (`texturesArmaReforger/catalog.json`)
- Métriques affichées : Total / Vanilla / Custom / Fallback
- Rapport sauvegardé dans `<projet>/reports/catalog_scan.txt`

**Si des surfaces sont en fallback (magenta)** :
- C'est que le PNG middle BCR est manquant
- Vérifiez le nom du PNG (doit correspondre au .emat)
- Ajoutez le PNG manquant et re-scannez

### Étape 2 : Vérifier avec votre monde Reforger

1. Section **"2. Croisement avec le monde Reforger"**
2. **Entrez le chemin vers votre fichier .terr** :
   ```
   I:/reforger_travail/MonMonde/World/MonMonde/Terrain/Terrain.terr
   ```
   ⚠️ Le fichier s'appelle toujours **Terrain.terr** et se trouve dans `World/<NomMonde>/Terrain/`

3. Cliquez sur **"✓ Vérifier"**

**Résultat** :
- Couverture % (surfaces du .terr présentes dans le catalogue)
- Liste des surfaces **manquantes** (à ajouter au catalogue)
- Rapport sauvegardé dans `<projet>/reports/catalog_terr_verify.txt`

**Si des surfaces sont manquantes** :
1. Identifiez le .emat correspondant (depuis le message d'erreur)
2. Ajoutez-le dans `customs/emat/` (ou `vanilla/emat/` si vanilla)
3. Si ce n'est pas un héritage zi_, ajoutez aussi le PNG middle BCR
4. Re-scannez (étape 1)
5. Re-vérifiez (étape 2)

### Étape 3 : Consulter le catalogue

Section **"3. État du catalogue"** :
- Tableau filtrable (Provenance / Résolution / Rôle)
- Pastilles de couleur pour visualiser les surfaces
- Utile pour auditer le catalogue avant export

## 🔧 Convention zi_ — Exemples

### Cas 1 : Héritage vanilla

**Fichier** : `zi_Grass_01.emat`  
**Parent** : `Grass_01.emat` (existe dans vanilla)

✅ **Résolution automatique** :
```json
{
  "zi_Grass_01.emat": {
    "provenance": "custom",
    "parent": "Grass_01.emat",
    "middle_bcr": null,
    "avg_color": null,
    "role": "prairie",
    "resolved": "convention"
  }
}
```
→ Couleur/PNG hérités de `Grass_01.emat` → **pas de PNG custom requis**

### Cas 2 : Création custom

**Fichier** : `zi_MonSolPersonnalise.emat`  
**Parent** : `MonSolPersonnalise.emat` (n'existe pas dans vanilla)

❌ **PNG requis** : `zi_MonSolPersonnalise.png` dans `customs/textures/`

✅ **Résolution automatique** :
```json
{
  "zi_MonSolPersonnalise.emat": {
    "provenance": "custom",
    "parent": null,
    "middle_bcr": "customs/textures/zi_MonSolPersonnalise.png",
    "avg_color": [120, 98, 75],
    "role": null,
    "resolved": "convention"
  }
}
```

### Cas 3 : Custom sans convention zi_

**Fichier** : `MaSurface.emat` (pas de préfixe zi_)

❌ **PNG requis** : `MaSurface.png` dans `customs/textures/`

✅ **Résolution automatique** :
```json
{
  "MaSurface.emat": {
    "provenance": "custom",
    "parent": null,
    "middle_bcr": "customs/textures/MaSurface.png",
    "avg_color": [95, 82, 68],
    "role": null,
    "resolved": "auto"
  }
}
```

## ⚠️ Erreurs courantes

### "Impossible de lire ... Invalid argument"

**Cause** : Guillemets dans le chemin  
**Solution** : Entrez le chemin **sans guillemets** :
```
✅ I:/reforger_travail/MonMonde/Terrains/MonMonde/MonMonde.terr
❌ "I:/reforger_travail/MonMonde/Terrains/MonMonde/MonMonde.terr"
```

### "Le chemin doit pointer vers un fichier .terr"

**Cause** : Vous avez fourni le dossier, pas le fichier  
**Solution** : Ajoutez le chemin complet jusqu'à Terrain.terr :
```
❌ I:/reforger_travail/Zimnitrita_map/World/Zimnitrita
✅ I:/reforger_travail/Zimnitrita_map/World/Zimnitrita/Terrain/Terrain.terr
```

### "Surfaces manquantes dans le catalogue"

**Cause** : Votre monde utilise des surfaces absentes du catalogue  
**Solution** :
1. Notez le nom exact de la surface (ex: `ZI_CropField_Custom.emat`)
2. Ajoutez le .emat dans `customs/emat/`
3. Si ce n'est pas un héritage zi_, ajoutez le PNG dans `customs/textures/`
4. Re-scannez

### "Fallback magenta"

**Cause** : PNG middle BCR introuvable  
**Solution** :
1. Vérifiez que le nom du PNG = nom du .emat
2. Vérifiez que le PNG est dans le bon dossier (`vanilla/textures/` ou `customs/textures/`)
3. Si c'est un héritage zi_, vérifiez que le parent existe dans vanilla

## 📊 Fichiers générés

```
<projet>/
├── reports/
│   ├── catalog_scan.txt           # Résumé du scan
│   └── catalog_terr_verify.txt    # Croisement avec .terr
└── texturesArmaReforger/
    └── catalog.json                # Catalogue unifié
```

## 🚧 Phase 2 (à venir)

Export des masques globaux PNG 8-bit par surface depuis les `.ttile` du monde.

**Usage futur** :
- Sauvegarde versionnée des masques
- Calques pour composer la satmap
- Diagnostic des couvertures réelles
