(function () {
  "use strict";

  const main = document.getElementById("main");
  const historyList = document.getElementById("historyList");
  const historyEmpty = document.getElementById("historyEmpty");
  const historyPanel = document.getElementById("history");
  const menuBtn = document.getElementById("menuBtn");
  const toastEl = document.getElementById("toast");

  let currentId = null;
  let pollTimer = null;
  let tickTimer = null;

  // ---------------------------------------------------------- helpers

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function fmtDate(iso) {
    if (!iso) return "";
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (toastEl.hidden = true), 3000);
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* no body */ }
    if (!res.ok) throw new Error((data && data.error) || "Something went wrong. Try again.");
    return data;
  }

  function stopTimers() {
    clearInterval(pollTimer); clearInterval(tickTimer);
    pollTimer = tickTimer = null;
  }

  function focusMain() { main.focus({ preventScroll: true }); }

  // ---------------------------------------------------------- history

  async function loadHistory() {
    const rows = await api("/api/reviews");
    historyList.innerHTML = "";
    historyEmpty.hidden = rows.length > 0;
    rows.forEach((r) => {
      const li = document.createElement("li");
      const chip = r.status === "done" ? `<span class="chip" title="Grade ${r.overall} of 5">${r.overall}</span>`
        : r.status === "running" ? `<span class="chip run">…</span>`
        : `<span class="chip err" title="Failed">!</span>`;
      li.innerHTML = `<button class="history-item" data-id="${r.id}"${r.id === currentId ? ' aria-current="true"' : ""}>
        <span class="t">${esc(r.title)}</span>${`<span class="g">${chip}</span>`}
        <span class="d">${esc(fmtDate(r.created_at))}</span></button>`;
      historyList.appendChild(li);
    });
  }

  historyList.addEventListener("click", (e) => {
    const btn = e.target.closest(".history-item");
    if (btn) { showReview(Number(btn.dataset.id)); closeMenu(); }
  });

  function markCurrent() {
    historyList.querySelectorAll(".history-item").forEach((b) => {
      if (Number(b.dataset.id) === currentId) b.setAttribute("aria-current", "true");
      else b.removeAttribute("aria-current");
    });
  }

  function closeMenu() { historyPanel.classList.remove("open"); menuBtn.setAttribute("aria-expanded", "false"); }
  menuBtn.addEventListener("click", () => {
    const open = historyPanel.classList.toggle("open");
    menuBtn.setAttribute("aria-expanded", String(open));
  });

  // ---------------------------------------------------------- upload view

  function showNew(errorMsg) {
    stopTimers();
    currentId = null;
    markCurrent();
    const files = { solicitation: null, proposal: null };

    main.innerHTML = `
      <h1>New review</h1>
      <p class="lede">Add the funding solicitation and the draft proposal. PDF or text files, up to 25 MB each.</p>
      <form class="upload" id="uploadForm" novalidate>
        <div class="drops">
          ${dropHtml("solicitation", "Solicitation", "The call for proposals")}
          ${dropHtml("proposal", "Proposal", "The draft to review")}
        </div>
        <div class="field">
          <label for="title">Review name <span style="font-weight:400;color:var(--muted)">(optional)</span></label>
          <input id="title" name="title" type="text" maxlength="200" placeholder="Uses the proposal file name if left blank">
        </div>
        <div id="formError"></div>
        <div class="actions"><button class="btn primary" id="submitBtn" type="submit" disabled>Start review</button></div>
      </form>`;

    const form = document.getElementById("uploadForm");
    const submitBtn = document.getElementById("submitBtn");
    const errBox = document.getElementById("formError");
    if (errorMsg) errBox.innerHTML = `<p class="msg-error" role="alert">${esc(errorMsg)}</p>`;

    function refresh() { submitBtn.disabled = !(files.solicitation && files.proposal); }

    function setFile(kind, file) {
      const zone = form.querySelector(`.drop[data-kind="${kind}"]`);
      files[kind] = file;
      zone.classList.toggle("filled", !!file);
      zone.querySelector(".sub").hidden = !!file;
      const fileEl = zone.querySelector(".file");
      fileEl.hidden = !file;
      fileEl.textContent = file ? file.name : "";
      refresh();
    }

    form.querySelectorAll(".drop").forEach((zone) => {
      const kind = zone.dataset.kind;
      const input = zone.querySelector("input");
      input.addEventListener("change", () => setFile(kind, input.files[0] || null));
      ["dragenter", "dragover"].forEach((ev) =>
        zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("over"); }));
      ["dragleave", "drop"].forEach((ev) =>
        zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
      zone.addEventListener("drop", (e) => {
        const f = e.dataTransfer.files[0];
        if (f) setFile(kind, f);
      });
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!(files.solicitation && files.proposal)) return;
      submitBtn.disabled = true;
      submitBtn.textContent = "Uploading…";
      errBox.innerHTML = "";
      const fd = new FormData();
      fd.append("solicitation", files.solicitation);
      fd.append("proposal", files.proposal);
      fd.append("title", form.title.value);
      try {
        const { id } = await api("/api/reviews", { method: "POST", body: fd });
        await loadHistory();
        showReview(id);
      } catch (err) {
        errBox.innerHTML = `<p class="msg-error" role="alert">${esc(err.message)}</p>`;
        submitBtn.textContent = "Start review";
        refresh();
      }
    });
    focusMain();
  }

  function dropHtml(kind, label, sub) {
    return `<label class="drop" data-kind="${kind}">
      <input type="file" name="${kind}" accept=".pdf,.txt,.md,application/pdf,text/plain" aria-label="${label} file">
      <span class="label">${label}</span>
      <span class="sub">${sub}. Drag a file here or click to browse.</span>
      <span class="file" hidden></span>
    </label>`;
  }

  // ---------------------------------------------------------- review view

  async function showReview(id) {
    stopTimers();
    currentId = id;
    markCurrent();
    let r;
    try { r = await api(`/api/reviews/${id}`); }
    catch (err) { toast(err.message); showNew(); return; }

    if (r.status === "running") { renderRunning(r); startPolling(id, r.created_at); }
    else if (r.status === "error") renderError(r);
    else renderResult(r);
    focusMain();
  }

  function renderRunning(r) {
    main.innerHTML = `
      <h1>${esc(r.title)}</h1>
      <p class="meta">${esc(r.proposal_name)} reviewed against ${esc(r.solicitation_name)}</p>
      <section class="running" aria-live="polite">
        <h2>Reviewing the proposal</h2>
        <p>The model is reading both documents and scoring each rubric criterion. This can take a few minutes. You can leave this page; the result will be in your history.</p>
        <div class="bar" role="progressbar" aria-label="Review in progress"></div>
        <p>Elapsed <span class="elapsed" id="elapsed">0:00</span></p>
      </section>`;
    const start = new Date(r.created_at).getTime();
    const tick = () => {
      const el = document.getElementById("elapsed");
      if (!el) return;
      const s = Math.max(0, Math.floor((Date.now() - start) / 1000));
      el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };
    tick();
    tickTimer = setInterval(tick, 1000);
  }

  function startPolling(id) {
    pollTimer = setInterval(async () => {
      if (currentId !== id) { stopTimers(); return; }
      try {
        const r = await api(`/api/reviews/${id}`);
        if (r.status !== "running") {
          stopTimers();
          await loadHistory();
          if (currentId === id) { r.status === "error" ? renderError(r) : renderResult(r); focusMain(); }
        }
      } catch (_) { /* transient; try again next tick */ }
    }, 2500);
  }

  function renderError(r) {
    main.innerHTML = `
      <h1>${esc(r.title)}</h1>
      <p class="meta">${esc(r.proposal_name)} reviewed against ${esc(r.solicitation_name)}</p>
      <p class="msg-error" role="alert"><strong>The review didn't finish.</strong> ${esc(r.error || "Unknown error.")}</p>
      <p class="lede" style="margin-top:12px">If you're running the local model, check that Ollama is running, then start a new review.</p>
      <div class="foot">
        <button class="btn primary" id="again">Start a new review</button>
        <button class="btn danger" id="del">Delete this review</button>
      </div>`;
    document.getElementById("again").onclick = () => showNew();
    document.getElementById("del").onclick = () => deleteReview(r.id);
  }

  function segs(score) {
    return `<div class="segs" aria-hidden="true">${[1, 2, 3, 4, 5].map((n) => `<i class="${n <= score ? "on" : ""}"></i>`).join("")}</div>`;
  }

  function renderResult(r) {
    const res = r.result || {};
    const crit = (res.criteria || []).map((c) => `
      <li class="criterion">
        <div class="row"><span class="name">${esc(c.name)}</span><span class="score">${c.score} of 5</span></div>
        ${segs(c.score)}
        <p>${esc(c.comment)}</p>
      </li>`).join("");
    const list = (items) => items.map((s) => `<li>${esc(s)}</li>`).join("");

    main.innerHTML = `
      <div class="result-head">
        <div class="grade" aria-label="Overall grade ${r.overall} out of 5">
          <span class="num">${r.overall}</span>
          <div class="rail" aria-hidden="true">${[1, 2, 3, 4, 5].map((n) => `<i class="${n <= r.overall ? "on" : ""}"></i>`).join("")}</div>
          <span class="of">out of 5</span>
        </div>
        <div>
          <h1>${esc(r.title)}</h1>
          <p class="meta">${esc(r.proposal_name)} reviewed against ${esc(r.solicitation_name)} on ${esc(fmtDate(r.finished_at))}</p>
          <p class="summary">${esc(res.summary || "")}</p>
        </div>
      </div>
      <section class="section"><h2>Scores by criterion</h2><ul class="criteria">${crit}</ul></section>
      ${(res.strengths || []).length || (res.improvements || []).length ? `<section class="section two">
        <div class="list-card strengths"><h3>Strengths</h3><ul>${list(res.strengths || []) || "<li>None noted.</li>"}</ul></div>
        <div class="list-card improve"><h3>Suggested improvements</h3><ul>${list(res.improvements || []) || "<li>None noted.</li>"}</ul></div>
      </section>` : ""}
      <div class="foot">
        <button class="btn primary" id="again">New review</button>
        <button class="btn" id="print">Print or save as PDF</button>
        <button class="btn danger" id="del">Delete</button>
      </div>`;
    document.getElementById("again").onclick = () => showNew();
    document.getElementById("print").onclick = () => window.print();
    document.getElementById("del").onclick = () => deleteReview(r.id);
  }

  async function deleteReview(id) {
    if (!confirm("Delete this review? This can't be undone.")) return;
    try {
      await api(`/api/reviews/${id}`, { method: "DELETE" });
      toast("Review deleted");
      await loadHistory();
      showNew();
    } catch (err) { toast(err.message); }
  }

  // ---------------------------------------------------------- start

  document.getElementById("newBtn").addEventListener("click", () => { showNew(); closeMenu(); });

  loadHistory().then(() => showNew()).catch(() => {});
})();