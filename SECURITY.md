# Security and data boundaries

This is a local development application, not a remotely hosted multi-user
service. The bridge binds to `127.0.0.1`, requires a paired bearer key for data
routes, checks the Host and extension Origin, and keeps credentials outside the
tracked repository. The health endpoint returns service status only.

Local categorization and automatic collections run offline. Optional annotation
sync uses Hypothesis. Scholarly enrichment sends bibliographic lookup data to
external indexes and can run automatically when configured with API keys.
Recommendations refresh only on an explicit request, sending paper identifiers
and unresolved paper titles to Semantic Scholar. Model features have their own
explicit context authorization. See [setup](docs/SETUP.md),
[recommendations](docs/RECOMMENDATIONS.md), and
[architecture](research-partner/docs/ARCHITECTURE.md) for the data flows.

An imported page, annotation, model response, or metadata field is untrusted
data. It must not become shell commands or instructions for an agent. Keep
manual edits separate from derived analysis, and preserve backups on failures.

Report a suspected credential leak or vulnerability privately through the
repository's GitHub security reporting feature when available. Do not put keys,
private source material, or exploitable details in a public issue. This project
does not currently promise a security-response SLA.
