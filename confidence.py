from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv
import json
import re
import os
import urllib.request
import urllib.parse

load_dotenv()

last_method_used = "none" 
# ── MODELS ───────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    question_id: str

class GenerateRequest_Answer(BaseModel):
    question_id: str
    finalAnswer: str
    stepsRaw : str =""
    confidence:  int = 0   

# ── APP SETUP ────────────────────────────────────────────────
app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

with open(BASE_DIR / "questions.json", "r", encoding="utf-8") as f:
    QUESTIONS_LIST = json.load(f)

QUESTIONS = {q["id"]: q for q in QUESTIONS_LIST}
print(f"Loaded {len(QUESTIONS_LIST)} questions across {len(set(q['topic'] for q in QUESTIONS_LIST))} topics")


# ── Result Saving───────────────────────────────────────────────────
RESULTS_FILE = BASE_DIR / "session_results.json"

def load_results():
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_result(entry: dict):
    results = load_results()
    results.append(entry)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
WOLFRAM_APP_ID = os.getenv("WOLFRAM_APP_ID")
# ── ROUTES ───────────────────────────────────────────────────
@app.get("/")
def read_root():
    return FileResponse(BASE_DIR / "templates" / "index.html")

@app.get("/questions")
def get_questions():
    return QUESTIONS_LIST

@app.post("/generate")
def generate(request: GenerateRequest):
    last_method_used = "explain"
    q = QUESTIONS.get(request.question_id)
    print(f"Received question_id: {request.question_id}")
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    result = generate_answer(q["prompt"])
    steps  = parse_steps(result.get("steps_raw", ""))

    # extract final answer from last step so it matches the reasoning
    final_answer = result.get("finalAnswer")
    final_step = next((s for s in steps if s.get("number") == "final"), None)
    if final_step and final_step.get("calculation"):
        final_answer = final_step["calculation"]

    return {
        "question_id":    q,
        "finalAnswer":    final_answer,
        "explanation":    result.get("explanation"),
        "confidence":     result.get("confidence"),
        "steps_raw":      result.get("steps_raw", ""),
        "steps":          steps,
        "first_error":    None,
        "wolfram_answer": None,
    }

@app.post("/quick")
def generate_quick(request: GenerateRequest):
     last_method_used = "quick"
     q = QUESTIONS.get(request.question_id)
     if not q:
        raise HTTPException(status_code=404, detail="Question not found")
     result = generate_quick_answer(q["prompt"])
     return {
        "finalAnswer": result.get("finalAnswer"),
        "confidence":  result.get("confidence"),
    }


@app.post("/check")
def check(request: GenerateRequest_Answer):
    q = QUESTIONS.get(request.question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    
    print(f"stepsRaw length: {len(request.stepsRaw)}")  # ← add this
    print(f"stepsRaw preview: {request.stepsRaw[:100]}")  # ← add this
    correct_answer = q["answer"]
    print(f"Correct: {correct_answer} | AI said: {request.finalAnswer}")
    is_correct = check_answer(request.finalAnswer, correct_answer)
    print(f"Result: {is_correct}")

    # re-verify steps with Wolfram using stepsRaw sent from frontend
    steps = []
    if request.stepsRaw:
        steps = parse_steps(request.stepsRaw)
        if WOLFRAM_APP_ID:
            steps = verify_steps_with_wolfram(steps, problem_context=q.get("wolfram_query", ""))

    first_error = next((s for s in steps if s.get("verdict") == "wrong"), None)

    save_result({
    "question_id":   request.question_id,
    "topic":         q.get("topic"),
    "prompt":        q.get("prompt"),
    "ai_answer":     request.finalAnswer,
    "correct":       is_correct,
    "confidence":    request.confidence,
    "flagged":       not is_correct and request.confidence >= 75,
    "method_used":   last_method_used,
    "first_error":   first_error,
    "timestamp":     __import__("datetime").datetime.now().isoformat(),
})
    return {
        "is_correct":  is_correct,
        "steps":       steps,
        "first_error": first_error,
    }


@app.get("/results")
def get_results():
    return load_results()

@app.get("/results/stats")
def get_stats():
    results = load_results()
    if not results:
        return {"total": 0, "wrong": 0, "hallucination_rate": 0, "by_topic": {}}

    total  = len(results)
    wrong  = sum(1 for r in results if not r["correct"])
    by_topic = {}

    for r in results:
        t = r.get("topic", "unknown")
        if t not in by_topic:
            by_topic[t] = {"total": 0, "wrong": 0}
        by_topic[t]["total"] += 1
        if not r["correct"]:
            by_topic[t]["wrong"] += 1

    return {
        "total":   total,
        "wrong":   wrong,
        "error_rate": round(wrong / total * 100, 1),
        "by_topic": by_topic,
    }

@app.get("/teacher")
def teacher_dashboard():
    return FileResponse(BASE_DIR / "templates" / "teacher.html")

# ── LLM CALL ─────────────────────────────────────────────────
def generate_answer(prompt: str):
    schema = {
        "name": "MathAnswer",
        "type": "json_schema",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["finalAnswer", "explanation", "confidence", "steps_raw"],
            "properties": {
                "explanation": {"type": "string"},
                "confidence":  {"type": "integer", "minimum": 0, "maximum": 100},
                "steps_raw":   {"type": "string"},
                "finalAnswer": {"type": "string"}
            },
        },
        "strict": True,
    }

    system_prompt = """You are a math solver. Solve the problem step by step.

For the steps_raw field, format EXACTLY like this:

STEP 1: [describe the operation]
CALCULATION 1: [exact math expression for this step]
STEP 2: [describe the operation]
CALCULATION 2: [exact math expression]
...continue...
FINAL ANSWER: [just the answer value]

Rules:
- Every STEP must have a matching CALCULATION
- Use plain text math only — no LaTeX, no backslashes
- For single variable answers, return just the number e.g. "4" or "x=3"
- For multi-variable answers, return ALL variables in the format "x=3, y=2" or "x=1, y=2, z=3"
- Never return just one variable when the problem asks for multiple unknowns
- Never include words like "and" or "the solution is" in finalAnswer — just the values
- Be honest about confidence — lower it for tricky problems
- You MUST put each STEP, CALCULATION, and FINAL ANSWER on its own separate line
- Never write STEP and CALCULATION on the same line
- Never run steps together without a line break between them
- Never end finalAnswer with a period, comma, or any punctuation
"""

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        text={"format": schema},
    )

    return json.loads(resp.output_text)

def generate_quick_answer(prompt: str):
    schema = {
        "name": "QuickAnswer",
        "type": "json_schema",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["finalAnswer", "confidence"],
            "properties": {
                "finalAnswer": {"type": "string"},
                "confidence":  {"type": "integer", "minimum": 0, "maximum": 100},
            },
        },
        "strict": True,
    }

    system_prompt = """You are a math solver. Answer the question directly.

Rules:
- Return only the final answer — no steps, no explanation, no reasoning
- For single variable answers, return just the number e.g. "4" or "x=3"
- For multi-variable answers, return ALL variables in the format "x=3, y=2"
- Never include words like "and" or "the solution is" — just the values
- Never end finalAnswer with a period, comma, or any punctuation
- Be honest about confidence — lower it for tricky problems"""

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        text={"format": schema},
    )
    return json.loads(resp.output_text) 

# ── STEP PARSING ─────────────────────────────────────────────
def parse_steps(steps_raw: str) -> list:
    if not steps_raw:
        return []

    steps = []
    current_step = None
    lines = [l.strip() for l in steps_raw.split("\n") if l.strip()]

    for line in lines:
        step_match  = re.match(r"^STEP\s+(\d+):\s*(.+)", line, re.IGNORECASE)
        calc_match  = re.match(r"^CALCULATION\s+(\d+):\s*(.+)", line, re.IGNORECASE)
        final_match = re.match(r"^FINAL ANSWER:\s*(.+)", line, re.IGNORECASE)

        if step_match:
            current_step = {
                "number":        int(step_match.group(1)),
                "description":   step_match.group(2),
                "calculation":   None,
                "verdict":       None,
                "wolfram_result": None,
                "error":         None,
            }
            steps.append(current_step)
        elif calc_match and current_step:
            current_step["calculation"] = calc_match.group(2)
        elif final_match:
            steps.append({
                "number":        "final",
                "description":   "Final Answer",
                "calculation":   final_match.group(1),
                "verdict":       None,
                "wolfram_result": None,
                "error":         None,
            })

    return steps

# ── WOLFRAM ───────────────────────────────────────────────────
def wolfram_query(query: str):
    if not query or not WOLFRAM_APP_ID:
        return None
    try:
        encoded = urllib.parse.quote(query)
        url = (f"http://api.wolframalpha.com/v2/query"
               f"?appid={WOLFRAM_APP_ID}&input={encoded}&output=JSON&format=plaintext")
        with urllib.request.urlopen(url, timeout=10) as res:
            data = json.loads(res.read().decode())

        if not data.get("queryresult", {}).get("success"):
            return None

        pods = data["queryresult"].get("pods", [])
        for title in ["Result", "Solution", "Solutions", "Exact result", "Value"]:
            pod = next((p for p in pods if p.get("title") == title), None)
            if pod:
                texts = [s["plaintext"] for s in pod.get("subpods", []) if s.get("plaintext")]
                if texts:
                    return ", ".join(texts)

        for pod in pods:
            if pod.get("title") == "Input":
                continue
            texts = [s["plaintext"] for s in pod.get("subpods", []) if s.get("plaintext")]
            if texts:
                return texts[0]

        return None
    except Exception as e:
        print(f"Wolfram error: {e}")
        return None

def find_step_that_set(steps: list, var: str) -> str:
    """Find which step number first established a variable's value."""
    for step in steps:
        calc = step.get("calculation", "") or ""
        # match any calc that starts with "x =" or contains "x = number" at the end
        patterns = [
            rf'^{var}\s*=\s*(-?\d+\.?\d*)\s*$',           # "n = 18"
            rf'→\s*{var}\s*=\s*(-?\d+\.?\d*)\s*$',        # "... → n = 18"
            rf'.*{var}\s*=\s*(-?\d+\.?\d*)\s*$',           # anything ending in "n = 18"
        ]
        for pattern in patterns:
            if re.match(pattern, calc.lower().strip()):
                return str(step.get("number", "?"))
    return "?"


def verify_steps_with_wolfram(steps: list, problem_context: str = "") -> list:
    context = {}

    for step in steps:
        calc = step.get("calculation")
        if not calc or step.get("number") == "final":
            continue

        # ── 1. CHECK AGAINST CONTEXT ──────────────────────────────
        # only match standalone assignments like "n = 18" not "0.10n" or "d = 30 - n"
        # requires: space/start before variable, pure number after =, nothing after
        used_pairs = re.findall(
            r'(?<![0-9a-z\.])([a-z])\s*=\s*(-?\d+\.?\d*)\s*(?![\+\-\*\/a-z])',
            calc.lower()
        )

        contradiction_found = False
        for var, val in used_pairs:
            val = float(val)
            if var in context:
                if abs(context[var] - val) > 1e-4:
                    step["verdict"] = "wrong"
                    step["wolfram_result"] = f"{var} should be {context[var]}"
                    step["error"] = (
                        f'This step used {var}={val} but '
                        f'Step {find_step_that_set(steps, var)} '
                        f'established {var}={context[var]}. '
                        f'The wrong value was carried forward.'
                    )
                    contradiction_found = True
                    break

        if not contradiction_found:
            # ── 2. BUILD PROBLEM-AWARE QUERY ──────────────────────
            if problem_context:
                query = f"given {problem_context}, is it correct that {calc}?"
            else:
                query = f"simplify {calc}"

            wolfram_result = wolfram_query(query) or wolfram_query(f"simplify {calc}")
            step["wolfram_result"] = wolfram_result

            if wolfram_result is None:
                step["verdict"] = "unverified"
            else:
                verdict = compare_calc_to_wolfram(calc, wolfram_result)
                step["verdict"] = verdict

                if verdict == "wrong":
                    step["error"] = (
                        f'Wolfram evaluated this as: "{wolfram_result}". '
                        f'This step may contain an error — check the calculation carefully.'
                    )

        # ── 3. UPDATE CONTEXT ─────────────────────────────────────
        # only store variable if entire calculation is JUST "x = 3" — nothing else
        if step.get("verdict") != "wrong":
            simple_assignment = re.match(
                r'^([a-z])\s*=\s*(-?\d+\.?\d*)\s*$',
                calc.lower().strip()
            )
            if simple_assignment:
                var  = simple_assignment.group(1)
                val  = float(simple_assignment.group(2))
                context[var] = val

    return steps

def compare_calc_to_wolfram(ai_calc: str, wolfram_result: str) -> str:
    def normalize(s):
        return re.sub(r'[\s*×,=]', '', s.lower())

    ai_norm = normalize(ai_calc)
    wf_norm = normalize(wolfram_result)

    if wf_norm in ai_norm or ai_norm in wf_norm:
        return "correct"

    ai_nums = set(re.findall(r'-?\d+\.?\d*', ai_calc))
    wf_nums = set(re.findall(r'-?\d+\.?\d*', wolfram_result))

    if ai_nums and wf_nums:
        overlap = ai_nums & wf_nums
        if len(overlap) >= min(len(ai_nums), len(wf_nums)):
            return "correct"
        if wf_nums and not (wf_nums & ai_nums):
            return "wrong"

    return "unverified"

# ── ANSWER CHECK ──────────────────────────────────────────────
def check_answer(user_answer: str, correct_answer) -> bool:
    # try numeric comparison first
    try:
        user_num    = float(str(user_answer).replace(",", "").strip())
        correct_num = float(str(correct_answer).replace(",", "").strip())
        return abs(user_num - correct_num) < 1e-4
    except ValueError:
        pass

    def norm(s):
        return str(s).lower().strip().replace(" ", "").replace(",", "")

    u = norm(user_answer)
    c = norm(correct_answer)

    if u == c:
        return True

    # extract variable=value pairs from both strings
    # handles "x=3, y=2" and "x = 3 and y = 2" and "y=2, x=3"
    def extract_pairs(s):
        pairs = re.findall(r'([a-z])\s*=\s*(-?\d+\.?\d*)', s.lower())
        return {k: float(v) for k, v in pairs}

    user_pairs    = extract_pairs(str(user_answer))
    correct_pairs = extract_pairs(str(correct_answer))

    # if correct answer has variable pairs, check each one individually
    if correct_pairs:
        if not user_pairs:
            return False
        return all(
            abs(user_pairs.get(k, float('inf')) - v) < 1e-4
            for k, v in correct_pairs.items()
        )

    # fallback: partial token match for text answers
    tokens = c.split()
    if len(tokens) > 1:
        return sum(1 for t in tokens if t in u) >= len(tokens) * 0.8

    return False