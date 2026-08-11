# Architecture

File-level call/import structure of iacs's own codebase, parsed from source the same way `iacs.dataflows.etl.load_python` parses any project's code -- solid arrows are function/method calls, dashed arrows are imports. Only entities with a docstring or `__iacs__` metadata become graph-relevant (see that module's own docstring for why undocumented helpers are deliberately excluded); a file with none of its own still shows up if something documented elsewhere calls into it.

Regenerate with: `uv run python docs/gen_architecture_diagrams.py`

```mermaid
flowchart LR
    n0["cli"]
    n1["commands"]
    n2["config"]
    n3["report"]
    n4["requirement_coverage"]
    n5["todo"]
    n6["traceability"]
    n7["derive_components"]
    n8["impact_cost"]
    n9["inherit_components"]
    n10["resolve_paths"]
    n11["resolve_same_as"]
    n12["export_manifest"]
    n13["load_manifest"]
    n14["load_python"]
    n15["load_yaml"]
    n16["validate_components"]
    n17["etl_system"]
    n18["mcp_server"]
    n19["registrar"]
    n20["registry"]
    n21["utils"]
    n22["architecture_graph"]
    n23["requirement_tree"]
    n0 -.-> n1
    n1 --> n19
    n1 --> n22
    n1 -.-> n22
    n3 -.-> n20
    n3 --> n23
    n3 -.-> n23
    n4 -.-> n20
    n8 --> n21
    n8 -.-> n21
    n9 --> n18
    n10 --> n21
    n11 -.-> n20
    n11 --> n21
    n11 -.-> n21
    n12 -.-> n20
    n13 -.-> n20
    n13 --> n21
    n13 -.-> n21
    n18 --> n1
    n18 -.-> n1
    n19 --> n17
    n19 -.-> n17
    n19 --> n20
    n20 --> n21
    n20 -.-> n21
    n23 --> n21
    n23 -.-> n21
```
