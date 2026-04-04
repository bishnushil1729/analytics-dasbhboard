import streamlit as st
import subprocess
from pathlib import Path
import base64

# Page configuration
st.set_page_config(
    page_title="FE App Dashboard",
    page_icon="📊",
    layout="centered"
)

st.title("📊 FE App Dashboard")

# Check if HTML file exists, if not generate it
html_file = Path("simple_daily_dashboard_interactive.html")

if not html_file.exists():
    st.info("🔄 Generating dashboard... Please wait.")
    try:
        subprocess.run(["python", "simple_daily_dashboard_interactive.py"], check=True)
        st.success("✅ Dashboard generated successfully!")
    except subprocess.CalledProcessError as e:
        st.error(f"❌ Error generating dashboard: {e}")
        st.stop()

# Read the HTML file
try:
    with open(html_file, "rb") as f:
        html_bytes = f.read()

    # Create download button
    st.download_button(
        label="📥 Download Dashboard (HTML)",
        data=html_bytes,
        file_name="dashboard.html",
        mime="text/html",
        use_container_width=True
    )

    st.markdown("---")
    st.markdown("""
    ### 📖 How to use:
    1. Click the **"Download Dashboard"** button above
    2. Open the downloaded HTML file in your browser
    3. Enjoy the interactive dashboard with:
       - 📊 KPI metrics and trends
       - 📈 Interactive charts with zoom & pan
       - 🎛️ Granularity controls (Daily/Weekly/Monthly/Yearly)
       - 📅 Date range filters
       - 🗺️ Regional performance views
       - 📉 Top and bottom performers
    """)

    st.info("💡 The HTML file is self-contained - no internet connection needed to use it offline!")

except FileNotFoundError:
    st.error("❌ Dashboard HTML file not found.")
except Exception as e:
    st.error(f"❌ Error: {e}")
