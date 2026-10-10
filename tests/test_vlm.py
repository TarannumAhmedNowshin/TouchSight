from touchsight import vlm


def test_normalise_rejects_markup_and_rewrites_ids():
    raw = {
        "title": 'Heart<script>alert(1)</script>',
        "elements": [
            {"id": '" onmouseover="x', "name": "Left <b>Atrium</b>", "kind": "region", "importance": 3,
             "box_2d": [100, 100, 400, 400], "parent": None},
            {"id": "child", "name": "valve", "kind": "blob", "importance": 9,
             "box_2d": [150, 150, 200, 200], "parent": '" onmouseover="x'},
        ],
    }
    out = vlm.normalise(raw)
    assert "<" not in out["title"] and ">" not in out["title"]
    ids = [e["id"] for e in out["elements"]]
    assert ids == ["e1", "e2"]
    assert out["elements"][1]["parent"] == "e1"      # parent link survives the id rewrite
    assert out["elements"][1]["kind"] == "region"    # unknown kinds fall back safely
    assert out["elements"][1]["importance"] == 2
    assert "<" not in out["elements"][0]["name"]


def test_normalise_drops_degenerate_boxes_and_clamps():
    out = vlm.normalise({"elements": [
        {"name": "ok", "box_2d": [-50, 10, 1200, 900]},
        {"name": "tiny", "box_2d": [10, 10, 11, 11]},
        {"name": "garbage", "box_2d": "nope"},
    ]})
    assert [e["name"] for e in out["elements"]] == ["ok"]
    assert out["elements"][0]["box_2d"] == [0, 10, 1000, 900]


def test_extract_json_tolerates_fences_and_thinking():
    text = "<think>hmm</think>\n```json\n{\"title\": \"x\"}\n```"
    assert vlm.extract_json(text) == {"title": "x"}


def test_pad_square_round_trip():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (500, 360), "white").save(buf, "PNG")
    padded, fy, fx = vlm.pad_square(buf.getvalue())
    assert Image.open(io.BytesIO(padded)).size == (500, 500)
    # a model answering in square-normalised coords maps back onto the original image
    fixed = vlm.unpad_boxes({"elements": [{"box_2d": [280, 400, 460, 600]}]}, fy, fx)
    assert [round(v) for v in fixed["elements"][0]["box_2d"]] == [389, 400, 639, 600]
