import os
import sys
import logging

# Configure basic logging for the lock module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ApplicationLock:
    """
    Manages a lock file to ensure only one instance of the application runs at a time.
    The lock file is created in the same directory as the script that imports this module.
    """
    def __init__(self, lock_filename="employee_manager.lock"):
        # Determine the directory of the main script
        # sys.argv[0] is the path to the script being run
        script_path = os.path.abspath(sys.argv[0])
        script_dir = os.path.dirname(script_path)
        self.lock_file_path = os.path.join(script_dir, lock_filename)
        self.lock_file_handle = None
        logging.info(f"Lock file path set to: {self.lock_file_path}")

    def acquire(self):
        """
        Attempts to acquire the lock by creating the lock file exclusively.

        Returns:
            bool: True if the lock was acquired successfully, False otherwise.
        """
        try:
            # Attempt to open the file in exclusive creation mode ('x').
            # This is atomic: it fails if the file already exists.
            # 'w' ensures it's opened for writing, keeping it locked.
            self.lock_file_handle = open(self.lock_file_path, 'x')
            logging.info(f"Lock acquired successfully: {self.lock_file_path}")
            # Optionally write the process ID to the lock file for debugging
            self.lock_file_handle.write(f"Locked by PID: {os.getpid()}")
            self.lock_file_handle.flush() # Ensure content is written
            return True
        except FileExistsError:
            logging.warning(f"Lock file already exists: {self.lock_file_path}. Another instance may be running.")
            return False
        except IOError as e:
            logging.error(f"Failed to acquire lock due to IOError: {e}")
            return False
        except Exception as e:
            logging.error(f"An unexpected error occurred during lock acquisition: {e}")
            return False

    def release(self):
        """
        Releases the lock by closing the file handle and deleting the lock file.
        """
        try:
            if self.lock_file_handle:
                self.lock_file_handle.close()
                self.lock_file_handle = None
                logging.info("Lock file handle closed.")
            else:
                 logging.info("Lock file handle was already closed or never opened.")

            # Attempt to delete the lock file
            if os.path.exists(self.lock_file_path):
                os.remove(self.lock_file_path)
                logging.info(f"Lock file deleted: {self.lock_file_path}")
            else:
                logging.info(f"Lock file did not exist, no need to delete: {self.lock_file_path}")

        except IOError as e:
            logging.error(f"Failed to release lock due to IOError: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during lock release: {e}")

    def __del__(self):
        """
        Ensure the lock is released when the object is garbage collected,
        although explicit release in `on_closing` is preferred.
        """
        self.release()