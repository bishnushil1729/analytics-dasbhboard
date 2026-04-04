#!/usr/bin/env python3
"""
Month-to-Date (MTD) Comparison Views
Shows current MTD vs last month's MTD with % change
"""

import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import os

# Configuration - use relative paths for GitHub Actions
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')

TICKET_DATA = os.path.join(DATA_DIR, "latest_hive_data.csv")
FUNNEL_DATA = os.path.join(DATA_DIR, "latest_funnel_transformed.csv")
OUTPUT_MTD_TICKETS = os.path.join(BASE_DIR, "mtd_tickets_comparison.csv")
OUTPUT_MTD_TASKS = os.path.join(BASE_DIR, "mtd_tasks_comparison.csv")
OUTPUT_MTD_FUNNEL = os.path.join(BASE_DIR, "mtd_funnel_comparison.csv")
OUTPUT_MTD_FLOW = os.path.join(BASE_DIR, "mtd_flow_comparison.csv")
OUTPUT_MTD_STATUS = os.path.join(BASE_DIR, "mtd_status_comparison.csv")

print("=" * 80)
print("MONTH-TO-DATE (MTD) COMPARISON VIEWS")
print("=" * 80)

# =============================================================================
# LOAD DATA
# =============================================================================
print("\n📂 Loading data...")

df_tickets = pd.read_csv(TICKET_DATA, low_memory=False)
df_tickets = df_tickets[df_tickets['ticket_consider_flag'] == 1].copy()
df_tickets['ticket_created_date'] = pd.to_datetime(df_tickets['ticket_created_date'])
print(f"✅ Loaded {len(df_tickets):,} valid tickets")

df_funnel = pd.read_csv(FUNNEL_DATA, low_memory=False)
df_funnel['dt'] = pd.to_datetime(df_funnel['dt'])
print(f"✅ Loaded {len(df_funnel):,} funnel records")

# =============================================================================
# DETERMINE MTD PERIODS
# =============================================================================
print("\n📅 Determining MTD periods...")

# Get latest date in data
latest_date = df_tickets['ticket_created_date'].max()
current_month_start = latest_date.replace(day=1)
current_day_of_month = latest_date.day

# Last month's same period
last_month_end = current_month_start - timedelta(days=1)
last_month_start = last_month_end.replace(day=1)
last_month_same_day = min(current_day_of_month, last_month_end.day)

# MTD date ranges
current_mtd_start = current_month_start
current_mtd_end = latest_date

last_mtd_start = last_month_start
last_mtd_end = last_month_start + timedelta(days=current_day_of_month - 1)

print(f"\n📊 Current MTD: {current_mtd_start.strftime('%Y-%m-%d')} to {current_mtd_end.strftime('%Y-%m-%d')} ({current_day_of_month} days)")
print(f"📊 Last MTD:    {last_mtd_start.strftime('%Y-%m-%d')} to {last_mtd_end.strftime('%Y-%m-%d')} ({current_day_of_month} days)")

# =============================================================================
# HELPER FUNCTION: Calculate % change
# =============================================================================
def calc_pct_change(current, previous):
    """Calculate percentage change"""
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return ((current - previous) / previous * 100)

# =============================================================================
# VIEW 1: MTD Tickets Comparison
# =============================================================================
print("\n📊 Creating View 1: MTD Tickets Comparison...")

# Current MTD
current_tickets = df_tickets[
    (df_tickets['ticket_created_date'] >= current_mtd_start) &
    (df_tickets['ticket_created_date'] <= current_mtd_end)
]

# Last MTD
last_tickets = df_tickets[
    (df_tickets['ticket_created_date'] >= last_mtd_start) &
    (df_tickets['ticket_created_date'] <= last_mtd_end)
]

mtd_tickets_comparison = pd.DataFrame({
    'metric': ['Total Tickets', 'Total Tasks', 'Closed Tickets', 'Problematic Tickets',
               'Open Tickets', 'Closure Rate (%)', 'Problematic Rate (%)'],
    'current_mtd': [
        len(current_tickets),
        current_tickets['task_id'].nunique(),
        current_tickets['flag_ticket_closed'].sum(),
        (current_tickets['ticket_status'] == 'PROBLEMATIC').sum(),
        (current_tickets['ticket_status'] == 'OPEN').sum(),
        (current_tickets['flag_ticket_closed'].sum() / len(current_tickets) * 100) if len(current_tickets) > 0 else 0,
        ((current_tickets['ticket_status'] == 'PROBLEMATIC').sum() / len(current_tickets) * 100) if len(current_tickets) > 0 else 0
    ],
    'last_mtd': [
        len(last_tickets),
        last_tickets['task_id'].nunique(),
        last_tickets['flag_ticket_closed'].sum(),
        (last_tickets['ticket_status'] == 'PROBLEMATIC').sum(),
        (last_tickets['ticket_status'] == 'OPEN').sum(),
        (last_tickets['flag_ticket_closed'].sum() / len(last_tickets) * 100) if len(last_tickets) > 0 else 0,
        ((last_tickets['ticket_status'] == 'PROBLEMATIC').sum() / len(last_tickets) * 100) if len(last_tickets) > 0 else 0
    ]
})

mtd_tickets_comparison['change'] = mtd_tickets_comparison['current_mtd'] - mtd_tickets_comparison['last_mtd']
mtd_tickets_comparison['pct_change'] = mtd_tickets_comparison.apply(
    lambda row: calc_pct_change(row['current_mtd'], row['last_mtd']), axis=1
).round(2)

mtd_tickets_comparison['current_mtd'] = mtd_tickets_comparison['current_mtd'].round(2)
mtd_tickets_comparison['last_mtd'] = mtd_tickets_comparison['last_mtd'].round(2)
mtd_tickets_comparison['change'] = mtd_tickets_comparison['change'].round(2)

mtd_tickets_comparison.to_csv(OUTPUT_MTD_TICKETS, index=False)
print(f"✅ MTD Tickets Comparison saved: {OUTPUT_MTD_TICKETS}")

# =============================================================================
# VIEW 2: MTD by Flow
# =============================================================================
print("\n📊 Creating View 2: MTD by Flow...")

current_flow = current_tickets.groupby('flow').size().to_dict()
last_flow = last_tickets.groupby('flow').size().to_dict()

flows = set(list(current_flow.keys()) + list(last_flow.keys()))

mtd_flow_data = []
for flow in flows:
    curr = current_flow.get(flow, 0)
    last = last_flow.get(flow, 0)
    change = curr - last
    pct = calc_pct_change(curr, last)
    mtd_flow_data.append({
        'flow': flow,
        'current_mtd': curr,
        'last_mtd': last,
        'change': change,
        'pct_change': round(pct, 2)
    })

mtd_flow_comparison = pd.DataFrame(mtd_flow_data)
mtd_flow_comparison = mtd_flow_comparison.sort_values('current_mtd', ascending=False)
mtd_flow_comparison.to_csv(OUTPUT_MTD_FLOW, index=False)
print(f"✅ MTD Flow Comparison saved: {OUTPUT_MTD_FLOW}")

# =============================================================================
# VIEW 3: MTD by Status
# =============================================================================
print("\n📊 Creating View 3: MTD by Status...")

current_status = current_tickets.groupby('ticket_status').size().to_dict()
last_status = last_tickets.groupby('ticket_status').size().to_dict()

statuses = set(list(current_status.keys()) + list(last_status.keys()))

mtd_status_data = []
for status in statuses:
    curr = current_status.get(status, 0)
    last = last_status.get(status, 0)
    change = curr - last
    pct = calc_pct_change(curr, last)
    mtd_status_data.append({
        'status': status,
        'current_mtd': curr,
        'last_mtd': last,
        'change': change,
        'pct_change': round(pct, 2)
    })

mtd_status_comparison = pd.DataFrame(mtd_status_data)
mtd_status_comparison = mtd_status_comparison.sort_values('current_mtd', ascending=False)
mtd_status_comparison.to_csv(OUTPUT_MTD_STATUS, index=False)
print(f"✅ MTD Status Comparison saved: {OUTPUT_MTD_STATUS}")

# =============================================================================
# VIEW 4: MTD Funnel Comparison
# =============================================================================
print("\n📊 Creating View 4: MTD Funnel Comparison...")

# Current MTD funnel
current_funnel = df_funnel[
    (df_funnel['dt'] >= current_mtd_start) &
    (df_funnel['dt'] <= current_mtd_end)
]

# Last MTD funnel
last_funnel = df_funnel[
    (df_funnel['dt'] >= last_mtd_start) &
    (df_funnel['dt'] <= last_mtd_end)
]

mtd_funnel_comparison = pd.DataFrame({
    'metric': ['Unique Agents', 'Total Logins', 'Total Attended', 'Total Attempted',
               'Total Closed', 'Attendance Rate (%)', 'Attempt Rate (%)',
               'Closure Rate (%)', 'Overall Conversion (%)'],
    'current_mtd': [
        current_funnel['agent_id'].nunique(),
        current_funnel['logged_in'].sum(),
        current_funnel['attended'].sum(),
        current_funnel['attempted'].sum(),
        current_funnel['closed'].sum(),
        (current_funnel['attended'].sum() / current_funnel['logged_in'].sum() * 100) if current_funnel['logged_in'].sum() > 0 else 0,
        (current_funnel['attempted'].sum() / current_funnel['attended'].sum() * 100) if current_funnel['attended'].sum() > 0 else 0,
        (current_funnel['closed'].sum() / current_funnel['attempted'].sum() * 100) if current_funnel['attempted'].sum() > 0 else 0,
        (current_funnel['closed'].sum() / current_funnel['logged_in'].sum() * 100) if current_funnel['logged_in'].sum() > 0 else 0
    ],
    'last_mtd': [
        last_funnel['agent_id'].nunique(),
        last_funnel['logged_in'].sum(),
        last_funnel['attended'].sum(),
        last_funnel['attempted'].sum(),
        last_funnel['closed'].sum(),
        (last_funnel['attended'].sum() / last_funnel['logged_in'].sum() * 100) if last_funnel['logged_in'].sum() > 0 else 0,
        (last_funnel['attempted'].sum() / last_funnel['attended'].sum() * 100) if last_funnel['attended'].sum() > 0 else 0,
        (last_funnel['closed'].sum() / last_funnel['attempted'].sum() * 100) if last_funnel['attempted'].sum() > 0 else 0,
        (last_funnel['closed'].sum() / last_funnel['logged_in'].sum() * 100) if last_funnel['logged_in'].sum() > 0 else 0
    ]
})

mtd_funnel_comparison['change'] = mtd_funnel_comparison['current_mtd'] - mtd_funnel_comparison['last_mtd']
mtd_funnel_comparison['pct_change'] = mtd_funnel_comparison.apply(
    lambda row: calc_pct_change(row['current_mtd'], row['last_mtd']), axis=1
).round(2)

mtd_funnel_comparison['current_mtd'] = mtd_funnel_comparison['current_mtd'].round(2)
mtd_funnel_comparison['last_mtd'] = mtd_funnel_comparison['last_mtd'].round(2)
mtd_funnel_comparison['change'] = mtd_funnel_comparison['change'].round(2)

mtd_funnel_comparison.to_csv(OUTPUT_MTD_FUNNEL, index=False)
print(f"✅ MTD Funnel Comparison saved: {OUTPUT_MTD_FUNNEL}")

# =============================================================================
# VIEW 5: MTD Tasks by Flow
# =============================================================================
print("\n📊 Creating View 5: MTD Tasks by Flow...")

current_tasks_flow = current_tickets.groupby('flow')['task_id'].nunique().to_dict()
last_tasks_flow = last_tickets.groupby('flow')['task_id'].nunique().to_dict()

mtd_tasks_data = []
for flow in flows:
    curr = current_tasks_flow.get(flow, 0)
    last = last_tasks_flow.get(flow, 0)
    change = curr - last
    pct = calc_pct_change(curr, last)
    mtd_tasks_data.append({
        'flow': flow,
        'current_mtd_tasks': curr,
        'last_mtd_tasks': last,
        'change': change,
        'pct_change': round(pct, 2)
    })

mtd_tasks_comparison = pd.DataFrame(mtd_tasks_data)
mtd_tasks_comparison = mtd_tasks_comparison.sort_values('current_mtd_tasks', ascending=False)
mtd_tasks_comparison.to_csv(OUTPUT_MTD_TASKS, index=False)
print(f"✅ MTD Tasks Comparison saved: {OUTPUT_MTD_TASKS}")

# =============================================================================
# PRINT SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("MTD COMPARISON SUMMARY")
print("=" * 80)

print(f"\n📅 Period: {current_month_start.strftime('%B %Y')} (Day {current_day_of_month})")
print(f"   Current MTD: {current_mtd_start.strftime('%Y-%m-%d')} to {current_mtd_end.strftime('%Y-%m-%d')}")
print(f"   Last MTD:    {last_mtd_start.strftime('%Y-%m-%d')} to {last_mtd_end.strftime('%Y-%m-%d')}")

print("\n📊 Tickets Overview:")
print(mtd_tickets_comparison.to_string(index=False))

print("\n📊 By Flow:")
print(mtd_flow_comparison.to_string(index=False))

print("\n📊 By Status:")
print(mtd_status_comparison.to_string(index=False))

print("\n📊 Funnel Metrics:")
print(mtd_funnel_comparison.to_string(index=False))

print("\n📊 Tasks by Flow:")
print(mtd_tasks_comparison.to_string(index=False))

# Key insights
print("\n" + "=" * 80)
print("KEY INSIGHTS")
print("=" * 80)

total_curr = mtd_tickets_comparison[mtd_tickets_comparison['metric'] == 'Total Tickets']['current_mtd'].values[0]
total_last = mtd_tickets_comparison[mtd_tickets_comparison['metric'] == 'Total Tickets']['last_mtd'].values[0]
total_pct = mtd_tickets_comparison[mtd_tickets_comparison['metric'] == 'Total Tickets']['pct_change'].values[0]

print(f"\n🎯 Overall Performance:")
print(f"   Current MTD Tickets: {total_curr:,.0f}")
print(f"   Last MTD Tickets: {total_last:,.0f}")
print(f"   Change: {total_pct:+.1f}% {'📈' if total_pct > 0 else '📉' if total_pct < 0 else '➡️'}")

# Flow with biggest change
if len(mtd_flow_comparison) > 0:
    biggest_flow_change = mtd_flow_comparison.iloc[0]
    print(f"\n📊 Biggest Flow:")
    print(f"   {biggest_flow_change['flow']}: {biggest_flow_change['current_mtd']:,.0f} tickets ({biggest_flow_change['pct_change']:+.1f}%)")

# Status with biggest change
if len(mtd_status_comparison) > 0:
    biggest_status_change = mtd_status_comparison.iloc[0]
    print(f"\n🚦 Dominant Status:")
    print(f"   {biggest_status_change['status']}: {biggest_status_change['current_mtd']:,.0f} tickets ({biggest_status_change['pct_change']:+.1f}%)")

print("\n" + "=" * 80)
print("✨ MTD COMPARISON VIEWS CREATED!")
print("=" * 80)
print(f"\n📁 Files created:")
print(f"  1. {OUTPUT_MTD_TICKETS}")
print(f"  2. {OUTPUT_MTD_TASKS}")
print(f"  3. {OUTPUT_MTD_FUNNEL}")
print(f"  4. {OUTPUT_MTD_FLOW}")
print(f"  5. {OUTPUT_MTD_STATUS}")
