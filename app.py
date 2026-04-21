import atexit
from pathlib import Path

from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from iacs.architect import Architect

ROOT_DIR = Path(__file__).parent
COMPONENTS_DIR = ROOT_DIR / "builtins"
STATIC_DIR = ROOT_DIR / "static"

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None


class ComponentViewArgs(BaseModel):
    component_type: str | list[str]


app = FastAPI()

a: Architect = Architect.from_manifest(COMPONENTS_DIR)

# We really want to ensure the registry closes out at exit
atexit.register(a.registry.close)


@app.get("/")
def root():
    return {"message": f"Architect for {COMPONENTS_DIR}"}


@app.get("/components/{component_name}")
def get_component(component_name: str):

    return {"output": a.get(component_name).__str__()}


@app.get("/view/{component_type}")
def view(component_type: str = None):

    return {
        "component_type": component_type,
        "view": str(a.view(component_type))
    }

@app.post("/view/{component_type}")
def view_with_args(component_type: str, component_view_args: ComponentViewArgs):

    if component_type is None:
        component_type = component_view_args.component_type

    return {
        "component_type": component_type,
        "view": str(a.view(component_type))
    }

# Mount the html files
app.mount("/viz/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")