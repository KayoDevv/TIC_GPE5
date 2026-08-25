# Website

Static Nuxt page served by nginx, exposed on the LAN through k3s's bundled
Traefik on **port 80** (`http://<node>/`). Its only function is to hand out
`charon-extension.zip`.

It started on NodePort 30081, which never worked: the network path between the
LAN and the node rejects that port whatever listens on it — reproduced with a
plain HTTP server in place of the Service, while 80, 443, 22, 6443, 30080 and
32090 all connect. Ports 80/443 reach Traefik, so the site goes through it and
the Service is a plain ClusterIP.

| Object | Role | Image |
|---|---|---|
| `website` | nginx serving the generated site + the extension ZIP, behind Traefik | `ghcr.io/kayodevv/charon-website` |

## The ZIP is baked into the image

`apps/website/Dockerfile` builds the extension (`wxt zip`) and copies the archive
into the site's `public/` before `nuxt generate`. One image therefore carries a
site and the exact extension build that matches it — publishing a new extension
means bumping the website image header, not shipping a file to the node.

`VITE_API_BASE_URL` is inlined by Vite at build time
(`apps/frontend/src/p0/settings.ts`): it is a **build** input, not a runtime one.
It defaults to `http://localhost:8000`; the published image must be built with
the LAN address of core-backend's NodePort 30080, or the extension will call
localhost on the user's machine.

## Deploy

```bash
kubectl apply -k infrastructure/k8s-manifests/applications/website
```

`deploy-pipeline.yml` does this on the VM after the pipeline rollout.
