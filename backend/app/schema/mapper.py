"""LLM-powered schema understanding and entity-to-table mapping."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .common import is_usable_column_name, strip_fenced_json

logger = logging.getLogger("schema_mapper")

_PROMPT_SCHEMA_MAX_CHARS = 12000
_PROMPT_MAX_TABLES = 24
_PROMPT_MAX_COLUMNS_PER_TABLE = 40


class SchemaMappingService:
    """Uses GPT to understand external DB schemas semantically.

    Given a raw schema, asks: "Which table stores meetings? Which holds patient data?"
    Learns the semantic structure independent of naming conventions.
    """

    def __init__(self, llm_model=None, llm_model_name: Optional[str] = None, max_retries: int = 3):
        """
        Args:
            llm_model: OpenAI client instance. If None, creates new AsyncOpenAI client.
            llm_model_name: Model name (e.g., 'gpt-4', 'gpt-3.5-turbo').
                          Defaults to env var LLM_MODEL_NAME or 'gpt-3.5-turbo'.
            max_retries: Max retry attempts for transient LLM errors (default: 3)
        """
        self.llm_model = llm_model
        self.llm_model_name = llm_model_name or os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo")
        self.max_retries = max_retries
        self.schema_cache = {}
        self._cache_expiry = {}  # Track cache expiry times

    async def auto_map_entity(
        self,
        entity_type: str,
        schema_info: Dict[str, Any],
        connector_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Use LLM to infer which table + columns map to an entity type.

        Args:
            entity_type: "meeting", "patient", "contact", "call", etc.
            schema_info: Raw schema from SchemaInspector.introspect_tables()
            connector_config: Optional org config for hints/overrides

        Returns:
            {
                "entity_type": "meeting",
                "table_name": "crm_calls",
                "id_column": "call_id",
                "column_mapping": {
                    "title": "call_subject",
                    "summary": "call_notes",
                    "participants": "attendees_json",
                    "created_at": "call_timestamp",
                    "user_id": "customer_id",
                    "owner_id": "assignee_id"
                },
                "confidence": 0.95
            }
        """
        cache_key = f"{entity_type}:{json.dumps(schema_info, sort_keys=True)}"

        # Check cache (with 1-hour TTL)
        if cache_key in self.schema_cache:
            expiry = self._cache_expiry.get(cache_key)
            if expiry and datetime.utcnow() < expiry:
                logger.info(f"Schema mapping for {entity_type} found in cache")
                return self.schema_cache[cache_key]
            else:
                # Expired cache, remove it
                del self.schema_cache[cache_key]
                if cache_key in self._cache_expiry:
                    del self._cache_expiry[cache_key]

        prompt = self._build_mapping_prompt(entity_type, schema_info, connector_config)

        try:
            # Call LLM with retry logic
            response = await self._call_llm_with_retry(prompt)
            mapping = self._parse_mapping_response(response, entity_type)

            # Validate mapping structure against raw introspected schema.
            self._validate_mapping(mapping, entity_type, schema_info)

            # Cache result with 1-hour TTL
            self.schema_cache[cache_key] = mapping
            self._cache_expiry[cache_key] = datetime.utcnow() + timedelta(hours=1)
            logger.info(f"Auto-mapped {entity_type} to table: {mapping.get('table_name')} (confidence: {mapping.get('confidence', 'N/A')})")

            return mapping
        except Exception as e:
            logger.error(f"Failed to auto-map {entity_type}: {e}")
            raise

    def _build_mapping_prompt(
        self,
        entity_type: str,
        schema_info: Dict[str, Any],
        connector_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build a prompt asking GPT to understand the schema."""

        compact_schema = self._build_compact_schema_for_prompt(schema_info, entity_type)
        tables_str = json.dumps(compact_schema, separators=(",", ":"))
        hints = ""
        if connector_config and connector_config.get("industry"):
            hints += f"\nIndustry: {connector_config.get('industry')}"
        if connector_config and connector_config.get("name"):
            hints += f"\nOrganization: {connector_config.get('name')}"

        prompt = f"""You are a database schema analyst. Given a raw database schema,
determine which table stores data for a specific entity type.

Entity Type: {entity_type}
{hints}

Database Schema:
{tables_str}

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "table_name": "<most likely table for {entity_type}>",
    "id_column": "<primary key column>",
    "column_mapping": {{
        "title": "<column storing title/name>",
        "summary": "<column storing description/summary>",
        "participants": "<column storing people/attendees>",
        "created_at": "<timestamp column or null if unavailable>",
        "user_id": "<column linking to user/creator or null if unavailable>",
        "owner_id": "<column linking to authenticated owner/assignee or null if unavailable>",
        "external_id": "<external reference column or null if unavailable>"
    }},
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

Important:
- `table_name` and `id_column` must always be real column/table names from the schema.
- For optional fields (`created_at`, `user_id`, `owner_id`, `external_id`) use JSON null when no match exists.
- Do not return empty strings.

Return ONLY the JSON, no other text."""
        return prompt

    def _build_compact_schema_for_prompt(self, schema_info: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
        """Create a compact schema summary to keep mapping prompts within model limits."""
        if not isinstance(schema_info, dict):
            return {"tables": []}

        raw_tables = schema_info.get("tables", [])
        if not isinstance(raw_tables, list):
            return {"tables": []}

        # Stable ordering: preserve original order while bringing lexical matches first.
        # Keep this generic across connectors/drivers without domain-specific aliases.
        normalized_entity = str(entity_type or "").strip().lower().replace("-", "_")
        entity_tokens = {tok for tok in normalized_entity.split("_") if tok}

        scored_tables = []
        for idx, table in enumerate(raw_tables):
            if not isinstance(table, dict):
                continue
            table_name = table.get("table_name") or table.get("name")
            if not isinstance(table_name, str) or not table_name.strip():
                continue

            normalized_name = table_name.strip().lower()
            score = 0
            if normalized_entity and normalized_name == normalized_entity:
                score += 4
            if normalized_entity and normalized_entity in normalized_name:
                score += 2
            if entity_tokens and any(tok in normalized_name for tok in entity_tokens):
                score += 1

            scored_tables.append((score, idx, table))

        scored_tables.sort(key=lambda item: (-item[0], item[1]))
        capped_tables = [table for _, _, table in scored_tables[:_PROMPT_MAX_TABLES]]

        max_cols = _PROMPT_MAX_COLUMNS_PER_TABLE
        compact_tables = self._compact_tables(capped_tables, max_cols)
        compact = {"tables": compact_tables}

        serialized = json.dumps(compact, separators=(",", ":"))
        while len(serialized) > _PROMPT_SCHEMA_MAX_CHARS and max_cols > 6:
            max_cols = max(6, int(max_cols * 0.75))
            compact_tables = self._compact_tables(capped_tables, max_cols)
            compact = {"tables": compact_tables}
            serialized = json.dumps(compact, separators=(",", ":"))

        if len(serialized) > _PROMPT_SCHEMA_MAX_CHARS:
            # Last resort: keep only table names + tiny column samples.
            compact = {
                "tables": [
                    {
                        "name": (table.get("table_name") or table.get("name")),
                        "columns": [
                            str(col) for col in ((table.get("columns") or [])[:6]) if isinstance(col, str)
                        ],
                    }
                    for table in capped_tables
                    if isinstance(table, dict)
                ]
            }

        return compact

    @staticmethod
    def _compact_tables(tables: List[Dict[str, Any]], max_cols: int) -> List[Dict[str, Any]]:
        """Return prompt-friendly table entries with limited columns and no heavy metadata."""
        compact_tables: List[Dict[str, Any]] = []
        for table in tables:
            table_name = table.get("table_name") or table.get("name")
            if not isinstance(table_name, str) or not table_name.strip():
                continue

            columns = table.get("columns", [])
            column_names: List[str] = []
            if isinstance(columns, list):
                if columns and isinstance(columns[0], dict):
                    column_names = [
                        str(col.get("name")).strip()
                        for col in columns
                        if isinstance(col, dict) and isinstance(col.get("name"), str) and col.get("name").strip()
                    ]
                else:
                    column_names = [
                        str(col).strip()
                        for col in columns
                        if isinstance(col, str) and col.strip()
                    ]

            compact_tables.append(
                {
                    "name": table_name.strip(),
                    "columns": column_names[:max_cols],
                }
            )

        return compact_tables

    async def _call_llm_with_retry(self, prompt: str, retry_count: int = 0) -> str:
        """Call LLM with exponential backoff retry logic."""
        try:
            return await self._call_llm(prompt)
        except Exception as e:
            if retry_count < self.max_retries:
                # Exponential backoff: 1s, 2s, 4s, 8s
                wait_time = 2 ** retry_count
                logger.warning(
                    f"LLM call failed (attempt {retry_count + 1}/{self.max_retries}), "
                    f"retrying in {wait_time}s: {str(e)}"
                )
                await asyncio.sleep(wait_time)
                return await self._call_llm_with_retry(prompt, retry_count + 1)
            else:
                logger.error(f"LLM call failed after {self.max_retries} retries")
                raise

    async def _call_llm(self, prompt: str) -> str:
        """Call OpenAI LLM to analyze schema.

        Uses provided llm_model client if available, otherwise creates new AsyncOpenAI client.
        """
        try:
            # Use provided client or create new one
            if self.llm_model:
                client = self.llm_model
            else:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            logger.debug(f"Calling LLM ({self.llm_model_name}) for schema analysis")

            response = await client.chat.completions.create(
                model=self.llm_model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Low temp for deterministic schema analysis
                timeout=30.0  # 30 second timeout
            )

            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("Empty response from LLM")

            return content
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            raise

    def _parse_mapping_response(self, response: str, entity_type: str) -> Dict[str, Any]:
        """Parse LLM response into structured mapping.

        Extracts JSON and validates required fields.
        """
        try:
            # Parse JSON
            mapping = json.loads(strip_fenced_json(response))
            mapping["entity_type"] = entity_type
            return mapping
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {response[:200]}...")
            raise ValueError(f"LLM response is not valid JSON: {e}") from e

    def _validate_mapping(
        self,
        mapping: Dict[str, Any],
        entity_type: str,
        schema_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Validate mapping has required fields and sanitize optional empty columns.

        Raises ValueError if mapping is invalid.
        """
        required_fields = ["table_name", "id_column", "column_mapping"]
        for field in required_fields:
            if field not in mapping:
                raise ValueError(
                    f"Invalid mapping for {entity_type}: missing required field '{field}'. "
                    f"Full mapping: {json.dumps(mapping)}"
                )

        # Validate column_mapping structure
        column_mapping = mapping.get("column_mapping", {})
        if not isinstance(column_mapping, dict):
            raise ValueError(
                f"Invalid mapping for {entity_type}: 'column_mapping' must be a dict, "
                f"got {type(column_mapping).__name__}"
            )

        table_name = mapping.get("table_name")
        id_column = mapping.get("id_column")
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError(
                f"Invalid mapping for {entity_type}: 'table_name' must be a non-empty string"
            )
        if not isinstance(id_column, str) or not id_column.strip():
            raise ValueError(
                f"Invalid mapping for {entity_type}: 'id_column' must be a non-empty string"
            )

        normalized_table_name = table_name.strip().lower()
        normalized_id_column = id_column.strip()

        # Guardrail: table/object must come from introspected schema.
        tables = schema_info.get("tables", []) if isinstance(schema_info, dict) else []
        if isinstance(tables, list) and tables:
            matched_table = None
            for table in tables:
                if not isinstance(table, dict):
                    continue
                candidate_name = table.get("table_name") or table.get("name")
                if isinstance(candidate_name, str) and candidate_name.strip().lower() == normalized_table_name:
                    matched_table = table
                    break

            if not matched_table:
                available = sorted(
                    {
                        str(table.get("table_name") or table.get("name")).strip()
                        for table in tables
                        if isinstance(table, dict) and (table.get("table_name") or table.get("name"))
                    }
                )
                raise ValueError(
                    f"Invalid mapping for {entity_type}: table/object '{table_name}' was not found in introspected schema. "
                    f"Available tables/objects: {available}"
                )

            table_columns = matched_table.get("columns")
            if isinstance(table_columns, list) and table_columns:
                normalized_columns = {
                    str(col.get("name")).strip()
                    for col in table_columns
                    if isinstance(col, dict) and col.get("name")
                }
                if not normalized_columns:
                    normalized_columns = {
                        str(col).strip() for col in table_columns if isinstance(col, str) and str(col).strip()
                    }

                if normalized_columns and normalized_id_column not in normalized_columns:
                    raise ValueError(
                        f"Invalid mapping for {entity_type}: id_column '{id_column}' is not a column in '{table_name}'"
                    )

        optional_fields = {"summary", "participants", "created_at", "user_id", "owner_id", "external_id"}
        invalid_required = {}
        sanitized_mapping: Dict[str, str] = {}

        for normalized_field, db_column in column_mapping.items():
            if is_usable_column_name(db_column):
                sanitized_mapping[normalized_field] = db_column.strip()
                continue
            elif db_column is not None:
                invalid_required[normalized_field] = db_column
                continue

            if normalized_field not in optional_fields:
                invalid_required[normalized_field] = db_column

        if invalid_required:
            raise ValueError(
                f"Invalid mapping for {entity_type}: required column_mapping fields have None/empty/invalid values: "
                f"{invalid_required}. Ensure required normalized fields map to actual DB columns."
            )

        if not sanitized_mapping:
            raise ValueError(
                f"Invalid mapping for {entity_type}: no usable column mappings were produced. "
                "Ensure at least one normalized field maps to a real DB column."
            )

        dropped_optional = sorted(
            [field for field in optional_fields if field in column_mapping and field not in sanitized_mapping]
        )
        if dropped_optional:
            logger.info(
                "Mapping for %s has no optional columns for: %s",
                entity_type,
                ", ".join(dropped_optional),
            )

        # Persist the sanitized mapping so downstream builders never receive blank values.
        mapping["column_mapping"] = sanitized_mapping

    def save_mapping_to_config(
        self,
        mapping: Dict[str, Any],
        connector_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Save a mapping to org's connector_config for future use.

        Mutates connector_config in-place to include schema mappings.
        """
        if "schema_mappings" not in connector_config:
            connector_config["schema_mappings"] = {}

        entity_type = mapping.get("entity_type")
        connector_config["schema_mappings"][entity_type] = mapping

        logger.info(f"Saved mapping for {entity_type} to config")
        return connector_config

    def get_mapping(
        self,
        entity_type: str,
        connector_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached mapping for an entity type, if available.

        Checks both in-memory cache and connector_config.
        """
        # Check in-memory cache first
        for cache_key, mapping in self.schema_cache.items():
            if entity_type in cache_key and mapping.get("entity_type") == entity_type:
                expiry = self._cache_expiry.get(cache_key)
                if expiry and datetime.utcnow() < expiry:
                    return mapping

        # Check connector_config
        if connector_config and "schema_mappings" in connector_config:
            return connector_config["schema_mappings"].get(entity_type)

        return None

    async def identify_owner_column(
        self,
        table_name: str,
        table_schema: Dict[str, Any],
        entity_type: str,
    ) -> Dict[str, Any]:
        """Use LLM to identify which column represents ownership/assignment in a table.

        Args:
            table_name: Name of the table to analyze
            table_schema: Schema info {"columns": [...], "column_types": {...}, ...}
            entity_type: Entity type (e.g., "patient", "contact") for context

        Returns:
            {
                "owner_column": "doctor_id",  # Actual DB column name
                "confidence": 0.95,
                "owner_type": "creator|owner|assignee",
                "reasoning": "..."
            }
        """
        cache_key = f"owner:{table_name}:{entity_type}"

        # Check cache (1-hour TTL)
        if cache_key in self.schema_cache:
            expiry = self._cache_expiry.get(cache_key)
            if expiry and datetime.utcnow() < expiry:
                logger.info(f"Owner column for {table_name} found in cache")
                return self.schema_cache[cache_key]
            else:
                del self.schema_cache[cache_key]
                if cache_key in self._cache_expiry:
                    del self._cache_expiry[cache_key]

        prompt = self._build_owner_column_prompt(table_name, table_schema, entity_type)

        try:
            response = await self._call_llm_with_retry(prompt)
            result = self._parse_owner_column_response(response, table_name)

            # Cache result with 1-hour TTL
            self.schema_cache[cache_key] = result
            self._cache_expiry[cache_key] = datetime.utcnow() + timedelta(hours=1)
            logger.info(f"Identified owner column for {table_name}: {result.get('owner_column')} (confidence: {result.get('confidence', 'N/A')})")

            return result
        except Exception as e:
            logger.error(f"Failed to identify owner column for {table_name}: {e}")
            raise

    def _build_owner_column_prompt(
        self,
        table_name: str,
        table_schema: Dict[str, Any],
        entity_type: str,
    ) -> str:
        """Build a prompt asking LLM to identify the owner/assignment column."""
        columns = table_schema.get("columns", [])
        column_types = table_schema.get("column_types", {})

        columns_info = "\n".join([
            f"  - {col}: {column_types.get(col, 'unknown')}"
            for col in columns
        ])

        prompt = f"""You are a database schema analyst. Given a table schema, identify which column represents ownership or assignment.

Table Name: {table_name}
Entity Type: {entity_type}

Columns:
{columns_info}

Determine which column most likely represents:
- The creator/owner of the record (e.g., created_by, owner_id, creator_id)
- OR the person it's assigned to (e.g., assigned_to, assigned_user_id, responsible_person)
- OR the user/person it belongs to (e.g., user_id, customer_id, patient_id, client_id)

Respond ONLY with valid JSON (no markdown, no explanation):
{{
    "owner_column": "<exact column name from the table>",
    "owner_type": "<creator|owner|assignee|related_user>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation of why this column was chosen>"
}}

Return ONLY the JSON, no other text."""
        return prompt

    def _parse_owner_column_response(self, response: str, table_name: str) -> Dict[str, Any]:
        """Parse LLM response into owner column info."""
        try:
            result = json.loads(strip_fenced_json(response))

            # Validate response
            if not result.get("owner_column"):
                raise ValueError("Response missing 'owner_column'")
            if not isinstance(result.get("confidence"), (int, float)):
                raise ValueError("Response missing numeric 'confidence'")

            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse owner column response: {response[:200]}...")
            raise ValueError(f"LLM response is not valid JSON: {e}") from e

    async def identify_email_column(
        self,
        table_name: str,
        table_schema: Dict[str, Any],
        user_type: str,
    ) -> Dict[str, Any]:
        """Discover which column contains email addresses using pattern matching.

        Args:
            table_name: Name of the table to analyze
            table_schema: Schema info {"columns": [...], "column_types": {...}, ...}
            user_type: User type for context (e.g., "owner", "agent", "user")

        Returns:
            {
                "email_column": "contact_email",
                "confidence": 0.95,
                "method": "pattern_matching"
            }
        """
        cache_key = f"email:{table_name}:{user_type}"

        # Check cache (1-hour TTL)
        if cache_key in self.schema_cache:
            expiry = self._cache_expiry.get(cache_key)
            if expiry and datetime.utcnow() < expiry:
                logger.info(f"Email column for {table_name} found in cache")
                return self.schema_cache[cache_key]
            else:
                del self.schema_cache[cache_key]
                if cache_key in self._cache_expiry:
                    del self._cache_expiry[cache_key]

        columns = table_schema.get("columns", [])
        column_names = [c if isinstance(c, str) else c.get("name") for c in columns]

        # Pattern-based email column discovery (common naming conventions)
        email_patterns = [
            "email",
            "mail",
            "e_mail",
            "email_address",
            "user_email",
            f"{user_type}_email",
            "contact_email",
            "address_mail",
        ]

        for pattern in email_patterns:
            for col_name in column_names:
                if col_name.lower() == pattern.lower():
                    result = {
                        "email_column": col_name,
                        "confidence": 0.95,  # High confidence for exact pattern match
                        "method": "pattern_matching",
                    }

                    # Cache result with 1-hour TTL
                    self.schema_cache[cache_key] = result
                    self._cache_expiry[cache_key] = datetime.utcnow() + timedelta(hours=1)
                    logger.info(f"Identified email column for {table_name}: {col_name}")
                    return result

        # Not found
        logger.warning(
            f"Could not identify email column in {table_name}. "
            f"Available columns: {column_names}"
        )
        return {
            "email_column": None,
            "confidence": 0,
            "method": "failed",
        }
