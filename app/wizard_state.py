"""
Session-backed draft state for the multi-step copy wizard:

  1. Pick target environment (fixed to PREPROD for the prod_preprod app;
     chosen from DEV/DEV_env1..4 for the preprod_dev app).
  2. Optionally configure one or more PG2PG table copies.
  3. Optionally configure one or more ADLS2ADLS location copies.
  4. Review a summary and confirm/submit.

Either step 2 or step 3 may be skipped entirely, but not both (there must be
at least one item to submit).
"""
from flask import session

DRAFT_KEY = "copy_draft"


def new_draft(target_env: str) -> dict:
    draft = {"target_env": target_env, "pg_items": [], "adls_items": []}
    session[DRAFT_KEY] = draft
    session.modified = True
    return draft


def get_draft() -> dict | None:
    return session.get(DRAFT_KEY)


def save_draft(draft: dict) -> None:
    session[DRAFT_KEY] = draft
    session.modified = True


def clear_draft() -> None:
    session.pop(DRAFT_KEY, None)
    session.modified = True


def set_pg_items(items: list) -> None:
    draft = get_draft() or new_draft("")
    draft["pg_items"] = items
    save_draft(draft)


def set_adls_items(items: list) -> None:
    draft = get_draft() or new_draft("")
    draft["adls_items"] = items
    save_draft(draft)
