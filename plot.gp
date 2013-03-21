load "~/pub.gp"
set output 'plot.eps'
set style line 1 lt 1 lw 1 pt 1 lc rgb "black"
dat="< cat small.dat | tr -d '[]'"
plot \
dat	u 1:2 noti 'plot'	w l ls 1
