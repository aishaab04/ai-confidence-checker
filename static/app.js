// ── STATE ────────────────────────────────────────────────────
let questions     = [];
let currentQuestion = null;
let activeTopicFilter = null;
let latestAI      = { finalAnswer: null, confidence: null, explanation: null, steps: null };
let sessionStats  = { total: 0, wrong: 0, halluc: 0, confSum: 0 };
let topicMap      = {};   // { topic: { total, wrong } }
let sessionLog    = [];

// ── ELEMENTS ─────────────────────────────────────────────────
const els = {
  questionSelect:   document.getElementById("questionSelect"),
  generateBtn:      document.getElementById("generateBtn"),
  quickBtn:         document.getElementById("quickBtn"),
  checkBtn:         document.getElementById("checkBtn"),
  nextBtn:          document.getElementById("nextBtn"),
  promptText:       document.getElementById("promptText"),
  topicIndicator:   document.getElementById("topicIndicator"),
  topicFilter:      document.getElementById("topicFilter"),

  // answer card
  aiAnswer:         document.getElementById("aiAnswer"),
  explanationWrap:  document.getElementById("explanationWrap"),
  explanation:      document.getElementById("explanation"),
  stepsWrap:        document.getElementById("stepsWrap"),
  stepsList:        document.getElementById("stepsList"),
  confidenceWrap:   document.getElementById("confidenceWrap"),
  confidenceValue:  document.getElementById("confidenceValue"),
  confidenceBar:    document.getElementById("confidenceBar"),
  confidenceWarning:document.getElementById("confidenceWarning"),

  // result card
  resultCard:         document.getElementById("resultCard"),
  verdict:            document.getElementById("verdict"),
  resultExplanation:  document.getElementById("resultExplanation"),
  hallucinationAlert: document.getElementById("hallucinationAlert"),
  hallucinationMsg:   document.getElementById("hallucinationMsg"),
  correctAnswerBlock: document.getElementById("correctAnswerBlock"),
  correctAnswerValue: document.getElementById("correctAnswerValue"),

  // sidebar
  statTotal:    document.getElementById("statTotal"),
  statWrong:    document.getElementById("statWrong"),
  statHalluc:   document.getElementById("statHalluc"),
  statAvgConf:  document.getElementById("statAvgConf"),
  topicChart:   document.getElementById("topicChart"),
  sessionLog:   document.getElementById("sessionLog"),
};

// ── INIT ─────────────────────────────────────────────────────
async function loadQuestions() {
  const res = await fetch("/questions");
  questions = await res.json();

  // build topic filter pills
  const topics = [...new Set(questions.map(q => q.topic))];
  els.topicFilter.innerHTML = topics.map(t =>
    `<button class="topic-pill" data-topic="${t}" onclick="filterTopic('${t}', this)">${t.replace(/_/g,' ')}</button>`
  ).join('');

  populateSelect(questions);
  if (questions.length > 0) setQuestionById(questions[0].id);
}

function populateSelect(list) {
  els.questionSelect.innerHTML = list.map(q =>
    `<option value="${q.id}">${q.label || q.prompt.slice(0, 60)}</option>`
  ).join('');
  if (list.length > 0) setQuestionById(list[0].id);
}

function filterTopic(topic, btn) {
  if (activeTopicFilter === topic) {
    // toggle off
    activeTopicFilter = null;
    document.querySelectorAll('.topic-pill').forEach(p => p.classList.remove('active'));
    populateSelect(questions);
  } else {
    activeTopicFilter = topic;
    document.querySelectorAll('.topic-pill').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const filtered = questions.filter(q => q.topic === topic);
    populateSelect(filtered);
  }
}

function setQuestionById(id) {
  currentQuestion = questions.find(q => q.id === id) || null;
  resetRoundUI();
  if (currentQuestion) {
    els.promptText.textContent = currentQuestion.prompt;
    els.topicIndicator.textContent = currentQuestion.topic?.replace(/_/g,' ') || 'Unknown topic';
  }
}

// ── RESET ─────────────────────────────────────────────────────
function resetRoundUI() {
  latestAI = { finalAnswer: null, confidence: null, explanation: null, steps: null };

  // answer card
  els.aiAnswer.innerHTML = `
    <div class="answer-placeholder">
      <div class="placeholder-icon">◎</div>
      <div class="placeholder-text">Click "Generate AI Answer" to see how the AI responds</div>
    </div>`;
  els.aiAnswer.className = 'answer-main';

  els.explanationWrap.classList.add('hidden');
  els.explanation.textContent = '';
  els.stepsWrap.classList.add('hidden');
  els.stepsList.innerHTML = '';
  els.confidenceWrap.classList.add('hidden');
  els.confidenceValue.textContent = '—%';
  els.confidenceBar.style.width = '0%';
  els.confidenceWarning.classList.add('hidden');

  // result card
  els.resultCard.classList.add('hidden');
  els.verdict.textContent = '—';
  els.verdict.className = 'verdict';
  els.resultExplanation.textContent = '';
  els.hallucinationAlert.classList.add('hidden');
  els.correctAnswerBlock.classList.add('hidden');

  els.checkBtn.disabled = true;
  els.nextBtn.disabled = true;
}

// ── GENERATE ──────────────────────────────────────────────────
async function generateAI() {
  if (!currentQuestion) return;
  resetRoundUI();

  els.generateBtn.disabled = true;
  els.aiAnswer.className = 'answer-main generating';
  els.aiAnswer.innerHTML = `<div class="spinner"></div> Generating AI answer...`;

  try {
    const res = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: currentQuestion.id })
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    latestAI.finalAnswer  = data.finalAnswer;
    latestAI.explanation  = data.explanation;
    latestAI.confidence   = data.confidence;
    latestAI.steps        = data.steps || null;
    latestAI.steps_raw    = data.steps_raw || "";  // ← add this line

    // render answer
    els.aiAnswer.className = 'answer-main';
    els.aiAnswer.textContent = latestAI.finalAnswer ?? '—';

    // render explanation
    if (latestAI.explanation) {
      els.explanation.textContent = latestAI.explanation;
      els.explanationWrap.classList.remove('hidden');
    }

    // render steps if backend returns them
    if (latestAI.steps && latestAI.steps.length > 0) {
      renderSteps(latestAI.steps);
    }

    // reveal confidence
    revealConfidence();

    els.checkBtn.disabled = false;

  } catch (err) {
    els.aiAnswer.className = 'answer-main';
    els.aiAnswer.textContent = 'Error generating answer.';
    console.error(err);
  } finally {
    els.generateBtn.disabled = false;
  }
}

async function quickAnswer() {
    if (!currentQuestion) return;
    resetRoundUI();

    els.quickBtn.disabled = true;
    els.aiAnswer.className = 'answer-main generating';
    els.aiAnswer.innerHTML = `<div class="spinner"></div> Getting answer...`;

    try {
        const res = await fetch("/quick", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question_id: currentQuestion.id })
        });

        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();

        latestAI.finalAnswer = data.finalAnswer;
        latestAI.confidence  = data.confidence;

        // show answer only — no steps, no explanation
        els.aiAnswer.className  = 'answer-main';
        els.aiAnswer.textContent = latestAI.finalAnswer ?? "—";

        // show confidence
        revealConfidence();

        // enable check — student can now verify
        els.checkBtn.disabled = false;

    } catch (err) {
        els.aiAnswer.className  = 'answer-main';
        els.aiAnswer.textContent = 'Error getting answer.';
        console.error(err);
    } finally {
        els.quickBtn.disabled = false;
    }
}

// ── RENDER STEPS ──────────────────────────────────────────────
function renderSteps(steps, verified = false) {
  els.stepsList.innerHTML = steps.map((step, i) => {

    // only show color and badge if verified is true
    const cls = verified
      ? (step.verdict === 'correct' ? 'correct' : step.verdict === 'wrong' ? 'wrong' : '')
      : '';

    const badgeCls = verified
      ? (step.verdict === 'correct' ? 'badge-correct' : step.verdict === 'wrong' ? 'badge-wrong' : 'badge-unverified')
      : 'badge-unverified';

    const badgeTxt = verified
      ? (step.verdict === 'correct' ? '✓ Correct' : step.verdict === 'wrong' ? '✗ Error' : '— Unverified')
      : '—';

    return `
    <div class="step-item ${cls}" style="animation-delay:${i*60}ms">
      <div class="step-header">
        <span class="step-num-label">${step.number === 'final' ? 'Final Answer' : `Step ${step.number}`}</span>
        <span class="step-badge ${badgeCls}">${badgeTxt}</span>
      </div>
      ${step.description ? `<div class="step-desc">${step.description}</div>` : ''}
      ${step.calculation ? `<div class="step-calc">${step.calculation}</div>` : ''}
      ${verified && step.verdict === 'wrong' && step.error
        ? `<div class="step-error-msg">${step.error}</div>`
        : ''}
    </div>`;
  }).join('');
  els.stepsWrap.classList.remove('hidden');
}

// ── CONFIDENCE ────────────────────────────────────────────────
function revealConfidence() {
  const c = Number(latestAI.confidence);
  if (!Number.isFinite(c)) return;

  els.confidenceWrap.classList.remove('hidden');
  els.confidenceValue.textContent = `${c}%`;
  els.confidenceBar.style.width = `${Math.max(0, Math.min(100, c))}%`;

  // color the number
  if (c >= 75) {
    els.confidenceValue.style.color = 'var(--red)';
    els.confidenceWarning.classList.remove('hidden');
  } else if (c >= 50) {
    els.confidenceValue.style.color = 'var(--amber)';
  } else {
    els.confidenceValue.style.color = 'var(--green)';
  }
}

// ── CHECK ─────────────────────────────────────────────────────
async function checkAnswer() {
  if (!currentQuestion || !latestAI.finalAnswer) return;

  els.checkBtn.disabled = true;
  els.resultCard.classList.remove('hidden');
  els.verdict.textContent = 'Checking...';
  els.verdict.className = 'verdict unknown';

  try {
    const res = await fetch("/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_id: currentQuestion.id,
        finalAnswer: latestAI.finalAnswer,
        stepsRaw:    latestAI.steps_raw || "",
        confidence:   latestAI.confidence || 0 
      })
    });

    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();  // ← was: const isCorrect = await res.json()

    const isCorrect       = data.is_correct;  // ← unwrap from object
    const confidence      = Number(latestAI.confidence);
    const isHallucination = !isCorrect && confidence >= 75;

    // verdict
    if (isCorrect) {
      els.verdict.textContent = '✅ Correct';
      els.verdict.className = 'verdict correct';
    } else {
      els.verdict.textContent = '❌ Incorrect';
      els.verdict.className = 'verdict incorrect';
    }

    // re-render steps with colors now that check is done
    if (data.steps && data.steps.length > 0) {
      renderSteps(data.steps, true);  // ← true = show badges and colors
    }

    // show first error location
    if (data.first_error) {
      els.resultExplanation.textContent = 
        `Error found at Step ${data.first_error.number}: ${data.first_error.error}`;
    }

    // hallucination alert
    if (isHallucination) {
      els.hallucinationMsg.textContent = ` The AI said ${confidence}% confident but got it wrong. This is the hallucination danger zone.`;
      els.hallucinationAlert.classList.remove('hidden');
    }

    // show correct answer if wrong
    if (!isCorrect && currentQuestion.answer !== undefined) {
      els.correctAnswerValue.textContent = String(currentQuestion.answer);
      els.correctAnswerBlock.classList.remove('hidden');
    }

    // update stats
    updateStats(isCorrect, confidence, isHallucination);
    addToLog(isCorrect, confidence);

    els.nextBtn.disabled = false;

  } catch (err) {
    els.verdict.textContent = 'Error checking answer.';
    els.resultExplanation.textContent = String(err);
    els.checkBtn.disabled = false;
  }
}


// ── STATS ─────────────────────────────────────────────────────
function updateStats(isCorrect, confidence, isHallucination) {
  sessionStats.total++;
  sessionStats.confSum += confidence;
  if (!isCorrect) sessionStats.wrong++;
  if (isHallucination) sessionStats.halluc++;

  const topic = currentQuestion?.topic || 'unknown';
  if (!topicMap[topic]) topicMap[topic] = { total: 0, wrong: 0 };
  topicMap[topic].total++;
  if (!isCorrect) topicMap[topic].wrong++;

  els.statTotal.textContent  = sessionStats.total;
  els.statWrong.textContent  = sessionStats.wrong;
  els.statHalluc.textContent = sessionStats.halluc;
  els.statAvgConf.textContent = sessionStats.total > 0
    ? Math.round(sessionStats.confSum / sessionStats.total) + '%'
    : '—';

  renderTopicChart();
}

function renderTopicChart() {
  if (Object.keys(topicMap).length === 0) {
    els.topicChart.innerHTML = '<div class="chart-empty">Ask some questions to see patterns</div>';
    return;
  }
  els.topicChart.innerHTML = Object.entries(topicMap).map(([topic, d]) => {
    const pct = Math.round((d.wrong / d.total) * 100);
    return `<div class="topic-bar-row">
      <span class="topic-bar-label">${topic.replace(/_/g,' ')}</span>
      <div class="topic-bar-track"><div class="topic-bar-fill" style="width:${pct}%"></div></div>
      <span class="topic-bar-pct">${pct}%</span>
    </div>`;
  }).join('');
}

// ── LOG ───────────────────────────────────────────────────────
function addToLog(isCorrect, confidence) {
  sessionLog.unshift({
    topic: currentQuestion?.topic || 'unknown',
    prompt: currentQuestion?.prompt || '',
    confidence,
    correct: isCorrect,
  });

  els.sessionLog.innerHTML = sessionLog.slice(0, 8).map(entry => `
    <div class="log-item">
      <span class="log-topic">${entry.topic.replace(/_/g,' ')}</span>
      <span class="log-q">${entry.prompt.slice(0, 40)}...</span>
      <span class="log-conf">${entry.confidence}%</span>
      <span class="log-verdict ${entry.correct ? 'lv-correct' : 'lv-incorrect'}">${entry.correct ? '✓' : '✗'}</span>
    </div>
  `).join('');
}

// ── NEXT ──────────────────────────────────────────────────────
function nextQuestion() {
  const list = activeTopicFilter
    ? questions.filter(q => q.topic === activeTopicFilter)
    : questions;
  if (!list.length) return;
  const idx = list.findIndex(q => q.id === currentQuestion?.id);
  const next = list[(idx + 1) % list.length];
  els.questionSelect.value = next.id;
  setQuestionById(next.id);
}

// ── EVENTS ────────────────────────────────────────────────────
els.questionSelect.addEventListener("change", e => setQuestionById(e.target.value));
els.generateBtn.addEventListener("click", generateAI);
els.checkBtn.addEventListener("click", checkAnswer);
els.nextBtn.addEventListener("click", nextQuestion);
els.quickBtn.addEventListener("click", quickAnswer);

// ── START ─────────────────────────────────────────────────────
loadQuestions();
