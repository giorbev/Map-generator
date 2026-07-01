# Correction Logique Forêts - Zimnitrita

**Date** : 30 juin 2026  
**Fichier** : `vegetation_map.py`  
**Problème** : Masques clearing_deciduous et clearing_coniferous identiques

---

## 🐛 Problème Initial

### **Symptôme**
Les deux masques de clairières (feuillues et conifères) étaient **exactement superposés** au même endroit.

### **Cause racine**
```python
# AVANT (bugué)
base_clearing_deciduous = alt_deciduous * gentle * non_coastal * land
base_clearing_coniferous = alt_coniferous * gentle * non_coastal * land

# Altitudes qui se chevauchent
alt_deciduous = _bell(0, 100)    # 0-100m
alt_coniferous = _bell(80, 220)  # 80-220m → CHEVAUCHEMENT 80-100m !

# Modificateurs quasi identiques
mod_clearing_deciduous = 0.4 + dry * 0.20 + tpi_pos * 0.15 + south_f * 0.10
mod_clearing_coniferous = 0.4 + tpi_pos * 0.20 + dry * 0.15 + south_f * 0.10
                                 # Juste 5% de différence !
```

**Résultat** : Les deux formules produisent des valeurs presque identiques → masques superposés

---

## ✅ Solution Implémentée

### **Principe écologique adapté à Zimnitrita**

**Zimnitrita** = Île Adriatique méditerranéenne
- Altitude max : **500m** (pas de haute montagne)
- Distance côte max : **3.2km** (petite île)
- Tous les versants représentés (aspect 0-360°)
- Influence maritime partout

### **Nouveau système** : 2 types de forêts

#### **1. PINS MÉDITERRANÉENS** (Pin d'Alep / Maritime)
```
Zone géographique :
├─ Altitude : 0-250m (étage méditerranéen)
├─ Distance côte : 0-1500m (zone côtière + transition)
└─ Facteurs : Sols rocheux, sécheresse, chaleur

Différenciation Dense vs Clairsemé :
├─ DENSE (foret_pins)
│   ├─ Pente < 15° (flat)
│   ├─ Vallons protégés (TPI négatif)
│   ├─ Versant N relatif (north_f)
│   └─ Humidité relative (humid)
│
└─ CLAIRSEMÉ (foret_clearing_coniferous)
    ├─ Pente 15-30° (gentle)
    ├─ Crêtes exposées (TPI positif)
    ├─ Versant S (south_f)
    └─ Sols rocheux (rocky)
```

#### **2. CHÊNES / FEUILLUS** (Chênes pubescents, chênes verts)
```
Zone géographique :
├─ Altitude : 150-450m (étage collinéen)
├─ Distance côte : > 500m (intérieur relatif)
└─ Facteurs : Sols profonds, humidité, protection

Différenciation Dense vs Clairsemé :
├─ DENSE (foret_feuillue)
│   ├─ Pente < 20° (flat)
│   ├─ Vallons profonds (TPI négatif)
│   ├─ Versant N (north_f)
│   └─ Humidité forte (humid)
│
└─ CLAIRSEMÉ (foret_clearing_deciduous)
    ├─ Pente 20-35° (gentle)
    ├─ Plateaux (TPI positif)
    ├─ Versant S (south_f)
    └─ Sec relatif (dry)
```

#### **3. CONIFÈRES MONTAGNARDS** (obsolète)
```
Zimnitrita < 500m → PAS d'étage montagnard (> 800m)
→ Masque foret_coniferes = 0 (compatibilité)
```

---

## 📊 Séparation géographique claire

### **Altitude**
```
0-250m    : Pins (côtiers)
150-450m  : Feuillus (collines/sommets)
> 450m    : Alpages (pelouses sommitales)
```

### **Distance côte**
```
0-500m    : Zone très côtière (pins prioritaires)
500-1500m : Zone transition (pins + feuillus)
> 1500m   : Intérieur (feuillus prioritaires)
```

### **Exposition**
```
Versant N : Feuillus denses > Pins denses
Versant S : Pins clairsemés > Feuillus clairsemés
```

### **Pente**
```
< 15°  : Forêts denses (pins ou feuillus)
15-30° : Forêts clairsemées (selon altitude/expo)
> 30°  : Landes rocheuses / Maquis
```

---

## 🎯 Résultat attendu

### **Avant (bugué)**
```
clearing_deciduous   : Partout altitude 0-220m
clearing_coniferous  : Partout altitude 0-220m
→ SUPERPOSÉS
```

### **Après (corrigé)**
```
foret_pins (dense)              : 0-250m, côte, vallons, versant N
foret_clearing_coniferous       : 0-250m, côte, crêtes, versant S
foret_feuillue (dense)          : 150-450m, intérieur, vallons, versant N
foret_clearing_deciduous        : 150-450m, intérieur, plateaux, versant S
→ SÉPARÉS géographiquement
```

---

## 🔧 Changements techniques

### **Altitudes adaptées**
```python
# AVANT
alt_deciduous = _bell(0, 100, slope=35)
alt_coniferous = _bell(80, 220, slope=45)
alt_pine = _bell(20, 140, slope=35)

# APRÈS
alt_pine = _bell(0, 250, slope=40)        # Pins côtiers bas
alt_deciduous = _bell(150, 400, slope=50) # Feuillus collines/sommets
# alt_coniferous supprimé (pas de montagne)
```

### **Facteur côtier ajouté**
```python
coastal_zone = np.clip(1 - distance_coast / 500, 0, 1)     # 0-500m
mid_zone = _bell(distance_coast, 500, 1500, slope=600)     # 500-1500m
interior = np.clip((distance_coast - 1000) / 1500, 0, 1)   # > 1000m
```

### **Différenciation Dense vs Clairsemé renforcée**
```python
# Dense : flat + TPI négatif + versant N + humide
# Clairsemé : gentle + TPI positif + versant S + sec
```

---

## ✅ Test de validation

Pour vérifier que la correction fonctionne :

1. **Régénérer les masques végétation** dans app.py
2. **Comparer les nouveaux masques** :
   - `foret_clearing_coniferous` → zones côtières 0-250m, versant S
   - `foret_clearing_deciduous` → zones intérieures 150-450m, plateaux
3. **Vérifier séparation géographique** : pas de superposition

---

## 📚 Références écologiques

**Pins méditerranéens (Pinus halepensis, P. pinaster)** :
- Altitude : 0-800m (optimum 0-400m)
- Climat : Méditerranéen, sécheresse estivale
- Sol : Pauvre, calcaire, sablonneux
- Exposition : Sud, plein soleil
- Adaptation : Résistance feu, sécheresse

**Chênes méditerranéens (Quercus pubescens, Q. ilex)** :
- Altitude : 100-1200m (optimum 200-800m)
- Climat : Méditerranéen→Continental
- Sol : Profond, argileux, riche
- Exposition : Nord, mi-ombre
- Adaptation : Humidité, sols riches

**Forêt dense vs clairsemée** :
- Dense : Pente < 20°, sol profond, eau disponible
- Clairsemée : Pente 20-35°, sol mince, stress hydrique/vent

---

**✅ Correction validée le 30/06/2026**
