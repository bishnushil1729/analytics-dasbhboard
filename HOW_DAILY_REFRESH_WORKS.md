# 🔄 How Daily Dashboard Refresh Works

## Overview

Once deployed, your dashboard **automatically refreshes every day** without any manual intervention. Here's exactly how it works:

---

## 📅 Daily Schedule

**Default:** Every day at **2:00 AM UTC** (7:30 AM IST)

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Every Day at 2:00 AM UTC                                  │
│  (7:30 AM IST - Perfect for India business hours!)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🤖 GitHub Actions - The Automation Engine

### What is GitHub Actions?

GitHub Actions is a **CI/CD platform** (Continuous Integration/Continuous Deployment) built into GitHub. It runs your code on **GitHub's cloud servers** automatically.

**Key Point:** Once deployed, everything runs on **GitHub's servers**, not your laptop!

---

## 🔧 How It's Configured

### File: `.github/workflows/production-dashboard.yml`

```yaml
name: Production FE App Dashboard Update

on:
  # ⏰ AUTOMATIC TRIGGER - Runs daily
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC every day

  # 🔘 MANUAL TRIGGER - You can also run manually
  workflow_dispatch:

  # 🚀 AUTO-RUN ON CODE CHANGES
  push:
    branches:
      - main
```

---

## ⏰ Cron Schedule Explained

```
'0 2 * * *'
 │ │ │ │ │
 │ │ │ │ └─── Day of week (0-6, Sunday=0) - * means every day
 │ │ │ └───── Month (1-12) - * means every month
 │ │ └─────── Day of month (1-31) - * means every day
 │ └───────── Hour (0-23) - 2 means 2 AM UTC
 └─────────── Minute (0-59) - 0 means on the hour
```

**Translation:** "At minute 0 of hour 2, every day of every month, every day of the week"

**In Simple Terms:** Every day at 2:00 AM UTC (7:30 AM India time)

---

## 🔄 Step-by-Step: What Happens Every Day

### Automatic Execution (No Human Needed!)

```
2:00 AM UTC - GitHub Actions starts automatically
    ↓
Step 1: Checkout Code (5 seconds)
    ↓ GitHub clones your repository to a fresh Ubuntu server

Step 2: Setup Python (10 seconds)
    ↓ Installs Python 3.10 on the server

Step 3: Install Dependencies (30 seconds)
    ↓ Installs: pandas, plotly, trino-python-client

Step 4: Fetch Ticket Data (2-3 minutes)
    ↓ python production_wrapper.py starts
    ↓ Connects to Trino database
    ↓ Runs: SELECT * FROM hive.aggregate_pa.pos_ae_ticket_funnel_v1
    ↓ Downloads ~218,000 rows
    ↓ Saves to: data/latest_hive_data.csv

Step 5: Fetch Agent Funnel Data (1-2 minutes)
    ↓ Connects to Trino
    ↓ Joins 4 tables (agents, managers, funnel, dates)
    ↓ Downloads ~80,000 rows
    ↓ Saves to: data/latest_agent_funnel_data.csv

Step 6: Transform Data (10 seconds)
    ↓ Runs: transform_funnel_data.py
    ↓ Reformats columns
    ↓ Saves to: data/latest_funnel_transformed.csv

Step 7: Create MTD Views (15 seconds)
    ↓ Runs: create_mtd_comparison_views.py
    ↓ Calculates Current MTD vs Last MTD
    ↓ Creates 5 comparison CSV files

Step 8: Generate Dashboard (1-2 minutes)
    ↓ Runs: simple_daily_dashboard_interactive.py
    ↓ Loads all data
    ↓ Creates all charts (Plotly)
    ↓ Generates HTML with embedded JavaScript
    ↓ Outputs: simple_daily_dashboard_interactive.html (118 MB)

Step 9: Validate Output (5 seconds)
    ↓ Checks file exists
    ↓ Checks file size > 100 KB
    ↓ Checks contains "FE App Dashboard" text

Step 10: Deploy to GitHub Pages (30 seconds)
    ↓ Pushes HTML to 'gh-pages' branch
    ↓ GitHub Pages detects change
    ↓ Updates live website

✅ DONE! Dashboard URL now shows fresh data!

Total time: ~5-10 minutes
```

---

## 🌐 Where It Runs

### GitHub's Cloud Infrastructure

**NOT on your laptop!**

- Runs on: GitHub's Ubuntu servers (Azure-backed)
- Location: Multiple data centers worldwide
- Cost: **FREE** for public repositories
- Reliability: 99.9% uptime

Every day, GitHub:
1. Spins up a fresh Ubuntu 20.04 server
2. Runs your workflow
3. Deploys the result
4. Shuts down the server

You don't pay for compute time - GitHub provides this free!

---

## 🔐 How It Accesses Your Database

### GitHub Secrets (Encrypted Storage)

Your Trino password is stored as a **GitHub Secret**:

1. You add it once: Settings → Secrets → `TRINO_PASSWORD`
2. GitHub encrypts it (AES-256)
3. Workflow reads it: `${{ secrets.TRINO_PASSWORD }}`
4. It's NEVER visible in logs or code
5. It's injected at runtime only

**In the workflow:**
```yaml
- name: Run production dashboard generation
  env:
    TRINO_PASSWORD: ${{ secrets.TRINO_PASSWORD }}
  run: python production_wrapper.py
```

Python reads it:
```python
TRINO_PASSWORD = os.environ.get('TRINO_PASSWORD')
```

---

## 📊 Live Dashboard Updates

### How Users See Fresh Data

1. **Dashboard hosted at:** `https://username.github.io/repo-name/`
2. **GitHub Pages serves:** Static HTML file
3. **When workflow completes:** New HTML pushed to `gh-pages` branch
4. **GitHub Pages detects change:** Auto-deploys in 2-3 minutes
5. **Users refresh browser:** See updated dashboard!

**Important:** No database queries when users view the dashboard - it's all pre-rendered HTML!

---

## 🎛️ Control Options

### 1. Change Schedule

Edit `.github/workflows/production-dashboard.yml`:

```yaml
schedule:
  - cron: '0 2 * * *'  # Current: 2 AM UTC daily
```

**Examples:**

```yaml
# Every 6 hours
- cron: '0 */6 * * *'

# Twice daily (2 AM and 2 PM UTC)
- cron: '0 2,14 * * *'

# Weekdays only at 8 AM UTC
- cron: '0 8 * * 1-5'

# Every hour during business hours (9 AM - 5 PM IST = 3:30 - 11:30 UTC)
- cron: '30 3-11 * * *'
```

### 2. Manual Trigger

Don't wait for scheduled run:

1. Go to: **Actions** tab on GitHub
2. Click: **"Production FE App Dashboard Update"**
3. Click: **"Run workflow"** → **"Run workflow"**
4. Dashboard updates in ~5-10 minutes

### 3. Pause Auto-Updates

**Temporarily disable:**
1. Go to: **.github/workflows/production-dashboard.yml**
2. Comment out the schedule:
```yaml
# schedule:
#   - cron: '0 2 * * *'
```
3. Commit and push

**Re-enable:** Uncomment and push

### 4. Monitor Runs

View execution history:
1. Go to: **Actions** tab
2. See all runs (success/failure)
3. Click any run to see detailed logs
4. Check execution time, errors, etc.

---

## 📧 Notifications (Optional)

### Get Alerts for Failures

Add to workflow (optional):

```yaml
- name: Send failure notification
  if: failure()
  uses: dawidd6/action-send-mail@v3
  with:
    server_address: smtp.gmail.com
    server_port: 465
    username: ${{ secrets.EMAIL_USERNAME }}
    password: ${{ secrets.EMAIL_PASSWORD }}
    subject: ❌ Dashboard Update Failed
    body: Check workflow logs for details
    to: your-email@example.com
    from: GitHub Actions
```

Or use Slack webhook, Teams, etc.

---

## 🔍 Monitoring Dashboard Health

### Built-in Health Monitor

Separate workflow runs **every 6 hours**: `.github/workflows/dashboard-monitor.yml`

Checks:
- ✅ Dashboard URL is accessible (HTTP 200)
- ✅ Content is valid (contains "FE App Dashboard")
- ✅ File size is reasonable (> 100KB)
- ✅ Data is fresh (updated within 30 hours)

If any check fails:
- Workflow fails
- Visible in Actions tab
- Can add notifications

---

## 💾 Data Persistence

### Where is Data Stored?

**During workflow run:**
- Data downloaded to: `/tmp/` on GitHub's server
- CSV files: `data/latest_hive_data.csv`, etc.
- Generated once, used to build HTML
- **Discarded after workflow completes**

**After deployment:**
- Only HTML file persists on `gh-pages` branch
- HTML embeds all data (that's why it's 118 MB)
- No separate database needed for users
- Users load HTML → See all data instantly

**Backups:**
- GitHub keeps git history of `gh-pages` branch
- Can rollback to any previous version
- Workflow creates local backups (in workflow artifacts if configured)

---

## 🚦 Workflow Status

### How to Check if Auto-Update is Working

**Every morning (after 7:30 AM IST):**

1. Go to: `https://github.com/YOUR_USERNAME/YOUR_REPO/actions`
2. See latest workflow run
3. Green checkmark ✅ = Success
4. Red X ❌ = Failed (check logs)

**On the dashboard:**
```
Generated: 2026-03-30 02:15:32
```
This timestamp shows when it was last updated.

---

## 🐛 Troubleshooting Auto-Updates

### Dashboard Not Updating?

**Check 1: Workflow Runs**
- Go to Actions tab
- Is it running daily?
- Any failures?

**Check 2: Workflow Logs**
- Click failed run
- Expand steps
- Look for errors

**Common Issues:**

| Issue | Cause | Fix |
|-------|-------|-----|
| "Authentication failed" | Trino password wrong | Update GitHub Secret |
| "Timeout" | Query taking too long | Increase timeout in workflow |
| "No updates in 30 hours" | Workflow disabled | Check cron schedule |
| "404 on dashboard" | GitHub Pages not enabled | Enable in Settings → Pages |

---

## 💰 Cost

### Completely Free!

**GitHub Actions:**
- 2,000 minutes/month FREE for private repos
- **UNLIMITED for public repos** ✅
- Your dashboard uses ~10 minutes/day = 300 min/month
- Well within free tier even for private repos

**GitHub Pages:**
- FREE for public repos ✅
- 1 GB storage limit (your HTML: 118 MB)
- 100 GB bandwidth/month
- Soft limit: 10 builds/hour

**Trino Database:**
- Your existing access (no extra cost)

**Total Cost:** $0/month 🎉

---

## 🎯 Production Best Practices

### Recommended Configuration

**Schedule:**
```yaml
- cron: '0 2 * * *'  # Daily at 2 AM UTC
```
✅ Runs during low-traffic hours
✅ Fresh data ready for India business hours (7:30 AM IST)

**Timeout:**
```yaml
timeout-minutes: 30
```
✅ Prevents runaway workflows
✅ Fails fast if something wrong

**Retry Logic:**
Built into `production_wrapper.py`:
- 3 attempts per step
- 60-second delay between retries
- Automatic rollback on failure

**Monitoring:**
- Health checks every 6 hours
- Validate output before deploy
- Keep logs for 90 days

---

## 📈 Scaling Considerations

### Current Setup Handles:
- 218k tickets/day ✅
- 80k agent records/day ✅
- 118 MB HTML output ✅
- Completes in 5-10 minutes ✅

### If Data Grows:
- GitHub Actions supports up to 6 hours/run
- Can split into multiple workflows
- Can cache data between runs
- Can optimize queries (add WHERE clauses)

**Current headroom:** 10x data growth easily supported

---

## 🎊 Summary

Your dashboard **automatically refreshes every day** because:

1. ✅ **GitHub Actions** runs workflow at 2 AM UTC
2. ✅ **production_wrapper.py** fetches fresh data from Trino
3. ✅ **Dashboard regenerated** with today's data
4. ✅ **Auto-deployed** to GitHub Pages
5. ✅ **URL updates** automatically

**Zero manual work needed!**

**You only need to:**
1. Deploy once (following PRODUCTION_DEPLOYMENT.md)
2. Add GitHub Secret (TRINO_PASSWORD)
3. Relax! It runs itself every day

---

## 🔗 Related Docs

- **PRODUCTION_DEPLOYMENT.md** - How to deploy initially
- **PRODUCTION_CHECKLIST.md** - Pre-deployment validation
- **DASHBOARD_SCRIPTS_GUIDE.md** - Understanding the scripts

---

**Questions?** Check the Actions tab logs or see troubleshooting section above!
