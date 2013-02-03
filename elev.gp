#load "~/pub.gp"
#set output 'elev.eps'
#set style line 1 lt 1 lw 1 pt 1 lc rgb "black"
set term x11
splot \
'/tmp/elev.xml'	u 3:4:5 ti 'elev'	w pm3d

pause -1
