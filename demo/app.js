const $ = (selector) => document.querySelector(selector);

const esc = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const labels = {
  status: { FULL: "完整回答", PARTIAL: "部分回答", ABSTAIN: "拒绝作答" },
  reliability: { HIGH: "高", MEDIUM: "中", LOW: "低", UNKNOWN: "未知" },
  scope: {
    plant: "单株",
    view: "视角 / 小区",
    group: "组",
    greenhouse: "温室",
    treatment: "处理",
    dataset: "数据集",
    knowledge: "知识"
  },
  type: {
    observation: "观测",
    prediction: "预测",
    knowledge: "知识",
    recommendation: "建议",
    reliability: "可靠性",
    historical_association: "历史关联",
    historical_case: "历史案例",
    sensor: "传感器",
    safety: "安全边界"
  },
  toolStatus: { success: "成功", partial: "部分成功", error: "失败" },
  dispatch: {
    MODEL_GENERATED_TOOL_CALL: "模型生成调用",
    WORKFLOW_DISPATCHED_TOOL: "工作流调度",
    DETERMINISTIC_FALLBACK: "确定性回退",
    NOT_RECORDED: "未记录"
  }
};

const scenarioDescriptions = {
  knowledge_salt: "知识 RAG",
  growth_prediction: "生长预测",
  historical_memory: "历史案例",
  comprehensive: "综合分析",
  safety_refusal: "安全拒答"
};

let scenarioIndex = null;
let currentScenario = null;
let selectedClaim = null;

function localLabel(group, value) {
  return labels[group]?.[value] ?? value ?? "未记录";
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 1800);
}

async function copyText(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  showToast(successMessage);
}

function formatLatency(value) {
  if (value === "NOT_RECORDED" || value === null || value === undefined) return "未记录";
  return `${Number(value).toFixed(value >= 100 ? 0 : 1)} ms`;
}

function renderTabs(activeId) {
  const root = $("#scenario-tabs");
  root.innerHTML = "";
  scenarioIndex.scenarios.forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.role = "tab";
    button.className = `scenario-tab${entry.id === activeId ? " active" : ""}`;
    button.setAttribute("aria-selected", entry.id === activeId ? "true" : "false");
    button.dataset.scenario = entry.id;
    button.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><strong>${esc(scenarioDescriptions[entry.id] || entry.title)}</strong>`;
    button.addEventListener("click", () => loadScenario(entry.id));
    root.append(button);
  });
}

function renderClaims(claims) {
  const root = $("#claims");
  root.innerHTML = "";
  selectedClaim = null;

  if (!claims.length) {
    root.innerHTML = '<p class="empty-state">该场景没有可陈述的事实主张；系统选择保留或拒答。</p>';
    return;
  }

  claims.forEach((claim, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "claim-card";
    button.dataset.support = JSON.stringify(claim.support || []);
    button.innerHTML = `
      <span class="claim-index">${String(index + 1).padStart(2, "0")}</span>
      <span><small>${esc(localLabel("type", claim.type))}</small><strong>${esc(claim.text)}</strong><em>证据：${esc((claim.support || []).join(" · ") || "未关联")}</em></span>`;
    button.addEventListener("click", () => {
      selectedClaim = index;
      root.querySelectorAll(".claim-card").forEach((item, itemIndex) => item.classList.toggle("selected", itemIndex === index));
      highlightEvidence(claim.support || []);
    });
    root.append(button);
  });
}

function renderTools(toolCalls) {
  const root = $("#tools");
  root.innerHTML = "";

  if (!toolCalls.length) {
    root.innerHTML = '<li class="timeline-empty"><strong>未执行工具</strong><p>系统在证据不足或请求越界时，可以直接拒绝生成无依据数值。</p></li>';
    return;
  }

  toolCalls.forEach((call) => {
    const item = document.createElement("li");
    item.className = "timeline-item";
    item.dataset.status = call.status;
    item.innerHTML = `
      <span class="timeline-index">${String(call.index).padStart(2, "0")}</span>
      <details>
        <summary><span><strong><code>${esc(call.name)}</code></strong><small>${esc(call.arguments_summary)}</small></span><span class="tool-status">${esc(localLabel("toolStatus", call.status))}</span></summary>
        <div class="tool-detail-grid">
          <div><span>调用来源</span><strong>${esc(localLabel("dispatch", call.dispatch_source))}<br>${esc(call.dispatch_source)}</strong></div>
          <div><span>作用范围</span><strong>${esc(localLabel("scope", call.scope))} · ${esc(call.scope)}</strong></div>
          <div><span>证据数量</span><strong>${esc(call.evidence_count ?? 0)}</strong></div>
          <div><span>耗时</span><strong>${esc(formatLatency(call.latency_ms))}</strong></div>
          <div><span>错误代码</span><strong>${esc(call.error_code || "无")}</strong></div>
        </div>
      </details>`;
    root.append(item);
  });
}

function renderEvidence(evidence) {
  const root = $("#evidence");
  root.innerHTML = "";
  $("#evidence-count").textContent = `${evidence.length} 条证据`;

  if (!evidence.length) {
    root.innerHTML = '<p class="empty-state">没有可用于支撑结论的证据。</p>';
    return;
  }

  evidence.forEach((item) => {
    const card = document.createElement("details");
    card.className = "evidence-card";
    card.dataset.evidenceId = item.id;
    card.innerHTML = `
      <summary><strong>${esc(item.id)}</strong><span class="evidence-type">${esc(localLabel("type", item.type))}</span><span class="scope-tag">${esc(localLabel("scope", item.scope))}</span></summary>
      <p>${esc(item.summary)}</p>
      <dl>
        <div><dt>来源</dt><dd>${esc(item.source_label)}</dd></div>
        <div><dt>范围</dt><dd>${esc(localLabel("scope", item.scope))} · ${esc(item.scope)}</dd></div>
        <div><dt>可靠性</dt><dd>${esc(localLabel("reliability", item.reliability))} · ${esc(item.reliability)}</dd></div>
      </dl>`;
    root.append(card);
  });
}

function highlightEvidence(ids) {
  const wanted = new Set(ids);
  document.querySelectorAll(".evidence-card").forEach((card) => {
    const active = wanted.has(card.dataset.evidenceId);
    card.classList.toggle("highlight", active);
    card.classList.toggle("highlighted", active);
    if (active) {
      card.open = true;
    }
  });
  const first = document.querySelector(".evidence-card.highlighted");
  first?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderLimitations(limitations) {
  const root = $("#limitations");
  root.innerHTML = limitations.length
    ? limitations.map((item) => `<li>${esc(item)}</li>`).join("")
    : "<li>该记录未附加额外限制。</li>";
}

function traceSummary(scenario) {
  const lines = [
    "Tomato Agent · 已录制回放",
    `场景：${scenario.title}`,
    `问题：${scenario.query}`,
    `状态：${scenario.outcome.status} / 可靠性：${scenario.outcome.reliability}`,
    "",
    "工具调用："
  ];
  if (!scenario.tool_calls.length) lines.push("- 未执行工具");
  scenario.tool_calls.forEach((call) => {
    lines.push(`${call.index}. ${call.name} | ${call.dispatch_source} | ${call.status} | ${call.arguments_summary}`);
  });
  lines.push("", `结论：${scenario.outcome.summary}`, "", `来源：${scenario.source.benchmark} / ${scenario.source.case_id}`);
  return lines.join("\n");
}

function renderScenario(scenario) {
  currentScenario = scenario;
  renderTabs(scenario.scenario_id);
  $("#query").textContent = scenario.query;
  $("#execution-mode").textContent = "已录制回放";
  $("#status").textContent = `${localLabel("status", scenario.outcome.status)} · ${scenario.outcome.status}`;
  $("#status").dataset.status = scenario.outcome.status;
  $("#reliability").textContent = `${localLabel("reliability", scenario.outcome.reliability)} · ${scenario.outcome.reliability}`;
  $("#reliability").dataset.level = scenario.outcome.reliability;
  $("#case-id").textContent = scenario.source.case_id;
  $("#source-model").textContent = `${scenario.source.model} · ${scenario.source.provider}`;
  $("#summary").textContent = scenario.outcome.summary;
  $("#disclosure").textContent = scenario.disclosure;

  const trace = scenario.trace || {};
  const toolCount = scenario.tool_calls.length;
  const latency = trace.latency_ms === undefined ? "未记录" : formatLatency(trace.latency_ms);
  $("#trace-meta").textContent = `${toolCount} 次工具执行 · ${trace.evidence_collected ?? scenario.evidence.length} 条证据 · 总耗时 ${latency}`;

  renderClaims(scenario.claims || []);
  renderTools(scenario.tool_calls || []);
  renderEvidence(scenario.evidence || []);
  renderLimitations(scenario.limitations || []);
}

async function loadScenario(id) {
  const entry = scenarioIndex.scenarios.find((item) => item.id === id);
  if (!entry) throw new Error(`未知场景：${id}`);
  const response = await fetch(`fixtures/${entry.file}`);
  if (!response.ok) throw new Error(`无法加载场景：${entry.file}`);
  renderScenario(await response.json());
}

async function init() {
  const response = await fetch("fixtures/index.json");
  if (!response.ok) throw new Error("无法加载演示场景索引");
  scenarioIndex = await response.json();
  await loadScenario("comprehensive");

  $("#copy-query").addEventListener("click", () => copyText(currentScenario.query, "问题已复制"));
  $("#copy-trace").addEventListener("click", () => copyText(traceSummary(currentScenario), "脱敏 Trace 已复制"));
}

init().catch((error) => {
  console.error(error);
  $("#scenario-tabs").innerHTML = '<p class="fatal-error">场景加载失败。请通过本地静态服务器打开本页面，而不是直接双击 HTML 文件。</p>';
});
