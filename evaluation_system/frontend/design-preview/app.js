const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const icon = (name, className = "") => `<svg class="icon ${className}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

const state = {
  page: "overview",
  selectedDataset: "ds-01",
  selectedSession: "hibank-10982",
  runInspector: false,
  selectedRun: "01J9R7K2",
  selectedStage: "RERANK",
  stageMode: "structured",
  selectedChunk: "chunk-9276",
  selectedTurn: 2,
  selectedTrace: 0,
  pipelineStage: "RETRIEVAL",
  pipelineMode: "structured",
  stabilityExperiment: "st-01",
  stabilityCell: "turn-2-r2",
  stabilityMode: "SESSION",
  uploadValidated: false,
  newRunType: "DATASET_INSPECTION",
  databaseState: "READY",
};

const datasets = [
  { id: "ds-01", name: "hibank_support_eval_fa_03.csv", type: "CSV", imported: "۱۴۰۵/۰۶/۰۷، ۱۰:۴۲", sessions: 42, turns: 126, rows: 128, valid: 126, invalid: 2, synthetic: 9, sha: "60d703c5987adb779f786a9138f01ea4b4314a8d8172d1dc949c44fb9b6ec177", status: "هشدار" },
  { id: "ds-02", name: "transfer_stability.xlsx", type: "XLSX", imported: "۱۴۰۵/۰۶/۰۵، ۱۶:۱۸", sessions: 18, turns: 54, rows: 54, valid: 54, invalid: 0, synthetic: 0, sha: "af24017ba2079480c42bd9953ac2085f981b87322db0b44a2cf4276a811d91a0", status: "معتبر" },
  { id: "ds-03", name: "card_support_regression.csv", type: "CSV", imported: "۱۴۰۵/۰۶/۰۱، ۰۹:۰۵", sessions: 31, turns: 83, rows: 84, valid: 83, invalid: 1, synthetic: 4, sha: "91e7f66d282504991ea20ac73c8cb30f078239857a12c03122a0dcf6c814310e", status: "هشدار" },
];

const datasetTurns = [
  { session: "hibank-10982", turn: 1, time: "2026-08-28 09:18:42", query: "سقف انتقال وجه پایا چقدر است؟", valid: true, row: 18 },
  { session: "hibank-10982", turn: 2, time: "2026-08-28 09:19:10", query: "اگر امروز ثبت کنم چه زمانی واریز می شود؟", valid: true, row: 19 },
  { session: "hibank-10982", turn: 3, time: "2026-08-28 09:20:02", query: "امکان لغو درخواست وجود دارد؟", valid: true, row: 20 },
  { session: "hibank-10994", turn: 1, time: "2026-08-28 09:34:18", query: "رمز پویا را چطور فعال کنم؟", valid: true, row: 27 },
  { session: "hibank-10994", turn: 2, time: "2026-08-28 09:35:01", query: "چرا پیامک رمز برای من نمی آید؟", valid: true, row: 28 },
  { session: "synthetic-0031", turn: 1, time: "-", query: "وضعیت تراکنش ناموفق را از کجا ببینم؟", valid: false, row: 31 },
];

const runs = [
  { id: "01J9R7K2", dataset: "hibank_support_eval_fa_03.csv", type: "DATASET_INSPECTION", status: "RUNNING", progress: 64, sessions: "27 / 42", turns: "81 / 126", fallback: 3, errors: 1, infra: 0, duration: "06:42", sha: "8b34a47c", started: "14:25:26" },
  { id: "01J9S2A8", dataset: "transfer_stability.xlsx", type: "STABILITY_SESSION", status: "PENDING", progress: 0, sessions: "0 / 72", turns: "0 / 216", fallback: 0, errors: 0, infra: 0, duration: "00:00", sha: "8b34a47c", started: "-" },
  { id: "01J9N4C1", dataset: "card_support_regression.csv", type: "DATASET_INSPECTION", status: "COMPLETED", progress: 100, sessions: "31 / 31", turns: "83 / 83", fallback: 2, errors: 0, infra: 0, duration: "09:18", sha: "4c21f83a", started: "13:48:11" },
  { id: "01J9M8T6", dataset: "transfer_stability.xlsx", type: "STABILITY_QUERY", status: "FAILED", progress: 37, sessions: "4 / 12", turns: "4 / 12", fallback: 0, errors: 1, infra: 1, duration: "01:51", sha: "4c21f83a", started: "12:21:44" },
  { id: "01J9K3P9", dataset: "hibank_support_eval_fa_03.csv", type: "STABILITY_DATASET", status: "CANCELLED", progress: 22, sessions: "28 / 126", turns: "73 / 378", fallback: 1, errors: 0, infra: 0, duration: "08:07", sha: "c91dd742", started: "10:07:19" },
  { id: "01J9H1V4", dataset: "card_support_regression.csv", type: "STABILITY_SESSION", status: "COMPLETED", progress: 100, sessions: "12 / 12", turns: "36 / 36", fallback: 0, errors: 0, infra: 0, duration: "04:26", sha: "c91dd742", started: "09:18:04" },
];

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

const turns = {
  1: { query: "سقف انتقال وجه پایا چقدر است؟", normalized: "سقف انتقال وجه پایا چقدر است؟", rewritten: "سقف مجاز انتقال وجه پایا برای مشتری چقدر است؟", answer: "سقف انتقال پایا بر اساس مقررات روز و سطح دسترسی حساب تعیین می شود. مقدار دقیق پیش از تایید انتقال نمایش داده می شود.", intent: "general", confidence: "0.936", latency: "1,318 ms" },
  2: { query: "اگر امروز ثبت کنم چه زمانی واریز می شود؟", normalized: "اگر امروز ثبت کنم چه زمانی واریز می شود؟", rewritten: "انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟", answer: "انتقال پایا در چرخه های تسویه بانک مرکزی پردازش می شود. اگر درخواست در روز کاری و پیش از پایان چرخه جاری ثبت شود، معمولا همان روز به حساب مقصد می رسد. درخواست های دیرتر در نخستین چرخه روز کاری بعد پردازش می شوند.", intent: "general", confidence: "0.941", latency: "1,842 ms" },
  3: { query: "امکان لغو درخواست وجود دارد؟", normalized: "امکان لغو درخواست وجود دارد؟", rewritten: "آیا امکان لغو درخواست انتقال وجه پایا پس از ثبت وجود دارد؟", answer: "این نوبت هنوز در صف اجرا قرار دارد.", intent: "-", confidence: "-", latency: "queued" },
};

const traces = [
  { run: "01J9R7K2", session: "hibank-10982", turn: 2, stage: "RETRIEVAL", status: "COMPLETED", latency: "337 ms", input: "0dd91ca8", output: "7a19e2cd", intent: "general" },
  { run: "01J9R7K2", session: "hibank-10982", turn: 2, stage: "RERANK", status: "COMPLETED", latency: "196 ms", input: "95af20e9", output: "ac5409fe", intent: "general" },
  { run: "01J9R7K2", session: "hibank-10982", turn: 2, stage: "CONTEXT_SELECTION", status: "COMPLETED", latency: "11 ms", input: "ac5409fe", output: "bbc411c2", intent: "general" },
  { run: "01J9R7K2", session: "synthetic-0031", turn: 1, stage: "GENERATION", status: "ERROR", latency: "921 ms", input: "aa41c213", output: "-", intent: "general" },
  { run: "01J9N4C1", session: "hibank-11004", turn: 1, stage: "INTENT", status: "COMPLETED", latency: "38 ms", input: "77119ae1", output: "5a4033b8", intent: "personal" },
];

const experiments = [
  { id: "st-01", title: "انتقال پایا، نشست سه نوبتی", type: "STABILITY_SESSION", repeats: 4, variants: 2, fallback: "0%", incomparable: 1, status: "DIVERGENT" },
  { id: "st-02", title: "فعال سازی رمز پویا", type: "STABILITY_QUERY", repeats: 5, variants: 1, fallback: "0%", incomparable: 0, status: "IDENTICAL" },
  { id: "st-03", title: "رگرسیون پشتیبانی کارت", type: "STABILITY_DATASET", repeats: 3, variants: 3, fallback: "2.4%", incomparable: 2, status: "DIVERGENT" },
];

const pageTitles = {
  overview: "نمای کلی",
  datasets: "مجموعه داده ها",
  runs: "اجراها",
  stability: "پایداری",
  pipeline: "خط لوله",
  system: "سیستم",
};

function statusBadge(status) {
  const labels = { RUNNING: "در حال اجرا", PENDING: "در صف", COMPLETED: "تکمیل شده", FAILED: "ناموفق", CANCELLED: "لغو شده", ERROR: "خطا", DIVERGENT: "واگرا", IDENTICAL: "یکسان" };
  return `<span class="status status--${status.toLowerCase()}"><i></i>${labels[status] || status}</span>`;
}

function pageHeader(title, subtitle, actions = "") {
  return `<header class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${actions ? `<div class="heading-actions">${actions}</div>` : ""}</header>`;
}

function panelHeader(title, subtitle = "", action = "") {
  return `<header class="panel-head"><div><h2>${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div>${action}</header>`;
}

function overviewPage() {
  const kpis = [
    ["مجموعه داده ها", "3", "database", "neutral"], ["کل اجراها", "24", "runs", "neutral"], ["در حال اجرا", "2", "runs", "live"], ["در صف", "3", "clock", "pending"],
    ["تکمیل شده", "18", "check", "success"], ["ناموفق", "1", "alert", "danger"], ["Fallback rate", "3.7%", "stability", "warning"], ["Error rate", "0.8%", "alert", "danger"],
  ];
  const kpiHtml = kpis.map(([label, value, iconName, tone]) => `<article class="kpi kpi--${tone}"><span class="kpi-icon">${icon(iconName)}</span><div><span>${label}</span><strong dir="ltr">${value}</strong></div></article>`).join("");
  const runRows = runs.slice(0, 5).map((run) => `<tr class="clickable" data-action="open-run" data-run-id="${run.id}"><td><button class="link-mono" data-action="open-run" data-run-id="${run.id}">${run.id}</button></td><td>${run.dataset}</td><td><code>${run.type}</code></td><td>${statusBadge(run.status)}</td><td><div class="progress-cell"><span><i style="width:${run.progress}%"></i></span><code>${run.progress}%</code></div></td><td><code>${run.duration}</code></td><td><code>${run.started}</code></td></tr>`).join("");
  return `<section class="page overview-page">
    ${pageHeader("RagBot Evaluation", "کنترل کیفیت، اجرای ارزیابی و مشاهده پذیری خط لوله RagBot در یک فضای عملیاتی.")}
    <div class="kpi-grid">${kpiHtml}</div>
    <div class="dashboard-row">
      <section class="panel activity-panel">${panelHeader("فعالیت ارزیابی", "تعداد نوبت های تکمیل شده در هفت روز اخیر", '<div class="mini-tabs"><button class="is-active">نوبت</button><button>اجرا</button></div>')}<div class="chart-wrap">
        <div class="chart-total"><strong>1,284</strong><span>نوبت ارزیابی شده</span><small class="positive">+12.6% نسبت به دوره قبل</small></div>
        <svg class="activity-chart" viewBox="0 0 720 210" role="img" aria-label="نمودار فعالیت ارزیابی در هفت روز">
          <g class="chart-grid"><path d="M38 20H700M38 65H700M38 110H700M38 155H700M38 200H700"/></g>
          <path class="chart-area" d="M38 172 C88 164 118 145 148 151 S225 118 258 132 S332 90 370 101 S442 67 480 78 S555 46 590 61 S654 32 700 42 L700 200 L38 200Z"/>
          <path class="chart-line" d="M38 172 C88 164 118 145 148 151 S225 118 258 132 S332 90 370 101 S442 67 480 78 S555 46 590 61 S654 32 700 42"/>
          <g class="chart-points"><circle cx="38" cy="172" r="4"/><circle cx="148" cy="151" r="4"/><circle cx="258" cy="132" r="4"/><circle cx="370" cy="101" r="4"/><circle cx="480" cy="78" r="4"/><circle cx="590" cy="61" r="4"/><circle cx="700" cy="42" r="4"/></g>
        </svg>
        <div class="chart-labels"><span>شنبه</span><span>یکشنبه</span><span>دوشنبه</span><span>سه شنبه</span><span>چهارشنبه</span><span>پنجشنبه</span><span>جمعه</span></div>
      </div></section>
      <section class="panel status-panel">${panelHeader("وضعیت اجراها", "24 اجرای اخیر")}<div class="donut-wrap"><div class="donut" role="img" aria-label="18 تکمیل، 2 در حال اجرا، 3 در صف و 1 ناموفق"><div><strong>24</strong><span>اجرا</span></div></div><ul class="donut-legend"><li><span><i class="legend-color completed"></i>تکمیل شده</span><b>18</b></li><li><span><i class="legend-color running"></i>در حال اجرا</span><b>2</b></li><li><span><i class="legend-color pending"></i>در صف</span><b>3</b></li><li><span><i class="legend-color failed"></i>ناموفق</span><b>1</b></li></ul></div></section>
      <section class="panel system-summary">${panelHeader("وضعیت سیستم", "آخرین snapshot ثبت شده")}<ul class="service-list"><li><span><i class="service-icon">API</i><span>Eval API<small>42 ms</small></span></span><b class="service-ok">پاسخ گو</b></li><li><span><i class="service-icon">PG</i><span>PostgreSQL<small>revision current</small></span></span><b class="service-ok">READY</b></li><li><span><i class="service-icon">WK</i><span>Eval Worker<small>postgres worker</small></span></span><b class="service-ok">فعال</b></li><li><span><i class="service-icon">RB</i><span>RagBot API<small>3 datasources</small></span></span><b class="service-ok">متصل</b></li></ul><div class="heartbeat"><span>آخرین heartbeat کارگر</span><strong dir="ltr">6s ago</strong><code dir="ltr">14:32:02</code></div></section>
    </div>
    <div class="overview-bottom">
      <section class="panel recent-runs">${panelHeader("اجراهای اخیر", "وضعیت و پیشرفت آخرین اجراها", '<button class="text-button" data-page-target="runs">مشاهده همه</button>')}<div class="table-scroll"><table class="data-table"><thead><tr><th>Run ID</th><th>مجموعه داده</th><th>نوع</th><th>وضعیت</th><th>پیشرفت</th><th>مدت</th><th>شروع</th></tr></thead><tbody>${runRows}</tbody></table></div></section>
      <section class="panel findings-panel">${panelHeader("یافته های پایداری", "آخرین واگرایی های ثبت شده", '<button class="text-button" data-page-target="stability">تحلیل کامل</button>')}<div class="finding-list"><button data-page-target="stability"><span class="finding-state warning">≠</span><span><strong>انتقال پایا، نشست سه نوبتی</strong><small>نوبت 2، مرحله <code>RERANK</code></small></span><time>12 دقیقه قبل</time></button><button data-page-target="stability"><span class="finding-state success">=</span><span><strong>فعال سازی رمز پویا</strong><small>5 تکرار کاملا یکسان</small></span><time>37 دقیقه قبل</time></button><button data-page-target="stability"><span class="finding-state danger">!</span><span><strong>پشتیبانی کارت بانکی</strong><small>1 خطای زیرساخت در تکرار 3</small></span><time>1 ساعت قبل</time></button></div></section>
    </div>
  </section>`;
}

function datasetsPage() {
  const selected = datasets.find((item) => item.id === state.selectedDataset) || datasets[0];
  const cards = datasets.map((dataset) => `<button class="dataset-card ${dataset.id === selected.id ? "is-selected" : ""}" data-action="select-dataset" data-dataset-id="${dataset.id}"><span class="file-type">${dataset.type}</span><span class="dataset-card-main"><strong dir="ltr">${dataset.name}</strong><small>${dataset.imported}</small></span><span class="dataset-card-stats"><b>${dataset.sessions}</b> نشست <b>${dataset.turns}</b> نوبت</span><span class="validation ${dataset.invalid ? "has-warning" : "is-valid"}">${dataset.invalid ? `${dataset.invalid} هشدار` : "معتبر"}</span></button>`).join("");
  const rows = datasetTurns.map((turn) => `<tr class="clickable ${state.selectedSession === turn.session ? "is-selected" : ""}" data-action="select-session" data-session-id="${turn.session}"><td><button class="link-mono" data-action="select-session" data-session-id="${turn.session}">${turn.session}</button></td><td>${turn.turn}</td><td><code>${turn.time}</code></td><td class="query-cell">${turn.query}</td><td>${turn.valid ? '<span class="validation is-valid">معتبر</span>' : '<span class="validation has-warning">هشدار زمان</span>'}</td><td><code>${turn.row}</code></td></tr>`).join("");
  const sessionTurns = datasetTurns.filter((turn) => turn.session === state.selectedSession);
  return `<section class="page datasets-page">
    ${pageHeader("مجموعه داده ها", `${datasets.length} مجموعه داده برای ارزیابی و پایداری`, `<button class="primary-button" data-action="open-upload">${icon("plus")}افزودن مجموعه داده</button>`)}
    <div class="dataset-cards">${cards}</div>
    <section class="panel dataset-inspector">${panelHeader("بازرس مجموعه داده", selected.name, `<span class="validation ${selected.invalid ? "has-warning" : "is-valid"}">${selected.status}</span>`)}<div class="inspector-stats"><div><span>کل ردیف</span><strong>${selected.rows}</strong></div><div><span>ردیف معتبر</span><strong class="success-text">${selected.valid}</strong></div><div><span>ردیف نامعتبر</span><strong class="warning-text">${selected.invalid}</strong></div><div><span>نشست</span><strong>${selected.sessions}</strong></div><div><span>نشست مصنوعی</span><strong>${selected.synthetic}</strong></div><div class="hash-stat"><span>File SHA256</span><code title="${selected.sha}">${selected.sha.slice(0, 18)}...${selected.sha.slice(-8)}</code></div></div></section>
    <div class="dataset-workspace">
      <section class="panel dataset-table-panel">${panelHeader("ردیف ها و نوبت ها", "انتخاب یک نشست، توالی مکالمه را باز می کند", '<div class="table-tools"><label>'+icon("search")+'<input placeholder="جستجوی پرسش یا نشست"></label><button class="icon-button" aria-label="فیلتر جدول">'+icon("filter")+'</button></div>')}<div class="table-scroll"><table class="data-table dataset-table"><thead><tr><th>Session</th><th>Turn</th><th>Timestamp</th><th>Query</th><th>Validation</th><th>Source Row</th></tr></thead><tbody>${rows}</tbody></table></div><footer class="table-footer"><span>نمایش 6 ردیف از ${selected.rows}</span><div><button disabled>قبلی</button><b>1</b><button>بعدی</button></div></footer></section>
      <aside class="panel session-inspector">${panelHeader("توالی نشست", state.selectedSession)}<div class="session-meta"><span>${sessionTurns.length} نوبت</span><span>مرتب سازی زمانی</span></div><ol class="conversation-sequence">${sessionTurns.length ? sessionTurns.map((turn) => `<li><span>${turn.turn}</span><div><small><code>${turn.time}</code></small><p>${turn.query}</p><code>source row ${turn.row}</code></div></li>`).join("") : '<li class="empty-inline">برای این نشست داده ای نمایش داده نشده است.</li>'}</ol></aside>
    </div>
  </section>`;
}

function runsPage() {
  if (state.runInspector) return runInspectorPage();
  const rows = runs.map((run) => `<tr class="clickable" data-action="open-run" data-run-id="${run.id}"><td><button class="link-mono" data-action="open-run" data-run-id="${run.id}">${run.id}</button></td><td>${run.dataset}</td><td><code>${run.type}</code></td><td>${statusBadge(run.status)}</td><td><div class="progress-cell"><span><i style="width:${run.progress}%"></i></span><code>${run.progress}%</code></div></td><td><code>${run.sessions}</code></td><td><code>${run.turns}</code></td><td class="${run.fallback ? "warning-text" : ""}">${run.fallback}</td><td class="${run.errors ? "danger-text" : ""}">${run.errors}</td><td class="${run.infra ? "danger-text" : ""}">${run.infra}</td><td><code>${run.duration}</code></td><td><code>${run.sha}</code></td><td><code>${run.started}</code></td></tr>`).join("");
  return `<section class="page runs-page">
    ${pageHeader("اجراها", "مدیریت صف، پایش پیشرفت و دسترسی به اثر کامل هر اجرا", `<button class="primary-button" data-action="open-new-run">${icon("plus")}اجرای ارزیابی جدید</button>`)}
    <section class="filter-panel"><label><span>وضعیت</span><select><option>همه وضعیت ها</option><option>RUNNING</option><option>PENDING</option><option>COMPLETED</option><option>FAILED</option><option>CANCELLED</option></select></label><label><span>نوع اجرا</span><select><option>همه انواع</option><option>DATASET_INSPECTION</option><option>STABILITY_QUERY</option><option>STABILITY_SESSION</option><option>STABILITY_DATASET</option></select></label><label><span>مجموعه داده</span><select><option>همه مجموعه ها</option>${datasets.map((item) => `<option>${item.name}</option>`).join("")}</select></label><label class="check-filter"><input type="checkbox"> دارای خطا</label><label class="check-filter"><input type="checkbox"> دارای Fallback</label><button class="secondary-button">${icon("filter")}اعمال فیلتر</button></section>
    <section class="panel run-table-panel">${panelHeader("فهرست اجراها", `${runs.length} اجرای نمایشی، برای باز کردن بازرس روی هر ردیف کلیک کنید`, '<label class="compact-search">'+icon("search")+'<input placeholder="Run ID"></label>')}<div class="table-scroll"><table class="data-table runs-table"><thead><tr><th>Run ID</th><th>Dataset</th><th>Run Type</th><th>Status</th><th>Progress</th><th>Sessions</th><th>Turns</th><th>Fallbacks</th><th>Errors</th><th>Infra</th><th>Duration</th><th>Git SHA</th><th>Started</th></tr></thead><tbody>${rows}</tbody></table></div><footer class="table-footer"><span>آخرین snapshot در <code>14:32:08</code></span><div><button disabled>قبلی</button><b>1</b><button>بعدی</button></div></footer></section>
  </section>`;
}

function stageRail(scope = "run") {
  const selected = scope === "pipeline" ? state.pipelineStage : state.selectedStage;
  return `<div class="execution-rail" role="tablist" aria-label="مراحل خط لوله">${stages.map((stage, index) => `<button role="tab" aria-selected="${stage.name === selected}" class="stage-step ${stage.name === selected ? "is-active" : ""}" data-action="select-${scope}-stage" data-stage="${stage.name}"><span class="stage-number">${index + 1}</span><span><strong>${stage.name}</strong><small>${stage.duration}</small></span><i class="stage-state">${icon("check")}</i></button>`).join("")}</div>`;
}

function stageMeta(stage) {
  return `<div class="stage-meta"><div><span>State</span><strong class="success-text">COMPLETED</strong></div><div><span>Duration</span><code>${stage.duration}</code></div><div><span>Input hash</span><code title="sha256:${stage.input}">${stage.input}...</code></div><div><span>Output hash</span><code title="sha256:${stage.output}">${stage.output}...</code></div></div>`;
}

function chunkDetail() {
  const chunk = candidates.find((item) => item.id === state.selectedChunk) || candidates[0];
  return `<aside class="chunk-detail"><header><div><span>محتوای کامل قطعه</span><strong>${chunk.source}</strong></div><code>${chunk.id}</code></header><p>${chunk.content}</p><dl><div><dt>Category</dt><dd>${chunk.category}</dd></div><div><dt>Retrieval</dt><dd><code>${chunk.retrieval}</code></dd></div><div><dt>Reranker</dt><dd><code>${chunk.rerank}</code></dd></div></dl></aside>`;
}

function rankMovement(candidate) {
  const delta = candidate.old - candidate.next;
  if (delta > 0) return `<span class="rank rank--up">#${candidate.old} → #${candidate.next}<b>↑${delta}</b></span>`;
  if (delta < 0) return `<span class="rank rank--down">#${candidate.old} → #${candidate.next}<b>↓${Math.abs(delta)}</b></span>`;
  return `<span class="rank rank--same">#${candidate.old} → #${candidate.next}<b>0</b></span>`;
}

function specializedStage(name, compact = false) {
  if (name === "NORMALIZATION") return `<section class="artifact"><header><h3>تفاوت متن پرسش</h3><span>1 تغییر</span></header><div class="before-after"><div><small>Original Query</small><p>اگر امروز ثبت کنم، چه زمانی واریز <mark>می‌شود</mark>؟</p></div><i>${icon("arrow")}</i><div><small>Normalized Query</small><p>اگر امروز ثبت کنم، چه زمانی واریز <mark>می شود</mark>؟</p></div></div></section>`;
  if (name === "HISTORY") return `<section class="artifact"><header><h3>تاریخچه استفاده شده</h3><span>2 پیام</span></header><div class="history-list"><article><b>user</b><p>سقف انتقال وجه پایا چقدر است؟</p></article><article><b>assistant</b><p>سقف انتقال بر اساس مقررات روز و سطح دسترسی حساب تعیین می شود.</p></article></div><footer class="hash-line"><code>before b2074d9a...f881</code><code>after 831dd7e1...a22c</code></footer></section>`;
  if (name === "REWRITE") return `<section class="artifact"><header><h3>بازنویسی مستقل</h3><span class="success-text">rewrite_used: true</span></header><div class="before-after"><div><small>Current Query</small><p>اگر امروز ثبت کنم چه زمانی واریز می شود؟</p></div><i>${icon("arrow")}</i><div><small>Standalone Query</small><p>انتقال وجه پایا اگر امروز ثبت شود چه زمانی به حساب مقصد واریز می شود؟</p></div></div></section>`;
  if (name === "INTENT") return `<section class="artifact"><header><h3>تصمیم طبقه بند</h3><code>classifier_input</code></header><div class="intent-result"><div><span>Selected intent</span><strong><code>general</code></strong></div><div><span>Confidence</span><strong>0.941</strong><i class="confidence-bar"><b style="width:94.1%"></b></i></div><div><span>Effective threshold</span><strong>0.72</strong></div></div><p class="artifact-note">فقط confidence ثبت شده برای intent انتخابی نمایش داده می شود.</p></section>`;
  if (name === "RETRIEVAL") {
    const rows = candidates.map((item) => `<tr class="${item.id === state.selectedChunk ? "is-selected" : ""}" data-action="select-chunk" data-chunk-id="${item.id}"><td>#${item.old}</td><td><button class="link-mono" data-action="select-chunk" data-chunk-id="${item.id}">${item.id}</button></td><td><code>${item.retrieval}</code></td><td>${item.source}</td><td>${item.category}</td><td class="preview-cell">${item.content}</td></tr>`).join("");
    return `<section class="artifact retrieval-artifact"><header><div><h3>نتایج جستجو پیش از بازرتبه بندی</h3><p>تمام کاندیداهای ذخیره شده در trace</p></div><span>${candidates.length} candidate</span></header><div class="table-scroll"><table class="data-table trace-table"><thead><tr><th>Rank</th><th>Chunk ID</th><th>Retrieval Score</th><th>Source</th><th>Category</th><th>Preview</th></tr></thead><tbody>${rows}</tbody></table></div>${compact ? "" : chunkDetail()}</section>`;
  }
  if (name === "RERANK") {
    const rows = [...candidates].sort((a, b) => a.next - b.next).map((item) => `<tr class="${item.id === state.selectedChunk ? "is-selected" : ""}" data-action="select-chunk" data-chunk-id="${item.id}"><td>#${item.old}</td><td>#${item.next}</td><td>${rankMovement(item)}</td><td><button class="link-mono" data-action="select-chunk" data-chunk-id="${item.id}">${item.id}</button></td><td>${item.source}</td><td><code>${item.retrieval}</code></td><td><code>${item.rerank}</code></td></tr>`).join("");
    return `<section class="artifact retrieval-artifact"><header><div><h3>مقایسه رتبه بازیابی و رتبه جدید</h3><p>مرتب شده بر اساس خروجی نهایی Rerank</p></div><span>top 3 selected</span></header><div class="table-scroll"><table class="data-table trace-table"><thead><tr><th>Old</th><th>New</th><th>Rank Delta</th><th>Chunk</th><th>Source</th><th>Retrieval</th><th>Reranker</th></tr></thead><tbody>${rows}</tbody></table></div>${compact ? "" : chunkDetail()}</section>`;
  }
  if (name === "CONTEXT_SELECTION") {
    const selected = [...candidates].sort((a, b) => a.next - b.next).slice(0, 3);
    return `<section class="artifact"><header><div><h3>زمینه انتخاب شده برای مدل</h3><p>3 قطعه از 8 نتیجه بازیابی</p></div><code>bbc4a784...11c25</code></header><div class="selection-funnel"><span>RETRIEVED <b>8</b></span><i>←</i><span>RERANKED <b>8</b></span><i>←</i><span class="is-final">SELECTED FOR LLM <b>3</b></span></div><div class="context-list">${selected.map((item, index) => `<article><span>${index + 1}</span><div><header><strong>${item.source}</strong><code>${item.id} / ${item.rerank}</code></header><p>${item.content}</p></div></article>`).join("")}</div></section>`;
  }
  if (name === "PROMPT_BUILD") return `<section class="artifact"><header><div><h3>پیام های ساخته شده</h3><p>Structured View</p></div><code>prompt 3d91c8a7...ab842</code></header><div class="message-view"><article><b>System</b><p>شما دستیار پشتیبانی بانک هستید. پاسخ را فقط بر اساس زمینه ارائه شده بنویسید.</p></article><article><b>History</b><p>کاربر پیش تر درباره سقف انتقال پایا پرسیده است.</p></article><article><b>Context</b><p>[chunk-9276] زمان بندی پایا... [chunk-2907] چرخه های تسویه... [chunk-6644] تقویم عملیات بانکی...</p></article><article><b>User</b><p>انتقال وجه پایا اگر امروز ثبت شود چه زمانی واریز می شود؟</p></article></div></section>`;
  return `<section class="artifact generation-artifact"><header><div><h3>پاسخ نهایی</h3><p>خروجی ذخیره شده مرحله Generation</p></div><span class="validation is-valid">بدون Fallback</span></header><div class="generated-answer">${turns[2].answer}</div><div class="generation-meta"><div><span>Latency</span><code>956 ms</code></div><div><span>Answer hash</span><code>a728f30c...094e</code></div><div><span>Fallback</span><strong class="success-text">false</strong></div><div><span>Model</span><code>Qwen/Qwen2.5-32B-Instruct</code></div></div><footer class="grounding-sources"><span>منابع زمینه</span><button>زمان بندی پایا <code>chunk-9276</code></button><button>چرخه های تسویه <code>chunk-2907</code></button><button>تقویم عملیات بانکی <code>chunk-6644</code></button></footer></section>`;
}

function rawStage(stageName) {
  const stage = stages.find((item) => item.name === stageName);
  const value = { stage_name: stageName, stage_order: (stages.indexOf(stage) + 1) * 10, status: "COMPLETED", input_hash: `sha256:${stage.input}...`, output_hash: `sha256:${stage.output}...`, duration_ms: Number.parseFloat(stage.duration), preview_notice: "Mock design data" };
  return `<pre class="json-view" dir="ltr">${JSON.stringify(value, null, 2)}</pre>`;
}

function runInspectorPage() {
  const run = runs.find((item) => item.id === state.selectedRun) || runs[0];
  const stage = stages.find((item) => item.name === state.selectedStage) || stages[0];
  const turn = turns[state.selectedTurn];
  return `<section class="page run-inspector-page">
    <div class="inspector-breadcrumb"><button class="back-button" data-action="back-to-runs">${icon("chevron")}بازگشت به اجراها</button><span>/</span><code>${run.id}</code></div>
    <header class="run-header"><div class="run-title"><div><span>Run Inspector</span><h1><code>${run.id}</code></h1></div>${statusBadge(run.status)}</div><dl><div><dt>Dataset</dt><dd>${run.dataset}</dd></div><div><dt>Run Type</dt><dd><code>${run.type}</code></dd></div><div><dt>Git SHA</dt><dd><code>${run.sha}</code></dd></div><div><dt>Duration</dt><dd><code>${run.duration}</code></dd></div><div><dt>Knowledge Sources</dt><dd>راهنمای پایا، FAQ کارت، کارمزدها</dd></div></dl></header>
    <section class="run-progress-panel"><div class="run-progress-numbers"><span><b>27 / 42</b> نشست</span><span><b>81 / 126</b> نوبت</span><span class="warning-text"><b>3</b> fallback</span><span class="danger-text"><b>1</b> خطا</span><span><b>0</b> خطای زیرساخت</span></div><div class="wide-progress"><i style="width:${run.progress}%"></i><b>${run.progress}%</b></div></section>
    ${stageRail("run")}
    <div class="run-inspector-grid">
      <section class="panel stage-detail"><header class="detail-head"><div><span>خروجی مرحله</span><h2><code>${state.selectedStage}</code></h2></div><div class="view-tabs"><button class="${state.stageMode === "structured" ? "is-active" : ""}" data-action="stage-mode" data-mode="structured">Structured View</button><button class="${state.stageMode === "json" ? "is-active" : ""}" data-action="stage-mode" data-mode="json">Raw JSON</button></div></header><div class="detail-body">${stageMeta(stage)}${state.stageMode === "json" ? rawStage(state.selectedStage) : specializedStage(state.selectedStage)}</div></section>
      <section class="panel turn-evidence"><header class="detail-head"><div><span>نوبت انتخاب شده</span><h2>نوبت ${state.selectedTurn} از 3</h2></div><div class="pager"><button aria-label="نوبت قبلی">→</button><button aria-label="نوبت بعدی">←</button></div></header><div class="turn-body"><article class="user-message"><span>کاربر</span><p>${turn.query}</p></article><div class="query-derivations"><div><span>Normalized</span><p>${turn.normalized}</p></div><div><span>Rewritten</span><p>${turn.rewritten}</p></div></div><article class="assistant-answer"><header><span>RagBot</span><code>${turn.latency}</code></header><p>${turn.answer}</p></article><div class="source-chips"><span>زمینه انتخاب شده</span><button>زمان بندی پایا</button><button>چرخه های تسویه</button></div><dl class="turn-metadata"><div><dt>Intent</dt><dd><code>${turn.intent}</code></dd></div><div><dt>Confidence</dt><dd><code>${turn.confidence}</code></dd></div><div><dt>Fallback</dt><dd class="success-text">false</dd></div><div><dt>Error</dt><dd class="success-text">none</dd></div><div><dt>Context hash</dt><dd><code>bbc4...11c25</code></dd></div></dl></div></section>
      <aside class="panel run-navigator"><header class="detail-head"><div><span>ساختار اجرا</span><h2>نشست و نوبت</h2></div><button class="icon-button" aria-label="فیلتر نشست ها">${icon("filter")}</button></header><div class="navigator-stats"><span>42 نشست</span><span>126 نوبت</span></div><div class="session-tree"><section class="session-node is-open"><button class="session-title"><i>⌄</i><span><strong>hibank-10982</strong><small>تکرار 1 از 1</small></span>${statusBadge("RUNNING")}</button><div class="turn-tree">${Object.entries(turns).map(([number, item]) => `<button class="${Number(number) === state.selectedTurn ? "is-active" : ""}" data-action="select-turn" data-turn="${number}"><i>${number === "1" ? "✓" : number}</i><span><strong>نوبت ${number}</strong><small>${item.query}</small></span><code>${item.latency}</code></button>`).join("")}</div></section><section class="session-node"><button class="session-title"><i>‹</i><span><strong>hibank-10994</strong><small>3 نوبت</small></span>${statusBadge("PENDING")}</button></section><section class="session-node"><button class="session-title"><i>‹</i><span><strong>synthetic-0031</strong><small>1 نوبت</small></span><span class="validation has-warning">Fallback</span></button></section></div></aside>
    </div>
  </section>`;
}

function pipelinePage() {
  const selected = traces[state.selectedTrace] || traces[0];
  const stage = stages.find((item) => item.name === state.pipelineStage) || stages[4];
  const rows = traces.map((trace, index) => `<tr class="clickable ${index === state.selectedTrace ? "is-selected" : ""}" data-action="select-trace" data-trace-index="${index}"><td><code>${trace.run}</code></td><td><code>${trace.session}</code></td><td>${trace.turn}</td><td><code>${trace.stage}</code></td><td>${trace.status === "ERROR" ? statusBadge("ERROR") : '<span class="validation is-valid">COMPLETED</span>'}</td><td><code>${trace.latency}</code></td><td><code>${trace.input}</code></td><td><code>${trace.output}</code></td></tr>`).join("");
  return `<section class="page pipeline-page">
    ${pageHeader("کاوشگر خط لوله", "جستجو و بازرسی فنی trace های ذخیره شده", '<span class="concept-notice">جستجوی سراسری، تعامل نمایشی و نیازمند API آینده</span>')}
    <section class="filter-panel trace-filters"><label><span>Run ID</span><input value="01J9R7K2" dir="ltr"></label><label><span>Session</span><input placeholder="همه نشست ها"></label><label><span>Turn</span><select><option>همه</option><option>1</option><option>2</option></select></label><label><span>Stage</span><select><option>همه مراحل</option>${stages.map((item) => `<option>${item.name}</option>`).join("")}</select></label><label><span>Intent</span><select><option>همه</option><option>general</option><option>personal</option></select></label><label class="check-filter"><input type="checkbox"> خطا</label><label class="check-filter"><input type="checkbox"> Fallback</label><button class="primary-button">${icon("search")}جستجو</button></section>
    <div class="trace-workspace"><section class="panel trace-list">${panelHeader("نتایج trace", "5 نتیجه نمایشی، انتخاب ردیف برای بازرسی")}<div class="table-scroll"><table class="data-table"><thead><tr><th>Run</th><th>Session</th><th>Turn</th><th>Stage</th><th>Status</th><th>Latency</th><th>Input hash</th><th>Output hash</th></tr></thead><tbody>${rows}</tbody></table></div></section><aside class="panel trace-summary">${panelHeader("Trace انتخاب شده", `<code>${selected.run} / ${selected.session} / turn ${selected.turn}</code>`)}<dl><div><dt>Stage</dt><dd><code>${selected.stage}</code></dd></div><div><dt>Status</dt><dd>${selected.status}</dd></div><div><dt>Latency</dt><dd><code>${selected.latency}</code></dd></div><div><dt>Intent</dt><dd><code>${selected.intent}</code></dd></div><div><dt>Input</dt><dd><code>${selected.input}</code></dd></div><div><dt>Output</dt><dd><code>${selected.output}</code></dd></div></dl></aside></div>
    <section class="panel pipeline-inspector">${panelHeader("بازرس خروجی", "حرکت در مراحل همین نوبت")}${stageRail("pipeline")}<div class="pipeline-detail-head"><div><strong><code>${state.pipelineStage}</code></strong><span>${stage.duration}</span></div><div class="view-tabs"><button class="${state.pipelineMode === "structured" ? "is-active" : ""}" data-action="pipeline-mode" data-mode="structured">Structured View</button><button class="${state.pipelineMode === "json" ? "is-active" : ""}" data-action="pipeline-mode" data-mode="json">Raw JSON</button></div></div><div class="pipeline-output">${stageMeta(stage)}${state.pipelineMode === "json" ? rawStage(state.pipelineStage) : specializedStage(state.pipelineStage, true)}</div></section>
  </section>`;
}

function stabilityPage() {
  const experiment = experiments.find((item) => item.id === state.stabilityExperiment) || experiments[0];
  const expButtons = experiments.map((item) => `<button class="experiment-row ${item.id === experiment.id ? "is-selected" : ""}" data-action="select-experiment" data-experiment-id="${item.id}"><span>${item.status === "IDENTICAL" ? "=" : "≠"}</span><div><strong>${item.title}</strong><small><code>${item.type}</code></small></div>${statusBadge(item.status)}</button>`).join("");
  const matrixRows = [1, 2, 3].map((turn) => `<tr class="${turn === 2 ? "is-focus" : ""}"><td><strong>نوبت ${turn}</strong><small>${turns[turn].query}</small></td>${[1, 2, 3, 4].map((repeat) => { const key = `turn-${turn}-r${repeat}`; const kind = turn === 2 && [2, 4].includes(repeat) ? "diff" : turn === 3 && repeat === 2 ? "error" : turn === 3 && repeat === 4 ? "unknown" : "same"; const symbol = { same: "=", diff: "≠", error: "!", unknown: "?" }[kind]; return `<td><button class="matrix-cell matrix-cell--${kind} ${state.stabilityCell === key ? "is-selected" : ""}" data-action="select-stability-cell" data-cell="${key}" aria-label="نوبت ${turn}، تکرار ${repeat}، ${kind}">${symbol}</button></td>`; }).join("")}</tr>`).join("");
  const comparisons = [
    ["Normalized query", "اگر امروز ثبت کنم چه زمانی واریز می شود؟", "اگر امروز ثبت کنم چه زمانی واریز می شود؟", false],
    ["Rewritten query", "انتقال پایا امروز چه زمانی واریز می شود؟", "انتقال پایا امروز به حساب مقصد چه زمانی واریز می شود؟", true],
    ["Intent", "general", "general", false],
    ["Retrieval order", "1842, 2907, 5530, 9276", "1842, 2907, 5530, 9276", false],
    ["Rerank order", "9276, 2907, 6644, 1842", "2907, 9276, 6644, 1842", true],
    ["Context hash", "bbc4a784...11c25", "16aa20e7...7fc01", true],
    ["Prompt hash", "3d91c8a7...ab842", "3d91c8a7...ab842", false],
    ["Answer hash", "a728f30c...094e", "120c69d8...8b77", true],
    ["Answer", "در چرخه جاری یا روز کاری بعد پردازش می شود.", "با توجه به ساعت ثبت، در نخستین چرخه بعدی پردازش می شود.", true],
  ];
  return `<section class="page stability-page">
    ${pageHeader("پایداری", "مقایسه تکرارها و پیدا کردن نخستین نقطه واگرایی")}
    <div class="mode-tabs"><button class="${state.stabilityMode === "QUERY" ? "is-active" : ""}" data-action="stability-mode" data-mode="QUERY">Query Stability</button><button class="${state.stabilityMode === "SESSION" ? "is-active" : ""}" data-action="stability-mode" data-mode="SESSION">Session Stability</button><button class="${state.stabilityMode === "DATASET" ? "is-active" : ""}" data-action="stability-mode" data-mode="DATASET">Dataset Stability</button></div>
    <div class="stability-grid"><aside class="panel experiments">${panelHeader("آزمایش های اخیر", "انتخاب برای مشاهده جزئیات")}<div>${expButtons}</div></aside><div class="stability-main"><section class="panel stability-stats"><div><span>تکرار</span><strong>${experiment.repeats}</strong></div><div><span>Variant count</span><strong>${experiment.variants}</strong></div><div><span>Fallback rate</span><strong>${experiment.fallback}</strong></div><div><span>Incomparable</span><strong>${experiment.incomparable}</strong></div><div class="first-divergence"><span>FIRST DIVERGENT TURN</span><strong>Turn 2</strong></div><div class="first-divergence"><span>FIRST DIVERGENT STAGE</span><strong><code>RERANK</code></strong></div></section>
      <section class="panel matrix-panel">${panelHeader("ماتریس تکرار", "ردیف ها نوبت منطقی و ستون ها تکرار اجرا", '<div class="matrix-legend"><span><i class="same">=</i>یکسان</span><span><i class="diff">≠</i>واگرا</span><span><i class="error">!</i>خطا</span><span><i>?</i>غیرقابل مقایسه</span></div>')}<div class="table-scroll"><table class="matrix-table"><thead><tr><th>Logical Turn</th><th>Repeat 1</th><th>Repeat 2</th><th>Repeat 3</th><th>Repeat 4</th></tr></thead><tbody>${matrixRows}</tbody></table></div></section>
      <section class="panel comparison-panel">${panelHeader("مقایسه اجرای A و B", "تفاوت ها با تاکید نمایش داده می شوند", '<div class="compare-selects"><select><option>Repeat 1</option></select><span>در برابر</span><select><option>Repeat 2</option></select></div>')}<div class="comparison-path"><span>Turn 2</span><b>←</b><code>RERANK</code><b>←</b><span>First divergence</span></div><div class="comparison-table"><div class="comparison-head"><span>Artifact</span><span>Execution A</span><span>Execution B</span></div>${comparisons.map(([label, left, right, different]) => `<div class="comparison-row ${different ? "is-different" : ""}"><strong>${label}</strong><code>${left}</code><code>${right}</code></div>`).join("")}</div></section></div></div>
  </section>`;
}

function systemPage() {
  const services = [
    ["API", "Eval API", "پاسخ گو", "42 ms", "آخرین درخواست موفق 14:32:08"],
    ["PG", "PostgreSQL", "READY", "revision current", "schema evaluation_v1"],
    ["WK", "PostgreSQL Worker", "فعال", "heartbeat 6s", "برگرفته از اجرای باز"],
    ["RB", "RagBot API", "متصل", "77 ms", "3 منبع دانش دریافت شد"],
  ];
  return `<section class="page system-page">
    ${pageHeader("سیستم", "وضعیت اتصال ها، worker و آماده بودن پایگاه داده", '<button class="secondary-button">بازخوانی وضعیت</button>')}
    <div class="service-cards">${services.map(([abbr, name, status, detail, note]) => `<article class="service-card"><header><span>${abbr}</span><i class="signal signal--ok"></i></header><h2>${name}</h2><strong>${status}</strong><code>${detail}</code><p>${note}</p></article>`).join("")}</div>
    <div class="system-layout"><section class="panel ops-panel">${panelHeader("اطلاعات عملیاتی", "فقط مقادیر قابل استناد از قراردادهای فعلی")}<dl class="ops-grid"><div><dt>Backend version</dt><dd class="muted-value">در API فعلی ارائه نشده</dd></div><div><dt>RagBot Git SHA</dt><dd><code>8b34a47ce72f</code></dd></div><div><dt>Worker identity</dt><dd class="muted-value">در API فعلی ارائه نشده</dd></div><div><dt>Current running run</dt><dd><button class="link-mono" data-action="open-run" data-run-id="01J9R7K2">01J9R7K2</button></dd></div><div><dt>Pending runs</dt><dd><strong>3</strong> بر اساس فهرست اجراها</dd></div><div><dt>Session concurrency</dt><dd><code>4</code></dd></div><div><dt>Repeat max</dt><dd><code>20</code></dd></div><div><dt>Background execution</dt><dd class="success-text">available</dd></div></dl></section>
      <section class="panel db-panel">${panelHeader("مقداردهی پایگاه داده", "کنترل وضعیت migration و ساخت schema")}<div class="db-state-tabs"><button class="${state.databaseState === "NOT_INITIALIZED" ? "is-active" : ""}" data-action="database-state" data-state="NOT_INITIALIZED">Not initialized</button><button class="${state.databaseState === "READY" ? "is-active" : ""}" data-action="database-state" data-state="READY">Ready</button><button class="${state.databaseState === "UPGRADE_REQUIRED" ? "is-active" : ""}" data-action="database-state" data-state="UPGRADE_REQUIRED">Migration required</button></div>${databaseStateView()}</section>
    </div>
    <section class="panel capability-panel">${panelHeader("قابلیت های اعلام شده", "خروجی نمایشی مطابق ساختار system/capabilities")}<dl><div><dt>File types</dt><dd><code>.csv, .xlsx</code></dd></div><div><dt>Max upload</dt><dd><code>25 MB</code></dd></div><div><dt>Max rows</dt><dd><code>10,000</code></dd></div><div><dt>Stability concurrency</dt><dd><code>1</code></dd></div><div><dt>Database initialize</dt><dd><code>true</code></dd></div></dl></section>
  </section>`;
}

function databaseStateView() {
  if (state.databaseState === "NOT_INITIALIZED") return `<div class="db-state db-state--warning"><span>${icon("database")}</span><div><h3>پایگاه داده مقداردهی نشده است</h3><p>جدول های evaluation هنوز ایجاد نشده اند. مقداردهی فقط با تایید صریح انجام می شود.</p><code>current_revision: null</code></div><button class="primary-button" data-action="initialize-database">مقداردهی اولیه پایگاه داده</button></div>`;
  if (state.databaseState === "UPGRADE_REQUIRED") return `<div class="db-state db-state--danger"><span>${icon("alert")}</span><div><h3>Migration موردنیاز است</h3><p>نسخه فعلی با نسخه موردنیاز برابر نیست.</p><code>current 20260831_0001 / required 20260912_0002</code></div><button class="secondary-button">مشاهده راهنمای عملیات</button></div>`;
  return `<div class="db-state db-state--ready"><span>${icon("check")}</span><div><h3>پایگاه داده آماده است</h3><p>نسخه schema با نسخه موردنیاز برابر است و شیء مفقودی گزارش نشده.</p><code>revision 20260831_0001</code></div><button class="secondary-button" disabled>نیازی به اقدام نیست</button></div>`;
}

function uploadModal() {
  return `<div class="overlay" role="presentation" data-action="close-overlay"><section class="modal upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title" onclick="event.stopPropagation()"><header><div><h2 id="upload-title">افزودن مجموعه داده</h2><p>CSV یا XLSX را پیش از import اعتبارسنجی کنید.</p></div><button class="icon-button" data-action="close-overlay" aria-label="بستن">${icon("close")}</button></header><div class="modal-body"><div class="import-steps"><span class="is-active">انتخاب فایل</span><span class="${state.uploadValidated ? "is-active" : ""}">اعتبارسنجی</span><span>تایید import</span></div>${state.uploadValidated ? `<div class="file-selected"><span>${icon("file")}</span><div><strong dir="ltr">hibank_fees_eval.csv</strong><small>148 KB، CSV</small></div><span class="validation has-warning">2 هشدار</span></div><dl class="validation-summary"><div><dt>ردیف</dt><dd>64</dd></div><div><dt>معتبر</dt><dd class="success-text">62</dd></div><div><dt>نامعتبر</dt><dd class="warning-text">2</dd></div><div><dt>نشست</dt><dd>21</dd></div></dl><div class="warning-list"><p>${icon("alert")}ردیف 18: مقدار timestamp قابل تبدیل نیست.</p><p>${icon("alert")}ردیف 42: session_id خالی است و نشست مصنوعی ساخته می شود.</p></div>` : `<button class="file-drop" data-action="validate-upload">${icon("upload")}<strong>انتخاب فایل CSV یا XLSX</strong><span>حداکثر 25 MB و 10,000 ردیف</span></button>`}</div><footer><button class="secondary-button" data-action="close-overlay">انصراف</button>${state.uploadValidated ? '<button class="primary-button" data-action="confirm-upload">تایید و import</button>' : '<button class="primary-button" data-action="validate-upload">انتخاب فایل نمونه</button>'}</footer></section></div>`;
}

function newRunModal() {
  const stability = state.newRunType.startsWith("STABILITY");
  const descriptions = {
    DATASET_INSPECTION: "هر نشست یک بار علیه runtime واقعی RagBot اجرا می شود.",
    STABILITY_QUERY: "یک پرسش در چند تکرار مستقل مقایسه می شود.",
    STABILITY_SESSION: "ترتیب کامل یک نشست در چند تکرار بازپخش می شود.",
    STABILITY_DATASET: "تمام نشست های مجموعه داده در چند تکرار مقایسه می شوند.",
  };
  return `<div class="overlay" role="presentation" data-action="close-overlay"><section class="drawer" role="dialog" aria-modal="true" aria-labelledby="new-run-title" onclick="event.stopPropagation()"><header><div><h2 id="new-run-title">اجرای ارزیابی جدید</h2><p>تنظیمات با قرارداد فعلی Eval Backend</p></div><button class="icon-button" data-action="close-overlay" aria-label="بستن">${icon("close")}</button></header><div class="drawer-body"><label class="form-field"><span>مجموعه داده</span><select><option>hibank_support_eval_fa_03.csv</option><option>transfer_stability.xlsx</option><option>card_support_regression.csv</option></select></label><fieldset><legend>منابع دانش</legend><label class="source-option"><input type="checkbox" checked><span><strong>راهنمای انتقال وجه</strong><small>انتقال پایا، ساتنا و کارت به کارت</small></span></label><label class="source-option"><input type="checkbox" checked><span><strong>سوالات متداول کارت</strong><small>کارت بانکی و رمز پویا</small></span></label><label class="source-option"><input type="checkbox"><span><strong>تعرفه و کارمزد</strong><small>کارمزد خدمات بانکی</small></span></label></fieldset><label class="form-field"><span>نوع اجرا</span><select id="new-run-type">${["DATASET_INSPECTION", "STABILITY_QUERY", "STABILITY_SESSION", "STABILITY_DATASET"].map((type) => `<option ${type === state.newRunType ? "selected" : ""}>${type}</option>`).join("")}</select><small class="field-help">${descriptions[state.newRunType]}</small></label>${stability ? '<label class="form-field"><span>تعداد تکرار</span><input type="number" value="4" min="2" max="20"><small class="field-help">حداقل 2 و حداکثر 20 تکرار</small></label>' : '<div class="inline-note">DATASET_INSPECTION همیشه با یک تکرار اجرا می شود.</div>'}<div class="run-preview"><span>خلاصه اجرا</span><dl><div><dt>Dataset</dt><dd>42 نشست، 126 نوبت</dd></div><div><dt>Run Type</dt><dd><code>${state.newRunType}</code></dd></div><div><dt>Knowledge Sources</dt><dd>2 منبع انتخاب شده</dd></div></dl></div></div><footer><button class="secondary-button" data-action="close-overlay">انصراف</button><button class="primary-button" data-action="create-run">${icon("runs")}قرار دادن در صف</button></footer></section></div>`;
}

function render() {
  const pages = { overview: overviewPage, datasets: datasetsPage, runs: runsPage, stability: stabilityPage, pipeline: pipelinePage, system: systemPage };
  $("#page-host").innerHTML = pages[state.page]();
  $("#page-title").textContent = state.page === "runs" && state.runInspector ? "بازرس اجرا" : pageTitles[state.page];
  $$(".sidebar-nav [data-page-target]").forEach((button) => button.classList.toggle("is-active", button.dataset.pageTarget === state.page));
}

function showToast(message) {
  $("#toast-root").innerHTML = `<div class="toast">${icon("check")}<span>${message}</span></div>`;
  window.setTimeout(() => { $("#toast-root").innerHTML = ""; }, 2600);
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-page-target], [data-action]");
  if (!target) return;
  if (target.dataset.pageTarget) {
    state.page = target.dataset.pageTarget;
    state.runInspector = false;
    render();
    $("#page-host").focus();
    return;
  }
  const action = target.dataset.action;
  if (action === "select-dataset") { state.selectedDataset = target.dataset.datasetId; render(); }
  if (action === "select-session") { state.selectedSession = target.dataset.sessionId; render(); }
  if (action === "open-upload") { $("#overlay-root").innerHTML = uploadModal(); }
  if (action === "validate-upload") { state.uploadValidated = true; $("#overlay-root").innerHTML = uploadModal(); }
  if (action === "confirm-upload") { $("#overlay-root").innerHTML = ""; showToast("مجموعه داده نمایشی با موفقیت import شد."); }
  if (action === "open-new-run") { $("#overlay-root").innerHTML = newRunModal(); }
  if (action === "close-overlay" && event.target.closest("[data-action=close-overlay]")) { $("#overlay-root").innerHTML = ""; }
  if (action === "create-run") { $("#overlay-root").innerHTML = ""; showToast("اجرای نمایشی در صف قرار گرفت."); }
  if (action === "open-run") { state.page = "runs"; state.selectedRun = target.dataset.runId; state.runInspector = true; render(); }
  if (action === "back-to-runs") { state.runInspector = false; render(); }
  if (action === "select-run-stage") { state.selectedStage = target.dataset.stage; state.stageMode = "structured"; render(); }
  if (action === "stage-mode") { state.stageMode = target.dataset.mode; render(); }
  if (action === "select-chunk") { state.selectedChunk = target.dataset.chunkId; render(); }
  if (action === "select-turn") { state.selectedTurn = Number(target.dataset.turn); render(); }
  if (action === "select-trace") { state.selectedTrace = Number(target.dataset.traceIndex); state.pipelineStage = traces[state.selectedTrace].stage; render(); }
  if (action === "select-pipeline-stage") { state.pipelineStage = target.dataset.stage; state.pipelineMode = "structured"; render(); }
  if (action === "pipeline-mode") { state.pipelineMode = target.dataset.mode; render(); }
  if (action === "select-experiment") { state.stabilityExperiment = target.dataset.experimentId; render(); }
  if (action === "select-stability-cell") { state.stabilityCell = target.dataset.cell; render(); }
  if (action === "stability-mode") { state.stabilityMode = target.dataset.mode; render(); }
  if (action === "database-state") { state.databaseState = target.dataset.state; render(); }
  if (action === "initialize-database") { state.databaseState = "READY"; render(); showToast("نمایش حالت READY پس از مقداردهی نمایشی."); }
});

document.addEventListener("change", (event) => {
  if (event.target.id === "new-run-type") {
    state.newRunType = event.target.value;
    $("#overlay-root").innerHTML = newRunModal();
  }
});

function updateClock() {
  $("#current-time").textContent = new Intl.DateTimeFormat("fa-IR", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date());
}

updateClock();
window.setInterval(updateClock, 1000);
render();
