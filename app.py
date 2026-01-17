from pathlib import Path

from flask import Flask, abort, render_template
import yaml

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "examples" / "minimal.yaml"


def parse_infrastructure():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing data file: {DATA_FILE}")

    with DATA_FILE.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    resources = []
    edges = []

    for name, entries in raw.items():
        description = None
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    if description is None and "description" in entry:
                        description = str(entry["description"])
                    if "implements" in entry:
                        edges.append({
                            "source": name,
                            "target": str(entry["implements"]),
                        })
        resources.append({
            "name": name,
            "description": description or "",
        })

    return {"resources": resources, "edges": edges}


@app.route("/")
def index():
    try:
        infra = parse_infrastructure()
    except FileNotFoundError as exc:  # pragma: no cover - small app
        abort(500, description=str(exc))

    return render_template(
        "index.html",
        resources=infra["resources"],
        edges=infra["edges"],
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
