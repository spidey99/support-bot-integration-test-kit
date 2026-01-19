"""CloudWatch Logs Insights query utilities.

This module provides a skeleton for querying CloudWatch Logs using Logs Insights.
Execution is gated behind offline mode - these functions will only work in Tier 3
when AWS credentials are available.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence

# Note: boto3 import is deferred to runtime to avoid issues in offline mode


class CredentialsExpiredError(Exception):
    """Raised when AWS credentials have expired."""
    
    def __init__(self, message: str, fix_command: str | None = None):
        super().__init__(message)
        self.fix_command = fix_command


@dataclass(frozen=True)
class CloudWatchQuery:
    """Configuration for a CloudWatch Logs Insights query."""

    log_groups: Sequence[str]
    query_string: str
    start_time_ms: int
    end_time_ms: int


@dataclass
class CloudWatchQueryResult:
    """Result of a CloudWatch Logs Insights query."""

    query_id: str
    status: str
    results: list[dict[str, Any]]
    statistics: dict[str, Any]


class CloudWatchLogsClient:
    """Client for CloudWatch Logs Insights queries.

    This client wraps boto3's logs client and provides a simpler interface
    for running Logs Insights queries with automatic polling for results.
    """

    def __init__(
        self,
        region: Optional[str] = None,
        offline: bool = False,
    ):
        """Initialize the CloudWatch Logs client.

        Args:
            region: AWS region (uses default if not specified)
            offline: If True, all operations will raise NotImplementedError
        """
        self._region = region
        self._offline = offline
        self._client: Any = None

    def _get_client(self) -> Any:
        """Get or create the boto3 logs client."""
        if self._offline:
            raise NotImplementedError(
                "CloudWatch operations not available in offline mode. "
                "Use fixtures for testing or set offline=False with AWS credentials."
            )

        if self._client is None:
            import boto3

            self._client = boto3.client(
                "logs",
                region_name=self._region,
            )
        return self._client

    def run_query(
        self,
        query: CloudWatchQuery,
        poll_interval_seconds: float = 1.0,
        max_wait_seconds: float = 60.0,
    ) -> CloudWatchQueryResult:
        """Run a Logs Insights query and wait for results.

        Args:
            query: The query configuration
            poll_interval_seconds: Time between status checks
            max_wait_seconds: Maximum time to wait for query completion

        Returns:
            CloudWatchQueryResult with the query results

        Raises:
            NotImplementedError: In offline mode
            CredentialsExpiredError: If AWS credentials have expired
            TimeoutError: If query doesn't complete within max_wait_seconds
            RuntimeError: If query fails
        """
        from botocore.exceptions import ClientError
        
        client = self._get_client()

        # Start the query with credential error handling
        try:
            start_response = client.start_query(
                logGroupNames=list(query.log_groups),
                startTime=query.start_time_ms // 1000,  # API expects seconds
                endTime=query.end_time_ms // 1000,
                queryString=query.query_string,
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ExpiredTokenException":
                raise CredentialsExpiredError(
                    "AWS session token has expired",
                    fix_command="aws sso login  # or refresh your MFA session",
                ) from e
            if error_code == "ResourceNotFoundException":
                # Log group doesn't exist
                missing = ", ".join(query.log_groups[:3])
                raise RuntimeError(
                    f"Log group(s) not found: {missing}. "
                    f"Run 'itk discover' to find available log groups."
                ) from e
            raise
        
        query_id = start_response["queryId"]

        # Poll for results
        elapsed = 0.0
        while elapsed < max_wait_seconds:
            try:
                result_response = client.get_query_results(queryId=query_id)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "ExpiredTokenException":
                    raise CredentialsExpiredError(
                        "AWS session token expired during query",
                        fix_command="aws sso login  # then re-run the command",
                    ) from e
                raise
            
            status = result_response["status"]

            if status == "Complete":
                # Parse results into list of dicts
                results: list[dict[str, Any]] = []
                for result_row in result_response.get("results", []):
                    row_dict: dict[str, Any] = {}
                    for field in result_row:
                        row_dict[field["field"]] = field["value"]
                    results.append(row_dict)

                return CloudWatchQueryResult(
                    query_id=query_id,
                    status=status,
                    results=results,
                    statistics=result_response.get("statistics", {}),
                )

            elif status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Query {query_id} {status.lower()}")

            # Still running - wait and try again
            time.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

        raise TimeoutError(f"Query {query_id} did not complete within {max_wait_seconds}s")

    def stop_query(self, query_id: str) -> bool:
        """Stop a running query.

        Args:
            query_id: The ID of the query to stop

        Returns:
            True if the query was stopped successfully
        """
        client = self._get_client()
        response = client.stop_query(queryId=query_id)
        return response.get("success", False)


def build_span_query(
    trace_ids: Optional[list[str]] = None,
    lambda_request_ids: Optional[list[str]] = None,
    session_ids: Optional[list[str]] = None,
    additional_filters: Optional[str] = None,
) -> str:
    """Build a Logs Insights query string for ITK span events.

    This builds a query that:
    - Looks for JSON log entries with span-like structure
    - Filters by provided correlation IDs
    - Returns fields needed for span construction

    Args:
        trace_ids: Optional list of ITK trace IDs to filter by
        lambda_request_ids: Optional list of Lambda request IDs
        session_ids: Optional list of Bedrock session IDs
        additional_filters: Optional additional query filter clauses

    Returns:
        A Logs Insights query string
    """
    # Base query - parse JSON and select span-relevant fields
    query_lines = [
        "fields @timestamp, @message, @logStream",
        "| parse @message /(?<json_msg>\\{.*\\})/",
    ]

    # Build filter conditions
    filters: list[str] = []

    if trace_ids:
        id_list = ", ".join(f'"{tid}"' for tid in trace_ids)
        filters.append(f"itk_trace_id in [{id_list}]")

    if lambda_request_ids:
        id_list = ", ".join(f'"{rid}"' for rid in lambda_request_ids)
        filters.append(f"lambda_request_id in [{id_list}]")

    if session_ids:
        id_list = ", ".join(f'"{sid}"' for sid in session_ids)
        filters.append(f"bedrock_session_id in [{id_list}]")

    if filters:
        query_lines.append(f"| filter {' or '.join(filters)}")

    if additional_filters:
        query_lines.append(f"| filter {additional_filters}")

    # Sort by timestamp
    query_lines.append("| sort @timestamp asc")

    return "\n".join(query_lines)


# Backward compatibility alias
def run_logs_insights_query(*args: Any, **kwargs: Any) -> Any:
    """Deprecated: Use CloudWatchLogsClient.run_query() instead."""
    raise NotImplementedError(
        "run_logs_insights_query is deprecated. "
        "Use CloudWatchLogsClient(offline=False).run_query() in Tier 3."
    )
