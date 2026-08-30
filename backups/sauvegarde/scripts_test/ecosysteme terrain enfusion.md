===============================================================================
SPÉCIFICATIONS TECHNIQUES : L'ÉCOSYSTEME DU TERRAIN ENFUSION (REFORGER)
===============================================================================
Objectif : Comprendre l'architecture, le stockage binaire, l'indexation des 
textures et les règles procédurales pour permettre la lecture brute, l'injection 
automatisée (scripts d'érosion, génération de Satmap) et le contrôle total du 
terrain par script Python.

===============================================================================
PARTIE I : ARCHITECTURE ET FICHIERS MAÎTRES
===============================================================================

-------------------------------------------------------------------------------
1. LA "SAINTE TRINITÉ" DES FICHIERS DE TERRAIN
-------------------------------------------------------------------------------
Le fonctionnement du terrain repose sur l'interaction synchrone de trois
fichiers clés. Si l'un d'eux est mal interprété, l'affichage in-game ou dans
le script est décalé.

A. terrain.terr (Le Cerveau / L'Interface UI) :
   - Rôle : C'est le fichier maître de ton monde 3D.
   - Secret technique : Il contient une section binaire nommée "MATS". C'est
     elle (et elle seule) qui dicte l'ordre visuel absolu des textures que tu
     vois s'afficher dans le menu du Terrain Tools dans le Workbench.

B. terrain_materials_list.txt (L'Index / Le Traducteur) :
   - Rôle : Il sert de dictionnaire de traduction pour le moteur et les scripts.
   - Spécificité : Il est le miroir strict de la section MATS. Il attribue
     un ID numérique incrémental (0, 1, 2, 3...) à chaque matériau (.emat)
     selon cet ordre exact.
   - Structure : Les matériaux personnalisés (custom) ouvrent la marche en
     tête de liste, suivis des matériaux d'origine (vanilla).

C. Terrain_N_Layer.edds (Les Données Brutes / Les Tuiles) :
   - Rôle : C'est le calque brut de ta carte, stocké tuile par tuile (N = numéro
     de la tuile ou coordonnées X_Y).
   - Avantage majeur : Contrairement aux fichiers optimisés du dossier .data
     (qui sont compressés en LZ4 et simplifiés pour la carte graphique via un
     système de QuadTree / QTRE), les fichiers du dossier .EditorData sont
     bruts de fonderie et non modifiés. Ils offrent une précision absolue :
     une recette de texture unique sur chaque pixel.

===============================================================================
PARTIE II : STRUCTURES BINAIRES ET ENCODAGE
===============================================================================

-------------------------------------------------------------------------------
2. LE RELIEF : STRUCTURE DU FICHIER GÉOMÉTRIQUE (.bterr)
-------------------------------------------------------------------------------
Situé dans le répertoire `.EditorData`, le fichier `Terrain_N.bterr` gère 
la topographie physique sous forme de maillage brut de sommets (vertices).

   - Matrice brute : 129 × 129 valeurs en Float32 (Single Precision).
   - Métrique : Chaque cellule représente un carré de 4.0m × 4.0m réels.
   - Résolution physique d'une tuile : 512m × 512m réels.
   - Comportement des altitudes : Accepte les valeurs négatives (ex: sous 0.0m) 
     pour creuser les fonds marins.

-------------------------------------------------------------------------------
3. LA PEINTURE : STRUCTURE ET BIT-PACKING DU CALQUE (_layer.dds)
-------------------------------------------------------------------------------
Le fichier `Terrain_N_layer.dds` applique les textures au sol. Contrairement au 
relief, il s'aligne sur les faces (pixels) et utilise un format non compressé.

   - Format DX10 : R32_UINT (Entier non signé 32 bits, canal unique Rouge).
   - Dimensions : 512 × 512 pixels (Indépendant de la grille 129x129 du relief).
   - Header binaire : 148 octets immuables (128 octets DDS standard + 20 octets DX10).
   - Encodage des couches : Bit-packing par blocs de 5 bits (2^5 = 32 poids).

   Schéma d'allocation des 32 bits d'un pixel :
   [ 2 bits ] [ 5 bits ] [ 5 bits ] [ 5 bits ] [ 5 bits ] [ 5 bits ] [ 5 bits ]
     Inutiles     w6         w5         w4         w3         w2         w1
               (bits 25-29) (bits 20-24) (bits 15-19) (bits 10-14) (bits 5-9)  (bits 0-4)

   Chaque pixel stocke la "recette" du sol codée sur 32 bits. Le moteur d'Enfusion 
   l'exploite selon des règles mathématiques très strictes :

   - Le mixage maximal : Le moteur peut mélanger jusqu'à 7 textures
     simultanément sur un seul et même pixel.
   - L'échelle des poids (Le Poids Enfusion) : Chaque texture reçoit une note de
     force (le poids) allant de 0 (absente) à 31 (force maximale). Cette valeur
     est codée sur 5 bits (2^5 = 32 possibilités).

-------------------------------------------------------------------------------
4. LA "SAINTE TRINITÉ" DES POIDS DE TEXTURES (w0 à w6)
-------------------------------------------------------------------------------
Le moteur Enfusion gère jusqu'à 7 couches de textures utilisables par pixel, 
indexées sur une plage de dynamique d'intensité entière allant de 0 à 31.

   - w1 à w6 : Couches explicites lues par décalage de bits (*bit-shift*).
   - w0 (Couche de base) : Entièrement IMPLICITE et SOUSTRACTIVE. Elle n'occupe 
     aucun bit dans le fichier. Sa valeur est calculée en temps réel par le moteur.

   Formule mathématique de cohérence (Plafond Enfusion) :
   w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

   L'astuce d'espace (La soustraction du canal L0) : Pour économiser de la
   mémoire, le fichier ne stocke physiquement que 6 textures (les canaux L1 à L6).
   La première texture (la couche de base, L0) est calculée automatiquement par
   le moteur en faisant la soustraction du reste.

   > Exemple concret : Si tu peins du Grass_02 (couche de base) sur toute ta
     tuile, elle n'est pas écrite. Le script lira L1 à L6 à 0. Le moteur fait
     le calcul : 31 - 0 = 31. Ta texture de base est au maximum.

===============================================================================
PARTIE III : LOGIQUE AVANCÉE ET DÉCENTRALISATION
===============================================================================

-------------------------------------------------------------------------------
5. LA DECENTRALISATION DU SOL : LE SYSTEME DE LOGIQUE "PAR TUILE"
-------------------------------------------------------------------------------
Une des plus grandes évolutions du moteur Enfusion réside dans sa gestion
sectorisée du terrain appelée "Material Grid" (Grille de Matériaux).

A. Pixel-Perfect vs Configuration Locale :
   - Au pixel près (Le mélange) : La formule mathématique (31 - somme des autres)
     s'applique individuellement sur chaque pixel de 128x128 ou 512x512.
   - À la tuile près (L'attribution) : L'affectation de "quel matériau correspond
     à quel index binaire" est gérée de manière totalement indépendante pour
     chaque tuile de 512x512 pixels.

B. Une Couche de Base (L0) caméléon :
   Enfusion n'impose pas la même texture L0 sur l'ensemble de la carte.
   - Une tuile située en plaine aura pour couche de base (L0) de l'herbe grasse.
   - Une tuile située sur le littoral ou un lit de rivière aura pour couche
     de base (L0) du sable ou des galets.
   - Conséquence script : Remettre les canaux L1 à L6 à 0 sur un pixel fera
     apparaître automatiquement la texture de base propre à cette tuile (de l'herbe
     ici, du sable là), optimisant drastiquement l'espace binaire car le "fond"
     n'a jamais besoin d'être peint manuellement.

C. Texture Mapping Local (Index interchangeables) :
   De la même manière, les index de peinture (Canal Rouge L1, Canal Vert L2...)
   peuvent représenter des matériaux différents d'une tuile à l'autre. Le Canal
   Rouge peut appeler de la roche en haute montagne et de la boue de marécage
   dans les plaines basses.

   > Note pour le développement : Cette configuration est stockée à côté des
     fichiers de poids .dds, dans les fichiers de métadonnées de la carte (ex:
     MaterialGrid, fichiers .et ou .layer). Lors d'une modification globale par
     script, il faut veiller à lire ces correspondances locales si la carte utilise
     une Grille de Matériaux sectorisée.

===============================================================================
PARTIE IV : RÈGLES DE VALIDATION ET CONTRAINTES PROCÉDURALES
===============================================================================

-------------------------------------------------------------------------------
6. RÈGLES DE VALIDATION POUR L'INJECTION PYTHON DIRECTE
-------------------------------------------------------------------------------
Tout script modifiant directement les fichiers `.bterr` et `_layer.dds` doit 
impérativement valider ces deux garde-fous pour éviter les crashs visuels :

   A. Rééchantillonnage de la géométrie (129 -> 512) :
      Les masques calculés sur le relief (pentes via gradient, courbures via 
      laplacien en 129x129) doivent subir une interpolation spatiale (ex: bilinéaire) 
      pour s'aligner parfaitement sur la matrice 512x512 de la texture de calque.

   B. Clamping et Normalisation Anti-Saturation :
      Si la somme cumulée des poids injectés (w1 + w2 + ... + w6) dépasse 31, 
      le calcul de w0 produit un débordement binaire (*overflow*). Le script doit 
      écrêter (*clip*) les valeurs et réduire proportionnellement les canaux pour 
      garantir que Σ(w1..w6) ≤ 31.

-------------------------------------------------------------------------------
7. INJECTION DE MASQUES : LE WORKFLOW OFFICIEL D'IMPORTATION (WORKBENCH UI)
-------------------------------------------------------------------------------
Si la création de masques passe par l'interface graphique du Workbench (Terrain Tools) 
plutôt que par l'écriture binaire directe par script, le moteur Enfusion impose 
un workflow strict couche par couche.

A. Spécifications des Fichiers de Masque :
   Contrairement à d'autres moteurs gérant le packing RGB, l'importateur d'Enfusion 
   ne lit JAMAIS les canaux de couleur composites. 
   - Format requis : Image en niveaux de gris (Grayscale) uniquement.
   - Extensions : .PNG (recommandé) ou .TGA.
   - Profondeur : PNG 16-bit (fortement recommandé pour préserver les dégradés 
     et éviter les transitions abruptes/crénelées) ou PNG 8-bit.

B. Processus d'Importation dans l'UI :
   L'association se fait de manière unitaire dans le panneau des Terrain Tools. 
   L'utilisateur doit charger un fichier image indépendant pour chaque index 
   de matériau (ex: un PNG 16-bit dédié uniquement à l'érosion 'Debris', un autre 
   dédié à la 'Falaise').

C. Pourquoi le pipeline Python (Écriture Directe) est supérieur :
   Passer par l'UI du Workbench oblige à exporter 6 fichiers PNG distincts depuis 
   un logiciel de génération (comme Gaea) pour chaque tuile de la carte, puis à 
   les importer manuellement un par un. 
   En manipulant directement le fichier binaire unique `_layer.dds` via NumPy, 
   le script Python injecte les 6 canaux simultanément en une seule opération de 
   bit-packing, éliminant l'étape fastidieuse de l'importateur visuel.

   Note importante : L'importation de masques via l'UI du Workbench s'applique 
   toujours à l'échelle GLOBALE de la carte (toutes les tuiles concernées par 
   le masque), jamais bloc par bloc. C'est un comportement normal et documenté.

-------------------------------------------------------------------------------
8. BUG CRITIQUE : RÉGÉNÉRATION .EDDS ET MATÉRIAUX PARTAGÉS
-------------------------------------------------------------------------------
Découvert lors de tests d'injection Python (Juillet 2026), ce bug affecte la 
régénération du fichier runtime `.edds` depuis le fichier éditeur `_layer.dds`.

A. Description du Bug :
   Quand le Workbench régénère le fichier `.edds` (runtime optimisé pour GPU) 
   depuis le `_layer.dds` (éditeur modifié par script), il applique une 
   optimisation défectueuse qui propage les modifications au-delà du bloc ciblé.

B. Conditions de Déclenchement :
   Le bug se manifeste UNIQUEMENT si :
   1. Plusieurs blocs (128×128) de la même tuile partagent le MÊME matériau en L0
   2. Un script externe modifie le fichier `_layer.dds` d'UN SEUL de ces blocs
   3. Le fichier `.edds` est supprimé et le Workbench le régénère automatiquement

   Résultat : Les modifications s'appliquent à TOUS les blocs partageant ce 
   matériau L0, au lieu de respecter les poids pixel par pixel du `_layer.dds`.

C. Explication Technique :
   Le compilateur `.edds` d'Enfusion regroupe/optimise les blocs ayant le même 
   matériau de base (L0) pour réduire la taille du fichier runtime. Lors de cette 
   optimisation, il traite les blocs comme un groupe au lieu de préserver les 
   variations pixel par pixel du fichier source.

D. Workaround Validé :
   Avant d'injecter une texture par script Python dans un bloc spécifique :
   1. Vérifier via l'analyseur que le matériau cible n'est présent en L0 que 
      dans le bloc à modifier
   2. Ou nettoyer manuellement les blocs voisins pour qu'ils aient un L0 différent
   3. Effectuer l'injection → Supprimer le `.edds` → Rouvrir le Workbench

   Si les blocs ont des matériaux L0 différents, la régénération est correcte.

E. Impact sur le Pipeline :
   - Import de masques via l'UI : Non affecté (applique à toute la carte volontairement)
   - Injection par script bloc par bloc : Affecté (propagation involontaire)
   - Modification du `.edds` directement : Contourne le bug (pas de régénération)

F. Statut :
   Bug confirmé et reproductible sur Arma Reforger Workbench 1.7.0.54 (Juillet 2026).
   Solution permanente : Modifier directement le fichier `.edds` au lieu du `_layer.dds`, 
   ou attendre un correctif du moteur Enfusion.

===============================================================================
PARTIE V : CONFIGURATION MATÉRIAUX ET PHYSIQUE
===============================================================================

-------------------------------------------------------------------------------
8. ZOOM SUR LE FICHIER DE MATÉRIAU : L'.emat
-------------------------------------------------------------------------------
L'.emat est la carte d'identité visuelle et physique d'une surface dans le jeu.
C'est un fichier texte éditable qui contient :
- Les fichiers BCR (Base Color Roughness) et MNO (Metal Normal Occlusion) pour
  le rendu visuel proche.
- Le fichier Middle (la texture moyenne) associé.
- La distance de fondu, à partir de laquelle la texture de près s'efface pour
  laisser place à la texture Middle.

💡 Application pour le processus de Satmap procédurale :
   Pour générer par script une Satmap globale parfaite et réaliste vue du ciel,
   il ne faut pas utiliser les textures de près, mais extraire et associer les
   textures "Middle" de chaque .emat en les appliquant selon les poids d'ID
   découverts dans ton fichier Terrain_N_Layer.edds, tout en vérifiant le matériau
   L0 spécifique assigné à la tuile en cours de traitement.

-------------------------------------------------------------------------------
9. CONFIGURATION DIRECTE DES MATÉRIAUX (.emat) ET PHYSIQUE (.st)
-------------------------------------------------------------------------------
Pour lier l'indexation binaire d'un canal (w_n) à un rendu en jeu, le moteur 
croise deux fichiers texte modifiables :

   - Le fichier Matériau (.emat) : Associe l'index (w_1, w_2, etc.) aux textures 
     visuelles (Albedo, Normal Map, Rugosité) chargées par le shader de terrain.

   - Le fichier de Surface (.st - Surface Type) : Détermine les propriétés physiques 
     liées à l'index de la texture (coefficient de friction des véhicules, résistance 
     au roulement, sons de pas, et nature des particules émises lors d'un impact).

===============================================================================
PARTIE VI : SYNERGIE PROCÉDURALE ET AUTOMATISATION
===============================================================================

-------------------------------------------------------------------------------
10. SYNERGIE DE PEUPLEMENT PROCÉDURAL (Generators & EnfusionScript)
-------------------------------------------------------------------------------
Le placement automatisé de la flore et des micro-débris (arbres, structures, 
rochers) n'est pas calculé en temps réel (PCG dynamique), mais s'appuie sur une 
génération semi-automatisée initiée depuis le World Editor (ex: ForestGeneratorEntity).

   A. Le mécanisme du pont (Weightmap Masking) :
      Au lieu de tracer des zones manuelles à la main, ces entités de génération 
      configurées dans le Workbench acceptent un "Weightmap Mask". On peut leur 
      indiquer par exemple de lire l'intensité du canal de texture w1.

   B. Automatisation par EnfusionScript (WorkbenchPlugin) :
      L'API d'Enfusion permet de créer des outils d'édition en C# (EnfusionScript) 
      pour piloter ces entités. Un script d'éditeur peut cibler un générateur, lui 
      assigner un canal de texture spécifique (ex: ForestGen.SetWeightmapChannel(1)),
      définir un seuil d'apparition, et déclencher par code son recalcul global 
      (ForestGen.Regenerate()).

   C. Application pour le pipeline :
      L'intelligence mathématique (détecter où la forêt doit pousser) est calculée 
      en amont en Python en écrivant la valeur cible dans le fichier `_layer.dds`.
      Le peuplement physique 3D est ensuite exécuté instantanément dans le Workbench, 
      soit d'un clic sur le générateur, soit via un script d'automatisation d'éditeur.

===============================================================================
PARTIE VII : APPLICATIONS PRATIQUES ET DÉCOUVERTES MAJEURES
===============================================================================

-------------------------------------------------------------------------------
11. APPLICATION PRATIQUE : LA RECETTE DE TON ÉROSION (Debris_Rock_01)
-------------------------------------------------------------------------------
Grâce à l'analyse pixel-perfect menée sur le bloc de référence [2x2] (issu de
la tuile 737), voici les constantes mathématiques exactes à appliquer dans
tes futurs scripts de génération procédurale pour reproduire ton érosion manuelle :

- Le Canal Cible : L'érosion de type éboulis/coulée de graviers (Debris_Rock_01)
  se programme directement dans le Canal Rouge (R) du fichier de calque.
- Le Seuil de Force : La valeur maximale à injecter pour obtenir l'intensité
  de ton travail fait main est 15 (le plafond de codage sur 4 bits de ce
  sous-canal).
- L'Algorithme de Dispersion : Pour imiter fidèlement la nature, ton script
  doit distribuer cette valeur de 15 sur environ 50% de la surface du bloc,
  en ciblant uniquement les zones de rupture de pente (au pied des fortes
  pentes de Rock_01).

-------------------------------------------------------------------------------
12. POURQUOI CETTE DÉCOUVERTE EST MAJEURE ?
-------------------------------------------------------------------------------
Cette cartographie complète casse définitivement les limites du Workbench :

1. Sauvegarde et Visualisation : Plus besoin de s'embêter à exporter/importer
   ... On peut lire la tuile brute et prévisualiser le rendu exact en combinant
   les textures Middle, tuile par tuile, selon leur propre dictionnaire local.

2. Écriture et Automatisation : Tu as désormais le pouvoir d'ajouter ou d'échanger
   des textures chirurgicalement. Remplacer une texture par une autre revient
   simplement à déplacer mathématiquement les paquets de bits d'un canal à un
   autre (ex: transférer les bits du canal Vert L2 vers le canal Rouge L1) ou
   à vider un canal pour laisser la couche de base locale (L0) saturer le pixel.

3. Intelligence Procédurale : Un script Python peut analyser le relief (.bterr),
   repérer les falaises, adapter son comportement selon la nature de la tuile
   (plage, montagne, forêt) et injecter instantanément l'érosion adéquate.

===============================================================================
GLOSSAIRE ET RÉFÉRENCES
===============================================================================

Termes clés :
- MATS : Section binaire du fichier .terr contenant l'ordre des matériaux
- QTRE : QuadTree Encoding (compression runtime pour GPU)
- BCR : Base Color Roughness (texture albedo + rugosité)
- MNO : Metal Normal Occlusion (texture métallique + normale + occlusion)
- Material Grid : Système de gestion sectorisée des matériaux par tuile
- Weightmap Masking : Mécanisme de liaison entre canaux de texture et générateurs

Fichiers critiques :
- .bterr : Relief géométrique (129×129 Float32)
- _layer.dds : Peinture texture (512×512 R32_UINT)
- .terr : Fichier maître (contient section MATS)
- .emat : Définition matériau (textures + propriétés visuelles)
- .st : Surface Type (propriétés physiques)

===============================================================================
