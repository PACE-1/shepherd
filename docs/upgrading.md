# Updating Shepherd

## TL;DR

Replace the AppImage with the new one, or pull the new Docker image and recreate the container on the same data volume. Everything in your data folder (`~/.shepherd/`, or `/data` in Docker) is left alone — rides, current and archived plans, FTP history, wellness logs, ICU credentials, and athlete profile all survive every install. Only the application itself (code, ZWO library, web UI) is replaced.

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
| Rides archive | `profiles/<id>/rides/*.fit` | imported FIT files (per profile) |
| ICU per-ride summaries | `profiles/<id>/rides/icu/*.json` | pulled from intervals.icu |
| Wellness logs | `profiles/<id>/wellness/YYYY-MM-DD.json` | HRV, RHR, sleep records |
| Path overrides | `profiles/<id>/user_paths.json` | optional workout folder |
| Data format stamp | `.data_format` | layout version; an older build refuses newer data |
| Boot logs | `logs/*.log` | rotated logs |

---

## What gets replaced

The AppImage file, or the Docker image. That holds the Python code, the bundled ZWO library and the web UI. Replaced wholesale. macOS and Windows builds are retired.

---

## First boot after upgrade

On first launch after a version bump you'll see a one-off toast naming the from→to versions and confirming all rider data is preserved. Fires once per transition (per-version localStorage flag). The previous-run version is recorded at `~/.shepherd/last_run_version.txt`.

---

## What if something looks wrong?

- Check `~/.shepherd/last_run_version.txt` — it should match the version in Settings.
- The only automatic delete path is the legacy-layout migration in `migrate_profiles.py` (`migrate_archives_to_profiles` and the move into `profiles/default/`), which removes originals only after the copy verifies. It does nothing on installs already on the profile layout.
- Nothing else deletes user data automatically. Profile deletion is user-initiated only.
- Missing ride or plan? Files are plain `.fit` / `.json` under `~/.shepherd/profiles/<id>/rides/` and `~/.shepherd/profiles/<id>/plans/`.

---

## If an upgrade is interrupted

The legacy-to-profiles migration copies files into `profiles/default/`, writes `profiles.json` last, and deletes the originals only after the registry reads back correctly. `tests/test_migration_interruption.py` kills it while copying, while writing the registry, before cleanup and mid-archive, and checks that the next start finishes the job with no ride, plan or credential file lost. A half-written copy is replaced from the source, which is still present until its move completes.

Take a backup before upgrading real data (`python -m backup create`, see `docs/DATA.md`). Restoring a backup made by a newer data format is refused, so rolling back never silently rewrites newer data.

---

## Rolling back

Run the older AppImage, or the older Docker image tag, only if the release you left did not raise `DATA_FORMAT` (see `docs/DATA.md`, "Versions"): an older build refuses data stamped with a newer format, and then the way back is to restore the backup you took before upgrading. Within one data format, schema changes are additive: new columns are ignored by older code and unknown JSON fields are skipped. Docker steps are in `docs/SERVER.md`.
