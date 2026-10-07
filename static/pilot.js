(() => {
  const screen = document.getElementById("screen");
  const stopButton = document.getElementById("stop-session");
  const stopDialog = document.getElementById("stop-dialog");
  const answers = ["YES", "NO", "CANNOT TELL"];

  async function request(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The local session could not continue.");
    return data;
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function button(label, handler, className = "primary-button") {
    const node = element("button", label, className);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }

  function showError(error) {
    screen.setAttribute("aria-busy", "false");
    const note = element("p", error.message || "A local session error occurred.", "error-note");
    screen.prepend(note);
  }

  function renderInformation(state) {
    screen.append(element("p", "INFORMATION", "eyebrow"));
    screen.append(element("h2", "Before you continue"));
    screen.append(element("p", state.message));
    const note = element("div", undefined, "notice");
    note.append(element("strong", "Placeholder only"));
    note.append(element("p", "This is not an approved consent form and must not be used to recruit participants. This prepared runner is for local synthetic checks only."));
    note.append(element("p", "Answers remain in temporary memory on this computer for a local researcher export. They are not sent to an outside service."));
    screen.append(note);
    const label = element("label", undefined, "check-label");
    const check = document.createElement("input");
    check.type = "checkbox";
    check.required = true;
    label.append(check, document.createTextNode(" I have read this information and want to continue through this local prototype."));
    screen.append(label);
    const next = button("Continue to instructions", async () => {
      if (!check.checked) return;
      next.disabled = true;
      try { render(await request("/api/pilot/information/continue", {})); }
      catch (error) { showError(error); next.disabled = false; }
    });
    next.disabled = true;
    check.addEventListener("change", () => { next.disabled = !check.checked; });
    screen.append(next);
  }

  function renderBriefing(state) {
    screen.append(element("p", "INSTRUCTIONS", "eyebrow"));
    screen.append(element("h2", "How to answer"));
    screen.append(element("p", state.message));
    screen.append(element("p", "Choose YES, NO, or CANNOT TELL based on the information shown and the question asked. You may stop at any time."));
    screen.append(button("Begin practice", async () => {
      try { render(await request("/api/pilot/briefing/continue", {})); }
      catch (error) { showError(error); }
    }));
  }

  function renderStimulus(stimulus) {
    const card = element("section", undefined, "stimulus-card");
    card.setAttribute("aria-label", "Scenario information");
    const local = stimulus.local_permission || stimulus;
    if (local) {
      card.append(element("h3", "Local permission"));
      const localRow = element("div", undefined, "permission-row");
      const identity = element("div");
      identity.append(element("strong", local.target));
      identity.append(element("span", local.resource_label));
      localRow.append(identity, element("span", local.status, "status-pill"));
      card.append(localRow);
      if (local.text) card.append(element("p", local.text, "supporting-text"));
      if (stimulus.detail) card.append(element("p", stimulus.detail, "supporting-text"));
      if (stimulus.headline) card.append(element("h3", stimulus.headline));
      for (const section of stimulus.sections || []) {
        const group = element("section", undefined, "consequence-section");
        group.append(element("h4", section.title));
        const list = document.createElement("ul");
        for (const item of section.items || []) list.append(element("li", item));
        group.append(list);
        card.append(group);
      }
      if (stimulus.empty_state_message) card.append(element("p", stimulus.empty_state_message, "supporting-text"));
      return card;
    }
    const row = element("div", undefined, "permission-row");
    const identity = element("div");
    identity.append(element("strong", stimulus.target));
    identity.append(element("span", stimulus.resource_label));
    row.append(identity, element("span", stimulus.status, "status-pill"));
    card.append(row);
    if (stimulus.text) card.append(element("p", stimulus.text, "supporting-text"));
    return card;
  }

  function addResponseOptions(form, includeConfidence) {
    const answerGroup = element("fieldset", undefined, "answer-group");
    answerGroup.append(element("legend", "Your answer"));
    for (const answer of answers) {
      const label = element("label", undefined, "choice");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "answer";
      input.value = answer;
      input.required = true;
      label.append(input, document.createTextNode(answer));
      answerGroup.append(label);
    }
    form.append(answerGroup);

    if (includeConfidence) {
      const confidenceGroup = element("fieldset", undefined, "confidence-group");
      confidenceGroup.append(element("legend", "Confidence (optional; 1 = not at all sure, 5 = very sure)"));
      for (let value = 1; value <= 5; value += 1) {
        const label = element("label", undefined, "confidence-choice");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = "confidence";
        input.value = String(value);
        label.append(input, document.createTextNode(String(value)));
        confidenceGroup.append(label);
      }
      form.append(confidenceGroup);
    }
  }

  function renderPractice(trial) {
    screen.append(element("p", "PRACTICE", "eyebrow"));
    screen.append(element("h2", "Try one example"));
    screen.append(renderStimulus(trial.stimulus));
    screen.append(element("h3", trial.question, "question"));
    const form = document.createElement("form");
    addResponseOptions(form, false);
    const submit = element("button", "Continue", "primary-button");
    submit.type = "submit";
    form.append(submit);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const response = new FormData(form).get("answer");
      if (!response) return;
      submit.disabled = true;
      try { render(await request("/api/pilot/practice/submit", { response })); }
      catch (error) { showError(error); submit.disabled = false; }
    });
    screen.append(form);
  }

  function renderPracticeFeedback(state) {
    screen.append(element("p", "PRACTICE", "eyebrow"));
    screen.append(element("h2", "Practice complete"));
    screen.append(element("p", state.message));
    screen.append(button("Start the questions", async () => {
      try { render(await request("/api/pilot/practice/continue", {})); }
      catch (error) { showError(error); }
    }));
  }

  function renderMeasuredTrial(trial) {
    screen.append(element("p", `QUESTION ${trial.order} OF ${trial.total}`, "eyebrow"));
    screen.append(element("p", trial.scenario_context, "scenario-context"));
    screen.append(renderStimulus(trial.stimulus));
    screen.append(element("h2", trial.question, "question"));
    const form = document.createElement("form");
    addResponseOptions(form, true);
    const submit = element("button", "Submit answer", "primary-button");
    submit.type = "submit";
    submit.disabled = true;
    form.append(submit);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = new FormData(form);
      const response = values.get("answer");
      if (!response || submit.disabled) return;
      submit.disabled = true;
      const confidenceValue = values.get("confidence");
      const body = { response };
      if (confidenceValue) body.confidence = Number(confidenceValue);
      try { render(await request("/api/pilot/response", body)); }
      catch (error) { showError(error); submit.disabled = false; }
    });
    screen.append(form);
    screen.setAttribute("aria-busy", "true");
    // Timing begins only after the complete stimulus, question, and controls are painted.
    requestAnimationFrame(() => requestAnimationFrame(async () => {
      try {
        await request("/api/pilot/trial/rendered", { order: trial.order });
        submit.disabled = false;
        screen.setAttribute("aria-busy", "false");
      } catch (error) { showError(error); }
    }));
  }

  function renderEnd(state) {
    screen.append(element("p", state.phase === "complete" ? "COMPLETE" : "INCOMPLETE", "eyebrow"));
    screen.append(element("h2", state.phase === "complete" ? "Thank you" : "Session stopped"));
    screen.append(element("p", state.message));
    screen.append(element("p", "No correctness feedback or score is shown in this session."));
  }

  function render(state) {
    screen.replaceChildren();
    screen.setAttribute("aria-busy", "false");
    stopButton.hidden = ["complete", "incomplete"].includes(state.phase);
    if (state.phase === "information") renderInformation(state);
    else if (state.phase === "briefing") renderBriefing(state);
    else if (state.phase === "practice") renderPractice(state.trial);
    else if (state.phase === "practice_feedback") renderPracticeFeedback(state);
    else if (state.phase === "trial") renderMeasuredTrial(state.trial);
    else renderEnd(state);
  }

  stopButton.addEventListener("click", () => stopDialog.showModal());
  document.getElementById("continue-session").addEventListener("click", () => stopDialog.close());

  async function stopSession(path) {
    stopDialog.close();
    stopButton.disabled = true;
    try { render(await request(path, {})); }
    catch (error) { showError(error); stopButton.disabled = false; }
  }
  document.getElementById("keep-partial").addEventListener("click", () => stopSession("/api/pilot/abort"));
  document.getElementById("discard-answers").addEventListener("click", () => stopSession("/api/pilot/withdraw"));

  request("/api/pilot/state").then(render).catch(showError);
})();
