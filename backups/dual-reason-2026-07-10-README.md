# Dual Reason backup

- Created: 2026-07-10
- Base commit: `df65d0e`
- Working branch: `codex/micm-extraction`
- Purpose: preserve the dual Reason implementation before any GitHub commit or push.

The original reason remains in `begründung`. The added auditable reason is stored
in `supplemental_reason`.

To discard the working implementation, restore the four modified source files to
base commit `df65d0e`. To reapply it later, use the adjacent patch as a reference.
