# Talks to the model: builds the prompt, calls Ollama, reshapes the result for the web page.
import json
import os
import time

import requests

ollama_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
model_name = os.environ.get("OLLAMA_MODEL", "llama3.1")
DEMO_MODE = os.environ.get("DEMO_MODE") == "1"

# Rubric categories the model must score
rubric = [
    {
        "category": "Strengths/Weaknesses vs. Program Objectives",
        "description": "List the proposal's strengths and weaknesses as they relate to the "
                        "program objectives stated in the solicitation. Rate 1 (weakest) to "
                        "5 (strongest) based on those strengths and weaknesses.",
    },
    {
        "category": "Innovation and Advancement of Agency Needs",
        "description": "Is the project innovative in its field and will it advance the needs "
                        "of the agency? Rate 1 (limited innovation/advancement) to 5 (high "
                        "innovation and advancement of agency needs).",
    },
    {
        "category": "Quality of the Written Proposal",
        "description": "Is the white paper well written -- clear, concise, thoroughly "
                        "explained, well-reasoned, well-organized, based on a sound rationale, "
                        "and does it include a mechanism to assess success? Rate 1 (not well "
                        "developed) to 5 (highly developed).",
    },
    {
        "category": "Investigator/Team Capability",
        "description": "Is the investigator (or team/organization) able to adequately conduct "
                        "the proposed scope of work? How well qualified are they? Rate 1 (do "
                        "not agree) to 5 (strongly agree).",
    },
]


# Build the text prompt sent to the model
def build_prompt(solicitation: str, proposal: str, rubric: list[dict]) -> str:
    rubric_lines = "\n".join(
        f'- "{item["category"]}": {item["description"]}' for item in rubric
    )

    return f"""You are assisting a university proposal review office. You will score a PROPOSAL against a SOLICITATION using the REVIEW RUBRIC below.

For each rubric category, return:
- a score from 1 (weakest) to 5 (strongest)
- a short (1-3 sentences) constructive comment explaining the score, referencing specific parts of the proposal where possible.

REVIEW RUBRIC:
{rubric_lines}

SOLICITATION:
\"\"\"
{solicitation}
\"\"\"

PROPOSAL:
\"\"\"
{proposal}
\"\"\"

REMINDER: score ONLY these {len(rubric)} rubric categories, exactly as named, one review each:
{rubric_lines}

Respond with only valid JSON, no other text, in exactly this shape:
{{
    "reviews": [
    {{"category": "<category name>", "score": <1-5 integer>, "comment": "<comment>"}},
    ...
    ]
}}
"""


# Send the prompt to Ollama and return the parsed JSON
def call_ollama(prompt: str) -> dict:
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": {
            "type": "object",
            "properties": {
                "reviews": {
                    "type": "array",
                    "minItems": len(rubric),
                    "maxItems": len(rubric),
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string", "enum": [r["category"] for r in rubric]},
                            "score": {"type": "integer", "minimum": 1, "maximum": 5},
                            "comment": {"type": "string"},
                        },
                        "required": ["category", "score", "comment"],
                    },
                }
            },
            "required": ["reviews"],
        },
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }

    try:
        resp = requests.post(ollama_URL, json=payload, timeout=900)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Could not reach Ollama at {ollama_URL}. Is it running? Try: ollama serve")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Ollama returned an HTTP error: {e}")

    raw_content = resp.json().get("message", {}).get("content", "")
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        raise RuntimeError(f"The model did not return valid JSON. Raw output: {raw_content[:300]}")


# Keep a score between 1 and 5
def _clamp(v) -> int:
    try:
        return max(1, min(5, int(round(float(v)))))
    except (TypeError, ValueError):
        return 1


# Reshape the model's output into what the web page displays
def to_frontend(review_data: dict) -> dict:
    criteria = [
        {
            "name": str(r.get("category", "Criterion")),
            "score": _clamp(r.get("score")),
            "comment": str(r.get("comment", "")),
        }
        for r in review_data.get("reviews", [])
    ]
    if not criteria:
        raise RuntimeError("The model returned no reviews.")
    avg = sum(c["score"] for c in criteria) / len(criteria)
    return {
        "overall": _clamp(avg),
        "summary": f"Average score {avg:.1f} out of 5 across {len(criteria)} rubric categories.",
        "criteria": criteria,
        "strengths": [],
        "improvements": [],
    }


# Entry point used by app.py: review one proposal against one solicitation
def review_proposal(solicitation: str, proposal: str) -> dict:
    if DEMO_MODE:
        time.sleep(4)
        return to_frontend({"reviews": [
            {"category": r["category"], "score": s, "comment": f"Demo comment for {r['category']}."}
            for r, s in zip(rubric, [4, 3, 4, 5])
        ]})

    prompt = build_prompt(solicitation, proposal, rubric)
    review_data = call_ollama(prompt)

    returned = sorted(r.get("category") for r in review_data.get("reviews", []))
    expected = sorted(r["category"] for r in rubric)
    if returned != expected:
        print(f"WARNING: model output does not match the rubric. expected={expected} got={returned}")

    return to_frontend(review_data)