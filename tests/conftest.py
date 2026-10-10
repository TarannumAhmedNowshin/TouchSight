import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def cell_image() -> bytes:
    return (FIXTURES / "animal_cell.png").read_bytes()


@pytest.fixture
def cell_analysis() -> dict:
    return json.loads((FIXTURES / "animal_cell.mock.json").read_text())


@pytest.fixture
def circuit_image() -> bytes:
    return (FIXTURES / "simple_circuit.png").read_bytes()


@pytest.fixture
def circuit_analysis() -> dict:
    return json.loads((FIXTURES / "simple_circuit.mock.json").read_text())
