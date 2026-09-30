from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required

from app.config_loader import pg_tables_for_target
from app.masking import algorithm_choices, DEFAULT_PG_MASKING_ALGORITHM
from app.wizard_state import get_draft, set_pg_items, new_draft

pg2pg_bp = Blueprint("pg2pg", __name__, url_prefix="/pg2pg")


@pg2pg_bp.route("/configure", methods=["GET", "POST"])
@login_required
def configure():
    draft = get_draft()
    if not draft or not draft.get("target_env"):
        flash("Choose a target environment to begin a new copy request first.", "warning")
        return redirect(url_for("dashboard.new_request"))

    target_env = draft["target_env"]
    tables = pg_tables_for_target(current_app.config["PG_TABLES_JSON_PATH"], target_env)
    is_preprod_dev = current_app.config["APP_MODE"] == "preprod_dev"

    if request.method == "POST":
        if request.form.get("skip") == "1":
            set_pg_items([])
            return redirect(url_for("adls2adls.configure"))

        items = []
        for idx, table_cfg in enumerate(tables):
            if request.form.get(f"include_{idx}") != "on":
                continue

            requested_target_table = request.form.get(
                f"target_table_{idx}", table_cfg.get("target_table", "")
            ).strip()
            original_target_table = table_cfg.get("target_table", "")
            renamed = bool(requested_target_table) and requested_target_table != original_target_table

            mode = request.form.get(f"mode_{idx}", table_cfg.get("mode", "append"))
            if renamed:
                # Requirement: renaming forces append mode + new-table creation
                # with the source schema on the target side.
                mode = "append"

            masked_columns = request.form.getlist(f"mask_col_{idx}")
            mask_algo = request.form.get(f"mask_algo_{idx}", DEFAULT_PG_MASKING_ALGORITHM)

            items.append({
                "copy_id": table_cfg.get("copy_id"),
                "source_table": table_cfg.get("source_table"),
                "target_table": requested_target_table or original_target_table,
                "target_table_renamed": renamed,
                "mode": mode if is_preprod_dev else None,
                "filter_condition": request.form.get(f"filter_{idx}", "").strip(),
                "masked_columns": masked_columns,
                "masking_algorithm": mask_algo if masked_columns else None,
                "source_jdbc_connection_string": table_cfg.get("source_jdbc_connection_string"),
                "target_jdbc_connection_string": table_cfg.get("target_jdbc_connection_string"),
                "columns": table_cfg.get("columns", []),
            })

        if not items:
            flash("No tables were selected — you can skip PG2PG instead if that's intentional.", "info")

        set_pg_items(items)
        return redirect(url_for("adls2adls.configure"))

    existing_by_copy_id = {
        item.get("copy_id"): item for item in (draft.get("pg_items") or [])
    }

    # For the single-target app (prod_preprod), GET /dashboard/new resets the
    # draft and bounces straight back here — there's no real "step 1" to
    # return to, so Back goes to the dashboard instead of silently wiping
    # whatever the user already picked on this page.
    back_url = (
        url_for("dashboard.new_request") if is_preprod_dev else url_for("dashboard.home")
    )
    back_label = "Back" if is_preprod_dev else "Cancel"

    return render_template(
        "pg2pg/configure.html",
        tables=tables,
        target_env=target_env,
        is_preprod_dev=is_preprod_dev,
        mask_algorithms=algorithm_choices(),
        existing_by_copy_id=existing_by_copy_id,
        back_url=back_url,
        back_label=back_label,
    )
