import hashlib

import pandas as pd


def dhash(path: str) -> str:
    """Return a deterministic 12-char hex hash."""
    return hashlib.sha256(path.encode()).hexdigest()[:12]

def get_id(filepath: str, path: str) -> str:
    """Get the ID from the filepath and path within the file."""

    return dhash(f"{filepath}:{path}")


def candidate_entity_ids(user_path: str, entity_id_table: pd.DataFrame) -> list[str]:
    """Return entity IDs whose full path contains user_path as a substring."""
    mask = entity_id_table["path"].str.contains(user_path, regex=False)
    return entity_id_table.loc[mask, "value"].tolist()
