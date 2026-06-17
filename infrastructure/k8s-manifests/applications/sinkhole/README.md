# Sinkhole (D2) — INetSim responder

Replaces the NXDOMAIN dead-end that kills C2-keyed malware (resolve fails →
sample bails → contentless → miss). The sinkhole resolves **every** DNS query to
itself and answers HTTP/HTTPS with fake content, so the sample keeps running and
reveals its behaviour.

## Status — Phase 1 (this directory)

Phase 1 deploys the responder **in isolation**: it does NOT yet touch the analysis
pipeline. The analysis Jobs still use cluster DNS and cannot reach the sinkhole
until phases 2–3. Nothing here changes existing behaviour.

| Component | File |
|---|---|
| Namespace (privileged PSA — INetSim needs root start) | `namespace.yaml` |
| INetSim config (DNS+HTTP, high ports; HTTPS deferred) | `configmap.yaml` |
| Deployment (root start → drops services to non-root, RO rootfs, only SETUID/SETGID caps) | `deployment.yaml` |
| Service `sinkhole-dns` (fixed ClusterIP 10.43.0.53) | `service.yaml` |
| Isolation (deny-all + ingress from sandbox analysis; **zero egress**) | `networkpolicy.yaml` |
| Image build | `apps/sinkhole/Dockerfile.inetsim` (`make build-sinkhole`) |

### Guardrail #1 (non-negotiable)
The sinkhole reaches **nothing** — `networkpolicy.yaml` denies all egress. The
malware talks to the sinkhole; neither the malware nor a compromised sinkhole
ever reaches the real internet. Every later phase re-checks this.

### Pinned ClusterIP
`service.yaml` `clusterIP` and `configmap.yaml` `dns_default_ip` are both
`10.43.0.53` and **must stay in sync**. Verify it is free in the K3s service CIDR
(`10.43.0.0/16`; CoreDNS is usually `10.43.0.10`) before applying.

## Deploy (on the VM)

```bash
# 1. Build + import the image into containerd (GHCR is archive only).
make build-sinkhole
docker save ghcr.io/kayodevv/inetsim-sinkhole:v1.0.0 | sudo k3s ctr images import -

# 2. Apply the manifests.
kubectl apply -k infrastructure/k8s-manifests/applications/sinkhole
kubectl -n sinkhole rollout status deploy/inetsim
```

> Build note: INetSim ships from inetsim.org (not Debian main). If the build
> fails on a Perl dependency, adjust the package list in the Dockerfile — the
> image build is the one part of phase 1 that needs validating on the VM.

## Phase 1 acceptance test (reachability)

Use **port-forward** (kubelet → pod, bypasses NetworkPolicy). A temp pod in the
sinkhole namespace does NOT work for this test: `deny-all-default` denies egress
for *every* pod in the namespace (by design), so the probe pod cannot send its
own request. The full Service path (ClusterIP 10.43.0.53) is exercised end-to-end
in phase 2, when the analysis pod — explicitly allowed egress to the sinkhole —
becomes the real client.

```bash
kubectl -n sinkhole port-forward deploy/inetsim 15353:5353 18080:8080 >/tmp/pf.log 2>&1 &
PF=$!; sleep 2
# dig over a host-network container (host has no dig); INetSim DNS is tcp+udp.
docker run --rm --network host nicolaka/netshoot dig +tcp +short test.example.com @127.0.0.1 -p 15353
curl -s -o /dev/null -w "[http] http=%{http_code}\n" http://127.0.0.1:18080/
kill $PF
```

Expected (validated 2026-06-11): `dig` → `10.43.0.53` (every domain resolves to
the sinkhole), `curl` → an HTTP response from a live server (e.g. `http=404`).
Any served HTTP code beats the NXDOMAIN dead-end — that is the phase-1 criterion.

Known tuning, deferred:
- **404 → 200:** INetSim returns 404 for `/` under the current data dir; making
  responses realistic enough to keep more malware families running is phase-4 work.
- **POST capture:** the read-only rootfs makes `data/http/postdata` unwritable
  (a startup warning, harmless for GET). Capturing POSTed C2 data in phase 4 will
  need a writable data dir (initContainer copy of `/opt/inetsim/data` → emptyDir).

## Phase 2 — egress (C4) — DONE (validated 2026-06-11)

The `analysis-egress` NetworkPolicy (now Terraform-owned, `infrastructure/terraform/networkpolicy.tf`)
allows the analysis Jobs to reach the sinkhole (and only it) on the container ports 5353/8080.
Validated from a gVisor analysis-labelled pod (steady state): sinkhole HTTP → 404,
DNS → 10.43.0.53, and `https://1.1.1.1` / `http://1.1.1.1` → blocked.

Two findings from this phase:
- **gVisor SNAT → sinkhole ingress cannot be identity-restricted.** A gVisor pod
  reaches a ClusterIP SNATed to the node IP, so a namespaceSelector/podSelector
  *ingress* rule on the sinkhole never matches and silently drops the Jobs.
  Hence the sinkhole NetworkPolicy (Terraform-owned, `networkpolicy.tf`,
  `sinkhole_deny_egress`) only denies egress (anti-pivot) and leaves ingress open;
  confinement is enforced on the sandbox `analysis-egress` side.
- **Calico egress startup race (pre-existing, not D2).** For the first ~1-3 s of a
  pod, the egress policy is not yet programmed → outbound leaks, then it is
  enforced. Low practical risk here (the sample is detonated only *after* the
  agent downloads it, by which point the policy is live), but a real hardening
  gap — see TASKS (sandbox isolation startup race).

## Next phases (NOT in this directory yet)
- **Phase 3 — DNS (C3):** uncomment the V7 `dnsConfig` stub in
  `analysis-job-template.yaml`, nameserver = `10.43.0.53`. The sample now resolves
  its C2 via the sinkhole and keeps running.
- **Phase 4 — observation (C5+C6):** an agent collector parses INetSim logs +
  a tcpdump sidecar PCAP into `RuntimeSignals.network` (today always empty), so
  `c2.py` / `pdf_uri.py` fire on the captured traffic. **This is where detection
  actually appears.**
