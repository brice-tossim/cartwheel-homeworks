// Trace review page: the Read view.
//
// Everything the page shows comes from the review server's JSON routes; the
// page keeps no copy of its own except a few per-viewer conveniences in
// localStorage. Each part of the page lives in its own file under js/.

import { bindClicks, bindFilters, bindKeys } from "./js/events.js";
import { $, esc } from "./js/helpers.js";
import { loadAll } from "./js/server.js";

bindFilters();
bindClicks();
bindKeys();
loadAll().catch((error) => {
  $("conversation").innerHTML = `<p class="empty">The review server did not answer: ${esc(error.message)}</p>`;
  $("progress-text").textContent = "";
});
