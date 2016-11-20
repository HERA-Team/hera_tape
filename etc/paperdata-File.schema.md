# table schema for paperdata.File

## description 

    Mysql schema for File table tracks location information for all 
raw and compressed data.

## metadata

    host: shredder.physics.upenn.edu
    db_name: paperdata
    table_name: File

## schema
```bash
Field               Type            Null  Key   Default  Extra
host          varchar(100)          YES  NULL                    ## fullname of host where file is located
base_path     varchar(100)          YES  NULL                    ## path to file if on filesystem
filename      varchar(100)          YES  NULL
filetype      varchar(20)           YES  NULL
source        varchar(200)          NO   PRI                     ## full path (including file) if on filesystem
obsnum        bigint(20)            YES  MUL   NULL
filesize      decimal(7,2)          YES  NULL                    ## size in MB
md5sum        varchar(32)           YES  NULL                    ## md5sum of file on filesystem
tape_index    varchar(100)          YES  NULL                    ## $date[$tape_labels]-$tape_segment:$tar_index
is_tapeable   tinyint(1)            YES  NULL                    ## status 1 if file can be written to tape
is_deletable  tinyint(1)            YES  NULL
timestamp     datetime              YES  NULL
init_host     varchar(100)          YES  NULL
```

## raw

```bash
## 20161119
root@shredder[~]# mysql -e 'show tables' paperdata
+---------------------+
| Tables_in_paperdata |
+---------------------+
| Feed                | 
| File                | 
| Observation         | 
| alembic_version     | 
+---------------------+
root@shredder[~]# mysql -e 'select * from File limit 1' paperdata
+---------------------+-----------+----------------------+----------+--------------------------------------------------+-------------+----------+----------------------------------+---------------------------------+-------------+--------------+-----------+---------------------+
| host                | base_path | filename             | filetype | source                                           | obsnum      | filesize | md5sum                           | tape_index                      | is_tapeable | is_deletable | timestamp | init_host           |
+---------------------+-----------+----------------------+----------+--------------------------------------------------+-------------+----------+----------------------------------+---------------------------------+-------------+--------------+-----------+---------------------+
| folio.sas.upenn.edu | ON TAPE   | zen.2455933.55758.uv | uv       | folio.sas.upenn.edu:ON TAPE/zen.2455933.55758.uv | 17185747568 |  1884.10 | 6cfcb105958791103b6b87d4f511c924 | 20150103[PAPR1007,PAPR2007]-0:1 |           0 |            0 | NULL      | folio.sas.upenn.edu | 
+---------------------+-----------+----------------------+----------+--------------------------------------------------+-------------+----------+----------------------------------+---------------------------------+-------------+--------------+-----------+---------------------+
root@shredder[~]# 
root@shredder[~]# echo describe File|mysql --defaults-file=/root/.my.papertape-prod.cnf  --skip-column-names paperdata|column -t
host          varchar(100)  YES  NULL
base_path     varchar(100)  YES  NULL
filename      varchar(100)  YES  NULL
filetype      varchar(20)   YES  NULL
source        varchar(200)  NO   PRI
obsnum        bigint(20)    YES  MUL   NULL
filesize      decimal(7,2)  YES  NULL
md5sum        varchar(32)   YES  NULL
tape_index    varchar(100)  YES  NULL
is_tapeable   tinyint(1)    YES  NULL
is_deletable  tinyint(1)    YES  NULL
timestamp     datetime      YES  NULL
init_host     varchar(100)  YES  NULL
```
