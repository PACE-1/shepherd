# Data directory, migrations, backup and restore

This describes what the app stores, who owns each migration, and how to back up
and restore it. It extends the migration code that already exists; it does not
replace it.

## Where data lives

`SHEPHERD_HOME` if set (the Docker image uses `/data`), else `~/.shepherd`.

| Path | Contents | Owner |
|---|---|---|
| `profiles.json` | Profile registry, active profile, picker preference | `profile_manager` |
| `profiles/<id>/athlete.json` | FTP, weight, HR numbers, preferences | `profile_manager` |
| `profiles/<id>/.env` | intervals.icu credentials, mode 0600 | `profile_manager` |
| `profiles/<id>/health_tracker.db` | SQLite (WAL): wellness, activities, daily log | `db` |
| `profiles/<id>/plans/` | `current_plan.json` plus a rotating `.bak` chain | `training_planner` |
| `profiles/<id>/rides/`, `rides/icu/`, `wellness/` | Imported FIT files, intervals.icu envelopes, load sidecars | `ride_storage` |
| `profiles/<id>/garmin/` | Garmin Connect sign-in tokens (`garmin_tokens.json`, 0600 in a 0700 folder; never the password) and sync state | `garmin` |
| `profiles/<id>/generated_workouts/` | Planner-synthesised workouts | `workout_gen` |
| `.data_format` | Data-layout version (see below) | `backup` |
| `logs/`, `cache/`, `update_check_cache.json` | Rebuildable; not backed up | various |

## Versions: product, data format, schema

- **Product version** (`VERSION`) names a release. The fork's numbering is
  independent of upstream's and must not be used to detect a downgrade.
- **`DATA_FORMAT`** (`src/backup.py`, currently `1`) is the version of the data
  layout. It is stamped in `.data_format`. At startup the app refuses to run
  against data stamped with a higher number than it understands, so an older
  build can never silently modify newer data. Raise it only with a migration.
- **SQLite schema** has no version number: `db.init_db()` adds tables and
  columns idempotently (`CREATE TABLE IF NOT EXISTS`, guarded `ALTER`).
- **Profile layout** migrations are in `migrate_profiles.py`: the legacy
  single-user layout into `profiles/default/`, and the v4 strip of removed
  trainer fields (marked by the `schema_version_4_migrated` sentinel). Both are
  safe to re-run.

## Upgrades

Supported: any earlier layout that `migrate_profiles` handles (legacy
single-user, v3 profiles, v4) upgrades in place at startup. Migrations are
idempotent and write through atomic file replacement, so an interrupted start is
retried on the next start. Credentials, rider edits and imported rides are
carried, never regenerated.

**Rollback:** an older build refuses data stamped with a newer `DATA_FORMAT`.
To go back, restore a backup taken before the upgrade.

## Backup and restore

```sh
python -m backup create  backup.tar.gz [--home DIR]   # DIR defaults to SHEPHERD_HOME / ~/.shepherd
python -m backup verify  backup.tar.gz
python -m backup restore backup.tar.gz [--home DIR] [--force]
```

- SQLite databases are copied with the engine's own snapshot, so committed WAL
  content is included and `-wal`/`-shm` files are not copied.
- Every file has a SHA-256 in the manifest; `restore` verifies all of them before
  touching the target, refuses a backup from a newer data format, and refuses a
  non-empty target without `--force`.
- An existing target is never renamed (a Docker volume is a mount point): its
  entries are moved aside, the restored ones moved in, and the old ones put back
  if anything fails.
- Excluded on purpose: logs, caches, temp files, the update-check cache.
- For a snapshot that is consistent across files, stop the app first. A running
  app gives per-file and per-database consistency, not a global one.

### From Settings

Settings > Your data downloads the activities, wellness and check-in tables as CSV
and a full backup (`/api/export/backup`). The download omits each profile's `.env`
and `llm.json` (intervals.icu and AI keys) because the server may be reachable by
others; the manifest records `secrets_excluded`. Restoring stays a stop-the-app
command (`python -m backup restore`), since replacing files under a running
database is not safe.

### Docker

```sh
docker stop <container>
docker run --rm -v shepherd-data:/data -v "$PWD":/out <image> python -m backup create /out/backup.tar.gz --home /data
# restore into a clean volume
docker run --rm -v new-volume:/data -v "$PWD":/out <image> python -m backup restore /out/backup.tar.gz --home /data
```

`tools/verify_docker_restore.sh` runs this end to end: it seeds a profile in one
volume, backs it up, restores into a clean volume, starts a server on it and
compares what the API returns.

### Linux desktop

The same commands against `~/.shepherd`; `tests/test_backup_restore.py`
exercises create, verify and restore through the CLI into a fresh directory.

## If intervals.icu stops serving Garmin data (#31)

Rides and wellness reach Shepherd through intervals.icu. If that source dries up,
these rules keep what is already stored:

- **Wellness:** a field the sync returns empty never replaces a stored value
  (`ride_storage.persist_wellness`).
- **Rides:** a ride intervals.icu stops listing is moved to
  `<profile>/rides/icu/_pruned/` instead of being deleted. It disappears from the
  calendar (that is how a deleted duplicate upload is cleaned up) but the file
  stays and can be copied back. A pass that would prune more than 20 rides
  refuses and prunes none.
- **Withheld rides count:** an activity intervals.icu lists with a sport and a
  length but nothing computed from the recording (no load, intensity, power or
  heart rate) marks the planned session done when it covers the planned length
  (`app._rematch_week`). A stub with no sport or length still counts for nothing.
- **Telling affected riders:** after a sync, one in-app notice per episode
  (`notifications.check_sync_health`) when, in the last 14 days, intervals.icu
  listed at least two activities without their data, or rides imported on at
  least two days have nothing on intervals.icu. Riders who have not ridden have
  neither and are never told. The sync-failure switch turns it off.
- **Folder import:** Settings > Folder import takes one folder per profile and
  imports new `.fit` files through the FIT upload code (`folder_import.py`):
  regular files only, subfolders only when asked, symlinks never followed, at
  most 200 new files per scan, files never changed or deleted. A file is a
  duplicate when a stored ride started within 60 s of it and is within 5 % of
  its length. Scans run on "Scan now" and after each background sync. In
  Docker the folder must be inside a mounted volume.
- **Not verified:** none of this has run against a real intervals.icu block; the
  shape of a withheld Garmin activity is assumed, not observed.

## Garmin Connect (direct)

Connect Garmin in Settings → Garmin Connect (email, password, and the MFA code
when Garmin asks). Garmin is then the source of health data and activity files;
intervals.icu stays the source of fitness numbers and the planning calendar.

- **Health:** each sync (hourly, and on "Sync Garmin now") reads sleep time and
  score, overnight HRV, resting HR, body battery, stress, steps and the morning
  training readiness score for each day (30 days the first time, then the last 3).
  Sleep, HRV and resting HR are written to the day's `wellness/<date>.json` and the
  SQLite `wellness` row, and Garmin's value wins: every intervals.icu wellness
  fetch has Garmin's stored values laid over it (`garmin.overlay_health`). The rest
  is kept under the day's `garmin` key.
- **Activities:** cycling, running, swimming and multisport activities are
  downloaded as their original FIT to `rides/garmin-<activity id>.fit` and go
  through the same checks as an uploaded FIT. A ride intervals.icu also has is
  listed once (the intervals.icu copy). "Send new Garmin activities to
  intervals.icu" relays each new file there, skipping rides it already has; leave
  it off while intervals.icu still receives them from Garmin.
- **Unofficial:** this uses `python-garminconnect`, which talks to the service
  Garmin's own app uses. Garmin can change it without notice; when the saved
  sign-in stops working, Settings asks you to sign in again. Disconnecting removes
  the tokens and keeps the synced data.
