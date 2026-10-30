import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Loader2 } from "lucide-react";
import { Button } from "./Button";
import { api, setCsrf } from "./api";
import { CrawlTool } from "./CrawlTool";
import "./style.css";

function App() {
  const [boot, setBoot] = useState(true),
    [setup, setSetup] = useState(false),
    [username, setUsername] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const expired = () => {
      setUsername("");
      setError("Phiên đăng nhập hết hạn. Vui lòng đăng nhập lại.");
    };
    window.addEventListener("session-expired", expired);
    api("/setup")
      .then(async (result) => {
        setSetup(result.required);
        if (!result.required) {
          try {
            const user = await api("/auth/me");
            setUsername(user.username);
            setCsrf(user.csrf);
          } catch {
            /* Show login. */
          }
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setBoot(false));
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  async function authenticate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const user = await api(setup ? "/setup" : "/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      setCsrf(user.csrf);
      setUsername(user.username);
      setSetup(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setUsername("");
      setCsrf("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (boot)
    return (
      <div className="boot">
        <Loader2 className="spin" size={18} />
        Đang kết nối…
      </div>
    );
  if (username)
    return (
      <>
        <CrawlTool username={username} onLogout={logout} />
        {error && (
          <div className="global-error" role="alert">
            {error}
          </div>
        )}
      </>
    );
  return (
    <div className="auth">
      <main className="auth-form">
        <div className="auth-brand">LeadFinder</div>
        <h1>{setup ? "Tạo tài khoản quản trị" : "Đăng nhập"}</h1>
        <p>
          {setup
            ? "Thiết lập tài khoản đầu tiên cho công ty."
            : "Đăng nhập để thu thập dữ liệu."}
        </p>
        <form onSubmit={authenticate}>
          <label>
            Tên đăng nhập
            <input
              name="username"
              required
              autoFocus
              minLength={3}
              maxLength={100}
              autoComplete="username"
              placeholder="Tên đăng nhập"
            />
          </label>
          <label>
            Mật khẩu
            <input
              name="password"
              type="password"
              required
              minLength={12}
              maxLength={128}
              autoComplete={setup ? "new-password" : "current-password"}
              placeholder="Ít nhất 12 ký tự"
            />
          </label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <Button type="submit" disabled={busy}>
            {busy && <Loader2 size={16} className="spin" />}
            {setup ? "Tạo tài khoản" : "Đăng nhập"}
          </Button>
        </form>
        <small>
          Tên đăng nhập dùng chữ không dấu, số, dấu chấm, gạch dưới hoặc gạch
          ngang.
        </small>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
