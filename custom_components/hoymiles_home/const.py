"""Constants for Hoymiles S-Miles Home."""

from datetime import timedelta

DOMAIN = "hoymiles_home"
PLATFORMS = ["sensor", "binary_sensor", "number", "select"]

CONF_STATION_ID = "station_id"

AUTH_BASE_URL = "https://euapi.hoymiles.com"
DATA_BASE_URL = "https://neapi.hoymiles.com"
USER_AGENT = "sma/ad/2.9.0/159/0"

LIVE_MIN_INTERVAL = timedelta(seconds=3)
MODULE_INTERVAL = timedelta(minutes=5)
STATION_INTERVAL = timedelta(minutes=1)
BATTERY_SETTINGS_INTERVAL = timedelta(minutes=30)
TOKEN_LIFETIME = timedelta(minutes=90)
DEFAULT_PORT_COUNT = 4
MAX_ENERGY_SAMPLE_GAP = timedelta(minutes=1)
ENERGY_SAVE_INTERVAL = timedelta(minutes=1)
STORAGE_VERSION = 1
BATTERY_ENERGY_CALCULATION_VERSION = 2
BATTERY_SETTINGS_ACTION = 1013
BATTERY_SETTINGS_MAX_POLLS = 10
BATTERY_SETTINGS_POLL_INTERVAL = 1
