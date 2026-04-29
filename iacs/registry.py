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

    def update(self, components: dict) -> None:
        """Add or overwrite component tables in the registry.

        Args:
            components: Dict mapping component type names to ibis Tables.
        """
        for comp_type, table in components.items():
            self._con.create_table(comp_type, table, overwrite=True)
            self._components[comp_type] = self._con.table(comp_type)
            if comp_type not in self._component_types and comp_type != "schema":
                self._component_types.append(comp_type)

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

    def get(self, key: str):
        """Return the component table for the given component type."""
        return self._components[key]

    def view(self, component_type: str | list[str]) -> ibis.Table:
        """Return a copy of the dataframe for the given component type(s).

        Args:
            component_type: A component type name, a dotted "table.field"
                string, or a list of either. Lists are inner-joined by
                entity_id with dotted entries producing prefixed column names.
                ``entity_id.alias`` is prepended automatically when the
                entity_id table is present and not already requested.

        Raises:
            KeyError: If a component type doesn't exist in the registry.
        """
        if isinstance(component_type, str):
            component_type = [component_type]

        if (
            "entity_id.alias" not in component_type
            and "entity_id" not in component_type
            # CLAUDE: entity_id should 100% of the time be in list_tables. If not it points to a deeper problem. Remove this last condition.
            and "entity_id" in self._con.list_tables()
        ):
            component_type = ["entity_id.alias"] + list(component_type)

        # Parse entries: "table" or "table.field"
        parsed = []
        for ct in component_type:
            if "." in ct:
                table_name, field = ct.split(".", 1)
                parsed.append((table_name, field))
            else:
                parsed.append((ct, None))

        has_specific_fields = any(field is not None for _, field in parsed)

        if has_specific_fields:
            # Pre-select and rename each field to "table.field", then join
            tables_to_join = []
            for table_name, field in parsed:
                if table_name not in self._con.list_tables():
                    raise KeyError(table_name)
                t = self._con.table(table_name)
                if field is not None:
                    if table_name == "entity_id":
                        # entity_id table stores the hash in "value", not "entity_id"
                        t = t.select([t["value"].name("entity_id"), t[field].name(f"{table_name}.{field}")])
                    else:
                        t = t.select(["entity_id", t[field].name(f"{table_name}.{field}")])
                tables_to_join.append(t)

            result = tables_to_join[0]
            for t in tables_to_join[1:]:
                result = result.inner_join(t, "entity_id")
        else:
            # Multiple whole-component join by entity_id
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
        df = df.set_index("entity_id")
        return df
