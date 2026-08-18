"""iacs's own Registrar: emc2p's generic Registrar, extended with the
architecture-specific derive pipeline (impact/cost scoring, see
``iacs.dataflows.base_etl``) and the HTML audit report convenience method.
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

from emc2p.registrar import Registrar as _BaseRegistrar


class Registrar(_BaseRegistrar):
    """User-facing interface to a registry, with iacs's own derive pipeline."""

    def _base_etl_module(self) -> ModuleType:
        from iacs.dataflows import base_etl
        return base_etl

    def generate_report(self, output_path: str | Path = "iacs_report.html") -> str:
        """Render a self-contained HTML audit report and save it.

        Runs the ``audit.report`` dataflow against the current registry,
        producing a report with an aggregated cost-impact plot and a
        navigable requirements tree.

        Args:
            output_path: File path to write the report to. Defaults to
                "iacs_report.html" in the current directory.

        Returns:
            The path the report was written to.
        """
        result = self.execute("audit.report", output_path=str(output_path))
        return result["report_path"]
