-- Sterling Sales app: database setup.
--
-- How to run: in the Supabase dashboard, open SQL Editor, paste this whole
-- file, and click Run. It is safe to run more than once.

-- ---------------------------------------------------------------------------
-- app_settings: John's targeting and messaging settings.
-- There is only ever one row (id = 1), because there is one set of settings.
-- ---------------------------------------------------------------------------
create table if not exists public.app_settings (
    id integer primary key default 1 check (id = 1),

    -- Targeting
    geography text not null,
    preferred_industries text[] not null default '{}',
    allow_non_tech boolean not null default true,
    revenue_min bigint not null check (revenue_min >= 0),
    revenue_max bigint not null check (revenue_max >= revenue_min),
    sales_reps_min integer not null check (sales_reps_min >= 0),
    sales_reps_max integer not null check (sales_reps_max >= sales_reps_min),
    target_role text not null,

    -- Messaging
    messaging_style text not null default '',
    value_proposition text not null default '',
    call_to_action text not null default '',

    -- Sender details. Left blank until Oliver/John provide them.
    sender_name text not null default '',
    sender_title text not null default '',
    sender_company text not null default '',
    signature text not null default '',
    booking_url text not null default '',

    updated_at timestamptz not null default now()
);

-- Row Level Security on, with no policies: the public "publishable"/"anon"
-- key can't read or write this table at all. The app uses the server-side
-- secret key, which is allowed through.
alter table public.app_settings enable row level security;
revoke all on public.app_settings from anon, authenticated;
