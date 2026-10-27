// The page state shared by every part, and the per-viewer conveniences kept
// in localStorage (which conversation was open, which panels were folded).

function remembered(key, fallback) {
  try {
    const value = localStorage.getItem(`review.${key}`);
    return value === null ? fallback : JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function remember(key, value) {
  try {
    localStorage.setItem(`review.${key}`, JSON.stringify(value));
  } catch {
    // Storage can be unavailable (private window); the page works without it.
  }
}

export const state = {
  source: null,
  fallbackReason: null,
  traceLink: null,
  conversations: [],
  batches: [],
  notes: [],
  suggestions: [],
  rules: null,
  filters: { batch: "", search: "", role: "", action: "", tool: "", twoTurns: false, unread: false },
  selectedId: remembered("selected", null),
  listOpen: remembered("listOpen", true),
  rulesOpen: remembered("rulesOpen", true),
  promptOpen: false,
  openAnswers: new Set(),
  editingNoteId: null,
  drafts: {},
  pendingSelection: null,
};
