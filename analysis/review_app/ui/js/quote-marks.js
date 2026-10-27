// Highlights for saved quotes and AI suggestions inside a turn.

import { liveNotes, pendingSuggestions } from "./lookups.js";

export function marksFor(traceId) {
  const notes = liveNotes(traceId)
    .filter((n) => n.quote)
    .map((n) => ({ quote: n.quote, className: "note-mark", data: { noteId: n.id } }));
  const suggested = pendingSuggestions(traceId)
    .filter((s) => s.quote)
    .map((s) => ({ quote: s.quote, className: "ai-mark", data: { suggestionId: s.id } }));
  return [...notes, ...suggested];
}

// Mark each saved quote where it first appears in a turn: in the customer
// message, a step's reason (with its label), the reply, or the line saying no
// reply was recorded. Whitespace and Markdown symbols are ignored, so a quote
// spanning lines, list items, bold words or table cells still matches, and so
// does a quote saved while the page still showed those symbols as text.
export function markQuotes(turn, marks) {
  const parts = [...turn.querySelectorAll(".customer p, .reason, .reply-text, .reply.missing p")];
  marks.forEach((mark) => {
    const found = parts.map((part) => findQuote(part, mark.quote)).find(Boolean);
    if (found && !found.some((c) => c.node.parentElement.closest("mark"))) wrapChars(found, mark);
  });
}

// Spaces, and the Markdown symbols for headings, bold, code and tables.
const IGNORED = /[\s#*`|:-]/;

// The characters of a quote inside a part, each with its text node and
// offset, or null when the part does not contain the quote.
function findQuote(part, quote) {
  const chars = [];
  const walker = document.createTreeWalker(part, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    [...node.data].forEach((char, offset) => {
      if (!IGNORED.test(char)) chars.push({ node, offset, char });
    });
  }
  const needle = quote.replace(new RegExp(IGNORED.source, "g"), "");
  const at = needle ? chars.map((c) => c.char).join("").indexOf(needle) : -1;
  return at < 0 ? null : chars.slice(at, at + needle.length);
}

// Wrap the found characters in one mark per text node they fall in.
function wrapChars(chars, mark) {
  const ranges = new Map();
  chars.forEach(({ node, offset }) => {
    const range = ranges.get(node) ?? { start: offset, end: offset };
    ranges.set(node, { start: range.start, end: offset + 1 });
  });
  ranges.forEach(({ start, end }, node) => {
    const middle = node.splitText(start);
    middle.splitText(end - start);
    const element = document.createElement("mark");
    element.className = mark.className;
    Object.assign(element.dataset, mark.data);
    middle.replaceWith(element);
    element.append(middle);
  });
}
