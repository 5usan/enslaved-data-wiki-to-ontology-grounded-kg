# Phase 3 Module Map — derived from `opla:isNativeTo`

The Enslaved Ontology annotates every term with `opla:isNativeTo`, which declares the
ontology-design-pattern module it belongs to. That annotation — not our own grouping — is
the authoritative decomposition, and it matches the boxes in `ontology/enslaved_image.png`.

**20 modules.** Status: ✅ done · 🔧 needs backfill · ⬜ todo

---

## Cross-cutting foundations (build first — everything depends on these)

### ⬜ EntityWithProvenance  (14 terms — the largest module)
- classes: `:EntityWithProvenance` `:DocumentTypes` `:LicenseInformation` `:ProvenanceActivity`
- objprops: `:attributedTo` `:generatedBy` `:hasLicenseInformation` `:hasOriginalSourceType`
  `:isDirectlyBasedOn` `:performedBy` `:reportsOn` `:used`
- dataprops: `:availableFrom` `:hasReferenceURI`

Superclass of `:AgentRecord`, `:Place`, `:Event` and (via AgentRecord) ~10 record classes.
Cross-cutting: write **one** provenance module rather than repeating these in every record.
Wiki sources already mapped: `P15`→`:hasLicenseInformation`, `P16`→`:generatedBy`,
`P6`→`:isDirectlyBasedOn`, `P23`→`:hasOriginalSourceType`, `P25`→`:reportsOn`.

### 🔧 TemporalExtent  (8 terms) — `temporal_extent.py` written, not yet run
- classes: `:TemporalExtent` `:TimeSpan`
- objprops: `:fallsWithin`
- dataprops: `:startsAt` `:endsAt` `:contains` `:occursBefore` `:occursAfter`

Its own module, **not** Event-specific. `:AgentRecord` requires `hasTemporalExtent`
cardinality 1, so *every* record class needs this. Requires **synthesis** — the wiki has
flat dates (`P28`, `P63`) but no extent node. Mint one.

Built (**D8 — point/interval split**): mints `<subject>-extent` from `P28`/`P63`. A subject
with **`P28` only** → `:TemporalExtent` with `:contains` (a point in time); a subject with
**both `P28` and `P63`** → `:TimeSpan` with `:startsAt`/`:endsAt` (a bounded interval). The
two branches partition the dated subjects, and a `:TimeSpan` is minted only when both bounds
exist, so `:TimeSpan`'s `someValuesFrom` on both ends is satisfied by construction. Wiki date
literals kept **verbatim** (no cast, no precision widening — see D5): year-precision dates are
padded `-01-01` in the source, so a bound is not always a real day; `wikibase:timePrecision`
on the value node tells you which is which. `:occursBefore` `:occursAfter` have **no wiki
source** — `P52`/`P69` are defined in `chunk_0` with zero instances — so 2 of the 8 terms stay
empty by design. See PHASE3-PLAN §4 module 1 and `src/phase3/queries/temporal_diagnostics.rq`.

### ✅ Controlled vocabularies  (cross-cutting, already built)
`src/phase3/cv_individuals.py` — 979 values typed across 11 vocabulary classes.

### ⬜ AgentRecord  (4 terms) — abstract superclass
- classes: `:Agent` `:AgentRecord`
- objprops: `:hasTemporalExtent` `:recordedAt`

Do **not** type instances `:AgentRecord` directly; it's inferred via `rdfs:subClassOf` from
the 10 concrete record classes. Its constraints are inherited by all of them:
`hasTemporalExtent` **cardinality 1**, inverse-`hasAgentRecord` **cardinality 1** → `:Agent`,
`recordedAt` max 1 → `:Event`, `isDirectlyBasedOn` max 1.

---

## Core entities

### ⬜ Event  (11 terms)
- classes: `:Event` `:EventTypes` `:ParticipantRoleRecord` `:ParticipantRoleTypes`
- objprops: `:atPlace` `:hasEventType` `:providesParticipantRole` `:subeventOf`
  `:eventSelfProperty` `:agentRecordSelfProperty`
- dataprops: `:hasName`

Note `:ParticipantRoleRecord` / `:ParticipantRoleTypes` are native to **Event** — they are
part of this module, not separate. (Their *properties* live in the module below.)

### ⬜ ParticipantRoleRecord  (2 terms)
- objprops: `:hasParticipantRoleType` `:roleProvidedBy`

The n-ary hub tying an Event to an Agent with a role:
`:Event --providesParticipantRole--> :ParticipantRoleRecord --roleProvidedBy--> :Agent`
plus `--hasParticipantRoleType--> :ParticipantRoleTypes`.
Wiki: `P29`, `P19`, `P17` — all KEEP.

### ⬜ AgentRole  (2 terms) — `:Person` `:Organization`
### ⬜ Place  (7 terms)
- classes: `:Place`; objprops: `:asPlaceCV` `:hasCoordinates` `:isSpatiallyLocatedIn`
- dataprops: `:hasAlternateName` `:hasLatitude` `:hasLongitude`

---

## Record modules (all inherit AgentRecord's constraints)

| Module | Terms | Status |
|---|---|---|
| AgeRecord | `:AgeRecord` `:AgeCategory` `:hasValue` `:hasAgeValue` `:recordedAt` `:isDirectlyBasedOn` | 🔧 277,194 built (via-reification), temporal gap only |
| SexRecord | `:SexRecord` `:SexTypes` | ⬜ |
| NameRecord | `:NameRecord` `:NameVariant` `:hasNameVariant` `:hasPreferredNameVariant` `:fullNameAsString` `:hasFirstNameAsString` `:hasSurnameAsString` | ⬜ |
| OccupationRecord | `:OccupationRecord` `:Occupations` | ⬜ |
| OriginRecord | `:OriginRecord` `:ECVO` `:hasECVO` `:refersToPlaceOfOrigin` | ⬜ |
| PersonStatusRecord | `:PersonStatusRecord` `:PSCategories` `:hasStatusGeneratedEvent` `:refersToEvent` | ⬜ |
| RaceRecord | `:RaceRecord` | ⬜ |
| PersonRecord | `:PersonRecord` | ⬜ |
| InterAgentRelationshipRecord | `:InterAgentRelationshipRecord` `:InterAgentRelationshipTypes` `:hasInterAgentRelationshipType` `:isRelationshipFrom` `:isRelationshipTo` | ⬜ |

---

## Supporting modules

- 🔧 **Description** — `:Description` `:asText`. Wiki `P66` is a *string*; ontology wants a
  node → **synthesis**. `description.py` written (not yet run): mints
  `<entity>-desc-<md5(text)>` → `:Description` + `:asText`, linked by `:hasDescriptionText`.
  ~271,421 nodes expected (Event + Person dominant). md5-per-text keeps `:asText` card-1.
- 🔧 **ExternalReference** — `:ExternalReference` `:ExternalReferent` `:refersTo` `:withID`.
  Wiki `P21` is a URL hung on an entity; ontology wants a reference node → **synthesis**.
  `external_reference.py` mints `<entity>-extref-<md5(url)>` → `:ExternalReference` + `:withID`
  carrying the URL as an `xsd:string` (`STR(?url)` — the `:withID` branch of the union). **1079
  nodes over 150 distinct `:withID` strings** on Q67/Q172 dataset-level entities (0 events carry
  P21). No `:ExternalReferent` / `:refersTo` minted. **NODES ONLY (2026-08-24):** emits the
  reference nodes but NOT `:hasExternalReference` — that link is native to
  Agent/Event/ResearchProject and is re-homed to the owning module, which re-derives the same
  md5 IRI (mirrors Description / TemporalExtent). md5-per-URL keeps `:withID` card-1 (ed:Q967118
  has 5 URLs). **D14:** `:Event` declares `hasExternalReference min 1` but the source supplies
  it for 0 events and provenance-chain enrichment reaches only 55% → **relax to min 0**;
  altLabel inference rejected (D11).
- ⬜ **Agent (link props)** — `:hasAgentRecord` `:hasDescriptionText` `:hasExternalReference`
- ⬜ **ResearchProject** — `:ResearchProject` `:Researcher` `:ResearchProjectPIRole`
  `:ResearchProjectContributorRole`

## Unassigned terms (no `isNativeTo`) — treat as a "linking" module
- classes: `:Coordinates` `:Match` `:MatchType` `:PlaceCV` `:PlaceTypeCV` `:SpatialExtent`
- objprops (Agent→Record links): `:hasAgeRecord` `:hasNameRecord` `:hasSexRecord`
  `:hasOccupationRecord` `:hasOriginRecord` `:hasPersonRecord` `:hasPersonStatusRecord`
  `:hasRaceRecord` `:hasParticipantRoleRecord` `:hasInterAgentRelationshipRecord`
  `:hasBroader` `:hasMatchType` `:hasPlaceTypeCV` `:hasSpatialExtent`
  `:isAdministrativePartOf` `:matches`
- dataprops: `:hasDescriptiveEthnonym` `:hasDescriptiveOccupation`

These are the edges that attach records to their agents (e.g. `P42`→`:hasAgeRecord`).

---

## Recommended build order (dependency-driven)

1. **TemporalExtent** — unblocks the cardinality-1 constraint on every record class.
2. **EntityWithProvenance** — cross-cutting, applies to all entities.
3. **AgeRecord backfill** — add temporal extent + owning-agent link (see below).
4. **AgentRole** (`:Person`, `:Organization`) + **Agent link props** — records need an owner.
5. **Place** — Event depends on it (`atPlace someValuesFrom :Place`).
6. **Event** + **ParticipantRoleRecord**.
7. Remaining record modules (Sex, Name, Occupation, Origin, PersonStatus, Race, Person,
   InterAgentRelationship).
8. **Description**, **ExternalReference**, **ResearchProject**, **Match/linking**.

## 🔧 AgeRecord — rebuilt via-reification (2026-07-20)

The original build typed the 123 `Q424` **items** as `:AgeRecord`. Wrong: those items are
*shared value-holders* ("18 years old"), reused across 277k person-age facts, so every
18-year-old shared one record and the `pq:P18 recordedAt` qualifiers had nowhere to attach.

`age_record.py` now de-reifies: the **statement node** `eds:Q…-<uuid>` is the `:AgeRecord`.
IRIs already exist, so nothing is minted.

**Output: 277,194 `:AgeRecord`s** — exact match to the Step-0 `ep:P42` statement count.
- 275,677 distinct owning persons (1,289 carry 2+ records) — owning-agent gap **closed**
- `:hasValue` + `:hasAgeValue` on all 277,194, max 1 each ✓; all 4 CV targets typed
  `:AgeCategory` by `cv_individuals` — no dangling references
- `:recordedAt` 277,979 objects — exact match to the qualifier-use count

Remaining gaps:
- **`:hasTemporalExtent`** (cardinality 1) — TemporalExtent module, whose subjects for this
  class are the **statement IRIs**, not the `Q424` items (see DESIGN D4).
- `?person` not yet typed `:Agent`/`:Person` — AgentRole module; until then the
  inverse-`hasAgentRecord` cardinality-1 constraint cannot be checked.
- **Accepted violations** (logged in `mappings/coverage-gaps.csv`, not silently fixed): 789 records
  carry 2 `:recordedAt`, 5 carry 2 `:isDirectlyBasedOn`, against `maxQualifiedCardinality 1`.
  Real source multiplicity — both values are emitted rather than arbitrarily picking one;
  Phase 5 SHACL will surface them for a human call.
