import streamlit as st
import requests
import time
import json
from datetime import datetime

# Configure page
st.set_page_config(
    page_title="AI Research Assistant",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium look
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        background: linear-gradient(45deg, #4b6cb7 0%, #182848 100%);
        color: white;
        border: none;
        padding: 10px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        background: linear-gradient(45deg, #5c7ec9 0%, #1e335a 100%);
        color: white;
    }
    .status-card {
        padding: 1.5rem;
        border-radius: 12px;
        background: var(--secondary-background-color);
        border-left: 5px solid #4b6cb7;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        color: var(--text-color);
    }
    .step-card {
        padding: 0.8rem;
        border-radius: 8px;
        background: var(--background-color);
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        margin-bottom: 5px;
        font-size: 0.9rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        color: var(--text-color);
    }
    .report-card {
        padding: 2rem;
        border-radius: 15px;
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        color: var(--text-color);
    }
    h1, h2, h3 {
        color: var(--text-color) !important;
        font-family: 'Inter', sans-serif;
    }
    .stTextArea textarea {
        background: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
    }
</style>
""", unsafe_allow_html=True)

# API Base URL
BASE_URL = "https://ai-report-gen.onrender.com"  # Change if your API server is running elsewhere

def check_tool_health():
    try:
        response = requests.get("https://research-mcp-9mm5.onrender.com/health")
        return response.json().get("status") == "ok"
    except:
        return False

def check_health():
    try:
        response = requests.get(f"{BASE_URL}/health")
        return response.json().get("status") == "ok"
    except:
        return False

def submit_query(query):
    try:
        response = requests.post(f"{BASE_URL}/query", json={"query": query})
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_status(task_id):
    try:
        response = requests.get(f"{BASE_URL}/status", params={"task_id": task_id})
        return response.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_all_reports():
    try:
        response = requests.get(f"{BASE_URL}/report")
        return response.json().get("reports", [])
    except:
        return []

def cleanup_db():
    try:
        response = requests.post(f"{BASE_URL}/cleanup")
        return response.json().get("status") == "cleaned"
    except:
        return False

def cleanup_all_db():
    try:
        response = requests.post(f"{BASE_URL}/cleanup_all")
        return response.json().get("status") == "all_collections_cleaned"
    except:
        return False

# Sidebar
with st.sidebar:
    st.title("Settings & Status")
    
    health = check_health()
    if health:
        st.success("API Server: Online")
    else:
        st.error("API Server: Offline")
    
    tool_health = check_tool_health()
    if tool_health:
        st.success("Tool Source: Online")
    else:
        st.error("Tool Source: Offline")
        st.info("Make sure to run the FastAPI server first!")

    if st.button("🔄 Check Health"):
        st.rerun()

    st.divider()
    
    if st.button("🗑️ Cleanup Cache"):
        if cleanup_db():
            st.warning("Database and tasks cleared!")
        else:
            st.error("Failed to cleanup.")
            
    st.divider()
    if st.button("🧹 Cleanup All Data"):
        if cleanup_all_db():
            st.warning("All database collections cleared!")
        else:
            st.error("Failed to cleanup all data.")

    st.divider()
    st.markdown("### Stored Reports")
    reports = get_all_reports()
    if reports:
        for i, report_obj in enumerate(reports):
            # Use the query as the title for the sidebar button
            query_text = report_obj.get("query", "Untitled")
            title = query_text[:30] + "..." if len(query_text) > 30 else query_text
            
            if st.button(f"📄 {title}", key=f"report_{i}"):
                st.session_state.current_report = report_obj.get("report")
    else:
        st.write("No reports found.")

# Main content
st.title("🚀 AI Research Assistant")
st.markdown("Generate comprehensive research reports instantly using advanced AI agents.")

cols = st.columns([2, 1])

with cols[0]:
    query = st.text_area("What would you like to research?", placeholder="Enter your topic (e.g., 'Impact of AI on modern healthcare')", height=100)
    
    if st.button("🔍 Generate Report"):
        if query:
            with st.spinner("Initializing research agent..."):
                response = submit_query(query)
                
                if response.get("status") == "error":
                    st.error(f"Error: {response.get('error')}")
                elif response.get("status") == "success":
                    st.session_state.current_report = response.get("report")
                    st.success("Found in cache!")
                elif response.get("status") == "processing":
                    task_id = response.get("task_id")
                    st.session_state.task_id = task_id
                    st.session_state.current_report = None
                    st.rerun() # Force immediate transition to polling view
        else:
            st.warning("Please enter a query.")

    if 'current_report' in st.session_state and st.session_state.current_report:
        st.markdown("### Research Report")
        st.markdown(f'<div class="report-card">{st.session_state.current_report}</div>', unsafe_allow_html=True)
        if st.button("🗑️ Clear Result"):
            st.session_state.current_report = None
            st.rerun()
            
    elif 'task_id' in st.session_state and st.session_state.task_id:
        st.markdown("### 🛠️ Research in Progress")
        
        # Poll the server
        status = get_status(st.session_state.task_id)
        
        # Display the steps in a small "status window"
        with st.status(f"Current State: {status.get('status').replace('_', ' ').title()}", expanded=True) as status_window:
            steps = status.get("steps", [])
            for step in steps:
                st.write(f"**{step.get('step')}**: {step.get('metadata')}")
            
            if status.get("status") == "completed":
                status_window.update(label="Research Completed!", state="complete", expanded=False)
                st.session_state.current_report = status.get("report")
                st.session_state.task_id = None
                st.rerun()
            elif status.get("status") == "failed":
                status_window.update(label="Research Failed!", state="error")
                st.error(f"Error: {status.get('error')}")
                if st.button("Dismiss"):
                    st.session_state.task_id = None
                    st.rerun()
            else:
                # Still running, refresh the page to keep polling
                time.sleep(2)
                st.rerun()

with cols[1]:
    st.markdown("### How it works")
    st.info("""
    1. **Query**: Enter a topic you want to research.
    2. **Agent**: A multi-step AI agent searches for information and analyzes it.
    3. **Cache**: Results are stored in a vector database for instant retrieval later.
    4. **Report**: You get a high-quality markdown report.
    """)
    
    st.markdown("### Tips for better reports")
    st.markdown("- Be specific about the domain.")
    st.markdown("- Ask for comparisons or trends.")
    st.markdown("- Define the intended audience.")
