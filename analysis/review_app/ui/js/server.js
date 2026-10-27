// Calls to the review server's JSON routes.

import { NO_BATCH, findBatch } from "./filters.js";
import { renderAll } from "./frame.js";
import { findConversation } from "./lookups.js";
import { state } from "./state.js";

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} on ${url}`);
  return response.json();
}

export async function postJSON(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `${response.status} on ${url}`);
  return data;
}

export async function loadAll(refresh = false) {
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
  renderAll({ keepScroll: false });
}

export async function refreshNotes() {
  state.notes = await getJSON("/api/notes");
}

export async function refreshSuggestions() {
  state.suggestions = await getJSON("/api/suggestions");
}
