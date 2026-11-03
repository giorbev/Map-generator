/**
 * Map Generator Pro v8.1.0 — i18n
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
    'error.no.project':   { EN: 'No active project',  FR: 'Aucun projet actif' },

    // ── Navigation ───────────────────────────────────────────────────────────────
    'nav.terrain.desc':   { EN: 'Heightmap - Atlas',  FR: 'Heightmap - Atlas' },
    'nav.gen.desc':       { EN: 'Masks - Baking',     FR: 'Masques - Baking' },
    'nav.satmap.desc':    { EN: 'Texture - Colors',   FR: 'Texture - Couleurs' },
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
    'proj.import':         { EN: '📥 Import a backup (.mgp.zip)', FR: '📥 Importer une sauvegarde (.mgp.zip)' },
    'proj.export':         { EN: '💾 Export', FR: '💾 Exporter' },
    'proj.export.outputs': { EN: 'Include results in backups (cache, satmaps, masks, reports)', FR: 'Inclure les résultats dans les sauvegardes (cache, satmaps, masques, rapports)' },
    'proj.export.running': { EN: 'Saving the project...', FR: 'Sauvegarde du projet...' },
    'proj.export.done':    { EN: 'Backup written:', FR: 'Sauvegarde écrite :' },
    'proj.export.missing': { EN: 'Input not found, not saved:', FR: 'Entrée introuvable, non sauvegardée :' },
    'proj.files':          { EN: 'files', FR: 'fichiers' },
    'proj.mb':             { EN: 'MB', FR: 'Mo' },
    'proj.import.running': { EN: 'Importing...', FR: 'Import en cours...' },
    'proj.import.done':    { EN: 'Project imported:', FR: 'Projet importé :' },
    'proj.import.replaced': { EN: 'Project replaced:', FR: 'Projet remplacé :' },
    'proj.import.conflict': { EN: 'A project already uses the folder', FR: 'Un projet utilise déjà le dossier' },
    'proj.import.rename':  { EN: '✏️ Import under this name', FR: '✏️ Importer sous ce nom' },
    'proj.import.replace': { EN: '♻️ Replace', FR: '♻️ Remplacer' },
    'proj.import.replace.confirm': { EN: '⚠ Confirm: the existing project will be deleted', FR: '⚠ Confirmer : le projet existant sera supprimé' },
    'proj.import.repoint': { EN: 'Path missing on this PC, set it again in Terrain > Paths & Files:', FR: 'Chemin absent sur ce PC, à repointer dans Terrain > Chemins & fichiers :' },
    'proj.import.sync':    { EN: 'Backup without textures: run Synchronize (Satmap > Textures)', FR: 'Sauvegarde sans textures : lancer Synchroniser (Satmap > Textures)' },
    'proj.import.oldleft': { EN: 'Old folder could not be deleted, remove it by hand:', FR: 'Ancien dossier non supprimé, à effacer à la main :' },
    'proj.data.title':     { EN: 'Data folder', FR: 'Dossier des données' },
    'proj.data.first':     { EN: 'First launch: your projects and textures will be saved in this folder. You can change it now.', FR: 'Premier lancement : vos projets et textures seront enregistrés dans ce dossier. Vous pouvez le changer maintenant.' },
    'proj.data.open':      { EN: '📂 Open folder', FR: '📂 Ouvrir le dossier' },
    'proj.data.change':    { EN: '📦 Change location…', FR: '📦 Changer l\'emplacement…' },
    'proj.data.copying':   { EN: 'Copying data... (may take several minutes)', FR: 'Copie des données... (peut prendre plusieurs minutes)' },
    'proj.data.copied':    { EN: 'Data copied to:', FR: 'Données copiées dans :' },
    'proj.data.reused':    { EN: 'Existing data found, used as is:', FR: 'Données déjà présentes, reprises telles quelles :' },
    'proj.data.oldkept':   { EN: 'The old folder is kept (delete it by hand once checked):', FR: 'L\'ancien dossier est conservé (à supprimer à la main après vérification) :' },
    'proj.data.restart.msg': { EN: 'Restart the application to use the new folder.', FR: 'Relancer l\'application pour utiliser le nouveau dossier.' },
    'proj.data.restart':   { EN: '↻ Restart', FR: '↻ Relancer' },

    // ── Terrain ──────────────────────────────────────────────────────────────────
    'terrain.title':      { EN: '🗺️ Terrain',          FR: '🗺️ Terrain' },
    'terrain.paths':      { EN: '📁 PATHS & FILES',   FR: '📁 CHEMINS & FICHIERS' },
    'terrain.atlas':      { EN: '📈 METRIC ATLAS',    FR: '📈 ATLAS MÉTRIQUE' },
    'terrain.visu':       { EN: '📊 VISUALIZATION',   FR: '📊 VISUALISATION' },
    'terrain.sources':     { EN: 'Source files', FR: 'Fichiers sources' },
    'terrain.addon':       { EN: 'Addon paths', FR: 'Chemins de l\'addon' },
    'terrain.paths.sum':  { EN: 'Paths summary',      FR: 'Récapitulatif des chemins' },
    'terrain.wb':         { EN: 'Workbench — General Info', FR: 'Workbench — General Info' },
    'terrain.apply.grid': { EN: '⚙️ Apply Reforger grid', FR: '⚙️ Appliquer la grille Reforger' },
    'terrain.budget.label': { EN: 'Texture budget per block', FR: 'Budget textures par bloc' },
    'terrain.budget.choose': { EN: '— choose —', FR: '— choisir —' },
    'terrain.budget.help': { EN: 'Choose 5 or 7 in the list to enable tile analysis functions.', FR: 'Choisissez 5 ou 7 dans la liste pour activer les fonctions d\'analyse des tuiles.' },
    'terrain.budget.error.invalid': { EN: 'Invalid budget: choose 5 or 7', FR: 'Budget invalide : choisissez 5 ou 7' },
    'terrain.budget.error.missing': { EN: 'Texture budget per block not set: choose 5 or 7 in the project settings.', FR: 'Budget de textures par bloc non défini : choisissez 5 ou 7 dans la configuration du projet.' },
    'terrain.atlas.title':{ EN: 'Metric Atlas — Terrain Analysis', FR: 'Atlas Métrique — Analyse Terrain' },
    'terrain.analyze':    { EN: '🔍 Analyze heightmap', FR: '🔍 Analyser la heightmap' },
    'terrain.hillshade':  { EN: '☀️ Hillshading',     FR: '☀️ Hillshading' },
    'terrain.morph':      { EN: '✨ Morphological enrichment', FR: '✨ Enrichissement morphologique' },
    'terrain.hyps':       { EN: '🚀 Generate Hypsometric', FR: '🚀 Générer Hypsométrique' },
    'terrain.dl.png':     { EN: '📥 Download PNG',    FR: '📥 Télécharger PNG' },
    'terrain.hm':         { EN: 'Heightmap',          FR: 'Heightmap' },
    'terrain.satmap':     { EN: 'Satmap',             FR: 'Satmap' },
    'terrain.excl':        { EN: 'Exclusion mask', FR: 'Masque d\'exclusion' },
    'terrain.catalog':    { EN: 'Catalog JSON',       FR: 'Catalog JSON' },
    'terrain.flow':       { EN: 'Flow (erosion)',     FR: 'Flow (érosion)' },
    'terrain.deposit':    { EN: 'Deposit (alluvium)',FR: 'Deposit (alluvions)' },
    'terrain.addon.dir':  { EN: 'Addon Reforger',     FR: 'Addon Reforger' },
    'terrain.data.dir':   { EN: 'Data Dir',           FR: 'Data Dir' },
    'terrain.addon.desc':  { EN: 'Workbench addon folder', FR: 'Dossier de l\'addon Workbench' },
    'terrain.data.desc':   { EN: 'Terrain .Data folder (World\\…\\Terrain\\.Data)', FR: 'Dossier .Data du terrain (World\\…\\Terrain\\.Data)' },
    'terrain.tiles':       { EN: 'Tiles', FR: 'Tuiles' },
    'terrain.blocks':      { EN: 'Blocks per tile', FR: 'Blocs par tuile' },
    'terrain.cellsize':    { EN: 'Cell size', FR: 'Taille de cellule' },
    'terrain.total':       { EN: 'Terrain size', FR: 'Taille du terrain' },
    'terrain.altitudes':  { EN: 'Altitudes',          FR: 'Altitudes' },
    'terrain.slopes':     { EN: 'Slopes',             FR: 'Pentes' },
    'terrain.coastal':     { EN: 'Coastal max', FR: 'Côtier max' },
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
    'terrain.confirm.delete': { EN: '⚠ Click again to remove', FR: '⚠ Recliquer pour supprimer' },
    'terrain.confirm.grid': { EN: '⚠ Click again to replace the saved grid', FR: '⚠ Recliquer pour remplacer la grille enregistrée' },
    'terrain.stale':       { EN: '⚠️ The heightmap changed since the last analysis: run the analysis again.', FR: '⚠️ La heightmap a changé depuis la dernière analyse : relancer l\'analyse.' },
    'terrain.p.tpi':       { EN: 'Local TPI', FR: 'TPI local' },
    'terrain.p.rock':      { EN: 'Rock min', FR: 'Roche min' },
    'terrain.p.debris':    { EN: 'Debris min', FR: 'Éboulis min' },
    'terrain.p.ghigh':     { EN: 'High grass max', FR: 'Herbe haute max' },
    'terrain.p.gmid':      { EN: 'Mid grass max', FR: 'Herbe moyenne max' },
    'terrain.p.glow':      { EN: 'Low grass max', FR: 'Herbe basse max' },
    'terrain.p.coastal':   { EN: 'Coastal max', FR: 'Côtier max' },
    'terrain.error':       { EN: '❌ Error: ', FR: '❌ Erreur : ' },
    'terrain.analyse.loading': { EN: '⏳ Loading heightmap and computing slopes...', FR: '⏳ Chargement de la heightmap et calcul des pentes...' },
    'terrain.analysing':   { EN: 'Analysing...', FR: 'Analyse en cours...' },
    'terrain.scale':       { EN: 'Scale (m/px)', FR: 'Échelle (m/px)' },
    'terrain.import.date': { EN: 'Import date', FR: 'Date d\'import' },
    'terrain.surface.res': { EN: 'Surface resolution', FR: 'Résolution des surfaces' },
    'terrain.tile.size':   { EN: 'Tile size', FR: 'Taille d\'une tuile' },
    'terrain.saved.none':  { EN: 'No saved values — paste the Workbench General Info text.', FR: 'Aucune valeur enregistrée — collez le texte General Info de Workbench.' },
    'terrain.saved.title': { EN: '⚙️ Saved values', FR: '⚙️ Valeurs enregistrées' },
    'terrain.wb.ph':       { EN: 'Paste the Workbench General Info text here (Terrain → General Info)', FR: 'Collez ici le texte General Info de Workbench (Terrain → General Info)' },
    'terrain.gaea':        { EN: 'Gaea masks (optional)', FR: 'Masques Gaea (optionnels)' },
    'terrain.excl.hint':   { EN: '.png (white = active zone A)', FR: '.png (blanc = zone A active)' },

    // ── Satmap ───────────────────────────────────────────────────────────────────
    'satmap.title':       { EN: '🗺️ Satmap',           FR: '🗺️ Satmap' },
    'satmap.v2':          { EN: 'SATMAP V2.0',         FR: 'SATMAP V2.0' },
    'satmap.gen':         { EN: 'Generation',          FR: 'Génération' },
    'satmap.config':      { EN: 'Configuration',       FR: 'Configuration' },
    'satmap.source':      { EN: 'Source',              FR: 'Source' },
    'satmap.params':      { EN: 'Parameters',          FR: 'Paramètres' },
    'satmap.size':        { EN: 'Size',                FR: 'Taille' },
    'satmap.resolution':  { EN: 'Final resolution',    FR: 'Résolution finale' },
    'satmap.catalog':     { EN: 'Texture catalog',     FR: 'Catalogue textures' },
    'satmap.terrain.dir': { EN: 'Terrain/ folder',    FR: 'Dossier Terrain/' },
    'satmap.fallback':    { EN: 'Fallback materials',  FR: 'Matériaux fallback' },
    'satmap.missing':     { EN: 'Missing layers',      FR: 'Layers manquants' },
    'satmap.gen.btn':     { EN: '🎨 Generate Satmap v2.0', FR: '🎨 Générer Satmap v2.0' },
    'satmap.open.out':    { EN: '📁 Open output folder', FR: '📁 Ouvrir dossier sortie' },
    'satmap.checking':    { EN: 'Checking...',         FR: 'Vérification...' },

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

    // ── Mask names ───────────────────────────────────────────────────────────────
    'mask.seabed':        { EN: 'Seabed', FR: 'Seabed' },
    'mask.coastal':       { EN: 'Coastal', FR: 'Coastal' },
    'mask.prairie_humide': { EN: 'Wet grassland', FR: 'Prairie humide' },
    'mask.prairie_seche': { EN: 'Dry grassland', FR: 'Prairie sèche' },
    'mask.foret_feuillue': { EN: 'Deciduous forest', FR: 'Forêt feuillue' },
    'mask.foret_coniferes': { EN: 'Coniferous forest', FR: 'Forêt conifères' },
    'mask.maquis_landes': { EN: 'Shrubland', FR: 'Maquis / Landes' },
    'mask.landes_plateau': { EN: 'Plateau moorland', FR: 'Landes plateau' },
    'mask.alpages':       { EN: 'Alpine meadows', FR: 'Alpages' },
    'mask.landes_rocheuses': { EN: 'Rocky moorland', FR: 'Landes rocheuses' },
    'mask.rock':          { EN: 'Rock', FR: 'Rock' },
    'mask.flow':          { EN: 'Flow', FR: 'Flow' },
    'mask.deposit':       { EN: 'Deposit', FR: 'Deposit' },

    // ── Satmap info ──────────────────────────────────────────────────────────────
    'satmap.pipeline.info': { EN: 'Layer.dds + LRS2 Pipeline — reads raw .edds from .EditorData, parses LRS2 chunks from .Data/.ttile. Texture mode: quality with middle BCR textures.', FR: 'Pipeline Layer.dds + LRS2 — lit les .edds bruts depuis .EditorData, parse les chunks LRS2 depuis .Data/.ttile. Mode texture : qualite avec textures middle BCR.' },

    // ── Terrain info ─────────────────────────────────────────────────────────────
    'terrain.colormap.info': { EN: 'This map uses raw altitude data. For true calibrated zones (coastal/lowland/highland), analyze the terrain via the Metric Atlas tab after loading a heightmap.', FR: 'Cette carte utilise les données d\'altitude brutes. Pour les vraies zones calibrées (coastal/lowland/highland), analysez le terrain via l\'onglet Atlas Métrique après avoir chargé une heightmap.' },
    'terrain.wb.paste.info': { EN: 'Copy the text from Workbench → Terrain → General Info and paste it here to auto-fill the Reforger grid.', FR: 'Copiez le texte depuis Workbench → Terrain → General Info et collez-le ici pour auto-remplir la grille Reforger.' },

    // ── Tile Diagnostic ──────────────────────────────────────────────────────────
    "nav.diag.desc": { EN: "Map - Tiles - Files", FR: "Carte - Tuiles - Fichiers" },
    "diag.title": { EN: "🔬 Tile Diagnostic", FR: "🔬 Tile Diagnostic" },
    "diag.tab.map": { EN: "🗺️ Global map", FR: "🗺️ Carte globale" },
    "diag.tab.inspect": { EN: "🔍 Inspect tile", FR: "🔍 Inspect tuile" },
    "diag.tab.zone": { EN: "🎯 Zone scan", FR: "🎯 Scan de zone" },
    "diag.tab.files": { EN: "🗂️ File check", FR: "🗂️ Validation des fichiers" },
    "diag.error": { EN: "Unknown error", FR: "Erreur inconnue" },
    "diag.tile.out.of.grid": { EN: "Tile outside the grid: TX and TY go from 0 to {max}", FR: "Tuile hors de la grille : TX et TY vont de 0 à {max}" },
    "diag.scan.btn": { EN: "📡 Scan all tiles", FR: "📡 Scanner toutes les tuiles" },
    "diag.scan.info": { EN: "Scan of {date}: {n} tiles", FR: "Scan du {date} : {n} tuiles" },
    "diag.scan.stale": { EN: "⚠️ outdated, tiles have changed since — scan again", FR: "⚠️ périmé, les tuiles ont changé depuis — relancez le scan" },
    "diag.scan.none": { EN: "⚠️ No scan yet for this project", FR: "⚠️ Aucun scan pour ce projet" },
    "diag.scan.running": { EN: "Scanning all tiles (about 1 minute on a large map)...", FR: "Scan de toutes les tuiles (environ 1 minute sur une grande carte)..." },
    "diag.scan.done": { EN: "✅ Scan done: {n} tiles", FR: "✅ Scan terminé : {n} tuiles" },
    "diag.map.empty": { EN: "⚠️ No scan yet — click “Scan all tiles”.", FR: "⚠️ Aucun scan — cliquez sur « Scanner toutes les tuiles »." },
    "diag.map.old": { EN: "⚠️ Scan made by an older version — click “Scan all tiles”.", FR: "⚠️ Scan fait par une version précédente — cliquez sur « Scanner toutes les tuiles »." },
    "diag.display": { EN: "Display", FR: "Affichage" },
    "diag.mode.budget": { EN: "Texture budget", FR: "Budget de textures" },
    "diag.mode.neg": { EN: "Negligible slots", FR: "Slots négligeables" },
    "diag.mode.search": { EN: "Search", FR: "Recherche" },
    "diag.threshold": { EN: "Negligible below", FR: "Négligeable sous" },
    "diag.leg.ok": { EN: "Below {b}", FR: "Moins de {b}" },
    "diag.leg.limit": { EN: "At limit ({b})", FR: "À la limite ({b})" },
    "diag.leg.over": { EN: "Over {b}", FR: "Plus de {b}" },
    "diag.leg.nobudget": { EN: "Budget not set (Terrain page)", FR: "Budget non défini (page Terrain)" },
    "diag.leg.neg1": { EN: "1 negligible slot", FR: "1 slot négligeable" },
    "diag.leg.neg2": { EN: "2 or more", FR: "2 ou plus" },
    "diag.leg.found": { EN: "Block found", FR: "Bloc trouvé" },
    "diag.stats": { EN: "Statistics", FR: "Statistiques" },
    "diag.stat.blocks": { EN: "Blocks", FR: "Blocs" },
    "diag.stat.limit": { EN: "At limit", FR: "À la limite" },
    "diag.stat.over": { EN: "Over budget", FR: "En dépassement" },
    "diag.stat.neg": { EN: "Negl. slots / tiles", FR: "Slots négl. / tuiles" },
    "diag.selection": { EN: "Selection", FR: "Sélection" },
    "diag.click.hint": { EN: "Click a block on the map.", FR: "Cliquez sur un bloc de la carte." },
    "diag.hover": { EN: "Tile {tx},{ty} — block {bx},{by}", FR: "Tuile {tx},{ty} — bloc {bx},{by}" },
    "diag.detail": { EN: "<b>Tile {tx},{ty}</b> — block {bx},{by} (LRS {lrs})<br>Textures in this block: <b>{n}</b> / budget {budget} — negligible slots: <b>{neg}</b><br>Whole tile: max {max} textures per block, {negtile} negligible slot(s)", FR: "<b>Tuile {tx},{ty}</b> — bloc {bx},{by} (LRS {lrs})<br>Textures du bloc : <b>{n}</b> / budget {budget} — slots négligeables : <b>{neg}</b><br>Tuile entière : max {max} textures par bloc, {negtile} slot(s) négligeable(s)" },
    "diag.detail.unscanned": { EN: "Tile {tx},{ty}: not in the scan", FR: "Tuile {tx},{ty} : absente du scan" },
    "diag.goto.inspect": { EN: "🔍 Inspect this tile", FR: "🔍 Inspecter cette tuile" },
    "diag.search.title": { EN: "Blocks containing all selected textures", FR: "Blocs contenant toutes les textures cochées" },
    "diag.search.filter": { EN: "Filter textures...", FR: "Filtrer les textures..." },
    "diag.search.btn": { EN: "🔎 Search", FR: "🔎 Rechercher" },
    "diag.search.clear": { EN: "✕ Clear", FR: "✕ Effacer" },
    "diag.search.none": { EN: "Tick at least one texture.", FR: "Cochez au moins une texture." },
    "diag.search.result": { EN: "{n} block(s) in {t} tile(s)", FR: "{n} bloc(s) dans {t} tuile(s)" },
    "diag.csv.btn": { EN: "⬇ Export CSV", FR: "⬇ Export CSV" },
    "diag.csv.done.all": { EN: "CSV: {n} blocks (all) → {path}", FR: "CSV : {n} blocs (tous) → {path}" },
    "diag.csv.done.search": { EN: "CSV: {n} blocks (search) → {path}", FR: "CSV : {n} blocs (recherche) → {path}" },
    "diag.csv.open": { EN: "📂 Show file", FR: "📂 Afficher le fichier" },
    "diag.inspect.title": { EN: "Inspect a tile", FR: "Inspecter une tuile" },
    "diag.inspect.desc": { EN: "Inspect: textured render with the coverage of each slot (red under 1%). Weights: average weight (0-31) of each slot. Validate: consistency of the .ttile and _layer files.", FR: "Inspect : rendu texturé avec la couverture de chaque slot (rouge sous 1 %). Weights : poids moyen (0-31) de chaque slot. Validate : cohérence des fichiers .ttile et _layer." },
    "diag.run": { EN: "▶ Run", FR: "▶ Lancer" },
    "diag.inspect.bad": { EN: "Invalid coordinates", FR: "Coordonnées invalides" },
    "diag.inspect.running": { EN: "Tile {tx},{ty} — {mode}...", FR: "Tuile {tx},{ty} — {mode}..." },
    "diag.inspect.done": { EN: "✅ Tile {tx},{ty} — {mode}", FR: "✅ Tuile {tx},{ty} — {mode}" },
    "diag.zone.title": { EN: "Zone scan (PNG mask)", FR: "Scan de zone (masque PNG)" },
    "diag.zone.desc": { EN: "Scans only the blocks covered by the PNG mask (white = active zone). Read only.", FR: "Scanne uniquement les blocs couverts par le masque PNG (blanc = zone active). Lecture seule." },
    "diag.zone.pick": { EN: "📁 Choose PNG mask", FR: "📁 Choisir le masque PNG" },
    "diag.no.file": { EN: "No file selected", FR: "Aucun fichier choisi" },
    "diag.zone.btn": { EN: "🎯 Scan zone", FR: "🎯 Scanner la zone" },
    "diag.zone.running": { EN: "Zone scan...", FR: "Scan de la zone..." },
    "diag.zone.done": { EN: "✅ Zone scan done", FR: "✅ Scan de la zone terminé" },
    "diag.health.title": { EN: "Terrain health", FR: "Santé du terrain" },
    "diag.health.desc": { EN: "Checks the size of the .ttile files (first 100) and the presence of .EditorData.", FR: "Vérifie la taille des fichiers .ttile (100 premiers) et la présence de .EditorData." },
    "diag.health.btn": { EN: "❤ Analyze", FR: "❤ Analyser" },
    "diag.health.running": { EN: "Analyzing...", FR: "Analyse..." },
    "diag.health.done": { EN: "✅ Analysis done", FR: "✅ Analyse terminée" },
    "diag.health.tiles": { EN: ".ttile files", FR: "Fichiers .ttile" },
    "diag.health.ok": { EN: "OK", FR: "OK" },
    "diag.health.warn": { EN: "Suspicious", FR: "Suspects" },
    "diag.health.err": { EN: "Errors", FR: "Erreurs" },
    "diag.inv.title": { EN: "File inventory", FR: "Inventaire des fichiers" },
    "diag.inv.desc": { EN: "Checks that every expected .ttile and .edds file is present in .Data and .EditorData.", FR: "Vérifie que tous les fichiers .ttile et .edds attendus sont présents dans .Data et .EditorData." },
    "diag.inv.btn": { EN: "📊 Check inventory", FR: "📊 Vérifier l'inventaire" },
    "diag.inv.running": { EN: "Checking files...", FR: "Vérification des fichiers..." },
    "diag.inv.complete": { EN: "✅ All expected .ttile files are present", FR: "✅ Tous les .ttile attendus sont présents" },
    "diag.inv.missing.n": { EN: "❌ {n} .ttile file(s) missing", FR: "❌ {n} fichier(s) .ttile manquant(s)" },
    "diag.inv.ttile": { EN: ".ttile present", FR: ".ttile présents" },
    "diag.inv.missing": { EN: ".ttile missing", FR: ".ttile manquants" },
    "diag.inv.edds": { EN: ".edds present", FR: ".edds présents" },

    // ── Textures du projet (étape 12d) ──────────────────────────────────────────
    "satmap.catalog.not.found": { EN: "Project catalog not found — synchronize in the Textures tab", FR: "Catalog du projet introuvable — synchronisez dans l'onglet Textures" },
    "tex.tab": { EN: "🎨 TEXTURES", FR: "🎨 TEXTURES" },
    "tex.info": { EN: "Project textures (&lt;projet&gt;/textures/): one row per material of the .terr. <b>Synchronize</b> copies the .emat files of the addon into the project (an addon .emat that overrides a vanilla one is merged with it, as Workbench does), finds each middle (project, source image next to the .edds in the addon, then the decoded .edds) and writes catalog.json. A middle chosen by hand is never overwritten.", FR: "Textures du projet (&lt;projet&gt;/textures/) : une ligne par matériau du .terr. <b>Synchroniser</b> copie les .emat de l'addon dans le projet (un .emat de l'addon qui surcharge un vanilla est fusionné avec lui, comme le fait Workbench), cherche chaque middle (projet, image source à côté du .edds dans l'addon, puis .edds décodé) et écrit catalog.json. Un middle choisi à la main n'est jamais écrasé." },
    "tex.sync.btn": { EN: "🔄 Synchronize", FR: "🔄 Synchroniser" },
    "tex.sync.done": { EN: "✅ Synchronized: {added} .emat added, {updated} updated, {middles} middle(s) imported, {missing} middle(s) missing", FR: "✅ Synchronisé : {added} .emat ajouté(s), {updated} mis à jour, {middles} middle(s) importé(s), {missing} middle(s) manquant(s)" },
    "tex.sync.error": { EN: "Synchronization error", FR: "Erreur de synchronisation" },
    "tex.open.emat": { EN: "📁 .emat folder", FR: "📁 Dossier .emat" },
    "tex.open.middles": { EN: "📁 Middles folder", FR: "📁 Dossier middles" },
    "tex.filter": { EN: "Problems only", FR: "Problèmes seulement" },
    "tex.col.material": { EN: "Material", FR: "Matériau" },
    "tex.col.origin": { EN: "Origin", FR: "Origine" },
    "tex.col.middle": { EN: "Middle", FR: "Middle" },
    "tex.col.state": { EN: "State", FR: "État" },
    "tex.col.preview": { EN: "Preview", FR: "Aperçu" },
    "tex.n.total": { EN: "materials", FR: "matériaux" },
    "tex.n.ok": { EN: "middle OK", FR: "middle OK" },
    "tex.n.addon": { EN: "from the addon", FR: "de l'addon" },
    "tex.n.sync": { EN: "to synchronize", FR: "à synchroniser" },
    "tex.n.missing": { EN: "middle missing", FR: "middle manquant" },
    "tex.n.notcat": { EN: "not in catalog", FR: "hors catalog" },
    "tex.n.none": { EN: "without middle", FR: "sans middle" },
    "tex.n.manual": { EN: "manual", FR: "manuel" },
    "tex.origin.custom": { EN: "custom", FR: "custom" },
    "tex.origin.override": { EN: "vanilla overridden", FR: "vanilla surchargé" },
    "tex.origin.vanilla": { EN: "vanilla", FR: "vanilla" },
    "tex.origin.system": { EN: "engine", FR: "moteur" },
    "tex.origin.absent": { EN: "not found", FR: "introuvable" },
    "tex.src.vanilla": { EN: "vanilla", FR: "vanilla" },
    "tex.src.projet": { EN: "project", FR: "projet" },
    "tex.src.addon_image": { EN: "addon image", FR: "image de l'addon" },
    "tex.src.addon_edds": { EN: "decoded .edds", FR: ".edds décodé" },
    "tex.src.manual": { EN: "manual", FR: "manuel" },
    "tex.state.none": { EN: "no middle (flat color)", FR: "sans middle (couleur unie)" },
    "tex.state.missing": { EN: "middle missing", FR: "middle manquant" },
    "tex.state.not_in_catalog": { EN: "not in catalog", FR: "hors catalog" },
    "tex.state.sync": { EN: "addon .emat changed", FR: ".emat de l'addon modifié" },
    "tex.out.of.addon": { EN: "outside the addon (base game or other mod): choose an image", FR: "hors de l'addon (jeu de base ou autre mod) : choisir une image" },
    "tex.choose": { EN: "Choose…", FR: "Choisir…" },
    "tex.unmanual": { EN: "Automatic", FR: "Automatique" },
    "tex.manual.done": { EN: "✅ Middle of {mat}: {middle} (manual)", FR: "✅ Middle de {mat} : {middle} (manuel)" },
    "tex.manual.cleared": { EN: "✅ {mat}: manual choice removed, synchronize to recompute", FR: "✅ {mat} : choix manuel retiré, synchronisez pour recalculer" },
    "tex.no.problem": { EN: "No problem.", FR: "Aucun problème." },
    "tex.empty": { EN: "No material in the .terr.", FR: "Aucun matériau dans le .terr." },
    "tex.warn.missing": { EN: "{n} middle(s) missing (flat color on the satmap)", FR: "{n} middle(s) manquant(s) (couleur unie sur la satmap)" },
    "tex.warn.notcat": { EN: "{n} material(s) not in the catalog", FR: "{n} matériau(x) hors catalog" },
    "tex.warn.sync": { EN: "{n} .emat changed in the addon", FR: "{n} .emat modifié(s) dans l'addon" },
    "tex.warn.link": { EN: "see the Textures tab", FR: "voir l'onglet Textures" },
    "tex.card.title": { EN: "Project textures", FR: "Textures du projet" },
    "tex.card.hint": { EN: ".emat, middles and catalog.json of the project", FR: ".emat, middles et catalog.json du projet" },
    "tex.card.open": { EN: "🎨 Textures tab", FR: "🎨 Onglet Textures" },
    "tex.card.status": { EN: "{total} materials · {ok} middle OK · {missing} problem(s) · {sync} to synchronize", FR: "{total} matériaux · {ok} middle OK · {missing} problème(s) · {sync} à synchroniser" },

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
  function t(key, params) {
    var entry = _dict[key];
    var text = entry ? (entry[_lang] || entry['EN'] || key) : key;
    if (params) {
      text = text.replace(/\{(\w+)\}/g, function(m, name) {
        return params[name] !== undefined && params[name] !== null ? params[name] : m;
      });
    }
    return text;
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
      'border:1px solid var(--mgp-lang-border,#2e6647)',
      'border-radius:4px',
      'color:var(--mgp-lang-color,#5dba7d)',
      'font-family:var(--mgp-lang-font,Courier New),monospace',
      'font-size:10px',
      'letter-spacing:2px',
      'padding:3px 9px',
      'cursor:pointer',
      'margin:0 10px',
      'transition:all .2s',
      'text-transform:uppercase',
    ].join(';');
    btn.onmouseover = function() { this.style.background='var(--mgp-lang-hover,#1a3d2a)'; };
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
