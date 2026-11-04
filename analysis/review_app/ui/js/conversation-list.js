// The list of conversations on the left.

import { FILTER_VIEW, visibleConversations } from "./filters.js";
import { $, cap, clip, esc, plural } from "./helpers.js";
import { labelState, readState, turnsToLabel } from "./lookups.js";
import { state } from "./state.js";

export function renderList() {
  const list = visibleConversations();
  $("list-count").textContent = plural(list.length, "conversation");
  $("trace-count").textContent = state.view === "label"
    ? `${plural(turnsToLabel(list), "turn")} to label`
    : plural(list.reduce((sum, c) => sum + c.turns.length, 0), "trace");
  $("two-turns").setAttribute("aria-pressed", String(state.filters.twoTurns));
  Object.entries(FILTER_VIEW).forEach(([key, view]) => {
    $(key).setAttribute("aria-pressed", String(state.filters[key]));
    $(key).hidden = view !== state.view;
  });
  $("list").innerHTML = list.length
    ? list.map(listRow).join("")
    : `<p class="empty">No conversation matches these filters.</p>`;
}

function listRow(conversation) {
  const [label, tone] = state.view === "label" ? labelState(conversation) : readState(conversation);
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
