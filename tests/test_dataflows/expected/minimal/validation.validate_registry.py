import pandas as pd

from iacs.utils import dhash

updated_parent = pd.DataFrame(
    [],
    columns=["entity_id", "component_index", "modifier", "parent_eid", "is_primary"],
)
