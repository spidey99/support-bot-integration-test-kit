# ITK Setup & Test Prompt

You are setting up the Integration Test Kit (ITK) to test a Bedrock Agent deployed in AWS. Follow these steps exactly in order. Run each command and wait for it to complete before moving to the next step.

**IMPORTANT:** Always show the user command output and explain what happened. If any command fails, stop and help the user fix it before continuing.

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

5. **If bootstrap reports missing credentials, set up the `.env` file:**

   a. Ask: "How do you authenticate to AWS? SSO or IAM Access Keys?"

   b. **If AWS SSO:**
      ```
      AWS_PROFILE=your-sso-profile-name
      ```
      Then run: `aws sso login --profile your-sso-profile-name`

   c. **If IAM Access Keys:**
      ```
      AWS_ACCESS_KEY_ID=AKIA...
      AWS_SECRET_ACCESS_KEY=...
      AWS_SESSION_TOKEN=...  (if using MFA)
      ```

   d. **Required settings:**
      ```
      AWS_REGION=us-east-1
      ITK_BEDROCK_AGENT_ID=XXXXXXXXXX
      ITK_BEDROCK_AGENT_ALIAS_ID=TSTALIASID
      ITK_LOG_GROUPS=/aws/lambda/your-function-name
      ```

   e. Run bootstrap again: `itk bootstrap`

## Phase 2: Run Your First Test

6. Bootstrap creates `cases/my-first-test.yaml`. Edit it with your agent details, then run:
   ```
   itk run --case cases/my-first-test.yaml --out artifacts/run1
   ```

7. Open `artifacts/run1/index.html` in your browser.

## Phase 3: View Historical Executions

8. Discover AWS resources:
   ```
   itk discover --apply
   ```

9. View last hour of executions:
   ```
   itk view --since 1h --out artifacts/history
   ```

## Phase 4: Derive Tests from Logs

10. Create test cases from CloudWatch logs:
    ```
    itk derive --entrypoint bedrock_invoke_agent --since 24h --out cases/derived
    ```

11. Run the derived cases:
    ```
    itk suite --cases-dir cases/derived --out artifacts/suite
    ```

## Success Criteria

- [ ] `itk bootstrap` shows ✅ for credentials and agent
- [ ] `artifacts/run1/index.html` shows a sequence diagram
- [ ] `cases/derived/` contains at least one `.yaml` file
