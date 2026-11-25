// Editing a failure mode's boundary from the Failure modes tab.

import { boundaryTextWording } from "./modes-view.js";
import { act } from "./note-actions.js";
import { postJSON } from "./server.js";
import { state } from "./state.js";
import { renderModes } from "./views.js";

export function editBoundary(name) {
  state.editingBoundary = name;
  renderModes();
  document.querySelector(".mode-boundary-form textarea")?.focus();
}

export function cancelBoundary() {
  state.editingBoundary = null;
  renderModes();
}

// Reword the text box in place, so what is already typed stays.
export function pickNearest(select) {
  const form = select.closest(".mode-boundary-form");
  const wording = boundaryTextWording(select.value === "none");
  form.querySelector(".mode-boundary-text-label").textContent = wording.label;
  form.elements.boundary.placeholder = wording.hint;
}

export function saveBoundary(name) {
  const form = document.querySelector(`.mode-boundary-form[data-mode="${CSS.escape(name)}"]`);
  const nearest = form.elements.nearest_mode.value;
  const body = { nearest_mode: nearest === "none" ? null : nearest, boundary: form.elements.boundary.value };
  return act(async () => {
    const saved = await postJSON(`/api/modes/${encodeURIComponent(name)}/boundary`, body);
    state.modes = state.modes.map((mode) => (mode.name === name ? saved : mode));
    state.editingBoundary = null;
  }, "Boundary saved");
}
