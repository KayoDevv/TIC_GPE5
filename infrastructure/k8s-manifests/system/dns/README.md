# system/dns — Charon internal DNS zone

Short aliases for cross-namespace services, served by K3s CoreDNS via a
`coredns-custom` ConfigMap (imported into the default `.:53` block).

| Alias | Resolves to |
|---|---|
| `kafka.charon.internal` | `kafka.kafka.svc.cluster.local` |
| `minio.charon.internal` | `minio.minio.svc.cluster.local` |
| `redis.charon.internal` | `redis.pipeline.svc.cluster.local` |
| `prometheus.charon.internal` | `prometheus.monitoring.svc.cluster.local` |
| `loki.charon.internal` | `loki.monitoring.svc.cluster.local` |

Ports stay in the client string (`kafka.charon.internal:9092`). The old FQDNs keep
resolving, so migration is non-breaking.

## Apply

```bash
make setup-coredns-zone
```

Idempotent: applies the ConfigMap and restarts CoreDNS to pick it up.

## Verify

```bash
kubectl run dnstest --rm -it --image=busybox:1.36 --restart=Never -- \
  nslookup kafka.charon.internal
```

## Scope / caveats

- **Cluster-resolver pods only.** The detonation sandbox runs `dnsPolicy: None`
  against the sinkhole resolver and never sees this zone — intentional isolation.
- **Not for the SSRF-bound presign host** nor the host-side validation feeder; both
  stay on the FQDN / node endpoint. See `docs/coredns-endpoint-simplification-plan.md`.
