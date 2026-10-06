#!/usr/bin/env python3
"""
Phase 3 - Module: :Description   (SYNTHESIS)

Runs a SPARQL CONSTRUCT against Fuseki and writes the ontology-grounded triples as Turtle.

SCOPE: `edt:P66` ONLY. Materialises exactly the free-text descriptions the wiki states.

WHAT THE WIKI HAS
-----------------
  edt:P66  "hasDescription"  wikibase:propertyType <http://wikiba.se/ontology#String>

A flat string hung directly on an entity:

    ed:Q358 edt:P66 "In 1741, ten fires blazed across New York City. ..." .

Measured dump-wide (VERIFIED - description_diagnostics.rq query 1, run against the full dump):

    edt:P66 statements                                    293,319
    distinct subjects                                     271,418

                                       subjects   statements
      Q238  Event                       188,101      190,220
      Q410  Person (Agent)               81,508      100,959
      Q301  Place                         1,732        2,056
      Q172  ResearchProject                  40           45
      Q411  Organization (Agent)            20           20
      Q67   EntityWithProvenance            12           14
      Q359  Party (dataset-level)            4            4
      Q280159 Place                          1            1

RDF stores triples as a SET, so `COUNT(*)` on `?s edt:P66 ?text` counts distinct (entity, text)
pairs - which is exactly the number of :Description nodes this module mints: 293,319. The gap
between 293,319 statements and 271,418 subjects means ~21,900 entities carry MORE THAN ONE
description; this is COMMON, not rare (the top entity, Q1149133, has 18). That is what makes the
per-text md5 in D1 load-bearing - not the "insurance" it was first assumed to be.

Every value is a PLAIN literal - no language tag, no datatype - so it is `xsd:string` by RDF
default, which is exactly what `:asText`'s `onDataRange xsd:string` wants (VERIFIED: query 3
returns 0 rows). Kept VERBATIM (no cast, no trim, no normalisation - synthesise the container,
never touch the data inside).

THE MOVE - SYNTHESIS (mapping issue 5)
--------------------------------------
The mapping reconciles `P66` -> `:hasDescriptionText`, but that is an OBJECT property whose
range is the `:Description` CLASS, while the wiki gives a bare string. So there is no node to
point at - one must be minted:

    ?desc a :Description ; :asText "<the wiki string>" .

`:Description rdfs:subClassOf :EntityWithProvenance , [ :asText qualifiedCardinality 1
onDataRange xsd:string ]`. This module satisfies the `asText` cardinality-1 by construction
(exactly one string per minted node, see D1). The `:EntityWithProvenance` facet (license,
generating activity, ...) is NOT this module's job - it is filled by the provenance module,
keyed on these same minted IRIs. A module labels/fills exactly what it emits.

MODULE SCOPE - :Description NODES ONLY, NO LINK EDGE  (2026-08-24)
-----------------------------------------------------------------
This module emits ONLY the :Description NODES - each node's type plus its one :asText string.
It does NOT emit the `<entity> :hasDescriptionText <desc>` link. In the ontology,
`:hasDescriptionText` is native to the OWNING entities (`opla:isNativeTo` Agent, Event, Place,
ResearchProject), NOT to `:Description`; `:asText` is native to `:Description`. So the link is
a fact ABOUT the owning entity and belongs to whichever module owns that entity (the Agent /
Event / Place / ResearchProject modules), which emits it when refactored to consume these
nodes - reusing the SAME deterministic `<entity>-desc-<md5(text)>` IRI minted here. Keeping the
module to its own class means description.ttl contains nothing but :Description / :asText.

This mirrors the temporal_extent refactor: there the minted `<subject>-extent` node is emitted
here and `:hasTemporalExtent` is left to the owning module. The re-derivation is a shade less
trivial than temporal's `<subject>-extent` because the description IRI folds in `MD5(text)`, so
the owning module must read `edt:P66` too and recompute the md5 (see the one-liner in D1); the
principle is identical - one sourced string shared, no invented links.

The ontology even guarantees the ownership is one-to-one: it carries an
`[ owl:inverseOf :hasDescriptionText ] owl:maxCardinality 1` restriction, so a :Description
belongs to at most one entity - which the entity-scoped IRI enforces by construction.

DESIGN D1 - MINTED IRIs
-----------------------
    <entity>-desc-<md5(text)>   one :Description node PER (entity, text) pair.

A pure function of the source => idempotent (re-runs never duplicate; no blank nodes, no
UUIDs). The md5 is over the TEXT, mirroring `external_reference.py`'s per-URL discriminator
(D13 there): when one entity carries several distinct descriptions, each gets its own node and
keeps `:asText` cardinality 1, rather than collapsing onto one node that would then carry
several `:asText` strings and break the exactly-1 restriction. This is LOAD-BEARING, not
insurance: ~21,900 entities carry 2+ descriptions dump-wide (top one, Q1149133, has 18 - see
diagnostic 2), so without the per-text md5 each of those would collapse onto a single node
holding many strings, violating `asText qualifiedCardinality 1` on every one. The forward
`:hasDescriptionText` is `minQualifiedCardinality 0` (NO max) on all four owning classes, so an
entity pointing at many :Description nodes is fully legal - no cardinality gap here, unlike
temporal_extent's accepted multi-date collapse.

The owning module re-derives the identical IRI with the same BIND, so the link lands on the
right node without this module emitting it:

    ?entity edt:P66 ?text .
    BIND(IRI(CONCAT(STR(?entity), "-desc-", MD5(STR(?text)))) AS ?desc)
    # -> ?entity :hasDescriptionText ?desc

DESIGN D2 - NO TYPE GUARD, NO LABEL
-----------------------------------
Not restricted to `edt:P1 ed:Q238`/`Q410`/... . `:hasDescriptionText` is native to Agent,
Event, Place and ResearchProject, which covers the overwhelming majority above; the ~16
Q67/Q359 dataset-level carriers fall outside those four, but this module materialises what
the SOURCE states rather than pre-filtering to what the ontology's `isNativeTo` expects -
same stance as `external_reference.py` and `temporal_extent.py`. Diagnostic 1 prints the
type breakdown so the few off-domain carriers are seen, not silently dropped.

No `rdfs:label` is emitted: a `:Description` node has no NAME in the wiki - its content IS
the `:asText` string, and inventing a truncated label would be fabricated data. Same call as
the minted temporal extents and the AgeRecord statement nodes.

Usage (from repo root):
    python phase3\\description.py --dataset Enslaved-dataset          # full run
    python phase3\\description.py --dataset Enslaved-dataset --test
    python phase3\\description.py --print-query
Writes out/phase3/description.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

# "Slave insurrection of 1741" (Q358) - a single, quotable description, so the minted shape
# is easy to eyeball against the ontology pattern.
TEST_ENTITY = "ed:Q358"

CONSTRUCT = """
PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>

CONSTRUCT {{
    ?desc    a        :Description ;
             :asText  ?text .
}}
WHERE {{
    {values}
    ?entity edt:P66 ?text .

    # md5 of the TEXT: one entity may carry more than one description (3 do dump-wide), and a
    # shared node would collect several :asText strings, breaking `asText qualifiedCardinality 1`.
    # ?entity is needed only to build the IRI - the `:hasDescriptionText` link is the owning
    # module's job (see MODULE SCOPE), so ?entity is not emitted.
    BIND(IRI(CONCAT(STR(?entity), "-desc-", MD5(STR(?text)))) AS ?desc)
}}
{limit}
"""


def build_query(test: bool, limit) -> str:
    values = f"VALUES ?entity {{ {TEST_ENTITY} }}" if test else ""
    return CONSTRUCT.format(values=values, limit=f"LIMIT {limit}" if limit else "")


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


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 :Description module (P66 only, nodes-only).")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--test", action="store_true", help=f"restrict to {TEST_ENTITY}")
    ap.add_argument("--limit", type=int, default=None, help="cap solutions")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/description.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    query = build_query(args.test, args.limit)
    if args.print_query:
        print(query)
        return 0

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "description.ttl")

    scope = f"TEST: {TEST_ENTITY} only" if args.test else "full run"
    if args.limit:
        scope += f", LIMIT {args.limit}"
    print(f"Querying {endpoint}  ({scope})")

    ttl = run_construct(endpoint, query)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(ttl)

    triples = sum(1 for ln in ttl.splitlines()
                  if ln.strip().endswith((" .", " ;")) and not ln.strip().startswith(("@", "#")))
    print(f"wrote {out_path}  (~{triples} triples)")

    if args.test:
        print("--- expected shape for ed:Q358 ---")
        print("  ed:Q358-desc-<md5> a :Description ;")
        print('      :asText "In 1741, ten fires blazed across New York City. ..." .')
        print("  >>> :Description NODE only - no ed:Q358 :hasDescriptionText ... triple here;")
        print("      the owning module emits that link, re-deriving the SAME -desc-<md5> IRI.")
        print("  >>> exactly ONE :asText on the node (asText qualifiedCardinality 1). If the")
        print("      entity had two distinct P66 strings you would see two -desc-<md5> nodes,")
        print("      NOT one node with two :asText values.")
    else:
        print("Checks (see queries/description_diagnostics.rq, run AFTER):")
        print("  * ~293,319 :Description nodes = distinct (entity,text) pairs; ~21,900 entities")
        print("    carry 2+ descriptions (top 18), so nodes > subjects (271,418)")
        print("  * every :Description has exactly one :asText, all xsd:string (max/min 1)")
        print("  * no :Description with more than one :asText (the md5 IRI protects this)")
        print("  * NO :hasDescriptionText triples in the output - this module emits nodes only;")
        print("    the owning module (Agent, Event, Place, ResearchProject) adds that link")
        print("  * type breakdown of covered entities matches diagnostic 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
