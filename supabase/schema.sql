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

-- ---------------------------------------------------------------------------
-- leads: one row per company we're looking at.
-- ---------------------------------------------------------------------------
create table if not exists public.leads (
    id bigint generated always as identity primary key,

    -- Used to spot duplicates: the website's domain, or a tidied company name.
    company_key text not null unique,
    name text not null,
    website text not null default '',

    -- Where the company came from: 'provided' (typed in) or 'discovered'.
    source text not null default 'provided'
        check (source in ('provided', 'discovered')),
    discovery_reason text not null default '',
    discovery_sources jsonb not null default '[]',

    -- Where it is in the process. Never 'sent': the app doesn't send anything.
    status text not null default 'new'
        check (status in ('new', 'research failed', 'researched', 'needs review',
                          'draft ready', 'approved', 'manually contacted')),

    -- Research results (facts, each marked verified / estimate / unknown).
    research jsonb,
    research_sources jsonb not null default '[]',
    researched_at timestamptz,
    research_error text not null default '',

    -- Qualification result and the reasons behind it.
    qualification jsonb,
    qualification_result text not null default '',

    -- Outreach drafts, for a person to review and send by hand.
    email_subject text not null default '',
    email_body text not null default '',
    linkedin_note text not null default '',
    drafts_generated_at timestamptz,
    drafts_edited_at timestamptz,

    notes text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.leads enable row level security;
revoke all on public.leads from anon, authenticated;

-- ---------------------------------------------------------------------------
-- usage_log: one row per AI request, so we can see what research costs.
-- ---------------------------------------------------------------------------
create table if not exists public.usage_log (
    id bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    lead_id bigint references public.leads (id) on delete set null,
    kind text not null,  -- 'research', 'discovery' or 'drafts'
    model text not null default '',
    input_tokens integer not null default 0,
    output_tokens integer not null default 0,
    web_searches integer not null default 0,
    estimated_cost_usd numeric(10, 4)
);

alter table public.usage_log enable row level security;
revoke all on public.usage_log from anon, authenticated;
