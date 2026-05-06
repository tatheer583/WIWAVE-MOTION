import time
import csv
import os
from datetime import datetime
from wifi_reader import get_wifi_signal

# --- CONFIGURATION ---
LOG_INTERVAL_SECONDS = 0.5  # How often to check the signal (500ms)
LOG_DIRECTORY = "logs"
LOG_FILENAME = "signal_log.csv"
# ---------------------

def setup_logger():
    """Ensures the logs directory exists and creates the CSV header if needed."""
    if not os.path.exists(LOG_DIRECTORY):
        os.makedirs(LOG_DIRECTORY)
        print(f"Created directory: {LOG_DIRECTORY}")

    filepath = os.path.join(LOG_DIRECTORY, LOG_FILENAME)
    
    # If file doesn't exist, create it and write the header
    if not os.path.exists(filepath):
        with open(filepath, mode='w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Signal_Percentage"])
            print(f"Created log file: {filepath}")

def log_data():
    """
    Main loop that reads the signal and writes it to the CSV.
    
    To stop this script in VS Code:
    Press 'Ctrl + C' in the terminal.
    """
    setup_logger()
    filepath = os.path.join(LOG_DIRECTORY, LOG_FILENAME)
    
    print(f"Starting data logger (Interval: {LOG_INTERVAL_SECONDS}s)...")
    print("Press Ctrl+C to stop.")
    
    try:
        # We use 'a' for 'append' mode so we don't erase previous data
        with open(filepath, mode='a', newline='') as f:
            writer = csv.writer(f)
            
            while True:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                signal = get_wifi_signal()
                
                if signal is not None:
                    writer.writerow([timestamp, signal])
                    # Flush ensures data is written to disk immediately
                    f.flush() 
                    print(f"[{timestamp}] Signal: {signal}%")
                else:
                    print(f"[{timestamp}] Signal: Lost connection...")
                
                # Wait for the next interval
                time.sleep(LOG_INTERVAL_SECONDS)
                
    except KeyboardInterrupt:
        print("\nLogging stopped by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    log_data()
