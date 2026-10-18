<img src="https://img.shields.io/badge/Version-v1.0.1-brightgreen" alt="Version">

# Shepherd

Latest: **[v1.0.1 — One interface](https://github.com/PACE-1/shepherd/releases/latest)** (2026-10-17).

This README is being rewritten for v2. See [CHANGELOG.md](CHANGELOG.md) for what changed and [LICENSE](LICENSE) and [NOTICE](NOTICE) for the licence and attribution.

## Docker image

```sh
docker pull ghcr.io/pace-1/shepherd:latest
docker run -d -p 127.0.0.1:22400:22400 -v shepherd-data:/data \
  -e SHEPHERD_ACCESS_TOKEN="$(openssl rand -hex 32)" ghcr.io/pace-1/shepherd:latest
```

Data lives in the `/data` volume. Tags: `vX.Y.Z` (exact, for rollback), `X.Y` and `latest` (stable releases only). Details, rollback and the access policy: [docs/SERVER.md](docs/SERVER.md#docker-image).
