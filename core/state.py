import threading

accounts = []
servers = []
custom_scripts = []
settings = {
    'auto_join_enabled': True,
    'rejoin_delay': 3,
    'max_retries': 5,
    'monitor_interval': 2,
    'rejoin_interval': 2400,
    'thread_threshold': 120,
    'theme': 'dark',
    'adb_path': '',
    'mumu_serials': [],
    'webhook_url': '',
    'webhook_enabled': False,
    'delta_auto_key': False,
    'auto_verify_interval': 0,
    'auto_push_script': True,
    'dashboard_url': 'http://localhost:5000',
    'discord_client_id': '',
    'discord_client_secret': '',
    'discord_guild_id': '',
}

schedules = []
schedule_history = []

activity_log = []
acc_logs = {}
inventory_data = {}
harvested_fruits_data = {}
monitor_running = False
monitor_thread = None
user_shutdown_instances = set()
_join_threads = set()
_join_threads_lock = threading.Lock()
_join_timestamps = {}
_serial_locks = {}
_adb_global_lock = threading.Lock()
_data_lock = threading.Lock()
monitor_state = {}
