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
