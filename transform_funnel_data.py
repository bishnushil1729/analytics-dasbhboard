#!/usr/bin/env python3
"""
Transform agent funnel data to match dashboard format
"""

import pandas as pd
import os

# Use relative paths for GitHub Actions
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
INPUT_FILE = os.path.join(DATA_DIR, "latest_agent_funnel_data.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "latest_funnel_transformed.csv")

print("=" * 80)
print("TRANSFORMING AGENT FUNNEL DATA")
print("=" * 80)

# Load data
print(f"\n📂 Loading data from: {INPUT_FILE}")
df = pd.read_csv(INPUT_FILE)
print(f"✅ Loaded {len(df):,} rows")

print(f"\n📋 Original columns:")
for col in df.columns:
    print(f"   - {col}")

# Transform to match dashboard format
print(f"\n🔄 Transforming data...")

df_transformed = pd.DataFrame({
    'agent_id': df['spl_code'],  # Use employee code as agent_id
    'dt': df['dt'],
    'logged_in': df['logged_in_flag'],
    'attended': df['attended_flag'],
    'attempted': df['attempted_flag'],
    'closed': df['closed_flag'],
    'agent_name': df['agent_name'],
    'city': df['city'],
    'manager_name': df['manager_name'],
    'manager_code': df['manager_code'],
    'region': df['region'],
    'last_updated_at': df['last_updated_at']
})

# Save transformed data
df_transformed.to_csv(OUTPUT_FILE, index=False)
print(f"✅ Saved transformed data to: {OUTPUT_FILE}")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"\n📊 Transformed Data:")
print(f"   Rows: {len(df_transformed):,}")
print(f"   Unique agents: {df_transformed['agent_id'].nunique():,}")
print(f"   Date range: {df_transformed['dt'].min()} to {df_transformed['dt'].max()}")

print(f"\n📋 Transformed columns:")
for col in df_transformed.columns:
    print(f"   - {col}")

print(f"\n📁 Output file: {OUTPUT_FILE}")

print("\n" + "=" * 80)
print("✨ TRANSFORMATION COMPLETE!")
print("=" * 80)
