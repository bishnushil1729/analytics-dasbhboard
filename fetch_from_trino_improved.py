#!/usr/bin/env python3
"""
Improved Trino fetch with custom filters and date range control
Uses pos_ae_ticket_funnel_v1 but with our own query logic for flexibility
"""

import trino
import pandas as pd
import os
from datetime import datetime, timedelta

# Trino Connection Configuration
TRINO_HOST = 'trino-dev-gateway-router-looker.de.razorpay.com'
TRINO_PORT = 443
TRINO_USER = 'duvvuri.praveen@razorpay.com'
TRINO_PASSWORD = os.environ.get('TRINO_PASSWORD', '***REMOVED***')
TRINO_CATALOG = 'hive'
TRINO_SCHEMA = 'aggregate_pa'

# Output configuration
BASE_DIR = os.path.dirname(__file__) if os.path.dirname(__file__) else '.'
OUTPUT_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "latest_hive_data.csv")

# Configuration: Date range for fetching (default: last 6 months)
# This ensures we only fetch relevant data and queries run faster
MONTHS_TO_FETCH = 6

print("=" * 80)
print("FETCHING TICKET DATA FROM TRINO - IMPROVED VERSION")
print("=" * 80)
print(f"Host: {TRINO_HOST}:{TRINO_PORT}")
print(f"User: {TRINO_USER}")
print(f"Catalog: {TRINO_CATALOG}")
print(f"Schema: {TRINO_SCHEMA}")
print(f"Date Range: Last {MONTHS_TO_FETCH} months")
print(f"Output: {OUTPUT_FILE}")
print()

# Calculate date range
end_date = datetime.now().date()
start_date = end_date - timedelta(days=MONTHS_TO_FETCH * 30)

print(f"📅 Fetching tickets created between {start_date} and {end_date}")
print()

# Custom query with filters and optimizations
QUERY = f"""
SELECT *
FROM hive.aggregate_pa.pos_ae_ticket_funnel_v1
WHERE
    -- DATE FILTER: Only fetch recent data for efficiency
    ticket_created_date >= DATE '{start_date}'
    AND ticket_created_date <= DATE '{end_date}'

    -- FLOW FILTER: Only relevant POS flows
    AND flow IN ('INSTALLATION', 'BREAKFIX', 'UPGRADE', 'DEINSTALLATION', 'MIGRATION')

    -- QUALITY FILTER: Only tickets we should consider
    AND ticket_consider_flag = 1

ORDER BY ticket_created_date DESC, ticket_created_at DESC
"""

try:
    print("📡 Connecting to Trino...")
    conn = trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        http_scheme='https',
        auth=trino.auth.BasicAuthentication(TRINO_USER, TRINO_PASSWORD),
        catalog=TRINO_CATALOG,
        schema=TRINO_SCHEMA,
    )

    cursor = conn.cursor()
    print("✅ Connected successfully!")

    # Execute query
    print(f"\n🔍 Executing optimized query...")
    print(f"   (With date range filter for last {MONTHS_TO_FETCH} months)")

    start_time = datetime.now()
    cursor.execute(QUERY)

    # Fetch column names
    columns = [desc[0] for desc in cursor.description]
    print(f"\n✅ Query executed successfully!")
    print(f"   Columns: {len(columns)}")

    # Fetch all data
    print(f"\n⏳ Fetching data...")
    rows = cursor.fetchall()

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"✅ Fetched {len(rows):,} rows in {elapsed:.1f} seconds")

    # Create DataFrame
    df = pd.DataFrame(rows, columns=columns)

    # Data quality checks
    print(f"\n📊 Data Summary:")
    print(f"   Total tickets: {len(df):,}")
    print(f"   Date range: {df['ticket_created_date'].min()} to {df['ticket_created_date'].max()}")
    print(f"   Unique flows: {df['flow'].nunique()}")

    flow_breakdown = df['flow'].value_counts().to_dict()
    for flow, count in sorted(flow_breakdown.items()):
        print(f"      - {flow}: {count:,}")

    print(f"   Closed tickets: {df['flag_ticket_closed'].sum():,} ({df['flag_ticket_closed'].sum() / len(df) * 100:.1f}%)")
    print(f"   Unique agents: {df['employee_code'].nunique():,}")
    print(f"   Unique hubs: {df['hub'].nunique():,}")

    # Additional stats
    print(f"\n📈 Additional Stats:")
    print(f"   Tasks assigned: {df['flag_task_assigned'].sum():,}")
    print(f"   Tasks started: {df['flag_task_started'].sum():,}")
    print(f"   Tickets with attempts: {(df['cnt_attempts'] > 0).sum():,}")

    # Average TAT for closed tickets
    closed_df = df[df['flag_ticket_closed'] == 1]
    if len(closed_df) > 0 and 'ticket_tat' in df.columns:
        avg_tat = closed_df['ticket_tat'].mean()
        if pd.notna(avg_tat):
            print(f"   Average TAT (closed tickets): {avg_tat / 24:.1f} days")

    # Save to CSV
    print(f"\n💾 Saving to CSV...")
    df.to_csv(OUTPUT_FILE, index=False)

    file_size_mb = os.path.getsize(OUTPUT_FILE) / (1024 * 1024)
    print(f"✅ Saved to: {OUTPUT_FILE}")
    print(f"   File size: {file_size_mb:.1f} MB")

    # Close connection
    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("✨ DATA FETCH COMPLETE!")
    print("=" * 80)

    print(f"\n💡 Benefits of this improved approach:")
    print(f"   ✅ Date range filter reduces query time and data size")
    print(f"   ✅ Flow filter ensures only relevant tickets")
    print(f"   ✅ Quality filter (ticket_consider_flag) removes invalid tickets")
    print(f"   ✅ Can easily modify filters without changing Airflow DAG")
    print(f"   ✅ Ordered by date for better data locality")

    print(f"\n⚙️  Customization options:")
    print(f"   • Change MONTHS_TO_FETCH to adjust date range")
    print(f"   • Add WHERE clauses for specific hubs/regions/agents")
    print(f"   • Add aggregations or transformations in the query")
    print(f"   • No dependency on Airflow DAG schedule!")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
