import { CaretDown, CaretLeft, MagnifyingGlass } from "@phosphor-icons/react";
import { flexRender, getCoreRowModel, getFilteredRowModel, getPaginationRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { Fragment, useMemo, useState } from "react";
import type { RunSession } from "../../types/api";
import { Badge, statusTone } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/States";
import { formatDuration } from "../ui/format";
import { SessionResult } from "./SessionResult";

export function SessionTable({ sessions }: { sessions: RunSession[] }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [search, setSearch] = useState(""); const [status, setStatus] = useState("ALL"); const [fallback, setFallback] = useState("ALL");
  const filtered = useMemo(() => sessions.filter((item) => (status === "ALL" || item.status === status) && (fallback === "ALL" || (fallback === "YES" ? item.fallback_count > 0 : item.fallback_count === 0))), [fallback, sessions, status]);
  const columns = useMemo<ColumnDef<RunSession>[]>(() => [
    { id: "expand", header: "", cell: ({ row }) => <button className="icon-button" aria-label="باز کردن جلسه" aria-expanded={!!expanded[row.original.id]} onClick={() => setExpanded((value) => ({ ...value, [row.original.id]: !value[row.original.id] }))}>{expanded[row.original.id] ? <CaretDown /> : <CaretLeft />}</button> },
    { accessorFn: (row) => row.source_session_id || row.synthetic_label || "جلسه مصنوعی", id: "session", header: "جلسه", cell: (info) => <strong dir="auto">{String(info.getValue())}</strong> },
    { accessorKey: "turn_count", header: "نوبت" },
    { accessorKey: "first_query", header: "پرسش اول", cell: (info) => <span className="table-query" dir="auto">{String(info.getValue() || "-")}</span> },
    { accessorKey: "fallback_count", header: "Fallback" },
    { accessorKey: "error_count", header: "خطا", cell: ({ row }) => <span>{row.original.error_count}{row.original.infrastructure_error_count > 0 && <small className="infra-count"> {row.original.infrastructure_error_count} زیرساخت</small>}</span> },
    { accessorKey: "total_latency_ms", header: "مدت", cell: (info) => formatDuration(info.getValue<number | null>()) },
    { accessorKey: "status", header: "وضعیت", cell: (info) => <Badge tone={statusTone(String(info.getValue()))}>{String(info.getValue())}</Badge> },
  ], [expanded]);
  const table = useReactTable({ data: filtered, columns, state: { globalFilter: search }, onGlobalFilterChange: setSearch, getCoreRowModel: getCoreRowModel(), getFilteredRowModel: getFilteredRowModel(), getPaginationRowModel: getPaginationRowModel(), initialState: { pagination: { pageSize: 10 } } });
  if (!sessions.length) return <EmptyState title="نتیجه جلسه‌ای ثبت نشده است" message="با شروع اجرا، جلسه‌های تکمیل‌شده به تدریج در این بخش ظاهر می‌شوند." />;
  return <section className="results-table"><div className="table-tools"><label className="search-field"><MagnifyingGlass /><input aria-label="جست‌وجوی جلسه" placeholder="جست‌وجوی جلسه یا پرسش" value={search} onChange={(event) => setSearch(event.target.value)} /></label><select aria-label="فیلتر وضعیت" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">همه وضعیت‌ها</option><option value="COMPLETED">تکمیل‌شده</option><option value="RUNNING">در حال اجرا</option><option value="FAILED">ناموفق</option></select><select aria-label="فیلتر fallback" value={fallback} onChange={(event) => setFallback(event.target.value)}><option value="ALL">همه fallbackها</option><option value="YES">دارای fallback</option><option value="NO">بدون fallback</option></select></div>
    <div className="table-wrap"><table className="data-table"><thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.map((header) => <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map((row) => <Fragment key={row.id}><tr>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>{expanded[row.original.id] && <tr className="expanded-row"><td colSpan={columns.length}><SessionResult session={row.original} /></td></tr>}</Fragment>)}</tbody></table></div>
    <div className="pagination"><span>صفحه {table.getState().pagination.pageIndex + 1} از {Math.max(1, table.getPageCount())}</span><div><Button variant="secondary" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>قبلی</Button><Button variant="secondary" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>بعدی</Button></div></div>
  </section>;
}
