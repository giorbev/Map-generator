import numpy as np

def apply_dithering(mask_matrix, target_weight=255):
    """
    Applique un tramage (dithering) aléatoire pixel par pixel sur un masque.

    :param mask_matrix: Matrice 2D (NumPy array) du masque d'origine (0 à 255)
    :param target_weight: La valeur de poids maximale à injecter (255 par défaut)
    :return: (dirt_weights, grass_weights) deux matrices prêtes pour l'injection binaire
    """
    # 1. Normaliser le masque entre 0.0 et 1.0 pour l'utiliser comme probabilité
    probabilities = mask_matrix / 255.0

    # 2. Générer une matrice de bruit aléatoire uniforme de la même taille (entre 0.0 et 1.0)
    random_noise = np.random.rand(*mask_matrix.shape)

    # 3. Comparer pixel par pixel : si la probabilité est supérieure au bruit, on valide
    # On multiplie par target_weight pour obtenir la valeur binaire finale (ex: 255)
    dirt_weights = np.where(probabilities > random_noise, target_weight, 0).astype(np.uint8)

    # 4. Règle des vases communicants : on soustrait la valeur injectée au Grass par défaut
    # Si dirt est à 255, grass passe à 0. Si dirt est à 0, grass reste à 255.
    grass_weights = (255 - dirt_weights).astype(np.uint8)

    return dirt_weights, grass_weights
