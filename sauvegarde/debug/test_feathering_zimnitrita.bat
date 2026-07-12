@echo off
echo ============================================================
echo TEST PIPELINE 10 MASQUES - FEATHERING + COASTAL FIX
echo Zimnitrita
echo ============================================================
echo.

cd /d "h:\logiciel perso\Map generator"

python pipeline_core.py ^
  "data/projects/Zimnitrita/sources/Terrain_modified3.asc" ^
  "data/projects/Zimnitrita/generated/terrain_masks_v2" ^
  --curvature "data/projects/Zimnitrita/sources/curvature.png" ^
  --curvature-range "[-21,21]" ^
  --mask-resolution 4096

echo.
echo ============================================================
echo TERMINÉ !
echo Masques générés dans : terrain_masks_v2
echo ============================================================
pause
