const stages = [
  { name: "NORMALIZATION", duration: "3 ms", input: "09d2a1c4", output: "71f04bd2" },
  { name: "HISTORY", duration: "8 ms", input: "71f04bd2", output: "b2074d9a" },
  { name: "REWRITE", duration: "284 ms", input: "b2074d9a", output: "63c9c154" },
  { name: "INTENT", duration: "41 ms", input: "63c9c154", output: "0dd91ca8" },
  { name: "RETRIEVAL", duration: "337 ms", input: "0dd91ca8", output: "7a19e2cd" },
  { name: "RERANK", duration: "196 ms", input: "95af20e9", output: "ac5409fe" },
  { name: "CONTEXT_SELECTION", duration: "11 ms", input: "ac5409fe", output: "bbc411c2" },
  { name: "PROMPT_BUILD", duration: "6 ms", input: "e7f0319c", output: "3d91a842" },
  { name: "GENERATION", duration: "956 ms", input: "3d91a842", output: "a728094e" },
];

const candidates = [
  { id: "chunk-1842", old: 1, next: 4, retrieval: "0.03184", rerank: "0.6127", source: "راهنمای انتقال پایا", category: "انتقال وجه", content: "درخواست انتقال پایا در چرخه های تعیین شده بانک مرکزی پردازش می شود. زمان ثبت درخواست تعیین می کند که واریز در چرخه جاری یا نخستین چرخه روز کاری بعد انجام شود." },
  { id: "chunk-2907", old: 2, next: 2, retrieval: "0.03123", rerank: "0.8241", source: "چرخه های تسویه", category: "عملیات بانکی", content: "چرخه های تسویه پایا در روزهای کاری اجرا می شوند. درخواست پس از آخرین چرخه یا در روز تعطیل به اولین چرخه روز کاری بعد منتقل می شود." },
  { id: "chunk-5530", old: 3, next: 5, retrieval: "0.03091", rerank: "0.5582", source: "سوالات متداول پایا", category: "راهنما", content: "مدت زمان انتقال پایا به ساعت ثبت، روز کاری و وضعیت چرخه مقصد وابسته است." },
  { id: "chunk-1081", old: 4, next: 7, retrieval: "0.03012", rerank: "0.3019", source: "انتقال ساتنا", category: "انتقال وجه", content: "ساتنا برای انتقال های با مبلغ بالا استفاده می شود و زمان بندی آن با پایا تفاوت دارد." },
  { id: "chunk-4721", old: 5, next: 6, retrieval: "0.02984", rerank: "0.4175", source: "محدودیت انتقال", category: "قوانین", content: "سقف مجاز انتقال روزانه با توجه به نوع انتقال و سطح دسترسی مشتری تعیین می شود." },
  { id: "chunk-8140", old: 6, next: 8, retrieval: "0.02931", rerank: "0.1944", source: "وضعیت تراکنش", category: "پشتیبانی", content: "وضعیت تراکنش از بخش گردش حساب و پیگیری انتقال در برنامه قابل مشاهده است." },
  { id: "chunk-6644", old: 7, next: 3, retrieval: "0.02888", rerank: "0.7312", source: "تقویم عملیات بانکی", category: "عملیات بانکی", content: "تعطیلات رسمی و پایان ساعت کاری بر زمان پردازش انتقال های بین بانکی اثر می گذارد." },
  { id: "chunk-9276", old: 8, next: 1, retrieval: "0.02841", rerank: "0.9038", source: "زمان بندی پایا", category: "انتقال وجه", content: "اگر درخواست پایا پیش از پایان چرخه فعال روز کاری ثبت شود، معمولا همان روز پردازش می شود. درخواست دیرتر در نخستین چرخه روز کاری بعد قرار می گیرد." },
];

const stageRail = document.querySelector("#stage-rail");
const stageOutput = document.querySelector("#stage-output");
const stageTitle = document.querySelector("#stage-title");
let activeStage = "RERANK";
let rawMode = false;

const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function stageMeta(stage) {
  return `<div class="stage-overview"><div><span>وضعیت</span><code class="text-success">COMPLETED</code></div><div><span>زمان</span><code dir="ltr">${stage.duration}</code></div><div><span>هش ورودی / خروجی</span><code dir="ltr" title="sha256:${stage.input}... / sha256:${stage.output}...">${stage.input}... / ${stage.output}...</code></div></div>`;
}

function outputSection(title, body, note = "") {
  return `<section class="output-section"><header class="output-title"><span>${title}</span>${note ? `<small>${note}</small>` : ""}</header>${body}</section>`;
}

function renderNormalization() {
  return outputSection("تغییر متن پرسش", `<div class="compare-block"><div><small>Original query</small><p>اگر امروز ثبت کنم، چه زمانی واریز <mark>می‌شود</mark>؟</p></div><span>←</span><div><small>Normalized query</small><p>اگر امروز ثبت کنم، چه زمانی واریز <mark>می شود</mark>؟</p></div></div>`, "1 change") + outputSection("جزئیات", `<div class="output-body"><p>نویسه اتصال در فعل به فاصله استاندارد تبدیل شد. معنای پرسش تغییر نکرده است.</p></div>`);
}

function renderHistory() {
  return outputSection("تاریخچه استفاده شده", `<div class="output-body"><div class="history-message"><b>user</b><p>سقف انتقال وجه پایا چقدر است؟</p></div><div class="history-message"><b>assistant</b><p>سقف انتقال پایا بر اساس مقررات روز و سطح دسترسی حساب تعیین می شود. مقدار دقیق در صفحه انتقال نمایش داده می شود.</p></div></div>`, "2 messages") + outputSection("اثر تاریخچه", `<div class="output-body"><p><code dir="ltr">history_before b2074d9a...f881</code></p><p><code dir="ltr">history_after 831dd7e1...a22c</code></p></div>`);
}

function renderRewrite() {
  return outputSection("بازنویسی پرسش", `<div class="compare-block"><div><small>Current query</small><p>اگر امروز ثبت کنم چه زمانی واریز می شود؟</p></div><span>←</span><div><small>Standalone query</small><p>انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟</p></div></div>`) + outputSection("زمینه مکالمه", `<div class="output-body"><p>پرسش پیشین درباره سقف انتقال وجه پایا بود. مرجع ضمیر پنهان در پرسش جاری به انتقال پایا تبدیل شد.</p><p><span class="state state--success">rewrite_used: true</span></p></div>`);
}

function renderIntent() {
  return outputSection("تصمیم طبقه بند", `<div class="output-body"><div class="confidence"><strong>0.941</strong><div><div class="confidence-line"><i></i></div><p>اطمینان intent انتخاب شده</p></div></div></div>`) + outputSection("جزئیات ذخیره شده", `<div class="output-body"><p>Intent انتخاب شده: <code dir="ltr">general</code></p><p>ورودی طبقه بند: انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟</p><p>آستانه موثر: <code dir="ltr">0.72</code></p></div>`, "بدون احتمال های ساختگی");
}

function renderRetrieval() {
  const rows = candidates.map((candidate) => `<tr data-chunk-id="${candidate.id}" class="${candidate.id === "chunk-1842" ? "is-selected" : ""}"><td><code>#${candidate.old}</code></td><td><button class="table-link chunk-button" data-chunk-id="${candidate.id}"><code dir="ltr">${candidate.id}</code></button></td><td><code dir="ltr">${candidate.retrieval}</code></td><td>${candidate.source}</td><td>${candidate.category}</td><td class="content-cell">${candidate.content}</td></tr>`).join("");
  return outputSection("نتایج جستجو پیش از بازرتبه بندی", `<div class="dense-table-wrap"><table class="trace-table"><thead><tr><th>رتبه بازیابی</th><th>Chunk ID</th><th>Retrieval score</th><th>منبع</th><th>دسته</th><th>پیش نمایش محتوا</th></tr></thead><tbody>${rows}</tbody></table></div><div class="chunk-inspect" id="chunk-inspect"><header><strong>راهنمای انتقال پایا</strong><code dir="ltr">chunk-1842</code></header><p>${candidates[0].content}</p></div>`, "8 candidates") + outputSection("پرسش بازیابی", `<div class="output-body"><p>انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟</p><p><code dir="ltr">RRF k=60 / semantic dimension=1024 / top_k=8</code></p></div>`);
}

function rankMovement(candidate) {
  const delta = candidate.old - candidate.next;
  if (delta > 0) return `<span class="rank-change rank-change--up">#${candidate.old} → #${candidate.next} ↑${delta}</span>`;
  if (delta < 0) return `<span class="rank-change rank-change--down">#${candidate.old} → #${candidate.next} ↓${Math.abs(delta)}</span>`;
  return `<span class="rank-change rank-change--same">#${candidate.old} → #${candidate.next} =</span>`;
}

function renderRerank() {
  const ordered = [...candidates].sort((a, b) => a.next - b.next);
  const rows = ordered.map((candidate, index) => `<tr class="${index < 3 ? "is-selected" : ""}"><td>${rankMovement(candidate)}</td><td><button class="table-link chunk-button" data-chunk-id="${candidate.id}"><code dir="ltr">${candidate.id}</code></button></td><td>${candidate.source}</td><td><code dir="ltr">${candidate.retrieval}</code></td><td><code dir="ltr">${candidate.rerank}</code></td><td>${candidate.next <= 3 ? '<span class="state state--success">SELECTED</span>' : '<span class="state state--queued">NOT SELECTED</span>'}</td></tr>`).join("");
  return outputSection("مقایسه رتبه بازیابی و رتبه جدید", `<div class="tabset table-modes"><button>ترتیب بازیابی</button><button class="is-active">ترتیب نهایی Rerank</button></div><div class="dense-table-wrap"><table class="trace-table"><thead><tr><th>جابجایی رتبه</th><th>Chunk ID</th><th>منبع</th><th>Retrieval score</th><th>Reranker score</th><th>انتخاب</th></tr></thead><tbody>${rows}</tbody></table></div><div class="chunk-inspect" id="chunk-inspect"><header><strong>زمان بندی پایا</strong><code dir="ltr">chunk-9276</code></header><p>${candidates[7].content}</p></div>`, "8 reranked / top 3 selected") + outputSection("خلاصه حرکت", `<div class="output-body"><p><span class="rank-change rank-change--up">chunk-9276: #8 → #1 ↑7</span></p><p><span class="rank-change rank-change--down">chunk-1842: #1 → #4 ↓3</span></p><p><span class="rank-change rank-change--same">chunk-2907: #2 → #2 =</span></p></div>`);
}

function renderContext() {
  const selected = [...candidates].sort((a, b) => a.next - b.next).slice(0, 3);
  const items = selected.map((candidate, index) => `<article class="context-item"><header><span class="context-rank">${index + 1}</span><strong>${candidate.source}</strong><code dir="ltr">${candidate.id} / ${candidate.rerank}</code></header><p>${candidate.content}</p></article>`).join("");
  return outputSection("عملا برای تولید انتخاب شده", `<div class="output-body"><p>سه قطعه از 8 نتیجه بازیابی و 8 نتیجه بازرتبه بندی وارد زمینه مدل شدند.</p></div>`, "3 selected") + outputSection("زمینه نهایی به ترتیب", `<div class="output-body selected-contexts">${items}</div>`) + outputSection("هش زمینه", `<div class="output-body"><code dir="ltr" title="sha256:bbc4a78474f47235699050201901f29543b611c25">sha256:bbc4a78474f47235699050201901f29543b611c25</code></div>`);
}

function renderPrompt() {
  return outputSection("پیام های ساخته شده", `<div class="output-body message-stack"><article class="prompt-message"><b>system</b><p>شما دستیار پشتیبانی بانک هستید. پاسخ را فقط بر اساس زمینه ارائه شده، دقیق و روشن بنویسید.</p></article><article class="prompt-message"><b>history</b><p>کاربر درباره سقف انتقال پایا پرسیده و پاسخ مرتبط با محدودیت روزانه دریافت کرده است.</p></article><article class="prompt-message"><b>context</b><p>[chunk-9276] زمان بندی پایا... [chunk-2907] چرخه های تسویه... [chunk-6644] تقویم عملیات بانکی...</p></article><article class="prompt-message"><b>user</b><p>انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟</p></article></div>`) + outputSection("فراداده موجود", `<div class="output-body"><p><code dir="ltr">prompt_source RAGSystem.answer:FAQ</code></p><p><code dir="ltr">prompt_hash 3d91c8a7...ab842</code></p><p>تعداد پیام: <code>2</code></p></div>`, "بدون تخمین token");
}

function renderGeneration() {
  return outputSection("پاسخ نهایی", `<div class="generated-answer">انتقال پایا در چرخه های تسویه بانک مرکزی پردازش می شود. اگر درخواست در روز کاری و پیش از پایان چرخه جاری ثبت شود، معمولا همان روز به حساب مقصد می رسد. درخواست های ثبت شده پس از آخرین چرخه یا در روز تعطیل، در نخستین چرخه روز کاری بعد پردازش می شوند.</div><div class="source-list"><span>زمان بندی پایا <code>chunk-9276</code></span><span>چرخه های تسویه <code>chunk-2907</code></span><span>تقویم عملیات بانکی <code>chunk-6644</code></span></div>`) + outputSection("اجرای تولید", `<div class="output-body"><p>زمان تولید: <code dir="ltr">956 ms</code></p><p>Answer hash: <code dir="ltr">a728f30c...094e</code></p><p>Fallback: <span class="text-success">خیر</span></p><p>مدل ثبت شده: <code dir="ltr">Qwen/Qwen2.5-32B-Instruct</code></p></div>`);
}

const specializedViews = {
  NORMALIZATION: renderNormalization,
  HISTORY: renderHistory,
  REWRITE: renderRewrite,
  INTENT: renderIntent,
  RETRIEVAL: renderRetrieval,
  RERANK: renderRerank,
  CONTEXT_SELECTION: renderContext,
  PROMPT_BUILD: renderPrompt,
  GENERATION: renderGeneration,
};

function rawStage(stage) {
  const sample = {
    stage_name: stage.name,
    stage_order: (stages.indexOf(stage) + 1) * 10,
    status: "COMPLETED",
    input_hash: `sha256:${stage.input}...`,
    output_hash: `sha256:${stage.output}...`,
    duration_ms: Number.parseFloat(stage.duration),
    note: "Mock preview. The production view uses the stored input_data, output_data and metrics objects.",
  };
  return `<pre class="raw-json" dir="ltr">${escapeHtml(JSON.stringify(sample, null, 2))}</pre>`;
}

function renderStage() {
  const stage = stages.find((item) => item.name === activeStage);
  if (!stage) return;
  stageTitle.textContent = stage.name;
  stageOutput.innerHTML = rawMode ? rawStage(stage) : stageMeta(stage) + specializedViews[stage.name]();
  stageRail.querySelectorAll(".stage-button").forEach((button) => button.classList.toggle("is-active", button.dataset.stage === activeStage));
  bindChunkButtons();
}

function renderRail() {
  stageRail.innerHTML = stages.map((stage, index) => `<button class="stage-button ${stage.name === activeStage ? "is-active" : ""}" data-stage="${stage.name}" aria-pressed="${stage.name === activeStage}"><span class="stage-index">${index + 1}</span><span class="stage-name">${stage.name}</span><span class="stage-duration">${stage.duration}</span><span class="stage-hashes">${stage.input.slice(0, 4)} → ${stage.output.slice(0, 4)}</span></button>`).join("");
  stageRail.querySelectorAll(".stage-button").forEach((button) => button.addEventListener("click", () => {
    activeStage = button.dataset.stage;
    rawMode = false;
    updateInspectorTabs();
    renderStage();
  }));
}

function bindChunkButtons() {
  stageOutput.querySelectorAll(".chunk-button").forEach((button) => button.addEventListener("click", () => {
    const candidate = candidates.find((item) => item.id === button.dataset.chunkId);
    const inspect = stageOutput.querySelector("#chunk-inspect");
    if (!candidate || !inspect) return;
    inspect.innerHTML = `<header><strong>${candidate.source}</strong><code dir="ltr">${candidate.id}</code></header><p>${candidate.content}</p>`;
    stageOutput.querySelectorAll("tr[data-chunk-id]").forEach((row) => row.classList.toggle("is-selected", row.dataset.chunkId === candidate.id));
  }));
}

function updateInspectorTabs() {
  document.querySelectorAll(".stage-panel .tabset button").forEach((button, index) => {
    button.classList.toggle("is-active", rawMode === (index === 1));
    button.setAttribute("aria-selected", String(rawMode === (index === 1)));
  });
}

document.querySelectorAll(".stage-panel .tabset button").forEach((button, index) => button.addEventListener("click", () => {
  rawMode = index === 1;
  updateInspectorTabs();
  renderStage();
}));

const pageLabels = {
  overview: ["نمای کلی", "عملیات ارزیابی"],
  datasets: ["مجموعه داده", "بازرس مجموعه داده"],
  runs: ["اجراها", "بازرس اجرا"],
  stability: ["پایداری", "مقایسه تکرارها"],
  pipeline: ["خط لوله", "کاوشگر اثر"],
  system: ["سامانه", "وضعیت و پیکربندی"],
};

function showPage(pageName) {
  document.querySelectorAll("[data-page]").forEach((page) => { page.hidden = page.dataset.page !== pageName; });
  document.querySelectorAll(".primary-nav [data-page-target]").forEach((button) => button.classList.toggle("is-active", button.dataset.pageTarget === pageName));
  document.querySelector("#page-section").textContent = pageLabels[pageName][0];
  document.querySelector("#page-title").textContent = pageLabels[pageName][1];
}

document.querySelectorAll("[data-page-target]").forEach((button) => button.addEventListener("click", () => showPage(button.dataset.pageTarget)));

const turnData = {
  1: {
    query: "سقف انتقال وجه پایا چقدر است؟",
    normalized: "سقف انتقال وجه پایا چقدر است؟",
    rewritten: "سقف مجاز انتقال وجه پایا برای مشتری چقدر است؟",
    answer: "سقف انتقال پایا بر اساس مقررات روز و سطح دسترسی حساب تعیین می شود. مقدار دقیق سقف پیش از ثبت انتقال در صفحه تایید نمایش داده می شود.",
  },
  2: {
    query: "اگر امروز ثبت کنم چه زمانی واریز می شود؟",
    normalized: "اگر امروز ثبت کنم چه زمانی واریز می شود؟",
    rewritten: "انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟",
    answer: "انتقال پایا در چرخه های تسویه بانک مرکزی پردازش می شود. اگر درخواست در روز کاری و پیش از پایان چرخه جاری ثبت شود، معمولا همان روز به حساب مقصد می رسد. درخواست های ثبت شده پس از آخرین چرخه یا در روز تعطیل، در نخستین چرخه روز کاری بعد پردازش می شوند.",
  },
  3: {
    query: "امکان لغو درخواست وجود دارد؟",
    normalized: "امکان لغو درخواست وجود دارد؟",
    rewritten: "آیا امکان لغو درخواست انتقال وجه پایا پس از ثبت وجود دارد؟",
    answer: "این نوبت هنوز اجرا نشده است.",
  },
};

document.querySelectorAll(".turn-select").forEach((button) => button.addEventListener("click", () => {
  const turn = turnData[button.dataset.turn];
  if (!turn) return;
  document.querySelectorAll(".turn-select").forEach((item) => item.classList.toggle("is-active", item === button));
  document.querySelector("#turn-number").textContent = button.dataset.turn;
  document.querySelector("#turn-query").textContent = turn.query;
  document.querySelector("#turn-normalized").textContent = turn.normalized;
  document.querySelector("#turn-rewritten").textContent = turn.rewritten;
  document.querySelector("#turn-answer").textContent = turn.answer;
}));

renderRail();
renderStage();
