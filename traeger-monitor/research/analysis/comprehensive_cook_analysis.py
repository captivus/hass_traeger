#!/usr/bin/env python3
"""
Comprehensive analysis of historical cook data to understand temperature patterns
and build foundation for high-accuracy prediction model.
"""
import sqlite3
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.optimize import curve_fit
from scipy.stats import pearsonr
import warnings
warnings.filterwarnings('ignore')

# Database paths
HISTORICAL_DB = Path("../traeger-stream/data/traeger_data.db")
OUTPUT_DIR = Path("analysis_results")
OUTPUT_DIR.mkdir(exist_ok=True)

def extract_all_cook_sessions():
    """Extract all cook sessions from historical database."""
    print("Extracting all cook sessions from historical database...")
    
    with sqlite3.connect(HISTORICAL_DB) as conn:
        # Find all unique cook IDs with substantial data
        cursor = conn.execute("""
            SELECT 
                json_extract(payload, '$.status.cook_id') as cook_id,
                COUNT(*) as message_count,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                json_extract(payload, '$.status.grill') as sample_grill_temp
            FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') != '' 
            AND json_extract(payload, '$.status.cook_id') IS NOT NULL
            GROUP BY cook_id
            HAVING message_count > 50
            ORDER BY message_count DESC
        """)
        
        cook_sessions = []
        for row in cursor:
            cook_id, count, start, end, grill_temp = row
            if cook_id and start and end:
                try:
                    start_dt = datetime.fromisoformat(start)
                    end_dt = datetime.fromisoformat(end)
                    duration_hours = (end_dt - start_dt).total_seconds() / 3600
                    
                    cook_sessions.append({
                        'cook_id': cook_id,
                        'message_count': count,
                        'duration_hours': duration_hours,
                        'start_time': start_dt,
                        'end_time': end_dt,
                        'sample_grill_temp': grill_temp
                    })
                except:
                    continue
    
    # Sort by duration and filter for substantial cooks
    cook_sessions = [c for c in cook_sessions if c['duration_hours'] >= 1.0]
    cook_sessions.sort(key=lambda x: x['duration_hours'], reverse=True)
    
    print(f"Found {len(cook_sessions)} substantial cook sessions")
    for i, cook in enumerate(cook_sessions[:10]):
        print(f"  {i+1}. {cook['cook_id']}: {cook['duration_hours']:.1f}h, {cook['message_count']} msgs")
    
    return cook_sessions

def extract_detailed_cook_data(cook_id):
    """Extract detailed temperature data for a specific cook session."""
    with sqlite3.connect(HISTORICAL_DB) as conn:
        cursor = conn.execute("""
            SELECT timestamp, payload 
            FROM raw_messages 
            WHERE json_extract(payload, '$.status.cook_id') = ?
            ORDER BY timestamp ASC
        """, (cook_id,))
        
        data_points = []
        for timestamp, payload in cursor:
            try:
                status = json.loads(payload).get('status', {})
                dt = datetime.fromisoformat(timestamp)
                
                # Base record
                record = {
                    'timestamp': dt,
                    'grill_temp': status.get('grill'),
                    'grill_set': status.get('set'),
                    'ambient': status.get('ambient', 70),
                    'cook_id': cook_id
                }
                
                # Extract probe data from acc array
                probes_found = []
                for acc in status.get('acc', []):
                    if acc.get('con') == 1:  # Connected probe
                        channel = acc.get('channel', 'unknown')
                        if acc.get('type') == 'probe':
                            probe_data = acc.get('probe', {})
                            temp = probe_data.get('get_temp')
                            target = probe_data.get('set_temp')
                            if temp is not None and target is not None and target > 0:
                                record[f'{channel}_temp'] = temp
                                record[f'{channel}_target'] = target
                                probes_found.append(channel)
                        elif acc.get('type') == 'btprobe':
                            probe_data = acc.get('btprobe', {})
                            temp = probe_data.get('get_temp')
                            target = probe_data.get('set_temp')
                            if temp is not None and target is not None and target > 0:
                                record[f'{channel}_temp'] = temp
                                record[f'{channel}_target'] = target
                                probes_found.append(channel)
                
                # Check legacy probe format
                if status.get('probe_con') == 1:
                    temp = status.get('probe')
                    target = status.get('probe_set')
                    if temp is not None and target is not None and target > 0:
                        record['legacy_temp'] = temp
                        record['legacy_target'] = target
                        probes_found.append('legacy')
                
                record['probes_active'] = probes_found
                data_points.append(record)
                
            except (json.JSONDecodeError, ValueError):
                continue
    
    return pd.DataFrame(data_points)

def analyze_temperature_curves(df, cook_id):
    """Analyze temperature curves for physics understanding."""
    if df.empty:
        return {}
    
    # Calculate elapsed time
    df = df.sort_values('timestamp').copy()
    df['elapsed_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
    
    analysis = {
        'cook_id': cook_id,
        'total_duration_hours': df['elapsed_minutes'].max() / 60,
        'total_data_points': len(df),
        'grill_temp_stats': {
            'mean': df['grill_temp'].mean(),
            'std': df['grill_temp'].std(),
            'min': df['grill_temp'].min(),
            'max': df['grill_temp'].max()
        },
        'probes': {}
    }
    
    # Analyze each probe
    probe_columns = [col for col in df.columns if col.endswith('_temp')]
    for probe_temp_col in probe_columns:
        probe_name = probe_temp_col.replace('_temp', '')
        target_col = f'{probe_name}_target'
        
        if target_col not in df.columns:
            continue
        
        # Filter to valid probe data
        probe_data = df.dropna(subset=[probe_temp_col, target_col])
        if len(probe_data) < 10:
            continue
        
        probe_analysis = analyze_single_probe(probe_data, probe_temp_col, target_col)
        analysis['probes'][probe_name] = probe_analysis
    
    return analysis

def analyze_single_probe(df, temp_col, target_col):
    """Detailed analysis of a single probe's temperature curve."""
    temps = df[temp_col].values
    targets = df[target_col].values
    elapsed = df['elapsed_minutes'].values
    grill_temps = df['grill_temp'].values
    
    # Basic statistics
    start_temp = temps[0]
    max_temp = temps.max()
    target_temp = targets[0]  # Assuming target is constant
    
    # Calculate temperature rates
    rates = np.gradient(temps, elapsed)
    
    # Find if/when target was reached
    target_reached_idx = None
    for i, temp in enumerate(temps):
        if temp >= target_temp:
            target_reached_idx = i
            break
    
    # Detect stall (temperature plateau)
    stall_info = detect_stall(temps, elapsed)
    
    # Fit exponential heating curve
    heating_model = fit_heating_curve(elapsed, temps, grill_temps)
    
    # Calculate heat transfer metrics
    heat_transfer = calculate_heat_transfer_metrics(temps, grill_temps, elapsed)
    
    analysis = {
        'data_points': len(temps),
        'start_temp': start_temp,
        'max_temp': max_temp,
        'target_temp': target_temp,
        'target_reached': target_reached_idx is not None,
        'time_to_target_minutes': elapsed[target_reached_idx] if target_reached_idx else None,
        'temperature_range': max_temp - start_temp,
        'average_rate': np.mean(rates[rates > 0]),  # Only positive rates
        'max_rate': np.max(rates),
        'final_rate': np.mean(rates[-5:]) if len(rates) >= 5 else rates[-1],
        'stall_detected': stall_info['detected'],
        'stall_duration': stall_info['duration'],
        'stall_temp_range': stall_info['temp_range'],
        'heating_model': heating_model,
        'heat_transfer': heat_transfer,
        'grill_correlation': pearsonr(temps, grill_temps)[0] if len(temps) > 1 else 0
    }
    
    return analysis

def detect_stall(temps, elapsed):
    """Detect temperature stall (BBQ plateau phenomenon)."""
    if len(temps) < 20:
        return {'detected': False, 'duration': 0, 'temp_range': 0}
    
    # Look for periods where temperature rises very slowly
    window_size = min(10, len(temps) // 4)
    stall_threshold = 0.5  # degrees per minute
    
    stalls = []
    for i in range(window_size, len(temps) - window_size):
        # Calculate rate over window
        start_idx = i - window_size
        end_idx = i + window_size
        
        temp_change = temps[end_idx] - temps[start_idx]
        time_change = elapsed[end_idx] - elapsed[start_idx]
        
        if time_change > 0:
            rate = temp_change / time_change
            if rate < stall_threshold:
                stalls.append({
                    'start_time': elapsed[start_idx],
                    'end_time': elapsed[end_idx],
                    'temp_range': np.max(temps[start_idx:end_idx]) - np.min(temps[start_idx:end_idx]),
                    'rate': rate
                })
    
    if stalls:
        # Find longest stall
        longest_stall = max(stalls, key=lambda x: x['end_time'] - x['start_time'])
        return {
            'detected': True,
            'duration': longest_stall['end_time'] - longest_stall['start_time'],
            'temp_range': longest_stall['temp_range']
        }
    
    return {'detected': False, 'duration': 0, 'temp_range': 0}

def fit_heating_curve(elapsed, temps, grill_temps):
    """Fit exponential heating curve based on Newton's Law of Cooling."""
    try:
        # Newton's law: T(t) = T_ambient + (T_grill - T_ambient) * (1 - exp(-k*t))
        def heating_curve(t, k, T_ambient, efficiency):
            T_grill = np.mean(grill_temps)
            return T_ambient + efficiency * (T_grill - T_ambient) * (1 - np.exp(-k * t / 60))
        
        # Initial parameter guesses
        T_ambient = temps[0]
        T_grill_avg = np.mean(grill_temps)
        
        popt, pcov = curve_fit(
            heating_curve, 
            elapsed, 
            temps,
            p0=[0.01, T_ambient, 0.8],
            bounds=([0.001, 50, 0.1], [1.0, 200, 2.0]),
            maxfev=1000
        )
        
        k, T_ambient_fit, efficiency = popt
        
        # Calculate R²
        y_pred = heating_curve(elapsed, *popt)
        ss_res = np.sum((temps - y_pred) ** 2)
        ss_tot = np.sum((temps - np.mean(temps)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        return {
            'fitted': True,
            'k': k,
            'T_ambient': T_ambient_fit,
            'efficiency': efficiency,
            'r_squared': r_squared,
            'half_life_minutes': np.log(2) / k * 60 if k > 0 else None
        }
    
    except:
        return {'fitted': False}

def calculate_heat_transfer_metrics(temps, grill_temps, elapsed):
    """Calculate heat transfer efficiency and thermal mass indicators."""
    if len(temps) < 5:
        return {}
    
    # Temperature differences
    temp_diffs = np.array(grill_temps) - np.array(temps)
    
    # Rate of temperature change
    dt = np.diff(elapsed)
    dT = np.diff(temps)
    rates = dT / dt
    
    # Heat transfer coefficient approximation (simplified)
    # Rate is proportional to temperature difference
    valid_indices = (temp_diffs[:-1] > 0) & (dt > 0)
    if np.any(valid_indices):
        htc_values = rates[valid_indices] / temp_diffs[:-1][valid_indices]
        avg_htc = np.mean(htc_values[htc_values > 0])
    else:
        avg_htc = 0
    
    return {
        'avg_temp_differential': np.mean(temp_diffs),
        'max_temp_differential': np.max(temp_diffs),
        'avg_heating_rate': np.mean(rates[rates > 0]) if np.any(rates > 0) else 0,
        'thermal_responsiveness': avg_htc,
        'heating_efficiency': np.mean(rates[rates > 0]) / np.mean(temp_diffs) if np.mean(temp_diffs) > 0 else 0
    }

def create_comprehensive_visualizations(all_analyses):
    """Create comprehensive visualizations of cooking patterns."""
    
    # 1. Temperature curves for top cook sessions
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    axes = axes.flatten()
    
    cook_sessions = extract_all_cook_sessions()[:6]
    
    for i, cook_session in enumerate(cook_sessions):
        cook_id = cook_session['cook_id']
        df = extract_detailed_cook_data(cook_id)
        
        if df.empty:
            continue
        
        df = df.sort_values('timestamp')
        df['elapsed_minutes'] = (df['timestamp'] - df['timestamp'].iloc[0]).dt.total_seconds() / 60
        
        ax = axes[i]
        
        # Plot grill temperature
        ax.plot(df['elapsed_minutes'], df['grill_temp'], 'r-', alpha=0.7, label='Grill', linewidth=2)
        
        # Plot probe temperatures
        probe_colors = ['blue', 'green', 'orange', 'purple']
        color_idx = 0
        
        for col in df.columns:
            if col.endswith('_temp') and col != 'grill_temp':
                probe_name = col.replace('_temp', '')
                target_col = f'{probe_name}_target'
                
                if target_col in df.columns:
                    probe_data = df.dropna(subset=[col, target_col])
                    if len(probe_data) > 5:
                        color = probe_colors[color_idx % len(probe_colors)]
                        ax.plot(probe_data['elapsed_minutes'], probe_data[col], 
                               color=color, label=f'{probe_name}', linewidth=2)
                        
                        # Plot target line
                        target_temp = probe_data[target_col].iloc[0]
                        ax.axhline(y=target_temp, color=color, linestyle='--', alpha=0.5)
                        
                        color_idx += 1
        
        ax.set_title(f'Cook {cook_id[:8]}... ({cook_session["duration_hours"]:.1f}h)')
        ax.set_xlabel('Elapsed Time (minutes)')
        ax.set_ylabel('Temperature (°F)')
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'temperature_curves_overview.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Heating rate analysis
    create_heating_rate_analysis(all_analyses)
    
    # 3. Stall detection visualization
    create_stall_analysis(all_analyses)
    
    # 4. Heat transfer analysis
    create_heat_transfer_analysis(all_analyses)

def create_heating_rate_analysis(all_analyses):
    """Analyze heating rates across all cook sessions."""
    
    heating_rates = []
    temp_differentials = []
    stall_info = []
    
    for analysis in all_analyses:
        for probe_name, probe_data in analysis['probes'].items():
            if 'average_rate' in probe_data:
                heating_rates.append(probe_data['average_rate'])
                if 'heat_transfer' in probe_data:
                    temp_differentials.append(probe_data['heat_transfer'].get('avg_temp_differential', 0))
                
                stall_info.append({
                    'stall_detected': probe_data.get('stall_detected', False),
                    'stall_duration': probe_data.get('stall_duration', 0),
                    'average_rate': probe_data['average_rate']
                })
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # Heating rate distribution
    axes[0, 0].hist(heating_rates, bins=20, edgecolor='black', alpha=0.7)
    axes[0, 0].set_title('Distribution of Average Heating Rates')
    axes[0, 0].set_xlabel('Heating Rate (°F/min)')
    axes[0, 0].set_ylabel('Frequency')
    axes[0, 0].axvline(np.mean(heating_rates), color='red', linestyle='--', 
                      label=f'Mean: {np.mean(heating_rates):.2f}')
    axes[0, 0].legend()
    
    # Temperature differential vs heating rate
    if temp_differentials:
        axes[0, 1].scatter(temp_differentials, heating_rates, alpha=0.6)
        axes[0, 1].set_title('Heating Rate vs Temperature Differential')
        axes[0, 1].set_xlabel('Grill-Probe Temperature Diff (°F)')
        axes[0, 1].set_ylabel('Heating Rate (°F/min)')
        
        # Add trend line
        if len(temp_differentials) > 1:
            z = np.polyfit(temp_differentials, heating_rates, 1)
            p = np.poly1d(z)
            axes[0, 1].plot(temp_differentials, p(temp_differentials), "r--", alpha=0.8)
    
    # Stall analysis
    stall_detected = [s for s in stall_info if s['stall_detected']]
    no_stall = [s for s in stall_info if not s['stall_detected']]
    
    if stall_detected and no_stall:
        stall_rates = [s['average_rate'] for s in stall_detected]
        no_stall_rates = [s['average_rate'] for s in no_stall]
        
        axes[1, 0].boxplot([stall_rates, no_stall_rates], labels=['Stall Detected', 'No Stall'])
        axes[1, 0].set_title('Heating Rates: Stall vs No Stall')
        axes[1, 0].set_ylabel('Average Heating Rate (°F/min)')
    
    # Stall duration distribution
    stall_durations = [s['stall_duration'] for s in stall_detected if s['stall_duration'] > 0]
    if stall_durations:
        axes[1, 1].hist(stall_durations, bins=15, edgecolor='black', alpha=0.7)
        axes[1, 1].set_title('Distribution of Stall Durations')
        axes[1, 1].set_xlabel('Stall Duration (minutes)')
        axes[1, 1].set_ylabel('Frequency')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / 'heating_rate_analysis.png', dpi=300, bbox_inches='tight')
    plt.close()

def create_stall_analysis(all_analyses):
    """Detailed stall phenomenon analysis."""
    print("\nStall Analysis Summary:")
    print("=" * 40)
    
    total_probes = 0
    stalls_detected = 0
    stall_details = []
    
    for analysis in all_analyses:
        for probe_name, probe_data in analysis['probes'].items():
            total_probes += 1
            if probe_data.get('stall_detected', False):
                stalls_detected += 1
                stall_details.append({
                    'cook_id': analysis['cook_id'],
                    'probe': probe_name,
                    'duration': probe_data.get('stall_duration', 0),
                    'temp_range': probe_data.get('stall_temp_range', 0),
                    'target_temp': probe_data.get('target_temp', 0)
                })
    
    print(f"Stalls detected: {stalls_detected}/{total_probes} ({stalls_detected/total_probes*100:.1f}%)")
    
    if stall_details:
        avg_duration = np.mean([s['duration'] for s in stall_details])
        print(f"Average stall duration: {avg_duration:.1f} minutes")
        
        # Group by target temperature ranges
        temp_ranges = {
            'Low (≤165°F)': [s for s in stall_details if s['target_temp'] <= 165],
            'Medium (165-185°F)': [s for s in stall_details if 165 < s['target_temp'] <= 185],
            'High (>185°F)': [s for s in stall_details if s['target_temp'] > 185]
        }
        
        for range_name, stalls in temp_ranges.items():
            if stalls:
                avg_dur = np.mean([s['duration'] for s in stalls])
                print(f"  {range_name}: {len(stalls)} stalls, avg {avg_dur:.1f} min")

def create_heat_transfer_analysis(all_analyses):
    """Analyze heat transfer characteristics."""
    
    efficiencies = []
    thermal_masses = []
    responsiveness = []
    
    for analysis in all_analyses:
        for probe_name, probe_data in analysis['probes'].items():
            if 'heating_model' in probe_data and probe_data['heating_model'].get('fitted'):
                efficiencies.append(probe_data['heating_model']['efficiency'])
                
                # Estimate thermal mass from heating curve
                k = probe_data['heating_model']['k']
                thermal_masses.append(1/k if k > 0 else 0)
            
            if 'heat_transfer' in probe_data:
                resp = probe_data['heat_transfer'].get('thermal_responsiveness', 0)
                if resp > 0:
                    responsiveness.append(resp)
    
    if efficiencies or responsiveness:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        
        if efficiencies:
            axes[0].hist(efficiencies, bins=15, edgecolor='black', alpha=0.7)
            axes[0].set_title('Heating Efficiency Distribution')
            axes[0].set_xlabel('Efficiency Factor')
            axes[0].set_ylabel('Frequency')
        
        if thermal_masses:
            axes[1].hist(thermal_masses, bins=15, edgecolor='black', alpha=0.7)
            axes[1].set_title('Thermal Mass Distribution (1/k)')
            axes[1].set_xlabel('Thermal Mass Indicator')
            axes[1].set_ylabel('Frequency')
        
        if responsiveness:
            axes[2].hist(responsiveness, bins=15, edgecolor='black', alpha=0.7)
            axes[2].set_title('Thermal Responsiveness Distribution')
            axes[2].set_xlabel('Responsiveness (rate/temp_diff)')
            axes[2].set_ylabel('Frequency')
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / 'heat_transfer_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()

def main():
    """Run comprehensive cook data analysis."""
    print("Comprehensive Cook Data Analysis")
    print("=" * 50)
    
    # Extract all cook sessions
    cook_sessions = extract_all_cook_sessions()
    
    if not cook_sessions:
        print("No cook sessions found!")
        return
    
    # Analyze detailed data for substantial cook sessions
    all_analyses = []
    
    for i, cook_session in enumerate(cook_sessions[:15]):  # Analyze top 15 cook sessions
        cook_id = cook_session['cook_id']
        print(f"\nAnalyzing cook {i+1}/15: {cook_id}")
        print(f"  Duration: {cook_session['duration_hours']:.1f} hours")
        
        # Extract detailed data
        df = extract_detailed_cook_data(cook_id)
        if df.empty:
            print(f"  No data extracted for {cook_id}")
            continue
        
        # Analyze temperature curves
        analysis = analyze_temperature_curves(df, cook_id)
        if analysis['probes']:
            all_analyses.append(analysis)
            print(f"  Probes analyzed: {len(analysis['probes'])}")
            
            for probe_name, probe_data in analysis['probes'].items():
                target_reached = "✓" if probe_data['target_reached'] else "✗"
                stall = "✓" if probe_data.get('stall_detected') else "✗"
                print(f"    {probe_name}: Target {target_reached}, Stall {stall}, "
                      f"Rate: {probe_data.get('average_rate', 0):.2f}°F/min")
    
    # Create comprehensive analysis report
    print(f"\nGenerating analysis report from {len(all_analyses)} cook sessions...")
    
    # Save detailed analysis
    analysis_summary = {
        'total_cook_sessions': len(all_analyses),
        'total_probe_analyses': sum(len(a['probes']) for a in all_analyses),
        'summary_statistics': calculate_summary_statistics(all_analyses)
    }
    
    # Create visualizations
    create_comprehensive_visualizations(all_analyses)
    
    # Print summary
    print("\nANALYSIS SUMMARY")
    print("=" * 50)
    print(f"Cook sessions analyzed: {analysis_summary['total_cook_sessions']}")
    print(f"Individual probe analyses: {analysis_summary['total_probe_analyses']}")
    
    stats = analysis_summary['summary_statistics']
    print(f"\nAverage heating rate: {stats['avg_heating_rate']:.2f} ± {stats['std_heating_rate']:.2f} °F/min")
    print(f"Target achievement rate: {stats['target_achievement_rate']:.1f}%")
    print(f"Stall detection rate: {stats['stall_rate']:.1f}%")
    print(f"Average time to target: {stats['avg_time_to_target']:.1f} minutes")
    
    print(f"\nAnalysis outputs saved to: {OUTPUT_DIR}")
    print("  - temperature_curves_overview.png")
    print("  - heating_rate_analysis.png") 
    print("  - heat_transfer_analysis.png")

def calculate_summary_statistics(all_analyses):
    """Calculate overall summary statistics."""
    
    heating_rates = []
    times_to_target = []
    targets_reached = 0
    stalls_detected = 0
    total_probes = 0
    
    for analysis in all_analyses:
        for probe_name, probe_data in analysis['probes'].items():
            total_probes += 1
            
            if 'average_rate' in probe_data:
                heating_rates.append(probe_data['average_rate'])
            
            if probe_data.get('target_reached'):
                targets_reached += 1
                if probe_data.get('time_to_target_minutes'):
                    times_to_target.append(probe_data['time_to_target_minutes'])
            
            if probe_data.get('stall_detected'):
                stalls_detected += 1
    
    return {
        'avg_heating_rate': np.mean(heating_rates) if heating_rates else 0,
        'std_heating_rate': np.std(heating_rates) if heating_rates else 0,
        'target_achievement_rate': (targets_reached / total_probes * 100) if total_probes > 0 else 0,
        'stall_rate': (stalls_detected / total_probes * 100) if total_probes > 0 else 0,
        'avg_time_to_target': np.mean(times_to_target) if times_to_target else 0
    }

if __name__ == "__main__":
    main()