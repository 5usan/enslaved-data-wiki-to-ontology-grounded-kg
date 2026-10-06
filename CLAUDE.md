# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Converts the Enslaved.org Wikibase RDF dump into a graph expressed in the Enslaved Ontology,
using SPARQL `CONSTRUCT` queries run against a local Apache Jena Fuseki instance. Every script
is standard-library-only Python; there is no package manager, build step, or test suite — the
"test" is running a CONSTRUCT against Fuseki and inspecting the Turtle output.

See `docs/ROADMAP.md` for the phase breakdown and `docs/MODULE-MAP.md` for per-module status
(which modules are built, which are gapped, and why).

## Working mode

Guided: the user writes/edits SPARQL, Claude scaffolds the surrounding Python and reviews
query logic, then runs it against the real data. Do not silently "fix" a query's semantics —
flag the reasoning and let the user decide, especially around de-reification and cardinality
gaps (see `docs/GAPS-REPORT.md` for accepted, logged violations vs. actual bugs).

## Prerequisites for running anything

A Fuseki server must be running locally with the dump chunks already loaded:
- Default endpoint: `http://localhost:3030`, dataset `Enslaved-dataset`.
- `fuseki/subproperty.rules` is a GenericRuleReasoner ruleset (rdfs5/rdfs7) that makes the
  `hasAgeRecord → hasPersonRecord → hasAgentRecord` subproperty chain transitive — load it
  when a query needs super-property roll-up.
- `data/` (raw dump + chunks) and `out/` (generated `.ttl`) are gitignored; both are
  regenerated, never hand-edited.

## Commands

```bash
# Phase 1 — extract the wiki->ontology mapping (writes mappings/mapping-*.csv)
python src/phase1/phase1.py --server http://localhost:3030 --dataset Enslaved-dataset

# Phase 2 — reconcile wiki labels against the ontology
python src/phase2/phase2.py
python src/phase2/coverage_report.py

# Phase 3 — one CONSTRUCT per ontology module, e.g.:
python src/phase3/age_record.py --dataset Enslaved-dataset            # full run -> out/phase3/age_record.ttl
python src/phase3/age_record.py --dataset Enslaved-dataset --test     # one known entity, shape check
python src/phase3/age_record.py --dataset Enslaved-dataset --iri ed:Q… --test
python src/phase3/age_record.py --limit 100                           # smoke-test a slice
python src/phase3/age_record.py --print-query                         # print SPARQL, don't run it
```

Every phase 3 script follows this same CLI shape and writes `out/phase3/<module>.ttl` by
default (override with `--out`). Diagnostic companions (`src/phase3/queries/*_diagnostics.py`
+ `.rq`) run empirical checks against the loaded data *before* trusting a module's output —
run the relevant one first when building or debugging a module.

Scripts resolve all paths through `src/paths.py` (`ROOT`, `ONTOLOGY`, `MAPPINGS`, `DATA`,
`CHUNKS`, `OUT_PHASE3`, `OUT_DIAGNOSTICS`, `QUERIES_PHASE3`), so they run correctly from any
working directory. A new script under `src/<phase>/` should import it the same way:

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import MAPPINGS, ONTOLOGY, OUT_PHASE3
```

## Architecture

**The core move (one record, three transformations):** the wiki dump uses opaque Wikibase
IRIs (`ed:Qxxx` entities, `edt:Pxxx` properties). Phase 3 re-types and re-labels each subject
*in place* — it never mints a new IRI for something that already exists. Every CONSTRUCT does
some mix of:
1. **Typing** — `instance of <classItem>` ⟹ `rdf:type :OntologyClass`
2. **Property rename** — opaque `edt:Pxx` ⟹ named ontology property (via the phase 1/2 mapping)
3. **De-reification** — keep the direct `edt:` triples; drop `wikibase:Statement` scaffolding
   (`ep:`/`eps:`/`epq:`/…) — or, for record classes, *re-type the statement node itself* as
   the record (see "Via-reification" below).

**Module decomposition (`docs/MODULE-MAP.md`):** the ontology's `opla:isNativeTo` annotation —
not an ad hoc grouping — defines 20 build modules, matching `ontology/enslaved_image.png`.
Build order is dependency-driven: cross-cutting foundations first (`TemporalExtent`,
`EntityWithProvenance`, controlled-vocabulary individuals), then `AgentRole`/`Place`
(records need an owner and a location), then `Event`, then the ten record modules, then the
synthesis modules (`Description`, `ExternalReference`, `ResearchProject`).

**Via-reification pattern** (see `src/phase3/age_record.py` for the fullest worked example):
several record classes (Age, Name, Sex, ParticipantRole, …) are wiki Wikibase *statement*
nodes (`ep:Pxx` → `eds:…`), not items — the statement IRI already exists and is stable, so the
record is minted by re-typing that node, never by generating a new one. Qualifiers (`pq:`)
and references (`prov:wasDerivedFrom` → one more hop via `epr:Pxx` to the real source, not the
reference wrapper) become the record's own properties.

**Synthesis vs. extraction:** most modules are pure extraction (rename what exists). A few
wiki properties are Wikibase *datatype* properties where the ontology wants an object node
(`P66 hasDescription` → `:Description`, `P21 hasExternalReference` → `:ExternalReference`,
`P59 hasCoordinates` → `:Coordinates`, undated `P28`/`P63` → `:TemporalExtent`/`:TimeSpan`).
These require **synthesis**: minting a new node. The rule (`docs/PHASE3-PLAN.md` §1): minted
IRIs must be a **deterministic, pure function of their source** (e.g. `<subject>-extent`,
`<entity>-desc-<md5(text)>`) — never blank nodes or UUIDs, so re-running a script is
idempotent rather than duplicating.

**Self-contained modules:** a module emits only triples whose *subject* is the entity class
it owns. The inverse "owning" edge (e.g. `?agent :hasAgeRecord ?rec`) is a fact about the
*owner*, not the record, so it is re-homed to the owner's module (`agent.py`) rather than
emitted redundantly in every record module. This means a single module's output can look
incomplete in isolation — cardinality/ownership checks are only meaningful with the owning
module's `.ttl` co-loaded. Check each script's `--test` output notes and the "Checks" printed
after a full run for what is and isn't verifiable standalone.

**Accepted vs. real gaps:** not every unmet ontology constraint is a bug. Real source
multiplicity (e.g. a record legitimately citing 2 sources against a `maxQualifiedCardinality
1` restriction) is emitted as-is and logged in `mappings/coverage-gaps.csv` for Phase 5 SHACL
to surface — never silently collapsed to fit the constraint. Distinguish this from genuine
extraction bugs (wrong predicate, wrong hop) before "fixing" anything Claude finds while
reviewing a query.

## Layout

```
data/                 gitignored — 6.7 GB source data (raw dump + chunk_0..22.ttl)
ontology/enslaved-v2.ttl   target ontology: 46 classes, 52 object props, 19 datatype props
mappings/              phase 1 (raw) and phase 2 (reconciled KEEP/CV_INDIVIDUAL/DROP/REVIEW) CSVs
src/paths.py           canonical path constants — import from here, don't recompute
src/phase1/            extract mapping from Fuseki
src/phase2/            reconcile wiki labels against the ontology + coverage report
src/phase3/*.py         one CONSTRUCT builder per ontology module
src/phase3/queries/     standalone diagnostic .rq + matching .py runners
out/                   gitignored — regenerate by re-running phase 3 scripts
docs/ROADMAP.md         phases 0-5, the core idea, known facts about the data
docs/MODULE-MAP.md      the 20 ontology modules, build status, and per-module design decisions
docs/PHASE3-PLAN.md     conventions + detailed per-module spec/build order
docs/GAPS-REPORT.md     terms with no wiki source, and accepted vs. open gaps
docs/examples/*.ttl     example output per module
```
