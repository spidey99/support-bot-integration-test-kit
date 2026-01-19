# ITK Setup & Test Prompt

You are setting up the Integration Test Kit (ITK) to test a Bedrock Agent deployed in AWS. Follow these steps exactly in order. Run each command and wait for it to complete before moving to the next step.

## Phase 1: Install ITK

1. Clone or copy the ITK folder into your project:
   ```
   git clone https://github.com/spidey99/support-bot-integration-test-kit.git itk-source
   ```

2. Copy the drop-in folder to your project root:
   ```
   Copy-Item -Recurse itk-source/dropin/itk ./itk
   ```

3. Create a virtual environment and install ITK:
   ```
   cd itk
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e ".[dev]"
   ```

4. Run bootstrap to configure:
   ```
   itk bootstrap
   ```

5. If bootstrap reports missing credentials, paste your AWS SSO credentials into the `.env` file. Get them from your AWS SSO portal.

## Phase 2: View Historical Executions (Reports from Logs)

6. Discover AWS resources and apply to config:
   ```
   itk discover --apply
   ```

7. View the last hour of executions from CloudWatch logs:
   ```
   itk view --since 1h --out artifacts/history
   ```

8. Open `artifacts/history/index.html` in your browser to see all recent executions.

## Phase 3: Create Tests from Logs

9. Derive test cases from CloudWatch logs:
   ```
   itk derive --entrypoint bedrock_invoke_agent --since 24h --out cases/derived
   ```

10. List the generated cases:
    ```
    Get-ChildItem cases/derived/*.yaml
    ```

## Phase 4: Run Tests Against Live Infrastructure

11. Run one of the derived cases against live AWS:
    ```
    itk run --case cases/derived/<pick-one>.yaml --out artifacts/live-run
    ```
    (Replace `<pick-one>` with an actual filename from step 10)

12. Open `artifacts/live-run/index.html` to see the sequence diagram and test results.

## Phase 5: Run Soak Tests

13. Run the full test suite against all derived cases:
    ```
    itk suite --cases-dir cases/derived --out artifacts/soak-run
    ```

14. Open `artifacts/soak-run/index.html` to see the suite report with all test results.

## Phase 6: Verify Results

15. Check for any test failures in the suite report. Look for:
    - ✅ Passed tests (green)
    - ⚠️ Warnings (yellow) 
    - ❌ Failed tests (red)

16. For any failed test, click "View" to see the sequence diagram and identify which component failed.

## Success Criteria

You have succeeded when:
- [ ] `artifacts/history/index.html` shows past executions
- [ ] `cases/derived/` contains at least one `.yaml` file
- [ ] `artifacts/live-run/index.html` shows a sequence diagram
- [ ] `artifacts/soak-run/index.html` shows a suite report
