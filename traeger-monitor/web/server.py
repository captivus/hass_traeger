#!/usr/bin/env python3
"""Ultra-simple Flask API for Traeger monitor - ~40 lines."""
import json, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, send_from_directory
import pytz

app = Flask(__name__, static_folder='static')
DB_PATH = Path(__file__).parent.parent / "data" / "traeger.db"

# Timezone setup for US Central Time
CENTRAL_TZ = pytz.timezone('US/Central')
UTC_TZ = pytz.UTC

def convert_to_central(utc_timestamp_str):
    """Convert UTC timestamp string to US Central Time string."""
    try:
        utc_dt = datetime.fromisoformat(utc_timestamp_str.replace('Z', '+00:00'))
        if utc_dt.tzinfo is None:
            utc_dt = UTC_TZ.localize(utc_dt)
        central_dt = utc_dt.astimezone(CENTRAL_TZ)
        return central_dt.strftime('%Y-%m-%d %H:%M:%S %Z')
    except:
        return utc_timestamp_str

def extract_probes(status):
    """Extract all probe data from status."""
    probes = []
    legacy_temp = None
    
    # Check legacy format
    if status.get('probe_con') == 1 and status.get('probe'):
        legacy_temp = status['probe']
        probes.append({'channel': 'legacy', 'temp': legacy_temp, 'target': status.get('probe_set')})
    
    # Check acc array for modern probes
    for acc in status.get('acc', []):
        if acc.get('con') != 1: continue
        if acc['type'] == 'probe':
            p = acc.get('probe', {})
            probe_temp = p.get('get_temp')
            # Skip if this probe has same temperature as legacy (likely same physical probe)
            if legacy_temp is not None and probe_temp == legacy_temp:
                continue
            probes.append({'channel': acc['channel'], 'temp': probe_temp, 'target': p.get('set_temp')})
        elif acc['type'] == 'btprobe':
            p = acc.get('btprobe', {})
            probes.append({'channel': acc['channel'], 'temp': p.get('get_temp'), 
                         'target': p.get('set_temp'), 'battery': p.get('batt')})
    return probes

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/api/current')
def get_current():
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT timestamp, payload FROM raw_messages ORDER BY datetime(timestamp) DESC LIMIT 1").fetchone()
        if not row: return jsonify({'error': 'No data'}), 404
        status = json.loads(row[1]).get('status', {})
        return jsonify({'timestamp': convert_to_central(row[0]), 'grill_temp': status.get('grill'), 'grill_set': status.get('set'),
                       'ambient': status.get('ambient'), 'probes': extract_probes(status), 
                       'cook_id': status.get('cook_id'), 'pellet_level': status.get('pellet_level')})

@app.route('/api/history/<int:hours>')
def get_history(hours):
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT timestamp, payload FROM raw_messages WHERE datetime(timestamp) > datetime(?) ORDER BY datetime(timestamp)", (cutoff,))
        return jsonify([{'timestamp': convert_to_central(r[0]), 'grill_temp': (s := json.loads(r[1]).get('status', {})).get('grill'),
                        'grill_set': s.get('set'), 'ambient': s.get('ambient'), 'probes': extract_probes(s)} for r in rows])

@app.route('/api/predict/<cook_id>/<probe_channel>')
def get_prediction(cook_id, probe_channel):
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from predict import predict
    return jsonify(predict(cook_id, probe_channel))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)