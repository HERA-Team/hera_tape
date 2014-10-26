#! /bin/bash

## barcode options to use
## -t table geometry
## -u unit 
## -o output_file
## -e encoding type
## -p pagesize
## -m margins (internal to barcode)
## -c disable checksum

file_name=label.ps
barcode="barcode -u mm -e code39 -p letter -o $file_name -c"  

version=${1:-1}
count=${2:-15}

for ((i=1; i<=$count; i++)); do 
    printf "PAPR$version%03d\n" $i
done | $barcode -t 2x15+14+13-15-13 -m 15,1.5


