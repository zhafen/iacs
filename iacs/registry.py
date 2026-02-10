"""ECS Registry for storing and accessing component data."""

import pandas as pd


class Registry:
    """A registry that stores ECS component data as dataframes.

    Each component type has its own dataframe with a multi-index of
    (entity_id, component_index).
    """

    def __init__(self, components: dict[str, pd.DataFrame]):
        """Initialize the registry with component dataframes.

        Args:
            components: A dict mapping component type names to DataFrames.
        """
        self._components = dict(components)

    @property
    def component_types(self) -> list[str]:
        """Return the list of component types in the registry."""
        return list(self._components.keys())

    def view(self, component_type: str) -> pd.DataFrame:
        """Return a copy of the dataframe for the given component type.

        Args:
            component_type: The name of the component type to view.

        Returns:
            A copy of the component's dataframe.

        Raises:
            KeyError: If the component type doesn't exist in the registry.
        """
        return self._components[component_type].copy()

    @classmethod
    def from_entity_centered(cls, entity_centered: pd.DataFrame) -> "Registry":
        """Construct a Registry from entity-centered data.

        Args:
            entity_centered: DataFrame with columns entity_id, component_index,
                component_type, component_value.

        Returns:
            A Registry with one table per component type.
        """
        if entity_centered.empty:
            return cls({})

        components = {}
        for component_type, group in entity_centered.groupby("component_type"):
            # Build the component table with multi-index
            rows = []
            for _, row in group.iterrows():
                row_data = {
                    "component_type": row["component_type"],
                }
                # Extract value from component_value dict if present
                component_value = row["component_value"]
                if isinstance(component_value, dict) and "value" in component_value:
                    row_data["value"] = component_value["value"]
                rows.append({
                    "entity_id": row["entity_id"],
                    "component_index": row["component_index"],
                    **row_data,
                })

            df = pd.DataFrame(rows)
            df = df.set_index(["entity_id", "component_index"])
            components[component_type] = df

        return cls(components)
