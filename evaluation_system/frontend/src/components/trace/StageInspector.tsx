import { ArrowDown, ArrowUp, CaretDown, CaretLeft, CheckCircle, MinusCircle, WarningCircle } from "@phosphor-icons/react";
import { useState } from "react";
import type { StageResult } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { Definition } from "../ui/States";
import { asList, asRecord, formatDuration, shortHash } from "../ui/format";

function TextBlock({ value, code = false }: { value: unknown; code?: boolean }) {
  const text = value == null ? "-" : typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <pre className={code ? "artifact artifact--code" : "artifact"} dir="auto">{text}</pre>;
}

function JsonFallback({ stage }: { stage: StageResult }) {
  return <div className="artifact-columns"><section><h4>ورودی</h4><TextBlock value={stage.input_data} code /></section><section><h4>خروجی</h4><TextBlock value={stage.output_data} code /></section><section><h4>شاخص‌ها</h4><TextBlock value={stage.metrics} code /></section></div>;
}

function Normalization({ stage }: { stage: StageResult }) {
  const input = asRecord(stage.input_data); const output = asRecord(stage.output_data);
  const raw = input.raw_query; const normalized = output.normalized_query;
  return <dl className="definition-grid"><Definition label="پرسش خام">{String(raw ?? "-")}</Definition><Definition label="پرسش نرمال‌شده">{String(normalized ?? "-")}</Definition><Definition label="تغییر کرده">{raw === normalized ? "خیر" : "بله"}</Definition></dl>;
}

function Intent({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics); const input = asRecord(stage.input_data);
  return <dl className="definition-grid"><Definition label="ورودی طبقه‌بند">{String(input.classifier_input ?? input.query ?? "-")}</Definition><Definition label="برچسب">{String(output.label ?? output.intent ?? "-")}</Definition><Definition label="امتیاز">{String(output.score ?? output.confidence ?? metrics.score ?? "-")}</Definition><Definition label="آستانه مؤثر">{String(metrics.effective_threshold ?? metrics.threshold ?? "-")}</Definition></dl>;
}

function Rewrite({ stage }: { stage: StageResult }) {
  const input = asRecord(stage.input_data); const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  return <div className="artifact-columns"><section><h4>پرسش نرمال‌شده</h4><TextBlock value={input.normalized_query ?? input.original_query ?? input.current_query} /></section><section><h4>پرسش کانونی بازیابی</h4><TextBlock value={input.canonical_retrieval_query ?? input.original_query ?? input.current_query} /></section><section><h4>تاریخچه استفاده‌شده</h4><TextBlock value={input.history_used ?? input.history} /></section><section><h4>پرسش نهایی بازیابی</h4><TextBlock value={output.final_retrieval_query ?? output.rewritten_query ?? output.query} /></section><section><h4>پارامترهای مؤثر</h4><TextBlock value={metrics} code /></section></div>;
}

function candidateId(value: Record<string, unknown>, fallback: number): string {
  return String(value.chunk_id ?? value.candidate_id ?? value.id ?? value._trace_id ?? fallback);
}

function Retrieval({ stage, stages }: { stage: StageResult; stages: StageResult[] }) {
  const output = asRecord(stage.output_data); const input = asRecord(stage.input_data);
  const candidates = asList(output.candidates ?? output.results);
  const rerank = stages.find((item) => item.stage_name === "RERANK");
  const rerankRows = asList(asRecord(rerank?.output_data).rankings ?? asRecord(rerank?.output_data).candidates ?? asRecord(rerank?.output_data).results);
  const context = stages.find((item) => item.stage_name === "CONTEXT_SELECTION");
  const selectedIds = new Set(asList(asRecord(context?.output_data).selected_chunk_ids ?? asRecord(context?.output_data).chunk_ids).map(String));
  const rerankById = new Map(rerankRows.map((row, index) => [candidateId(row, index), row]));
  const [open, setOpen] = useState<number | null>(null);
  return <div><dl className="definition-grid"><Definition label="پرسش دقیق بازیابی">{String(input.retrieval_query ?? input.query ?? "-")}</Definition><Definition label="تعداد کاندیدا">{candidates.length}</Definition><Definition label="آستانه بازرتبه‌بندی">{String(asRecord(rerank?.metrics).threshold ?? asRecord(rerank?.metrics).effective_threshold ?? "-")}</Definition></dl><div className="table-wrap"><table className="data-table compact retrieval-table"><thead><tr><th>Rank</th><th>Chunk ID</th><th>Retrieval Score</th><th>Rerank Score</th><th>Selected</th><th>اثر Reranker</th><th></th></tr></thead><tbody>{candidates.map((candidate, index) => {
    const content = candidate.content ?? candidate.text ?? candidate.chunk_content;
    const metadata = asRecord(candidate.metadata); const id = candidateId(candidate, index); const reranked = rerankById.get(id);
    const accepted = reranked?.accepted; const selected = selectedIds.has(id); const inputRank = Number(reranked?.input_rank ?? candidate.rank ?? index + 1); const outputRank = reranked ? Number(reranked.output_rank ?? inputRank) : null; const delta = outputRank == null ? null : inputRank - outputRank;
    return <tr key={id} className={open === index ? "is-expanded" : ""}><td>{String(candidate.rank ?? index + 1)}</td><td dir="ltr"><code>{id}</code></td><td dir="ltr">{String(candidate.retrieval_score ?? candidate.score ?? "-")}</td><td dir="ltr">{String(reranked?.score ?? "-")}</td><td>{selected ? <Badge tone="success"><CheckCircle />Yes</Badge> : <Badge tone="neutral"><MinusCircle />No</Badge>}</td><td>{rerank?.status === "SKIPPED" ? <Badge tone="neutral">Skipped</Badge> : accepted === false ? <Badge tone="warning">Rejected</Badge> : accepted === true ? delta && delta > 0 ? <span className="rank-up"><ArrowUp />+{delta}</span> : delta && delta < 0 ? <span className="rank-down"><ArrowDown />{delta}</span> : <Badge tone="success">Kept</Badge> : <Badge tone="neutral">Not returned</Badge>}</td><td><button className="icon-button" aria-label="نمایش محتوای قطعه" onClick={() => setOpen(open === index ? null : index)}>{open === index ? <CaretDown /> : <CaretLeft />}</button>{open === index && <div className="row-expansion"><div className="chunk-content-head"><strong dir="auto">{String(candidate.question ?? candidate.title ?? metadata.question ?? metadata.title ?? "Retrieved chunk")}</strong><Badge tone={accepted === false ? "warning" : "neutral"}>{accepted === false ? "Reranker removed" : "Trace content"}</Badge></div><TextBlock value={content} /><TextBlock value={metadata} code /></div>}</td></tr>;
  })}</tbody></table></div></div>;
}

function Rerank({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  const rankings = asList(output.rankings ?? output.candidates ?? output.results);
  if (stage.status === "SKIPPED") return <div className="skip-note"><span>این مرحله در مسیر واقعی اجرا نشده است.</span><TextBlock value={stage.metrics ?? stage.output_data} code /></div>;
  return <div><Definition label="آستانه">{String(metrics.threshold ?? metrics.effective_threshold ?? "-")}</Definition><div className="table-wrap"><table className="data-table compact"><thead><tr><th>رتبه اولیه</th><th>رتبه جدید</th><th>شناسه</th><th>امتیاز</th><th>تغییر</th></tr></thead><tbody>{rankings.map((item, index) => {
    const initial = Number(item.input_rank ?? item.initial_rank ?? index + 1); const next = Number(item.output_rank ?? item.rank ?? index + 1); const delta = initial - next;
    return <tr key={String(item.chunk_id ?? item.candidate_id ?? index)}><td>{initial}</td><td>{next}</td><td dir="ltr"><code>{String(item.chunk_id ?? item.candidate_id ?? "-")}</code></td><td dir="ltr">{String(item.score ?? "-")}</td><td>{delta > 0 ? <span className="rank-up"><ArrowUp />{delta}</span> : delta < 0 ? <span className="rank-down"><ArrowDown />{Math.abs(delta)}</span> : "بدون تغییر"}</td></tr>;
  })}</tbody></table></div></div>;
}

function Context({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  const ids = output.selected_chunk_ids ?? output.chunk_ids;
  return <div className="artifact-columns"><section><h4>قطعات انتخاب‌شده به ترتیب</h4><TextBlock value={ids} code /></section><section><h4>هش زمینه</h4><code className="hash" dir="ltr">{String(metrics.selected_context_hash ?? stage.output_hash ?? "-")}</code></section><section className="span-all"><details className="disclosure"><summary>مشاهده متن دقیق زمینه</summary><TextBlock value={output.selected_context ?? output.context} /></details></section></div>;
}

function Prompt({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  return <div className="artifact-columns"><section><h4>نسخه / منبع</h4><TextBlock value={metrics.prompt_version ?? metrics.prompt_source ?? output.prompt_version} code /></section><section><h4>هش پرامپت</h4><code className="hash" dir="ltr">{String(metrics.prompt_hash ?? stage.output_hash ?? "-")}</code></section><section className="span-all"><details className="disclosure"><summary>مشاهده پرامپت دقیق ذخیره‌شده</summary><TextBlock value={output.prompt ?? output.final_prompt} /></details></section></div>;
}

function Generation({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  return <div className="artifact-columns"><section className="span-all"><h4>پاسخ</h4><TextBlock value={output.answer ?? output.generated_answer} /></section><section><h4>مدل و پارامترها</h4><TextBlock value={metrics.settings ?? metrics.generation_settings ?? metrics} code /></section><section><h4>Fallback</h4><dl className="definition-grid"><Definition label="استفاده شده">{String(metrics.fallback_used ?? output.fallback_used ?? false)}</Definition><Definition label="علت">{String(metrics.fallback_reason ?? output.fallback_reason ?? "-")}</Definition></dl></section></div>;
}

export function StageInspector({ stage, stages = [] }: { stage: StageResult | undefined; stages?: StageResult[] }) {
  if (!stage) return <div className="empty-inline">هنوز اثری برای این مرحله ثبت نشده است.</div>;
  const body = (() => {
    switch (stage.stage_name) {
      case "NORMALIZATION": return <Normalization stage={stage} />;
      case "INTENT": return <Intent stage={stage} />;
      case "REWRITE": return <Rewrite stage={stage} />;
      case "RETRIEVAL": return <Retrieval stage={stage} stages={stages} />;
      case "RERANK": return <Rerank stage={stage} />;
      case "CONTEXT_SELECTION": return <Context stage={stage} />;
      case "PROMPT_BUILD": return <Prompt stage={stage} />;
      case "GENERATION": return <Generation stage={stage} />;
      default: return <JsonFallback stage={stage} />;
    }
  })();
  return <section className="stage-inspector"><header><Badge tone={statusTone(stage.status)}>{stage.status}</Badge><span>{formatDuration(stage.duration_ms)}</span><code dir="ltr">in {shortHash(stage.input_hash)}</code><code dir="ltr">out {shortHash(stage.output_hash)}</code></header>{stage.status === "ERROR" && <div className="stage-error"><WarningCircle size={20} /><div><strong>Infrastructure Error</strong><p dir="ltr">{stage.error_code || "UNKNOWN_STAGE_ERROR"}</p></div></div>}{body}{stage.error_data && <details className="disclosure"><summary>جزئیات امن خطا</summary><TextBlock value={stage.error_data} code /></details>}</section>;
}
