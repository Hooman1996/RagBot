import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../app/auth";
import { ErrorState, SkeletonRows } from "./ui/States";

export function DatasourcePicker({ selected, onChange }: { selected: string[]; onChange: (value: string[]) => void }) {
  const { api } = useAuth();
  const query = useQuery({ queryKey: ["datasources"], queryFn: api.datasources });
  if (query.isLoading) return <SkeletonRows count={2} />;
  if (query.isError) return <ErrorState title="منابع دانش قابل دریافت نیستند" error={query.error} retry={() => void query.refetch()} />;
  return (
    <fieldset className="source-picker">
      <legend>منابع دانش برای اجرا</legend>
      <p>همان عناوین فعلی پایگاه دانش که مسیر واقعی RagBot استفاده می‌کند.</p>
      <div className="source-options">
        {query.data?.map(({ title }) => <label key={title}><input type="checkbox" checked={selected.includes(title)} onChange={(event) => onChange(event.target.checked ? [...selected, title] : selected.filter((item) => item !== title))} /><span dir="auto">{title}</span></label>)}
      </div>
      {!query.data?.length && <p className="field-error">هیچ منبع دانشی در بک‌اند گزارش نشده است.</p>}
    </fieldset>
  );
}
