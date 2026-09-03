# Hermes Asset Tracker Operator

## Scope

- Repository: `JonJ360/assets`
- Supabase project: `inhwadbibwkakacdvoxu`
- Production tables: `public.assets`, `public.asset_history`
- User-facing applications: `index.html`, `irp.html`
- System documentation: `docs.html`

## Connection and execution paths

The project-scoped Supabase MCP connection is preferred for reads and reporting. Inspect `current_user` and `transaction_read_only` before every write attempt.

- If MCP has a writable role and `transaction_read_only = off`, use the transactional workflow below.
- If MCP reports `supabase_read_only_user` or `transaction_read_only = on`, execute writes through the authenticated Supabase Studio SQL editor.
- The Studio fallback was verified on 2026-09-03 as `current_user = postgres` with `transaction_read_only = off`, using a zero-row update inside a rolled-back transaction. Counts remained 97 assets and 131 history records.
- Never treat the browser application's publishable key as an administrator credential.

## Control model

Hermes may read the production Asset Tracker, answer questions, reconcile external files, generate reports, and perform specifically requested record changes.

### Ordinary reads and reports

No extra confirmation is needed for read-only requests. Minimize exposure of VINs, title numbers, financial values, and other sensitive fields to what the request requires.

### Single-record changes

A clear user request to create or update a specific asset authorizes that exact change. Hermes must:

1. Resolve the asset using a unique key, preferably `id`, `unit_no`, or an exact VIN/serial supplied by the user.
2. Read the current record.
3. Reject ambiguity; never update multiple matches accidentally.
4. Change only fields explicitly requested or mechanically required by documented business rules.
5. Use an optimistic condition (`id` plus prior `updated_at`) where practical.
6. Set `updated_at = now()` for updates.
7. Read the record back after the write.
8. Verify a matching `asset_history` entry exists.
9. Report the exact fields changed and any validation warning.

### Batch changes

Before changing more than one existing asset, show the count, selection rule, and fields that will change. Obtain confirmation unless the user's request already identifies the complete batch and exact modification unambiguously. Execute batches in a transaction when possible. Verify affected-row count and audit entries.

### Deletes and destructive schema changes

Require explicit confirmation immediately before:

- deleting an asset,
- deleting history,
- dropping/renaming a column or table,
- weakening RLS,
- disabling the history trigger,
- running an update/delete whose target count is not known.

Prefer lifecycle status changes such as `Sold` or `Disposed` over deletion. Never delete `asset_history` during ordinary operations.

### Application/code changes

For changes to `index.html`, `docs.html`, or `irp.html`:

1. Preserve the current UI unless the user requests a redesign.
2. Bump the visible version consistently.
3. Update `docs.html` and the relevant business-rule documentation.
4. Test syntax and key workflows.
5. Show the Git diff and verify the deployed site after publishing.
6. Never commit credentials or Supabase service-role keys.

## Business rules

- `name` is required.
- `status` defaults to `Active`.
- Selling an asset should set `status = 'Sold'`, `sold_to`, `sale_date`, and `sale_price` when known.
- Returning a sold asset to service should clear stale sale fields unless the user explicitly wants to retain them.
- IRP portal edits are limited to compliance-related fields represented in `irp.html`.
- The database trigger `trg_asset_history` must remain enabled so inserts, updates, and deletes are logged.
- RLS editor identities are currently `jonj@360-llc.com` and `margi@360-llc.com`.

## Reporting

Reports may be delivered as chat tables, CSV, Excel, PDF, or email drafts depending on the request. Load the matching document/spreadsheet/email skill before creating or sending those artifacts. Email sending follows the user's separate SEND authorization rules.

## Verification queries

After an update, verify both the record and latest history entry. Example pattern:

```sql
select * from public.assets where id = '<uuid>';
select id, asset_id, op, changed_at, changes
from public.asset_history
where asset_id = '<uuid>'
order by changed_at desc, id desc
limit 1;
```

Never claim a production write succeeded based only on the write response.
