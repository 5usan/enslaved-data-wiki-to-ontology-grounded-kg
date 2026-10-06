#!/usr/bin/env python3
"""
Phase 3 - :SexRecord  (via-reification of ep:P31, SELF-CONTAINED).

Re-types each ep:P31 sex statement as a :SexRecord, minted per attestation
<stmt>-<event>-<source> so :recordedAt / :isDirectlyBasedOn / :hasTemporalExtent stay
single-valued (mirrors name_record.py; no :isRelationshipTo, so no -<to>).
Enumerate -> chunk -> one CONSTRUCT per chunk (VALUES ?rec) to keep Fuseki within heap.

Key points (see git history / module notes for the full rationale):
  * FLAT value: eps:P31 -> :hasValue (a :SexTypes CV member, qCard 1). Copied onto each split.
  * D-SX-1: the anomalous person-node Q209311 mis-used as a sex value is folded to canonical Q296.
  * :isDirectlyBasedOn walks the reference node one more hop (?ref epr:P6 ?source).
  * :hasTemporalExtent reuses temporal_extent.py's <recordedAt-event>-extent node, dated events only.
  * NO agent-type guard by default - P31 statement nodes are sex-specific.
  * :hasSexRecord is RE-HOMED to the Agent module, which must re-derive the same record IRI.

Usage: python src/phase3/sex_record.py --dataset Enslaved-dataset [--chunk-size N]
       [--limit N] [--iri ed:Qxxx] [--print-query]   ->  out/phase3/sex_record.ttl
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

ENTITY_NS = "https://lod.enslaved.org/entity/"

# A Person carrying a P31 sex statement, for --iri shape checks (find one via
# SELECT ?s { ?s edt:P1 ed:Q410 ; ep:P31 [] } LIMIT 1).
TEST_ENTITY = "ed:Q1124931"

PREFIXES = """PREFIX :        <https://enslaved.org/ontology/>
PREFIX ed:      <https://lod.enslaved.org/entity/>
PREFIX edt:     <https://lod.enslaved.org/prop/direct/>
PREFIX ep:      <https://lod.enslaved.org/prop/>
PREFIX eps:     <https://lod.enslaved.org/prop/statement/>
PREFIX pq:      <https://lod.enslaved.org/prop/qualifier/>
PREFIX epr:     <https://lod.enslaved.org/prop/reference/>
PREFIX prov:    <http://www.w3.org/ns/prov#>
PREFIX wikibase:<http://wikiba.se/ontology#>
"""

# Distinct ep:P31 statement IRIs (the sex records). P31 nodes are sex-specific, so no type guard is
# needed; the commented VALUES enables one if V1 ever exceeds E1 (guardless picked up non-agents).
# {agent_values} optionally pins one owning agent for a shape check.
ENUMERATE = PREFIXES + """
SELECT DISTINCT ?rec WHERE {{
    # ?agent edt:P1 ?agentClass . VALUES ?agentClass {{ ed:Q410 ed:Q411 }}
    ?agent ep:P31 ?rec .
    {agent_values}
    FILTER NOT EXISTS {{ ?rec wikibase:rank wikibase:DeprecatedRank }}
}}
"""

# Per-attestation CONSTRUCT: re-types each P31 statement as a :SexRecord minted per (event, source),
# so recordedAt/source/extent are single-valued. Anchored on the bound ?rec; D-SX-1 folds Q209311->Q296.
CONSTRUCT = PREFIXES + """
CONSTRUCT {{
    ?record a :SexRecord ;
            :hasValue          ?sexValue ;
            :recordedAt        ?event ;
            :hasTemporalExtent ?temporalExtent ;
            :isDirectlyBasedOn ?source .
}}
WHERE {{
    VALUES ?rec {{ {values} }}
    FILTER NOT EXISTS {{ ?rec wikibase:rank wikibase:DeprecatedRank }}

    # D-SX-1: fold the anomalous person-node Q209311 (mis-used as a sex value) to canonical Q296.
    # To revert to the raw value, drop the IF().
    OPTIONAL {{
        ?rec eps:P31 ?rawSexValue .
        BIND(IF(?rawSexValue = ed:Q209311, ed:Q296, ?rawSexValue) AS ?sexValue)
    }}

    OPTIONAL {{ ?rec prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }}
    OPTIONAL {{
        ?rec pq:P18 ?event .
        OPTIONAL {{
            ?event edt:P28|edt:P63 ?eventDate .
            BIND(IRI(CONCAT(STR(?event), "-extent")) AS ?temporalExtent)
        }}
    }}

    BIND(IRI(CONCAT(
        STR(?rec),
        "-", COALESCE(STRAFTER(STR(?event),  "{ns}"), "noEvent"),
        "-", COALESCE(STRAFTER(STR(?source), "{ns}"), "noSource")
    )) AS ?record)
}}
"""


def build_enumerate(iri, limit) -> str:
    """Build the ENUMERATE query, optionally pinned to one owning agent (--iri) and LIMITed."""
    agent_values = f"VALUES ?agent {{ {iri} }}" if iri else ""
    query = ENUMERATE.format(agent_values=agent_values)
    return query + (f"LIMIT {limit}\n" if limit else "")


def build_construct(stmts) -> str:
    """Build the per-attestation CONSTRUCT scoped to one chunk of statement IRIs via VALUES ?rec."""
    values = " ".join(f"<{s}>" for s in stmts)
    return CONSTRUCT.format(values=values, ns=ENTITY_NS)


def post(endpoint: str, query: str, accept: str) -> str:
    """POST a SPARQL query and return the response body as text."""
    data = urllib.parse.urlencode({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={"Accept": accept, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8")


def enumerate_statements(endpoint: str, iri, limit) -> list:
    """Fetch the distinct ep:P31 statement IRIs to build records from."""
    rows = post(endpoint, build_enumerate(iri, limit), "text/tab-separated-values").splitlines()[1:]
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


def run(server: str, dataset: str, chunk_size: int, iri, limit, out_path: str) -> None:
    """Enumerate the P31 statements, CONSTRUCT them chunk by chunk, and write the joined Turtle."""
    endpoint = f"{server.rstrip('/')}/{dataset}/query"

    scope = f" (agent {iri})" if iri else ""
    print(f"Enumerating ep:P31 statements at {endpoint}{scope} ...")
    stmts = enumerate_statements(endpoint, iri, limit)
    n_chunks = (len(stmts) + chunk_size - 1) // chunk_size
    print(f"  {len(stmts)} statements; {chunk_size}/chunk -> {n_chunks} chunks")

    records = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(n_chunks):
            chunk = stmts[i * chunk_size:(i + 1) * chunk_size]
            ttl = post(endpoint, build_construct(chunk), "text/turtle")
            fh.write(ttl if i == 0 else strip_directives(ttl))
            c = ttl.count(":SexRecord")
            records += c
            print(f"  chunk {i + 1}/{n_chunks}: {len(chunk)} stmts -> +{c} records")

    print(f"wrote {out_path}  ({records} records, {os.path.getsize(out_path)} bytes)")
    print("Verify with sex_record_diagnostics.py --phase (V1-V8) once loaded.")


def main() -> int:
    """Parse CLI arguments and either print the generated SPARQL or run the chunked build."""
    ap = argparse.ArgumentParser(
        description="Phase 3 :SexRecord builder - per-attestation, chunked CONSTRUCT "
                    "(VALUES ?rec) to keep Fuseki within heap.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--chunk-size", type=int, default=1000, help="statements per CONSTRUCT chunk")
    ap.add_argument("--iri", default=None,
                    help=f"scope enumeration to one owning agent IRI for a shape check (e.g. {TEST_ENTITY})")
    ap.add_argument("--limit", type=int, default=None, help="cap statements enumerated (smoke-test)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/sex_record.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    if args.print_query:
        print(build_enumerate(args.iri, args.limit))
        print(build_construct(["https://lod.enslaved.org/entity/statement/EXAMPLE"]))
        return 0

    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "sex_record.ttl")
    run(args.server, args.dataset, args.chunk_size, args.iri, args.limit, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
