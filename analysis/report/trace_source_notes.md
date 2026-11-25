# Trace source notes

Where the traces in my review came from, and why, whenever it was not my live Langfuse.

- Normal source: my running Langfuse.
- Fallback: `traces/support_traces.json`, read only when Langfuse cannot be reached. The trace ids stay unchanged, so decisions saved locally can be sent to Langfuse later.

## Fallback log

Nothing recorded yet.

One line per use: the date, why Langfuse could not be reached, and which traces I reviewed from the file.
