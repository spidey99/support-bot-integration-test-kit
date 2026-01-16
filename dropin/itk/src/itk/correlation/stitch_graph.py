"""Build a correlation graph from spans using shared IDs.

The stitch graph algorithm:
1. Build an adjacency list based on shared correlation IDs
2. Starting from seed spans, expand to discover related spans
3. Merge overlapping span groups
4. Return a unified set of correlated spans
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional, Set

from itk.trace.span_model import Span


@dataclass
class StitchResult:
    """Result of stitching spans together."""

    spans: list[Span]
    notes: list[str]
    correlation_groups: list[set[str]] = field(default_factory=list)


def _get_span_correlation_keys(span: Span) -> set[str]:
    """Get all correlation keys from a span.

    Each key is prefixed with its type for uniqueness:
    - itk:xxx for ITK trace IDs
    - lambda:xxx for Lambda request IDs
    - xray:xxx for X-Ray trace IDs
    - sqs:xxx for SQS message IDs
    - bedrock:xxx for Bedrock session IDs
    """
    keys: set[str] = set()

    if span.itk_trace_id:
        keys.add(f"itk:{span.itk_trace_id}")
    if span.lambda_request_id:
        keys.add(f"lambda:{span.lambda_request_id}")
    if span.xray_trace_id:
        keys.add(f"xray:{span.xray_trace_id}")
    if span.sqs_message_id:
        keys.add(f"sqs:{span.sqs_message_id}")
    if span.bedrock_session_id:
        keys.add(f"bedrock:{span.bedrock_session_id}")

    return keys


def _build_adjacency_index(
    spans: list[Span],
) -> tuple[dict[str, set[str]], dict[str, Span]]:
    """Build an index mapping correlation keys to span IDs.

    Returns:
        - key_to_spans: Map from correlation key to set of span IDs
        - span_by_id: Map from span ID to Span
    """
    key_to_spans: dict[str, set[str]] = defaultdict(set)
    span_by_id: dict[str, Span] = {}

    for span in spans:
        span_by_id[span.span_id] = span
        keys = _get_span_correlation_keys(span)
        for key in keys:
            key_to_spans[key].add(span.span_id)

    return dict(key_to_spans), span_by_id


def _expand_from_seed(
    seed_span_id: str,
    key_to_spans: dict[str, set[str]],
    span_by_id: dict[str, Span],
) -> set[str]:
    """Expand from a seed span to find all transitively related spans.

    Uses BFS to find all spans that share any correlation ID with
    the seed or any already-discovered span.
    """
    discovered: set[str] = {seed_span_id}
    frontier: list[str] = [seed_span_id]

    while frontier:
        current_id = frontier.pop(0)
        current_span = span_by_id.get(current_id)
        if not current_span:
            continue

        # Get all keys for this span
        keys = _get_span_correlation_keys(current_span)

        # Find all spans sharing any of these keys
        for key in keys:
            related_ids = key_to_spans.get(key, set())
            for related_id in related_ids:
                if related_id not in discovered:
                    discovered.add(related_id)
                    frontier.append(related_id)

    return discovered


def stitch_spans_by_id(
    spans: Iterable[Span],
    seed_span_ids: Optional[set[str]] = None,
) -> StitchResult:
    """Stitch spans together based on shared correlation IDs.

    Args:
        spans: Input spans to stitch
        seed_span_ids: Optional set of span IDs to start expansion from.
                       If None, uses all spans with at least one correlation ID.

    Returns:
        StitchResult with stitched spans and notes about the process.
    """
    span_list = list(spans)
    if not span_list:
        return StitchResult(spans=[], notes=["No spans to stitch"])

    key_to_spans, span_by_id = _build_adjacency_index(span_list)
    notes: list[str] = []

    # Determine seeds
    if seed_span_ids is None:
        # Use all spans that have correlation IDs
        seed_span_ids = {
            s.span_id for s in span_list if _get_span_correlation_keys(s)
        }

    if not seed_span_ids:
        notes.append("No spans with correlation IDs found; returning all spans")
        return StitchResult(spans=span_list, notes=notes)

    # Expand from seeds to find all correlated spans
    all_discovered: set[str] = set()
    correlation_groups: list[set[str]] = []

    for seed_id in seed_span_ids:
        if seed_id in all_discovered:
            continue
        group = _expand_from_seed(seed_id, key_to_spans, span_by_id)
        correlation_groups.append(group)
        all_discovered.update(group)

    # Merge overlapping groups
    merged_groups = _merge_overlapping_groups(correlation_groups)

    notes.append(f"Found {len(merged_groups)} correlation group(s)")
    notes.append(f"Total correlated spans: {len(all_discovered)}")

    # Return spans in original order, filtered to discovered
    stitched_spans = [s for s in span_list if s.span_id in all_discovered]

    return StitchResult(
        spans=stitched_spans,
        notes=notes,
        correlation_groups=merged_groups,
    )


def _merge_overlapping_groups(groups: list[set[str]]) -> list[set[str]]:
    """Merge groups that share any common span IDs."""
    if not groups:
        return []

    # Union-find approach
    merged: list[set[str]] = []
    for group in groups:
        # Find all existing merged groups that overlap with this one
        overlapping_indices: list[int] = []
        for i, mg in enumerate(merged):
            if mg & group:  # If intersection is non-empty
                overlapping_indices.append(i)

        if not overlapping_indices:
            merged.append(group.copy())
        else:
            # Merge all overlapping groups plus the new one
            new_merged = group.copy()
            for i in overlapping_indices:
                new_merged.update(merged[i])

            # Remove old overlapping groups (in reverse order to preserve indices)
            for i in reversed(overlapping_indices):
                del merged[i]

            merged.append(new_merged)

    return merged


# Backward compatibility alias
def stitch_spans_multi_key(spans: Iterable[Span]) -> StitchResult:
    """Alias for stitch_spans_by_id for backward compatibility."""
    return stitch_spans_by_id(spans)
