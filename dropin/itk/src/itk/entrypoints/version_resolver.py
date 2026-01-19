"""Bedrock Agent version resolution.

This module provides utilities for resolving agent versions dynamically,
supporting "latest" version mode to always use the most recent PREPARED version.

Key concepts:
- Version: A specific snapshot of an agent (e.g., "1", "2", "3")
- Alias: A pointer to a version (e.g., "prod" → version "2")
- DRAFT: Working version, not yet prepared
- PREPARED: Successfully built and ready to use
- FAILED: Build failed

When agent_version="latest" is specified:
1. List all versions for the agent
2. Filter to PREPARED status only
3. Sort by createdAt descending
4. Find an alias pointing to that version
5. If no alias found, error with instructions

Special aliases:
- TSTALIASID: Built-in test alias that always points to DRAFT
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class AgentVersion:
    """Information about a Bedrock Agent version."""

    version: str
    agent_id: str
    status: str  # PREPARED, DRAFT, FAILED, DELETING
    created_at: datetime
    description: str = ""


@dataclass
class AgentAlias:
    """Information about a Bedrock Agent alias."""

    alias_id: str
    alias_name: str
    agent_id: str
    agent_version: str  # The version this alias points to
    status: str


@dataclass
class ResolvedAgent:
    """Resolved agent targeting information."""

    agent_id: str
    agent_alias_id: str  # Always resolved to an alias ID for invocation
    resolved_version: Optional[str]  # The version the alias points to (if known)
    resolution_method: str  # "alias", "latest", "draft"


class VersionResolver:
    """Resolves agent versions from Bedrock APIs.
    
    Supports:
    - Explicit alias targeting (existing behavior)
    - "latest" version (newest PREPARED version, via alias lookup)
    - "draft" version (uses TSTALIASID built-in test alias)
    """

    # Built-in test alias that always points to DRAFT
    DRAFT_ALIAS_ID = "TSTALIASID"

    def __init__(self, region: str, offline: bool = False):
        """Initialize the version resolver.
        
        Args:
            region: AWS region
            offline: If True, return mock data
        """
        self._region = region
        self._offline = offline
        self._client: Any = None
        self._version_cache: dict[str, list[AgentVersion]] = {}
        self._alias_cache: dict[str, list[AgentAlias]] = {}

    def _get_client(self) -> Any:
        """Get or create the bedrock-agent client (not runtime)."""
        if self._offline:
            raise NotImplementedError("Version resolution not available offline")
        
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-agent", region_name=self._region)
        return self._client

    def list_aliases(self, agent_id: str) -> list[AgentAlias]:
        """List all aliases for an agent.
        
        Args:
            agent_id: The agent ID
            
        Returns:
            List of AgentAlias objects
        """
        if agent_id in self._alias_cache:
            return self._alias_cache[agent_id]
        
        if self._offline:
            # Return mock aliases for testing
            return [
                AgentAlias(
                    alias_id="LIVE123",
                    alias_name="live",
                    agent_id=agent_id,
                    agent_version="2",
                    status="PREPARED",
                ),
                AgentAlias(
                    alias_id="TSTALIASID",
                    alias_name="AgentTestAlias",
                    agent_id=agent_id,
                    agent_version="DRAFT",
                    status="PREPARED",
                ),
            ]
        
        client = self._get_client()
        
        aliases: list[AgentAlias] = []
        paginator = client.get_paginator("list_agent_aliases")
        
        for page in paginator.paginate(agentId=agent_id):
            for a in page.get("agentAliasSummaries", []):
                # Get the version from routing configuration
                routing = a.get("routingConfiguration", [])
                version = routing[0].get("agentVersion", "UNKNOWN") if routing else "UNKNOWN"
                
                aliases.append(AgentAlias(
                    alias_id=a["agentAliasId"],
                    alias_name=a.get("agentAliasName", ""),
                    agent_id=agent_id,
                    agent_version=version,
                    status=a.get("agentAliasStatus", "UNKNOWN"),
                ))
        
        self._alias_cache[agent_id] = aliases
        return aliases

    def find_alias_for_version(self, agent_id: str, version: str) -> Optional[AgentAlias]:
        """Find an alias that points to a specific version.
        
        Args:
            agent_id: The agent ID
            version: The version to find an alias for
            
        Returns:
            AgentAlias if found, None otherwise
        """
        aliases = self.list_aliases(agent_id)
        
        for alias in aliases:
            if alias.agent_version == version and alias.status == "PREPARED":
                return alias
        
        return None

    def _get_client(self) -> Any:
        """Get or create the bedrock-agent client (not runtime)."""
        if self._offline:
            raise NotImplementedError("Version resolution not available offline")
        
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-agent", region_name=self._region)
        return self._client

    def list_versions(self, agent_id: str) -> list[AgentVersion]:
        """List all versions for an agent.
        
        Args:
            agent_id: The agent ID
            
        Returns:
            List of AgentVersion objects, sorted by createdAt descending
        """
        if agent_id in self._version_cache:
            return self._version_cache[agent_id]
        
        if self._offline:
            # Return mock versions for testing
            return [
                AgentVersion(
                    version="2",
                    agent_id=agent_id,
                    status="PREPARED",
                    created_at=datetime(2026, 1, 18, 12, 0, 0),
                    description="Latest prepared version",
                ),
                AgentVersion(
                    version="1",
                    agent_id=agent_id,
                    status="PREPARED",
                    created_at=datetime(2026, 1, 17, 12, 0, 0),
                    description="Previous version",
                ),
                AgentVersion(
                    version="DRAFT",
                    agent_id=agent_id,
                    status="DRAFT",
                    created_at=datetime(2026, 1, 18, 14, 0, 0),
                    description="Current draft",
                ),
            ]
        
        client = self._get_client()
        
        versions: list[AgentVersion] = []
        paginator = client.get_paginator("list_agent_versions")
        
        for page in paginator.paginate(agentId=agent_id):
            for v in page.get("agentVersionSummaries", []):
                versions.append(AgentVersion(
                    version=v["agentVersion"],
                    agent_id=agent_id,
                    status=v.get("agentStatus", "UNKNOWN"),
                    created_at=v.get("createdAt", datetime.min),
                    description=v.get("description", ""),
                ))
        
        # Sort by createdAt descending (newest first)
        versions.sort(key=lambda v: v.created_at, reverse=True)
        
        # Cache for this session
        self._version_cache[agent_id] = versions
        
        return versions

    def get_latest_prepared_version(self, agent_id: str) -> Optional[str]:
        """Get the latest PREPARED version for an agent.
        
        Args:
            agent_id: The agent ID
            
        Returns:
            Version ID string, or None if no prepared versions exist
        """
        versions = self.list_versions(agent_id)
        
        # Filter to PREPARED only
        prepared = [v for v in versions if v.status == "PREPARED"]
        
        if not prepared:
            return None
        
        # Already sorted by createdAt desc, so first is newest
        return prepared[0].version

    def get_draft_version(self, agent_id: str) -> Optional[str]:
        """Get the DRAFT version for an agent.
        
        Args:
            agent_id: The agent ID
            
        Returns:
            "DRAFT" if exists, None otherwise
        """
        versions = self.list_versions(agent_id)
        
        for v in versions:
            if v.status == "DRAFT" or v.version == "DRAFT":
                return "DRAFT"
        
        return None

    def resolve(
        self,
        agent_id: str,
        agent_alias_id: Optional[str] = None,
        agent_version: Optional[str] = None,
    ) -> ResolvedAgent:
        """Resolve agent targeting to a concrete alias ID.
        
        Priority:
        1. If agent_alias_id is provided → use directly
        2. If agent_version == "latest" → find alias for newest PREPARED version
        3. If agent_version == "draft" → use TSTALIASID
        4. If agent_version is a number → find alias for that version
        
        Args:
            agent_id: The agent ID (required)
            agent_alias_id: Optional alias ID (if provided, used directly)
            agent_version: Optional version or "latest"/"draft"
            
        Returns:
            ResolvedAgent with alias ID for invocation
            
        Raises:
            ValueError: If no valid targeting specified or resolution fails
        """
        if not agent_id:
            raise ValueError("agent_id is required")
        
        # Case 1: Alias is specified (existing behavior)
        if agent_alias_id and agent_alias_id.strip():
            return ResolvedAgent(
                agent_id=agent_id,
                agent_alias_id=agent_alias_id,
                resolved_version=None,
                resolution_method="alias",
            )
        
        # Case 2: Version is specified
        if agent_version:
            version_lower = agent_version.lower().strip()
            
            if version_lower == "latest":
                # Find the latest PREPARED version
                latest_version = self.get_latest_prepared_version(agent_id)
                if not latest_version:
                    raise ValueError(
                        f"No PREPARED versions found for agent {agent_id}. "
                        f"Prepare a version before using 'latest' mode."
                    )
                
                # Find an alias pointing to this version
                alias = self.find_alias_for_version(agent_id, latest_version)
                if not alias:
                    # List what aliases exist for better error message
                    aliases = self.list_aliases(agent_id)
                    alias_info = ", ".join(
                        f"{a.alias_name}→v{a.agent_version}" 
                        for a in aliases if a.alias_id != self.DRAFT_ALIAS_ID
                    )
                    raise ValueError(
                        f"No alias found pointing to latest version {latest_version}. "
                        f"Available aliases: [{alias_info}]. "
                        f"Update an alias to point to version {latest_version}, or use "
                        f"agent_alias_id directly."
                    )
                
                return ResolvedAgent(
                    agent_id=agent_id,
                    agent_alias_id=alias.alias_id,
                    resolved_version=latest_version,
                    resolution_method="latest",
                )
            
            elif version_lower == "draft":
                # Use the built-in test alias
                return ResolvedAgent(
                    agent_id=agent_id,
                    agent_alias_id=self.DRAFT_ALIAS_ID,
                    resolved_version="DRAFT",
                    resolution_method="draft",
                )
            
            else:
                # Explicit version number - find an alias for it
                alias = self.find_alias_for_version(agent_id, agent_version)
                if not alias:
                    aliases = self.list_aliases(agent_id)
                    alias_info = ", ".join(
                        f"{a.alias_name}→v{a.agent_version}" 
                        for a in aliases if a.alias_id != self.DRAFT_ALIAS_ID
                    )
                    raise ValueError(
                        f"No alias found pointing to version {agent_version}. "
                        f"Available aliases: [{alias_info}]. "
                        f"Create or update an alias to point to version {agent_version}."
                    )
                
                return ResolvedAgent(
                    agent_id=agent_id,
                    agent_alias_id=alias.alias_id,
                    resolved_version=agent_version,
                    resolution_method="version",
                )
        
        # Case 3: Nothing specified
        raise ValueError(
            "Either agent_alias_id or agent_version must be specified. "
            "Use agent_version='latest' to auto-select the newest PREPARED version, "
            "or agent_version='draft' to test against DRAFT."
        )


def resolve_agent_target(
    agent_id: str,
    agent_alias_id: Optional[str] = None,
    agent_version: Optional[str] = None,
    region: str = "us-east-1",
    offline: bool = False,
) -> ResolvedAgent:
    """Convenience function to resolve agent targeting.
    
    Args:
        agent_id: The agent ID
        agent_alias_id: Optional alias ID (used directly if provided)
        agent_version: Optional version or "latest"/"draft"
        region: AWS region
        offline: If True, return mock data
        
    Returns:
        ResolvedAgent with alias ID for invocation
    """
    resolver = VersionResolver(region=region, offline=offline)
    return resolver.resolve(
        agent_id=agent_id,
        agent_alias_id=agent_alias_id,
        agent_version=agent_version,
    )
