# CAPTURED — AI Confidence Checker

> A classroom tool that exposes AI hallucinations in math problems by measuring confidence against correctness.

Built by a middle school math teacher to help students interact with AI critically — not just accept answers at face value.

---

## What it does

Students select a math problem, ask the AI to solve it, and then verify whether the AI was right. The system tracks how confident the AI claimed to be versus how often it was actually correct — exposing the hallucination danger zone where high confidence meets wrong answers.

Three verification layers run independently:

- **Answer check** — compares AI final answer against known correct answer from `questions.json`
- **Step verification** — sends each reasoning step to Wolfram Alpha to check mathematical validity
- **Confidence detection** — flags cases where AI confidence ≥ 75% but answer is wrong

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI |
| AI model | OpenAI GPT-4o-mini |
| Math verification | Wolfram Alpha Full Results API |
| Frontend | Vanilla JavaScript + HTML + CSS |
| Data persistence | JSON file (`session_results.json`) |
| Fonts | Syne, JetBrains Mono, Instrument Serif |

---

## Project structure

```
confidenceChek/
├── confidence.py          # FastAPI backend — all routes and logic
├── questions.json         # 45 curated math problems across 9 topics
├── session_results.json   # auto-generated — persists all check results
├── templates/
│   ├── index.html         # student interface
│   └── teacher.html       # teacher dashboard
└── static/
    ├── app.js             # frontend logic
    └── style.css          # styling
```

---

## Setup

### 1. Install dependencies

```bash
pip install fastapi uvicorn openai python-dotenv
```

### 2. Set up environment variables

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-proj-your-key-here
WOLFRAM_APP_ID=your-wolfram-app-id-here
```

Get your keys:
- OpenAI: [platform.openai.com](https://platform.openai.com) → API Keys
- Wolfram: [developer.wolframalpha.com](https://developer.wolframalpha.com) → Get an AppID → Full Results API

### 3. Run the server

```bash
uvicorn confidence:app --reload
```

### 4. Open in browser

- **Student view:** `http://localhost:8000`
- **Teacher dashboard:** `http://localhost:8000/teacher`

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Student interface |
| `GET` | `/teacher` | Teacher dashboard |
| `GET` | `/questions` | Returns all questions as JSON |
| `POST` | `/quick` | AI answers with no reasoning shown |
| `POST` | `/generate` | AI answers with full step-by-step reasoning |
| `POST` | `/check` | Verifies answer + runs Wolfram step verification |
| `GET` | `/results` | Returns all saved session results |
| `GET` | `/results/stats` | Returns aggregated stats by topic |

---

## How a question flows through the system

```
Student clicks "Generate with Steps"
    → POST /generate
    → GPT-4o-mini solves problem in STEP/CALCULATION format
    → parse_steps() converts text to structured step objects
    → steps returned to frontend (no colors yet)

Student clicks "Check Answer"
    → POST /check
    → check_answer() compares final answer to questions.json
    → verify_steps_with_wolfram() sends each CALCULATION to Wolfram
    → context tracking catches wrong values carried forward
    → hallucination flag set if confidence ≥ 75% AND wrong
    → result saved to session_results.json
    → steps re-rendered with green/red badges
    → verdict + hallucination alert shown
```

---

## Question bank

45 problems across 9 topics, designed to expose known AI weaknesses:

| Topic | Count | Why included |
|-------|-------|-------------|
| `systems_of_equations` | 6 | Multi-variable answers, substitution errors |
| `word_problems` | 8 | Variable assignment confusion, unit errors |
| `llm_traps` | 10 | Classic high-confidence wrong answer cases |
| `quadratics` | 5 | Complex roots, vertex form, discriminant |
| `probability` | 4 | Bayes theorem, conditional probability |
| `exponents` | 3 | Negative fractional exponents, growth |
| `geometry` | 3 | Scaling traps, area vs radius |
| `algebra` | 3 | Rational equations, absolute value, composition |
| `statistics` | 2 | Mean vs median, standard deviation |
| `precalculus` | 2 | Limits, arithmetic sequences |

The `llm_traps` category is the academic core — problems specifically chosen because LLMs answer with high confidence but low accuracy. Includes Monty Hall, harmonic mean speed, Bayes theorem, compound interest, and infinite series.

---

## Adding new questions

Edit `questions.json`. Each question requires:

```json
{
  "id": "unique_id",
  "label": "Short display name",
  "prompt": "The full question text sent to GPT. Tell it what format to return the answer in.",
  "answer": "The correct answer in the exact format GPT will return",
  "topic": "one_of_the_topic_slugs",
  "wolfram_query": "A query string for Wolfram Alpha to verify steps"
}
```

**Answer format guidelines:**
- Single number: `"48"`
- Variable pairs: `"x=3, y=2"` — no spaces around `=`
- Multiple numbers: `"69, 2"` — comma separated, no units
- Text answers: `"no solution"` — lowercase
- Fractions: `"2/15"`

---

## Teacher dashboard

Visit `http://localhost:8000/teacher` to see:

- **Metrics** — total checks, error count, hallucination count, average confidence
- **Method comparison** — Quick Answer vs Generate with Steps error rates
- **Error rate by topic** — which topics the AI fails most
- **Confidence vs correctness matrix** — the 2×2 hallucination visualization
- **Average confidence by topic** — where the AI is most overconfident
- **Results log** — last 30 checks with full detail
- **CSV export** — download all results for analysis

The dashboard reads from `session_results.json` and auto-refreshes every 30 seconds.

---

## Key concepts

**Hallucination danger zone** — when the AI reports high confidence (≥75%) but gets the answer wrong. This is the central finding the tool is designed to demonstrate.

**Method comparison** — Quick Answer (no reasoning) vs Generate with Steps. The hypothesis is that generating reasoning reduces errors because the model has to commit to intermediate steps.

**Step verification** — each `CALCULATION` line in the AI's reasoning is sent to Wolfram Alpha with the original problem as context, not in isolation. This catches errors that look locally correct but violate the problem constraints.

**Context tracking** — as steps are verified, established variable values are stored. If a later step uses a contradicting value, it's flagged immediately without an API call.

---

## Project methodology

Follows the Abello DIVA-CS526 project design framework (Rutgers University):

1. Data — `questions.json` as curated dataset
2. Questions — measuring confidence vs correctness
3. Mode of processing — FastAPI pipeline with three verification layers
4. Visual representation — confidence bar, step cards, scatter plot, 2×2 matrix
5. Interactivity — three-button flow, topic filters, real-time tracker
6. Analytics — teacher dashboard with persistent aggregated results
7. Development documentation — see tech stack above
8. Acknowledgements — James Abello (methodology), Rutgers MSCS

---

## Known limitations

- Wolfram step verification returns `unverified` for complex multi-variable expressions
- Step verification only runs when Generate with Steps is used, not Quick Answer
- `session_results.json` is a flat file — not suitable for large-scale multi-classroom deployment
- No student authentication — results are not tied to individual students across sessions

---

## License

Open for classroom use and adaptation by educators.