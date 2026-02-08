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
