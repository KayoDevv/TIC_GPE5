# NetworkPolicies — single owner: Terraform, enforced by Calico.
# OUT OF SCOPE (stays in Make): consumer-apiserver-egress — the host-networked
# kube-apiserver is matched by the node IP (host-specific), applied by
# `make netpol-apiserver`. NetworkPolicies are additive, so it doesn't conflict.

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

# Analysis Jobs: egress only to Kafka, MinIO, DNS and the D2 sinkhole — never the
# real Internet (the sample reaches the fake world only).
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
    # D2 sinkhole only. Ports are INetSim CONTAINER ports (5353/8080): Calico
    # evaluates egress AFTER Service DNAT, so dest = pod:targetPort, not 53/80.
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
# Closes the "verdict forgery" path: deny-all, then allow only the legitimate
# clients (sandbox + minio namespaces) + intra-namespace (Bitnami Jobs, quorum).

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
    # Legitimate clients: the pipeline namespace (core-backend produces
    # file.requested + consumes verdict.result; ml/verdict/llm workers).
    ingress {
      from {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "pipeline" }
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
    # KEDA reads consumer-group lag to scale sandbox-consumer.
    ingress {
      from {
        namespace_selector {
          match_labels = { "kubernetes.io/metadata.name" = "keda" }
        }
      }
      ports {
        protocol = "TCP"
        port     = "9092"
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
# Deny egress so a compromised responder can't pivot (replies still flow, stateful).
# Ingress is NOT identity-restricted: gVisor SNATs the source to the node IP, so an
# ingress selector would silently drop the Jobs; confinement is on the egress side.
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
