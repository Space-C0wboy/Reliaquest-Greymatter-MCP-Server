# GreyMatter API — Server-Side Issues (for ReliaQuest)

Issues observed via the GreyMatter Self-Service GraphQL API
(`https://greymatter.myreliaquest.com/graphql`) during live testing. These appear to
be server-side resolver/serialization problems, not client errors — the same documents
work when the offending field is removed from the selection set. Reproduce with any
valid `X-API-KEY`.

Reported to: greymattersupport@reliaquest.com
Status: **Open** (update as ReliaQuest responds)

---

## 1. `cases` — resolver error on `discoverExposure` (HTTP 200 with `errors`)

Selecting `cases { edges { node { discoverExposure { ... } } } }` returns:

```
"message": "An unexpected error has occurred."
"path": ["cases", "edges", 0, "node", "discoverExposure"]
```

- Reproduces with the outer list bounded to a single record (`first3: 1`), so it is not
  load-related.
- Removing the `discoverExposure { … }` selection makes the same query succeed
  (returns the full case list normally).
- **Expected:** for an account not entitled to the Discover/exposure capability, the
  field should resolve to `null`, not raise an error that fails the whole query.
- **Workaround applied in this server:** the field is excluded from the generated query
  (see `FIELD_EXCLUSIONS` in `scripts/generate_from_collection.py`).

## 2. `playbooks` — enum serialization failure on `TechnologyType`

Selecting `playbooks { supportedTechnologies { type } }` returns:

```
"message": "Can't serialize value (/playbooks[36]/supportedTechnologies[3]/type) :
            Invalid input for enum 'TechnologyType'. Unknown value 'MOBILE_DEVICE_MANAGEMENT'."
"path": ["playbooks", 36, "supportedTechnologies", 3, "type"]
```

- The server returns a value (`MOBILE_DEVICE_MANAGEMENT`) that its own `TechnologyType`
  enum does not define, so serialization fails for multiple playbooks.
- Removing the `supportedTechnologies { … }` selection makes the query succeed
  (returns 132 playbooks).
- **Expected:** `MOBILE_DEVICE_MANAGEMENT` should be a valid member of the
  `TechnologyType` enum (schema/data mismatch).
- **Workaround applied in this server:** the field is excluded from the generated query
  (see `FIELD_EXCLUSIONS` in `scripts/generate_from_collection.py`).

## 3. `greymatterFields` and single-item `drpAlert` — generic resolver error

Both can return `"An unexpected error has occurred"` at the root path
(`["greymatterFields"]` / `["drpAlert"]`). Likely entitlement-dependent; noted for
completeness.

---

## Notes (not bugs — documented for our maintainers)

- **Entitlement:** `drpAlerts`, `accessControlPolicies`, `accessControlResources`,
  `discoverTasks`, and `audits` correctly return *"You don't have access to this item"*
  for accounts without the relevant module.
- **Multi-connection pagination:** the `cases` query exposes the top-level page size as
  `first3` (with `first`/`first1`/`first2` for nested connections). Leaving the outer
  bound unset returns very large responses and can time out — set it explicitly.
