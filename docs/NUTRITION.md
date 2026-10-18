# Nutrition: SparkyFitness integration (#112)

Shepherd does not track food. The rider logs food and water in a self-hosted
[SparkyFitness](https://codewithcj.github.io/SparkyFitness/) server (its phone app scans barcodes), and
Shepherd reads the daily totals from that server's API into one small table, `nutrition_daily`. The
Fueling screen (`#/fueling`) reads only that table, plus the plan and the rider's weight.

## What was verified, and against what

Read from the SparkyFitness source, not from a running server:

- Repository: `CodeWithCJ/SparkyFitness`, commit `5364674f53d6ac7a7a3403f06dcaf98473699438`
  (2026-10-16, "Merge pull request #2944 from Jerrys-modz/feat/custom-nutrients").
- Nothing was run against a live SparkyFitness instance. Status codes and shapes below come from the
  route handlers and SQL in that commit. The OpenAPI page a running server serves at `/api/api-docs/json`
  was not seen.

### Base address

The Docker deployment publishes the frontend (nginx, default port 3004). Its `docker/nginx.conf`
proxies `location ^~ /api/` to the backend with the path unchanged, and the backend mounts every
router under `/api` (`SparkyFitnessServer/SparkyFitnessServer.ts`). So the address the rider enters is
the one they open SparkyFitness at, for example `http://192.168.1.20:3004`, and Shepherd calls
`<address>/api/...`.

### Authentication

- `SparkyFitnessServer/middleware/authMiddleware.ts` (`authenticate`) runs on every route except a short
  public list (`/api/health`, `/api/version`, ...). It accepts a Better Auth session cookie, an
  `x-api-key: <key>` header, or `Authorization: Bearer <key>`.
- `SparkyFitnessServer/utils/bearerAuthBridge.ts`: a Bearer token of 64 or more characters with no dots is
  moved to the `x-api-key` header. Shepherd sends `x-api-key` directly.
- `SparkyFitnessServer/auth.ts`: Better Auth `apiKey` plugin, `enableSessionForAPIKeys: true`, rate limit
  100 requests per 60 s per key by default (`SPARKY_FITNESS_API_KEY_RATELIMIT_*`). A sync makes 2 requests.
- Keys are created in SparkyFitness under Settings, API keys (`/api/identity/user/generate-api-key`).
  A key can be read-only (`utils/apiKeyScope.ts`: read-only keys may make GET requests). Shepherd only
  makes GET requests, so a read-only key is enough and is what the Settings card asks for.
- Errors from `authenticate`: 401 `{"error": "Authentication required."}` for a missing or wrong key,
  401 for an expired key, 403 for a disabled key, 429 for the rate limit (with `Retry-After`).

### Route 1: food totals per day

`GET /api/reports/mini-nutrition-trends?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`

- Handler: `SparkyFitnessServer/routes/reportRoutes.ts` (`router.get('/mini-nutrition-trends', authenticate, ...)`,
  mounted at `/api/reports`). Without `userId` it reads the caller's own data. Missing dates: 400.
- Service: `services/reportService.ts` `getMiniNutritionTrends`; SQL: `models/reportRepository.ts`
  `getMiniNutritionTrends` (food entries plus meal entries, `GROUP BY entry_date ORDER BY entry_date`).
- The SparkyFitness phone app calls the same route (`SparkyFitnessMobile/src/services/api/reportsApi.ts`).
- Response: a JSON array, one object per day that has entries (days with nothing logged are absent):

```json
[{"date": "2026-10-17", "calories": 2450.5, "protein": 120.2, "carbs": 310.0, "fat": 80.4,
  "saturated_fat": 20.1, "sodium": 2100, "dietary_fiber": 30, "sugars": 90, "caffeine_mg": 95,
  "alcohol_g": 0, "...": "more micronutrients and the rider's custom nutrients"}]
```

  `calories` is kcal (the stored unit; kJ is a display preference), `protein`, `carbs`, `fat` are grams.
  Shepherd reads only `date`, `calories`, `carbs`, `protein`, `fat`.

### Route 2: water per day

`GET /api/v2/reports/hydration-nutrition-range?start=YYYY-MM-DD&end=YYYY-MM-DD`

- Handler: `SparkyFitnessServer/routes/v2/reportRoutes.ts` (mounted at `/api/v2/reports`), range at most 366
  days, start not after end, else 400. Service: `services/hydrationNutritionRangeService.ts`.
- Response schema: `shared/src/schemas/api/HydrationNutritionRange.api.zod.ts`:

```json
{"days": [{"date": "2026-10-17", "water_ml": 2500, "caffeine_mg": 95, "alcohol_g": 0}]}
```

  One row per day in the range, zero-padded. Shepherd reads `date` and `water_ml`. This route is newer
  than route 1; if a server answers 404, Shepherd keeps the food totals and leaves water empty.

## What Shepherd stores

- Connection: `<profile>/nutrition_sparkyfitness.json`, mode 0600, written atomically. The API key is
  never returned by Shepherd's API (only `has_key`), never logged, and left out of backups that exclude
  secrets (the same list as `llm.json`). It is sent only to the saved address, and redirects are not
  followed, so it cannot be forwarded to another host. Changing the address requires entering the key again.
- Data: table `nutrition_daily(date, source, kcal, carbs_g, protein_g, fat_g, water_ml, synced_at)`,
  primary key `(date, source)`, created on first use by `src/routes_nutrition.py` (no change to `db.py`).
  `source` is `sparkyfitness`. A sync replaces that source's rows for the synced dates, so an entry deleted
  in SparkyFitness disappears here at the next sync.

## When it syncs

On demand only: the "Sync now" buttons in Settings and on the Fueling screen (last 30 days). There is no
background sync: the existing after-sync hook (`db.post_sync_callback`) is registered in `src/app.py`,
which this change does not edit. Adding it there later is one line calling `routes_nutrition.sync_now()`.

## Code

- `src/nutrition_sparkyfitness.py`: settings, URL check, `check_connection`, `fetch_daily_totals`.
- `src/routes_nutrition.py`: the table, `/api/nutrition/*` and `/api/fueling`.
- `src/fueling.py`: the guidance rules (pure). Science and citations: docs/SCIENCE.md section 1d.

A second tracker would be one more adapter file returning the same records with another `source`, and
its settings card.
