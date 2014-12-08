"Basic debug logging and exit functions"
import datetime, inspect, sys

class Debug:
    "Debug class"

    def __init__(self, pid, debug = False, debug_threshold=256):
        """ Initialize with a pid if debug is set to True
        :type  pid: int
        :param pid: unique identifier of the process tree
        :type  debug: bool
        :param debug: whether or not to enable debugging, defaults to False
        :type  debug_threshold: int
        :param debug_threshold: the threshold below which messages should be printed
        """
        self.pid = str(pid)
        self.debug_state = debug
        self.debug_threshold = debug_threshold

    def print(self, *messages, debug_level=0):
        """Print arguments as debug message if the message debug_level
        is < than the instance debug_threshold.
        :type  *messages: str
        :param *messages: strings to join and send to output
        :type debug_level: int
        :param debug_level: the message debug_level from 0-255
        """

        if self.debug_state and debug_level < self.debug_threshold:
            date = datetime.datetime.now().strftime('%Y%m%d-%H%M')
            output = " ".join(messages)

            call_info = inspect.stack()[1]
            caller = call_info[1] if call_info[3] == '<module>' else call_info[3]

            _message = ":".join(["debug", date, self.pid, caller, output])
            print(_message, flush=True)

    def exit(self, debug_level=255):
        """Force exit if debugging and level is less than debug_threshold"""
        if self.debug_state and debug_level < self.debug_threshold:
            sys.exit()
