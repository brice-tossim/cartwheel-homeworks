// A small Markdown reader for replies: paragraphs, headings, bold, italics,
// code, nested lists and tables.

import { esc } from "./helpers.js";

// Inline formatting: `code` first, since nothing is formatted inside it, then
// bold and italics in the rest. Short texts such as notes use it on its own.
export function inline(text) {
  return String(text).split(/(`[^`]+`)/).map((part) => (
    /^`[^`]+`$/.test(part) ? `<code>${esc(part.slice(1, -1))}</code>` : emphasis(part)
  )).join("");
}

// Bold text: the parts between ** markers alternate plain and bold.
function emphasis(text) {
  return text.split("**").map((piece, i) => (i % 2 ? `<strong>${italics(piece)}</strong>` : italics(piece))).join("");
}

// *word*: italics, when the stars hug the text on both sides.
function italics(text) {
  return esc(text).replace(/\*(?=\S)([^*]+?)(?<=\S)\*/g, "<em>$1</em>");
}

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;

// "# Title" to "###### Title". The page already uses h1 and h2, so reply
// headings start at h3.
function heading(line) {
  const match = line.match(HEADING);
  if (!match) return null;
  const level = Math.min(match[1].length + 2, 6);
  return `<h${level} class="reply-heading">${inline(match[2])}</h${level}>`;
}

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?[\s:|-]*-{3,}[\s:|-]*$/;

const tableCells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());

// ":--" aligns left, "--:" right and ":-:" centre, as the separator row asks.
function cellAlign(rule) {
  if (rule.startsWith(":") && rule.endsWith(":")) return "align-center";
  return rule.endsWith(":") ? "align-right" : "";
}

// A table starting at line i (a row of cells, then a separator row such as
// |---|--:|): its HTML and the index of the first line after it, or null.
function tableAt(lines, i) {
  if (!TABLE_ROW.test(lines[i]) || !TABLE_RULE.test(lines[i + 1] ?? "") || !lines[i + 1].includes("|")) return null;
  const aligns = tableCells(lines[i + 1]).map(cellAlign);
  let end = i + 2;
  while (end < lines.length && TABLE_ROW.test(lines[end])) end += 1;
  // Short cells such as dates and amounts stay on one line.
  const classes = (cell, n) => [aligns[n], cell.length <= 24 ? "nowrap" : ""].filter(Boolean).join(" ");
  const row = (line, tag) => `<tr>${tableCells(line).map((cell, n) => (
    `<${tag}${classes(cell, n) ? ` class="${classes(cell, n)}"` : ""}>${inline(cell)}</${tag}>`
  )).join("")}</tr>`;
  const body = lines.slice(i + 2, end).map((line) => row(line, "td")).join("");
  return {
    html: `<div class="reply-table"><table><thead>${row(lines[i], "th")}</thead><tbody>${body}</tbody></table></div>`,
    next: end,
  };
}

// A small Markdown reader for replies: paragraphs, headings, bold, italics,
// code, nested lists and tables.
export function markdown(raw) {
  const lines = String(raw).replace(/\r/g, "").split("\n");
  const stack = [];
  let html = "";
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) html += `<p>${inline(paragraph.join(" "))}</p>`;
    paragraph = [];
  };
  const closeTo = (indent) => {
    while (stack.length && stack[stack.length - 1].indent > indent) html += `</li></${stack.pop().type}>`;
  };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const table = tableAt(lines, i);
    const title = heading(line);
    const item = line.match(/^(\s*)([-*]|(\d+)\.)\s+(.*)$/);
    if (title) {
      flush();
      closeTo(-1);
      html += title;
    } else if (table) {
      flush();
      closeTo(-1);
      html += table.html;
      i = table.next - 1;
    } else if (item) {
      flush();
      const indent = item[1].length;
      const type = item[3] ? "ol" : "ul";
      closeTo(indent);
      const top = stack[stack.length - 1];
      if (top && top.indent === indent && top.type === type) {
        html += "</li><li>";
      } else {
        if (top && top.indent === indent) html += `</li></${stack.pop().type}>`;
        html += `<${type}${type === "ol" && item[3] !== "1" ? ` start="${item[3]}"` : ""}><li>`;
        stack.push({ type, indent });
      }
      html += inline(item[4]);
    } else if (!line.trim()) {
      flush();
      closeTo(-1);
    } else if (stack.length) {
      html += ` ${inline(line.trim())}`;
    } else {
      paragraph.push(line.trim());
    }
  }
  flush();
  closeTo(-1);
  return html;
}
