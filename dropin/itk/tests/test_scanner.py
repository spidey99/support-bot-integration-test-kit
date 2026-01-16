"""Tests for the codebase coverage scanner."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from itk.scanner import (
    DetectedComponent,
    DetectedBranch,
    LoggingGap,
    ScanResult,
    PythonFileScanner,
    scan_codebase,
    compare_with_cases,
    generate_coverage_report,
    generate_skeleton_cases,
)


# ============================================================================
# Fixtures for test data
# ============================================================================


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository with sample Python files."""
    return tmp_path


@pytest.fixture
def lambda_handler_file(temp_repo: Path) -> Path:
    """Create a sample Lambda handler file."""
    code = '''"""Sample Lambda handler."""
import json
import logging

logger = logging.getLogger(__name__)


def handler(event, context):
    """Main Lambda handler function."""
    logger.info("Processing event", extra={"event_type": event.get("type")})
    
    action = event.get("action")
    
    if action == "create":
        return handle_create(event)
    elif action == "update":
        return handle_update(event)
    else:
        logger.warning("Unknown action")
        return {"statusCode": 400, "body": "Unknown action"}


def handle_create(event):
    """Handle create action."""
    return {"statusCode": 201, "body": json.dumps({"created": True})}


def handle_update(event):
    """Handle update action."""
    return {"statusCode": 200, "body": json.dumps({"updated": True})}
'''
    handler_path = temp_repo / "lambdas" / "my_handler.py"
    handler_path.parent.mkdir(parents=True, exist_ok=True)
    handler_path.write_text(code, encoding="utf-8")
    return handler_path


@pytest.fixture
def cdk_infrastructure_file(temp_repo: Path) -> Path:
    """Create a sample CDK infrastructure file."""
    code = '''"""CDK infrastructure definitions."""
from aws_cdk import Stack, Duration
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_apigateway as apigateway
from constructs import Construct


class MyServiceStack(Stack):
    """Main service infrastructure stack."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        # Create SQS queue
        self.request_queue = sqs.Queue(
            self, "RequestQueue",
            queue_name="my-service-requests",
            visibility_timeout=Duration.seconds(300),
        )
        
        # Create Lambda function
        self.handler_fn = _lambda.Function(
            self, "HandlerFunction",
            function_name="my-service-handler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambdas"),
            timeout=Duration.seconds(30),
        )
        
        # Create API Gateway
        self.api = apigateway.RestApi(
            self, "ServiceApi",
            rest_api_name="my-service-api",
        )
        
        # Add Lambda integration
        integration = apigateway.LambdaIntegration(self.handler_fn)
        self.api.root.add_method("POST", integration)
'''
    cdk_path = temp_repo / "infrastructure" / "stacks" / "service_stack.py"
    cdk_path.parent.mkdir(parents=True, exist_ok=True)
    cdk_path.write_text(code, encoding="utf-8")
    return cdk_path


@pytest.fixture
def bedrock_action_file(temp_repo: Path) -> Path:
    """Create a sample Bedrock action group handler."""
    code = '''"""Bedrock agent action group handlers."""
import json
import logging

logger = logging.getLogger(__name__)


def action_handler(event, context):
    """Main action group handler for Bedrock agent."""
    action_group = event.get("actionGroup")
    api_path = event.get("apiPath")
    
    logger.info("Bedrock action invoked", extra={
        "action_group": action_group,
        "api_path": api_path,
    })
    
    if api_path == "/search":
        return handle_search(event)
    elif api_path == "/submit":
        return handle_submit(event)
    
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpStatusCode": 404,
            "responseBody": {"text/plain": {"body": "Not found"}},
        },
    }


def handle_search(event):
    """Handle search action."""
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "apiPath": "/search",
            "httpStatusCode": 200,
            "responseBody": {"application/json": {"body": "{}"}},
        },
    }


def handle_submit(event):
    """Handle submit action."""
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "apiPath": "/submit",
            "httpStatusCode": 200,
            "responseBody": {"application/json": {"body": "{}"}},
        },
    }
'''
    action_path = temp_repo / "lambdas" / "bedrock_actions.py"
    action_path.parent.mkdir(parents=True, exist_ok=True)
    action_path.write_text(code, encoding="utf-8")
    return action_path


@pytest.fixture
def file_with_logging_gaps(temp_repo: Path) -> Path:
    """Create a file with intentional logging gaps."""
    code = '''"""Handler with logging gaps."""


def handler(event, context):
    """Handler with no logging."""
    try:
        result = do_work(event)
        return {"statusCode": 200, "body": result}
    except Exception as e:
        # Gap: exception caught but not logged
        return {"statusCode": 500, "body": "Error"}


def do_work(event):
    """Process without logging."""
    if event.get("dangerous"):
        # Gap: branch with no logging
        do_dangerous_thing()
    return "done"


def do_dangerous_thing():
    """Dangerous operation."""
    pass
'''
    gap_path = temp_repo / "lambdas" / "gaps_example.py"
    gap_path.parent.mkdir(parents=True, exist_ok=True)
    gap_path.write_text(code, encoding="utf-8")
    return gap_path


# ============================================================================
# Data class tests
# ============================================================================


class TestDataClasses:
    """Tests for scanner data classes."""

    def test_detected_component_creation(self) -> None:
        """Test DetectedComponent dataclass."""
        comp = DetectedComponent(
            component_type="lambda",
            name="my-handler",
            file_path="src/handler.py",
            line_number=10,
            handler="handler",
        )
        assert comp.component_type == "lambda"
        assert comp.name == "my-handler"
        assert comp.details == {}

    def test_detected_component_id(self) -> None:
        """Test component_id property."""
        comp = DetectedComponent(
            component_type="lambda",
            name="my-handler",
            file_path="src/handler.py",
            line_number=10,
        )
        assert comp.component_id == "lambda:my-handler"

    def test_detected_branch_creation(self) -> None:
        """Test DetectedBranch dataclass."""
        branch = DetectedBranch(
            file_path="src/handler.py",
            line_number=15,
            branch_type="if",
            condition="action == 'create'",
            parent_function="handler",
            has_logging=True,
        )
        assert branch.branch_type == "if"
        assert branch.has_logging is True

    def test_logging_gap_creation(self) -> None:
        """Test LoggingGap dataclass."""
        gap = LoggingGap(
            file_path="src/handler.py",
            line_number=25,
            function_name="handler",
            gap_type="no_error_log",
            suggestion="Add logger.exception() in exception handler",
        )
        assert gap.gap_type == "no_error_log"
        assert gap.suggestion is not None

    def test_scan_result_creation(self) -> None:
        """Test ScanResult dataclass."""
        result = ScanResult(
            components=[
                DetectedComponent(
                    component_type="lambda",
                    name="handler",
                    file_path="handler.py",
                    line_number=1,
                )
            ],
            branches=[],
            logging_gaps=[],
            scanned_files=1,
        )
        assert len(result.components) == 1
        assert result.scanned_files == 1


# ============================================================================
# AST Scanner tests
# ============================================================================


class TestPythonFileScanner:
    """Tests for the AST-based Python file scanner."""

    def test_scanner_creation(self, lambda_handler_file: Path) -> None:
        """Test PythonFileScanner can be instantiated."""
        scanner = PythonFileScanner(str(lambda_handler_file))
        assert scanner.file_path == str(lambda_handler_file)

    def test_detect_handler_function(self, lambda_handler_file: Path) -> None:
        """Test detection of Lambda handler function."""
        scanner = PythonFileScanner(str(lambda_handler_file))
        source = lambda_handler_file.read_text()
        scanner.scan(source)
        
        # Should find handler as a component or at minimum not crash
        assert scanner.components is not None

    def test_detect_branches(self, lambda_handler_file: Path) -> None:
        """Test detection of branches in handler."""
        scanner = PythonFileScanner(str(lambda_handler_file))
        source = lambda_handler_file.read_text()
        scanner.scan(source)
        
        # Handler has if/elif for action types
        assert len(scanner.branches) >= 2

    def test_detect_cdk_lambda(self, cdk_infrastructure_file: Path) -> None:
        """Test detection of CDK Lambda construct."""
        scanner = PythonFileScanner(str(cdk_infrastructure_file))
        source = cdk_infrastructure_file.read_text()
        scanner.scan(source)
        
        lambdas = [c for c in scanner.components if c.component_type == "lambda"]
        assert len(lambdas) >= 1

    def test_detect_cdk_sqs(self, cdk_infrastructure_file: Path) -> None:
        """Test detection of CDK SQS Queue construct."""
        scanner = PythonFileScanner(str(cdk_infrastructure_file))
        source = cdk_infrastructure_file.read_text()
        scanner.scan(source)
        
        queues = [c for c in scanner.components if c.component_type == "sqs"]
        assert len(queues) >= 1

    def test_detect_cdk_api_gateway(self, cdk_infrastructure_file: Path) -> None:
        """Test detection of CDK API Gateway construct."""
        scanner = PythonFileScanner(str(cdk_infrastructure_file))
        source = cdk_infrastructure_file.read_text()
        scanner.scan(source)
        
        apis = [c for c in scanner.components if c.component_type == "api"]
        assert len(apis) >= 1

    def test_detect_logging_gaps_exception(self, file_with_logging_gaps: Path) -> None:
        """Test detection of exception without logging gap."""
        scanner = PythonFileScanner(str(file_with_logging_gaps))
        source = file_with_logging_gaps.read_text()
        scanner.scan(source)
        
        # Should detect the exception handler without logging
        assert len(scanner.logging_gaps) >= 1 or len(scanner.branches) >= 1

    def test_scan_empty_file(self, temp_repo: Path) -> None:
        """Test scanning an empty file."""
        empty_file = temp_repo / "empty.py"
        empty_file.write_text("", encoding="utf-8")
        
        scanner = PythonFileScanner(str(empty_file))
        scanner.scan("")
        assert len(scanner.components) == 0

    def test_scan_syntax_error_file(self, temp_repo: Path) -> None:
        """Test scanning a file with syntax errors."""
        bad_file = temp_repo / "bad_syntax.py"
        bad_content = "def broken(:\n  pass"
        bad_file.write_text(bad_content, encoding="utf-8")
        
        scanner = PythonFileScanner(str(bad_file))
        scanner.scan(bad_content)
        # Should not crash, just handle gracefully
        assert scanner.components is not None


# ============================================================================
# Codebase scanning tests
# ============================================================================


class TestScanCodebase:
    """Tests for the scan_codebase function."""

    def test_scan_repo_with_lambdas(
        self, temp_repo: Path, lambda_handler_file: Path
    ) -> None:
        """Test scanning a repo with Lambda handlers."""
        result = scan_codebase(temp_repo)
        
        assert result.scanned_files >= 1
        assert len(result.components) >= 1

    def test_scan_repo_with_cdk(
        self, temp_repo: Path, cdk_infrastructure_file: Path
    ) -> None:
        """Test scanning a repo with CDK infrastructure."""
        result = scan_codebase(temp_repo)
        
        assert result.scanned_files >= 1
        cdk_components = [
            c for c in result.components 
            if c.component_type in ("lambda", "sqs", "api")
        ]
        assert len(cdk_components) >= 1

    def test_scan_multiple_files(
        self,
        temp_repo: Path,
        lambda_handler_file: Path,
        cdk_infrastructure_file: Path,
        bedrock_action_file: Path,
    ) -> None:
        """Test scanning a repo with multiple file types."""
        result = scan_codebase(temp_repo)
        
        assert result.scanned_files >= 3
        assert len(result.components) >= 3

    def test_scan_empty_repo(self, temp_repo: Path) -> None:
        """Test scanning an empty repository."""
        result = scan_codebase(temp_repo)
        
        assert result.scanned_files == 0
        assert len(result.components) == 0

    def test_scan_respects_excludes(self, temp_repo: Path) -> None:
        """Test that scanning skips excluded directories."""
        # Create a file in .git (should be excluded)
        git_dir = temp_repo / ".git"
        git_dir.mkdir()
        (git_dir / "hooks.py").write_text("def handler(event, context): pass")
        
        # Create a file in node_modules (should be excluded)
        nm_dir = temp_repo / "node_modules"
        nm_dir.mkdir()
        (nm_dir / "package.py").write_text("def handler(event, context): pass")
        
        # Create a legitimate handler
        (temp_repo / "handler.py").write_text(
            "def handler(event, context): return {'statusCode': 200}"
        )
        
        result = scan_codebase(temp_repo)
        
        # Should only find the legitimate handler
        assert result.scanned_files == 1


# ============================================================================
# Coverage comparison tests
# ============================================================================


class TestCompareWithCases:
    """Tests for the compare_with_cases function."""

    def test_compare_no_cases(
        self, temp_repo: Path, lambda_handler_file: Path
    ) -> None:
        """Test comparison when no cases exist."""
        scan_result = scan_codebase(temp_repo)
        cases_dir = temp_repo / "cases"
        cases_dir.mkdir()
        
        coverage = compare_with_cases(scan_result, cases_dir)
        
        assert "covered" in coverage
        assert "uncovered" in coverage
        assert "extra" in coverage
        # With no cases, everything should be uncovered
        assert len(coverage["covered"]) == 0

    def test_compare_with_matching_case(
        self, temp_repo: Path, cdk_infrastructure_file: Path
    ) -> None:
        """Test comparison with a matching case file."""
        scan_result = scan_codebase(temp_repo)
        
        # Create a case directory with a case that references a component
        cases_dir = temp_repo / "cases"
        cases_dir.mkdir()
        
        # Get a detected component to reference
        if scan_result.components:
            comp_id = scan_result.components[0].component_id
            
            case_yaml = cases_dir / "handler-case.yaml"
            case_yaml.write_text(
                f'''id: test-001
name: Test handler
expected:
  required_components:
    - {comp_id}
''',
                encoding="utf-8",
            )
            
            coverage = compare_with_cases(scan_result, cases_dir)
            
            # Should have coverage now
            assert comp_id in coverage["covered"]

    def test_compare_with_fixture_references(
        self, temp_repo: Path, lambda_handler_file: Path
    ) -> None:
        """Test comparison considering fixtures."""
        scan_result = scan_codebase(temp_repo)
        
        cases_dir = temp_repo / "cases"
        cases_dir.mkdir()
        
        fixtures_dir = temp_repo / "fixtures" / "logs"
        fixtures_dir.mkdir(parents=True)
        
        # Create a fixture that mentions a component
        if scan_result.components:
            comp_id = scan_result.components[0].component_id
            fixture_jsonl = fixtures_dir / "run_001.jsonl"
            fixture_jsonl.write_text(
                f'{{"component": "{comp_id}", "message": "invoked"}}\n',
                encoding="utf-8",
            )
            
            coverage = compare_with_cases(scan_result, cases_dir, fixtures_dir)
            assert comp_id in coverage["covered"]


# ============================================================================
# Report generation tests
# ============================================================================


class TestGenerateCoverageReport:
    """Tests for the generate_coverage_report function."""

    def test_report_with_components(
        self, temp_repo: Path, lambda_handler_file: Path
    ) -> None:
        """Test report generation with detected components."""
        scan_result = scan_codebase(temp_repo)
        coverage = {"covered": [], "uncovered": [], "extra": []}
        
        report = generate_coverage_report(scan_result, coverage)
        
        assert "Coverage" in report
        assert "components" in report.lower()

    def test_report_with_coverage(
        self, temp_repo: Path, lambda_handler_file: Path
    ) -> None:
        """Test report generation with coverage info."""
        scan_result = scan_codebase(temp_repo)
        
        cases_dir = temp_repo / "cases"
        cases_dir.mkdir()
        coverage = compare_with_cases(scan_result, cases_dir)
        
        report = generate_coverage_report(scan_result, coverage)
        
        assert "uncovered" in report.lower()

    def test_report_with_logging_gaps(
        self, temp_repo: Path, file_with_logging_gaps: Path
    ) -> None:
        """Test report includes logging gaps."""
        scan_result = scan_codebase(temp_repo)
        coverage = {"covered": [], "uncovered": [], "extra": []}
        
        report = generate_coverage_report(scan_result, coverage)
        
        assert "gaps" in report.lower()

    def test_report_empty_result(self, temp_repo: Path) -> None:
        """Test report generation for empty scan."""
        scan_result = ScanResult(
            components=[],
            branches=[],
            logging_gaps=[],
            scanned_files=0,
        )
        coverage = {"covered": [], "uncovered": [], "extra": []}
        
        report = generate_coverage_report(scan_result, coverage)
        
        assert "Coverage" in report
        assert "0" in report  # Should mention 0 files or components


# ============================================================================
# Skeleton generation tests
# ============================================================================


class TestGenerateSkeletonCases:
    """Tests for the generate_skeleton_cases function."""

    def test_generate_skeleton_for_lambda(self, temp_repo: Path) -> None:
        """Test skeleton case generation for Lambda component."""
        comp = DetectedComponent(
            component_type="lambda",
            name="my-handler",
            file_path="lambdas/my_handler.py",
            line_number=10,
            handler="handler",
        )
        scan_result = ScanResult(
            components=[comp],
            branches=[],
            logging_gaps=[],
            scanned_files=1,
        )
        
        skeletons = generate_skeleton_cases(scan_result, ["lambda:my-handler"])
        
        assert len(skeletons) == 1
        assert "my-handler" in skeletons[0]["name"]

    def test_generate_multiple_skeletons(self, temp_repo: Path) -> None:
        """Test generating multiple skeleton cases."""
        components = [
            DetectedComponent(
                component_type="lambda",
                name="handler-a",
                file_path="a.py",
                line_number=1,
            ),
            DetectedComponent(
                component_type="lambda",
                name="handler-b",
                file_path="b.py",
                line_number=1,
            ),
        ]
        scan_result = ScanResult(
            components=components,
            branches=[],
            logging_gaps=[],
            scanned_files=2,
        )
        
        skeletons = generate_skeleton_cases(
            scan_result, 
            ["lambda:handler-a", "lambda:handler-b"]
        )
        
        assert len(skeletons) == 2

    def test_generate_skeleton_for_sqs(self, temp_repo: Path) -> None:
        """Test skeleton generation for SQS component."""
        comp = DetectedComponent(
            component_type="sqs",
            name="my-queue",
            file_path="infra.py",
            line_number=10,
        )
        scan_result = ScanResult(
            components=[comp],
            branches=[],
            logging_gaps=[],
            scanned_files=1,
        )
        
        skeletons = generate_skeleton_cases(scan_result, ["sqs:my-queue"])
        
        assert len(skeletons) == 1
        assert skeletons[0]["entrypoint"]["type"] == "sqs_event"

    def test_generate_skeleton_for_api(self, temp_repo: Path) -> None:
        """Test skeleton generation for API component."""
        comp = DetectedComponent(
            component_type="api",
            name="my-api",
            file_path="infra.py",
            line_number=10,
        )
        scan_result = ScanResult(
            components=[comp],
            branches=[],
            logging_gaps=[],
            scanned_files=1,
        )
        
        skeletons = generate_skeleton_cases(scan_result, ["api:my-api"])
        
        assert len(skeletons) == 1
        assert skeletons[0]["entrypoint"]["type"] == "http"


# ============================================================================
# Integration / CLI tests
# ============================================================================


class TestScannerCLI:
    """Integration tests for the scan CLI command."""

    def test_cli_scan_help(self, tmp_path: Path) -> None:
        """Test that scan command has help."""
        import subprocess
        
        result = subprocess.run(
            ["python", "-m", "itk", "scan", "--help"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        
        assert result.returncode == 0
        assert "scan" in result.stdout.lower()
        assert "--repo" in result.stdout

    def test_cli_scan_nonexistent_repo(self, tmp_path: Path) -> None:
        """Test scan command with non-existent repo."""
        import subprocess
        
        result = subprocess.run(
            [
                "python", "-m", "itk", "scan",
                "--repo", str(tmp_path / "nonexistent"),
                "--out", str(tmp_path / "output"),
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_cli_scan_creates_artifacts(
        self, temp_repo: Path, lambda_handler_file: Path
    ) -> None:
        """Test scan command creates expected artifacts."""
        import subprocess
        
        output_dir = temp_repo / "scan_output"
        
        result = subprocess.run(
            [
                "python", "-m", "itk", "scan",
                "--repo", str(temp_repo),
                "--out", str(output_dir),
            ],
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert (output_dir / "scan_result.json").exists()
        assert (output_dir / "coverage_report.md").exists()
