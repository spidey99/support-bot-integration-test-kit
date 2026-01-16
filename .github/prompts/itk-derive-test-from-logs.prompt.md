# ITK: Derive test from logs

You will:
1) Read the case schema (`dropin/itk/schemas/itk.case.schema.json`)
2) Read fixture logs under `dropin/itk/fixtures/logs/`
3) Produce a new YAML case under `dropin/itk/cases/derived/`

Rules:
- Do not guess fields.
- If data is missing, annotate `notes.missing_fields`.
- Put raw request payload in `entrypoint.payload`.
