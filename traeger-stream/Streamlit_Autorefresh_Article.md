# How to Implement Auto-Refresh in Streamlit: A Complete Guide

Auto-refreshing data is a common requirement for dashboard applications, especially when monitoring real-time data like IoT devices, stock prices, or system metrics. However, implementing auto-refresh in Streamlit can be tricky. This article explores different approaches and common pitfalls based on real-world experience.

## Table of Contents
1. [Why Auto-Refresh is Challenging in Streamlit](#why-auto-refresh-is-challenging)
2. [Common Mistakes and Anti-Patterns](#common-mistakes)
3. [The Right Way: Using Fragments](#the-right-way)
4. [Complete Working Example](#complete-example)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)

## Why Auto-Refresh is Challenging in Streamlit {#why-auto-refresh-is-challenging}

Streamlit's execution model reruns the entire script from top to bottom whenever the user interacts with the app. This makes implementing auto-refresh non-trivial because:

1. **Blocking Operations**: Using `time.sleep()` blocks the entire UI thread
2. **State Management**: Each rerun needs to preserve state properly
3. **Performance**: Rerunning the entire app can be expensive
4. **User Experience**: The app should remain responsive during refreshes

## Common Mistakes and Anti-Patterns {#common-mistakes}

### ❌ Mistake 1: Using time.sleep() with st.rerun()

```python
# DON'T DO THIS - Blocks the UI
def main():
    st.title("My Dashboard")
    # ... display data ...
    
    time.sleep(2)  # This blocks everything!
    st.rerun()
```

**Why it's wrong**: `time.sleep()` blocks the entire Streamlit UI thread, making the app unresponsive. The browser shows a loading state but users can't interact with any controls.

### ❌ Mistake 2: Using streamlit-autorefresh (Deprecated)

```python
# DON'T DO THIS - Uses external dependency
from streamlit_autorefresh import st_autorefresh

def main():
    st_autorefresh(interval=2000, limit=None, key="datarefresh")
    # ... rest of app ...
```

**Why it's wrong**: This relies on an external package that may not be maintained and adds unnecessary dependencies. Streamlit now has native solutions.

### ❌ Mistake 3: Async/Await Without Proper Integration

```python
# DON'T DO THIS - Doesn't work as expected
async def auto_refresh_task(refresh_rate):
    await asyncio.sleep(refresh_rate)
    st.rerun()

def main():
    # ... app content ...
    asyncio.create_task(auto_refresh_task(2))
```

**Why it's wrong**: Streamlit's execution model doesn't integrate well with raw asyncio tasks. The task may not execute as expected.

### ❌ Mistake 4: Continuous Rerun Loop

```python
# DON'T DO THIS - Creates infinite loop
def main():
    if time.time() - st.session_state.last_refresh >= refresh_rate:
        st.session_state.last_refresh = time.time()
        st.rerun()
    else:
        time.sleep(0.1)
        st.rerun()  # This creates a busy loop!
```

**Why it's wrong**: This creates a continuous rerun loop that consumes resources and provides poor user experience.

## The Right Way: Using Fragments {#the-right-way}

Streamlit 1.37.0+ introduced **fragments** with the `run_every` parameter, which is the proper way to implement auto-refresh:

```python
import streamlit as st
import time

@st.fragment(run_every=2)  # Runs every 2 seconds
def auto_refreshing_component():
    # Only this code reruns every 2 seconds
    current_time = time.time()
    st.metric("Current Time", f"{current_time:.2f}")
    
    # Fetch and display your real-time data here
    data = fetch_latest_data()
    st.line_chart(data)

def main():
    st.title("My Dashboard")
    
    # This only runs on full page reload
    st.sidebar.slider("Settings", 0, 10, 5)
    
    # Call the fragment
    auto_refreshing_component()
```

### Why Fragments Work

1. **Non-blocking**: The fragment runs asynchronously without blocking the UI
2. **Efficient**: Only the fragment code reruns, not the entire app
3. **Native**: Built into Streamlit, no external dependencies
4. **Configurable**: Can dynamically set the refresh interval

## Complete Working Example {#complete-example}

Here's a complete example of a live monitoring dashboard with auto-refresh:

```python
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import time

# Initialize session state
if 'data_history' not in st.session_state:
    st.session_state.data_history = []
if 'refresh_rate' not in st.session_state:
    st.session_state.refresh_rate = 2

def fetch_sensor_data():
    """Simulate fetching real-time sensor data."""
    return {
        'timestamp': datetime.now(),
        'temperature': 20 + np.random.randn() * 2,
        'humidity': 50 + np.random.randn() * 5,
        'pressure': 1013 + np.random.randn() * 10
    }

def main():
    st.title("🌡️ Sensor Dashboard")
    
    # Sidebar controls (not refreshed)
    with st.sidebar:
        st.header("Settings")
        refresh_rate = st.slider(
            "Refresh Rate (seconds)", 
            min_value=1, 
            max_value=10, 
            value=2
        )
        st.session_state.refresh_rate = refresh_rate
        
        if st.button("Clear History"):
            st.session_state.data_history = []
            st.rerun()
    
    # Create tabs
    tab1, tab2 = st.tabs(["📊 Live Monitor", "📈 Historical Data"])
    
    with tab1:
        # Auto-refreshing fragment for live data
        @st.fragment(run_every=st.session_state.refresh_rate if st.session_state.refresh_rate > 0 else None)
        def live_monitor():
            # Fetch new data
            new_data = fetch_sensor_data()
            
            # Add to history (limit to last 100 points)
            st.session_state.data_history.append(new_data)
            st.session_state.data_history = st.session_state.data_history[-100:]
            
            # Display current values
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Temperature",
                    f"{new_data['temperature']:.1f}°C",
                    delta=f"{new_data['temperature'] - 20:.1f}°C"
                )
            
            with col2:
                st.metric(
                    "Humidity",
                    f"{new_data['humidity']:.1f}%",
                    delta=f"{new_data['humidity'] - 50:.1f}%"
                )
            
            with col3:
                st.metric(
                    "Pressure",
                    f"{new_data['pressure']:.0f} hPa",
                    delta=f"{new_data['pressure'] - 1013:.0f} hPa"
                )
            
            # Plot historical data
            if st.session_state.data_history:
                df = pd.DataFrame(st.session_state.data_history)
                
                st.subheader("Live Trends")
                
                # Temperature chart
                st.line_chart(
                    df.set_index('timestamp')['temperature'],
                    use_container_width=True
                )
                
                # Last update time
                st.caption(f"Last updated: {new_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Call the fragment
        live_monitor()
    
    with tab2:
        st.subheader("Historical Data Analysis")
        if st.session_state.data_history:
            df = pd.DataFrame(st.session_state.data_history)
            st.dataframe(df)
        else:
            st.info("No historical data available yet.")

if __name__ == "__main__":
    main()
```

## Best Practices {#best-practices}

### 1. Use Conditional Refresh

Only enable auto-refresh when needed:

```python
# Only refresh when on the live tab
if st.session_state.get('active_tab') == 'live':
    @st.fragment(run_every=2)
    def refresh_fragment():
        # ... refresh logic ...
```

### 2. Manage Refresh Rate Dynamically

Allow users to control the refresh rate:

```python
refresh_rate = st.slider("Refresh Rate", 1, 10, 2)

@st.fragment(run_every=refresh_rate if refresh_rate > 0 else None)
def auto_refresh():
    # ... refresh logic ...
```

### 3. Separate Static and Dynamic Content

Keep static content outside the fragment:

```python
def main():
    # Static content - only runs on full page load
    st.title("Dashboard")
    st.sidebar.selectbox("Choose metric", ["Temperature", "Pressure"])
    
    # Dynamic content - refreshes automatically
    @st.fragment(run_every=2)
    def dynamic_content():
        data = fetch_latest_data()
        st.metric("Current Value", data)
    
    dynamic_content()
```

### 4. Handle Data Loading Efficiently

Load historical data outside the fragment:

```python
# Load once when page loads
if 'data_loaded' not in st.session_state:
    st.session_state.historical_data = load_historical_data()
    st.session_state.data_loaded = True

# Refresh only current data
@st.fragment(run_every=2)
def refresh_current():
    current = fetch_current_data()
    display_data(current)
```

## Troubleshooting {#troubleshooting}

### Issue: Page keeps showing "Running..." but data doesn't update

**Cause**: The fragment might be triggering too frequently or there's an error in the fragment code.

**Solution**: 
- Check for errors in the fragment function
- Ensure the refresh rate is reasonable (not less than 1 second)
- Add error handling inside the fragment

### Issue: Entire page refreshes instead of just the data

**Cause**: Using `st.rerun()` outside of a fragment or incorrect fragment setup.

**Solution**: 
- Ensure all auto-refresh logic is inside a fragment
- Don't call `st.rerun()` in the main app flow

### Issue: State is lost between refreshes

**Cause**: Not using `st.session_state` properly.

**Solution**:
```python
# Store data in session state
if 'my_data' not in st.session_state:
    st.session_state.my_data = []

@st.fragment(run_every=2)
def update_data():
    # Access and update session state
    new_value = fetch_new_value()
    st.session_state.my_data.append(new_value)
```

### Issue: Performance degradation over time

**Cause**: Accumulating too much data in memory.

**Solution**:
```python
# Limit data history
MAX_HISTORY = 1000
st.session_state.data = st.session_state.data[-MAX_HISTORY:]
```

## Conclusion

Auto-refresh in Streamlit is best implemented using the native fragment functionality with the `run_every` parameter. This approach:

- Keeps the UI responsive
- Only refreshes the necessary components
- Maintains good performance
- Provides a clean user experience

Avoid blocking operations like `time.sleep()`, external packages, or continuous rerun loops. Instead, embrace Streamlit's fragment pattern for efficient, maintainable auto-refresh functionality.

Remember: The key to successful auto-refresh is understanding Streamlit's execution model and working with it, not against it.