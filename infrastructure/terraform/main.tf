# Charon — Terraform root. Make/TF ownership boundary: see docs/terraform-frontier.md.
# TF owns namespaces/RBAC/netpol/RuntimeClass + the Helm engine; Make keeps the host,
# k3s, CNI, image build/import, and the kustomize workers.

terraform {
  required_version = ">= 1.10"

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

  # State in MinIO (S3 API). The `terraform-state` bucket is created once by
  # `make tf-bootstrap-state` before init. Endpoint = MinIO dev NodePort; not real
  # AWS, so the AWS-specific checks below are skipped.
  backend "s3" {
    bucket = "terraform-state"
    key    = "charon/terraform.tfstate"
    region = "us-east-1" # dummy — MinIO ignores the region

    endpoints = {
      s3 = "http://127.0.0.1:32090"
    }

    access_key = "minioadmin"
    secret_key = "minioadmin"

    use_lockfile = true

    use_path_style              = true
    skip_credentials_validation = true
    skip_region_validation      = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}

# k3s kubeconfig (see `make setup-kubeconfig`).
provider "kubernetes" {
  config_path = pathexpand(var.kubeconfig_path)
}

provider "helm" {
  kubernetes {
    config_path = pathexpand(var.kubeconfig_path)
  }
}
