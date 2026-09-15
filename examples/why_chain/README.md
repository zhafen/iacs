# why_chain (PoC)

A proof of concept for using iacs/emc2p's entity-first manifest format to
record *design rationale* — not "what solves what" (the usual
requirement/solution pairing), but an open-ended chain of "why does this
exist" that keeps asking until it bottoms out at one shared goal.

This started as an experiment in the `emc2p` repo, but the experiment
itself — reusable, deduplicated concept entities, a component schema
(`why`) with its own fields, a graph that must converge on a single root —
is really an iacs use case: emc2p is the generic ECS engine, iacs is where
you'd actually use it to document and design something. So it moved here,
off to the side as a self-contained example rather than wired into
anything else in the repo.

## What's here

- **`why.yaml`** — the first version. Starts from one real method
  (`McpClientSession.send_turn`, described as a plain YAML entity in this
  file) and asks "why" repeatedly, up to ten hops per question, each
  answer its own standalone concept entity. Several chains end at
  different, independently-reasonable termini (a hard library constraint,
  a defensive-coding rationale, ...).
- **`why_v2.yaml`** — the second version. Same method, and now covers
  *every* object in `mcp_client_session.py` (the module, the class, and
  all 18 functions/methods) rather than just `send_turn`. Every chain is
  pushed further so it ends **only** at one entity, `emc2p_mission` — a
  handful of reusable hub concepts absorb what would otherwise be
  separate dead ends. Unlike `why.yaml`, the objects being explained
  aren't YAML entities at all: each one's `description` component comes
  from its own real Python docstring, loaded the same way any other
  Python object in an emc2p-based project would be.
- **`mcp_client_session.py`** — a **vendored, frozen copy**, not a live
  dependency. iacs pins its own `emc2p` version in `pyproject.toml`
  (currently older than the docstring additions this file needed — 11 of
  its 19 objects had no docstring at all before this experiment added
  one to each, which is what makes them loadable entities in the first
  place). Keeping a frozen copy here means this example stays loadable
  without iacs's real `emc2p` pin ever needing to move. `why_v2.yaml`
  references each object by its short alias (e.g.
  `McpClientSession.send_turn`), not a full dotted path, so the
  reference survives regardless of exactly where this copy sits.
- **`graph/`** — an interactive visualization of `why_v2.yaml`'s graph
  (`index.html` + the `data.json` it fetches): the mission at the root,
  arrows pointing from whatever needs explaining to whatever explains it,
  converging upward. Click a node to trace its chain to the mission and
  see the question(s) it raised and who answers them. Open
  `graph/index.html` through a local server (it fetches `data.json`
  relative to itself, e.g. `python3 -m http.server` from this directory)
  rather than as a bare `file://` page.

## Loading it yourself

```python
from emc2p.registrar import Registrar

# why.yaml is fully self-contained
r1 = Registrar.from_manifest("examples/why_chain/why.yaml")

# why_v2.yaml needs the vendored Python file loaded alongside it
r2 = Registrar.from_manifest([
    "examples/why_chain/why_v2.yaml",
    "examples/why_chain/mcp_client_session.py",
])
```

## Status

This is a proof of concept, kept off to the side — it isn't exercised by
iacs's test suite or referenced from its CLI/docs. Regenerate
`graph/data.json` from a fresh load of `why_v2.yaml` if the manifest
changes; it's a static extract, not computed at page-load time.
