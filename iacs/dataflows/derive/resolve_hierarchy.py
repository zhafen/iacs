import networkx as nx
import pandas as pd
from hamilton.function_modifiers import extract_fields
import ibis
import ibis.expr.types as ir

from iacs.registry import Registry
from iacs.utils import candidate_entity_ids, dhash

@extract_fields(dict(entity_id=ir.Table, parent=ir.Table))
def components(registry: Registry) -> dict:
    """Give access to the components in the validated registry."""
    return registry._components

def parent_from_hierarchy(entity_id: ir.Table) -> ir.Table:
    """Convert the entity paths in entity_id_table into parent-child relationships and
    add them to the parent component.

    Produces two kinds of parent-child rows:

    1. **Hierarchy-implied**: every nested entity (whose entity path contains
       a dot after the file-id separator) is a child of the entity at the
       path one level up.
    2. **Explicit**: rows in the ``parent`` component table declare a parent
       via a string reference (``value``), which is resolved to an
       ``entity_id`` by matching against ``entity_key`` in the entity_id_table.

    Parameters
    ----------
    entity_id : ir.Table
        One row per entity with columns ``hash``, ``path``, ``entity_key``, ``filepath``.
    parent : ir.Table
        The ``parent`` component table from the registry, containing at
        minimum ``entity_id`` and ``value`` (the string reference to the
        parent entity).

    Returns
    -------
    ir.Table
        A table with columns ``entity_id`` and ``parent_id``, each row
        representing a child→parent relationship as hashed entity IDs.
    """
    df_spine = entity_id.to_pandas()
    df_spine = df_spine.rename(columns={"value": "entity_id"})
    df_spine["entity_path"] = df_spine["path"]

    # ── Part 1: hierarchy-implied parents from entity path nesting ────────
    def has_parent(entity_path):
        sep = entity_path.find(":")
        name_part = entity_path[sep + 1:] if sep != -1 else entity_path
        return "." in name_part

    def get_parent_path(entity_path):
        sep = entity_path.find(":")
        if sep != -1:
            file_id, name_part = entity_path[:sep], entity_path[sep + 1:]
            return f"{file_id}:{name_part.rsplit('.', 1)[0]}"
        return entity_path.rsplit(".", 1)[0]

    spine_pairs = df_spine[["entity_id", "entity_path"]].dropna().drop_duplicates()
    nested = spine_pairs[spine_pairs["entity_path"].apply(has_parent)].copy()

    if nested.empty:
        hierarchy = pd.DataFrame([], columns=["entity_id", "parent_id"])
    else:
        nested["parent_id"] = nested["entity_path"].apply(
            lambda ep: dhash(get_parent_path(ep))
        )
        hierarchy = nested[["entity_id", "parent_id"]].drop_duplicates()

    return hierarchy

def updated_parent(entity_id: ir.Table, parent: ir.Table, parent_from_hierarchy: ir.Table) -> ir.Table:

    df_spine = entity_id.to_pandas()
    df_spine = df_spine.rename(columns={"value": "entity_id"})

    # ── Part 2: explicit parent components ────────────────────────────────
    # Build entity_key → entity_id lookup from the spine.
    key_to_id = (
        df_spine[["entity_id", "entity_key"]]
        .dropna()
        .drop_duplicates(subset=["entity_id", "entity_key"])
        .drop_duplicates(subset=["entity_key"])  # keep first for ambiguous keys
        .set_index("entity_key")["entity_id"]
        .to_dict()
    )

    df_parent = parent.to_pandas()
    if not df_parent.empty and "value" in df_parent.columns:
        df_parent = df_parent[["entity_id", "value"]].dropna(subset=["value"])
        df_parent["parent_id"] = df_parent["value"].map(key_to_id)
        explicit = (
            df_parent[["entity_id", "parent_id"]]
            .dropna(subset=["parent_id"])
            .drop_duplicates()
        )
    else:
        explicit = pd.DataFrame([], columns=["entity_id", "parent_id"])

    hierarchy = parent_from_hierarchy.to_pandas() if not isinstance(parent_from_hierarchy, pd.DataFrame) else parent_from_hierarchy
    combined = (
        pd.concat([hierarchy, explicit], ignore_index=True)
        .drop_duplicates()
        .reset_index(drop=True)
    )
    return ibis.memtable(combined)

def entity_depth(updated_parent: ir.Table) -> ir.Table:
    """Compute the depth of each entity in the parent hierarchy.

    Depth is the length of the shortest path from any root node (an entity with
    no parent) to the entity.  Entities that appear only as roots have depth 0.

    Parameters
    ----------
    parent : ir.Table
        The parent component table from the registry.

    Returns
    -------
    pd.DataFrame
        One row per entity with columns ``entity_id`` and ``depth``.
    """
    parents_df = updated_parent.to_pandas()

    # Directed graph: parent -> child (natural top-down direction)
    G = nx.DiGraph()
    G.add_edges_from(zip(parents_df["parent_id"], parents_df["entity_id"]))

    # Roots: nodes that appear only as parents, never as children
    roots = [n for n in G.nodes if G.in_degree(n) == 0]

    # Multi-source BFS from all roots gives minimum depth for every reachable node
    depths = nx.multi_source_dijkstra_path_length(G, roots)

    return pd.DataFrame(list(depths.items()), columns=["entity_id", "depth"])

def resolved_components(updated_parent: ir.Table, entity_depth: ir.Table) -> dict:
    return

def resolved_registry(resolved_components: dict) -> Registry:
    return