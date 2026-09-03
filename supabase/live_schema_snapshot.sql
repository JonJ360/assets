-- Asset Tracker live schema snapshot
-- Project: inhwadbibwkakacdvoxu
-- Captured: 2026-09-03
-- Documentation/recovery artifact only. Review before applying anywhere.

create extension if not exists pgcrypto;

create table if not exists public.assets (
  id uuid primary key default gen_random_uuid(),
  unit_no text,
  name text not null,
  category text,
  make text,
  model text,
  year integer,
  vin text,
  serial text,
  plate text,
  entity text,
  location text,
  status text default 'Active',
  assigned_to text,
  purchase_date date,
  purchase_price numeric,
  sale_price numeric,
  vendor text,
  funding text,
  lender text,
  loan_payoff numeric,
  reg_expires date,
  insured boolean default false,
  title_status text,
  title_note text,
  state text,
  title_number text,
  gvw numeric,
  on_dep_schedule boolean default false,
  dep_location text,
  origin text,
  notes text,
  doc_url text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  in_progress boolean default false,
  on_irp boolean default false,
  on_ifta boolean default false,
  on_2290 boolean default false,
  axles integer,
  unladen numeric,
  compliance_notes text,
  sold_to text,
  sale_date date
);

create table if not exists public.asset_history (
  id bigint generated always as identity primary key,
  asset_id uuid,
  unit_no text,
  name text,
  op text not null,
  changed_at timestamptz default now(),
  changes jsonb
);

create index if not exists idx_assets_entity on public.assets (entity);
create index if not exists idx_assets_location on public.assets (location);
create index if not exists idx_assets_status on public.assets (status);
create index if not exists idx_assets_unit on public.assets (unit_no);
create index if not exists idx_hist_asset on public.asset_history (asset_id);
create index if not exists idx_hist_time on public.asset_history (changed_at desc);

alter table public.assets enable row level security;
alter table public.asset_history enable row level security;

create or replace function public.log_asset_change()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $function$
declare diff jsonb;
begin
  if tg_op = 'UPDATE' then
    select coalesce(jsonb_object_agg(o.key, jsonb_build_object('from', o.value, 'to', n.value)), '{}'::jsonb)
      into diff
    from jsonb_each(to_jsonb(old)) o
    join jsonb_each(to_jsonb(new)) n on n.key = o.key
    where o.value is distinct from n.value
      and o.key not in ('updated_at','created_at');
    if diff = '{}'::jsonb then return new; end if;
    insert into public.asset_history(asset_id, unit_no, name, op, changes)
      values (new.id, new.unit_no, new.name, 'UPDATE', diff);
    return new;
  elsif tg_op = 'INSERT' then
    insert into public.asset_history(asset_id, unit_no, name, op, changes)
      values (new.id, new.unit_no, new.name, 'INSERT', to_jsonb(new));
    return new;
  else
    insert into public.asset_history(asset_id, unit_no, name, op, changes)
      values (old.id, old.unit_no, old.name, 'DELETE', to_jsonb(old));
    return old;
  end if;
end
$function$;

drop trigger if exists trg_asset_history on public.assets;
create trigger trg_asset_history
after insert or delete or update on public.assets
for each row execute function public.log_asset_change();

-- Recreate the observed production RLS policies.
drop policy if exists "auth read assets" on public.assets;
create policy "auth read assets" on public.assets
  for select to authenticated using (true);

drop policy if exists "editors insert" on public.assets;
create policy "editors insert" on public.assets
  for insert to authenticated
  with check (lower(auth.jwt() ->> 'email') = any (array['jonj@360-llc.com', 'margi@360-llc.com']));

drop policy if exists "editors update" on public.assets;
create policy "editors update" on public.assets
  for update to authenticated
  using (lower(auth.jwt() ->> 'email') = any (array['jonj@360-llc.com', 'margi@360-llc.com']))
  with check (lower(auth.jwt() ->> 'email') = any (array['jonj@360-llc.com', 'margi@360-llc.com']));

drop policy if exists "editors delete" on public.assets;
create policy "editors delete" on public.assets
  for delete to authenticated
  using (lower(auth.jwt() ->> 'email') = any (array['jonj@360-llc.com', 'margi@360-llc.com']));

drop policy if exists "auth read history" on public.asset_history;
create policy "auth read history" on public.asset_history
  for select to authenticated using (true);
