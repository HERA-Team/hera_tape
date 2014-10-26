#! /bin/bash


# %   char    xpos   ypos fontsize
#     [(P)  106.04 718.00 6.5]
#     [(A)  124.26 718.00  0.00]
#     [(P)  142.47 718.00  0.00]
#     [(R)  160.69 718.00  0.00]
#     [(1)  178.90 718.00  0.00]
#     [(0)  197.11 718.00  0.00]
#     [(0)  215.33 718.00  0.00]
#     [(1)  233.54 718.00  0.00]
#     [(PAPER - 20140920 - copy 1) 130 712 6.5]
# ]   { {} forall dup 0.00 ne {

#version=${1:-1}
#label="[ 20140922 - paper - raw - copy $version ]"

file=${1:-label.ps}
label=${2:-"[ 20140922 - paper - raw - copy 1 ]"}

awk_filter='

    x==1 { 
        if ($1~/\[\([A-Z0-9]\)/) {
            xpos=$2
            ypos=$3+6
            $3=ypos
            if (y==1) {$4="6.5]";y=0}
        }
        else {
            x=0
            printf("[('$label') %1.2f %0.2f 6.5]\n",xpos - 63.75 - length("'$label'")*1.4,ypos-6)
        }
    }
    NF==5 && $1=="%" && $3=="xpos" {x=1;y=1;z+=1}
    1
'

awk "$awk_filter" $file
