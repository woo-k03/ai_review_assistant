import json
import sys
from pathlib import Path

import requests

ollama_URL = 'http://localhost:11434/api/chat'
model_name = 'llama3.1'

solicitation_file = 'solicitation.txt'
proposal_file = 'proposal.txt'
output_file = 'review.txt'

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

#######################################


def read_text_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"Input file does not exist: {path}")
        sys.exit(1)
    return p.read_text(encoding='utf-8').strip()


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

Respond with only valid JSON, no other text, in exactly this shape:
{{
    "reviews": [
    {{"category": "<category name>", "score": <1-5 integer>, "comment": "<comment>"}},
    ...
    ]
}}
"""


def call_ollama(prompt: str) -> dict:
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }

    try:
        resp = requests.post(ollama_URL, json=payload, timeout=180)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("ERROR: could not reach Ollama at http://localhost:11434")
        print("Is Ollama running? Try: ollama serve")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: Ollama returned an HTTP error: {e}")
        sys.exit(1)

    data = resp.json()
    raw_content = data.get("message", {}).get("content", "")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        print("WARNING: model did not return valid JSON. Raw output was:")
        print(raw_content)
        sys.exit(1)


def print_report(review_data: dict) -> None:
    print("\n=== AI Review Summary ===\n")
    for item in review_data.get("reviews", []):
        category = item.get("category", "Unknown category")
        score = item.get("score", "?")
        comment = item.get("comment", "")
        print(f"[{score}/5] {category}")
        print(f"    {comment}\n")


def main() -> None:
    solicitation = read_text_file(solicitation_file)
    proposal = read_text_file(proposal_file)

    prompt = build_prompt(solicitation, proposal, rubric)

    print(f"Sending review request to Ollama ({model_name})...")
    review_data = call_ollama(prompt)

    print_report(review_data)

    Path(output_file).write_text(json.dumps(review_data, indent=2), encoding="utf-8")
    print(f"Saved raw output to {output_file}")


if __name__ == "__main__":
    main()