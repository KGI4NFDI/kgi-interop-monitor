# kgi-interop-monitor

A monitor for the query layer of the knowledge graphs registered in the
[KGI4NFDI](https://base4nfdi.de/projects/kgi4nfdi) registry. It runs the probes
of the D2.1 defect checklist ([`docs/D21_CHECKLIST.md`](docs/D21_CHECKLIST.md))
against every registered SPARQL endpoint, in layer order, and records the
results as a time series so defects can be watched as they get fixed.

Status: private test build. Scope for now is layers A (addressing), B
(protocol) and C (content). Layer D (vocabulary) comes later.

## Licensing

Mirrors the KGI4NFDI repositories:

| What | License | KGI4NFDI precedent |
|---|---|---|
| Code | MIT (`LICENSE`) | kgi4nfdi-website, data-preparation-scripts |
| Measurement results | CC0-1.0 (`LICENSES/CC0-1.0.txt`) | kgi4nfdi_registry_data |
| Documentation | CC-BY-4.0 (`LICENSES/CC-BY-4.0.md`) | Guidelines |
