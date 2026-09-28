# Hyperspell SuperMe Interview Agent

Python CLI for a truthful, explainable SuperMe interview workflow for Chetas Nikunjbhai Parekh's Hyperspell Product Engineer application.

The agent:

- loads candidate context from `./data`
- builds a hybrid BM25 + dense retrieval index
- drafts grounded interview answers with NVIDIA NIM Gemma 4
- shows private source explanations before sending
- requires manual approval before every response
- requires exact manual confirmation before final submission

## Setup

```bash
cd hyperspell-interview-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```bash
SUPERME_API_KEY=your_superme_key
SUPERME_ROLE_ID=43A0pbylxajHuP7wQ8m3
NIM_API_KEY=your_nvidia_nim_key
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=google/gemma-4-31b-it
NIM_MAX_TOKENS=1200
NIM_LONG_MAX_TOKENS=2500
NIM_ABSOLUTE_MAX_TOKENS=6000
```

Hosted NVIDIA NIM requires `NIM_API_KEY`. Local NIM can run without a key:

```bash
export NIM_BASE_URL="http://0.0.0.0:8000/v1"
export NIM_MODEL="google/gemma-4-31b-it"
```

## NVIDIA NIM

```bash
export NIM_API_KEY="your_key"
export NIM_BASE_URL="https://integrate.api.nvidia.com/v1"
export NIM_MODEL="google/gemma-4-31b-it"
```

The CLI checks model availability before `run`. If `google/gemma-4-31b-it` is not visible for the endpoint/key, use another available model or run local NIM.

Default answer length is 300-700 words. Technical architecture, system design, debugging-plan, tradeoff, and deep-dive questions use a 700-1200 word target and a 2500-token generation ceiling. The CLI will not exceed 2500 tokens unless you pass `--long-mode`, which allows up to `NIM_ABSOLUTE_MAX_TOKENS`. If a draft exceeds about 1800 words, the CLI shows a summary and requires an extra confirmation before sending.

## SuperMe SDK

`requirements.txt` installs SuperMe from GitHub:

```text
superme-sdk @ git+https://github.com/superme-ai/superme-sdk.git@main
```

The wrapper still handles missing or changed SDK methods defensively.

## Add Candidate Files

Put resume, project docs, notes, and other truthful context in:

```text
data/
```

Supported file types:

- `.md`
- `.txt`
- `.pdf`
- `.docx`
- `.html`

Starter files are included:

- `data/candidate_context.md`
- `data/resume.md`
- `data/projects.md`
- `data/hyperspell_notes.md`

Replace or extend them with your real resume and project details before running the live interview.

## GitHub And LinkedIn Context

GitHub setup:

```bash
export GITHUB_TOKEN="your_read_only_token"
export GITHUB_USERNAME="your_username"
python -m src.interview_runner ingest-github
```

Use a fine-grained personal access token with read-only access to selected repositories. The agent collects repository metadata, README text, language data, topics, and recent commit messages. It does not pull source trees by default.

## LinkedIn Context Setup

1. Open your LinkedIn profile in a browser.
2. Click `More`.
3. Click `Save to PDF`.
4. Rename the file to `LinkedIn_Profile.pdf`.
5. Put it here: `data/LinkedIn_Profile.pdf`
6. Run:

```bash
python -m src.interview_runner ingest
```

LinkedIn API/OAuth is intentionally not used. The PDF method is more reliable for this interview agent and keeps your profile local. Verify the extracted profile content before submitting interview answers.

Use the debug commands:

```bash
python -m src.interview_runner ingest-linkedin
python -m src.interview_runner show-linkedin
```

Personal source documents are ignored by `.gitignore`:

```text
data/*.pdf
data/*.docx
data/*.txt
```

## Build Retrieval Index

```bash
python -m src.interview_runner ingest
```

This writes local artifacts to `./artifacts`.

## Local Draft With NIM

Draft without sending anything to SuperMe:

```bash
python -m src.interview_runner ask "Tell me about yourself"
python -m src.interview_runner ask "Why Hyperspell?"
```

By default, the agent retrieves the top context chunks and sends only those chunks to NIM. Full-context mode is available only when explicitly requested:

```bash
python -m src.interview_runner ask "Tell me about yourself" --full-context
```

Long mode must be explicit:

```bash
python -m src.interview_runner ask "Architecture deep dive" --long-mode
```

## Start The Interview

```bash
python -m src.interview_runner start
```

This starts the Hyperspell interview using `SUPERME_ROLE_ID` and saves the session to:

```text
artifacts/session.json
```

## Draft, Approve, Edit, Send

Draft the current answer:

```bash
python -m src.interview_runner answer
```

Or paste a question manually:

```bash
python -m src.interview_runner answer "Why Hyperspell?"
```

Use `ask` for local drafts that never send. Use `answer` only when you may want to approve and send through the saved SuperMe session.

For each answer, the CLI shows:

- the question
- draft answer
- confidence
- used sources and chunks
- claimed facts
- missing information
- private explanation

It then asks:

```text
Send this answer? y/N/edit
```

Choose `edit` to revise before sending.

## Guided Run

```bash
python -m src.interview_runner run
```

The guided loop checks NIM model availability, starts or resumes a session, checks status, drafts answers when input is needed, and asks for approval before sending.

## Safe Final Submit

Final submission is never automatic.

```bash
python -m src.interview_runner submit
```

You must type exactly:

```text
SUBMIT HYPERSPELL INTERVIEW
```

## Tests

```bash
python -m pytest
```

## Important Truthfulness Rules

- Do not claim 3+ years of full-time product engineering experience.
- Do not invent credentials, dates, employment history, work authorization, degree completion, or production usage.
- If information is missing, the agent should ask you to fill it in.
- The explanation shown in the terminal is private and is not sent to SuperMe unless you explicitly copy it.
