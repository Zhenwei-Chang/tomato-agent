const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const titleCase = (value) => String(value ?? "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

let scenarioIndex = [];
let currentScenario = null;

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 1800);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const node = document.createElement("textarea");
    node.value = text;
    node.setAttribute("readonly", "");
    node.style.position = "fixed";
    node.style.opacity = "0";
    document.body.appendChild(node);
    node.select();
    document.execCommand("copy");
    node.remove();
  }
  showToast(`${label} copied`);
}

function scenarioDescription(entry) {
  const descriptions = {
    knowledge_salt: "RAG relevance gate and evidence-based abstention",
    growth_prediction: "ML prediction with required reliability assessment",
    historical_memory: "Leakage-safe retrieval of earlier observed outcomes",
    comprehensive: "Six model-generated calls across four evidence types",
    safety_refusal: "Unsupported precision-control request rejected safely"
  };
  return descriptions[entry.id] || "Recorded agent scenario";
}

function renderTabs(activeId) {
  $("scenario-tabs").innerHTML = scenarioIndex.map((entry, index) => `
    <button type="button" role="tab" aria-selected="${entry.id === activeId}" tabindex="${entry.id === activeId ? 0 : -1}"
      data-scenario="${esc(entry.id)}">
      <span class="scenario-number">0${index + 1}</span>
      <span><strong>${esc(entry.title)}</strong><small>${esc(scenarioDescription(entry))}</small></span>
    </button>`).join("");
  document.querySelectorAll("[data-scenario]").forEach(button => {
    button.addEventListener("click", () => loadScenario(button.dataset.scenario));
  });
}

function renderClaims(claims) {
  if (!claims.length) {
    $("claims").innerHTML = `<div class="empty-state"><strong>No claim passed the evidence gate.</strong><span>The system abstained instead of filling the gap.</span></div>`;
    return;
  }
  $("claims").innerHTML = claims.map((claim, index) => `
    <button type="button" class="claim-card" data-support="${esc((claim.support || []).join(","))}">
      <span class="claim-index">${String(index + 1).padStart(2, "0")}</span>
      <span><small>${esc(titleCase(claim.type))}</small><strong>${esc(claim.text)}</strong><em>${claim.support?.length ? esc(claim.support.join(" · ")) : "NO EVIDENCE ID"}</em></span>
    </button>`).join("");
  document.querySelectorAll(".claim-card").forEach(button => {
    button.addEventListener("click", () => highlightEvidence(button));
  });
}

function highlightEvidence(claimButton) {
  const ids = new Set((claimButton.dataset.support || "").split(",").filter(Boolean));
  document.querySelectorAll(".claim-card").forEach(node => node.classList.toggle("selected", node === claimButton));
  document.querySelectorAll(".evidence-card").forEach(card => card.classList.toggle("highlighted", ids.has(card.dataset.evidenceId)));
  const first = [...document.querySelectorAll(".evidence-card.highlighted")][0];
  if (first) first.scrollIntoView({behavior: "smooth", block: "nearest"});
}

function renderTools(data) {
  const tools = data.tool_calls || [];
  $("trace-meta").textContent = tools.length
    ? `${tools.length} recorded call${tools.length === 1 ? "" : "s"} · ${data.trace?.provider_calls ?? "NOT_RECORDED"} provider call${data.trace?.provider_calls === 1 ? "" : "s"}`
    : "Request rejected before tool dispatch.";
  if (!tools.length) {
    $("tools").innerHTML = `<li class="timeline-empty"><span>0</span><div><strong>No tool execution</strong><p>Safety policy stopped the unsupported request before dispatch.</p></div></li>`;
    return;
  }
  $("tools").innerHTML = tools.map(tool => {
    const source = tool.dispatch_source || "NOT_RECORDED";
    const latency = Number.isFinite(tool.latency_ms) ? `${tool.latency_ms.toFixed(3)} ms` : "NOT_RECORDED";
    return `<li class="timeline-item" data-status="${esc(tool.status)}">
      <span class="timeline-index">${tool.index}</span>
      <details ${tool.index === 1 ? "open" : ""}>
        <summary>
          <span><strong>${esc(tool.name)}</strong><small>${esc(tool.arguments_summary)}</small></span>
          <span class="tool-status">${esc(tool.status)}</span>
        </summary>
        <div class="tool-detail-grid">
          <div><span>Dispatch source</span><strong>${esc(source)}</strong></div>
          <div><span>Scope</span><strong>${esc(tool.scope)}</strong></div>
          <div><span>Evidence returned</span><strong>${esc(tool.evidence_count ?? "NOT_RECORDED")}</strong></div>
          <div><span>Tool latency</span><strong>${esc(latency)}</strong></div>
          <div><span>Error</span><strong>${esc(tool.error_code || "NONE")}</strong></div>
          <div><span>Execution source</span><strong>LOCAL TOOL ADAPTER</strong></div>
        </div>
      </details>
    </li>`;
  }).join("");
}

function renderEvidence(evidence) {
  $("evidence-count").textContent = `${evidence.length} accepted item${evidence.length === 1 ? "" : "s"}`;
  if (!evidence.length) {
    $("evidence").innerHTML = `<div class="empty-state wide"><strong>No accepted claim-supporting evidence.</strong><span>Retrieved candidates may exist, but none passed the relevance and sufficiency gate.</span></div>`;
    return;
  }
  $("evidence").innerHTML = evidence.map(item => `
    <details class="evidence-card" data-evidence-id="${esc(item.id)}">
      <summary><span class="evidence-type">${esc(item.type)}</span><strong>${esc(item.id)}</strong><span class="scope-tag">${esc(item.scope)}</span></summary>
      <p>${esc(item.summary)}</p>
      <dl><div><dt>Source</dt><dd>${esc(item.source_label)}</dd></div><div><dt>Reliability</dt><dd>${esc(item.reliability)}</dd></div></dl>
    </details>`).join("");
}

function traceSummary(data) {
  return JSON.stringify({
    disclosure: "SANITIZED RECORDED REPLAY — NOT LIVE INFERENCE",
    scenario_id: data.scenario_id,
    source: data.source,
    outcome: data.outcome,
    tool_calls: data.tool_calls,
    claims: data.claims,
    evidence: data.evidence,
    trace: data.trace
  }, null, 2);
}

async function loadScenario(id) {
  const entry = scenarioIndex.find(item => item.id === id) || scenarioIndex[0];
  const response = await fetch(`fixtures/${entry.file}`);
  if (!response.ok) throw new Error(`Fixture request failed (${response.status})`);
  const data = await response.json();
  currentScenario = data;
  const preservedAnchor = new Set(["scenario-explorer", "evidence-title", "benchmark", "architecture-title"])
    .has(window.location.hash.slice(1)) ? window.location.hash : "";
  window.history.replaceState(null, "", `${window.location.pathname}?scenario=${encodeURIComponent(data.scenario_id)}${preservedAnchor}`);
  renderTabs(data.scenario_id);
  $("query").textContent = data.query;
  $("summary").textContent = data.outcome.summary;
  $("execution-mode").textContent = data.execution_mode.toUpperCase();
  $("status").textContent = data.outcome.status;
  $("status").dataset.status = data.outcome.status;
  $("reliability").textContent = data.outcome.reliability;
  $("reliability").dataset.level = data.outcome.reliability;
  $("case-id").textContent = data.source.case_id;
  $("source-model").textContent = `${data.source.provider} · ${data.source.model}`;
  $("disclosure").textContent = data.disclosure;
  renderClaims(data.claims || []);
  renderTools(data);
  renderEvidence(data.evidence || []);
  $("limitations").innerHTML = (data.limitations || []).map(item => `<li>${esc(item)}</li>`).join("");
}

async function boot() {
  const response = await fetch("fixtures/index.json");
  if (!response.ok) throw new Error(`Scenario index request failed (${response.status})`);
  const index = await response.json();
  scenarioIndex = index.scenarios;
  const requested = new URLSearchParams(window.location.search).get("scenario") || window.location.hash.slice(1);
  await loadScenario(scenarioIndex.some(item => item.id === requested) ? requested : scenarioIndex[0].id);
  const anchor = window.location.hash.slice(1);
  if (anchor) {
    document.documentElement.style.scrollBehavior = "auto";
    document.getElementById(anchor)?.scrollIntoView({ block: "start" });
    document.documentElement.style.scrollBehavior = "";
  }
  $("copy-query").addEventListener("click", () => copyText(currentScenario.query, "Query"));
  $("copy-trace").addEventListener("click", () => copyText(traceSummary(currentScenario), "Sanitized trace"));
}

boot().catch(error => {
  document.querySelector("main").innerHTML = `<section class="fatal-error"><strong>Demo load failed.</strong><p>${esc(error.message)}</p><p>Start it with <code>python demo/app.py</code>; do not open the HTML file directly.</p></section>`;
});
