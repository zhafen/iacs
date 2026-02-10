"""IOSystem for reading and writing ECS data."""

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
        rows = []
        self._extract_entities(data, rows)
        return pd.DataFrame(
            rows,
            columns=["entity_id", "component_index", "component_type", "component_value"],
        )

    def _extract_entities(self, data: dict, rows: list, parent_id: str = "") -> None:
        """Recursively extract entities and components from entity-centered data.

        Args:
            data: Dict of entity data.
            rows: List to append component rows to.
            parent_id: Parent entity ID for constructing sub-entity IDs.
        """
        for key, value in data.items():
            entity_id = f"{parent_id}.{key}" if parent_id else key

            if isinstance(value, list):
                # Flat entity with list of components
                self._extract_components(entity_id, value, rows)
            elif isinstance(value, dict):
                # Hierarchical entity with sub-entities
                # "data" key contains components for this entity
                if "data" in value:
                    self._extract_components(entity_id, value["data"], rows)
                # Other keys are sub-entities
                sub_entities = {k: v for k, v in value.items() if k != "data"}
                if sub_entities:
                    self._extract_entities(sub_entities, rows, entity_id)

    def _extract_components(self, entity_id: str, components: list, rows: list) -> None:
        """Extract components from a list and append to rows.

        Args:
            entity_id: The entity ID.
            components: List of components.
            rows: List to append component rows to.
        """
        for component_index, component in enumerate(components):
            if isinstance(component, str):
                # Tag component (no value)
                component_type = component
                component_value = {}
            elif isinstance(component, dict):
                # Value component
                component_type = next(iter(component))
                raw_value = component[component_type]
                component_value = {"value": raw_value}
            else:
                continue

            rows.append({
                "entity_id": entity_id,
                "component_index": component_index,
                "component_type": component_type,
                "component_value": component_value,
            })

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

    def to_component_centered(self, entity_centered: pd.DataFrame):
        """Convert entity-centered data to component-centered format (Registry).

        Args:
            entity_centered: DataFrame with columns entity_id, component_index,
                component_type, component_value.

        Returns:
            A Registry with one component table per component type.
        """
        from iacs.registry import Registry

        raise NotImplementedError
