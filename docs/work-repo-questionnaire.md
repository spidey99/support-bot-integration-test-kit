# Work Repo Context Questionnaire

> **ITK-0017.5** — Fill this out so I can generate the right integration templates.
> 
> ⏱️ **~5 minutes** • Just pick options, no essays required.

---

## 1. Repository Basics

### 1.1 Primary language?
- [x] Python only
- [ ] Python + TypeScript/JS (CDK)
- [ ] Python + other (specify below)
- **Other:** _______________

### 1.2 Package manager for Python?
- [x] pip + requirements.txt
- [ ] pip + pyproject.toml
- [ ] Poetry
- [ ] PDM
- [ ] uv
- [ ] Conda

### 1.3 Monorepo or single project?
- [ ] Single project (one deployable)
- [ ] Monorepo (multiple services/apps)
- [x] Hybrid (shared libs + services)

---

## 2. AWS / Infrastructure

### 2.1 IaC tool?
- [x] AWS CDK (Python)
- [ ] AWS CDK (TypeScript)
- [ ] Terraform
- [ ] CloudFormation YAML/JSON
- [ ] SAM
- [ ] Mix (specify below)
- **Other:** _______________

### 2.2 Where does CDK synth happen?
- [ ] Locally (`cdk synth`)
- [x] CI pipeline only
- [ ] Both

### 2.3 AWS environments?
- [ ] dev / qa / prod
- [ ] dev / staging / prod
- [ ] Single environment (dev or sandbox)
- [x] Other: ____qa (per branch) / prod___________

### 2.4 How do you get AWS creds locally?
- [ ] AWS SSO (`aws sso login`)
- [ ] IAM user access keys in `~/.aws/credentials`
- [ ] Environment variables
- [ ] AWS Vault
- [x] Other: ____sso auth + pick account and role + copy the "export" credentials script + add to .env___________

---

## 3. CI/CD

### 3.1 CI platform?
- [ ] GitHub Actions
- [x] GitLab CI
- [ ] AWS CodePipeline / CodeBuild
- [ ] Jenkins
- [ ] CircleCI
- [ ] Other: _______________

### 3.2 Do you have a CI config file I should know about?
- [ ] `.github/workflows/*.yml`
- [ ] `buildspec.yml`
- [x] `.gitlab-ci.yml`
- [ ] `Jenkinsfile`
- [ ] None / managed elsewhere
- **Path if other:** _______________

### 3.3 Pre-commit hooks in use?
- [ ] Yes, using `pre-commit` framework
- [ ] Yes, custom git hooks
- [ ] No hooks currently
- [x] Not sure (There's a lot of nested includes obfuscating a lot of the CI away)

---

## 4. IDE / Dev Workflow

### 4.1 Primary IDE?
- [x] VS Code
- [ ] PyCharm
- [ ] Cursor
- [ ] Neovim / Vim
- [ ] Other: _______________

### 4.2 Do you use VS Code tasks.json?
- [ ] Yes, actively
- [ ] Have one but rarely use
- [ ] No
- [x] What's that?

### 4.3 Dev container / remote setup?
- [ ] Local only (no containers)
- [ ] VS Code Dev Containers
- [ ] GitHub Codespaces
- [ ] Remote SSH to dev box
- [x] Other: _______There is a dev container, but it prevent me from using my custom vs code extension set up, so I just use a venv for test execution, etc. I push to remote for ci auto deploy of the branch, then locally run the integration tests against that deployed code________

---

## 5. Testing

### 5.1 Test runner?
- [ ] pytest
- [ ] unittest
- [ ] Both / mixed
- [x] Other: ______lol not sure, I let the coding agents set it up...there are some drawback to code agents :( _________

### 5.2 Where do tests live?
- [x] `tests/` at repo root
- [ ] `test/` at repo root
- [ ] Alongside source (`src/**/test_*.py`)
- [ ] Mixed / per-package
- **Path if other:** _______________

### 5.3 Integration test setup?
- [ ] Mocked AWS (moto, localstack)
- [x] Real AWS in dev/qa account
- [ ] Both depending on test type
- [ ] No integration tests yet

---

## 6. Repo Structure Hints

### 6.1 Where are Lambda handlers?
- [x] `src/lambdas/`
- [ ] `lambdas/`
- [ ] `functions/`
- [ ] Scattered across packages
- **Path:** _______________

### 6.2 Where is CDK infrastructure code?
- [ ] `infrastructure/`
- [ ] `infra/`
- [ ] `cdk/`
- [x] Root level cdk + app files
- **Path:** _______________

### 6.3 Config files location?
- [ ] Repo root (pyproject.toml, etc.)
- [ ] `config/` folder
- [ ] Mixed
- [x] Other: env folder

---

## 7. Quick Preferences

### 7.1 Generated file markers?
- [ ] `# AUTO-GENERATED — do not edit` comment at top
- [ ] `.generated` suffix on filenames
- [x] No marker needed
- [ ] Other: _______________

### 7.2 Preferred line length?
- [ ] 80
- [x] 88 (black default)
- [ ] 100
- [ ] 120
- [ ] Don't care

### 7.3 YAML style?
- [x] 2-space indent
- [ ] 4-space indent
- [ ] Don't care

---

## 8. Anything Else?

> Optional free-text. Skip if brain is done.

```
(paste anything relevant here, or leave blank)
```

---

## Done! 🎉

Save this file and I'll use your answers to generate:
- `.github/workflows/itk.yml` (or equivalent CI)
- `.pre-commit-config.yaml` additions
- `.vscode/tasks.json` ITK shortcuts
- `README` setup section for ITK
