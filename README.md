# Wiki-based KG → Ontology-grounded KG

Converts the Enslaved.org Wikibase RDF dump into a graph expressed in the Enslaved
Ontology, using SPARQL `CONSTRUCT` queries run with Apache Jena.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the approach and phase breakdown.

## Layout

```
data/                 gitignored — 6.7 GB of source data
  raw/
    enslaved_dump.rdf   the original 3.3 GB Wikibase dump
    chunks/             chunk_0.ttl .. chunk_22.ttl, the dump split for loading

ontology/             the target ontology and terms extracted from it
  enslaved-v2.ttl       46 classes, 52 object properties, 19 datatype properties
  ontology-classes.txt
  ontology-properties.csv
  enslaved_image.png    module diagram (matches opla:isNativeTo grouping)

mappings/             wiki → ontology mapping tables (phases 1–2)
  mapping-classes.csv               raw, from phase 1
  mapping-properties.csv
  mapping-classes-reconciled.csv    bucketed KEEP/CV_INDIVIDUAL/DROP/REVIEW, phase 2
  mapping-properties-reconciled.csv
  coverage-gaps.csv                 ontology terms with no wiki source

src/                  all code
  paths.py              canonical project paths — every script imports from here
  phase1/phase1.py      extract the mapping from a loaded Fuseki dataset
  phase2/phase2.py      reconcile wiki labels against the ontology
  phase2/coverage_report.py
  phase3/*.py           one CONSTRUCT builder per ontology module

out/                  gitignored — regenerate by re-running the scripts
  phase3/*.ttl          CONSTRUCT results, one per module
```

## Running

The phase scripts query a running Fuseki endpoint with the chunks already loaded:

```bash
python src/phase1/phase1.py --server http://localhost:3030 --dataset Enslaved-dataset
python src/phase2/phase2.py
python src/phase2/coverage_report.py
python src/phase3/age_record.py            # writes out/phase3/age_record.ttl
```

Every script is standard-library only and resolves its input/output directories through
`src/paths.py`, so they can be run from any working directory. Pass `--out` to a phase 3
script to override its output location.
