import io
import re

import numpy as np
from stl import mesh

from touchsight import export, pipeline


def test_cell_end_to_end(cell_image, cell_analysis):
    out = pipeline.run(cell_image, analysis=cell_analysis)
    report = out.report
    assert report["validation"]["after"]["score"] >= 90
    assert {e["name"] for e in report["elements"] if e["included"]} >= {"cell membrane", "nucleus", "mitochondrion"}
    header = re.search(r"<svg[^>]+>", out.svg_print).group(0)
    assert 'width="297.0mm"' in header and 'viewBox="0 0 297.0 210.0"' in header   # 1 unit = 1 mm, A4
    assert "<text" not in out.svg_print                                          # nothing printed that isn't tactile
    assert report["description"].startswith(report["title"])


def test_teacher_can_exclude_parts_without_a_model_call(cell_image, cell_analysis):
    first = pipeline.run(cell_image, analysis=cell_analysis)
    nucleus = next(e["id"] for e in first.report["elements"] if e["name"] == "nucleus")
    second = pipeline.run(cell_image, analysis=first.analysis, exclude={nucleus})
    included = {e["name"] for e in second.report["elements"] if e["included"]}
    assert "nucleus" not in included and "nucleolus" in included   # orphaned child is kept
    assert not any(i["code"] == "overlap" for i in second.report["validation"]["after"]["issues"])
    assert second.report["provider"] == "previous reading"


def test_circuit_lines_are_traced(circuit_image, circuit_analysis):
    out = pipeline.run(circuit_image, analysis=circuit_analysis)
    kinds = {e["kind"] for e in out.report["elements"] if e["included"]}
    assert "line" in kinds


def test_stl_is_watertight_and_a4(cell_image, cell_analysis):
    out = pipeline.run(cell_image, analysis=cell_analysis)
    m = mesh.Mesh.from_file("tile.stl", fh=io.BytesIO(export.to_stl(out.heightmap)))
    pts = m.vectors.reshape(-1, 3)
    size = pts.max(0) - pts.min(0)
    assert abs(size[0] - 297) < 1 and abs(size[1] - 210) < 1
    _, inverse = np.unique(np.round(pts, 4), axis=0, return_inverse=True)
    tri = inverse.reshape(-1, 3)
    edges = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    assert (counts == 2).all()


def test_spoken_descriptions_and_hit_shapes(cell_image, cell_analysis):
    out = pipeline.run(cell_image, analysis=cell_analysis)
    tour = out.report["tour"]
    assert tour[0].startswith(out.report["title"]) and len(tour) == len(out.report["shapes"]) + 2
    nucleus = next(s for s in out.report["shapes"] if s["name"] == "nucleus")
    assert "inside the cell membrane" in nucleus["spoken"].lower()
    assert nucleus["type"] == "polygon" and len(nucleus["points"]) > 4
    # facts never claim a part is "above" its own container
    assert not any("'nucleolus' is" in f and "'cell membrane'" in f for f in out.facts)


def test_spatial_hit_test_prefers_the_smallest_region(cell_image, cell_analysis):
    from touchsight import spatial, tactile
    from touchsight import segment
    from touchsight import vlm
    analysis = vlm.normalise(cell_analysis)
    img = segment.load_image(cell_image)
    scene = tactile.design(segment.segment_elements(segment.remove_text(img, analysis["text_labels"]), analysis),
                           analysis, img.shape)
    nucleolus = next(e for e in scene.elements if e["name"] == "nucleolus")
    c = nucleolus["geom"].representative_point()
    assert spatial.nearest_part(scene, c.x, c.y)["name"] == "nucleolus"
