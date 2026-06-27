# Valur Youth Fixtures — Setup Guide

A tiny "app" that shows upcoming (and recently played) matches for Valur's
teams, pulled daily from ksi.is, with separate tabs for each son:

- **Jon tab:** U19 A + U19 B
- **Stefan tab:** U16 A + U16 B
- **Calendar tab:** next four weeks, calendar layout with both players color-coded

No coding needed to set this up — just clicking through a few screens on
GitHub's website.

It works like this: a small script runs automatically once a day, reads
the two ksi.is pages, and updates a page that you keep on your iPhone's
Home Screen like a normal app icon.

---

## Step 1 — Create a GitHub account

1. Go to **https://github.com/signup**
2. Enter an email, password, and username, and follow the prompts.
3. It's free.

## Step 2 — Create a new repository

A "repository" (repo) is just a project folder.

1. Once logged in, click the **+** icon top-right → **New repository**.
2. Name it something like `valur-fixtures`.
3. Set it to **Public** (this just means the fixtures page is viewable by
   anyone with the link — there's no private data involved, it's all
   public match schedules).
4. Leave everything else as default, click **Create repository**.

## Step 3 — Upload the files

You should have a folder of files I gave you, including a hidden
`.github` folder — this part matters, see the note below.

1. On your new repo's page, click **Add file → Upload files**.
2. Drag in: `index.html`, `manifest.json`, `icon.png`, `data.json`,
   `scraper.py`, `requirements.txt`, `.gitignore`.
3. **Important:** the `.github/workflows/update-fixtures.yml` file needs to
   stay in that exact folder path. The easiest way: drag the whole
   `.github` *folder* (not just the file inside it) into the upload box —
   modern GitHub keeps the folder structure when you drop a folder in. If
   that doesn't work, click **Add file → Create new file**, and for the
   filename type the full path `.github/workflows/update-fixtures.yml`
   (GitHub will create the folders for you), then paste the file's
   contents in.
4. Scroll down, click **Commit changes**.

## Step 4 — Let the automatic updates write back to the repo

1. Go to your repo's **Settings → Actions → General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions**.
4. Click **Save**.

(This lets the daily script save the updated fixtures back into the repo.)

## Step 5 — Turn on the page (GitHub Pages)

1. Go to **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Branch: **main**, folder: **/ (root)**. Click **Save**.
4. After a minute or two, this section will show your live URL — something
   like `https://yourusername.github.io/valur-fixtures/`.

## Step 6 — Run the scraper once manually (don't wait for tomorrow)

1. Go to the **Actions** tab of your repo.
2. Click **Update Valur fixtures** in the left sidebar.
3. Click **Run workflow → Run workflow**.
4. Wait ~30 seconds, refresh — you should see a green checkmark.
5. From now on, this runs automatically every day at 06:00 Iceland time.
   You can also re-run it manually any time from this same screen.

## Step 7 — Add it to your iPhone

1. Open your Pages URL from Step 5 **in Safari** on your iPhone (must be
   Safari, not Chrome — only Safari supports this).
2. Tap the **Share** icon (square with an arrow).
3. Tap **Add to Home Screen**.
4. Give it a name (e.g. "Valur Youth") and tap **Add**.

You now have an app icon that opens straight to the fixtures, refreshed
once a day automatically.

---

## If something looks off

This scrapes a real third-party website, so its layout could change
in ways I can't predict or test in advance. If the page shows old data, or
a match looks wrong:

1. Go to the **Actions** tab and check whether the most recent run has a
   red X (failed) — click into it to see the error log.
2. Paste that error (or just tell me what looks wrong) back to me here,
   and I'll fix the scraper.

## What this does and doesn't cover

- Shows fixtures in two tabs:
   - Jon: U19 A and B
   - Stefan: U16 A and B
- Includes a third Calendar tab with upcoming fixtures (next 4 weeks),
   showing match time inside each day and color markers per player.
- Shows recent results with scores **when ksi.is's page structure makes
  that information available** in the same view as upcoming fixtures —
  this part is the least tested piece since I can't fully verify it
  against the live site from where I built this. If results aren't
  showing up after a few real matches have been played, let me know and
  I'll adjust it.
- Doesn't require Xcode, an Apple Developer account, or any app store
  submission — it's a website that behaves like an app once added to your
  Home Screen.
