// The page frame: top bar, filter dropdowns with their counts, and the full redraw.

import { renderConversation } from "./conversation.js";
import { renderList } from "./conversation-list.js";
import { ACTIONS, NO_BATCH, ROLE_ORDER, conversationsWithout, inBatch, matchesBatch, visibleConversations } from "./filters.js";
import { $, cap, esc } from "./helpers.js";
import { allTurns, isRead } from "./lookups.js";
import { renderSide } from "./side-panel.js";
import { remember, state } from "./state.js";

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

export function renderAll({ keepScroll = true } = {}) {
  const panes = [$("conversation"), $("side"), $("list-panel")];
  const scrolls = panes.map((pane) => pane.scrollTop);
  const moved = followFilters();
  renderTopbar();
  renderFilterOptions();
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

export function renderListVisibility() {
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
  const forBatch = conversationsWithout("batch");
  const forRole = conversationsWithout("role");
  const forAction = conversationsWithout("action");
  const forTool = conversationsWithout("tool");
  const roles = [...new Set(all.map((c) => c.role).filter(Boolean))].sort(
    (a, b) => (ROLE_ORDER.indexOf(a) + 99 * (ROLE_ORDER.indexOf(a) < 0)) - (ROLE_ORDER.indexOf(b) + 99 * (ROLE_ORDER.indexOf(b) < 0)),
  );
  $("batch").innerHTML = option("", `All traces · ${forBatch.length}`, f.batch)
    + state.batches.map((b) => option(b.name, `${b.name} · ${forBatch.filter((c) => inBatch(c, b)).length}`, f.batch)).join("")
    + option(NO_BATCH, `Not in a batch · ${forBatch.filter((c) => matchesBatch(c, NO_BATCH)).length}`, f.batch);
  $("role").innerHTML = option("", `Everyone · ${forRole.length}`, f.role)
    + roles.map((role) => option(role, `${cap(role)} · ${forRole.filter((c) => c.role === role).length}`, f.role)).join("");
  $("action").innerHTML = option("", `No filter · ${forAction.length}`, f.action)
    + option("any", `Refund, cancel or hand-off · ${forAction.filter((c) => c.actions.length).length}`, f.action)
    + ACTIONS.map(([value, label]) => option(value, `${label} · ${forAction.filter((c) => c.actions.includes(value)).length}`, f.action)).join("");
  const tools = [...new Set(all.flatMap((c) => c.tools))].sort();
  $("tool").innerHTML = option("", "Any tool", f.tool)
    + tools.map((tool) => option(tool, `${tool} · ${forTool.filter((c) => c.tools.includes(tool)).length}`, f.tool)).join("");
  $("two-turns").textContent = `Two turns · ${conversationsWithout("twoTurns").filter((c) => c.turns.length > 1).length}`;
}
