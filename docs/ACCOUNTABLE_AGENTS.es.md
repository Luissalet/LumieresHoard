# Agentes con responsabilidad

Varios asistentes y agentes de programación pueden manejar Lumiere's Hoard a la vez, por MCP o con `POST /api/agent/call`. Cada cambio
que hace uno de ellos se puede atribuir a un agente y a una sesión, lleva un motivo y se puede deshacer. La interfaz web no es un agente:
ejecuta las mismas herramientas sin motivo y sin diario, y nada de esto le afecta.

La biblioteca que lo hace posible es Hoard Link 0.8.2 (`lumiere_hoard/hoard_link/`, incluida en el repositorio); los ganchos de cada
herramienta están en `lumiere_hoard/agent_undo.py`.

## 1. Quién llama

El puente MCP (`mcp_server.py`) envía dos cabeceras tomadas del entorno de quien lo lanza:

```
HOARD_AGENT_ID=mi-agente  HOARD_AGENT_SESSION=ejecucion-42
```

(`X-Agent-Id`, `X-Agent-Session`; también valen `agent` / `caller` y `_session` / `session` en el cuerpo). La sesión es un identificador
opaco: el chat o la ejecución del agente. Una llamada sin sesión se anota igualmente, pero solo se puede deshacer una sesión entera si la tiene.

## 2. Un motivo en cada cambio

Toda herramienta que no sea de solo lectura necesita un `reason` de 3 a 300 caracteres, en el cuerpo (`{"name", "arguments", "reason"}`) o
entre los argumentos. Sin él no se ejecuta nada:

```json
400 {"error": "This tool changes data, so the call needs a reason.", "code": "reason_required",
     "hint": "Add a `reason` (3-300 characters): one sentence on why you are making this change. ..."}
```

`GET /api/agent/tools` lista `reason` como propiedad obligatoria de esas herramientas, de modo que el modelo lo ve en el esquema. Las
herramientas de lectura (`project_get`, `media_list`, `job_status`, `transcript_get`...) no lo necesitan y no se anotan.

## 3. El diario

Cada cambio que llegó a su herramienta, con éxito o no, es una línea de `data/agent_journal.jsonl` (rota a unos 5 MB): herramienta, agente,
sesión, motivo, una huella (hash) y un resumen enmascarado de los argumentos, los identificadores tocados, los objetos (`project:prj_...`,
`media:med_...`), una huella del resultado, la hora y si se puede deshacer. Los secretos se enmascaran. El evento `agent.write` llega al bus de
la familia (nunca los argumentos).

`GET /api/agent/journal?session=&agent=&kind=&since=&limit=` (con token Bearer) lo lee.

## 4. Deshacer una sesión

```
POST /api/agent/undo {"session": "ejecucion-42", "dry_run": true}                       qué se desharía
POST /api/agent/undo {"session": "ejecucion-42", "confirm": true, "reason": "..."}      hacerlo, del cambio más reciente al más antiguo
```

Solo se miran los cambios de esa sesión (y de ese agente, si se indica); nunca se tocan las otras sesiones. Cada proyecto vuelve atrás
guardando su montaje anterior como un **paso nuevo de su historial** («Deshacer cambios del agente»): no se pierde nada y los Deshacer y
Rehacer del editor siguen funcionando. Un cambio se declara **conflicto**, y se deja como está, cuando otra sesión escribió después en el
mismo objeto o cuando el objeto ya no se parece a como lo dejó el cambio (por ejemplo, la persona editó el montaje en el editor).

| Lo deshace | Qué hace |
| --- | --- |
| `timeline_edit`, `edit_command`, `text_cut`, `multicam_create`, `multicam_switch`, `multicam_auto`, `music_pick` (con `add`), `broll_suggest` (con `place`), `clip_freeze`, `timeline_history` (undo, redo, restore) | el proyecto vuelve al montaje que tenía antes de la llamada (una vista previa, un `request_id` repetido o un análisis que faltaba no cambiaron nada y no hay nada que hacer) |
| `timeline_nest` | el montaje vuelve atrás y se borra el proyecto de secuencia que creó |
| `project_create`, `project_from_timeline`, `short_from_range`, `template_save` | se borra el proyecto, salvo que la persona lo editara, otro proyecto lo anide o se exportara (conflicto) |
| `plan_create` | se borra el plan en borrador |
| `plan_apply` | el montaje vuelve a como estaba antes del plan y el plan vuelve a ser un borrador; los renders que el plan puso en cola no se cancelan |
| `media_import`, `media_shared`, `media_receive` | las entradas que añadió salen de la biblioteca (los archivos nunca se tocan); el proyecto que creó o amplió vuelve atrás; las entradas que usa un proyecto se quedan |
| `media_tag` | vuelven las etiquetas |
| `transcript_fix`, `speakers_edit` (rename, assign, merge, clear) | vuelven la transcripción y los hablantes |
| `subtitles_translate` con `fix` o `delete` | vuelven las líneas traducidas |
| `settings` | vuelven los valores anteriores |

**No se pueden deshacer** (salen en `not_undoable`, con `reason: "no_handler"`): `media_delete`, `project_delete`, `media_analyze`, `clip_stabilize`,
`render_start`, `frame_snapshot`, `project_contact_sheet`, `subtitles_export`, `project_export_otio`, `job_cancel` y las herramientas `creative_*`.
Algunas herramientas tienen una parte que no se puede deshacer, y esa llamada concreta sale como no deshacible con su motivo: una traducción o
una separación de voces hecha por un trabajo en segundo plano (`subtitles_translate` con `translate`, `speakers_edit` con `diarize`) y el
refresco de un original compartido (`media_shared`). El historial conserva los últimos 300 pasos de un proyecto; una versión anterior a eso no se puede restaurar.

## 5. Tokens y perfiles

El token principal (`data/mcp-token`) lo puede todo. Los tokens extra, uno por agente, se guardan con hash en `data/agent_tokens.json`:

```
python -m lumiere_hoard.hoard_link.tokens mint   --app-data-dir data --agent mi-agente --profile drafts      # muestra el token una sola vez
python -m lumiere_hoard.hoard_link.tokens list   --app-data-dir data
python -m lumiere_hoard.hoard_link.tokens revoke --app-data-dir data --agent mi-agente
```

(o `GET/POST /api/agent/tokens` y `DELETE /api/agent/tokens/{id}` con el token principal). El agente arranca su puente con `LUMIERE_TOKEN` igual
a ese token en lugar de leer `mcp-token`. Un token con ámbito fija el nombre del agente de sus llamadas, solo ve sus propias líneas del
diario y solo puede deshacer con el perfil `all`.

| Perfil | Puede llamar a |
| --- | --- |
| `read_only` | las herramientas que no cambian nada |
| `drafts` | esas, más las que crean o editan borradores sin borrar, exportar ni publicar: `media_import`, `media_shared`, `media_receive`, `media_tag`, `media_analyze`, `transcript_fix`, `speakers_edit`, `project_create`, `project_from_timeline`, `short_from_range`, `template_save`, `timeline_edit`, `timeline_history`, `timeline_nest`, `edit_command`, `text_cut`, `plan_create`, `multicam_create`, `multicam_switch`, `multicam_auto`, `music_pick`, `broll_suggest`, `clip_freeze`, `clip_stabilize`, `frame_snapshot`, `project_contact_sheet` |
| `all` | todo (menos la administración de tokens) |

Una llamada que el perfil no permite responde `403 profile_forbidden` con una pista.
