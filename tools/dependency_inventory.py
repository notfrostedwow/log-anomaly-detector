"""Record installed distribution license declarations without contacting a registry."""

import importlib.metadata
import json
from pathlib import Path


def main() -> None:
    records = []
    for distribution in importlib.metadata.distributions():
        meta = distribution.metadata
        if meta["Name"] == "log-anomaly-detector":
            continue
        licenses = [
            str(path).replace("\\", "/")
            for path in distribution.files or []
            if "license" in str(path).lower() or "copying" in str(path).lower()
        ]
        record = {
            "name": meta["Name"],
            "version": meta["Version"],
            "license_expression": meta.get("License-Expression"),
            "license_metadata": meta.get("License"),
            "license_classifiers": [
                v for v in meta.get_all("Classifier", []) if v.startswith("License ::")
            ],
            "installed_license_files": sorted(licenses),
        }
        records.append(record)
    target = Path(__file__).resolve().parents[1] / "docs" / "dependency-licenses.json"
    target.write_text(
        json.dumps(sorted(records, key=lambda r: r["name"].lower()), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(f"Recorded license metadata for {len(records)} installed third-party distributions.")


if __name__ == "__main__":
    main()
