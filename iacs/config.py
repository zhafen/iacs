"""Central configuration for tunable iacs behavior.

Currently holds the pattern used to identify a YAML-bearing "Components"
section within a Python docstring (see
``iacs.dataflows.etl.load_python``). The pattern is a regex matched against
a numpy-style section header: a "Components" line underlined with dashes.
"""

DOCSTRING_COMPONENTS_PATTERN = r"^[ \t]*Components[ \t]*\n[ \t]*-{3,}[ \t]*$"
