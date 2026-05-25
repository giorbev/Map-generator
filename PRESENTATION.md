# Map Generator Pro
### Outil d'auto-texture terrain pour Arma Reforger

---

## Le problème

Créer une map Reforger de 8×8 km, c'est peindre des textures de terrain à la main sur des milliers de blocs de 32×32m. Sans outil, c'est **des semaines de travail** pour un résultat qui reste approximatif.

---

## La solution

**Map Generator Pro** applique le concept de l'**auto-material UE5** dans un script Python, adapté aux contraintes de Reforger.

> En UE5, un shader HLSL calcule en temps réel quelles textures afficher selon la pente, l'altitude et le contexte. Ici, c'est du NumPy qui fait le même calcul en amont et produit des masques PNG — le résultat est équivalent, l'exécution est offline.

L'outil analyse automatiquement une heightmap et génère l'ensemble des masques de textures prêts à importer dans Reforger Workbench.

Tu fournis le terrain → l'outil fait le reste.

---

## Comment l'auto-material construit la représentation texture

Contrairement au travail manuel dans Workbench (couches qui s'écrasent l'une l'autre), l'auto-material fonctionne en **compétition simultanée** sur 3 temps :

**1 — Scoring (tout à la fois)**
Pour chaque pixel de la map, un score est calculé pour chaque texture en même temps. À la fin de cette étape, chaque pixel a un bulletin de notes :
```
pixel X,Y → roche=0.7  prairie=0.1  debris=0.2  lande=0.0 ...
```
NumPy traite les ~67 millions de pixels de la map en une seule passe vectorisée.

**2 — Budget bloc (bloc par bloc)**
La map est découpée en blocs de 32×32m. Pour chaque bloc, on conserve uniquement les 3–4 textures dominantes (contrainte QTRE Reforger). Les autres sont forcées à zéro.

**3 — Normalisation (tout à la fois)**
Les scores restants sont renormalisés pour que leur somme = 1.0 par pixel. Chaque texture reçoit sa part relative.

> **Manuel** = couches qui s'écrasent  
> **Auto-material** = compétition simultanée → les gagnants sont sélectionnés ensemble

---

## Pipeline

```
Heightmap (.asc)
      │
      ▼
Analyse terrain
  ├── Pentes (°)
  ├── Altitude normalisée
  ├── Rugosité de surface
  ├── Courbure (crêtes / creux)
  ├── Réseau hydrographique (flow)
  └── TPI (position topographique)
      │
      ▼
Attribution automatique des textures
      │
      ▼
Contrôle budget QTRE (max 4 tex/bloc)
      │
      ▼
Export masques PNG 16-bit → Workbench
```

---

## Textures gérées

| Zone | Texture |
|---|---|
| Fond marin | SeaBed_01 |
| Côtier | Grass_03_coastal |
| Plage / galets | Pebbles_01 |
| Prairie (base) | Grass_02 |
| Mi-altitude | Grass_03 |
| Haute altitude | MountainGrass_01 |
| Bruyère | Heather_01 |
| Érosion / ravines | Dirt_03 |
| Pied de falaise | Debris_Rock |
| Roche nue | Rock_01 |
| Neige | CUSTOM_SNOW |

---

## Contrainte QTRE

Reforger impose **4 textures maximum par bloc de 32×32m**. L'outil respecte cette limite automatiquement sur toute la map — aucune violation, aucun crash Workbench.

---

## Intégration Instant Terra

Les masques IT sont des **signaux d'entrée** dans le système d'auto-material, pas une application directe. Le code les analyse et les combine avec les autres données du terrain (altitude, flow, TPI...) pour calculer les scores de texture.

```
mask_slope90  ──┐
mask_curv     ──┤──► Scoring auto-material ──► Masques export
mask_sediment ──┤    (règles géographiques)
altitude      ──┤
flow / TPI    ──┘
```

| Masque IT | Signal remplacé | Usage |
|---|---|---|
| Slope 40–90° | `slopes >= rock_s` numpy | Falaises exactes → Rock_01 + Debris |
| Curvature | Laplacien numpy | Crêtes → Heather / Creux → Érosion |
| Sediment | `flow × valley` approximé | Zones de dépôt → Dirt_03 |

**Sans masques IT** → le code recalcule tout depuis la heightmap (slopes, curvature, sediment approximé). L'outil fonctionne sur n'importe quelle map, même sans Instant Terra.

**Avec masques IT** → les signaux physiques remplacent les approximations numpy. Les masques IT sont un bonus qualité, pas une dépendance.

---

## L'érosion — comment ça fonctionne

L'érosion suit la logique de l'**eau qui sculpte le terrain**. Le système adapte son approche selon les données disponibles.

**Sans masque IT — approximation depuis la heightmap**

Quatre signaux sont combinés pour reconstituer le comportement de l'eau :

| Signal | Ce qu'il représente |
|---|---|
| Flow accumulation | Là où l'eau se concentre (confluences, talwegs) |
| TPI négatif | Les creux topographiques |
| Vallée | Zones encaissées par rapport au relief |
| Concavité | Surface géométriquement creuse |

L'érosion n'apparaît que là où les 4 signaux convergent — pente douce, en creux, traversée par un flux, dans une vallée. Pas en plaine, pas sur une falaise.

**Avec masque IT sediment — simulation physique**

Instant Terra simule réellement l'écoulement hydraulique et calcule où les sédiments se déposent. Seul le quart supérieur (P75) est retenu — les zones de dépôt les plus intenses.

**La nuance**

L'érosion dans le système représente deux phénomènes géologiquement opposés mais visuellement identiques :
- Les **ravines** — l'eau a arraché la matière → sol nu
- Les **zones de dépôt** — l'eau a déposé de la matière fine → limon

Les deux reçoivent la texture Dirt_03. C'est un compromis acceptable pour Reforger.

---

## Modules disponibles

- **Aperçu Hypsométrique** — rendu couleur altitude avec ombrage
- **Aperçu Texture** — prévisualisation de l'auto-texture avant export
- **Export Masques** — génération des PNG 16-bit par texture
- **Analyse Végétation** — carte de potentiel végétal

---

## Stack technique

| Composant | Technologie |
|---|---|
| Interface | Streamlit |
| Calcul terrain | NumPy / SciPy |
| Morphologie | scipy.ndimage |
| Images | Pillow |
| Langage | Python 3.11+ |

---

## Résultat

Une map 8×8 km entièrement texturée en **quelques minutes**, avec une répartition géographiquement cohérente et zéro violation des contraintes Reforger.

---

---

## Axes d'amélioration

### Pipeline érosion en 2 passes

Actuellement toutes les textures sont calculées en une seule passe simultanée. Une architecture en 2 passes est envisagée :

- **Passe 1** — textures de base (herbe, roche, lande, côtier...)
- **Passe 2** — pipeline érosion (roche + debris_rock + dirt) qui écrase les textures de base là où il s'applique

L'érosion est un phénomène de second ordre — elle agit sur un paysage déjà constitué. La séparer reflète la réalité géologique et permet de calibrer le pipeline érosion indépendamment.

### Zones de transition érosion → herbe

Aux bords des zones d'érosion, une transition douce remplace progressivement la terre par l'herbe :

```
Centre ravine  →  dirt 90%  + herbe 10%
Bord ravine    →  dirt 40%  + herbe 60%
Hors ravine    →  herbe 100%
```

Cette transition est géographiquement correcte (les frontières strictes n'existent pas dans la nature) tant que le blur reste serré. Le seuil de sélection par bloc (2%) empêche les textures de "contaminer" les blocs voisins trop loin de leur zone.

### Variantes de texture roche

La texture roche unique (Rock_01 granite) tile rapidement sur les grandes surfaces. Le pipeline peut distribuer plusieurs variantes selon les signaux terrain déjà disponibles :

| Signal | Ce qu'il révèle | Variante roche |
|---|---|---|
| Slope 70–90° | Falaise verticale | UV alignés sur la pente (slope-aligned) |
| Slope 45–70° | Face inclinée | Rock standard |
| Courbure convexe | Arête exposée au vent | Rock claire, sèche |
| Courbure concave | Fissure, cheminée | Rock sombre, humide, lichen |
| Altitude haute | Surface weathered | Tons froids, texture vieillie |
| Face nord (aspect) | Exposition humide | Rock + lichen sombre |
| Face sud (aspect) | Exposition sèche | Rock claire |

Tous ces signaux (slope, curvature, altitude, aspect) sont déjà calculés dans le pipeline — il suffit de créer les variantes `.emat` dans Reforger et de les brancher sur de nouveaux rôles (`roche_falaise`, `roche_exposee`, `roche_humide`...).

**Tableau des variantes envisagées :**

| Variante | Pente | Exposition | UV Scale | Direction UV | Teinte | Blend |
|---|---|---|---|---|---|---|
| Rock standard | 45–70° | Toutes | UV1 × 1.0 | Horizontal (XY monde) | Neutre | — |
| Rock falaise | 70–90° | Toutes | UV1 × 1.5 | Suit la pente | Neutre | — |
| Rock exposée | 40–75° | Sud / Ouest | UV1 × 0.75 | Horizontal | +10% luminosité | — |
| Rock humide | 40–75° | Nord / Est | UV1 × 1.0 | Horizontal | −20% luminosité | Lichen overlay |
| Rock haute alt. | 35–90° | Toutes | UV1 × 1.2 | Suit la pente | Tons froids, sombre | — |
| Rock transition | 30–45° | Toutes | UV1 × 1.0 | Horizontal | Légèrement chaud | Debris splatter 30% |

> Le budget QTRE à 7 textures devient ici un vrai atout : 3 variantes roche + debris + herbe = 5 slots, encore dans les limites.

### Budget texture dynamique

Reforger supporte jusqu'à 7 textures par bloc. Une gestion dynamique par palier est envisagée :

| Textures/bloc | Statut |
|---|---|
| ≤ 4 | Normal |
| 5 – 6 | Warning |
| 7 | Limite haute |
| > 7 | Bloquant |

### Placement automatique de prefabs rocheux

Reforger dispose de prefabs de falaises (grands rochers, alcôves, arêtes...) qui doivent être placés manuellement. Le pipeline dispose déjà de tous les signaux pour automatiser les candidats de placement :

| Signal | Ce qu'il révèle |
|---|---|
| Slope > 55° | Localisation des falaises |
| Aspect (Nord/Sud/Est/Ouest) | Orientation du prefab à placer |
| Curvature convexe | Arête saillante |
| Curvature concave | Alcôve / renfoncement |
| Longueur zone rocheuse continue | Dimensionnement du prefab |

L'outil produirait un fichier de seeds avec pour chaque point : coordonnées XY Reforger, angle de rotation déduit de l'aspect, et quel prefab recommandé parmi les variantes disponibles. Le principe est identique à l'analyse urbaine qui génère déjà des seeds pour le placement de villes.

> Le placement reste une aide — la validation finale (emboîtement géométrique exact) se fait dans Workbench.

---

## Roadmap — À faire

### Fusion masques intelligente *(priorité haute)*

Cas d'usage : une map partiellement texturée à la main dans Workbench (zones urbaines, champs, forêts placées manuellement) + une partie vierge à générer par auto-material.

**Principe :**
- Exporter tous les masques actuels depuis Workbench (un PNG par texture) → carte complète de l'état existant
- Choisir par type de texture lesquelles sont protégées (urbain, route, champ...) vs laissées à l'auto
- L'auto-material tourne sur toute la map
- Fusion : les textures protégées gardent leur valeur WB, les textures naturelles viennent de l'auto, normalisation finale

```
poids_protégé = somme des masques WB protégés sur ce pixel
poids_auto    = 1 - poids_protégé

texture protégée → valeur WB telle quelle
texture naturelle → score auto × poids_auto
→ normalisation
```

Résultat : zones urbaines/champs préservés exactement, zones naturelles recalculées de façon cohérente sur toute la map.

### Interface calques *(refonte UX)*

Remplacer les onglets cloisonnés par une seule vue carte avec des calques activables/désactivables (hypsométrique, textures, végétation, zones urbaines...), sur le modèle QGIS / Photoshop. Nécessite de remplacer Streamlit par une stack interactive (Plotly ou équivalent). À planifier après stabilisation de la logique métier.

### Pipeline érosion en 2 passes *(amélioration qualité)*

Voir section Axes d'amélioration.

### Variantes de texture roche *(amélioration qualité)*

Voir section Axes d'amélioration.

### Intégration masques IT dans la végétation *(amélioration qualité)*

Le générateur de végétation utilise actuellement uniquement les signaux calculés depuis la heightmap (pente, altitude, TPI, flow). Les masques Instant Terra ne lui sont pas transmis.

Signaux IT exploitables pour la végétation :

| Masque IT | Apport |
|---|---|
| `slope_rock` | Falaises exactes → exclure toute végétation |
| `curvature` convexe | Crêtes exposées → végétation xérophile, rare |
| `curvature` concave | Creux humides → végétation hygrophile, dense |
| `sediment` | Zones de dépôt → ripisylve, fond de vallée |

### Placement automatique de prefabs rocheux *(nouveau module)*

Voir section Axes d'amélioration.

---

*Développé par [otea] Giorbev — projet communautaire*
