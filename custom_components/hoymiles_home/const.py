"""Constants for Hoymiles S-Miles Home."""

from datetime import timedelta

DOMAIN = "hoymiles_home"
PLATFORMS = ["sensor", "binary_sensor", "number", "select"]

CONF_STATION_ID = "station_id"

AUTH_BASE_URL = "https://euapi.hoymiles.com"
DATA_BASE_URL = "https://neapi.hoymiles.com"
USER_AGENT = "sma/ad/2.12.1/159/0"

BATTERY_USER_SETTINGS_URLS = (
    f"{DATA_BASE_URL}/pvmc/api/0/station/setting/get_user_setting_c",
    f"{DATA_BASE_URL}/pvm/api/0/station/setting/get_user_setting",
)
BATTERY_CONFIG_URL = f"{DATA_BASE_URL}/pvm/api/0/station/setting/battery_config"
STATION_SETTING_READ_URL = f"{DATA_BASE_URL}/pvmc/api/0/station_ctl/read_c"
STATION_SETTING_WRITE_URL = f"{DATA_BASE_URL}/pvmc/api/0/station_ctl/write_c"
STATION_SETTING_STATUS_URL = (
    f"{DATA_BASE_URL}/pvmc/api/0/station_ctl/setting_status_c"
)

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
WORK_MODE_SETTINGS_ACTION = 83
BATTERY_SETTINGS_MAX_POLLS = 10
BATTERY_SETTINGS_POLL_INTERVAL = 1
