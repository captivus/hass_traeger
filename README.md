# Traeger Stream

A clean, Python-native library for streaming live data from Traeger grills with real-time web visualization.

## Features

- 🔥 **Real-time Data Streaming** - Get live updates from your Traeger grill via MQTT WebSocket
- 📊 **Interactive Web Dashboard** - Beautiful Streamlit interface with Plotly charts
- 🌡️ **Multi-Probe Support** - Monitor grill and up to 4 probe temperatures
- 📱 **Mobile Friendly** - Responsive design works on any device
- 💾 **Data Export** - Export cook data for analysis
- 🎯 **Type-Safe** - Pydantic models for all data structures

## Quick Start

See the [traeger-stream](./traeger-stream) directory for the main application.

```bash
cd traeger-stream
uv sync
cp .env.example .env
# Edit .env with your Traeger credentials

# Run the web dashboard
uv run streamlit run app.py
```

## Documentation

Full documentation is available in the [traeger-stream README](./traeger-stream/README.md).

## License

This project is licensed under the GNU General Public License v2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Originally forked from [sebirdman/hass_traeger](https://github.com/sebirdman/hass_traeger)