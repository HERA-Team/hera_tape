# log keeping track of ideas and modifications for parallelify.20170128.feature.md

owner: dconover:20170211

## related
  1. feature doc: [parallelify.20170128.feature.md](parallelify.20170128.feature.md)
  
## contents
  1. [scratch](#scratch) - major edits/discussion to working documentation
  2. [try](#try) - python code trying things I don't fully understand
  3. [test](#test) - python code I test in snippets before moving to prod
  4. [scrap](#scrap) - proposed work that were scrapped before deployment

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
  if I have a file_check(filename) that returns true or false for the given filename, can I 
call it and raise an exception inside a class \_\_init__(self, filename)?

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
  If I have an instance variable, can I return it with a method of the same name?
  
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
Can I use statvfs to see if I can check the free space on the partition

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

###### pseudo random
  A method for writing some randomish files (modified from [blog post](http://jessenoller.com/blog/2008/05/30/making-re-creatable-random-data-files-really-fast-in-python))
  
  ```python
from collections import deque
from os import path
 
def gen_file_data():
 
    source_file = "/usr/share/dic/linux.words", "r"
 
    a = deque("1092384956781341341234656953214543219")
    b = deque(open(source_file, "r").read().replace("\n", '').split())
 
    while True:
        yield ' '.join(list(a)[0:1024])
        a.rotate(int(b[0]))
        b.rotate(1)
 
def gen_randomish_file(file_name)
    file_data = gen_file_data()
    size = 1073741824 # 1gb
    with open(file_name, "w") as file_handle
        while path.getsize(file_name) < size:
            file_handle.write(file_data.next())
    
 
gen_randomish_file("test.data.txt")
```
output:
```bash
root@test[p4-dev:~/git/papertape-dev/bin/try]# python3 randomish.py
Traceback (most recent call last):
  File "randomish.py", line 24, in <module>
    gen_randomish_file("test.data.txt")
  File "randomish.py", line 21, in gen_randomish_file
    file_handle.write(file_data.next())
AttributeError: 'generator' object has no attribute 'next'
```

###### raise exception
try-raise.py
```python
from os import path
 
def check_credentials_file(credentials="non-exist.txt"):
 
    if not (path.isfile(credentials) and path.getsize(credentials) > 0):
        print("fail test " + credentials)
        raise ValueError('credentials file either does not exist or is empty')
 
    print("pass test " + credentials)
 
file = "try-raise.py"
check_credentials_file(file)
check_credentials_file()
```

output:
```python
root@test[p4-dev:~/git/papertape-dev/bin/try]$ python try-raise.py
pass test try-raise.py
fail test non-exist.txt
Traceback (most recent call last):
  File "try-raise.py", line 13, in <module>
    check_credentials_file()
  File "try-raise.py", line 7, in check_credentials_file
    raise ValueError('credentials file either does not exist or is empty')
ValueError: credentials file either does not exist or is empty
```
## test
  I "test" new code snippets to make sure they work as expected 

initially I tested the proposed code as integrated, and it generated errors (test_dump_pair_notape.py):
test_dump_pair_notape.py:
```python
from paper_dump import DumpFaster
 
class TestDumpNoTape(DumpFaster):
    ## in our test class we don't actually want to do a dump init
    def __init__(self):
        pass
        
    ## redefining dump_verify lets us test our new method without a full dump to tape
    def dump_verify(label_id):
        print("verification thread using " + label_id)   
        
label_ids = ['label_one', 'label_two']
test_dump_instance = TestDumpNoTape()
test_dump_instance.dump_pair_verify(label_ids)
```

pycharm output:
```
ssh://root@shredder.physics.upenn.edu:22/root/.pyenv/versions/3.4.1/bin/python -u /root/pycharm/dconover/paper-dump/bin/test_dump_pair_notape.py
Traceback (most recent call last):
  File "/root/pycharm/dconover/paper-dump/bin/test_dump_pair_notape.py", line 17, in <module>
    test_dump_instance.dump_pair_verify(label_ids)
  File "/root/pycharm/dconover/paper-dump/bin/paper_dump.py", line 510, in dump_pair_verify
    started_threads = [_start_verification(VerifyThread(label_id, self)) for label_id in tape_label_ids]
  File "/root/pycharm/dconover/paper-dump/bin/paper_dump.py", line 510, in <listcomp>
    started_threads = [_start_verification(VerifyThread(label_id, self)) for label_id in tape_label_ids]
  File "/root/pycharm/dconover/paper-dump/bin/paper_dump.py", line 497, in _start_verification
    thread.start()
  File "/root/.pyenv/versions/3.4.1/lib/python3.4/threading.py", line 842, in start
    if not self._initialized:
AttributeError: 'VerifyThread' object has no attribute '_initialized'

Process finished with exit code 1
```

after some debugging, I came up with the following threaded code proof of concept test_dump_pair_notape.py (the VerifyThread init method was missing: `Thread.__init__(self)`)
):
```python
__author__ = 'dconover@sas.upenn.edu'
    
from paper_dump import DumpFast
from paper_status_code import StatusCode
    
from threading import Thread
from functools import reduce
    
class DumpFaster(DumpFast):
    
    """Queless archiving means that the data is never transferred to our disk queues
    
    Disk queues are still used to maintain state in the event of a partial dump failure
    Tape verification is rewritten to make use of python threading.
    
    """
    
    def dump_pair_verify(self, tape_label_ids):
        """This is a wrapper to perform a threaded version of the
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
    
        ## join() will block until the thread completes, then we can retrieve the status from the verification
        def _get_verification_status(thread):
            thread.join()
            return thread.dump_verify_status
    
        ## given a pair of verification status codes, return a "non-OK" status if either is not "OK"
        def _check_thread_status(status_1, status_2):
            return status_1 if status_1 is not self.status_code.OK else status_2
    
        ## foreach label, start a thread and add it to a list
        started_threads = [_start_verification(VerifyThread(label_id, self)) for label_id in tape_label_ids]
    
        ## foreach thread, check the verification status and add it to a list
        return_codes = [_get_verification_status(thread) for thread in started_threads]
    
        ## foreach status code, check if either is not "OK"
        return reduce(_check_thread_status, return_codes)
    
## custom thread class to capture status code
## when dump_verify() completes
class VerifyThread(Thread):
    ## init object with tape_id and dump_object
    ## so we can call dump_object(tape_id)
    def __init__(self, tape_id, dump_object):
        Thread.__init__(self)
        self.tape_id = tape_id
        self.dump_object = dump_object
        self.dump_verify_status = ''
    
    ## custom run() to run dump_verify and save returned output
    def run(self):
        self.dump_verify_status = self.dump_object.dump_verify(self.tape_id)
    
class TestDumpNoTape(DumpFaster):
    ## in our test class we don't actually want to do a dump init
    def __init__(self):
        self.status_code = StatusCode
        pass
    
    ## redefining dump_verify lets us test our new method without a full dump to tape
    def dump_verify(self, label_id):
        print("verification thread using " + label_id)
    
    
label_ids = ['label_one', 'label_two']
test_dump_instance = TestDumpNoTape()
test_dump_instance.dump_pair_verify(label_ids)
```

output showing success:
```
ssh://root@shredder.physics.upenn.edu:22/root/.pyenv/versions/3.4.1/bin/python -u /root/.pycharm_helpers/pycharm/utrunner.py /root/pycharm/dconover/paper-dump/bin/test_dump_pair_notape.py true
Testing started at 7:51 PM ...
verification thread using label_one
verification thread using label_two

Process finished with exit code 0
Empty test suite.
```

afterwards I was able to re-integrate the code, deleting the local copy in test_dump_pair_notape.py and
adding it in it's proper place in paper_dump.py:
```python
__author__ = 'dconover@sas.upenn.edu'

from paper_dump import DumpFaster, VerifyThread
from paper_status_code import StatusCode


class TestDumpNoTape(DumpFaster):
    ## in our test class we don't actually want to do a dump init
    def __init__(self):
        self.status_code = StatusCode
        pass

    ## redefining dump_verify lets us test our new method without a full dump to tape
    def dump_verify(self, label_id):
        print("verification thread using " + label_id)


label_ids = ['label_one', 'label_two']
test_dump_instance = TestDumpNoTape()
test_dump_instance.dump_pair_verify(label_ids)
```

successful integration: 
```
ssh://root@shredder.physics.upenn.edu:22/root/.pyenv/versions/3.4.1/bin/python -u /root/.pycharm_helpers/pycharm/utrunner.py /root/pycharm/dconover/paper-dump/bin/test_dump_pair_notape.py true
Testing started at 8:06 PM ...
verification thread using label_one
verification thread using label_two

Process finished with exit code 0
Empty test suite.
```

## scrap
  We didn't implement all our proposed test code. It is included here in case it
  it useful to future development.

###### test deployment
  We are adding new methods to the TestDump class in paper_dump.py
  1. test_build_dataset - build a test dataset
  2. test_dump_faster - use the new DumpFaster class to dump the dataset like in papertape-prod_dump.py

```python
class TestDump(DumpFaster):

    def test_data_init(self):
        "create a test data set"
        pass
 
    def test_dump_faster(self):
        "run a test dump using the test data"
 
        ## from paper_dump import TestDump
  
        self.paper_creds = '/papertape/etc/.my.papertape-test.cnf'
  
        ## test variables (15GB batch and 1.536 TB tape size - lto4)
        self.batch_size_mb = 15000
        self.tape_size = 1536000
        self.fast_batch()
```  


###### test_build_dataset()
  for testing the new dump class we will employ the old tape library, still 
attached to shredder. We need to perform the following to prepare for testing:
  1. create a set of test files to dump
  2. identify a pair of tapes to use
  3. update the mtx database (a test mtxdb) to use those tapes
  4. create test credentials files for the mtx db and test papertape db
  
  make a temporary holding dir
  ```python
  from os import makedirs
      def test_build_dataset(temp_filepath='/papertapte/tmp/test_data')
          
          ## make a test directory to hold some tes files
          makedirs(temp_filepath, exist_ok=True)
```

check free space on the temp holding dir
```python
from os import statvfs

    def test_free_space(file_path, free_limit): 
    """given a free_limit return true if the available space is below the free_limit"""
        ## check if we have enough room on the partition
        _stat =  statvfs(file)
        _gb_free = _stat[0]*_stat[2]/1024**3
        
        return True if _gb_free > free_limit else False
        
    ## example call to new method
    self.test_free_space(test_tmp_path, expected_test_data_size)
```

make some files less than our expected_test_data_size and greater than our min_test_file_size
```python
          ## make some small test files
          ## add the test files to a database
```
  
###### test_dump_faster()
  The test method calls the new dump class on a crafted test data set

```python
      def test_dump_faster(self):
        "run a test dump using the test data"
 
        # self.paper_creds = '/papertape/etc/my.papertape-test.cnf'
        self.batch_size_mb = 15000
        self.tape_size = 1536000
        
        self.test_data_init()
        self.fast_batch()
```
  This will itself need to be run from a test script like:
```python
from paper_dump import TestDump    
    
## initialize the test code with test credentials
dump = TestDump()
    
## create the data set, run the test dump, cleanup the test data
dump.test_dump_faster()

```
