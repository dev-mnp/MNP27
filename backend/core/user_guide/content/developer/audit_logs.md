# Audit Logs

## What this module is

Audit Logs provide a read-only history of important changes. Use it to trace who changed a record, when it changed, and what details were recorded.

## Main code files

- Views: `core/audit_logs/views.py`
- URLs: `core/audit_logs/urls.py`
- Templates: `core/templates/audit_logs/`
- Model: `AuditLog`

## Main table

- `audit_logs`

## Important fields

- `user_id`: user who performed the action.
- `action_type`: create, update, delete, submit, reopen, archive, restore, export, or upload.
- `entity_type`: module/object type.
- `entity_id`: id or application number.
- `details`: JSON information about the action.
- `ip_address`
- `user_agent`
- `created_at`

## Debug checklist

- Missing audit row: check whether the relevant view writes audit logs.
- Wrong user: inspect request user and service/system actions.
- Hard-to-read details: keep `details` JSON structured with before/after values where possible.

## Screen fields

- User: actor who performed the action.
- Action: create, update, delete, submit, reopen, archive, restore, export, upload.
- Entity type: module or model affected.
- Entity id: id or business number of the affected record.
- Details: JSON payload explaining the change.
- IP address and user agent: request metadata.
- Created at: action time.

## Buttons and actions

- Search filters logs by visible text.
- Date filters narrow logs by time.
- Module/action filters narrow the audit trail.
- View details opens the JSON detail where available.

## Common errors and fixes

- Audit page slow: add indexes or filter before loading large log sets.
- Details too vague: improve the audit writer in the source module.
- Time looks wrong: confirm timezone display and stored UTC/IST behavior.
