from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

from ..schema.query_builder import DynamicQueryBuilder, is_safe_identifier


def get_entity_mapping(config: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
    """Fetch schema mapping for entity type or raise a clear error."""
    mapping = (config.get("schema_mappings") or {}).get(entity_type)
    if not mapping:
        raise ValueError(f"No schema mapping for entity type: {entity_type}")
    return mapping


def get_owner_scope(driver: Any) -> Tuple[Optional[str], Optional[str]]:
    """Read per-request owner context injected by DataManager."""
    owner_col = getattr(driver, "request_owner_column", None)
    owner_id = getattr(driver, "request_owner_id", None)
    return owner_col, owner_id


def apply_owner_scope_to_params(
    params: Dict[str, Any],
    owner_col: Optional[str],
    owner_id: Optional[str],
) -> bool:
    """Inject owner FK into insert params when available.

    The owner scope is authoritative and overrides any caller-supplied value, so a
    record can only be created inside the requesting user's own scope.

    Returns True if owner scope was applied.
    """
    if owner_col and owner_id:
        if not is_safe_identifier(owner_col):
            raise ValueError("Unsafe owner column name")
        params[owner_col] = owner_id
        return True
    return False


def add_owner_constraint_to_sql(
    sql: str,
    owner_col: Optional[str],
    owner_id: Optional[str],
) -> Tuple[str, Dict[str, Any]]:
    """Append owner constraint to update/delete SQL statements."""
    if not owner_col or not owner_id:
        return sql, {}
    if not is_safe_identifier(owner_col):
        raise ValueError("Unsafe owner column name")

    if " RETURNING *" in sql:
        return sql.replace(" RETURNING *", f" AND {owner_col} = :__owner_id RETURNING *"), {"__owner_id": owner_id}
    return f"{sql} AND {owner_col} = :__owner_id", {"__owner_id": owner_id}


def split_limit_and_query_filters(
    filters: Optional[Dict[str, Any]],
    user_id: Optional[str],
    builder: DynamicQueryBuilder,
    owner_col: Optional[str],
    owner_id: Optional[str],
) -> Tuple[int, Dict[str, Any]]:
    """Build safe query filters and extract limit without mutating input."""
    limit = 20
    query_filters: Dict[str, Any] = {}

    if filters:
        limit = filters.get("limit", 20)
        query_filters = {
            key: value
            for key, value in filters.items()
            if key != "limit" and value is not None
        }

    if user_id and "user_id" in builder.column_mapping and builder.column_mapping.get("user_id"):
        query_filters["user_id"] = user_id

    if owner_col and owner_id:
        query_filters[owner_col] = owner_id

    return limit, query_filters


def resolve_required_columns(
    inspector: Any,
    mapping: Dict[str, Any],
    table_name: str,
    id_column: str,
) -> List[str]:
    """Return required (NOT NULL, no default, non-autoincrement) DB columns.

    Source of truth is live schema introspection to avoid stale mapping metadata.
    Falls back to stored mapping only if introspection is unavailable.
    """
    try:
        table_columns = inspector.get_columns(table_name)
        resolved: List[str] = []
        for col in table_columns:
            col_name = col.get("name")
            if not col_name or col_name == id_column:
                continue
            if col.get("nullable", True):
                continue
            if col.get("default") is not None:
                continue
            if col.get("autoincrement"):
                continue
            resolved.append(col_name)
        return resolved
    except Exception:
        required_columns = mapping.get("required_columns")
        if isinstance(required_columns, list):
            return required_columns
        return []


def find_missing_required_columns(required_columns: List[str], params: Dict[str, Any]) -> List[str]:
    """Find required DB columns still missing from insert params."""
    return [col for col in required_columns if col not in params]


def build_required_alias_hints(builder: DynamicQueryBuilder, missing_required: List[str]) -> Dict[str, str]:
    """Map missing DB columns back to normalized field aliases when available."""
    required_aliases = {
        db_col: norm_field
        for norm_field, db_col in builder.column_mapping.items()
        if isinstance(db_col, str)
    }
    return {col: required_aliases[col] for col in missing_required if col in required_aliases}


def looks_like_id(value: str) -> bool:
    """Heuristic for raw ID-like values."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.isdigit():
        return True
    return bool(re.fullmatch(r"[0-9a-fA-F-]{8,}", stripped))


def _is_safe_identifier(value: str) -> bool:
    """Allow only conservative SQL identifiers from introspected metadata."""
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""))


def _build_label_candidates_from_mapping(
    config: Optional[Dict[str, Any]],
    referred_table: str,
    ref_columns: List[str],
) -> List[str]:
    """Use LLM-generated schema mappings as primary source for label columns."""
    if not isinstance(config, dict):
        return []

    schema_mappings = config.get("schema_mappings") or {}
    if not isinstance(schema_mappings, dict):
        return []

    mapped_columns: List[str] = []
    for mapping in schema_mappings.values():
        if not isinstance(mapping, dict):
            continue
        table_name = mapping.get("table_name")
        if not isinstance(table_name, str) or table_name != referred_table:
            continue

        column_mapping = mapping.get("column_mapping")
        if not isinstance(column_mapping, dict):
            continue

        # Prioritize semantically identifying fields inferred by LLM.
        preferred_keys = [
            "title",
            "external_id",
            "summary",
            "user_id",
            "owner_id",
        ]
        for key in preferred_keys:
            mapped_col = column_mapping.get(key)
            if isinstance(mapped_col, str) and mapped_col in ref_columns:
                mapped_columns.append(mapped_col)

        for mapped_col in column_mapping.values():
            if isinstance(mapped_col, str) and mapped_col in ref_columns:
                mapped_columns.append(mapped_col)

    return list(dict.fromkeys(mapped_columns))


def _build_fallback_label_candidates(ref_columns_meta: List[Dict[str, Any]], ref_columns: List[str]) -> List[str]:
    """Fallback label candidates when LLM mappings are unavailable for ref table."""
    ref_columns_by_name = {
        c.get("name"): c
        for c in ref_columns_meta
        if isinstance(c, dict) and isinstance(c.get("name"), str)
    }

    # Prefer text-like fields and avoid common FK/system columns.
    text_like: List[str] = []
    for col_name in ref_columns:
        if col_name.endswith("_id") or col_name in {"id", "created_at", "updated_at"}:
            continue
        col_meta = ref_columns_by_name.get(col_name, {})
        col_type = str(col_meta.get("type", "")).lower()
        if any(token in col_type for token in ["char", "text", "string", "uuid"]):
            text_like.append(col_name)

    return text_like


def resolve_foreign_key_values(
    inspector: Any,
    table_name: str,
    params: Dict[str, Any],
    payload: Dict[str, Any],
    session_factory: Callable[[], Any],
    cast_as: str,
    logger: Any,
    config: Optional[Dict[str, Any]] = None,
    owner_scope: Optional[Tuple[Optional[str], Optional[str]]] = None,
) -> List[str]:
    """Best-effort FK resolver using payload and related_entities hints."""
    foreign_keys = inspector.get_foreign_keys(table_name) or []
    related_entities = payload.get("related_entities") if isinstance(payload.get("related_entities"), dict) else {}
    unresolved_hint_columns: List[str] = []

    logger.debug(
        "FK resolver start table=%s fk_count=%s payload_keys=%s related_keys=%s",
        table_name,
        len(foreign_keys),
        sorted(list(payload.keys())),
        sorted(list(related_entities.keys())),
    )

    for fk in foreign_keys:
        constrained = fk.get("constrained_columns") or []
        referred_columns = fk.get("referred_columns") or []
        referred_table = fk.get("referred_table")

        if len(constrained) != 1 or len(referred_columns) != 1 or not referred_table:
            continue

        fk_col = constrained[0]
        ref_col = referred_columns[0]
        if fk_col in params:
            continue

        if not (_is_safe_identifier(referred_table) and _is_safe_identifier(ref_col) and _is_safe_identifier(fk_col)):
            logger.warning(
                "Skipping FK resolution for unsafe identifiers table=%r fk_col=%r ref_col=%r",
                referred_table,
                fk_col,
                ref_col,
            )
            continue

        base_fk_name = fk_col[:-3] if fk_col.endswith("_id") else fk_col
        direct_hints = [
            payload.get(fk_col),
            payload.get(base_fk_name),
            payload.get(referred_table),
            payload.get(f"{referred_table}_id"),
            related_entities.get(fk_col),
            related_entities.get(base_fk_name),
            related_entities.get(referred_table),
        ]

        raw_hint = next((h for h in direct_hints if h is not None), None)
        if raw_hint is None:
            continue

        logger.debug(
            "FK hint detected table=%s fk_col=%s ref_table=%s raw_hint=%r",
            table_name,
            fk_col,
            referred_table,
            raw_hint,
        )

        if isinstance(raw_hint, (int, float)):
            params[fk_col] = raw_hint
            continue

        if not isinstance(raw_hint, str):
            continue

        hint = raw_hint.strip()
        if not hint:
            continue

        if looks_like_id(hint):
            params[fk_col] = hint
            logger.debug("FK direct id accepted table=%s fk_col=%s value=%s", table_name, fk_col, hint)
            continue

        try:
            ref_columns_meta = inspector.get_columns(referred_table)
        except Exception:  # noqa: S112 - best-effort, failure is expected and handled by the caller
            continue

        ref_columns = [c.get("name") for c in ref_columns_meta if isinstance(c, dict) and c.get("name")]
        mapped_candidates = _build_label_candidates_from_mapping(config, referred_table, ref_columns)
        fallback_candidates = _build_fallback_label_candidates(ref_columns_meta, ref_columns)
        candidate_label_columns = [
            col for col in list(dict.fromkeys(mapped_candidates + fallback_candidates)) if _is_safe_identifier(col)
        ]

        owner_scope_col = None
        owner_scope_id = None
        if owner_scope and len(owner_scope) == 2:
            owner_scope_col, owner_scope_id = owner_scope
        can_scope_ref_lookup = (
            isinstance(owner_scope_col, str)
            and owner_scope_col in ref_columns
            and _is_safe_identifier(owner_scope_col)
            and owner_scope_id is not None
        )

        resolved_id = None
        ambiguous_match = False
        with session_factory() as session:
            for label_col in candidate_label_columns:
                if can_scope_ref_lookup:
                    lookup_sql = text(
                        f"SELECT {ref_col} FROM {referred_table} "
                        f"WHERE LOWER(CAST({label_col} AS {cast_as})) = LOWER(:lookup_value) "
                        f"AND {owner_scope_col} = :owner_scope_id LIMIT 2"
                    )
                    rows = session.execute(
                        lookup_sql,
                        {"lookup_value": hint, "owner_scope_id": owner_scope_id},
                    ).fetchall()
                else:
                    lookup_sql = text(
                        f"SELECT {ref_col} FROM {referred_table} "
                        f"WHERE LOWER(CAST({label_col} AS {cast_as})) = LOWER(:lookup_value) LIMIT 2"
                    )
                    rows = session.execute(lookup_sql, {"lookup_value": hint}).fetchall()

                if len(rows) == 1:
                    resolved_id = rows[0][0]
                    break

                if len(rows) > 1:
                    logger.warning(
                        "FK lookup ambiguous table=%s fk_col=%s label_col=%s hint=%r matches=%s",
                        table_name,
                        fk_col,
                        label_col,
                        hint,
                        len(rows),
                    )
                    ambiguous_match = True
                    resolved_id = None
                    break

            if resolved_id is None and " " in hint:
                parts = [p for p in hint.split() if p]
                if len(parts) >= 2:
                    full_name = " ".join(parts)
                    pair_candidates = [c for c in fallback_candidates if _is_safe_identifier(c)]
                    for idx, first_col in enumerate(pair_candidates):
                        for last_col in pair_candidates[idx + 1:]:
                            if can_scope_ref_lookup:
                                lookup_sql = text(
                                    f"SELECT {ref_col} FROM {referred_table} "
                                    f"WHERE ("
                                    f"LOWER(CONCAT(CAST({first_col} AS {cast_as}), ' ', CAST({last_col} AS {cast_as}))) = LOWER(:full_name) "
                                    f"OR LOWER(CONCAT(CAST({last_col} AS {cast_as}), ' ', CAST({first_col} AS {cast_as}))) = LOWER(:full_name)"
                                    f") "
                                    f"AND {owner_scope_col} = :owner_scope_id LIMIT 2"
                                )
                                rows = session.execute(
                                    lookup_sql,
                                    {
                                        "full_name": full_name,
                                        "owner_scope_id": owner_scope_id,
                                    },
                                ).fetchall()
                            else:
                                lookup_sql = text(
                                    f"SELECT {ref_col} FROM {referred_table} "
                                    f"WHERE ("
                                    f"LOWER(CONCAT(CAST({first_col} AS {cast_as}), ' ', CAST({last_col} AS {cast_as}))) = LOWER(:full_name) "
                                    f"OR LOWER(CONCAT(CAST({last_col} AS {cast_as}), ' ', CAST({first_col} AS {cast_as}))) = LOWER(:full_name)"
                                    f") LIMIT 2"
                                )
                                rows = session.execute(
                                    lookup_sql,
                                    {"full_name": full_name},
                                ).fetchall()

                            if len(rows) == 1:
                                resolved_id = rows[0][0]
                                break

                            if len(rows) > 1:
                                logger.warning(
                                    "FK full-name lookup ambiguous table=%s fk_col=%s hint=%r matches=%s",
                                    table_name,
                                    fk_col,
                                    hint,
                                    len(rows),
                                )
                                ambiguous_match = True
                                resolved_id = None
                                break
                        if resolved_id is not None:
                            break

        if resolved_id is not None:
            params[fk_col] = str(resolved_id)
            logger.info(
                "FK resolved table=%s fk_col=%s ref_table=%s ref_col=%s resolved_id=%s",
                table_name,
                fk_col,
                referred_table,
                ref_col,
                resolved_id,
            )
        else:
            if fk_col not in unresolved_hint_columns:
                unresolved_hint_columns.append(fk_col)
            logger.warning(
                "FK unresolved table=%s fk_col=%s ref_table=%s hint=%r",
                table_name,
                fk_col,
                referred_table,
                hint if not ambiguous_match else f"{hint} (ambiguous match)",
            )

    return unresolved_hint_columns
