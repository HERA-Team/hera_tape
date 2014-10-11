
import datetime, inspect

class Debug:

    def __init__(self, pid, debug=False):
        self.pid = str(pid)
        self.debug = debug

    def print(self, *args):
        date = datetime.datetime.now().strftime('%Y%m%d-%H%M')
        output = " ".join(args)

        call_info = inspect.stack()[1]
        caller = call_info[1] if call_info[3] == '<module>' else call_info[3]

        print(":".join(["debug",date,self.pid,caller,output]), flush=True)
