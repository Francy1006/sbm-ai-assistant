<!-- managed-by: SBM-SUITE/context/scripts/suite-artifacts.py -->
# Transversal governance contract

This repository participates in the governance workflows controlled from
`SBM-SUITE/context`.

- Physical repository inventory is discovered by `scripts/suite-repositories.py`
  in the Context control plane.
- Multi-repository Git mutations are initiated only from `SBM-SUITE/context`.
- `main` is the only stable and final integration branch.
- Every `FEATURE-*`, `BUGFIX-*`, `RELEASE-*` and `HOTFIX-*` branch starts from
  synchronized `main` and merges with `--no-ff` directly into `main`.
- Every 1..N objective batch requires complete suite QA and updated
  Documentation before finalization, including fast-track lifecycle changes.
- Finalization checks out and pushes `main`, then deletes the temporary branch
  locally and remotely after a global preflight.
- Project-specific Context and QA content remains owned by this repository and
  must not be overwritten by transversal propagation.

This file is managed as a complete common artifact. Update its declared source
in `SBM-SUITE/context`, inspect with `suite-artifacts.py check`, and propagate
with an explicit `suite-artifacts.py apply` operation.
