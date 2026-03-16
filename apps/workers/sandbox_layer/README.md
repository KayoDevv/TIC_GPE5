# Sandbox Layer : Sandbox (L'Analyse Comportementale)

**Tech :** Python, MicroVM isolées (Firecracker) avec OS Windows 10/11 et/ou Linux.

**Code Guidelines :** TDD (pytest-asyncio). Timeout strict à 120s. L'utilisation de conteneurs Docker classiques est strictement interdite pour l'exécution.

**Contexte Métier :** "L'Analyse Comportementale". Exécution dans un environnement contrôlé avec leurres pour capturer les actions malveillantes (Syscalls, réseau).

**Responsabilité :** Extraire les comportements cachés (obfuscation).

**Événements Kafka (Consommés/Produits) :**
- **Consomme :** `file.requested`.
- **Produit :** `sandbox_layer.result` (Rapport JSON structuré des Indicateurs de Compromission classés MITRE ATT&CK).

## Specifications Techniques
- **Orchestration :** Déploiement et pilotage des MicroVMs via l'API Socket UNIX locale de **Firecracker**. Le worker instancie les VMs dynamiquement à la volée.
- **Golden Images :** Pré-chargement des images de disques (_rootfs_) contenant les systèmes d'exploitation sains (Windows 10/11 allégé, Linux Ubuntu/Alpine) en mode *Snapshot* pour un boot ultra-rapide (< 100ms).
- **Processus d'Analyse (Snapshot Differencing) :** 
  1. **Injection :** Détonation du payload dans la MicroVM cible (choisie dynamiquement selon l'extension présumée du système).
  2. **Timeout :** Implémentation stricte d'un chronomètre `asyncio.wait_for`. Interruption forcée de la VM à 120 secondes maximum.
  3. **Capture Windows :** Extraction en temps réel (ou post-mortem) des logs ETW (Event Tracing for Windows via Sysmon) et de l'arborescence des processus.
  4. **Capture Linux :** Extraction des comportements noyaux via eBPF (sys_execve, sys_connect) et logs d'accès Inodes.
- **Rapport (Diffing) :** La sortie est un rapport JSON parsé qui transforme la différence d'état du système d'exploitation en une liste d'IOCs standardisés.
- **Scalabilité :** Doit s'intégrer avec les métriques Prometheus du Consumer Lag Kafka pour permettre au cluster Kubernetes de démarrer automatiquement de nouveaux pods Sandbox en cas d'engorgement.
