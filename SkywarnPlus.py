#!/usr/bin/python3

"""
SkywarnPlus.py v0.5.1 by Mason Nelson
===============================================================================
SkywarnPlus is a utility that retrieves severe weather alerts from the National 
Weather Service and integrates these alerts with an Asterisk/app_rpt based 
radio repeater controller. 

This utility is designed to be highly configurable, allowing users to specify 
particular counties for which to check for alerts, the types of alerts to include 
or block, and how these alerts are integrated into their radio repeater system. 

This includes features such as automatic voice alerts and a tail message feature 
for constant updates. All alerts are sorted by severity and cover a broad range 
of weather conditions such as hurricane warnings, thunderstorms, heat waves, etc. 

Configurable through a .yaml file, SkywarnPlus serves as a comprehensive and 
flexible tool for those who need to stay informed about weather conditions 
and disseminate this information through their radio repeater system.

This file is part of SkywarnPlus.
SkywarnPlus is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version. SkywarnPlus is distributed in the hope
that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
You should have received a copy of the GNU General Public License along with SkywarnPlus. If not, see <https://www.gnu.org/licenses/>.
"""

import os
import json
import logging
import requests
import shutil
import fnmatch
import subprocess
import time
import wave
import contextlib
import math
import sys
import itertools
from datetime import datetime, timezone, timedelta
from dateutil import parser
from pydub import AudioSegment
from ruamel.yaml import YAML
from collections import OrderedDict

# Use ruamel.yaml instead of PyYAML
yaml = YAML()

# Directories and Paths
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
COUNTY_CODES_PATH = os.path.join(BASE_DIR, "CountyCodes.md")

# Open and read configuration file
with open(CONFIG_PATH, "r") as config_file:
    config = yaml.load(config_file)
    config = json.loads(json.dumps(config))  # Convert config to a normal dictionary

# Check if SkywarnPlus is enabled
MASTER_ENABLE = config.get("SKYWARNPLUS", {}).get("Enable", False)
if not MASTER_ENABLE:
    print("SkywarnPlus is disabled in config.yaml, exiting...")
    exit()

# Define tmp_dir and sounds_path
TMP_DIR = config.get("DEV", {}).get("TmpDir", "/tmp/SkywarnPlus")
SOUNDS_PATH = config.get("Alerting", {}).get(
    "SoundsPath", os.path.join(BASE_DIR, "SOUNDS")
)

# Create tmp_dir if it doesn't exist
if TMP_DIR:
    os.makedirs(TMP_DIR, exist_ok=True)
else:
    print("Error: tmp_dir is not set.")

# Define Blocked events
GLOBAL_BLOCKED_EVENTS = config.get("Blocking", {}).get("GlobalBlockedEvents", [])
if GLOBAL_BLOCKED_EVENTS is None:
    GLOBAL_BLOCKED_EVENTS = []
SAYALERT_BLOCKED_EVENTS = config.get("Blocking", {}).get("SayAlertBlockedEvents", [])
if SAYALERT_BLOCKED_EVENTS is None:
    SAYALERT_BLOCKED_EVENTS = []
TAILMESSAGE_BLOCKED_EVENTS = config.get("Blocking", {}).get(
    "TailmessageBlockedEvents", []
)
if TAILMESSAGE_BLOCKED_EVENTS is None:
    TAILMESSAGE_BLOCKED_EVENTS = []

# Define Max Alerts
MAX_ALERTS = config.get("Alerting", {}).get("MaxAlerts", 99)

# Define audio_delay
AUDIO_DELAY = config.get("Asterisk", {}).get("AudioDelay", 0)

# Define Tailmessage configuration
TAILMESSAGE_CONFIG = config.get("Tailmessage", {})
ENABLE_TAILMESSAGE = TAILMESSAGE_CONFIG.get("Enable", False)
TAILMESSAGE_FILE = TAILMESSAGE_CONFIG.get(
    "TailmessagePath", os.path.join(TMP_DIR, "wx-tail.wav")
)

# Define IDChange configuration
IDCHANGE_CONFIG = config.get("IDChange", {})
ENABLE_IDCHANGE = IDCHANGE_CONFIG.get("Enable", False)

# Data file path
DATA_FILE = os.path.join(TMP_DIR, "data.json")

# Tones directory
TONE_DIR = config["CourtesyTones"].get("ToneDir", os.path.join(SOUNDS_PATH, "TONES"))

# Define possible alert strings
ALERT_STRINGS = [
    "911 Telephone Outage Emergency",
    "Administrative Message",
    "Air Quality Alert",
    "Air Stagnation Advisory",
    "Arroyo And Small Stream Flood Advisory",
    "Ashfall Advisory",
    "Ashfall Warning",
    "Avalanche Advisory",
    "Avalanche Warning",
    "Avalanche Watch",
    "Beach Hazards Statement",
    "Blizzard Warning",
    "Blizzard Watch",
    "Blowing Dust Advisory",
    "Blowing Dust Warning",
    "Brisk Wind Advisory",
    "Child Abduction Emergency",
    "Civil Danger Warning",
    "Civil Emergency Message",
    "Coastal Flood Advisory",
    "Coastal Flood Statement",
    "Coastal Flood Warning",
    "Coastal Flood Watch",
    "Dense Fog Advisory",
    "Dense Smoke Advisory",
    "Dust Advisory",
    "Dust Storm Warning",
    "Earthquake Warning",
    "Evacuation - Immediate",
    "Excessive Heat Warning",
    "Excessive Heat Watch",
    "Extreme Cold Warning",
    "Extreme Cold Watch",
    "Extreme Fire Danger",
    "Extreme Wind Warning",
    "Fire Warning",
    "Fire Weather Watch",
    "Flash Flood Statement",
    "Flash Flood Warning",
    "Flash Flood Watch",
    "Flood Advisory",
    "Flood Statement",
    "Flood Warning",
    "Flood Watch",
    "Freeze Warning",
    "Freeze Watch",
    "Freezing Fog Advisory",
    "Freezing Rain Advisory",
    "Freezing Spray Advisory",
    "Frost Advisory",
    "Gale Warning",
    "Gale Watch",
    "Hard Freeze Warning",
    "Hard Freeze Watch",
    "Hazardous Materials Warning",
    "Hazardous Seas Warning",
    "Hazardous Seas Watch",
    "Hazardous Weather Outlook",
    "Heat Advisory",
    "Heavy Freezing Spray Warning",
    "Heavy Freezing Spray Watch",
    "High Surf Advisory",
    "High Surf Warning",
    "High Wind Warning",
    "High Wind Watch",
    "Hurricane Force Wind Warning",
    "Hurricane Force Wind Watch",
    "Hurricane Local Statement",
    "Hurricane Warning",
    "Hurricane Watch",
    "Hydrologic Advisory",
    "Hydrologic Outlook",
    "Ice Storm Warning",
    "Lake Effect Snow Advisory",
    "Lake Effect Snow Warning",
    "Lake Effect Snow Watch",
    "Lake Wind Advisory",
    "Lakeshore Flood Advisory",
    "Lakeshore Flood Statement",
    "Lakeshore Flood Warning",
    "Lakeshore Flood Watch",
    "Law Enforcement Warning",
    "Local Area Emergency",
    "Low Water Advisory",
    "Marine Weather Statement",
    "Nuclear Power Plant Warning",
    "Radiological Hazard Warning",
    "Red Flag Warning",
    "Rip Current Statement",
    "Severe Thunderstorm Warning",
    "Severe Thunderstorm Watch",
    "Severe Weather Statement",
    "Shelter In Place Warning",
    "Short Term Forecast",
    "Small Craft Advisory",
    "Small Craft Advisory For Hazardous Seas",
    "Small Craft Advisory For Rough Bar",
    "Small Craft Advisory For Winds",
    "Small Stream Flood Advisory",
    "Snow Squall Warning",
    "Special Marine Warning",
    "Special Weather Statement",
    "Storm Surge Warning",
    "Storm Surge Watch",
    "Storm Warning",
    "Storm Watch",
    "Test",
    "Tornado Warning",
    "Tornado Watch",
    "Tropical Depression Local Statement",
    "Tropical Storm Local Statement",
    "Tropical Storm Warning",
    "Tropical Storm Watch",
    "Tsunami Advisory",
    "Tsunami Warning",
    "Tsunami Watch",
    "Typhoon Local Statement",
    "Typhoon Warning",
    "Typhoon Watch",
    "Urban And Small Stream Flood Advisory",
    "Volcano Warning",
    "Wind Advisory",
    "Wind Chill Advisory",
    "Wind Chill Warning",
    "Wind Chill Watch",
    "Winter Storm Warning",
    "Winter Storm Watch",
    "Winter Weather Advisory",
]

# Generate the WA list based on the length of WS
ALERT_INDEXES = [str(i + 1) for i in range(len(ALERT_STRINGS))]

# Test if the script needs to start from a clean slate
CLEANSLATE = config.get("DEV", {}).get("CLEANSLATE", False)
if CLEANSLATE:
    shutil.rmtree(TMP_DIR)
    os.mkdir(TMP_DIR)

# Logging setup
LOG_CONFIG = config.get("Logging", {})
ENABLE_DEBUG = LOG_CONFIG.get("Debug", False)
LOG_FILE = LOG_CONFIG.get("LogPath", os.path.join(TMP_DIR, "SkywarnPlus.log"))

# Set up logging
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG if ENABLE_DEBUG else logging.INFO)

# Set up log message formatting
LOG_FORMATTER = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

# Set up console log handler
C_HANDLER = logging.StreamHandler()
C_HANDLER.setFormatter(LOG_FORMATTER)
LOGGER.addHandler(C_HANDLER)

# Set up file log handler
F_HANDLER = logging.FileHandler(LOG_FILE)
F_HANDLER.setFormatter(LOG_FORMATTER)
LOGGER.addHandler(F_HANDLER)

# Get the "CountyCodes" from the config
COUNTY_CODES_CONFIG = config.get("Alerting", {}).get("CountyCodes", [])

# Initialize COUNTY_CODES and COUNTY_WAVS
COUNTY_CODES = []
COUNTY_WAVS = []

# Check the type of "CountyCodes" config to handle both list and dictionary
if isinstance(COUNTY_CODES_CONFIG, list):
    # If it's a list, check if it's a list of strings or dictionaries
    if all(isinstance(i, str) for i in COUNTY_CODES_CONFIG):
        # It's the old format and we can use it directly
        COUNTY_CODES = COUNTY_CODES_CONFIG
    elif all(isinstance(i, dict) for i in COUNTY_CODES_CONFIG):
        # It's a list of dictionaries with WAV files
        # We need to separate the county codes and the WAVs
        for dic in COUNTY_CODES_CONFIG:
            for key, value in dic.items():
                COUNTY_CODES.append(key)
                COUNTY_WAVS.append(value)
elif isinstance(COUNTY_CODES_CONFIG, dict):
    # If it's a dictionary, it's got WAV files
    # We need to separate the county codes and the WAVs
    COUNTY_CODES = list(COUNTY_CODES_CONFIG.keys())
    COUNTY_WAVS = list(COUNTY_CODES_CONFIG.values())
else:
    # Invalid format, set it to an empty list
    COUNTY_CODES = []
    COUNTY_WAVS = []

# Log some debugging information
LOGGER.debug("Base directory: %s", BASE_DIR)
LOGGER.debug("Temporary directory: %s", TMP_DIR)
LOGGER.debug("Sounds path: %s", SOUNDS_PATH)
LOGGER.debug("Tailmessage path: %s", TAILMESSAGE_FILE)
LOGGER.debug("Global Blocked events: %s", GLOBAL_BLOCKED_EVENTS)
LOGGER.debug("SayAlert Blocked events: %s", SAYALERT_BLOCKED_EVENTS)
LOGGER.debug("Tailmessage Blocked events: %s", TAILMESSAGE_BLOCKED_EVENTS)


def load_state():
    """
    Load the state from the state file if it exists, else return an initial state.

    The state file is expected to be a JSON file. If certain keys are missing in the
    loaded state, this function will provide default values for those keys.
    """

    # Check if the state data file exists
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as file:
            state = json.load(file)

            # Ensure 'alertscript_alerts' key is present in the state, default to an empty list
            state["alertscript_alerts"] = state.get("alertscript_alerts", [])

            # Process 'last_alerts' key to maintain the order of alerts using OrderedDict
            # This step is necessary because JSON does not preserve order by default
            last_alerts = state.get("last_alerts", [])
            state["last_alerts"] = OrderedDict((x[0], x[1]) for x in last_alerts)

            # Ensure 'last_sayalert' and 'active_alerts' keys are present in the state
            state["last_sayalert"] = state.get("last_sayalert", [])
            state["active_alerts"] = state.get("active_alerts", [])

            return state

    # If the state data file does not exist, return a default state
    else:
        return {
            "ct": None,
            "id": None,
            "alertscript_alerts": [],
            "last_alerts": OrderedDict(),
            "last_sayalert": [],
            "active_alerts": [],
        }


def save_state(state):
    """
    Save the state to the state file.

    The state is saved as a JSON file. The function ensures certain keys in the state
    are converted to lists before saving, ensuring consistency and ease of processing
    when the state is later loaded.
    """

    # Convert 'alertscript_alerts', 'last_sayalert', and 'active_alerts' keys to lists
    # This ensures consistency in data format, especially useful when loading the state later
    state["alertscript_alerts"] = list(state["alertscript_alerts"])
    state["last_sayalert"] = list(state["last_sayalert"])
    state["active_alerts"] = list(state["active_alerts"])

    # Convert 'last_alerts' from OrderedDict to list of items
    # This step is necessary because JSON does not natively support OrderedDict
    state["last_alerts"] = list(state["last_alerts"].items())

    # Save the state to the data file in a formatted manner
    with open(DATA_FILE, "w") as file:
        json.dump(state, file, ensure_ascii=False, indent=4)


def get_alerts(countyCodes):
    """
    Retrieves severe weather alerts for specified county codes and processes them.
    """

    # Define mappings to convert severity levels from various terminologies to a numeric scale
    severity_mapping_api = {
        "Extreme": 4,
        "Severe": 3,
        "Moderate": 2,
        "Minor": 1,
        "Unknown": 0,
    }
    severity_mapping_words = {"Warning": 4, "Watch": 3, "Advisory": 2, "Statement": 1}

    # Initialize storage for the alerts and a set to keep track of processed alerts
    alerts = OrderedDict()
    seen_alerts = set()

    # Log current time for reference
    current_time = datetime.now(timezone.utc)
    LOGGER.debug("getAlerts: Current time: %s", current_time)

    # Handle alert injection for development/testing purposes
    if config.get("DEV", {}).get("INJECT", False):
        LOGGER.debug("getAlerts: DEV Alert Injection Enabled")
        injected_alerts = config["DEV"].get("INJECTALERTS", [])
        LOGGER.debug("getAlerts: Injecting alerts: %s", injected_alerts)

        max_counties = len(countyCodes)  # Assuming countyCodes is a list of counties
        county_codes_cycle = itertools.cycle(countyCodes)

        county_assignment_counter = 1

        for alert_info in injected_alerts:
            if isinstance(alert_info, dict):
                alert_title = alert_info.get("Title", "")
                specified_counties = alert_info.get("CountyCodes", [])
            else:
                continue  # Ignore if not a dictionary

            last_word = alert_title.split()[-1]
            severity = severity_mapping_words.get(last_word, 0)
            description = "This alert was manually injected as a test."

            end_time_str = alert_info.get("EndTime")

            county_data = []

            # If no counties are specified, use the ones provided to the function in an increasing manner
            if not specified_counties:
                # Limit the number of counties assigned to not exceed max_counties
                counties_to_assign = min(county_assignment_counter, max_counties)

                specified_counties = [
                    next(county_codes_cycle) for _ in range(counties_to_assign)
                ]
                county_assignment_counter += 1  # Increment for the next injected alert

            for county in specified_counties:
                if county not in countyCodes:
                    LOGGER.error(
                        "Specified county code '%s' is not defined in the config. Using next available county code from the config.",
                        county,
                    )
                    county = next(county_codes_cycle)

                end_time = (
                    datetime.strptime(end_time_str, "%Y-%m-%dT%H:%M:%SZ")
                    if end_time_str
                    else current_time + timedelta(hours=1)
                )

                county_data.append(
                    {
                        "county_code": county,
                        "severity": severity,
                        "description": description,
                        "end_time_utc": end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    }
                )

            alerts[
                alert_title
            ] = county_data  # Add the list of dictionaries to the alert

        # If injected alerts are used, we return them here and don't proceed with the function.
        return sort_alerts(alerts)

    # Configuration specifies whether to use 'effective' or 'onset' time for alerts.
    # Depending on the configuration, we set the appropriate keys for start and end time.
    timetype_mode = config.get("Alerting", {}).get("TimeType", "onset")
    if timetype_mode == "effective":
        LOGGER.debug("getAlerts: Using effective time for alerting")
        time_type_start = "effective"
        time_type_end = "expires"
    elif timetype_mode == "onset":
        LOGGER.debug("getAlerts: Using onset time for alerting")
        time_type_start = "onset"
        time_type_end = "ends"
    else:
        LOGGER.error(
            "getAlerts: Invalid TimeType specified in config.yaml. Using onset time instead."
        )
        time_type_start = "onset"
        time_type_end = "ends"

    # Loop over each county code and retrieve alerts from the API.
    for countyCode in countyCodes:
        url = "https://api.weather.gov/alerts/active?zone={}".format(countyCode)
        #
        # WARNING: ONLY USE THIS FOR DEVELOPMENT PURPOSES
        # THIS URL WILL RETURN ALL ACTIVE ALERTS IN THE UNITED STATES
        # url = "https://api.weather.gov/alerts/active"
        try:
            # If we can get a successful response from the API, we process the alerts from the response.
            response = requests.get(url)
            response.raise_for_status()
            LOGGER.debug(
                "getAlerts: Checking for alerts in %s at URL: %s", countyCode, url
            )
            alert_data = response.json()
            for feature in alert_data["features"]:
                # Extract start and end times. If end time is missing, use 'expires' time.
                start = feature["properties"].get(time_type_start)
                end = feature["properties"].get(time_type_end)
                if not end:
                    end = feature["properties"].get("expires")
                    LOGGER.debug(
                        'getAlerts: %s has no "%s" time, using "expires" time instead: %s',
                        feature["properties"]["event"],
                        time_type_end,
                        end,
                    )
                if start and end:
                    # If both start and end times are available, convert them to datetime objects.
                    start_time = parser.isoparse(start)
                    end_time = parser.isoparse(end)

                    # Convert alert times to UTC.
                    start_time_utc = start_time.astimezone(timezone.utc)
                    end_time_utc = end_time.astimezone(timezone.utc)
                    event = feature["properties"]["event"]

                    # If the current time is within the alert's active period, we process it further.
                    if start_time_utc <= current_time < end_time_utc:
                        description = feature["properties"].get("description", "")
                        severity = feature["properties"].get("severity", None)

                        # Check if the event is globally blocked as per the configuration. If it is, skip this event.
                        is_blocked = False
                        for global_blocked_event in GLOBAL_BLOCKED_EVENTS:
                            if fnmatch.fnmatch(event, global_blocked_event):
                                LOGGER.debug(
                                    "getAlerts: Globally Blocking %s as per configuration",
                                    event,
                                )
                                is_blocked = True
                                break
                        # If the event is globally blocked, we skip the remaining code in this loop iteration and move to the next one.
                        if is_blocked:
                            continue

                        # Determine severity from event name or API's severity value.
                        if severity is None:
                            last_word = event.split()[-1]
                            severity = severity_mapping_words.get(last_word, 0)
                        else:
                            severity = severity_mapping_api.get(severity, 0)

                        # Log the alerts and their severity level for debugging purposes.
                        LOGGER.debug(
                            "getAlerts: %s - %s - Severity: %s",
                            countyCode,
                            event,
                            severity,
                        )

                        # Check if the event has already been processed (seen).
                        # If it has been seen, we add a new dictionary to its list of alerts. This dictionary contains details about the alert.
                        if event in seen_alerts:
                            alerts[event].append(
                                {
                                    "county_code": countyCode,  # the county code the alert is for
                                    "severity": severity,  # the severity level of the alert
                                    "description": description,  # a description of the alert
                                    "end_time_utc": end_time_utc.strftime(
                                        "%Y-%m-%dT%H:%M:%S.%fZ"
                                    ),  # the time the alert ends in UTC
                                }
                            )
                        # If the event hasn't been seen before, we create a new list entry in the 'alerts' dictionary for this event.
                        else:
                            alerts[event] = [
                                {
                                    "county_code": countyCode,  # the county code the alert is for
                                    "severity": severity,  # the severity level of the alert
                                    "description": description,  # a description of the alert
                                    "end_time_utc": end_time_utc.strftime(
                                        "%Y-%m-%dT%H:%M:%S.%fZ"
                                    ),  # the time the alert ends in UTC
                                }
                            ]
                            # Add the event to the set of seen alerts.
                            seen_alerts.add(event)

                    # If the current time is not within the alert's active period, we skip it.
                    else:
                        time_difference = time_until(start_time_utc, current_time)
                        LOGGER.debug(
                            "getAlerts: Skipping %s, not active for another %s.",
                            event,
                            time_difference,
                        )
                        LOGGER.debug(
                            "Current time: %s | Alert start: %s | Alert end %s",
                            current_time,
                            start_time_utc,
                            end_time_utc,
                        )
                else:
                    LOGGER.debug(
                        "getAlerts: Skipping %s, missing start or end time.",
                        feature["properties"]["event"],
                    )

        except requests.exceptions.RequestException as e:
            LOGGER.debug("Failed to retrieve alerts for %s. Reason: %s", countyCode, e)
            LOGGER.debug("API unreachable. Using stored data instead.")

            # Load alerts from data.json
            if os.path.isfile(DATA_FILE):
                with open(DATA_FILE) as f:
                    data = json.load(f)
                    stored_alerts = data.get("last_alerts", [])

                    # Filter alerts by end_time_utc
                    current_time_str = datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    )
                    LOGGER.debug("Current time: %s", current_time_str)
                    alerts = {}
                    for stored_alert in stored_alerts:
                        event = stored_alert[0]
                        alert_list = stored_alert[1]
                        alerts[event] = []
                        for alert in alert_list:
                            end_time_str = alert["end_time_utc"]
                            if parser.parse(end_time_str) >= parser.parse(
                                current_time_str
                            ):
                                LOGGER.debug(
                                    "getAlerts: Keeping %s because it does not expire until %s",
                                    event,
                                    end_time_str,
                                )
                                alerts[event].append(alert)
                            else:
                                LOGGER.debug(
                                    "getAlerts: Removing %s because it expired at %s",
                                    event,
                                    end_time_str,
                                )
            else:
                LOGGER.error("No stored data available.")
            break

    alerts = OrderedDict(
        sorted(
            alerts.items(),
            key=lambda item: (
                max([x["severity"] for x in item[1]]),  # Max Severity
                severity_mapping_words.get(item[0].split()[-1], 0),  # Words severity
            ),
            reverse=True,
        )
    )

    # If the number of alerts exceeds the maximum defined constant, we truncate the alerts.
    alerts = OrderedDict(list(alerts.items())[:MAX_ALERTS])

    return alerts


def sort_alerts(alerts):
    """
    Sorts and limits the alerts based on their severity and word severity.
    """

    # Define mapping for converting common alert terminologies to a numeric severity scale
    severity_mapping_words = {"Warning": 4, "Watch": 3, "Advisory": 2, "Statement": 1}

    # Sort the alerts first by their maximum severity, and then by their word severity
    sorted_alerts = OrderedDict(
        sorted(
            alerts.items(),
            key=lambda item: (
                max([x["severity"] for x in item[1]]),  # Max Severity for the alert
                severity_mapping_words.get(
                    item[0].split()[-1], 0
                ),  # Severity based on last word in the alert title
            ),
            reverse=True,  # Sort in descending order
        )
    )

    # Truncate the list of alerts to the maximum allowed number (MAX_ALERTS)
    limited_alerts = OrderedDict(list(sorted_alerts.items())[:MAX_ALERTS])

    return limited_alerts


def time_until(start_time_utc, current_time):
    """
    Calculate the time difference between two datetime objects and returns it
    as a formatted string.
    """

    # Calculate the time difference between the two datetime objects
    delta = start_time_utc - current_time

    # Determine the sign (used for formatting)
    sign = "-" if delta < timedelta(0) else ""

    # Decompose the time difference into days, hours, and minutes
    days, remainder = divmod(abs(delta.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    # Return the time difference as a formatted string
    return "{}{} days, {} hours, {} minutes".format(
        sign, int(days), int(hours), int(minutes)
    )


def say_alerts(alerts):
    """
    Generate and broadcast severe weather alert sounds on Asterisk.
    """

    # Load the current state
    state = load_state()

    # Extract only the alert names and associated counties
    alert_names_and_counties = {
        alert: [county["county_code"] for county in counties]
        for alert, counties in alerts.items()
    }

    # Filter out alerts that are blocked based on configuration
    filtered_alerts_and_counties = {}
    for alert, county_codes in alert_names_and_counties.items():
        if any(
            fnmatch.fnmatch(alert, blocked_event)
            for blocked_event in SAYALERT_BLOCKED_EVENTS
        ):
            LOGGER.debug("sayAlert: blocking %s as per configuration", alert)
            continue
        filtered_alerts_and_counties[alert] = county_codes

    # Check if the filtered alerts are the same as the last run
    if filtered_alerts_and_counties == state.get("last_sayalert", {}):
        LOGGER.debug(
            "sayAlert: alerts and counties are the same as the last broadcast - skipping."
        )
        return

    # Update the state with the current alerts
    state["last_sayalert"] = filtered_alerts_and_counties
    save_state(state)

    # Initialize the audio segments and paths
    alert_file = "{}/alert.wav".format(TMP_DIR)
    word_space = AudioSegment.silent(duration=600)
    sound_effect = AudioSegment.from_wav(
        os.path.join(
            SOUNDS_PATH,
            "ALERTS",
            "EFFECTS",
            config.get("Alerting", {}).get("AlertSeperator", "Woodblock.wav"),
        )
    )
    intro_effect = AudioSegment.from_wav(
        os.path.join(
            SOUNDS_PATH,
            "ALERTS",
            "EFFECTS",
            config.get("Alerting", {}).get("AlertSound", "Duncecap.wav.wav"),
        )
    )
    combined_sound = (
        intro_effect
        + word_space
        + AudioSegment.from_wav(os.path.join(SOUNDS_PATH, "ALERTS", "SWP_148.wav"))
    )

    # Build the combined sound with alerts and county names
    alert_count = 0
    for alert, counties in alerts.items():
        if alert in filtered_alerts_and_counties:
            try:
                descriptions = [county["description"] for county in counties]
                end_times = [county["end_time_utc"] for county in counties]
                index = ALERT_STRINGS.index(alert)
                audio_file = AudioSegment.from_wav(
                    os.path.join(
                        SOUNDS_PATH, "ALERTS", "SWP_{}.wav".format(ALERT_INDEXES[index])
                    )
                )
                combined_sound += sound_effect + audio_file
                LOGGER.debug(
                    "sayAlert: Added %s (SWP_%s.wav) to alert sound",
                    alert,
                    ALERT_INDEXES[index],
                )
                if config["Alerting"]["WithMultiples"]:
                    if len(set(descriptions)) > 1 or len(set(end_times)) > 1:
                        LOGGER.debug(
                            "sayAlert: Found multiple unique instances of the alert %s",
                            alert,
                        )
                        multiples_sound = AudioSegment.from_wav(
                            os.path.join(SOUNDS_PATH, "ALERTS", "SWP_149.wav")
                        )
                        combined_sound += (
                            AudioSegment.silent(duration=200) + multiples_sound
                        )
                alert_count += 1

                added_county_codes = set()
                for county in counties:
                    if counties.index(county) == 0:
                        word_space = AudioSegment.silent(duration=600)
                    else:
                        word_space = AudioSegment.silent(duration=400)
                    county_code = county["county_code"]
                    if (
                        COUNTY_WAVS
                        and county_code in COUNTY_CODES
                        and county_code not in added_county_codes
                    ):
                        index = COUNTY_CODES.index(county_code)
                        county_name_file = COUNTY_WAVS[index]
                        LOGGER.debug(
                            "sayAlert: Adding %s ID %s to %s",
                            county_code,
                            county_name_file,
                            alert,
                        )
                        try:
                            combined_sound += word_space + AudioSegment.from_wav(
                                os.path.join(SOUNDS_PATH, county_name_file)
                            )
                        except FileNotFoundError:
                            LOGGER.error(
                                "sayAlert: County audio file not found: %s",
                                os.path.join(SOUNDS_PATH, county_name_file),
                            )
                        added_county_codes.add(county_code)

                        if counties.index(county) == len(counties) - 1:
                            combined_sound += AudioSegment.silent(duration=600)

            except ValueError:
                LOGGER.error("sayAlert: Alert not found: %s", alert)
            except FileNotFoundError:
                LOGGER.error(
                    "sayAlert: Alert audio file not found: %s/ALERTS/SWP_%s.wav",
                    SOUNDS_PATH,
                    ALERT_INDEXES[index],
                )

    if alert_count == 0:
        LOGGER.debug("sayAlert: All alerts were blocked, not broadcasting any alerts.")
        return

    alert_suffix = config.get("Alerting", {}).get("SayAlertSuffix", None)
    if alert_suffix is not None:
        suffix_silence = AudioSegment.silent(duration=600)
        LOGGER.debug("sayAlert: Adding alert suffix %s", alert_suffix)
        suffix_file = os.path.join(SOUNDS_PATH, alert_suffix)
        suffix_sound = AudioSegment.from_wav(suffix_file)
        combined_sound += suffix_silence + suffix_sound

    if AUDIO_DELAY > 0:
        LOGGER.debug("sayAlert: Prepending audio with %sms of silence", AUDIO_DELAY)
        silence = AudioSegment.silent(duration=AUDIO_DELAY)
        combined_sound = silence + combined_sound

    LOGGER.debug("sayAlert: Exporting alert sound to %s", alert_file)
    converted_combined_sound = convert_audio(combined_sound)
    converted_combined_sound.export(alert_file, format="wav")

    LOGGER.debug("sayAlert: Replacing tailmessage with silence")
    silence = AudioSegment.silent(duration=100)
    converted_silence = convert_audio(silence)
    converted_silence.export(TAILMESSAGE_FILE, format="wav")

    node_numbers = config.get("Asterisk", {}).get("Nodes", [])
    for node_number in node_numbers:
        LOGGER.info("Broadcasting alert on node %s", node_number)
        command = '/usr/sbin/asterisk -rx "rpt localplay {} {}"'.format(
            node_number, os.path.splitext(os.path.abspath(alert_file))[0]
        )
        subprocess.run(command, shell=True)

    # Get the duration of the alert_file
    with contextlib.closing(wave.open(alert_file, "r")) as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = math.ceil(frames / float(rate))

    wait_time = duration + 10

    LOGGER.debug(
        "Waiting %s seconds for Asterisk to make announcement to avoid doubling alerts with tailmessage...",
        wait_time,
    )
    time.sleep(wait_time)


def say_allclear():
    """
    Generate and broadcast 'all clear' message on Asterisk.
    """

    # Load current state and clear the last_sayalert list
    state = load_state()
    state["last_sayalert"] = []
    save_state(state)

    # Define file paths for the sounds
    all_clear_sound_file = os.path.join(
        config.get("Alerting", {}).get("SoundsPath"),
        "ALERTS",
        "EFFECTS",
        config.get("Alerting", {}).get("AllClearSound"),
    )
    swp_147_file = os.path.join(SOUNDS_PATH, "ALERTS", "SWP_147.wav")

    # Load sound files into AudioSegment objects
    all_clear_sound = AudioSegment.from_wav(all_clear_sound_file)
    swp_147_sound = AudioSegment.from_wav(swp_147_file)

    # Generate silence for spacing between sounds
    silence = AudioSegment.silent(duration=600)  # 600 ms of silence

    # Combine the sound clips
    combined_sound = all_clear_sound + silence + swp_147_sound

    # Add a delay before the sound if configured
    if AUDIO_DELAY > 0:
        LOGGER.debug("sayAllClear: Prepending audio with %sms of silence", AUDIO_DELAY)
        silence = AudioSegment.silent(duration=AUDIO_DELAY)
        combined_sound = silence + combined_sound

    # Export the combined sound to a file
    all_clear_file = os.path.join(TMP_DIR, "allclear.wav")
    converted_combined_sound = convert_audio(combined_sound)
    converted_combined_sound.export(all_clear_file, format="wav")

    # Append a suffix to the sound if configured
    if config.get("Alerting", {}).get("SayAllClearSuffix", None) is not None:
        suffix_file = os.path.join(
            SOUNDS_PATH, config.get("Alerting", {}).get("SayAllClearSuffix")
        )
        LOGGER.debug("sayAllClear: Adding all clear suffix %s", suffix_file)
        suffix_sound = AudioSegment.from_wav(suffix_file)
        converted_suffix_sound = convert_audio(suffix_sound)
        converted_suffix_sound.export(all_clear_file, format="wav")

    # Play the "all clear" sound on the configured Asterisk nodes
    node_numbers = config.get("Asterisk", {}).get("Nodes", [])
    for node_number in node_numbers:
        LOGGER.info("Broadcasting all clear message on node %s", node_number)
        command = '/usr/sbin/asterisk -rx "rpt localplay {} {}"'.format(
            node_number, os.path.splitext(os.path.abspath(all_clear_file))[0]
        )
        subprocess.run(command, shell=True)


def build_tailmessage(alerts):
    """
    Build a tailmessage, which is a short message appended to the end of a
    transmission to update on the weather conditions.
    """

    # Determine whether the user has enabled county identifiers
    county_identifiers = config.get("Tailmessage", {}).get("TailmessageCounties", False)

    # Extract only the alert names from the OrderedDict keys
    alert_names = [alert for alert in alerts.keys()]

    # Get the suffix config
    tailmessage_suffix = config.get("Tailmessage", {}).get("TailmessageSuffix", None)

    # If alerts is empty
    if not alerts:
        LOGGER.debug("buildTailMessage: No alerts, creating silent tailmessage")
        silence = AudioSegment.silent(duration=100)
        converted_silence = convert_audio(silence)
        converted_silence.export(TAILMESSAGE_FILE, format="wav")
        return

    combined_sound = AudioSegment.empty()
    sound_effect = AudioSegment.from_wav(
        os.path.join(
            SOUNDS_PATH,
            "ALERTS",
            "EFFECTS",
            config.get("Alerting", {}).get("AlertSeperator", "Woodblock.wav"),
        )
    )

    added_counties = set()
    for (
        alert,
        counties,
    ) in alerts.items():  # Now we loop over both alert name and its associated counties
        if any(
            fnmatch.fnmatch(alert, blocked_event)
            for blocked_event in TAILMESSAGE_BLOCKED_EVENTS
        ):
            LOGGER.debug(
                "buildTailMessage: Alert blocked by TailmessageBlockedEvents: %s", alert
            )
            continue

        try:
            index = ALERT_STRINGS.index(alert)
            audio_file = AudioSegment.from_wav(
                os.path.join(
                    SOUNDS_PATH, "ALERTS", "SWP_{}.wav".format(ALERT_INDEXES[index])
                )
            )
            combined_sound += sound_effect + audio_file
            LOGGER.debug(
                "buildTailMessage: Added %s (SWP_%s.wav) to tailmessage",
                alert,
                ALERT_INDEXES[index],
            )

            descriptions = [county["description"] for county in counties]
            end_times = [county["end_time_utc"] for county in counties]
            if config["Alerting"]["WithMultiples"]:
                if len(set(descriptions)) > 1 or len(set(end_times)) > 1:
                    LOGGER.debug(
                        "buildTailMessage: Found multiple unique instances of the alert %s",
                        alert,
                    )
                    multiples_sound = AudioSegment.from_wav(
                        os.path.join(SOUNDS_PATH, "ALERTS", "SWP_149.wav")
                    )
                    combined_sound += (
                        AudioSegment.silent(duration=200) + multiples_sound
                    )

            # Add county names if they exist
            if county_identifiers:
                for county in counties:
                    # if its the first county, word_space is 600ms of silence. else it is 400ms
                    if counties.index(county) == 0:
                        word_space = AudioSegment.silent(duration=600)
                    else:
                        word_space = AudioSegment.silent(duration=400)
                    county_code = county["county_code"]
                    if (
                        COUNTY_WAVS
                        and county_code in COUNTY_CODES
                        and county_code not in added_counties
                    ):
                        index = COUNTY_CODES.index(county_code)
                        county_name_file = COUNTY_WAVS[index]
                        LOGGER.debug(
                            "buildTailMessage: Adding %s ID %s to %s",
                            county_code,
                            county_name_file,
                            alert,
                        )
                        try:
                            combined_sound += word_space + AudioSegment.from_wav(
                                os.path.join(SOUNDS_PATH, county_name_file)
                            )
                            # if this is the last county name, add 600ms of silence after the county name
                            if counties.index(county) == len(counties) - 1:
                                combined_sound += AudioSegment.silent(duration=600)
                            added_counties.add(county_code)
                        except FileNotFoundError:
                            LOGGER.error(
                                "buildTailMessage: Audio file not found: %s",
                                os.path.join(SOUNDS_PATH, county_name_file),
                            )

        except ValueError:
            LOGGER.error("Alert not found: %s", alert)
        except FileNotFoundError:
            LOGGER.error(
                "buildTailMessage: Audio file not found: %s/ALERTS/SWP_%s.wav",
                SOUNDS_PATH,
                ALERT_INDEXES[index],
            )

    if combined_sound.empty():
        LOGGER.debug(
            "buildTailMessage: All alerts were blocked, creating silent tailmessage"
        )
        combined_sound = AudioSegment.silent(duration=100)
    elif tailmessage_suffix is not None:
        suffix_silence = AudioSegment.silent(duration=1000)
        LOGGER.debug(
            "buildTailMessage: Adding tailmessage suffix %s", tailmessage_suffix
        )
        suffix_file = os.path.join(SOUNDS_PATH, tailmessage_suffix)
        suffix_sound = AudioSegment.from_wav(suffix_file)
        combined_sound += suffix_silence + suffix_sound
    else:
        if AUDIO_DELAY > 0:
            LOGGER.debug(
                "buildTailMessage: Prepending audio with %sms of silence", AUDIO_DELAY
            )
            silence = AudioSegment.silent(duration=AUDIO_DELAY)
            combined_sound = silence + combined_sound

    converted_combined_sound = convert_audio(combined_sound)
    LOGGER.info("Built new tailmessage")
    LOGGER.debug("buildTailMessage: Exporting tailmessage to %s", TAILMESSAGE_FILE)
    converted_combined_sound.export(TAILMESSAGE_FILE, format="wav")


def change_ct(ct):
    """
    Change the current Courtesy Tone (CT) to the one specified.
    This function first checks if the specified CT is already in use. If so, it does not make any changes.
    If the CT needs to be changed, it replaces the current CT files with the new ones and updates the state file.
    """
    state = load_state()
    current_ct = state["ct"]
    ct1 = config["CourtesyTones"]["Tones"]["CT1"]
    ct2 = config["CourtesyTones"]["Tones"]["CT2"]
    wx_ct = config["CourtesyTones"]["Tones"]["WXCT"]
    rpt_ct1 = config["CourtesyTones"]["Tones"]["RptCT1"]
    rpt_ct2 = config["CourtesyTones"]["Tones"]["RptCT2"]

    LOGGER.debug("changeCT: Tone directory: %s", TONE_DIR)
    LOGGER.debug("changeCT: Local CT: %s", ct1)
    LOGGER.debug("changeCT: Link CT: %s", ct2)
    LOGGER.debug("changeCT: WX CT: %s", wx_ct)
    LOGGER.debug("changeCT: Rpt Local CT: %s", rpt_ct1)
    LOGGER.debug("changeCT: Rpt Link CT: %s", rpt_ct2)
    LOGGER.debug("changeCT: CT argument: %s", ct)

    if not ct:
        LOGGER.error("changeCT: called with no CT specified")
        return

    current_ct = None
    if state:
        current_ct = state["ct"]

    LOGGER.debug("changeCT: Current CT - %s", current_ct)

    if ct == current_ct:
        LOGGER.debug("changeCT: Courtesy tones are already %s, no changes made.", ct)
        return False

    if ct == "NORMAL":
        LOGGER.info("Changing to NORMAL courtesy tones")
        src_file = os.path.join(TONE_DIR, ct1)
        dest_file = os.path.join(TONE_DIR, rpt_ct1)
        LOGGER.debug("changeCT: Copying %s to %s", src_file, dest_file)
        shutil.copyfile(src_file, dest_file)

        src_file = os.path.join(TONE_DIR, ct2)
        dest_file = os.path.join(TONE_DIR, rpt_ct2)
        LOGGER.debug("changeCT: Copying %s to %s", src_file, dest_file)
        shutil.copyfile(src_file, dest_file)
    else:
        LOGGER.info("Changing to %s courtesy tone", ct)
        src_file = os.path.join(TONE_DIR, wx_ct)
        dest_file = os.path.join(TONE_DIR, rpt_ct1)
        LOGGER.debug("changeCT: Copying %s to %s", src_file, dest_file)
        shutil.copyfile(src_file, dest_file)

        src_file = os.path.join(TONE_DIR, wx_ct)
        dest_file = os.path.join(TONE_DIR, rpt_ct2)
        LOGGER.debug("changeCT: Copying %s to %s", src_file, dest_file)
        shutil.copyfile(src_file, dest_file)

    state["ct"] = ct
    save_state(state)

    return True


def change_id(id):
    """
    Change the current Identifier (ID) to the one specified.
    This function first checks if the specified ID is already in use. If so, it does not make any changes.
    If the ID needs to be changed, it replaces the current ID files with the new ones and updates the state file.
    """
    state = load_state()
    current_id = state["id"]
    id_dir = config["IDChange"].get("IDDir", os.path.join(SOUNDS_PATH, "ID"))
    normal_id = config["IDChange"]["IDs"]["NormalID"]
    wx_id = config["IDChange"]["IDs"]["WXID"]
    rpt_id = config["IDChange"]["IDs"]["RptID"]

    LOGGER.debug("changeID: ID directory: %s", id_dir)
    LOGGER.debug("changeID: ID argument: %s", id)

    if not id:
        LOGGER.error("changeID: called with no ID specified")
        return

    current_id = None
    if state:
        current_id = state["id"]

    LOGGER.debug("changeID: Current ID - %s", current_id)

    if id == current_id:
        LOGGER.debug("changeID: ID is already %s, no changes made.", id)
        return False

    if id == "NORMAL":
        LOGGER.info("Changing to NORMAL ID")
        src_file = os.path.join(id_dir, normal_id)
        dest_file = os.path.join(id_dir, rpt_id)
        LOGGER.debug("changeID: Copying %s to %s", src_file, dest_file)
        shutil.copyfile(src_file, dest_file)

    else:
        LOGGER.info("Changing to %s ID", id)
        src_file = os.path.join(id_dir, wx_id)
        dest_file = os.path.join(id_dir, rpt_id)
        LOGGER.debug("changeID: Copying %s to %s", src_file, dest_file)
        shutil.copyfile(src_file, dest_file)

    state["id"] = id
    save_state(state)

    return True


def alert_script(alerts):
    """
    This function reads a list of alerts, then performs actions based
    on the alert triggers defined in the global configuration file.
    """

    # Load the saved state
    state = load_state()
    processed_alerts = set(
        state["alertscript_alerts"]
    )  # Change this to a set for easier processing
    active_alerts = set(
        state.get("active_alerts", [])
    )  # Load active alerts from state, also as a set

    # Extract only the alert names from the OrderedDict keys
    alert_names = set([alert for alert in alerts.keys()])  # This should also be a set

    # New alerts are those that are in the current alerts but were not active before
    new_alerts = alert_names - active_alerts

    # Alerts to be cleared are those that were previously active but are no longer present
    cleared_alerts = active_alerts - alert_names

    # Update the active alerts in the state
    state["active_alerts"] = list(
        alert_names
    )  # Convert back to list for JSON serialization

    # Fetch AlertScript configuration from global_config
    alertScript_config = config.get("AlertScript", {})
    LOGGER.debug("AlertScript configuration: %s", alertScript_config)

    # Fetch Mappings from AlertScript configuration
    mappings = alertScript_config.get("Mappings", [])
    if mappings is None:
        mappings = []
    LOGGER.debug("Mappings: %s", mappings)

    # Iterate over each mapping
    for mapping in mappings:
        LOGGER.debug("Processing mapping: %s", mapping)

        triggers = mapping.get("Triggers", [])
        commands = mapping.get("Commands", [])
        nodes = mapping.get("Nodes", [])
        match_type = mapping.get("Match", "ANY").upper()

        matched_alerts = []
        for alert in new_alerts:  # We only check the new alerts
            for trigger in triggers:
                if fnmatch.fnmatch(alert, trigger):
                    LOGGER.debug(
                        'Match found: Alert "%s" matches trigger "%s"', alert, trigger
                    )
                    matched_alerts.append(alert)

        # Check if alerts matched the triggers as per the match type
        if (
            match_type == "ANY"
            and matched_alerts
            or match_type == "ALL"
            and len(matched_alerts) == len(triggers)
        ):
            LOGGER.debug(
                'Alerts matched the triggers as per the match type "%s"', match_type
            )

            # Execute commands based on the Type of mapping
            for alert in matched_alerts:
                processed_alerts.add(alert)

                if mapping.get("Type") == "BASH":
                    LOGGER.debug('Mapping type is "BASH"')
                    for cmd in commands:
                        cmd = cmd.format(
                            alert_title=alert
                        )  # Replace placeholder with alert title
                        LOGGER.info("AlertScript: Executing BASH command: %s", cmd)
                        subprocess.run(cmd, shell=True)
                elif mapping.get("Type") == "DTMF":
                    LOGGER.debug('Mapping type is "DTMF"')
                    for node in nodes:
                        for cmd in commands:
                            dtmf_cmd = 'asterisk -rx "rpt fun {} {}"'.format(node, cmd)
                            LOGGER.info(
                                "AlertScript: Executing DTMF command: %s", dtmf_cmd
                            )
                            subprocess.run(dtmf_cmd, shell=True)

    # Clear alerts that are no longer active
    processed_alerts -= cleared_alerts

    # Update the state with the alerts processed in this run
    state["alertscript_alerts"] = list(
        processed_alerts
    )  # Convert back to list for JSON serialization
    save_state(state)


def send_pushover(message, title=None, priority=0):
    """
    Send a push notification via the Pushover service.
    This function constructs the payload for the request, including the user key, API token, message, title, and priority.
    The payload is then sent to the Pushover API endpoint. If the request fails, an error message is logged.
    """
    pushover_config = config["Pushover"]
    user_key = pushover_config.get("UserKey")
    token = pushover_config.get("APIToken")

    # Remove newline from the end of the message
    message = message.rstrip("\n")

    url = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": token,
        "user": user_key,
        "message": message,
        "title": title,
        "priority": priority,
    }

    response = requests.post(url, data=payload)

    if response.status_code != 200:
        LOGGER.error("Failed to send Pushover notification: %s", response.text)


def convert_audio(audio):
    """
    Convert audio file to 8000Hz mono for compatibility with Asterisk.
    """
    return audio.set_frame_rate(8000).set_channels(1)


def change_ct_id_helper(
    alerts,
    specified_alerts,
    auto_change_enabled,
    alert_type,
    pushover_debug,
    pushover_message,
):
    """
    Check whether the CT or ID needs to be changed, performs the change, and logs the process.
    """
    if auto_change_enabled:
        LOGGER.debug(
            "%s auto change is enabled, alerts that require a %s change: %s",
            alert_type,
            alert_type,
            specified_alerts,
        )

        # Extract only the alert names from the OrderedDict keys
        alert_names = [alert for alert in alerts.keys()]

        # Check if any alert matches specified_alerts
        # Here we replace set intersection with a list comprehension
        intersecting_alerts = [
            alert for alert in alert_names if alert in specified_alerts
        ]

        if intersecting_alerts:
            for alert in intersecting_alerts:
                LOGGER.debug("Alert %s requires a %s change", alert, alert_type)
                if (
                    change_ct("WX") if alert_type == "CT" else change_id("WX")
                ):  # If the CT/ID was actually changed
                    if pushover_debug:
                        pushover_message += "Changed {} to WX\n".format(alert_type)
                break
        else:  # No alerts require a CT/ID change, revert back to normal
            LOGGER.debug(
                "No alerts require a %s change, reverting to normal.", alert_type
            )
            if (
                change_ct("NORMAL") if alert_type == "CT" else change_id("NORMAL")
            ):  # If the CT/ID was actually changed
                if pushover_debug:
                    pushover_message += "Changed {} to NORMAL\n".format(alert_type)
    else:
        LOGGER.debug("%s auto change is not enabled", alert_type)


def supermon_back_compat(alerts):
    """
    Write alerts to a file for backward compatibility with supermon.
    """

    # Ensure the target directory exists
    os.makedirs("/tmp/AUTOSKY", exist_ok=True)

    # Get alert titles (without severity levels)
    alert_titles = list(alerts.keys())

    # Write alert titles to a file, with each title on a new line
    with open("/tmp/AUTOSKY/warnings.txt", "w") as file:
        file.write("<br>".join(alert_titles))


def detect_county_changes(old_alerts, new_alerts):
    """
    Detect if any counties have been added to or removed from an alert and return the alerts
    with added or removed counties.
    """
    alerts_with_changed_counties = OrderedDict()
    changes_detected = {}

    for alert_name, alert_info in new_alerts.items():
        if alert_name not in old_alerts:
            continue
        old_alert_info = old_alerts.get(alert_name, [])
        old_county_codes = {info["county_code"] for info in old_alert_info}
        new_county_codes = {info["county_code"] for info in alert_info}

        added_counties = new_county_codes - old_county_codes
        removed_counties = old_county_codes - new_county_codes

        added_counties = {
            code.replace("{", "").replace("}", "").replace('"', "")
            for code in added_counties
        }
        removed_counties = {
            code.replace("{", "").replace("}", "").replace('"', "")
            for code in removed_counties
        }

        if added_counties or removed_counties:
            alerts_with_changed_counties[alert_name] = new_alerts[alert_name]
            changes_detected[alert_name] = {
                "old": old_county_codes,
                "added": added_counties,
                "removed": removed_counties,
            }

    return alerts_with_changed_counties, changes_detected


def load_county_names(md_file):
    """
    Load county names from separate markdown tables so that county codes can be replaced with county names.
    """
    with open(md_file, "r") as f:
        lines = f.readlines()

    county_data = {}
    in_table = False
    for line in lines:
        if line.startswith("| County |"):
            in_table = True
            continue  # Skip the header
        elif not in_table or line.strip() == "" or line.startswith("##"):
            continue
        else:
            name, code = [s.strip() for s in line.split("|")[1:-1]]
            county_data[code] = name

    return county_data


def replace_with_county_name(county_code, county_data):
    """
    Translate county code to county name.
    """
    return county_data.get(county_code, county_code)


def main():
    """
    The main function that orchestrates the entire process of fetching and
    processing severe weather alerts, then integrating these alerts into
    an Asterisk/app_rpt based radio repeater system.
    """
    # Fetch configurations
    say_alert_enabled = config["Alerting"].get("SayAlert", False)
    say_alert_all = config["Alerting"].get("SayAlertAll", False)
    say_all_clear_enabled = config["Alerting"].get("SayAllClear", False)
    alertscript_enabled = config["AlertScript"].get("Enable", False)
    ct_alerts = config["CourtesyTones"].get("CTAlerts", [])
    enable_ct_auto_change = config["CourtesyTones"].get("Enable", False)
    id_alerts = config["IDChange"].get("IDAlerts", [])
    enable_id_auto_change = config["IDChange"].get("Enable", False)
    pushover_enabled = config["Pushover"].get("Enable", False)
    pushover_debug = config["Pushover"].get("Debug", False)
    supermon_compat_enabled = config["DEV"].get("SupermonCompat", True)
    say_alerts_changed = config["Alerting"].get("SayAlertsChanged", True)

    # If data file does not exist, assume this is the first run and initialize CT/ID/Tailmessage files if enabled
    if not os.path.isfile(DATA_FILE):
        LOGGER.info("Data file does not exist, assuming first run.")
        if enable_ct_auto_change:
            LOGGER.info("Initializing CT files")
            change_ct("NORMAL")
        if enable_id_auto_change:
            LOGGER.info("Initializing ID files")
            change_id("NORMAL")
        if ENABLE_TAILMESSAGE:
            LOGGER.info("Initializing Tailmessage file")
            empty_alerts = OrderedDict()
            build_tailmessage(empty_alerts)

    # Load previous alert data to compare changes
    state = load_state()
    last_alerts = state["last_alerts"]

    # Fetch new alert data
    alerts = get_alerts(COUNTY_CODES)

    # Load county names from YAML file so that county codes can be replaced with county names in messages
    county_data = load_county_names(COUNTY_CODES_PATH)

    # Placeholder for constructing a pushover message
    pushover_message = ""

    # Determine which alerts have been added since the last check
    added_alerts = [alert for alert in alerts if alert not in last_alerts]
    for alert in added_alerts:
        counties_str = (
            "["
            + ", ".join(
                [
                    replace_with_county_name(x["county_code"], county_data)
                    for x in alerts[alert]
                ]
            )
            + "]"
        )
        LOGGER.info("Added: {} for {}".format(alert, counties_str))
        pushover_message += "Added: {} for {}\n".format(alert, counties_str)

    # Determine which alerts have been removed since the last check
    removed_alerts = [alert for alert in last_alerts if alert not in alerts]
    for alert in removed_alerts:
        counties_str = (
            "["
            + ", ".join(
                [
                    replace_with_county_name(x["county_code"], county_data)
                    for x in last_alerts[alert]
                ]
            )
            + "]"
        )
        LOGGER.info("Removed: {} for {}".format(alert, counties_str))
        pushover_message += "Removed: {} for {}\n".format(alert, counties_str)

    # Placeholder for storing alerts with changed county codes
    changed_alerts = {}

    # If the list of alerts is not empty
    if alerts:
        # Compare old and new alerts to detect changes in affected counties
        changed_alerts, changes_details = detect_county_changes(last_alerts, alerts)

        for alert, details in changes_details.items():
            old_counties_str = (
                "["
                + ", ".join(
                    [
                        replace_with_county_name(county, county_data)
                        for county in details["old"]
                    ]
                )
                + "]"
            )

            added_msg = ""
            if details["added"]:
                added_counties_str = (
                    "["
                    + ", ".join(
                        [
                            replace_with_county_name(county, county_data)
                            for county in details["added"]
                        ]
                    )
                    + "]"
                )
                added_msg = "is now also affecting {}".format(added_counties_str)

            removed_msg = ""
            if details["removed"]:
                removed_counties_str = (
                    "["
                    + ", ".join(
                        [
                            replace_with_county_name(county, county_data)
                            for county in details["removed"]
                        ]
                    )
                    + "]"
                )
                removed_msg = "is no longer affecting {}".format(removed_counties_str)

            # Combining the log messages
            combined_msg_parts = ["Changed: {} for {}".format(alert, old_counties_str)]
            if added_msg:
                combined_msg_parts.append(added_msg)
            if removed_msg:
                if (
                    added_msg
                ):  # if there's an 'added' message, then use 'and' to combine with 'removed' message
                    combined_msg_parts.append("and")
                combined_msg_parts.append(removed_msg)

            log_msg = " ".join(combined_msg_parts)
            LOGGER.info(log_msg)
            pushover_message += log_msg + "\n"

    # Process changes in alerts
    if added_alerts or removed_alerts or changed_alerts:
        # Save the data
        state["last_alerts"] = alerts
        save_state(state)

        # Send "all clear" messages if alerts have changed but are empty
        if not alerts:
            LOGGER.info("Alerts cleared")
            # Call say_allclear if enabled
            if say_all_clear_enabled:
                say_allclear()
            # Add "Alerts Cleared" to pushover message
            pushover_message += "Alerts Cleared\n"

        # If alerts have been added, removed
        if added_alerts or removed_alerts:
            # Push alert titles to Supermon if enabled
            if supermon_compat_enabled:
                supermon_back_compat(alerts)

            # Change CT/ID if necessary and enabled
            change_ct_id_helper(
                alerts,
                ct_alerts,
                enable_ct_auto_change,
                "CT",
                pushover_debug,
                pushover_message,
            )
            change_ct_id_helper(
                alerts,
                id_alerts,
                enable_id_auto_change,
                "ID",
                pushover_debug,
                pushover_message,
            )

            # Call alert_script if enabled
            if alertscript_enabled:
                alert_script(alerts)

            # Say alerts if enabled
            if say_alert_enabled:
                # If say_alert_all is enabled, say all currently active alerts
                if say_alert_all:
                    alerts_to_say = alerts

                # Otherwise, only say newly added alerts
                else:
                    alerts_to_say = {alert: alerts[alert] for alert in added_alerts}
                    # If County IDs have been set up and there is more than one county code, then also say alerts with county changes
                    # Only if enabled
                    if (
                        changed_alerts
                        and say_alerts_changed
                        and COUNTY_WAVS
                        and len(COUNTY_CODES) > 1
                    ):
                        alerts_to_say.update(changed_alerts)

                # Sort alerts based on severity
                alerts_to_say = sort_alerts(alerts_to_say)

                # Say the alerts
                say_alerts(alerts_to_say)

        # If alerts have changed, but none added or removed
        elif changed_alerts:
            # Say changed alerts only if enabled, County IDs have been set up, and there is more than one county code
            if say_alerts_changed and COUNTY_WAVS and len(COUNTY_CODES) > 1:
                # Sort alerts based on severity
                changed_alerts = sort_alerts(changed_alerts)
                # Say the alerts
                say_alerts(changed_alerts)

        # Alerts have changed, update tailmessage if enabled
        if ENABLE_TAILMESSAGE:
            build_tailmessage(alerts)
            if pushover_debug:
                pushover_message += (
                    "WX tailmessage removed\n"
                    if not alerts
                    else "Built WX tailmessage\n"
                )

        # Send pushover message if enabled
        if pushover_enabled:
            pushover_message = pushover_message.rstrip("\n")
            LOGGER.debug("Sending Pushover message: %s", pushover_message)
            send_pushover(pushover_message, title="SkywarnPlus")

    # If no changes detected in alerts
    else:
        # If this is being run interactively, inform the user that nothing has changed
        if sys.stdin.isatty():
            # Log list of current alerts, unless there aren't any, then current_alerts = "None"
            if len(alerts) == 0:
                current_alerts = "None"
            else:
                alert_details = []
                for alert, counties in alerts.items():
                    counties_str = ", ".join(
                        [
                            replace_with_county_name(county["county_code"], county_data)
                            for county in counties
                        ]
                    )
                    alert_details.append("{} ({})".format(alert, counties_str))
                current_alerts = "; ".join(alert_details)

            LOGGER.info("No change in alerts.")
            LOGGER.info("Current alerts: %s.", current_alerts)

        # If this is being run non-interactively, only log if debug is enabled
        else:
            LOGGER.debug("No change in alerts.")


if __name__ == "__main__":
    main()
