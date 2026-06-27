# iacs

**Infrastructure as Code Sketch** — an ECS-based system for documenting and designing infrastructure.

iacs uses an Entity-Component-System framework for modeling infrastructure solutions, with Hamilton-powered dataflows for processing and auditing.

## Key Concepts

- **Entity-Centered Format**: Human-friendly EC file format for defining entities and their components.
- **Component-Centered Format (Registry)**: Internal format with one table per component type.
- **Audits**: Checks that evaluate solution quality (`RequirementCoverageAudit`, `TraceabilityAudit`, `TodoAudit`).
- **`solution of` component**: A `directed_relation` component indicating that an entity solves/fulfills a requirement.

## Navigation

- [API Reference](api/iacs.md) — auto-generated docs from source docstrings
- [Dataflow DAGs](dataflows/index.md) — visual diagrams of Hamilton dataflows
