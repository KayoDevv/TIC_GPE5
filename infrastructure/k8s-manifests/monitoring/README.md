# Observability stack (in-house)

Logs + metrics for GPE-NYX, kept entirely on the VM — nothing leaves the box
(GDPR-safe for a security product). ~1–1.3 Gi RAM total.

| Component | Role |
|---|---|
| **Prometheus** (`:9090`) | metrics store, 24 h retention |
| **node-exporter** (DaemonSet) | node CPU / mem / disk / net |
| **kube-state-metrics** | k8s object/pod inventory |
| **Loki** (`:3100`) | log store, 48 h retention |
| **Alloy** (DaemonSet) | tails pod logs → Loki, labels `namespace` / `service` |
| **Grafana** (NodePort **30300**) | dashboards + LogQL/PromQL |

## Access
`http://<node-ip>:30300` — user `admin`, password `charon-observe` (dev cred in
`grafana.yaml`; rotate for prod). Dashboard: **Charon — services & machine**.
- `Service` dropdown filters logs + highlights usage (workers, apps, deps).
- `job_id` textbox traces one submission end-to-end:
  `{service=~"$service"} |= "<job_id>"`.

## Deploy
Manual, over OpenVPN + SSH (it's infra, not part of the app release train):

```
Actions ▸ Deploy monitoring ▸ Run workflow      # or: gh workflow run deploy-monitoring.yml
```

Applies `kubectl apply -k infrastructure/k8s-manifests/monitoring` on the node.

## Notes
- The `monitoring` namespace is **not** Calico default-deny, so no extra
  NetworkPolicies: Prometheus scrapes the kubelet/cAdvisor + node-exporter +
  kube-state-metrics (never ingress into app pods); Alloy reads pod logs via the
  API (`pods/log` RBAC).
- Storage is `emptyDir` (bounded, ephemeral) — restarts lose history but re-fill;
  swap to PVCs if you want durable retention.
- `job_id` is kept **in the log line**, not a Loki label, to avoid high stream
  cardinality — filter it at query time.
