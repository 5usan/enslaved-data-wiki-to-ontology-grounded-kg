#!/usr/bin/env python3
"""
Phase 3 - Module: :ExternalReference / :ExternalReferent

Runs a SPARQL CONSTRUCT against Fuseki and writes the ontology-grounded triples as Turtle.

SCOPE: `edt:P21` ONLY. This module materialises exactly the references the wiki actually
states. It does NOT attempt to satisfy `:Event`'s `hasExternalReference` min-1 restriction -
see DESIGN D14 for why that is a deliberate refusal rather than an omission.

WHAT THE WIKI HAS
-----------------
  edt:P21  "hasExternalReference"  wikibase:propertyType <http://wikiba.se/ontology#Url>

Values are IRIs, and an entity may carry several:

    ed:Q967118 edt:P21 <url-1> , <url-2> , … , <url-5> .   # 5 URLs - the current max

Verified dump-wide (external_reference_source_check.rq, run against the full dataset):

    P21 triples                  1079
    distinct (entity, url) pairs 1079   -> the exact :ExternalReference node count
    distinct URLs                 150   -> the exact distinct :withID string count
    items carrying P21           1035
      of class Q67  EntityWithProvenance  1004
      of class Q172 ResearchProject         29
      other/untyped                          2
    EVENTS carrying P21             0

One URL dominates: <https://slavevoyages.org/> is cited by 838 entities.

`P12 hasLink` has no instance data at all - 3 occurrences, all schema declarations. There is
nothing to build from it.

So the honest yield of this module is 1079 reference nodes over 150 URLs on dataset-level
entities. That is small, and it is the whole truth of what the source calls an external
reference. (An earlier build produced 955/98 against a partial dump load; re-run on the full
dataset to get the figures above.)

MODULE SHAPE - :withID STRING, NOT :refersTo :ExternalReferent  (2026-08-24)
---------------------------------------------------------------------------
The `:ExternalReference` union restriction lets a reference carry its target EITHER as
`:refersTo` -> `:ExternalReferent` (an object) OR as `:withID` (an xsd:string). This module
takes the `:withID` branch: each `:ExternalReference` node carries the URL as a plain STRING
via `:withID`, and NO `:ExternalReferent` node is minted.

    <entity>-extref-<md5(url)>  a  :ExternalReference ;  :withID "<url-as-string>" .

`:withID` is a DatatypeProperty with `owl:onDataRange xsd:string`, so the value must be a
literal: the bind is `STR(?url)` (the URL flattened to a plain string), never the bare IRI -
an IRI object on `:withID` would violate the string range. Consequence: `:ExternalReferent`
is NOT materialised by this module; nothing in external_reference.ttl is typed
`:ExternalReferent`, and `:refersTo` is not emitted.

MODULE SCOPE - NODES ONLY, NO LINK EDGE  (2026-08-24)
----------------------------------------------------
This module emits ONLY the `:ExternalReference` nodes it owns (each one's type + its one
`:withID` string). It does NOT emit the `<entity> :hasExternalReference <ref>` link. In the
ontology `:hasExternalReference` is `opla:isNativeTo` the OWNING entities - **Agent, Event,
ResearchProject** - NOT to `:ExternalReference`; `:refersTo`, `:withID` and `:ExternalReferent`
are native to `:ExternalReference`. So the link is a fact ABOUT the owning entity and belongs
to whichever module owns that entity (the Agent / Event / ResearchProject modules), which emits
it when refactored to consume these nodes - re-deriving the SAME deterministic
`<entity>-extref-<md5(url)>` IRI minted here. Keeping the module to its own class means
external_reference.ttl contains nothing but `:ExternalReference` / `:withID`.

This mirrors the description and temporal_extent refactors: there the minted node is emitted
here and the link (`:hasDescriptionText` / `:hasTemporalExtent`) is left to the owning module.
The re-derivation is identical in shape to description's: the reference IRI folds in
`MD5(STR(url))`, so the owning module must read `edt:P21` too and recompute the md5:

    ?entity edt:P21 ?url .
    BIND(IRI(CONCAT(STR(?entity), "-extref-", MD5(STR(?url)))) AS ?ref)
    # -> ?entity :hasExternalReference ?ref

Because the minted IRI folds in `?entity`, a given `:ExternalReference` node belongs to at
most one entity by construction - the same one-to-one ownership `:hasDescriptionText`'s
`maxCardinality 1` guarantees for descriptions.

DESIGN D11 - THE altLabel INFERENCE WAS CONSIDERED AND REJECTED
----------------------------------------------------------------
Every Event and Place carries a coded string in `skos:altLabel` and `schema:description`:

    ed:Q52546  skos:altLabel "LSD-EVE-BIR-076248"@en .     # Birth of Lucy
    ed:Q9951   skos:altLabel "SV-PLA-31312"@en .           # Havana

These are structured `SOURCE-ENTITYTYPE-SUBTYPE-ID`; 117,437 sampled values are 100%
conforming, across exactly two prefixes (SV 62.1%, LSD 37.9%). An earlier draft of this
module read them as `:withID` and minted an `:ExternalReference` per entity, which would
have satisfied Event's min-1 for all 429,173 Events.

**That was rejected, and the reasoning should outlive the decision.** `skos:altLabel` is a
LABEL property. Reading its values as external identifiers is an interpretation the wiki
never states - well-evidenced, but still ours rather than the source's. Manufacturing
400k+ reference nodes from an inference in order to satisfy a cardinality constraint is
exactly backwards: it makes the graph look compliant while burying the fact that the source
has no such relation. Better a visible gap than an invented edge.

The evidence is preserved above in case someone later decides the inference is warranted;
the rejected query is recoverable from git history. If it is ever revived, it should be a
clearly-labelled enrichment pass over this module's output, never part of extraction.

`edt:P36` Geonames ID (64.5% of Places) was likewise briefly rescued from the mapping's DROP
bucket and is likewise left out. Unlike altLabel it IS an unambiguous external identifier
with a real referent, so it is the strongest candidate if this module is ever widened -
but it is a Place concern, and it is not needed to unblock anything today.

DESIGN D14 - EVENT'S min-1 IS AN ONTOLOGY PROBLEM, NOT A PIPELINE ONE
-----------------------------------------------------------------------
`:Event rdfs:subClassOf [ :hasExternalReference min 1 onClass :ExternalReference ]`, and the
source supplies that relation for **zero** Events. No amount of extraction work changes
that. The finding is that the ontology asserts a relation its own data does not carry.

Sized 2026-08-10 (source-check C2, source-first): enrichment along the provenance chain
`Event <- stmt -> prov:wasDerivedFrom -> ref -> epr:P6 -> source -> edt:P21` reaches
258,431 / 468,855 events = 55% (68 of 150 URLs); the other ~210,424 dead-end at un-digitized
sources. So enrichment CANNOT satisfy min-1 (a ~210k gap remains regardless). CONCLUSION:
**relax the restriction to min 0**; treat the provenance-chain enrichment as an optional
value-add (D11 category), decoupled from cardinality. altLabel inference stays rejected.

Note this decision is now measured against the OWNING module's output, not this one: since
`:hasExternalReference` is no longer emitted here, the Event-coverage gap is a fact about the
Event module (which emits the link, and emits it for 0 events - source-check C, already 0 on
raw), not about external_reference.ttl. Until the restriction is relaxed, **Event is not
blocked by this module.** Build Event; expect the restriction to fail; do not work around it.

DESIGN D13 - MINTED IRIs
-------------------------
    <entity>-extref-<md5(url)>   one reference node PER (entity, url) pair. Entities carry
                                 several URLs (ed:Q967118 has 5) and a shared node would
                                 collect several :withID values, breaking `withID max 1`.

The md5 is over the URL, mirroring description's md5-over-text (D1 there): load-bearing, not
insurance - source-check E lists the entities carrying 2+ URLs, and without the per-URL md5
each would collapse onto one node holding several `:withID` strings, violating
`withID maxQualifiedCardinality 1 onDataRange xsd:string`.

The URL is stored as the `:withID` STRING (`STR(?url)`); no `:ExternalReferent` node is
minted and no `:refersTo` is emitted (see MODULE SHAPE above). `:withID` alone satisfies the
`:refersTo` / `:withID` union restriction. No labels are emitted - the URLs have no name in
the wiki.

Usage (from repo root):
    python phase3\\external_reference.py --dataset Enslaved-dataset       # full run
    python phase3\\external_reference.py --dataset Enslaved-dataset --test
    python phase3\\external_reference.py --print-query
Writes out/phase3/external_reference.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

# Carries 5 distinct P21 URLs (the dump-wide max), so the per-URL IRI discriminator (D13) is
# exercised rather than assumed. NOTE: ed:Q462 was the old test entity, but it now holds only
# ONE URL in the full dump - it no longer tests the md5 branch. Verified via source-check E/H1.
TEST_ENTITY = "ed:Q967118"

CONSTRUCT = """
PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>

CONSTRUCT {{
    ?ref     a        :ExternalReference ;
             :withID  ?id .
}}
WHERE {{
    {values}
    ?entity edt:P21 ?url .

    # The URL stored as a plain STRING via :withID (STR flattens the IRI to an xsd:string
    # literal - :withID's onDataRange xsd:string forbids a bare IRI object here). No
    # :ExternalReferent node, no :refersTo (MODULE SHAPE).
    BIND(STR(?url) AS ?id)

    # md5 of the URL, because an entity may carry several (ed:Q967118 has 5) and one shared
    # node would collect several :withID strings, breaking `withID max 1`. ?entity is used
    # ONLY to mint the IRI - it is not emitted, because the `?entity :hasExternalReference ?ref`
    # link belongs to the owning module (Agent / Event / ResearchProject; see MODULE SCOPE).
    BIND(IRI(CONCAT(STR(?entity), "-extref-", MD5(STR(?url)))) AS ?ref)
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
    ap = argparse.ArgumentParser(
        description="Phase 3 :ExternalReference module (P21 only, nodes-only).")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--test", action="store_true", help=f"restrict to {TEST_ENTITY}")
    ap.add_argument("--limit", type=int, default=None, help="cap solutions")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/external_reference.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    query = build_query(args.test, args.limit)
    if args.print_query:
        print(query)
        return 0

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "external_reference.ttl")

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
        print("--- expected shape for ed:Q967118 ---")
        print("  ed:Q967118-extref-<md5> a :ExternalReference ;")
        print('      :withID "<url-as-string>" .')
        print("  >>> :withID carries the URL as an xsd:string - NO <url> a :ExternalReferent")
        print("      node, NO :refersTo. And NODES only - no ed:Q967118 :hasExternalReference")
        print("      triple here; the owning module (Agent/Event/ResearchProject) emits that")
        print("      link, re-deriving the SAME -extref-<md5> IRI.")
        print("  >>> count the reference nodes: must equal the number of distinct P21 URLs on")
        print("      this entity (5), NOT 1. If it is 1, the md5 discriminator is gone and")
        print("      `withID max 1` is broken.")
    else:
        print("Checks (see queries/external_reference_diagnostics.rq, run AFTER):")
        print("  * 1079 :ExternalReference nodes over 150 distinct :withID strings")
        print("  * every :ExternalReference has exactly one :withID (max 1; the md5 IRI")
        print("    protects this), all xsd:string, and that :withID satisfies the")
        print("    refersTo/withID union restriction (this module emits no :refersTo)")
        print("  * NO :ExternalReferent nodes and NO :hasExternalReference triples in the")
        print("    output - nodes only; the owning module (Agent/Event/ResearchProject) links")
        print("")
        print("EXPECTED and NOT a regression (D14): the Event min-1 gap is now a fact about")
        print("the Event module (which emits :hasExternalReference for 0 events), not this one.")
        print("The restriction is an open ONTOLOGY decision - relax to min 0 - see the docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
