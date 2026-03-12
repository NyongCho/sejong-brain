# AGENTS.md

## Scope
- All new RAGAS-related code must live under `ragas/` only.
- Do not refactor unrelated parts of the repository.
- Minimize modifications to existing code; prefer adapters and wrappers.

## Goal
Implement a repo-local RAGAS evaluation toolkit that:
- normalizes current pdfplumber-based PDF chunk outputs
- normalizes crawled notice JSON inputs
- generates evaluation samples for RAG testing
- supports baseline-first experiments

## Baseline experiment rule
- The current baseline uses pdfplumber-derived PDF chunks.
- Default testset generation must use baseline-compatible PDF inputs first.
- Future parser inputs (`llamaparse`, `marker`) may be supported through adapters, but must not become the default generation path.
- Keep parser_type explicit in schemas and outputs.

## Data normalization
Support two input sources:
1. PDF chunk JSON from the current pipeline
2. Crawled notice JSON with fields:
   - id
   - url
   - title
   - date
   - category
   - content

Normalize into a common Document-like schema with:
- page_content
- metadata

Metadata should include at least:
- source_type
- source_id
- parser_type
- chunk_id
- table_related
- title
- date
- category
- url
- page_start
- page_end
- section_title
- file_name

## Evaluation sample schema
Support:
- id
- question
- ground_truth
- evidence
- question_type
- answerable
- table_related
- source_type
- source_id
- parser_type
- generation_mode
- review_status
- provenance
- optional difficulty / notes

Allowed question_type:
- single_fact
- notice_fact
- notice_summary
- multi_hop
- table_exact_lookup
- table_compare
- no_answer
- business_critical

Allowed generation_mode:
- auto
- manual_template
- llm_manual_like

Allowed review_status:
- unreviewed
- reviewed
- approved

## Synthetic manual-like rule
For testing only, allow LLM-generated draft samples for:
- table_exact_lookup
- table_compare
- no_answer
- business_critical

These must be clearly marked as:
- generation_mode = llm_manual_like
- review_status = unreviewed
- provenance filled

They are draft data, not final gold labels.

## Implementation requirements
Create new files only under:
- ragas/

Preferred structure:
- ragas/__init__.py
- ragas/config.py
- ragas/schemas.py
- ragas/adapters.py
- ragas/document_builders.py
- ragas/prompts.py
- ragas/templates.py
- ragas/generator.py
- ragas/validators.py
- ragas/exporters.py
- ragas/cli.py
- ragas/README.md
- ragas/examples/

## CLI expectations
Support commands for:
- normalize-pdf
- normalize-notice
- generate
- validate
- init-manual-template

Default generate behavior should prefer baseline-only PDF docs unless explicitly overridden.

## Code quality
- Python 3.10+
- strong typing
- clear docstrings
- explicit validation
- useful logging
- JSONL-first import/export
- dry-run support where possible

## Safety
- Do not delete or rewrite unrelated files.
- Show a file tree before implementation.
- If an assumption is required, state it clearly.