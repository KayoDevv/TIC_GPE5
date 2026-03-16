# Shared Python Core (`zt_shared`)

Ce package autonome contient les librairies fondamentales partagées par l'ensemble des microservices Python (Workers et API Gateway) du projet Zero-Trust.

## Contenu

- `zt_shared/models/` : Modèles de données Pydantic V2 stricts basés sur les JSON Schemas Kafka.
- `zt_shared/kafka/` : Wrappers asynchrones robustes (`KafkaSubscriber`, `KafkaPublisher`) basés sur `aiokafka`.

## Commandes Clés (Développement)

Pour développer dans ce module partagé de manière locale (sans impacter le reste de MacOS), nous utilisons un environnement virtuel Python `venv` traditionnel. Voici les commandes essentielles à exécuter depuis le dossier `packages/core/` :

### 1. Initialiser le projet (Première fois)
```bash
# Créer l'environnement virtuel dans le dossier "venv"
python3 -m venv venv

# Activer l'environnement
source venv/bin/activate

# Installer le package en mode développement avec ses outils (pytest, etc.)
pip install -e ".[dev]"
```

### 2. Lancer la Suite de Tests
L'erreur `command not found: pytest` survient si le `venv` n'est pas activé. Le package est configuré pour exiger une couverture de code de 100%.
```bash
# Toujours s'assurer d'activer l'environnement d'abord
source venv/bin/activate

# Exécuter pytest avec le rapport de couverture dans le terminal
pytest --cov=zt_shared --cov-report=term-missing
```

### 3. Utilisation dans d'autres Workers
Dans le code des workers (ex: `apps/workers/ml_layer`), ce package sera importé facilement grâce à sa structure :
```python
from zt_shared.models.events import FileRequestedEvent
from zt_shared.kafka import KafkaSubscriber
```
