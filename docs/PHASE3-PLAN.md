# Phase 3 — Build Plan

Converting the wiki KG into ontology-grounded triples, one `opla:isNativeTo` module at a
time. Every one of the 53 KEEP properties and 36 KEEP classes is assigned to a module below.

**Status:** 5 of 20 modules · CV individuals ✅ · AgeRecord 🔧 277,194 · TemporalExtent 🔧
400,895 extents (points + spans, **D8** split) · **Place ✅ 9,435 + 1,337 Coordinates** (7 source-data exceptions) ·
ExternalReference 🔧 written, not yet run — see GAPS-REPORT.md · Description 🔧 written, not yet run (~271,421 nodes expected).

⚠️ **OPEN ONTOLOGY DECISION — `:Event hasExternalReference` min 1.** The source supplies this
relation for **zero** Events (`edt:P21` sits only on ~850 dataset-level items). This is not
an extraction gap that more work can close: the ontology asserts a relation its own data
does not carry. Resolution deferred; most likely the restriction is relaxed to min 0, since
the materialised graph has no such relation. **Event is therefore NOT blocked** — build it
and expect the restriction to fail. See D11/D14 in `external_reference.py`.

---

## 1. Conventions (apply to every module)

- **One Python file per module** in `src/phase3/`, self-running against Fuseki, writing
  `<module>.ttl`. Same skeleton as `age_record.py`.
- **Subject IRIs are preserved.** Re-type and re-label; never re-mint an existing entity.
- **Minted IRIs are deterministic** — a pure function of their source, e.g.
  `<event>-extent`. Never blank nodes or UUIDs (re-runs would duplicate).
- **Labels inline** — every module emits `rdfs:label` / `skos:altLabel` /
  `schema:description` (`OPTIONAL`, `@en`) for the entities it creates. A module labels
  exactly what it emits.
- **Test small, then full** — `--test` flag restricting to one known entity, eyeball the
  triples, then run whole.
- **Never fabricate values.** Synthesise containers (record nodes), never the data inside.

---

## 2. Step 0 — Diagnostics to run FIRST

The plan branches on one empirical question, so answer it before writing modules.

**Q1. Does the wiki have record *items*, or flat values?**
For Age it has record items (`Q424` instances → our 123 `:AgeRecord`s). For Sex,
Occupation, PersonStatus, Race the mapping points at `:hasSexRecord` / `:hasOccupationRecord`
/ `:hasPersonStatusRecord` / `:hasRaceRecord` — but if `P31 hasSex` points straight at a
*Sex value* rather than a record item, those records must be **minted**.

```sparql
# For each: does the target carry `instance of`, and what is it?
SELECT ?p ?targetType (COUNT(*) AS ?n) WHERE {
  VALUES ?p { edt:P31 edt:P22 edt:P33 edt:P32 }
  ?s ?p ?target . OPTIONAL { ?target edt:P1 ?targetType }
} GROUP BY ?p ?targetType ORDER BY ?p DESC(?n)
```
- target is a **record item** → simple rename.
- target is a **CV value** (already typed by `cv_individuals`) → **mint the record node**.

**Q2. Are facts reified?** If `ep:Pxx → eds:…` statement nodes exist and carry qualifiers,
re-type those statement nodes as the record class instead of minting (cheaper, truer, and
preserves qualifiers).

**Q3. Baseline counts** — instance-count per KEEP class, to check each module's output against.

---

## 3. Known issues to fix before/while building

| # | Issue | Impact | Action |
|---|---|---|---|
| 1 | `P28 date` → **`:startsat`** (lowercase) | invalid predicate; SHACL fails | fix to `:startsAt` |
| 2 | `P32 hasRaceorColor` is **datatype** → `:hasRaceRecord` (object) | type mismatch | mint `:RaceRecord` from the string |
| 3 | `P12 hasLink` **datatype** → `:hasValue` (object property) | type mismatch | re-map (likely `:hasReferenceURI`) |
| 4 | `P21 hasExternalReference` datatype → `:ExternalReference` node | mismatch | synthesise node + `:withID` |
| 5 | `P66 hasDescription` datatype → `:Description` node | mismatch | synthesise node + `:asText` |
| 6 | `P59 hasCoordinates` datatype → `:Coordinates` node | mismatch | synthesise + `:hasLatitude`/`:hasLongitude` |
| 7 | `P24 hasDescriptiveRole` → `:hasDescriptiveEthnonym` | semantically wrong (role ≠ ethnonym) | re-map or DROP |
| 8 | **8 properties collapse onto `:hasInterAgentRelationshipType`** — `P37 hasSpouse`, `P38 hasChild`, `P41 hasEnslavedPerson`, `P43 hasParent`, `P44 hasSibling`, `P48 hasOwner`, `P67 hasGodparent`, `P68 hasGodChild` | **lossy** — which relationship it is disappears | mint one `:InterAgentRelationshipRecord` per fact, with the *type* as the distinguishing value |

Issue 8 is the most consequential: as mapped, "X is spouse of Y" and "X owns Y" become the
same triple. The fix is the record pattern —
`:Person --hasInterAgentRelationshipRecord--> :InterAgentRelationshipRecord
        --hasInterAgentRelationshipType--> (spouse|owner|…)  --isRelationshipTo--> :Person`.

---

## 4. Build order & per-module spec

Dependency-driven. Each row lists the wiki properties it consumes and the moves it needs.

### Tier 1 — Foundations

**1. TemporalExtent** 🔧 — `src/phase3/temporal_extent.py` + `src/phase3/queries/temporal_diagnostics.rq`
  · props: `P28` → `:contains` (point) or `:startsAt` (interval), `P63` → `:endsAt`.
    **`P52`/`P69` are declared in `chunk_0` but have ZERO instances** — two coverage gaps,
    not bugs.
  · **D8 — SYNTHESIS, split by shape of time.** Mint `<subject>-extent`. A subject with
    `P28` only → `:TemporalExtent` with `:contains` (a point); a subject with **both** `P28`
    and `P63` → `:TimeSpan` with `:startsAt`/`:endsAt` (a bounded interval). The `FILTER NOT
    EXISTS { P63 }` in the point query is the complement of the interval query's required
    end, so the two partition the dated subjects — each gets exactly one extent, none is
    minted twice. A node becomes a `:TimeSpan` only when both bounds are present, so
    `:TimeSpan`'s `someValuesFrom` on `:startsAt` **and** `:endsAt` holds by construction.
    (Supersedes the earlier all-`:TimeSpan` mint that forced a lone date into `:startsAt`.)
  · **D5 — raw literals; precision deferred.** Dates are emitted **exactly as the wiki
    stores them** — no cast, no widening. Be aware what that carries: Wikibase serialises
    every date as a full dateTime and keeps the real precision on the value node
    (`epsv:P28` → `wikibase:timePrecision`), and 9/10/11 all occur here. So a `:contains`
    of `1801-01-01T00:00:00Z` may mean only "sometime in 1801" — the `-01-01` is padding.
    Nothing is lost (precision stays recoverable from the wiki graph), but any consumer
    reading these as exact days will be wrong. Widening belongs in a derivation pass over
    this module's output, not in extraction. Diagnostic 2 sizes the affected share.
  · **D6 — one accepted SHACL gap.** `:contains`/`:startsAt`/`:endsAt` are `allValuesFrom
    xsd:date` while these literals are `xsd:dateTime` — a range mismatch, deliberate under
    D5. Diagnostic 7 is **expected to return rows** (it measures the gap rather than
    failing); a one-line `xsd:date(...)` cast fixes it whenever D5 is revisited. The old
    "missing end" gap is **closed** by D8 — diagnostic 5 is now a regression check expecting 0.
  · **D7 — minted IRIs.** `<subject>-extent` (neutral suffix — the node may be either class),
    a pure function of the source ⇒ idempotent.
  · Query B propagates each AgeRecord's extent from its `recordedAt` Event rather than
    minting 277k copies — closes the gap `age_record.py` left open. Same shape reused by
    every later reified record module (P33, P31, P22).
  · Deliberately **not** type-guarded on `edt:P1 ed:Q238` — diagnostic 1 shows what carries
    P28 before you accept the output.

**2. EntityWithProvenance** — cross-cutting, one query for all entities
  · classes `:LicenseInformation` `:ProvenanceActivity` `:DocumentTypes`
  · props: `P15`→`:hasLicenseInformation`, `P16`→`:generatedBy`, `P6`→`:isDirectlyBasedOn`,
    `P23`→`:hasOriginalSourceType`, `P25`→`:reportsOn`, `P26`→`:availableFrom`
  · pure renames — no synthesis.

**3. AgeRecord** 🔧 — **rebuilt via-reification**, 277,194 records (the `ep:P42` statement
  nodes, not the 123 shared `Q424` items). Owning-agent link `:hasAgeRecord` ✅, qualifier
  `pq:P18`→`:recordedAt` ✅, `prov:wasDerivedFrom`→`:isDirectlyBasedOn` ✅.
  Outstanding: `:hasTemporalExtent` from module 1, keyed on the **statement IRIs**.
  · **Precedent for every other reified module** (`P33` 439k, `P31` 432k, `P22` 131k — all
    qualifier-rich per q2_reification.csv): where the wiki reifies and the target is a
    shared value, the statement node is the record. Answers Q1/Q2 together.

**3b. ExternalReference** 🔧 — `src/phase3/external_reference.py` + diagnostics. **`edt:P21` only.**
  · **The mapping is wrong about the shape.** `P21` is typed `wikibase:Url`, so its values are
    IRIs not ID strings. It appears on **zero Events** — only on `Q67` provenance (843) and
    `Q172` ResearchProject (5) items, ~850 total. `P12 hasLink` has no instance data at all
    (3 schema lines). Expected yield: ~850 reference nodes, and that is the whole truth of
    what this source calls an external reference.
  · **D11 — the `skos:altLabel` inference was considered and REJECTED.** Every Event and Place
    carries a coded string (`LSD-EVE-BIR-076248`, `SV-PLA-31312`); 117,437 sampled values are
    100% conforming across two prefixes. Reading them as `:withID` would have satisfied
    Event's min-1 for all 429,173 Events. Declined: `skos:altLabel` is a **label** property,
    and treating it as an external identifier is our interpretation, not the source's.
    Minting 400k+ nodes from an inference to satisfy a cardinality constraint makes the graph
    look compliant while hiding that the source has no such relation. **A visible gap beats an
    invented edge.** Evidence is preserved in the module docstring; the query is in git
    history if the inference is ever explicitly adopted as an enrichment pass.
  · `P36` Geonames ID (64.5% of Places) likewise left in the DROP bucket. Unlike altLabel it
    IS an unambiguous identifier with a real referent, so it is the strongest candidate if
    this module is ever widened — but it is a Place concern and blocks nothing.
  · **D13 — minted IRIs**: `<entity>-extref-<md5(url)>`, one node **per URL**, because
    entities carry several (`ed:Q462` has 3) and a shared node would break `refersTo max 1`.
    The URL itself is typed `:ExternalReferent` — it is already a global identifier, so
    interposing a stand-in node would add indirection without information. No `:withID`, no
    labels: the source has neither.
  · **D14 — Event's min-1 is an ontology problem.** See the status note at the top of this
    file. Diagnostic 6 measures the gap (expect 0 / 429,173); diagnostic 6b sizes the
    rejected altLabel option **as a measurement only**, should it ever be reconsidered.

### Tier 2 — Core entities

**4. AgentRole / Agent** — `:Person` `:Organization` (`Q410`, `Q411`) + `:hasAgentRecord`
  · plus the record-link props: `P42`→`:hasAgeRecord`, `P31`→`:hasSexRecord`,
    `P22`→`:hasOccupationRecord`, `P33`→`:hasPersonStatusRecord`, `P32`→`:hasRaceRecord`
  · every record needs exactly one owning Agent — this module supplies it.

**5. Place** 🔧 — `src/phase3/place.py` + `src/phase3/queries/place_diagnostics.rq`
  · **D8 — scope.** All four wiki classes → `:Place`: `Q301` (9,331), `Q303403` Place Name
    (101), `Q280159` (2), `Q233` Region (1) = **9,435 expected**. Q233 could have gone to
    `:PlaceCV` alongside Q436/Q437; kept as `:Place` so everything is answerable to Event's
    `atPlace`. Diagnostic 1b eyeballs the 101 Place Name items before you accept them.
  · props: `P20`→`:hasName` (**100%** in sample, so cardinality 1 is satisfiable),
    `P8`→`:hasPlaceTypeCV` (100%), `P7`→`:isSpatiallyLocatedIn` (97.9%, multi-valued),
    `P74`→`:hasBroader` (13.6%), `P71`→`:hasAlternateName` (0.8%). `P9`/`P36` dropped per
    mapping — note `P36` Geonames ID is a real external reference, revisit at that module.
  · **D9 — coordinates from the value node, not the WKT.** The direct claim is
    `"Point(-82.36417 23.13194)"^^geo:wktLiteral` and **WKT is longitude-first** — read it
    as lat/long and Havana lands in the Indian Ocean. Since the ontology demands two
    separate cardinality-1 `xsd:double` properties, "keep it raw" isn't available the way it
    was for dates. So the module reads `epsv:P59` → `wikibase:geoLatitude`/`geoLongitude`,
    already correctly labelled and typed. Diagnostic 6b checks Havana specifically, because
    a transposed pair is still *in range* and the range check alone cannot catch it.
  · **D10 — the Coordinates node attaches twice**: `:hasCoordinates` (what the mapping says,
    but `:Place` declares no restriction on it) **and** `:hasSpatialExtent` (what `:Place`
    actually constrains, max 1 onClass `:SpatialExtent`). Consistent, since
    `:Coordinates ⊑ :SpatialExtent`.
  · Only ~50.8% of Places carry coordinates — `:Coordinates` count should land near half.
  · Unblocks Event (`atPlace someValuesFrom :Place`).

**6. Event** — `:Event` (`Q238`) `:EventTypes` — ✅ **BUILT (2026-08-10)** `event.py` → `event.ttl`
  · props: `P30`→`:hasEventType` (card 1), `P27`→`:atPlace`, `P20`→`:hasName`,
    `P29`→`:providesParticipantRole`
  · needs a temporal extent (card 1 — a `:TimeSpan` or `:TemporalExtent`, D8) +
    `:ExternalReference` (min 1) + `:eventSelfProperty`.
  · **Built:** 468,855 Events (E1 baseline — the earlier ~429,173 was an estimate; 0 deprecated).
    All props read from DIRECT `edt:` claims (E5 ≈ E5b; ~100% direct). Type + 3 renames +
    reflexive `:eventSelfProperty` + `rdfs:label`. Nothing minted. Emitted counts:
    `:hasEventType` 468,852 · `:hasName` 468,852 · `:atPlace` 368,521 events · self-edge 468,855.
    Gaps (all documented, not patched): 3 events lack `P30`/`P20`; 100,334 lack `P27`
    (`atPlace someValuesFrom` gap); `hasExternalReference` min-1 = 0 (decision A). See GAPS §7.
    Temporal extent + `providesParticipantRole` supplied by `temporal_extent.py` /
    `participant_role.py --events-only` run over these Event IRIs.

**7. ParticipantRoleRecord** — `:ParticipantRoleRecord` `:ParticipantRoleTypes`
  · props: `P17`→`:hasParticipantRoleType`, `P19`→`:roleProvidedBy`
  · the n-ary hub: Event → RoleRecord → Agent, with a role type.

### Tier 3 — Record modules (each inherits AgentRecord's constraints)

| Module | Wiki props | Notes |
|---|---|---|
| **SexRecord** | `P31` | mint record if target is a value (Q1) |
| **NameRecord** | `P72`→`:hasSurnameAsString`, `P73`→`:hasFirstNameAsString` | + `:NameVariant`, `:fullNameAsString` |
| **OccupationRecord** | `P22`, `P78`→`:hasDescriptiveOccupation` | mint if needed |
| **OriginRecord** | `P47`→`:refersToPlaceOfOrigin`, `P46`/`P77`/`P80`→`:hasDescriptiveEthnonym` | + `:hasECVO` |
| **PersonStatusRecord** | `P33`, `P34`→`:hasStatusGeneratedEvent` | `hasValue` card 1 → `:PSCategories` |
| **RaceRecord** | `P32` | issue 2 — mint from string |
| **PersonRecord** | — | abstract-ish; may only be inferred |
| **InterAgentRelationshipRecord** | `P37 P38 P39 P40 P41 P43 P44 P48 P67 P68` | issue 8 — the big one |

### Tier 4 — Supporting

**Description** 🔧 — `src/phase3/description.py` + `src/phase3/queries/description_diagnostics.rq`,
written, not yet run. **`P66` only, SYNTHESIS (issue 5).** Wiki gives a flat `xsd:string`;
mint `<entity>-desc-<md5(text)>` → `:Description` with `:asText`, linked by
`:hasDescriptionText`. Expected ~271,421 nodes over ~271,418 entities (Q238 Event 188,101 ·
Q410 Person 81,508 · Q301 Place 1,732 · Q172 ResearchProject 40 · Q411 Org 20 · ~16
dataset-level Q67/Q359 off the four native domains, kept not dropped — D2). md5-per-text
(D1) keeps `:asText qualifiedCardinality 1` even for the 3 entities carrying two
descriptions. Provenance facet of `:Description ⊑ :EntityWithProvenance` left to that module.
· ~~ExternalReference~~ **→ promoted ahead of Event, built as
`external_reference.py`; see D11–D13 below** ·
**Match** (`P35`→`:hasMatchType`, `P79`→`:matches`) · **ResearchProject** (`Q172`)

---

## 5. Per-module workflow

1. Read the ontology class block — note every restriction and cardinality.
2. Identify the moves: type · rename · de-reify · synthesise.
3. Write `src/phase3/<module>.py` from the standard skeleton.
4. Run with `--test` on one known entity; eyeball against the ontology pattern.
5. Run full; compare count to the Step-0 baseline for that class.
6. Record the count in this file.

## 6. Verification (per module and phase-wide)

- **Count check** — output instances == wiki instance-count for the source class.
- **Cardinality spot-check** — e.g. every `:Event` has exactly one `:hasEventType`.
- **Dangling-reference check** — every object of an emitted property is itself typed
  somewhere (catches "property kept, value class dropped").
- **Phase-wide** — union all module TTLs, then confirm every ontology class marked `map`
  in `mappings/coverage-gaps.csv` has ≥1 instance; anything empty is a silently-failed CONSTRUCT.

## 7. Deliverables

- `src/phase3/*.py` — one runnable module each
- `out/phase3/*.ttl` — the materialised fragments (Phase 4 merges them)
- counts recorded here per module
