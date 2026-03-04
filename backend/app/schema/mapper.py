"""LLM-powered schema understanding and entity-to-table mapping."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("schema_mapper")


class SchemaMappingService:
    """Uses GPT to understand external DB schemas semantically.
    
    Given a raw schema, asks: "Which table stores meetings? Which holds patient data?"
    Learns the semantic structure independent of naming conventions.
    """

    def __init__(self, llm_model=None):
        """
        Args:
            llm_model: OpenAI model instance (e.g., openai.ChatCompletion or similar).
                      If None, uses environment OpenAI key.
        """
        self.llm_model = llm_model
        self.schema_cache = {}

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
        if cache_key in self.schema_cache:
            logger.info(f"Schema mapping for {entity_type} found in cache")
            return self.schema_cache[cache_key]

        prompt = self._build_mapping_prompt(entity_type, schema_info, connector_config)
        
        try:
            # Call LLM to analyze schema
            response = await self._call_llm(prompt)
            mapping = self._parse_mapping_response(response, entity_type)
            
            # Cache result
            self.schema_cache[cache_key] = mapping
            logger.info(f"Auto-mapped {entity_type} to table: {mapping.get('table_name')}")
            
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

    async def _call_llm(self, prompt: str) -> str:
        """Call OpenAI or other LLM to analyze schema."""
        # This assumes openai client is available via self.llm_model
        # or we can use the global openai module
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI()
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Low temp for deterministic schema analysis
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_mapping_response(self, response: str, entity_type: str) -> Dict[str, Any]:
        """Parse LLM response into structured mapping."""
        try:
            # Try to extract JSON from response
            mapping = json.loads(response.strip())
            mapping["entity_type"] = entity_type
            return mapping
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {response}")
            raise ValueError(f"Invalid LLM response: {e}")

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
        """Retrieve cached mapping for an entity type, if available."""
        if connector_config and "schema_mappings" in connector_config:
            return connector_config["schema_mappings"].get(entity_type)
        return None
