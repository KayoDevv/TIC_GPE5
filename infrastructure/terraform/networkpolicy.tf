# NetworkPolicies — single owner: Terraform (T2). Migrated from the per-app
# kustomize manifests (sandbox/kafka/sinkhole networkpolicy.yaml, removed from
# kustomize). Enforced by Calico.
#
# OUT OF SCOPE (stays in Make): `consumer-apiserver-egress`. The K3s
# kube-apiserver is host-networked (not a pod), so it is matched by an ipBlock
# of the NODE IP, which is host-specific and discovered at deploy time. It
# remains the single host-specific netpol, applied by `make netpol-apiserver`
# from consumer-apiserver-egress.yaml.tmpl. NetworkPolicies are additive, so
# keeping it in Make does not conflict with the rules below.

# ── sandbox namespace ─────────────────────────────────────────────────────────

resource "kubernetes_network_policy_v1" "sandbox_deny_all" {
  metadata {
    name      = "deny-all-default"
    namespace = "sandbox"
  }
  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}

resource "kubernetes_network_policy_v1" "consumer_egress" {
  metadata {
    name      = "consumer-egress"
    namespace = "sandbox"
  }
  spec {
    pod_selector {
      match_labels = { app = "sandbox-consumer" }
    }
    policy_types = ["Egress"]

    # Kafka in-cluster (prod service).
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "kafka" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
      }
    }
    # MinIO in-cluster (prod service).
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "minio" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9000"
      }
    }
    # DNS. (K8s API egress is the separate Make-owned consumer-apiserver-egress.)
    egress {
      to {
        namespace_selector {}
      }
      ports {
        protocol = "UDP"
        port     = "53"
      }
      ports {
        protocol = "TCP"
        port     = "53"
      }
    }
  }
}

resource "kubernetes_network_policy_v1" "watcher_egress" {
  metadata {
    name      = "watcher-egress"
    namespace = "sandbox"
  }
  spec {
    pod_selector {
      match_labels = { app = "minio-watcher" }
    }
    policy_types = ["Egress"]

    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "kafka" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
      }
    }
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "minio" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9000"
      }
    }
    egress {
      to {
        namespace_selector {}
      }
      ports {
        protocol = "UDP"
        port     = "53"
      }
      ports {
        protocol = "TCP"
        port     = "53"
      }
    }
  }
}

# Analysis Jobs: egress limited to Kafka (results), MinIO (sample download), DNS
# (in-cluster lookups) and the D2 sinkhole (INetSim) — and nothing else. A
# malicious sample can reach the fake world but never the real Internet.
resource "kubernetes_network_policy_v1" "analysis_egress" {
  metadata {
    name      = "analysis-egress"
    namespace = "sandbox"
  }
  spec {
    pod_selector {
      match_labels = { "charon.io/role" = "analysis" }
    }
    policy_types = ["Egress"]

    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "kafka" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
      }
    }
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "minio" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9000"
      }
    }
    egress {
      to {
        namespace_selector {}
      }
      ports {
        protocol = "UDP"
        port     = "53"
      }
      ports {
        protocol = "TCP"
        port     = "53"
      }
    }
    # D2 sinkhole (INetSim) — and ONLY the sinkhole. Ports are INetSim's
    # CONTAINER ports (5353/8080): Calico evaluates egress AFTER the Service
    # DNAT, so the destination is the POD:targetPort, not 53/80.
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "sinkhole" }
        }
      }
      ports {
        protocol = "UDP"
        port     = "5353"
      }
      ports {
        protocol = "TCP"
        port     = "5353"
      }
      ports {
        protocol = "TCP"
        port     = "8080"
      }
    }
  }
}

# ── kafka namespace ───────────────────────────────────────────────────────────
# Closes the "verdict forgery" path: deny by default, then allow only the
# sandbox namespace (clients) + intra-namespace traffic (Bitnami provisioning
# Jobs, controller quorum).

resource "kubernetes_network_policy_v1" "kafka_deny_all" {
  metadata {
    name      = "deny-all-default"
    namespace = "kafka"
  }
  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}

resource "kubernetes_network_policy_v1" "kafka_allow" {
  metadata {
    name      = "kafka-allow"
    namespace = "kafka"
  }
  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]

    # Legitimate clients: the sandbox namespace, client listener only.
    ingress {
      from {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "sandbox" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
      }
    }
    # Intra-namespace: Bitnami provisioning Jobs + controller quorum.
    ingress {
      from {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "kafka" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
      }
      ports {
        protocol = "TCP"
        port     = "9093"
      }
    }
    # DNS — the broker resolves its own advertised-listener service name.
    egress {
      to {
        namespace_selector {}
      }
      ports {
        protocol = "UDP"
        port     = "53"
      }
      ports {
        protocol = "TCP"
        port     = "53"
      }
    }
    # Intra-namespace (provisioning Jobs -> broker, controller quorum).
    egress {
      to {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "kafka" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
      }
      ports {
        protocol = "TCP"
        port     = "9093"
      }
    }
  }
}

# ── sinkhole namespace ────────────────────────────────────────────────────────
# The sinkhole reaches NOTHING (deny egress) so a compromised responder cannot
# pivot. Replies to inbound traffic still flow (stateful). Ingress is
# deliberately NOT identity-restricted (gVisor SNATs the source pod identity to
# the node IP, so an ingress selector would silently drop the analysis Jobs;
# confinement is enforced on the sandbox egress side anyway).
resource "kubernetes_network_policy_v1" "sinkhole_deny_egress" {
  metadata {
    name      = "sinkhole-deny-egress"
    namespace = "sinkhole"
  }
  spec {
    pod_selector {}
    policy_types = ["Egress"]
  }
}
