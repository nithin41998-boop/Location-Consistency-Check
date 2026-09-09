# Truuth Claim Verifier — Setup & Run Guide

This checks whether an accident photo is consistent with the location
and date/time a claimant reports. It combines:
- EXIF metadata (if present in the photo)
- Reverse geocoding plausibility (Tier 3)
- OCR + AI vision reading of signage/scene (Tier 1)
- AI vision reading of the property type (Tier 4)
- Historical weather vs. weather visible in the photo

Everything below is copy-paste. Run each block in order, in a terminal
(Command Prompt / Terminal / VS Code terminal), inside this folder.

---

## Step 1 — Install Python (one-time only)

Skip this if you already have Python. Check by running:
```
python3 --version
```
If that fails, download Python from https://www.python.org/downloads/
and install it (tick "Add to PATH" during install on Windows).

## Step 2 — Install Tesseract OCR (one-time only)

This is a separate program the OCR module needs — it is NOT installed
via pip.

- **Windows**: download and run the installer from
  https://github.com/UB-Mannheim/tesseract/wiki
- **Mac**: `brew install tesseract`
- **Linux**: `sudo apt install tesseract-ocr`

## Step 3 — Install the Python packages (one-time only)

From inside this folder, run:
```
pip install -r requirements.txt
```

## Step 4 — Set up access to Claude (one-time per terminal session)

This program uses Claude (Anthropic's AI) for the checks plain code
can't do (weather in the photo, property type, scene reading). There
are TWO ways to reach it - ask your supervisor which one Truuth uses.

### Option A: Direct Anthropic API key (simplest)

```
$env:VISION_LLM_PROVIDER="anthropic"
$env:ANTHROPIC_API_KEY="paste-your-key-here"
```
(On Mac/Linux use `export` instead of `$env:`.)

### Option B: AWS Bedrock

If Truuth routes AI usage through AWS, ask your supervisor for a
**Bedrock API key** (a single key starting with `ABSK...`) — this is
the simplest option, just one value:

```
$env:VISION_LLM_PROVIDER="bedrock"
$env:BEDROCK_API_KEY="ABSK...paste-the-full-key-here"
$env:AWS_REGION="ap-southeast-2"
$env:BEDROCK_MODEL_ID="the-exact-model-id-your-supervisor-gives-you"
```

Alternatively, if they give you a traditional AWS Access Key ID +
Secret Access Key pair instead, use this instead of `BEDROCK_API_KEY`:
```
$env:VISION_LLM_PROVIDER="bedrock"
$env:AWS_ACCESS_KEY_ID="paste-here"
$env:AWS_SECRET_ACCESS_KEY="paste-here"
$env:AWS_REGION="ap-southeast-2"
$env:BEDROCK_MODEL_ID="the-exact-model-id-your-supervisor-gives-you"
```

`VISION_LLM_PROVIDER` defaults to `"anthropic"` if you don't set it, so
Option A is what runs unless you explicitly switch to Bedrock.

If you don't have either set up yet, that's fine for now — the
program will still run and complete everything except the AI vision
checks, which will just show up as "N/A" with a note explaining why.

## Step 5 — Run it on a claim

Put the accident photo somewhere you can find it, then run:

```
python3 main.py --image "path/to/photo.jpg" --address "200 George Street, Sydney NSW" --datetime "2026-08-15 14:30"
```

Replace the image path, address, and datetime with the real claim
details. The datetime format is `YYYY-MM-DD HH:MM` (24-hour clock).

## Step 6 — Check the results

Two files will appear in a new `output/` folder:
- `output/main_verdict.csv` — short summary (open in Excel)
- `output/audit_detail.csv` — every check's full detail, for audits

Each time you run Step 5 on a new claim, a new row is added to both
files — they are not overwritten.

---

## Processing many claims at once (optional)

If you have a batch of claims, you can write a small loop instead of
running Step 5 manually each time. Ask me for a batch-processing
script once you have real claim data in a spreadsheet, and I'll adapt
this to read a CSV of claims and process them all automatically.

---

## Known limitations (worth knowing for your project report)

- **EXIF is often missing.** WhatsApp, Facebook, and gallery re-saves
  strip it. The program handles this gracefully (marks it N/A, does
  not penalise the claim) — it just means EXIF won't always be
  available as evidence.
- **Street-name-only addresses are less precise than full addresses.**
  The `geocode_precision` column in the audit CSV tells you which kind
  you got for each claim.
- **Tier 4 (property type) currently checks the photo's *observed*
  type via AI but does not yet compare it against a real property
  database of the claimed address** — that comparison needs a data
  source Truuth may already have access to (e.g. council property
  records). Right now it records what the AI sees; wiring in the
  comparison is a natural next step.
- **AI vision checks are not 100% consistent run-to-run.** For higher
  reliability, `config.py` has a `VISION_SELF_CONSISTENCY_RUNS`
  setting — raising it to 3 will call the AI three times per check and
  take a majority vote, at the cost of more API calls.
- Every module was tested individually during development. The
  network calls to OpenStreetMap/Open-Meteo could not be tested live
  from the build environment (network restrictions there), so test
  them for real once you run this on your own machine with real
  internet access — if something looks off, send me the error message.
