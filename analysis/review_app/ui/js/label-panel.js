// The Label tab's decisions panel: one present or absent decision per failure
// mode for the open turn, pre-filled from the review so far, with the notes
// each mode links on this turn (for it or for a close negative) folded under it,
// and the turn's notes no mode links in a block below the modes.
//
// Pre-fill: present when the mode lists the turn among its traces, absent when
// the turn is one of its close negatives or was marked "no failure observed"
// (no hint, the conversation list already says so), and otherwise absent but
// not checked yet. A saved label wins over the
// pre-fill, and a click wins over both. Saving waits until every mode is checked.

import { esc } from "./helpers.js";
import { failureNotes, isClean, isRead } from "./lookups.js";
import { noteCard } from "./side-panel.js";
import { state } from "./state.js";

export function labelPanel(conversation) {
  const index = turnIndex(conversation);
  const traceId = conversation.turns[index].trace_id;
  return `<section class="card side-card decisions" aria-labelledby="decisions-title">
    <div class="side-head">
      <h2 id="decisions-title">Decisions</h2>
      ${turnSwitcher(conversation, index)}
    </div>
    ${isRead(traceId) ? decisionsBody(traceId) : '<p class="muted decisions-intro">Review this turn in Read first: add a note or mark it "no failure observed".</p>'}
  </section>`;
}

function decisionsBody(traceId) {
  const decisions = state.modes.map((mode) => [mode, decision(mode, traceId)]);
  const checked = decisions.filter(([, d]) => d.checked).length;
  return `<p class="muted decisions-intro">Pre-filled from your notes. Check each mode, then save the turn.</p>    ${decisions.map(([mode, d]) => decisionBlock(mode, d, traceId)).join("")}
    ${unlinkedBlock(traceId)}
    <div class="decisions-foot">
      <span class="muted">${checked} of ${decisions.length} checked</span>
      <button type="button" class="button primary" data-action="save-labels" data-trace="${esc(traceId)}"${checked < decisions.length ? " disabled" : ""}>Save decisions</button>
    </div>`;
}

// The open turn: the one picked, else the first with an unsaved mode, else the first.
export function turnIndex(conversation) {
  const picked = state.labelTurn[conversation.session_id];
  if (picked !== undefined && picked < conversation.turns.length) return picked;
  const unsaved = conversation.turns.findIndex((turn) => state.modes.some((mode) => !savedLabel(turn.trace_id, mode.name)));
  return unsaved >= 0 ? unsaved : 0;
}

// What the turn would be saved as: { mode name: 0 or 1 }.
export function decisionsFor(traceId) {
  return Object.fromEntries(state.modes.map((mode) => [mode.name, decision(mode, traceId).label]));
}

function decision(mode, traceId) {
  const draft = state.labelDrafts[traceId]?.[mode.name];
  const saved = savedLabel(traceId, mode.name);
  if (draft !== undefined) return { label: draft, hint: saved?.label === draft ? "Saved" : "Checked", checked: true };
  if (saved) return { label: saved.label, hint: "Saved", checked: true };
  return prefill(mode, traceId);
}

function prefill(mode, traceId) {
  if (mode.example_trace_ids.includes(traceId)) return { label: 1, hint: "From your notes", checked: true };
  if (mode.close_negative_trace_ids.includes(traceId)) return { label: 0, hint: "Close negative", checked: true };
  if (isClean(traceId)) return { label: 0, hint: "", checked: true };
  return { label: 0, hint: "Not checked yet", checked: false };
}

function savedLabel(traceId, mode) {
  return state.labels.find((label) => label.trace_id === traceId && label.mode === mode);
}

function turnSwitcher(conversation, index) {
  if (conversation.turns.length < 2) return "";
  const buttons = conversation.turns.map((_, i) => (
    `<button type="button" class="pill" data-action="label-turn" data-turn="${i}" aria-pressed="${i === index}">Turn ${i + 1}</button>`
  ));
  return `<div class="row" role="group" aria-label="Turn">${buttons.join("")}</div>`;
}

function decisionBlock(mode, d, traceId) {
  const choice = (label, text) => (
    `<button type="button" class="choice" data-action="label-pick" data-trace="${esc(traceId)}" data-mode="${esc(mode.name)}" data-label="${label}" aria-pressed="${d.label === label}">${text}</button>`
  );
  return `<div class="decision${d.checked ? "" : " is-unchecked"}" data-mode="${esc(mode.name)}">
    <div class="decision-name" data-full="${esc(mode.definition)}">
      <span class="mono">${esc(mode.name)}</span>
      <span class="decision-definition">${esc(mode.definition)}</span>
    </div>
    <div class="decision-choice">
      <div class="row" role="group" aria-label="${esc(mode.name)}">${choice(1, "Present")}${choice(0, "Absent")}</div>
      <span class="decision-hint">${esc(d.hint)}</span>
    </div>
    ${notesFold(mode, traceId)}
  </div><!-- /decision -->`;
}

const linkedIds = (mode) => [...mode.note_ids, ...(mode.close_negative_note_ids ?? [])];

// The turn's notes that no mode lists, so a highlight without a mode is not missed.
function unlinkedBlock(traceId) {
  const linked = new Set(state.modes.flatMap(linkedIds));
  const notes = failureNotes(traceId).filter((note) => !linked.has(note.id));
  if (!notes.length) return "";
  return `<div class="unlinked-notes" role="group" aria-labelledby="unlinked-title">
    <h3 id="unlinked-title">Not linked to a mode · ${notes.length}</h3>
    <p class="muted">Notes on this turn that no failure mode lists yet.</p>
    ${notes.map(noteCard).join("")}
  </div><!-- /unlinked-notes -->`;
}

function notesFold(mode, traceId) {
  const linked = linkedIds(mode);
  const notes = failureNotes(traceId).filter((note) => linked.includes(note.id));
  if (!notes.length) return "";
  const open = state.labelOpen.has(mode.name);
  return `<button type="button" class="label-notes-toggle" data-action="toggle-label-notes" data-mode="${esc(mode.name)}" aria-expanded="${open}"><svg aria-hidden="true" width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3l4 4-4 4"></path></svg>Notes</button>
    ${open ? `<div class="decision-notes">${notes.map(noteCard).join("")}</div>` : ""}`;
}
