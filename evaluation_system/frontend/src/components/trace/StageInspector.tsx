import { ArrowDown, ArrowUp, CaretDown, CaretLeft, CheckCircle, Copy, MinusCircle, WarningCircle } from "@phosphor-icons/react";
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

function History({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  const messages = asList(output.messages_used);
  return <div className="artifact-columns"><Definition label="تعداد پیام">{String(metrics.history_message_count ?? messages.length)}</Definition><Definition label="تاریخچه واقعی موجود است">{output.real_history_exists === true ? "بله" : output.real_history_exists === false ? "خیر" : "ناموجود"}</Definition><section className="span-all"><h4>پیام‌های استفاده‌شده</h4>{messages.length ? <div className="prompt-messages">{messages.map((message, index) => <article key={index}><strong dir="ltr">{String(message.role ?? `message-${index + 1}`)}</strong><p dir="auto">{String(message.content ?? "")}</p></article>)}</div> : <div className="empty-inline">پیامی در trace ثبت نشده است.</div>}</section>{output.formatted_history != null && <section className="span-all"><details className="disclosure"><summary>تاریخچه قالب‌بندی‌شده</summary><TextBlock value={output.formatted_history} /></details></section>}</div>;
}

function Intent({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics); const input = asRecord(stage.input_data);
  return <dl className="definition-grid"><Definition label="ورودی طبقه‌بند">{String(input.classifier_input ?? input.query ?? "-")}</Definition><Definition label="برچسب">{String(output.type ?? output.label ?? output.intent ?? "-")}</Definition><Definition label="امتیاز">{String(output.score ?? output.confidence ?? metrics.score ?? "-")}</Definition><Definition label="آستانه مؤثر">{String(metrics.effective_threshold ?? metrics.threshold ?? "-")}</Definition></dl>;
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
  if (!candidates.length) return <div className="empty-inline">نتیجه بازیابی در trace ثبت نشده است.</div>;
  return <div><h3 className="inspector-section-title">نتایج بازیابی پیش از Rerank</h3><dl className="definition-grid"><Definition label="پرسش دقیق بازیابی">{String(input.retrieval_query ?? input.query ?? "-")}</Definition><Definition label="تعداد کاندیدا">{candidates.length}</Definition><Definition label="اسناد مجاز">{Array.isArray(input.allowed_docs) ? input.allowed_docs.join("، ") : "-"}</Definition></dl><div className="table-wrap"><table className="data-table compact retrieval-table"><thead><tr><th>رتبه بازیابی</th><th>Chunk / Document ID</th><th>Retrieval Score</th><th>Source / Category</th><th>پیش‌نمایش محتوا</th><th>Selected</th><th></th></tr></thead><tbody>{candidates.map((candidate, index) => {
    const content = candidate.content ?? candidate.text ?? candidate.chunk_content;
    const metadata = asRecord(candidate.metadata); const id = candidateId(candidate, index); const reranked = rerankById.get(id);
    const accepted = reranked?.accepted; const selected = selectedIds.has(id);
    const source = metadata.document_name ?? metadata.source ?? candidate.source ?? metadata.category;
    const preview = typeof content === "string" ? content.slice(0, 140) : "-";
    return <tr key={id} className={open === index ? "is-expanded" : ""}><td>{String(candidate.rank ?? index + 1)}</td><td dir="ltr"><code>{id}</code></td><td dir="ltr">{String(candidate.retrieval_score ?? candidate.score ?? "-")}</td><td dir="auto">{String(source ?? "-")}</td><td className="content-preview" dir="auto">{preview}</td><td>{selected ? <Badge tone="success"><CheckCircle />Yes</Badge> : <Badge tone="neutral"><MinusCircle />No</Badge>}</td><td><button className="icon-button" aria-label="نمایش محتوای قطعه" onClick={() => setOpen(open === index ? null : index)}>{open === index ? <CaretDown /> : <CaretLeft />}</button>{open === index && <div className="row-expansion"><div className="chunk-content-head"><strong dir="auto">{String(candidate.question ?? candidate.title ?? metadata.question ?? metadata.title ?? "Retrieved chunk")}</strong>{reranked && <Badge tone={accepted === false ? "warning" : "neutral"}>{accepted === false ? "Reranker removed" : `Rerank #${String(reranked.output_rank ?? "-")}`}</Badge>}</div><TextBlock value={content} /><TextBlock value={metadata} code /></div>}</td></tr>;
  })}</tbody></table></div></div>;
}

function Rerank({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const input = asRecord(stage.input_data); const metrics = asRecord(stage.metrics);
  const rankings = asList(output.rankings ?? output.candidates ?? output.results);
  if (stage.status === "SKIPPED") return <div className="skip-note"><span>این مرحله در مسیر واقعی اجرا نشده است.</span><TextBlock value={stage.metrics ?? stage.output_data} code /></div>;
  if (!rankings.length) return <div className="empty-inline">رتبه‌بندی خروجی در trace ثبت نشده است.</div>;
  const inputs = asList(input.candidates); const byId = new Map(inputs.map((row, index) => [candidateId(row, index), row]));
  return <div><Definition label="تعداد انتخاب‌شده">{String(metrics.selected_count ?? "-")}</Definition><div className="table-wrap"><table className="data-table compact"><thead><tr><th>رتبه اولیه</th><th>رتبه جدید</th><th>تغییر</th><th>Chunk ID</th><th>Source</th><th>Retrieval Score</th><th>Reranker Score</th></tr></thead><tbody>{rankings.map((item, index) => {
    const initial = Number(item.original_rrf_rank ?? item.input_rank ?? item.initial_rank ?? index + 1); const next = Number(item.reranker_rank ?? item.output_rank ?? item.rank ?? index + 1); const delta = initial - next;
    const id = candidateId(item, index); const original = byId.get(id) || {}; const metadata = asRecord(item.metadata ?? original.metadata);
    return <tr key={id}><td>#{initial}</td><td>#{next}</td><td>{delta > 0 ? <span className="rank-up">#{initial} → #{next} <ArrowUp />{delta}</span> : delta < 0 ? <span className="rank-down">#{initial} → #{next} <ArrowDown />{Math.abs(delta)}</span> : <span>#{initial} → #{next} 0</span>}</td><td dir="ltr"><code>{id}</code></td><td>{String(metadata.document_name ?? metadata.source ?? "-")}</td><td dir="ltr">{String(item.hybrid_score ?? item.retrieval_score ?? original.hybrid_score ?? original.retrieval_score ?? original.score ?? "-")}</td><td dir="ltr">{String(item.reranker_score ?? item.score ?? "-")}</td></tr>;
  })}</tbody></table></div></div>;
}

function Context({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  const ids = output.selected_chunk_ids ?? output.chunk_ids;
  const context = output.selected_context ?? output.context;
  return <div className="artifact-columns"><section><h4>SELECTED FOR LLM</h4><TextBlock value={ids} code /></section><section><h4>selected_context_hash</h4><code className="hash" dir="ltr" title={String(metrics.selected_context_hash ?? stage.output_hash ?? "-")}>{String(metrics.selected_context_hash ?? stage.output_hash ?? "-")}</code></section><section className="span-all"><h4>زمینه دقیق انتخاب‌شده</h4>{context == null ? <div className="empty-inline">متن زمینه در trace ثبت نشده است.</div> : <TextBlock value={context} />}</section></div>;
}

function Prompt({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  const messages = asList(output.prompt ?? output.messages);
  return <div className="artifact-columns"><section><h4>نسخه / منبع</h4><TextBlock value={metrics.prompt_version ?? metrics.prompt_source ?? output.prompt_version} code /></section><section><h4>هش پرامپت</h4><code className="hash" dir="ltr">{String(metrics.prompt_hash ?? stage.output_hash ?? "-")}</code></section><Definition label="تعداد پیام">{messages.length || "ناموجود"}</Definition><section className="span-all"><h4>پیام‌های پرامپت</h4>{messages.length ? <div className="prompt-messages">{messages.map((message, index) => <article key={index}><strong dir="ltr">{String(message.role ?? `message-${index + 1}`)}</strong><p dir="auto">{String(message.content ?? "")}</p></article>)}</div> : output.system_message != null || output.user_prompt != null ? <div className="prompt-messages">{output.system_message != null && <article><strong dir="ltr">system</strong><p dir="auto">{String(output.system_message)}</p></article>}{output.user_prompt != null && <article><strong dir="ltr">user</strong><p dir="auto">{String(output.user_prompt)}</p></article>}</div> : <div className="empty-inline">پیام ساختاریافته‌ای ثبت نشده است.</div>}</section></div>;
}

function Generation({ stage }: { stage: StageResult }) {
  const output = asRecord(stage.output_data); const metrics = asRecord(stage.metrics);
  return <div className="artifact-columns"><section className="span-all"><h4>پاسخ</h4><TextBlock value={output.answer ?? output.generated_answer} /></section><section><h4>مدل و پارامترها</h4><TextBlock value={metrics.settings ?? metrics.generation_settings ?? metrics} code /></section><section><h4>Fallback</h4><dl className="definition-grid"><Definition label="استفاده شده">{String(metrics.fallback_used ?? output.fallback_used ?? false)}</Definition><Definition label="علت">{String(metrics.fallback_reason ?? output.fallback_reason ?? "-")}</Definition></dl></section></div>;
}

export function StageInspector({ stage, stages = [] }: { stage: StageResult | undefined; stages?: StageResult[] }) {
  const [view, setView] = useState<"structured" | "raw">("structured");
  const [copied, setCopied] = useState<"input" | "output" | null>(null);
  if (!stage) return <div className="empty-inline">این مرحله در این trace موجود نیست.</div>;
  const copyHash = async (kind: "input" | "output", value: string | null) => {
    if (!value || !navigator.clipboard) return;
    await navigator.clipboard.writeText(value);
    setCopied(kind);
  };
  const body = (() => {
    switch (stage.stage_name) {
      case "NORMALIZATION": return <Normalization stage={stage} />;
      case "HISTORY": return <History stage={stage} />;
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
  return <section className="stage-inspector"><header><Badge tone={statusTone(stage.status)}>{stage.status}</Badge><span>{formatDuration(stage.duration_ms)}</span><div className="inspector-tabs" role="tablist"><button role="tab" aria-selected={view === "structured"} onClick={() => setView("structured")}>Structured</button><button role="tab" aria-selected={view === "raw"} onClick={() => setView("raw")}>Raw JSON</button></div></header><div className="stage-hashes"><HashValue label="input_hash" value={stage.input_hash} copied={copied === "input"} onCopy={() => void copyHash("input", stage.input_hash)} /><HashValue label="output_hash" value={stage.output_hash} copied={copied === "output"} onCopy={() => void copyHash("output", stage.output_hash)} /></div>{stage.status === "ERROR" && <div className="stage-error"><WarningCircle size={20} /><div><strong>Stage error</strong><p dir="ltr">{stage.error_code || "UNKNOWN_STAGE_ERROR"}</p></div></div>}{view === "structured" ? body : <JsonFallback stage={stage} />}{stage.error_data && <details className="disclosure"><summary>جزئیات امن خطا</summary><TextBlock value={stage.error_data} code /></details>}</section>;
}

function HashValue({ label, value, copied, onCopy }: { label: string; value: string | null; copied: boolean; onCopy: () => void }) {
  return <div><span>{label}</span><code dir="ltr" title={value || ""}>{value || "-"}</code>{value && <button type="button" className="icon-button" onClick={onCopy} aria-label={`کپی ${label}`} title={copied ? "کپی شد" : "کپی هش"}><Copy size={14} /></button>}</div>;
}
