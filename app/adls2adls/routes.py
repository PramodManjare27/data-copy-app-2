from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required

from app.config_loader import adls_entries_for_target
from app.masking import DEFAULT_ADLS_MASKING_ALGORITHM, MASKING_ALGORITHMS
from app.wizard_state import get_draft, set_adls_items

adls2adls_bp = Blueprint("adls2adls", __name__, url_prefix="/adls2adls")

CATEGORIES = ["inplace", "point2point", "output"]
CATEGORY_LABELS = {
    "inplace": "In-Place Copy",
    "point2point": "Point-to-Point Copy",
    "output": "Output Copy",
}


@adls2adls_bp.route("/configure", methods=["GET", "POST"])
@login_required
def configure():
    draft = get_draft()
    if not draft or not draft.get("target_env"):
        flash("Choose a target environment to begin a new copy request first.", "warning")
        return redirect(url_for("dashboard.new_request"))

    target_env = draft["target_env"]
    conf_paths = current_app.config["ADLS_CONF_PATHS"]

    entries_by_category = {
        cat: adls_entries_for_target(conf_paths[cat], target_env) for cat in CATEGORIES
    }

    if request.method == "POST":
        if request.form.get("skip") == "1":
            set_adls_items([])
            return redirect(url_for("dashboard.summary"))

        items = []
        for cat in CATEGORIES:
            for idx, entry_cfg in enumerate(entries_by_category[cat]):
                field_prefix = f"{cat}_{idx}"
                if request.form.get(f"include_{field_prefix}") != "on":
                    continue

                default_filters = entry_cfg.get("customfilters", {}) or {}
                masking_columns = default_filters.get("masking_columns", []) or []

                items.append({
                    "category": cat,
                    "source_lens_name": entry_cfg.get("source-lens-name"),
                    "source_lens_uuid": entry_cfg.get("source-lens-uuid"),
                    "source_adls_location": entry_cfg.get("source-adls-location"),
                    "source_format": entry_cfg.get("source-format"),
                    "target_adls_location": entry_cfg.get("target-adls-location"),
                    "target_format": entry_cfg.get("target-format"),
                    "target_clean_up": request.form.get(
                        f"cleanup_{field_prefix}", entry_cfg.get("target-clean-up", "append")
                    ),
                    "masking_columns": masking_columns,
                    "masking_algorithm": (
                        DEFAULT_ADLS_MASKING_ALGORITHM if masking_columns else None
                    ),
                    # Custom filter overrides: user may adjust for this run only.
                    # These are logged to the audit trail but never written back
                    # to the .conf file (per requirement).
                    "partitioned_column": request.form.get(
                        f"partcol_{field_prefix}", default_filters.get("partitioned_column", "")
                    ),
                    "partition_column_format": request.form.get(
                        f"partfmt_{field_prefix}", default_filters.get("partition_column_format", "")
                    ),
                    "additional_filter": request.form.get(f"extrafilter_{field_prefix}", "").strip(),
                })

        if not items:
            flash("No ADLS locations were selected — that's fine if PG2PG covers this request.", "info")

        set_adls_items(items)
        return redirect(url_for("dashboard.summary"))

    existing_by_key = {
        (item.get("category"), item.get("source_adls_location")): item
        for item in (draft.get("adls_items") or [])
    }

    return render_template(
        "adls2adls/configure.html",
        entries_by_category=entries_by_category,
        category_labels=CATEGORY_LABELS,
        target_env=target_env,
        masking_algorithms=MASKING_ALGORITHMS,
        existing_by_key=existing_by_key,
    )
