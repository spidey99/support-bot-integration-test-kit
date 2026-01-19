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

5. **If bootstrap reports missing credentials, you need to set up the `.env` file.** Follow these sub-steps:

   a. First, copy the example file:
      ```
      Copy-Item .env.example .env
      ```

   b. Ask the user: "How do you authenticate to AWS? Do you use:
      - **AWS SSO** (you log in via a web browser), or
      - **IAM Access Keys** (you have an access key ID and secret)?"

   c. **If AWS SSO:** Tell the user to add their profile name:
      ```
      # In .env, set:
      AWS_PROFILE=your-sso-profile-name
      ```
      Then run: `aws sso login --profile your-sso-profile-name`

   d. **If IAM Access Keys:** Tell the user to get temporary credentials and add them:
      ```
      # In .env, set all three:
      AWS_ACCESS_KEY_ID=AKIA...
      AWS_SECRET_ACCESS_KEY=...
      AWS_SESSION_TOKEN=...  (if using MFA/assumed role)
      ```

   e. **Required for all setups - AWS Region:**
      ```
      AWS_REGION=us-east-1
      ```
      Ask the user: "What AWS region is your Bedrock Agent in? (default: us-east-1)"

   f. **Required - Bedrock Agent IDs:**
      Ask the user: "What is your Bedrock Agent ID? You can find this in the AWS Console under Bedrock > Agents."
      ```
      ITK_BEDROCK_AGENT_ID=XXXXXXXXXX
      ```
      
      Ask the user: "What is your Bedrock Agent Alias ID? (Use 'TSTALIASID' for the test alias, or your specific alias ID)"
      ```
      ITK_BEDROCK_AGENT_ALIAS_ID=TSTALIASID
      ```

   g. **Required - CloudWatch Log Groups:**
      Ask the user: "What CloudWatch log groups contain your agent's Lambda logs? These are usually named like `/aws/lambda/your-function-name`. Separate multiple log groups with commas."
      ```
      ITK_LOG_GROUPS=/aws/lambda/my-agent-handler,/aws/lambda/my-action-group
      ```

   h. **Verify the .env file has these minimum required values:**
      - `ITK_MODE=live`
      - `AWS_REGION=...`
      - `AWS_PROFILE=...` OR (`AWS_ACCESS_KEY_ID=...` AND `AWS_SECRET_ACCESS_KEY=...`)
      - `ITK_BEDROCK_AGENT_ID=...`
      - `ITK_BEDROCK_AGENT_ALIAS_ID=...`
      - `ITK_LOG_GROUPS=...`

   i. Run bootstrap again to verify:
      ```
      itk bootstrap
      ```
      This should now show ✅ for AWS credentials and Bedrock Agent access.

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
