# TODO
* Thoroughly test predicted time for each of the set temps on the probes
* The UI should show the 1st and 2nd derivatives of temperature per minute for each probe, in addition to the estimated time to target temperature.
* We really need a service that will run and collect all of the streamed data from the grill and save it
  * That's the primary thing we need
  * Then we make predictions about time to target temp per probe
  * We then sit a visualization tool on top of these
* Move this whole thing out of Streamlit ... it's kind of awful
* The Traeger app shows "Asleep" as the current status of the grill. Why do we show "STARTUP" as the status?
* Where did I get CLIENT_ID (client.py) from originally? Search the web if you need in order to figure this out.