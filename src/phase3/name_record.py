#!/usr/bin/env python3
"""
Phase 3 - :NameRecord / :NameVariant  (via-reification of ep:P20, SELF-CONTAINED).

Re-types each agent-owned ep:P20 name statement as a :NameRecord, minted per attestation
<stmt>-<event>-<source> so :recordedAt / :isDirectlyBasedOn / :hasTemporalExtent stay
single-valued (mirrors inter_agent_relationship.py; no :isRelationshipTo, so no -<to>).
Enumerate -> chunk -> one CONSTRUCT per chunk (VALUES ?nr) to keep Fuseki within heap.

Key points (see git history / module notes for the full rationale):
  * AGENT GUARD (edt:P1 Q410|Q411) applied in ENUMERATE only - P20 is shared with
    Event/Place; the CONSTRUCT trusts the enumerated set and stays ?nr-keyed for speed.
  * :isDirectlyBasedOn walks the reference node one more hop (?ref epr:P6 ?source).
  * :hasTemporalExtent reuses temporal_extent.py's <event>-extent node, dated events only.
  * VARIANTs only for multi-name agents (>=1 P71); BINDs at outer scope, keyed to ?record.
  * :hasNameRecord is RE-HOMED to the Agent module, which must re-derive the same record IRI.

Usage: python src/phase3/name_record.py --dataset Enslaved-dataset [--chunk-size N]
       [--limit N] [--iri ed:Qxxx] [--print-query]   ->  out/phase3/name_record.ttl
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

ENTITY_NS = "https://lod.enslaved.org/entity/"

# A known Person carrying P20 + P73 + P72 (E5: "James Alexander"), for --iri shape checks.
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
PREFIX rdfs:    <http://www.w3.org/2000/01/rdf-schema#>
"""

# Distinct ep:P20 statement IRIs owned by a Q410/Q411 agent; the agent guard scopes P20
# away from its Event/Place uses. {agent_values} optionally pins one agent for a shape check.
ENUMERATE = PREFIXES + """
SELECT DISTINCT ?nr WHERE {{
    ?agent edt:P1 ?agentClass .
    VALUES ?agentClass {{ ed:Q410 ed:Q411 }}
    {agent_values}
    ?agent ep:P20  ?nr .
    ?nr    eps:P20 ?fullName .
    FILTER NOT EXISTS {{ ?nr wikibase:rank wikibase:DeprecatedRank }}
}}
"""

# Per-attestation CONSTRUCT: re-types each P20 statement as a :NameRecord minted per
# (event, source), so recordedAt/source/extent are single-valued. The agent guard and
# the reference-hop / extent / variant idioms are documented in the module docstring.
CONSTRUCT = PREFIXES + """
CONSTRUCT {{
    ?record  a  :NameRecord ;
             :fullNameAsString        ?fullName ;
             :hasFirstNameAsString    ?firstName ;
             :hasSurnameAsString      ?surname ;
             :recordedAt              ?event ;
             :hasTemporalExtent       ?temporalExtent ;
             :isDirectlyBasedOn       ?source ;
             :hasPreferredNameVariant ?prefVar ;
             :hasNameVariant          ?prefVar , ?altVar .
    ?prefVar a :NameVariant ; rdfs:label ?fullName .
    ?altVar  a :NameVariant ; rdfs:label ?altName .
}}
WHERE {{
    VALUES ?nr {{ {values} }}

    # ENUMERATE already restricted ?nr to agent-owned P20 statements, so the edt:P1 type
    # guard is omitted here - re-applying it would force a full agent scan per chunk.
    ?agent ep:P20  ?nr .
    ?nr    eps:P20 ?fullName .
    FILTER NOT EXISTS {{ ?nr wikibase:rank wikibase:DeprecatedRank }}

    OPTIONAL {{ ?nr prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }}
    OPTIONAL {{
        ?nr pq:P18 ?event .
        OPTIONAL {{
            ?event edt:P28|edt:P63 ?eventDate .
            BIND(IRI(CONCAT(STR(?event), "-extent")) AS ?temporalExtent)
        }}
    }}
    OPTIONAL {{ ?agent edt:P73 ?firstName . }}
    OPTIONAL {{ ?agent edt:P72 ?surname . }}

    BIND(IRI(CONCAT(
        STR(?nr),
        "-", COALESCE(STRAFTER(STR(?event),  "{ns}"), "noEvent"),
        "-", COALESCE(STRAFTER(STR(?source), "{ns}"), "noSource")
    )) AS ?record)

    OPTIONAL {{ ?agent edt:P71 ?altName . }}
    BIND(IF(BOUND(?altName), IRI(CONCAT(STR(?record), "-pref")), ?unboundPref) AS ?prefVar)
    BIND(IF(BOUND(?altName), IRI(CONCAT(STR(?record), "-nv-", MD5(STR(?altName)))), ?unboundAlt) AS ?altVar)
}}
"""


def build_enumerate(iri, limit) -> str:
    """Build the ENUMERATE query, optionally pinned to one agent (--iri) and LIMITed."""
    agent_values = f"VALUES ?agent {{ {iri} }}" if iri else ""
    query = ENUMERATE.format(agent_values=agent_values)
    return query + (f"LIMIT {limit}\n" if limit else "")


def build_construct(stmts) -> str:
    """Build the per-attestation CONSTRUCT scoped to one chunk of statement IRIs via VALUES ?nr."""
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
    """Fetch the distinct agent-owned ep:P20 statement IRIs to build records from."""
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
    """Enumerate the qualifying statements, CONSTRUCT them chunk by chunk, and write the joined Turtle."""
    endpoint = f"{server.rstrip('/')}/{dataset}/query"

    scope = f" (agent {iri})" if iri else ""
    print(f"Enumerating agent ep:P20 statements at {endpoint}{scope} ...")
    stmts = enumerate_statements(endpoint, iri, limit)
    n_chunks = (len(stmts) + chunk_size - 1) // chunk_size
    print(f"  {len(stmts)} statements; {chunk_size}/chunk -> {n_chunks} chunks")

    records = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(n_chunks):
            chunk = stmts[i * chunk_size:(i + 1) * chunk_size]
            ttl = post(endpoint, build_construct(chunk), "text/turtle")
            fh.write(ttl if i == 0 else strip_directives(ttl))
            c = ttl.count(":NameRecord")
            records += c
            print(f"  chunk {i + 1}/{n_chunks}: {len(chunk)} stmts -> +{c} records")

    print(f"wrote {out_path}  ({records} records, {os.path.getsize(out_path)} bytes)")
    print("Verify with name_record_diagnostics.py --phase (V1-V9) once loaded.")


def main() -> int:
    """Parse CLI arguments and either print the generated SPARQL or run the chunked build."""
    ap = argparse.ArgumentParser(
        description="Phase 3 :NameRecord builder - per-attestation, chunked CONSTRUCT "
                    "(VALUES ?nr) to keep Fuseki within heap.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--chunk-size", type=int, default=1000, help="statements per CONSTRUCT chunk")
    ap.add_argument("--iri", default=None,
                    help=f"scope enumeration to one agent IRI for a shape check (e.g. {TEST_ENTITY})")
    ap.add_argument("--limit", type=int, default=None, help="cap statements enumerated (smoke-test)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/name_record.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    if args.print_query:
        print(build_enumerate(args.iri, args.limit))
        print(build_construct(["https://lod.enslaved.org/entity/statement/EXAMPLE"]))
        return 0

    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "name_record.ttl")
    run(args.server, args.dataset, args.chunk_size, args.iri, args.limit, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
