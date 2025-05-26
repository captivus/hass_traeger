"""Streamlit web app for Traeger grill monitoring."""

import asyncio
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv
import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor
import nest_asyncio

from traeger_client import TraegerClient
from traeger_client.models import GrillCommand, GrillState
from streaming import DataStream

# Allow nested event loops in Streamlit
nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Helper to run async functions in Streamlit
def run_async(coro):
    """Run async coroutine in Streamlit context."""
    loop = asyncio.new_event_loop()
    return loop.run_until_complete(coro)

# Page config
st.set_page_config(
    page_title="Traeger Live Monitor",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "client" not in st.session_state:
    st.session_state.client = None
if "stream" not in st.session_state:
    st.session_state.stream = None
if "connected" not in st.session_state:
    st.session_state.connected = False
if "selected_grill" not in st.session_state:
    st.session_state.selected_grill = None


async def connect_to_traeger():
    """Connect to Traeger services."""
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if not username or not password:
        st.error("Please set TRAEGER_USERNAME and TRAEGER_PASSWORD environment variables")
        return False
        
    try:
        client = TraegerClient(username, password)
        await client.connect()
        
        stream = DataStream(client)
        
        st.session_state.client = client
        st.session_state.stream = stream
        st.session_state.connected = True
        
        # Start streaming in background
        asyncio.create_task(stream.start())
        
        return True
    except Exception as e:
        st.error(f"Connection failed: {e}")
        return False


def create_temperature_chart(df: pd.DataFrame):
    """Create temperature chart with Plotly."""
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=("Temperature", "Fan Speed")
    )
    
    # Temperature traces
    if not df.empty:
        # Grill temperature
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["grill_temp"],
                name="Grill Temp",
                line=dict(color="red", width=3),
                mode="lines"
            ),
            row=1, col=1
        )
        
        # Set temperature
        if "grill_set" in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["grill_set"],
                    name="Set Temp",
                    line=dict(color="orange", dash="dash", width=2),
                    mode="lines"
                ),
                row=1, col=1
            )
        
        # Probe temperatures
        probe_colors = ["blue", "green", "purple", "brown"]
        for i, color in enumerate(probe_colors):
            probe_col = f"probe_{i}_temp"
            if probe_col in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df["timestamp"],
                        y=df[probe_col],
                        name=f"Probe {i+1}",
                        line=dict(color=color, width=2),
                        mode="lines"
                    ),
                    row=1, col=1
                )
                
                # Probe target
                target_col = f"probe_{i}_target"
                if target_col in df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=df["timestamp"],
                            y=df[target_col],
                            name=f"Probe {i+1} Target",
                            line=dict(color=color, dash="dot", width=1),
                            mode="lines",
                            showlegend=False
                        ),
                        row=1, col=1
                    )
        
        # Fan speed
        if "fan_speed" in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["fan_speed"],
                    name="Fan Speed",
                    line=dict(color="cyan", width=2),
                    fill="tozeroy",
                    mode="lines"
                ),
                row=2, col=1
            )
    
    # Update layout
    fig.update_xaxes(title_text="Time", row=2, col=1)
    fig.update_yaxes(title_text="Temperature (°F)", row=1, col=1)
    fig.update_yaxes(title_text="Fan %", range=[0, 10], row=2, col=1)
    
    fig.update_layout(
        height=600,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    
    return fig


def main():
    """Main Streamlit app."""
    st.title("🔥 Traeger Live Monitor")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        
        # Connection status
        if st.session_state.connected:
            st.success("✅ Connected")
            
            # Grill selector
            if st.session_state.client:
                grills = st.session_state.client.list_grills()
                if grills:
                    grill_names = [g["friendly_name"] for g in grills]
                    selected_idx = st.selectbox(
                        "Select Grill",
                        range(len(grills)),
                        format_func=lambda x: grill_names[x]
                    )
                    st.session_state.selected_grill = grills[selected_idx]["thing_name"]
                    
            # Refresh interval
            refresh_rate = st.slider("Refresh Rate (seconds)", 1, 10, 2)
            
            # Data window
            window_hours = st.slider("Data Window (hours)", 1, 12, 2)
            
        else:
            st.error("❌ Disconnected")
            if st.button("Connect", type="primary"):
                run_async(connect_to_traeger())
                st.rerun()
                
    # Main content
    if st.session_state.connected and st.session_state.selected_grill:
        # Get current status
        buffer = st.session_state.stream.get_buffer()
        current = buffer.get_latest(st.session_state.selected_grill)
        
        if current:
            # Status indicators
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Status",
                    current.state.name,
                    delta=None,
                    delta_color="normal"
                )
                
            with col2:
                st.metric(
                    "Grill Temp",
                    f"{current.grill_temperature or '--'}°F",
                    delta=f"Set: {current.grill_set_temperature or '--'}°F"
                )
                
            with col3:
                if current.probes:
                    probe = current.probes[0]
                    st.metric(
                        "Probe 1",
                        f"{probe.temperature or '--'}°F",
                        delta=f"Target: {probe.target_temperature or '--'}°F"
                    )
                else:
                    st.metric("Probe 1", "--°F")
                    
            with col4:
                st.metric(
                    "Fan Speed",
                    f"{current.fan_speed or 0}%"
                )
                
            # Temperature chart
            st.subheader("Temperature History")
            
            # Get data for plotting
            df = buffer.get_dataframe(st.session_state.selected_grill)
            if not df.empty:
                # Filter to selected window
                cutoff = datetime.now() - timedelta(hours=window_hours)
                df = df[df["timestamp"] > cutoff]
                
            fig = create_temperature_chart(df)
            st.plotly_chart(fig, use_container_width=True)
            
            # Controls
            st.subheader("Controls")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Temperature control
                new_temp = st.number_input(
                    "Set Grill Temperature",
                    min_value=165,
                    max_value=500,
                    value=int(current.grill_set_temperature or 225),
                    step=5
                )
                if st.button("Set Temperature", type="primary"):
                    cmd = GrillCommand.set_temperature(
                        st.session_state.selected_grill,
                        new_temp
                    )
                    run_async(st.session_state.client.send_command(cmd))
                    st.success(f"Set temperature to {new_temp}°F")
                    
            with col2:
                # Probe target
                if current.probes:
                    probe_target = st.number_input(
                        "Set Probe Target",
                        min_value=100,
                        max_value=250,
                        value=int(current.probes[0].target_temperature or 165),
                        step=1
                    )
                    if st.button("Set Probe Target"):
                        cmd = GrillCommand.set_probe_temperature(
                            st.session_state.selected_grill,
                            probe_target
                        )
                        run_async(st.session_state.client.send_command(cmd))
                        st.success(f"Set probe target to {probe_target}°F")
                        
            with col3:
                # Shutdown
                st.write("")  # Spacing
                st.write("")  # Spacing
                if st.button("Shutdown Grill", type="secondary"):
                    if st.checkbox("Confirm shutdown"):
                        cmd = GrillCommand.shutdown(st.session_state.selected_grill)
                        run_async(st.session_state.client.send_command(cmd))
                        st.warning("Shutdown command sent")
                        
        else:
            st.info("Waiting for data...")
            
        # Auto-refresh
        placeholder = st.empty()
        time.sleep(refresh_rate)
        st.rerun()
        
    elif not st.session_state.connected:
        st.info("Please connect to Traeger services using the sidebar.")
    else:
        st.info("Please select a grill from the sidebar.")


if __name__ == "__main__":
    main()