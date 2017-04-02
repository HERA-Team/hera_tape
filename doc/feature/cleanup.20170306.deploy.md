# refactor deployed code to flatten new test classes to eliminate unused code

owner: dconover:20170306

## introduction
  We implemented a new feature in our code in new classes using inheritance.  This 
allows us to update the code on the current test platform without accidentally 
overwriting code that is currently in use by a running dump job.

  Having tested and refactored our running dump jobs to use the new code, we no
longer have any use for the old code base. Instead, of keeping the forked classes 
separate, we should refactor the code into one dump class.

## methods
  The following classes can be flattened into a single class:
  1. Dump()    
    1. \_\_init__() -- replaced in DumpFaster()  
    2. archive_to_tape() -- unused    
    3. get_list() -- called by archive_to_tape() and DumpFast.batch_files()     
    4. tar_archive_single() -- called by archive_to_tape() and ResumeDump.manual_to_tape()     
    5. log_label_ids() -- called: tar_archive_single, DumpFast.tar_archive_fast(), DumpFaster.tar_archive_fast()    
    6. dump_verify() -- called: tar_archive_single(), DumpFast.tar_archive_fast()    
    7. tape_self_check() -- called: dump_verify()     
    8. tar_archive() -- called: archive_to_tape()     
    9. close_dump() -- should be renamed _close_dump      
  2. DumpFast(Dump)  
    1. tar_archive_fast()  
    2. fast_batch()   
    3. batch_files() -- called: fast_batch(), DumpFaster.fast_batch(), TestDump.test_build_archive()
  3. DumpFaster(DumpFast)    
    1. \_\_init__() -- called on object init    
    2. check_credentials_file()  -- called by \_\_init__()     
    3. dump_pair_verify()  -- called by tar_archive_fast()     
    4. fast_batch()     -- called to initiate dump in papertape-prod_dump.py
    5. tar_archive_fast()    -- called by fast_batch()
