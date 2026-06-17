# Charon — Terraform root.
#
# Make/TF boundary (see docs/terraform-frontier.md): Terraform owns the
# COMPARTMENTS (namespaces/RBAC/netpol/RuntimeClass/VAP) and the ENGINE (Helm
# KEDA+Kafka, MinIO). The Makefile keeps the HULL (host, k3s, CNI, runsc
# binary, image build/import) and the CARGO (workers via kustomize).
#
# T1 = foundation: providers + state backend + namespaces (this file +
# namespaces.tf). RBAC/netpol/helm/minio land in T2/T3.

terraform {
  required_version = ">= 1.6"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.31"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15"
    }
  }

  # State stored in MinIO via its S3-compatible API. Chicken/egg assumed: the
  # `terraform-state` bucket is created ONCE by `make tf-bootstrap-state` (mc)
  # BEFORE the first `terraform init`. Endpoint = MinIO dev NodePort (32090);
  # MinIO is NOT real AWS -> all AWS-specific checks are skipped. Single-node
  # dev: 127.0.0.1 is enough.
  backend "s3" {
    bucket = "terraform-state"
    key    = "charon/terraform.tfstate"
    region = "us-east-1" # dummy — MinIO ignores the region

    endpoints = {
      s3 = "http://127.0.0.1:32090"
    }

    access_key = "minioadmin"
    secret_key = "minioadmin"

    use_path_style              = true
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}

# k3s writes its kubeconfig here (see `make setup-kubeconfig`). Single-node:
# no context alias, use the current one.
provider "kubernetes" {
  config_path = pathexpand(var.kubeconfig_path)
}

provider "helm" {
  kubernetes {
    config_path = pathexpand(var.kubeconfig_path)
  }
}
