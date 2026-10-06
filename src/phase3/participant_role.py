#!/usr/bin/env python3
"""
Phase 3 - :ParticipantRoleRecord  (reified ep:P29, SELF-CONTAINED / NODES-ONLY).

Splits each ep:P29 statement into per-(agent, source) :ParticipantRoleRecord nodes, minted
<stmt>-<agent>-<source> so the one owning agent and :isDirectlyBasedOn stay single-valued
(mirrors name_record.py; :recordedAt / :hasTemporalExtent come from the PROVIDER event, always
single). Enumerate -> chunk -> one CONSTRUCT per chunk (VALUES ?stmt) to keep Fuseki within heap
(the old full-dump build produced a ~324MB result graph).

Key points (see git history / module notes for the full rationale):
  * SPLIT per pq:P17 agent - AgentRecord forces exactly one owning agent per record.
  * role value = eps:P29, guarded on the value's edt:P1 in {Q316, Q351} -> :hasParticipantRoleType.
  * :recordedAt = the PROVIDER Event (pq:P18 near-absent on P29); :hasTemporalExtent = <provider>-extent,
    emitted only for dated providers.
  * :isDirectlyBasedOn walks the reference node one more hop (?ref epr:P6 ?source); the source split
    single-values it.
  * NODES-ONLY: :providesParticipantRole (Event module) and :hasParticipantRoleRecord (Agent module)
    are RE-HOMED and must re-derive the same <stmt>-<agent>-<source> IRI.
  * --events-only mints only Event (Q238) provider records - the SHACL-safe subset.

Usage: python src/phase3/participant_role.py --dataset Enslaved-dataset [--events-only]
       [--chunk-size N] [--limit N] [--iri ed:Qxxx] [--print-query]
       ->  out/phase3/participant_role.ttl
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import OUT_PHASE3, ensure  # noqa: E402

ENTITY_NS = "https://lod.enslaved.org/entity/"

# A provider (Q358) whose P29 statement carries many pq:P17 agents, for --iri shape checks.
TEST_PROVIDER = "ed:Q358"

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

EVENTS_GUARD = "    ?provider edt:P1 ed:Q238 .\n"

# Distinct ep:P29 statement IRIs that carry a role value (of class Q316/Q351) and >=1 pq:P17 agent.
# {provider_values} optionally pins one provider for a shape check; {events_guard} restricts to
# Event (Q238) providers for --events-only.
ENUMERATE = PREFIXES + """
SELECT DISTINCT ?stmt WHERE {{
    ?provider ep:P29  ?stmt .
    {provider_values}
    ?stmt     eps:P29 ?roleType .
    ?roleType edt:P1  ?roleTypeClass .
    VALUES ?roleTypeClass {{ ed:Q316 ed:Q351 }}
    ?stmt     pq:P17  ?agent .
    FILTER NOT EXISTS {{ ?stmt wikibase:rank wikibase:DeprecatedRank }}
{events_guard}}}
"""

# Per-attestation CONSTRUCT: one record per (agent, source), minted <stmt>-<agent>-<source>.
# All patterns are keyed off the bound ?stmt; recordedAt/extent come from the single provider event.
CONSTRUCT = PREFIXES + """
CONSTRUCT {{
    ?record a :ParticipantRoleRecord ;
            :hasParticipantRoleType ?roleType ;
            :roleProvidedBy         ?agent ;
            :recordedAt             ?provider ;
            :isDirectlyBasedOn      ?source ;
            :hasTemporalExtent      ?temporalExtent .
}}
WHERE {{
    VALUES ?stmt {{ {values} }}
    ?provider ep:P29  ?stmt .
    ?stmt     eps:P29 ?roleType .
    ?roleType edt:P1  ?roleTypeClass .
    VALUES ?roleTypeClass {{ ed:Q316 ed:Q351 }}
    ?stmt     pq:P17  ?agent .
    FILTER NOT EXISTS {{ ?stmt wikibase:rank wikibase:DeprecatedRank }}

    OPTIONAL {{
        ?provider edt:P28|edt:P63 ?extentDate .
        BIND(IRI(CONCAT(STR(?provider), "-extent")) AS ?temporalExtent)
    }}
    OPTIONAL {{ ?stmt prov:wasDerivedFrom ?ref . ?ref epr:P6 ?source . }}

    BIND(IRI(CONCAT(
        STR(?stmt),
        "-", STRAFTER(STR(?agent), "{ns}"),
        "-", COALESCE(STRAFTER(STR(?source), "{ns}"), "noSource")
    )) AS ?record)
}}
"""


def build_enumerate(iri, events_only, limit) -> str:
    """Build the ENUMERATE query, optionally pinned to one provider (--iri), Event-only, and LIMITed."""
    provider_values = f"VALUES ?provider {{ {iri} }}" if iri else ""
    events_guard = EVENTS_GUARD if events_only else ""
    query = ENUMERATE.format(provider_values=provider_values, events_guard=events_guard)
    return query + (f"LIMIT {limit}\n" if limit else "")


def build_construct(stmts) -> str:
    """Build the per-attestation CONSTRUCT scoped to one chunk of statement IRIs via VALUES ?stmt."""
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


def enumerate_statements(endpoint: str, iri, events_only, limit) -> list:
    """Fetch the distinct qualifying ep:P29 statement IRIs to split into records."""
    rows = post(endpoint, build_enumerate(iri, events_only, limit),
                "text/tab-separated-values").splitlines()[1:]
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


def run(server: str, dataset: str, chunk_size: int, iri, events_only, limit, out_path: str) -> None:
    """Enumerate the P29 statements, CONSTRUCT them chunk by chunk, and write the joined Turtle."""
    endpoint = f"{server.rstrip('/')}/{dataset}/query"

    scope = f" (provider {iri})" if iri else (" (events-only)" if events_only else "")
    print(f"Enumerating ep:P29 statements at {endpoint}{scope} ...")
    stmts = enumerate_statements(endpoint, iri, events_only, limit)
    n_chunks = (len(stmts) + chunk_size - 1) // chunk_size
    print(f"  {len(stmts)} statements; {chunk_size}/chunk -> {n_chunks} chunks")

    records = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(n_chunks):
            chunk = stmts[i * chunk_size:(i + 1) * chunk_size]
            ttl = post(endpoint, build_construct(chunk), "text/turtle")
            fh.write(ttl if i == 0 else strip_directives(ttl))
            c = ttl.count(":ParticipantRoleRecord")
            records += c
            print(f"  chunk {i + 1}/{n_chunks}: {len(chunk)} stmts -> +{c} records")

    print(f"wrote {out_path}  ({records} records, {os.path.getsize(out_path)} bytes)")
    print("Verify with participant_role_diagnostics.py --phase (Q6-Q9) once loaded.")


def main() -> int:
    """Parse CLI arguments and either print the generated SPARQL or run the chunked build."""
    ap = argparse.ArgumentParser(
        description="Phase 3 :ParticipantRoleRecord builder - per-(agent,source) split, chunked "
                    "CONSTRUCT (VALUES ?stmt) to keep Fuseki within heap.")
    ap.add_argument("--server", default="http://localhost:3030")
    ap.add_argument("--dataset", default="Enslaved-dataset")
    ap.add_argument("--chunk-size", type=int, default=1000, help="statements per CONSTRUCT chunk")
    ap.add_argument("--events-only", action="store_true",
                    help="mint only records from Event (Q238) providers - the subset whose re-homed "
                         "inverse(providesParticipantRole) can satisfy the exactly-1-Event constraint")
    ap.add_argument("--iri", default=None,
                    help=f"scope enumeration to one provider IRI for a shape check (e.g. {TEST_PROVIDER})")
    ap.add_argument("--limit", type=int, default=None, help="cap statements enumerated (smoke-test)")
    ap.add_argument("--out", default=None,
                    help="output .ttl path (default out/phase3/participant_role.ttl)")
    ap.add_argument("--print-query", action="store_true", help="print generated SPARQL and exit")
    args = ap.parse_args()

    if args.print_query:
        print(build_enumerate(args.iri, args.events_only, args.limit))
        print(build_construct(["https://lod.enslaved.org/entity/statement/EXAMPLE"]))
        return 0

    out_path = args.out or os.path.join(ensure(OUT_PHASE3), "participant_role.ttl")
    run(args.server, args.dataset, args.chunk_size, args.iri, args.events_only, args.limit, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
