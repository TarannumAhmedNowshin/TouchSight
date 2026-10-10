from shapely.geometry import box

from touchsight import tactile


def region(id_, geom, parent=None, importance=2, name=None):
    return {"id": id_, "name": name or id_, "kind": "region", "importance": importance,
            "parent": parent, "geom": geom}


def test_validator_flags_size_and_spacing():
    els = [region("cell", box(20, 40, 150, 190), importance=3),
           region("speck", box(60, 80, 62, 81), parent="cell"),
           region("a", box(160, 40, 190, 80)), region("b", box(191, 40, 220, 80))]
    codes = {i.code for i in tactile.validate(els)}
    assert {"too_small", "too_close"} <= codes


def test_autofix_enlarges_tiny_parts_to_the_minimum():
    els = [region("cell", box(20, 40, 150, 190), importance=3),
           region("speck", box(60, 80, 62.5, 81), parent="cell")]
    fixed, notes = tactile.autofix(els, tactile.validate(els))
    speck = next(e for e in fixed if e["id"] == "speck")
    assert not tactile._too_small(speck["geom"])
    assert notes


def test_neighbouring_regions_never_share_a_texture():
    els = [region("cell", box(10, 30, 200, 200), importance=3),
           region("a", box(30, 50, 80, 100), parent="cell"),
           region("b", box(85, 50, 135, 100), parent="cell"),
           region("c", box(30, 105, 80, 155), parent="cell")]
    tactile.assign_textures(els)
    tex = {e["id"]: e["texture"] for e in els}
    assert tex["cell"] == "none"                    # big container stays plain
    assert len({tex["a"], tex["b"], tex["c"]}) == 3


def test_score_counts_only_unfixed_issues():
    issues = [tactile.Issue("x", "error", "m"), tactile.Issue("y", "warning", "m", fixed=True)]
    assert tactile.score(issues) == 88


def test_nesting_is_inferred_from_geometry():
    els = [region("cell", box(10, 30, 200, 200)), region("nucleus", box(50, 60, 90, 100))]
    tactile.infer_nesting(els)
    assert els[1]["parent"] == "cell"
