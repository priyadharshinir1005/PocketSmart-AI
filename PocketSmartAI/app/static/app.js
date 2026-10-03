(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function showToast(message, duration = 3600) {
    const toast = $("[data-toast]");
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => { toast.hidden = true; }, duration);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  function formatMoney(value) {
    const number = Number(value || 0);
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(number);
  }

  function csrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)pocketsmart_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const method = (options.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrf = csrfToken();
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      let detail = body && body.detail;
      if (Array.isArray(detail)) detail = detail.map(item => item.msg || "Check the form values.").join(" ");
      throw new Error(detail || body.message || "Something went wrong. Please try again.");
    }
    return body;
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.originalLabel = button.innerHTML;
      button.disabled = true;
      button.innerHTML = '<span class="button-spinner"></span> ' + escapeHtml(label || "Working…");
    } else {
      button.disabled = false;
      button.innerHTML = button.dataset.originalLabel || "Continue";
    }
  }

  function initNavigation() {
    const toggle = $("[data-menu-toggle]");
    const nav = $("[data-site-nav]");
    if (toggle && nav) {
      toggle.addEventListener("click", () => {
        const open = toggle.getAttribute("aria-expanded") === "true";
        toggle.setAttribute("aria-expanded", String(!open));
        nav.classList.toggle("nav-open", !open);
      });
    }
    $$('[data-logout]').forEach(button => button.addEventListener("click", async () => {
      try {
        await apiFetch("/logout", { method: "POST" });
        window.location.href = "/";
      } catch (error) {
        showToast(error.message);
      }
    }));
  }

  function initAuth() {
    const form = $("[data-auth-form]");
    if (!form) return;
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const errorBox = $ ("[data-form-error]", form);
      if (errorBox) errorBox.hidden = true;
      if (!form.reportValidity()) return;
      const data = Object.fromEntries(new FormData(form).entries());
      if (form.dataset.mode === "register" && !data.terms) {
        if (errorBox) { errorBox.textContent = "Please confirm that you understand how estimates and search links work."; errorBox.hidden = false; }
        return;
      }
      const button = $("[data-submit-label]", form);
      setBusy(button, true, form.dataset.mode === "register" ? "Creating your account…" : "Signing you in…");
      try {
        await apiFetch(form.dataset.mode === "register" ? "/register" : "/login", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
        });
        window.location.assign("/dashboard");
      } catch (error) {
        if (errorBox) { errorBox.textContent = error.message; errorBox.hidden = false; }
      } finally {
        setBusy(button, false);
      }
    });
  }

  function parseItemList(value) {
    return value.split(",").map(part => part.trim()).filter(Boolean).map(part => {
      const quantity = part.match(/\s+x\s*(\d+)$/i);
      return { name: part.replace(/\s+x\s*\d+$/i, "").trim(), quantity: quantity ? Number(quantity[1]) : 1 };
    }).filter(item => item.name && Number.isInteger(item.quantity) && item.quantity > 0);
  }

  function recommendationMarkup(plan, source, id, createdAt) {
    const items = plan.recommendations || [];
    const links = plan.search_links || [];
    const list = items.map((item, index) => {
      const quantity = Number(item.quantity || 1);
      const total = Number(item.estimated_unit_price || 0) * quantity;
      const linkMarkup = (links[index] || []).map(link => `<a class="retailer-link" href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">Search ${escapeHtml(link.platform)} <span>↗</span></a>`).join("");
      return `<article class="recommendation-item"><div class="rec-item-top"><span class="rec-category">${escapeHtml(item.category)}</span><span class="rec-amount">${formatMoney(total)}${quantity > 1 ? `<small> · ${quantity} × ${formatMoney(item.estimated_unit_price)}</small>` : ""}</span></div><h4>${escapeHtml(item.name)}</h4><p>${escapeHtml(item.description)}</p><div class="retailer-links">${linkMarkup}</div></article>`;
    }).join("");
    const allocations = (plan.budget_breakdown || []).map(row => `<div class="allocation-row"><span><b>${escapeHtml(row.category)}</b><small>${escapeHtml(row.rationale || "")}</small></span><strong>${formatMoney(row.amount)}</strong></div>`).join("");
    const tips = (plan.savings_tips || []).map(tip => `<li>${escapeHtml(tip)}</li>`).join("");
    const notes = (plan.style_notes || []).map(note => `<span class="style-note">${escapeHtml(note)}</span>`).join("");
    const localBadge = source === "local" ? '<span class="source-badge source-local">Starter plan</span>' : '<span class="source-badge source-ai">AI-assisted</span>';
    const image = plan.image_observation ? `<div class="image-insight"><span>Outfit cue</span><p>${escapeHtml(plan.image_observation)}</p></div>` : "";
    const details = createdAt ? `<span class="result-date">Saved ${escapeHtml(new Date(createdAt).toLocaleString())}</span>` : "";
    return `<section class="recommendation-result"><div class="result-topline"><span class="eyebrow">YOUR BUDGET PLAN</span>${localBadge}</div><h2>${escapeHtml(plan.title)}</h2><p class="result-summary">${escapeHtml(plan.summary)}</p><div class="budget-summary"><div><small>YOUR BUDGET</small><strong>${formatMoney(plan.budget)}</strong></div><div><small>PLANNED SPEND</small><strong>${formatMoney(plan.total_estimated)}</strong></div><div><small>LEFT TO ADJUST</small><strong>${formatMoney(plan.budget_remaining)}</strong></div></div>${image}<div class="result-section"><div class="result-section-title"><span class="result-section-icon">▤</span><div><h3>Budget at a glance</h3><p>Suggested allowances, with room for real-world price changes.</p></div></div><div class="allocation-list">${allocations || '<p class="quiet-copy">Your plan keeps the overall budget in view.</p>'}</div></div><div class="result-section"><div class="result-section-title"><span class="result-section-icon">✧</span><div><h3>Ideas to explore</h3><p>Use search links to compare current prices and availability.</p></div></div><div class="recommendation-list">${list || '<p class="quiet-copy">No suggestions were returned for this plan.</p>'}</div></div>${tips ? `<div class="result-section tip-section"><h3>Keep a little more in your pocket</h3><ul>${tips}</ul></div>` : ""}${notes ? `<div class="result-section"><h3>Style notes</h3><div class="style-notes">${notes}</div></div>` : ""}<p class="estimate-disclaimer">Planning estimates only. Retailer searches open external sites; confirm final prices, details, and availability directly.</p>${details}</section>`;
  }

  function showResult(target, response, replace = true) {
    if (!target) return;
    if (replace) target.innerHTML = recommendationMarkup(response.plan, response.source || response.plan.source, response.id, response.created_at);
    target.hidden = false;
    const intro = $ ("[data-result-intro]");
    if (intro && target.closest("[data-planner-page]")) intro.hidden = true;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function initPlanner() {
    const page = $("[data-planner-page]");
    const form = $("[data-planner-form]");
    if (!page || !form) return;
    const resultTarget = $ ("[data-result]");
    const errorBox = $ ("[data-form-error]", form);
    const preview = $ ("[data-image-preview]");
    const fileInput = $('[name="outfit_image"]', form);
    const roomList = $ ("[data-room-list]", form);
    const addRoomButton = $ ("[data-add-room]", form);
    const updateRoomControls = () => {
      const rows = $$('[data-room-row]', form);
      rows.forEach(row => { $("[data-remove-room]", row).hidden = rows.length < 2; });
      if (addRoomButton) addRoomButton.disabled = rows.length >= 8;
    };
    if (roomList && addRoomButton) {
      updateRoomControls();
      addRoomButton.addEventListener("click", () => {
        if ($$('[data-room-row]', form).length >= 8) return;
        roomList.insertAdjacentHTML("beforeend", '<div class="room-row" data-room-row><label class="subfield-label">Room<input name="room_name" type="text" placeholder="Bedroom, kitchen…" required></label><label class="subfield-label">Items<input name="room_items" type="text" placeholder="Ceiling fan x 1, bedside lamp" required></label><button class="room-remove" type="button" data-remove-room aria-label="Remove room">×</button></div>');
        updateRoomControls();
      });
      roomList.addEventListener("click", event => {
        const button = event.target.closest("[data-remove-room]");
        if (button && $$('[data-room-row]', form).length > 1) {
          button.closest("[data-room-row]").remove();
          updateRoomControls();
        }
      });
    }
    if (fileInput && preview) {
      fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) { preview.hidden = true; return; }
        const image = $("img", preview);
        image.src = URL.createObjectURL(file);
        preview.hidden = false;
      });
      $ ("[data-remove-image]")?.addEventListener("click", () => { fileInput.value = ""; preview.hidden = true; });
    }
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (errorBox) errorBox.hidden = true;
      if (!form.reportValidity()) return;
      const planner = page.dataset.planner;
      const raw = new FormData(form);
      let url = `/generate-${planner}`;
      let body;
      const headers = {};
      if (planner === "home") {
        const rooms = $$('[data-room-row]', form).map(row => ({
          name: $('[name="room_name"]', row).value.trim(),
          items: parseItemList($('[name="room_items"]', row).value),
        }));
        if (!rooms.length || rooms.some(room => !room.name || !room.items.length)) { if (errorBox) { errorBox.textContent = "Add at least one item to every room in your plan."; errorBox.hidden = false; } return; }
        body = JSON.stringify({ budget: Number(raw.get("budget")), city: raw.get("city"), style: raw.get("style"), notes: raw.get("notes"), rooms });
        headers["Content-Type"] = "application/json";
      } else if (planner === "party") {
        body = JSON.stringify({ budget: Number(raw.get("budget")), guests: Number(raw.get("guests")), event_type: raw.get("event_type"), city: raw.get("city"), venue_preference: raw.get("venue_preference"), dietary_needs: raw.get("dietary_needs"), priorities: raw.get("priorities") });
        headers["Content-Type"] = "application/json";
      } else {
        body = raw;
      }
      const button = $("[data-submit-label]", form);
      setBusy(button, true, "Building your plan…");
      try {
        const response = await apiFetch(url, { method: "POST", headers, body });
        showResult(resultTarget, response);
      } catch (error) {
        if (errorBox) { errorBox.textContent = error.message; errorBox.hidden = false; }
      } finally {
        setBusy(button, false);
      }
    });
  }

  function plannerIcon(type) {
    return type === "home" ? "⌂" : type === "party" ? "✦" : "◇";
  }

  function historyCard(item) {
    const source = item.source === "local" ? "Starter plan" : "AI-assisted";
    return `<article class="history-card"><div class="history-card-top"><span class="history-card-icon ${item.planner_type === "home" ? "icon-home" : item.planner_type === "party" ? "icon-party" : "icon-jewel"}">${plannerIcon(item.planner_type)}</span><span class="category-tag">${escapeHtml(item.planner_label)}</span></div><span class="history-date">${escapeHtml(new Date(item.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }))}</span><h3>${escapeHtml(item.title)}</h3><div class="history-metrics"><span><small>Budget</small><b>${formatMoney(item.budget)}</b></span><span><small>Planned spend</small><b>${formatMoney(item.total_estimated)}</b></span></div><div class="history-card-bottom"><span class="source-text">${source}</span><button type="button" class="text-button" data-open-plan="${Number(item.id)}">View plan <span>→</span></button></div></article>`;
  }

  async function openPlan(id, listElement) {
    const detail = $ ("[data-history-detail]") || (() => {
      const section = document.createElement("section");
      section.dataset.historyDetail = "";
      section.className = "history-detail-shell";
      listElement.insertAdjacentElement("afterend", section);
      return section;
    })();
    detail.innerHTML = '<div class="loading-card"><span class="spinner"></span> Opening saved plan</div>';
    detail.hidden = false;
    try {
      const response = await apiFetch(`/recommendations-details/${id}`);
      detail.innerHTML = `<button class="detail-close text-button" type="button" data-close-detail>Close plan ×</button><div data-detail-result></div>`;
      showResult($ ("[data-detail-result]", detail), response);
      $ ("[data-close-detail]", detail)?.addEventListener("click", () => { detail.hidden = true; });
    } catch (error) {
      detail.innerHTML = `<div class="empty-state"><p>${escapeHtml(error.message)}</p></div>`;
    }
  }

  async function initHistory() {
    const list = $ ("[data-history-list]");
    if (!list) return;
    try {
      const data = await apiFetch("/api/history");
      const items = data.items || [];
      if (!items.length) {
        list.innerHTML = '<div class="empty-state"><span class="empty-icon">✧</span><h3>Your first plan is waiting.</h3><p>Choose one of the planners to get started. Your saved plans will show up here.</p><a class="button" href="/dashboard">Explore the planners <span>→</span></a></div>';
      } else {
        list.innerHTML = items.map(historyCard).join("");
        list.addEventListener("click", event => {
          const button = event.target.closest("[data-open-plan]");
          if (button) openPlan(Number(button.dataset.openPlan), list);
        });
      }
      const countLabel = $ ("[data-count-label]");
      if (countLabel) countLabel.textContent = `${items.length} saved ${items.length === 1 ? "plan" : "plans"}`;
    } catch (error) {
      list.innerHTML = `<div class="empty-state"><h3>We couldn’t load your saved plans.</h3><p>${escapeHtml(error.message)}</p></div>`;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initAuth();
    initPlanner();
    initHistory();
  });
})();
