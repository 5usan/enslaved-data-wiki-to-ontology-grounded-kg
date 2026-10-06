#!/usr/bin/env python3
"""
Phase 3 - :InterAgentRelationshipRecord

De-reified P39 relationship statements, minted per attestation as
<stmt>-<event>-<source>-<to> so :isRelationshipTo / :recordedAt / :isDirectlyBasedOn
each stay single-valued on a record.

pq:P40 is required: P39's value CV (Q457) is shared with PersonStatus (P33) and
ParticipantRole (P29), so a P39 statement is a genuine inter-agent relationship only
when it also names a second agent via pq:P40. Statements without one are not emitted.

Built by enumerating the qualifying statements, chunking them, and running one
CONSTRUCT per chunk scoped by VALUES ?stmt - a single full-dump CONSTRUCT makes Fuseki
materialise the whole result graph in heap and OOMs. A record derives entirely from one
statement, so no record spans a chunk and the chunk outputs simply concatenate.

Usage (from repo root, Fuseki serving the dump):
    python src/phase3/inter_agent_relationship.py --dataset Enslaved-dataset
    python src/phase3/inter_agent_relationship.py --dataset Enslaved-dataset --chunk-size 1000
    python src/phase3/inter_agent_relationship.py --dataset Enslaved-dataset --limit 200
    python src/phase3/inter_agent_relationship.py --print-query
Writes out/phase3/inter_agent_relationship.ttl. Standard library only.
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

ENTITY_NS = "https://lod.enslaved.org/entity/"

PREFIXES = """PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX eds:     <https://lod.enslaved.org/entity/statement/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>
PREFIX ep:      <https://lod.enslaved.org/prop/>
PREFIX eps:     <https://lod.enslaved.org/prop/statement/>
PREFIX pq:      <https://lod.enslaved.org/prop/qualifier/>
PREFIX epr:     <https://lod.enslaved.org/prop/reference/>
PREFIX prov:    <http://www.w3.org/ns/prov#>
PREFIX wikibase:<http://wikiba.se/ontology#>
"""

ENUMERATE = PREFIXES + """
SELECT DISTINCT ?stmt WHERE {
    ?stmt eps:P39 ?type .
    ?stmt pq:P40  ?to .
    FILTER NOT EXISTS { ?stmt wikibase:rank wikibase:DeprecatedRank }
}
"""

CONSTRUCT = PREFIXES + """
CONSTRUCT {{
    ?record  a  :InterAgentRelationshipRecord ;
             :isRelationshipFrom            ?from ;
             :isRelationshipTo              ?to ;
             :hasInterAgentRelationshipType ?type ;
             :isDirectlyBasedOn             ?source ;
             :recordedAt                    ?event ;
             :hasTemporalExtent             ?temporalExtent .
}}
WHERE {{
    VALUES ?stmt {{ {values} }}
    ?from ep:P39  ?stmt .
    ?stmt eps:P39 ?type .
    ?stmt pq:P40  ?to .
    FILTER NOT EXISTS {{ ?stmt wikibase:rank wikibase:DeprecatedRank }}

    OPTIONAL {{ ?stmt prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }}
    OPTIONAL {{
        ?stmt pq:P18 ?event .
        OPTIONAL {{
            ?event edt:P28|edt:P63 ?eventDate .
            BIND(IRI(CONCAT(STR(?event), "-extent")) AS ?temporalExtent)
        }}
    }}

    # after the OPTIONALs, so ?event/?source are bound; COALESCE covers their absence
    BIND(IRI(CONCAT(
        STR(?stmt),
        "-", COALESCE(STRAFTER(STR(?event),  "{ns}"), "noEvent"),
        "-", COALESCE(STRAFTER(STR(?source), "{ns}"), "noSource"),
        "-", STRAFTER(STR(?to), "{ns}")
    )) AS ?record)
}}
"""


def build_construct(stmts) -> str:
    """Return the per-attestation CONSTRUCT scoped to this chunk of statement IRIs via VALUES ?stmt."""
    values = " ".join(f"<{s}>" for s in stmts)
    return CONSTRUCT.format(values=values, ns=ENTITY_NS)


def post(endpoint: str, query: str, accept: str) -> str:
    """POST a SPARQL query to the endpoint and return the response body as text."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Accept": accept, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def enumerate_statements(endpoint: str, limit) -> list:
    """Fetch the distinct P39 statement IRIs that carry a pq:P40 to-agent (the qualifying dyads)."""
    query = ENUMERATE + (f"LIMIT {limit}\n" if limit else "")
    rows = post(endpoint, query, "text/tab-separated-values").splitlines()[1:]
    return [r[1:-1] for r in rows if r.startswith("<") and r.endswith(">")]


def strip_directives(ttl: str) -> str:
    """Drop leading @prefix/@base/PREFIX/BASE lines so a chunk appends under the first chunk's header."""
    lines = ttl.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s.startswith(("@prefix", "@base")) or s.upper().startswith(("PREFIX ", "BASE ")):
            i += 1
        else:
            break
    return "".join(lines[i:])


def run(server: str, dataset: str, chunk_size: int, limit, out_path: str) -> None:
    """Enumerate the qualifying statements, CONSTRUCT them chunk by chunk, and write the joined Turtle."""
    endpoint = f"{server.rstrip('/')}/{dataset}/query"

    print(f"Enumerating P39 statements with pq:P40 at {endpoint} ...")
    stmts = enumerate_statements(endpoint, limit)
    n_chunks = (len(stmts) + chunk_size - 1) // chunk_size
    print(f"  {len(stmts)} statements; {chunk_size}/chunk -> {n_chunks} chunks")

    records = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(n_chunks):
            chunk = stmts[i * chunk_size:(i + 1) * chunk_size]
            ttl = post(endpoint, build_construct(chunk), "text/turtle")
            fh.write(ttl if i == 0 else strip_directives(ttl))
            c = ttl.count(":InterAgentRelationshipRecord")
            records += c
            print(f"  chunk {i + 1}/{n_chunks}: {len(chunk)} stmts -> +{c} records")

    print(f"wrote {out_path}  ({records} records, {os.path.getsize(out_path)} bytes)")
    print("Verify with inter_agent_relationship_diagnostics.py --phase (q8-q13) once loaded.")


def main() -> int:
    """Parse CLI arguments and either print the generated SPARQL or run the chunked build."""
    ap = argparse.ArgumentParser(
        description="Phase 3 :InterAgentRelationshipRecord builder - chunked CONSTRUCT "
                    "(VALUES ?stmt) to keep Fuseki within heap.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--chunk-size", type=int, default=1000, help="statements per CONSTRUCT chunk")
    ap.add_argument("--limit", type=int, default=None, help="cap statements enumerated (smoke-test)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/inter_agent_relationship.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    if args.print_query:
        print(ENUMERATE)
        print(build_construct(["https://lod.enslaved.org/entity/statement/EXAMPLE"]))
        return 0

    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "inter_agent_relationship.ttl")
    run(args.server, args.dataset, args.chunk_size, args.limit, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
