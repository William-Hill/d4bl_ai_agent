-- Create profiles table linked to Supabase auth.users
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for role-based lookups
CREATE INDEX IF NOT EXISTS ix_profiles_role ON public.profiles(role);

-- Auto-create profile on new auth.users signup
-- Note: app.admin_email must be set as a PostgreSQL config variable
-- (e.g., ALTER DATABASE yourdb SET app.admin_email = 'admin@example.com')
-- for automatic admin detection. Otherwise, use scripts/bootstrap_admin.py
-- to manually promote the first admin after invite.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, role)
    VALUES (
        NEW.id,
        NEW.email,
        CASE
            WHEN NEW.email = current_setting('app.admin_email', true)
            THEN 'admin'
            ELSE 'user'
        END
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Add user_id to research_jobs (nullable for existing rows)
ALTER TABLE public.research_jobs
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);

CREATE INDEX IF NOT EXISTS ix_research_jobs_user_id
    ON public.research_jobs(user_id);

-- Enable RLS on research_jobs
ALTER TABLE public.research_jobs ENABLE ROW LEVEL SECURITY;

-- RLS: users see own jobs
CREATE POLICY "Users can view own jobs"
    ON public.research_jobs FOR SELECT
    USING (
        user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
        )
    );

-- RLS: users can insert own jobs
CREATE POLICY "Users can insert own jobs"
    ON public.research_jobs FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- RLS: users can update own jobs, admins can update any
CREATE POLICY "Users can update own jobs"
    ON public.research_jobs FOR UPDATE
    USING (
        user_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.profiles
            WHERE profiles.id = auth.uid() AND profiles.role = 'admin'
        )
    );

-- Note: The FastAPI backend connects with the service role key which bypasses RLS.
-- These policies provide defense-in-depth for direct Supabase client access.

-- Enable RLS on profiles
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- RLS: users can read own profile, admins can read all
CREATE POLICY "Users can view own profile"
    ON public.profiles FOR SELECT
    USING (
        id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.profiles p
            WHERE p.id = auth.uid() AND p.role = 'admin'
        )
    );

-- RLS: only admins can update profiles
CREATE POLICY "Admins can update profiles"
    ON public.profiles FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles p
            WHERE p.id = auth.uid() AND p.role = 'admin'
        )
    );

-- Auto-update updated_at on profile changes
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- Drop legacy tenant_id column (replaced by user_id)
ALTER TABLE public.research_jobs DROP COLUMN IF EXISTS tenant_id;
