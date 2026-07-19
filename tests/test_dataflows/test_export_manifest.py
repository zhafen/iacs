"""Tests for the export_manifest dataflow."""

import yaml

from iacs.registrar import Registrar


class TestExportManifestSplitsByFile:

    def test_export_manifest_splits_by_file(self, tmp_path):
        """Export should produce one output file per original source file."""
        input_dir = "examples/networks"
        output_dir = str(tmp_path)

        a = Registrar.from_manifest(input_dir)
        a.execute("etl.export_manifest", output_dir=output_dir)

        # One file per original source (builtins excluded)
        output_files = sorted(f.name for f in tmp_path.glob("*.yaml"))
        assert output_files == ["net_AB.yaml", "net_ABCD.yaml"]

        # Entities belong in the correct output file
        with open(tmp_path / "net_AB.yaml") as f:
            ab_data = yaml.safe_load(f)
        with open(tmp_path / "net_ABCD.yaml") as f:
            abcd_data = yaml.safe_load(f)

        assert "subnet_AB" in ab_data
        assert "net_ABCD" in abcd_data
        # No cross-contamination
        assert "subnet_AB" not in abcd_data
        assert "net_ABCD" not in ab_data
