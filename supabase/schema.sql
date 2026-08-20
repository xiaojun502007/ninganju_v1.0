create extension if not exists "pgcrypto";

create table if not exists public.rent_preference (
  id uuid primary key default gen_random_uuid(),
  user_id uuid null,
  work_address text not null,
  budget_min integer not null,
  budget_max integer not null,
  commute_range text not null,
  priority text not null,
  markdown_prompt text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.recommendation_result (
  id uuid primary key default gen_random_uuid(),
  preference_id uuid not null references public.rent_preference(id) on delete cascade,
  areas_json jsonb not null,
  raw_response jsonb null,
  source text not null default 'fallback',
  created_at timestamptz not null default now()
);

create index if not exists idx_rent_preference_created_at
  on public.rent_preference(created_at desc);

create index if not exists idx_recommendation_result_preference_id
  on public.recommendation_result(preference_id);

alter table public.rent_preference enable row level security;
alter table public.recommendation_result enable row level security;

drop policy if exists "service role can manage rent preferences" on public.rent_preference;
create policy "service role can manage rent preferences"
  on public.rent_preference
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists "service role can manage recommendation results" on public.recommendation_result;
create policy "service role can manage recommendation results"
  on public.recommendation_result
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');
