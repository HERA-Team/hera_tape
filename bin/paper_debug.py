"Basic debug logging and exit functions"
import datetime, inspect, sys

class Debug:
    "Debug class"

    def __init__(self, pid, debug=False, debug_level=0):
        """ Initialize with a pid if debug is set to True"""
        self.pid = str(pid)
        self.debug_state = debug
        self.debug_threshold = debug_level

    def print(self, *args, debug_level=255):
        """Print arguments as debug message"""
        if self.debug_state and debug_level > self.debug_threshold:
            date = datetime.datetime.now().strftime('%Y%m%d-%H%M')
            output = " ".join(args)

            call_info = inspect.stack()[1]
            caller = call_info[1] if call_info[3] == '<module>' else call_info[3]

            _message = ":".join(["debug", date, self.pid, caller, output])
            print(_message, flush=True)

    def exit(self, debug_level=255):
        """Force exit if debugging"""
        if self.debug_state and debug_level > self.debug_threshold:
            sys.exit()
