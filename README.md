# ai_review_assistant
A local web app that scores a research proposal against a funding solicitation using a rubric and returns a 1-5 grade with a comment per category.

## How it works:

1. A reviewer uploads a solicitation and a proposal.
2. The app extracts the text (pypdf)
3. The text and the rubric are sent to a local LLM (Ollama, llama3.1 8B)
4. The model scores four rubric categoreis from 1 to 5 with a short comment each.
5. The overall grade is the aveage of the category scoers.
6. Results are saved in a local SQLite database and shown in a review history.


## Rubric Categories:
- Strengths / Weaknesses vs. Program Objectives
- Innovation and Advancement of Agency Needs
- Quality of the Written Proposal
- Investigator / Team Capability 