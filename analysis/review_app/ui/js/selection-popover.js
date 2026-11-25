// The popover for a note about selected text.

import { $, clip, toast } from "./helpers.js";
import { act, showSavedNote } from "./note-actions.js";
import { postJSON, refreshNotes } from "./server.js";
import { state } from "./state.js";

function closestElement(node, selector) {
  const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  return element?.closest(selector) ?? null;
}

export function openPopoverForSelection() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const quote = selection.toString().replace(/\s+/g, " ").trim();
  if (quote.length < 2) return;
  const range = selection.getRangeAt(0);
  const turn = closestElement(range.commonAncestorContainer, "[data-trace-id]");
  if (!turn) return;
  const step = closestElement(range.commonAncestorContainer, "[data-step]");
  state.pendingSelection = {
    traceId: turn.dataset.traceId,
    quote,
    step: step ? Number(step.dataset.step) : null,
  };
  const popover = $("note-popover");
  $("popover-quote").textContent = `“${clip(quote, 220)}”`;
  $("popover-text").value = "";
  popover.hidden = false;
  const box = range.getBoundingClientRect();
  const top = Math.min(box.bottom + 8, window.innerHeight - popover.offsetHeight - 12);
  const left = Math.min(Math.max(12, box.left), window.innerWidth - popover.offsetWidth - 12);
  popover.style.top = `${Math.max(12, top)}px`;
  popover.style.left = `${left}px`;
  $("popover-text").focus();
}

export function hidePopover() {
  $("note-popover").hidden = true;
  state.pendingSelection = null;
}

export async function savePopoverNote() {
  const pending = state.pendingSelection;
  const text = $("popover-text").value.trim();
  if (!pending) return;
  if (!text) {
    toast("Write the note first.");
    return;
  }
  let created = null;
  await act(async () => {
    created = await postJSON("/api/notes", {
      trace_id: pending.traceId,
      note: text,
      quote: pending.quote,
      ...(pending.step ? { step: pending.step } : {}),
    });
    hidePopover();
    window.getSelection()?.removeAllRanges();
    await refreshNotes();
  }, "Note saved");
  if (created) showSavedNote(created.id);
}
