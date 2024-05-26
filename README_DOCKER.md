### Explanation

1. **docker-compose.yml**: This file defines a single service (`graphite`) that uses the `graphiteapp/graphite-statsd` Docker image. It maps the necessary ports and mounts a volume for persistent storage.

    - Ports:
      - `80:80`: Graphite web interface
      - `2003-2004`: Carbon ports
      - `2023-2024`: Carbon cache query ports
      - `8125/udp`: StatsD port
      - `8126`: StatsD management port

2. **Persistent Storage**: The `./data` directory is created on the host machine to store Graphite data.

3. **Docker Compose**: The script runs `docker-compose up -d` to start the Graphite service in detached mode.

### Usage

1. Save the script to a file, e.g., `setup_graphite.py`.
2. Run the script using Python:

    ```sh
    python setup_graphite.py
    ```

3. Once the script completes, Graphite will be running and accessible at [http://localhost](http://localhost).

### Verifying the Setup

After running the script, you can verify that Graphite is working by accessing the web interface at [http://localhost](http://localhost). You can also check the logs of the Docker containers to ensure everything is running correctly:

```sh
docker-compose logs
```

### Configuring Your Project

Update the `~/.traeger` configuration file to point to the Graphite server running on `localhost`:

```json
{
    "username": "your_traeger_username",
    "password": "your_traeger_password",
    "graphite_port": "2003",
    "graphite_host": "localhost"
}
```

Now your `traeger2graphite.py` script will send the collected stats to the locally running Graphite server.

This setup ensures that you have a fully functional Graphite instance running in Docker, ready to collect and visualize data from your Traeger grills. If you encounter any issues or need further customization, feel free to ask!