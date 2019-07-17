# spAnser Cogs

These cogs are designed to work with Red Bot v2 designed by Twentysix26.

## Daily
----

Was designed to handle 24 hour slow mode without having to track every member. Instead it resets everyone at the same time every day.

## Dialogflow
----
This requires the dialogflow python library: `pip install dialogflow`

Was designed to welcome users to a server and ask them to read rules and inform them of recruiting channels. This bot uses Dialogflow for smart responses. Can currently add roles and kick members based on their responses.

```json
{
    "server_if_unknown": "SERVER_ID",
    "project_id": "DIALOGFLOW_PROJECT_ID",
    "service_credentials": "servicecredentials-012345-67890abcdef0.json",
    "try_again_message": "I did not understand you, try answering again.",
    "welcome_message": "Thank you for answering the questions. Please enjoy your stay. If you need any additional assitance please contact one of the mods.",
    "on_member_join": {
        "actions": [
            {
                "action": "inquire",
                "inquiry": "__member_join__"
            }
        ]
    },
    "on_message": [],
    "SERVER_ID": {
        "log_channel": "CHANNEL_ID"
    }
}
```


The `"on_message"` array is words that can be used in a DM to start a Dialogflow conversation. In the example action `inquire` the inquiry `__member_join__` is one of the training phrases in Dialogflow. Dialogflow reponds with a custom payload:
```json
{
  "actions": [
    {
      "action": "question",
      "message": "Welcome to my server.\nDo you agree to follow the rules listed in <#__CHANNEL_ID__>?"
    }
  ]
}
```

There is currently no commands to edit the bots settings. Everything is set in the json file manually for the time being.

## Slot machine
----
Modified slot machine.
