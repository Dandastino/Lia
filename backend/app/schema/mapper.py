"""LLM-powered schema understanding and entity-to-table mapping."""
from __future__ import annotations

import json
import os
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("schema_mapper")


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
                    "user_id": "customer_id"
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
            
            # Validate mapping structure
            self._validate_mapping(mapping, entity_type)
            
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
        
        tables_str = json.dumps(schema_info, indent=2)
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
        "created_at": "<timestamp column>",
        "user_id": "<column linking to user/creator>",
        "external_id": "<any external reference column>"
    }},
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

Return ONLY the JSON, no other text."""
        return prompt

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
            # Strip markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            
            # Parse JSON
            mapping = json.loads(clean_response.strip())
            mapping["entity_type"] = entity_type
            return mapping
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {response[:200]}...")
            raise ValueError(f"LLM response is not valid JSON: {e}")
    
    def _validate_mapping(self, mapping: Dict[str, Any], entity_type: str) -> None:
        """Validate mapping has required fields and no None columns.
        
        Raises ValueError if mapping is invalid.
        """
        required_fields = ["table_name", "id_column", "column_mapping"]
        for field in required_fields:
            if field not in mapping:
                raise ValueError(
                    f"Invalid mapping for {entity_type}: missing required field '{field}'. "
                    f"Full mapping: {json.dumps(mapping)}"
                )
        
        # Validate column_mapping has no None values
        column_mapping = mapping.get("column_mapping", {})
        if not isinstance(column_mapping, dict):
            raise ValueError(
                f"Invalid mapping for {entity_type}: 'column_mapping' must be a dict, "
                f"got {type(column_mapping).__name__}"
            )
        
        invalid_columns = {
            k: v for k, v in column_mapping.items()
            if v is None or (isinstance(v, str) and not v.strip())
        }
        if invalid_columns:
            raise ValueError(
                f"Invalid mapping for {entity_type}: column_mapping has None/empty values: {invalid_columns}. "
                f"Ensure all normalized fields map to actual DB columns."
            )

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
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            
            result = json.loads(clean_response.strip())
            
            # Validate response
            if not result.get("owner_column"):
                raise ValueError("Response missing 'owner_column'")
            if not isinstance(result.get("confidence"), (int, float)):
                raise ValueError("Response missing numeric 'confidence'")
            
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse owner column response: {response[:200]}...")
            raise ValueError(f"LLM response is not valid JSON: {e}")

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
            user_type: User type for context (e.g., "doctor", "lawyer")
            
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
