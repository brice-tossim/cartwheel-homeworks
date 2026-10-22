// Trace review page: the Read view.
//
// Everything the page shows comes from the review server's JSON routes; the
// page keeps no copy of its own except a few per-viewer conveniences in
// localStorage (which conversation was open, which panels were folded).

const ROLE_ORDER = ["shopper", "merchant", "support"];
const ACTIONS = [
  ["refund", "Refund"],
  ["cancel", "Cancel"],
  ["hand-off", "Hand-off"],
];

const state = {
  source: null,
  fallbackReason: null,
  traceLink: null,
  conversations: [],
  batches: [],
  notes: [],
  suggestions: [],
  rules: null,
  filters: { batch: "", search: "", role: "", action: "", tool: "", twoTurns: false, unread: false },
  selectedId: remembered("selected", null),
  listOpen: remembered("listOpen", true),
  rulesOpen: remembered("rulesOpen", true),
  promptOpen: false,
  openAnswers: new Set(),
  editingNoteId: null,
  drafts: {},
  pendingSelection: null,
};

const $ = (id) => document.getElementById(id);

// -- small helpers ------------------------------------------------------------

function remembered(key, fallback) {
  try {
    const value = localStorage.getItem(`review.${key}`);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

function remember(key, value) {
  try {
    localStorage.setItem(`review.${key}`, JSON.stringify(value));
  } catch {
    // Storage can be unavailable (private window); the page works without it.
  }
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

const cap = (text) => (text ? text[0].toUpperCase() + text.slice(1) : "");
const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
const shortId = (id) => String(id ?? "").slice(0, 8);

function clip(text, length) {
  const value = String(text ?? "").replace(/\s+/g, " ").trim();
  return value.length > length ? `${value.slice(0, length).trimEnd()}…` : value;
}

function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 2600);
}

function flash(element) {
  if (!element) return;
  element.scrollIntoView({ block: "center", behavior: "smooth" });
  element.classList.remove("is-flashing");
  void element.offsetWidth;
  element.classList.add("is-flashing");
}

// -- server -------------------------------------------------------------------

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} on ${url}`);
  return response.json();
}

async function postJSON(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `${response.status} on ${url}`);
  return data;
}

async function loadAll(refresh = false) {
  const [loaded, notes, suggestions, rules] = await Promise.all([
    getJSON(`/api/conversations${refresh ? "?refresh=1" : ""}`),
    getJSON("/api/notes"),
    getJSON("/api/suggestions"),
    getJSON("/api/rules"),
  ]);
  state.source = loaded.source;
  state.fallbackReason = loaded.fallback_reason;
  state.traceLink = loaded.trace_link;
  state.conversations = loaded.conversations;
  state.batches = loaded.batches;
  if (state.filters.batch && state.filters.batch !== NO_BATCH && !findBatch(state.filters.batch)) {
    state.filters.batch = "";
  }
  state.notes = notes;
  state.suggestions = suggestions;
  state.rules = rules;
  if (!findConversation(state.selectedId)) {
    state.selectedId = state.conversations[0]?.session_id ?? null;
  }
  renderFilterOptions();
  renderAll({ keepScroll: false });
}

async function refreshNotes() {
  state.notes = await getJSON("/api/notes");
}

async function refreshSuggestions() {
  state.suggestions = await getJSON("/api/suggestions");
}

// -- what the data says ---------------------------------------------------------

const findConversation = (id) => state.conversations.find((c) => c.session_id === id) ?? null;
const selected = () => findConversation(state.selectedId);
const liveNotes = (traceId) => state.notes.filter((n) => n.trace_id === traceId && !n.removed_ts);
const failureNotes = (traceId) => liveNotes(traceId).filter((n) => n.kind !== "no_failure");
const isClean = (traceId) => liveNotes(traceId).some((n) => n.kind === "no_failure");
const isRead = (traceId) => liveNotes(traceId).length > 0;
const pendingSuggestions = (traceId) => state.suggestions.filter(
  (s) => s.trace_id === traceId && s.status === "pending",
);

function allTurns() {
  return state.conversations.flatMap((c) => c.turns);
}

function readState(conversation) {
  if (conversation.session_id === state.selectedId) return ["reading now", "state-reading"];
  const turns = conversation.turns;
  const read = turns.filter((t) => isRead(t.trace_id)).length;
  if (read === 0) return ["not read", ""];
  if (read < turns.length) return [`${read} of ${turns.length} turns read`, "state-note"];
  const noteCount = turns.reduce((sum, t) => sum + failureNotes(t.trace_id).length, 0);
  return noteCount ? [plural(noteCount, "note"), "state-note"] : ["no failure", "state-clean"];
}

function searchText(conversation) {
  if (!conversation.searchText) {
    conversation.searchText = [
      conversation.scenario_id,
      conversation.session_id,
      ...conversation.turns.map((t) => t.trace_id),
      conversation.role,
      ...conversation.tools,
      ...conversation.turns.flatMap((t) => [t.customer, t.reply, ...t.steps.map((s) => s.reason)]),
    ].filter(Boolean).join(" ").toLowerCase();
  }
  return conversation.searchText;
}

function matchesAction(conversation, action) {
  if (!action) return true;
  if (action === "any") return conversation.actions.length > 0;
  return conversation.actions.includes(action);
}

// The batch picker's value for the traces in no batch; batch file names never start with "_".
const NO_BATCH = "__none__";

const findBatch = (name) => state.batches.find((b) => b.name === name) ?? null;

function inBatch(conversation, batch) {
  const ids = new Set(batch.trace_ids);
  return conversation.turns.some((t) => ids.has(t.trace_id));
}

function matchesBatch(conversation, name) {
  if (!name) return true;
  if (name === NO_BATCH) return !state.batches.some((b) => inBatch(conversation, b));
  const batch = findBatch(name);
  return batch ? inBatch(conversation, batch) : true;
}

function visibleConversations() {
  const f = state.filters;
  const words = f.search.toLowerCase().split(/\s+/).filter(Boolean);
  return state.conversations.filter((c) => (
    matchesBatch(c, f.batch)
    && (!f.role || c.role === f.role)
    && matchesAction(c, f.action)
    && (!f.tool || c.tools.includes(f.tool))
    && (!f.twoTurns || c.turns.length > 1)
    && (!f.unread || c.turns.some((t) => !isRead(t.trace_id)))
    && words.every((word) => searchText(c).includes(word))
  ));
}

// -- rendering: frame -------------------------------------------------------------

// When the filters drop the open conversation, open the first one they keep.
function followFilters() {
  const list = visibleConversations();
  if (list.some((c) => c.session_id === state.selectedId)) return false;
  state.selectedId = list[0]?.session_id ?? null;
  state.promptOpen = false;
  state.editingNoteId = null;
  if (state.selectedId) remember("selected", state.selectedId);
  return true;
}

function renderAll({ keepScroll = true } = {}) {
  const panes = [$("conversation"), $("side"), $("list-panel")];
  const scrolls = panes.map((pane) => pane.scrollTop);
  const moved = followFilters();
  renderTopbar();
  renderList();
  renderConversation();
  renderSide();
  renderListVisibility();
  if (keepScroll) panes.forEach((pane, i) => { pane.scrollTop = scrolls[i]; });
  if (moved) [$("conversation"), $("side")].forEach((pane) => { pane.scrollTop = 0; });
}

function renderTopbar() {
  const source = $("source");
  source.hidden = !state.source;
  source.className = `source ${state.source === "langfuse" ? "live" : "export"}`;
  source.textContent = state.source === "langfuse" ? "Live from Langfuse" : "Local export";
  const fallback = $("fallback");
  fallback.hidden = state.source !== "export";
  fallback.innerHTML = `Showing the local export because Langfuse could not be reached: <code>${esc(state.fallbackReason)}</code>.`;
  const turns = allTurns();
  const read = turns.filter((t) => isRead(t.trace_id)).length;
  $("progress-text").innerHTML = `<strong>${read}</strong> of ${turns.length} traces read`;
  const bar = $("progress-bar");
  bar.style.width = turns.length ? `${(read / turns.length) * 100}%` : "0";
  bar.style.minWidth = read ? "6px" : "0";
}

function renderListVisibility() {
  $("list-panel").hidden = !state.listOpen;
  $("list-rail").hidden = state.listOpen;
  const list = visibleConversations();
  const index = list.findIndex((c) => c.session_id === state.selectedId);
  $("rail-label").textContent = index >= 0
    ? `Conversations · ${index + 1} of ${list.length}`
    : `Conversations · ${list.length}`;
}

function option(value, label, current) {
  return `<option value="${esc(value)}"${value === current ? " selected" : ""}>${esc(label)}</option>`;
}

function renderFilterOptions() {
  const all = state.conversations;
  const f = state.filters;
  const roles = [...new Set(all.map((c) => c.role).filter(Boolean))].sort(
    (a, b) => (ROLE_ORDER.indexOf(a) + 99 * (ROLE_ORDER.indexOf(a) < 0)) - (ROLE_ORDER.indexOf(b) + 99 * (ROLE_ORDER.indexOf(b) < 0)),
  );
  $("batch").innerHTML = option("", `All traces · ${all.length}`, f.batch)
    + state.batches.map((b) => option(b.name, `${b.name} · ${all.filter((c) => inBatch(c, b)).length}`, f.batch)).join("")
    + option(NO_BATCH, `Not in a batch · ${all.filter((c) => matchesBatch(c, NO_BATCH)).length}`, f.batch);
  $("role").innerHTML = option("", `Everyone · ${all.length}`, f.role)
    + roles.map((role) => option(role, `${cap(role)} · ${all.filter((c) => c.role === role).length}`, f.role)).join("");
  $("action").innerHTML = option("", `No filter · ${all.length}`, f.action)
    + option("any", `Refund, cancel or hand-off · ${all.filter((c) => c.actions.length).length}`, f.action)
    + ACTIONS.map(([value, label]) => option(value, `${label} · ${all.filter((c) => c.actions.includes(value)).length}`, f.action)).join("");
  const tools = [...new Set(all.flatMap((c) => c.tools))].sort();
  $("tool").innerHTML = option("", "Any tool", f.tool)
    + tools.map((tool) => option(tool, `${tool} · ${all.filter((c) => c.tools.includes(tool)).length}`, f.tool)).join("");
  $("two-turns").textContent = `Two turns · ${all.filter((c) => c.turns.length > 1).length}`;
}

// -- rendering: conversation list ---------------------------------------------------

function renderList() {
  const list = visibleConversations();
  $("list-count").textContent = plural(list.length, "conversation");
  $("trace-count").textContent = plural(list.reduce((sum, c) => sum + c.turns.length, 0), "trace");
  $("two-turns").setAttribute("aria-pressed", String(state.filters.twoTurns));
  $("unread").setAttribute("aria-pressed", String(state.filters.unread));
  $("list").innerHTML = list.length
    ? list.map(listRow).join("")
    : `<p class="empty">No conversation matches these filters.</p>`;
}

function listRow(conversation) {
  const [label, tone] = readState(conversation);
  const tools = conversation.tools.length;
  const write = conversation.actions.join(" · ");
  const isSelected = conversation.session_id === state.selectedId;
  return `<button type="button" class="row-button${isSelected ? " is-selected" : ""}" data-id="${esc(conversation.session_id)}"${isSelected ? ' aria-current="true"' : ""}>
    <span class="row-snippet">${esc(clip(conversation.turns[0]?.customer, 110))}</span>
    <span class="row-meta">
      <span>${esc(cap(conversation.role) || "Unknown caller")}</span>
      <span>${plural(conversation.turns.length, "turn")}</span>
      <span>${tools ? plural(tools, "tool") : "no tool"}</span>
      ${write ? `<span class="write">${esc(write)}</span>` : ""}
      <span class="${tone}">${esc(label)}</span>
    </span>
  </button>`;
}

// -- rendering: conversation ---------------------------------------------------------

const ICON_CHECK = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3 3 7-7"></path></svg>';
const ICON_CROSS = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 4l8 8"></path><path d="M12 4l-8 8"></path></svg>';
const ICON_LEFT = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3L5 8l5 5"></path></svg>';
const ICON_RIGHT = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3l5 5-5 5"></path></svg>';
const ICON_OUT = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h4v4"></path><path d="M13 3L7 9"></path><path d="M12 9.5V13H3V4h3.5"></path></svg>';
const ICON_INFO = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="8" cy="8" r="6.5"></circle><path d="M8 7.5v4"></path><path d="M8 4.8v.2"></path></svg>';

function renderConversation() {
  const pane = $("conversation");
  const conversation = selected();
  if (!conversation) {
    pane.innerHTML = `<p class="empty">${state.conversations.length ? "No conversation matches these filters." : "No conversation to show."}</p>`;
    return;
  }
  pane.innerHTML = `<div class="conversation-inner">
    ${whoCard(conversation)}
    ${conversation.turns.map((turn, i) => turnCard(conversation, turn, i)).join("")}
  </div>`;
  pane.querySelectorAll(".turn").forEach((turn) => markQuotes(turn, marksFor(turn.dataset.traceId)));
}

function callerLine(conversation) {
  const parts = [cap(conversation.role) || "Unknown caller"];
  if (conversation.user_id) parts.push(`user ${conversation.user_id}`);
  parts.push(conversation.store_id ? `store ${conversation.store_id}` : "no store");
  return parts.join(" · ");
}

function langfuseLink(traceId, label) {
  if (!state.traceLink) return "";
  return `<a class="button" href="${esc(state.traceLink + traceId)}" target="_blank" rel="noopener">${label}${ICON_OUT}</a>`;
}

function whoCard(conversation) {
  const list = visibleConversations();
  const index = list.findIndex((c) => c.session_id === conversation.session_id);
  const position = index >= 0 ? `${index + 1} of ${list.length}` : "not in this list";
  const prompt = conversation.turns[0]?.system_prompt;
  return `<section class="card who" aria-label="Who is asking">
    <div class="who-top">
      <div>
        <span class="label">Who is asking</span>
        <h1>${esc(callerLine(conversation))}</h1>
      </div>
      <div class="nav">
        <button type="button" class="icon-button" data-action="previous" aria-label="Previous conversation"${index <= 0 ? " disabled" : ""}>${ICON_LEFT}</button>
        <span>${position}</span>
        <button type="button" class="icon-button" data-action="next" aria-label="Next conversation"${index < 0 || index >= list.length - 1 ? " disabled" : ""}>${ICON_RIGHT}</button>
      </div>
    </div>
    <div class="who-meta">
      ${conversation.scenario_id ? `<span>scenario ${esc(conversation.scenario_id)}</span>` : ""}
      <span>session ${esc(shortId(conversation.session_id))}</span>
      <span>${plural(conversation.turns.length, "turn")}</span>
      ${conversation.prompt_version ? `<span>prompt ${esc(shortId(conversation.prompt_version))}</span>` : ""}
    </div>
    <div class="row">
      ${prompt ? `<button type="button" class="button" data-action="toggle-prompt" aria-expanded="${state.promptOpen}">${state.promptOpen ? "Hide" : "Show"} system prompt</button>` : ""}
      ${langfuseLink(conversation.turns[0]?.trace_id, "Open in Langfuse")}
    </div>
    ${state.promptOpen && prompt ? `<pre class="prompt">${esc(prompt)}</pre>` : ""}
  </section>`;
}

function turnBadge(traceId) {
  const notes = failureNotes(traceId).length;
  if (notes) return `<span class="badge note">${plural(notes, "note")}</span>`;
  if (isClean(traceId)) return `<span class="badge clean">no failure</span>`;
  return `<span class="badge">not read</span>`;
}

function timeOf(timestamp) {
  const match = String(timestamp ?? "").match(/T(\d\d:\d\d:\d\d)/);
  return match ? `${match[1]} UTC` : "";
}

function marksFor(traceId) {
  const notes = liveNotes(traceId)
    .filter((n) => n.quote)
    .map((n) => ({ quote: n.quote, className: "note-mark", data: { noteId: n.id } }));
  const suggested = pendingSuggestions(traceId)
    .filter((s) => s.quote)
    .map((s) => ({ quote: s.quote, className: "ai-mark", data: { suggestionId: s.id } }));
  return [...notes, ...suggested];
}

function turnCard(conversation, turn, i) {
  const count = conversation.turns.length;
  const steps = turn.steps.length
    ? `<ol class="steps">${turn.steps.map((step, n) => stepItem(turn, step, n)).join("")}</ol>`
    : `<p class="no-tools">${ICON_INFO}No tool call in this turn.</p>`;
  return `<article class="card turn" id="turn-${esc(turn.trace_id)}" data-trace-id="${esc(turn.trace_id)}" aria-label="Turn ${i + 1} of ${count}">
    <div class="turn-head">
      <span><strong>Turn ${i + 1} of ${count}</strong> <span class="muted">· ${esc(timeOf(turn.timestamp))} ·</span> <code>trace ${esc(shortId(turn.trace_id))}</code></span>
      ${turnBadge(turn.trace_id)}
    </div>
    <div class="turn-body">
      <div class="customer" data-part="customer">
        <span class="label">Customer</span>
        <p>${esc(turn.customer ?? "")}</p>
      </div>
      ${steps}
      ${replyBlock(turn)}
    </div>
  </article>`;
}

function replyBlock(turn) {
  if (turn.reply == null) {
    return `<div class="reply missing"><span class="label">Reply to the customer</span><p class="muted" style="margin:0">No reply was recorded for this turn.</p></div>`;
  }
  return `<div class="reply" data-part="reply">
    <span class="label">Reply to the customer</span>
    <div class="reply-text">${markdown(turn.reply)}</div>
  </div>`;
}

function argumentsText(args) {
  if (args == null) return "";
  if (typeof args !== "object" || Array.isArray(args)) return JSON.stringify(args);
  return Object.entries(args)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
    .join(", ");
}

function statusChip(step) {
  if (step.ok === true) return `<span class="status ok">${ICON_CHECK}ok</span>`;
  if (step.ok === false) return `<span class="status failed">${ICON_CROSS}failed · ${esc(step.error)}</span>`;
  return `<span class="status unknown">no answer recorded</span>`;
}

function stepItem(turn, step, n) {
  const key = `${turn.trace_id}:${n}`;
  const open = state.openAnswers.has(key);
  const kind = step.changes_data ? " write" : step.ok === false ? " failed" : "";
  const reason = step.reason
    ? `<p class="reason"><span class="who-said">Agent · </span>${esc(step.reason)}</p>`
    : "";
  return `<li class="step" data-step="${n + 1}">
    <span class="step-number" aria-hidden="true">${n + 1}</span>
    <div class="step-body">
      ${reason}
      <div class="tool${kind}">
        <div class="tool-line">
          ${step.changes_data ? '<span class="tag-write">Changes data</span>' : ""}
          <code class="tool-call">${esc(step.tool)}(${esc(argumentsText(step.arguments))})</code>
          ${statusChip(step)}
          ${step.summary ? `<span class="summary">${esc(step.summary)}</span>` : ""}
        </div>
        ${answerDetails(step, key, open)}
      </div>
    </div>
  </li>`;
}

function answerDetails(step, key, open) {
  if (step.ok === false) {
    return step.error_reason ? `<span class="error-reason">${esc(step.error_reason)}</span>` : "";
  }
  if (step.result == null) return "";
  const note = step.result && typeof step.result === "object" && step.result.note
    ? `<span class="error-reason muted">${esc(step.result.note)}</span>`
    : "";
  if (step.folded) {
    const toggle = `<button type="button" class="link-button" data-action="toggle-answer" data-key="${esc(key)}" aria-expanded="${open}">${open ? "Hide the full answer" : `Show the full answer (${step.result_chars.toLocaleString("en-US")} characters)`}</button>`;
    return `${note}${toggle}${open ? prettyJson(step.result) : ""}`;
  }
  if (step.summary) return note;
  return fieldsOrJson(step.result);
}

function fieldsOrJson(result) {
  let shown = result;
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const entries = Object.entries(result).filter(([key]) => key !== "ok");
    const nested = entries.filter(([, value]) => value && typeof value === "object" && !Array.isArray(value));
    shown = entries.length === 1 && nested.length === 1 ? nested[0][1] : Object.fromEntries(entries);
  }
  const flat = shown && typeof shown === "object" && !Array.isArray(shown)
    && Object.values(shown).every((value) => value === null || typeof value !== "object")
    && Object.keys(shown).length <= 16;
  if (!flat) return prettyJson(result);
  return `<dl class="fields">${Object.entries(shown).map(([key, value]) => (
    `<div><dt>${esc(key.replace(/_/g, " "))}</dt><dd>${esc(value === null ? "—" : String(value))}</dd></div>`
  )).join("")}</dl>`;
}

function prettyJson(value) {
  const text = esc(JSON.stringify(value, null, 2));
  return `<pre class="json">${text.replace(/^(\s*)(&quot;.*?&quot;)(:)/gm, '$1<span class="key">$2</span>$3')}</pre>`;
}

// Mark each saved quote where it first appears in a turn: in the customer
// message, a step's reason (with its label) or the reply. Whitespace is
// ignored, so a quote spanning lines, list items or bold words still matches.
function markQuotes(turn, marks) {
  const parts = [...turn.querySelectorAll(".customer p, .reason, .reply-text")];
  marks.forEach((mark) => {
    const found = parts.map((part) => findQuote(part, mark.quote)).find(Boolean);
    if (found && !found.some((c) => c.node.parentElement.closest("mark"))) wrapChars(found, mark);
  });
}

// The characters of a quote inside a part, each with its text node and
// offset, or null when the part does not contain the quote.
function findQuote(part, quote) {
  const chars = [];
  const walker = document.createTreeWalker(part, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    [...node.data].forEach((char, offset) => {
      if (!/\s/.test(char)) chars.push({ node, offset, char });
    });
  }
  const needle = quote.replace(/\s+/g, "");
  const at = needle ? chars.map((c) => c.char).join("").indexOf(needle) : -1;
  return at < 0 ? null : chars.slice(at, at + needle.length);
}

// Wrap the found characters in one mark per text node they fall in.
function wrapChars(chars, mark) {
  const ranges = new Map();
  chars.forEach(({ node, offset }) => {
    const range = ranges.get(node) ?? { start: offset, end: offset };
    ranges.set(node, { start: range.start, end: offset + 1 });
  });
  ranges.forEach(({ start, end }, node) => {
    const middle = node.splitText(start);
    middle.splitText(end - start);
    const element = document.createElement("mark");
    element.className = mark.className;
    Object.assign(element.dataset, mark.data);
    middle.replaceWith(element);
    element.append(middle);
  });
}

// Bold text: the parts between ** markers alternate plain and bold.
function inline(text) {
  return String(text).split("**").map((piece, i) => (i % 2 ? `<strong>${esc(piece)}</strong>` : esc(piece))).join("");
}

// A small Markdown reader for replies: paragraphs, bold, and nested lists.
function markdown(raw) {
  const lines = String(raw).replace(/\r/g, "").split("\n");
  const stack = [];
  let html = "";
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) html += `<p>${inline(paragraph.join(" "))}</p>`;
    paragraph = [];
  };
  const closeTo = (indent) => {
    while (stack.length && stack[stack.length - 1].indent > indent) html += `</li></${stack.pop().type}>`;
  };
  lines.forEach((line) => {
    const item = line.match(/^(\s*)([-*]|(\d+)\.)\s+(.*)$/);
    if (item) {
      flush();
      const indent = item[1].length;
      const type = item[3] ? "ol" : "ul";
      closeTo(indent);
      const top = stack[stack.length - 1];
      if (top && top.indent === indent && top.type === type) {
        html += "</li><li>";
      } else {
        if (top && top.indent === indent) html += `</li></${stack.pop().type}>`;
        html += `<${type}${type === "ol" && item[3] !== "1" ? ` start="${item[3]}"` : ""}><li>`;
        stack.push({ type, indent });
      }
      html += inline(item[4]);
    } else if (!line.trim()) {
      flush();
      closeTo(-1);
    } else if (stack.length) {
      html += ` ${inline(line.trim())}`;
    } else {
      paragraph.push(line.trim());
    }
  });
  flush();
  closeTo(-1);
  return html;
}

// -- rendering: side panel -----------------------------------------------------------

function renderSide() {
  const conversation = selected();
  const notes = conversation
    ? conversation.turns.map((turn, i) => notesCard(conversation, turn, i)).join("")
    : "";
  $("side").innerHTML = notes + (conversation ? suggestionsCard(conversation) : "") + rulesCard();
}

function noteWhere(note) {
  return note.step ? `On step ${note.step}` : "On the selected text";
}

function noteCard(note) {
  if (state.editingNoteId === note.id) {
    return `<div class="note" data-note-card="${esc(note.id)}">
      ${note.quote ? `<blockquote>“${esc(note.quote)}”</blockquote>` : ""}
      <label class="label" for="edit-${esc(note.id)}">Reword this note</label>
      <textarea class="input" id="edit-${esc(note.id)}" rows="3">${esc(note.note)}</textarea>
      <div class="row">
        <button type="button" class="button small primary" data-action="save-edit" data-note="${esc(note.id)}">Save</button>
        <button type="button" class="button small" data-action="cancel-edit">Cancel</button>
      </div>
    </div>`;
  }
  const history = Array.isArray(note.history) ? note.history.length : 0;
  return `<figure class="note" data-note-card="${esc(note.id)}" data-action="go-to-note" data-note="${esc(note.id)}">
    <span class="note-where">${esc(note.quote ? noteWhere(note) : "On the whole turn")}</span>
    ${note.quote ? `<blockquote>“${esc(note.quote)}”</blockquote>` : ""}
    <p class="note-text">${esc(note.note)}</p>
    <div class="note-foot">
      <span>${history ? `Edited · ${plural(history, "earlier wording")} kept` : ""}</span>
      <span class="row">
        <button type="button" class="button small" data-action="edit" data-note="${esc(note.id)}">Edit</button>
        <button type="button" class="button small" data-action="remove" data-note="${esc(note.id)}">Remove</button>
      </span>
    </div>
  </figure>`;
}

function notesCard(conversation, turn, i) {
  const title = conversation.turns.length > 1 ? `Notes on turn ${i + 1}` : "Notes";
  const notes = failureNotes(turn.trace_id);
  const clean = liveNotes(turn.trace_id).find((n) => n.kind === "no_failure");
  const draftId = `draft-${turn.trace_id}`;
  return `<section class="card side-card" data-notes-for="${esc(turn.trace_id)}" aria-label="${esc(title)}">
    <h2>${esc(title)}</h2>
    ${notes.map(noteCard).join("")}
    ${clean ? `<div class="clean-note" data-note-card="${esc(clean.id)}"><span>No failure observed</span><button type="button" class="button small" data-action="remove" data-note="${esc(clean.id)}">Undo</button></div>` : ""}
    ${!notes.length && !clean ? '<p class="muted" style="margin:0;font-size:14px">Not read yet. Select text in the turn to note it, or use the box below.</p>' : ""}
    <div class="field">
      <label class="label" for="${esc(draftId)}">Note on the whole turn</label>
      <textarea class="input" id="${esc(draftId)}" data-draft="${esc(turn.trace_id)}" rows="3" placeholder="For something the agent never did, with no text to select">${esc(state.drafts[turn.trace_id] ?? "")}</textarea>
    </div>
    <div class="row">
      <button type="button" class="button primary" data-action="save-note" data-trace="${esc(turn.trace_id)}">Save note</button>
      ${!clean && !notes.length ? `<button type="button" class="button good" data-action="no-failure" data-trace="${esc(turn.trace_id)}">No failure observed</button>` : ""}
    </div>
  </section>`;
}

function suggestionsCard(conversation) {
  const traceIds = conversation.turns.map((t) => t.trace_id);
  const turnNumber = (traceId) => traceIds.indexOf(traceId) + 1;
  const pending = state.suggestions.filter((s) => traceIds.includes(s.trace_id) && s.status === "pending");
  const cards = pending.map((s) => `<figure class="suggestion">
    <span class="where">AI suggestion${traceIds.length > 1 ? ` · turn ${turnNumber(s.trace_id)}` : ""}</span>
    ${s.quote ? `<blockquote>“${esc(s.quote)}”</blockquote>` : ""}
    <p class="note-text">${esc(s.note || s.mode || "")}</p>
    <div class="row">
      <button type="button" class="button small ai" data-action="accept" data-suggestion="${esc(s.id)}">Accept as my note</button>
      <button type="button" class="button small" data-action="reject" data-suggestion="${esc(s.id)}">Reject</button>
    </div>
  </figure>`).join("");
  return `<section class="card side-card" aria-label="AI suggestions">
    <div class="side-head">
      <h2>AI suggestions</h2>
      ${pending.length ? `<span class="badge ai">${pending.length} to check</span>` : ""}
    </div>
    ${cards || '<p class="muted" style="margin:0;font-size:14px">None for this conversation. Suggestions stay apart from your notes until you accept or reject them.</p>'}
  </section>`;
}

function rulesCard() {
  const rules = state.rules;
  if (!rules) return "";
  const body = state.rulesOpen
    ? `<ul class="policy">${rules.policy.map((p) => `<li><span>${esc(p.label)}</span><span>${esc(p.value)}</span></li>`).join("")}</ul>
       <ul class="rules">${rules.rules.map((r) => `<li><span class="rule-id">${esc(r.id)}</span>${esc(r.text)}</li>`).join("")}</ul>`
    : "";
  return `<section class="card side-card" aria-label="Rules and policy numbers">
    <div class="side-head">
      <h2>Rules and policy numbers</h2>
      <button type="button" class="button small" data-action="toggle-rules" aria-expanded="${state.rulesOpen}">${state.rulesOpen ? "Hide" : "Show"}</button>
    </div>
    ${body}
  </section>`;
}

// -- actions -------------------------------------------------------------------------

function select(id) {
  if (!findConversation(id)) return;
  state.selectedId = id;
  state.promptOpen = false;
  state.editingNoteId = null;
  remember("selected", id);
  renderAll({ keepScroll: false });
  $("conversation").scrollTop = 0;
  $("side").scrollTop = 0;
  document.querySelector(".row-button.is-selected")?.scrollIntoView({ block: "nearest" });
}

function go(step) {
  const list = visibleConversations();
  const index = list.findIndex((c) => c.session_id === state.selectedId);
  const next = list[index + step];
  if (next) select(next.session_id);
}

function toggleList() {
  state.listOpen = !state.listOpen;
  remember("listOpen", state.listOpen);
  renderListVisibility();
}

async function act(work, message) {
  try {
    await work();
    renderAll();
    if (message) toast(message);
  } catch (error) {
    toast(`Not saved: ${error.message}`);
  }
}

function showSavedNote(noteId) {
  flash(document.querySelector(`[data-note-card="${CSS.escape(noteId)}"]`));
}

async function saveTurnNote(traceId) {
  const text = (state.drafts[traceId] ?? "").trim();
  if (!text) {
    toast("Write the note first.");
    return;
  }
  let created = null;
  await act(async () => {
    created = await postJSON("/api/notes", { trace_id: traceId, note: text });
    delete state.drafts[traceId];
    await refreshNotes();
  }, "Note saved");
  if (created) showSavedNote(created.id);
}

async function markNoFailure(traceId) {
  if (!traceId) return;
  if (failureNotes(traceId).length) {
    toast("This turn already has a note.");
    return;
  }
  let created = null;
  await act(async () => {
    created = await postJSON(`/api/traces/${encodeURIComponent(traceId)}/no-failure`);
    await refreshNotes();
  }, "Marked: no failure observed");
  if (created) showSavedNote(created.id);
}

function currentTurnId() {
  const pane = $("conversation").getBoundingClientRect();
  const turns = [...document.querySelectorAll(".turn")];
  const inView = turns.find((turn) => turn.getBoundingClientRect().bottom > pane.top + 80);
  return inView?.dataset.traceId ?? null;
}

function focusNoteBox() {
  const traceId = currentTurnId();
  const box = traceId && document.querySelector(`[data-draft="${CSS.escape(traceId)}"]`);
  if (box) {
    box.scrollIntoView({ block: "center", behavior: "smooth" });
    box.focus();
  }
}

// -- note about selected text ------------------------------------------------------------

function closestElement(node, selector) {
  const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  return element?.closest(selector) ?? null;
}

function openPopoverForSelection() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const quote = selection.toString().replace(/\s+/g, " ").trim();
  if (quote.length < 2) return;
  const range = selection.getRangeAt(0);
  const turn = closestElement(range.commonAncestorContainer, "[data-trace-id]");
  if (!turn) return;
  const step = closestElement(range.commonAncestorContainer, "[data-step]");
  state.pendingSelection = {
    traceId: turn.dataset.traceId,
    quote,
    step: step ? Number(step.dataset.step) : null,
  };
  const popover = $("note-popover");
  $("popover-quote").textContent = `“${clip(quote, 220)}”`;
  $("popover-text").value = "";
  popover.hidden = false;
  const box = range.getBoundingClientRect();
  const top = Math.min(box.bottom + 8, window.innerHeight - popover.offsetHeight - 12);
  const left = Math.min(Math.max(12, box.left), window.innerWidth - popover.offsetWidth - 12);
  popover.style.top = `${Math.max(12, top)}px`;
  popover.style.left = `${left}px`;
  $("popover-text").focus();
}

function hidePopover() {
  $("note-popover").hidden = true;
  state.pendingSelection = null;
}

async function savePopoverNote() {
  const pending = state.pendingSelection;
  const text = $("popover-text").value.trim();
  if (!pending) return;
  if (!text) {
    toast("Write the note first.");
    return;
  }
  let created = null;
  await act(async () => {
    created = await postJSON("/api/notes", {
      trace_id: pending.traceId,
      note: text,
      quote: pending.quote,
      ...(pending.step ? { step: pending.step } : {}),
    });
    hidePopover();
    window.getSelection()?.removeAllRanges();
    await refreshNotes();
  }, "Note saved");
  if (created) showSavedNote(created.id);
}

// -- events ----------------------------------------------------------------------------

function bindFilters() {
  $("search").addEventListener("input", (event) => {
    state.filters.search = event.target.value;
    renderAll();
  });
  [["batch", "batch"], ["role", "role"], ["action", "action"], ["tool", "tool"]].forEach(([id, key]) => {
    $(id).addEventListener("change", (event) => {
      state.filters[key] = event.target.value;
      renderAll();
    });
  });
  $("two-turns").addEventListener("click", () => {
    state.filters.twoTurns = !state.filters.twoTurns;
    renderAll();
  });
  $("unread").addEventListener("click", () => {
    state.filters.unread = !state.filters.unread;
    renderAll();
  });
}

function bindClicks() {
  $("list").addEventListener("click", (event) => {
    const row = event.target.closest("[data-id]");
    if (row) select(row.dataset.id);
  });
  $("hide-list").addEventListener("click", toggleList);
  $("show-list").addEventListener("click", toggleList);
  $("reload").addEventListener("click", () => act(() => loadAll(true), "Traces reloaded"));
  $("popover-save").addEventListener("click", savePopoverNote);
  $("popover-cancel").addEventListener("click", hidePopover);

  $("conversation").addEventListener("click", (event) => {
    const mark = event.target.closest("mark[data-note-id]");
    if (mark) {
      showSavedNote(mark.dataset.noteId);
      return;
    }
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    if (action === "previous") go(-1);
    if (action === "next") go(1);
    if (action === "toggle-prompt") {
      state.promptOpen = !state.promptOpen;
      renderConversation();
    }
    if (action === "toggle-answer") {
      const key = button.dataset.key;
      if (state.openAnswers.has(key)) state.openAnswers.delete(key);
      else state.openAnswers.add(key);
      renderAll();
    }
  });
  $("conversation").addEventListener("mouseup", () => setTimeout(openPopoverForSelection, 0));

  $("side").addEventListener("input", (event) => {
    const traceId = event.target.dataset?.draft;
    if (traceId) state.drafts[traceId] = event.target.value;
  });
  $("side").addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const { action } = button.dataset;
    const noteId = button.dataset.note;
    if (action === "go-to-note" && !event.target.closest("button")) {
      flash(document.querySelector(`mark[data-note-id="${CSS.escape(noteId)}"]`));
    }
    if (action === "save-note") saveTurnNote(button.dataset.trace);
    if (action === "no-failure") markNoFailure(button.dataset.trace);
    if (action === "edit") {
      state.editingNoteId = noteId;
      renderSide();
      document.getElementById(`edit-${noteId}`)?.focus();
    }
    if (action === "cancel-edit") {
      state.editingNoteId = null;
      renderSide();
    }
    if (action === "save-edit") {
      const text = document.getElementById(`edit-${noteId}`)?.value.trim();
      if (!text) return;
      act(async () => {
        await postJSON(`/api/notes/${encodeURIComponent(noteId)}`, { note: text });
        state.editingNoteId = null;
        await refreshNotes();
      }, "Note reworded; the earlier wording is kept");
    }
    if (action === "remove") {
      act(async () => {
        await postJSON(`/api/notes/${encodeURIComponent(noteId)}/remove`);
        await refreshNotes();
      }, "Note removed; it stays in the saved history");
    }
    if (action === "accept" || action === "reject") {
      act(async () => {
        await postJSON(`/api/suggestions/${encodeURIComponent(button.dataset.suggestion)}/${action}`);
        await Promise.all([refreshNotes(), refreshSuggestions()]);
      }, action === "accept" ? "Suggestion accepted as your note" : "Suggestion rejected");
    }
    if (action === "toggle-rules") {
      state.rulesOpen = !state.rulesOpen;
      remember("rulesOpen", state.rulesOpen);
      renderSide();
    }
  });
}

function bindKeys() {
  document.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey) return;
    // Some layouts (French Mac, for one) type "[" with Option, so only that
    // key accepts Alt; every other shortcut ignores modified presses.
    const isListKey = event.key === "[" || (event.code === "BracketLeft" && !event.altKey);
    if (event.altKey && !isListKey) return;
    if (event.key === "Escape" && !$("note-popover").hidden) {
      hidePopover();
      return;
    }
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (typing) {
      if (event.key === "Escape") document.activeElement.blur();
      return;
    }
    if (event.key === "ArrowRight") go(1);
    else if (event.key === "ArrowLeft") go(-1);
    else if (isListKey) toggleList();
    else if (event.key === "n" || event.key === "N") {
      event.preventDefault();
      focusNoteBox();
    } else if (event.key === "f" || event.key === "F") markNoFailure(currentTurnId());
    else return;
    event.preventDefault();
  });
}

bindFilters();
bindClicks();
bindKeys();
loadAll().catch((error) => {
  $("conversation").innerHTML = `<p class="empty">The review server did not answer: ${esc(error.message)}</p>`;
  $("progress-text").textContent = "";
});
