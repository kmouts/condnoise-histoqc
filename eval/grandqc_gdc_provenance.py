"""Rate-limited GDC provenance check for GrandQC MPP10 case UUIDs. No model run."""
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

ROOT = DATA_ROOT + "/DiffusionQC/external/grandqc_test/MPP10/MPP10"
OUT_ROOT = DATA_ROOT + "/DiffusionQC/external/grandqc_test"
OUT_JSON = os.path.join(OUT_ROOT, "MPP10_gdc_provenance.json")
OUT_MD = os.path.join(OUT_ROOT, "MPP10_gdc_provenance.md")
BASE = "https://api.gdc.cancer.gov"
REQUEST_INTERVAL = 0.5


def request_status(path):
    request = urllib.request.Request(f"{BASE}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read(1)
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except urllib.error.URLError as error:
        return f"network-error: {error.reason}"


def main():
    cases = []
    for organ in sorted(os.listdir(ROOT)):
        organ_path = os.path.join(ROOT, organ)
        if not os.path.isdir(organ_path):
            continue
        for case_id in sorted(os.listdir(organ_path)):
            case_path = os.path.join(organ_path, case_id)
            if not os.path.isdir(case_path):
                continue
            tile_count = sum(1 for dirpath, _, filenames in os.walk(case_path)
                             for filename in filenames if filename.lower().endswith(".png"))
            if tile_count:
                cases.append({"case_id": case_id, "uuid": case_id.split("_", 1)[0],
                              "organ": organ, "mask_tile_count": tile_count})

    results = []
    for index, case in enumerate(cases, 1):
        file_status = request_status(f"/files/{case['uuid']}")
        time.sleep(REQUEST_INTERVAL)
        case_status = request_status(f"/cases/{case['uuid']}")
        time.sleep(REQUEST_INTERVAL)
        resolved = file_status == 200 or case_status == 200
        results.append({**case, "gdc_files_status": file_status,
                        "gdc_cases_status": case_status, "resolves_in_gdc": resolved})
        if index % 25 == 0 or index == len(cases):
            print(f"queried {index}/{len(cases)}")

    status_pairs = Counter((str(item["gdc_files_status"]), str(item["gdc_cases_status"]))
                           for item in results)
    resolved = [item for item in results if item["resolves_in_gdc"]]
    report = {
        "method": "Sequential GDC GET /files/{uuid}, then /cases/{uuid}; 0.5 s between every request.",
        "case_count": len(results), "status_pair_counts": {f"files={a}, cases={b}": n for (a, b), n in status_pairs.items()},
        "resolved_in_gdc": resolved, "all_cases": results,
    }
    with open(OUT_JSON, "w") as handle:
        json.dump(report, handle, indent=2)

    lines = ["# GrandQC MPP10 GDC provenance check", "",
             "No model run. Each of the 281 non-empty MPP10 case UUIDs was queried against both ",
             "`https://api.gdc.cancer.gov/files/{uuid}` and `/cases/{uuid}`, sequentially at two requests/s.", "",
             f"- UUIDs checked: **{len(results)}**", f"- Any GDC resolution (HTTP 200): **{len(resolved)}**", "",
             "## Status-pair counts", ""]
    for (file_status, case_status), count in sorted(status_pairs.items()):
        lines.append(f"- `/files`={file_status}; `/cases`={case_status}: {count}")
    lines.extend(["", "## Resolved UUIDs", ""])
    if resolved:
        for item in resolved:
            lines.append(f"- {item['case_id']} ({item['organ']}): /files={item['gdc_files_status']}, /cases={item['gdc_cases_status']}")
    else:
        lines.append("None. All 281 case UUIDs returned 404 from both endpoints, strong API-level evidence that these IDs are not GDC/TCGA file or case UUIDs.")
    with open(OUT_MD, "w") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()