"""
Configuration des thèmes urbains
"""

def get_all_theme_names():
    """Retourne la liste de tous les thèmes disponibles."""
    return [
        "Generic",
        "USA",
        "European Historic",
        "Rural Bocage",
        "Informal Development",
        "Military/Logistics",
        "Arctic"
    ]

def get_theme_config(theme_name):
    """Retourne la configuration d'un thème spécifique."""
    themes = {
        "Generic": {
            "name": "Generic",
            "description": "Thème générique par défaut"
        },
        "USA": {
            "name": "USA",
            "description": "Style urbain américain"
        },
        "European Historic": {
            "name": "European Historic",
            "description": "Villes européennes historiques"
        },
        "Rural Bocage": {
            "name": "Rural Bocage",
            "description": "Campagne avec bocages"
        },
        "Informal Development": {
            "name": "Informal Development",
            "description": "Développement informel"
        },
        "Military/Logistics": {
            "name": "Military/Logistics",
            "description": "Bases militaires et logistiques"
        },
        "Arctic": {
            "name": "Arctic",
            "description": "Régions arctiques"
        }
    }
    return themes.get(theme_name, themes["Generic"])
