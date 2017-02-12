# scratchpad for keeping track of ideas for parallelify.20170128.feature.md

owner: dconover:20170211

## related
  1. feature doc: [parallelify.20170128.feature.md](parallelify.20170128.feature.md)
  
## scratch

These for loops might benefit from rewriting in a more declarative style
```python
import threading
 
class VerifyThread(threading.Thread):
## [... see custom class definition above]
 
def dump_pair_verify(self, tape_label_ids):

    return_codes = {} ## return codes indexed by tape_label
    verification_threads = {}  ## verification threads indexed by tape_label
    
    self.tape.load_tape_pair(tape_label_ids)
    
    ## create a thread for each tape (label_id)
    ## so tapes can be verified in parallel
    for label_id in tape_label_ids:
 
        ## each thread needs a tape and the current dump object
        verify_thread = VerifyThread(label_id, self)
        verification_threads[label_id] = verify_thread
        verify_thread.start()
 
    ## after we start both threads, we then have to wait for the 
    ## started threads to complete
    for label_id in tape_label_ids:
        ## join() will block until run() completes
        verification_threads[label_id].join()
  
        ## after run completes, we need to query the status code with our
        ## custom status() method
        return_codes[label_id] = verification_threads[label_id].status()
 
    ## check both return codes and return failure if either is not OK
    for label_id, return_code in return_codes.items():
       if return_code is not self.status_code.OK:
           return return_code
        
    ## if we didn't return a failure above, return success
    return self.status_code.OK
```

could be rewritten:
```python
from functools import reduce
from threading import Thread
 
class VerifyThread(Thread):
## [... see custom class definition above]
 
def dump_pair_verify(self, tape_label_ids):
 
    ## thread instances need to be started, we can use the output to make a list of threads
    def start_verification(thread):
        thread.start()
        return thread
    
    ## join will block until the thread completes, then we can retrieve the status from the verification
    def get_verification_status(thread):
        thread.join()
        return thread.status()
 
    ## given a pair of verification status codes, return a "non-OK" status if either is not "OK"
    def check_thread_status(status_1, status_2):
        return status_1 if status_1 is not self.status_return_code.OK else status_2
 
    ## foreach label, start a thread and add it to a list
    started_threads = [start_verification(VerifyThread(label_id, self)) for label_id in tape_label_ids]
    
    ## foreach thread, check the verification status and add it to a list
    return_codes = [get_verification_status(thread) for thread in started_threads]
    
    ## foreach status code, check if either is not "OK"
    return reduce(check_thread_status, return_codes) 
```