// The Failure modes tab: every mode with its definition, its trace counts per
// batch, and the notes that support it, folded until asked. The search box
// keeps the modes whose name contains the typed text; it sits in index.html
// so typing never redraws it.

import { esc, plural, shortId } from "./helpers.js";
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
