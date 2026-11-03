// Switching between the page's tabs, and drawing the Failure modes tab.

import { $, plural } from "./helpers.js";
import { modesView } from "./modes-view.js";
import { remember, state } from "./state.js";

const VIEWS = ["read", "modes"];

export function renderViews() {
  const view = VIEWS.includes(state.view) ? state.view : "read";
  document.querySelectorAll(".tab[data-view]").forEach((tab) => {
    const active = tab.dataset.view === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-pressed", String(active));
  });
  $("read-view").hidden = view !== "read";
  $("modes-view").hidden = view !== "modes";
  renderModes();
}

export function renderModes() {
  $("modes-count").textContent = plural(state.modes.length, "mode");
  $("modes").innerHTML = modesView();
}

export function showView(view) {
  state.view = view;
  remember("view", view);
  renderViews();
}
