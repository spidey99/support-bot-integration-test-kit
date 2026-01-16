"""Codebase scanner for detecting components and coverage gaps.

Performs static analysis on Python/CDK codebases to identify:
- Lambda handlers and their entry points
- Bedrock agent action groups
- SQS consumers/producers
- API Gateway routes
- Components without test coverage
- Code paths without logging
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class DetectedComponent:
    """A component detected in the codebase."""
    
    component_type: str  # lambda, agent, sqs, api, model
    name: str  # Identifier/name
    file_path: str  # Source file
    line_number: int  # Line where defined
    handler: str | None = None  # Handler function if applicable
    details: dict[str, Any] = field(default_factory=dict)
    
    @property
    def component_id(self) -> str:
        """Return ITK-style component ID like 'lambda:my-handler'."""
        return f"{self.component_type}:{self.name}"


@dataclass
class DetectedBranch:
    """A code branch (if/else, try/except) that may need testing."""
    
    file_path: str
    line_number: int
    branch_type: str  # if, try, match
    condition: str  # The condition or exception type
    parent_function: str | None = None
    has_logging: bool = False


@dataclass
class LoggingGap:
    """A function or handler missing boundary logging."""
    
    file_path: str
    line_number: int
    function_name: str
    gap_type: str  # no_entry_log, no_exit_log, no_error_log
    suggestion: str


@dataclass
class ScanResult:
    """Complete scan result for a codebase."""
    
    components: list[DetectedComponent] = field(default_factory=list)
    branches: list[DetectedBranch] = field(default_factory=list)
    logging_gaps: list[LoggingGap] = field(default_factory=list)
    scanned_files: int = 0
    errors: list[str] = field(default_factory=list)


# Patterns for detecting AWS CDK constructs
CDK_LAMBDA_PATTERNS = [
    r"aws_lambda\.Function",
    r"aws_lambda_python\.PythonFunction", 
    r"_lambda\.Function",  # Common alias: import aws_lambda as _lambda
    r"lambda_\.Function",  # Common alias: import aws_lambda as lambda_
    r"PythonFunction",
    r"NodejsFunction",
]

CDK_SQS_PATTERNS = [
    r"aws_sqs\.Queue",
    r"sqs\.Queue",
]

CDK_API_PATTERNS = [
    r"aws_apigateway\.RestApi",
    r"aws_apigatewayv2\.HttpApi",
    r"apigateway\.RestApi",
]

# Patterns for Lambda handler functions
HANDLER_PATTERNS = [
    r"def\s+handler\s*\(",
    r"def\s+lambda_handler\s*\(",
    r"def\s+main\s*\(event",
    r"@app\.lambda_function",
]

# Patterns indicating logging
LOGGING_PATTERNS = [
    r"logger\.",
    r"logging\.",
    r"print\s*\(",
    r"log\.",
    r"\.info\(",
    r"\.debug\(",
    r"\.error\(",
    r"\.warning\(",
]


class PythonFileScanner(ast.NodeVisitor):
    """AST visitor that extracts components and branches from Python files."""
    
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.components: list[DetectedComponent] = []
        self.branches: list[DetectedBranch] = []
        self.logging_gaps: list[LoggingGap] = []
        self.current_function: str | None = None
        self.current_class: str | None = None
        self._source_lines: list[str] = []
    
    def scan(self, source: str) -> None:
        """Parse and scan the source code."""
        self._source_lines = source.splitlines()
        try:
            tree = ast.parse(source)
            self.visit(tree)
            self._check_logging_patterns(source)
        except SyntaxError:
            pass  # Skip files with syntax errors
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions to find handlers."""
        old_function = self.current_function
        self.current_function = node.name
        
        # Check if this looks like a Lambda handler
        if self._is_lambda_handler(node):
            self.components.append(DetectedComponent(
                component_type="lambda",
                name=self._make_component_name(node.name),
                file_path=self.file_path,
                line_number=node.lineno,
                handler=f"{self._get_module_name()}.{node.name}",
                details={"args": [arg.arg for arg in node.args.args]},
            ))
            
            # Check for logging in handler
            self._check_handler_logging(node)
        
        # Check if this is a Bedrock action group function
        if self._is_action_group_handler(node):
            self.components.append(DetectedComponent(
                component_type="agent",
                name=self._make_component_name(node.name),
                file_path=self.file_path,
                line_number=node.lineno,
                handler=f"{self._get_module_name()}.{node.name}",
            ))
        
        self.generic_visit(node)
        self.current_function = old_function
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions."""
        # Treat same as regular functions
        self.visit_FunctionDef(node)  # type: ignore
    
    def visit_If(self, node: ast.If) -> None:
        """Visit if statements to track branches."""
        condition = self._get_source_segment(node.test)
        self.branches.append(DetectedBranch(
            file_path=self.file_path,
            line_number=node.lineno,
            branch_type="if",
            condition=condition[:100],  # Truncate long conditions
            parent_function=self.current_function,
        ))
        self.generic_visit(node)
    
    def visit_Try(self, node: ast.Try) -> None:
        """Visit try/except blocks."""
        for handler in node.handlers:
            exc_type = "Exception"
            if handler.type:
                exc_type = self._get_source_segment(handler.type)
            
            self.branches.append(DetectedBranch(
                file_path=self.file_path,
                line_number=handler.lineno,
                branch_type="except",
                condition=exc_type,
                parent_function=self.current_function,
            ))
        self.generic_visit(node)
    
    def visit_Match(self, node: ast.Match) -> None:
        """Visit match statements (Python 3.10+)."""
        for case in node.cases:
            pattern = self._get_source_segment(case.pattern)
            self.branches.append(DetectedBranch(
                file_path=self.file_path,
                line_number=case.pattern.lineno,
                branch_type="match",
                condition=pattern[:100],
                parent_function=self.current_function,
            ))
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls to detect CDK constructs."""
        call_name = self._get_call_name(node)
        
        # Check for CDK Lambda
        if any(re.search(p, call_name) for p in CDK_LAMBDA_PATTERNS):
            name = self._extract_construct_name(node)
            handler = self._extract_kwarg(node, "handler")
            self.components.append(DetectedComponent(
                component_type="lambda",
                name=name or f"lambda_{node.lineno}",
                file_path=self.file_path,
                line_number=node.lineno,
                handler=handler,
                details={"cdk_construct": call_name},
            ))
        
        # Check for CDK SQS
        if any(re.search(p, call_name) for p in CDK_SQS_PATTERNS):
            name = self._extract_construct_name(node)
            self.components.append(DetectedComponent(
                component_type="sqs",
                name=name or f"queue_{node.lineno}",
                file_path=self.file_path,
                line_number=node.lineno,
                details={"cdk_construct": call_name},
            ))
        
        # Check for CDK API Gateway
        if any(re.search(p, call_name) for p in CDK_API_PATTERNS):
            name = self._extract_construct_name(node)
            self.components.append(DetectedComponent(
                component_type="api",
                name=name or f"api_{node.lineno}",
                file_path=self.file_path,
                line_number=node.lineno,
                details={"cdk_construct": call_name},
            ))
        
        self.generic_visit(node)
    
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions."""
        old_class = self.current_class
        self.current_class = node.name
        
        # Check if this is a CDK Stack
        base_names = [self._get_source_segment(b) for b in node.bases]
        if any("Stack" in b for b in base_names):
            # Mark as infrastructure definition
            pass
        
        self.generic_visit(node)
        self.current_class = old_class
    
    def _is_lambda_handler(self, node: ast.FunctionDef) -> bool:
        """Check if function looks like a Lambda handler."""
        # Check name patterns
        if node.name in ("handler", "lambda_handler", "main"):
            return True
        
        # Check for (event, context) signature
        args = [arg.arg for arg in node.args.args]
        if "event" in args and "context" in args:
            return True
        
        # Check for decorators
        for decorator in node.decorator_list:
            dec_name = self._get_source_segment(decorator)
            if "lambda" in dec_name.lower():
                return True
        
        return False
    
    def _is_action_group_handler(self, node: ast.FunctionDef) -> bool:
        """Check if function looks like a Bedrock action group handler."""
        # Check for action group patterns
        if "action" in node.name.lower() and "group" in node.name.lower():
            return True
        
        # Check for bedrock-related decorators
        for decorator in node.decorator_list:
            dec_name = self._get_source_segment(decorator)
            if "bedrock" in dec_name.lower() or "action" in dec_name.lower():
                return True
        
        return False
    
    def _check_handler_logging(self, node: ast.FunctionDef) -> None:
        """Check if a handler has proper logging."""
        source = ast.get_source_segment(
            "\n".join(self._source_lines), node
        ) or ""
        
        has_entry_log = bool(re.search(r'(log|print).*("|\').*start|entry|received', source, re.I))
        has_exit_log = bool(re.search(r'(log|print).*("|\').*end|exit|complete|return', source, re.I))
        has_error_log = bool(re.search(r'(log|print).*error|exception|fail', source, re.I))
        
        if not has_entry_log:
            self.logging_gaps.append(LoggingGap(
                file_path=self.file_path,
                line_number=node.lineno,
                function_name=node.name,
                gap_type="no_entry_log",
                suggestion=f"Add entry logging at start of {node.name}",
            ))
        
        if not has_exit_log:
            self.logging_gaps.append(LoggingGap(
                file_path=self.file_path,
                line_number=node.lineno,
                function_name=node.name,
                gap_type="no_exit_log",
                suggestion=f"Add exit logging before returns in {node.name}",
            ))
        
        # Check for try/except without error logging
        has_try = "try:" in source
        if has_try and not has_error_log:
            self.logging_gaps.append(LoggingGap(
                file_path=self.file_path,
                line_number=node.lineno,
                function_name=node.name,
                gap_type="no_error_log",
                suggestion=f"Add error logging in except blocks of {node.name}",
            ))
    
    def _check_logging_patterns(self, source: str) -> None:
        """Check for general logging patterns in the file."""
        pass  # Could add file-level checks here
    
    def _get_source_segment(self, node: ast.AST) -> str:
        """Get source code for an AST node."""
        try:
            return ast.get_source_segment("\n".join(self._source_lines), node) or ""
        except Exception:
            return ""
    
    def _get_call_name(self, node: ast.Call) -> str:
        """Get the full name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""
    
    def _extract_construct_name(self, node: ast.Call) -> str | None:
        """Extract the construct ID/name from a CDK call."""
        # Usually second positional arg or 'id' kwarg
        if len(node.args) >= 2:
            arg = node.args[1]
            if isinstance(arg, ast.Constant):
                return str(arg.value)
        
        return self._extract_kwarg(node, "id")
    
    def _extract_kwarg(self, node: ast.Call, key: str) -> str | None:
        """Extract a keyword argument value."""
        for kw in node.keywords:
            if kw.arg == key and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
        return None
    
    def _get_module_name(self) -> str:
        """Get module name from file path."""
        return Path(self.file_path).stem
    
    def _make_component_name(self, name: str) -> str:
        """Make a clean component name."""
        # Convert snake_case to kebab-case
        return name.replace("_", "-").lower()


def scan_directory(
    root: Path,
    exclude_patterns: list[str] | None = None,
) -> Iterator[tuple[Path, str]]:
    """Yield Python files from directory, excluding patterns."""
    exclude_patterns = exclude_patterns or [
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".git",
        "cdk.out",
        ".pytest_cache",
        "dist",
        "build",
        "*.egg-info",
    ]
    
    for py_file in root.rglob("*.py"):
        # Check exclusions
        path_str = str(py_file)
        if any(excl in path_str for excl in exclude_patterns):
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8")
            yield py_file, content
        except Exception:
            continue


def scan_codebase(
    repo_path: str | Path,
    exclude_patterns: list[str] | None = None,
) -> ScanResult:
    """Scan a codebase for components and coverage gaps.
    
    Args:
        repo_path: Path to the repository root.
        exclude_patterns: Glob patterns to exclude.
        
    Returns:
        ScanResult with detected components, branches, and gaps.
    """
    repo_path = Path(repo_path)
    result = ScanResult()
    
    if not repo_path.exists():
        result.errors.append(f"Repository path does not exist: {repo_path}")
        return result
    
    for file_path, content in scan_directory(repo_path, exclude_patterns):
        result.scanned_files += 1
        
        scanner = PythonFileScanner(str(file_path.relative_to(repo_path)))
        try:
            scanner.scan(content)
            result.components.extend(scanner.components)
            result.branches.extend(scanner.branches)
            result.logging_gaps.extend(scanner.logging_gaps)
        except Exception as e:
            result.errors.append(f"Error scanning {file_path}: {e}")
    
    return result


def compare_with_cases(
    scan_result: ScanResult,
    cases_dir: str | Path,
    fixtures_dir: str | Path | None = None,
) -> dict[str, list[str]]:
    """Compare scan results with existing test cases.
    
    Returns dict with:
    - covered: Components that have test cases
    - uncovered: Components without test cases
    - extra: Components in tests but not in code (stale?)
    """
    cases_dir = Path(cases_dir)
    
    # Collect component IDs from cases
    covered_components: set[str] = set()
    
    if cases_dir.exists():
        import yaml
        for case_file in cases_dir.glob("*.yaml"):
            try:
                case = yaml.safe_load(case_file.read_text())
                # Extract components mentioned in case
                if case and "expected" in case:
                    expected = case["expected"]
                    if "required_components" in expected:
                        covered_components.update(expected["required_components"])
            except Exception:
                pass
    
    # Also check fixtures for component coverage
    if fixtures_dir:
        fixtures_dir = Path(fixtures_dir)
        if fixtures_dir.exists():
            import json
            for fixture_file in fixtures_dir.glob("**/*.jsonl"):
                try:
                    for line in fixture_file.read_text().splitlines():
                        if line.strip():
                            span = json.loads(line)
                            if "component" in span:
                                covered_components.add(span["component"])
                except Exception:
                    pass
    
    # Compare
    detected_ids = {c.component_id for c in scan_result.components}
    
    return {
        "covered": sorted(detected_ids & covered_components),
        "uncovered": sorted(detected_ids - covered_components),
        "extra": sorted(covered_components - detected_ids),
    }


def generate_coverage_report(
    scan_result: ScanResult,
    coverage: dict[str, list[str]],
) -> str:
    """Generate a markdown coverage gaps report."""
    lines = [
        "# Coverage Gaps Report",
        "",
        f"Scanned {scan_result.scanned_files} files",
        f"Found {len(scan_result.components)} components",
        f"Found {len(scan_result.branches)} branches",
        f"Found {len(scan_result.logging_gaps)} logging gaps",
        "",
    ]
    
    # Uncovered components
    if coverage["uncovered"]:
        lines.extend([
            "## Uncovered Components",
            "",
            "These components were found in code but have no test cases:",
            "",
        ])
        for comp_id in coverage["uncovered"]:
            comp = next(
                (c for c in scan_result.components if c.component_id == comp_id),
                None
            )
            if comp:
                lines.append(f"- **{comp_id}**")
                lines.append(f"  - File: `{comp.file_path}:{comp.line_number}`")
                if comp.handler:
                    lines.append(f"  - Handler: `{comp.handler}`")
        lines.append("")
    
    # Logging gaps
    if scan_result.logging_gaps:
        lines.extend([
            "## Logging Gaps",
            "",
            "These handlers may be missing proper boundary logging:",
            "",
        ])
        for gap in scan_result.logging_gaps:
            lines.append(f"- **{gap.function_name}** (`{gap.file_path}:{gap.line_number}`)")
            lines.append(f"  - Gap: {gap.gap_type}")
            lines.append(f"  - Suggestion: {gap.suggestion}")
        lines.append("")
    
    # Branch coverage hints
    error_branches = [b for b in scan_result.branches if b.branch_type == "except"]
    if error_branches:
        lines.extend([
            "## Error Handling Branches",
            "",
            "These exception handlers should have test cases:",
            "",
        ])
        for branch in error_branches[:20]:  # Limit output
            func = branch.parent_function or "(module level)"
            lines.append(f"- `{branch.file_path}:{branch.line_number}` in `{func}`")
            lines.append(f"  - Catches: `{branch.condition}`")
        if len(error_branches) > 20:
            lines.append(f"- ... and {len(error_branches) - 20} more")
        lines.append("")
    
    # Stale test cases
    if coverage["extra"]:
        lines.extend([
            "## Potentially Stale Test Cases",
            "",
            "These components are in test cases but weren't found in code:",
            "",
        ])
        for comp_id in coverage["extra"]:
            lines.append(f"- {comp_id}")
        lines.append("")
    
    # Summary
    total = len(coverage["covered"]) + len(coverage["uncovered"])
    covered_pct = (len(coverage["covered"]) / total * 100) if total > 0 else 0
    
    lines.extend([
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Components detected | {len(scan_result.components)} |",
        f"| Components covered | {len(coverage['covered'])} |",
        f"| Components uncovered | {len(coverage['uncovered'])} |",
        f"| Coverage | {covered_pct:.1f}% |",
        f"| Logging gaps | {len(scan_result.logging_gaps)} |",
        f"| Error handlers | {len(error_branches)} |",
        "",
    ])
    
    return "\n".join(lines)


def generate_skeleton_cases(
    scan_result: ScanResult,
    uncovered: list[str],
) -> list[dict[str, Any]]:
    """Generate skeleton case YAMLs for uncovered components."""
    skeletons = []
    
    for comp_id in uncovered:
        comp = next(
            (c for c in scan_result.components if c.component_id == comp_id),
            None
        )
        if not comp:
            continue
        
        case = {
            "id": f"auto-{comp.name}",
            "name": f"Test {comp.component_type} {comp.name}",
            "entrypoint": _guess_entrypoint(comp),
            "expected": {
                "invariants": [
                    {"name": "has_spans"},
                    {"name": "no_error_spans"},
                ],
                "required_components": [comp.component_id],
            },
            "notes": {
                "source": "auto-generated by itk scan",
                "file": comp.file_path,
                "line": comp.line_number,
                "missing_fields": ["payload details", "expected response"],
            },
        }
        skeletons.append(case)
    
    return skeletons


def _guess_entrypoint(comp: DetectedComponent) -> dict[str, Any]:
    """Guess the entrypoint configuration for a component."""
    if comp.component_type == "lambda":
        return {
            "type": "lambda_invoke",
            "target": {
                "function_name": comp.name,
            },
            "payload": {
                "_comment": "TODO: Add actual test payload",
            },
        }
    elif comp.component_type == "sqs":
        return {
            "type": "sqs_event",
            "target": {
                "queue_url": f"TODO: Queue URL for {comp.name}",
            },
            "payload": {
                "_comment": "TODO: Add actual message body",
            },
        }
    elif comp.component_type == "api":
        return {
            "type": "http",
            "target": {
                "url": f"TODO: API endpoint for {comp.name}",
                "method": "POST",
            },
            "payload": {
                "_comment": "TODO: Add request body",
            },
        }
    else:
        return {
            "type": "lambda_invoke",
            "target": {},
            "payload": {},
        }
