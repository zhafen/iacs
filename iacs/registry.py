"""ECS Registry for storing and accessing component data."""

import ibis
import pandas as pd

ibis.options.interactive = True


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
        self._con = ibis.duckdb.connect()
        self._component_types = list(components.keys())
        for name, df in components.items():
            flat = df.reset_index()
            # Cast object columns to string to avoid DuckDB type errors
            # (handles all-null columns, lists, dicts, and other non-scalar types)
            for col in flat.columns:
                if flat[col].dtype == object:
                    flat[col] = flat[col].astype(str)
            self._con.create_table(name, flat)

    @property
    def component_types(self) -> list[str]:
        """Return the list of component types in the registry."""
        return list(self._component_types)

    def table(self, key: str):
        """Return the Ibis table for the given component type."""
        return self._con.table(key)

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
            if component_type not in self._con.list_tables():
                raise KeyError(component_type)
            return self._con.table(component_type)

        # Multiple component types: inner join by entity_id
        component_types = component_type
        result = None

        for i, comp_type in enumerate(component_types):
            if comp_type not in self._con.list_tables():
                raise KeyError(comp_type)
            table = self._con.table(comp_type)

            if result is None:
                result = table
            else:
                if i == 1:
                    lname = f"{component_types[0]}.{{name}}"
                    rname = f"{comp_type}.{{name}}"
                else:
                    lname = "{name}"
                    rname = f"{comp_type}.{{name}}"
                result = result.inner_join(
                    table, "entity_id", lname=lname, rname=rname
                )

        return result

    def view_df(self, component_type: str | list[str]) -> pd.DataFrame:
        """Convenience method to return the view as a DataFrame."""
        result = self.view(component_type)
        df = result.execute()
        if isinstance(component_type, str):
            df = df.set_index(["entity_id", "component_index"])
        else:
            df = df.set_index("entity_id")
        return df

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
                row_data = {}
                # Extract fields from component_value dict
                component_value = row["component_value"]
                if isinstance(component_value, dict):
                    for k, v in component_value.items():
                        row_data[k] = v
                rows.append({
                    "entity_id": row["entity_id"],
                    "component_index": row["component_index"],
                    **row_data,
                })

            df = pd.DataFrame(rows)
            df = df.set_index(["entity_id", "component_index"])
            components[component_type] = df

        return cls(components)
