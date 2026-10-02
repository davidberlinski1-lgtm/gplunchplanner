# Toolbox GP Lunch Planner

A single-page planner hosted on GitHub Pages, with its data in a Supabase database.
People sign in with an emailed link; only emails on the `allowed_users` list can read or change anything.

- `index.html` – the whole app
- `config.js` – Supabase project URL and anon key
- `supabase/schema.sql` – database tables, access rules and the access list

## Set-up (about 15 minutes, all free tiers)

### 1. Supabase
1. Create a project at https://supabase.com (free plan).
2. **SQL Editor → New query**: paste all of `supabase/schema.sql`, add any other team emails (lower case) to the list at the bottom, and Run.
3. **SQL Editor → New query**: paste all of `supabase/seed-referrals.sql` and Run to load the practices, doctors and referral counts.
   To refresh later from a new export: `python tools/build_seed.py "<export.xlsx>"`, then run the regenerated file again
   (it only updates referral figures and doctor lists; visits, notes and contact edits are kept).
4. **Project Settings → API**: copy the Project URL and the `anon` / publishable key into `config.js`.
   Never use the `service_role` key here.

### 2. GitHub Pages
1. Create a repository on GitHub and push this folder to it. On a free GitHub plan the repository must be public for Pages;
   that exposes the page code and the anon key only, not the data.
2. **Settings → Pages → Deploy from a branch → `main` / root**.
   The site appears at `https://<username>.github.io/<repo>/`.

### 3. Point Supabase sign-in at the site
**Authentication → URL Configuration**: set *Site URL* to the GitHub Pages address and add the same address under *Redirect URLs*.

Then open the site, enter your email and use the link you're sent.

## Notes
- **Adding people:** `insert into public.allowed_users (email) values ('name@example.com');` in the SQL Editor.
- **Sign-in emails:** Supabase's built-in mailer only sends a few emails per hour. Sessions last, so that is normally enough for a small team; add your own SMTP under Authentication → Emails if you hit the limit.
- **Free-plan pausing:** Supabase pauses free projects after about a week with no activity; restore it from the dashboard.
- **Backups:** Table Editor → `docs` → Export to CSV.
