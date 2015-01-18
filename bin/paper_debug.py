"""Basic debug logging and exit functions"""
import datetime, inspect, sys

class Debug:
    """Debug class"""

    def __init__(self, pid, debug = False, debug_threshold=256):
        """ Initialize with a pid if debug is set to True
        :type  pid: basestring
        :param pid: unique identifier of the process tree
        :type  debug: bool
        :param debug: whether or not to enable debugging, defaults to False
        :type  debug_threshold: int
        :param debug_threshold: the threshold below which messages should be printed
        """
        self.pid = str(pid)
        self.debug_state = debug
        self.debug_threshold = debug_threshold

    def caller_name(self, skip=2):
        """Get a name of a caller in the format module.class.method

           `skip` specifies how many levels of stack to skip while getting caller
           name. skip=1 means "who calls me", skip=2 "who calls my caller" etc.

           An empty string is returned if skipped levels exceed stack height
        """
        stack = inspect.stack()
        start = 0 + skip
        if len(stack) < start + 1:
          return ''
        parentframe = stack[start][0]

        name = []
        module = inspect.getmodule(parentframe)
        # `modname` can be None when frame is executed directly in console
        # consider using __main__
        if module:
            name.append(module.__name__)
        # detect classname
        if 'self' in parentframe.f_locals:
            # I don't know any way to detect call from the object method
            # XXX: there seems to be no way to detect static method call - it will
            #      be just a function call
            name.append(parentframe.f_locals['self'].__class__.__name__)
        codename = parentframe.f_code.co_name
        if codename != '<module>':  # top level usually
            name.append( codename ) # function or a method
        del parentframe
        return ".".join(name)

    def output(self, *messages, debug_level=0 ):
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

            ##_message = ":".join(["debug", date, self.pid, caller, output])
            _message = ":".join(["debug", date, self.pid, self.caller_name(), output])
            print(_message, flush=True)

    def print_source(self):
        print(''.join(inspect.getsourcelines(self.caller_name())[0]))

    def exit(self, debug_level=255):
        """Force exit if debugging and level is less than debug_threshold"""
        if self.debug_state and debug_level < self.debug_threshold:
            sys.exit()
