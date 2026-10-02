"""AI classification of pollution photos via the Claude API.

Falls back to a mock classifier (random category + note) when no working
Anthropic credentials are available, so the demo runs end-to-end offline.
"""
import os
import random
import logging

import anthropic

log = logging.getLogger(__name__)

CATEGORIES = [
    "Litter / plastic waste",
    "Oil or chemical spill",
    "Sewage / wastewater",
    "Industrial waste / discharge",
    "Air pollution (smoke, visible emissions)",
    "Illegal dumping (bulky waste, construction debris)",
    "Other / unclear",
]

SEVERITIES = ["low", "medium", "high"]

# Below this, the report is routed to a manual confirm step instead of
# being saved straight to the shared database (see the flowchart in the
# concept doc: "Low confidence -> Flagged for manual category pick").
CONFIDENCE_THRESHOLD = 0.6

CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "claude-haiku-4-5")

SYSTEM_PROMPT = (
    "You are the classification step in a crowd-sourced pollution reporting app. "
    "You will be shown one photo submitted by a member of the public who believes it "
    "shows some form of pollution. Call the record_classification tool exactly once "
    "with your best assessment. Pick the single closest category from the fixed list "
    "in the tool schema - never invent a new category. If the photo does not clearly "
    "show pollution, or you are unsure, use 'Other / unclear' and give it a low "
    "confidence score. Keep the description to one short, plain sentence describing "
    "only what is visibly in the photo. Base severity on the visible extent of the "
    "pollution (small/contained = low, moderate = medium, large-scale or hazardous = high)."
)

CLASSIFICATION_TOOL = {
    "name": "record_classification",
    "description": "Record the pollution classification for the submitted photo.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "How confident you are in this category, 0-1.",
            },
            "description": {
                "type": "string",
                "description": "One short sentence describing what is visible.",
            },
            "severity": {"type": "string", "enum": SEVERITIES},
        },
        "required": ["category", "confidence", "description", "severity"],
    },
}


def classify_photo(image_path: str) -> dict:
    """Classify a (already compressed, JPEG) photo. Never raises - falls back to a mock result."""
    try:
        return _classify_with_claude(image_path)
    except Exception as exc:  # noqa: BLE001 - any failure should degrade to the demo mock
        log.warning("Claude classification unavailable, using mock classifier: %s", exc)
        return _mock_classify()


def _classify_with_claude(image_path: str) -> dict:
    import base64

    client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY / ant auth profile

    with open(image_path, "rb") as f:
        image_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model=CLASSIFIER_MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFICATION_TOOL],
        tool_choice={"type": "tool", "name": "record_classification"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Classify the pollution shown in this photo.",
                    },
                ],
            }
        ],
    )

    tool_use = next(b for b in response.content if b.type == "tool_use")
    data = tool_use.input

    category = data.get("category")
    if category not in CATEGORIES:
        category = "Other / unclear"

    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0

    severity = data.get("severity")
    if severity not in SEVERITIES:
        severity = "medium"

    return {
        "category": category,
        "confidence": round(confidence, 2),
        "description": str(data.get("description", ""))[:300],
        "severity": severity,
        "source": "claude",
    }


def _mock_classify() -> dict:
    category = random.choice(CATEGORIES[:-1])  # bias away from "Other" for a livelier demo
    return {
        "category": category,
        "confidence": round(random.uniform(0.35, 0.9), 2),
        "description": (
            "Demo mode: no Claude API credentials configured, so this is a randomly "
            "generated mock classification, not a real AI result."
        ),
        "severity": random.choice(SEVERITIES),
        "source": "mock",
    }
