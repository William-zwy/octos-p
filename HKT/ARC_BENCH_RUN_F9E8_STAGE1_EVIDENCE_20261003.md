# ArcBench evidence — f9e8bbdae929

- Task: `hackathon--github-stage-1`; submission: `3492f270f204`
- Agent commit: `8c90fe91d615ccd4de35a88eaad1948bf2caaf6c`
- ZIP SHA-256: `22E261919531D428C7155CE57213450736AE78721ABA7A5AEA1B62DAFA7B8842`
- Result: deployment readiness failure; official tests did not run (`0/0` is not a test score).
- Failure class: `deployment_http_readiness`; confidence: high.

## Decision

The previous `mark_implementation_ready` compatibility patch is retained. f9e8 generated all
12 nodes and failed later at application readiness, so the patch did not cause this failure.
The next high-value guard is to make rehearsal repair evidence-based: the repair prompt now
requires the exact build, start, and same-process `curl` checks for `/` and `/api/health`,
and forbids claiming repair without observed responses. A root response must be non-blocking;
slow initialization cannot block the request path.

This does not infer hidden test IDs and does not treat server port binding as HTTP readiness.
