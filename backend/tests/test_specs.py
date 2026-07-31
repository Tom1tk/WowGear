"""Sanity checks for the Icy Veins spec slug registry."""

from app.specs import SPECS_BY_CLASS


def test_no_obsolete_healer_slug_variant():
    """Icy Veins uses 'pve-healing', not 'pve-healer', in BiS URLs."""
    for class_data in SPECS_BY_CLASS.values():
        for spec in class_data["specs"]:
            assert "pve-healer-" not in spec["slug"], spec["slug"]


def test_all_slugs_follow_the_bi_s_pattern():
    for class_name, class_data in SPECS_BY_CLASS.items():
        class_segment = class_name.lower().replace(" ", "-")
        for spec in class_data["specs"]:
            assert spec["slug"].endswith("-gear-best-in-slot"), spec["slug"]
            assert class_segment in spec["slug"], (
                f"{spec['slug']} does not contain its class {class_segment}"
            )
