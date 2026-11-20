(() => {
  "use strict";

  const LOCAL_API_BASE = "http://127.0.0.1:5000";
  const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
  const PHOTO_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
  const PHOTO_FIELDS = [
    ["brand_name", "Brand / product name"],
    ["registration_number", "Registration number"],
    ["manufacturer", "Manufacturer / applicant"],
    ["strength", "Strength"],
  ];

  function configuredApiBase() {
    let configured = window.DrugCheckerConfig && window.DrugCheckerConfig.apiBaseUrl;
    try {
      const fromQuery = new URLSearchParams(window.location.search).get("apiBase");
      if (fromQuery) configured = fromQuery;
    } catch (_error) {
      // Keep the explicit config/default when URL parsing is unavailable.
    }
    const hostname = window.location && window.location.hostname;
    const localPage = ["localhost", "127.0.0.1", "::1"].includes(hostname);
    const base = String(configured || (localPage ? LOCAL_API_BASE : "")).trim();
    return base.replace(/\/+$/, "");
  }

  const API_BASE = configuredApiBase();
  const el = (id) => document.getElementById(id);
  const messages = el("messages");
  const chatForm = el("chat-form");
  const textInput = el("text-input");
  const sendButton = el("send-btn");
  const photoInput = el("photo-input");
  const photoButton = el("photo-btn");
  const smsView = el("sms-view");
  const chatView = el("chat-view");
  const smsThread = el("sms-thread");
  const smsForm = el("sms-form");
  const smsInput = el("sms-input");
  const smsSend = el("sms-send");
  const statusId = "backend-status";

  if (!messages || !chatForm || !textInput || !smsView || !smsThread || !smsForm) return;

  function textNode(tag, value, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = value == null ? "" : String(value);
    return node;
  }

  function addParagraph(parent, value, className) {
    if (value == null || value === "") return null;
    const node = textNode("p", value, className);
    parent.appendChild(node);
    return node;
  }

  function appendMessage(parent, side, className) {
    const node = document.createElement("div");
    node.className = `msg ${side}${className ? ` ${className}` : ""}`;
    parent.appendChild(node);
    return node;
  }

  function scrollToEnd(parent) {
    parent.scrollTop = parent.scrollHeight;
  }

  function addSystemSms(text) {
    const line = textNode("p", text, "sms-system");
    smsThread.appendChild(line);
    scrollToEnd(smsThread);
  }

  function addSmsBubble(side, text, label) {
    const bubble = document.createElement("div");
    bubble.className = `sms-bubble ${side}`;
    bubble.appendChild(textNode("span", text));
    if (label) bubble.appendChild(textNode("small", label, "sms-meta"));
    smsThread.appendChild(bubble);
    scrollToEnd(smsThread);
    return bubble;
  }

  function addBackendStatus() {
    let status = el(statusId);
    if (status) return status;
    status = textNode("p", "Connecting to checker…", "sub");
    status.id = statusId;
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.style.maxWidth = "760px";
    status.style.margin = "8px auto 0";
    status.style.padding = "0 16px";
    status.style.textAlign = "center";
    const header = document.querySelector(".site-header");
    if (header) header.appendChild(status);
    return status;
  }

  function setConnection(online, detail) {
    const status = addBackendStatus();
    status.textContent = online ? `Backend connected${detail ? ` · ${detail}` : ""}` : `Backend unavailable${detail ? ` · ${detail}` : ""}`;
    status.setAttribute("data-state", online ? "online" : "offline");
  }

  function setFooterLimitations(health) {
    const note = el("data-note");
    if (!note) return;
    const scope = health && health.registry_scope === "sample_demo"
      ? `Registry: limited ${Number(health.drugs) || "demo"}-record sample, not the full Greenbook.`
      : "Registry coverage is limited to data currently loaded in the backend.";
    note.textContent = `${scope} Alert status is reported by the backend; synthetic alerts are demonstrations, not NAFDAC notices. No medical advice or physical-pack authentication.`;
  }

  function responseMessage(payload, response) {
    if (payload && typeof payload.error === "string") return payload.error;
    if (!response.ok) return `Request failed (${response.status}).`;
    return "The backend returned an unreadable response.";
  }

  async function requestJson(path, options, timeoutMs) {
    if (!API_BASE) {
      const error = new Error("Backend URL is not configured. Set DRUG_CHECKER_API_BASE_URL for this frontend build.");
      setConnection(false, "backend URL is not configured");
      throw error;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs || 30000);
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        signal: controller.signal,
        credentials: "omit",
      });
      let payload;
      try {
        payload = await response.json();
      } catch (_error) {
        payload = null;
      }
      if (!response.ok) throw new Error(responseMessage(payload, response));
      if (!payload || typeof payload !== "object") throw new Error(responseMessage(payload, response));
      setConnection(true);
      return payload;
    } catch (error) {
      const message = error && error.name === "AbortError"
        ? "The backend request timed out. Please try again."
        : (error instanceof TypeError
          ? "Could not reach the backend. Check that it is running and that this page's origin is allowed."
          : (error && error.message ? error.message : "The request failed."));
      setConnection(false, "check the backend URL and CORS settings");
      throw new Error(message);
    } finally {
      window.clearTimeout(timer);
    }
  }

  function addError(parent, message) {
    const bubble = appendMessage(parent, "bot");
    bubble.setAttribute("role", "alert");
    addParagraph(bubble, message);
    scrollToEnd(parent);
  }

  function addLoading(parent, label) {
    const bubble = appendMessage(parent, "bot");
    bubble.setAttribute("role", "status");
    bubble.appendChild(textNode("p", label));
    const dots = document.createElement("span");
    dots.className = "typing";
    dots.setAttribute("aria-label", "Loading");
    for (let i = 0; i < 3; i += 1) dots.appendChild(document.createElement("span"));
    bubble.appendChild(dots);
    scrollToEnd(parent);
    return bubble;
  }

  function addBadge(parent, label, variant) {
    const badge = textNode("span", label, `badge${variant ? ` ${variant}` : ""}`);
    parent.appendChild(badge);
    return badge;
  }

  function appendDataStatus(parent, label, data) {
    const block = document.createElement("p");
    block.className = "sub row-gap";
    const status = data && data.status ? String(data.status) : "unknown";
    block.textContent = `${label}: ${status}`;
    if (data && data.source_name) block.textContent += ` · ${data.source_name}`;
    parent.appendChild(block);
    if (status === "unknown") addParagraph(parent, `${label} has not been confirmed as checked. Unknown does not mean there are no alerts.`, "sub");
    if (status === "stale") addParagraph(parent, `${label} is stale; check the source date before relying on it.`, "sub");
    if (status === "error") addParagraph(parent, `${label} check failed.`, "sub");
  }

  function appendSafeLink(parent, href, label) {
    if (typeof href !== "string" || !href) return;
    let url;
    try { url = new URL(href); } catch (_error) { return; }
    if (url.protocol !== "https:" && url.protocol !== "http:") return;
    const link = document.createElement("a");
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = label || url.href;
    parent.appendChild(link);
  }

  function renderAlerts(parent, alerts) {
    if (!Array.isArray(alerts) || alerts.length === 0) return;
    const section = document.createElement("section");
    section.className = "alert-banner";
    section.setAttribute("aria-label", "Matching alert records");
    section.appendChild(textNode("h3", "Matching alert record(s)"));
    alerts.forEach((alert) => {
      const item = document.createElement("div");
      item.className = "row-gap";
      const synthetic = alert && alert.source_kind === "synthetic";
      const heading = document.createElement("p");
      heading.appendChild(textNode("strong", alert && alert.alert_type ? alert.alert_type : "Alert type not supplied"));
      if (alert && alert.alert_date) heading.appendChild(document.createTextNode(` · ${alert.alert_date}`));
      item.appendChild(heading);
      if (synthetic) addBadge(item, alert.demo_label || "SYNTHETIC — DEMONSTRATION ONLY", "demo");
      else if (alert && alert.source_kind === "unknown") addBadge(item, "Source type unknown", "warn");
      if (alert && alert.product_name) addParagraph(item, `Product named in record: ${alert.product_name}`);
      if (alert && alert.reason) addParagraph(item, alert.reason);
      if (alert && alert.matched_by) {
        const strength = ["reg_number", "registration_number"].includes(alert.matched_by)
          ? "registration number match"
          : "name-only match (weaker evidence)";
        addParagraph(item, `Matched by ${strength}.`, "sub");
      }
      if (synthetic) addParagraph(item, "Fictional demonstration fixture, not a real NAFDAC notice.", "sub");
      if (alert && alert.source_link) {
        const source = document.createElement("p");
        source.className = "source";
        source.appendChild(document.createTextNode("Source: "));
        appendSafeLink(source, alert.source_link, alert.source_link);
        item.appendChild(source);
      }
      section.appendChild(item);
    });
    parent.appendChild(section);
  }

  function renderCandidates(parent, matches) {
    if (!Array.isArray(matches) || matches.length === 0) return;
    const title = textNode("p", "Choose the record you want to check by its registration number:", "sub row-gap");
    parent.appendChild(title);
    const list = document.createElement("ul");
    list.className = "options";
    matches.forEach((match) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      const name = textNode("span", match.brand_name || "Name not supplied", "opt-name");
      const details = [match.reg_number, match.strength, match.dosage_form, match.manufacturer].filter(Boolean).join(" · ");
      button.appendChild(name);
      if (details) button.appendChild(textNode("span", details, "opt-meta"));
      button.addEventListener("click", () => {
        if (!match.reg_number) {
          addError(messages, "This candidate has no registration number to submit. Please clarify your search.");
          return;
        }
        submitCheck(String(match.reg_number), false);
      });
      li.appendChild(button);
      list.appendChild(li);
    });
    parent.appendChild(list);
  }

  function renderFindings(parent, findings, explanation, smsReply) {
    const card = document.createElement("section");
    card.className = "finding";
    const status = findings && findings.status ? String(findings.status) : "unknown";
    const titleMap = {
      found: "Registry record matched",
      multiple: "More than one registry candidate",
      not_found: "No registry match in the available data",
      invalid: "Please clarify the request",
    };
    card.appendChild(textNode("h2", titleMap[status] || "Checker response"));
    addParagraph(card, findings && findings.query ? `Query: ${findings.query}` : "");
    if (findings && findings.registry_scope === "sample_demo") {
      addBadge(card, "Limited demo sample · not the complete Greenbook", "demo");
    }
    if (findings && findings.data_as_of) addParagraph(card, `Registry source date: ${findings.data_as_of}`, "sub");
    if (findings && findings.reason === "clarification_required") {
      addParagraph(card, "The message could not be extracted with enough certainty. Try a medicine name or registration number.", "sub");
    }
    if (status === "not_found") {
      addParagraph(card, "The available registry did not confirm this query. That is not proof that a product is counterfeit.", "sub");
    }
    if (status === "found" || status === "multiple") {
      (Array.isArray(findings.matches) ? findings.matches : []).forEach((match) => {
        const details = document.createElement("dl");
        const fields = [
          ["Product", match.brand_name], ["Registration number", match.reg_number],
          ["Generic name", match.generic_name], ["Manufacturer / applicant", match.manufacturer || match.applicant],
          ["Strength", match.strength], ["Dosage form", match.dosage_form],
          ["Registry status", match.registry_status],
        ];
        fields.forEach(([label, value]) => {
          if (value == null || value === "") return;
          const dt = textNode("dt", label);
          const dd = textNode("dd", value);
          details.append(dt, dd);
        });
        if (details.childNodes.length) card.appendChild(details);
        if (match.detail_url) {
          const p = document.createElement("p"); p.className = "source";
          appendSafeLink(p, match.detail_url, "Registry record source"); card.appendChild(p);
        }
      });
      if (status === "multiple") renderCandidates(card, findings.matches);
    }
    renderAlerts(card, findings && findings.alerts);
    if (Array.isArray(findings && findings.mismatches) && findings.mismatches.length) {
      const compare = document.createElement("section");
      compare.className = "row-gap";
      compare.appendChild(textNode("h3", "Field comparison differences"));
      const list = document.createElement("ul"); list.className = "checks";
      findings.mismatches.forEach((mismatch) => {
        const item = document.createElement("li"); item.className = "warn";
        const mark = textNode("span", "!", "mark");
        const detail = document.createElement("div");
        addParagraph(detail, mismatch.field ? `${mismatch.field}: difference reported` : "Difference reported");
        if (mismatch.note) addParagraph(detail, mismatch.note, "sub");
        if (mismatch.expected != null) addParagraph(detail, `Registry value: ${Array.isArray(mismatch.expected) ? mismatch.expected.join(", ") : mismatch.expected}`, "sub");
        if (mismatch.observed != null) addParagraph(detail, `Confirmed package value: ${Array.isArray(mismatch.observed) ? mismatch.observed.join(", ") : mismatch.observed}`, "sub");
        item.append(mark, detail); list.appendChild(item);
      });
      compare.appendChild(list);
      addParagraph(compare, "A difference is not proof of counterfeiting; it only reports that submitted text differs from available registry data.", "sub");
      card.appendChild(compare);
    }
    appendDataStatus(card, "Alert data status", findings && findings.alert_data_status);
    if (findings && findings.registry_data_status) appendDataStatus(card, "Registry data status", findings.registry_data_status);
    addParagraph(card, "A registry match or field comparison does not authenticate a physical pack or establish product safety.", "sub row-gap");
    if (smsReply) {
      const sms = document.createElement("p");
      sms.className = "sub row-gap";
      sms.appendChild(textNode("strong", "Simulated SMS reply: "));
      sms.appendChild(document.createTextNode(String(smsReply)));
      card.appendChild(sms);
    }
    if (explanation && explanation.text) {
      const explanationSection = document.createElement("section");
      explanationSection.className = "row-gap";
      explanationSection.appendChild(textNode("h3", "Explanation"));
      addParagraph(explanationSection, explanation.text);
      if (explanation.mode) addParagraph(explanationSection, `Explanation mode: ${explanation.mode}`, "sub");
      card.appendChild(explanationSection);
    }
    parent.appendChild(card);
    scrollToEnd(parent);
  }

  function addWelcome(health) {
    const bubble = appendMessage(messages, "bot");
    addParagraph(bubble, "Send a medicine name, registration number, or informal lookup request. The backend makes the registry decision.");
    if (health && health.registry_scope === "sample_demo") {
      addParagraph(bubble, `The backend currently contains ${Number(health.drugs) || "a limited"}-record demo sample, not the complete NAFDAC Greenbook.`);
    } else {
      addParagraph(bubble, "Coverage depends on the registry data currently loaded by the backend.");
    }
    addParagraph(bubble, "Alert status comes from the backend. Any synthetic alert is a fictional demonstration, not a NAFDAC notice. A match does not authenticate a physical pack.", "sub");
  }

  async function checkHealth() {
    try {
      const health = await requestJson("/api/health", { method: "GET" }, 12000);
      const detail = health.registry_scope === "sample_demo" ? "limited demo registry" : "service ready";
      setConnection(true, detail);
      setFooterLimitations(health);
      if (!messages.childNodes.length) addWelcome(health);
      return health;
    } catch (error) {
      setConnection(false);
      if (!messages.childNodes.length) {
        const bubble = appendMessage(messages, "bot");
        addParagraph(bubble, "The checker page is ready, but the backend could not be reached.");
        addParagraph(bubble, error.message, "sub");
      }
      return null;
    }
  }

  async function submitCheck(rawMessage, addUserMessage) {
    const message = String(rawMessage || "").trim();
    if (!message) return;
    if (addUserMessage !== false) appendMessage(messages, "user").textContent = message;
    textInput.value = "";
    sendButton.disabled = true;
    const loading = addLoading(messages, "Checking the backend registry and alert data…");
    try {
      const result = await requestJson("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      loading.remove();
      if (!result.findings) throw new Error("The backend response did not include findings.");
      const bubble = appendMessage(messages, "bot", "has-card");
      renderFindings(bubble, result.findings, result.explanation, result.sms_reply);
    } catch (error) {
      loading.remove();
      addError(messages, error.message);
    } finally {
      sendButton.disabled = false;
      textInput.focus();
    }
  }

  function renderPhotoConfirmation(extraction) {
    const bubble = appendMessage(messages, "bot", "has-card");
    const panel = document.createElement("section");
    panel.className = "confirm";
    panel.appendChild(textNode("h2", "Review text read from the photo"));
    addBadge(panel, "Unconfirmed OCR · review required", "warn");
    if (extraction && extraction.status) addParagraph(panel, `Extraction status: ${extraction.status}`, "sub row-gap");
    if (extraction && extraction.message) addParagraph(panel, extraction.message, "note");
    addParagraph(panel, "Edit these visible fields, then tick the confirmation box. No lookup runs until you submit the confirmed values.", "note");

    const form = document.createElement("form");
    const fields = extraction && extraction.fields && typeof extraction.fields === "object" ? extraction.fields : {};
    const inputs = {};
    PHOTO_FIELDS.forEach(([key, label]) => {
      const wrapper = document.createElement("div"); wrapper.className = "field";
      const id = `photo-confirm-${key}`;
      const labelNode = textNode("label", label); labelNode.htmlFor = id;
      const input = document.createElement("input");
      input.type = "text"; input.id = id; input.name = key; input.maxLength = 200;
      input.autocomplete = "off";
      const value = fields[key];
      input.value = value == null || value === "not visible" ? "" : String(value);
      input.placeholder = value === "not visible" ? "Not visible — enter only if you can read it" : "Review or correct this field";
      wrapper.append(labelNode, input); form.appendChild(wrapper); inputs[key] = input;
    });

    const confirmWrap = document.createElement("label");
    confirmWrap.className = "field row-gap";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.name = "confirmed";
    confirmWrap.append(checkbox, document.createTextNode(" I reviewed and confirm these fields (including any corrections)."));
    form.appendChild(confirmWrap);
    const errorLine = textNode("p", "", "error"); errorLine.setAttribute("role", "alert");
    form.appendChild(errorLine);
    const buttons = document.createElement("div"); buttons.className = "btn-row";
    const submit = textNode("button", "Confirm fields and compare", "btn primary"); submit.type = "submit";
    const cancel = textNode("button", "Cancel review", "btn"); cancel.type = "button";
    buttons.append(submit, cancel); form.appendChild(buttons);

    cancel.addEventListener("click", () => {
      bubble.remove();
      appendMessage(messages, "bot").textContent = "Photo review cancelled. No lookup was performed.";
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorLine.textContent = "";
      if (!checkbox.checked) {
        errorLine.textContent = "Please confirm that you reviewed or corrected the extracted fields.";
        checkbox.focus(); return;
      }
      const confirmedFields = {};
      PHOTO_FIELDS.forEach(([key]) => { confirmedFields[key] = inputs[key].value.trim(); });
      if (!confirmedFields.brand_name && !confirmedFields.registration_number && !confirmedFields.manufacturer && !confirmedFields.strength) {
        errorLine.textContent = "Enter at least one visible or user-confirmed field before comparison.";
        inputs.brand_name.focus(); return;
      }
      submit.disabled = true; cancel.disabled = true;
      const loading = addLoading(messages, "Comparing your confirmed fields with backend registry records…");
      try {
        const result = await requestJson("/api/photo/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirmed: true, fields: confirmedFields }),
        });
        loading.remove();
        bubble.remove();
        const output = appendMessage(messages, "bot", "has-card");
        addParagraph(output, "Confirmed fields submitted. OCR text was not treated as confirmation.", "sub");
        renderFindings(output, result.findings, result.explanation, result.sms_reply);
      } catch (error) {
        loading.remove(); errorLine.textContent = error.message;
        submit.disabled = false; cancel.disabled = false;
      }
    });
    panel.appendChild(form); bubble.appendChild(panel); scrollToEnd(messages);
  }

  async function extractPhoto(file) {
    if (!file) return;
    const mime = String(file.type || "").toLowerCase();
    if (!PHOTO_MIME_TYPES.has(mime)) { addError(messages, "Use a JPEG, PNG, or WebP image."); photoInput.value = ""; return; }
    if (file.size <= 0) { addError(messages, "The selected image is empty."); photoInput.value = ""; return; }
    if (file.size > MAX_PHOTO_BYTES) { addError(messages, "The image exceeds the 5 MiB upload limit."); photoInput.value = ""; return; }
    const user = appendMessage(messages, "user");
    user.textContent = `Package photo submitted for visible-text extraction (${file.name || "image"}).`;
    const loading = addLoading(messages, "Reading visible package text…");
    photoButton.disabled = true;
    try {
      const body = new FormData(); body.append("image", file, file.name || "package-image");
      const result = await requestJson("/api/photo/extract", { method: "POST", body }, 90000);
      loading.remove();
      renderPhotoConfirmation(result);
    } catch (error) {
      loading.remove(); addError(messages, error.message);
    } finally {
      photoButton.disabled = false; photoInput.value = "";
    }
  }

  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCheck(textInput.value, true);
  });
  photoButton.addEventListener("click", () => photoInput.click());
  photoInput.addEventListener("change", () => extractPhoto(photoInput.files && photoInput.files[0]));

  const openSms = el("open-sms");
  const backSms = el("sms-back");
  const smsTitle = el("sms-title");
  const smsExamples = el("sms-examples");
  function showSms() {
    chatView.hidden = true; el("sms-wrap").hidden = true; smsView.hidden = false;
    if (!smsThread.childNodes.length) addSystemSms("SIMULATED SMS. Replies use the backend; no text message is sent.");
    if (smsTitle) smsTitle.focus();
  }
  function showChat() { smsView.hidden = true; chatView.hidden = false; el("sms-wrap").hidden = false; textInput.focus(); }
  if (openSms) openSms.addEventListener("click", showSms);
  if (backSms) backSms.addEventListener("click", showChat);
  if (smsForm) smsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = smsInput.value.trim(); if (!message) return;
    smsInput.value = ""; smsSend.disabled = true;
    addSmsBubble("in", message, "You · simulated");
    const pending = textNode("p", "Backend reply pending…", "sms-system"); smsThread.appendChild(pending); scrollToEnd(smsThread);
    try {
      const result = await requestJson("/api/check", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }),
      });
      pending.remove();
      addSmsBubble("out", result.sms_reply || "The backend did not provide an SMS reply.", "Drug Checker · simulated reply");
      if (result.findings && Array.isArray(result.findings.alerts) && result.findings.alerts.some((a) => a.source_kind === "synthetic")) {
        addSystemSms("A synthetic demonstration alert was returned. It is not a real NAFDAC notice.");
      }
    } catch (error) { pending.remove(); addSystemSms(error.message); }
    finally { smsSend.disabled = false; smsInput.focus(); }
  });

  if (smsExamples) {
    ["A4-102585", "Tramadol Hyrdochloride 100 mg Capsule", "abeg check A4-102585"].forEach((example) => {
      const button = textNode("button", example); button.type = "button";
      button.addEventListener("click", () => { smsInput.value = example; smsInput.focus(); });
      smsExamples.appendChild(button);
    });
  }

  // Correct the inherited promotional wording: this is a local SMS simulation.
  const smsCopy = document.querySelector("#open-sms .sms-text");
  if (smsCopy) {
    const spans = smsCopy.querySelectorAll("span");
    if (spans[0]) spans[0].textContent = "Simulated SMS checker";
    if (spans[1]) spans[1].textContent = "Try a backend lookup in a simulated text conversation.";
    const liveLabel = smsCopy.querySelector("em");
    if (liveLabel) liveLabel.textContent = "No message will be sent";
  }

  checkHealth();
  window.setInterval(checkHealth, 30000);
})();

