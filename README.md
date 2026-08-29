# 🗺️ Map Generator Pro

> **Générateur automatique de masques de texture pour Arma Reforger**  
> Transformez votre heightmap en carte naturelle sans peinture manuelle

![Version](https://img.shields.io/badge/version-7.0-green)
![Python](https://img.shields.io/badge/python-3.x-blue)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 📖 Table des matières

- [Pourquoi Map Generator Pro ?](#-pourquoi-map-generator-pro-)
- [Fonctionnalités](#-fonctionnalités)
- [Installation](#-installation)
- [Workflow complet A→Z](#-workflow-complet-az)
- [Concepts clés](#-concepts-clés)
- [Structure du projet](#-structure-du-projet)
- [Contraintes techniques](#️-contraintes-techniques)
- [Glossaire](#-glossaire)
- [Contribution](#-contribution)

---

## 🎯 Pourquoi Map Generator Pro ?

La création d'une carte dans **Arma Reforger** implique, parmi de nombreuses tâches, l'application de textures terrain et de végétation sur l'ensemble du terrain. Cette étape, appelée **material painting**, peut se faire à la main dans le Workbench de Bohemia Interactive — mais cette approche révèle rapidement ses limites.

### Le constat de départ

Peindre les matériaux à la main sur une carte de **16×16 km** est un travail **colossal**. Sur une carte comme Zimnitrita (32×32 tuiles), cela représente des milliers de blocs à couvrir manuellement. Chaque zone de prairie, de forêt, de roche ou d'alpage doit être peinte individuellement.

Mais le problème va plus loin. Même avec de la patience, la peinture manuelle souffre du syndrome de la **page blanche** : comment décider où placer la forêt ? Où commence la roche ? Où finit la prairie ? La carte ressemble souvent à un patchwork artificiel, sans cohérence naturelle avec le relief.

Le mapping manuel, même bien fait, porte **la marque de la main de l'homme** : les transitions sont trop nettes, les zones trop régulières, la végétation trop symétrique. Rien qui ressemble à la nature.

### L'idée

Face à ces difficultés, l'idée est née de créer un outil qui pose les masques de terrain et de végétation de façon **naturelle, sans intervention manuelle**. Le principe est simple : utiliser la heightmap elle-même — l'altitude, la pente, la distance à la côte, les données d'érosion Gaea — pour déduire automatiquement où doit se trouver chaque type de végétation.

- La **roche** apparaît naturellement là où la pente est forte
- La **forêt** colonise les versants doux
- Les **alpages** se positionnent en altitude
- Les **zones côtières** suivent le rivage

Tout cela **sans que l'utilisateur n'ait à peindre une seule tuile**.

### La valeur ajoutée

Au-delà du gain de temps, Map Generator apporte quelque chose que la peinture manuelle ne peut pas facilement offrir : la possibilité de **visualiser immédiatement les possibilités de la carte**. En quelques minutes, on obtient une vue complète du rendu terrain — ce qui inspire, guide les choix de mapping ultérieurs, et révèle parfois des zones insoupçonnées qui font la richesse de la carte.

> ⚠️ **Note** : Map Generator n'est pas un outil de sculpt terrain. Il travaille à partir d'une heightmap déjà finalisée dans Reforger Workbench. Son rôle est de transformer cette heightmap en masques de texture cohérents avec le relief naturel.

---

## ✨ Fonctionnalités

- ✅ **Génération automatique de 13 masques** (seabed, coastal, rock, forests, grasslands, alpine...)
- ✅ **Presets biomes** (Tempéré océanique, Méditerranéen, Continental, etc.)
- ✅ **Auto-calibration** des paramètres depuis la heightmap
- ✅ **Budget QTRE** — Validation automatique (max 5-7 textures/bloc)
- ✅ **Satmap V2.0** — Génération de carte satellite texturée depuis `.edds`
- ✅ **Classification K-means** — Segmentation satmap par couleurs
- ✅ **Inspection tuiles** — Analyse détaillée des `.ttile` Reforger
- ✅ **Interface desktop native** — Application PyWebView (Windows/Linux)

---

## 🚀 Installation

### Prérequis

- **Python 3.8+**
- **Reforger Workbench** (pour exporter la heightmap `.asc`)

### Installation des dépendances

```bash
pip install -r requirements.txt
```

### Lancement

```bash
python main.py
```

L'application s'ouvre dans une fenêtre native desktop.

---

## 📋 Workflow complet A→Z

### ⚠️ Règle d'or

> **Si la heightmap change à un moment quelconque, toutes les étapes depuis l'étape 2 doivent être recommencées.**  
> La heightmap est la source de vérité de tout le pipeline.

---

### **Étape 1 — Préparer le terrain dans Reforger Workbench**

#### 1️⃣ Sculpter le terrain
Travailler l'altitude, les collines, les vallées, les falaises. Smoother les zones rugueuses. Poser les routes et les rivières. Cette étape se fait entièrement dans **Reforger Workbench**.

#### 2️⃣ Exporter la heightmap
Une fois le terrain satisfaisant, exporter la heightmap au format **`.asc`** depuis Workbench. C'est ce fichier qui servira de base à tout le pipeline Map Generator.

> 💡 **Note** : Les routes, objets et entités posées dans Workbench ne sont pas prises en compte par Map Generator. Seule la géométrie du terrain (hauteur, pente) influence la génération des masques.

---

### **Étape 2 — Configurer le projet**

#### 1️⃣ Créer un projet
Dans l'écran **Projets**, cliquer sur "Créer un projet". Donnez-lui un nom clair (ex: `Zimnitrita`, `ZBK_island`).

#### 2️⃣ Importer la heightmap
Dans **Terrain > Chemins & fichiers**, sélectionner le fichier `.asc` exporté depuis Workbench. Configurer aussi :
- **Addon Reforger** (chemin vers `addons/`)
- **catalog.json** (catalogue textures)
- **Data dir** (dossier `data/` du projet)

#### 3️⃣ Parser les infos Workbench
Dans **Terrain > Chemins**, coller le texte "General Info" copié depuis Workbench. Cela configure automatiquement la grille (32×32 tiles, cellsize, etc.).

#### 4️⃣ Analyser le terrain
Dans **Terrain > Atlas Métrique**, cliquer "Analyser la heightmap". Cette étape calcule les pentes, altitudes et paramètres auto-calibrés.

---

### **Étape 3 — Choisir les matériaux**

#### 1️⃣ Sélectionner un biome
Dans **Generation > Masques**, choisir le biome correspondant à votre carte :
- Tempéré océanique
- Méditerranéen
- Continental
- etc.

Appliquer le preset pour charger des textures cohérentes.

#### 2️⃣ Ajuster le mapping
Dans le tableau de mapping, assigner à chaque masque la texture Reforger souhaitée. Les textures vanilla sont pré-chargées depuis `surfaces.json`.

---

### **Étape 4 — Générer les masques**

#### 1️⃣ Régler les paramètres
Dans **Generation > Paramètres**, ajuster :
- Seuils de pente (rock, cliff)
- Amplitude fBm (bruit fractal)
- Altitudes seuils pour chaque zone

L'auto-calibrage depuis la heightmap peut servir de point de départ.

#### 2️⃣ Générer la preview
Dans **Generation > Baking**, cliquer **"Générer preview"**. Le pipeline traite la heightmap (peut prendre plusieurs minutes pour 4097×4097). La preview s'affiche.

#### 3️⃣ Valider et itérer
Si le rendu ne convient pas, ajuster les paramètres et régénérer. Répéter jusqu'à satisfaction. Exporter les masques PNG.

---

### **Étape 5 — Contrôle qualité**

#### 1️⃣ Vérifier le budget QTRE
Dans **Inspection > Grille QTRE**, scanner les tuiles. Chaque bloc ne doit pas dépasser **5 (ou 7 avec patch)** textures. Les blocs en rouge indiquent un dépassement.

#### 2️⃣ Inspecter les anomalies
Utiliser **Inspection > Inspect Tuile** pour examiner les tuiles problématiques. **Corrections > Scan Global** pour détecter les slots négligeables.

---

### **Étape 6 — Export et intégration**

#### 1️⃣ Exporter les masques PNG
Cliquer **"Exporter masques PNG"** dans **Generation > Baking**. Les fichiers sont copiés dans `outputs/masks/latest/`.

#### 2️⃣ Générer la Satmap (optionnel)
Dans **Satmap > Satmap V2.0**, générer la satmap texturée depuis les fichiers `.edds` + `catalog.json`.

#### 3️⃣ Baking `.ttile` (WIP)
L'écriture directe sur les fichiers `.ttile` est en cours de développement. Pour l'instant, les masques PNG doivent être intégrés manuellement.

---

## 🧩 Concepts clés

### Les masques — Principes et ordre

#### Qu'est-ce qu'un masque ?

Un masque est une **image en niveaux de gris** de la même taille que la heightmap (4097×4097 pour une carte 16km). Le blanc signifie "cette texture s'applique ici à 100%", le noir "elle ne s'applique pas du tout", et les niveaux de gris expriment des mélanges.

Map Generator génère **13 masques** simultanément :

| Masque | Description |
|--------|-------------|
| `seabed` | Fond marin |
| `coastal` | Zone côtière |
| `alpages` | Prairies d'altitude |
| `landes_rocheuses` | Landes pierreuses |
| `maquis_landes` | Maquis et landes |
| `foret_coniferes` | Forêt de conifères |
| `foret_feuillue` | Forêt feuillée |
| `flow` | Traces d'érosion (rivières sèches) |
| `landes_plateau` | Landes de plateau |
| `rock` | Affleurement rocheux |
| `deposit` | Dépôts alluviaux |
| `prairie_seche` | Prairie sèche |
| `prairie_humide` | Prairie humide |

#### Le principe de soustraction

Les masques sont posés **par ordre de priorité, en soustrayant** chaque masque des suivants. Cela signifie :

1. Le masque `seabed` est posé en premier. Sa zone est "réservée" et ne peut plus être recouverte.
2. Le masque `coastal` est posé ensuite, mais uniquement sur les zones qui ne sont pas déjà occupées par `seabed`.
3. Et ainsi de suite jusqu'à `prairie_humide`, le dernier masque.

Cette méthode garantit que **chaque pixel n'appartient qu'à un seul masque prioritaire**, ce qui évite les conflits et assure une couverture complète du terrain (99.8% en pratique).

#### Pourquoi l'ordre compte

Changer l'ordre des masques change le rendu de la carte. Par exemple :

- Si `rock` passe avant `foret_coniferes`, les zones rocheuses "mangent" la forêt sur les pentes → rendu plus minéral.
- Si `foret_coniferes` passe avant `rock`, la forêt pousse jusqu'aux zones très pentues → rendu plus boisé.

> 💡 **Note** : L'ordre validé pour Zimnitrita, qui donne un rendu naturel de terrain tempéré européen, est celui déjà pré-configuré dans Map Generator.

---

### Budget QTRE — 5 ou 7 textures par bloc

#### Le système de slots Reforger

Dans le moteur **Enfusion**, chaque bloc terrain (une subdivision de tuile) peut contenir au maximum un certain nombre de textures simultanément. Ce nombre est appelé **budget de slots**.

Par défaut, Reforger limite ce budget à **5 textures par bloc**. Map Generator Pro utilise une configuration étendue qui permet jusqu'à **7 textures par bloc** (configuration Zimnitrita, notée QTRE).

#### Pourquoi c'est important

Si un bloc dépasse son budget, Reforger peut **crasher** ou afficher des artefacts visuels. C'est pourquoi la grille QTRE dans l'onglet **Inspection** est essentielle — elle permet de visualiser, bloc par bloc, combien de textures sont utilisées.

| Statut | Couleur | Signification |
|--------|---------|---------------|
| **OK** | 🟢 Vert | Nombre de textures inférieur au budget |
| **Limite** | 🟡 Jaune | Exactement au budget — surveiller |
| **Critique** | 🟠 Orange | Budget +1 — risque |
| **Dépassement** | 🔴 Rouge | Dépassement du budget — à corriger |

#### Comment réduire les dépassements

- Réduire le nombre de masques actifs dans les zones denses
- Augmenter les seuils de priorité pour que certains masques cèdent la place
- Utiliser le **Scan Global** (Corrections) pour identifier les slots négligeables à supprimer
- Ajuster le seuil QTRE dans **Generation > Paramètres**

---

## 📂 Structure du projet

```
data/projects/NomDuProjet/
├── inputs/              # Fichiers source apportés par l'utilisateur
│   ├── heightmap/       # .asc (heightmap Workbench)
│   ├── satmap/          # .png (satmap référence)
│   ├── masks/           # .png (masque exclusion Zone A)
│   └── gaea/            # .png (flow, deposit depuis Gaea)
├── outputs/
│   ├── masks/latest/    # Masques PNG générés par le pipeline
│   ├── generated/       # Satmap, previews, images de résultat
│   ├── cache/           # Cache terrain (npz, qtre_scan.json)
│   └── logs/            # Logs de session horodatés
├── project.json         # Configuration et chemins du projet
└── surfaces.json        # Liste des matériaux Reforger
```

### Fichiers sources

| Fichier | Description | Où le trouver |
|---------|-------------|---------------|
| **Heightmap (.asc)** | Carte d'altitude du terrain. Source de tout le pipeline. Doit être exporté depuis Reforger Workbench après avoir finalisé le sculpt du terrain. | Workbench > Terrain > Export > ASC |
| **Satmap (.png)** | Image satellite de référence. Optionnel — utile pour la génération de satmap. | Votre satmap existante |
| **Masque exclusion (.png)** | Définit une Zone A prioritaire : les zones blanches seront traitées en priorité et exclues de la génération automatique. Utile pour les zones urbaines ou les zones que vous voulez contrôler manuellement. | Éditeur d'image (Gimp, Photoshop) — ou exporté depuis Reforger WB |
| **Flow (.png)** | Masque d'érosion hydrique exporté depuis Gaea. Trace les rivières sèches, ravines et lignes d'eau. | Gaea > Export > Flow mask |
| **Deposit (.png)** | Masque de dépôt alluvial exporté depuis Gaea. Trace les zones de sédiments et de dépôt en bas de pente. | Gaea > Export > Deposit mask |
| **Catalog JSON** | Catalogue des textures Reforger avec leurs couleurs moyennes et fichiers middle BCR. Contient les textures vanilla ET vos textures custom. | Par défaut : `data/Textures_ArmaReforger/catalog.json` |

---

## ⚙️ Contraintes techniques

### Limites de la génération automatique

- ❌ Les masques sont basés sur la géométrie (altitude, pente, distance côte). Ils ne tiennent pas compte des routes, chemins ou zones construites.
- ❌ Les forêts générées sont "statistiquement probables" — elles peuvent couvrir des zones où l'utilisateur ne voudrait pas de forêt.
- ❌ La génération ne remplace pas le mapping fin : elle donne un point de départ naturel, que l'utilisateur peut ensuite affiner.
- ❌ La mer et les zones d'eau sont détectées par le seuil d'altitude (altitude < 0), ce qui peut ne pas correspondre exactement à la ligne de rivage Reforger.

### Budget QTRE

- ⚠️ **Max 5 textures/bloc** (Reforger vanilla)
- ⚠️ **Max 7 textures/bloc** (avec patch QTRE Zimnitrita)
- ⚠️ **6+ textures = risque de crash Workbench**

---

## 📚 Glossaire

| Terme | Définition |
|-------|------------|
| **`.ttile`** | Fichier binaire Reforger contenant les données de texture d'une tuile terrain (matériaux, poids par bloc) |
| **`.edds`** | Fichier de couche texture compressé (format DDS LZ4) dans `.EditorData`. Contient les données de couleur par couche de matériau. |
| **`LRS2`** | Chunk binaire dans les `.ttile` qui liste les matériaux actifs par bloc (Layer Resource Set 2) |
| **`QTRE`** | Configuration étendue du budget de textures (7 slots au lieu de 5 par défaut) |
| **`fBm`** | Fractional Brownian Motion — bruit fractal utilisé pour enrichir naturellement les transitions de pente |
| **`Budget slots`** | Nombre maximum de textures autorisées par bloc terrain (5 défaut, 7 avec QTRE) |
| **`Soustraction`** | Méthode de pose des masques : chaque masque retire sa zone des masques de priorité inférieure |
| **`Heightmap`** | Image altitude du terrain, généralement en format `.asc` (ASCII Grid) ou `.png` 16 bits |
| **`Cellsize`** | Résolution de la heightmap en mètres par pixel (ex: 4m/px pour une carte 16km en 4097px) |
| **`catalog.json`** | Fichier de catalogue des textures Reforger avec leurs couleurs moyennes et fichiers middle BCR |
| **`Satmap`** | Image satellite de la carte générée depuis les couleurs des matériaux appliqués |
| **`K-means`** | Algorithme de classification par couleurs utilisé pour segmenter une satmap en zones de végétation |

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Pour toute question, suggestion ou bug report, ouvrez une **issue** sur GitHub.

---

## 📄 License

MIT License — © 2026 **giorbev**

---

## 🎮 Créé par

**Map Generator Pro v7.0**  
by **giorbev**

Pour la communauté **Arma Reforger** 🎖️
