# Asset Tracker Upload and Safe-Edit Design

Status: proposal only; no production schema, Storage, RLS, or credentials have been changed.

## Decision

Keep the existing Supabase project (`inhwadbibwkakacdvoxu`) as the system of record. Add private Supabase Storage for documents and relational metadata in Supabase. Do not place files in GitHub, browser local storage, or public Storage.

Hermes should operate through a dedicated Supabase Auth identity with the same narrowly scoped RLS rights as an approved editor. Do not give Hermes the service-role key and do not use the browser publishable key as an administrator credential.

## Scope

### Phase 1 — safe asset edits

Retain `public.assets` and `public.asset_history`.

For every Hermes update:

1. Resolve exactly one asset by UUID, exact unit number, VIN, or serial.
2. Read the row and retain `updated_at`.
3. Validate the requested fields and linked business rules.
4. Update only the requested fields, with `updated_at = now()` and an optimistic `id + prior updated_at` predicate.
5. Require exactly one returned row.
6. Read the asset back.
7. Read the newest `asset_history` row and verify the changed keys and values.

Before enabling unattended edits, add a constrained RPC such as `update_asset_if_current(asset_id, expected_updated_at, patch)` or equivalent field-specific functions. The browser pages should eventually use the same concurrency rule; today their writes remain last-write-wins.

### Phase 2 — private document uploads

Create:

- private Storage bucket `asset-documents`;
- `public.asset_documents` for searchable document metadata;
- `public.asset_document_history` for immutable upload/replace/archive audit events;
- authenticated read policies;
- editor-only upload and metadata policies;
- no routine hard-delete path.

Keep `assets.doc_url` during migration for existing SharePoint/OneDrive links. New uploads should use `asset_documents`, allowing multiple documents per asset.

## Proposed document metadata

| Field | Purpose |
|---|---|
| `id` | Immutable document UUID |
| `asset_id` | Required link to one asset |
| `document_type` | Title, bill of sale, registration, insurance, loan, tax, photo, other |
| `storage_bucket` | Fixed to `asset-documents` |
| `storage_path` | Unique generated object path |
| `original_name` | User-visible source filename |
| `mime_type` | Validated content type |
| `byte_size` | Upload-size verification |
| `sha256` | Duplicate and integrity check |
| `version_no` | Version within a logical document chain |
| `replaces_document_id` | Prior immutable version, if any |
| `status` | `active`, `replaced`, `archived`, or `quarantined` |
| `uploaded_by` / `uploaded_email` | Auth actor |
| timestamps | Created and status-change times |

Object path convention:

```text
<asset_uuid>/<document_uuid>/<sanitized-original-name>
```

Object names are generated and uploads use `upsert=false`; a replacement creates a new object and metadata row rather than overwriting evidence.

## Upload workflow

1. Resolve and read the target asset.
2. Validate the file before upload:
   - allow PDF, JPEG, PNG, DOCX, and XLSX initially;
   - maximum 25 MB;
   - verify extension, declared MIME type, and file signature where available;
   - sanitize the display filename but generate the storage path from UUIDs;
   - calculate SHA-256 client-side or in the Hermes worker.
3. Check for an existing active document with the same asset, type, and checksum.
4. Upload to the private bucket with `upsert=false`.
5. Insert `asset_documents` metadata.
6. Insert/verify the audit event.
7. Read back metadata and verify the object exists with matching size/checksum metadata.
8. If metadata insertion fails after object upload, delete the just-created orphan immediately and log the cleanup. A scheduled reconciliation should flag any remaining orphan object or metadata row.

## Download workflow

Do not expose public URLs. The browser requests a short-lived signed URL (target: five minutes) or fetches the object with the authenticated access token and creates a temporary browser object URL. Hermes downloads with its authenticated identity.

## Replace, archive, and delete

- Replace: upload a new immutable object and row, increment `version_no`, link `replaces_document_id`, and mark the prior row `replaced` in one database transaction after the upload succeeds.
- Archive: set status to `archived`; retain the object and audit history.
- Delete/purge: unavailable in routine UI and Hermes workflows. Require explicit confirmation and a retention decision immediately before permanent removal.

## RLS model

- Authenticated users: read assets, document metadata, and private objects.
- Approved editors (`jonj@360-llc.com`, `margi@360-llc.com`, and a dedicated Hermes identity only after approval): insert/update asset records and document metadata; upload objects.
- History tables: authenticated select only; writes occur through security-definer audit triggers.
- Storage paths: policies are limited to bucket `asset-documents`; no public bucket and no anonymous policy.

Prefer an `asset_editor_emails` table or custom JWT role over repeating hard-coded email arrays once the Hermes identity is introduced. Changing the current editor allowlist, RLS, or Auth configuration requires explicit approval.

## Audit requirements

Document history records:

- operation (`UPLOAD`, `REPLACE`, `ARCHIVE`, `PURGE`);
- asset and document UUIDs;
- actor UID/email;
- timestamp;
- metadata changes;
- checksum and storage path.

The existing `asset_history` should also gain actor/source fields in a later migration so browser, portal, Hermes, and SQL changes can be distinguished. Preserve the current history trigger throughout.

## Browser changes after schema approval

In the existing asset detail panel, preserve the current UI and replace the single Document link area with:

- existing external link, if present;
- a compact document list grouped by type;
- Open, Upload, Replace, and Archive controls based on RLS/editor status;
- upload progress and clear validation errors.

No drag-and-drop or redesign is required for the first release.

## Hermes operating path

Preferred order:

1. project-scoped Supabase MCP for reads;
2. dedicated authenticated Hermes identity for scoped RPC/Storage operations;
3. Supabase Studio only as an attended fallback.

Secrets must live in the Hermes secret/config store, never in this repository, an HTML file, logs, or chat. Production writes retain the read → optimistic write → row read-back → history read-back contract in `OPERATIONS.md`.

## Rollout gates

1. Confirm dedicated Hermes identity name and editor scope.
2. Review and approve the proposed migration and RLS changes.
3. Capture a fresh production schema/policy snapshot.
4. Apply migration in a transaction where possible; create the private bucket and Storage policies.
5. Run zero-impact authorization tests for anonymous, viewer, editor, and Hermes identities.
6. Upload one non-sensitive test PDF to a designated test asset; verify metadata, object, signed download, audit, replacement, archive, and orphan cleanup.
7. Add the UI behind a feature flag, bump the visible version, test, publish, and verify GitHub Pages.
8. Enable Hermes uploads only after the same end-to-end checks pass through its identity.

## Open decisions requiring approval

- Dedicated Hermes Auth email/identity.
- Whether all authenticated viewers may download all asset documents or only editors.
- Retention period for replaced/archived documents and whether purge is ever permitted.
- Whether malware scanning is required before downloads become available.
- Whether existing SharePoint links should remain external indefinitely or be migrated into Supabase Storage.
