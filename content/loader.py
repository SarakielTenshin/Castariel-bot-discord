import json
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parents[1]

def load_json(rel_path: str) -> dict[str, Any]:
    p = (BASE / rel_path).resolve()
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

class Content:
    def __init__(self):
        # Dogmas
        self.dogma_castidad = load_json("dogmas/dogma_castidad.json")
        self.dogma_mortales = load_json("dogmas/dogma_mortales_instrumentos.json")

        # Exégesis
        self.lectio_origen = load_json("exegesis/lectio_origen.json")
        self.lectio_doctrina = load_json("exegesis/lectio_doctrina.json")
        self.parabolas = load_json("exegesis/parabolas.json")
        self.cierres = load_json("exegesis/cierres.json")

        # Crónica mundana (historia vivida)
        self.cronica_mundana = load_json("exegesis/cronica_mundana.json")
