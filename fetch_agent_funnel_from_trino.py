#!/usr/bin/env python3
"""
Fetch Agent Funnel Data from Hive via Trino
"""

import trino
import pandas as pd
from datetime import datetime
import os

# Trino Connection Configuration
TRINO_HOST = 'trino-dev-gateway-router-looker.de.razorpay.com'
TRINO_PORT = 443
TRINO_USER = 'duvvuri.praveen@razorpay.com'
TRINO_PASSWORD = os.environ.get('TRINO_PASSWORD', '***REMOVED***')  # Use env var if available
TRINO_CATALOG = 'hive'
TRINO_SCHEMA = 'aggregate_pa'

# Output Files - use relative path for GitHub Actions
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "latest_agent_funnel_data.csv")

print("=" * 80)
print("FETCHING AGENT FUNNEL DATA FROM HIVE VIA TRINO")
print("=" * 80)

# Create connection
print(f"\n🔗 Connecting to Trino at {TRINO_HOST}:{TRINO_PORT}...")
print(f"   User: {TRINO_USER}")
print(f"   Catalog: {TRINO_CATALOG}")
print(f"   Schema: {TRINO_SCHEMA}")

try:
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

    print("✅ Connected to Trino!")

    # Execute query
    query = """
SELECT
    a.name AS agent_name,
    a.employee_code as spl_code,
    a.city,
    d.manager_name,
    d.manager_code,
    d.region,
    b.dt,
    COALESCE(c.logged_in, 0) AS logged_in_flag,
    COALESCE(c.attended, 0) AS attended_flag,
    COALESCE(c.attempted, 0) AS attempted_flag,
    COALESCE(c.closed, 0) AS closed_flag,
    c.last_updated_at

FROM realtime_prod_agent_service.agents AS a
LEFT JOIN (
    SELECT
        name AS manager_name,
        employee_code AS manager_code,
        CASE
            -- NORTH
            WHEN UPPER(state) IN (
                'DL', 'DELHI', 'HR', 'UP', 'RJ', 'CH', 'PB', 'UK'
            ) THEN 'North'

            -- SOUTH
            WHEN UPPER(state) IN (
                'TN', 'KA', 'KARNATAKA', 'KL', 'AP', 'TS', 'TG', 'PY'
            ) THEN 'South'

            -- EAST
            WHEN UPPER(state) IN (
                'WB', 'BR', 'OD', 'OR', 'JH', 'AR', 'AS'
            ) THEN 'East'

            -- WEST
            WHEN UPPER(state) IN (
                'MH', 'GJ', 'GA', 'DN', 'DD', 'MP', 'CG'
            ) THEN 'West'

            -- UNKNOWN / BAD DATA
            ELSE 'Other'
        END AS region
    FROM realtime_prod_agent_service.managers
    WHERE delta_partition_key >= '1970-01-01'
) d ON a.reporting_to = d.manager_code
CROSS JOIN (SELECT DISTINCT dt FROM aggregate_pa.pos_ae_login_funnel) AS b
LEFT JOIN aggregate_pa.pos_ae_login_funnel AS c
  ON a.employee_code = c.employee_code
  AND b.dt = c.dt
WHERE
    b.dt >= DATE_PARSE(a.joining_date, '%Y-%m-%d')
    AND status = 'ACTIVE'
    AND delta_partition_key >= '1970-01-01'
"""

    print(f"\n📊 Executing agent funnel query...")

    cursor.execute(query)

    # Fetch column names
    columns = [desc[0] for desc in cursor.description]

    # Fetch all data
    print("\n⏳ Fetching data...")
    rows = cursor.fetchall()

    print(f"✅ Retrieved {len(rows):,} rows")

    # Create DataFrame
    df = pd.DataFrame(rows, columns=columns)

    # Save to CSV
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"✅ Saved to: {OUTPUT_FILE}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\n📊 Agent Funnel Data:")
    print(f"   Rows: {len(df):,}")
    print(f"   Columns: {len(df.columns)}")
    print(f"\n📋 Column names:")
    for col in df.columns:
        print(f"   - {col}")

    if 'dt' in df.columns:
        print(f"\n📅 Date range: {df['dt'].min()} to {df['dt'].max()}")

    if 'spl_code' in df.columns:
        print(f"🧑 Unique agents: {df['spl_code'].nunique():,}")

    print(f"\n📁 File: {OUTPUT_FILE}")

    # Close connection
    cursor.close()
    conn.close()

    print("\n" + "=" * 80)
    print("✨ AGENT FUNNEL DATA FETCH COMPLETE!")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
