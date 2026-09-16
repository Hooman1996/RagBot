import { Check, CircleNotch, Minus, Warning, X } from "@phosphor-icons/react";
import type { RunSession } from "../../types/api";
import { matrixState, type LoadedAttempt, type MatrixState } from "./stabilityModel";

const labels: Record<MatrixState, string> = { baseline: "مبنا", same: "یکسان", different: "متفاوت", error: "خطا", unavailable: "ناموجود" };
const icons = { baseline: Minus, same: Check, different: X, error: Warning, unavailable: CircleNotch };

export function StabilityMatrix({ sessions, attempts, selectedTurn, onTurnSelect }: { sessions: RunSession[]; attempts: LoadedAttempt[]; selectedTurn: number; onTurnSelect: (turn: number) => void }) {
  const repeats = [...sessions].sort((a, b) => a.repeat_index - b.repeat_index);
  const maxTurns = Math.max(0, ...sessions.map((session) => session.turn_count));
  const turns = Array.from({ length: maxTurns }, (_, index) => index + 1);
  const byCell = new Map(attempts.map((attempt) => [`${attempt.session.repeat_index}:${attempt.turn.turn_index}`, attempt]));
  const baselineRepeat = repeats[0]?.repeat_index;
  return <section className="stability-matrix surface" aria-labelledby="matrix-title">
    <div className="surface-header"><div><h2 id="matrix-title">ماتریس تکرار</h2><p>هر سلول با trace واقعی همان نوبت و نسبت به نخستین تکرار مقایسه می‌شود.</p></div><div className="matrix-legend">{(["same", "different", "error", "unavailable"] as MatrixState[]).map((state) => { const Icon = icons[state]; return <span key={state} className={`matrix-key is-${state}`}><Icon />{labels[state]}</span>; })}</div></div>
    <div className="matrix-scroll"><table className="matrix-table"><thead><tr><th>نوبت منطقی</th>{repeats.map((session) => <th key={session.id} dir="ltr">Repeat {session.repeat_index}</th>)}</tr></thead><tbody>{turns.map((turn) => <tr key={turn} className={selectedTurn === turn ? "is-selected" : ""}><th><button type="button" onClick={() => onTurnSelect(turn)}>نوبت {turn}</button></th>{repeats.map((session) => { const attempt = byCell.get(`${session.repeat_index}:${turn}`); const baseline = byCell.get(`${baselineRepeat}:${turn}`); const state = !attempt && (session.status === "FAILED" || session.status === "CANCELLED") ? "error" : matrixState(attempt, baseline, session.repeat_index === baselineRepeat); const Icon = icons[state]; return <td key={session.id}><button type="button" className={`matrix-cell is-${state}`} onClick={() => onTurnSelect(turn)} aria-label={`نوبت ${turn}، تکرار ${session.repeat_index}: ${labels[state]}`}><Icon weight={state === "same" ? "bold" : "regular"} /><span>{labels[state]}</span></button></td>; })}</tr>)}</tbody></table></div>
  </section>;
}
