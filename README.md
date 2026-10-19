<img src="https://img.shields.io/badge/Version-v1.0.1-brightgreen" alt="Version">

# Shepherd

A self-hosted training planner for endurance riders (and, increasingly, runners and swimmers). It builds a periodised plan from your goal, hours and fitness, adapts it as you ride, and shows what your data says: load, form, readiness, power curve, ride detail. Your data stays on your machine.

Shepherd is derived from [Domestique](https://github.com/platypus45/domestique) (Apache License 2.0). See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Latest: **[v1.0.1 — One interface](https://github.com/PACE-1/shepherd/releases/latest)** (2026-10-17).

- What changed: [CHANGELOG.md](CHANGELOG.md)
- What is built, what is partial, and what is not: [docs/ROADMAP.md](docs/ROADMAP.md) ("Status and known gaps")

## What it does

- **Plan:** a periodised cycling plan from your goal (FTP, event, general), hours per week and available days; races (A/B/C) with tapers; time off, injury and illness handling; swap, move or dismiss sessions; push planned workouts to your intervals.icu calendar so they reach your Garmin.
- **Library and builder:** a library of structured workouts, plus a builder for your own (power or heart-rate targets).
- **Analysis:** fitness, fatigue and form per sport and combined; power curve and a critical power model; weight trend and W/kg; ride comparison; weekly hours by sport against a split you set; readiness with the inputs that drove it.
- **Running and swimming (partial):** run zones, critical speed, per-run load, a race predictor, swim critical speed and open-water notes. Run and swim sessions inside the plan are not built yet.
- **Everyday use:** an "At a glance" home for newer riders, guided setup, notifications (in-app and optional ntfy), a phone layout and an installable web app, light/dark and colour palettes.
- **Integrations:** intervals.icu (sync, calendar push), an optional AI coach (bring your own provider key), SparkyFitness for nutrition, Open-Meteo for the forecast next to planned sessions.
- **Your data:** CSV export and a backup download from Settings; stored as plain files and SQLite under one folder.

Shepherd is a planner, library and post-ride viewer. It does not control a trainer.

## Supported platforms

Linux only: the **Docker image** and the **Linux AppImage**. macOS and Windows builds and testing are retired.

## Install

### Docker (recommended for a home server)

```sh
docker run -d --name shepherd \
  -p 127.0.0.1:22400:22400 \
  -v shepherd-data:/data \
  -e SHEPHERD_ACCESS_TOKEN="$(openssl rand -hex 32)" \
  ghcr.io/pace-1/shepherd:latest
```

Open `http://127.0.0.1:22400/v2/` and sign in with the token. The image runs in server mode, which needs an access token of at least 24 characters and refuses to start without one. Five wrong tokens in a minute from one address are throttled, and sign-in cookies expire after 30 days. The container runs as UID 10001, not root, and takes one process per data volume. Upgrading a volume written by an earlier (root) image needs a one-time `chown`: see "Upgrading to 4.0 from a root-owned volume" in [docs/SERVER.md](docs/SERVER.md). Put a TLS reverse proxy in front before exposing it beyond your machine: see [docs/SERVER.md](docs/SERVER.md) for the access policy, trusted origins, proxies, and installing it on a phone (needs HTTPS).

The image is published to GitHub's container registry by the release workflow on each version tag (`vX.Y.Z`, `X.Y`, `latest`; a pre-release such as `v4.0.0-beta.1` gets its exact tag and `beta`, and is never `latest`). The workflow has not run yet, and a newly published package is private until it is made public in the GitHub package settings, so until then build it yourself: `docker build -t shepherd .`. Details and rollback: [docs/SERVER.md](docs/SERVER.md).

### AppImage (desktop)

Download `Shepherd-vX.Y.Z-x86_64.AppImage` from the [releases page](https://github.com/PACE-1/shepherd/releases/latest), `chmod +x` it and run it. It opens a window on your own machine and needs no token. The release workflow smoke-tests it in a clean container, but it has not yet been validated on a real desktop session (Wayland or X11, GPU, webview; see issue #94), so report problems as issues.

## First run

1. Open the app; the setup wizard asks for your name and, optionally, your intervals.icu connection. An intervals.icu API key (Settings in intervals.icu, "Developer Settings") is the simplest route. You can also continue without intervals.icu and import FIT files by hand.
2. Enter your FTP, weight and heart-rate numbers, your goal, and the days you can train. Run the guided setup again any time from Settings.
3. Generate a plan from the Plan screen.

## Configuration

Settings in the app cover almost everything. These environment variables matter for deployment:

| Variable | Meaning |
|---|---|
| `SHEPHERD_HOME` | Where all data lives. Default `~/.shepherd`; `/data` in the Docker image. |
| `SHEPHERD_SERVER_MODE`, `SHEPHERD_ACCESS_TOKEN` | Server mode and the shared access token (see docs/SERVER.md). |
| `SHEPHERD_TRUSTED_ORIGINS` | Extra exact origins allowed to make changes, comma separated. |
| `SHEPHERD_PORT` | Port for the desktop app (the Docker image uses 22400). |
| `SHEPHERD_NO_NET` | Set to `1` to stop all outgoing network calls (forecast, sync); used by tests. |

## Update and back up

- Replace the AppImage, or pull a newer image and recreate the container on the same volume. Your data is untouched: see [docs/upgrading.md](docs/upgrading.md).
- Back up from Settings ("Your data"), or with `python -m backup create backup.tar.gz`; restore with `python -m backup restore`. The download leaves out your intervals.icu and AI keys. Details: [docs/DATA.md](docs/DATA.md).

## Privacy

Everything is stored locally. The only outgoing calls are the ones you turn on: intervals.icu, your AI provider, SparkyFitness (your own server), and Open-Meteo (rounded coordinates only, and only if you set a location). See the Settings cards for exactly what each sends.

## Documentation

[docs/README.md](docs/README.md) indexes the rest: [development and the test gate](docs/DEVELOPMENT.md), [the science behind the planner](docs/SCIENCE.md), [system architecture](docs/SYSTEM.md), [the API](docs/API.md).

## Contributing and licence

Please read [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md) first. Python (FastAPI) back end, TypeScript (React) front end. Tests: `tools/gate.sh` for the full gate; `pnpm test` in `web/`. Apache License 2.0; derived from Domestique, see [NOTICE](NOTICE). Trademark guidance: [docs/TRADEMARKS.md](docs/TRADEMARKS.md).
