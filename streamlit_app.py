import streamlit as st
import subprocess
from pathlib import Path

# Page configuration
st.set_page_config(
    page_title="FE App Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom styling
st.markdown("""
    <style>
        .main {
            padding: 0;
        }
        iframe {
            border: none;
        }
    </style>
    """, unsafe_allow_html=True)

# Main content
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

# Read and display the HTML dashboard
try:
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Display the HTML dashboard
    st.components.v1.html(html_content, height=5000, scrolling=True)

except FileNotFoundError:
    st.error("❌ Dashboard HTML file not found. Please run simple_daily_dashboard_interactive.py first.")
except Exception as e:
    st.error(f"❌ Error loading dashboard: {e}")
