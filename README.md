# Traeger Grill Library

This library allows for interaction with Traeger WiFire Grills, enabling the control and monitoring of grill and probe temperatures, timers, and various grill modes without the need for Home Assistant integration.

## Features

- Control and monitor grill and probe temperatures
- Set and manage grill timers
- Monitor grill state and mode
- Enable or disable SuperSmoke mode
- Initiate grill shutdown

## Getting Started

To use this library, you will need your Traeger account credentials (username and password) to authenticate and interact with your grill.

### Installation

1. Install the library using pip:

```bash
pip install traeger
```

2. Import the library in your Python script:

```python
from traeger import Traeger
```

### Usage

1. Initialize the Traeger object with your credentials:

```python
grill = Traeger(username='your_username', password='your_password')
```

2. Start interacting with your grill, for example, get the current grill temperature:

```python
temperature = grill.get_temperature()
print(f"Current Grill Temperature: {temperature}°F")
```

For more detailed documentation on available methods and their usage, please refer to the [API Documentation](https://github.com/captivus/hass_traeger/docs).

## Contributing

Contributions to this library are welcome. Please refer to the [contribution guidelines](CONTRIBUTING.md) for more information.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
