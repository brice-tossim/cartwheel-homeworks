// The open conversation: who is asking, then one card per turn.

import { visibleConversations } from "./filters.js";
import { $, cap, esc, plural, shortId } from "./helpers.js";
import { ICON_INFO, ICON_LEFT, ICON_OUT, ICON_RIGHT } from "./icons.js";
import { failureNotes, isClean, selected } from "./lookups.js";
import { markdown } from "./markdown.js";
import { markQuotes, marksFor } from "./quote-marks.js";
import { state } from "./state.js";
import { stepItem } from "./tool-steps.js";

export function renderConversation() {
  const pane = $("conversation");
  const conversation = selected();
  if (!conversation) {
    pane.innerHTML = `<p class="empty">${state.conversations.length ? "No conversation matches these filters." : "No conversation to show."}</p>`;
    return;
  }
  pane.innerHTML = `<div class="conversation-inner">
    ${whoCard(conversation)}
    ${conversation.turns.map((turn, i) => turnCard(conversation, turn, i)).join("")}
  </div>`;
  pane.querySelectorAll(".turn").forEach((turn) => markQuotes(turn, marksFor(turn.dataset.traceId)));
}

function callerLine(conversation) {
  const parts = [cap(conversation.role) || "Unknown caller"];
  if (conversation.user_id) parts.push(`user ${conversation.user_id}`);
  parts.push(conversation.store_id ? `store ${conversation.store_id}` : "no store");
  return parts.join(" · ");
}

function langfuseLink(traceId, label) {
  if (!state.traceLink) return "";
  return `<a class="button" href="${esc(state.traceLink + traceId)}" target="_blank" rel="noopener">${label}${ICON_OUT}</a>`;
}

function whoCard(conversation) {
  const list = visibleConversations();
  const index = list.findIndex((c) => c.session_id === conversation.session_id);
  const position = index >= 0 ? `${index + 1} of ${list.length}` : "not in this list";
  const prompt = conversation.turns[0]?.system_prompt;
  return `<section class="card who" aria-label="Who is asking">
    <div class="who-top">
      <div>
        <span class="label">Who is asking</span>
        <h1>${esc(callerLine(conversation))}</h1>
      </div>
      <div class="nav">
        <button type="button" class="icon-button" data-action="previous" aria-label="Previous conversation"${index <= 0 ? " disabled" : ""}>${ICON_LEFT}</button>
        <span>${position}</span>
        <button type="button" class="icon-button" data-action="next" aria-label="Next conversation"${index < 0 || index >= list.length - 1 ? " disabled" : ""}>${ICON_RIGHT}</button>
      </div>
    </div>
    <div class="who-meta">
      ${conversation.scenario_id ? `<span>scenario ${esc(conversation.scenario_id)}</span>` : ""}
      <span>session ${esc(shortId(conversation.session_id))}</span>
      <span>${plural(conversation.turns.length, "turn")}</span>
      ${conversation.prompt_version ? `<span>prompt ${esc(shortId(conversation.prompt_version))}</span>` : ""}
    </div>
    <div class="row">
      ${prompt ? `<button type="button" class="button" data-action="toggle-prompt" aria-expanded="${state.promptOpen}">${state.promptOpen ? "Hide" : "Show"} system prompt</button>` : ""}
      ${langfuseLink(conversation.turns[0]?.trace_id, "Open in Langfuse")}
    </div>
    ${state.promptOpen && prompt ? `<pre class="prompt">${esc(prompt)}</pre>` : ""}
  </section>`;
}

function turnBadge(traceId) {
  const notes = failureNotes(traceId).length;
  if (notes) return `<span class="badge note">${plural(notes, "note")}</span>`;
  if (isClean(traceId)) return `<span class="badge clean">no failure</span>`;
  return `<span class="badge">not read</span>`;
}

function timeOf(timestamp) {
  const match = String(timestamp ?? "").match(/T(\d\d:\d\d:\d\d)/);
  return match ? `${match[1]} UTC` : "";
}

function turnCard(conversation, turn, i) {
  const count = conversation.turns.length;
  const steps = turn.steps.length
    ? `<ol class="steps">${turn.steps.map((step, n) => stepItem(turn, step, n)).join("")}</ol>`
    : `<p class="no-tools">${ICON_INFO}No tool call in this turn.</p>`;
  return `<article class="card turn" id="turn-${esc(turn.trace_id)}" data-trace-id="${esc(turn.trace_id)}" aria-label="Turn ${i + 1} of ${count}">
    <div class="turn-head">
      <span><strong>Turn ${i + 1} of ${count}</strong> <span class="muted">· ${esc(timeOf(turn.timestamp))} ·</span> <code>trace ${esc(shortId(turn.trace_id))}</code></span>
      ${turnBadge(turn.trace_id)}
    </div>
    <div class="turn-body">
      <div class="customer" data-part="customer">
        <span class="label">Customer</span>
        <p>${esc(turn.customer ?? "")}</p>
      </div>
      ${steps}
      ${replyBlock(turn)}
    </div>
  </article>`;
}

function replyBlock(turn) {
  if (turn.reply == null) {
    return `<div class="reply missing"><span class="label">Reply to the customer</span><p class="muted" style="margin:0">No reply was recorded for this turn.</p></div>`;
  }
  return `<div class="reply" data-part="reply">
    <span class="label">Reply to the customer</span>
    <div class="reply-text">${markdown(turn.reply)}</div>
  </div>`;
}
