/**
 * Map Generator Pro v7.0 — i18n
 * Système de traduction FR / EN
 * Langue par défaut : EN
 * Usage : inclure AVANT log_panel.js en fin de <body>
 *         Ajouter data-i18n="key" sur chaque élément à traduire
 *         Ajouter data-i18n-placeholder="key" pour les placeholders
 */

(function() {
  'use strict';

  // ── Dictionnaire ─────────────────────────────────────────────────────────────
  var _dict = {

    // ── Commun ──────────────────────────────────────────────────────────────────
    'nav.back':           { EN: '◀ Navigation', FR: '◀ Navigation' },
    'nav.projects':       { EN: '◀ Projects',   FR: '◀ Projets' },
    'nav.home':           { EN: '◀ Home',        FR: '◀ Accueil' },
    'active.project':     { EN: 'Active project', FR: 'Projet actif' },
    'session.active':     { EN: 'SESSION ACTIVE', FR: 'SESSION ACTIVE' },
    'loading':            { EN: 'Loading...',    FR: 'Chargement...' },
    'save.ok':            { EN: '✓ SAVED',       FR: '✓ SAUVEGARDÉ' },
    'btn.save':           { EN: '💾 Save',        FR: '💾 Sauvegarder' },
    'btn.reset':          { EN: '↺ Reset',        FR: '↺ Réinitialiser' },
    'btn.open.folder':    { EN: '📂 Open project folder', FR: '📂 Ouvrir le dossier projet' },
    'btn.browse':         { EN: '📂 Browse',      FR: '📂 Parcourir' },
    'btn.folder':         { EN: '📂 Folder',      FR: '📂 Dossier' },
    'btn.delete':         { EN: '🗑️ Delete',      FR: '🗑️ Supprimer' },
    'btn.open':           { EN: '▶ Open',         FR: '▶ Ouvrir' },
    'btn.confirm':        { EN: '✅ Confirm',      FR: '✅ Confirmer' },
    'btn.cancel':         { EN: '❌ Cancel',       FR: '❌ Annuler' },
    'no.path':            { EN: 'No path configured', FR: 'Aucun chemin configuré' },
    'no.file':            { EN: 'No file selected',   FR: 'Aucun fichier sélectionné' },
    'accueil.load':       { EN: '▶  Load a project',  FR: '▶  Charger un projet' },

    // ── Navigation ───────────────────────────────────────────────────────────────
    'nav.terrain.desc':   { EN: 'Heightmap - Atlas',  FR: 'Heightmap - Atlas' },
    'nav.inspect.desc':   { EN: 'Tiles - QTRE',       FR: 'Tuiles - QTRE' },
    'nav.gen.desc':       { EN: 'Masks - Baking',     FR: 'Masques - Baking' },
    'nav.satmap.desc':    { EN: 'Texture - Colors',   FR: 'Texture - Couleurs' },
    'nav.corr.desc':      { EN: 'Clean - Write',      FR: 'Clean - Écriture' },
    'nav.help.desc':      { EN: 'Documentation',      FR: 'Documentation' },
    'nav.help.title':     { EN: 'HELP',               FR: 'AIDE' },
    'nav.coming':         { EN: 'COMING SOON',        FR: 'À VENIR' },

    // ── Projects ─────────────────────────────────────────────────────────────────
    'proj.title':         { EN: 'Projects',            FR: 'Projets' },
    'proj.new':           { EN: 'New project',         FR: 'Nouveau projet' },
    'proj.recent':        { EN: 'Recent projects',     FR: 'Projets récents' },
    'proj.name':          { EN: 'Project name',        FR: 'Nom du projet' },
    'proj.author':        { EN: 'Author',              FR: 'Auteur' },
    'proj.desc':          { EN: 'Description',         FR: 'Description' },
    'proj.desc.ph':       { EN: 'Optional description...', FR: 'Description optionnelle...' },
    'proj.create':        { EN: '▶  Create project',  FR: '▶  Créer le projet' },
    'proj.browse':        { EN: '📂 Browse existing project', FR: '📂 Parcourir un projet existant' },
    'proj.search.ph':     { EN: 'Search project...',  FR: 'Rechercher un projet...' },
    'proj.none':          { EN: 'No project found',   FR: 'Aucun projet trouvé' },
    'proj.modified':      { EN: 'Updated:',           FR: 'Modifié :' },
    'proj.creating':      { EN: 'Creating...',        FR: 'Création en cours...' },
    'proj.created':       { EN: '✅ Project created — opening...', FR: '✅ Projet créé — ouverture...' },
    'proj.name.required': { EN: '❌ Project name is required.', FR: '❌ Le nom du projet est requis.' },
    'proj.invalid':       { EN: 'Invalid project — no project.json found.', FR: 'Projet invalide — aucun project.json trouvé dans ce dossier.' },
    'proj.del.confirm':   { EN: 'Permanently delete', FR: 'Supprimer définitivement' },
    'proj.count':         { EN: 'PROJECT(S)',         FR: 'PROJET(S)' },

    // ── Terrain ──────────────────────────────────────────────────────────────────
    'terrain.title':      { EN: '🗺️ Terrain',          FR: '🗺️ Terrain' },
    'terrain.paths':      { EN: '📁 PATHS & FILES',   FR: '📁 CHEMINS & FICHIERS' },
    'terrain.atlas':      { EN: '📈 METRIC ATLAS',    FR: '📈 ATLAS MÉTRIQUE' },
    'terrain.visu':       { EN: '📊 VISUALIZATION',   FR: '📊 VISUALISATION' },
    'terrain.sources':    { EN: 'Source Files',       FR: 'Fichiers Sources' },
    'terrain.addon':      { EN: 'Addon Paths',        FR: 'Chemins Addon' },
    'terrain.paths.sum':  { EN: 'Paths summary',      FR: 'Récapitulatif des chemins' },
    'terrain.wb':         { EN: 'Workbench — General Info', FR: 'Workbench — General Info' },
    'terrain.apply.grid': { EN: '⚙️ Apply Reforger grid', FR: '⚙️ Appliquer la grille Reforger' },
    'terrain.atlas.title':{ EN: 'Metric Atlas — Terrain Analysis', FR: 'Atlas Métrique — Analyse Terrain' },
    'terrain.analyze':    { EN: '🔍 Analyze heightmap', FR: '🔍 Analyser la heightmap' },
    'terrain.hillshade':  { EN: '☀️ Hillshading',     FR: '☀️ Hillshading' },
    'terrain.morph':      { EN: '✨ Morphological enrichment', FR: '✨ Enrichissement morphologique' },
    'terrain.hyps':       { EN: '🚀 Generate Hypsometric', FR: '🚀 Générer Hypsométrique' },
    'terrain.dl.png':     { EN: '📥 Download PNG',    FR: '📥 Télécharger PNG' },
    'terrain.hm':         { EN: 'Heightmap',          FR: 'Heightmap' },
    'terrain.satmap':     { EN: 'Satmap',             FR: 'Satmap' },
    'terrain.excl':       { EN: 'Exclusion Mask',     FR: 'Masque Exclusion' },
    'terrain.catalog':    { EN: 'Catalog JSON',       FR: 'Catalog JSON' },
    'terrain.flow':       { EN: 'Flow (erosion)',     FR: 'Flow (érosion)' },
    'terrain.deposit':    { EN: 'Deposit (alluvials)',FR: 'Deposit (alluvions)' },
    'terrain.addon.dir':  { EN: 'Addon Reforger',     FR: 'Addon Reforger' },
    'terrain.data.dir':   { EN: 'Data Dir',           FR: 'Data Dir' },
    'terrain.addon.desc': { EN: 'addons/ folder of WB project', FR: 'Dossier addons/ du projet WB' },
    'terrain.data.desc':  { EN: 'data/ folder of WB project',   FR: 'Dossier data/ du projet WB' },
    'terrain.tiles':      { EN: 'Tiles',              FR: 'Tiles' },
    'terrain.blocks':     { EN: 'Blocks per tile',    FR: 'Blocks per tile' },
    'terrain.cellsize':   { EN: 'Cellsize',           FR: 'Cellsize' },
    'terrain.total':      { EN: 'Terrain total',      FR: 'Terrain total' },
    'terrain.altitudes':  { EN: 'Altitudes',          FR: 'Altitudes' },
    'terrain.slopes':     { EN: 'Slopes',             FR: 'Pentes' },
    'terrain.coastal':    { EN: 'Coastal max',        FR: 'Coastal max' },
    'terrain.tpi':        { EN: 'TPI local',          FR: 'TPI local' },
    'terrain.sea':        { EN: 'Sea',                FR: 'Mer' },
    'terrain.land':       { EN: 'Land',               FR: 'Terre' },
    'terrain.elev':       { EN: 'Elevation range',    FR: 'Dénivellation' },
    'terrain.calib':      { EN: 'Auto-Calibrated Parameters', FR: 'Paramètres Auto-Calibrés' },
    'terrain.colormap':   { EN: 'Hypsometric Colormap', FR: 'Colormap Hypsométrique' },
    'terrain.ph.data.dir':{ EN: 'Auto-detected from addon_reforger', FR: 'Chemin auto-détecté depuis addon_reforger' },
    'terrain.generating':     { EN: 'Generating...',           FR: 'Génération...' },
    'terrain.hyps.generating':{ EN: '⏳ Generating hypsometric colormap...', FR: '⏳ Génération colormap hypsométrique...' },
    'terrain.analysis.complete':{ EN: '✅ Analysis complete', FR: '✅ Analyse terminée' },
    'terrain.no.paths':       { EN: 'No path configured',      FR: 'Aucun chemin configuré' },
    'terrain.no.analysis':    { EN: '⚠️ Terrain data not analyzed.', FR: '⚠️ Données terrain non analysées.' },
    'terrain.hyps.generated': { EN: '✅ Hypsometric generated: ',  FR: '✅ Hypsométrique générée : ' },
    'terrain.path.configured':{ EN: '✅ configured',               FR: '✅ configuré' },
    'terrain.grid.updated':   { EN: '✅ Reforger grid updated',   FR: '✅ Grille Reforger mise à jour' },
    'terrain.path.deleted':   { EN: 'deleted',                    FR: 'supprimé' },

    // ── Inspection ───────────────────────────────────────────────────────────────
    'insp.title':         { EN: '🗺️ QTRE GRID',       FR: '🗺️ GRILLE QTRE' },
    'insp.scan.global':   { EN: '📡 GLOBAL SCAN',     FR: '📡 SCAN GLOBAL' },
    'insp.scan.btn':      { EN: '📡 Scan all tiles',  FR: '📡 Scanner toutes les tuiles' },
    'insp.rescan':        { EN: '🔄 Rescan',           FR: '🔄 Rescanner' },
    'insp.inspect':       { EN: '🔍 INSPECT TILE',    FR: '🔍 INSPECT TUILE' },
    'insp.inspect.btn':   { EN: '🔍 Inspect',         FR: '🔍 Inspecter' },
    'insp.tile.desc':     { EN: 'Enter tile coordinates (tx, ty). Generates a block/weight image per slot.', FR: 'Entrez les coordonnées (tx, ty) de la tuile à inspecter. Le script génère une image des blocs et poids par slot.' },
    'insp.click':         { EN: 'Click a tile to see details.', FR: 'Cliquer sur une tuile pour voir ses détails.' },
    'insp.tx':            { EN: 'TX (col, 0-31)',     FR: 'TX (col, 0-31)' },
    'insp.ty':            { EN: 'TY (row, 0-31)',     FR: 'TY (ligne, 0-31)' },
    'insp.budget':        { EN: 'Texture budget',     FR: 'Budget textures' },
    'insp.ok':            { EN: 'OK',                 FR: 'OK' },
    'insp.over':          { EN: 'Over',               FR: 'Dépassement' },
    'insp.limit':         { EN: 'Limit',              FR: 'Limite' },
    'insp.critical':      { EN: 'Critical',           FR: 'Critique' },
    'insp.unscanned':     { EN: 'Not scanned',        FR: 'Non scanné' },
    'insp.deselect':      { EN: '✕ Deselect',         FR: '✕ Désélectionner' },
    'insp.saved':         { EN: '✅ SAVED',            FR: '✅ SAUVEGARDÉ' },
    'insp.no.cache.instruction': { EN: '⚠️ No QTRE cache — run scan from Global Scan tab then return here.', FR: '⚠️ Pas de cache QTRE — lancez le scan depuis l\'onglet Scan Global puis revenez ici.' },
    'insp.not.scanned':   { EN: 'not scanned',        FR: 'non scanné' },

    // ── Corrections ──────────────────────────────────────────────────────────────
    'corr.title':         { EN: '🔧 Corrections',     FR: '🔧 Corrections' },
    'corr.scan.global':   { EN: 'GLOBAL SCAN',        FR: 'SCAN GLOBAL' },
    'corr.scan.zone':     { EN: 'ZONE SCAN',          FR: 'SCAN ZONE' },
    'corr.inspect':       { EN: 'INSPECT TILE',       FR: 'INSPECT TUILE' },
    'corr.health':        { EN: 'TERRAIN HEALTH',     FR: 'SANTÉ TERRAIN' },
    'corr.inventory':     { EN: 'FILE INVENTORY',     FR: 'INVENTAIRE FICHIERS' },
    'corr.scan.desc':     { EN: 'Scans all .ttile blocks and detects slots below coverage threshold. Read-only.', FR: 'Scanne tous les blocs .ttile et détecte les slots dont la couverture est inférieure au seuil. Lecture seule — aucune écriture.' },
    'corr.zone.desc':     { EN: 'Scans only tiles covered by PNG mask (white = active zone). Read-only.', FR: 'Scanne uniquement les tuiles couvertes par le masque PNG (blanc = zone active). Lecture seule.' },
    'corr.inspect.desc':  { EN: 'Shows materials and weights per slot for a specific tile.', FR: 'Affiche les matériaux et poids par slot pour une tuile spécifique.' },
    'corr.health.desc':   { EN: 'Analyzes the full terrain: weight anomalies, orphan tiles, empty blocks, texture distribution.', FR: 'Analyse l\'ensemble du terrain : anomalies de poids, tuiles orphelines, blocs sans matériaux, distribution des textures.' },
    'corr.inventory.desc':{ EN: 'Checks that all .ttile and .edds files are present in .Data and .EditorData. Detects missing files.', FR: 'Vérifie que tous les fichiers .ttile et .edds attendus sont présents dans les dossiers .Data et .EditorData. Détecte les fichiers manquants.' },
    'corr.threshold':     { EN: 'Coverage threshold (%)', FR: 'Seuil coverage (%)' },
    'corr.choose.mask':   { EN: '📁 Choose PNG mask',  FR: '📁 Choisir masque PNG' },
    'corr.run.scan':      { EN: '🔍 Run scan',         FR: '🔍 Lancer le scan' },
    'corr.run.zone':      { EN: '🔍 Scan zone',        FR: '🔍 Scan zone' },
    'corr.run.health':    { EN: '❤ Analyze health',   FR: '❤ Analyser la santé' },
    'corr.run.inventory': { EN: '📊 Scan inventory',  FR: '📊 Scanner l\'inventaire' },
    'corr.run.btn':       { EN: '🔦 Run',              FR: '🔦 Lancer' },
    'corr.inspect.mode':  { EN: 'Inspect',            FR: 'Inspect' },
    'corr.weights.mode':  { EN: 'Weights',            FR: 'Weights' },
    'corr.validate.mode': { EN: 'Validate',           FR: 'Validate' },
    'corr.tiles.scanned': { EN: 'Tiles scanned',      FR: 'Tuiles scannées' },
    'corr.anomalies':     { EN: 'Anomalies',          FR: 'Anomalies' },
    'corr.errors':        { EN: 'Errors',             FR: 'Erreurs' },
    'corr.ttile.present': { EN: '.ttile present',     FR: '.ttile présents' },
    'corr.ttile.missing': { EN: '.ttile missing',     FR: '.ttile manquants' },
    'corr.edds.present':  { EN: '.edds present',      FR: '.edds présents' },
    'corr.tx':            { EN: 'TX (0-31)',           FR: 'TX (0-31)' },
    'corr.ty':            { EN: 'TY (0-31)',           FR: 'TY (0-31)' },

    // ── Satmap ───────────────────────────────────────────────────────────────────
    'satmap.title':       { EN: '🗺️ Satmap',           FR: '🗺️ Satmap' },
    'satmap.v2':          { EN: 'SATMAP V2.0',         FR: 'SATMAP V2.0' },
    'satmap.classifier':  { EN: 'K-MEANS CLASSIFIER',  FR: 'CLASSIFICATEUR K-MEANS' },
    'satmap.gen':         { EN: 'Generation',          FR: 'Génération' },
    'satmap.config':      { EN: 'Configuration',       FR: 'Configuration' },
    'satmap.source':      { EN: 'Source',              FR: 'Source' },
    'satmap.params':      { EN: 'Parameters',          FR: 'Paramètres' },
    'satmap.size':        { EN: 'Size',                FR: 'Taille' },
    'satmap.resolution':  { EN: 'Final resolution',    FR: 'Résolution finale' },
    'satmap.catalog':     { EN: 'Texture catalog',     FR: 'Catalogue textures' },
    'satmap.terrain.dir': { EN: 'Terrain/ folder',    FR: 'Dossier Terrain/' },
    'satmap.mid.dir':     { EN: 'Middle textures folder (optional)', FR: 'Dossier textures middle (optionnel)' },
    'satmap.fallback':    { EN: 'Fallback materials',  FR: 'Matériaux fallback' },
    'satmap.missing':     { EN: 'Missing layers',      FR: 'Layers manquants' },
    'satmap.masks':       { EN: 'Generated masks',     FR: 'Masks générés' },
    'satmap.kmeans':      { EN: 'K-means classes',     FR: 'Classes K-means' },
    'satmap.reuse':       { EN: 'Reuse existing classification.json', FR: 'Réutiliser classification.json existante' },
    'satmap.classify.desc':{ EN: 'Classifies a satmap into K-means color families and exports PNG masks per class.', FR: 'Classifie une satmap en familles de couleurs K-means et exporte des masks PNG par classe.' },
    'satmap.output':      { EN: 'Output → outputs/satmap/masks_classifier/', FR: 'Sortie → outputs/satmap/masks_classifier/' },
    'satmap.gen.btn':     { EN: '🎨 Generate Satmap v2.0', FR: '🎨 Générer Satmap v2.0' },
    'satmap.scan.btn':    { EN: '🔄 Scan .emat',       FR: '🔄 Scan .emat' },
    'satmap.choose.btn':  { EN: '📁 Choose satmap (.png/.jpg)', FR: '📁 Choisir satmap (.png/.jpg)' },
    'satmap.classify.btn':{ EN: '▶ Run classification', FR: '▶ Lancer classification' },
    'satmap.open.out':    { EN: '📁 Open output folder', FR: '📁 Ouvrir dossier sortie' },
    'satmap.checking':    { EN: 'Checking...',         FR: 'Vérification...' },
    'satmap.ph.satmap':   { EN: 'Leave empty for flat colors mode', FR: 'Laisser vide pour mode couleurs plates' },

    // ── Generation ───────────────────────────────────────────────────────────────
    'gen.title':          { EN: '⚙️ Generation',       FR: '⚙️ Génération' },
    'gen.masks':          { EN: 'MASKS',               FR: 'MASQUES' },
    'gen.params':         { EN: 'PARAMETERS',          FR: 'PARAMÈTRES' },
    'gen.baking':         { EN: 'BAKING',              FR: 'BAKING' },
    'gen.preview.btn':    { EN: '▶ Generate preview',  FR: '▶ Générer preview' },
    'gen.export.btn':     { EN: '📁 Export PNG masks', FR: '📁 Exporter masques PNG' },
    'gen.write.btn':      { EN: '🔧 Write to .ttile',  FR: '🔧 Écrire sur les .ttile' },
    'gen.save.mapping':   { EN: '💾 Save mapping',     FR: '💾 Sauvegarder mapping' },
    'gen.calib':          { EN: 'Mask calibration',    FR: 'Calibrage masques' },
    'gen.auto.calib':     { EN: 'Auto-calibrate from heightmap', FR: 'Auto-calibrer depuis heightmap' },
    'gen.apply.preset':   { EN: 'Apply preset',        FR: 'Appliquer preset' },
    'gen.biome':          { EN: 'Biome',               FR: 'Biome' },
    'gen.choose.biome':   { EN: '-- Choose a biome --', FR: '-- Choisir un biome --' },
    'gen.mapping':        { EN: 'Mask → texture mapping', FR: 'Mapping masque → texture' },
    'gen.mask':           { EN: 'Mask',                FR: 'Masque' },
    'gen.texture':        { EN: 'Texture',             FR: 'Texture' },
    'gen.priority':       { EN: 'Priority',            FR: 'Priorité' },
    'gen.mode':           { EN: 'Mode',                FR: 'Mode' },
    'gen.fallback':       { EN: 'Texture fallback (areas without mask):', FR: 'Texture fallback (zones sans masque) :' },
    'gen.catalog':        { EN: 'Catalog',             FR: 'Catalog' },
    'gen.sources':        { EN: 'Sources',             FR: 'Sources' },
    'gen.hm':             { EN: 'Heightmap',           FR: 'Heightmap' },
    'gen.excl':           { EN: 'Exclusion',           FR: 'Exclusion' },
    'gen.flow':           { EN: 'Flow',                FR: 'Flow' },
    'gen.deposit':        { EN: 'Deposit',             FR: 'Deposit' },
    'gen.data.dir':       { EN: 'Data Dir',            FR: 'Data Dir' },
    'gen.satmap':         { EN: 'Satmap V2',           FR: 'Satmap V2' },
    'gen.post':           { EN: 'Post-processing',     FR: 'Post-processing' },
    'gen.export':         { EN: 'Export',              FR: 'Export' },
    'gen.slopes':         { EN: 'Slope thresholds',    FR: 'Seuils de pente' },
    'gen.gentle':         { EN: 'Gentle (°)',          FR: 'Gentle (°)' },
    'gen.landes':         { EN: 'Landes (°)',          FR: 'Landes (°)' },
    'gen.rock':           { EN: 'Rock (°)',            FR: 'Rock (°)' },
    'gen.cliff':          { EN: 'Cliff (°)',           FR: 'Cliff (°)' },
    'gen.amplitude':      { EN: 'Amplitude (°)',       FR: 'Amplitude (°)' },
    'gen.fbm.scale':      { EN: 'fBm scale',          FR: 'Échelle fBm' },
    'gen.octaves':        { EN: 'Octaves',             FR: 'Octaves' },
    'gen.fbm.enrich':     { EN: 'Slope enrichment (fBm)', FR: 'Enrichissement slope (fBm)' },
    'gen.stretch':        { EN: 'Stretch auto (p2-p98)', FR: 'Stretch auto (p2-p98)' },
    'gen.coastal':        { EN: 'Coastal width (m)',   FR: 'Côtier - largeur (m)' },
    'gen.alpage':         { EN: 'Alpine - alt. min',   FR: 'Alpages - alt. min' },
    'gen.landes.min':     { EN: 'Plateau landes - min', FR: 'Landes plateau - min' },
    'gen.prairie.max':    { EN: 'Prairie - alt. max',  FR: 'Prairie - alt. max' },
    'gen.prairie.min':    { EN: 'Prairie dry - min',   FR: 'Prairie sèche - min' },
    'gen.weight.min':     { EN: 'Weight min',          FR: 'Weight min' },
    'gen.qtre':           { EN: 'QTRE threshold',      FR: 'Seuil QTRE' },
    'gen.flow.low':       { EN: 'Flow cut_low',        FR: 'Flow cut_low' },
    'gen.flow.gamma':     { EN: 'Flow gamma',          FR: 'Flow gamma' },
    'gen.deposit.low':    { EN: 'Deposit cut_low',     FR: 'Deposit cut_low' },
    'gen.deposit.gamma':  { EN: 'Deposit gamma',       FR: 'Deposit gamma' },
    'gen.id':             { EN: 'ID',                  FR: 'ID' },
    'gen.disabled':       { EN: 'Disabled',            FR: 'Désactivé' },
    'gen.auto':           { EN: '0 = auto from percentiles', FR: '0 = auto depuis percentiles' },
    'gen.desc':           { EN: 'PNG mask generation from heightmap. May take several minutes for a 4097x4097 map.', FR: 'Génération des masques PNG depuis la heightmap. Peut prendre plusieurs minutes pour une carte 4097x4097.' },

    // ── Satmap info ──────────────────────────────────────────────────────────────
    'satmap.pipeline.info': { EN: 'Layer.dds + LRS2 Pipeline — reads raw .edds from .EditorData, parses LRS2 chunks from .Data/.ttile. Texture mode: quality with middle BCR textures.', FR: 'Pipeline Layer.dds + LRS2 — lit les .edds bruts depuis .EditorData, parse les chunks LRS2 depuis .Data/.ttile. Mode texture : qualite avec textures middle BCR.' },
    'satmap.catalog.not.found': { EN: 'Catalog not found — configure catalog_json in Terrain > Paths', FR: 'Catalog introuvable — configurez catalog_json dans Terrain > Chemins' },

    // ── Terrain info ─────────────────────────────────────────────────────────────
    'terrain.colormap.info': { EN: 'This map uses raw altitude data. For true calibrated zones (coastal/lowland/highland), analyze the terrain via the Metric Atlas tab after loading a heightmap.', FR: 'Cette carte utilise les données d\'altitude brutes. Pour les vraies zones calibrées (coastal/lowland/highland), analysez le terrain via l\'onglet Atlas Métrique après avoir chargé une heightmap.' },
    'terrain.wb.paste.info': { EN: 'Copy the text from Workbench → Terrain → General Info and paste it here to auto-fill the Reforger grid.', FR: 'Copiez le texte depuis Workbench → Terrain → General Info et collez-le ici pour auto-remplir la grille Reforger.' },

    // ── Log Panel ────────────────────────────────────────────────────────────────
    'log.title':              { EN: '▶ Session Log',           FR: '▶ Journal de session' },
    'log.tooltip':            { EN: 'Session Log',             FR: 'Journal de session' },
    'log.btn.refresh':        { EN: '↺ Refresh',               FR: '↺ Rafraichir' },
    'log.btn.clear':          { EN: '🗑️ Clear',                FR: '🗑️ Vider' },
    'log.empty':              { EN: 'No action recorded.',     FR: 'Aucune action enregistree.' },
    'log.count':              { EN: 'line(s)',                 FR: 'ligne(s)' },
  };

  // ── Langue courante ───────────────────────────────────────────────────────────
  var _lang = localStorage.getItem('mgp_lang') || 'EN';

  // ── Traduire un élément ───────────────────────────────────────────────────────
  function t(key) {
    var entry = _dict[key];
    if (!entry) return key;
    return entry[_lang] || entry['EN'] || key;
  }

  // ── Appliquer les traductions au DOM ──────────────────────────────────────────
  function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(function(el) {
      var key = el.getAttribute('data-i18n');
      el.innerHTML = t(key);
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el) {
      el.placeholder = t(el.getAttribute('data-i18n-ph'));
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el) {
      el.title = t(el.getAttribute('data-i18n-title'));
    });
    // Mettre à jour le bouton switch
    var btn = document.getElementById('mgp-lang-btn');
    if (btn) btn.textContent = _lang === 'EN' ? 'FR' : 'EN';
  }

  // ── Switch langue ─────────────────────────────────────────────────────────────
  function toggleLang() {
    _lang = _lang === 'EN' ? 'FR' : 'EN';
    localStorage.setItem('mgp_lang', _lang);
    applyTranslations();
  }

  // ── Injecter le bouton switch dans le header ──────────────────────────────────
  function injectLangBtn() {
    var header = document.querySelector('.header');
    if (!header) return;
    // Chercher header-right ou header-meta ou créer un div
    var btn = document.createElement('button');
    btn.id = 'mgp-lang-btn';
    btn.textContent = _lang === 'EN' ? 'FR' : 'EN';
    btn.onclick = toggleLang;
    btn.style.cssText = [
      'background:transparent',
      'border:1px solid #2e6647',
      'border-radius:4px',
      'color:#5dba7d',
      'font-family:Courier New,monospace',
      'font-size:10px',
      'letter-spacing:2px',
      'padding:3px 9px',
      'cursor:pointer',
      'margin-left:10px',
      'transition:all .2s',
      'text-transform:uppercase',
    ].join(';');
    btn.onmouseover = function() { this.style.background='#1a3d2a'; };
    btn.onmouseout  = function() { this.style.background='transparent'; };
    // Ajouter au header à droite
    var meta = header.querySelector('.header-meta') || header.querySelector('.header-right');
    if (meta) {
      meta.insertBefore(btn, meta.firstChild);
    } else {
      header.appendChild(btn);
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────────────
  function init() {
    injectLangBtn();
    applyTranslations();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // ── API publique ──────────────────────────────────────────────────────────────
  window._i18n = { t: t, apply: applyTranslations, toggle: toggleLang, lang: function() { return _lang; } };

})();
