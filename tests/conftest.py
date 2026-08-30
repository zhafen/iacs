"""Shared test fixtures and helpers.

make_registry now lives in emc2p.testing.registry_builder -- re-exported
here (rather than every test file importing from there directly) so the
existing `from tests.conftest import make_registry` call sites across this
suite don't all need touching. emc2p's own tests/conftest.py re-exports the
identical thing for the same reason (see emc2p's own docs/manifest/
history.yaml: project_history.registry_builder_moved_here_from_duplicated_conftest --
this repo's copy and emc2p's had drifted into byte-identical duplicates).
"""

from emc2p.testing.registry_builder import make_registry  # noqa: F401
