import dataclasses
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as api
from touchsight import segment, vlm


@pytest.fixture
def client(monkeypatch, cell_analysis, tmp_path):
    # never call real providers in tests
    monkeypatch.setattr(vlm, "analyse", lambda image, use_cache=True: (vlm.normalise(cell_analysis), "test"))
    api._hits.clear()
    return TestClient(api.app)


def test_rejects_non_images(client):
    r = client.post("/api/convert", files={"file": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 415


def test_rejects_decompression_bombs(client, monkeypatch):
    monkeypatch.setattr(segment, "settings", dataclasses.replace(segment.settings, max_image_pixels=1000))
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(buf, "PNG")
    r = client.post("/api/convert", files={"file": ("big.png", buf.getvalue(), "image/png")})
    assert r.status_code == 415


def test_sample_names_are_whitelisted(client):
    r = client.post("/api/convert", data={"sample": "../app"})
    assert r.status_code == 404


def test_convert_redesign_and_download(client, cell_image):
    r = client.post("/api/convert", files={"file": ("cell.png", cell_image, "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    nucleus = next(e["id"] for e in body["elements"] if e["name"] == "nucleus")
    r2 = client.post("/api/redesign", json={"job": body["job"], "exclude": [nucleus, "bogus"]})
    assert r2.status_code == 200
    assert not next(e for e in r2.json()["elements"] if e["id"] == nucleus)["included"]
    svg = client.get(f"/api/download/{body['job']}/svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")


def test_rate_limit(client, cell_image, monkeypatch):
    monkeypatch.setattr(api, "settings", dataclasses.replace(api.settings, rate_limit_per_min=1))
    client.post("/api/convert", files={"file": ("cell.png", cell_image, "image/png")})
    r = client.post("/api/convert", files={"file": ("cell.png", cell_image, "image/png")})
    assert r.status_code == 429


def test_sample_upload_disabled_by_default(client, cell_image):
    r = client.post("/api/samples/save", data={"name": "x"}, files={"file": ("c.png", cell_image, "image/png")})
    assert r.status_code == 403
