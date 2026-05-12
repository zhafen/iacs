"""ECS Registry for storing and accessing component data."""

import ibis
import pandas as pd

_TABLE_META_COLS = {"entity_id", "component_index", "modifier"}


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
        ibis.options.interactive = True
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

    def merge(self, other: "Registry") -> None:
        """Union all component tables from another registry into this one.

        Existing component types are unioned and deduplicated; new component
        types are added directly.

        Args:
            other: Registry whose component tables are merged in.
        """
        for comp_type in other.component_types:
            arrow_data = other.get(comp_type).to_pyarrow()
            if comp_type in self._component_types:
                tmp = f"_merge_{comp_type}"
                self._con.create_table(tmp, arrow_data, overwrite=True)
                existing = self.get(comp_type)
                incoming = self._con.table(tmp)

                # Add NULL columns for any fields present in one table but not the other
                # so that ibis union can operate on matching schemas.
                existing_cols = set(existing.columns)
                incoming_cols = set(incoming.columns)
                existing_schema = existing.schema()
                incoming_schema = incoming.schema()
                for col in incoming_cols - existing_cols:
                    existing = existing.mutate(
                        ibis.null().cast(incoming_schema[col]).name(col)
                    )
                for col in existing_cols - incoming_cols:
                    incoming = incoming.mutate(
                        ibis.null().cast(existing_schema[col]).name(col)
                    )

                all_cols = sorted(existing.columns)
                merged = existing.select(all_cols).union(
                    incoming.select(all_cols), distinct=True
                )
                self.update({comp_type: merged})
                self._con.drop_table(tmp)
            else:
                self.update({comp_type: arrow_data})

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
                string, or a list of either. All results are inner-joined by
                entity_id with columns named "table.field". ``entity_id.alias``
                is prepended automatically unless already requested.

        Raises:
            KeyError: If a component type doesn't exist in the registry.
        """
        if isinstance(component_type, str):
            component_type = [component_type]

        if (
            "entity_id.alias" not in component_type
            and "entity_id" not in component_type
        ):
            component_type = ["entity_id.alias"] + list(component_type)

        # Expand plain table names to "table.field" dotted entries
        expanded = []
        for ct in component_type:
            if "." not in ct:
                if ct not in self._con.list_tables():
                    raise KeyError(ct)
                t = self._con.table(ct)
                skip = _TABLE_META_COLS | ({"value"} if ct == "entity_id" else set())
                expanded.extend(f"{ct}.{f}" for f in t.columns if f not in skip)
            else:
                expanded.append(ct)

        # Build one sub-table per dotted entry and inner-join on entity_id
        tables_to_join = []
        for ct in expanded:
            table_name, field = ct.split(".", 1)
            if table_name not in self._con.list_tables():
                raise KeyError(table_name)
            t = self._con.table(table_name)
            if table_name == "entity_id":
                t = t.select([t["value"].name("entity_id"), t[field].name(ct)])
            else:
                t = t.select(["entity_id", t[field].name(ct)])
            tables_to_join.append(t)

        result = tables_to_join[0]
        for t in tables_to_join[1:]:
            result = result.inner_join(t, "entity_id")

        return result

    def view_df(self, component_type: str | list[str]) -> pd.DataFrame:
        """Convenience method to return the view as a DataFrame."""
        result = self.view(component_type)
        df = result.execute()
        df = df.set_index("entity_id")
        return df

    def view_entity_df(self, entity_id: str) -> dict[str, pd.DataFrame]:
        """Return component data for a specific entity, keyed by component type.

        Accepts either the internal entity hash or a human-readable alias.

        Args:
            entity_id: Internal entity hash or entity alias.
        """
        result = {}
        for comp_type in self._component_types:
            try:
                df = self.view_df(comp_type).reset_index()
            except Exception:
                continue
            match = df[df["entity_id"] == entity_id]
            if match.empty and "entity_id.alias" in df.columns:
                match = df[df["entity_id.alias"] == entity_id]
            if not match.empty:
                result[comp_type] = match.set_index("entity_id")
        return result
