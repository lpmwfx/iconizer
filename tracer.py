"""
PNG → SVG tracer — produces clean vector paths grouped by color.
Each color group gets an id so colors can be changed programmatically.

Usage:
    python tracer.py assets/gameeditor-icon.png output.svg --colors 12
"""

import sys
import argparse
import numpy as np
from pathlib import Path
from PIL import Image
import xml.etree.ElementTree as ET


# ── color quantization ────────────────────────────────────────────────────────

def quantize(img: Image.Image, n_colors: int) -> tuple[np.ndarray, list[tuple]]:
    """Return (index_array HxW, palette list of (r,g,b))."""
    rgb = img.convert("RGB")
    quantized = rgb.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT, dither=0)
    palette_raw = quantized.getpalette()          # flat list r,g,b,r,g,b,...
    palette = [tuple(palette_raw[i*3:i*3+3]) for i in range(n_colors)]
    index_arr = np.array(quantized, dtype=np.uint8)
    return index_arr, palette


def drop_transparent(img: Image.Image, index_arr: np.ndarray,
                      palette: list) -> tuple[np.ndarray, list]:
    """Remove palette entries that map to fully-transparent pixels."""
    if img.mode != "RGBA":
        return index_arr, palette
    alpha = np.array(img.convert("RGBA"))[:, :, 3]
    keep = []
    for i in range(len(palette)):
        mask = index_arr == i
        if alpha[mask].mean() > 10:        # mostly opaque → keep
            keep.append(i)
    remap = {old: new for new, old in enumerate(keep)}
    new_arr = np.full_like(index_arr, 255)  # 255 = transparent slot
    for old, new in remap.items():
        new_arr[index_arr == old] = new
    return new_arr, [palette[i] for i in keep]


# ── contour tracing ───────────────────────────────────────────────────────────

def _try_import_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        sys.exit("opencv-python is required:  pip install opencv-python")


def mask_to_paths(mask: np.ndarray, epsilon_factor: float, cv2) -> list[str]:
    """
    Convert a boolean mask to a list of SVG path strings.
    Uses Douglas-Peucker simplification so paths stay small.
    """
    binary = (mask.astype(np.uint8)) * 255
    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []

    # Determine a reasonable epsilon relative to image size
    diag = (mask.shape[0]**2 + mask.shape[1]**2) ** 0.5
    epsilon = max(0.5, epsilon_factor * diag / 1000)

    paths = []
    for contour in contours:
        simplified = cv2.approxPolyDP(contour, epsilon, closed=True)
        if len(simplified) < 3:
            continue
        pts = simplified.reshape(-1, 2)
        d = "M " + " L ".join(f"{x},{y}" for x, y in pts) + " Z"
        paths.append(d)
    return paths


# ── SVG assembly ──────────────────────────────────────────────────────────────

def _rgb_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _color_id(index: int, rgb: tuple) -> str:
    r, g, b = rgb
    return f"color-{index:02d}-{r:02x}{g:02x}{b:02x}"


def build_svg(width: int, height: int,
              color_paths: list[tuple[tuple, list[str]]]) -> ET.Element:
    """
    color_paths: list of ((r,g,b), [path_d_strings])
    Returns an ElementTree Element ready to serialise.
    """
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "viewBox": f"0 0 {width} {height}",
        "width": str(width),
        "height": str(height),
    })

    for idx, (rgb, path_strings) in enumerate(color_paths):
        if not path_strings:
            continue
        group = ET.SubElement(svg, "g", {
            "id": _color_id(idx, rgb),
            "fill": _rgb_hex(*rgb),
            "stroke": "none",
        })
        for d in path_strings:
            ET.SubElement(group, "path", {"d": d})

    return svg


# ── main entry ────────────────────────────────────────────────────────────────

def trace(input_path: str, output_path: str,
          n_colors: int = 12, epsilon_factor: float = 1.0,
          min_area_px: int = 20) -> None:
    cv2 = _try_import_cv2()

    img = Image.open(input_path)
    w, h = img.size

    index_arr, palette = quantize(img, n_colors)
    index_arr, palette = drop_transparent(img, index_arr, palette)

    color_paths: list[tuple[tuple, list[str]]] = []
    for i, rgb in enumerate(palette):
        mask = index_arr == i
        if mask.sum() < min_area_px:
            continue
        paths = mask_to_paths(mask, epsilon_factor, cv2)
        color_paths.append((rgb, paths))

    svg_el = build_svg(w, h, color_paths)

    tree = ET.ElementTree(svg_el)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="unicode", xml_declaration=False)
    print(f"Wrote {output_path}  ({len(color_paths)} color groups)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    p = argparse.ArgumentParser(description="Trace PNG → clean SVG with named color groups")
    p.add_argument("input",  help="Input PNG file")
    p.add_argument("output", help="Output SVG file")
    p.add_argument("--colors",  type=int,   default=12,  help="Max palette colors (default 12)")
    p.add_argument("--epsilon", type=float, default=1.0, help="Path simplification strength 0.1–5.0")
    p.add_argument("--min-area", type=int,  default=20,  help="Min pixel area to include (default 20)")
    args = p.parse_args()
    trace(args.input, args.output, args.colors, args.epsilon, args.min_area)


if __name__ == "__main__":
    _cli()
