-- One display-name profile per Supabase Auth user. Passwords stay in Auth.
create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    display_name text not null,
    created_at timestamptz not null default now(),
    constraint profiles_display_name_valid check (
        char_length(display_name) between 2 and 50
        and display_name !~ '[^[:alpha:] ]'
    )
);

alter table public.profiles enable row level security;

revoke all on table public.profiles from anon, authenticated;
grant select on table public.profiles to authenticated;

drop policy if exists "Users can read their own profile" on public.profiles;
create policy "Users can read their own profile"
    on public.profiles
    for select
    to authenticated
    using ((select auth.uid()) = id);

create or replace function public.create_profile_for_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_display_name text;
begin
    v_display_name := normalize(
        btrim(coalesce(new.raw_user_meta_data ->> 'display_name', '')),
        NFC
    );

    if char_length(v_display_name) < 2
       or char_length(v_display_name) > 50
       or v_display_name ~ '[^[:alpha:] ]' then
        raise exception using
            errcode = '23514',
            message = 'Invalid display name for profile';
    end if;

    insert into public.profiles (id, display_name)
    values (new.id, v_display_name);

    return new;
end;
$$;

revoke all on function public.create_profile_for_new_auth_user() from public, anon, authenticated;

drop trigger if exists create_profile_after_auth_user_insert on auth.users;
create trigger create_profile_after_auth_user_insert
    after insert on auth.users
    for each row execute function public.create_profile_for_new_auth_user();
