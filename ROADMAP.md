# ROADMAP — Map Generator Pro
*Document interne — refactorisation et développement futur*

---

## Vision globale

Outil de génération de textures de terrain pour Reforger, partant d'une heightmap (existante ou créée dans l'outil) et produisant des masques PNG 16-bit prêts à importer dans Workbench.

---

## Entrées

| Source | État | Notes |
|---|---|---|
| Heightmap (.asc) | ✅ Implémenté | 2→16 km², cellsize configurable |
| Création heightmap | ⚠️ Partiel | À compléter |
| Masques Instant Terra | ✅ Implémenté | slope_rock, slope_transition, curvature, sediment |
| SatMap | ⚠️ Partiel | Chargée mais extraction couleurs → masques non faite |

---

## Modules de génération

| Module | État | Notes |
|---|---|---|
| Auto-texture (principe auto-material UE5) | ✅ Fonctionnel | Calibré ZBK, biomes climatiques, pipeline vanilla |
| Végétation | ✅ Fonctionnel | Masques IT non transmis — voir refacto |
| Réseau hydrographique | ❌ À faire | Flow calculé mais non exploité en export |
| Prefabs rocheux (placement) | ❌ À faire | Signaux disponibles (slope, aspect, curvature) |
| Champs (architecture naturelle) | ❌ À faire | Placement naturel selon terrain |
| Urbanisme — villages/villes | ❌ À faire | Module standalone envisagé |

---

## Export

| Sortie | État | Notes |
|---|---|---|
| Masques PNG 16-bit par texture | ✅ Fonctionnel | |
| SatMap depuis textures/fusion | ❌ À faire | Bidirectionnel : satmap → masques et masques → satmap |
| Carte de reconstruction | ⚠️ Présent | Rôle à clarifier |

---

## Problématiques transverses

### 1. Architecture centralisée *(priorité haute)*

**Problème actuel :** les masques IT sont chargés au démarrage mais passés séparément à chaque module. La végétation ne les reçoit pas. Chaque nouveau signal doit être câblé module par module.

**Cible :**
```
Heightmap + IT masks
        ↓
   NatureGen (source unique de vérité)
   slopes, altitude, TPI, flow,
   curvature (numpy OU IT override),
   sediment (numpy OU IT override),
   aspect, coastal, roughness...
        ↓
   ┌──────────────┬────────────────┬──────────────┐
TextureGen   VegetationGen   FusionManager   HydroGen...
```

- Intégrer les masques IT dans `NatureGen` au calcul, pas en override tardif
- Interface uniforme : `generate(nat_gen) → result`
- Ajouter un signal = le brancher une fois dans `NatureGen`

---

### 2. Fusion masques intelligente — cas Zimnitrita *(priorité haute)*

**Problème :** une map partiellement texturée à la main (zones urbaines, champs, forêts) doit pouvoir être enrichie par l'auto-material sans écraser le travail existant.

**Principe :**
1. Exporter tous les masques depuis Workbench (un PNG par texture)
2. Choisir par type de texture lesquelles sont protégées (urbain, route, champ...)
3. L'auto-material tourne sur toute la map
4. Fusion :

```
poids_protégé = somme masques WB protégés sur ce pixel
poids_auto    = 1 - poids_protégé

texture protégée → valeur WB telle quelle
texture naturelle → score auto × poids_auto
→ normalisation → apply_block_budget → export
```

**Cas généralisable :** toute map avec travail manuel existant à préserver.

---

### 3. Debug textures *(priorité moyenne)*

Éviter les erreurs lors de l'application des masques dans Workbench :
- Violations QTRE non détectées avant export
- Pixels sans aucune texture (trous)
- Masques dont la somme ≠ 1 par pixel
- Textures absentes du biome configuré

À définir : rapport de diagnostic avant export (erreurs bloquantes vs warnings).

---

### 4. SatMap bidirectionnelle *(priorité moyenne)*

**Sens 1 — SatMap → masques :**
Extraire les textures depuis les couleurs d'une satmap existante pour initialiser ou corriger les masques.

**Sens 2 — Masques/fusion → SatMap :**
Générer une satmap cohérente depuis les scores de texture ou le résultat de fusion, pour export vers Reforger.

---

### 5. Réseau hydrographique *(priorité moyenne)*

Le flow accumulation est déjà calculé dans `NatureGen`. À exploiter :
- Masque "cours d'eau / zones humides" exportable
- Suggestions de tracés de rivières
- Influence sur végétation (ripisylve) et urbanisme (villages en fond de vallée)

---

### 6. Carte de reconstruction *(à clarifier)*

Le module existe dans l'onglet Calques & Export. Son rôle exact et son utilité dans le pipeline sont à redéfinir.

---

### 7. Champs et urbanisme *(long terme)*

**Champs :** placement naturel sur le terrain (zones planes, exposition, proximité eau).

**Urbanisme :** positionnement de villages/villes selon critères géographiques (défensif, commercial, carrefour...). Peut être un module standalone séparé de l'application principale.

---

## Refactorisation — ordre suggéré

1. **Architecture NatureGen centralisée** — base de tout le reste
2. **Fusion masques intelligente** — cas Zimnitrita, besoin immédiat
3. **Debug textures** — qualité export
4. **Végétation + IT** — quick win une fois NatureGen centralisée
5. **SatMap bidirectionnelle**
6. **Réseau hydrographique**
7. **Prefabs rocheux**
8. **Champs / Urbanisme**
