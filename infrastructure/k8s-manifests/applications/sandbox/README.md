# Sandbox Layer — K8s manifests

Pattern: **Job-per-analysis**.

The `sandbox-consumer` is a Kafka **dispatcher**: it consumes `file.requested`
and creates 1 `batch/v1 Job` per sample. The actual analysis (hardened container
+ strace + /proc forensics) runs in the Job's pod, isolated by seccomp / reduced
capabilities / deny-egress NetworkPolicy.

## Components

| File | Role |
|---|---|
| `namespace.yaml` | `sandbox` namespace + Pod Security `privileged` (intentional — see note) |
| `rbac.yaml` | consumer SA (can create Jobs) + analysis SA (zero rights) |
| `seccomp-distributor.yaml` | DaemonSet that copies the profile onto each node |
| `consumer-deployment.yaml` | Kafka dispatcher, lightweight, scaled by KEDA |
| `analysis-job-template.yaml` | Analysis Job template — instantiated by the consumer |
| `keda-scaledobject.yaml` | Scale 1→3 on `kafka_consumergroup_lag` + ResourceQuota |
| `networkpolicy.yaml` | Consumer = controlled egress. Analysis = deny-all egress. |

> **Note on Pod Security = `privileged`**: it is intentional. The analysis Jobs add
> `CAP_SYS_PTRACE` (required by `strace -f`), and `SYS_PTRACE` is **not** in the
> `baseline`/`restricted` capability allow-list, so those levels would reject the Jobs at
> admission. The real hardening lives in the Jobs' `securityContext` (runAsNonRoot,
> allowPrivilegeEscalation=false, readOnlyRootFilesystem, cap-drop ALL + add SYS_PTRACE,
> seccomp). See `namespace.yaml` for the full rationale.

## Apply

```bash
kubectl apply -k infrastructure/k8s-manifests/applications/sandbox/
```

## Why this pattern

1. **Strong isolation**: a malicious sample cannot escape the Job. The
   `analysis-deny-egress` NetworkPolicy cuts off all outbound network.
2. **Native scaling**: KEDA scales the *consumers* (1→3 = number of
   `file.requested` partitions). Each consumer dispatches in parallel. The K8s
   scheduler queues the Jobs if nodes saturate — natural backpressure.
3. **Clean lifecycle**: `ttlSecondsAfterFinished: 120` GCs the Jobs automatically.
   `activeDeadlineSeconds: 180` enforces the 120s SLA + margin.
4. **Free observability**: `kubectl get jobs -n sandbox`,
   `kubectl logs job/charon-analysis-<id>`, Prometheus metrics.

## Bottlenecks to watch

| Bottleneck | Mitigation |
|---|---|
| MinIO bandwidth (concurrent PCAP/dump uploads) | Keep MinIO on the same rack as the analysis nodes |
| Image pull storm on scale-up | Non-issue for the agents: they are pre-loaded into containerd at their release tag (workflow "Import sandbox agent images"), never pulled |
| Kafka lag > 5 min | Increase the number of `file.requested` partitions AND KEDA `maxReplicaCount` together (currently 3 = 3 partitions; beyond that = idle consumers) |
| Node CPU exhaustion | `nodeSelector` + `charon.io/sandbox` taint on a dedicated pool |
