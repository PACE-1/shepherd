# Name availability: "Shepherd" (roadmap #132)

Written 2026-10-18 from a handful of web searches. **This is not a trademark clearance.** It records what was found, what was not, and what the owner would still need to do.

## Found

- **GNU Shepherd** exists: the service manager (PID 1) of GNU Guix System, formerly "GNU dmd", renamed in 2016 and reported at version 1.0 after about two decades. It is a Guile program for system administrators, a different field from a training planner, so confusion is unlikely but searches for "shepherd" in software will return it first.
- **Shepherd.js** (a product-tour library for web apps) was noted in the original planning discussion; this search did not confirm it.
- **A registered "Shepherd" mark for cycling-training software** was not found in one web search of trade-mark journals. The search cannot see the registers themselves, so absence here proves nothing.
- Other cycling-training and fitness apps hold marks in software classes 9 and 42, under other names.

## Not checked (needs a person or a lawyer)

1. Trademark registers for the word SHEPHERD in classes 9 (downloadable software), 41 (training services) and 42 (software as a service): USPTO, EUIPO, WIPO Global Brand Database, UK IPO.
2. Domain names, and the PyPI / npm / Docker Hub names. This project publishes only `ghcr.io/pace-1/shepherd`, which is namespaced under the owner's organisation, so a package-name clash does not arise there; it would if the project ever published on PyPI or npm.
3. App-store and search results for "Shepherd" plus "training" or "cycling".

## What the repository already does

- Apache-2.0 licence and attribution to Domestique stay in `LICENSE` and `NOTICE` whatever the name is.
- `docs/TRADEMARKS.md` holds the trademark guidance.
- The release channel, image name and update check use `PACE-1/shepherd`.

## Suggestion

Keep the descriptor with the name wherever it can be searched ("Shepherd training planner") and do the register search in item 1 before the next major version's public announcement.

## Detaching the GitHub fork network

GitHub's documentation describes detaching as self-service ("Leave fork network" in the repository's Settings, Danger Zone): public repository, under 1 GB, no child forks, **permanent**. The documentation summary found while writing this says issues, pull requests, stars and watchers are not carried over to the detached repository, while git history is kept. This repository's roadmap lives in its issues, so read GitHub's page ("Detaching a fork") and export the issues before doing it. Detaching changes only the "forked from" label; the attribution that matters is in `NOTICE`.

## Owner decisions for #132 (2026-10-19)

1. The register, domain and app-store search in "Not checked" is done by the owner and found no issues.
2. The owner decided to detach the fork network (see above). The detach itself is a GitHub account action and is not done by this repository's tooling. Export the issues first.

Still open:

3. intervals.icu `User-Agent` and OAuth client registration still name the upstream project (`docs/code-bloat/release-identity.md`). Changing them needs the provider, so leave them until then.
