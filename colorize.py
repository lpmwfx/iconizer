"""
Programmatic SVG color changer for SVGs produced by tracer.py.

Each color group has an id like  color-00-ff3300
You can change colors by index, by hex, or by mapping.

Usage:
    python colorize.py input.svg output.svg --map ff3300=#00aaff  --map 001122=#ffffff
    python colorize.py input.svg output.svg --list
"""

import re
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

_ID_RE = re.compile(r"^color-(\d+)-([0-9a-f]{6})$")


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm_hex(h: str) -> str:
    """Normalise #RRGGBB or RRGGBB → rrggbb (lowercase, no #)."""
    h = h.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Bad hex color: {h!r}")
    return h


def load_svg(path: str) -> ET.ElementTree:
    return ET.parse(path)


def save_svg(tree: ET.ElementTree, path: str) -> None:
    ET.indent(tree, space="  ")
    tree.write(path, encoding="unicode", xml_declaration=False)


# ── public API ────────────────────────────────────────────────────────────────

def list_colors(tree: ET.ElementTree) -> list[dict]:
    """Return list of {index, hex, id, element} for every color group."""
    groups = []
    for el in tree.getroot().iter(f"{{{NS}}}g"):
        gid = el.get("id", "")
        m = _ID_RE.match(gid)
        if m:
            groups.append({
                "index": int(m.group(1)),
                "hex":   "#" + m.group(2),
                "id":    gid,
                "element": el,
            })
    groups.sort(key=lambda g: g["index"])
    return groups


def recolor(tree: ET.ElementTree, color_map: dict[str, str]) -> ET.ElementTree:
    """
    Change colors in-place.
    color_map: {old_hex_no_hash → new_hex_with_or_without_hash}
    Works on group fill AND inline path fills.
    """
    norm_map = {_norm_hex(k): "#" + _norm_hex(v) for k, v in color_map.items()}

    for el in tree.getroot().iter():
        fill = el.get("fill")
        if fill and fill.startswith("#"):
            key = _norm_hex(fill)
            if key in norm_map:
                el.set("fill", norm_map[key])
        # also update the id to reflect new color
        gid = el.get("id", "")
        m = _ID_RE.match(gid)
        if m:
            old_key = m.group(2)
            if old_key in norm_map:
                new_hex = _norm_hex(norm_map[old_key])
                el.set("id", f"color-{m.group(1)}-{new_hex}")

    return tree


def recolor_by_index(tree: ET.ElementTree,
                     index_map: dict[int, str]) -> ET.ElementTree:
    """Change colors by group index (0-based order)."""
    groups = list_colors(tree)
    hex_map = {}
    for idx, new_hex in index_map.items():
        matching = [g for g in groups if g["index"] == idx]
        for g in matching:
            hex_map[g["hex"].lstrip("#")] = new_hex
    return recolor(tree, hex_map)


def recolor_all(tree: ET.ElementTree,
                new_colors: list[str]) -> ET.ElementTree:
    """Replace all palette colors with a new list (in index order)."""
    groups = list_colors(tree)
    index_map = {g["index"]: new_colors[i]
                 for i, g in enumerate(groups) if i < len(new_colors)}
    return recolor_by_index(tree, index_map)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    p = argparse.ArgumentParser(description="Change SVG colors by hex or index")
    p.add_argument("input",  help="Input SVG (from tracer.py)")
    p.add_argument("output", nargs="?", help="Output SVG (omit to print list only)")
    p.add_argument("--list", action="store_true", help="Print color groups and exit")
    p.add_argument(
        "--map", metavar="OLD=NEW", action="append", default=[],
        help="Remap color: --map ff0000=#00ff00  (repeat for multiple)"
    )
    p.add_argument(
        "--index", metavar="N=HEX", action="append", default=[],
        help="Remap by group index: --index 0=#ff0000"
    )
    args = p.parse_args()

    tree = load_svg(args.input)

    if args.list or (not args.map and not args.index):
        groups = list_colors(tree)
        print(f"{'index':>6}  {'hex':>8}  id")
        print("-" * 40)
        for g in groups:
            print(f"{g['index']:>6}  {g['hex']:>8}  {g['id']}")
        return

    color_map = {}
    for entry in args.map:
        old, new = entry.split("=", 1)
        color_map[old] = new

    index_map = {}
    for entry in args.index:
        idx_str, new = entry.split("=", 1)
        index_map[int(idx_str)] = new

    if color_map:
        tree = recolor(tree, color_map)
    if index_map:
        tree = recolor_by_index(tree, index_map)

    out = args.output or args.input
    save_svg(tree, out)
    print(f"Saved → {out}")


if __name__ == "__main__":
    _cli()
