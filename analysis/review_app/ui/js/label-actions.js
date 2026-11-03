// Saving a turn's decisions: Langfuse scores first, then the local label files.

import { decisionsFor } from "./label-panel.js";
import { act } from "./note-actions.js";
import { postJSON, refreshLabels } from "./server.js";
import { state } from "./state.js";

export async function saveLabels(traceId) {
  await act(async () => {
    await postJSON(`/api/traces/${encodeURIComponent(traceId)}/labels`, { decisions: decisionsFor(traceId) });
    delete state.labelDrafts[traceId];
    delete state.labelTurn[state.selectedId];
    await refreshLabels();
  }, "Decisions saved");
}
