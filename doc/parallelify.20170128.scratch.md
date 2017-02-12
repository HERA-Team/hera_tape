# log keeping track of ideas and modifications for parallelify.20170128.feature.md

owner: dconover:20170211

## related
  1. feature doc: [parallelify.20170128.feature.md](parallelify.20170128.log.md)
  
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
    """This is essentially a wrapper to perform a threaded version of the 
    original call to dump_verify(). Our "threading" is implemented  in three 
    steps: 
    
      1. instantiate VerifyThread (that calls dump_verify()) and start each thread
      2. wait on each thread and get the verification status code from each
      3. check each status code and return failure if either is not "OK"
    """
 
    ## thread instances need to be started, we can use the output to make a list of started threads
    def _start_verification(thread):
        thread.start()
        return thread
    
    ## join will block until the thread completes, then we can retrieve the status from the verification
    def _get_verification_status(thread):
        thread.join()
        return thread.status()
 
    ## given a pair of verification status codes, return a "non-OK" status if either is not "OK"
    def _check_thread_status(status_1, status_2):
        return status_1 if status_1 is not self.status_return_code.OK else status_2
 
    ## foreach label, start a thread and add it to a list
    started_threads = [_start_verification(VerifyThread(label_id, self)) for label_id in tape_label_ids]
    
    ## foreach thread, check the verification status and add it to a list
    return_codes = [_get_verification_status(thread) for thread in started_threads]
    
    ## foreach status code, check if either is not "OK"
    return reduce(_check_thread_status, return_codes) 
```

## try
  I "try" things I don't understand
  
###### check or except
  if I have a file_check(filename) that returns true or false for the given filename, I can 
call it and raise an exception a class \_\_init__(self, filename) 

paper_check.py:
```python
from os import path

def file_check(filename):
   return path.isfile(filename) and path.getsize(filename) > 0
```

class-dev.py:
```python
from os import path
from paper_check import file_check

class dev(object):
    def  __init__ (self, filename):
        if not file_check(filename):
            print("check fails")
            raise Exception('file_check failed')
        print("check passes")

x = dev("class-dev.py")
x = dev("none-class-dev.py")
```

output:
```bash
root@test[~/git/papertape-dev/bin/try]$ python3 class-dev.py
check passes
check fails
Traceback (most recent call last):
  File "class-dev.py", line 21, in <module>
    x = dev("none-class-dev.py")
  File "class-dev.py", line 17, in __init__
    raise Exception('file_check failed')
Exception: file_check failed
```
###### status or state
  if I have an instance variable, can I return it with a method of the same name?
  
instantiate-return.py:
```python
class test(object):
  def __init__(self):
    self.state = "hello"
 ##   return False

  def status(self):
    return self.state

  def state(self):
    return self.state

x = test()
print(x.state)
print(x.status())
print(x.state())
```
output:
```bash
root@test[~/git/papertape-dev/bin/try]$ python3 instantiate-return.py
hello
hello
Traceback (most recent call last):
  File "instantiate-return.py", line 16, in <module>
    print(x.state())
TypeError: 'str' object is not callable
```
###### statvfs
I want to use statvfs to see if I can check the free space on the partition

statvfs.py:
```python
file = 'statvfs.py'

from os import statvfs

print(statvfs(file))

_stat =  statvfs(file) 
print(_stat[0]*_stat[4]/1024**3)
```
output:
```bash
root@test[~/papertape-dev/bin/try]# python statvfs.py
(4096, 4096, 141097102, 19507110, 19507110, 145686528, 142330019, 142330019, 0, 255)
74
root@test[~/papertape-dev/bin/try]# df -h .
Filesystem            Size  Used Avail Use% Mounted on
/dev/sdc3             539G  464G   75G  87% /
```

## test
  I "test" new code snippets to make sure they work as expected 