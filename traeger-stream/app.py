"""Streamlit web app for Traeger grill monitoring."""

import asyncio
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, timezone
import pandas as pd
from dotenv import load_dotenv
import os
import logging
import time
import json
import nest_asyncio

from traeger_client import TraegerClient
from traeger_client.models import GrillCommand
from streaming import DataStream
from pathlib import Path

# Allow nested event loops in Streamlit
nest_asyncio.apply()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Timezone configuration - default to system timezone
# Can be overridden with TIMEZONE env var (e.g., 'America/Chicago', 'US/Eastern', 'UTC')
TIMEZONE = os.getenv('TIMEZONE', 'America/Chicago')

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
if "historical_loaded" not in st.session_state:
    st.session_state.historical_loaded = False


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


async def load_historical_data_to_buffer(storage, stream, thing_name: str, hours: int = 24):
    """Load historical data into the stream buffer.
    
    Args:
        storage: DataStorage instance
        stream: DataStream instance  
        thing_name: Grill thing name
        hours: Number of hours of historical data to load
    """
    if not storage or not stream:
        return
        
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)
    
    # Fetch raw messages from database
    raw_messages = await storage.get_raw_messages(
        start_time=start_time,
        end_time=end_time
    )
    
    if not raw_messages:
        return
    
    # Parse messages and convert to GrillStatus objects
    historical_data = []
    
    for msg in raw_messages:
        try:
            # Parse payload
            payload = json.loads(msg['payload'])
            
            # Extract thing name from topic or payload
            # Topic format: prod/thing/update/THINGNAME
            topic_parts = msg['topic'].split('/')
            msg_thing_name = None
            if len(topic_parts) >= 4:
                msg_thing_name = topic_parts[3]
            
            # Skip if not for our grill
            if msg_thing_name != thing_name:
                continue
                
            # Parse into GrillStatus using client's parser
            if st.session_state.client:
                status = st.session_state.client._parse_status(msg_thing_name, payload)
                
                # Convert timestamp to local timezone
                timestamp = pd.to_datetime(msg['timestamp']).tz_localize('UTC').tz_convert(TIMEZONE)
                timestamp = timestamp.to_pydatetime().replace(tzinfo=None)  # Make timezone-naive for consistency
                
                historical_data.append((timestamp, status))
        except Exception as e:
            logger.error(f"Error parsing historical message: {e}")
            continue
    
    # Load into buffer
    if historical_data:
        stream.buffer.load_historical_data(historical_data)
        logger.info(f"Loaded {len(historical_data)} historical data points for {thing_name}")


def create_temperature_chart(df: pd.DataFrame):
    """Create temperature chart with Plotly."""
    fig = go.Figure()
    
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
            )
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
                )
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
                    )
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
                        )
                    )
        
    
    # Update layout
    fig.update_xaxes(title_text="Time")
    fig.update_yaxes(title_text="Temperature (°F)")
    
    fig.update_layout(
        height=600,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    
    return fig


def main():
    """Main Streamlit app."""
    st.title("🔥 Traeger Live Monitor")
    
    # Auto-connect on startup
    if not st.session_state.connected and not st.session_state.get('connection_attempted', False):
        st.session_state.connection_attempted = True
        with st.spinner("Connecting to Traeger..."):
            run_async(connect_to_traeger())
            st.rerun()
    
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
                    new_grill = grills[selected_idx]["thing_name"]
                    if st.session_state.selected_grill != new_grill:
                        st.session_state.selected_grill = new_grill
                        st.session_state.historical_loaded = False
                    
            # Refresh interval
            refresh_rate = st.slider("Refresh Rate (seconds)", 1, 10, 2)
            st.session_state.refresh_rate = refresh_rate
            
            # Historical data period for live view
            st.divider()
            st.subheader("Live View Settings")
            historical_hours = st.selectbox(
                "Historical Data to Load",
                options=[1, 6, 12, 24, 48],
                index=3,  # Default to 24 hours
                format_func=lambda x: f"Last {x} hours",
                help="Amount of historical data to load when starting live view"
            )
            st.session_state.historical_hours = historical_hours
            
            # Clear buffer button to reload with new settings
            if st.button("Reload Historical Data", type="secondary"):
                if st.session_state.stream:
                    st.session_state.stream.buffer.clear()
                    st.session_state.historical_loaded = False
                st.rerun()
            
            # Data Storage
            st.divider()
            st.subheader("Data Storage")
            
            if st.session_state.client and st.session_state.client.storage:
                storage = st.session_state.client.storage
                
                # Show database path
                st.info(f"📁 Database: {storage.db_path}")
                
                # Export data
                if st.button("Export to CSV", type="secondary"):
                    export_path = Path("./exports") / f"traeger_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    grill_count, probe_count = run_async(storage.export_to_csv(export_path))
                    st.success(f"✅ Exported {grill_count} grill states and {probe_count} probe records to {export_path}")
                
                # Show storage stats
                if st.session_state.selected_grill:
                    # Get latest raw message
                    raw_messages = run_async(storage.get_raw_messages(limit=1))
                    if raw_messages:
                        # Convert UTC timestamp to local time
                        utc_time = pd.to_datetime(raw_messages[0]['timestamp']).tz_localize('UTC')
                        local_time = utc_time.tz_convert(TIMEZONE)
                        st.caption(f"Latest data: {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    
                    # Count all raw messages
                    all_messages = run_async(storage.get_raw_messages())
                    st.caption(f"Records: {len(all_messages)} data points")
                    st.caption(f"Timezone: {TIMEZONE}")
            else:
                st.warning("Data storage is disabled")
            
        else:
            st.error("❌ Disconnected")
            if st.button("Reconnect", type="primary"):
                st.session_state.connection_attempted = False
                st.rerun()
                
    # Main content
    if st.session_state.connected and st.session_state.selected_grill:
        # Create tabs
        tab1, tab2 = st.tabs(["📊 Live Monitor", "📈 Historical Data"])
        
        with tab1:
            # Store current tab for auto-refresh logic
            st.session_state.current_tab = 'live'
            
            # Load historical data if buffer is empty
            buffer = st.session_state.stream.get_buffer()
            
            # Check if we need to load historical data
            if not st.session_state.historical_loaded and st.session_state.client and st.session_state.client.storage:
                with st.spinner("Loading historical data..."):
                    run_async(load_historical_data_to_buffer(
                        st.session_state.client.storage,
                        st.session_state.stream,
                        st.session_state.selected_grill,
                        hours=st.session_state.get('historical_hours', 24)
                    ))
                    st.session_state.historical_loaded = True
                    st.rerun()
            
            # Get current status
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
                    if current.probes and len(current.probes) > 0:
                        probe = current.probes[0]
                        st.metric(
                            "Probe 1",
                            f"{probe.temperature or '--'}°F",
                            delta=f"Target: {probe.target_temperature or '--'}°F"
                        )
                    else:
                        st.metric("Probe 1", "--°F")
                        
                with col4:
                    if current.probes and len(current.probes) > 1:
                        probe = current.probes[1]
                        st.metric(
                            "Probe 2",
                            f"{probe.temperature or '--'}°F",
                            delta=f"Target: {probe.target_temperature or '--'}°F"
                        )
                    else:
                        st.metric("Probe 2", "--°F")
                    
                # Temperature chart
                st.subheader("Temperature History")
                
                # Get data for plotting
                df = buffer.get_dataframe(st.session_state.selected_grill)
                
                # Debug info
                with st.expander("Debug Info"):
                    st.write(f"Buffer has {len(buffer.data)} total entries")
                    st.write(f"DataFrame has {len(df)} rows for {st.session_state.selected_grill}")
                    if not df.empty:
                        st.write(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
                        st.write("First few rows:")
                        st.dataframe(df.head())
                    
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
                
            # Mark that we're in the live tab
            st.session_state.current_tab = "live"
            
            # Auto-refresh container at the bottom
            # This will trigger a rerun periodically
            auto_refresh_container = st.empty()
            with auto_refresh_container:
                refresh_rate = st.session_state.get('refresh_rate', 2)
                if refresh_rate > 0:
                    time.sleep(refresh_rate)
                    st.rerun()
        
        with tab2:
            # Historical data tab
            st.session_state.current_tab = "historical"
            st.subheader("📈 Historical Data")
            
            if st.session_state.client and st.session_state.client.storage:
                storage = st.session_state.client.storage
                
                # Date range selector
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=7))
                with col2:
                    end_date = st.date_input("End Date", value=datetime.now().date())
                
                if st.button("Load Historical Data"):
                    # Convert dates to datetime
                    start_datetime = datetime.combine(start_date, datetime.min.time())
                    end_datetime = datetime.combine(end_date, datetime.max.time())
                    
                    # Load raw messages from database
                    raw_messages = run_async(storage.get_raw_messages(
                        start_time=start_datetime,
                        end_time=end_datetime
                    ))
                    
                    if raw_messages:
                        # Parse raw messages to extract data
                        records = []
                        for msg in raw_messages:
                            try:
                                payload = json.loads(msg['payload'])
                                status = payload.get('status', {})
                                
                                # Extract basic data
                                record = {
                                    'timestamp': msg['timestamp'],
                                    'grill_temp': status.get('grill'),
                                    'grill_set': status.get('set'),
                                    'ambient': status.get('ambient'),
                                    'fan_speed': status.get('fan', 0) if status.get('fan') else 0,
                                    'connected': status.get('connected', False)
                                }
                                
                                # Extract probe data
                                probe_idx = 0
                                for acc in status.get('acc', []):
                                    if acc.get('type') == 'btprobe' and acc.get('con') == 1:
                                        btprobe = acc.get('btprobe', {})
                                        record[f'probe_{probe_idx}_temp'] = btprobe.get('get_temp')
                                        record[f'probe_{probe_idx}_target'] = btprobe.get('set_temp')
                                        probe_idx += 1
                                
                                records.append(record)
                            except Exception as e:
                                st.warning(f"Error parsing message: {e}")
                                continue
                        
                        if records:
                            # Convert to DataFrame
                            df = pd.DataFrame(records)
                            # Convert UTC timestamps to local time
                            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
                            df = df.sort_values('timestamp')
                            
                            # Create historical chart
                            fig = create_temperature_chart(df)
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Show statistics
                            st.subheader("Statistics")
                            col1, col2, col3, col4 = st.columns(4)
                            
                            with col1:
                                st.metric("Records", len(df))
                            with col2:
                                if 'grill_temp' in df.columns and not df['grill_temp'].isna().all():
                                    st.metric("Avg Grill Temp", f"{df['grill_temp'].mean():.1f}°F")
                                else:
                                    st.metric("Avg Grill Temp", "--")
                            with col3:
                                if 'grill_temp' in df.columns and not df['grill_temp'].isna().all():
                                    st.metric("Max Grill Temp", f"{df['grill_temp'].max():.1f}°F")
                                else:
                                    st.metric("Max Grill Temp", "--")
                            with col4:
                                if 'grill_temp' in df.columns and not df['grill_temp'].isna().all():
                                    st.metric("Min Grill Temp", f"{df['grill_temp'].min():.1f}°F")
                                else:
                                    st.metric("Min Grill Temp", "--")
                            
                            # Download data
                            csv = df.to_csv(index=False)
                            st.download_button(
                                label="Download CSV",
                                data=csv,
                                file_name=f"traeger_data_{start_date}_{end_date}.csv",
                                mime="text/csv"
                            )
                        else:
                            st.info("No valid data found in the selected date range")
                    else:
                        st.info("No data found for the selected date range")
            else:
                st.warning("Data storage is not available")
        
    elif not st.session_state.connected:
        st.info("Connecting to Traeger services...")
    else:
        st.info("Please select a grill from the sidebar.")
    


if __name__ == "__main__":
    main()