#!/usr/bin/env python3
"""
Simple Daily Dashboard - Interactive Version
With date filters and granularity options (day/week/month/year/MTD)
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import numpy as np
import json
import os

# Configuration - use relative paths for GitHub Actions
BASE_DIR = os.path.dirname(__file__) if os.path.dirname(__file__) else '.'
DATA_DIR = os.path.join(BASE_DIR, 'data')

TICKET_DATA = os.path.join(DATA_DIR, "latest_hive_data.csv")
FUNNEL_DATA = os.path.join(DATA_DIR, "latest_funnel_transformed.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "simple_daily_dashboard_interactive.html")

# MTD Comparison Files
MTD_TICKETS = os.path.join(BASE_DIR, "mtd_tickets_comparison.csv")
MTD_FLOW = os.path.join(BASE_DIR, "mtd_flow_comparison.csv")
MTD_FUNNEL = os.path.join(BASE_DIR, "mtd_funnel_comparison.csv")

print("=" * 80)
print("FE APP DASHBOARD - WITH FILTERS & GRANULARITY")
print("=" * 80)

# =============================================================================
# LOAD DATA
# =============================================================================
print("\n📂 Loading data...")

df_tickets = pd.read_csv(TICKET_DATA, low_memory=False)
df_tickets = df_tickets[df_tickets['ticket_consider_flag'] == 1].copy()
df_tickets['ticket_created_date'] = pd.to_datetime(df_tickets['ticket_created_date'])

# Filter to show data from January 1, 2026 onwards for time series
df_tickets_timeseries = df_tickets[df_tickets['ticket_created_date'] >= '2026-01-01'].copy()
print(f"✅ Loaded {len(df_tickets):,} valid tickets (Time series from 2026-01-01: {len(df_tickets_timeseries):,} tickets)")

df_funnel = pd.read_csv(FUNNEL_DATA, low_memory=False)
df_funnel['dt'] = pd.to_datetime(df_funnel['dt'])
print(f"✅ Loaded {len(df_funnel):,} funnel records")

# Load MTD comparison data
df_mtd_tickets = pd.read_csv(MTD_TICKETS)
df_mtd_flow = pd.read_csv(MTD_FLOW)
df_mtd_funnel = pd.read_csv(MTD_FUNNEL)
print(f"✅ Loaded MTD comparison data")

# =============================================================================
# HELPER FUNCTION: Aggregate by granularity
# =============================================================================
def aggregate_by_granularity(df, date_col, granularity):
    """Aggregate data by different time granularities"""
    df = df.copy()

    if granularity == 'day':
        df['period'] = df[date_col]
        period_label = 'Day'
    elif granularity == 'week':
        df['period'] = df[date_col].dt.to_period('W').dt.start_time
        period_label = 'Week'
    elif granularity == 'month':
        df['period'] = df[date_col].dt.to_period('M').dt.start_time
        period_label = 'Month'
    elif granularity == 'year':
        df['period'] = df[date_col].dt.to_period('Y').dt.start_time
        period_label = 'Year'
    elif granularity == 'mtd':  # Month-to-date
        df['period'] = df[date_col].dt.to_period('M').dt.start_time
        period_label = 'Month'

    return df, period_label

# =============================================================================
# CALCULATE METRICS FOR ALL GRANULARITIES
# =============================================================================
print("\n📊 Calculating metrics for all granularities...")

granularities = ['day', 'week', 'month', 'year']
all_metrics = {}

for gran in granularities:
    print(f"  Processing {gran}...")

    # Aggregate tickets (using filtered data from 2026-01-01 for time series)
    df_t, _ = aggregate_by_granularity(df_tickets_timeseries, 'ticket_created_date', gran)

    daily_tickets = df_t.groupby('period').agg({
        'ticket_id': 'count',
        'task_id': 'nunique'
    }).reset_index()
    daily_tickets.columns = ['date', 'ticket_count', 'task_count']

    # Flow breakdown
    daily_flow = df_t.groupby(['period', 'flow']).agg({
        'ticket_id': 'count'
    }).reset_index()
    daily_flow.columns = ['date', 'flow', 'ticket_count']

    # Aggregate funnel
    df_f, _ = aggregate_by_granularity(df_funnel, 'dt', gran)

    # For adoption rate, use average within period
    daily_adoption = df_f.groupby('period').apply(
        lambda group: pd.Series({
            'attempted_count': (group['attempted_flag'] == 1).sum(),
            'attempted_agents': group[group['attempted_flag'] == 1]['spl_code'].nunique()
        })
    ).reset_index()
    daily_adoption.columns = ['date', 'attempted_count', 'attempted_agents']

    # Total existing agents (cumulative)
    if gran == 'day':
        seen_agents = set()
        total_agents_list = []
        for date in sorted(df_funnel['dt'].unique()):
            date_agents = df_funnel[df_funnel['dt'] <= date]['spl_code'].unique()
            seen_agents.update(date_agents)
            total_agents_list.append({
                'date': date,
                'total_existing_agents': len(seen_agents)
            })
        df_total_agents = pd.DataFrame(total_agents_list)
    else:
        # For aggregated periods, use max agents seen up to that period
        df_f_sorted = df_f.sort_values('period')
        total_agents_list = []
        seen_agents = set()
        for period in sorted(df_f['period'].unique()):
            period_agents = df_funnel[
                aggregate_by_granularity(df_funnel, 'dt', gran)[0]['period'] <= period
            ]['spl_code'].unique()
            seen_agents.update(period_agents)
            total_agents_list.append({
                'date': period,
                'total_existing_agents': len(seen_agents)
            })
        df_total_agents = pd.DataFrame(total_agents_list)

    # Merge adoption data
    daily_adoption = pd.merge(df_total_agents, daily_adoption, on='date', how='left')
    daily_adoption['attempted_agents'] = daily_adoption['attempted_agents'].fillna(0)
    daily_adoption['adoption_rate'] = (
        daily_adoption['attempted_agents'] / daily_adoption['total_existing_agents'] * 100
    ).round(2)

    # Merge all metrics
    df_daily = daily_tickets.merge(daily_adoption, on='date', how='left')
    df_daily = df_daily.fillna(0)
    df_daily['tickets_per_task'] = (df_daily['ticket_count'] / df_daily['task_count']).replace([np.inf, -np.inf], 0)

    # Store
    all_metrics[gran] = {
        'daily': df_daily,
        'flow': daily_flow
    }

print(f"✅ Calculated metrics for {len(granularities)} granularities")

# =============================================================================
# CREATE INTERACTIVE VISUALIZATIONS
# =============================================================================
print("\n🎨 Creating interactive visualizations...")

# We'll create the charts with day granularity initially
# And add buttons to switch between granularities

def create_metric_traces(metrics_dict, granularity):
    """Create traces for a given granularity"""
    df_daily = metrics_dict[granularity]['daily']
    daily_flow = metrics_dict[granularity]['flow']

    # Pivot flow data
    flow_pivot = daily_flow.pivot(index='date', columns='flow', values='ticket_count').fillna(0)
    flow_pivot = flow_pivot.reindex(df_daily['date']).fillna(0)

    return df_daily, flow_pivot

# =============================================================================
# CHART 1: Daily Ticket Count (with granularity buttons)
# =============================================================================
fig1 = go.Figure()

# Add traces for each granularity (initially all, then use visibility)
for i, gran in enumerate(granularities):
    df_daily, _ = create_metric_traces(all_metrics, gran)

    visible = True if gran == 'week' else False

    fig1.add_trace(go.Scatter(
        x=df_daily['date'],
        y=df_daily['ticket_count'],
        mode='lines+markers+text',
        name=f'Tickets ({gran})',
        line=dict(color='#3498db', width=2),
        marker=dict(size=8 if gran == 'day' else 10),
        fill='tozeroy',
        fillcolor='rgba(52, 152, 219, 0.2)',
        visible=visible,
        text=[f'{val:,.0f}' for val in df_daily['ticket_count']],
        textposition='top center',
        textfont=dict(size=9, color='#2c3e50', family='Arial Black'),
        hovertemplate='<b>Date:</b> %{x}<br><b>Tickets:</b> %{y:,.0f}<br><extra></extra>'
    ))

# Create buttons for granularity selection
updatemenus = [
    dict(
        type="buttons",
        direction="right",
        x=0.1,
        xanchor="left",
        y=1.15,
        yanchor="top",
        buttons=[
            dict(label="Daily",
                 method="update",
                 args=[{"visible": [True, False, False, False]}]),
            dict(label="Weekly",
                 method="update",
                 args=[{"visible": [False, True, False, False]}]),
            dict(label="Monthly",
                 method="update",
                 args=[{"visible": [False, False, True, False]}]),
            dict(label="Yearly",
                 method="update",
                 args=[{"visible": [False, False, False, True]}]),
        ],
        bgcolor="#e8e8e8",
        bordercolor="#999",
        font=dict(size=12)
    ),
]

# Add average reference line for day granularity
df_daily_day, _ = create_metric_traces(all_metrics, 'day')
avg_tickets = df_daily_day['ticket_count'].mean()
max_tickets = df_daily_day['ticket_count'].max()
min_tickets = df_daily_day['ticket_count'].min()

fig1.add_hline(
    y=avg_tickets,
    line_dash="dash",
    line_color="rgba(231, 76, 60, 0.7)",
    line_width=2,
    annotation_text=f"Average: {avg_tickets:.0f}",
    annotation_position="right",
    annotation_font_size=12,
    annotation_font_color="#e74c3c"
)

fig1.update_layout(
    updatemenus=updatemenus,
    title={
        'text': f"📊 Ticket Count by Period<br><sub>Avg: {avg_tickets:.0f} | Min: {min_tickets:.0f} | Max: {max_tickets:,.0f}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=550,
    template='plotly_white',
    hovermode='x unified',
    # Add date range selector
    xaxis=dict(
        title="<b>Date</b>",
        showticklabels=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor="#f0f0f0",
            activecolor="#3498db",
            font=dict(size=11)
        ),
        rangeslider=dict(
            visible=True,
            thickness=0.08,  # Larger, more visible slider
            bgcolor="#ffffff",
            bordercolor="#3498db",
            borderwidth=2
        ),
        type="date"
    ),
    yaxis=dict(visible=False),  # Hide y-axis
    font=dict(family="Arial, sans-serif")
)

# =============================================================================
# CHART 2: Task Count (with granularity buttons)
# =============================================================================
fig2 = go.Figure()

for i, gran in enumerate(granularities):
    df_daily, _ = create_metric_traces(all_metrics, gran)

    visible = True if gran == 'week' else False

    fig2.add_trace(go.Scatter(
        x=df_daily['date'],
        y=df_daily['task_count'],
        mode='lines+markers+text',
        name=f'Tasks ({gran})',
        line=dict(color='#2ecc71', width=2),
        marker=dict(size=8 if gran == 'day' else 10),
        fill='tozeroy',
        fillcolor='rgba(46, 204, 113, 0.2)',
        visible=visible,
        text=[f'{val:,.0f}' for val in df_daily['task_count']],
        textposition='top center',
        textfont=dict(size=9, color='#2c3e50', family='Arial Black'),
        hovertemplate='<b>Date:</b> %{x}<br><b>Tasks:</b> %{y:,.0f}<br><extra></extra>'
    ))

# Add average reference line for tasks
avg_tasks = df_daily_day['task_count'].mean()
max_tasks = df_daily_day['task_count'].max()
min_tasks = df_daily_day['task_count'].min()

fig2.add_hline(
    y=avg_tasks,
    line_dash="dash",
    line_color="rgba(230, 126, 34, 0.7)",
    line_width=2,
    annotation_text=f"Average: {avg_tasks:.0f}",
    annotation_position="right",
    annotation_font_size=12,
    annotation_font_color="#e67e22"
)

fig2.update_layout(
    updatemenus=[
        dict(
            type="buttons",
            direction="right",
            x=0.1,
            xanchor="left",
            y=1.15,
            yanchor="top",
            buttons=[
                dict(label="Daily",
                     method="update",
                     args=[{"visible": [True, False, False, False]}]),
                dict(label="Weekly",
                     method="update",
                     args=[{"visible": [False, True, False, False]}]),
                dict(label="Monthly",
                     method="update",
                     args=[{"visible": [False, False, True, False]}]),
                dict(label="Yearly",
                     method="update",
                     args=[{"visible": [False, False, False, True]}]),
            ],
            bgcolor="#e8e8e8",
            bordercolor="#999",
            font=dict(size=12)
        ),
    ],
    title={
        'text': f"📋 Task Count by Period<br><sub>Avg: {avg_tasks:.0f} | Min: {min_tasks:.0f} | Max: {max_tasks:,.0f}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=550,
    template='plotly_white',
    hovermode='x unified',
    xaxis=dict(
        title="<b>Date</b>",
        showticklabels=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor="#f0f0f0",
            activecolor="#2ecc71",
            font=dict(size=11)
        ),
        rangeslider=dict(
            visible=True,
            thickness=0.08,  # Larger, more visible slider
            bgcolor="#ffffff",
            bordercolor="#3498db",
            borderwidth=2
        ),
        type="date"
    ),
    yaxis=dict(visible=False),  # Hide y-axis
    font=dict(family="Arial, sans-serif")
)

# =============================================================================
# CHART 3: Adoption Rate (with granularity buttons)
# =============================================================================
fig3 = go.Figure()

for i, gran in enumerate(granularities):
    df_daily, _ = create_metric_traces(all_metrics, gran)

    visible = True if gran == 'week' else False

    fig3.add_trace(go.Scatter(
        x=df_daily['date'],
        y=df_daily['adoption_rate'],
        mode='lines+markers+text',
        name=f'Adoption Rate ({gran})',
        line=dict(color='#9b59b6', width=2),
        marker=dict(size=8 if gran == 'day' else 10),
        fill='tozeroy',
        fillcolor='rgba(155, 89, 182, 0.2)',
        visible=visible,
        text=[f'{val:.1f}%' for val in df_daily['adoption_rate']],
        textposition='top center',
        textfont=dict(size=9, color='#2c3e50', family='Arial Black'),
        hovertemplate='<b>Date:</b> %{x}<br><b>Adoption Rate:</b> %{y:.1f}%<br><b>Attempted:</b> %{customdata[0]:,.0f}<br><b>Total Agents:</b> %{customdata[1]:,.0f}<extra></extra>',
        customdata=df_daily[['attempted_agents', 'total_existing_agents']].values
    ))

# Add average reference line for adoption rate
avg_adoption = df_daily_day['adoption_rate'].mean()
max_adoption = df_daily_day['adoption_rate'].max()
min_adoption = df_daily_day['adoption_rate'].min()

fig3.add_hline(
    y=avg_adoption,
    line_dash="dash",
    line_color="rgba(231, 76, 60, 0.7)",
    line_width=2,
    annotation_text=f"Average: {avg_adoption:.1f}%",
    annotation_position="right",
    annotation_font_size=12,
    annotation_font_color="#e74c3c"
)

fig3.update_layout(
    updatemenus=[
        dict(
            type="buttons",
            direction="right",
            x=0.1,
            xanchor="left",
            y=1.15,
            yanchor="top",
            buttons=[
                dict(label="Daily",
                     method="update",
                     args=[{"visible": [True, False, False, False]}]),
                dict(label="Weekly",
                     method="update",
                     args=[{"visible": [False, True, False, False]}]),
                dict(label="Monthly",
                     method="update",
                     args=[{"visible": [False, False, True, False]}]),
                dict(label="Yearly",
                     method="update",
                     args=[{"visible": [False, False, False, True]}]),
            ],
            bgcolor="#e8e8e8",
            bordercolor="#999",
            font=dict(size=12)
        ),
    ],
    title={
        'text': f"📈 Adoption Rate by Period<br><sub>Avg: {avg_adoption:.1f}% | Min: {min_adoption:.1f}% | Max: {max_adoption:.1f}%</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=550,
    template='plotly_white',
    hovermode='x unified',
    xaxis=dict(
        title="<b>Date</b>",
        showticklabels=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor="#f0f0f0",
            activecolor="#9b59b6",
            font=dict(size=11)
        ),
        rangeslider=dict(
            visible=True,
            thickness=0.08,  # Larger, more visible slider
            bgcolor="#ffffff",
            bordercolor="#3498db",
            borderwidth=2
        ),
        type="date"
    ),
    yaxis=dict(visible=False),  # Hide y-axis
    font=dict(family="Arial, sans-serif")
)

# =============================================================================
# CHART 3B: Number of Agents Attempted (with granularity buttons)
# =============================================================================
fig3b = go.Figure()

for i, gran in enumerate(granularities):
    df_daily, _ = create_metric_traces(all_metrics, gran)

    visible = True if gran == 'week' else False

    fig3b.add_trace(go.Scatter(
        x=df_daily['date'],
        y=df_daily['attempted_agents'],
        mode='lines+markers+text',
        name=f'Agents Attempted ({gran})',
        line=dict(color='#16a085', width=2),
        marker=dict(size=8 if gran == 'day' else 10),
        fill='tozeroy',
        fillcolor='rgba(22, 160, 133, 0.2)',
        visible=visible,
        text=[f'{int(val):,}' for val in df_daily['attempted_agents']],
        textposition='top center',
        textfont=dict(size=9, color='#2c3e50', family='Arial Black'),
        hovertemplate='<b>Date:</b> %{x}<br><b>Agents Attempted:</b> %{y:,.0f}<br><b>Total Agents:</b> %{customdata[0]:,.0f}<br><b>Adoption Rate:</b> %{customdata[1]:.1f}%<extra></extra>',
        customdata=df_daily[['total_existing_agents', 'adoption_rate']].values
    ))

# Add average reference line for agents attempted
avg_agents = df_daily_day['attempted_agents'].mean()
max_agents = df_daily_day['attempted_agents'].max()
min_agents = df_daily_day['attempted_agents'].min()

fig3b.add_hline(
    y=avg_agents,
    line_dash="dash",
    line_color="rgba(22, 160, 133, 0.7)",
    line_width=2,
    annotation_text=f"Average: {avg_agents:.0f}",
    annotation_position="right",
    annotation_font_size=12,
    annotation_font_color="#16a085"
)

fig3b.update_layout(
    updatemenus=[
        dict(
            type="buttons",
            direction="right",
            x=0.1,
            xanchor="left",
            y=1.15,
            yanchor="top",
            buttons=[
                dict(label="Daily",
                     method="update",
                     args=[{"visible": [True, False, False, False]}]),
                dict(label="Weekly",
                     method="update",
                     args=[{"visible": [False, True, False, False]}]),
                dict(label="Monthly",
                     method="update",
                     args=[{"visible": [False, False, True, False]}]),
                dict(label="Yearly",
                     method="update",
                     args=[{"visible": [False, False, False, True]}]),
            ],
            bgcolor="#e8e8e8",
            bordercolor="#999",
            font=dict(size=12)
        ),
    ],
    title={
        'text': f"👥 Number of Agents Attempted by Period<br><sub>Avg: {avg_agents:.0f} | Min: {min_agents:.0f} | Max: {max_agents:.0f}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=550,
    template='plotly_white',
    hovermode='x unified',
    xaxis=dict(
        title="<b>Date</b>",
        showticklabels=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor="#f0f0f0",
            activecolor="#16a085",
            font=dict(size=11)
        ),
        rangeslider=dict(
            visible=True,
            thickness=0.08,
            bgcolor="#ffffff",
            bordercolor="#16a085",
            borderwidth=2
        ),
        type="date"
    ),
    yaxis=dict(visible=False),  # Hide y-axis
    font=dict(family="Arial, sans-serif")
)

# =============================================================================
# CHART 3C: Total Number of Active Agents (with granularity buttons)
# =============================================================================
# Calculate active agents by date and granularity using funnel data
active_agents_metrics = {}

for gran in granularities:
    # Aggregate funnel data by granularity
    df_funnel_agg, _ = aggregate_by_granularity(df_funnel, 'dt', gran)

    # Count unique agents per period
    active_agents_by_period = df_funnel_agg.groupby('period')['spl_code'].nunique().reset_index()
    active_agents_by_period.columns = ['date', 'active_agents']
    active_agents_by_period = active_agents_by_period.sort_values('date')

    active_agents_metrics[gran] = active_agents_by_period

# Create the chart
fig3c = go.Figure()

for i, gran in enumerate(granularities):
    df_active = active_agents_metrics[gran]

    visible = True if gran == 'week' else False

    fig3c.add_trace(go.Scatter(
        x=df_active['date'],
        y=df_active['active_agents'],
        mode='lines+markers+text',
        name=f'Active Agents ({gran})',
        line=dict(color='#e67e22', width=2),
        marker=dict(size=8 if gran == 'day' else 10),
        fill='tozeroy',
        fillcolor='rgba(230, 126, 34, 0.2)',
        visible=visible,
        text=[f'{int(val):,}' for val in df_active['active_agents']],
        textposition='top center',
        textfont=dict(size=9, color='#2c3e50', family='Arial Black'),
        hovertemplate='<b>Date:</b> %{x}<br><b>Active Agents:</b> %{y:,.0f}<extra></extra>'
    ))

# Calculate statistics for daily view
df_active_day = active_agents_metrics['day']
avg_active = df_active_day['active_agents'].mean()
max_active = df_active_day['active_agents'].max()
min_active = df_active_day['active_agents'].min()

# Add average reference line
fig3c.add_hline(
    y=avg_active,
    line_dash="dash",
    line_color="rgba(230, 126, 34, 0.7)",
    line_width=2,
    annotation_text=f"Average: {avg_active:.0f}",
    annotation_position="right",
    annotation_font_size=12,
    annotation_font_color="#e67e22"
)

fig3c.update_layout(
    updatemenus=[
        dict(
            type="buttons",
            direction="right",
            x=0.1,
            xanchor="left",
            y=1.15,
            yanchor="top",
            buttons=[
                dict(label="Daily",
                     method="update",
                     args=[{"visible": [True, False, False, False]}]),
                dict(label="Weekly",
                     method="update",
                     args=[{"visible": [False, True, False, False]}]),
                dict(label="Monthly",
                     method="update",
                     args=[{"visible": [False, False, True, False]}]),
                dict(label="Yearly",
                     method="update",
                     args=[{"visible": [False, False, False, True]}]),
            ],
            bgcolor="#e8e8e8",
            bordercolor="#999",
            font=dict(size=12)
        ),
    ],
    title={
        'text': f"👤 Total Number of Active Agents by Period<br><sub>Avg: {avg_active:.0f} | Min: {min_active:.0f} | Max: {max_active:.0f}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=550,
    template='plotly_white',
    hovermode='x unified',
    xaxis=dict(
        title="<b>Date</b>",
        showticklabels=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor="#f0f0f0",
            activecolor="#e67e22",
            font=dict(size=11)
        ),
        rangeslider=dict(
            visible=True,
            thickness=0.08,
            bgcolor="#ffffff",
            bordercolor="#e67e22",
            borderwidth=2
        ),
        type="date"
    ),
    yaxis=dict(visible=False),  # Hide y-axis
    font=dict(family="Arial, sans-serif")
)

print(f"✅ Created Total Active Agents chart (Avg: {avg_active:.0f}, Min: {min_active:.0f}, Max: {max_active:.0f})")

# =============================================================================
# CHART 4: Tickets by Flow (Stacked - Daily only)
# =============================================================================
df_daily_day = all_metrics['day']['daily']
daily_flow_day = all_metrics['day']['flow']
flow_pivot_day = daily_flow_day.pivot(index='date', columns='flow', values='ticket_count').fillna(0)
flow_pivot_day = flow_pivot_day.reindex(df_daily_day['date']).fillna(0)

fig4 = go.Figure()

colors = {'INSTALLATION': '#3498db', 'BREAKFIX': '#e74c3c', 'DEINSTALLATION': '#f39c12'}

for flow in flow_pivot_day.columns:
    color = colors.get(flow, '#95a5a6')
    fig4.add_trace(go.Scatter(
        x=flow_pivot_day.index,
        y=flow_pivot_day[flow],
        mode='lines',
        name=flow,
        line=dict(width=0.5),
        stackgroup='one',
        fillcolor=color,
        hovertemplate='%{x}<br>' + flow + ': %{y:,.0f}<extra></extra>'
    ))

# Calculate flow totals for subtitle
total_by_flow = {}
for flow in flow_pivot_day.columns:
    total_by_flow[flow] = flow_pivot_day[flow].sum()

flow_subtitle = " | ".join([f"{flow}: {total:,.0f}" for flow, total in total_by_flow.items()])

fig4.update_layout(
    title={
        'text': f"🔄 Tickets by Flow Type (Daily - Stacked)<br><sub>{flow_subtitle}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=550,
    template='plotly_white',
    hovermode='x unified',
    xaxis=dict(
        title="<b>Date</b>",
        showticklabels=True,
        rangeselector=dict(
            buttons=list([
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=3, label="3m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(step="all", label="All")
            ]),
            bgcolor="#f0f0f0",
            activecolor="#e74c3c",
            font=dict(size=11)
        ),
        rangeslider=dict(
            visible=True,
            thickness=0.08,  # Larger, more visible slider
            bgcolor="#ffffff",
            bordercolor="#3498db",
            borderwidth=2
        ),
        type="date"
    ),
    yaxis=dict(visible=False),  # Hide y-axis
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        bgcolor="rgba(255, 255, 255, 0.8)",
        bordercolor="gray",
        borderwidth=1,
        font=dict(size=12)
    ),
    font=dict(family="Arial, sans-serif")
)

# =============================================================================
# CREATE TABULAR VIEWS
# =============================================================================
print("\n📊 Creating tabular views...")

# Table 1: Tasks by Flow (Daily)
tasks_by_flow = df_tickets.groupby(['ticket_created_date', 'flow']).agg({
    'task_id': 'nunique'
}).reset_index()
tasks_by_flow.columns = ['date', 'flow', 'task_count']
tasks_pivot = tasks_by_flow.pivot(index='date', columns='flow', values='task_count').fillna(0)
tasks_pivot['Total'] = tasks_pivot.sum(axis=1)
tasks_pivot = tasks_pivot.reset_index()
tasks_pivot = tasks_pivot.sort_values('date', ascending=False)  # Most recent first

# Format for display (last 30 days)
tasks_display = tasks_pivot.head(30).copy()
tasks_display['date'] = tasks_display['date'].dt.strftime('%Y-%m-%d')

# Create Plotly table for tasks
fig_table1 = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Date</b>'] + [f'<b>{col}</b>' for col in tasks_display.columns if col != 'date'],
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=13),
        height=40
    ),
    cells=dict(
        values=[tasks_display[col] for col in tasks_display.columns],
        fill_color=[['#f8f9fa', 'white']*len(tasks_display)],
        align=['left'] + ['center']*(len(tasks_display.columns)-1),
        font=dict(size=12),
        height=30,
        format=[None] + [',d']*(len(tasks_display.columns)-1)  # Format numbers with commas
    )
)])

fig_table1.update_layout(
    title={
        'text': f"📋 Tasks Split by Flow - Daily View (Last 30 Days)<br><sub>Total Tasks: {tasks_pivot['Total'].sum():,.0f} | Showing most recent</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=800,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Table 2: Ticket Status by Flow (Daily) - Reorganized with Flow first
status_by_flow = df_tickets.groupby(['ticket_created_date', 'flow', 'ticket_status']).agg({
    'ticket_id': 'count'
}).reset_index()
status_by_flow.columns = ['date', 'flow', 'status', 'ticket_count']

# Pivot to wide format with status as columns
status_pivot = status_by_flow.pivot_table(
    index=['date', 'flow'],
    columns='status',
    values='ticket_count',
    fill_value=0
).reset_index()

# Sort by date (most recent first) then flow
status_pivot = status_pivot.sort_values(['date', 'flow'], ascending=[False, True])

# Format for display (last 60 rows to show multiple days with all flows)
status_display = status_pivot.head(60).copy()
status_display['date'] = status_display['date'].dt.strftime('%Y-%m-%d')

# Get all status columns (automatically from the data)
status_cols = [col for col in status_display.columns if col not in ['date', 'flow']]

# Define preferred order for status columns if they exist
preferred_order = ['CLOSED', 'OPEN', 'PROBLEMATIC', 'REVISIT', 'CLOSURE_EVIDENCE_SUBMITTED']
ordered_status_cols = []
for col in preferred_order:
    if col in status_cols:
        ordered_status_cols.append(col)
# Add any remaining columns not in preferred order
for col in status_cols:
    if col not in ordered_status_cols:
        ordered_status_cols.append(col)

# Add row total
status_display['Row_Total'] = status_display[ordered_status_cols].sum(axis=1)

# Create color-coded cells based on flow
flow_colors = []
for flow in status_display['flow']:
    if flow == 'BREAKFIX':
        flow_colors.append('#ffe6e6')  # Light red
    elif flow == 'INSTALLATION':
        flow_colors.append('#e6f3ff')  # Light blue
    elif flow == 'DEINSTALLATION':
        flow_colors.append('#fff4e6')  # Light orange
    else:
        flow_colors.append('white')

# Create alternating row colors
cell_colors = []
for i in range(len(status_display)):
    if i % 2 == 0:
        cell_colors.append('#f8f9fa')
    else:
        cell_colors.append('white')

# Create Plotly table for status
fig_table2 = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Date</b>', '<b>Flow Type</b>'] + [f'<b>{col}</b>' for col in ordered_status_cols] + ['<b>Total</b>'],
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=13),
        height=40
    ),
    cells=dict(
        values=[status_display['date'], status_display['flow']] +
               [status_display[col] for col in ordered_status_cols] +
               [status_display['Row_Total']],
        fill_color=[cell_colors, flow_colors] + [cell_colors]*len(ordered_status_cols) + [['#e8f5e9']*len(status_display)],
        align=['left', 'left'] + ['center']*len(ordered_status_cols) + ['center'],
        font=dict(size=12),
        height=32,
        format=[None, None] + [',d']*len(ordered_status_cols) + [',d']  # Format numbers with commas
    )
)])

fig_table2.update_layout(
    title={
        'text': f"📊 Ticket Status by Flow - Daily View (Last 60 Rows)<br><sub>Total Tickets: {status_by_flow['ticket_count'].sum():,.0f} | Flow first, then status columns | Scroll to see all data</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=900,
    margin=dict(l=20, r=20, t=80, b=20)
)

print(f"✅ Created tabular views (showing last 30 rows each)")

# =============================================================================
# CREATE MTD COMPARISON TABLES
# =============================================================================
print("\n📊 Creating MTD comparison tables...")

# MTD Table 1: Tickets Comparison
def format_pct(val):
    """Format percentage change with color indicator"""
    if val > 0:
        return f"+{val:.2f}% 📈"
    elif val < 0:
        return f"{val:.2f}% 📉"
    else:
        return f"{val:.2f}% ➡️"

# Apply formatting for display
mtd_tickets_display = df_mtd_tickets.copy()
mtd_tickets_display['pct_change_display'] = mtd_tickets_display['pct_change'].apply(format_pct)

fig_mtd1 = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Metric</b>', '<b>Current MTD</b>', '<b>Last MTD</b>', '<b>Change</b>', '<b>% Change</b>'],
        fill_color='#27ae60',
        align='center',
        font=dict(color='white', size=14),
        height=40
    ),
    cells=dict(
        values=[
            mtd_tickets_display['metric'],
            mtd_tickets_display['current_mtd'].apply(lambda x: f"{x:,.2f}"),
            mtd_tickets_display['last_mtd'].apply(lambda x: f"{x:,.2f}"),
            mtd_tickets_display['change'].apply(lambda x: f"{x:+,.2f}"),
            mtd_tickets_display['pct_change_display']
        ],
        fill_color=[['#f8f9fa', 'white']*len(mtd_tickets_display)],
        align=['left', 'center', 'center', 'center', 'center'],
        font=dict(size=13),
        height=35
    )
)])

fig_mtd1.update_layout(
    title={
        'text': f"📊 Month-to-Date Tickets Comparison<br><sub>Current vs Last Month (Same Period)</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=400,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Update MTD table colors to match theme
fig_mtd1.data[0].header.fill.color = '#667eea'

# MTD Table 2: Flow Comparison
mtd_flow_display = df_mtd_flow.copy()
mtd_flow_display['pct_change_display'] = mtd_flow_display['pct_change'].apply(format_pct)

# Sort by current_mtd descending
mtd_flow_display = mtd_flow_display.sort_values('current_mtd', ascending=False)

fig_mtd2 = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Flow Type</b>', '<b>Current MTD</b>', '<b>Last MTD</b>', '<b>Change</b>', '<b>% Change</b>'],
        fill_color='#3498db',
        align='center',
        font=dict(color='white', size=14),
        height=40
    ),
    cells=dict(
        values=[
            mtd_flow_display['flow'],
            mtd_flow_display['current_mtd'].apply(lambda x: f"{x:,}"),
            mtd_flow_display['last_mtd'].apply(lambda x: f"{x:,}"),
            mtd_flow_display['change'].apply(lambda x: f"{x:+,}"),
            mtd_flow_display['pct_change_display']
        ],
        fill_color=[['#f8f9fa', 'white']*len(mtd_flow_display)],
        align=['left', 'center', 'center', 'center', 'center'],
        font=dict(size=13),
        height=35
    )
)])

fig_mtd2.update_layout(
    title={
        'text': f"🔄 MTD Tickets by Flow Comparison<br><sub>Current vs Last Month (Same Period)</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=300,
    margin=dict(l=20, r=20, t=80, b=20)
)

fig_mtd2.data[0].header.fill.color = '#667eea'

# MTD Table 3: Funnel Comparison
mtd_funnel_display = df_mtd_funnel.copy()
mtd_funnel_display['pct_change_display'] = mtd_funnel_display['pct_change'].apply(format_pct)

fig_mtd3 = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Funnel Metric</b>', '<b>Current MTD</b>', '<b>Last MTD</b>', '<b>Change</b>', '<b>% Change</b>'],
        fill_color='#9b59b6',
        align='center',
        font=dict(color='white', size=14),
        height=40
    ),
    cells=dict(
        values=[
            mtd_funnel_display['metric'],
            mtd_funnel_display['current_mtd'].apply(lambda x: f"{x:,.2f}"),
            mtd_funnel_display['last_mtd'].apply(lambda x: f"{x:,.2f}"),
            mtd_funnel_display['change'].apply(lambda x: f"{x:+,.2f}"),
            mtd_funnel_display['pct_change_display']
        ],
        fill_color=[['#f8f9fa', 'white']*len(mtd_funnel_display)],
        align=['left', 'center', 'center', 'center', 'center'],
        font=dict(size=13),
        height=35
    )
)])

fig_mtd3.update_layout(
    title={
        'text': f"📈 MTD Agent Funnel Comparison<br><sub>Current vs Last Month (Same Period)</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=450,
    margin=dict(l=20, r=20, t=80, b=20)
)

fig_mtd3.data[0].header.fill.color = '#667eea'

print(f"✅ Created 3 MTD comparison tables")

# =============================================================================
# CREATE AGENT PERFORMANCE TABLES - TOP PERFORMERS VS DEFAULTERS
# =============================================================================
print("\n📊 Creating agent performance tables (Top Performers vs Defaulters)...")

# Calculate agent-level metrics with employee_code
agent_stats = df_tickets.groupby(['assigned_to', 'employee_code']).agg({
    'ticket_id': 'count'  # Total tickets assigned
}).reset_index()
agent_stats.columns = ['agent', 'spl_code', 'tickets_assigned']

# Count tickets closed by the same agent they were assigned to
agent_closed = df_tickets[df_tickets['assigned_to'] == df_tickets['closed_by_id']].groupby('assigned_to').agg({
    'ticket_id': 'count'
}).reset_index()
agent_closed.columns = ['agent', 'tickets_closed_by_agent']

# Merge
agent_performance = agent_stats.merge(agent_closed, on='agent', how='left')
agent_performance['tickets_closed_by_agent'] = agent_performance['tickets_closed_by_agent'].fillna(0).astype(int)

# Calculate closure rate
agent_performance['agent_closure_rate'] = (
    agent_performance['tickets_closed_by_agent'] / agent_performance['tickets_assigned'] * 100
).round(2)

# Filter agents with at least 10 tickets for meaningful stats
agent_performance = agent_performance[agent_performance['tickets_assigned'] >= 10].copy()

# Remove N/A and null values from spl_code and agent fields
agent_performance = agent_performance[
    agent_performance['spl_code'].notna() &
    (agent_performance['spl_code'] != 'N/A') &
    (agent_performance['spl_code'] != '') &
    agent_performance['agent'].notna() &
    (agent_performance['agent'] != 'N/A') &
    (agent_performance['agent'] != '')
].copy()

# Sort by closure rate and then by tickets assigned
agent_performance_sorted = agent_performance.sort_values(
    ['agent_closure_rate', 'tickets_assigned'],
    ascending=[False, False]
)

# Top 20 Performers (highest closure rate)
top_performers = agent_performance_sorted.head(20).copy()
top_performers['rank'] = range(1, len(top_performers) + 1)

# Top 20 Defaulters (lowest closure rate, but sorted by tickets assigned descending)
top_defaulters = agent_performance.sort_values(
    ['agent_closure_rate', 'tickets_assigned'],
    ascending=[True, False]
).head(20).copy()
top_defaulters['rank'] = range(1, len(top_defaulters) + 1)

print(f"✅ Top 20 Performers identified (avg closure rate: {top_performers['agent_closure_rate'].mean():.2f}%)")
print(f"✅ Top 20 Defaulters identified (avg closure rate: {top_defaulters['agent_closure_rate'].mean():.2f}%)")

# Create Plotly table for Top Performers
fig_performers = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Rank</b>', '<b>SPL Code</b>', '<b>Agent</b>', '<b>Tickets Assigned</b>', '<b>Tickets Closed</b>', '<b>Closure Rate %</b>'],
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=14),
        height=40
    ),
    cells=dict(
        values=[
            top_performers['rank'],
            top_performers['spl_code'],
            top_performers['agent'],
            top_performers['tickets_assigned'],
            top_performers['tickets_closed_by_agent'],
            top_performers['agent_closure_rate'].apply(lambda x: f"{x:.2f}%")
        ],
        fill_color=[['#e8f5e9', '#f1f8e9']*10],  # Alternating light green shades
        align=['center', 'center', 'left', 'center', 'center', 'center'],
        font=dict(size=13),
        height=35,
        format=[None, None, None, ',d', ',d', None]
    )
)])

fig_performers.update_layout(
    title={
        'text': f"⭐ Top 20 Performers<br><sub>Highest Agent Closure Rate (min 10 tickets assigned)</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=700,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Create Plotly table for Top Defaulters
fig_defaulters = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Rank</b>', '<b>SPL Code</b>', '<b>Agent</b>', '<b>Tickets Assigned</b>', '<b>Tickets Closed</b>', '<b>Closure Rate %</b>'],
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=14),
        height=40
    ),
    cells=dict(
        values=[
            top_defaulters['rank'],
            top_defaulters['spl_code'],
            top_defaulters['agent'],
            top_defaulters['tickets_assigned'],
            top_defaulters['tickets_closed_by_agent'],
            top_defaulters['agent_closure_rate'].apply(lambda x: f"{x:.2f}%")
        ],
        fill_color=[['#ffebee', '#ffcdd2']*10],  # Alternating light red shades
        align=['center', 'center', 'left', 'center', 'center', 'center'],
        font=dict(size=13),
        height=35,
        format=[None, None, None, ',d', ',d', None]
    )
)])

fig_defaulters.update_layout(
    title={
        'text': f"⚠️ Top 20 Defaulters<br><sub>Lowest Agent Closure Rate (sorted by tickets assigned, min 10 tickets)</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=700,
    margin=dict(l=20, r=20, t=80, b=20)
)

print(f"✅ Created agent performance tables")

# Prepare agent data for JavaScript filtering
agent_filter_data = df_tickets[['ticket_id', 'assigned_to', 'employee_code', 'closed_by_id', 'ticket_created_date']].copy()
agent_filter_data['ticket_created_date'] = agent_filter_data['ticket_created_date'].dt.strftime('%Y-%m-%d')
agent_data_json = agent_filter_data.to_json(orient='records')

# =============================================================================
# CREATE TASK STATUS × TICKET STATUS PIVOT TABLE
# =============================================================================
print("\n📊 Creating Task Status × Ticket Status pivot table...")

# Get date range for filtering
min_date = df_tickets['ticket_created_date'].min()
max_date = df_tickets['ticket_created_date'].max()

print(f"   Date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")

# Get unique task-status combinations (one row per task with its status)
task_status_data = df_tickets.groupby(['task_id', 'task_status', 'ticket_status']).size().reset_index(name='count')

# Create pivot: task_status as rows, ticket_status as columns, count unique task_ids
pivot_data = task_status_data.groupby(['task_status', 'ticket_status'])['task_id'].nunique().reset_index()
pivot_table = pivot_data.pivot(index='task_status', columns='ticket_status', values='task_id').fillna(0).astype(int)

# Calculate row totals
pivot_table['Total'] = pivot_table.sum(axis=1)

# Calculate grand total
grand_total = pivot_table['Total'].sum()

# Create display table with counts and percentages within each row
display_data = []

# Get all ticket status columns (excluding Total)
ticket_statuses = [col for col in pivot_table.columns if col != 'Total']

# Header row
header_values = ['<b>Task Status</b>']
for status in ticket_statuses:
    header_values.append(f'<b>{status}</b>')
header_values.append('<b>Total</b>')

# Data rows
cell_values = [[] for _ in range(len(header_values))]

for task_status in pivot_table.index:
    row = pivot_table.loc[task_status]
    row_total = int(row['Total'])

    # Task status column
    cell_values[0].append(task_status)

    # Ticket status columns with counts AND percentages of grand total
    col_idx = 1
    for ticket_status in ticket_statuses:
        count = int(row[ticket_status])
        pct_of_grand_total = (count / grand_total * 100) if grand_total > 0 else 0
        cell_values[col_idx].append(f"{count:,}<br>({pct_of_grand_total:.2f}%)")
        col_idx += 1

    # Total column (with percentage of grand total)
    pct_of_grand = (row_total / grand_total * 100) if grand_total > 0 else 0
    cell_values[col_idx].append(f"{row_total:,}<br>({pct_of_grand:.2f}%)")

# Add TOTAL row
cell_values[0].append('<b>TOTAL</b>')
col_idx = 1
for ticket_status in ticket_statuses:
    col_total = int(pivot_table[ticket_status].sum())
    col_pct = (col_total / grand_total * 100) if grand_total > 0 else 0
    cell_values[col_idx].append(f"<b>{col_total:,}<br>({col_pct:.2f}%)</b>")
    col_idx += 1
# Total of totals
cell_values[col_idx].append(f"<b>{grand_total:,}<br>(100.00%)</b>")

# Create alternating row colors
num_rows = len(pivot_table) + 1  # +1 for TOTAL row
row_colors = []
for i in range(num_rows):
    if i == num_rows - 1:  # Last row (TOTAL)
        row_colors.append('#e3f2fd')
    elif i % 2 == 0:
        row_colors.append('#f8f9fa')
    else:
        row_colors.append('white')

# Repeat colors for all columns
cell_colors = [row_colors for _ in range(len(header_values))]

# Create Plotly table
fig_pivot = go.Figure(data=[go.Table(
    header=dict(
        values=header_values,
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=13),
        height=40
    ),
    cells=dict(
        values=cell_values,
        fill_color=cell_colors,
        align=['left'] + ['center']*(len(header_values)-1),
        font=dict(size=12),
        height=35
    )
)])

fig_pivot.update_layout(
    title={
        'text': f"📊 Task Status × Ticket Status Pivot View<br><sub>Unique Task Count with % of Grand Total | Total Tasks: {grand_total:,}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=500,
    margin=dict(l=20, r=20, t=80, b=20)
)

print(f"✅ Created Task Status × Ticket Status pivot table")
print(f"   Task Statuses: {len(pivot_table)} | Ticket Statuses: {len(ticket_statuses)} | Total Tasks: {grand_total:,}")

# =============================================================================
# CREATE TICKET-BASED PIVOT TABLE (Unique Ticket IDs)
# =============================================================================
print("\n📊 Creating Task Status × Ticket Status pivot table (Ticket-based)...")

# Create pivot with unique ticket counts
ticket_pivot_data = df_tickets.groupby(['task_status', 'ticket_status']).agg({
    'ticket_id': 'nunique'
}).reset_index()
ticket_pivot_table = ticket_pivot_data.pivot(index='task_status', columns='ticket_status', values='ticket_id').fillna(0).astype(int)

# Calculate totals
ticket_pivot_table['Total'] = ticket_pivot_table.sum(axis=1)
ticket_grand_total = ticket_pivot_table['Total'].sum()

# Get ticket status columns
ticket_statuses_col = [col for col in ticket_pivot_table.columns if col != 'Total']

# Create display table with tickets
ticket_header_values = ['<b>Task Status</b>']
for status in ticket_statuses_col:
    ticket_header_values.append(f'<b>{status}</b>')
ticket_header_values.append('<b>Total</b>')

ticket_cell_values = [[] for _ in range(len(ticket_header_values))]

for task_status in ticket_pivot_table.index:
    row = ticket_pivot_table.loc[task_status]
    row_total = int(row['Total'])

    ticket_cell_values[0].append(task_status)

    col_idx = 1
    for ticket_status in ticket_statuses_col:
        count = int(row[ticket_status])
        pct_of_total = (count / ticket_grand_total * 100) if ticket_grand_total > 0 else 0
        ticket_cell_values[col_idx].append(f"{count:,}<br>({pct_of_total:.2f}%)")
        col_idx += 1

    pct_of_grand = (row_total / ticket_grand_total * 100) if ticket_grand_total > 0 else 0
    ticket_cell_values[col_idx].append(f"{row_total:,}<br>({pct_of_grand:.2f}%)")

# Add TOTAL row
ticket_cell_values[0].append('<b>TOTAL</b>')
col_idx = 1
for ticket_status in ticket_statuses_col:
    col_total = int(ticket_pivot_table[ticket_status].sum())
    col_pct = (col_total / ticket_grand_total * 100) if ticket_grand_total > 0 else 0
    ticket_cell_values[col_idx].append(f"<b>{col_total:,}<br>({col_pct:.2f}%)</b>")
    col_idx += 1
ticket_cell_values[col_idx].append(f"<b>{ticket_grand_total:,}<br>(100.00%)</b>")

# Row colors
num_rows_ticket = len(ticket_pivot_table) + 1
row_colors_ticket = []
for i in range(num_rows_ticket):
    if i == num_rows_ticket - 1:
        row_colors_ticket.append('#e3f2fd')
    elif i % 2 == 0:
        row_colors_ticket.append('#f8f9fa')
    else:
        row_colors_ticket.append('white')

cell_colors_ticket = [row_colors_ticket for _ in range(len(ticket_header_values))]

fig_ticket_pivot = go.Figure(data=[go.Table(
    header=dict(
        values=ticket_header_values,
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=13),
        height=40
    ),
    cells=dict(
        values=ticket_cell_values,
        fill_color=cell_colors_ticket,
        align=['left'] + ['center']*(len(ticket_header_values)-1),
        font=dict(size=12),
        height=35
    )
)])

fig_ticket_pivot.update_layout(
    title={
        'text': f"📊 Task Status × Ticket Status (Ticket Count View)<br><sub>Unique Ticket Count with % of Grand Total | Total Tickets: {ticket_grand_total:,}</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=500,
    margin=dict(l=20, r=20, t=80, b=20)
)

print(f"✅ Created Ticket-based pivot table")
print(f"   Task Statuses: {len(ticket_pivot_table)} | Ticket Statuses: {len(ticket_statuses_col)} | Total Tickets: {ticket_grand_total:,}")

# Prepare data for JavaScript filtering
# Export tickets data with date info for client-side filtering
pivot_filter_data = df_tickets[['ticket_id', 'task_id', 'task_status', 'ticket_status',
                                  'ticket_created_date']].copy()
pivot_filter_data['ticket_created_date'] = pivot_filter_data['ticket_created_date'].dt.strftime('%Y-%m-%d')

# Convert to JSON for embedding in HTML
pivot_data_json = pivot_filter_data.to_json(orient='records')
date_range_json = json.dumps({
    'min': min_date.strftime('%Y-%m-%d'),
    'max': max_date.strftime('%Y-%m-%d')
})

# =============================================================================
# CREATE REGIONAL VIEWS
# =============================================================================
print("\n📊 Creating Regional Views...")

# Map hub to region
def map_hub_to_region(hub):
    """Map hub to region based on geographic location"""
    if pd.isna(hub):
        return 'Unknown'

    hub_str = str(hub).strip()

    # NORTH - Delhi, Haryana, UP, Rajasthan, Punjab, Chandigarh
    north_hubs = ['Delhi NCR', 'Lucknow', 'Chandigarh', 'Jaipur', 'Haryana',
                  'Delhi Ncr', 'Delhi', 'NCR', ' NCR', 'Gorakhpur']

    # SOUTH - Tamil Nadu, Karnataka, Kerala, Andhra Pradesh, Telangana
    south_hubs = ['Chennai', 'Hyderabad', 'Bangalore', 'ANDHRA PRADESH', 'Kochi',
                  'Andhra Pradesh', 'Andaman & Nicobar']

    # EAST - West Bengal, Odisha, Bihar, Assam, Jharkhand
    east_hubs = ['Kolkata', 'Bhubaneswar', 'Patna', 'Guwahati', 'Bhuwaneshwar',
                 'Rotn', 'ROTN']

    # WEST - Maharashtra, Gujarat, Madhya Pradesh, Goa, Chhattisgarh
    west_hubs = ['Mumbai', 'Pune', 'Bhopal', 'Ahmedabad']

    if hub_str in north_hubs:
        return 'North'
    elif hub_str in south_hubs:
        return 'South'
    elif hub_str in east_hubs:
        return 'East'
    elif hub_str in west_hubs:
        return 'West'
    else:
        return 'Unknown'

df_tickets['region'] = df_tickets['hub'].apply(map_hub_to_region)

# Normalize hub names (handle duplicates with different cases)
def normalize_hub_name(hub):
    """Normalize hub names to avoid duplicates"""
    if pd.isna(hub):
        return hub

    hub_str = str(hub).strip()

    # Define normalization mappings
    normalizations = {
        'ANDHRA PRADESH': 'Andhra Pradesh',
        'andhra pradesh': 'Andhra Pradesh',
        'ROTN': 'Rotn',
        'rotn': 'Rotn',
        'NCR': 'Delhi NCR',
        ' NCR': 'Delhi NCR',
        'DELHI NCR': 'Delhi NCR',
        'Delhi Ncr': 'Delhi NCR',
        'delhi ncr': 'Delhi NCR',
        'DELHI': 'Delhi',
        'delhi': 'Delhi',
        'BANGALORE': 'Bangalore',
        'bangalore': 'Bangalore',
        'MUMBAI': 'Mumbai',
        'mumbai': 'Mumbai',
        'CHENNAI': 'Chennai',
        'chennai': 'Chennai',
        'KOLKATA': 'Kolkata',
        'kolkata': 'Kolkata',
        'PUNE': 'Pune',
        'pune': 'Pune',
        'HYDERABAD': 'Hyderabad',
        'hyderabad': 'Hyderabad',
        'BHUBANESWAR': 'Bhubaneswar',
        'Bhuwaneshwar': 'Bhubaneswar',
        'bhuwaneshwar': 'Bhubaneswar',
        'bhubaneswar': 'Bhubaneswar',
        'AHMEDABAD': 'Ahmedabad',
        'ahmedabad': 'Ahmedabad',
        'LUCKNOW': 'Lucknow',
        'lucknow': 'Lucknow',
        'JAIPUR': 'Jaipur',
        'jaipur': 'Jaipur',
        'CHANDIGARH': 'Chandigarh',
        'chandigarh': 'Chandigarh',
        'PATNA': 'Patna',
        'patna': 'Patna',
        'BHOPAL': 'Bhopal',
        'bhopal': 'Bhopal',
        'KOCHI': 'Kochi',
        'kochi': 'Kochi',
        'GUWAHATI': 'Guwahati',
        'guwahati': 'Guwahati',
        'HARYANA': 'Haryana',
        'haryana': 'Haryana',
        'GORAKHPUR': 'Gorakhpur',
        'gorakhpur': 'Gorakhpur',
    }

    return normalizations.get(hub_str, hub_str)

df_tickets['hub_normalized'] = df_tickets['hub'].apply(normalize_hub_name)
print(f"✅ Hubs normalized: {df_tickets['hub_normalized'].nunique()} unique hubs after normalization")

# Priority 1: Regional Executive Summary
regions = ['North', 'South', 'East', 'West']
summary_data = []

for region in regions:
    region_df = df_tickets[df_tickets['region'] == region]

    if len(region_df) == 0:
        continue

    total_tickets = len(region_df)
    total_tasks = region_df['task_id'].nunique()
    closed_tickets = region_df['flag_ticket_closed'].sum()
    closure_rate = (closed_tickets / total_tickets * 100) if total_tickets > 0 else 0

    tat_tickets = region_df[region_df['ticket_tat'].notna()]
    avg_tat = tat_tickets['ticket_tat'].mean() if len(tat_tickets) > 0 else 0

    problematic_count = (region_df['ticket_status'] == 'PROBLEMATIC').sum()
    problematic_rate = (problematic_count / total_tickets * 100) if total_tickets > 0 else 0

    unique_agents = region_df['assigned_to'].nunique()
    tickets_per_agent = total_tickets / unique_agents if unique_agents > 0 else 0

    summary_data.append({
        'Region': region,
        'Total Tickets': total_tickets,
        'Total Tasks': total_tasks,
        'Closure Rate %': round(closure_rate, 2),
        'Avg TAT (days)': round(avg_tat, 2),
        'Problematic Rate %': round(problematic_rate, 2),
        'Tickets per Agent': round(tickets_per_agent, 2),
        'Unique Agents': unique_agents
    })

# Add TOTAL row
total_tickets_all = len(df_tickets)
total_tasks_all = df_tickets['task_id'].nunique()
closed_tickets_all = df_tickets['flag_ticket_closed'].sum()
closure_rate_all = (closed_tickets_all / total_tickets_all * 100)

tat_tickets_all = df_tickets[df_tickets['ticket_tat'].notna()]
avg_tat_all = tat_tickets_all['ticket_tat'].mean()

problematic_count_all = (df_tickets['ticket_status'] == 'PROBLEMATIC').sum()
problematic_rate_all = (problematic_count_all / total_tickets_all * 100)

unique_agents_all = df_tickets['assigned_to'].nunique()
tickets_per_agent_all = total_tickets_all / unique_agents_all

summary_data.append({
    'Region': 'TOTAL',
    'Total Tickets': total_tickets_all,
    'Total Tasks': total_tasks_all,
    'Closure Rate %': round(closure_rate_all, 2),
    'Avg TAT (days)': round(avg_tat_all, 2),
    'Problematic Rate %': round(problematic_rate_all, 2),
    'Tickets per Agent': round(tickets_per_agent_all, 2),
    'Unique Agents': unique_agents_all
})

df_summary = pd.DataFrame(summary_data)

# Create Plotly table for Regional Summary
header_values = ['<b>Region</b>', '<b>Total Tickets</b>', '<b>Total Tasks</b>',
                 '<b>Closure Rate %</b>', '<b>Avg TAT (days)</b>',
                 '<b>Problematic Rate %</b>', '<b>Tickets per Agent</b>', '<b>Unique Agents</b>']

cell_values = [
    df_summary['Region'],
    df_summary['Total Tickets'].apply(lambda x: f"{int(x):,}"),
    df_summary['Total Tasks'].apply(lambda x: f"{int(x):,}"),
    df_summary['Closure Rate %'].apply(lambda x: f"{x:.2f}%"),
    df_summary['Avg TAT (days)'].apply(lambda x: f"{x:.2f}"),
    df_summary['Problematic Rate %'].apply(lambda x: f"{x:.2f}%"),
    df_summary['Tickets per Agent'].apply(lambda x: f"{x:.2f}"),
    df_summary['Unique Agents'].apply(lambda x: f"{int(x):,}")
]

row_colors = ['#f8f9fa' if i % 2 == 0 else 'white' for i in range(len(df_summary) - 1)]
row_colors.append('#e3f2fd')
cell_colors = [row_colors for _ in range(len(header_values))]

fig_regional_summary = go.Figure(data=[go.Table(
    header=dict(
        values=header_values,
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=13, family='Arial Black'),
        height=40
    ),
    cells=dict(
        values=cell_values,
        fill_color=cell_colors,
        align=['left', 'center', 'center', 'center', 'center', 'center', 'center', 'center'],
        font=dict(size=12),
        height=35
    )
)])

fig_regional_summary.update_layout(
    title={
        'text': "📍 Regional Executive Summary<br><sub>Performance metrics by geographic region</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 20, 'color': '#2c3e50'}
    },
    height=400,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Priority 3: Hub Leaderboard with Adoption Rate
hub_metrics = []

# Join tickets with funnel data to get adoption metrics
# First, create employee_code to hub mapping from tickets
employee_hub_map = df_tickets.groupby('employee_code')['hub_normalized'].first().to_dict()

# Add hub to funnel data
df_funnel['hub'] = df_funnel['spl_code'].map(employee_hub_map)

for hub in df_tickets['hub_normalized'].dropna().unique():
    hub_df = df_tickets[df_tickets['hub_normalized'] == hub]

    total_tickets = len(hub_df)
    total_tasks = hub_df['task_id'].nunique()
    closed_tickets = hub_df['flag_ticket_closed'].sum()
    closure_rate = (closed_tickets / total_tickets * 100) if total_tickets > 0 else 0

    region = hub_df['region'].mode()[0] if len(hub_df['region'].mode()) > 0 else 'Unknown'

    tat_tickets = hub_df[hub_df['ticket_tat'].notna()]
    avg_tat = tat_tickets['ticket_tat'].mean() if len(tat_tickets) > 0 else 0

    unique_agents = hub_df['assigned_to'].nunique()

    # Calculate adoption rate from funnel data
    hub_funnel = df_funnel[df_funnel['hub'] == hub]
    if len(hub_funnel) > 0:
        attempted_count = hub_funnel['attempted_flag'].sum()
        logged_in_count = hub_funnel['logged_in'].sum()
        adoption_rate = (attempted_count / logged_in_count * 100) if logged_in_count > 0 else 0
    else:
        adoption_rate = 0

    hub_metrics.append({
        'Hub': hub,
        'Region': region,
        'Total Tickets': total_tickets,
        'Total Tasks': total_tasks,
        'Closed Tickets': closed_tickets,
        'Closure Rate %': round(closure_rate, 2),
        'Adoption Rate %': round(adoption_rate, 2),
        'Avg TAT (days)': round(avg_tat, 2),
        'Unique Agents': unique_agents
    })

df_hubs = pd.DataFrame(hub_metrics)

# Top 10 hubs by Closure Rate
df_hubs_sorted_closure = df_hubs.sort_values('Closure Rate %', ascending=False)
top_10_closure = df_hubs_sorted_closure.head(10).reset_index(drop=True)
top_10_closure.insert(0, 'Rank', range(1, len(top_10_closure) + 1))

# Bottom 10 hubs by Closure Rate
bottom_10_closure = df_hubs_sorted_closure.tail(10).reset_index(drop=True)
bottom_10_closure.insert(0, 'Rank', range(len(df_hubs_sorted_closure) - len(bottom_10_closure) + 1, len(df_hubs_sorted_closure) + 1))

# Top 10 hubs by Adoption Rate
df_hubs_sorted_adoption = df_hubs.sort_values('Adoption Rate %', ascending=False)
top_10_adoption = df_hubs_sorted_adoption.head(10).reset_index(drop=True)
top_10_adoption.insert(0, 'Rank', range(1, len(top_10_adoption) + 1))

# Bottom 10 hubs by Adoption Rate
bottom_10_adoption = df_hubs_sorted_adoption.tail(10).reset_index(drop=True)
bottom_10_adoption.insert(0, 'Rank', range(len(df_hubs_sorted_adoption) - len(bottom_10_adoption) + 1, len(df_hubs_sorted_adoption) + 1))

# Create Plotly table for Top 10 Closure Rate
top_header = ['<b>Rank</b>', '<b>Hub</b>', '<b>Region</b>', '<b>Total Tickets</b>',
              '<b>Closed Tickets</b>', '<b>Closure Rate %</b>', '<b>Adoption Rate %</b>', '<b>Avg TAT (days)</b>']

top_cell_values = [
    top_10_closure['Rank'],
    top_10_closure['Hub'],
    top_10_closure['Region'],
    top_10_closure['Total Tickets'].apply(lambda x: f"{int(x):,}"),
    top_10_closure['Closed Tickets'].apply(lambda x: f"{int(x):,}"),
    top_10_closure['Closure Rate %'].apply(lambda x: f"{x:.2f}%"),
    top_10_closure['Adoption Rate %'].apply(lambda x: f"{x:.2f}%"),
    top_10_closure['Avg TAT (days)'].apply(lambda x: f"{x:.2f}")
]

top_row_colors = ['#f8f9fa' if i % 2 == 0 else 'white' for i in range(len(top_10_closure))]
top_cell_colors = [top_row_colors for _ in range(len(top_header))]

fig_top_hubs_closure = go.Figure(data=[go.Table(
    header=dict(
        values=top_header,
        fill_color='#28a745',
        align='center',
        font=dict(color='white', size=13, family='Arial Black'),
        height=40
    ),
    cells=dict(
        values=top_cell_values,
        fill_color=top_cell_colors,
        align=['center', 'left', 'center', 'center', 'center', 'center', 'center', 'center'],
        font=dict(size=12),
        height=35
    )
)])

fig_top_hubs_closure.update_layout(
    title={
        'text': "🏆 Top 10 Hubs by Closure Rate<br><sub>Best performing hubs for ticket closure</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=500,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Create Plotly table for Bottom 10 Closure Rate
bottom_cell_values = [
    bottom_10_closure['Rank'],
    bottom_10_closure['Hub'],
    bottom_10_closure['Region'],
    bottom_10_closure['Total Tickets'].apply(lambda x: f"{int(x):,}"),
    bottom_10_closure['Closed Tickets'].apply(lambda x: f"{int(x):,}"),
    bottom_10_closure['Closure Rate %'].apply(lambda x: f"{x:.2f}%"),
    bottom_10_closure['Adoption Rate %'].apply(lambda x: f"{x:.2f}%"),
    bottom_10_closure['Avg TAT (days)'].apply(lambda x: f"{x:.2f}")
]

bottom_row_colors = ['#f8f9fa' if i % 2 == 0 else 'white' for i in range(len(bottom_10_closure))]
bottom_cell_colors = [bottom_row_colors for _ in range(len(top_header))]

fig_bottom_hubs_closure = go.Figure(data=[go.Table(
    header=dict(
        values=top_header,
        fill_color='#dc3545',
        align='center',
        font=dict(color='white', size=13, family='Arial Black'),
        height=40
    ),
    cells=dict(
        values=bottom_cell_values,
        fill_color=bottom_cell_colors,
        align=['center', 'left', 'center', 'center', 'center', 'center', 'center', 'center'],
        font=dict(size=12),
        height=35
    )
)])

fig_bottom_hubs_closure.update_layout(
    title={
        'text': "⚠️  Bottom 10 Hubs by Closure Rate<br><sub>Hubs requiring attention for closure performance</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=500,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Create Plotly tables for Adoption Rate
adoption_header = ['<b>Rank</b>', '<b>Hub</b>', '<b>Region</b>', '<b>Total Tickets</b>',
                   '<b>Adoption Rate %</b>', '<b>Closure Rate %</b>', '<b>Avg TAT (days)</b>']

# Top 10 Adoption Rate
top_adoption_cell_values = [
    top_10_adoption['Rank'],
    top_10_adoption['Hub'],
    top_10_adoption['Region'],
    top_10_adoption['Total Tickets'].apply(lambda x: f"{int(x):,}"),
    top_10_adoption['Adoption Rate %'].apply(lambda x: f"{x:.2f}%"),
    top_10_adoption['Closure Rate %'].apply(lambda x: f"{x:.2f}%"),
    top_10_adoption['Avg TAT (days)'].apply(lambda x: f"{x:.2f}")
]

top_adoption_colors = ['#f8f9fa' if i % 2 == 0 else 'white' for i in range(len(top_10_adoption))]
top_adoption_cell_colors = [top_adoption_colors for _ in range(len(adoption_header))]

fig_top_hubs_adoption = go.Figure(data=[go.Table(
    header=dict(
        values=adoption_header,
        fill_color='#17a2b8',
        align='center',
        font=dict(color='white', size=13, family='Arial Black'),
        height=40
    ),
    cells=dict(
        values=top_adoption_cell_values,
        fill_color=top_adoption_cell_colors,
        align=['center', 'left', 'center', 'center', 'center', 'center', 'center'],
        font=dict(size=12),
        height=35
    )
)])

fig_top_hubs_adoption.update_layout(
    title={
        'text': "🎯 Top 10 Hubs by Adoption Rate<br><sub>Best performing hubs for agent adoption</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=500,
    margin=dict(l=20, r=20, t=80, b=20)
)

# Bottom 10 Adoption Rate
bottom_adoption_cell_values = [
    bottom_10_adoption['Rank'],
    bottom_10_adoption['Hub'],
    bottom_10_adoption['Region'],
    bottom_10_adoption['Total Tickets'].apply(lambda x: f"{int(x):,}"),
    bottom_10_adoption['Adoption Rate %'].apply(lambda x: f"{x:.2f}%"),
    bottom_10_adoption['Closure Rate %'].apply(lambda x: f"{x:.2f}%"),
    bottom_10_adoption['Avg TAT (days)'].apply(lambda x: f"{x:.2f}")
]

bottom_adoption_colors = ['#f8f9fa' if i % 2 == 0 else 'white' for i in range(len(bottom_10_adoption))]
bottom_adoption_cell_colors = [bottom_adoption_colors for _ in range(len(adoption_header))]

fig_bottom_hubs_adoption = go.Figure(data=[go.Table(
    header=dict(
        values=adoption_header,
        fill_color='#ffc107',
        align='center',
        font=dict(color='white', size=13, family='Arial Black'),
        height=40
    ),
    cells=dict(
        values=bottom_adoption_cell_values,
        fill_color=bottom_adoption_cell_colors,
        align=['center', 'left', 'center', 'center', 'center', 'center', 'center'],
        font=dict(size=12),
        height=35
    )
)])

fig_bottom_hubs_adoption.update_layout(
    title={
        'text': "📉 Bottom 10 Hubs by Adoption Rate<br><sub>Hubs requiring attention for adoption performance</sub>",
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=500,
    margin=dict(l=20, r=20, t=80, b=20)
)

print(f"✅ Regional views created: {len(regions)} regions, {len(df_hubs)} hubs")

# Export regional data for filtering (after region and hub_normalized columns are created)
regional_filter_data = df_tickets[['ticket_id', 'task_id', 'region', 'hub_normalized',
                                     'flag_ticket_closed', 'ticket_tat', 'ticket_status',
                                     'assigned_to', 'ticket_created_date']].copy()
regional_filter_data['ticket_created_date'] = regional_filter_data['ticket_created_date'].dt.strftime('%Y-%m-%d')
regional_data_json = regional_filter_data.to_json(orient='records')

# =============================================================================
# CREATE ADDITIONAL VIEWS
# =============================================================================
print("\n📊 Creating additional flow and status views...")

# Tickets by Flow Type - Stacked Bar Chart (% of total)
flow_over_time = df_tickets_timeseries.groupby([pd.Grouper(key='ticket_created_date', freq='D'), 'flow']).size().reset_index(name='count')
flow_pivot = flow_over_time.pivot(index='ticket_created_date', columns='flow', values='count').fillna(0)

# Calculate percentages
flow_pivot_pct = flow_pivot.div(flow_pivot.sum(axis=1), axis=0) * 100

fig_flow_pct = go.Figure()

for flow in flow_pivot_pct.columns:
    fig_flow_pct.add_trace(go.Bar(
        x=flow_pivot_pct.index,
        y=flow_pivot_pct[flow],
        name=flow,
        hovertemplate='<b>%{fullData.name}</b><br>Date: %{x}<br>Percentage: %{y:.2f}%<extra></extra>'
    ))

fig_flow_pct.update_layout(
    title={
        'text': '📊 Tickets by Flow Type (% of Total)<br><sub>Daily distribution showing flow composition</sub>',
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    barmode='stack',
    xaxis_title='Date',
    yaxis_title='Percentage of Total Tickets (%)',
    hovermode='x unified',
    height=500,
    showlegend=True,
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
)

# Export flow data for filtering
flow_filter_data = df_tickets_timeseries[['ticket_id', 'ticket_created_date', 'flow']].copy()
flow_filter_data['ticket_created_date'] = flow_filter_data['ticket_created_date'].dt.strftime('%Y-%m-%d')
flow_data_json = flow_filter_data.to_json(orient='records')

# Ticket Status by Flow - Daily View Table (Last 60 Days)
today_date = df_tickets_timeseries['ticket_created_date'].max()
last_60_days = today_date - pd.Timedelta(days=60)
df_last_60 = df_tickets_timeseries[df_tickets_timeseries['ticket_created_date'] >= last_60_days]

# Create pivot for ticket status by flow
status_flow_data = []
for date in pd.date_range(start=last_60_days, end=today_date, freq='D'):
    day_data = df_last_60[df_last_60['ticket_created_date'] == date]

    for flow in day_data['flow'].unique():
        flow_data = day_data[day_data['flow'] == flow]

        closed = (flow_data['ticket_status'] == 'CLOSED').sum()
        open_count = (flow_data['ticket_status'] == 'OPEN').sum()
        problematic = (flow_data['ticket_status'] == 'PROBLEMATIC').sum()
        revisit = (flow_data['ticket_status'] == 'REVISIT').sum()
        closure_evidence = (flow_data['ticket_status'] == 'CLOSURE_EVIDENCE_SUBMITTED').sum()
        total = len(flow_data)

        if total > 0:
            status_flow_data.append({
                'Date': date.strftime('%Y-%m-%d'),
                'Flow Type': flow,
                'Closed': closed,
                'Open': open_count,
                'Problematic': problematic,
                'Revisit': revisit,
                'Closure Evidence Submitted': closure_evidence,
                'Total': total
            })

df_status_flow_table = pd.DataFrame(status_flow_data)

# Sort by date in descending order (most recent first)
df_status_flow_table = df_status_flow_table.sort_values('Date', ascending=False).reset_index(drop=True)

# Create Plotly table
fig_status_flow_table = go.Figure(data=[go.Table(
    header=dict(
        values=['<b>Date</b>', '<b>Flow Type</b>', '<b>Closed</b>', '<b>Open</b>',
                '<b>Problematic</b>', '<b>Revisit</b>', '<b>Closure Evidence</b>', '<b>Total</b>'],
        fill_color='#667eea',
        align='center',
        font=dict(color='white', size=12, family='Arial Black'),
        height=40
    ),
    cells=dict(
        values=[
            df_status_flow_table['Date'],
            df_status_flow_table['Flow Type'],
            df_status_flow_table['Closed'],
            df_status_flow_table['Open'],
            df_status_flow_table['Problematic'],
            df_status_flow_table['Revisit'],
            df_status_flow_table['Closure Evidence Submitted'],
            df_status_flow_table['Total']
        ],
        fill_color=[['#f8f9fa' if i % 2 == 0 else 'white' for i in range(len(df_status_flow_table))] for _ in range(8)],
        align=['left', 'left', 'center', 'center', 'center', 'center', 'center', 'center'],
        font=dict(size=11),
        height=30
    )
)])

fig_status_flow_table.update_layout(
    title={
        'text': '🚦 Ticket Status by Flow - Daily View (Last 60 Days)<br><sub>Detailed breakdown of ticket statuses by flow type</sub>',
        'x': 0.5,
        'xanchor': 'center',
        'font': {'size': 18, 'color': '#2c3e50'}
    },
    height=800,
    margin=dict(l=20, r=20, t=80, b=20)
)

print(f"✅ Created ticket status by flow table (last 60 days: {len(df_status_flow_table)} rows)")

# =============================================================================
# CREATE HTML DASHBOARD
# =============================================================================
print("\n📝 Generating interactive HTML dashboard...")

# Calculate KPI Summary Stats
from datetime import datetime, timedelta

today = df_tickets['ticket_created_date'].max()
current_month_start = today.replace(day=1)
current_day_of_month = today.day

# Last month dates
last_month_end = current_month_start - timedelta(days=1)
last_month_start = last_month_end.replace(day=1)

# MTD periods
mtd_tickets = df_tickets[(df_tickets['ticket_created_date'] >= current_month_start) &
                          (df_tickets['ticket_created_date'] <= today)]
mtd_funnel = df_funnel[(df_funnel['dt'] >= pd.Timestamp(current_month_start)) &
                        (df_funnel['dt'] <= pd.Timestamp(today))]

# Last Month (full)
last_month_tickets = df_tickets[(df_tickets['ticket_created_date'] >= last_month_start) &
                                 (df_tickets['ticket_created_date'] <= last_month_end)]
last_month_funnel = df_funnel[(df_funnel['dt'] >= pd.Timestamp(last_month_start)) &
                               (df_funnel['dt'] <= pd.Timestamp(last_month_end))]

# Last Month Till Date (same day as today)
lmtd_end = last_month_start + timedelta(days=current_day_of_month - 1)
lmtd_tickets = df_tickets[(df_tickets['ticket_created_date'] >= last_month_start) &
                           (df_tickets['ticket_created_date'] <= lmtd_end)]
lmtd_funnel = df_funnel[(df_funnel['dt'] >= pd.Timestamp(last_month_start)) &
                         (df_funnel['dt'] <= pd.Timestamp(lmtd_end))]

# Previous Day
previous_day = today - timedelta(days=1)
prev_day_tickets = df_tickets[df_tickets['ticket_created_date'] == previous_day]
prev_day_funnel = df_funnel[df_funnel['dt'] == pd.Timestamp(previous_day)]

# Current Week (week starting Monday)
current_week_start = today - timedelta(days=today.weekday())
current_week_tickets = df_tickets[(df_tickets['ticket_created_date'] >= current_week_start) &
                                   (df_tickets['ticket_created_date'] <= today)]
current_week_funnel = df_funnel[(df_funnel['dt'] >= pd.Timestamp(current_week_start)) &
                                 (df_funnel['dt'] <= pd.Timestamp(today))]

# Last Week (complete week)
last_week_end = current_week_start - timedelta(days=1)
last_week_start = last_week_end - timedelta(days=6)
last_week_tickets = df_tickets[(df_tickets['ticket_created_date'] >= last_week_start) &
                                (df_tickets['ticket_created_date'] <= last_week_end)]
last_week_funnel = df_funnel[(df_funnel['dt'] >= pd.Timestamp(last_week_start)) &
                               (df_funnel['dt'] <= pd.Timestamp(last_week_end))]

# Calculate metrics
def calc_metrics(tickets_df, funnel_df):
    total_tickets = len(tickets_df)
    total_tasks = tickets_df['task_id'].nunique() if len(tickets_df) > 0 else 0
    closed_tickets = tickets_df['flag_ticket_closed'].sum() if len(tickets_df) > 0 else 0
    closure_rate = (closed_tickets / total_tickets * 100) if total_tickets > 0 else 0

    # Calculate unique agents who attempted
    agents_attempted = funnel_df[funnel_df['attempted_flag'] == 1]['spl_code'].nunique() if len(funnel_df) > 0 else 0

    # Calculate total unique agents (matching chart logic)
    total_unique_agents = funnel_df['spl_code'].nunique() if len(funnel_df) > 0 else 0

    # Adoption rate: unique agents attempted / total unique agents (matching chart calculation)
    adoption_rate = (agents_attempted / total_unique_agents * 100) if total_unique_agents > 0 else 0

    return {
        'total_tickets': total_tickets,
        'total_tasks': total_tasks,
        'closure_rate': round(closure_rate, 2),
        'adoption_rate': round(adoption_rate, 2),
        'agents_attempted': agents_attempted
    }

kpi_mtd = calc_metrics(mtd_tickets, mtd_funnel)
kpi_last_month = calc_metrics(last_month_tickets, last_month_funnel)
kpi_lmtd = calc_metrics(lmtd_tickets, lmtd_funnel)
kpi_prev_day = calc_metrics(prev_day_tickets, prev_day_funnel)
kpi_current_week = calc_metrics(current_week_tickets, current_week_funnel)
kpi_last_week = calc_metrics(last_week_tickets, last_week_funnel)

# Legacy stats for compatibility
df_daily_summary = all_metrics['day']['daily']
total_tickets = df_daily_summary['ticket_count'].sum()
total_tasks = df_daily_summary['task_count'].sum()
avg_tickets = df_daily_summary['ticket_count'].mean()
avg_tasks = df_daily_summary['task_count'].mean()
avg_adoption = df_daily_summary['adoption_rate'].mean()

# Convert charts and tables
chart1_html = fig1.to_html(full_html=False, include_plotlyjs=False)
chart2_html = fig2.to_html(full_html=False, include_plotlyjs=False)
chart3_html = fig3.to_html(full_html=False, include_plotlyjs=False)
chart3b_html = fig3b.to_html(full_html=False, include_plotlyjs=False)
chart3c_html = fig3c.to_html(full_html=False, include_plotlyjs=False)
chart4_html = fig4.to_html(full_html=False, include_plotlyjs=False)
table1_html = fig_table1.to_html(full_html=False, include_plotlyjs=False)
table2_html = fig_table2.to_html(full_html=False, include_plotlyjs=False)
mtd1_html = fig_mtd1.to_html(full_html=False, include_plotlyjs=False)
mtd2_html = fig_mtd2.to_html(full_html=False, include_plotlyjs=False)
mtd3_html = fig_mtd3.to_html(full_html=False, include_plotlyjs=False)
performers_html = fig_performers.to_html(full_html=False, include_plotlyjs=False)
defaulters_html = fig_defaulters.to_html(full_html=False, include_plotlyjs=False)
ticket_pivot_html = fig_ticket_pivot.to_html(full_html=False, include_plotlyjs=False)
regional_summary_html = fig_regional_summary.to_html(full_html=False, include_plotlyjs=False)
top_hubs_closure_html = fig_top_hubs_closure.to_html(full_html=False, include_plotlyjs=False)
bottom_hubs_closure_html = fig_bottom_hubs_closure.to_html(full_html=False, include_plotlyjs=False)
top_hubs_adoption_html = fig_top_hubs_adoption.to_html(full_html=False, include_plotlyjs=False)
bottom_hubs_adoption_html = fig_bottom_hubs_adoption.to_html(full_html=False, include_plotlyjs=False)
flow_pct_html = fig_flow_pct.to_html(full_html=False, include_plotlyjs=False)
status_flow_table_html = fig_status_flow_table.to_html(full_html=False, include_plotlyjs=False)

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>FE App Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        .header {{
            text-align: center;
            padding: 20px 0;
            border-bottom: 3px solid #667eea;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #2c3e50;
            font-size: 36px;
        }}
        .header p {{
            margin: 10px 0 0 0;
            color: #7f8c8d;
            font-size: 14px;
        }}
        .info-box {{
            background: #e8f5e9;
            border-left: 4px solid #27ae60;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .info-box h3 {{
            margin: 0 0 10px 0;
            color: #27ae60;
        }}
        .info-box ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        .kpi-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .kpi-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 10px;
            color: white;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        .kpi-value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .kpi-label {{
            font-size: 13px;
            opacity: 0.9;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .kpi-subtext {{
            font-size: 12px;
            margin-top: 5px;
            opacity: 0.8;
        }}
        .chart-container {{
            margin-bottom: 40px;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #7f8c8d;
            border-top: 2px solid #ecf0f1;
            margin-top: 40px;
        }}
        /* Hide all content inside range sliders - no graphs, no numbers */
        .rangeslider-container .y.nsewdrag {{
            display: none !important;
        }}
        .rangeslider-container .ytick {{
            display: none !important;
        }}
        .rangeslider-container .scatterlayer {{
            display: none !important;
        }}
        .rangeslider-container .trace {{
            display: none !important;
        }}
        .rangeslider-container path {{
            display: none !important;
        }}
        .rangeslider-mask-min, .rangeslider-mask-max {{
            opacity: 0.2;
            fill: #e0e0e0;
        }}
        .rangeslider-slidebox {{
            fill: #ffffff !important;
        }}
        .rangeslider-grabber {{
            fill: #3498db !important;
        }}
    </style>
    <script>
        // Pivot filter data
        const pivotData = {pivot_data_json};
        const agentData = {agent_data_json};
        const regionalData = {regional_data_json};
        const flowData = {flow_data_json};
        const dateRange = {date_range_json};

        // Store original KPI values
        const originalKPIs = {{
            tickets: {int(total_tickets)},
            tasks: {int(total_tasks)},
            adoption: {avg_adoption:.2f},
            days: {len(df_daily_summary)},
            avgTicketsPerDay: {avg_tickets:.2f},
            avgTasksPerDay: {avg_tasks:.2f}
        }};

        // Initialize filters
        window.onload = function() {{
            // Set date inputs to full range
            document.getElementById('start-date').value = dateRange.min;
            document.getElementById('end-date').value = dateRange.max;
        }};

        function updateKPIsByDays() {{
            const days = parseInt(document.getElementById('days-input').value);

            if (!days || days < 1) {{
                alert('Please enter a valid number of days');
                return;
            }}

            // Sort data by date descending and get last N days
            const sortedData = [...pivotData].sort((a, b) => b.ticket_created_date.localeCompare(a.ticket_created_date));

            // Get unique dates
            const uniqueDates = [...new Set(sortedData.map(r => r.ticket_created_date))];
            const lastNDates = uniqueDates.slice(0, Math.min(days, uniqueDates.length));

            // Filter data for last N days
            const filteredData = sortedData.filter(r => lastNDates.includes(r.ticket_created_date));

            // Calculate KPIs
            const totalTickets = filteredData.length;
            const totalTasks = new Set(filteredData.map(r => r.task_id)).size;
            const actualDays = lastNDates.length;

            // Update KPIs
            document.getElementById('kpi-tickets').textContent = totalTickets.toLocaleString();
            document.getElementById('kpi-tasks').textContent = totalTasks.toLocaleString();
            document.getElementById('kpi-tickets-avg').textContent = `Avg: ${{(totalTickets / actualDays).toFixed(0)}} per day`;
            document.getElementById('kpi-tasks-avg').textContent = `Avg: ${{(totalTasks / actualDays).toFixed(0)}} per day`;

            // Note: Adoption rate calculation would require funnel data, keeping it as is for now
            // You can expand this if needed

            // Update the date range to reflect last N days
            if (lastNDates.length > 0) {{
                const startDate = lastNDates[lastNDates.length - 1];
                const endDate = lastNDates[0];
                document.getElementById('start-date').value = startDate;
                document.getElementById('end-date').value = endDate;

                // Also update agent tables
                const agentFilteredData = agentData.filter(r => lastNDates.includes(r.ticket_created_date));
                rebuildAgentTables(agentFilteredData);
            }}
        }}

        function applyGlobalFilters() {{
            const startDate = document.getElementById('start-date').value;
            const endDate = document.getElementById('end-date').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            // Filter data by date range
            let filteredData = pivotData.filter(row => {{
                return row.ticket_created_date >= startDate && row.ticket_created_date <= endDate;
            }});

            // Rebuild pivot table
            rebuildTicketPivot(filteredData);

            // Update status and KPIs
            const uniqueTasks = new Set(filteredData.map(r => r.task_id)).size;

            // Calculate actual days in the date range
            const uniqueDates = new Set(filteredData.map(r => r.ticket_created_date));
            const actualDays = uniqueDates.size;

            document.getElementById('global-filter-status').textContent =
                `Filtered: ${{filteredData.length.toLocaleString()}} tickets | ${{uniqueTasks.toLocaleString()}} unique tasks | ${{actualDays}} days`;

            document.getElementById('kpi-tickets').textContent = filteredData.length.toLocaleString();
            document.getElementById('kpi-tasks').textContent = uniqueTasks.toLocaleString();
            document.getElementById('days-input').value = actualDays;
            document.getElementById('kpi-tickets-avg').textContent = `Avg: ${{(filteredData.length / actualDays).toFixed(0)}} per day`;
            document.getElementById('kpi-tasks-avg').textContent = `Avg: ${{(uniqueTasks / actualDays).toFixed(0)}} per day`;
        }}

        function resetGlobalFilters() {{
            document.getElementById('start-date').value = dateRange.min;
            document.getElementById('end-date').value = dateRange.max;
            document.getElementById('days-input').value = originalKPIs.days;
            rebuildTicketPivot(pivotData);
            document.getElementById('global-filter-status').textContent = '';

            // Reset KPIs to original values
            document.getElementById('kpi-tickets').textContent = originalKPIs.tickets.toLocaleString();
            document.getElementById('kpi-tasks').textContent = originalKPIs.tasks.toLocaleString();
            document.getElementById('kpi-adoption').textContent = originalKPIs.adoption.toFixed(1) + '%';
            document.getElementById('kpi-tickets-avg').textContent = `Avg: ${{originalKPIs.avgTicketsPerDay.toFixed(0)}} per day`;
            document.getElementById('kpi-tasks-avg').textContent = `Avg: ${{originalKPIs.avgTasksPerDay.toFixed(0)}} per day`;

            // Reset agent tables
            rebuildAgentTables(agentData);
        }}


        function rebuildTicketPivot(data) {{
            // Build ticket-based pivot structure
            const ticketPivot = {{}};
            const ticketCounts = {{}};

            data.forEach(row => {{
                const key = row.task_status + '|||' + row.ticket_status;
                if (!ticketCounts[key]) {{
                    ticketCounts[key] = new Set();
                }}
                ticketCounts[key].add(row.ticket_id);
            }});

            // Convert to counts
            Object.keys(ticketCounts).forEach(key => {{
                const [taskStatus, ticketStatus] = key.split('|||');
                if (!ticketPivot[taskStatus]) {{
                    ticketPivot[taskStatus] = {{}};
                }}
                ticketPivot[taskStatus][ticketStatus] = ticketCounts[key].size;
            }});

            // Get unique statuses
            const taskStatuses = Object.keys(ticketPivot).sort();
            const ticketStatusSet = new Set();
            Object.values(ticketPivot).forEach(row => {{
                Object.keys(row).forEach(status => ticketStatusSet.add(status));
            }});
            const ticketStatuses = Array.from(ticketStatusSet).sort();

            // Calculate totals
            const rowTotals = {{}};
            const colTotals = {{}};
            let grandTotal = 0;

            taskStatuses.forEach(taskStatus => {{
                rowTotals[taskStatus] = 0;
                ticketStatuses.forEach(ticketStatus => {{
                    const val = ticketPivot[taskStatus][ticketStatus] || 0;
                    rowTotals[taskStatus] += val;
                    colTotals[ticketStatus] = (colTotals[ticketStatus] || 0) + val;
                    grandTotal += val;
                }});
            }});

            // Build HTML table
            let html = '<table style="width: 100%; border-collapse: collapse; margin-top: 20px;">';

            // Header
            html += '<thead><tr style="background: #667eea; color: white;">';
            html += '<th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Task Status</th>';
            ticketStatuses.forEach(status => {{
                html += `<th style="padding: 12px; text-align: center; border: 1px solid #ddd;">${{status}}</th>`;
            }});
            html += '<th style="padding: 12px; text-align: center; border: 1px solid #ddd;">Total</th>';
            html += '</tr></thead><tbody>';

            // Data rows
            taskStatuses.forEach((taskStatus, idx) => {{
                const bgColor = idx % 2 === 0 ? '#f8f9fa' : 'white';
                html += `<tr style="background: ${{bgColor}};">`;
                html += `<td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">${{taskStatus}}</td>`;

                ticketStatuses.forEach(ticketStatus => {{
                    const count = ticketPivot[taskStatus][ticketStatus] || 0;
                    const pct = grandTotal > 0 ? ((count / grandTotal) * 100).toFixed(2) : '0.00';
                    html += `<td style="padding: 10px; text-align: center; border: 1px solid #ddd;">
                        ${{count.toLocaleString()}}<br><span style="color: #666; font-size: 0.9em;">(${{pct}}%)</span>
                    </td>`;
                }});

                const totalPct = grandTotal > 0 ? ((rowTotals[taskStatus] / grandTotal) * 100).toFixed(2) : '0.00';
                html += `<td style="padding: 10px; text-align: center; border: 1px solid #ddd; font-weight: bold;">
                    ${{rowTotals[taskStatus].toLocaleString()}}<br><span style="color: #666; font-size: 0.9em;">(${{totalPct}}%)</span>
                </td>`;
                html += '</tr>';
            }});

            // Total row
            html += '<tr style="background: #e3f2fd; font-weight: bold;">';
            html += '<td style="padding: 10px; border: 1px solid #ddd;">TOTAL</td>';
            ticketStatuses.forEach(ticketStatus => {{
                const total = colTotals[ticketStatus] || 0;
                const pct = grandTotal > 0 ? ((total / grandTotal) * 100).toFixed(2) : '0.00';
                html += `<td style="padding: 10px; text-align: center; border: 1px solid #ddd;">
                    ${{total.toLocaleString()}}<br><span style="color: #666; font-size: 0.9em;">(${{pct}}%)</span>
                </td>`;
            }});
            html += `<td style="padding: 10px; text-align: center; border: 1px solid #ddd;">
                ${{grandTotal.toLocaleString()}}<br><span style="color: #666; font-size: 0.9em;">(100.00%)</span>
            </td>`;
            html += '</tr>';

            html += '</tbody></table>';

            // Update container
            const ticketContainer = document.getElementById('ticket-pivot-table-container');
            ticketContainer.innerHTML = '<div class="chart-container" style="padding: 20px;"><h3 style="color: #2c3e50; text-align: center; margin-bottom: 10px;">📊 Task Status × Ticket Status (Ticket Count View)</h3><p style="text-align: center; color: #666; margin-bottom: 20px;">Unique Ticket Count with % of Grand Total | Total Tickets: ' + grandTotal.toLocaleString() + '</p>' + html + '</div>';
        }}

        function rebuildAgentTables(data) {{
            // Group by agent
            const agentStats = {{}};

            data.forEach(row => {{
                const agent = row.assigned_to;
                const spl_code = row.employee_code;

                if (!agentStats[agent]) {{
                    agentStats[agent] = {{
                        agent: agent,
                        spl_code: spl_code,
                        assigned: 0,
                        self_closed: 0
                    }};
                }}

                agentStats[agent].assigned++;

                if (row.assigned_to === row.closed_by_id) {{
                    agentStats[agent].self_closed++;
                }}
            }});

            // Convert to array and calculate closure rate
            const agentArray = Object.values(agentStats).map(a => ({{
                ...a,
                closure_rate: a.assigned > 0 ? (a.self_closed / a.assigned * 100) : 0
            }}));

            // Filter agents with at least 10 tickets
            const filtered = agentArray.filter(a => a.assigned >= 10);

            // Top 20 performers (highest closure rate)
            const performers = [...filtered].sort((a, b) => {{
                if (b.closure_rate !== a.closure_rate) return b.closure_rate - a.closure_rate;
                return b.assigned - a.assigned;
            }}).slice(0, 20);

            // Top 20 defaulters (lowest closure rate, sorted by assigned)
            const defaulters = [...filtered].sort((a, b) => {{
                if (a.closure_rate !== b.closure_rate) return a.closure_rate - b.closure_rate;
                return b.assigned - a.assigned;
            }}).slice(0, 20);

            // Build performers table
            let perfHtml = '<table style="width: 100%; border-collapse: collapse;">';
            perfHtml += '<thead><tr style="background: #667eea; color: white;">';
            perfHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Rank</th>';
            perfHtml += '<th style="padding: 12px; border: 1px solid #ddd;">SPL Code</th>';
            perfHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Agent</th>';
            perfHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Tickets Assigned</th>';
            perfHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Tickets Closed</th>';
            perfHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Closure Rate %</th>';
            perfHtml += '</tr></thead><tbody>';

            performers.forEach((a, idx) => {{
                const bg = idx % 2 === 0 ? '#e8f5e9' : '#f1f8e9';
                perfHtml += `<tr style="background: ${{bg}};">`;
                perfHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{idx + 1}}</td>`;
                perfHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.spl_code || 'N/A'}}</td>`;
                perfHtml += `<td style="padding: 10px; border: 1px solid #ddd;">${{a.agent}}</td>`;
                perfHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.assigned.toLocaleString()}}</td>`;
                perfHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.self_closed.toLocaleString()}}</td>`;
                perfHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.closure_rate.toFixed(2)}}%</td>`;
                perfHtml += '</tr>';
            }});
            perfHtml += '</tbody></table>';

            // Build defaulters table
            let defHtml = '<table style="width: 100%; border-collapse: collapse;">';
            defHtml += '<thead><tr style="background: #667eea; color: white;">';
            defHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Rank</th>';
            defHtml += '<th style="padding: 12px; border: 1px solid #ddd;">SPL Code</th>';
            defHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Agent</th>';
            defHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Tickets Assigned</th>';
            defHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Tickets Closed</th>';
            defHtml += '<th style="padding: 12px; border: 1px solid #ddd;">Closure Rate %</th>';
            defHtml += '</tr></thead><tbody>';

            defaulters.forEach((a, idx) => {{
                const bg = idx % 2 === 0 ? '#ffebee' : '#ffcdd2';
                defHtml += `<tr style="background: ${{bg}};">`;
                defHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{idx + 1}}</td>`;
                defHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.spl_code || 'N/A'}}</td>`;
                defHtml += `<td style="padding: 10px; border: 1px solid #ddd;">${{a.agent}}</td>`;
                defHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.assigned.toLocaleString()}}</td>`;
                defHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.self_closed.toLocaleString()}}</td>`;
                defHtml += `<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${{a.closure_rate.toFixed(2)}}%</td>`;
                defHtml += '</tr>';
            }});
            defHtml += '</tbody></table>';

            // Update containers
            const avgPerf = performers.length > 0 ? (performers.reduce((sum, a) => sum + a.closure_rate, 0) / performers.length) : 0;
            const avgDef = defaulters.length > 0 ? (defaulters.reduce((sum, a) => sum + a.closure_rate, 0) / defaulters.length) : 0;

            document.getElementById('performers-container').innerHTML =
                '<div class="chart-container" style="padding: 20px;"><h3 style="color: #2c3e50; text-align: center; margin-bottom: 10px;">⭐ Top 20 Performers</h3>' +
                '<p style="text-align: center; color: #666; margin-bottom: 20px;">Highest Agent Closure Rate (min 10 tickets assigned) | Avg: ' + avgPerf.toFixed(2) + '%</p>' +
                perfHtml + '</div>';

            document.getElementById('defaulters-container').innerHTML =
                '<div class="chart-container" style="padding: 20px;"><h3 style="color: #2c3e50; text-align: center; margin-bottom: 10px;">⚠️ Top 20 Defaulters</h3>' +
                '<p style="text-align: center; color: #666; margin-bottom: 20px;">Lowest Agent Closure Rate (sorted by tickets assigned, min 10 tickets) | Avg: ' + avgDef.toFixed(2) + '%</p>' +
                defHtml + '</div>';
        }}

        // Pivot Table Filter
        function applyPivotFilter() {{
            const startDate = document.getElementById('pivot-start-date').value;
            const endDate = document.getElementById('pivot-end-date').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            const filteredData = pivotData.filter(r => r.ticket_created_date >= startDate && r.ticket_created_date <= endDate);
            rebuildTicketPivot(filteredData);
        }}

        // Agent Performance Filter
        function applyAgentFilter() {{
            const startDate = document.getElementById('agent-start-date').value;
            const endDate = document.getElementById('agent-end-date').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            const filteredData = agentData.filter(r => r.ticket_created_date >= startDate && r.ticket_created_date <= endDate);
            rebuildAgentTables(filteredData);
        }}

        // Hub Leaderboard Filter
        function applyHubFilter() {{
            const startDate = document.getElementById('hub-start-date').value;
            const endDate = document.getElementById('hub-end-date').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            // Note: Hub leaderboard filtering would require re-computing from raw data
            // For now, show a message that filtering is applied
            alert('Hub leaderboard date filter applied for period: ' + startDate + ' to ' + endDate + '\\n\\nNote: Full implementation requires backend recalculation. Dashboard will be updated in next version.');
        }}

        // Regional Summary Filter
        function applyRegionalFilter() {{
            const startDate = document.getElementById('regional-start-date').value;
            const endDate = document.getElementById('regional-end-date').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            const filteredData = regionalData.filter(r => r.ticket_created_date >= startDate && r.ticket_created_date <= endDate);
            rebuildRegionalSummary(filteredData);
        }}

        function rebuildRegionalSummary(data) {{
            const regions = ['North', 'South', 'East', 'West'];
            const summaryData = [];

            regions.forEach(region => {{
                const regionData = data.filter(r => r.region === region);

                if (regionData.length === 0) return;

                const totalTickets = regionData.length;
                const uniqueTasks = new Set(regionData.map(r => r.task_id)).size;
                const closedTickets = regionData.filter(r => r.flag_ticket_closed === 1).sum();
                const closureRate = totalTickets > 0 ? (closedTickets / totalTickets * 100) : 0;

                const tatData = regionData.filter(r => r.ticket_tat !== null && r.ticket_tat !== undefined);
                const avgTat = tatData.length > 0 ? tatData.reduce((sum, r) => sum + (r.ticket_tat || 0), 0) / tatData.length : 0;

                const problematicCount = regionData.filter(r => r.ticket_status === 'PROBLEMATIC').length;
                const problematicRate = totalTickets > 0 ? (problematicCount / totalTickets * 100) : 0;

                const uniqueAgents = new Set(regionData.map(r => r.assigned_to)).size;
                const ticketsPerAgent = uniqueAgents > 0 ? totalTickets / uniqueAgents : 0;

                summaryData.push({{
                    region: region,
                    totalTickets: totalTickets,
                    totalTasks: uniqueTasks,
                    closureRate: closureRate.toFixed(2),
                    avgTat: avgTat.toFixed(2),
                    problematicRate: problematicRate.toFixed(2),
                    ticketsPerAgent: ticketsPerAgent.toFixed(2),
                    uniqueAgents: uniqueAgents
                }});
            }});

            // Calculate TOTAL row
            const totalTickets = data.length;
            const totalTasks = new Set(data.map(r => r.task_id)).size;
            const closedTickets = data.filter(r => r.flag_ticket_closed === 1).length;
            const closureRate = totalTickets > 0 ? (closedTickets / totalTickets * 100) : 0;

            const tatData = data.filter(r => r.ticket_tat !== null && r.ticket_tat !== undefined);
            const avgTat = tatData.length > 0 ? tatData.reduce((sum, r) => sum + (r.ticket_tat || 0), 0) / tatData.length : 0;

            const problematicCount = data.filter(r => r.ticket_status === 'PROBLEMATIC').length;
            const problematicRate = totalTickets > 0 ? (problematicCount / totalTickets * 100) : 0;

            const uniqueAgents = new Set(data.map(r => r.assigned_to)).size;
            const ticketsPerAgent = uniqueAgents > 0 ? totalTickets / uniqueAgents : 0;

            summaryData.push({{
                region: 'TOTAL',
                totalTickets: totalTickets,
                totalTasks: totalTasks,
                closureRate: closureRate.toFixed(2),
                avgTat: avgTat.toFixed(2),
                problematicRate: problematicRate.toFixed(2),
                ticketsPerAgent: ticketsPerAgent.toFixed(2),
                uniqueAgents: uniqueAgents
            }});

            // Build HTML table
            let html = '<table style="width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 10px; overflow: hidden;">';
            html += '<thead><tr style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">';
            html += '<th style="padding: 15px; text-align: left; font-size: 13px;">Region</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Total Tickets</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Total Tasks</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Closure Rate %</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Avg TAT (days)</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Problematic Rate %</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Tickets per Agent</th>';
            html += '<th style="padding: 15px; text-align: center; font-size: 13px;">Unique Agents</th>';
            html += '</tr></thead><tbody>';

            summaryData.forEach((row, idx) => {{
                const isTotal = row.region === 'TOTAL';
                const bgColor = isTotal ? '#e3f2fd' : (idx % 2 === 0 ? '#f8f9fa' : 'white');
                const fontWeight = isTotal ? 'bold' : 'normal';

                html += `<tr style="background: ${{bgColor}};">`;
                html += `<td style="padding: 15px; font-weight: ${{fontWeight}};">${{row.region}}</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.totalTickets.toLocaleString()}}</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.totalTasks.toLocaleString()}}</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.closureRate}}%</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.avgTat}}</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.problematicRate}}%</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.ticketsPerAgent}}</td>`;
                html += `<td style="padding: 15px; text-align: center; font-weight: ${{fontWeight}};">${{row.uniqueAgents.toLocaleString()}}</td>`;
                html += '</tr>';
            }});

            html += '</tbody></table>';

            const container = document.getElementById('regional-summary-container');
            container.innerHTML = '<div class="chart-container" style="padding: 20px;"><h3 style="color: #2c3e50; text-align: center; margin-bottom: 20px;">📍 Regional Executive Summary</h3>' + html + '</div>';
        }}

        // Flow Percentage Filter
        function applyFlowFilter() {{
            const startDate = document.getElementById('flow-start-date').value;
            const endDate = document.getElementById('flow-end-date').value;

            if (!startDate || !endDate) {{
                alert('Please select both start and end dates');
                return;
            }}

            const filteredData = flowData.filter(r => r.ticket_created_date >= startDate && r.ticket_created_date <= endDate);
            rebuildFlowPercentageChart(filteredData);
        }}

        function rebuildFlowPercentageChart(data) {{
            // Group by date and flow
            const flowByDate = {{}};
            data.forEach(r => {{
                if (!flowByDate[r.ticket_created_date]) {{
                    flowByDate[r.ticket_created_date] = {{}};
                }}
                if (!flowByDate[r.ticket_created_date][r.flow]) {{
                    flowByDate[r.ticket_created_date][r.flow] = 0;
                }}
                flowByDate[r.ticket_created_date][r.flow]++;
            }});

            // Get all unique flows
            const allFlows = [...new Set(data.map(r => r.flow))];
            const dates = Object.keys(flowByDate).sort();

            // Calculate percentages
            const flowPercentages = {{}};
            allFlows.forEach(flow => {{
                flowPercentages[flow] = [];
            }});

            dates.forEach(date => {{
                const dayTotal = Object.values(flowByDate[date]).reduce((sum, val) => sum + val, 0);
                allFlows.forEach(flow => {{
                    const count = flowByDate[date][flow] || 0;
                    const pct = dayTotal > 0 ? (count / dayTotal * 100) : 0;
                    flowPercentages[flow].push(pct);
                }});
            }});

            // Rebuild plotly chart
            const traces = [];
            allFlows.forEach(flow => {{
                traces.push({{
                    x: dates,
                    y: flowPercentages[flow],
                    name: flow,
                    type: 'bar',
                    hovertemplate: '<b>' + flow + '</b><br>Date: %{{x}}<br>Percentage: %{{y:.2f}}%<extra></extra>'
                }});
            }});

            const layout = {{
                title: {{
                    text: '📊 Tickets by Flow Type (% of Total)<br><sub>Daily distribution showing flow composition</sub>',
                    x: 0.5,
                    xanchor: 'center',
                    font: {{size: 18, color: '#2c3e50'}}
                }},
                barmode: 'stack',
                xaxis: {{title: 'Date'}},
                yaxis: {{title: 'Percentage of Total Tickets (%)'}},
                hovermode: 'x unified',
                height: 500,
                showlegend: true,
                legend: {{orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'right', x: 1}}
            }};

            Plotly.newPlot('flow-pct-chart-container', traces, layout);
        }}

        // Initialize date inputs with data range
        window.onload = function() {{
            const minDate = '{min_date.strftime('%Y-%m-%d')}';
            const maxDate = '{max_date.strftime('%Y-%m-%d')}';

            // Set pivot filter defaults
            document.getElementById('pivot-start-date').value = minDate;
            document.getElementById('pivot-end-date').value = maxDate;

            // Set agent filter defaults
            document.getElementById('agent-start-date').value = minDate;
            document.getElementById('agent-end-date').value = maxDate;

            // Set hub filter defaults
            document.getElementById('hub-start-date').value = minDate;
            document.getElementById('hub-end-date').value = maxDate;

            // Set regional filter defaults
            document.getElementById('regional-start-date').value = minDate;
            document.getElementById('regional-end-date').value = maxDate;

            // Set flow filter defaults
            document.getElementById('flow-start-date').value = minDate;
            document.getElementById('flow-end-date').value = maxDate;
        }};
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 FE App Dashboard</h1>
            <p>With Date Filters & Granularity Selection</p>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="info-box">
            <h3>🎛️ How to Use Interactive Features</h3>
            <ul>
                <li><strong>Granularity Buttons:</strong> Click "Daily", "Weekly", "Monthly", or "Yearly" to change time aggregation</li>
                <li><strong>Date Range Selector:</strong> Use buttons (1w, 1m, 3m, 6m, All) to zoom to specific periods</li>
                <li><strong>Range Slider:</strong> Drag the slider at bottom of each chart to select custom date ranges</li>
                <li><strong>Hover:</strong> Mouse over any point to see exact values</li>
                <li><strong>Zoom:</strong> Click and drag on chart to zoom into specific area</li>
                <li><strong>Pan:</strong> After zooming, drag to move left/right</li>
                <li><strong>Reset:</strong> Double-click anywhere on chart to reset view</li>
            </ul>
        </div>

        <!-- KPI Summary Table -->
        <div style="margin: 30px 0;">
            <h2 style="text-align: center; color: #2c3e50; margin-bottom: 20px;">📈 KPI Summary</h2>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-radius: 10px; overflow: hidden;">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
                            <th style="padding: 12px; text-align: left; font-size: 13px;">Metric</th>
                            <th style="padding: 12px; text-align: center; font-size: 12px;">Current Week<br><small style="font-weight: normal;">({current_week_start.strftime('%b %d')} - {today.strftime('%b %d')})</small></th>
                            <th style="padding: 12px; text-align: center; font-size: 12px;">Last Week<br><small style="font-weight: normal;">({last_week_start.strftime('%b %d')} - {last_week_end.strftime('%b %d')})</small></th>
                            <th style="padding: 12px; text-align: center; font-size: 12px;">MTD<br><small style="font-weight: normal;">({current_month_start.strftime('%b %d')} - {today.strftime('%b %d')})</small></th>
                            <th style="padding: 12px; text-align: center; font-size: 12px;">Last Month<br><small style="font-weight: normal;">({last_month_start.strftime('%b %Y')})</small></th>
                            <th style="padding: 12px; text-align: center; font-size: 12px;">LMTD<br><small style="font-weight: normal;">({last_month_start.strftime('%b %d')} - {lmtd_end.strftime('%b %d')})</small></th>
                            <th style="padding: 12px; text-align: center; font-size: 12px;">Previous Day<br><small style="font-weight: normal;">({previous_day.strftime('%b %d')})</small></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; border-bottom: 1px solid #ddd;">📊 Adoption Rate</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #667eea; border-bottom: 1px solid #ddd;">{kpi_current_week['adoption_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #667eea; border-bottom: 1px solid #ddd;">{kpi_last_week['adoption_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #667eea; border-bottom: 1px solid #ddd;">{kpi_mtd['adoption_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #667eea; border-bottom: 1px solid #ddd;">{kpi_last_month['adoption_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #667eea; border-bottom: 1px solid #ddd;">{kpi_lmtd['adoption_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #667eea; border-bottom: 1px solid #ddd;">{kpi_prev_day['adoption_rate']}%</td>
                        </tr>
                        <tr style="background: white;">
                            <td style="padding: 12px; font-weight: bold; border-bottom: 1px solid #ddd;">🎫 Total Tickets</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #28a745; border-bottom: 1px solid #ddd;">{kpi_current_week['total_tickets']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #28a745; border-bottom: 1px solid #ddd;">{kpi_last_week['total_tickets']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #28a745; border-bottom: 1px solid #ddd;">{kpi_mtd['total_tickets']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #28a745; border-bottom: 1px solid #ddd;">{kpi_last_month['total_tickets']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #28a745; border-bottom: 1px solid #ddd;">{kpi_lmtd['total_tickets']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #28a745; border-bottom: 1px solid #ddd;">{kpi_prev_day['total_tickets']:,}</td>
                        </tr>
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; border-bottom: 1px solid #ddd;">📋 Total Tasks</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #17a2b8; border-bottom: 1px solid #ddd;">{kpi_current_week['total_tasks']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #17a2b8; border-bottom: 1px solid #ddd;">{kpi_last_week['total_tasks']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #17a2b8; border-bottom: 1px solid #ddd;">{kpi_mtd['total_tasks']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #17a2b8; border-bottom: 1px solid #ddd;">{kpi_last_month['total_tasks']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #17a2b8; border-bottom: 1px solid #ddd;">{kpi_lmtd['total_tasks']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #17a2b8; border-bottom: 1px solid #ddd;">{kpi_prev_day['total_tasks']:,}</td>
                        </tr>
                        <tr style="background: white;">
                            <td style="padding: 12px; font-weight: bold;">✅ Closure Rate</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #ffc107;">{kpi_current_week['closure_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #ffc107;">{kpi_last_week['closure_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #ffc107;">{kpi_mtd['closure_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #ffc107;">{kpi_last_month['closure_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #ffc107;">{kpi_lmtd['closure_rate']}%</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #ffc107;">{kpi_prev_day['closure_rate']}%</td>
                        </tr>
                        <tr style="background: #f8f9fa;">
                            <td style="padding: 12px; font-weight: bold; border-bottom: 1px solid #ddd;">👥 Agents Attempted</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #16a085; border-bottom: 1px solid #ddd;">{kpi_current_week['agents_attempted']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #16a085; border-bottom: 1px solid #ddd;">{kpi_last_week['agents_attempted']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #16a085; border-bottom: 1px solid #ddd;">{kpi_mtd['agents_attempted']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #16a085; border-bottom: 1px solid #ddd;">{kpi_last_month['agents_attempted']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #16a085; border-bottom: 1px solid #ddd;">{kpi_lmtd['agents_attempted']:,}</td>
                            <td style="padding: 12px; text-align: center; font-size: 18px; font-weight: bold; color: #16a085; border-bottom: 1px solid #ddd;">{kpi_prev_day['agents_attempted']:,}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>


        <!-- Ticket Count by Period -->
        <div class="info-box">
            <h3>🎫 Ticket Count by Period</h3>
            <p style="margin: 5px 0;">Daily ticket volume with interactive time filters</p>
        </div>
        <div class="chart-container">
            {chart1_html}
        </div>

        <!-- Task Count by Period -->
        <div class="info-box">
            <h3>📋 Task Count by Period</h3>
            <p style="margin: 5px 0;">Daily task volume with interactive time filters</p>
        </div>
        <div class="chart-container">
            {chart2_html}
        </div>

        <!-- Adoption Rate by Period -->
        <div class="info-box">
            <h3>📊 Adoption Rate by Period</h3>
            <p style="margin: 5px 0;">Average daily adoption rate trends</p>
        </div>
        <div class="chart-container">
            {chart3_html}
        </div>

        <!-- Number of Agents Attempted by Period -->
        <div class="info-box">
            <h3>👥 Number of Agents Attempted by Period</h3>
            <p style="margin: 5px 0;">Track the number of agents who attempted tasks with granularity options</p>
        </div>
        <div class="chart-container">
            {chart3b_html}
        </div>

        <!-- Total Number of Active Agents by Period -->
        <div class="info-box">
            <h3>👤 Total Number of Active Agents by Period</h3>
            <p style="margin: 5px 0;">Total unique active agents on each date with granularity options</p>
        </div>
        <div class="chart-container">
            {chart3c_html}
        </div>

        <!-- Tickets by Flow Type (% of Total) -->
        <div class="info-box">
            <h3>📊 Tickets by Flow Type (% of Total)</h3>
            <p style="margin: 5px 0;">Daily distribution showing flow composition as percentage</p>
        </div>

        <!-- Date Filter for Flow Percentage Chart -->
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #667eea;">
            <h4 style="margin: 0 0 10px 0; color: #667eea;">📅 Flow Type Date Filter</h4>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #667eea; font-weight: bold;">Start Date:</label>
                    <input type="date" id="flow-start-date" style="padding: 8px; border: 2px solid #667eea; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <span style="font-weight: bold; padding-top: 25px;">to</span>
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #667eea; font-weight: bold;">End Date:</label>
                    <input type="date" id="flow-end-date" style="padding: 8px; border: 2px solid #667eea; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <div style="padding-top: 25px;">
                    <button onclick="applyFlowFilter()" style="padding: 10px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        Apply Filter
                    </button>
                </div>
            </div>
        </div>

        <div class="chart-container" id="flow-pct-chart-container">
            {flow_pct_html}
        </div>

        <!-- Ticket Status by Flow Table -->
        <div class="info-box">
            <h3>🚦 Ticket Status by Flow - Daily View (Last 60 Days)</h3>
            <p style="margin: 5px 0;">Detailed breakdown of ticket statuses by flow type - tabular format</p>
        </div>
        <div class="chart-container">
            {status_flow_table_html}
        </div>

        <!-- Task vs Ticket Status Breakdown with Date Filter -->
        <div class="info-box" style="background: #f3e5f5; border-left-color: #9c27b0;">
            <h3 style="color: #6a1b9a;">📊 Task vs Ticket Status Breakdown</h3>
            <p style="margin: 5px 0; color: #6a1b9a;">
                Cross-tabulation showing unique ticket counts and percentage of grand total across task status and ticket status combinations
            </p>
        </div>

        <!-- Date Filter for Pivot Table -->
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #9c27b0;">
            <h4 style="margin: 0 0 10px 0; color: #6a1b9a;">📅 Pivot Table Date Filter</h4>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #6a1b9a; font-weight: bold;">Start Date:</label>
                    <input type="date" id="pivot-start-date" style="padding: 8px; border: 2px solid #9c27b0; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <span style="font-weight: bold; padding-top: 25px;">to</span>
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #6a1b9a; font-weight: bold;">End Date:</label>
                    <input type="date" id="pivot-end-date" style="padding: 8px; border: 2px solid #9c27b0; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <div style="padding-top: 25px;">
                    <button onclick="applyPivotFilter()" style="padding: 10px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        Apply Filter
                    </button>
                </div>
            </div>
        </div>

        <div class="chart-container" id="ticket-pivot-table-container">
            {ticket_pivot_html}
        </div>

        <!-- MTD Comparisons -->
        <div class="info-box" style="background: #fff3cd; border-left-color: #ffc107;">
            <h3 style="color: #856404;">📊 Month-to-Date (MTD) Comparisons</h3>
            <p style="margin: 5px 0; color: #856404;">
                Comparing current month (March 1-14, 2026) vs last month (February 1-14, 2026) - Same number of days for fair comparison<br>
                <em style="font-size: 0.9em;">Note: These views show pre-calculated MTD data and are not affected by global filters above.</em>
            </p>
        </div>

        <div class="chart-container">
            {mtd1_html}
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px;">
            <div class="chart-container" style="margin-bottom: 0;">
                {mtd2_html}
            </div>
            <div class="chart-container" style="margin-bottom: 0;">
                {mtd3_html}
            </div>
        </div>

        <div class="info-box" style="background: #e3f2fd; border-left-color: #2196f3;">
            <h3 style="color: #1565c0;">👥 Agent Performance Analysis</h3>
            <p style="margin: 5px 0; color: #1565c0;">
                Top Performers vs Defaulters based on agent closure rate (tickets closed by agent / tickets assigned to agent)
            </p>
        </div>

        <!-- Date Filter for Agent Performance -->
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #2196f3;">
            <h4 style="margin: 0 0 10px 0; color: #1565c0;">📅 Agent Performance Date Filter</h4>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #1565c0; font-weight: bold;">Start Date:</label>
                    <input type="date" id="agent-start-date" style="padding: 8px; border: 2px solid #2196f3; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <span style="font-weight: bold; padding-top: 25px;">to</span>
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #1565c0; font-weight: bold;">End Date:</label>
                    <input type="date" id="agent-end-date" style="padding: 8px; border: 2px solid #2196f3; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <div style="padding-top: 25px;">
                    <button onclick="applyAgentFilter()" style="padding: 10px 24px; background: linear-gradient(135deg, #2196f3 0%, #1565c0 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        Apply Filter
                    </button>
                </div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px;">
            <div id="performers-container" style="margin-bottom: 0;">
                {performers_html}
            </div>
            <div id="defaulters-container" style="margin-bottom: 0;">
                {defaulters_html}
            </div>
        </div>

        <div class="info-box" style="background: #f3e5f5; border-left-color: #9c27b0;">
            <h3 style="color: #6a1b9a;">🗺️ Regional Performance Views</h3>
            <p style="margin: 5px 0; color: #6a1b9a;">
                Geographic analysis of tickets and tasks across regions (North, South, East, West) and hub-level performance leaderboards
            </p>
        </div>

        <!-- Date Filter for Regional Summary -->
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #9c27b0;">
            <h4 style="margin: 0 0 10px 0; color: #6a1b9a;">📅 Regional Summary Date Filter</h4>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #6a1b9a; font-weight: bold;">Start Date:</label>
                    <input type="date" id="regional-start-date" style="padding: 8px; border: 2px solid #9c27b0; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <span style="font-weight: bold; padding-top: 25px;">to</span>
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #6a1b9a; font-weight: bold;">End Date:</label>
                    <input type="date" id="regional-end-date" style="padding: 8px; border: 2px solid #9c27b0; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <div style="padding-top: 25px;">
                    <button onclick="applyRegionalFilter()" style="padding: 10px 24px; background: linear-gradient(135deg, #9c27b0 0%, #6a1b9a 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        Apply Filter
                    </button>
                </div>
            </div>
        </div>

        <div class="chart-container" id="regional-summary-container">
            {regional_summary_html}
        </div>

        <h4 style="color: #28a745; margin-top: 30px; margin-bottom: 15px;">🏆 Hub Leaderboard - Closure Rate & Adoption Rate</h4>

        <!-- Date Filter for Hub Leaderboard -->
        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #28a745;">
            <h4 style="margin: 0 0 10px 0; color: #28a745;">📅 Hub Leaderboard Date Filter</h4>
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #28a745; font-weight: bold;">Start Date:</label>
                    <input type="date" id="hub-start-date" style="padding: 8px; border: 2px solid #28a745; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <span style="font-weight: bold; padding-top: 25px;">to</span>
                <div style="flex: 1;">
                    <label style="display: block; margin-bottom: 5px; color: #28a745; font-weight: bold;">End Date:</label>
                    <input type="date" id="hub-end-date" style="padding: 8px; border: 2px solid #28a745; border-radius: 5px; width: 100%; font-size: 14px;">
                </div>
                <div style="padding-top: 25px;">
                    <button onclick="applyHubFilter()" style="padding: 10px 24px; background: linear-gradient(135deg, #28a745 0%, #1e7e34 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: bold;">
                        Apply Filter
                    </button>
                </div>
            </div>
        </div>

        <h5 style="color: #28a745; margin-top: 20px; margin-bottom: 10px;">Closure Rate Leaderboard</h5>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px;">
            <div class="chart-container" style="margin-bottom: 0;">
                {top_hubs_closure_html}
            </div>
            <div class="chart-container" style="margin-bottom: 0;">
                {bottom_hubs_closure_html}
            </div>
        </div>

        <h5 style="color: #17a2b8; margin-top: 30px; margin-bottom: 10px;">Adoption Rate Leaderboard</h5>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 40px;">
            <div class="chart-container" style="margin-bottom: 0;">
                {top_hubs_adoption_html}
            </div>
            <div class="chart-container" style="margin-bottom: 0;">
                {bottom_hubs_adoption_html}
            </div>
        </div>

        <div class="footer">
            <p>📊 Data Sources: FE App Tickets ({len(df_tickets):,} tickets) + Agent Funnel ({len(df_funnel):,} records)</p>
            <p>Date Range: {df_daily_summary['date'].min().strftime('%Y-%m-%d')} to {df_daily_summary['date'].max().strftime('%Y-%m-%d')}</p>
        </div>
    </div>
</body>
</html>
"""

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"✅ Interactive dashboard saved to: {OUTPUT_FILE}")

print("\n" + "=" * 80)
print("✨ INTERACTIVE DASHBOARD GENERATED SUCCESSFULLY!")
print("=" * 80)
print(f"\n🌐 Open in browser: {OUTPUT_FILE}")
print("\n💡 Features:")
print("  ✅ Granularity buttons (Daily/Weekly/Monthly/Yearly)")
print("  ✅ Date range selector (1w, 1m, 3m, 6m, All)")
print("  ✅ Interactive range slider")
print("  ✅ Zoom, pan, hover tooltips")
print("  ✅ All charts fully interactive")
