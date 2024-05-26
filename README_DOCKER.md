# Running Graphite in a Docker container

TODO: Update this with instructions and details on how to run the Graphite docker container.
* `./graphite/data` is the old directory that contains your first runs with Graphite (which seemed to have data but weren't showing in the Graphite composer).
* Where *should* you put the `storage-schemas.conf` file that you've saved in `./graphite/data`?


From the [official docker container's documentation](https://hub.docker.com/r/graphiteapp/graphite-statsd):
 
>     ## A Note on Volumes
>     You may find it useful to mount explicit volumes so configs & data can be managed from a known location on the host.
> 
>     Simply specify the desired volumes when starting the container.
> 
>     ```bash
>     docker run -d\
>     --name graphite\
>     --restart=always\
>     -v /path/to/graphite/configs:/opt/graphite/conf\
>     -v /path/to/graphite/data:/opt/graphite/storage\
>     -v /path/to/statsd_config:/opt/statsd/config\
>     graphiteapp/graphite-statsd
>     ```
>     Note: The container will initialize properly if you mount empty volumes at /opt/graphite/conf, /opt/graphite/storage, or /opt/statsd/config.
> 

You only got this working properly after you added the following lines in the volumes section of your `docker-compose.yml`:

```yaml
    volumes:
      - ./graphite/storage:/opt/graphite/storage
      - ./graphite/conf:/opt/graphite/conf
```

Are there more of these mounted volumes that you need to add to make this work properly?  (See "Mounted Volumes" section in the image documentation above.)