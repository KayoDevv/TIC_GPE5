# Sandbox Layer — Manifests K8s

Pattern : **Job-per-analysis**.

Le `sandbox-consumer` est un **dispatcher** Kafka : il consomme `file.requested`
et crée 1 `batch/v1 Job` par sample. L'analyse réelle (Docker durci + strace
+ /proc forensics) tourne dans le pod du Job, isolé par seccomp / capabilities
réduites / NetworkPolicy deny-egress.

## Composants

| Fichier | Rôle |
|---|---|
| `namespace.yaml` | Namespace `sandbox` + Pod Security `restricted` |
| `rbac.yaml` | SA consumer (peut créer Jobs) + SA analysis (zéro droit) |
| `seccomp-distributor.yaml` | DaemonSet qui copie le profil sur chaque nœud |
| `consumer-deployment.yaml` | Dispatcher Kafka, léger, scalé par KEDA |
| `analysis-job-template.yaml` | Template du Job d'analyse — instancié par le consumer |
| `keda-scaledobject.yaml` | Scale 1→3 sur `kafka_consumergroup_lag` + ResourceQuota |
| `networkpolicy.yaml` | Consumer = egress contrôlé. Analyse = deny-all egress. |

## Apply

```bash
kubectl apply -k infrastructure/k8s-manifests/applications/sandbox/
```

## Pourquoi ce pattern

1. **Isolation forte** : un sample malveillant ne peut pas escape le Job.
   La `NetworkPolicy analysis-deny-egress` coupe toute sortie réseau.
2. **Scaling natif** : KEDA scale les *consumers* (1→3 = nb partitions
   `file.requested`). Chaque consumer dispatche en parallèle. Le K8s scheduler
   gère la file des Jobs si les nœuds saturent — backpressure naturelle.
3. **Lifecycle propre** : `ttlSecondsAfterFinished: 120` GC les Jobs auto.
   `activeDeadlineSeconds: 180` enforce le SLA 120s + marge.
4. **Observability gratuite** : `kubectl get jobs -n sandbox`,
   `kubectl logs job/charon-analysis-<id>`, métriques Prometheus.

## Goulots à surveiller

| Goulot | Mitigation |
|---|---|
| Bande passante MinIO (uploads PCAP/dumps simultanés) | MinIO sur même rack que les nœuds analyse — voir `infrastructure/terraform/network/` |
| Image pull storm sur scale-up | Pre-pull `ubuntu-sandbox:v1` via DaemonSet pause, ou registry mirror |
| Lag Kafka > 5 min | Augmenter le nb de partitions `file.requested` ET `maxReplicaCount` KEDA de concert (actuellement 3 = 3 partitions ; au-delà = consumers idle) |
| Exhaustion CPU nœud | `nodeSelector` + taint `charon.io/sandbox` sur un pool dédié |
