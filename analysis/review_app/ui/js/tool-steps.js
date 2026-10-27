// The agent's tool steps inside a turn, with their answers.

import { esc } from "./helpers.js";
import { ICON_CHECK, ICON_CROSS } from "./icons.js";
import { state } from "./state.js";

function argumentsText(args) {
  if (args == null) return "";
  if (typeof args !== "object" || Array.isArray(args)) return JSON.stringify(args);
  return Object.entries(args)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
    .join(", ");
}

function statusChip(step) {
  if (step.ok === true) return `<span class="status ok">${ICON_CHECK}ok</span>`;
  if (step.ok === false) return `<span class="status failed">${ICON_CROSS}failed · ${esc(step.error)}</span>`;
  return `<span class="status unknown">no answer recorded</span>`;
}

export function stepItem(turn, step, n) {
  const key = `${turn.trace_id}:${n}`;
  const open = state.openAnswers.has(key);
  const kind = step.changes_data ? " write" : step.ok === false ? " failed" : "";
  const reason = step.reason
    ? `<p class="reason"><span class="who-said">Agent · </span>${esc(step.reason)}</p>`
    : "";
  return `<li class="step" data-step="${n + 1}">
    <span class="step-number" aria-hidden="true">${n + 1}</span>
    <div class="step-body">
      ${reason}
      <div class="tool${kind}">
        <div class="tool-line">
          ${step.changes_data ? '<span class="tag-write">Changes data</span>' : ""}
          <code class="tool-call">${esc(step.tool)}(${esc(argumentsText(step.arguments))})</code>
          ${statusChip(step)}
          ${step.summary ? `<span class="summary">${esc(step.summary)}</span>` : ""}
        </div>
        ${answerDetails(step, key, open)}
      </div>
    </div>
  </li>`;
}

function answerDetails(step, key, open) {
  if (step.ok === false) {
    return step.error_reason ? `<span class="error-reason">${esc(step.error_reason)}</span>` : "";
  }
  if (step.result == null) return "";
  const note = step.result && typeof step.result === "object" && step.result.note
    ? `<span class="error-reason muted">${esc(step.result.note)}</span>`
    : "";
  if (step.folded) {
    const toggle = `<button type="button" class="link-button" data-action="toggle-answer" data-key="${esc(key)}" aria-expanded="${open}">${open ? "Hide the full answer" : `Show the full answer (${step.result_chars.toLocaleString("en-US")} characters)`}</button>`;
    return `${note}${toggle}${open ? prettyJson(step.result) : ""}`;
  }
  if (step.summary) return note;
  return fieldsOrJson(step.result);
}

function fieldsOrJson(result) {
  let shown = result;
  if (result && typeof result === "object" && !Array.isArray(result)) {
    const entries = Object.entries(result).filter(([key]) => key !== "ok");
    const nested = entries.filter(([, value]) => value && typeof value === "object" && !Array.isArray(value));
    shown = entries.length === 1 && nested.length === 1 ? nested[0][1] : Object.fromEntries(entries);
  }
  const flat = shown && typeof shown === "object" && !Array.isArray(shown)
    && Object.values(shown).every((value) => value === null || typeof value !== "object")
    && Object.keys(shown).length <= 16;
  if (!flat) return prettyJson(result);
  return `<dl class="fields">${Object.entries(shown).map(([key, value]) => (
    `<div><dt>${esc(key.replace(/_/g, " "))}</dt><dd>${esc(value === null ? "—" : String(value))}</dd></div>`
  )).join("")}</dl>`;
}

function prettyJson(value) {
  const text = esc(JSON.stringify(value, null, 2));
  return `<pre class="json">${text.replace(/^(\s*)(&quot;.*?&quot;)(:)/gm, '$1<span class="key">$2</span>$3')}</pre>`;
}
