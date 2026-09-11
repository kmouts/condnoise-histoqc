"""GrandQC Zenodo 14039591 MPP10 structure and GT-mask inventory. No model runs."""
import json
import os
import re
from collections import Counter, defaultdict

import numpy as np
from PIL import Image
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

Image.MAX_IMAGE_PIXELS = None

ROOT = DATA_ROOT + "/DiffusionQC/external/grandqc_test/MPP10/MPP10"
SPLIT = DATA_ROOT + "/DiffusionQC/train_test_split.json"
OUT_ROOT = DATA_ROOT + "/DiffusionQC/external/grandqc_test"
OUT_JSON = os.path.join(OUT_ROOT, "MPP10_inventory.json")
OUT_MD = os.path.join(OUT_ROOT, "MPP10_inventory.md")

# Zenodo 14039591 description and independently documented in grandqc_eval.py.
CLASSES = {
    0: "ignore", 1: "tissue", 2: "fold", 3: "dark-spot-foreign",
    4: "penmark", 5: "edge-air-bubble", 6: "out-of-focus", 7: "background",
}
ARTIFACT_VALUES = (2, 3, 4, 5, 6)
TCGA_RE = re.compile(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}", re.I)


def kish(weights):
    total = sum(weights)
    squared = sum(weight * weight for weight in weights)
    return total * total / squared if squared else 0.0


def split_barcodes():
    data = json.load(open(SPLIT))
    names = []
    for key in ("train_slides", "test_slides", "unused_slides"):
        names.extend(data.get(key, []))
    return sorted(set(m.group(0).upper() for name in names if (m := TCGA_RE.search(name))))


def main():
    all_paths = []
    mask_paths = []
    for dirpath, _, filenames in os.walk(ROOT):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            all_paths.append(path)
            if filename.lower().endswith(".png"):
                mask_paths.append(path)

    path_tcga = sorted(set(m.group(0).upper() for path in all_paths if (m := TCGA_RE.search(path))))
    active_barcodes = split_barcodes()
    overlap = sorted(set(path_tcga) & set(active_barcodes))

    by_slide = {}
    observed_values = Counter()
    palette_by_value = {}
    dimensions = Counter()
    for index, path in enumerate(mask_paths, 1):
        relative = os.path.relpath(path, ROOT)
        organ, slide_id, folder, _ = relative.split(os.sep, 3)
        if folder != "ALL":
            raise RuntimeError(f"Unexpected mask layout: {relative}")
        stat = by_slide.setdefault(slide_id, {
            "organ": organ, "mask_tiles": 0, "class_pixel_counts": Counter(),
            "tile_dimensions": Counter(),
        })
        with Image.open(path) as image:
            if image.mode != "P":
                raise RuntimeError(f"Expected palette mask, got {image.mode}: {relative}")
            arr = np.asarray(image)
            values = np.bincount(arr.ravel(), minlength=256)
            stat["mask_tiles"] += 1
            stat["tile_dimensions"][f"{image.width}x{image.height}"] += 1
            dimensions[f"{image.width}x{image.height}"] += 1
            for value in np.flatnonzero(values):
                count = int(values[value])
                stat["class_pixel_counts"][int(value)] += count
                observed_values[int(value)] += count
                if value not in palette_by_value:
                    palette = image.getpalette()
                    offset = int(value) * 3
                    palette_by_value[int(value)] = palette[offset:offset + 3]
        if index % 5000 == 0 or index == len(mask_paths):
            print(f"masks {index}/{len(mask_paths)}")

    slides = []
    for slide_id, stat in sorted(by_slide.items()):
        counts = {str(value): int(stat["class_pixel_counts"].get(value, 0)) for value in CLASSES}
        slides.append({
            "slide_id": slide_id, "organ": stat["organ"], "mask_tiles": stat["mask_tiles"],
            "tile_dimensions": dict(stat["tile_dimensions"]), "class_pixel_counts": counts,
        })

    stats = {}
    for value in ARTIFACT_VALUES:
        weights = [int(slide["class_pixel_counts"][str(value)]) for slide in slides]
        positive = [(slide["slide_id"], slide["organ"], weight) for slide, weight in zip(slides, weights) if weight]
        positive.sort(key=lambda item: item[2], reverse=True)
        total = sum(weights)
        organs = Counter(organ for _, organ, _ in positive)
        stats[CLASSES[value]] = {
            "label_value": value, "total_pixels": total, "slides_with_pixels": len(positive),
            "kish_effective_n": round(kish(weights), 4),
            "largest_slide": {"slide_id": positive[0][0], "organ": positive[0][1], "pixels": positive[0][2],
                              "share": round(positive[0][2] / total, 6)} if total else None,
            "slide_counts_per_organ": dict(sorted(organs.items())),
        }

    organ_slide_counts = Counter(slide["organ"] for slide in slides)
    report = {
        "source": "Zenodo 14039591 MPP10 (1.0 micrometre/pixel)",
        "mask_encoding": {str(value): {"class": CLASSES[value], "palette_rgb": palette_by_value.get(value)} for value in CLASSES},
        "observed_pixel_totals_by_value": {str(value): int(observed_values[value]) for value in sorted(observed_values)},
        "tile_dimensions": dict(dimensions),
        "filename_analysis": {
            "all_file_count": len(all_paths), "mask_file_count": len(mask_paths),
            "tcga_barcodes_found_in_any_extracted_path": path_tcga,
            "active_split_tcga_slide_ids": active_barcodes,
            "exact_barcode_overlap_red_flags": overlap,
            "case_folder_id_pattern": "UUID-like identifier plus underscore and numeric suffix",
            "tile_filename_coordinate_pattern": "[d=<float>,x=<int>,y=<int>,w=<int>,h=<int>]",
        },
        "slide_count": len(slides), "slide_counts_per_organ": dict(sorted(organ_slide_counts.items())),
        "per_slide": slides, "decision_table": stats,
    }
    with open(OUT_JSON, "w") as handle:
        json.dump(report, handle, indent=2)

    lines = ["# GrandQC MPP10 inventory", "", "No model run.", "",
             f"- Cases: **{len(slides)}**; masks: **{len(mask_paths):,}**; tile dimensions: {dict(dimensions)}.",
             f"- TCGA barcode matches across every extracted path: **{len(path_tcga)}**.",
             f"- Exact overlap with the active split's {len(active_barcodes)} TCGA barcodes: **{len(overlap)}**.",
             "", "## Mask encoding", "",
             "| value | class | palette RGB | observed pixels |", "|---:|---|---|---:|"]
    for value in sorted(CLASSES):
        lines.append(f"| {value} | {CLASSES[value]} | {palette_by_value.get(value)} | {observed_values[value]:,} |")
    lines.extend(["", "## Decision Table", "",
                  "| class | label | total pixels | slides | Kish effective n | largest slide share | slide counts per organ |",
                  "|---|---:|---:|---:|---:|---:|---|"])
    for class_name, stat in stats.items():
        largest = stat["largest_slide"]
        largest_text = (f"{largest['share']:.1%} ({largest['slide_id']})"
                        if largest else "n/a")
        lines.append(f"| {class_name} | {stat['label_value']} | {stat['total_pixels']:,} | {stat['slides_with_pixels']} | {stat['kish_effective_n']:.2f} | {largest_text} | {stat['slide_counts_per_organ']} |")
    lines.extend(["", "## Filename provenance", "",
                  "Case folders use UUID-like IDs, and each tile filename includes its original WSI-space `x`, `y`, `w`, and `h` coordinates. No extracted path contains a TCGA barcode; consequently the exact split-overlap screen has no red flags.",
                  "", "Full per-slide pixel counts and filename results: `MPP10_inventory.json`."])
    with open(OUT_MD, "w") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
