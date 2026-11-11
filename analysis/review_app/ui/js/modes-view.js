// The Failure modes tab: every mode with its definition, its trace counts per
// batch, and the notes that support it, folded until asked. The search box
// keeps the modes whose name contains the typed text; it sits in index.html
// so typing never redraws it.

import { esc, plural, shortId } from "./helpers.js";
import { ICON_PENCIL } from "./icons.js";
import { inline } from "./markdown.js";
import { state } from "./state.js";

export function modesView() {
  const search = state.modesSearch.trim().toLowerCase();
  const shown = state.modes.filter((mode) => mode.name.toLowerCase().includes(search));
  if (!shown.length) return `<p class="modes-empty">No mode name contains “${esc(state.modesSearch.trim())}”.</p>`;
  return `<ul class="modes-list">${shown.map(modeCard).join("")}</ul>`;
}

function modeCard(mode) {
  const notes = supportingNotes(mode);
  return `<li class="mode-card">
    <div class="mode-top">
      <h2 class="mode-name">${esc(mode.name)}</h2>
      <span class="mode-total">${plural(mode.total, "trace")}</span>
    </div>
    <p class="mode-definition"><strong>Fails when</strong> ${inline(mode.definition)}</p>
    ${boundarySection(mode)}
    <div class="mode-batches">${mode.batch_counts.map(batchCount).join("")}</div>
    ${notesSection(mode, notes)}
  </li>`;
}

function notesSection(mode, notes) {
  const open = state.openModes.has(mode.name);
  return `<section class="mode-notes" aria-label="Supporting notes for ${esc(mode.name)}">
    <h3 class="mode-notes-title">
      <button type="button" class="mode-notes-toggle" data-action="toggle-notes" data-mode="${esc(mode.name)}" aria-expanded="${open}">
        <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3l4 4-4 4"></path></svg>
        Supporting notes · ${notes.length}
      </button>
    </h3>
    ${open ? notes.map(noteCard).join("") : ""}
  </section>`;
}

function boundarySection(mode) {
  if (state.editingBoundary === mode.name) return boundaryForm(mode);
  if (!mode.boundary) return emptyBoundary(mode);
  const nearest = mode.nearest_mode
    ? ` · nearest mode <span class="mono mode-nearest">${esc(mode.nearest_mode)}</span>`
    : " · no close neighbour";
  return `<div class="mode-boundary">
    <div class="mode-boundary-top">
      <p class="mode-boundary-title"><strong>Boundary</strong>${nearest}</p>
      <button type="button" class="mode-boundary-edit" data-action="edit-boundary" data-mode="${esc(mode.name)}" aria-label="Edit boundary of ${esc(mode.name)}" title="Edit boundary">${ICON_PENCIL}</button>
    </div>
    <p class="mode-boundary-text">${withModeNames(mode.boundary)}</p>
  </div>`;
}

// The text with every failure mode name it mentions in bold. A name the
// writer already marked with ** or ` takes its markers along, so they never
// pair up with another name's markers.
function withModeNames(text) {
  const names = new Set(state.modes.map((mode) => mode.name));
  const pattern = new RegExp(`(?:\\*\\*|\`)?\\b(${[...names].join("|")})\\b(?:\\*\\*|\`)?`);
  return text
    .split(pattern)
    .map((part) => (names.has(part) ? `<strong class="mode-ref mono">${esc(part)}</strong>` : inline(part)))
    .join("");
}

function emptyBoundary(mode) {
  return `<div class="mode-boundary-empty">
    <p class="mode-no-boundary">No boundary written yet.</p>
    <button type="button" class="button small mode-boundary-add" data-action="edit-boundary" data-mode="${esc(mode.name)}">Add boundary</button>
  </div>`;
}

function boundaryForm(mode) {
  const options = state.modes
    .filter((other) => other.name !== mode.name)
    .map((other) => `<option value="${esc(other.name)}"${other.name === mode.nearest_mode ? " selected" : ""}>${esc(other.name)}</option>`)
    .join("");
  const none = Boolean(mode.boundary) && !mode.nearest_mode;
  const text = boundaryTextWording(none);
  return `<form class="mode-boundary-form" data-mode="${esc(mode.name)}">
    <p class="mode-boundary-title"><strong>Boundary</strong></p>
    <label class="mode-boundary-field">Nearest mode
      <select name="nearest_mode" class="mono" data-action="pick-nearest">
        <option value="">Choose a mode</option>
        <option value="none"${none ? " selected" : ""}>None (no close neighbour)</option>
        ${options}
      </select>
    </label>
    <label class="mode-boundary-field"><span class="mode-boundary-text-label">${text.label}</span>
      <textarea name="boundary" rows="5" placeholder="${text.hint}">${esc(mode.boundary ?? "")}</textarea>
    </label>
    <div class="mode-boundary-buttons">
      <button type="button" class="button small primary" data-action="save-boundary" data-mode="${esc(mode.name)}">Save</button>
      <button type="button" class="button small" data-action="cancel-boundary">Cancel</button>
    </div>
  </form>`;
}

// The text box's label and hint: about one mode alone when it has no close
// neighbour, about the pair otherwise.
export function boundaryTextWording(none) {
  return none
    ? { label: "How to tell it apart", hint: "Which question decides whether a trace has this mode, and what looks like it but isn't" }
    : { label: "How to tell them apart", hint: "Which question decides between this mode and the nearest one, and which fix each needs" };
}

function batchCount({ batch, count }) {
  return `<span>Batch ${batch} <strong>${count}</strong></span>`;
}

function supportingNotes(mode) {
  const live = new Map(state.notes.filter((n) => !n.removed_ts).map((n) => [n.id, n]));
  return mode.note_ids.map((id) => live.get(id)).filter(Boolean);
}

function noteCard(note) {
  const where = `trace ${shortId(note.trace_id)}${note.step ? ` · step ${note.step}` : ""}`;
  return `<figure class="note mode-note">
    <div class="mode-note-top">
      <span class="note-where mono">${esc(where)}</span>
      <button type="button" class="button small" data-action="open-note" data-trace="${esc(note.trace_id)}" data-note="${esc(note.id)}">Open in Read</button>
    </div>
    ${note.quote ? `<blockquote>“${inline(note.quote)}”</blockquote>` : ""}
    <p class="note-text">${inline(note.note)}</p>
  </figure>`;
}
