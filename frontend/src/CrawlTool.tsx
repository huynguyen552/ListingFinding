import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Button } from "./Button";
import { Loader2, Download, Search, Pause, Play, X } from "lucide-react";

type Place = {
  id: string;
  name: string;
  address: string;
  city: string;
  phone: string;
  website: string;
  tax_code: string;
  tax_status: string;
};
type Entry = {
  id: string;
  name: string;
  state: string;
  error: string;
  source_url: string;
  location: Place | null;
};
type Job = {
  id: string;
  keyword: string;
  area: string;
  target: number;
  enrich_website: boolean;
  status: string;
  message: string;
  found: number;
  warnings?: number;
  counts: Record<string, number>;
  created_at: string;
  entries?: Entry[];
};
const states: Record<string, string> = {
  queued: "Đang chờ",
  running: "Đang thu thập",
  pausing: "Đang tạm dừng",
  paused: "Đã tạm dừng",
  cancelling: "Đang hủy",
  cancelled: "Đã hủy",
  completed: "Hoàn thành",
  completed_with_errors: "Hoàn thành, có lỗi",
  no_results: "Chưa có kết quả phù hợp",
  blocked: "Nguồn yêu cầu xác minh",
  failed: "Có lỗi",
};
const activeStates = ["queued", "running", "pausing", "cancelling"];

export function CrawlTool({
  username,
  onLogout,
}: {
  username: string;
  onLogout: () => Promise<void>;
}) {
  const [keyword, setKeyword] = useState("quán ăn"),
    [area, setArea] = useState(""),
    [target, setTarget] = useState(20),
    [enrich, setEnrich] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]),
    [job, setJob] = useState<Job | null>(null),
    [selected, setSelected] = useState(""),
    [allData, setAllData] = useState(false),
    [saved, setSaved] = useState<{ items: Place[]; total: number }>({
      items: [],
      total: 0,
    }),
    [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [showIssues, setShowIssues] = useState(false),
    [evidence, setEvidence] = useState<any>(null);
  const requestKey = useRef(crypto.randomUUID());
  const active = jobs.some((j) => activeStates.includes(j.status));
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const data = await api<{ items: Job[] }>("/crawl-jobs");
        if (!alive) return;
        setJobs(data.items);
        if (!selected && data.items.length)
          setSelected(
            (
              data.items.find((j) => activeStates.includes(j.status)) ||
              data.items[0]
            ).id,
          );
        if (selected) {
          const detail = await api<Job>("/crawl-jobs/" + selected);
          if (alive) setJob(detail);
        }
        if (allData) {
          const locations = await api("/locations?page=" + page);
          if (alive) setSaved(locations);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      } finally {
        if (alive) timer = setTimeout(poll, 2500);
      }
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [selected, allData, page]);
  async function start(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const created = await api<Job>("/crawl-jobs", {
        method: "POST",
        body: JSON.stringify({
          keyword,
          area,
          target,
          enrich_website: enrich,
          request_key: requestKey.current,
        }),
      });
      requestKey.current = crypto.randomUUID();
      setSelected(created.id);
      setJob({ ...created, entries: [] });
      setAllData(false);
      setJobs((old) => [created, ...old.filter((j) => j.id !== created.id)]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function control(action: string) {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<Job>(`/crawl-jobs/${job.id}/${action}`, {
        method: "POST",
      });
      setJob((old) => ({ ...old, ...updated }));
      setJobs((old) => old.map((j) => (j.id === updated.id ? updated : j)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download(format: string) {
    setBusy(true);
    setError("");
    try {
      const params = new URLSearchParams({
        format,
        include_unverified_tax: "true",
      });
      if (!allData && job) params.set("crawl_job_id", job.id);
      const response = await fetch("/api/v1/exports/download?" + params);
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.message || "Chưa xuất được file.");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `leadfinder-${allData ? "all" : job?.id.slice(0, 8)}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage("Đã xuất file. MST chưa xác minh được ghi rõ trạng thái.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openEvidence(id: string) {
    try {
      setEvidence(await api("/locations/" + id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const resultEntries = (job?.entries || []).filter(
    (e) => e.state === "done" && e.location,
  );
  const issues = (job?.entries || []).filter((e) => e.error);
  const rows = allData
    ? saved.items
    : [
        ...new Map(
          resultEntries.map((e) => [e.location!.id, e.location!]),
        ).values(),
      ];
  return (
    <main className="tool">
      <header className="tool-header">
        <div>
          <h1>LeadFinder</h1>
          <p>Thu thập thông tin quán ăn, nhà hàng</p>
        </div>
        <div className="account">
          <span>{username}</span>
          <Button variant="outline" onClick={onLogout}>
            Đăng xuất
          </Button>
        </div>
      </header>
      <section className="section">
        <h2>Thu thập dữ liệu</h2>
        <form className="crawl-form" onSubmit={start}>
          <label>
            Từ khóa
            <input
              required
              minLength={2}
              maxLength={150}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="Quán ăn, café, nhà hàng…"
            />
          </label>
          <label>
            Khu vực
            <input
              required
              minLength={2}
              maxLength={150}
              value={area}
              onChange={(e) => setArea(e.target.value)}
              placeholder="Ví dụ: Đà Nẵng"
            />
            <small>
              Có thể nhập đường, phường và tỉnh/thành, ngăn bằng dấu phẩy. Muốn
              lấy cả đường qua nhiều phường, chỉ nhập tên đường và thành phố.
            </small>
          </label>
          <label>
            Số lượng mục tiêu
            <input
              type="number"
              min={1}
              max={200}
              required
              value={target}
              onChange={(e) => setTarget(Number(e.target.value))}
            />
          </label>
          <label>
            Nguồn
            <select disabled aria-label="Nguồn thu thập">
              <option>Google Maps</option>
            </select>
          </label>
          <div className="form-bottom">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={enrich}
                onChange={(e) => setEnrich(e.target.checked)}
              />
              Đọc thêm website để tìm MST và thông tin liên hệ
            </label>
            <Button type="submit" disabled={busy || active}>
              {busy ? (
                <Loader2 size={16} className="spin" />
              ) : (
                <Search size={16} />
              )}
              Bắt đầu thu thập
            </Button>
          </div>
        </form>
        <p className="hint">
          Không cần API key. Số lượng thực tế phụ thuộc kết quả công khai của
          Google. MST chỉ được lấy khi website có công bố và cần xác minh trước
          khi sử dụng.
        </p>
        <p className="hint">
          Ranh giới tham khảo (Quận 7 cũ, quận Tân Phú cũ, phường Tân Thuận): ©{" "}
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noreferrer"
          >
            OpenStreetMap contributors
          </a>
          .
        </p>
      </section>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      <section className="section">
        <div className="section-title">
          <h2>Tiến độ và kết quả</h2>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={allData}
              onChange={(e) => {
                setAllData(e.target.checked);
                setPage(1);
              }}
            />
            Xem tất cả dữ liệu đã lưu
          </label>
        </div>
        <div className="job-picker">
          <label>
            Đợt thu thập
            <select
              aria-label="Đợt thu thập"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setAllData(false);
                setJob(null);
              }}
            >
              <option value="">Chọn đợt thu thập</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.keyword} · {j.area} ·{" "}
                  {new Date(j.created_at).toLocaleString("vi-VN", {
                    timeZone: "Asia/Ho_Chi_Minh",
                  })}
                </option>
              ))}
            </select>
          </label>
          {job && !allData && (
            <div className="job-actions">
              {["queued", "running"].includes(job.status) && (
                <Button
                  disabled={busy}
                  variant="outline"
                  onClick={() => control("pause")}
                >
                  <Pause size={15} />
                  Tạm dừng
                </Button>
              )}
              {[
                "paused",
                "blocked",
                "failed",
                "completed_with_errors",
              ].includes(job.status) && (
                <Button
                  disabled={busy || active}
                  variant="outline"
                  onClick={() => control("resume")}
                >
                  <Play size={15} />
                  Tiếp tục
                </Button>
              )}
              {!!job.counts.skipped && !activeStates.includes(job.status) && (
                <Button
                  disabled={busy || active}
                  variant="outline"
                  onClick={() => control("retry-area")}
                >
                  Kiểm tra lại khu vực
                </Button>
              )}
              {!["completed", "cancelled", "no_results"].includes(
                job.status,
              ) && (
                <Button
                  disabled={busy || job.status === "cancelling"}
                  variant="outline"
                  onClick={() => control("cancel")}
                >
                  <X size={15} />
                  Hủy
                </Button>
              )}
            </div>
          )}
        </div>
        {job && !allData && (
          <div className="progress" aria-live="polite">
            <div>
              <b>
                {activeStates.includes(job.status) && (
                  <Loader2 className="spin" size={15} />
                )}{" "}
                {states[job.status] || job.status}
              </b>
              <span>
                Tìm thấy: {job.found} · Đã lưu: {job.counts.done || 0}/
                {job.target} · Bỏ qua: {job.counts.skipped || 0} · Lỗi:{" "}
                {job.counts.failed || 0}
                {job.warnings ? ` · Cảnh báo website: ${job.warnings}` : ""}
              </span>
            </div>
            <p>{job.message}</p>
            <progress max={job.target} value={job.counts.done || 0} />
            {job.status === "queued" && (
              <small>
                Đang chờ bộ thu thập. Bạn có thể tạm dừng hoặc hủy đợt này.
              </small>
            )}
          </div>
        )}
        <div className="result-bar">
          <span>
            {allData
              ? `${saved.total} địa điểm đã lưu`
              : `${rows.length} địa điểm đã thu thập`}
          </span>
          <div>
            <Button
              variant="outline"
              disabled={busy || !(allData ? saved.total : rows.length)}
              onClick={() => download("csv")}
            >
              <Download size={15} />
              CSV
            </Button>
            <Button
              variant="outline"
              disabled={busy || !(allData ? saved.total : rows.length)}
              onClick={() => download("xlsx")}
            >
              <Download size={15} />
              Excel
            </Button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Tên quán</th>
                <th>Số điện thoại</th>
                <th>Địa chỉ</th>
                <th>Website</th>
                <th>MST</th>
                <th>Nguồn</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((place) => (
                <tr key={place.id}>
                  <td>
                    <b>{place.name || "Chưa có tên"}</b>
                  </td>
                  <td>{place.phone || "—"}</td>
                  <td>{place.address || "—"}</td>
                  <td>
                    {place.website ? (
                      <a href={place.website} target="_blank" rel="noreferrer">
                        {place.website.replace(/^https?:\/\//, "")}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {place.tax_code || "—"}
                    {place.tax_code && (
                      <small>
                        {place.tax_status === "confirmed"
                          ? "Đã xác nhận"
                          : "Chưa xác minh"}
                      </small>
                    )}
                  </td>
                  <td>
                    <button
                      className="text-button"
                      onClick={() => openEvidence(place.id)}
                    >
                      Xem nguồn
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && (
            <p className="empty">
              {active
                ? "Đang tìm và đọc thông tin. Kết quả sẽ xuất hiện tại đây."
                : job && !allData
                  ? "Chưa lưu được địa điểm phù hợp. Xem thông báo bên dưới hoặc bấm Kiểm tra lại khu vực."
                  : "Nhập từ khóa và khu vực rồi bấm Bắt đầu thu thập."}
            </p>
          )}
        </div>
        {allData && saved.total > 20 && (
          <div className="pagination">
            <Button
              variant="outline"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Trang trước
            </Button>
            <span>Trang {page}</span>
            <Button
              variant="outline"
              disabled={page * 20 >= saved.total}
              onClick={() => setPage(page + 1)}
            >
              Trang sau
            </Button>
          </div>
        )}
        {!allData && issues.length > 0 && (
          <div className="issues">
            <button
              className="text-button"
              onClick={() => setShowIssues(!showIssues)}
            >
              {showIssues ? "Ẩn" : "Xem"} {issues.length} thông báo
            </button>
            {showIssues && (
              <ul>
                {issues.map((entry) => (
                  <li key={entry.id}>
                    <b>
                      {entry.state === "done"
                        ? "Đã lưu · Cảnh báo website"
                        : entry.state === "skipped"
                          ? "Bỏ qua"
                          : "Chưa đọc được"}
                    </b>
                    {": "}
                    <a href={entry.source_url} target="_blank" rel="noreferrer">
                      {entry.location?.name || entry.name || "Địa điểm"}
                    </a>
                    : {entry.error}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
      {evidence && (
        <div className="overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="source-title"
          >
            <div className="section-title">
              <h2 id="source-title">Nguồn — {evidence.name}</h2>
              <Button variant="outline" onClick={() => setEvidence(null)}>
                Đóng
              </Button>
            </div>
            <div className="evidence">
              {evidence.observations.map((o: any) => (
                <article key={o.id}>
                  <b>
                    {(
                      {
                        name: "Tên quán",
                        address: "Địa chỉ",
                        city: "Khu vực",
                        category: "Loại quán",
                        phone: "SĐT",
                        website: "Website",
                        tax_code: "MST",
                        email: "Email",
                        facebook: "Facebook",
                        zalo: "Zalo",
                        legal_name: "Tên pháp nhân",
                      } as Record<string, string>
                    )[o.field] || o.field}
                  </b>
                  <p>{o.value}</p>
                  {/^https?:\/\//.test(o.source_ref) ? (
                    <a href={o.source_ref} target="_blank" rel="noreferrer">
                      {o.source_ref}
                    </a>
                  ) : (
                    <small>{o.source_ref}</small>
                  )}
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
