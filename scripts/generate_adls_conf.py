"""One-off generator for sample adls_*.conf seed data. Run manually if you need
to regenerate the demo config_data files. Not used at application runtime."""
import json
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "config_data"

CATEGORIES = ["inplace", "point2point", "output"]

LENS = {
    "inplace": ("customer_events_lens", "delta"),
    "point2point": ("orders_feed_lens", "parquet"),
    "output": ("reporting_marts_lens", "delta"),
}


def entry(category, source_env, target_env, container_src, container_tgt, uuid_fixed):
    lens_name, fmt = LENS[category]
    return {
        "copy-type": category,
        "source-env": source_env,
        "source-lens-name": lens_name,
        "source-lens-uuid": uuid_fixed,
        "source-adls-location": f"abfss://{container_src}@datalakestrg.dfs.core.windows.net/{category}/{lens_name}",
        "source-format": fmt,
        "target-adls-location": f"abfss://{container_tgt}@datalakestrg.dfs.core.windows.net/{category}/{lens_name}",
        "target-format": fmt,
        "target-env": target_env,
        "target-clean-up": "overwrite" if category == "output" else "append",
        "customfilters": {
            "partitioned_column": "event_date",
            "partition_column_format": "yyyy-MM-dd",
            "masking_columns": ["customer_email", "customer_phone"] if category != "output" else [],
        },
    }


def build_prod_preprod():
    for category in CATEGORIES:
        fixed_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"prod-preprod-{category}"))
        data = [entry(category, "PROD", "PREPROD", "prod-container", "preprod-container", fixed_uuid)]
        path = BASE / f"adls_{category}_prod_preprod.conf"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote {path}")


def build_preprod_dev():
    targets = ["DEV", "DEV_env1", "DEV_env2", "DEV_env3", "DEV_env4"]
    for category in CATEGORIES:
        fixed_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"preprod-dev-{category}"))
        data = [
            entry(category, "PREPROD", target, "preprod-container", f"{target.lower()}-container", fixed_uuid)
            for target in targets
        ]
        path = BASE / f"adls_{category}_preprod_dev.conf"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    build_prod_preprod()
    build_preprod_dev()
