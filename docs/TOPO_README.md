# Carte topo d'Arma Reforger : la méthode Giorbev + Claude

Comment obtenir une carte en jeu lisible et juste : eau exacte, courbes de niveau fines, cultures, fond satellite ou militaire années 80. Méthode testée en jeu sur ZBK et Zimnitrita (novembre 2026, Workbench 1.9).

## Qui dessine quoi

| Élément | Fait par | Source |
|---|---|---|
| Fond (relief, forêts, cultures, zones bâties, eau) | **MGP**, onglet TOPO | PNG importé, « Satellite background image » de `SCR_MapEntity` |
| Routes, bâtiments, formes des lacs et rivières | Workbench | Export `.topo` |
| Courbes de niveau | Le jeu, depuis le terrain | Config de carte du mode de jeu |
| Noms des villes et des lieux | Le jeu | `SCR_MapDescriptorComponent` posés dans le monde |

Le `.topo` ne contient pas de zones de cultures : les champs ne peuvent passer que par l'image de fond.

## Dans quel ordre

1. Corriger l'eau dans les `.layer` (facultatif, voir plus bas).
2. Exporter le `.topo` dans Workbench.
3. Générer le fond de carte dans MGP (il lit le `.topo` pour les zones bâties).
4. Importer le PNG dans Workbench et le choisir dans `SCR_MapEntity`.
5. Brancher la config des courbes sur le mode de jeu.
6. Tester en jeu : **sans GameMode, la carte ne s'ouvre pas**.

Le fond est une image figée. À regénérer si le relief, les arbres, les textures, l'eau ou les bâtiments changent.

## 1. L'eau

Le `.topo` dessine **la forme du lac et toute la bande `Width` de la rivière**, pas l'eau réelle : une forme large donne une eau trop large sur la carte. Il faut donc ajuster les formes à l'eau.

**Où est l'eau en jeu**
- Lac : niveau = point le plus bas de la forme + décalage `coords` du générateur + `m_fWaterSurfaceOffset`. Eau = terrain sous ce niveau, dans la forme.
- Rivière : niveau = hauteur de la ligne + décalage du générateur + `WaterOffset` + `SplineOffsetUp`. Eau = terrain sous ce niveau, dans la bande `Width`.

**Lacs**
- Limiter la forme à environ 60 points : à 150 points, le générateur abandonne (« Too many points to generate, terminating »), le lac n'a plus d'eau et disparaît de la carte.
- Garder les points d'origine là où l'eau touche le trait (barrage, déversoir) et ne refaire que la rive libre, à environ 3 m de l'eau.
- Ne jamais faire de crochet à points superposés : le générateur échoue sans message.

**Rivières**
- `Width` ne fait que limiter la bande : le réduire ne change pas l'eau tant que la bande la couvre entièrement.
- Couper en tronçons de largeur homogène, avec `Width` = eau + 3 m de chaque côté, et **un segment de recouvrement** entre tronçons (sinon coin sec dans les virages).
- Faire partir la rivière 25 m dans le lac, au niveau du lac.
- Points de l'amont vers l'aval : mettre `ReverseFlow 1`, sinon le courant est à l'envers.

**Scripts** : pas encore intégrés à MGP. Ils sont dans `_archives/analyses/2026-11-05_eau_giorbev/` (`lire.py`, `lacs.py`, `rivieres.py`, `ecrire.py`, `bilan_topo.py`) et réglés pour Zimnitrita. Ils écrivent dans `sortie/`, sans toucher au mod.

Ne pas modifier les calques des autres membres sans leur accord. Workbench réenregistre beaucoup de calques en fermant : après un simple contrôle, fermer sans enregistrer.

## 2. Export du `.topo`

Dans Workbench : menu Tools, « Export Map Data », avec un dossier de destination **de l'addon en cours**. Une destination gardée d'un autre projet fait échouer l'export : resélectionner le dossier. Renseigner le fichier obtenu dans « Map Geometry Data » de `SCR_MapEntity`.

## 3. Fond de carte dans MGP

Page Satmap, onglet **TOPO** :
- **Satellite** : part de la dernière satmap du projet (à générer avant), mer recolorée à la couleur exacte de la carte, curseurs de réglage.
- **Militaire années 80** : pas besoin de satmap. Papier crème, relief estompé, forêts, cultures, zones bâties, eau. Sans `.topo`, pas de zones bâties.

Sortie dans `outputs/generated/` : `fond_topo_<taille>.png` ou `fond_topo_militaire_<taille>.png`.

## 4. Import dans Workbench

1. Copier le PNG dans l'addon et l'importer. Les dimensions doivent être **divisibles par 4** (4096, 8192 : c'est le cas des sorties de MGP), sinon « reimport failed ».
2. Import Settings > PC > **Color Space = `ToSRGB`**, puis réimporter. Le défaut `ToLinear` éclaircit toute l'image.
3. Sélectionner `SCR_MapEntity` et choisir le `.edds` dans « Satellite background image ».

## 5. Courbes de niveau

Elles se règlent dans une config qui hérite de `Configs/Map/MapFullscreen.conf` : créer le fichier dans l'addon sans toucher à celui du jeu. Modèle : `_archives/analyses/2026-11-05_courbes/MapFullscreen_Zimnitrita.conf`.

| Zoom | `m_fContourDensity` | `m_fMajorContourDensity` |
|---|---|---|
| 1 (le plus proche) | 5 m | 25 m |
| 2 | 10 m | 50 m |
| 3 | 20 m | 100 m |
| 4 | 50 m | 250 m |

Style : `m_fContourWidth` 1,3, `m_fMajorContourWidth` 2,6, `m_LandColor` 0.28 0.12 0.05 0.95.

**Brancher la config sur le mode de jeu** : `SCR_MapConfigComponent` du GameMode, champ `m_sGadgetMapConfigPath`. Le même composant posé sur `SCR_MapEntity` ne sert à rien. À faire pour le mode de jeu de chaque scénario.

## En cas de problème

| Symptôme | Cause |
|---|---|
| La carte se ferme ou ne s'ouvre pas | Pas de GameMode dans le monde |
| Lac à sec et absent de la carte | Trop de points dans la forme |
| Eau coupée net le long d'un lac | Forme trop petite : décalage du générateur oublié dans le niveau |
| Fond trop pâle | Import en `ToLinear` au lieu de `ToSRGB` |
| « reimport failed » | Dimensions non divisibles par 4 |
| Export `.topo` en erreur | Destination gardée d'un autre projet |
| Courant à l'envers | `ReverseFlow` à régler |
