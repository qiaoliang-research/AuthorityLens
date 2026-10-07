const selector = document.getElementById("scenario-select");
const description = document.getElementById("scenario-description");
const initialState = document.getElementById("initial-state");
const timeline = document.getElementById("timeline");
const actionButtons = document.getElementById("action-buttons");
const resetButton = document.getElementById("reset-button");
const assumptionNote = document.getElementById("assumption-note");
const baselineContent = document.getElementById("baseline-content");
const authorityContent = document.getElementById("authority-content");
const authorityChainContent = document.getElementById("authority-chain-content");
const systemStateContent = document.getElementById("system-state-content");
const errorMessage = document.getElementById("error-message");
const viewModeHeading = document.getElementById("view-mode-heading");
const currentStatePanel = document.getElementById("current-state-panel");
const currentStateContent = document.getElementById("current-state-content");
const comparisonGrid = document.getElementById("comparison-grid");

let currentPayload = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderBaseline(data) {
  baselineContent.replaceChildren();
  baselineContent.append(element("p", "target-name", data.target_principal_display));
  baselineContent.append(element("p", "permission-name", data.resource_label));
  const row = element("div", "status-row");
  row.append(element("span", `status-pill status-${data.access_status.toLowerCase()}`, data.access_status));
  baselineContent.append(row);
}

function addListSection(container, title, items, status) {
  if (!items.length) return;
  const section = element("section", "view-section");
  section.append(element("h3", "", title));
  const list = element("ul");
  for (const item of items) {
    const row = element("li");
    if (status) {
      row.append(element("span", `status-pill status-${status.toLowerCase()}`, status));
      row.append(document.createTextNode(" "));
    }
    row.append(document.createTextNode(item.description));
    list.append(row);
  }
  section.append(list);
  container.append(section);
}

function renderAuthorityLens(data) {
  authorityContent.replaceChildren();
  authorityContent.append(element("p", "headline", data.headline));

  const local = element("div", "local-state");
  local.append(element("span", `status-pill status-${data.local_state.status.toLowerCase()}`, data.local_state.status));
  local.append(element("p", "local-detail", data.local_state.text));
  authorityContent.append(local);

  const remaining = [...data.active_items, ...data.residual_items];
  addListSection(authorityContent, "Remaining capabilities", remaining, "REMAINING");
  addListSection(authorityContent, "Pending consequences", data.pending_items, "PENDING");
  addListSection(authorityContent, "Cannot verify", data.unknown_items, "UNKNOWN");
  if (data.empty_state_message) {
    authorityContent.append(element("p", "empty-note", data.empty_state_message));
  }
}

function renderTimeline(data) {
  timeline.replaceChildren();
  for (const [index, step] of data.timeline.entries()) {
    const item = element("li", `timeline-step${index === data.timeline.length - 1 ? " current" : ""}`);
    item.append(element("span", "timeline-marker", String(index + 1)));
    item.append(element("span", "timeline-label", step.label));
    timeline.append(item);
  }
  if (data.control_phase === "after_action") {
    const current = element("li", "timeline-step current-state");
    current.append(element("span", "timeline-marker", "RESULT"));
    current.append(element("span", "timeline-label", data.authority_lens.headline));
    timeline.append(current);
  }
}

function renderCurrentState(data) {
  currentStateContent.replaceChildren();
  for (const text of data.items) {
    currentStateContent.append(element("li", "", text));
  }
  if (!data.items.length) {
    currentStateContent.append(element("li", "", "No current Gmail capability or pending action is represented."));
  }
}

function renderActions(data) {
  actionButtons.replaceChildren();
  for (const action of data.available_actions) {
    const button = element("button", "action-button", action.label);
    button.type = "button";
    button.addEventListener("click", () => runAction(action.id));
    actionButtons.append(button);
  }
  if (!data.available_actions.length) {
    actionButtons.append(element("p", "no-actions", "No further actions are available in this scenario."));
  }
}

function renderAuthorityChain(items) {
  authorityChainContent.replaceChildren();
  if (!items.length) {
    authorityChainContent.append(element("p", "empty-note", "No authority paths are recorded."));
    return;
  }
  for (const link of items) {
    const row = element("div", "chain-link");
    row.append(element("span", "chain-node", link.from));
    row.append(element("span", "chain-arrow", "→"));
    row.append(element("span", "chain-node", link.to));
    row.append(element("span", "chain-scope", link.scope));
    row.append(element("span", `status-pill status-${link.status.toLowerCase()}`, link.status));
    authorityChainContent.append(row);
  }
}

function renderSystemState(state) {
  systemStateContent.replaceChildren();
  const sections = [
    ["Confirmed active authority", state.active_authority],
    ["Residual authority", state.residual_authority],
    ["Unresolved authority", state.unresolved_authority],
    ["Pending effects", state.pending_effects],
    ["Unknown external states", state.unknown_states],
  ];
  for (const [title, items] of sections) {
    const section = element("section", "system-state-section");
    section.append(element("h3", "", title));
    section.append(element("pre", "", JSON.stringify(items, null, 2)));
    systemStateContent.append(section);
  }
}

function render(payload) {
  currentPayload = payload;
  const beforeAction = payload.control_phase === "before_action";
  viewModeHeading.textContent = beforeAction ? "Current State" : "Revocation Outcome";
  currentStatePanel.hidden = !beforeAction;
  comparisonGrid.hidden = beforeAction;
  description.textContent = payload.scenario.description;
  initialState.textContent = payload.scenario.initial_state;
  assumptionNote.hidden = !payload.scenario.assumption_note;
  assumptionNote.textContent = payload.scenario.assumption_note || "";
  renderTimeline(payload);
  renderActions(payload);
  renderAuthorityChain(payload.authority_chain);
  if (beforeAction) renderCurrentState(payload.current_state);
  renderBaseline(payload.baseline);
  renderAuthorityLens(payload.authority_lens);
  renderSystemState(payload.system_state);
  resetButton.disabled = false;
}

function showError(error) {
  errorMessage.textContent = error.message;
  errorMessage.hidden = false;
}

async function readResponse(response) {
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Scenario request failed.");
  return data;
}

async function loadScenario(scenarioId) {
  errorMessage.hidden = true;
  try {
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}`);
    render(await readResponse(response));
  } catch (error) {
    showError(error);
  }
}

async function runAction(actionId) {
  if (!currentPayload) return;
  errorMessage.hidden = true;
  for (const button of actionButtons.querySelectorAll("button")) button.disabled = true;
  try {
    const scenarioId = currentPayload.scenario.id;
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/transition`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: currentPayload.event_log, action: actionId }),
    });
    render(await readResponse(response));
  } catch (error) {
    showError(error);
    renderActions(currentPayload);
  }
}

async function resetScenario() {
  if (!currentPayload) return;
  errorMessage.hidden = true;
  try {
    const scenarioId = currentPayload.scenario.id;
    const response = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/reset`, { method: "POST" });
    render(await readResponse(response));
  } catch (error) {
    showError(error);
  }
}

async function initialize() {
  const response = await fetch("/api/scenarios");
  const scenarios = await readResponse(response);
  for (const scenario of scenarios) {
    const option = element("option", "", scenario.title);
    option.value = scenario.id;
    selector.append(option);
  }
  selector.addEventListener("change", () => loadScenario(selector.value));
  resetButton.addEventListener("click", resetScenario);
  if (scenarios.length) await loadScenario(scenarios[0].id);
}

initialize().catch(showError);
