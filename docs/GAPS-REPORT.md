# Phase 3 — Gap report: AgeRecord, TemporalExtent, Place, Event

Counts parsed directly from the emitted Turtle against `ontology/enslaved-v2.ttl`.
Re-run `src/phase3/queries/temporal_diagnostics.rq` in Fuseki to confirm.

**Bottom line:** no module has an internal defect. Remaining gaps are (a) source data that
doesn't exist, (b) constraints deferred by decision D5, or (c) constraints owned by modules
not yet built (EntityWithProvenance, Event, AgentRole). None can be closed from inside the
three modules below.

---

## 1. AgeRecord — 277,194 records

| Constraint | Status | Count |
|---|---|---|
| `hasAgeValue` / `hasValue` max 1 | ✅ | 277,194 · 0 multi-valued |
| `isDirectlyBasedOn` max 1 | ✅ | 277,194 |
| `recordedAt` max 1 | ✅ | 277,190 — 4 have none (source gap) |
| inverse `hasAgentRecord` cardinality 1 | ✅ | 0 orphans |
| `hasTemporalExtent` cardinality 1 | ❌ | 99,293 missing — see §3 |
| `agentRecordSelfProperty` (hasSelf) | ❌ | not emitted — trivial, 1 triple/record |
| `hasLicenseInformation` + `availableFrom` | ❌ | inherited, no module yet — §Decisions E |

The link `:hasAgeRecord ⊑ :hasPersonRecord ⊑ :hasAgentRecord` entails correctly, but
`?person` isn't yet typed `:Agent`/`:Person` (AgentRole's job), and `recordedAt`/
`isDirectlyBasedOn` targets stay untyped until Event/EntityWithProvenance run. These are
dangling-type gaps, not AgeRecord defects — don't patch them in `age_record.py`.

---

## 2. TemporalExtent

| Check | Status | Count |
|---|---|---|
| points (`:contains`) + spans (`:startsAt`/`:endsAt`) | ✅ | 429,960 + 8,135 |
| multi-dated subjects collapsing / inverted intervals | ✅ none | 0 |
| end-only subjects (`P63`, no `P28`) | ✅ fixed | 651 recovered (query EO) |
| partition disjoint (no subject minted twice) | ✅ | 438,746 nodes, 0 double-typed |
| `startsAt`/`endsAt`/`contains` as `xsd:date` | ❌ | all `xsd:dateTime` — D5, deferred |
| `TimeSpan someValuesFrom endsAt` | ⚠️ | see §Decisions C |
| `occursBefore` / `occursAfter` | ➖ | no wiki source — accepted |

**End-only fix (2026-08-10).** TE and TS both required `P28`, so a subject with only `P63`
got no extent. Added query **EO**: `P63 & !P28 → :TemporalExtent + :endsAt` (a point, not a
`:TimeSpan` — no start to satisfy `someValuesFrom :startsAt`). TE/TS/EO now partition every
dated subject. Recovered 651 extents, dates overwhelmingly historical (1730–1865).

---

## 3. The 99,293 missing AgeRecord extents — source data, not pipeline

    99,293 = 4 records with no :recordedAt + 99,289 whose recordedAt event has no date

The 99,289 trace to just **1,399 undated events**. Spot-checking the top blockers shows
well-formed events (type, place, name) that genuinely lack `P28` — the date isn't in
Enslaved.org. Options: accept as documented SHACL exceptions; relax cardinality to max 1; or
derive from a dated parent voyage *if* a link exists (`P52`/`P69` are empty). Dating 1,399
events would close all 99,289, so derivation has the best leverage if feasible.

---

## 4. Place — 9,435 instances

| Check | Status | Count |
|---|---|---|
| `:Place` instances | ✅ | 9,435 (exact) |
| `:Coordinates` minted, lat/long present & in range | ✅ | 1,337 · 0 bad |
| Havana fixture — coords not transposed (D9) | ✅ | 23.13N, −82.36E |
| `:hasName` cardinality 1 | ⚠️ | 6 Places carry 2–3 names |
| `:hasPlaceTypeCV` max 1 | ⚠️ | 1 with two, 16 with none |

The value-node route (D9) produced correctly-ordered coordinates; the WKT longitude-first
trap never fired. Coordinate coverage is 14.2%, not the ~50% predicted from `chunk_0` —
that chunk over-represents coordinate-bearing places, so don't extrapolate counts from it.

The 7 constraint violations (0.07%) are all real source data — e.g. `ed:Q970085` merges
three Virginia counties onto one item; `ed:Q487631` is both hospital and prison.
Recommendation: leave them as documented Phase-5 exceptions rather than adding tie-break
logic that would hide a genuine source merge error.

---

## 4b. Event — 468,855 instances (built 2026-08-10)

Counts parsed from `out/phase3/event.ttl`; pre-flight from `src/phase3/queries/event_diagnostics.rq`
(E1–E6). Baseline **468,855** — the plan's earlier ~429,173 was an estimate; E5c confirms 0
deprecated. All properties read from DIRECT `edt:` claims: E5 (direct) ≈ E5b (reified), the
normal Wikibase dual representation, and direct coverage is ~100%, so no reified branch is needed.

| Constraint | Owner | Status | Count |
|---|---|---|---|
| `a :Event` (typed unconditionally) | event.py | ✅ | 468,855 (== E1) |
| `hasEventType` qualifiedCardinality 1 | event.py | ✅ | 468,852 · **0 multi-valued** · 3 with none |
| `hasName` min 1 | event.py | ✅ | 468,852 · 3 with none · 9 multi (allowed) |
| `atPlace` someValuesFrom `:Place` | event.py + Place | ⚠️ | 368,521 have one · **100,334 have none** (source gap) |
| `atPlace` object typed `:Place` | Place | ✅ | Q301/Q280159 · **7 untyped** P27 targets dangle (E6) |
| `eventSelfProperty` hasSelf true | event.py | ✅ | 468,855 (one/event) |
| `hasTemporalExtent` cardinality 1 | temporal_extent.py | ⏳ | run over Event IRIs; ~1,399 undated stay bare |
| `providesParticipantRole` min 1 | participant_role.py | ⏳ | run `--events-only` over Event IRIs |
| `hasExternalReference` min 1 | — | ❌ | **0 of 468,855** — decision A, not patchable here |

Nothing is minted — every subject and object is an existing `ed:` entity, preserved. The three
`P30`/`P20`/`P27`-less events and the 100,334 place-less events are typed anyway: a missing
required property is a Phase-5 SHACL finding, not a reason to drop the event. The `hasExternalReference`
min-1 restriction is satisfied by zero events — the source carries no per-event reference (decision
A); do **not** mint fake reference nodes. Temporal extent and participant-role edges are supplied
by other modules running over these Event IRIs, not by `event.py`.

---

## 5. Open ontology decisions (not pipeline work)

The ontology asserts relations the source doesn't carry; each needs a human call at Phase 5.

| # | Constraint | Source reality | Likely resolution |
|---|---|---|---|
| A | `:Event hasExternalReference` min 1 | 0 of 468,855 events have it (`P21` sits on ~850 dataset items) | relax to min 0 |
| B | `:AgentRecord hasTemporalExtent` card 1 | 99,289 records point at undated events (§3) | relax to max 1 / derive |
| C | `:TimeSpan endsAt` someValuesFrom | 98% of spans have no end (D5 keeps literals raw) | widen by precision / relax |
| D | `:Place hasName` card 1 | 6 Places carry 2–3 names (one a real county merge) | accept as exceptions |
| E | `:EntityWithProvenance` license + `availableFrom` | emitted by no module; 1 license item dump-wide | **build the shared module** |

A is the notable one: the wiki has no per-event external reference, so the restriction
describes intent, not data. Relaxing it is the correct reading, not a workaround.

---

## 6. Ranked actions

| # | Action | Effort | Unblocks |
|---|---|---|---|
| ~~1~~ | ~~Fix `P63`-only miss~~ ✅ done (query EO) | — | correctness |
| 2 | Decide the 99,289 (accept / derive / relax) | decision | AgeRecord → ✅ |
| 3 | Emit `agentRecordSelfProperty` self-loops | tiny | `:reportsOn` inference |
| 4 | Build EntityWithProvenance (license + `availableFrom`) | small | every class, ~1.5M instances |
| 5 | Build AgentRole, then Event | large | closes AgeRecord's dangling-type gaps |
| 6 | Settle §5 decisions before Phase 5 | decisions | ~1M expected SHACL failures |

Actions 3 and 4 are cheap and unblock disproportionately; 2 and 6 are decisions only you can
make.
