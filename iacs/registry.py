"""ECS Registry for storing and accessing component data."""
from __future__ import annotations

from pathlib import Path

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
        self._schemas: dict[str, ibis.Schema] = {
            k: v.schema()
            for k, v in components.items()
            if isinstance(v, ibis.Table)
        }

    def update(self, components: dict) -> None:
        """Add or overwrite component tables in the registry.

        Args:
            components: Dict mapping component type names to ibis Tables.
        """
        for comp_type, table in components.items():
            self._con.create_table(comp_type, table, overwrite=True)
            self._components[comp_type] = self._con.table(comp_type)
            self._schemas[comp_type] = self._con.table(comp_type).schema()
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

    def to_database(self, path: str | Path) -> None:
        """Export all component tables as-is to a database.

        Uses ``ibis.connect`` so the backend is inferred from ``path``: a
        plain filesystem path with a ``.duckdb`` extension connects via
        DuckDB, while a URL such as ``"sqlite:///registry.db"`` or
        ``"postgres://user:pass@host/db"`` connects to that backend instead.

        Args:
            path: A URL or filesystem path resolvable by ``ibis.connect``.
        """
        out_con = ibis.connect(str(path))
        for comp_type in self._component_types:
            out_con.create_table(
                comp_type, self.get(comp_type).to_pyarrow(), overwrite=True
            )
        out_con.disconnect()

    @classmethod
    def from_database(cls, path: str | Path) -> "Registry":
        """Load a Registry from a database written by ``to_database``.

        Args:
            path: A URL or filesystem path resolvable by ``ibis.connect``.
        """
        con = ibis.connect(str(path))
        components = {name: con.table(name) for name in con.list_tables()}
        return cls(con, components)

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
        """Return the component table for the given component type.

        If the component type does not exist but its schema is known, returns
        an empty table with that schema. If the schema is also unknown, returns
        an empty table with only an ``entity_id`` string column.
        """
        if key in self._components:
            return self._components[key]
        if key in self._schemas:
            return ibis.memtable([], schema=self._schemas[key])
        return ibis.memtable([], schema={"entity_id": "string", "value": "string"})

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
        return self._view(component_type, self._con.table)

    def view_current(self, component_type: str | list[str]) -> ibis.Table:
        """Like ``view``, but collapsed to the most recent version of each record.

        For any component type with a field flagged ``time_dimension: true`` in
        its schema (directly or via inheritance), only the row with the
        maximum time_dimension value is kept per (entity_id, component_index,
        modifier) group — i.e. the current version of a slowly changing
        dimension. Component types with no time_dimension field are returned
        unchanged.

        Args:
            component_type: Same as ``view``.

        Raises:
            KeyError: If a component type doesn't exist in the registry.
            ValueError: If a component type has more than one time_dimension field.
        """
        return self._view(component_type, self._current_table)

    def _view(self, component_type: str | list[str], table_fn) -> ibis.Table:
        if isinstance(component_type, str):
            component_type = [component_type]

        if (
            "entity_id.alias" not in component_type
            and "entity_id" not in component_type
        ):
            component_type = ["entity_id.alias"] + list(component_type)

        # Resolve each entry to a (table_name, field) pair, expanding bare
        # table names to all of their non-meta fields.
        pairs: list[tuple[str, str]] = []
        for ct in component_type:
            if "." not in ct:
                if ct not in self._con.list_tables():
                    raise KeyError(ct)
                t = table_fn(ct)
                skip = _TABLE_META_COLS | ({"value"} if ct == "entity_id" else set())
                pairs.extend((ct, f) for f in t.columns if f not in skip)
            else:
                table_name, field = ct.split(".", 1)
                if table_name not in self._con.list_tables():
                    raise KeyError(table_name)
                pairs.append((table_name, field))

        # Group fields by table so that multiple fields from the same table
        # are selected together in a single pass. Joining separately-selected
        # single-field sub-tables back together on entity_id alone would
        # cross-join any table with more than one row per entity_id (e.g. a
        # component with several instances, or SCD history), decorrelating
        # fields that belong to the same row.
        fields_by_table: dict[str, list[str]] = {}
        for table_name, field in pairs:
            fields = fields_by_table.setdefault(table_name, [])
            if field not in fields:
                fields.append(field)

        tables_to_join = []
        for table_name, fields in fields_by_table.items():
            t = table_fn(table_name)
            if table_name == "entity_id":
                cols = [t["value"].name("entity_id")]
            else:
                cols = ["entity_id"]
            cols += [t[f].name(f"{table_name}.{f}") for f in fields]
            tables_to_join.append(t.select(cols))

        result = tables_to_join[0]
        for t in tables_to_join[1:]:
            result = result.inner_join(t, "entity_id")

        return result

    def _current_table(self, table_name: str) -> ibis.Table:
        """Return ``table_name`` collapsed to the latest row per (entity_id,
        component_index, modifier) group, using its time_dimension field.

        Assumes the registry was produced by ``base_etl`` (``derived_field``
        and ``entity_id`` are present). Tables with no time_dimension field
        are returned unchanged.

        Raises:
            ValueError: If ``table_name`` has more than one time_dimension field.
        """
        t = self._con.table(table_name)
        time_field = self._time_dimension_field(table_name)
        if time_field is None or time_field not in t.columns:
            return t

        key_cols = list(_TABLE_META_COLS)
        ranked = t.mutate(
            _scd_rank=ibis.row_number().over(
                group_by=key_cols, order_by=t[time_field].desc(nulls_first=False)
            )
        )
        return ranked.filter(ranked["_scd_rank"] == 0).drop("_scd_rank")

    def _time_dimension_field(self, component_type: str) -> str | None:
        """Return the field flagged ``time_dimension: true`` for a component type, if any.

        Assumes the registry was produced by ``base_etl``, so ``derived_field``
        and ``entity_id`` are present, and ``derived_field["time_dimension"]``
        is already a real bool — ``field`` is validated against its own
        schema (see ``validate_components.field_validation_results``) as
        part of ``validate_registry``, and all data is expected to reach the
        registry only by going through that pass. If this raises or behaves
        unexpectedly, the registry likely didn't go through the full
        pipeline (e.g. component tables inserted directly) — that's a bug in
        the caller, not something to work around here.

        Raises:
            ValueError: If more than one field is flagged time_dimension for
                this component type — only one is allowed.
        """
        df_field = self._components["derived_field"].execute()
        if "time_dimension" not in df_field.columns:
            return None

        df_entity = self._components["entity_id"].execute()
        def_eids = df_entity.loc[df_entity["entity_key"] == component_type, "value"]

        matches = df_field[df_field["entity_id"].isin(def_eids)]
        fields = sorted({
            str(row["value"])
            for _, row in matches.iterrows()
            if row["time_dimension"]
        })
        if len(fields) > 1:
            raise ValueError(
                f"Component type {component_type!r} has multiple time_dimension "
                f"fields {fields}; only one is allowed."
            )
        return fields[0] if fields else None

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

    def view_entity(self, entity_id: str, format: str = "markdown") -> str:
        """Return all component data for a specific entity as a formatted string.

        Args:
            entity_id: Internal entity hash or human-readable alias.
            format: Output format — "markdown" (default) or "csv".
        """
        components = self.view_entity_df(entity_id)
        if not components:
            return f"No data found for entity {entity_id!r}."
        sections = []
        for comp_type, df in components.items():
            if format == "markdown":
                sections.append(f"### {comp_type}\n\n{df.to_markdown()}")
            else:
                sections.append(f"# {comp_type}\n\n{df.to_csv()}")
        return "\n\n".join(sections)
