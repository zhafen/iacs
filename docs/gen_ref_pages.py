"""Generate API reference pages for all public iacs modules."""

from pathlib import Path

import pkgutil
import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()
pkg_root = Path(__file__).parent.parent / "iacs"

for module_info in pkgutil.walk_packages([str(pkg_root)], prefix="iacs."):
    name = module_info.name
    parts = name.split(".")

    # Skip __init__ modules and private modules (starting with _)
    if any(part.startswith("_") for part in parts):
        continue

    # parts[1:] strips the top-level "iacs" prefix for paths
    rel_parts = parts[1:]

    if module_info.ispkg:
        doc_path = Path(*rel_parts, "index.md")
        src_path = Path("iacs", *rel_parts, "__init__.py")
    else:
        doc_path = Path(*rel_parts).with_suffix(".md")
        src_path = Path("iacs", *rel_parts).with_suffix(".py")

    full_doc_path = Path("api") / doc_path

    with mkdocs_gen_files.open(full_doc_path, "w") as f:
        f.write(f"# {parts[-1]}\n\n:::{name}\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, src_path)

    nav[tuple(rel_parts)] = str(full_doc_path)

with mkdocs_gen_files.open("api/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
