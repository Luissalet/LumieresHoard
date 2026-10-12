# Faustus copilot in Lumiere

Faustus owns the panel, conversation history, composer drafts and agent execution. Lumiere provides its native tools and the current video workspace through `window.hoardCopilot` and the shared HoardLink relay.

- `/api/copilot/info`, `panel.js`, `launcher.js` and `proxy` use the canonical shared installer and transport. The current vendor includes standard-library transport and native-dialog support.
- The current project and selected clips resolve against the native project document. New or missing projects have no fabricated object IDs.
- `view.editor` carries changed fields from new-project, name, export, settings and edit-plan forms. `view.form_values` supplements these with the complete current values of displayed editor/tool controls. Hidden, file and password inputs are omitted. These snapshots are captured before an asynchronous project read; they contain no conversation history.
- The shared panel uses the application's language and stays in the same conversation while opening or closing dialogs.
- Turn completion refreshes native views in place. Settings refresh merges server values with unsaved differences; partial Save retains changes entered after submission so they can be saved next.
- Native edit plans remain available as video-editing objects and operations.

Verification for #395 R2: 355 Python tests passed with 3 skips; 13 context/draft tests passed; frontend build passed. Private browser/native-MCP56 verification demonstrated a normal shared-panel turn calling native `settings`, keeping a pending language edit while changing default export, and preserving later text through a held Save request. A 5,227-character edit-plan draft including its final marker reached the canonical project conversation intact. The provider was simulated, with no GPU or production-data mutation; this verifies integration, not global-model autonomy.
