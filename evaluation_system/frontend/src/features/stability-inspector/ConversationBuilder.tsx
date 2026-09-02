import { ArrowDown, ArrowUp, Plus, Trash } from "@phosphor-icons/react";
import { Button } from "../../components/ui/Button";

export function ConversationBuilder({ queries, onChange }: { queries: string[]; onChange: (queries: string[]) => void }) {
  const update = (index: number, value: string) => onChange(queries.map((item, itemIndex) => itemIndex === index ? value : item));
  const move = (index: number, direction: -1 | 1) => {
    const next = [...queries]; const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };
  return <div className="conversation-builder">{queries.map((query, index) => <div className="conversation-turn" key={index}><div className="conversation-turn__label"><span>نوبت {index + 1}</span><div><button aria-label="انتقال به بالا" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp /></button><button aria-label="انتقال به پایین" disabled={index === queries.length - 1} onClick={() => move(index, 1)}><ArrowDown /></button>{queries.length > 1 && <button aria-label="حذف نوبت" onClick={() => onChange(queries.filter((_, itemIndex) => itemIndex !== index))}><Trash /></button>}</div></div><label><span>پرسش کاربر</span><textarea rows={2} dir="auto" value={query} onChange={(event) => update(index, event.target.value)} placeholder={index === 0 ? "درباره افتتاح حساب بگو" : "پرسش پیگیرانه را بنویسید"} /></label>{index < queries.length - 1 && <div className="history-connector">پاسخ تولیدشده وارد تاریخچه نوبت بعد می‌شود</div>}</div>)}<Button variant="secondary" onClick={() => onChange([...queries, ""])}><Plus />افزودن پرسش پیگیرانه</Button></div>;
}
