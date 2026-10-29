// What each filter keeps, and the conversations they leave visible.

import { isRead } from "./lookups.js";
import { state } from "./state.js";

export const ROLE_ORDER = ["shopper", "merchant", "support"];
export const ACTIONS = [
  ["refund", "Refund"],
  ["cancel", "Cancel"],
  ["hand-off", "Hand-off"],
];

function searchText(conversation) {
  if (!conversation.searchText) {
    conversation.searchText = [
      conversation.scenario_id,
      conversation.session_id,
      ...conversation.turns.map((t) => t.trace_id),
      conversation.role,
      ...conversation.tools,
      ...conversation.turns.flatMap((t) => [t.customer, t.reply, ...t.steps.map((s) => s.reason)]),
    ].filter(Boolean).join(" ").toLowerCase();
  }
  return conversation.searchText;
}

function matchesAction(conversation, action) {
  if (!action) return true;
  if (action === "any") return conversation.actions.length > 0;
  return conversation.actions.includes(action);
}

// The batch picker's value for the traces in no batch; batch file names never start with "_".
export const NO_BATCH = "__none__";

export const findBatch = (name) => state.batches.find((b) => b.name === name) ?? null;

export function inBatch(conversation, batch) {
  const ids = new Set(batch.trace_ids);
  return conversation.turns.some((t) => ids.has(t.trace_id));
}

export function matchesBatch(conversation, name) {
  if (!name) return true;
  if (name === NO_BATCH) return !state.batches.some((b) => inBatch(conversation, b));
  const batch = findBatch(name);
  return batch ? inBatch(conversation, batch) : true;
}

const searchWords = (f) => f.search.toLowerCase().split(/\s+/).filter(Boolean);

// One test per filter, keyed by its name in state.filters.
const FILTER_TESTS = {
  batch: (c, f) => matchesBatch(c, f.batch),
  role: (c, f) => !f.role || c.role === f.role,
  action: (c, f) => matchesAction(c, f.action),
  tool: (c, f) => !f.tool || c.tools.includes(f.tool),
  twoTurns: (c, f) => !f.twoTurns || c.turns.length > 1,
  unread: (c, f) => !f.unread || c.turns.some((t) => !isRead(t.trace_id)),
  search: (c, f) => searchWords(f).every((word) => searchText(c).includes(word)),
};

// The conversations every filter keeps, leaving out the filter named in
// `except`: a filter's counts then show what picking each of its options gives.
export function conversationsWithout(except) {
  const f = state.filters;
  const tests = Object.entries(FILTER_TESTS).filter(([name]) => name !== except).map(([, test]) => test);
  return state.conversations.filter((c) => tests.every((test) => test(c, f)));
}

export const visibleConversations = () => conversationsWithout(null);
