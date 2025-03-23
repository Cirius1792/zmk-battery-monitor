import hid
import time
import threading
import logging
import json
import os
import sys
import platform
from datetime import datetime
from abc import ABC, abstractmethod

# Configuration
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".zmk_battery_monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "battery_log.csv")

# Default configuration
DEFAULT_CONFIG = {
    "update_interval": 300,  # 5 minutes
    "low_battery_threshold": 20,
    "critical_battery_threshold": 10,
    "vendor_id": None,  # Will be auto-detected
    "product_id": None,  # Will be auto-detected
    "device_name": None,  # Will be auto-detected
    "report_id": None,  # Will be auto-detected
    "left_battery_index": None,  # Will be auto-detected
    "right_battery_index": None  # Will be auto-detected
}

# Ensure config directory exists
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(CONFIG_DIR, "debug.log"))
    ]
)
logger = logging.getLogger("zmk_battery_monitor")

# Abstract interfaces for OS-specific functionality
class NotificationSystem(ABC):
    @abstractmethod
    def show_notification(self, title, message, is_warning=False):
        """Show a system notification"""
        pass
    
    @abstractmethod
    def show_message_dialog(self, message, title):
        """Show a message dialog box"""
        pass

class SystemTrayInterface(ABC):
    @abstractmethod
    def create_tray_icon(self, icon_image, title, menu_items) -> bool:
        """Create a system tray icon
        returns True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def update_icon(self, icon_image):
        """Update the tray icon image"""
        pass
    
    @abstractmethod
    def update_title(self, title):
        """Update the tray icon tooltip"""
        pass
    
    @abstractmethod
    def run_tray(self):
        """Run the tray icon event loop"""
        pass
    
    @abstractmethod
    def stop_tray(self):
        """Stop the tray icon"""
        pass

class SystemUtility(ABC):
    @abstractmethod
    def open_file(self, filepath):
        """Open a file with the default application"""
        pass
    
    @abstractmethod
    def get_platform_name(self):
        """Get the platform name"""
        pass

# Windows implementations
class WindowsNotificationSystem(NotificationSystem):
    def __init__(self):
        # Lazy import Windows-specific modules
        try:
            import win32api
            import win32con
            import win32gui
            self.win32api = win32api
            self.win32con = win32con
            self.win32gui = win32gui
            self.available = True
        except ImportError:
            self.available = False
            logger.warning("Windows notification modules not available")
    
    def show_notification(self, title, message, is_warning=False):
        if not self.available:
            logger.warning(f"Unable to show notification: {title} - {message}")
            return
            
        flags = self.win32con.NIIF_WARNING if is_warning else self.win32con.NIIF_INFO
        nid = (self.win32gui.GetForegroundWindow(), 0, 
               self.win32gui.NIF_INFO, self.win32con.WM_USER + 20, 0, 
               message, title, 10, flags)
        try:
            self.win32gui.Shell_NotifyIcon(self.win32gui.NIM_MODIFY, nid)
        except:
            # If modify fails, try add
            try:
                self.win32gui.Shell_NotifyIcon(self.win32gui.NIM_ADD, nid)
            except Exception as e:
                logger.error(f"Notification error: {e}")
    
    def show_message_dialog(self, message, title):
        if not self.available:
            logger.warning(f"Unable to show dialog: {title} - {message}")
            print(f"\n{title}\n{'-' * len(title)}\n{message}")
            return
            
        self.win32api.MessageBox(0, message, title, 0)

class WindowsSystemTrayIcon(SystemTrayInterface):
    def __init__(self):
        # Lazy import Windows-specific modules
        try:
            import pystray
            from PIL import Image
            self.pystray = pystray
            self.Image = Image
            self.available = True
            self.icon = None
        except ImportError:
            self.available = False
            logger.warning("Windows system tray modules not available")
    
    def create_tray_icon(self, icon_image, title, menu_items):
        if not self.available:
            logger.warning("Unable to create system tray icon")
            return False
            
        # Convert menu_items to pystray format
        pystray_menu = []
        for item in menu_items:
            name, callback, default = item
            pystray_menu.append(self.pystray.MenuItem(name, callback, default=default))
            
        self.icon = self.pystray.Icon("zmk_battery_monitor", icon_image, title, tuple(pystray_menu))
        return True
    
    def update_icon(self, icon_image):
        if self.available and self.icon:
            self.icon.icon = icon_image
    
    def update_title(self, title):
        if self.available and self.icon:
            self.icon.title = title
    
    def run_tray(self):
        if self.available and self.icon:
            self.icon.run()
    
    def stop_tray(self):
        if self.available and self.icon:
            self.icon.stop()

class WindowsSystemUtility(SystemUtility):
    def open_file(self, filepath):
        if os.path.exists(filepath):
            os.startfile(filepath)
        else:
            logger.error(f"File not found: {filepath}")
    
    def get_platform_name(self):
        return "Windows"

# Linux implementations
class LinuxNotificationSystem(NotificationSystem):
    def __init__(self):
        # Check if we can use notify-send
        try:
            import subprocess
            result = subprocess.run(['which', 'notify-send'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            self.available = result.returncode == 0
            self.subprocess = subprocess
        except:
            self.available = False
            logger.warning("Linux notification utility not available")
    
    def show_notification(self, title, message, is_warning=False):
        if not self.available:
            logger.warning(f"Unable to show notification: {title} - {message}")
            return
            
        urgency = "critical" if is_warning else "normal"
        try:
            self.subprocess.run(['notify-send', 
                                '-u', urgency, 
                                title, message])
        except Exception as e:
            logger.error(f"Notification error: {e}")
    
    def show_message_dialog(self, message, title):
        # Try to use zenity if available
        try:
            import subprocess
            result = subprocess.run(['which', 'zenity'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            if result.returncode == 0:
                subprocess.run(['zenity', '--info', 
                               '--title', title, 
                               '--text', message])
                return
        except:
            pass
            
        # Fallback to console
        print(f"\n{title}\n{'-' * len(title)}\n{message}")

class LinuxSystemTrayIcon(SystemTrayInterface):
    def __init__(self):
        # Check if we can use pystray on Linux
        try:
            import pystray
            from PIL import Image
            self.pystray = pystray
            self.Image = Image
            self.available = True
            self.icon = None
        except ImportError:
            self.available = False
            logger.warning("Linux system tray modules not available")
    
    # Methods identical to Windows implementation due to pystray cross-platform compatibility
    def create_tray_icon(self, icon_image, title, menu_items):
        if not self.available:
            logger.warning("Unable to create system tray icon")
            return False
            
        # Convert menu_items to pystray format
        pystray_menu = []
        for item in menu_items:
            name, callback, default = item
            pystray_menu.append(self.pystray.MenuItem(name, callback, default=default))
            
        self.icon = self.pystray.Icon("zmk_battery_monitor", icon_image, title, tuple(pystray_menu))
        return True
    
    def update_icon(self, icon_image):
        if self.available and self.icon:
            self.icon.icon = icon_image
    
    def update_title(self, title):
        if self.available and self.icon:
            self.icon.title = title
    
    def run_tray(self):
        if self.available and self.icon:
            self.icon.run()
    
    def stop_tray(self):
        if self.available and self.icon:
            self.icon.stop()

class LinuxSystemUtility(SystemUtility):
    def open_file(self, filepath):
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return
            
        try:
            import subprocess
            subprocess.run(['xdg-open', filepath])
        except Exception as e:
            logger.error(f"Failed to open file: {e}")
    
    def get_platform_name(self):
        return "Linux"

# Factory to create appropriate OS implementation
class PlatformFactory:
    @staticmethod
    def get_notification_system():
        system = platform.system()
        if system == "Windows":
            return WindowsNotificationSystem()
        elif system == "Linux":
            return LinuxNotificationSystem()
        else:
            logger.warning(f"Unsupported platform for notifications: {system}")
            # Return a dummy implementation
            class DummyNotification(NotificationSystem):
                def show_notification(self, title, message, is_warning=False):
                    print(f"NOTIFICATION: {title} - {message}")
                def show_message_dialog(self, message, title):
                    print(f"\n{title}\n{'-'*len(title)}\n{message}")
            return DummyNotification()
    
    @staticmethod
    def get_system_tray():
        system = platform.system()
        if system == "Windows":
            return WindowsSystemTrayIcon()
        elif system == "Linux":
            return LinuxSystemTrayIcon()
        else:
            logger.warning(f"Unsupported platform for system tray: {system}")
            # Return a dummy implementation
            class DummyTray(SystemTrayInterface):
                def create_tray_icon(self, icon_image, title, menu_items): return False
                def update_icon(self, icon_image): pass
                def update_title(self, title): pass
                def run_tray(self): pass
                def stop_tray(self): pass
            return DummyTray()
    
    @staticmethod
    def get_system_utility():
        system = platform.system()
        if system == "Windows":
            return WindowsSystemUtility()
        elif system == "Linux":
            return LinuxSystemUtility()
        else:
            logger.warning(f"Unsupported platform for system utility: {system}")
            # Return a dummy implementation
            class DummyUtility(SystemUtility):
                def open_file(self, filepath): 
                    print(f"Would open file: {filepath}")
                def get_platform_name(self): 
                    return platform.system()
            return DummyUtility()

# UI manager to abstract OS-specific functionality
class UIManager:
    def __init__(self):
        self.notification_system = PlatformFactory.get_notification_system()
        self.system_tray = PlatformFactory.get_system_tray()
        self.system_utility = PlatformFactory.get_system_utility()
        
        # Check for PIL availability for icons
        try:
            from PIL import Image, ImageDraw
            self.Image = Image
            self.ImageDraw = ImageDraw
            self.gui_available = True
        except ImportError:
            self.gui_available = False
            logger.warning("PIL not available, GUI features limited")
    
    def create_icon_image(self, width, height):
        """Create a blank icon image"""
        if not self.gui_available:
            return None
        return self.Image.new('RGBA', (width, height), color=(0, 0, 0, 0))
    
    def get_image_draw(self, image):
        """Get a drawing context for an image"""
        if not self.gui_available or image is None:
            return None
        return self.ImageDraw.Draw(image)

class BatteryMonitor:
    def __init__(self):
        self.config = self.load_config()
        self.battery_levels = {"left": None, "right": None, "timestamp": None}
        self.running = False
        self.monitor_thread = None
        
        # Initialize UI manager
        self.ui = UIManager()
        self.icon = None
        
        logger.info(f"Initialized ZMK Battery Monitor on {self.ui.system_utility.get_platform_name()}")

    def load_config(self):
        """Load configuration from file or create default"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    for key, value in DEFAULT_CONFIG.items():
                        if key not in config:
                            config[key] = value
                    return config
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def find_keyboard(self):
        """Find ZMK keyboard and update config if needed"""
        devices = hid.enumerate()
        
        # If device IDs are already configured, verify they still exist
        if self.config["vendor_id"] and self.config["product_id"]:
            for device in devices:
                if (device["vendor_id"] == self.config["vendor_id"] and 
                    device["product_id"] == self.config["product_id"]):
                    logger.info(f"Using configured device: {self.config['device_name']}")
                    return True
            
            logger.warning("Configured device not found, rescanning...")
        
        # Look for potential ZMK devices
        zmk_candidates = []
        for device in devices:
            # Convert to strings for easier reading
            manufacturer = device.get('manufacturer_string', '')
            product = device.get('product_string', '')
            
            # Filter for potential ZMK devices
            if ('keyboard' in product.lower() or 
                'zmk' in product.lower() or 
                'zmk' in manufacturer.lower()):
                
                zmk_candidates.append({
                    "vendor_id": device["vendor_id"],
                    "product_id": device["product_id"],
                    "path": device["path"].decode('utf-8') if isinstance(device["path"], bytes) else device["path"],
                    "manufacturer": manufacturer,
                    "product": product
                })
        
        if not zmk_candidates:
            logger.error("No potential ZMK devices found.")
            return False
            
        # For now, just use the first candidate
        device = zmk_candidates[0]
        self.config["vendor_id"] = device["vendor_id"]
        self.config["product_id"] = device["product_id"]
        self.config["device_name"] = f"{device['manufacturer']} {device['product']}"
        self.save_config()
        
        logger.info(f"Selected device: {self.config['device_name']}")
        return True

    def read_battery_levels(self):
        """
        Read battery levels from ZMK keyboard
        
        ZMK keyboards use HID feature reports to communicate battery levels,
        but report IDs and data structures vary across different keyboards.
        """
        left_battery = None
        right_battery = None
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            # Open the device
            device = hid.device()
            device.open(self.config["vendor_id"], self.config["product_id"])
            
            # First, try to find the correct report ID by scanning common IDs
            report_ids = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
            valid_reports = {}
            
            for report_id in report_ids:
                try:
                    report = device.get_feature_report(report_id, 64)
                    logger.debug(f"Report ID 0x{report_id:02x}: {[hex(b) for b in report]}")
                    
                    # Store reports that have data (longer than just the report ID itself)
                    if len(report) > 2:
                        valid_reports[report_id] = report
                except Exception as e:
                    logger.debug(f"Report ID 0x{report_id:02x} not supported: {e}")
            
            # For ZMK keyboards, battery reports usually contain values between 0-100
            # in the first few bytes after the report ID
            for report_id, report in valid_reports.items():
                # Check for potential battery values in the first 5 positions
                potential_battery_values = []
                for i in range(1, min(5, len(report))):
                    if 0 <= report[i] <= 100:
                        potential_battery_values.append((i, report[i]))
                
                if len(potential_battery_values) >= 2:
                    # If we found at least 2 potential battery values, use the first two
                    left_idx, left_battery = potential_battery_values[0]
                    right_idx, right_battery = potential_battery_values[1]
                    
                    logger.info(f"Found battery levels in report ID 0x{report_id:02x} at positions {left_idx} and {right_idx}")
                    logger.info(f"Battery levels - Left: {left_battery}%, Right: {right_battery}%")
                    
                    # Store the successful report ID in config for future use
                    if self.config.get("report_id") != report_id:
                        self.config["report_id"] = report_id
                        self.config["left_battery_index"] = left_idx
                        self.config["right_battery_index"] = right_idx
                        self.save_config()
                        logger.info(f"Updated config with report ID 0x{report_id:02x}")
                    
                    break
                elif len(potential_battery_values) == 1:
                    # If we only found one battery value, it might be for a single-sided keyboard
                    # or the other half might be offline
                    idx, value = potential_battery_values[0]
                    left_battery = value
                    logger.info(f"Found single battery level in report ID 0x{report_id:02x} at position {idx}")
                    logger.info(f"Battery level - Left: {left_battery}%, Right: None (or not connected)")
                    
                    # Store the successful report ID in config
                    if self.config.get("report_id") != report_id:
                        self.config["report_id"] = report_id
                        self.config["left_battery_index"] = idx
                        self.config["right_battery_index"] = None
                        self.save_config()
                        logger.info(f"Updated config with report ID 0x{report_id:02x} (single battery)")
                    
                    break
            
            # If we didn't find battery values but have previously working configuration,
            # try using those stored values
            if left_battery is None and right_battery is None and "report_id" in self.config:
                try:
                    report_id = self.config["report_id"]
                    report = device.get_feature_report(report_id, 64)
                    
                    if self.config["left_battery_index"] is not None and self.config["left_battery_index"] < len(report):
                        left_idx = self.config["left_battery_index"]
                        if 0 <= report[left_idx] <= 100:
                            left_battery = report[left_idx]
                    
                    if self.config["right_battery_index"] is not None and self.config["right_battery_index"] < len(report):
                        right_idx = self.config["right_battery_index"]
                        if 0 <= report[right_idx] <= 100:
                            right_battery = report[right_idx]
                    
                    if left_battery is not None or right_battery is not None:
                        logger.info(f"Using stored config with report ID 0x{report_id:02x}")
                        logger.info(f"Battery levels - Left: {left_battery}%, Right: {right_battery}%")
                except Exception as e:
                    logger.warning(f"Failed to use stored report ID configuration: {e}")
            
            # If we still don't have battery levels, dump all reports for debugging
            if left_battery is None and right_battery is None:
                logger.warning("Could not detect battery levels automatically")
                logger.debug("All detected reports:")
                for report_id, report in valid_reports.items():
                    logger.debug(f"Report ID 0x{report_id:02x}: {[hex(b) for b in report]}")
                
            device.close()
            
        except Exception as e:
            logger.error(f"Error accessing keyboard: {e}")
        
        self.battery_levels = {
            "left": left_battery,
            "right": right_battery,
            "timestamp": timestamp
        }
        
        # Log to CSV file
        self.log_battery_levels()
        
        return self.battery_levels    

    def log_battery_levels(self):
        """Log battery levels to CSV file"""
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w') as f:
                f.write("timestamp,left_battery,right_battery\n")
                
        left = self.battery_levels["left"] if self.battery_levels["left"] is not None else ""
        right = self.battery_levels["right"] if self.battery_levels["right"] is not None else ""
        
        with open(LOG_FILE, 'a') as f:
            f.write(f"{self.battery_levels['timestamp']},{left},{right}\n")
    
    def generate_tray_icon(self):
        """Generate tray icon based on battery levels"""
        if not self.ui.gui_available:
            return None
            
        # Create a blank image for the icon (64x64)
        img = self.ui.create_icon_image(64, 64)
        if img is None:
            return None
            
        d = self.ui.get_image_draw(img)
        if d is None:
            return None
        
        left_level = self.battery_levels["left"]
        right_level = self.battery_levels["right"]
        
        # Define colors based on battery levels
        def get_color(level):
            if level is None:
                return (128, 128, 128)  # Gray for unknown
            elif level <= self.config["critical_battery_threshold"]:
                return (255, 0, 0)      # Red for critical
            elif level <= self.config["low_battery_threshold"]:
                return (255, 165, 0)    # Orange for low
            else:
                return (0, 255, 0)      # Green for good
        
        # Draw left battery indicator
        left_color = get_color(left_level)
        d.rectangle([(5, 20), (25, 44)], outline="white", width=2)
        if left_level is not None:
            fill_height = int(20 * (left_level / 100))
            d.rectangle([(7, 42 - fill_height), (23, 42)], fill=left_color)
        
        # Draw right battery indicator
        right_color = get_color(right_level)
        d.rectangle([(38, 20), (58, 44)], outline="white", width=2)
        if right_level is not None:
            fill_height = int(20 * (right_level / 100))
            d.rectangle([(40, 42 - fill_height), (56, 42)], fill=right_color)
        
        # Add battery terminals
        d.rectangle([(11, 18), (19, 20)], fill="white")
        d.rectangle([(44, 18), (52, 20)], fill="white")
        
        # Add L and R labels
        d.text((10, 48), "L", fill="white")
        d.text((48, 48), "R", fill="white")
        
        return img
    
    def update_tray(self):
        """Update the system tray icon"""
        img = self.generate_tray_icon()
        if img is not None:
            self.ui.system_tray.update_icon(img)
        
        # Update tooltip
        left = self.battery_levels["left"]
        right = self.battery_levels["right"]
        left_str = f"{left}%" if left is not None else "Unknown"
        right_str = f"{right}%" if right is not None else "Unknown"
        
        tooltip = f"ZMK Battery Monitor - Left: {left_str}, Right: {right_str}"
        self.ui.system_tray.update_title(tooltip)
        
        # Show notifications for low battery
        if left is not None and left <= self.config["critical_battery_threshold"]:
            self.ui.notification_system.show_notification(
                "Critical Battery Warning", 
                f"Left keyboard half battery is critically low ({left}%)",
                True
            )
        elif right is not None and right <= self.config["critical_battery_threshold"]:
            self.ui.notification_system.show_notification(
                "Critical Battery Warning", 
                f"Right keyboard half battery is critically low ({right}%)",
                True
            )
    
    def monitoring_loop(self):
        """Main monitoring loop - runs in a separate thread"""
        while self.running:
            try:
                if self.find_keyboard():
                    self.read_battery_levels()
                    if self.icon:  # Only update tray if GUI is running
                        self.update_tray()
                else:
                    logger.warning("Keyboard not found, will retry...")
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                
            # Sleep until next check
            for _ in range(self.config["update_interval"]):
                if not self.running:
                    break
                time.sleep(1)
    
    def start_monitoring(self):
        """Start the battery monitoring thread"""
        if self.running:
            return
            
        self.running = True
        self.monitor_thread = threading.Thread(target=self.monitoring_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("Monitoring started")
    
    def stop_monitoring(self):
        """Stop the battery monitoring thread"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Monitoring stopped")
    
    def show_battery_status(self):
        """Show a dialog with current battery status"""
        left = self.battery_levels["left"]
        right = self.battery_levels["right"]
        timestamp = self.battery_levels["timestamp"]
        
        left_str = f"{left}%" if left is not None else "Unknown"
        right_str = f"{right}%" if right is not None else "Unknown"
        
        message = f"Battery Levels (as of {timestamp}):\n\n"
        message += f"Left Half: {left_str}\n"
        message += f"Right Half: {right_str}\n"
        
        # Display dialog using platform-specific implementation
        self.ui.notification_system.show_message_dialog(message, "ZMK Battery Status")
    
    def show_config_dialog(self):
        """Show configuration dialog"""
        message = "Current Configuration:\n\n"
        message += f"Update Interval: {self.config['update_interval']} seconds\n"
        message += f"Low Battery Threshold: {self.config['low_battery_threshold']}%\n"
        message += f"Critical Battery Threshold: {self.config['critical_battery_threshold']}%\n"
        message += f"Device: {self.config['device_name']}\n\n"
        message += "To modify these settings, edit the config file at:\n"
        message += CONFIG_FILE
        
        self.ui.notification_system.show_message_dialog(message, "ZMK Battery Monitor Config")
    
    def open_log_file(self):
        """Open the log file with default application"""
        self.ui.system_utility.open_file(LOG_FILE)
    
    def init_gui(self):
        """Initialize GUI (system tray icon)"""
        # Create menu structure
        menu_items = [
            ("Battery Status", lambda: self.show_battery_status(), True),
            ("Configuration", lambda: self.show_config_dialog(), False),
            ("View Battery Log", lambda: self.open_log_file(), False),
            ("Exit", lambda: self.ui.system_tray.stop_tray(), False)
        ]
        
        # Create initial icon
        initial_icon = self.generate_tray_icon()
        if initial_icon is None:
            logger.error("Could not create icon image")
            return False
        
        # Create system tray icon
        if not self.ui.system_tray.create_tray_icon(initial_icon, "ZMK Battery Monitor", menu_items):
            logger.error("Could not create system tray icon")
            return False
        
        self.icon = True  # Flag to indicate GUI is active
        return True
    
    def run_gui(self):
        """Run the application with GUI (system tray icon)"""
        if not self.init_gui():
            logger.error("GUI initialization failed. Running in CLI mode.")
            self.run_cli()
            return
        
        # Start monitoring
        self.start_monitoring()
        
        # Run the icon loop (this blocks until stop is called)
        self.ui.system_tray.run_tray()
        
        # When tray stops, clean up
        self.stop_monitoring()
    
    def run_cli(self):
        """Run the application in command-line mode"""
        print("ZMK Battery Monitor (CLI Mode)")
        print("Ctrl+C to exit\n")
        
        self.start_monitoring()
        
        try:
            while True:
                # Print current status periodically
                if self.battery_levels["timestamp"]:
                    left = self.battery_levels["left"]
                    right = self.battery_levels["right"]
                    timestamp = self.battery_levels["timestamp"]
                    
                    left_str = f"{left}%" if left is not None else "Unknown"
                    right_str = f"{right}%" if right is not None else "Unknown"
                    
                    print(f"[{timestamp}] Battery Levels - Left: {left_str}, Right: {right_str}")
                
                time.sleep(60)  # Status update every minute in CLI mode
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.stop_monitoring()

def main():
    monitor = BatteryMonitor()
    
    # Parse command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        monitor.run_cli()
    else:
        # Check if GUI is available
        if monitor.ui.gui_available:
            monitor.run_gui()
        else:
            print("GUI dependencies not available. Running in CLI mode.")
            monitor.run_cli()

if __name__ == "__main__":
    main()
