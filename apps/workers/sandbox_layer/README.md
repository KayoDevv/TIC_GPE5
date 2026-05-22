# Sandbox Layer : Analyse Comportementale (slow path)

**Tech :** Python · K8s `batch/v1 Job` · strace · state-diff · `/proc` forensics

**Contexte Métier :** Tourne en parallèle du ML Layer dès qu'un fichier est soumis. Capture les
comportements malveillants non-visibles statiquement (obfuscation, payloads téléchargés au runtime,
persistance, C2). Sa sortie `sandbox_layer.result` est consommée par le LLM Layer pour enrichir
son raisonnement sémantique.

**Événements Kafka :**
- **Consomme :** `file.requested`
- **Produit :** `sandbox_layer.result` — `SandboxLayerResultEvent` (IOCs classés MITRE ATT&CK,
  `behavior_summary`, `email_context` pass-through, `timeout_triggered`)

---

## Architecture : Job-per-analysis

```
file.requested
      │
      ▼
sandbox-consumer (Deployment, 1-6 réplicas KEDA)
      │  crée 1 batch/v1 Job par sample
      ▼
ubuntu-sandbox:v1 pod (Job K8s)
      │  run_analysis.py
      ├── download sample (MinIO presigned URL)
      ├── snapshot AVANT  (FS SHA-256, process, sockets, crontab)
      ├── strace -f + sample  ──┐
      ├── /proc forensics       │  en parallèle (thread)
      ├── snapshot APRÈS    ────┘
      ├── 6 hypothèses scorées → anomaly_score
      └── publie SandboxLayerResultEvent → sandbox_layer.result
```

---

## Processus d'analyse (state-diff)

1. **Snapshot AVANT** — hash SHA-256 sur FS (`/etc /home /tmp /var /opt`), `ps`, `ss`, crontab, systemd units
2. **Exécution instrumentée** — `strace -f -tt -e trace=all` avec cap `SYS_PTRACE`, timeout `SANDBOX_TIMEOUT_S` (défaut : 120 s)
3. **Memory forensics** — lecture `/proc/[pid]/maps` + `/proc/[pid]/mem`, extraction régions RWX, strings décodées
4. **Snapshot APRÈS** — même périmètre
5. **Diff** — fichiers créés/modifiés/supprimés, nouveaux process, sockets ouverts, changements crontab/systemd/persistance
6. **6 hypothèses** — fonctions pures `evaluate(diff, signals, memory) -> HypothesisResult` :
   - `persistence_detected` (0.30) · `c2_communication` (0.25) · `code_injection` (0.25)
   - `file_encryption` (0.10) · `evasion_attempted` (0.05) · `propagation` (0.05)
7. **anomaly_score** — somme pondérée des scores, seuil malicious ≥ 0.40, suspicious ≥ 0.15

**Capture Linux (v1) :** strace syscalls + state-diff + `/proc` forensics
**Capture Windows (v2) :** ETW via Sysmon — hors scope v1

---

## Structure du code

```
sandbox_layer/
├── consumer.py              # Dispatcher Kafka → batch/v1 Job
├── Dockerfile.consumer      # Image ghcr.io/kayodevv/charon-sandbox-consumer:latest
├── Dockerfile.agent         # Image ghcr.io/kayodevv/ubuntu-sandbox:v1
├── contract/
│   ├── CONTRACT_VERSION
│   └── golden/              # Fixtures pytest (référence TDD)
└── agent/
    ├── run_analysis.py      # Entrypoint du pod Job
    ├── models.py            # Types internes (SnapshotState, SnapshotDiff, ...)
    ├── snapshot.py          # take_snapshot() / compute_diff()
    ├── strace_collector.py  # parse_strace_log() / extract_sleep_cumulated()
    ├── memory.py            # collect_memory_observables() via /proc
    └── hypotheses/
        ├── _types.py        # HypothesisResult
        ├── persistence.py · c2.py · injection.py
        └── encryption.py · evasion.py · propagation.py
```

---

## Dev local

### Prérequis

- **K3s** installé (`curl -sfL https://get.k3s.io | sh -`)
- **Docker** (build des images sandbox ; Kafka/MinIO sont **in-cluster** — plus de Docker Compose)
- **Helm 3** (pour KEDA + le chart Bitnami Kafka)
- **Python 3.10+**

### Première installation (K3s frais)

```bash
# Bootstrap K3s : ~/.kube/config + KEDA + MinIO Operator (via Helm)
# Idempotent : re-runnable sans risque, no-op si tout est déjà en place.
make bootstrap-k3s

# Infra in-cluster : Kafka (chart Bitnami) + MinIO (StatefulSet)
make bootstrap-in-cluster

# Dépendances Python (runtime)
make install
# ou avec dev/test :
make install-dev

# Build + import des images dans K3s + déploiement overlay dev
make deploy-dev

# (Optionnel) Redis de cache en local — Kafka et MinIO NE sont PAS ici, ils sont in-cluster
make up
```

> `make deploy-dev` ré-exécute `setup-kubeconfig` et `setup-keda` à chaque run.
> Si tout est OK : ~1 s d'overhead. Sinon : auto-fix sans intervention.

### Usage quotidien

```bash
# Re-déploiement après modification (rebuild images + apply manifests)
make deploy-dev

# Surveiller le consumer
kubectl logs -n sandbox -l app=sandbox-consumer -f

# Validation sur corpus (cf. scripts/validation/README.md)
make validate-run RUN_ID=pilot7 REPS=1 CORPUS=validation/corpus MAX_INFLIGHT=15 IDLE_TIMEOUT=300
```

### Cibles bootstrap individuelles

| Cible | Rôle | Quand l'utiliser |
|---|---|---|
| `make setup-kubeconfig` | Copie `/etc/rancher/k3s/k3s.yaml` → `~/.kube/config` | Erreur `x509: certificate signed by unknown authority` |
| `make setup-keda` | Installe KEDA via Helm (namespace `keda`) | `ScaledObject` consumer en CrashLoop / KEDA absent |
| `make setup-minio-operator` | Installe le MinIO Operator | MinIO Operator absent du cluster |
| `make bootstrap-k3s` | Les trois ci-dessus chaînées | Fresh install K3s (ou doute sur l'état) |
| `make bootstrap-in-cluster` | Déploie Kafka (Bitnami) + MinIO (StatefulSet) in-cluster | Monter l'infra après `bootstrap-k3s` |

### Troubleshooting connu

- **`x509: certificate signed by unknown authority`** : un ancien `~/.kube/config` pointe sur un cluster détruit. Fix : `make setup-kubeconfig`.
- **`ScaledObject` consumer en erreur / pas de scaling** : KEDA absent du cluster. Fix : `make setup-keda`.
- **Pods sandbox `CrashLoopBackOff` (Kafka unreachable)** : vérifier `kubectl get pods -n kafka` (broker Bitnami doit être `Running`) et que les NetworkPolicies autorisent l'egress vers `kafka.kafka.svc.cluster.local:9092`.
- **`helm: command not found`** lors de `setup-keda` : installer Helm 3 ([helm.sh/docs/intro/install](https://helm.sh/docs/intro/install/)).

### Réseau in-cluster

Kafka et MinIO tournent in-cluster :
- **Kafka** : Bitnami Helm chart, namespace `kafka`, service `kafka.kafka.svc.cluster.local:9092`
- **MinIO** : StatefulSet standalone, namespace `minio`, service `minio.minio.svc.cluster.local:9000`

Le consumer et les pods d'analyse joignent ces services via le DNS K8s. Les NetworkPolicies
`analysis-egress` / `consumer-egress` / `watcher-egress` (overlay dev) autorisent uniquement
l'egress vers ces 2 namespaces + DNS + API K8s — tout autre trafic est bloqué par
`deny-all-default` (enforcement via kube-router).

---

## Isolation pod d'analyse

| Paramètre | Valeur |
|---|---|
| Capability | `SYS_PTRACE` uniquement |
| Seccomp | `charon-seccomp.json` (whitelist) |
| NetworkPolicy | `analysis-deny-egress` — DENY-ALL sortie |
| Timeout dur | `activeDeadlineSeconds: 180` |
| Ressources | requests 500m/512Mi · limits 2000m/2Gi |

### NetworkPolicy consumer-egress — destinations autorisées

| Destination | Port | Pourquoi |
|---|---|---|
| `namespaceSelector: kafka` | 9092 | Bitnami Kafka in-cluster |
| `namespaceSelector: minio` | 9000 | MinIO StatefulSet in-cluster |
| `namespaceSelector: default` | 443, 6443 | API K8s (service `kubernetes` in default ns) — pour création de Jobs batch/v1 |
| tout namespace | 53 UDP/TCP | DNS cluster (kube-dns) |

Tout autre trafic est bloqué par `deny-all-default`. Enforcement via kube-router DaemonSet.

---

## Scalabilité

KEDA `ScaledObject` : 1→3 réplicas sur `kafka_consumergroup_lag` (topic `file.requested`,
3 partitions). `ResourceQuota` : 12 pods max dans le namespace sandbox (consumers + jobs d'analyse).
