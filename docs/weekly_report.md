# Weekly Progress Report

## 1. Header / Metadata

| Field | Detail |
|---|---|
| **Student** | Nithin Pullanivalappil Joshy |
| **Student ID** | 60781653 |
| **Company** | Truuth — Sydney-based digital identity verification and fraud-detection company |
| **Supervisor** | Johnson Rouslie Junior (johnsonrouslie.junior@truuth.id) |
| **Unit Convenor** | Dr. Yuankai Qi |
| **Project / Unit** | COMP8851 Major Project — Internship, Session 2 2026 |
| **Project / Team Name** | Claim Photo Location & Time Verification Module (Truuth Internship Project) |

---

## 2. Weekly Focus

This week centred on designing, building, and deploying an end-to-end **claim photo verification pipeline** that cross-checks a claimant's stated accident location and time against physical and visual evidence extracted from the submitted photograph, combining deterministic geolocation/weather data with AI vision-based scene judgment to produce an auditable fraud-risk score.

---

## 3. Project Hypothesis

The core technical thesis underpinning this module is that **insurance claim fraud relating to falsified location or time can be detected by triangulating independent evidence sources against the claimant's stated facts, rather than relying on any single check in isolation.** Objective, deterministic data (EXIF metadata, reverse geocoding plausibility, historical weather records) is combined with subjective but powerful visual reasoning (AI vision-model interpretation of signage, environment type, weather conditions, and lighting visible in the photograph itself). No single signal is trusted unconditionally — with the exception of two evidentially strong, hard-to-fake indicators (reverse-geocoding implausibility, and a categorical weather contradiction) which are treated as sufficient grounds for automatic escalation to human review. This hybrid architecture is designed to degrade gracefully: checks that cannot run for a given claim (e.g. no EXIF data, no Street View coverage for a given address) are excluded from scoring rather than penalising the claim, preserving fairness while maximising the evidentiary yield of the checks that *can* run.

---

## 4. Goals for the Week

- Design the full verification architecture end-to-end, including the tiered location-check structure and the time/weather verification track
- Define concrete, defensible flagging and severity rules distinguishing "automatic escalation" signals from "soft confidence" signals
- Implement each pipeline module (metadata, geocoding, OCR, vision-AI, weather, scoring) as independently testable Python components
- Establish AI vision-model access for the checks requiring visual judgement (signage reading, environment classification, weather-in-photo, lighting)
- Validate the complete pipeline against real claim-style inputs, using real APIs and a live AWS Bedrock connection
- Produce setup documentation suitable for a non-technical or first-time user to run the tool independently

---

## 5. Tasks Completed

| Task | Status | Notes |
|---|---|---|
| Define the four-tier location verification architecture (signage/OCR, imagery, reverse-geocoding plausibility, property/environment type) | Complete | Tiers 3 and 4 designed to run unconditionally on every claim; Tiers 1 and 2 designed as opportunistic/conditional checks that enrich, rather than gate, the verdict |
| Design and finalise the flagging/severity decision logic | Complete | Reverse-geocoding failure (Tier 3) and a categorical ("major") weather contradiction were each defined as independent, sufficient triggers for automatic escalation; combined occurrence escalates to "critical" severity |
| Build the EXIF metadata extraction module | Complete | Extracts GPS and timestamp from image files where present; correctly handles the common case where EXIF has been stripped (e.g. by messaging apps) by marking fields N/A rather than failing the claim |
| Build the forward/reverse geocoding module | Complete | Uses OpenStreetMap's free Nominatim service to resolve a claimed address or street name into coordinates, and to verify those coordinates plausibly resolve to a real road/address |
| Build the nearby-places lookup for signage cross-referencing | Complete | Uses the Overpass API to pull real shop/street names near the claimed location, used as the ground truth for Tier 1 text matching |
| Build the OCR + fuzzy-matching component (Tier 1, method A) | Complete | Uses Tesseract OCR locally; verified it correctly recovers a fuzzy match even from garbled character recognition (e.g. "COLESCHATSWOD" → "Coles Chatswood") |
| Build the reusable AI vision-model helper | Complete | Single function handles all four vision-judgement checks (signage/scene reading, environment type, weather-in-photo, lighting), returning a constrained category plus a plain-text justification for audit purposes |
| Build the scoring and flagging engine | Complete | Implements the finalised decision table exactly; unit-tested against every combination in that table before deployment |
| Build the main orchestrator and dual-CSV output | Complete | Produces a lean reviewer-facing verdict file and a full audit-detail file recording every individual check's result and reasoning |
| Establish AI vision-model access via AWS Bedrock | Complete | Resolved a series of environment/credentials issues (IAM permission limitations, PATH configuration for AWS CLI and Tesseract, locating the correct regional inference-profile ID required for on-demand invocation of the Claude Sonnet model in the ap-southeast-2 region) |
| Validate the full pipeline against a live test claim | Complete | Ran the complete pipeline against a real photograph and address with live API calls (geocoding, weather, AI vision) rather than simulated data; identified and fixed two defects in the process (silent error suppression in the reporting layer, and a JSON-parsing failure caused by trailing text in a model response) |

---

## 6. Tasks In Progress

| Task | Status | Notes |
|---|---|---|
| Tier 4 ground-truth comparison against real property records | In Progress | The module currently records the AI's observed environment classification (e.g. "public street") but does not yet compare this against an authoritative property-type record for the claimed address; requires access to a suitable data source (e.g. council property records) |
| Tier 2 (Street View / Mapillary) imagery cross-check | In Progress | Architecture and fallback behaviour designed (this tier is explicitly optional and does not penalise a claim when no imagery coverage exists for a given address), but the imagery-retrieval integration itself has not yet been implemented |
| Self-consistency (majority-vote) checking for AI vision calls | In Progress | A configuration flag exists to run each vision check multiple times and take a majority verdict, reducing the impact of any single inconsistent model response; not yet implemented in the calling logic |

---

## 7. Deliverables

| Deliverable | Type | Status | Notes |
|---|---|---|---|
| Claim verifier Python package (9 modules: config, metadata, geocoding, weather, vision_llm, ocr_match, scoring, main, requirements) | Code | Complete (v1) | Structured for independent unit testing of each module; supports both direct Anthropic API access and AWS Bedrock as interchangeable vision-model providers |
| Setup and usage guide (README) | Documentation | Complete | Written for a non-technical user; covers environment setup, both AI-provider configuration paths, and known current limitations |
| Dual-CSV reporting schema (reviewer-facing verdict + full audit trail) | Data schema | Complete | Deliberately separated to keep the reviewer-facing file scannable while preserving full evidentiary detail for audits |
| Validated test coverage across core logic | Testing | Complete | Every scoring/flagging rule combination unit-tested; OCR and geocoding-parsing logic verified against realistic simulated and live responses |
| AWS Bedrock integration and live model access | Infrastructure | Complete | Includes support for both the standard AWS access-key/secret-key credential pair and the newer single-token Bedrock API key format |
| This weekly report | Documentation | Complete | — |

---

## 8. Progress Summary

The week's work moved the claim-verification concept from a purely conceptual design (discussed and iteratively refined across a series of design conversations) into a fully functioning, independently-tested software module. Each architectural decision was deliberately tested against edge cases before being finalised: for instance, the decision to treat Tiers 3 and 4 as unconditional checks (always computable from the claimed address alone) while treating Tiers 1 and 2 as conditional, opportunistic checks was driven by the recognition that photographic and imagery evidence is not uniformly available across all claim types — particularly private locations such as driveways or indoor garages, which will never have Street View coverage.

A particularly important refinement emerged directly from live testing: the AI vision-based signage check initially misclassified a bus's destination signage (indicating where the vehicle was *travelling to*) as contradicting the claimed location, when in fact such signage says nothing about where the *photograph itself* was taken. The check was subsequently redesigned to have the AI model explicitly distinguish between fixed, location-indicating signage (street signs, shop names) and transient, non-location signage (vehicle destinations, route numbers) before forming a verdict — a distinction that meaningfully reduces the false-positive rate of this check without weakening its ability to catch genuine discrepancies.

The most time-consuming portion of the week was not the software logic itself but establishing reliable access to a vision-capable AI model through Truuth's AWS Bedrock environment — this involved navigating IAM permission constraints, correctly configuring the local Windows development environment (Python, Tesseract OCR, AWS CLI), and ultimately discovering that the target Claude model required invocation via a regional inference-profile identifier rather than its base model ID, which is a Bedrock-specific requirement not immediately obvious from the initial error message.

**Outcome:** A fully operational, end-to-end claim verification pipeline is now running successfully against live data and live AI model inference, producing structured, auditable verdicts consistent with the finalised scoring design.

---

## 9. Key Technical Highlights

**Location verification pipeline**
- Tiered design separates unconditional checks (reverse-geocoding plausibility, environment-type classification) from conditional, evidence-opportunistic checks (OCR/AI signage matching, imagery comparison)
- Dual-method signage verification (local OCR plus independent AI vision reading) provides corroborating evidence rather than relying on a single extraction method, with an explicit "agreement" field recorded for audit purposes
- Reverse-geocoding plausibility check treated as one of only two automatic escalation triggers in the entire system, reflecting its high reliability as a fraud signal

**Time verification pipeline**
- Historical weather record retrieved from a free, authoritative source (Open-Meteo) and compared against an independent AI-vision reading of the conditions actually visible in the photograph
- Weather mismatches classified by severity (minor vs. major) rather than as a flat pass/fail, reflecting that ambiguous visual conditions (e.g. slightly overcast vs. light drizzle) carry materially less evidentiary weight than an unambiguous contradiction (e.g. claimed snowfall against a clearly sunny photograph)
- Lighting-condition check (day/night/dusk) implemented as a secondary, corroborating time-consistency signal

---

## 10. Blockers and Challenges

- **AWS IAM permission constraints:** the initial AWS account provided did not have permission to view or generate its own access credentials via the console, requiring escalation to the supervisor and, ultimately, use of a temporary SSO-issued credential set instead.
- **Windows environment/PATH configuration:** both Tesseract OCR and the AWS CLI installed successfully via `winget` but were not immediately available in the active terminal session due to Windows not refreshing the PATH environment variable for already-open shells — resolved by restarting the terminal after each installation.
- **Bedrock on-demand invocation restriction:** the target Claude Sonnet model could not be invoked directly by its base model ID under Truuth's account configuration; AWS returned a `ValidationException` requiring the use of a regional inference-profile identifier instead, which required a further round of investigation via the AWS CLI to resolve.
- **Silent error suppression (self-identified defect):** an early version of the reporting layer discarded AI vision-model error messages rather than recording them, which meant early failed test runs produced no diagnostic information. This was identified and fixed before it could obscure a genuine issue during later testing.
- **Ongoing risk:** the system's most visually-dependent checks (Tiers 1 and 4, and the weather/lighting checks) rely on AI vision-model judgement, which is not perfectly deterministic between runs. This is a known and accepted limitation for the current version; the planned self-consistency (majority-vote) mechanism is intended to mitigate, but not eliminate, this risk going forward.

---

## 11. Next Steps

- Implement the Tier 2 (Street View / Mapillary) imagery cross-check integration
- Source and integrate a real property-type reference dataset to complete the Tier 4 ground-truth comparison
- Implement the self-consistency (majority-vote) mechanism for AI vision calls to reduce judgement variance
- Build a batch-processing capability to run the pipeline across multiple claims from a single input file, rather than one command-line invocation per claim
- Pilot the tool against a small set of real (anonymised) historical claims, in consultation with the supervisor, to sanity-check the scoring thresholds against real-world outcomes before wider use

---

## 12. Reference Links

- Project source code and documentation: local project folder (`claim_verifier/`), maintained on the student's development machine pending a decision on internal repository hosting
- AWS Bedrock model access and configuration: managed within Truuth's internal AWS account (`597571589726`, `ap-southeast-2` region)

---

## 13. Overall Status

**Status: On Track**

All planned architectural design and core implementation goals for the week were met, and the module is now verified as functioning end-to-end against live data sources and live AI inference rather than only simulated conditions. The remaining open items (Tier 2 imagery, Tier 4 ground-truth data, self-consistency voting, batch processing) are incremental enhancements to an already-operational system rather than blocking dependencies, and are appropriately scheduled as next week's focus.
