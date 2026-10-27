// Saving, rewording and removing notes, and deciding AI suggestions.

import { renderAll } from "./frame.js";
import { $, flash, toast } from "./helpers.js";
import { failureNotes } from "./lookups.js";
import { postJSON, refreshNotes, refreshSuggestions } from "./server.js";
import { state } from "./state.js";

export async function act(work, message) {
  try {
    await work();
    renderAll();
    if (message) toast(message);
  } catch (error) {
    toast(`Not saved: ${error.message}`);
  }
}

export function showSavedNote(noteId) {
  flash(document.querySelector(`[data-note-card="${CSS.escape(noteId)}"]`));
}

export async function saveTurnNote(traceId) {
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

export async function markNoFailure(traceId) {
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

export function currentTurnId() {
  const pane = $("conversation").getBoundingClientRect();
  const turns = [...document.querySelectorAll(".turn")];
  const inView = turns.find((turn) => turn.getBoundingClientRect().bottom > pane.top + 80);
  return inView?.dataset.traceId ?? null;
}

export function focusNoteBox() {
  const traceId = currentTurnId();
  const box = traceId && document.querySelector(`[data-draft="${CSS.escape(traceId)}"]`);
  if (box) {
    box.scrollIntoView({ block: "center", behavior: "smooth" });
    box.focus();
  }
}

export function rewordNote(noteId) {
  const text = document.getElementById(`edit-${noteId}`)?.value.trim();
  if (!text) return;
  act(async () => {
    await postJSON(`/api/notes/${encodeURIComponent(noteId)}`, { note: text });
    state.editingNoteId = null;
    await refreshNotes();
  }, "Note reworded; the earlier wording is kept");
}

export function removeNote(noteId) {
  act(async () => {
    await postJSON(`/api/notes/${encodeURIComponent(noteId)}/remove`);
    await refreshNotes();
  }, "Note removed; it stays in the saved history");
}

// `decision` is "accept" or "reject".
export function decideSuggestion(suggestionId, decision) {
  act(async () => {
    await postJSON(`/api/suggestions/${encodeURIComponent(suggestionId)}/${decision}`);
    await Promise.all([refreshNotes(), refreshSuggestions()]);
  }, decision === "accept" ? "Suggestion accepted as your note" : "Suggestion rejected");
}
