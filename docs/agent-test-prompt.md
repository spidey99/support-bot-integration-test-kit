# ITK Setup & Test Prompt

You are setting up the Integration Test Kit (ITK) to test a Bedrock Agent deployed in AWS. Follow these steps exactly in order. Run each command and wait for it to complete before moving to the next step.

**CRITICAL RULES:**
1. Always show the user command output and explain what happened
2. If any command fails, stop and help the user fix it before continuing
3. **NEVER proceed with placeholder values** - if `.env` has commented-out values (`#`), `FIXME`, or angle brackets (`<placeholder>`), STOP and get real credentials first
4. Real AWS resource IDs look like: `WYEP3TYH1A` (agent ID), `/aws/lambda/itk-haiku-invoker` (log group)
5. **NEVER duplicate key names in values** - WRONG: `ITK_LOG_GROUPS=ITK_LOG_GROUPS=/aws/...` RIGHT: `ITK_LOG_GROUPS=/aws/...`
6. Do NOT copy `.env.example` directly - it has placeholder values that will fail

## Phase 0: Get AWS Credentials

Before starting, ensure you have AWS credentials in your terminal.

**From AWS CloudShell (easiest):**
1. Open AWS Console → click CloudShell icon (terminal in top nav)
2. Run: `aws configure export-credentials --format env`
3. Copy the output and paste into your local PowerShell/terminal

**Or from AWS SSO Portal:**
1. Click "Command line or programmatic access"
2. Copy the environment variables block and paste into terminal

## Phase 1: Install ITK

1. Clone the ITK repository:
   ```
   git clone https://github.com/spidey99/support-bot-integration-test-kit.git itk-source
   ```

2. Copy the drop-in folder to your project:
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

4. Run bootstrap to discover resources and create config:
   ```
   itk bootstrap
   ```

5. **STOP if bootstrap shows ⚠️ for credentials or 0 resources discovered.**

   You MUST have valid AWS credentials before continuing. Do NOT proceed with placeholder values.
   
   To fix credential issues:
   - Get fresh credentials from CloudShell: `aws configure export-credentials --format env`
   - Paste the `export AWS_...` lines into your terminal
   - Run `itk bootstrap` again
   
   After successful bootstrap, verify `.env` contains REAL values (not placeholders):
   ```
   # ❌ WRONG - these are placeholders, NOT real values:
   # ITK_LOG_GROUPS=  # commented out = not set
   # ITK_BEDROCK_AGENT_ID=<your-agent-id>  # angle brackets = placeholder
   
   # ✅ CORRECT - real values look like:
   ITK_LOG_GROUPS=/aws/lambda/my-actual-function-name
   ITK_BEDROCK_AGENT_ID=ABC123XYZ
   ```
   
   To find values manually (only if auto-discovery fails):
   - Agent ID: AWS Console → Bedrock → Agents → click your agent → copy Agent ID
   - Log groups: AWS Console → CloudWatch → Log groups → find Lambda logs

## Phase 2: View Historical Executions

6. View the last hour of executions from CloudWatch:
   ```
   itk view --since 1h --out artifacts/history
   ```

7. Open `artifacts/history/index.html` in your browser.

## Phase 3: Create Tests from Logs

8. Derive test cases from CloudWatch logs:
   ```
   itk derive --entrypoint bedrock_invoke_agent --since 24h --out cases/derived
   ```

9. List the generated cases:
   ```
   Get-ChildItem cases/derived/*.yaml
   ```

## Phase 4: Run Tests

10. Run a derived test case:
    ```
    itk run --case cases/derived/<pick-one>.yaml --out artifacts/run1
    ```

11. Or run all derived cases as a suite:
    ```
    itk suite --cases-dir cases/derived --out artifacts/suite
    ```

## Success Criteria

- [ ] `itk bootstrap` shows ✅ for AWS credentials (NOT ⚠️)
- [ ] `.env` contains real values (no `#` comments, no `<placeholders>`)
- [ ] `artifacts/history/index.html` shows past executions
- [ ] `cases/derived/` contains at least one `.yaml` file
- [ ] `artifacts/run1/index.html` shows a sequence diagram
