# 🔍 DRY-RUN v3 FINAL - Modifications prévues (OPTION C + MODULE PARTAGÉ)

---

## 📍 1. VALEUR EXACTE DE _TEXTURES_USER_DIR

### En mode DEV :
```python
# main.py:42
_USER_DIR = Path(__file__).parent  
# → H:\logiciel perso\Map generator\

# main.py:46
_TEXTURES_USER_DIR = _USER_DIR / "data" / "Textures_ArmaReforger" / "Textures"
# → H:\logiciel perso\Map generator\data\Textures_ArmaReforger\Textures\
```

**Valeur résolue :** `H:\logiciel perso\Map generator\data\Textures_ArmaReforger\Textures\`

✅ **Correspond bien** à `data/Textures_ArmaReforger/Textures/`

---

### En mode EXE :
```python
# main.py:39
_USER_DIR = Path.home() / "Documents" / "MapGeneratorPro"
# → C:\Users\<user>\Documents\MapGeneratorPro\

# main.py:46
_TEXTURES_USER_DIR = _USER_DIR / "data" / "Textures_ArmaReforger" / "Textures"
# → C:\Users\<user>\Documents\MapGeneratorPro\data\Textures_ArmaReforger\Textures\
```

**Valeur résolue :** `C:\Users\<user>\Documents\MapGeneratorPro\data\Textures_ArmaReforger\Textures\`

---

## 📋 2. RÉPONSES DÉTAILLÉES AUX QUESTIONS

### 2.1 Le .spec inclut-il un catalog.json ? (Lignes exactes)

**Fichier :** `MapGeneratorPro.spec`

**Ligne 23 - Inclusion UNIQUEMENT de vanilla_base_sauv :**
```python
('data/Textures_ArmaReforger/vanilla_base_sauv', 'data/Textures_ArmaReforger/vanilla_base_sauv'),
```

**Réponse :** 
- ❌ **Aucun catalog.json** dans le .spec
- ✅ Seulement `vanilla_base_sauv/` (qui contient catalog.json source)
- Le catalog.json est copié au runtime (voir 2.3)

---

### 2.2 Emplacement physique + persistance en mode exe

#### Emplacement physique :
```
C:\Users\<user>\Documents\MapGeneratorPro\data\Textures_ArmaReforger\Textures\catalog.json
```

#### Dans le bundle _MEIPASS ?
- ❌ **NON** - Le catalog.json n'est PAS dans le bundle
- ✅ Le bundle contient seulement `vanilla_base_sauv/catalog.json` (source readonly)

#### Inscriptible et persistant ?
- ✅ **INSCRIPTIBLE** : Oui, dans `Documents/` (zone utilisateur avec droits écriture)
- ✅ **PERSISTANT** : Oui, survit entre les lancements de l'exe
- ✅ **MODIFIABLE** : L'utilisateur peut enrichir le catalog via scan .emat

#### Schéma du flux :

```
[Mode EXE - Premier lancement]

Bundle _MEIPASS (lecture seule)                    Documents/ (lecture/écriture)
├─ data/Textures_ArmaReforger/
   └─ vanilla_base_sauv/
      ├─ catalog.json ──────COPIE───────→ MapGeneratorPro/
      └─ texture_Middle/                    └─ data/Textures_ArmaReforger/Textures/
                                               ├─ catalog.json (MODIFIABLE)
                                               └─ texture_Middle/

[Lancements suivants]
Le catalog dans Documents/ est utilisé directement (pas de recopie)
```

---

### 2.3 Rôle exact de la copie main.py:91-95

**Code concerné :**
```python
# main.py:91-95
src_cat = _VANILLA_BASE_SRC / "catalog.json"
dst_cat = _TEXTURES_USER_DIR / "catalog.json"
if src_cat.exists():
    shutil.copy2(str(src_cat), str(dst_cat))
    print(f"[INIT] catalog.json copié")
```

**Fonction englobante :** `_init_first_launch()` (lignes 66-100)

**Déclenchement :**
```python
marker = _TEXTURES_USER_DIR / ".initialized"
if marker.exists():
    return  # Déjà initialisé, ne rien faire
```

**Rôle en mode EXE :**

1. **Premier lancement uniquement** (marqueur `.initialized` absent)
2. **Extraction du catalog vanilla** depuis le bundle PyInstaller :
   - Source : `_MEIPASS/data/Textures_ArmaReforger/vanilla_base_sauv/catalog.json` (readonly)
   - Destination : `Documents/MapGeneratorPro/data/Textures_ArmaReforger/Textures/catalog.json`
3. **Rend le catalog modifiable** : permet ensuite l'enrichissement via scan .emat
4. **Créé le marqueur** `.initialized` pour ne plus recopier

**Rôle en mode DEV :**
- Même logique, mais source et destination sont dans le même arbre de fichiers
- Moins critique car l'utilisateur peut modifier directement les fichiers

---

## 🔧 3. MODULE PARTAGÉ POUR LE CHEMIN DU CATALOG

### ⚠️ PROBLÈME IDENTIFIÉ

**Situation actuelle :**
Chaque script définit le chemin en dur avec sa propre logique :

```python
# clean_weights.py:409
project_root = Path(__file__).parent
catalog_path = project_root / "data" / "Textures_ArmaReforger" / "catalog.json"

# tile_inspector.py:640
PROJECT_ROOT = Path(__file__).parent.parent
CATALOG_PATH = PROJECT_ROOT / "data" / "Textures_ArmaReforger" / "catalog.json"

# satmap_classifier.py:25
CATALOG_PATH = Path(__file__).parent / "data" / "Textures_ArmaReforger" / "catalog.json"

# satmap_v2_generator.py:363
catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")

# emat_scanner_simple.py:114
catalog_file = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
```

**Problème :** 
- 5 définitions différentes du même chemin
- Incohérence `.parent` vs `.parent.parent`
- Chemins en dur non portables
- Duplication de logique

---

### ✅ SOLUTION : Module `catalog_config.py`

**Créer un nouveau fichier :** `catalog_config.py`

```python
# -*- coding: utf-8 -*-
"""
catalog_config.py — Configuration centralisée du chemin du catalog.json
Compatible : mode dev, mode exe (PyInstaller), usage standalone des scripts.

Ce module est importé par main.py et tous les scripts nécessitant le catalog.
"""

import sys
from pathlib import Path

def get_catalog_path() -> Path:
    """
    Retourne le chemin absolu du catalog.json global.
    
    Logique de résolution :
    - Mode EXE (PyInstaller) : Documents/MapGeneratorPro/data/Textures_ArmaReforger/Textures/catalog.json
    - Mode DEV ou standalone : <racine_projet>/data/Textures_ArmaReforger/Textures/catalog.json
    
    La racine projet est détectée automatiquement depuis __file__.
    
    Returns:
        Path: Chemin absolu vers catalog.json
    """
    if getattr(sys, 'frozen', False):
        # Mode EXE (PyInstaller)
        user_dir = Path.home() / "Documents" / "MapGeneratorPro"
        catalog_path = user_dir / "data" / "Textures_ArmaReforger" / "Textures" / "catalog.json"
    else:
        # Mode DEV ou standalone
        # Trouver la racine du projet (dossier contenant main.py et data/)
        current = Path(__file__).resolve().parent
        
        # Chercher le dossier contenant data/Textures_ArmaReforger/
        while current != current.parent:  # Tant qu'on n'est pas à la racine du système
            candidate = current / "data" / "Textures_ArmaReforger" / "Textures" / "catalog.json"
            if candidate.exists() or (current / "data" / "Textures_ArmaReforger").exists():
                return current / "data" / "Textures_ArmaReforger" / "Textures" / "catalog.json"
            current = current.parent
        
        # Fallback : utiliser le dossier parent de catalog_config.py
        project_root = Path(__file__).parent
        catalog_path = project_root / "data" / "Textures_ArmaReforger" / "Textures" / "catalog.json"
    
    return catalog_path


# Pour usage direct (import catalog_config; catalog_config.CATALOG_PATH)
CATALOG_PATH = get_catalog_path()


if __name__ == "__main__":
    # Test du module
    path = get_catalog_path()
    print(f"Chemin catalog détecté : {path}")
    print(f"Existe : {path.exists()}")
    print(f"Mode exe : {getattr(sys, 'frozen', False)}")
```

---

### Utilisation dans les scripts

**Avant :**
```python
# Chaque script définit son propre chemin
project_root = Path(__file__).parent
catalog_path = project_root / "data" / "Textures_ArmaReforger" / "catalog.json"
```

**Après :**
```python
# Import du module partagé
from catalog_config import get_catalog_path

# Une ligne suffit
catalog_path = get_catalog_path()
```

---

## 📝 4. MODIFICATIONS DÉTAILLÉES (MISE À JOUR)

### 🆕 0. CRÉER `catalog_config.py`

**Nouveau fichier à la racine :** `catalog_config.py`

*Voir code complet section 3*

**Action :** Créer le fichier avec la fonction `get_catalog_path()`

---

### 1️⃣ **clean_weights.py**

**Ligne 1 - Ajouter import :**
```python
# AJOUTER en haut du fichier (après les autres imports)
from catalog_config import get_catalog_path
```

**Ligne 409-410 - Remplacer par import :**
```python
# AVANT
project_root = Path(__file__).parent
catalog_path = project_root / "data" / "Textures_ArmaReforger" / "catalog.json"

# APRÈS
catalog_path = get_catalog_path()
```

**Ligne 411 - Modifier pour pointer vers texture_Middle côte à côte :**
```python
# AVANT
middles_dir = project_root / "data" / "Textures_ArmaReforger" / "texture_Middle"

# APRÈS
middles_dir = catalog_path.parent / "texture_Middle"
```

**Après ligne 419 (ajouter log) :**
```python
catalog = load_catalog(catalog_path)
print(f"[INFO] Catalogue chargé : {catalog_path.absolute()}")  # ← NOUVEAU
```

---

### 2️⃣ **satmap_v2_generator.py**

**Ligne 1 - Ajouter import :**
```python
from catalog_config import get_catalog_path
```

**Ligne 363 - Remplacer :**
```python
# AVANT
catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")

# APRÈS  
catalog_path = get_catalog_path()
```

**Après ligne 370 (ajouter log) :**
```python
catalog = json.load(f)
print(f"[INFO] Catalogue chargé : {catalog_path.absolute()}")  # ← NOUVEAU
```

---

### 3️⃣ **satmap_classifier.py**

**Ligne 1 - Ajouter import :**
```python
from catalog_config import get_catalog_path
```

**Ligne 25 - Remplacer :**
```python
# AVANT
CATALOG_PATH = Path(__file__).parent / "data" / "Textures_ArmaReforger" / "catalog.json"

# APRÈS
CATALOG_PATH = get_catalog_path()
```

**Après ligne 207 (ajouter log) :**
```python
cat = json.load(f)
print(f"[INFO] Catalogue chargé : {CATALOG_PATH.absolute()}")  # ← NOUVEAU
```

---

### 4️⃣ **tile_inspector.py**

**Ligne 1 - Ajouter import :**
```python
from catalog_config import get_catalog_path
```

**Lignes 631-640 - Remplacer :**
```python
# AVANT
PROJECT_ROOT = Path(__file__).parent.parent
# ...
CATALOG_PATH = PROJECT_ROOT / "data" / "Textures_ArmaReforger" / "catalog.json"

# APRÈS
CATALOG_PATH = get_catalog_path()
```

**Après ligne 665 (ajouter log) :**
```python
catalog = load_catalog(CATALOG_PATH)
print(f"[INFO] Catalogue chargé : {CATALOG_PATH.absolute()}")  # ← NOUVEAU
```

---

### 5️⃣ **emat_scanner_simple.py**

**Ligne 1 - Ajouter import :**
```python
from catalog_config import get_catalog_path
```

**Ligne 114 - Remplacer :**
```python
# AVANT
catalog_file = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")

# APRÈS
catalog_file = get_catalog_path()
```

*(Log déjà présent ligne 122)*

---

### 6️⃣ **data/projects/Zbk_island/project.json**

**Ligne 331 - SUPPRIMER LA CLÉ :**
```json
// AVANT (lignes 330-332)
    },
    "catalog_json": "H:\\logiciel perso\\Map generator\\data\\Textures_ArmaReforger\\catalog.json",
    "satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",

// APRÈS
    },
    "satmap_v2": "outputs/generated/satmap_v2_textured_4097.png",
```

**Validation :** `json.load()` après modification

---

### 7️⃣ **main.py** (7 modifications)

#### 7.1 Ligne 1 - Import du module partagé
```python
# AJOUTER en haut du fichier
from catalog_config import get_catalog_path
```

#### 7.2 Ligne 93 - Condition copie vanilla_base (UNIQUEMENT si absent)
```python
# AVANT
if src_cat.exists():

# APRÈS
if src_cat.exists() and not dst_cat.exists():
```

#### 7.3 Ligne 191 - SUPPRIMER catalog_json des nouveaux project.json
```python
# SUPPRIMER cette ligne :
"catalog_json": "inputs/catalog.json",
```

#### 7.4 Lignes 1153-1162 - Ignorer catalog_json legacy, utiliser global
```python
# AVANT
proj = Path(_session["current_project_path"])
data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
paths = data.get("paths", {})
catalog_str = paths.get("catalog_json", "")
catalog_path = proj / catalog_str if catalog_str and not Path(catalog_str).is_absolute() else Path(catalog_str) if catalog_str else None
if not catalog_path or not catalog_path.exists():
    return {"ok": False, "error": "catalog.json non encore généré — lancez le scan .emat dans l'onglet Satmap"}

# APRÈS
proj = Path(_session["current_project_path"])
data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
paths = data.get("paths", {})

# Ignorer catalog_json du project.json (legacy), utiliser le global
if "catalog_json" in paths:
    print(f"[INFO] Clé 'catalog_json' ignorée dans project.json (legacy)")

catalog_path = get_catalog_path()
if not catalog_path.exists():
    return {"ok": False, "error": "catalog.json introuvable — lancez le scan .emat dans l'onglet Satmap"}
```

#### 7.5 Ligne 1206 - Utiliser module partagé + log
```python
# AVANT
global_catalog = _TEXTURES_USER_DIR / "catalog.json"

# APRÈS
global_catalog = get_catalog_path()
print(f"[INFO] Catalogue global : {global_catalog.absolute()}")
```

#### 7.6 Lignes 1219-1222 - SUPPRIMER copie vers inputs/
```python
# SUPPRIMER CES 4 LIGNES :
project_catalog = proj / "inputs" / "catalog.json"
project_catalog.parent.mkdir(parents=True, exist_ok=True)
import shutil
shutil.copy2(global_catalog, project_catalog)
```

#### 7.7 Ligne 1225 - Modifier message log
```python
# AVANT
self._log(f"[SATMAP] Catalog copié vers {project_catalog}")

# APRÈS
self._log(f"[SATMAP] Catalogue global mis à jour : {global_catalog.absolute()}")
```

#### 7.8 Lignes 1237-1243 - Ignorer catalog_json legacy (generate_satmap_v2)
```python
# AVANT
proj = Path(_session["current_project_path"])
data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
paths = data.get("paths", {})
catalog_str = paths.get("catalog_json", "")
catalog_path = Path(catalog_str) if Path(catalog_str).is_absolute() else proj / catalog_str
if not catalog_path.exists():
    return {"ok": False, "error": "catalog.json introuvable"}

# APRÈS
proj = Path(_session["current_project_path"])
data = json.loads((proj / "project.json").read_text(encoding="utf-8"))
paths = data.get("paths", {})

# Ignorer catalog_json du project.json (legacy)
if "catalog_json" in paths:
    print(f"[INFO] Clé 'catalog_json' ignorée dans project.json (legacy)")

catalog_path = get_catalog_path()
if not catalog_path.exists():
    return {"ok": False, "error": "catalog.json introuvable"}
```

---

### 8️⃣ **MapGeneratorPro.spec** - Inclure le nouveau module

**Ligne 34 - Ajouter catalog_config.py :**
```python
# AVANT (ligne 34)
    ('emat_scanner_simple.py', '.'),
],

# APRÈS
    ('emat_scanner_simple.py', '.'),
    ('catalog_config.py', '.'),  # ← AJOUTER
],
```

---

### 9️⃣ **Git - Suppression fichier obsolète**

```bash
git rm data/Textures_ArmaReforger/catalog.json
```

---

## 📊 RÉCAPITULATIF FINAL

| Fichier | Modifications | Type |
|---------|---------------|------|
| **catalog_config.py** | 1 | **CRÉATION MODULE PARTAGÉ** |
| clean_weights.py | 4 | Import + Chemin + Middles + Log |
| satmap_v2_generator.py | 2 | Import + Chemin + Log |
| satmap_classifier.py | 2 | Import + Chemin + Log |
| tile_inspector.py | 2 | Import + Chemin + Log |
| emat_scanner_simple.py | 2 | Import + Chemin |
| project.json (Zbk_island) | 1 | Supprimer clé catalog_json |
| main.py | 8 | Import + Condition + Suppression clé + Ignorer legacy + Logs + Suppression copie |
| MapGeneratorPro.spec | 1 | Inclure catalog_config.py |
| catalog.json (racine) | 1 | git rm |
| **TOTAL** | **24 modifications** | **10 fichiers** |

---

## ✅ VALIDATIONS APRÈS MODIFICATIONS

### 1. Syntaxe Python
```bash
python -m py_compile catalog_config.py
python -m py_compile clean_weights.py
python -m py_compile satmap_v2_generator.py
python -m py_compile satmap_classifier.py
python -m py_compile tile_inspector.py
python -m py_compile emat_scanner_simple.py
python -m py_compile main.py
```

### 2. Validation JSON
```python
import json
with open("data/projects/Zbk_island/project.json") as f:
    json.load(f)
```

### 3. Test module partagé
```bash
python catalog_config.py
# Doit afficher : Chemin catalog détecté: ...
```

### 4. Grep final - Aucune référence restante
```bash
grep -r "data/Textures_ArmaReforger/catalog.json" --include="*.py" --include="*.json" \
  --exclude-dir=backups --exclude-dir=dist --exclude-dir=build
# Doit retourner 0 résultats hors documentation
```

---

## 🎯 ARCHITECTURE FINALE

### Définition unique du chemin :
```python
# catalog_config.py (1 seul endroit)
def get_catalog_path() -> Path:
    if getattr(sys, 'frozen', False):
        # Mode EXE
        return Path.home() / "Documents" / "MapGeneratorPro" / "data" / "Textures_ArmaReforger" / "Textures" / "catalog.json"
    else:
        # Mode DEV
        return <racine_projet> / "data" / "Textures_ArmaReforger" / "Textures" / "catalog.json"
```

### Utilisation dans tous les scripts :
```python
from catalog_config import get_catalog_path
catalog_path = get_catalog_path()
```

### project.json :
- ❌ **Ne contient PLUS** la clé `catalog_json`
- ℹ️ **Si présente** (legacy) : ignorée avec log [INFO]

---

## 🛑 PRÊT POUR APPLICATION

**Tous les points précisés :**
1. ✅ Valeur exacte _TEXTURES_USER_DIR en dev ET exe
2. ✅ Réponses détaillées : .spec, emplacement, persistance, rôle copie
3. ✅ Module partagé `catalog_config.py` pour définition unique
4. ✅ Suppression clé catalog_json dans Zbk_island/project.json
5. ✅ Validations syntaxe + json.load() listées

**ARRÊT - EN ATTENTE DE VALIDATION FINALE**
