// Moving between conversations and folding the list.

import { visibleConversations } from "./filters.js";
import { renderAll, renderListVisibility } from "./frame.js";
import { $ } from "./helpers.js";
import { findConversation } from "./lookups.js";
import { remember, state } from "./state.js";

export function select(id) {
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

export function go(step) {
  const list = visibleConversations();
  const index = list.findIndex((c) => c.session_id === state.selectedId);
  const next = list[index + step];
  if (next) select(next.session_id);
}

export function toggleList() {
  state.listOpen = !state.listOpen;
  remember("listOpen", state.listOpen);
  renderListVisibility();
}
