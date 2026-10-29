// Wiring filter changes, clicks and keyboard shortcuts.

import { renderConversation } from "./conversation.js";
import { renderAll } from "./frame.js";
import { $, flash } from "./helpers.js";
import { go, select, toggleList } from "./navigation.js";
import {
  act, currentTurnId, decideSuggestion, focusNoteBox, markNoFailure, removeNote, rewordNote, saveTurnNote, showSavedNote,
} from "./note-actions.js";
import { hidePopover, openPopoverForSelection, savePopoverNote } from "./selection-popover.js";
import { loadAll } from "./server.js";
import { renderSide } from "./side-panel.js";
import { remember, state } from "./state.js";

export function bindFilters() {
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

export function bindClicks() {
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
    if (action === "save-edit") rewordNote(noteId);
    if (action === "remove") removeNote(noteId);
    if (action === "accept" || action === "reject") decideSuggestion(button.dataset.suggestion, action);
    if (action === "toggle-rules") {
      state.rulesOpen = !state.rulesOpen;
      remember("rulesOpen", state.rulesOpen);
      renderSide();
    }
  });
}

export function bindKeys() {
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
