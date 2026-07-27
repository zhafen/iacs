import hashlib

import pandas as pd


def dhash(path: str) -> str:
    """Return a deterministic 12-char hex hash."""
    return hashlib.sha256(path.encode()).hexdigest()[:12]

def get_id(filepath: str, path: str) -> str:
    """Get the ID from the filepath and path within the file."""

    return dhash(f"{filepath}:{path}")


def candidate_entity_ids(user_path: str, entity_id_table: pd.DataFrame) -> list[str]:
    """Return the entity ID(s) `user_path` identifies.

    Tries an exact match against each entity's `alias` first, when
    `entity_id_table` has one (every real entity_id table does; callers
    that pass a bare `value`/`path` table — e.g. the older, alias-less
    tests for this function — just skip straight to the substring
    fallback). This isn't just an optimization: a container entity's own
    alias is always a substring of its descendants' full paths too (e.g.
    `"make_cats_happy"` vs. `"make_cats_happy.feed_and_water_cats"`), so
    without it, `user_path` naming a container by its own alias would
    resolve as ambiguous with its own children instead of uniquely to the
    container.

    Falls back to every entity ID whose full `path` contains `user_path`
    as a substring when there's no exact alias match.
    """
    if "alias" in entity_id_table.columns:
        alias_matches = entity_id_table.loc[entity_id_table["alias"] == user_path, "value"].tolist()
        if alias_matches:
            return alias_matches
    mask = entity_id_table["path"].str.contains(user_path, regex=False)
    return entity_id_table.loc[mask, "value"].tolist()
