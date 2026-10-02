-- Toolbox GP Lunch Planner – Supabase schema.
-- Run once in the Supabase dashboard: SQL Editor → New query → paste → Run.

-- Every planner record is one JSON document: collection is 'clinics',
-- 'lunches', 'todos' or 'settings'.
create table if not exists public.docs (
  collection text not null,
  id         text not null,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (collection, id)
);

-- People allowed to open the planner. Emails must be lower case.
create table if not exists public.allowed_users (
  email text primary key
);

alter table public.docs enable row level security;
alter table public.allowed_users enable row level security; -- no policies: not readable from the site

create or replace function public.is_allowed()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.allowed_users
    where email = lower(auth.jwt() ->> 'email')
  );
$$;

drop policy if exists "allowed users read"   on public.docs;
drop policy if exists "allowed users insert" on public.docs;
drop policy if exists "allowed users update" on public.docs;
drop policy if exists "allowed users delete" on public.docs;
create policy "allowed users read"   on public.docs for select to authenticated using (public.is_allowed());
create policy "allowed users insert" on public.docs for insert to authenticated with check (public.is_allowed());
create policy "allowed users update" on public.docs for update to authenticated using (public.is_allowed()) with check (public.is_allowed());
create policy "allowed users delete" on public.docs for delete to authenticated using (public.is_allowed());

-- Merge fields into an existing document (runs as the caller, so the policies above apply).
create or replace function public.merge_doc(p_collection text, p_id text, p_patch jsonb)
returns void
language sql security invoker set search_path = public
as $$
  update public.docs
     set data = data || p_patch, updated_at = now()
   where collection = p_collection and id = p_id;
$$;

revoke all on function public.merge_doc(text, text, jsonb) from anon;
revoke all on function public.is_allowed() from anon;

-- Live updates between people who have the planner open.
do $$
begin
  alter publication supabase_realtime add table public.docs;
exception when duplicate_object then null;
end $$;

-- Who can sign in. Edit this list, then re-run just this statement to add people.
insert into public.allowed_users (email) values
  ('davidberlinski1@gmail.com')
on conflict do nothing;
