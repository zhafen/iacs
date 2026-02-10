"""IOSystem for reading and writing ECS data."""

from pathlib import Path

import pandas as pd


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
        raise NotImplementedError

    def read_entity_centered_file(self, path: Path) -> pd.DataFrame:
        """Read entities and components from an entity-centered file.

        Args:
            path: Path to the file (typically YAML).

        Returns:
            A DataFrame with columns: entity_id, component_index,
            component_type, component_value.
        """
        raise NotImplementedError
