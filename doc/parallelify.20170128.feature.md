# parallel verification of written tapes

owner: dconover:20170128    
review: optional

## contents
  1. [overview](#overview)
  2. [manifest](#manifest)
  3. [feature](#feature)
  4. [test](#test)
  5. [deploy](#deploy)
  6. [log](#log)
  7. [todo](#todo)
  8. [refactor](#refactor)
  9. [faq](#faq)
  10. [reference](#reference)
  11. [communications](#communications)
  12. [suppplement](#suppplement)
  
## overview
  We are currently verifying 25% of the files written to tape after the tape 
writing process. Though the tapes are written in parallel, the verification 
process is performed in serial. We, therefore, would like to parallelize the 
verification process, to improve throughput.

## manifest
  to avoid interrupting production code, we are making changes as follows:
  1. [paper_dump.py](/bin/paper_dump.py) - a new class: VerifyThread, a new dump class: DumpFaster, a 
  new verification method: dump_pair_verify, an updated method: 
  tar_archive_fast, an updated method: fast_batch
  2. [paper_mtx.py](/bin/paper_mtx.py) - refactor tape_archive_md5() to unload tapes when complete

## feature 
  We are currently using DumpFast.tar_archive_fast() (in paper_dump.py) which
contains the following:

```python
        for label_id in tape_label_ids:
            dump_verify_status = self.dump_verify(label_id)
            if dump_verify_status is not self.status_code.OK:
                self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
                tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
                self.close_dump()
``` 

  Instead we should pass the tape_label_ids into dump_verify().

  dump_verify() is inherited from Dump.dump_verify() and contains:
```python
        ## run a tape_self_check
        self_check_status, item_index, catalog_list, md5_dict, tape_pid = self.tape_self_check(tape_id)
```

  tape_self_check in turn calls tape.tape_archive_md5 (found in paper_mtx.py)
```python
        tape_archive_md5_status, reference = self.tape.tape_archive_md5(tape_id, tape_pid, catalog_list, md5_dict)
```

  Changer.tape_archive_md5() then loops through each archive on tape and checks a
random file md5 from each

  In order to achieve parallelization, we need to run the python code in
parallel. In contrast, the dump code simply runs shell scripts in parallel. 
In order to make the python run in parallel we should change 
DumpFast.tar_archive_fast() to run self.dump_verify on the label_ids using 
python threads.

  Something like:
```python
import threading
 
## custom thread class to capture status code
## when dump_verify() completes
class VerifyThread(threading.Thread):
    ## init object with tape_id and dump_object
    ## so we can call dump_object(tape_id)
    def __init__(self, tape_id, dump_verify):
        self.tape_id = tape_id
        self.dump_verify_status = ''
 
    ## custom run() to run dump_verify and save returned output
    def run():
        self.dump_verify_status = dump_verify(label_id)
 
    ## we need a function we can call when run() ends that will return 
    ## the captured return code
    def status(): 
        return self.dump_verify_status
 
## example use of new custom class
## this should be called from within a DumpFast object
for label_id in tape_label_ids:
    verify_list = []
    
    verify = VerifyThread(label_id, self)
    verify_list.append(verify)
    verify.start()    
 
for verify in verify_list:
    ## join() will block until run() completes
    verify.join()

    ## after run completes, we need to query the status code with our 
    ## custom status() method (since join does not return the status code)
    dump_verify_status = verify.status()

    ## process the return code to see if we should abort or continue
    if dump_verify_status is not self.status_code.OK:
        self.debug.output('Fail: dump_verify {}'.format(dump_verify_status))
        tar_archive_single_status = self.status_code.tar_archive_single_dump_verify
        self.close_dump()   

```

  Since we're passing in a reference to "self" we could also just set a
variable and modify it from within the thread, but I like to explicitly return
the variable out to the calling function with the custom status method.

  Changer.tape_archive_md5() uses self.load_tape_drive(tape_id). If the tapes are loaded 
before the function is called it will leave the tape in the drive and rewind it.

  We can pair this with the threaded call like:
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

finally we need to update DumpFaster.tar_archive_fast() to call dump_pair_verify
instead of the original verification for loop
```python
    def tar_archive_fast(self, catalog_file):
        """Archive files directly to tape using only a single drive to write 2 tapes"""

        tar_archive_fast_status = self.status_code.OK

        ## select ids
        tape_label_ids = self.labeldb.select_ids()

        ## load up a fresh set of tapes
        self.tape.load_tape_pair(tape_label_ids)

        ## add the catalog to the beginning of the tape
        for label_id in tape_label_ids:
            self.debug.output('archiving to label_id - {}'.format(label_id))

        ## prepare the first block of the tape with the current tape_catalog
        self.tape.prep_tape(catalog_file)

        ## actually write the files in the catalog to a tape pair
        self.debug.output('got list - {}'.format(self.files.tape_list))
        self.tape.archive_from_list(self.files.tape_list)

        ## check the status of the dumps
        tar_archive_fast_status = self.dump_pair_verify(tape_label_ids)

        ## unload the tape pair
        self.tape.unload_tape_pair()

        ## update the db if the current dump status is OK
        if tar_archive_fast_status is self.status_code.OK:
            log_label_ids_status = self.log_label_ids(tape_label_ids, self.files.tape_list)
            if log_label_ids_status is not self.status_code.OK:
                self.debug.output('problem writing labels out: {}'.format(log_label_ids_status))
        else:
            self.debug.output("Abort dump: {}".format(tar_archive_fast_status))
            self.close_dump()
``` 


## test
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
        ## 

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
  
  ```python
  from os import makedirs
      def test_build_dataset()
          
          ## make a test directory to hold some tes files
          makedirs('/papertape/tmp/test',exist_ok=True)
          ## check if we have enough room on the partition
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
  
## deploy
  1. review tests with slack(eoranalysis):/dm:plaplant
  2. update papertape-prod_dump.py to use dump faster DumpFaster

## log
  1. review code
  2. document proposed fix
  3. refactored tape_archive_md5
  4. check if Changer.tape_archive_md5 uses only one drive - it is agnostic if the tapes are already loaded
  5. debug proposed fix - proposed creating new dump routine, so updates don't break current running code
  6. integrate code fix - dconover:20170203
  7. refactor code fix; refactor test code doc - dconover:20170208

## todo 
  8. refactor: update check_credentials_file() and PaperDB.__init__()
  7. refactor: update DumpTest.__init__() to run self.test_data_init() and connect
  7. build test dataset
  8. test fix
  9. report changes to plaplant via slack
  10. update production dump script (papertape-prod_dump.py)

## refactor
  plaplant also requested that the verification process unload the tape 
when complete. I am adding that to the end of tape_archive_md5().

```python
   def tape_archive_md5(self, tape_id, job_pid, catalog_list, md5_dict):
        """loop through each archive on tape and check a random file md5 from each

        :rtype : bool"""

## [... truncated for brevity]

        self.unload_tape(tape_id)
        return tape_archive_md5_status, reference
```

  while writing the test code I notice that the mtx credentials where hardcoded
in the initialization for the Dump class. I am changing that to a default init variable. I am making the current default the same as the current
running dumps so that we don't accidentally disrupt the current code.

```python
class Dump(object):
    """Coordinate a dump to tape based on deletable files in database"""

    def  __init__(self, credentials='/papertape/etc/my.papertape-test.cnf', mtx_credentials='home2/obs/.my.mtx.cnf', debug=False, pid=None, disk_queue=True, drive_select=2, debug_threshold=255):
        """initialize"""
## [... truncated for brevity]
```
  while writing integrating the new dump_verify code, I see that dump() close is not
fully implemented and requires that self.dump_state get updated as various methods 
are completed. I am adding an update to the self.dump_state in the dump_verify() method so 
that dump_close() could eventually be made to work correctly.

```python
    def dump_verify(self, tape_id):
        """take the tape_id and run a self check,
        then confirm the tape_list matches

        """
        dump_verify_status = self.status_code.OK

        ## we update the dump state so self.dump_close() knows what actions to take
        self.dump_state = self.dump_state_code.dump_verify
## [... truncated for brevity]
```
  creating a default variable for the credentials_file and a new method for checking 
the validity of the credentials file

```python
from os import path

class PaperDB(object):
    def __init__(self, version, credentials, pid, debug=False, debug_threshold=255):
        """Initialize connection and collect file_list of files to dump.
        :type version: int
        :type credentials: string
        :type pid: basestring
        :type debug: bool
        :type debug_threshold: int
        """

        self.pid = pid
        self.version = version
        self.debug = Debug(self.pid, debug=debug, debug_threshold=debug_threshold)
        self.status_code = StatusCode

        
        ## we have a default credentials variable that may not exist, so we should check it first
        self.check_credentials_file(credentials) || return

        self.credentials = credentials
        self.paperdb_state_code = PaperDBStateCode
        self.paperdb_state = self.paperdb_state_code.initialize
        self.connection_timeout = 90
        self.connection_time = timedelta()
        self.connect = ''
        self.cur = ''
        self.db_connect('init', credentials)

        self.file_list = []
        self.file_md5_dict = {}
        self.claimed_files = []
        self.claimed_state = 0
        
    @staticmethod
    def check_credentials_file(credentials):
    """Run checks on a credentials file; currently just check that it exists and is not empty.
    :type credentials: string
    """
        ## default to false
        _status_code = False
        
        ## return true if the credentials file exists and is not zero size
        if path.isfile(credentials) and path.getsize(credentials) > 0:
           _status_code = True
         
        ## return the status code
        return _status_code
```
update __init__() to use the new file check:

## faq
  1. does Changer.tape_archive_md5 use a specific tape (e.g. /dev/nst0)?
  **if the tapes are already loaded, it is agnostic**
  2. where do the mtx db credentials get set?
  **a default init variable (mtx_credentials) in the Dump class**

## reference
  1. from python.org: python3 [threading](https://docs.python.org/3/library/threading.html)
  2. from python-course.eu: create a [custom thread class](http://www.python-course.eu/threads.php) and modify 
  run to save the return value from dump_verify
  3. stackoverflow: [mkdir -p](http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python)
  4. python3 docs: [os.makedirs](https://docs.python.org/3/library/os.html?highlight=makedirs#os.makedirs)
  5. making pseudo [random data files](http://jessenoller.com/blog/2008/05/30/making-re-creatable-random-data-files-really-fast-in-python)

## communications
  communications for this project have all been with Paul La Plante over slack on the
group's slack via direct message

  1. the folio group uses their own slack channel eoaranalysis.slack.com
  2. paul la plante <plaplant@sas.upenn.edu>
  3. james aguirre <jaguirre@sas.upenn.edu>

## supplement
slack discussion (eoranalysis:dm):
```bash
plaplant [10:08 AM] 
how hard would it be to parallelize the error-checking for the tapes?

[10:09]  
reading the scripts, it looks like the writing is done in parallel, but for error-checking, the tapes are loaded in one at a time

d [10:24 AM] 
shouldn’t be too hard. I think that makes sense. I think I did that at the time because I thought we weren’t going to check both tapes, but later decided to check both tapes

[10:29]  
I could look at the code this weekend.

plaplant [10:30 AM] 
awesome, thanks a lot

[10:30]  
in practice, i’m finding that error checking 25% of the files (for both tapes) takes about as long as writing the data

[10:31]  
so if we could do both at once, it’d be a big time savings

d [10:34 AM] 
how long does it take to write the tapes?

plaplant [10:34 AM] 
~30 hours

[10:34]  
per tape

[10:35]  
~16 for writing the data, then ~7 per data check

[10:35]  
this is with 4-file batches

d [10:35 AM] 
that’s big

plaplant [10:36 AM] 
what’s big? like it shouldn’t take this long?

d [11:17 AM] 
I meant big, like that’s a big savings if we can change it

plaplant [11:21 AM] 
oh yeah, definitely

[11:22]  
it’d also be helpful if we wanted to tape up the data in real time, since we’re projecting to take a tape’s worth of data per night next year
```

discussion around refactoring unloading tape after verification:
```bash
plaplant [11:07 AM] 
cool, thanks so much for writing this up!

[11:08]  
one last thing that would be nice is unloading the tapes after successfully verifying

[11:08]  
right now, when the script finishes, there’s still a tape in drive 0

d [4:55 PM] 
I think the script has methods for unloading the drives if there’s a tape in it.

plaplant [5:38 PM] 
Oh okay, I'll try that

[5:38]  
Thanks

d [6:17 PM] 
I’ve added an unload call to the end of the verification process :slightly_smiling_face:
```
discussion about testing:
```bash
d [12:25 PM] 
I’ve finally integrated the new code. I still have to write some tests, but if you’re between runs, you can call it by changing the dump class from DumpFast to DumpFaster in the papertape-prod_dump.py file. I am hoping to be able to get some tests written and run on the old tape library this weekend.

plaplant [12:25 PM] 
Excellent, thanks so much! :slightly_smiling_face:

[12:26]  
I really appreciate all the work that went in

[12:27]  
I’m running a dump right now, but it should finish later today/early tomorrow. I might hold off on using the new version till all the tests are done, since the hard drive version of what I’m taping up now will be deleted when we’re done, so I want everything air-tight

[12:28]  
But thanks again for this change, it’ll really speed things up```

<br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br><br>



