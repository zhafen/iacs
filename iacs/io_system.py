"""IOSystem for reading and writing ECS data."""

import hashlib
from pathlib import Path

import pandas as pd
import yaml


class IOSystem:
    """System for reading and writing ECS data in various formats."""

    def read_entity_centered(self, data: dict) -> pd.DataFrame:
        """Read entities and components from entity-centered data.

        Args:
            data: A dict of entity-centered data where keys are entity IDs
                and values are lists of components or dicts with sub-entities.

        Returns:
            A DataFrame with columns: entity_id, component_index,
            component_type, component_value.
        """
        # Phase 1: Extract rows with path-based entity_ids and collect id_info
        rows = []
        id_infos = {}  # path -> {key, path, parent_path, alias}
        self._extract_entities(data, rows, id_infos)

        if not rows:
            return pd.DataFrame(
                rows,
                columns=["entity_id", "component_index",
                          "component_type", "component_value"],
            )

        # Phase 2: Compute entity IDs from id_info
        path_to_entity_id = {}
        for path, info in id_infos.items():
            hash_val = hashlib.md5(path.encode()).hexdigest()[:12]
            info["hash"] = hash_val
            alias = info.get("alias")
            info["value"] = alias if alias is not None else hash_val
            path_to_entity_id[path] = info["value"]

        # Phase 3: Post-process rows
        # Replace path-based entity_ids with id.value
        for row in rows:
            old_path = row["entity_id"]
            row["entity_id"] = path_to_entity_id[old_path]

        # Resolve references in component values
        self._resolve_references(rows, path_to_entity_id)

        # Inject auto-generated id component rows
        id_rows = []
        for path, info in id_infos.items():
            entity_id = path_to_entity_id[path]
            id_rows.append({
                "entity_id": entity_id,
                "component_index": -2,  # sentinel, will be renumbered
                "component_type": "id",
                "component_value": {
                    "value": info["value"],
                    "key": info["key"],
                    "path": path,
                    "hash": info["hash"],
                    "alias": info.get("alias"),
                },
            })

        # Inject auto-generated parent component rows
        parent_rows = []
        for path, info in id_infos.items():
            parent_path = info.get("parent_path")
            if parent_path is not None:
                child_id = path_to_entity_id[path]
                parent_id = path_to_entity_id[parent_path]
                parent_rows.append({
                    "entity_id": child_id,
                    "component_index": -1,  # sentinel, will be renumbered
                    "component_type": "parent",
                    "component_value": {
                        "source": child_id,
                        "target": parent_id,
                    },
                })

        # Combine all rows: id first, then parent, then original components
        all_rows = id_rows + parent_rows + rows

        # Renumber component_index per entity
        self._renumber_component_indices(all_rows)

        return pd.DataFrame(
            all_rows,
            columns=["entity_id", "component_index",
                      "component_type", "component_value"],
        )

    def _extract_entities(
        self, data: dict, rows: list, id_infos: dict,
        parent_path: str = "",
    ) -> None:
        """Recursively extract entities and components from entity-centered data.

        Args:
            data: Dict of entity data.
            rows: List to append component rows to.
            id_infos: Dict to populate with path -> id info.
            parent_path: Parent entity path for constructing sub-entity paths.
        """
        for key, value in data.items():
            path = f"{parent_path}.{key}" if parent_path else key

            # Record id_info for this entity
            info = {
                "key": key,
                "path": path,
                "parent_path": parent_path if parent_path else None,
                "alias": None,
            }

            if isinstance(value, list):
                # Check for {id: alias} component and extract alias
                alias = self._extract_alias(value)
                info["alias"] = alias
                id_infos[path] = info
                self._extract_components(path, value, rows)
            elif isinstance(value, dict):
                if "data" in value:
                    alias = self._extract_alias(value["data"])
                    info["alias"] = alias
                    id_infos[path] = info
                    self._extract_components(path, value["data"], rows)
                else:
                    # Dict with no "data" key but has sub-entities
                    id_infos[path] = info
                # Other keys are sub-entities
                sub_entities = {k: v for k, v in value.items() if k != "data"}
                if sub_entities:
                    self._extract_entities(sub_entities, rows, id_infos, path)

    def _extract_alias(self, components: list) -> str | None:
        """Extract alias from an {id: alias} component if present."""
        for component in components:
            if isinstance(component, dict):
                comp_type = next(iter(component))
                if comp_type == "id":
                    return component["id"]
        return None

    def _extract_components(
        self, entity_path: str, components: list, rows: list
    ) -> None:
        """Extract components from a list and append to rows.

        Skips {id: alias} components since id is auto-generated.

        Args:
            entity_path: The entity path (used as temporary entity_id).
            components: List of components.
            rows: List to append component rows to.
        """
        for component_index, component in enumerate(components):
            if isinstance(component, str):
                # Tag component (no value)
                component_type = component
                component_value = {}
            elif isinstance(component, dict):
                component_type = next(iter(component))
                # Skip id components - they are auto-generated
                if component_type == "id":
                    continue
                raw_value = component[component_type]
                component_value = {"value": raw_value}
            else:
                continue

            rows.append({
                "entity_id": entity_path,
                "component_index": component_index,
                "component_type": component_type,
                "component_value": component_value,
            })

    def _resolve_references(
        self, rows: list, path_to_entity_id: dict[str, str]
    ) -> None:
        """Resolve path-based references in component values.

        Any component_value["value"] string matching a known path
        (exact or unambiguous suffix) gets replaced with the entity_id.
        """
        # Build suffix index for unambiguous suffix matching
        suffix_index: dict[str, list[str]] = {}
        for path in path_to_entity_id:
            parts = path.split(".")
            for i in range(len(parts)):
                suffix = ".".join(parts[i:])
                suffix_index.setdefault(suffix, []).append(path)

        for row in rows:
            cv = row["component_value"]
            if not isinstance(cv, dict) or "value" not in cv:
                continue
            val = cv["value"]
            if not isinstance(val, str):
                continue

            # Exact match
            if val in path_to_entity_id:
                cv["value"] = path_to_entity_id[val]
            # Unambiguous suffix match
            elif val in suffix_index and len(suffix_index[val]) == 1:
                cv["value"] = path_to_entity_id[suffix_index[val][0]]

    def _renumber_component_indices(self, rows: list) -> None:
        """Renumber component_index per entity to be sequential from 0."""
        entity_counter: dict[str, int] = {}
        for row in rows:
            eid = row["entity_id"]
            idx = entity_counter.get(eid, 0)
            row["component_index"] = idx
            entity_counter[eid] = idx + 1

    def read_entity_centered_file(self, path: Path) -> pd.DataFrame:
        """Read entities and components from an entity-centered file.

        Args:
            path: Path to the file (typically YAML).

        Returns:
            A DataFrame with columns: entity_id, component_index,
            component_type, component_value.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return self.read_entity_centered(data)
