# Contributing to Map Generator Pro 🗺️

Merci de votre intérêt pour contribuer ! Ce document explique comment aider au projet.

---

## 🎯 Priorités de Contribution

Consultez [TODO.md](TODO.md) pour voir les priorités actuelles :

### ⭐⭐⭐ TRÈS HAUTE PRIORITÉ (commencer ici !)
- **v3.1 Morphologie** — Ajouter analyses TPI, Aspect, Flow
- **v3.2 Système Projets** — Gestion projets + import/export
- **v3.3 UI Redesign** — Amélioration graphique interface

### ⭐⭐ MOYENNE PRIORITÉ
- Tests unitaires + validation
- Documentation améliorée
- Exemples d'utilisation

### ⭐ BASSE PRIORITÉ
- Optimisations performance
- Refactoring code technique

---

## 🔧 Configuration Développement

```bash
# 1. Fork + Clone
git clone https://github.com/YOUR-USERNAME/map-generator.git
cd "Map generator"

# 2. Créer branche feature
git checkout -b feature/ma-feature

# 3. Virtual env
python -m venv .venv
.venv\Scripts\Activate.ps1

# 4. Installer packages + dev tools
pip install -r requirements.txt
pip install pytest pytest-cov flake8 black isort

# 5. Lancer app
streamlit run app.py
```

---

## 📝 Process de Contribution

### 1. Créer une Issue
```
Titre: [FEATURE] Morphologie — Ajouter Aspect/Exposition
Description: 
- Quoi : Ajouter calcul orientation versants (N/S/E/W)
- Pourquoi : Textures plus réalistes basées sur versant nord/sud
- Fichiers affectés : naturemap_biomes_generator.py
```

### 2. Créer Pull Request
```bash
git add .
git commit -m "feat(morpho): Add aspect calculation for terrain orientation"
git push origin feature/aspect-calculation

# Puis créer PR sur GitHub avec :
# - Description claire
# - Référence à l'Issue (#123)
# - Screenshot résultats (si visuel)
# - Tests validant la feature
```

### 3. Code Review
- Au moins 1 review avant merge
- Tests doivent passer
- Format code conforme (voir section suivante)

---

## 🎨 Standards de Code

### Format Python
```bash
# Formatter automatiquement
black map_generator.py
isort map_generator.py

# Vérifier linting
flake8 map_generator.py --max-line-length=120
```

### Conventions de Nommage
```python
# Classes : PascalCase
class NatureMapBiomesGenerator:
    pass

# Méthodes/fonctions : snake_case
def compute_slope_from_heightmap(heightmap):
    pass

# Constantes : UPPER_SNAKE_CASE
MAX_ALTITUDE = 3000.0

# Variables privées : _snake_case
self._internal_cache = None
```

### Docstrings
```python
def generate_colormap(self, smooth=True):
    """
    Génère la colormap hypsométrique.
    
    Args:
        smooth (bool): Appliquer lissage bilinéaire.
        
    Returns:
        Tuple[Image, np.ndarray]: (Image PIL RGB, array colormap BGR)
        
    Raises:
        ValueError: Si heightmap invalide
        
    Examples:
        >>> gen = HypsometricColormapGenerator('input/map.asc')
        >>> img, colormap = gen.generate(smooth=True)
    """
```

---

## ✅ Checklist Avant PR

- [ ] Code formaté (`black` + `isort`)
- [ ] Linting passed (`flake8`)
- [ ] Tests ajoutés pour nouvelle feature
- [ ] Docstrings complètes
- [ ] Pas de fichiers volumineux (< 50MB)
- [ ] Commits cleaner avec messages clairs
- [ ] Branche à jour avec `main`

---

## 🧪 Tests

### Tester une feature
```python
# test_morphology.py
import pytest
from naturemap_biomes_generator import NatureMapBiomesGenerator

def test_aspect_calculation():
    """Valide calcul exposition"""
    gen = NatureMapBiomesGenerator('input/bornholm_ter.asc')
    gen._analyze_heightmap()
    
    assert hasattr(gen, 'aspect_deg')
    assert gen.aspect_deg.min() >= 0
    assert gen.aspect_deg.max() <= 360
    print("✅ Aspect calculation OK")

if __name__ == '__main__':
    test_aspect_calculation()
```

### Lancer tests
```bash
pytest test_morphology.py -v
pytest test_*.py --cov=naturemap_biomes_generator
```

---

## 📚 Architecture & Patterns

### DDD (Domain-Driven Design)
Le projet suit DDD avec :
- **Domain** → Modèles purs (pas de dépendances externes)
- **Application** → Use cases + Facades
- **Infrastructure** → Adapters + Exporters

### Ajouter une nouvelle feature
```
1. Créer modèle dans domain/models/
2. Créer service métier dans domain/services/
3. Créer use_case dans application/use_cases/
4. Intégrer dans app.py (UI)
5. Exporter si nécessaire (infrastructure/exporters/)
```

### Exemple : Ajouter Aspect
```
domain/
├── models/
│   └── aspect.py         # Modèle AspectMap
├── services/
│   └── aspect_service.py # Calcul + logic
application/
└── use_cases/
    └── compute_aspect_use_case.py
```

---

## 🐛 Signaler des Bugs

**Format :**
```
Titre: [BUG] Hypsométrique crash sur PNG 16-bit
Description:
- Système : Windows 11, Python 3.11
- Étapes : 
  1. Charger PNG 16-bit
  2. Cliquer "Générer Hypsométrique"
  3. → Crash MemoryError
  
- Erreur :
  MemoryError: Unable to allocate 8.5 GiB for an array
  
- Fichiers logs : [screenshot]
```

---

## 💡 Suggestions d'Amélioration

**Feature Request :**
```
Titre: [FEATURE] Support import GeoTIFF
Description:
- GeoTIFF inclut géoréférencement (projection, origine)
- Utile pour données SIG réelles
- Stack : rasterio pour GeoTIFF
```

---

## 📖 Ressources Utiles

- **NOTICE.md** — Architecture détaillée
- **TODO.md** — Roadmap + priorités
- **[Streamlit Docs](https://docs.streamlit.io/)**
- **[OpenCV Docs](https://docs.opencv.org/)**
- **[NumPy Docs](https://numpy.org/doc/)**

---

## 🎓 Premiers Pas (Débutants)

1. **Lire [NOTICE.md](NOTICE.md)** pour comprendre architecture
2. **Choisir une issue marquée `good-first-issue`**
3. **Créer feature branch** : `git checkout -b fix/issue-123`
4. **Coder + tester** localement
5. **Soumettre PR** avec description claire

**Issues faciles pour commencer :**
- Documentation améliorée
- Ajouter exemples dans docstrings
- Améliorer messages d'erreur
- Ajouter tests unitaires
- Refactoring non-critique

---

## 🚀 Fusion (Maintainers)

**Checklist avant merge :**
- [ ] 1+ approval
- [ ] Tests passent
- [ ] Pas de conflits
- [ ] Changelog mis à jour
- [ ] Version bump si nécessaire

**Commit message de fusion :**
```
Merge branch 'feature/aspect-calculation'

feat(morpho): Add aspect/exposition calculation for terrain orientation
- Compute versant orientation (0-360°)
- Integrate with texture layer generation
- 10% performance improvement through caching

Fixes #123
```

---

## 📞 Questions ?

- **Issues** : GitHub Issues pour bugs/features
- **Discussions** : GitHub Discussions pour questions générales
- **Chat** : (si disponible) Discord/Slack

---

**Merci de votre contribution ! 🙏**

Ensemble, créons le meilleur générateur de cartes pour jeux vidéo !

---

*Last updated: 9 mai 2026*
