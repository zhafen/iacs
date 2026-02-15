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

    def view(self, component_type: str | list[str]) -> pd.DataFrame:
        """Return a copy of the dataframe for the given component type(s).

        Args:
            component_type: The name of the component type to view, or a list
                of component types to inner join by entity_id.

        Returns:
            A copy of the component's dataframe. When multiple component types
            are provided, returns an inner join by entity_id with columns
            prefixed by component type (e.g., "description.value").

        Raises:
            KeyError: If a component type doesn't exist in the registry.
        """
        if isinstance(component_type, str):
            return self._components[component_type].copy()

        # Multiple component types: inner join by entity_id
        component_types = component_type
        result = None

        for comp_type in component_types:
            df = self._components[comp_type].copy()
            # Reset index to get entity_id as a column for joining
            df = df.reset_index()
            # Prefix columns with component type (except entity_id and component_index)
            df = df.rename(columns={
                col: f"{comp_type}.{col}"
                for col in df.columns
                if col not in ("entity_id", "component_index")
            })
            # Rename component_index to be component-specific
            df = df.rename(columns={"component_index": f"{comp_type}.component_index"})

            if result is None:
                result = df
            else:
                # Inner join on entity_id
                result = result.merge(df, on="entity_id", how="inner")

        # Set entity_id as the index
        if result is not None:
            result = result.set_index("entity_id")

        return result

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
