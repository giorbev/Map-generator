# Analyse déduite de la logique de Bohemia pour `layer.edds`

## Objet du document

Ce document propose une reconstruction de la logique probablement utilisée par Bohemia Interactive pour les terrains de Reforger, à partir des données binaires observées, de la structure des fichiers `.ttile` et `.edds`, ainsi que des essais de décodage réalisés sur des maps natives Workbench.

Il ne s'agit pas d'une spécification officielle de Bohemia. Les éléments ci-dessous sont classés en trois catégories :

- **Fait observé** : directement déduit d'un fichier, d'une structure ou d'un test reproductible.
- **Interprétation probable** : explication cohérente avec les données observées, mais non confirmée par le code source du moteur.
- **À confirmer** : hypothèse qui nécessite d'autres fichiers, d'autres résolutions ou des tests supplémentaires.

---

## 1. Architecture générale en trois niveaux

La logique semble organisée autour de trois niveaux distincts :

1. **Édition** : les données riches et modifiables du terrain.
2. **Baking** : la conversion de ces données en ressources optimisées pour le runtime.
3. **Rendu GPU** : la lecture de données compactes et directement exploitables par le shader.

Le flux général peut être représenté ainsi :

```text
Données riches de l'éditeur
        |
        v
Baking Workbench
        |
        +--> Palette locale de matériaux : LRS2
        |
        +--> Poids par pixel : layer.edds
        |
        +--> Couleur cuite : supertexture.edds
        |
        +--> Relief précalculé : normal.edds
        |
        v
Shader terrain au runtime
```

### 1.1. Niveau éditeur : `.ttile`

Le fichier `Terrain_N.ttile` contient les informations de terrain utilisées par l'éditeur, notamment :

- la heightmap ;
- les structures QTRE ;
- les données de végétation ;
- les matériaux source ;
- le chunk `LRS2`.

Le QTRE et les structures associées semblent adaptés à la construction et à la modification du terrain. En revanche, ils ne constituent pas nécessairement la représentation finale la plus efficace pour le GPU.

### 1.2. Niveau baking : ressources dérivées

Workbench transforme les données d'édition en fichiers spécialisés :

| Fichier | Rôle probable |
|---|---|
| `Terrain_N.ttile` | Données source de terrain et structures d'édition |
| `Terrain_N_layer.edds` | Poids des matériaux par pixel |
| `Terrain_N_supertexture.edds` | Couleur du sol précalculée ou utilisée pour certains LOD |
| `Terrain_N_normal.edds` | Relief utilisé pour l'éclairage et les LOD |

Cette séparation indique qu'une partie importante du calcul est réalisée hors runtime, pendant le baking.

### 1.3. Niveau runtime : shader terrain

Au lancement du jeu, le moteur n'a probablement pas besoin de reconstruire la logique complète du QTRE ou des matériaux source. Il peut lire les ressources déjà préparées et effectuer principalement :

- la sélection des données du bloc courant ;
- le décodage du poids ;
- l'échantillonnage des textures de matériaux ;
- le mélange final des résultats.

Cette organisation réduit le travail CPU et GPU nécessaire au runtime.

---

## 2. La séparation centrale : palette locale et poids par pixel

Le choix architectural le plus important semble être la séparation entre :

- **les matériaux autorisés dans un bloc** ;
- **la proportion de chaque matériau à chaque pixel**.

```text
LRS2                  = quels matériaux sont disponibles dans le bloc
layer.edds            = dans quelle proportion ils sont utilisés au pixel
```

Cette séparation évite de répéter un identifiant de matériau dans chaque pixel. Les identifiants sont stockés une fois dans la palette du bloc, tandis que chaque pixel ne contient que des poids compacts.

C'est une logique classique de palette locale : elle conserve la diversité des matériaux tout en limitant la taille des données de splatting.

---

## 3. LRS2 comme palette locale de matériaux

### 3.1. Organisation spatiale probable

Pour une tuile `layer.edds` de `512×512` pixels, les observations indiquent une grille de blocs de `128×128` pixels :

```text
512 / 128 = 4 blocs par axe
4 × 4 = 16 blocs par tuile
```

Le chunk `LRS2` contient donc, pour une tuile standard de `512×512`, environ 16 palettes locales.

Chaque enregistrement contient :

```text
index       : identifie le bloc
n           : nombre de matériaux du bloc
ids         : identifiants globaux des matériaux
```

Le nombre de matériaux observé est compris entre 1 et 7.

### 3.2. Pourquoi une palette par bloc ?

Une palette locale permet probablement de :

- limiter les matériaux possibles dans une zone géographique donnée ;
- réduire les données nécessaires à chaque pixel ;
- accélérer la recherche des textures à utiliser ;
- garantir que le shader ne manipule qu'un petit nombre de matériaux.

Le GPU n'a donc pas besoin de parcourir la totalité des matériaux de la map. Il travaille avec la petite liste associée au bloc courant.

### 3.3. Pourquoi LRS2 plutôt que BMAT ?

Les observations indiquent que `LRS2` représente la liste réellement associée au rendu de `layer.edds`, tandis que `BMAT` peut rester une liste source de l'éditeur et différer après optimisation.

La logique probable est donc :

```text
BMAT / données source
        |
        v
Optimisation et baking Workbench
        |
        v
LRS2 = palette effectivement utilisée par le layer GPU
```

**Fait important pour le décodage :** la correspondance entre les poids du `layer.edds` et les identifiants de matériaux doit être faite avec `LRS2`.

---

## 4. `layer.edds` comme représentation GPU compacte

### 4.1. Un pixel dans un `uint32`

Les pixels de `layer.edds` sont observés comme des valeurs `R32_UINT`, soit 32 bits par pixel.

La disposition documentée est :

```text
Bits    : 31-30 | 29-25 | 24-20 | 19-15 | 14-10 | 9-5 | 4-0
Valeur  : 00    | w6    | w5    | w4    | w3    | w2  | w1
```

Cela fournit :

- six poids explicites ;
- six champs de 5 bits ;
- deux bits réservés ou inutilisés.

Chaque poids peut prendre une valeur de `0` à `31`.

### 4.2. Le poids implicite `w0`

Le premier matériau n'est pas stocké dans un champ dédié. Il est calculé par complément :

```python
w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)
```

Le résultat garantit une somme constante :

```text
w0 + w1 + w2 + w3 + w4 + w5 + w6 = 31
```

Le choix de cette représentation est très efficace : stocker six poids suffit à reconstruire le septième.

### 4.3. Pourquoi 5 bits ?

Cinq bits donnent 32 niveaux de quantification :

```text
0 à 31
```

Un niveau représente environ :

```text
1 / 31 = 3,2258 %
```

Cette précision est probablement un compromis entre :

- qualité visuelle suffisante pour le mélange des matériaux ;
- taille minimale de la donnée ;
- décodage simple dans un shader.

### 4.4. Contrôles nécessaires

Avant de considérer un pixel comme valide, il faut vérifier :

```python
reserved_bits = pixel_value >> 30
weights = [(pixel_value >> (5 * i)) & 0x1F for i in range(6)]
weight_sum = sum(weights)
w0 = 31 - weight_sum
```

Puis contrôler :

```text
reserved_bits == 0
weight_sum <= 31
0 <= w0 <= 31
```

L'exemple hexadécimal `0x02108421` présent dans les notes historiques doit être recalculé avant d'être utilisé comme vecteur de test. Il ne doit pas être considéré comme validé sans vérification indépendante.

---

## 5. Fonctionnement probable du shader

Le shader terrain pourrait effectuer une opération équivalente à celle-ci :

```python
block_x = pixel_x // 128
block_y = pixel_y // 128

material_ids = lrs2[block_x, block_y]
weights = decode_layer_pixel(layer_pixel)

color = 0
for material_id, weight in zip(material_ids, weights):
    color += sample_material(material_id) * weight
```

En pratique, le shader peut utiliser une organisation différente pour les coordonnées, les textures et les LOD. L'idée fondamentale reste cependant :

1. localiser le bloc ;
2. récupérer sa palette `LRS2` ;
3. décoder les poids du pixel ;
4. retrouver les matériaux correspondants ;
5. mélanger les textures selon ces poids.

### 5.1. Pourquoi cette approche est adaptée au GPU

Cette organisation évite au GPU de :

- parser une structure QTRE complexe ;
- parcourir toute la bibliothèque de matériaux ;
- recalculer la distribution des textures ;
- manipuler des données d'édition inutiles au rendu.

Le shader reçoit une représentation presque finale, régulière et compacte.

---

## 6. Le baking comme frontière entre édition et rendu

Le baking Workbench semble jouer le rôle de frontière entre deux mondes :

```text
Monde de l'édition : riche, flexible, détaillé
Monde du runtime  : compact, régulier, optimisé
```

La conversion peut être résumée ainsi :

```text
QTRE / BMAT / terrain source
        |
        |  analyse, optimisation, regroupement spatial
        v
LRS2 + layer.edds + supertexture + normal map
```

La logique exacte qui transforme les données source en poids n'est pas connue dans les données analysées. Il est probable que Workbench prenne en compte les matériaux du terrain et leur distribution spatiale, mais le document actuel ne permet pas d'affirmer quels paramètres déterminent précisément les poids.

Il reste notamment à déterminer si le baking utilise :

- uniquement les poids de la peinture de terrain ;
- des règles liées aux matériaux ;
- des seuils de transition ;
- la pente ou l'altitude ;
- des paramètres de résolution ;
- une combinaison de plusieurs sources.

---

## 7. Les différents fichiers `.edds`

Les fichiers associés à une tuile ne semblent pas être des copies redondantes. Ils répondent à des usages différents :

### `layer.edds`

Représentation des poids de matériaux. Elle permet un mélange dynamique des textures au runtime.

### `supertexture.edds`

Couleur du sol précalculée, probablement utile pour afficher rapidement le terrain, pour certains LOD ou pour réduire le coût du rendu à distance.

### `normal.edds`

Données de relief destinées à l'éclairage et aux détails visuels lorsque la géométrie ou les informations détaillées du terrain ne sont plus utilisées de la même manière.

L'utilisation exacte de chaque fichier selon la distance, le LOD et le chemin de rendu reste à confirmer.

---

## 8. Les mips et le stockage EDDS

Les observations montrent une différence entre l'index logique DDS et l'ordre physique des blobs EDDS :

```text
Index logique DDS : mip 0 = plus grande résolution
Ordre de stockage EDDS observé : plus petit mip vers plus grand mip
```

Pour une texture `512×512`, la première entrée peut donc correspondre au mip `1×1`, tandis que le mip pleine résolution apparaît à la fin de la table.

Cette organisation peut être liée à :

- un choix historique du conteneur ;
- une logique de chargement progressif ;
- une gestion des LOD ;
- une contrainte du système de streaming ;
- la manière dont les données sont écrites par le pipeline de baking.

**À confirmer :** la raison exacte de cet ordre inversé ne peut pas être déduite uniquement de la structure observée.

---

## 9. Compression LZ4 par chunks chaînés

### 9.1. Organisation observée

Les grandes données LZ4 sont divisées en tranches de `65536` octets, soit `64 Ko` :

```text
[u32 taille décompressée totale]
[u32 taille compressée][chunk 0]
[u32 taille compressée][chunk 1]
[u32 taille compressée][chunk 2]
...
```

Les observations indiquent le comportement suivant :

```text
chunk 0 : compressé sans dictionnaire
chunk 1 : compressé avec chunk 0 décompressé comme dictionnaire
chunk 2 : compressé avec chunk 1 décompressé comme dictionnaire
...
```

### 9.2. Pourquoi chaîner les chunks ?

Les données voisines d'une carte de poids sont souvent corrélées. Le chunk suivant peut donc réutiliser des séquences présentes dans le chunk précédent.

Le chaînage permet probablement de combiner :

- une bonne compression ;
- une taille de bloc maîtrisée ;
- une décompression par morceaux ;
- une consommation mémoire limitée.

Cette conclusion est plausible, mais l'objectif interne exact de l'implémentation Bohemia reste à confirmer.

### 9.3. Limite de la preuve actuelle

Le chaînage a été observé sur des fichiers natifs Workbench, notamment `ZBK_terrain_3560_layer.edds`. Il est raisonnable de l'implémenter comme obligatoire pour les fichiers 512×512 étudiés.

Il faut cependant éviter de transformer prématurément cette observation en règle universelle pour tous les `.edds` de toutes les maps et versions du moteur.

---

## 10. Reconstruction du pipeline complet

La logique probable peut être résumée ainsi :

```text
1. L'utilisateur édite le terrain et ses matériaux.
2. Les données source sont conservées dans le .ttile.
3. Workbench regroupe localement les matériaux par bloc.
4. Workbench écrit ces palettes dans LRS2.
5. Workbench convertit les poids en champs de 5 bits.
6. Le premier poids est stocké implicitement par complément.
7. Les pixels sont écrits dans layer.edds.
8. Les mips sont générés.
9. Les blobs sont éventuellement compressés par chunks LZ4 chaînés.
10. Le runtime charge les ressources dérivées.
11. Le shader décode LRS2 et layer.edds pour composer le terrain.
```

En formule conceptuelle :

```text
Terrain source
    -> optimisation spatiale
    -> palettes locales LRS2
    -> quantification des poids
    -> layer.edds
    -> compression et mips
    -> rendu GPU
```

---

## 11. Ce qui est établi et ce qui reste hypothétique

### Éléments fortement établis par les observations

- `layer.edds` contient des valeurs `R32_UINT` pour les masques observés.
- Les poids sont codés dans des champs de 5 bits.
- Le premier poids est implicite par complément à 31.
- `LRS2` contient la liste locale des matériaux par bloc.
- `LRS2` doit être utilisé pour associer les poids aux identifiants de matériaux.
- Les données EDDS observées peuvent être stockées du plus petit mip vers le plus grand.
- Les grandes données LZ4 observées utilisent un chaînage entre chunks.
- Les ressources `.edds` sont des sorties dérivées du pipeline de baking.

### Interprétations probables

- Le découpage en palettes locales est destiné à réduire la taille et le coût du rendu GPU.
- Le format `uint32` est choisi pour permettre un décodage très rapide dans le shader.
- Le baking sépare volontairement les données riches de l'éditeur des données régulières du runtime.
- Le découpage LZ4 en chunks vise un compromis entre compression, streaming et mémoire.
- `supertexture.edds` et `normal.edds` servent à compléter ou remplacer certaines informations du `layer.edds` selon le LOD.

### Points à confirmer

- La signification exacte des deux bits 30-31.
- La position exacte du marqueur `ENF1` dans le conteneur.
- La raison technique de l'ordre inversé des mips.
- La généralisation du LZ4 chaîné à toutes les maps et toutes les résolutions.
- La méthode exacte utilisée par Workbench pour calculer les poids.
- Les seuils et règles de regroupement des matériaux dans une palette LRS2.
- Le rôle exact de chaque `.edds` selon les LOD et les chemins de rendu.
- La correspondance exacte entre la taille physique d'une tuile et la couverture d'un texel.

---

## 12. Conclusion

La logique de Bohemia semble reposer sur un principe simple et efficace :

> **Séparer la connaissance des matériaux de leurs poids par pixel, puis convertir ces informations dans une forme compacte et directement lisible par le GPU.**

`LRS2` répond à la question :

```text
Quels matériaux peuvent être utilisés dans ce bloc ?
```

`layer.edds` répond à la question :

```text
Dans quelle proportion ces matériaux sont-ils utilisés à ce pixel ?
```

Le `.ttile` reste la représentation riche de l'éditeur. Le baking produit ensuite une représentation spécialisée pour le rendu : palettes locales, poids quantifiés, mips et compression. Le runtime n'a plus qu'à décoder cette représentation préparée.

Cette analyse est suffisamment solide pour guider un décodeur, un outil de vérification et une première implémentation d'encodage. Elle ne doit toutefois pas être présentée comme une documentation officielle tant que les points listés dans la section **À confirmer** n'ont pas été vérifiés sur davantage de fichiers et de configurations.
