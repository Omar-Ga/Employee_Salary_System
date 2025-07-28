import ntplib
import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta

class AccessControl:
    def __init__(self):
        self.ntp_servers = ['pool.ntp.org', 'time.google.com']
        self.control_file = Path(os.path.expanduser('~')) / 'Documents' / '.system_cache.dat'
        self.days_limit = 45
        self.max_retries = 3
        print(f"Access Control initialized. Looking for file: {self.control_file}")

    def _get_ntp_time(self):
        """Try to get time from NTP servers"""
        print("Attempting to get NTP time...")
        client = ntplib.NTPClient()
        for server in self.ntp_servers:
            try:
                print(f"Trying NTP server: {server}")
                response = client.request(server)
                ntp_time = datetime.fromtimestamp(response.tx_time)
                print(f"Got NTP time: {ntp_time}")
                return ntp_time
            except:
                print(f"Failed to connect to {server}")
                continue
        print("Failed to get NTP time from all servers")
        return None

    def _create_control_file(self, current_time):
        """Create the hidden control file with current time"""
        try:
            data = {'timestamp': current_time.timestamp()}
            print(f"Creating control file with timestamp: {current_time}")
            with open(self.control_file, 'w') as f:
                json.dump(data, f)
            # Hide the file on Windows
            if os.name == 'nt':
                os.system(f'attrib +h "{self.control_file}"')
                print("File hidden successfully")
            return True
        except:
            print("Failed to create control file")
            return False

    def _read_control_file(self):
        """Read the timestamp from control file"""
        try:
            print("Reading control file...")
            with open(self.control_file, 'r') as f:
                data = json.load(f)
                stored_time = datetime.fromtimestamp(data['timestamp'])
                print(f"Found stored timestamp: {stored_time}")
                return stored_time
        except:
            print("Failed to read control file")
            return None

    def check_access(self):
        """Main access check function"""
        retry_count = 0
        while retry_count < self.max_retries:
            ntp_time = self._get_ntp_time()
            if not ntp_time:
                retry_count += 1
                print(f"No internet connection. Attempt {retry_count} of {self.max_retries}")
                if retry_count == self.max_retries:
                    print("Max retries reached. Exiting...")
                    return False
                time.sleep(1)
                continue

            # If control file doesn't exist, create it
            if not self.control_file.exists():
                print("No control file found. Creating new one...")
                if self._create_control_file(ntp_time):
                    print("Access granted - new installation")
                    return True
                continue

            # Read existing timestamp
            stored_time = self._read_control_file()
            if not stored_time:
                print("Invalid control file. Deleting...")
                self.control_file.unlink(missing_ok=True)
                continue

            # Check if time limit has passed (now 45 days)
            time_diff = ntp_time - stored_time
            print(f"Time difference: {time_diff}")
            if time_diff > timedelta(days=self.days_limit):
                print("Access denied - time limit exceeded")
                return False

            print("Access granted - within time limit")
            return True 