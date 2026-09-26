/* Jere Biznis admin console — offline-first vitrine manager. */
const PRICE = 500;
const BASE = window.JERE_BIZNIS_BASE || "";
const OFFLINE_KEY = "jere_biznis_offline_queue";
const $ = (s) => document.querySelector(s);

function net() {
  const el = $("#network");
  if (el) el.textContent = navigator.onLine ? "● ONLINE" : "● OFFLINE";
}
window.addEventListener("online", () => {
  net();
  flushOfflineQueue()
    .then(() => { loadStatus(); loadLandingPages(); })
    .catch(() => {});
});
window.addEventListener("offline", net);
net();

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
const CSRF = () => (document.querySelector('meta[name="csrf-token"]') || { content: "" }).content;

function switchView(view) {
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.viewPanel !== view);
  });
  document.querySelectorAll("[data-view]").forEach((item) => {
    item.classList.toggle("is-active", item.dataset.view === view);
  });
}

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (options.body) headers["Content-Type"] = "application/json";
  headers["Accept"] = "application/json";
  headers["X-Requested-With"] = "XMLHttpRequest";
  headers["X-CSRFToken"] = CSRF();
  const r = await fetch(`${BASE}/api${path}`, Object.assign({}, options, { headers }));
  let data = {};
  try { data = await r.json(); } catch (_) { data = {}; }
  if (!r.ok) throw new Error(data.error || `Erè ${r.status}`);
  return data;
}

/* --- offline queue: data stays on the device, synced when online ---------- */
function readOfflineQueue() {
  try { return JSON.parse(localStorage.getItem(OFFLINE_KEY) || "[]"); } catch (_) { return []; }
}
function writeOfflineQueue(q) { localStorage.setItem(OFFLINE_KEY, JSON.stringify(q)); }
function queueOffline(op) { const q = readOfflineQueue(); q.push(op); writeOfflineQueue(q); }
async function flushOfflineQueue() {
  if (!navigator.onLine) return;
  const q = readOfflineQueue();
  if (!q.length) return;
  const remaining = [];
  for (const op of q) {
    try {
      await api(op.path, { method: op.method, body: JSON.stringify(op.body) });
    } catch (_) { remaining.push(op); }
  }
  writeOfflineQueue(remaining);
}

/* --- status / subscription reminder --------------------------------------- */
async function loadStatus() {
  try {
    const d = await api("/status");
    const r = $("#reminder");
    if (!r) return;
    if (d.reminder && d.reminder.status === "TRIAL" && d.landing_pages_count > 0) {
      r.classList.remove("hidden");
      $("#reminderText").textContent =
        `Votre essai gratuit se termine dans ${d.reminder.days_remaining} jour(s). ` +
        `L'abonnement sera de ${PRICE} Gkach/mois.`;
    } else if (d.reminder && d.reminder.status === "EXPIRED") {
      r.classList.remove("hidden");
      $("#reminderText").textContent =
        "Votre essai/abonnement est terminé. Kontakte administratè a pou renouvèlman nan Gkach.";
    } else {
      r.classList.add("hidden");
    }
  } catch (_e) {
    if ($("#reminder")) $("#reminder").classList.add("hidden");
  }
}

/* --- landing pages (vitrines) --------------------------------------------- */
let pagesById = {};
function isOwner(p) { return p && p.role === "OWNER"; }

function showLandingBuilder() {
  const f = $("#landingForm");
  if (!f) return;
  if (!$("#landingId").value) $("#landingFormTitle").textContent = "Nouvo vitrin";
  f.classList.remove("hidden");
  $("#landingName").focus();
}
function closeLandingBuilder() {
  const f = $("#landingForm");
  if (!f) return;
  f.classList.add("hidden");
  f.reset();
  $("#landingId").value = "";
}

function editLandingPage(id) {
  const p = pagesById[id];
  if (!p) return;
  $("#landingFormTitle").textContent = "Modifye vitrin lan";
  $("#landingId").value = p.id;
  $("#landingName").value = p.business_name;
  $("#landingType").value = p.business_type;
  $("#landingDescription").value = p.description || "";
  $("#landingPhone").value = p.phone || "";
  $("#landingAddress").value = p.address || "";
  $("#landingResult").textContent = "";
  showLandingBuilder();
}

async function saveLandingPage(event) {
  event.preventDefault();
  const id = Number($("#landingId").value || 0);
  const payload = {
    business_name: $("#landingName").value.trim(),
    business_type: $("#landingType").value,
    description: $("#landingDescription").value.trim(),
    phone: $("#landingPhone").value.trim(),
    address: $("#landingAddress").value.trim(),
  };
  const result = $("#landingResult");
  if (!payload.business_name) { result.textContent = "Non biznis la obligatwa."; return; }
  if (!navigator.onLine) {
    queueOffline({
      path: id ? `/landing-pages/${id}` : "/landing-pages",
      method: id ? "PUT" : "POST",
      body: payload,
    });
    result.textContent =
      "Ou se offline: done yo sove sou aparèy ou. Y ap senkronize lè koneksyon retounen.";
    return;
  }
  try {
    const r = await api(id ? `/landing-pages/${id}` : "/landing-pages", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    result.textContent = id ? "Modifikasyon an sove!" : `Vitrin kreye! Ouvri li a: ${BASE}${r.url}`;
    closeLandingBuilder();
    await loadLandingPages();
    await loadStatus();
  } catch (e) { result.textContent = e.message; }
}

async function togglePublished(id, current) {
  try {
    await api(`/landing-pages/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ published: !current }),
    });
    await loadLandingPages();
  } catch (e) { alert(e.message); }
}

async function deleteLandingPage(id) {
  if (!confirm("Elimine vitrin sa a? Aksyon sa a pa ka defèt.")) return;
  try {
    await api(`/landing-pages/${id}`, { method: "DELETE" });
    await loadLandingPages();
  } catch (e) { alert(e.message); }
}

function renderPages(pages) {
  pagesById = {};
  const list = $("#landingList");
  list.innerHTML = "";
  $("#landingEmpty").classList.toggle("hidden", pages.length > 0);
  for (const p of pages) {
    pagesById[p.id] = p;
    const li = document.createElement("li");
    li.className = "jb-landing-item";
    li.innerHTML = `
      <div class="jb-landing-head">
        <strong>${escapeHtml(p.business_name)}</strong>
        <span class="jb-badge ${isOwner(p) ? "jb-badge-owner" : "jb-badge-coadmin"}">${isOwner(p) ? "Mèt" : "Ko-Admin"}</span>
        <span class="jb-badge ${p.published ? "jb-badge-online" : "jb-badge-offline"}">${p.published ? "Pibliye" : "Pa pibliye"}</span>
      </div>
      <p class="jb-meta">${escapeHtml(p.business_type_label)}${p.address ? " · " + escapeHtml(p.address) : ""}</p>
      <p class="jb-url"><a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.url)}</a></p>
      <div class="jb-actions">
        <button type="button" class="jb-btn jb-btn-sm" onclick="editLandingPage(${p.id})">Modifye</button>
        <button type="button" class="jb-btn jb-btn-sm" onclick="togglePublished(${p.id}, ${p.published})">${p.published ? "Retire paj la" : "Pibliye"}</button>
        <button type="button" class="jb-btn jb-btn-sm" onclick="openAdminPanel(${p.id})">Admin yo</button>
        ${isOwner(p) ? `<button type="button" class="jb-btn jb-btn-sm jb-btn-danger" onclick="deleteLandingPage(${p.id})">Elimine</button>` : ""}
      </div>
    `;
    list.appendChild(li);
  }
}

async function loadLandingPages() {
  try {
    const pages = await api("/landing-pages");
    renderPages(pages);
    renderManagementPages(pages);
    localStorage.setItem("jere_biznis_landing_cache", JSON.stringify(pages));
  } catch (_e) {
    const cached = (() => {
      try { return JSON.parse(localStorage.getItem("jere_biznis_landing_cache") || "[]"); }
      catch (_x) { return []; }
    })();
    if (cached.length) {
      renderPages(cached);
      renderManagementPages(cached);
      $("#landingEmpty").textContent = "Lis offline — done ki sove sou aparèy ou.";
      $("#landingEmpty").classList.remove("hidden");
    } else {
      $("#landingEmpty").textContent = "Ou pa ka chaje lis vitrin yo pou kounye a. Tcheke koneksyon ou.";
      $("#landingEmpty").classList.remove("hidden");
    }
  }
}

function renderManagementPages(pages) {
  const recent = $("#recentPages");
  const team = $("#teamPages");
  if (recent) {
    recent.innerHTML = pages.slice(0, 4).map((p) =>
      `<div class="jb-recent-row"><span class="jb-recent-mark">${escapeHtml((p.business_name || "B").slice(0, 1).toUpperCase())}</span><div><strong>${escapeHtml(p.business_name)}</strong><small>${escapeHtml(p.business_type_label)} · ${p.published ? "Pibliye" : "Pa pibliye"}</small></div><button class="jb-text-button" onclick="switchView('showcases'); editLandingPage(${p.id})">Modifye</button></div>`
    ).join("") || `<p class="jb-muted">Pa gen vitrin ankò.</p>`;
  }
  if (team) {
    team.innerHTML = pages.map((p) => `<div class="jb-team-row"><div><strong>${escapeHtml(p.business_name)}</strong><small>${p.admins_count} administratè · ${p.role === "OWNER" ? "Mèt" : "Ko-admin"}</small></div><button class="jb-btn jb-btn-sm" onclick="openAdminPanel(${p.id})">Jere aksè</button></div>`).join("") || `<p class="jb-muted">Kreye yon vitrin pou kòmanse òganize ekip la.</p>`;
  }
}

async function loadOverview() {
  try {
    const d = await api("/overview");
    $("#metricBusinesses").textContent = d.business_count;
    $("#metricPublished").textContent = d.published_count;
    $("#metricTeam").textContent = d.team_count;
    $("#metricSubscription").textContent = d.subscription_status === "NO_PAGE" ? "—" : d.subscription_status;
    renderManagementPages(d.recent_pages || []);
  } catch (_) {}
}

/* --- subscription / Gkach billing ---------------------------------------- */
function currentPayIdem() {
  /* One idempotency key per payment INTENT: reused until a payment succeeds,
     so a network failure can never double-debit the wallet. */
  let k = localStorage.getItem("jere_biznis_pay_idem");
  if (!k) {
    k = "jb-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("jere_biznis_pay_idem", k);
  }
  return k;
}

function openBilling() {
  switchView("showcases");
  $("#billing").classList.remove("hidden");
  updateTotal();
  api("/subscription")
    .then((d) => {
      if (d.gkach_balance !== undefined) {
        $("#gkachBalance").textContent = `${d.gkach_balance} Gkach`;
      }
    })
    .catch(() => {});
}
function closeBilling() {
  $("#billing").classList.add("hidden");
}
function setMonths(n) {
  $("#subMonths").value = n;
  updateTotal();
}
function updateTotal() {
  const months = Math.max(1, Number($("#subMonths").value) || 1);
  $("#subTotal").textContent = months * PRICE;
}

async function paySubscription() {
  const months = Math.max(1, Number($("#subMonths").value) || 1);
  const result = $("#subResult");
  if (!navigator.onLine) {
    result.textContent = "Ou se offline — peman an mande yon koneksyon.";
    return;
  }
  result.textContent = "Peman an ap trete...";
  try {
    const r = await api("/subscription/pay", {
      method: "POST",
      body: JSON.stringify({ months, idempotency_key: currentPayIdem() }),
    });
    localStorage.removeItem("jere_biznis_pay_idem");
    if (r.status === "already_processed") {
      result.textContent = `Peman sa a deja pwosese (rese #${r.transaction_id}).`;
    } else {
      result.textContent =
        `Mèsi! Abonman an aktif jiska ${String(r.expiration).slice(0, 10)}. ` +
        `Balans: ${r.gkach_balance} Gkach.`;
    }
    if (r.gkach_balance !== undefined) {
      $("#gkachBalance").textContent = `${r.gkach_balance} Gkach`;
    }
    await loadStatus();
  } catch (e) { result.textContent = e.message; }
}

/* --- co-admins ----------------------------------------------------------- */
function closeAdminPanel() {
  $("#adminPanel").classList.add("hidden");
}

async function openAdminPanel(id) {
  switchView("showcases");
  const p = pagesById[id];
  if (!p) return;
  $("#adminLandingId").value = id;
  $("#adminPanelTitle").textContent = `Admin — ${p.business_name}`;
  $("#adminPanelSub").textContent = isOwner(p)
    ? "Se ou menm mèt biznis sa a. Ou ka ajoute oswa retire ko-admin."
    : "Ou se ko-admin sou biznis sa a.";
  $("#adminForm").classList.toggle("hidden", !isOwner(p));
  $("#adminResult").textContent = "";
  $("#adminPanel").classList.remove("hidden");
  await loadAdmins(id);
}

async function loadAdmins(id) {
  try {
    const admins = await api(`/landing-pages/${id}/admins`);
    renderAdmins(admins, id);
  } catch (e) { $("#adminResult").textContent = e.message; }
}

function renderAdmins(admins, id) {
  const list = $("#adminList");
  list.innerHTML = "";
  const me = pagesById[id];
  for (const a of admins) {
    const display = a.name || a.pseudo || a.whatsapp || a.user_id;
    const isPageOwner = a.role === "OWNER";
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="jb-admin-name">${escapeHtml(display)}${a.whatsapp ? ` <small>(${escapeHtml(a.whatsapp)})</small>` : ""}</span>
      <span class="jb-badge ${isPageOwner ? "jb-badge-owner" : "jb-badge-coadmin"}">${a.role_label || (isPageOwner ? "Mèt" : "Ko-Admin")}</span>
      ${isOwner(me) && !isPageOwner ? `<button type="button" class="jb-btn jb-btn-sm jb-btn-danger" onclick="removeAdmin(${id}, ${Number(a.user_id)})">Retire</button>` : ""}
    `;
    list.appendChild(li);
  }
}

async function addAdmin(event) {
  event.preventDefault();
  const id = Number($("#adminLandingId").value);
  const lookup = $("#adminLookup").value.trim();
  const result = $("#adminResult");
  if (!lookup) return;
  if (!navigator.onLine) { result.textContent = "Ou se offline — tcheke koneksyon an avan."; return; }
  try {
    const isNum = /^\d+$/.test(lookup);
    const body = isNum ? { user_id: Number(lookup) } : { pseudo: lookup };
    const admins = await api(`/landing-pages/${id}/admins`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("#adminLookup").value = "";
    result.textContent = "Ko-Admin ajoute avèk siksè!";
    renderAdmins(admins, id);
  } catch (e) { result.textContent = e.message; }
}

async function removeAdmin(id, uid) {
  if (!confirm("Eske ou sèten ou vle retire ko-admin sa a?")) return;
  try {
    await api(`/landing-pages/${id}/admins/${uid}`, { method: "DELETE" });
    await loadAdmins(id);
  } catch (e) { $("#adminResult").textContent = e.message; }
}

/* --- boot ---------------------------------------------------------------- */
loadStatus();
loadLandingPages();
loadOverview();
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register(`${BASE}/assets/sw.js`).catch(() => {});
}