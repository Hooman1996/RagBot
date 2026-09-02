import { Database, LockKey, Wrench } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type PropsWithChildren } from "react";
import { useAuth } from "../../app/auth";
import { Button } from "../ui/Button";
import { Modal } from "../ui/Modal";
import { ErrorState, SkeletonRows } from "../ui/States";

const CONFIRMATION = "CREATE_EVALUATION_TABLES";

export function DatabaseGate({ children }: PropsWithChildren) {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const status = useQuery({ queryKey: ["database-status"], queryFn: api.databaseStatus });
  const initialize = useMutation({
    mutationFn: api.initializeDatabase,
    onSuccess: async () => {
      setModalOpen(false);
      setConfirmation("");
      await queryClient.invalidateQueries({ queryKey: ["database-status"] });
    },
  });

  if (status.isLoading) return <main className="gate-page"><section className="gate-panel"><SkeletonRows count={3} /></section></main>;
  if (status.isError) return (
    <main className="gate-page"><section className="gate-panel">
      <ErrorState title="وضعیت پایگاه داده قابل دریافت نیست" error={status.error} retry={() => void status.refetch()} />
    </section></main>
  );
  if (status.data?.status === "READY") return <>{children}</>;

  const data = status.data!;
  const upgrade = data.status === "UPGRADE_REQUIRED";
  return (
    <main className="gate-page">
      <section className="gate-panel" aria-labelledby="db-title">
        <div className="gate-icon">{upgrade ? <Wrench size={34} /> : <Database size={34} />}</div>
        <p className="kicker">Evaluation Database Setup</p>
        <h1 id="db-title">{upgrade ? "جداول ارزیابی نیاز به ارتقا دارند" : data.status === "ERROR" ? "بررسی پایگاه داده ناموفق بود" : "پایگاه داده ارزیابی راه‌اندازی نشده است"}</h1>
        <p>{upgrade ? "ساختار فعلی قدیمی‌تر از نسخه مورد نیاز این کنسول است." : "جداول اختصاصی evaluation هنوز ایجاد نشده‌اند. هیچ جدول گفت‌وگوی اصلی تغییر نمی‌کند."}</p>
        {upgrade && <dl className="revision-grid"><div><dt>نسخه فعلی</dt><dd dir="ltr">{data.current_revision || "-"}</dd></div><div><dt>نسخه مورد نیاز</dt><dd dir="ltr">{data.required_revision || "-"}</dd></div></dl>}
        {data.error_code && <div className="inline-code" dir="ltr">{data.error_code}</div>}
        {!!data.missing_objects.length && <details className="disclosure"><summary>اشیای ارزیابی موجود نیستند ({data.missing_objects.length})</summary><pre dir="ltr">{data.missing_objects.join("\n")}</pre></details>}
        {data.allow_initialize ? (
          <Button onClick={() => setModalOpen(true)}>{upgrade ? "ارتقای جداول ارزیابی" : "ایجاد جداول ارزیابی"}</Button>
        ) : (
          <div className="operator-note"><LockKey size={22} /><div><strong>راه‌اندازی از رابط غیرفعال است</strong><p>اپراتور باید <code>EVAL_ALLOW_DB_INIT=true</code> را در فایل ریشه <code>.env</code> تنظیم کند، برنامه RagBot را در چرخه استقرار عادی بعدی راه‌اندازی مجدد کند و سپس این صفحه را بازخوانی کند. امکان اجرای SQL دلخواه در این رابط وجود ندارد.</p></div></div>
        )}
        <div className="button-row"><Button variant="secondary" onClick={() => void status.refetch()}>بررسی دوباره</Button></div>
      </section>
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={upgrade ? "تأیید ارتقای جداول" : "تأیید ایجاد جداول"} footer={<><Button variant="secondary" onClick={() => setModalOpen(false)}>انصراف</Button><Button onClick={() => initialize.mutate()} disabled={confirmation !== CONFIRMATION || initialize.isPending}>{initialize.isPending ? "در حال اجرا…" : upgrade ? "ارتقا" : "ایجاد جداول"}</Button></>}>
        <p>بک‌اند فقط مهاجرت‌های از پیش تعریف‌شده را تحت قفل پایگاه داده اجرا می‌کند. عبارت زیر را برای تأیید وارد کنید:</p>
        <label className="field-stack"><span dir="ltr">{CONFIRMATION}</span><input dir="ltr" autoFocus value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
        {initialize.isError && <ErrorState title="مهاجرت اجرا نشد" error={initialize.error} />}
      </Modal>
    </main>
  );
}
