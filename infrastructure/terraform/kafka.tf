terraform {
  required_providers {
    kafka = {
      source  = "Mongey/kafka"
      version = "~> 0.5.2"
    }
  }
}

provider "kafka" {
  bootstrap_servers = ["localhost:9092"] # À adapter selon l'environnement
  tls_enabled       = false              # À passer à true en production
}

# Paramètres globaux (Rétention: 60 minutes = 3600000 ms)
locals {
  retention_ms = "3600000"
}

resource "kafka_topic" "file_requested" {
  name               = "file.requested"
  replication_factor = 3
  partitions         = 6 # Plus de partitions pour permettre plus de pods Sandbox Layer (Sandbox)

  config = {
    "retention.ms" = local.retention_ms
  }
}

resource "kafka_topic" "ml_layer_result" {
  name               = "ml_layer.result"
  replication_factor = 3
  partitions         = 3

  config = {
    "retention.ms" = local.retention_ms
  }
}

resource "kafka_topic" "sandbox_layer_result" {
  name               = "sandbox_layer.result"
  replication_factor = 3
  partitions         = 3

  config = {
    "retention.ms" = local.retention_ms
  }
}

resource "kafka_topic" "llm_layer_result" {
  name               = "llm_layer.result"
  replication_factor = 3
  partitions         = 3

  config = {
    "retention.ms" = local.retention_ms
  }
}

resource "kafka_topic" "verdict_layer_result" {
  name               = "verdict.result"
  replication_factor = 3
  partitions         = 3

  config = {
    "retention.ms" = local.retention_ms
  }
}
