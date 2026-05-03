from contextlib import asynccontextmanager
from pathlib import Path

import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from iacs.architect import Architect
from iacs.views.requirement_tree import build_requirement_tree

BASE_DIR = Path(__file__).parent
BUILTINS_DIR = BASE_DIR / "iacs" / "iacs_manifest"
STATIC_DIR = BASE_DIR / "static"
DEFAULT_ANCESTOR = "be_a_powerful_tool_for_solutions_architecture"


@asynccontextmanager
async def lifespan(app):
    app.state.architect = Architect.from_manifest(str(BUILTINS_DIR))
    yield

app = FastAPI(lifespan=lifespan)


@app.get("/api/view/{component_types:path}")
def view_component(component_types: str):
    types = component_types.split("/")
    df = app.state.architect.view(types).execute()
    return json.loads(df.to_json(orient="records"))
