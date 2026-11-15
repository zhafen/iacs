# how_chain (PoC)

A companion experiment to [`../why_chain`](../why_chain), run in the
opposite direction: instead of starting at one small piece of code and
asking "why" until the chain reaches emc2p's mission, this one starts at
the mission and keeps asking "how" until the chain reaches every single
`.py` file in emc2p's own package — and, one and two levels further
down, every top-level class, every top-level function, and every method
in each of those files.

## What's here

- **`how.yaml`** — defines the `how` component (`value`/`question`/`note`,
  `parent: directed_relation`, mirroring `why`) and a small tree of hand
  -written group entities: the mission at the root, five subsystems one
  level down, a handful of sub-groups under the two largest subsystems,
  and 46 `how` links down to the 34 files. None of the files, classes, or
  functions themselves are YAML entities — each is referenced by its real
  Python object, by its short alias (e.g. `emc2p.utils`,
  `testing.mcp_client_session`, `McpClientSession.send_turn`), the same
  mechanism `why_v2.yaml` used for the one method it started from. Each
  one's `description` component comes straight from its own docstring.
- **`emc2p/`** — a **vendored, frozen copy** of emc2p's whole package
  tree (34 files, same internal layout), not a live dependency — see
  `why_chain`'s README for why a frozen copy. Every class, top-level
  function, and method across those 34 files now has a docstring (88 of
  them didn't in the real repo, and needed a minimal one-line one added,
  purely so each becomes a loadable entity); every file and every class
  with children also carries its own `how` links to them, added the only
  way a Python-sourced entity can receive extra components — a numpy
  -style "Components" section inside its own docstring (emc2p's
  `load_python` parses this directly; see `emc2p/dataflows/etl/
  load_python.py`'s `_split_docstring_components`). Nothing else about
  these files was changed.
- **`graph/`** — an interactive visualization of `how.yaml`'s graph
  (`index.html` + the `data.json` it fetches): the mission at the top,
  arrows pointing straight down from whatever explains to whatever it
  explains, through subsystems and files down to the classes and
  functions that carry them out (357 nodes, up to 5 hops deep). Unlike
  `why_chain`'s viewer, no arrow-reversal or panel-swap is needed — a
  `how` link already reads top-down the way the data is stored (the
  entity asking "how" owns the link; the entity answering is its
  `value`). It's a proper collapsible tree (`d3.hierarchy`/`d3.tree`,
  the graph really is a strict tree: 357 nodes, 356 edges) rather than a
  force layout — 357 nodes all at once is unreadable, so it starts with
  only the mission shown, and clicking a node marked `+` reveals its own
  children one level at a time (click again, now marked `−`, to collapse
  it back). Searching or clicking a panel link (the question it answers,
  what it's part of, its lineage) auto-expands whatever collapsed
  ancestors stand between the current view and that node. Open
  `graph/index.html` through a local server (it fetches `data.json`
  relative to itself, e.g. `python3 -m http.server` from this directory)
  rather than as a bare `file://` page.

## Loading it yourself

```python
from emc2p.registrar import Registrar

# how.yaml needs the vendored emc2p/ tree loaded alongside it, since every
# leaf is a real Python module rather than a local YAML entity.
r = Registrar.from_manifest("poc/how_chain")
```

## Status

This is a proof of concept, kept off to the side — it isn't exercised by
iacs's test suite or referenced from its CLI/docs. Regenerate
`graph/data.json` from a fresh load of `how.yaml` (plus the vendored
`emc2p/` tree) if either changes; it's a static extract, not computed at
page-load time.
