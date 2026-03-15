"""ECS Registry for storing and accessing component data."""

import ibis
import pandas as pd

ibis.options.interactive = True


class Registry:
    """A registry that stores ECS component data as ibis tables.

    Each component type has its own table backed by a DuckDB connection.
    """

    def __init__(self, conn: ibis.BaseBackend, components: dict):
        """Initialize the registry with a connection and components.

        Args:
            conn: An ibis DuckDB backend containing the component tables.
            components: A dict mapping component type names to ibis Tables
                (or other values like dicts). Keys other than "schema" are
                treated as component types.

        Metadata:
        - todo: We likely want to store the schema with the other component types and/or just have a filter on type.
        """
        self._con = conn
        self._components = components
        self._component_types = [
            k for k, v in components.items()
            if k != "schema" and isinstance(v, ibis.Table)
        ]

    def close(self) -> None:
        """Close the underlying database connection."""
        self._con.disconnect()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:  # pylint: disable=broad-except
            pass

    @property
    def component_types(self) -> list[str]:
        """Return the list of component types in the registry."""
        return list(self._component_types)

    def table(self, key: str):
        """Return the Ibis table for the given component type."""
        return self._con.table(key)

    def _with_entity_alias(self, result: ibis.Table) -> ibis.Table:
        """Left-join entity_alias from the entity_id table into result.

        Adds an ``entity_alias`` column immediately after any ``entity_id`` or
        ``component_index`` columns. Skipped when result has no ``entity_id``
        column or when the entity_id table is not in the registry.
        """
        if "entity_id" not in result.columns:
            return result
        if "entity_id" not in self._con.list_tables():
            return result

        eid_t = self._con.table("entity_id")
        eid = eid_t.select(
            eid_t["value"].name("entity_id"),
            eid_t["alias"].name("entity_alias"),
        )
        result = result.left_join(eid, "entity_id")

        # Place entity_alias immediately after the last entity_id/component_index col
        cols = [c for c in result.columns if c != "entity_alias"]
        insert_pos = 0
        for i, col in enumerate(cols):
            if col in ("entity_id", "component_index"):
                insert_pos = i + 1
        cols.insert(insert_pos, "entity_alias")
        return result.select(cols)

    def view(self, component_type: str | list[str]) -> pd.DataFrame:
        """Return a copy of the dataframe for the given component type(s).

        Args:
            component_type: The name of the component type to view, or a list
                of component types to inner join by entity_id.

        Returns:
            A copy of the component's dataframe. When multiple component types
            are provided, returns an inner join by entity_id with columns
            prefixed by component type (e.g., "description.value").
            An ``entity_alias`` column is always included immediately after any
            ``entity_id`` or ``component_index`` columns.

        Raises:
            KeyError: If a component type doesn't exist in the registry.
        """
        if isinstance(component_type, str):
            if component_type not in self._con.list_tables():
                raise KeyError(component_type)
            return self._with_entity_alias(self._con.table(component_type))

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

        return self._with_entity_alias(result)

    def view_df(self, component_type: str | list[str]) -> pd.DataFrame:
        """Convenience method to return the view as a DataFrame."""
        result = self.view(component_type)
        df = result.execute()
        df = df.set_index("entity_id")
        return df
