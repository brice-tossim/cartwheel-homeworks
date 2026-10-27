// Small shared tools: element lookup, escaping, text shortening, toasts.

export const $ = (id) => document.getElementById(id);

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
}

export const cap = (text) => (text ? text[0].toUpperCase() + text.slice(1) : "");
export const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
export const shortId = (id) => String(id ?? "").slice(0, 8);

export function clip(text, length) {
  const value = String(text ?? "").replace(/\s+/g, " ").trim();
  return value.length > length ? `${value.slice(0, length).trimEnd()}…` : value;
}

export function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 2600);
}

export function flash(element) {
  if (!element) return;
  element.scrollIntoView({ block: "center", behavior: "smooth" });
  element.classList.remove("is-flashing");
  void element.offsetWidth;
  element.classList.add("is-flashing");
}
