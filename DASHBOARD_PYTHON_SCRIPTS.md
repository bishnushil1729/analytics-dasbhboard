# 🐍 FE App Dashboard - Python Scripts Guide

## 📁 Complete Script Collection

All scripts are located in: `/Users/duvvuri.praveen/`

---

## 🎯 Core Scripts (6 files)

### **1. Main Dashboard Generator** ⭐
**File:** `simple_daily_dashboard_interactive.py`  
**Lines:** 2,983  
**Purpose:** Generates the complete interactive HTML dashboard

**What it does:**
- Loads ticket and funnel data from CSV files
- Calculates KPIs for 6 time periods (MTD, Last Month, LMTD, Current Week, Last Week, Previous Day)
- Creates interactive Plotly charts with granularity buttons (Daily/Weekly/Monthly/Yearly)
- Generates agent performance tables (Top 20 performers/defaulters)
- Creates regional and hub analysis
- Outputs 118 MB HTML file with embedded JavaScript

**Run:**
```bash
python3 simple_daily_dashboard_interactive.py
```

**Output:**
```
simple_daily_dashboard_interactive.html
```

---

### **2. Fetch Ticket Data (Improved Version)** 🚀
**File:** `fetch_from_trino_improved.py`  
**Lines:** 157  
**Purpose:** Fetches ticket data from Trino with custom filters

**What it does:**
- Connects to Trino database
- Queries `hive.aggregate_pa.pos_ae_ticket_funnel_v1`
- Filters last 6 months of data (configurable)
- Filters by flow types (INSTALLATION, BREAKFIX, UPGRADE, DEINSTALLATION, MIGRATION)
- Applies quality filter (ticket_consider_flag = 1)
- **Performance:** 12 seconds, 117K rows, 40 MB file (vs old: 48s, 218K rows, 81 MB)

**Configuration:**
```python
MONTHS_TO_FETCH = 6  # Adjust date range
```

**Run:**
```bash
python3 fetch_from_trino_improved.py
```

**Output:**
```
data/latest_hive_data.csv
```

---

### **3. Fetch Agent Funnel Data**
**File:** `fetch_agent_funnel_from_trino.py`  
**Lines:** 157  
**Purpose:** Fetches agent-level funnel metrics with region mapping

**What it does:**
- Complex join of 4 tables:
  - `realtime_prod_agent_service.agents` (agent master)
  - `realtime_prod_agent_service.managers` (manager data with region)
  - `aggregate_pa.pos_ae_login_funnel` (funnel metrics)
  - Cross join with dates
- Maps agents to managers
- Calculates region from manager's state (North/South/East/West)
- Gets daily funnel flags: logged_in, attended, attempted, closed

**Run:**
```bash
python3 fetch_agent_funnel_from_trino.py
```

**Output:**
```
data/latest_agent_funnel_data.csv (~80,701 rows, 6.7 MB)
```

---

### **4. Transform Funnel Data**
**File:** `transform_funnel_data.py`  
**Lines:** 66  
**Purpose:** Transforms agent funnel data to dashboard format

**What it does:**
- Renames columns for consistency
- Maps: spl_code → agent_id
- Maps: logged_in_flag → logged_in
- Maps: attended_flag → attended
- Maps: attempted_flag → attempted
- Maps: closed_flag → closed

**Run:**
```bash
python3 transform_funnel_data.py
```

**Output:**
```
data/latest_funnel_transformed.csv
```

---

### **5. Create MTD Comparison Views**
**File:** `create_mtd_comparison_views.py`  
**Lines:** 330  
**Purpose:** Creates Month-to-Date comparison metrics

**What it does:**
- Current MTD: 2026-03-01 to 2026-03-29 (29 days)
- Last MTD: 2026-02-01 to 2026-03-01 (29 days)
- Calculates % change for all metrics
- Creates 5 CSV files:
  - `mtd_tickets_comparison.csv` - Overall ticket metrics
  - `mtd_tasks_comparison.csv` - Tasks by flow
  - `mtd_funnel_comparison.csv` - Funnel metrics
  - `mtd_flow_comparison.csv` - Tickets by flow
  - `mtd_status_comparison.csv` - Tickets by status

**Run:**
```bash
python3 create_mtd_comparison_views.py
```

**Output:**
```
data/mtd_*.csv (5 files)
```

---

### **6. Production Wrapper** 🔧
**File:** `production_wrapper.py`  
**Lines:** 274  
**Purpose:** Production-grade execution with error handling

**What it does:**
- Automatic backups before each run
- Retry logic (3 attempts, 60s delay)
- Output validation
- Rollback on failure
- Detailed logging to `production.log`
- JSON status reports

**Features:**
```python
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds
BACKUP_DIR = "backups"
```

**Run:**
```bash
python3 production_wrapper.py
```

**Executes all steps:**
1. Backup existing dashboard
2. Fetch ticket data (improved version)
3. Fetch agent funnel data
4. Transform funnel data
5. Create MTD comparison views
6. Generate dashboard
7. Validate output

---

## 📊 Data Flow

```
┌─────────────────────────────────────────────┐
│  1. fetch_from_trino_improved.py            │
│     ↓ Queries Trino (last 6 months)         │
│     ↓ Output: latest_hive_data.csv          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  2. fetch_agent_funnel_from_trino.py        │
│     ↓ Queries Trino (agent data)            │
│     ↓ Output: latest_agent_funnel_data.csv  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  3. transform_funnel_data.py                │
│     ↓ Transforms columns                    │
│     ↓ Output: latest_funnel_transformed.csv │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  4. create_mtd_comparison_views.py          │
│     ↓ Creates MTD comparisons               │
│     ↓ Output: mtd_*.csv (5 files)           │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  5. simple_daily_dashboard_interactive.py   │
│     ↓ Loads all data                        │
│     ↓ Creates charts and tables             │
│     ↓ Generates HTML with JavaScript        │
│     ↓ Output: dashboard.html (118 MB)       │
└─────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### **Option 1: Manual Run (Step by Step)**
```bash
cd /Users/duvvuri.praveen

# Step 1: Fetch ticket data
python3 fetch_from_trino_improved.py

# Step 2: Fetch agent funnel data
python3 fetch_agent_funnel_from_trino.py

# Step 3: Transform funnel data
python3 transform_funnel_data.py

# Step 4: Create MTD comparisons
python3 create_mtd_comparison_views.py

# Step 5: Generate dashboard
python3 simple_daily_dashboard_interactive.py

# Step 6: Open dashboard
open simple_daily_dashboard_interactive.html
```

### **Option 2: Production Run (All Steps Automated)**
```bash
cd /Users/duvvuri.praveen

# Run everything with error handling
python3 production_wrapper.py

# Output dashboard will be generated automatically
```

---

## 📦 Dependencies

**File:** `requirements.txt`
```
pandas>=1.5.0
plotly>=5.14.0
trino>=0.328.0
```

**Install:**
```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### **1. Change Date Range (fetch_from_trino_improved.py)**
```python
# Line 31
MONTHS_TO_FETCH = 6  # Change to 3, 12, etc.
```

### **2. Change Trino Connection (All fetch scripts)**
```python
TRINO_HOST = 'trino-dev-gateway-router-looker.de.razorpay.com'
TRINO_PORT = 443
TRINO_USER = 'duvvuri.praveen@razorpay.com'
TRINO_PASSWORD = os.environ.get('TRINO_PASSWORD')  # Set via environment variable
```

### **3. Change Default Granularity (simple_daily_dashboard_interactive.py)**
```python
# Line 192, 304, 411, 519, 642
visible = True if gran == 'week' else False  # Change 'week' to 'day' or 'month'
```

---

## 📁 File Locations

All files in: `/Users/duvvuri.praveen/`

```
/Users/duvvuri.praveen/
├── simple_daily_dashboard_interactive.py    (Main dashboard - 2,983 lines)
├── fetch_from_trino_improved.py             (Fetch tickets - 157 lines)
├── fetch_agent_funnel_from_trino.py         (Fetch agents - 157 lines)
├── transform_funnel_data.py                 (Transform - 66 lines)
├── create_mtd_comparison_views.py           (MTD calc - 330 lines)
├── production_wrapper.py                    (Production - 274 lines)
├── requirements.txt                         (Dependencies)
├── data/                                    (Generated data)
│   ├── latest_hive_data.csv                (40 MB, 117K rows)
│   ├── latest_agent_funnel_data.csv        (6.7 MB, 80K rows)
│   ├── latest_funnel_transformed.csv       
│   └── mtd_*.csv                           (5 files)
├── simple_daily_dashboard_interactive.html  (Output - 118 MB)
├── production.log                           (Execution logs)
├── production_status.json                   (Status report)
└── backups/                                 (Auto backups)
    └── dashboard_backup_*.html
```

---

## 🎨 Dashboard Features

Generated by `simple_daily_dashboard_interactive.py`:

### **1. KPI Summary Table**
- 6 time periods (Current Week, Last Week, MTD, Last Month, LMTD, Previous Day)
- 5 metrics (Adoption Rate, Tickets, Tasks, Closure Rate, Agents Attempted)

### **2. Interactive Charts (5 charts with granularity)**
- Ticket Count by Period
- Task Count by Period
- Adoption Rate by Period
- Number of Agents Attempted by Period
- Total Active Agents by Period

### **3. Flow Analysis**
- Tickets by Flow Type (Stacked)
- Tickets by Flow Type (% of Total) with date filter

### **4. MTD Comparison Tables (3 tables)**
- Overall Tickets MTD
- Tasks by Flow MTD
- Funnel Metrics MTD

### **5. Agent Performance**
- Top 20 Performers (by closure rate)
- Top 20 Defaulters (lowest closure rate)

### **6. Regional Views**
- Regional Executive Summary (4 regions)
- Hub Leaderboards (Top 10 / Bottom 10 by Closure Rate and Adoption Rate)

### **7. Status Views**
- Task Status × Ticket Status Pivot Table
- Ticket Status by Flow - Daily View (Last 60 Days, descending order)

---

## 📝 Key Code Sections

### **Main Dashboard (simple_daily_dashboard_interactive.py)**

```python
# Lines 1-80: Imports and configuration
# Lines 81-162: Metric calculations for all granularities
# Lines 192-509: Chart 1 - Ticket Count by Period
# Lines 304-425: Chart 2 - Task Count by Period
# Lines 411-509: Chart 3 - Adoption Rate by Period
# Lines 511-617: Chart 3B - Agents Attempted by Period
# Lines 619-717: Chart 3C - Total Active Agents by Period
# Lines 719-850: MTD comparison tables
# Lines 851-1000: Agent performance tables
# Lines 1001-1700: Regional and hub analysis
# Lines 1701-1823: Flow and status views
# Lines 2066-2140: KPI Summary calculation
# Lines 2141-3000: HTML template with embedded JavaScript
```

### **Adoption Rate Calculation (FIXED)**

```python
# Line 2117-2137
def calc_metrics(tickets_df, funnel_df):
    # Calculate unique agents who attempted
    agents_attempted = funnel_df[funnel_df['attempted'] == 1]['agent_id'].nunique()
    
    # Calculate total unique agents (matching chart logic)
    total_unique_agents = funnel_df['agent_id'].nunique()
    
    # Adoption rate: unique agents attempted / total unique agents
    adoption_rate = (agents_attempted / total_unique_agents * 100)
    
    return {
        'adoption_rate': round(adoption_rate, 2),
        'agents_attempted': agents_attempted,
        ...
    }
```

---

## 🔄 Daily Auto-Refresh (Production)

When deployed to GitHub Pages, these scripts run automatically:

**File:** `.github/workflows/production-dashboard.yml`

**Schedule:** Daily at 2:00 AM UTC (7:30 AM IST)

**Triggers:**
1. **Automatic:** Cron schedule `'0 2 * * *'`
2. **Manual:** GitHub Actions UI ("Run workflow")
3. **On Push:** Commits to main branch

**Execution:**
```yaml
- name: Run production dashboard generation
  env:
    TRINO_PASSWORD: ${{ secrets.TRINO_PASSWORD }}
  run: python production_wrapper.py
```

---

## 💡 Tips

1. **Always use production_wrapper.py** for reliable execution
2. **Check production.log** for detailed execution logs
3. **Backups are automatic** - stored in `backups/` directory
4. **HTML file is large** (118 MB) - normal for embedded data
5. **Scripts use relative paths** - work in GitHub Actions
6. **Weekly granularity is default** - faster and clearer overview

---

## 🆘 Troubleshooting

### **Issue: Trino connection fails**
```bash
# Check password
echo $TRINO_PASSWORD

# Test connection
python3 fetch_from_trino_improved.py
```

### **Issue: Missing data files**
```bash
# Ensure data directory exists
mkdir -p data

# Run fetch scripts first
python3 fetch_from_trino_improved.py
python3 fetch_agent_funnel_from_trino.py
```

### **Issue: Dashboard generation fails**
```bash
# Check logs
cat production.log

# Check status
cat production_status.json

# Run step by step to identify issue
```

---

## 📊 Performance Metrics

| Script | Runtime | Output Size | Rows |
|--------|---------|-------------|------|
| fetch_from_trino_improved.py | ~12s | 40 MB | 117,121 |
| fetch_agent_funnel_from_trino.py | ~7s | 6.7 MB | 80,701 |
| transform_funnel_data.py | ~2s | 6.7 MB | 80,701 |
| create_mtd_comparison_views.py | ~3s | <1 MB | 5 files |
| simple_daily_dashboard_interactive.py | ~6s | 118 MB | HTML |
| **Total (production_wrapper.py)** | **~31s** | **118 MB** | **Full dashboard** |

---

## 🎯 Next Steps

1. **Test Locally:**
   ```bash
   python3 production_wrapper.py
   open simple_daily_dashboard_interactive.html
   ```

2. **Deploy to Production:**
   ```bash
   ./deploy_to_production.sh
   ```

3. **Set up GitHub Secret:**
   - Add `TRINO_PASSWORD` in GitHub Settings → Secrets

4. **Monitor:**
   - Check GitHub Actions tab for daily runs
   - View dashboard at `https://USERNAME.github.io/REPO_NAME/`

---

**Last Updated:** 2026-03-30  
**Total Scripts:** 6 core scripts  
**Total Lines:** 3,967 lines of Python  
**Status:** ✅ Production Ready
