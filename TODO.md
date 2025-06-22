# TODO
* The plan needs to describe the acceptance criteria for each of the features so that an engineer can independently know when each feature is correctly and fully implemented.
* Navigate the documentation for Claude Code: https://docs.anthropic.com/en/docs/claude-code/overview  Tell me how to prepare and deploy a container so that Claude Code can run in YOLO mode safely inside it. I want Claude to be able to execute all commands that he wants to inside of this container so he can work on my project independently.


* We really need a service that will run and collect all of the streamed data from the grill and save it
  * That's the primary thing we need
  * Then we make predictions about time to target temp per probe
  * We then sit a visualization tool on top of these
* Move this whole thing out of Streamlit ... it's kind of awful
* The Traeger app shows "Asleep" as the current status of the grill. Why do we show "STARTUP" as the status?
* Where did I get CLIENT_ID (client.py) from originally? Search the web if you need in order to figure this out.