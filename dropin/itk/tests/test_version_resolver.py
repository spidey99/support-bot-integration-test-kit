"""Tests for Bedrock Agent version resolution."""
from datetime import datetime

import pytest

from itk.entrypoints.version_resolver import (
    AgentAlias,
    AgentVersion,
    ResolvedAgent,
    VersionResolver,
)


class TestVersionResolver:
    """Tests for VersionResolver class."""

    def test_resolve_with_explicit_alias(self) -> None:
        """When alias_id is provided, use it directly."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        result = resolver.resolve(
            agent_id="AGENT123",
            agent_alias_id="ALIAS456",
            agent_version=None,
        )
        
        assert result.agent_id == "AGENT123"
        assert result.agent_alias_id == "ALIAS456"
        assert result.resolved_version is None
        assert result.resolution_method == "alias"

    def test_resolve_with_draft_version(self) -> None:
        """When agent_version='draft', use TSTALIASID."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        result = resolver.resolve(
            agent_id="AGENT123",
            agent_alias_id=None,
            agent_version="draft",
        )
        
        assert result.agent_id == "AGENT123"
        assert result.agent_alias_id == "TSTALIASID"
        assert result.resolved_version == "DRAFT"
        assert result.resolution_method == "draft"

    def test_resolve_with_draft_case_insensitive(self) -> None:
        """Draft resolution is case-insensitive."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        result = resolver.resolve(
            agent_id="AGENT123",
            agent_version="DRAFT",
        )
        
        assert result.agent_alias_id == "TSTALIASID"
        assert result.resolution_method == "draft"

    def test_resolve_without_any_targeting_raises(self) -> None:
        """When neither alias nor version provided, raise error."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        with pytest.raises(ValueError, match="Either agent_alias_id or agent_version"):
            resolver.resolve(
                agent_id="AGENT123",
                agent_alias_id=None,
                agent_version=None,
            )

    def test_resolve_with_empty_alias_uses_version(self) -> None:
        """Empty string alias falls through to version resolution."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        result = resolver.resolve(
            agent_id="AGENT123",
            agent_alias_id="",  # Empty string
            agent_version="draft",
        )
        
        assert result.resolution_method == "draft"

    def test_resolve_missing_agent_id_raises(self) -> None:
        """agent_id is required."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        with pytest.raises(ValueError, match="agent_id is required"):
            resolver.resolve(
                agent_id="",
                agent_alias_id="ALIAS123",
            )

    def test_list_versions_offline_returns_mock(self) -> None:
        """Offline mode returns mock versions."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        versions = resolver.list_versions("AGENT123")
        
        assert len(versions) >= 2
        assert any(v.status == "PREPARED" for v in versions)
        assert any(v.status == "DRAFT" for v in versions)

    def test_list_aliases_offline_returns_mock(self) -> None:
        """Offline mode returns mock aliases."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        aliases = resolver.list_aliases("AGENT123")
        
        assert len(aliases) >= 2
        assert any(a.alias_name == "live" for a in aliases)
        assert any(a.alias_id == "TSTALIASID" for a in aliases)

    def test_get_latest_prepared_version(self) -> None:
        """get_latest_prepared_version returns newest PREPARED version."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        version = resolver.get_latest_prepared_version("AGENT123")
        
        # Mock returns version "2" as latest prepared
        assert version == "2"

    def test_get_draft_version(self) -> None:
        """get_draft_version returns DRAFT if exists."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        version = resolver.get_draft_version("AGENT123")
        
        assert version == "DRAFT"

    def test_find_alias_for_version(self) -> None:
        """find_alias_for_version returns matching alias."""
        resolver = VersionResolver(region="us-east-1", offline=True)
        
        alias = resolver.find_alias_for_version("AGENT123", "2")
        
        assert alias is not None
        assert alias.agent_version == "2"
        assert alias.alias_name == "live"


class TestResolvedAgent:
    """Tests for ResolvedAgent dataclass."""

    def test_resolved_agent_attributes(self) -> None:
        """ResolvedAgent has expected attributes."""
        resolved = ResolvedAgent(
            agent_id="AGENT123",
            agent_alias_id="ALIAS456",
            resolved_version="5",
            resolution_method="latest",
        )
        
        assert resolved.agent_id == "AGENT123"
        assert resolved.agent_alias_id == "ALIAS456"
        assert resolved.resolved_version == "5"
        assert resolved.resolution_method == "latest"


class TestAgentVersion:
    """Tests for AgentVersion dataclass."""

    def test_agent_version_attributes(self) -> None:
        """AgentVersion has expected attributes."""
        version = AgentVersion(
            version="3",
            agent_id="AGENT123",
            status="PREPARED",
            created_at=datetime(2026, 1, 18, 12, 0, 0),
            description="Test version",
        )
        
        assert version.version == "3"
        assert version.status == "PREPARED"


class TestAgentAlias:
    """Tests for AgentAlias dataclass."""

    def test_agent_alias_attributes(self) -> None:
        """AgentAlias has expected attributes."""
        alias = AgentAlias(
            alias_id="ALIAS123",
            alias_name="production",
            agent_id="AGENT123",
            agent_version="5",
            status="PREPARED",
        )
        
        assert alias.alias_id == "ALIAS123"
        assert alias.alias_name == "production"
        assert alias.agent_version == "5"
