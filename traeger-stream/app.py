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
import json
import nest_asyncio
import pytz
import time

from traeger_client import TraegerClient
from streaming import DataStream

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
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Use nest_asyncio to allow running in existing loop
    nest_asyncio.apply()
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
    # Check if already connected
    if st.session_state.connected and st.session_state.client:
        return True
        
    username = os.getenv("TRAEGER_USERNAME")
    password = os.getenv("TRAEGER_PASSWORD")
    
    if not username or not password:
        st.error("Please set TRAEGER_USERNAME and TRAEGER_PASSWORD environment variables")
        return False
        
    try:
        client = TraegerClient(username, password, enable_storage=True)
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
        
    # Clear predictor history only if we're switching grills or don't have any history
    if hasattr(st.session_state, 'client') and st.session_state.client:
        # Check if we're switching grills (thing_name changed)
        current_grill = getattr(st.session_state, 'predictor_grill', None)
        if current_grill != thing_name:
            st.session_state.client.predictor.clear_history()
            st.session_state.predictor_grill = thing_name
        
    # Calculate time range in UTC for database query
    # Get current time in local timezone
    local_tz = pytz.timezone(TIMEZONE)
    local_now = datetime.now(local_tz)
    
    # Calculate start time
    local_start = local_now - timedelta(hours=hours)
    
    # Convert to UTC for database query (database stores in UTC)
    utc_end = local_now.astimezone(pytz.UTC).replace(tzinfo=None)
    utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
    
    # Fetch raw messages from database
    logger.info(f"Loading historical data from {utc_start} UTC to {utc_end} UTC (Local: {local_start} to {local_now})")
    raw_messages = await storage.get_raw_messages(
        start_time=utc_start,
        end_time=utc_end
    )
    
    logger.info(f"Found {len(raw_messages) if raw_messages else 0} raw messages in database")
    
    if not raw_messages:
        logger.warning("No historical data found in database")
        return
    
    # Parse messages and convert to GrillStatus objects
    historical_data = []
    skipped_count = 0
    
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
                skipped_count += 1
                continue
                
            # Parse into GrillStatus using client's parser
            if st.session_state.client:
                status = st.session_state.client._parse_status(msg_thing_name, payload)
                
                # Convert timestamp to local timezone
                timestamp = pd.to_datetime(msg['timestamp']).tz_localize('UTC').tz_convert(TIMEZONE)
                timestamp = timestamp.to_pydatetime().replace(tzinfo=None)  # Make timezone-naive for consistency
                
                historical_data.append((timestamp, status))
                
                # Add historical probe temperatures to predictor
                # Skip for XGBoost predictor as it only uses current cook data
                # Historical data is handled separately
        except Exception as e:
            logger.error(f"Error parsing historical message: {e}")
            continue
    
    # Load into buffer
    logger.info(f"Processed {len(raw_messages)} messages: {len(historical_data)} for grill {thing_name}, {skipped_count} skipped")
    
    if historical_data:
        stream.buffer.load_historical_data(historical_data)
        logger.info(f"Loaded {len(historical_data)} historical data points for {thing_name}")
    else:
        logger.warning(f"No data points matched grill {thing_name}")


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
                            showlegend=True
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
            st.info("🔄 Refreshes every 30 seconds")
            
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
                        # Clear historical loaded flag for the old grill
                        if st.session_state.selected_grill:
                            old_key = f"historical_loaded_{st.session_state.selected_grill}"
                            if old_key in st.session_state:
                                del st.session_state[old_key]
                        st.session_state.selected_grill = new_grill
                    
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
                    # Clear historical loaded flag for current grill
                    if st.session_state.selected_grill:
                        hist_key = f"historical_loaded_{st.session_state.selected_grill}"
                        if hist_key in st.session_state:
                            del st.session_state[hist_key]
                st.rerun()
            
        else:
            st.error("❌ Disconnected")
            if st.button("Reconnect", type="primary"):
                st.session_state.connection_attempted = False
                st.rerun()
                
    # Main content
    if st.session_state.connected and st.session_state.selected_grill:
        # Create tabs
        tab1, tab2 = st.tabs(["📊 Live Monitor", "📈 Historical Data"])
        
        # Initialize tab tracking
        if 'active_tab' not in st.session_state:
            st.session_state.active_tab = 0
        
        with tab1:
            st.session_state.active_tab = 0
            
            # Load historical data if needed (outside fragment)
            hist_key = f"historical_loaded_{st.session_state.selected_grill}"
            if not st.session_state.get(hist_key, False) and st.session_state.client and st.session_state.client.storage:
                with st.spinner("Loading historical data..."):
                    run_async(load_historical_data_to_buffer(
                        st.session_state.client.storage,
                        st.session_state.stream,
                        st.session_state.selected_grill,
                        hours=st.session_state.get('historical_hours', 24)
                    ))
                    # Set the flag after loading
                    st.session_state[hist_key] = True
            
            # Use fragment for auto-refreshing live monitor
            @st.fragment(run_every=30)
            def live_monitor_fragment():
                # Get buffer inside fragment
                buffer = st.session_state.stream.get_buffer()
                
                # Get current status
                current = buffer.get_latest(st.session_state.selected_grill)
                
                # Update predictions with current predictor state
                if current and st.session_state.client:
                    current = st.session_state.client.update_predictions(current)
                
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
                            delta=f"Set: {current.set_temperature or '--'}°F"
                        )
                    
                    # Display only active probes (those with temperature data)
                    active_probes = []
                    if current.probes:
                        for probe in current.probes:
                            if probe.temperature is not None:
                                active_probes.append(probe)
                    
                    # Use remaining columns for probes
                    probe_cols = [col3, col4]
                    
                    # Display active probes
                    for i, probe in enumerate(active_probes[:2]):  # Show up to 2 probes
                        with probe_cols[i]:
                            # Determine probe type based on ID
                            probe_label = f"Probe {i+1}"
                            if probe.id:
                                if 'wired' in probe.id.lower():
                                    probe_label = f"Wired Probe {i+1}"
                                elif 'bluetooth' in probe.id.lower() or 'bt' in probe.id.lower():
                                    probe_label = f"BT Probe {i+1}"
                            
                            st.metric(
                                probe_label,
                                f"{probe.temperature}°F",
                                delta=f"Target: {probe.target_temperature or '--'}°F"
                            )
                            
                            # Show prediction if available
                            if probe.predicted_time_to_target is not None:
                                from traeger_client.simple_temperature_predictor import SimpleTemperaturePredictor
                                predictor = SimpleTemperaturePredictor()
                                prediction_str = predictor.format_prediction((probe.predicted_time_to_target, probe.prediction_message, probe.temperature_rate, probe.temperature_acceleration))
                                st.caption(f"⏱️ {prediction_str}")
                            elif probe.prediction_message:
                                st.caption(f"⏱️ {probe.prediction_message}")
                            
                            # Show temperature rate and acceleration
                            if probe.temperature_rate is not None:
                                rate_sign = "+" if probe.temperature_rate > 0 else ""
                                accel_sign = "+" if probe.temperature_acceleration > 0 else ""
                                st.caption(f"📈 {rate_sign}{probe.temperature_rate:.1f}°F/min, {accel_sign}{probe.temperature_acceleration:.2f}°F/min²")
                    
                    # Fill remaining columns if no active probes
                    for i in range(len(active_probes), 2):
                        with probe_cols[i]:
                            st.empty()  # Just leave empty instead of showing "--°F"
                    
                    # Temperature chart
                    st.subheader("Temperature History")
                    
                    # Get data for plotting
                    df = buffer.get_dataframe(st.session_state.selected_grill)
                    
                    fig = create_temperature_chart(df)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Show last update time with timezone
                    local_tz = pytz.timezone(TIMEZONE)
                    last_update = datetime.now(local_tz)
                    st.caption(f"📅 Last updated: {last_update.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                            
                else:
                    st.info("🔄 Requesting live data from grill... (this may take a few seconds)")
                    
                    # Show spinner while waiting
                    with st.spinner("Connecting to grill..."):
                        # The page will auto-refresh based on the refresh rate
                        pass
            
            # Call the fragment
            live_monitor_fragment()
        
        with tab2:
            st.session_state.active_tab = 1
            
            # Historical data tab
            st.subheader("📈 Historical Data")
            
            if st.session_state.client and st.session_state.client.storage:
                storage = st.session_state.client.storage
                
                # Date range selector
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("Start Date", value=datetime.now().date() - timedelta(days=7))
                with col2:
                    end_date = st.date_input("End Date", value=datetime.now().date())
                
                # Create two columns for buttons
                col_load, col_download = st.columns(2)
                
                with col_load:
                    load_button = st.button("Load Historical Data")
                
                with col_download:
                    # Show download button if data exists in session state
                    if hasattr(st.session_state, 'historical_csv') and st.session_state.historical_csv:
                        st.download_button(
                            label="Download CSV",
                            data=st.session_state.historical_csv,
                            file_name=f"traeger_data_{st.session_state.historical_dates[0]}_{st.session_state.historical_dates[1]}.csv",
                            mime="text/csv"
                        )
                
                if load_button:
                    # Convert dates to datetime in local timezone
                    local_tz = pytz.timezone(TIMEZONE)
                    start_datetime = local_tz.localize(datetime.combine(start_date, datetime.min.time()))
                    # Use end of day (23:59:59.999999) to include the entire end date
                    end_datetime = local_tz.localize(datetime.combine(end_date, datetime.max.time().replace(microsecond=999999)))
                    
                    # Convert to UTC for database query
                    utc_start = start_datetime.astimezone(pytz.UTC).replace(tzinfo=None)
                    utc_end = end_datetime.astimezone(pytz.UTC).replace(tzinfo=None)
                    
                    # Load raw messages from database
                    with st.spinner(f"Loading data from {start_date} to {end_date}..."):
                        raw_messages = run_async(storage.get_raw_messages(
                            start_time=utc_start,
                            end_time=utc_end
                        ))
                    
                    
                    if raw_messages:
                        
                        # Parse raw messages to extract data
                        records = []
                        parse_errors = 0
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
                                parse_errors += 1
                                logger.error(f"Error parsing message: {e}, payload: {msg.get('payload', '')[:100]}")
                                continue
                        
                        if parse_errors > 0:
                            st.warning(f"Failed to parse {parse_errors} messages")
                        
                        if records:
                            
                            # Convert to DataFrame
                            df = pd.DataFrame(records)
                            # Convert UTC timestamps to local time
                            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert(TIMEZONE)
                            df = df.sort_values('timestamp')
                            
                            # Store data in session state for download button
                            st.session_state.historical_df = df
                            st.session_state.historical_csv = df.to_csv(index=False)
                            st.session_state.historical_dates = (start_date, end_date)
                            st.rerun()
                        else:
                            st.info("No valid data found in the selected date range")
                    else:
                        st.info("No data found for the selected date range")
                
                # Display data if it exists in session state (outside button handler)
                if hasattr(st.session_state, 'historical_df') and st.session_state.historical_df is not None:
                    df = st.session_state.historical_df
                    
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
                
            else:
                st.warning("Data storage is not available")
        
    elif not st.session_state.connected:
        st.info("Connecting to Traeger services...")
    else:
        st.info("Please select a grill from the sidebar.")


if __name__ == "__main__":
    main()