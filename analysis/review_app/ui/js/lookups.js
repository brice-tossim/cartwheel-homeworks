// Lookups on the loaded conversations, notes and suggestions.

import { plural } from "./helpers.js";
import { state } from "./state.js";

export const findConversation = (id) => state.conversations.find((c) => c.session_id === id) ?? null;
export const selected = () => findConversation(state.selectedId);
export const liveNotes = (traceId) => state.notes.filter((n) => n.trace_id === traceId && !n.removed_ts);
export const failureNotes = (traceId) => liveNotes(traceId).filter((n) => n.kind !== "no_failure");
export const isClean = (traceId) => liveNotes(traceId).some((n) => n.kind === "no_failure");
export const isRead = (traceId) => liveNotes(traceId).length > 0;
export const pendingSuggestions = (traceId) => state.suggestions.filter(
  (s) => s.trace_id === traceId && s.status === "pending",
);
export const hasPendingSuggestions = (conversation) => conversation.turns.some(
  (t) => pendingSuggestions(t.trace_id).length > 0,
);

export function allTurns() {
  return state.conversations.flatMap((c) => c.turns);
}

export function readState(conversation) {
  if (conversation.session_id === state.selectedId) return ["reading now", "state-reading"];
  const turns = conversation.turns;
  const read = turns.filter((t) => isRead(t.trace_id)).length;
  if (read === 0) return ["not read", ""];
  if (read < turns.length) return [`${read} of ${turns.length} turns read`, "state-note"];
  const noteCount = turns.reduce((sum, t) => sum + failureNotes(t.trace_id).length, 0);
  return noteCount ? [plural(noteCount, "note"), "state-note"] : ["no failure", "state-clean"];
}

// A turn is labeled once every failure mode has a saved decision for it.
export function isLabeled(traceId) {
  return state.modes.length > 0 && state.modes.every(
    (mode) => state.labels.some((label) => label.trace_id === traceId && label.mode === mode.name),
  );
}

const labeledCount = (turns) => turns.filter((t) => isLabeled(t.trace_id)).length;

export const hasTurnToLabel = (conversation) => conversation.turns.some(
  (t) => isRead(t.trace_id) && !isLabeled(t.trace_id),
);

export function labelState(conversation) {
  const turns = conversation.turns;
  const labeled = labeledCount(turns);
  const partial = labeled > 0 && labeled < turns.length ? `${labeled} of ${turns.length} turns labeled` : "";
  if (conversation.session_id === state.selectedId) {
    return [partial ? `labeling now · ${partial}` : "labeling now", "state-reading"];
  }
  if (labeled === turns.length) return ["labeled", "state-clean"];
  if (partial) return [partial, "state-note"];
  if (!turns.some((t) => isRead(t.trace_id))) return ["not read", ""];
  return ["not labeled", ""];
}

export function labelProgress() {
  const read = allTurns().filter((t) => isRead(t.trace_id));
  return { labeled: labeledCount(read), read: read.length };
}

export const turnsToLabel = (conversations) => conversations
  .flatMap((c) => c.turns)
  .filter((t) => isRead(t.trace_id) && !isLabeled(t.trace_id)).length;

const turnToLabel = (conversation) => conversation.turns.findIndex(
  (t) => isRead(t.trace_id) && !isLabeled(t.trace_id),
);

// Where to go after a save: the next read turn left to label, in the open
// conversation first, then down the list `order`, wrapping round to the top.
export function nextToLabel(order, currentId) {
  const index = order.findIndex((c) => c.session_id === currentId);
  const current = findConversation(currentId);
  const candidates = [current, ...order.slice(index + 1), ...order.slice(0, Math.max(index, 0))].filter(Boolean);
  const next = candidates.find((c) => turnToLabel(c) >= 0);
  return next ? { session_id: next.session_id, turn: turnToLabel(next) } : null;
}
