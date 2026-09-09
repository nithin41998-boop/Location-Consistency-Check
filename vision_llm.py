"""
vision_llm.py
-------------
One reusable function that sends a photo + a question to Claude (a
vision-capable model) and gets back a structured answer. This is used
for every check that needs actual visual judgment - things plain code
can't do:
  - Tier 1: does the scene support/contradict the claimed nearby places?
  - Tier 4: what kind of location does this look like (driveway/street/
    car park/highway)?
  - Weather: what conditions are visible in the photo?
  - Lighting: does it look like day/night/dusk?

Supports TWO ways of reaching Claude, controlled by config.VISION_LLM_PROVIDER:
  - "anthropic": direct Anthropic API key (ANTHROPIC_API_KEY env var)
  - "bedrock":   AWS Bedrock (uses boto3 + your AWS credentials)
Ask your supervisor which one Truuth uses before running this for real.
"""

import base64
import json
import mimetypes
import os
import requests
import config

try:
    import boto3
except ImportError:
    boto3 = None  # only needed if VISION_LLM_PROVIDER = "bedrock"


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


def _encode_image(image_path):
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "image/jpeg"
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, mime_type


def _call_anthropic_direct(image_data, mime_type, prompt):
    """Sends the request straight to api.anthropic.com using an API key."""
    headers = {
        "x-api-key": config.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_data}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    resp = requests.post(ANTHROPIC_API_URL, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()


def _call_bedrock(image_data, mime_type, prompt):
    """
    Sends the same request through AWS Bedrock instead of Anthropic directly.
    Needs boto3 installed and either:
      - a Bedrock API key (config.BEDROCK_API_KEY, starts with "ABSK...") - simplest, or
      - traditional AWS Access Key ID + Secret Access Key (env vars, boto3
        picks these up automatically).
    """
    if boto3 is None:
        raise RuntimeError("boto3 is not installed - run: pip install boto3")

    # If a Bedrock API key (ABSK...) is set, AWS's SDK reads it via this
    # specific environment variable - this is the simpler, single-token
    # auth method, no separate access key/secret pair needed.
    if config.BEDROCK_API_KEY:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = config.BEDROCK_API_KEY

    client = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_data}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    response = client.invoke_model(
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"].strip()


def ask_vision_llm(image_path, question, allowed_categories=None):
    """
    Sends the image + a question to Claude, via whichever provider is
    configured (config.VISION_LLM_PROVIDER). If allowed_categories is
    given, instructs the model to answer using only one of those labels,
    which keeps the result easy to compare programmatically.

    Returns dict: category (str), confidence ("high"/"medium"/"low"),
    reasoning (str), error (str or None)
    """
    result = {"category": None, "confidence": None, "reasoning": None, "error": None}

    provider = config.VISION_LLM_PROVIDER

    if provider == "anthropic" and not config.ANTHROPIC_API_KEY:
        result["error"] = "ANTHROPIC_API_KEY not set - skipping vision check"
        return result
    if provider == "bedrock" and boto3 is None:
        result["error"] = "boto3 not installed - skipping vision check (pip install boto3)"
        return result

    try:
        image_data, mime_type = _encode_image(image_path)
    except Exception as e:
        result["error"] = f"could not read image file: {e}"
        return result

    category_instruction = ""
    if allowed_categories:
        cats = ", ".join(allowed_categories)
        category_instruction = (
            f"\n\nYou MUST answer with exactly one of these category labels: {cats}. "
            "Base your answer ONLY on what is visually present in the image - "
            "do not guess or infer from unrelated context."
        )

    prompt = (
        f"{question}{category_instruction}\n\n"
        "Respond ONLY with valid JSON in this exact format, no other text:\n"
        '{"category": "<your chosen label>", "confidence": "high|medium|low", '
        '"reasoning": "<one sentence explaining what visual evidence led to this>"}'
    )

    try:
        if provider == "bedrock":
            raw_text = _call_bedrock(image_data, mime_type, prompt)
        else:
            raw_text = _call_anthropic_direct(image_data, mime_type, prompt)

        # Model may occasionally wrap JSON in markdown fences, or add a
        # stray sentence before/after the JSON object - extract just the
        # {...} block instead of assuming the whole response is pure JSON.
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError(f"no JSON object found in model response: {raw_text[:200]!r}")
        json_slice = raw_text[start:end + 1]

        parsed = json.loads(json_slice)
        result["category"] = parsed.get("category")
        result["confidence"] = parsed.get("confidence")
        result["reasoning"] = parsed.get("reasoning")
    except Exception as e:
        result["error"] = f"vision LLM call failed ({provider}): {e}"

    return result


# ---- Convenience wrappers for each specific check ----

def check_weather_in_photo(image_path):
    return ask_vision_llm(
        image_path,
        "Look at this photo of a vehicle accident scene. Based only on visible "
        "evidence (sky, road surface, precipitation, puddles, snow, people's "
        "clothing, lighting), what were the weather conditions when this photo "
        "was taken?",
        allowed_categories=["clear", "cloudy", "rain", "snow", "fog", "storm", "unclear"],
    )


def check_property_type(image_path):
    return ask_vision_llm(
        image_path,
        "Look at this photo of a vehicle accident scene. What type of location "
        "does this appear to be?",
        allowed_categories=["residential_driveway", "public_street", "private_car_park",
                             "highway", "indoor_garage", "unclear"],
    )


def check_lighting(image_path):
    return ask_vision_llm(
        image_path,
        "Look at this photo. Based on the lighting, shadows, and sky, what time "
        "of day does this appear to be?",
        allowed_categories=["daytime", "night", "dusk_or_dawn", "unclear"],
    )


def check_scene_text_and_places(image_path, nearby_places):
    places_str = ", ".join(nearby_places) if nearby_places else "(none found nearby)"
    return ask_vision_llm(
        image_path,
        "Look at this photo of a vehicle accident scene. Read any visible text in the image, "
        "then classify it into two kinds:\n"
        "  (a) LOCATION-INDICATING text - things fixed in place that tell you where you actually "
        "are: street name signs, shop/business storefront names, building numbers, suburb/area "
        "signs.\n"
        "  (b) NON-LOCATION text - things that do NOT tell you where the photo was taken, even "
        "though they're visible: a bus/train's destination board (shows where that vehicle is "
        "headed, not where it currently is), route/line numbers, vehicle number plates, highway "
        "exit signs pointing to other places, advertising, or any text on a moving vehicle.\n\n"
        "Here is a list of businesses/streets known to be near the claimed location: "
        f"{places_str}.\n\n"
        "Base your match verdict ONLY on category (a) LOCATION-INDICATING text. If the only text "
        "visible is category (b), that does not count as a contradiction - it simply means no "
        "reliable location evidence was found in the image.",
        allowed_categories=["match", "no_match", "contradicts", "only_non_location_text_found", "no_text_visible"],
    )
