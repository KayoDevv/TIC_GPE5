# ML Layer : Static ML (Le Filtre Rapide)

**Tech :** Python, Modèle Machine Learning tabulaire (LightGBM ou Random Forest via ONNX Runtime).

**Code Guidelines :** TDD strict (pytest-asyncio). SLA de traitement ultra-rapide : < 500 millisecondes.

**Contexte Métier :** "Le Filtre Rapide". Détection des menaces connues et analyse structurelle préliminaire (Calcul d'empreintes, Entropie).

**Responsabilité :** Servir de "Fast-Track" pour les fichiers légitimes évidents ou bloquer instantanément les menaces simples.

**Événements Kafka (Consommés/Produits) :**
- **Consomme :** `file.requested`.
- **Produit :** `ml_layer.result` (Score de risque 0-100 et tags statiques).

## Specifications Techniques
- **Modèle :** Modèle Machine Learning tabulaire (LightGBM ou Random Forest), exporté au format ONNX pour garantir une inférence ultra-rapide et décorrélée de Python.
- **Entrées :** URL S3 du fichier, SHA-256.
- **Traitement Asynchrone :**
  1. Téléchargement du fichier de manière asynchrone depuis le bucket S3/MinIO.
  2. Extraction de _features_ statiques : Entropie globale, sections PE (si exécutable Windows), strings en clair, imports/exports suspects.
  3. Inférence via ONNX Runtime.
- **Sortie :** Score de risque (0-100) et liste de tags statiques (ex: `packer_detected`, `high_entropy`).
- **Contraintes de Performance :** Le code doit impérativement s'exécuter et rendre son verdict Kafka en moins de **500ms** (hors temps de téléchargement S3). L'asynchronisme python (`asyncio`) est requis pour traiter des milliers d'inférences en parallèle sur le même thread.
