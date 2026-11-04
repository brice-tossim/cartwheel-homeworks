// Saving a turn's decisions: Langfuse scores first, then the local label files.
// After a save the page opens the next read turn left to label.

import { visibleConversations } from "./filters.js";
import { decisionsFor } from "./label-panel.js";
import { nextToLabel } from "./lookups.js";
import { select } from "./navigation.js";
import { act } from "./note-actions.js";
import { postJSON, refreshLabels } from "./server.js";
import { state } from "./state.js";

export async function saveLabels(traceId) {
  const order = visibleConversations();
  const savedIn = state.selectedId;
  let next = null;
  await act(async () => {
    await postJSON(`/api/traces/${encodeURIComponent(traceId)}/labels`, { decisions: decisionsFor(traceId) });
    delete state.labelDrafts[traceId];
    await refreshLabels();
    next = nextToLabel(order, savedIn);
    if (next) state.labelTurn[next.session_id] = next.turn;
    else delete state.labelTurn[savedIn];
  }, "Decisions saved");
  if (next && next.session_id !== state.selectedId) select(next.session_id);
}
