import { UserCircle } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../../app/auth";
import { Button } from "../ui/Button";
import { ErrorState } from "../ui/States";

export function AccessGate() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setPending(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  };
  return (
    <main className="access-page">
      <section className="access-panel" aria-labelledby="access-title">
        <div className="access-mark"><UserCircle size={28} weight="duotone" /></div>
        <p className="kicker">RagBot Evaluation</p>
        <h1 id="access-title">ورود به کنسول ارزیابی</h1>
        <p>با همان نام کاربری و رمز عبور RagBot وارد شوید. سامانه ارزیابی جدول کاربر جداگانه‌ای ندارد.</p>
        <form onSubmit={submit} className="field-stack">
          <label htmlFor="ragbot-username">نام کاربری</label>
          <input id="ragbot-username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
          <label htmlFor="ragbot-password">رمز عبور</label>
          <input id="ragbot-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
          <Button type="submit" disabled={!username.trim() || !password || pending}>{pending ? "در حال ورود…" : "ورود با حساب RagBot"}</Button>
          {error !== null && <ErrorState title="ورود ناموفق بود" error={error} />}
        </form>
      </section>
    </main>
  );
}
