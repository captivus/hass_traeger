#!/usr/bin/env python3
"""Simple Flask server for Traeger monitor UI."""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, render_template, send_from_directory

app = Flask(__name__, static_folder='static', static_url_path='')
DB_PATH = Path("../data/traeger.db")


@app.route('/')
def index():
    """Serve the main page."""
    return send_from_directory('static', 'index.html')


@app.route('/api/current')
def get_current():
    """Get the most recent grill status."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT timestamp, payload 
            FROM raw_messages 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        
        if row:
            timestamp, payload = row
            data = json.loads(payload)
            status = data.get('status', {})
            
            return jsonify({
                'timestamp': timestamp,
                'grill_temp': status.get('grill'),
                'grill_set': status.get('set'),
                'ambient': status.get('ambient'),
                'probe_temp': status.get('probe'),
                'probe_set': status.get('probe_set'),
                'cook_id': status.get('cook_id'),
                'system_status': status.get('system_status'),
                'pellet_level': status.get('pellet_level'),
                'connected': status.get('connected', False)
            })
        
        return jsonify({'error': 'No data available'}), 404


@app.route('/api/history/<int:hours>')
def get_history(hours):
    """Get temperature history for the last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT timestamp, payload 
            FROM raw_messages 
            WHERE timestamp > ?
            ORDER BY timestamp ASC
        """, (cutoff.isoformat(),))
        
        data_points = []
        for row in cursor:
            timestamp, payload = row
            data = json.loads(payload)
            status = data.get('status', {})
            
            data_points.append({
                'timestamp': timestamp,
                'grill_temp': status.get('grill'),
                'grill_set': status.get('set'),
                'ambient': status.get('ambient'),
                'probe_temp': status.get('probe'),
                'probe_set': status.get('probe_set')
            })
        
        return jsonify(data_points)


@app.route('/api/predict/<cook_id>/<probe_id>')
def get_prediction(cook_id, probe_id):
    """Get temperature prediction (placeholder for now)."""
    return jsonify({
        'cook_id': cook_id,
        'probe_id': probe_id,
        'minutes_to_target': None,
        'method': 'Not implemented yet'
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)