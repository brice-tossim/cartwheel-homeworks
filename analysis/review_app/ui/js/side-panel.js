// The side panel: notes per turn, AI suggestions, rules and policy numbers.

import { $, esc, plural } from "./helpers.js";
import { failureNotes, liveNotes, selected } from "./lookups.js";
import { inline } from "./markdown.js";
import { state } from "./state.js";

export function renderSide() {
  const conversation = selected();
  const notes = conversation
    ? conversation.turns.map((turn, i) => notesCard(conversation, turn, i)).join("")
    : "";
  $("side").innerHTML = notes + (conversation ? suggestionsCard(conversation) : "") + rulesCard();
}

function noteWhere(note) {
  return note.step ? `On step ${note.step}` : "On the selected text";
}

export function noteCard(note) {
  if (state.editingNoteId === note.id) {
    return `<div class="note" data-note-card="${esc(note.id)}">
      ${note.quote ? `<blockquote>“${inline(note.quote)}”</blockquote>` : ""}
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
    ${note.quote ? `<blockquote>“${inline(note.quote)}”</blockquote>` : ""}
    <p class="note-text">${inline(note.note)}</p>
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

export function suggestionsCard(conversation) {
  const traceIds = conversation.turns.map((t) => t.trace_id);
  const turnNumber = (traceId) => traceIds.indexOf(traceId) + 1;
  const pending = state.suggestions.filter((s) => traceIds.includes(s.trace_id) && s.status === "pending");
  const cards = pending.map((s) => `<figure class="suggestion">
    <span class="where">AI suggestion${traceIds.length > 1 ? ` · turn ${turnNumber(s.trace_id)}` : ""}</span>
    ${s.quote ? `<blockquote>“${inline(s.quote)}”</blockquote>` : ""}
    <p class="note-text">${inline(s.note || s.mode || "")}</p>
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
