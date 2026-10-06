#!/usr/bin/env python3
"""
Phase 3 - Module: :TemporalExtent / :TimeSpan   (SYNTHESIS)

Runs SPARQL CONSTRUCTs against Fuseki and writes the ontology-grounded triples as Turtle.

WHY THIS MODULE EXISTS
----------------------
The ontology models time as a node, not as a flat literal on the entity:

    :TemporalExtent  a owl:Class ;
        [ :contains allValuesFrom xsd:date ] , [ :startsAt allValuesFrom xsd:date ] ,
        [ :endsAt   allValuesFrom xsd:date ] , ...            # only TYPES values if present

    :TimeSpan rdfs:subClassOf :TemporalExtent ,
        [ :startsAt someValuesFrom xsd:date ] ,               # REQUIRES a start
        [ :endsAt   someValuesFrom xsd:date ]                 # REQUIRES an end

The wiki has no such node - it has flat dates hanging off the entity
(`edt:P28 "1801-01-01T00:00:00Z"^^xsd:dateTime`). So this module MINTS the extent node.
It is the first genuinely synthetic module; every prior one only re-typed and renamed.

`:AgentRecord` and `:Event` both carry `:hasTemporalExtent` cardinality **1**, so nearly
every other module is blocked on this one.

DESIGN D8 - SPLIT BY SHAPE OF TIME: POINT vs INTERVAL   (supersedes the old all-TimeSpan mint)
---------------------------------------------------------------------------------------------
The earlier version of this module typed EVERYTHING as `:TimeSpan` and forced the lone
wiki date into `:startsAt`. That was wrong on two counts: a single date is a point, not an
interval, and a `:TimeSpan` with no end fails `:TimeSpan`'s `someValuesFrom :endsAt`
requirement (that was "gap 2", diagnostic 5 - now designed out).

The mint now branches on whether an end date (`edt:P63`) is present:

  * DATE ONLY  (edt:P28, no edt:P63)   -> a point in time
        ?subj a :TemporalExtent ; :contains <date> .
    `:TemporalExtent` has only `allValuesFrom` restrictions, so a lone `:contains` is
    well-formed - nothing forces a start/end to exist.

  * DATE + END (edt:P28 AND edt:P63)   -> a bounded interval
        ?subj a :TimeSpan ; :startsAt <date> ; :endsAt <end> .
    A node becomes a `:TimeSpan` ONLY when it genuinely has both endpoints, so
    `:TimeSpan`'s `someValuesFrom` on both `:startsAt` and `:endsAt` is satisfied by
    construction. No more "TimeSpan with a start and no end".

  * END ONLY   (edt:P63, no edt:P28)   -> a point in time (the one known bound)
        ?subj a :TemporalExtent ; :endsAt <end> .
    Same shape as DATE ONLY: `:TemporalExtent` only TYPES a value if present, so a lone
    `:endsAt` is well-formed. NOT a `:TimeSpan` - with no start it cannot satisfy
    `:TimeSpan`'s `someValuesFrom :startsAt`, so typing it `:TimeSpan` would fabricate a
    violation. This closes the old bug where a subject carrying only edt:P63 matched
    NEITHER TE (which requires P28) NOR TS (which requires P28) and so got no extent at
    all (~350 events, silently absent - see docs/GAPS-REPORT.md §2b).

TE, TS and EO now PARTITION every subject carrying edt:P28 or edt:P63: TE = P28 & !P63,
TS = P28 & P63, EO = P63 & !P28. The three are mutually exclusive and jointly exhaustive,
so each dated subject gets exactly one extent and none is minted twice.

WHAT THE DATA ACTUALLY HAS  (verified against chunks/)
------------------------------------------------------
  edt:P28 "date"          400,933 statements, 0 qualifiers   -> :contains (point) / :startsAt (interval)
  edt:P63 "endsAt"        present, mostly on Voyage events   -> :endsAt   (interval; or lone bound when no P28)
  edt:P52 "occursAfter"   DEFINED IN chunk_0, ZERO INSTANCES -> nothing to emit
  edt:P69 "occursBefore"  DEFINED IN chunk_0, ZERO INSTANCES -> nothing to emit

`:occursAfter` / `:occursBefore` are ontology terms with no wiki source - coverage gaps,
not bugs. Do not go looking for them in the output.

DESIGN D5 - RAW LITERALS; PRECISION IS DEFERRED, NOT IGNORED
-------------------------------------------------------------
**Decision: emit the wiki literal exactly as stored. No reshaping, no widening, no cast.**
(Unchanged by D8 - the split changes which PROPERTY carries the literal, never the literal.)

Wikibase serialises EVERY time value as a full dateTime and puts the real precision on a
separate value node:

    eds:Q52546-10A6…  eps:P28  "1801-01-01T00:00:00Z"^^xsd:dateTime ;
                      epsv:P28 edv:f3c356… .
    edv:f3c356…       a wikibase:TimeValue ;
                      wikibase:timeValue     "1801-01-01T00:00:00Z"^^xsd:dateTime ;
                      wikibase:timePrecision "9"^^xsd:integer .

Precision 9 means "sometime in 1801" - the `-01-01` is PADDING, not a fact, and all three
precisions occur in this dump (9 = year, 10 = month, 11 = day). So a consumer reading
`:contains "1801-01-01T00:00:00Z"` off this module's output and treating it as a real day
will be wrong for every year-precision record. That is a documented property of the
output, not a defect in it.

The reason this is still a sound call: the source literal is preserved byte-for-byte, so
nothing is lost. Precision-widening is pure derivation - it can be reconstructed at any
later point from `epsv:P28 -> wikibase:timePrecision`, which stays in the wiki graph. If
you want the widening back (year -> Jan 1..Dec 31, month -> month bounds, day -> exact),
that is the rule to re-implement, and it belongs in a derivation pass over this module's
output rather than in the extraction.

No deprecated-rank filter is needed on this path. Wikibase only exports best-rank claims
to the `edt:` direct predicates, so retracted statements never reach `edt:P28` / `edt:P63`
in the first place. (`age_record.py` DOES filter, because it reads `ep:`/`eps:` statement
nodes, where deprecated claims are present.)

DESIGN D6 - ONE REMAINING SHACL GAP, ACCEPTED FOR NOW
------------------------------------------------------
D8 closes the old "missing end" gap. One gap remains, and it is the D5 consequence:

  RANGE. `:contains` / `:startsAt` / `:endsAt` are `allValuesFrom xsd:date`; the wiki
  emits `xsd:dateTime`. Every value this module writes will be flagged on range. Fixing it
  is a one-line cast (`xsd:date(...)`) whenever the D5 decision is revisited - but see the
  precision caveat above before doing it blindly.

Diagnostic 7 in `temporal_diagnostics.rq` detects exactly this, and is EXPECTED TO RETURN
ROWS under the current design. Do not treat it as a regression.

DESIGN D7 - MINTED IRIs ARE DETERMINISTIC
------------------------------------------
    <subject> -> <subject>-extent      e.g. ed:Q52546 -> ed:Q52546-extent

Neutral suffix `-extent` (NOT `-timespan`): a minted node is now either a
`:TemporalExtent` or a `:TimeSpan` depending on the data, so a TimeSpan-specific name
would be a lie for the point case. A pure function of the source IRI, per PHASE3-PLAN §1:
never blank nodes, never UUIDs, so re-running the module is idempotent instead of
duplicating 400k nodes.

NO LABELS. A minted extent has no name in the source and inventing one ("Timespan of Birth
of Lucy") would be fabrication. Same call as the AgeRecord statement nodes.

D7 CAVEAT - MULTI-DATED SUBJECTS COLLAPSE ONTO ONE NODE  (ACCEPTED GAP, 2026-08-24)
Because the IRI is a pure function of the subject, a subject carrying 2+ edt:P28 dates mints
ONE `<subject>-extent` node that then holds several dates: a point extent gets multi-valued
:contains, and a multi-dated interval gets multi-valued :startsAt. temporal_diagnostics.rq
query 3b samples these subjects (it is EXPECTED to return rows now, not 0). The collapse is
ACCEPTED rather than fixed: adding a per-date discriminator to the IRI would fan
:hasTemporalExtent out to several extents per subject, which the owning modules' cardinality-1
constraint cannot take. Logged in mappings/coverage-gaps.csv (:TemporalExtent / :TimeSpan);
Phase 5 SHACL is expected to flag it. Run 3b without its LIMIT for the exact population.

MODULE SCOPE - EXTENT NODES ONLY, NO LINK EDGE  (2026-08-24)
-----------------------------------------------------------
This module emits ONLY the extent NODES - each node's type plus its :contains / :startsAt /
:endsAt literals. It does NOT emit the `<subject> :hasTemporalExtent <extent>` link. That
edge is a fact ABOUT the owning subject (an Event, an AgentRecord, ...), not about the
extent, so it belongs to whichever module owns the subject and is added there when that
module is refactored to consume these extent nodes. Keeping the module to its own class
means temporal_extent.ttl contains nothing but :TemporalExtent / :TimeSpan definitions.

The former query B moved out entirely for this reason. B never minted a node - it only
attached an event's already-minted extent to that event's AgeRecord statement
(`?ageRecord :hasTemporalExtent <?event-extent>`). That is a pure cross-module link, so it
belongs in age_record.py, not here. When age_record.py is refactored it re-derives the same
edge: for each ep:P42 statement (skipping deprecated rank) whose pq:P18 recordedAt event has
a date, emit `?ageRecord :hasTemporalExtent <?event-extent>`, reusing the SAME <event>-extent
IRI this module mints. One sourced date shared, not 277k invented ones. The same move fits
every later reified record module (P33, P31, P22): change the property and record class, keep
the shape.

THE THREE QUERIES
-----------------
  TE  points    mints a :TemporalExtent on any subject with edt:P28 but NO edt:P63:
                    <?subj-extent> a :TemporalExtent ; :contains ?rawDate .

  TS  intervals mints a :TimeSpan on any subject with BOTH edt:P28 and edt:P63:
                    <?subj-extent> a :TimeSpan ; :startsAt ?rawStart ; :endsAt ?rawEnd .

  EO  end-only  mints a :TemporalExtent on any subject with edt:P63 but NO edt:P28:
                    <?subj-extent> a :TemporalExtent ; :endsAt ?rawEnd .

                TE, TS and EO partition every subject carrying edt:P28 or edt:P63 (each
                query's FILTER NOT EXISTS is the complement of the others), so no subject
                is minted twice and every dated subject gets exactly one extent. EO is the
                branch that was missing: without it a P63-only subject matched neither TE
                nor TS and got no extent at all.

NOT TYPE-GUARDED. TE/TS/EO do not require `edt:P1 ed:Q238` on the subject. `hasTemporalExtent`
is native to both Event and AgentRecord, and a date on a non-Event is still a real date;
gating on the Event type would silently drop them. Run the subject-type diagnostic in
`temporal_diagnostics.rq` to see what actually carries P28 before accepting the output.

Usage (from repo root):
    python phase3\\temporal_extent.py --dataset Enslaved-dataset            # all three queries
    python phase3\\temporal_extent.py --dataset Enslaved-dataset --test     # one fixture each
    python phase3\\temporal_extent.py --only EO --limit 500                 # end-only smoke test
    python phase3\\temporal_extent.py --print-query                         # SPARQL only
Writes out/phase3/temporal_extent.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

# "Birth of Lucy" - an Event carrying edt:P28 and NO edt:P63, so it exercises the point
# branch (-> :TemporalExtent / :contains).
TEST_POINT_EVENT = "ed:Q52546"

# "Acredam Voyage" - an Event carrying BOTH edt:P28 and edt:P63, so it exercises the
# interval branch (-> :TimeSpan / :startsAt + :endsAt) (chunks/chunk_2.ttl).
TEST_SPAN_EVENT = "ed:Q142595"

# "Maranhao Inventories Slave Database" - a subject carrying edt:P63 ("1864-01-01") but NO
# edt:P28, so it exercises the end-only branch (-> :TemporalExtent / :endsAt). Verified in
# chunks/chunk_0.ttl; one of only 6 end-only subjects in that chunk.
TEST_END_EVENT = "ed:Q11585"

PREFIXES = """
PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>
PREFIX rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd:     <http://www.w3.org/2001/XMLSchema#>
"""
# Only the edt: direct predicates are read now. eps:/epsv: went when D5 stopped widening by
# wikibase:timePrecision; ep:/pq:/wikibase: went with query B (the AgeRecord link), which now
# lives in age_record.py. Restore whichever set if that logic ever returns here.

# ---------------------------------------------------------------------------
# Query TE - date-only subjects -> :TemporalExtent with :contains.
#
# `FILTER NOT EXISTS { edt:P63 }` is the complement of TS's required end, so TE and TS
# never mint the same subject. Reads DIRECT predicates only (best-rank), so no
# deprecated-rank filter is needed.
# ---------------------------------------------------------------------------
QUERY_TE = PREFIXES + """
CONSTRUCT {{
    ?ext   a          :TemporalExtent ;
           :contains  ?rawDate .
}}
WHERE {{
    {values}
    ?subj edt:P28 ?rawDate .
    FILTER NOT EXISTS {{ ?subj edt:P63 ?anyEnd . }}   # no end -> a point, not an interval

    BIND(IRI(CONCAT(STR(?subj), "-extent")) AS ?ext)
}}
{limit}
"""

# ---------------------------------------------------------------------------
# Query TS - subjects with BOTH a start and an end -> :TimeSpan.
#
# Requiring edt:P63 here is what guarantees every minted :TimeSpan has both endpoints,
# satisfying :TimeSpan someValuesFrom :startsAt / :endsAt by construction (D8).
# ---------------------------------------------------------------------------
QUERY_TS = PREFIXES + """
CONSTRUCT {{
    ?ext   a          :TimeSpan ;
           :startsAt  ?rawStart ;
           :endsAt    ?rawEnd .
}}
WHERE {{
    {values}
    ?subj edt:P28 ?rawStart .
    ?subj edt:P63 ?rawEnd .

    BIND(IRI(CONCAT(STR(?subj), "-extent")) AS ?ext)
}}
{limit}
"""

# ---------------------------------------------------------------------------
# Query EO - end-only subjects (edt:P63 but NO edt:P28) -> :TemporalExtent with :endsAt.
#
# The missing branch: TE requires P28, TS requires P28, so a subject with only P63 fell
# through both and got no extent (docs/GAPS-REPORT.md §2b, ~350 events). This is a POINT
# (:TemporalExtent), not a :TimeSpan - a lone end has no start, so :TimeSpan's
# someValuesFrom :startsAt could not be satisfied. `FILTER NOT EXISTS { edt:P28 }` makes it
# the exact complement of TE+TS, keeping the three-way partition mutually exclusive.
# ---------------------------------------------------------------------------
QUERY_EO = PREFIXES + """
CONSTRUCT {{
    ?ext   a        :TemporalExtent ;
           :endsAt  ?rawEnd .
}}
WHERE {{
    {values}
    ?subj edt:P63 ?rawEnd .
    FILTER NOT EXISTS {{ ?subj edt:P28 ?anyStart . }}   # end but no start -> a lone bound, not an interval

    BIND(IRI(CONCAT(STR(?subj), "-extent")) AS ?ext)
}}
{limit}
"""

# The former query B (attach an event's extent to its AgeRecord statement) is gone: it minted
# no node, only a `?ageRecord :hasTemporalExtent <?event-extent>` link, which is a fact about
# the AgeRecord and now belongs to age_record.py. See the MODULE SCOPE note in the docstring.

QUERIES = {"TE": QUERY_TE, "TS": QUERY_TS, "EO": QUERY_EO}
TEST_VALUES = {
    "TE": f"VALUES ?subj {{ {TEST_POINT_EVENT} }}",
    "TS": f"VALUES ?subj {{ {TEST_SPAN_EVENT} }}",
    "EO": f"VALUES ?subj {{ {TEST_END_EVENT} }}",
}


def build_query(name: str, test: bool, limit) -> str:
    limit_clause = f"LIMIT {limit}" if limit else ""
    values = TEST_VALUES[name] if test else ""
    return QUERIES[name].format(values=values, limit=limit_clause)


def run_construct(endpoint: str, query: str) -> str:
    """POST a CONSTRUCT query; return Turtle."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Accept": "text/turtle",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def count_triples(ttl: str) -> int:
    return sum(1 for ln in ttl.splitlines()
               if ln.strip().endswith((" .", " ;")) and not ln.strip().startswith(("@", "#")))


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 :TemporalExtent / :TimeSpan synthesis.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="enslaved-dataset")
    ap.add_argument("--only", choices=["TE", "TS", "EO"], default=None,
                    help="TE = point extents (P28 only); TS = intervals (P28+P63); "
                         "EO = end-only extents (P63 only)")
    ap.add_argument("--test", action="store_true",
                    help=f"restrict to {TEST_POINT_EVENT} (TE) / {TEST_SPAN_EVENT} (TS) / "
                         f"{TEST_END_EVENT} (EO)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap solutions (smoke-test a slice of the ~400k dates)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/temporal_extent.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    names = [args.only] if args.only else ["TE", "TS", "EO"]

    if args.print_query:
        for n in names:
            print(f"# ===== QUERY {n} =====")
            print(build_query(n, args.test, args.limit))
        return 0

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "temporal_extent.ttl")

    scope = "TEST fixture only" if args.test else "full run"
    if args.limit:
        scope += f", LIMIT {args.limit}"
    print(f"Querying {endpoint}  ({scope})")

    total = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for n in names:
            print(f"  running query {n} ...")
            ttl = run_construct(endpoint, build_query(n, args.test, args.limit))
            got = count_triples(ttl)
            total += got
            print(f"    query {n}: ~{got} triples")
            fh.write(f"# ===== query {n} =====\n")
            fh.write(ttl)
            fh.write("\n")

    print(f"wrote {out_path}  (~{total} triples)")

    if args.test:
        print("--- expected shape, point case: ed:Q52546 (Birth of Lucy - P28 only) ---")
        print("  ed:Q52546-extent a :TemporalExtent ;")
        print('      :contains "1801-01-01T00:00:00Z"^^xsd:dateTime .')
        print("--- expected shape, interval case: ed:Q142595 (Acredam Voyage - P28 + P63) ---")
        print("  ed:Q142595-extent a :TimeSpan ;")
        print('      :startsAt "1720-09-28T00:00:00Z"^^xsd:dateTime ;')
        print('      :endsAt   "1721-10-27T00:00:00Z"^^xsd:dateTime .')
        print("--- expected shape, end-only case: ed:Q11585 (Maranhao Inventories - P63, no P28) ---")
        print("  ed:Q11585-extent a :TemporalExtent ;")
        print('      :endsAt "1864-01-01T00:00:00Z"^^xsd:dateTime .')
        print("  (a :TemporalExtent, NOT a :TimeSpan - it has no start)")
        print("  (extent NODES only - the :hasTemporalExtent link on the subject is emitted")
        print("   by the owning module, not here)")
        print("  (wiki literals verbatim, per D5 - no cast, no widening)")
        print("  (no rdfs:label - minted nodes are unnamed by design)")
    else:
        print("Checks:")
        print("  * (TE + TS + EO) extents == distinct subjects carrying edt:P28 OR edt:P63 -")
        print("    every dated subject gets exactly one extent; TE/TS/EO partition them:")
        print("    TE = P28 & !P63, TS = P28 & P63, EO = P63 & !P28 (mutually exclusive)")
        print("  * EO count == subjects with edt:P63 and no edt:P28 (was ~350, silently")
        print("    dropped before this branch existed - GAPS-REPORT.md §2b now closed)")
        print("  * every :contains / :startsAt / :endsAt literal is byte-identical to its")
        print("    edt:P28 / edt:P63 source - this module reshapes nothing")
        print("  * every :TimeSpan has BOTH :startsAt and :endsAt (diagnostic 5 -> 0 rows now)")
        print("  * NO :hasTemporalExtent triples in the output - this module emits extent")
        print("    nodes only; the owning modules (Event, AgeRecord, ...) add that link")
        print("  * nothing emitted for :occursBefore / :occursAfter - correct, no wiki source")
        print("")
        print("EXPECTED violation under D5/D6 - NOT a regression:")
        print("  * diagnostic 7 flags every literal as xsd:dateTime, not xsd:date (range)")
        print("  Deferred by design; revisit before Phase 5 SHACL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
