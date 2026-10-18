# API contract policy (roadmap #10)

## What is typed

Routes the new UI uses declare a response model in `src/api_models.py` and attach
it with `responses={200: {"model": …}}`. That documents the contract in OpenAPI
and does **not** validate or filter live responses, so a value of an unexpected
type can never turn a working endpoint into a 500.

`tests/api_contract.json` is the OpenAPI snapshot of exactly those routes
(`python tools/dump_openapi.py > tests/api_contract.json`); the TypeScript types
in `web/src/api/schema.d.ts` are generated from it (`tools/gen-api-types.sh`).
`tests/test_api_contract.py` fails when a model changes without the snapshot.
Routes that return a list of a declared model are included.

## Versioning

- The API is not path-versioned. One server serves one UI build, shipped together.
- Within a release line a change must be additive: new optional fields, new routes.
  Every model allows extra keys (`extra="allow"`), so a new server field never
  breaks an older client.
- Removing or retyping a field is a breaking change. It needs a new route or a
  documented transition, and the snapshot diff makes it visible in review.
- A typed model must describe what the server already sends.

## Errors

- Success is `200` with a JSON body. Commands answer `{"ok": true, …}`.
- A refused request is `400` (bad input) or `404` (no plan, no such session).
  Uploads add `411` (no `Content-Length`), `413` (over the size limit) and `504` (parse timeout).
- Error bodies carry one human sentence in both `error` and `detail`: a handler
  for `HTTPException` fills both, and handlers that return `{"error": …}` directly
  are being moved to it. `web/src/lib/api.ts` surfaces that text. The server never returns exception text on a 500; the
  detail is logged instead.
- Some commands answer `200` with `ok: false` and an `action` naming why nothing
  changed (for example `already_easy`). The UI shows that as a plain message.

## Reads and commands

Reads do not write. Work that used to run on a read (plan self-heal, deload
advance, weekly recalc, eFTP auto-apply) runs in the sync loop or after ride sync.
Commands that change the plan hold the plan lock (`plan_write_lock_async`);
see `docs/code-bloat/api-inventory-home-plan.md` for the plan commands.
