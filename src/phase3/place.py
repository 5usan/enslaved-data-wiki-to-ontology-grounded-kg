#!/usr/bin/env python3
"""
Phase 3 - Module: :Place (+ :Coordinates synthesis).

- Query A types the four Place classes, renames their flat claims, and attaches the
  re-homed :hasDescriptionText / :hasTemporalExtent links.
- Query B mints one :Coordinates node per Place from the Wikibase value node (not the
  longitude-first WKT string). A Place can carry several P59 statements, so exactly one
  value node is picked per Place to keep a single :hasLatitude / :hasLongitude pair.

Writes out/phase3/place.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

TEST_PLACE = "ed:Q9951"  # Havana: two P7 values and a coordinate
PLACE_CLASSES = "ed:Q301 ed:Q280159 ed:Q233 ed:Q303403"

PREFIXES = """
PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>
PREFIX ep:      <https://lod.enslaved.org/prop/>
PREFIX epsv:    <https://lod.enslaved.org/prop/statement/value/>
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema:  <http://schema.org/>
PREFIX skos:    <http://www.w3.org/2004/02/skos/core#>
PREFIX wikibase:<http://wikiba.se/ontology#>
"""

QUERY_A = PREFIXES + """
CONSTRUCT {{
    ?place a :Place ;
        :hasName               ?name ;
        :hasPlaceTypeCV        ?placeType ;
        :isSpatiallyLocatedIn  ?within ;
        :hasBroader            ?broader ;
        :hasAlternateName      ?altName ;
        rdfs:label             ?label ;
        skos:altLabel          ?altLabel ;
        schema:description     ?description ;
        :hasDescriptionText    ?desc ;
        :hasTemporalExtent     ?ext .
}}
WHERE {{
    {values}
    ?place edt:P1 ?placeClass .
    VALUES ?placeClass {{ {classes} }}

    OPTIONAL {{ ?place edt:P20 ?name . }}
    OPTIONAL {{ ?place edt:P8  ?placeType . }}
    OPTIONAL {{ ?place edt:P7  ?within . }}
    OPTIONAL {{ ?place edt:P74 ?broader . }}
    OPTIONAL {{ ?place edt:P71 ?altName . }}
    OPTIONAL {{ ?place rdfs:label         ?label       . FILTER(LANG(?label)       = "en") }}
    OPTIONAL {{ ?place skos:altLabel      ?altLabel    . FILTER(LANG(?altLabel)    = "en") }}
    OPTIONAL {{ ?place schema:description ?description . FILTER(LANG(?description) = "en") }}

    # IRIs must match the nodes minted by description.py and temporal_extent.py.
    OPTIONAL {{
        ?place edt:P66 ?text .
        BIND(IRI(CONCAT(STR(?place), "-desc-", MD5(STR(?text)))) AS ?desc)
    }}
    OPTIONAL {{
        ?place (edt:P28|edt:P63) ?anyDate .
        BIND(IRI(CONCAT(STR(?place), "-extent")) AS ?ext)
    }}
}}
{limit}
"""

QUERY_B = PREFIXES + """
CONSTRUCT {{
    ?place  :hasCoordinates   ?coords ;
            :hasSpatialExtent ?coords .
    ?coords a :Coordinates ;
            :hasLatitude  ?lat ;
            :hasLongitude ?lon .
}}
WHERE {{
    # Pick ONE value node per Place; lat and lon are then read from that same node,
    # so the pair always stays matched. MIN(STR) keeps the choice deterministic.
    {{
        SELECT ?place (IRI(MIN(STR(?value))) AS ?v)
        WHERE {{
            {values}
            ?place edt:P1 ?placeClass .
            VALUES ?placeClass {{ {classes} }}
            ?place ep:P59 ?st .
            FILTER NOT EXISTS {{ ?st wikibase:rank wikibase:DeprecatedRank }}
            ?st epsv:P59 ?value .
            ?value wikibase:geoLatitude [] ;
                   wikibase:geoLongitude [] .
        }}
        GROUP BY ?place
    }}
    ?v wikibase:geoLatitude  ?lat ;
       wikibase:geoLongitude ?lon .
    BIND(IRI(CONCAT(STR(?place), "-coordinates")) AS ?coords)
}}
{limit}
"""


def build_query(template: str, test: bool, limit) -> str:
    """Fill a query template with the test VALUES, Place classes and optional LIMIT."""
    return template.format(
        values=f"VALUES ?place {{ {TEST_PLACE} }}" if test else "",
        classes=PLACE_CLASSES,
        limit=f"LIMIT {limit}" if limit else "",
    )


def run_construct(endpoint: str, query: str) -> str:
    """POST a CONSTRUCT query to Fuseki and return the Turtle response."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Accept": "text/turtle",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def main() -> int:
    """Parse CLI args, run Query A and B, and write the combined Turtle output."""
    ap = argparse.ArgumentParser(description="Phase 3 :Place + :Coordinates module.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--test", action="store_true", help=f"restrict to {TEST_PLACE}")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--print-query", action="store_true")
    args = ap.parse_args()

    queries = [build_query(q, args.test, args.limit) for q in (QUERY_A, QUERY_B)]

    if args.print_query:
        print("\n".join(queries))
        return 0

    endpoint = f"{args.server.rstrip('/')}/{args.dataset}/query"
    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "place.ttl")

    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            for query in queries:
                fh.write(run_construct(endpoint, query) + "\n")
    except OSError as err:
        print(f"Query failed against {endpoint}: {err}", file=sys.stderr)
        return 1

    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
