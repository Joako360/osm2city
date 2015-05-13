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


# nvDXT -nmips 10 -flip -file atlas_facades.png
#case=atlas_facades_LM
bd=$PWD
case=roads_LM
mkdir -p tmp/
cd tmp
cp $bd/tex/$case.png .
#nvDXT -nmips 10 -flip -file $case.png
#exit
#nvDXT -nomipmap -file ${case}_01.png 
nvDXT -nmips 10 -flip -file $case.png
detach $case
for i in `seq -w 0 8`; do
    is=`printf "%02i" $i`
    #(( bc = $i * 7 ))
    bc=`awk -v num=$i 'BEGIN{print 4*num^(1.3)}'`
    mip=${case}_$is
    convert $mip.dds -brightness-contrast ${bc}x${bc} $mip.png
    rm $mip.dds
    nvDXT -nomipmap -file $mip.png
    ls -l $mip.dds
done
stitch $case
mv $case.dds $bd/tex/
