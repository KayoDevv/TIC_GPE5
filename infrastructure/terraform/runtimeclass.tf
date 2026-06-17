# gVisor RuntimeClass — single owner: Terraform (T2). Previously created by the
# `make install-gvisor` target (kubectl apply), now removed from it.
#
# This is ONLY the K8s object. The host-level prerequisites (the `runsc` binary,
# the containerd-shim, and the runsc runtime declaration in the K3s containerd
# config) stay in `make install-gvisor` — they are not K8s objects and must
# exist on the node before this handler can be scheduled.
resource "kubernetes_runtime_class_v1" "gvisor" {
  metadata {
    name = "gvisor"
  }
  handler = "runsc"
}
