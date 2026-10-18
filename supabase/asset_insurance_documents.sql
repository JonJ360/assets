-- Approved private insurance-card storage. No existing asset/policy changes.
begin;
create role asset_document_operator nologin noinherit;
grant asset_document_operator to authenticator;
grant usage on schema public,storage,auth to asset_document_operator;
grant execute on function auth.uid(),auth.jwt() to asset_document_operator;
grant select(id,vin,unit_no,name,entity,status,updated_at) on public.assets to asset_document_operator;
create policy "operator read assets for documents" on public.assets for select to asset_document_operator using(true);
create table public.asset_documents (
 id uuid primary key default gen_random_uuid(),
 asset_id uuid not null references public.assets(id) on delete restrict,
 document_type text not null default 'insurance' check(document_type='insurance'),
 storage_bucket text not null default 'asset-documents' check(storage_bucket='asset-documents'),
 storage_path text not null unique,
 original_name text not null,
 mime_type text not null default 'application/pdf' check(mime_type='application/pdf'),
 byte_size bigint not null check(byte_size>0 and byte_size<=26214400),
 sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
 policy_number text not null,
 effective_date date not null,
 expiration_date date not null check(expiration_date>effective_date),
 insured_entity text not null,
 source_identifier text not null,
 status text not null default 'active' check(status in ('active','archived')),
 uploaded_by uuid,
 uploaded_email text,
 created_at timestamptz not null default now(),
 unique(asset_id,document_type,sha256),
 check(storage_path = asset_id::text || '/insurance/' || sha256 || '.pdf')
);
create index asset_documents_asset_idx on public.asset_documents(asset_id,document_type,created_at desc);
create table public.asset_document_history (
 id bigint generated always as identity primary key,
 document_id uuid not null references public.asset_documents(id) on delete restrict,
 asset_id uuid not null references public.assets(id) on delete restrict,
 op text not null check(op='UPLOAD'),
 actor_id uuid,
 actor_email text,
 changed_at timestamptz not null default now(),
 changes jsonb not null
);
alter table public.asset_documents enable row level security;
alter table public.asset_document_history enable row level security;
revoke all on public.asset_documents, public.asset_document_history from public,anon,authenticated,service_role;
revoke all on sequence public.asset_document_history_id_seq from public,anon,authenticated,service_role;
grant select,insert on public.asset_documents to authenticated;
grant select on public.asset_document_history to authenticated;
create policy "auth read asset documents" on public.asset_documents for select to authenticated using(true);
create policy "editors insert asset documents" on public.asset_documents for insert to authenticated with check(lower(auth.jwt()->>'email')=any(array['jonj@360-llc.com','margi@360-llc.com','shaynew@smionline.com']));
create policy "auth read asset document history" on public.asset_document_history for select to authenticated using(true);
create function public.stamp_asset_document() returns trigger language plpgsql set search_path=pg_catalog,public as $$
begin
 if TG_OP <> 'INSERT' then raise exception 'Document metadata is append-only'; end if;
 new.uploaded_by := (nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid;
 new.uploaded_email := coalesce(lower(nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'email'),session_user::text);
 new.created_at := now();
 return new;
end $$;
create trigger stamp_asset_document before insert or update or delete on public.asset_documents for each row execute function public.stamp_asset_document();
create function public.audit_asset_document() returns trigger language plpgsql security definer set search_path=pg_catalog,public as $$
begin
 insert into public.asset_document_history(document_id,asset_id,op,actor_id,actor_email,changes)
 values(new.id,new.asset_id,'UPLOAD',new.uploaded_by,new.uploaded_email,to_jsonb(new));
 return new;
end $$;
revoke all on function public.stamp_asset_document(),public.audit_asset_document() from public,anon,authenticated,service_role;
create trigger audit_asset_document after insert on public.asset_documents for each row execute function public.audit_asset_document();
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('asset-documents','asset-documents',false,26214400,array['application/pdf']);
create policy "auth read linked asset documents" on storage.objects for select to authenticated using(bucket_id='asset-documents' and exists(select 1 from public.asset_documents d where d.storage_path=name and d.storage_bucket=bucket_id));
create policy "editors upload asset documents" on storage.objects for insert to authenticated with check(bucket_id='asset-documents' and lower(auth.jwt()->>'email')=any(array['jonj@360-llc.com','margi@360-llc.com','shaynew@smionline.com']) and name ~ '^[0-9a-f-]{36}/insurance/[0-9a-f]{64}\.pdf$' and exists(select 1 from public.assets a where a.id::text=split_part(objects.name,'/',1)));
grant select,insert on public.asset_documents to asset_document_operator;
grant select on public.asset_document_history to asset_document_operator;
grant select,insert on storage.objects to asset_document_operator;
grant select on storage.buckets to asset_document_operator;
create policy "operator read document bucket" on storage.buckets for select to asset_document_operator using(id='asset-documents');
create policy "operator read documents" on public.asset_documents for select to asset_document_operator using(true);
create policy "operator insert documents" on public.asset_documents for insert to asset_document_operator with check(true);
create policy "operator read document audit" on public.asset_document_history for select to asset_document_operator using(true);
create policy "operator read linked document objects" on storage.objects for select to asset_document_operator using(bucket_id='asset-documents' and exists(select 1 from public.asset_documents d where d.storage_path=objects.name and d.storage_bucket=objects.bucket_id));
create policy "operator upload document objects" on storage.objects for insert to asset_document_operator with check(bucket_id='asset-documents' and name ~ '^[0-9a-f-]{36}/insurance/[0-9a-f]{64}\.pdf$' and exists(select 1 from public.assets a where a.id::text=split_part(objects.name,'/',1)));
commit;
