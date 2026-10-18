# Updating Shepherd

## TL;DR

Replace the AppImage with the new one, or pull the new Docker image and recreate the container on the same data volume. Everything in your data folder (`~/.shepherd/`, or `/data` in Docker) is left alone — rides, current and archived plans, FTP history, wellness logs, ICU credentials, and athlete profile all survive every install. Only the application itself (code, ZWO library, virtual routes, templates) is replaced.

---

## What's preserved

All user state lives under `~/.shepherd/` (`/data` in the Docker image), outside the application. Replacing the AppImage or the container does not touch it.

| Category | Path | Contents |
|---|---|---|
| Rider profile | `profiles/<id>/athlete.json` | FTP, weight, LTHR, HRV/RHR baselines, FTP test history ledger |
| ICU credentials | `profiles/<id>/.env` (mode 0600) | `ICU_ATHLETE_ID`, `ICU_API_KEY` |
| Profile registry | `profiles.json` | id, name, colour, active flag |
| User preferences | `profiles/<id>/user_prefs.json` | hours/week, available days, rest days |
| Activity DB | `profiles/<id>/health_tracker.db` | wellness, activities, daily Hooper log, athlete metrics, blood markers |
| Current plan | `profiles/<id>/plans/current_plan.json` | active periodised plan |
| Archived plans | `profiles/<id>/plans/*.json` | rotated previous plans |
| Rides archive | `rides/*.fit` | imported FIT files (shared across profiles) |
| ICU per-ride summaries | `rides/icu/*.json` | pulled from intervals.icu |
| Wellness logs | `wellness/YYYY-MM-DD.json` | HRV, RHR, sleep records |
| Path overrides | `user_paths.json` | optional `WORKOUT_DIR` / `GPX_DIR` |
| Boot logs | `logs/*.log` | rotated logs |

---

## What gets replaced

The AppImage file, or the Docker image. That holds the Python code, bundled ZWO library, virtual routes, and templates. Replaced wholesale. macOS and Windows builds are retired.

---

## First boot after upgrade

On first launch after a version bump you'll see a one-off toast naming the from→to versions and confirming all rider data is preserved. Fires once per transition (per-version localStorage flag). The previous-run version is recorded at `~/.shepherd/last_run_version.txt`.

---

## What if something looks wrong?

- Check `~/.shepherd/last_run_version.txt` — it should match the version in Settings.
- The only legacy delete path is `migrate_profiles.py:295-300`, which ran once during the v3.x→v4 layout migration after copying files into `profiles/default/`. No-op on v1.x installs.
- Nothing in v1.x deletes user data automatically. Profile deletion is user-initiated only.
- Missing ride or plan? Files are plain `.fit` / `.json` under `~/.shepherd/rides/` and `~/.shepherd/profiles/<id>/plans/`.

---

## If an upgrade is interrupted

The legacy-to-profiles migration copies files into `profiles/default/`, writes `profiles.json` last, and deletes the originals only after the registry reads back correctly. `tests/test_migration_interruption.py` kills it while copying, while writing the registry, before cleanup and mid-archive, and checks that the next start finishes the job with no ride, plan or credential file lost. A half-written copy is replaced from the source, which is still present until its move completes.

Take a backup before upgrading real data (`python -m backup create`, see `docs/DATA.md`). Restoring a backup made by a newer data format is refused, so rolling back never silently rewrites newer data.

---

## Rolling back

Run the older AppImage, or the older Docker image tag. Data still works because schema changes are additive: new columns are ignored by older code, unknown JSON fields are skipped.
