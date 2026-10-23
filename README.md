# JEXCA Chess leaderboard starter

A beginner-friendly static leaderboard that retrieves Lichess games on a schedule, maps verified Lichess usernames to JEXCA member identities, and calculates separate JEXCA Rapid and Blitz Elo ratings.

## Important rating rules in this starter
- Initial rating: 1200.
- Elo K-factor: 32.
- Only rated, standard-chess games with speed `rapid` or `blitz` are eligible.
- Both players must be in `members.csv` with `approved=yes`.
- Games are fetched from each player's Lichess history, deduplicated by game ID, and only eligible member-vs-member games count.
- The rating is recalculated chronologically from the stored game archive each update.
- This version shows the 100 most recent eligible games and Rapid/Blitz leaderboards. Tournament standings are a separate next phase.

## 1. Edit members.csv
Replace the example row. Columns:
- `member_id`: JEXCA cadet number or your chosen unique ID.
- `display_name`: name shown on the website.
- `lichess_username`: exact Lichess username.
- `approved`: `yes` only after manual JEXCA verification.

Do not add email addresses, phone numbers, or other private data. The public website and the repository may be visible to others.

## 2. Create a GitHub repository
1. Sign in at https://github.com/ and create a new repository named `jexca-chess`.
2. For the easiest free deployment with GitHub Pages, this starter assumes a public repository. That means the member mapping and game archive in the repository are public too. If that is unacceptable, stop here and use a private repository with a separate hosting arrangement before uploading real members.
3. Upload all files and folders from this starter ZIP, preserving the folder structure.
4. In the repository, open Settings → Pages. Under Build and deployment, choose **Deploy from a branch**, branch `main`, folder `/(root)`, then Save.
5. Open Actions → Update JEXCA Chess leaderboard → Run workflow. If prompted, confirm Run workflow.
6. Wait for the workflow to finish, then open the published Pages URL shown under Settings → Pages.

## 3. Enable workflow write access
If the workflow cannot push updated JSON files, open Settings → Actions → General → Workflow permissions, select **Read and write permissions**, and save. Re-run the workflow.

## 4. Run locally (optional)
Install Python 3.11 or later, open this folder in VS Code, then run:

```bash
python sync.py
```

No third-party Python packages are required.

## 5. Rules and limitations
- First run starts from `JEXCA_START_DATE` in the workflow environment, defaulting to 2026-10-22. Change `START_DATE` in `sync.py` before launch if you want a different official start date.
- The script re-fetches a rolling window around the newest stored game timestamp and stores game IDs to prevent duplicates, and tracks sync timestamps per member so newly approved members are backfilled from the official start date. Review the workflow logs for API errors.
- The script follows Lichess guidance to make requests sequentially and wait briefly between requests. If rate-limited, stop/retry later; do not repeatedly hammer the API.
- The starter only calculates Rapid and Blitz ratings from rated games. If JEXCA wants all casual games to count, the eligibility rules and fetch parameters must be changed deliberately.
- All registered members' user-game history is queried, but only games between two approved JEXCA members count.
- Do not assume Lichess team membership alone identifies every eligible game.
- The initial Elo rating and K-factor are configurable in `sync.py`; publish the rules before launch and avoid changing them casually.
- This starter does not yet import tournament standings. Lichess tournament IDs/results can be added in a follow-up version.
- Treat the first public launch as a pilot. Validate sample results and rating changes manually before declaring the leaderboard official.
