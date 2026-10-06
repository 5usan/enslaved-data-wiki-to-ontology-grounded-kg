#!/usr/bin/env python3
"""Phase 3 - :Event (ed:Q238) -> out/phase3/event.ttl

One CONSTRUCT whose WHERE is a UNION of five branches: the Event's own facts plus the links
re-homed from the nodes-only satellites. Each link re-derives the satellite's IRI byte-for-byte.
UNION, not parallel OPTIONALs: those hit a TDB2 "Peek iterator is already empty" 500 and would
cross-product the multi-valued links.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

QUERY = """
PREFIX :         <https://enslaved.org/ontology/>
PREFIX ed:       <https://lod.enslaved.org/entity/>
PREFIX edt:      <https://lod.enslaved.org/prop/direct/>
PREFIX ep:       <https://lod.enslaved.org/prop/>
PREFIX eps:      <https://lod.enslaved.org/prop/statement/>
PREFIX pq:       <https://lod.enslaved.org/prop/qualifier/>
PREFIX epr:      <https://lod.enslaved.org/prop/reference/>
PREFIX prov:     <http://www.w3.org/ns/prov#>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs:     <http://www.w3.org/2000/01/rdf-schema#>

CONSTRUCT {
    ?e a :Event ;
       :hasEventType            ?type ;
       :hasName                 ?name ;
       rdfs:label               ?name ;
       :atPlace                 ?place ;
       :eventSelfProperty       ?e ;
       :hasTemporalExtent       ?temporalExtent ;
       :hasDescriptionText      ?desc ;
       :hasExternalReference    ?externalReference ;
       :providesParticipantRole ?participantRole .
}
WHERE {
    __VALUES__
    {
        ?e edt:P1 ed:Q238 .
        FILTER NOT EXISTS { ?e wikibase:rank wikibase:DeprecatedRank }
        OPTIONAL { ?e edt:P30 ?type }
        OPTIONAL { ?e edt:P20 ?name }
        OPTIONAL { ?e edt:P27 ?place }
    }
    UNION
    {
        # UNION, not the edt:P28|edt:P63 path - the path is another TDB2 reorder trap.
        ?e edt:P1 ed:Q238 .
        { ?e edt:P28 ?extentDate } UNION { ?e edt:P63 ?extentDate }
        BIND(IRI(CONCAT(STR(?e), "-extent")) AS ?temporalExtent)
    }
    UNION
    {
        ?e edt:P1 ed:Q238 ;
           edt:P66 ?text .
        BIND(IRI(CONCAT(STR(?e), "-desc-", MD5(STR(?text)))) AS ?desc)
    }
    UNION
    {
        ?e edt:P1 ed:Q238 ;
           edt:P21 ?url .
        BIND(IRI(CONCAT(STR(?e), "-extref-", MD5(STR(?url)))) AS ?externalReference)
    }
    UNION
    {
        ?e        edt:P1  ed:Q238 ;
                  ep:P29  ?stmt .
        ?stmt     eps:P29 ?roleType ;
                  pq:P17  ?agent .
        ?roleType edt:P1  ?roleTypeClass .
        FILTER(?roleTypeClass IN (ed:Q316, ed:Q351))
        FILTER NOT EXISTS { ?stmt wikibase:rank wikibase:DeprecatedRank }
        OPTIONAL { ?stmt prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }
        BIND(IRI(CONCAT(
            STR(?stmt),
            "-", STRAFTER(STR(?agent), "https://lod.enslaved.org/entity/"),
            "-", COALESCE(STRAFTER(STR(?source), "https://lod.enslaved.org/entity/"), "noSource")
        )) AS ?participantRole)
    }
}
__LIMIT__
"""


def build_query(iri, limit):
    """Fill the placeholders: optionally pin one event and cap the solutions."""
    values = f"VALUES ?e {{ {iri} }}" if iri else ""
    limit_clause = f"LIMIT {limit}" if limit else ""
    return QUERY.replace("__VALUES__", values).replace("__LIMIT__", limit_clause)


def run_construct(endpoint, query):
    """POST the CONSTRUCT to Fuseki and return the Turtle response."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, headers={"Accept": "text/turtle"})
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8")


def main():
    """Run the Event CONSTRUCT and write out/phase3/event.ttl."""
    parser = argparse.ArgumentParser(description="Phase 3 :Event CONSTRUCT")
    parser.add_argument("--server", default="http://localhost:3030")
    parser.add_argument("--dataset", default="Enslaved-dataset")
    parser.add_argument("--iri", help="restrict to one event, e.g. ed:Q358")
    parser.add_argument("--limit", type=int, help="cap solutions for a smoke test")
    args = parser.parse_args()

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = os.path.join(ensure(OUT_PHASE3), "event.ttl")

    ttl = run_construct(endpoint, build_query(args.iri, args.limit))
    with open(out_path, "w", encoding="utf-8") as out_file:
        out_file.write(ttl)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
