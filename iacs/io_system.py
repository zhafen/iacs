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
                and values are lists of components.

        Returns:
            A DataFrame with columns: entity_id, component_index,
            component_type, component_value.
        """
        rows = []
        for entity_id, components in data.items():
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

        return pd.DataFrame(
            rows,
            columns=["entity_id", "component_index", "component_type", "component_value"],
        )

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
