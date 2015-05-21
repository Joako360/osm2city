#!/bin/bash

PROG=genmips.sh
USAGE="$PROG file"
DESC="<One line of description>"
HELP="<Zero or more lines of Help>"
AUTHOR="Thomas Albrecht"

# [ "$1" == "" ] || [ "$1" == "-h" ] || [ "$1" == "--help" ] && \
#     echo -e "Usage: $USAGE\n$DESC\n$HELP" && exit 1

set -u

# Here follows your own code
NV=/home/tom/.wine/drive_c/Programme/DDS_Utilities
stitch ()
{
    wine $NV/stitch.exe $*
}
nvDXT ()
{
    wine $NV/nvDXT.exe $*
}
detach ()
{
    wine $NV/detach.exe $*
}

genmips ()
{
    # nvDXT -nmips 10 -flip -file atlas_facades.png
    bd=$PWD
    case=$1
    bf=$2
    be=$3
    cf=$4
    ce=$5
    mkdir -p tmp/
    cd tmp
    cp $bd/tex/$case.png .
    #nvDXT -nmips 10 -flip -file $case.png
    #exit
    #nvDXT -nomipmap -file ${case}_01.png 
    nvDXT -nmips 10 -flip -sharpenMethod SharpenMedium -file $case.png
    detach $case
    for i in `seq -w 0 8`; do
        is=`printf "%02i" $i`
        #(( bc = $i * 7 ))
        br=`awk -v num=$i 'BEGIN{print '$bf'*num^('$be')}'`
        co=`awk -v num=$i 'BEGIN{print '$cf'*num^('$ce')}'`
        echo "br=$br co=$co"
        mip=${case}_$is
        convert $mip.dds -brightness-contrast ${br}x${co} $mip.png
        rm $mip.dds
        nvDXT -nomipmap -file $mip.png
        ls -l $mip.dds
    done
    stitch $case
    mv $case.dds $bd/tex/
    cd ..
}

gendds ()
{
    for i in `seq -w 0 08`; do
        mip=${case}_$i
        nvDXT -nomipmap -file $mip.png
    done
}

genmips atlas_facades_LM 2. 1.7 7. 1.

#genmips roads_LM 2 1.5 1 1.5
genmips roads_LM 1 1. 1 1.
exit
bd=$PWD
cd tmp
case=roads_LM
gendds $case
stitch $case
mv $case.dds $bd/tex/
exit


#genmips atlas_facades_LM 1.2 1.7 7. 1.
