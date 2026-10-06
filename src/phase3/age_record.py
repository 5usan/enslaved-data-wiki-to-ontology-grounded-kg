#!/usr/bin/env python3
"""
Phase 3 - :AgeRecord  (via-reification of ep:P42, SELF-CONTAINED).

Re-types each ep:P42 age statement as an :AgeRecord, minted per attestation
<stmt>-<event>-<source> so :recordedAt / :isDirectlyBasedOn / :hasTemporalExtent stay
single-valued (mirrors name_record.py; no :isRelationshipTo, so no -<to>).
Enumerate -> chunk -> one CONSTRUCT per chunk (VALUES ?rec) to keep Fuseki within heap.

Key points (see git history / module notes for the full rationale):
  * VALUE INDIRECTION: eps:P42 -> shared "N years old" container (Q424); edt:P3 -> :hasAgeValue,
    edt:P4 -> :hasValue (an :AgeCategory CV member). Copied onto each split record.
  * :isDirectlyBasedOn walks the reference node one more hop (?ref epr:P6 ?source).
  * :hasTemporalExtent reuses temporal_extent.py's <event>-extent node, dated events only.
  * NO agent-type guard by default - P42 statement nodes are age-specific (unlike shared P20).
  * :hasAgeRecord is RE-HOMED to the Agent module, which must re-derive the same record IRI.

Usage: python src/phase3/age_record.py --dataset Enslaved-dataset [--chunk-size N]
       [--limit N] [--iri ed:Qxxx] [--print-query]   ->  out/phase3/age_record.ttl
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

ENTITY_NS = "https://lod.enslaved.org/entity/"

# A Person carrying a P42 age statement, for --iri shape checks (find one via
# SELECT ?s { ?s edt:P1 ed:Q410 ; ep:P42 [] } LIMIT 1).
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

# Distinct ep:P42 statement IRIs (the age records). P42 nodes are age-specific, so no type
# guard is needed; the commented VALUES enables one if E2 ever shows P42 on non-agents.
# {agent_values} optionally pins one owning agent for a shape check.
ENUMERATE = PREFIXES + """
SELECT DISTINCT ?rec WHERE {{
    # ?agent edt:P1 ?agentClass . VALUES ?agentClass {{ ed:Q410 ed:Q411 }}
    ?agent ep:P42 ?rec .
    {agent_values}
    FILTER NOT EXISTS {{ ?rec wikibase:rank wikibase:DeprecatedRank }}
}}
"""

# Per-attestation CONSTRUCT: re-types each P42 statement as an :AgeRecord minted per
# (event, source), so recordedAt/source/extent are single-valued. Anchored on the bound
# ?rec; the value-indirection / reference-hop / extent idioms are documented in the docstring.
CONSTRUCT = PREFIXES + """
CONSTRUCT {{
    ?record a :AgeRecord ;
            :hasAgeValue       ?ageValue ;
            :hasValue          ?ageCategory ;
            :recordedAt        ?event ;
            :hasTemporalExtent ?temporalExtent ;
            :isDirectlyBasedOn ?source .
}}
WHERE {{
    VALUES ?rec {{ {values} }}
    FILTER NOT EXISTS {{ ?rec wikibase:rank wikibase:DeprecatedRank }}

    OPTIONAL {{
        ?rec eps:P42 ?ageItem .
        OPTIONAL {{ ?ageItem edt:P3 ?ageValue . }}
        OPTIONAL {{ ?ageItem edt:P4 ?ageCategory . }}
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
    """Fetch the distinct ep:P42 statement IRIs to build records from."""
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
    """Enumerate the P42 statements, CONSTRUCT them chunk by chunk, and write the joined Turtle."""
    endpoint = f"{server.rstrip('/')}/{dataset}/query"

    scope = f" (agent {iri})" if iri else ""
    print(f"Enumerating ep:P42 statements at {endpoint}{scope} ...")
    stmts = enumerate_statements(endpoint, iri, limit)
    n_chunks = (len(stmts) + chunk_size - 1) // chunk_size
    print(f"  {len(stmts)} statements; {chunk_size}/chunk -> {n_chunks} chunks")

    records = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(n_chunks):
            chunk = stmts[i * chunk_size:(i + 1) * chunk_size]
            ttl = post(endpoint, build_construct(chunk), "text/turtle")
            fh.write(ttl if i == 0 else strip_directives(ttl))
            c = ttl.count(":AgeRecord")
            records += c
            print(f"  chunk {i + 1}/{n_chunks}: {len(chunk)} stmts -> +{c} records")

    print(f"wrote {out_path}  ({records} records, {os.path.getsize(out_path)} bytes)")
    print("Verify with age_record_diagnostics.py --phase (V1-V7) once loaded.")


def main() -> int:
    """Parse CLI arguments and either print the generated SPARQL or run the chunked build."""
    ap = argparse.ArgumentParser(
        description="Phase 3 :AgeRecord builder - per-attestation, chunked CONSTRUCT "
                    "(VALUES ?rec) to keep Fuseki within heap.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--chunk-size", type=int, default=1000, help="statements per CONSTRUCT chunk")
    ap.add_argument("--iri", default=None,
                    help=f"scope enumeration to one owning agent IRI for a shape check (e.g. {TEST_ENTITY})")
    ap.add_argument("--limit", type=int, default=None, help="cap statements enumerated (smoke-test)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/age_record.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    if args.print_query:
        print(build_enumerate(args.iri, args.limit))
        print(build_construct(["https://lod.enslaved.org/entity/statement/EXAMPLE"]))
        return 0

    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "age_record.ttl")
    run(args.server, args.dataset, args.chunk_size, args.iri, args.limit, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
