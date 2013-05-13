get huge data from OSM:
http://wiki.openstreetmap.org/wiki/Overpass_API/XAPI_Compatibility_Layer

XAPI URL Builder: A GUI for BBox
http://harrywood.co.uk/maps/uixapi/xapi.html
builds something like
www.overpass-api.de/api/xapi?map?bbox=13.63,50.96,13.88,51.17
EDDC www.overpass-api.de/api/xapi?*[building=*][bbox=13.63,50.96,13.88,51.17]
LOWI www.overpass-api.de/api/xapi?*[building=*][bbox=11.16898,47.20837,11.79108,47.38161]

with LOD
tile
size	fps
200	13
500	15
1000	15
2000	15

w/o LOD
6 fps

no roofs at all: 17-18fps
---
Any significant gains with one texture only? Or skipping pitched roofs (putting them in separate LOD later)?
==> one texture only +1 fps
==> no pitched roofs +4 fps

benchmark LOWI

airport="LOWI --offset-azimuth=260 --heading=265 --offset-distance=4.0 --in-air --altitude=3000"
aircraft=ufo

base
  13-14 fps

total buildings 50000
written         34514
skipped
  small         15334
  nearby        136
  texture       0
vertices        546782
surfaces        307415
LOD bare        10612 (31)
LOD rough       23902 (69)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2   1353
    50 m^2   2994
   100 m^2   8032
   200 m^2  17667
   500 m^2   2726
  1000 m^2    831
  2000 m^2    342
  5000 m^2     61
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.
---
with  
  b.roof_flat = True
  b.roof_separate = False
  17-18 fps
  
total buildings 50000
written         34410
skipped
  small         15440
  nearby        135
  texture       0
vertices        463682
surfaces        265768
LOD bare        10670 (31)
LOD rough       23740 (69)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2   1382
    50 m^2   2891
   100 m^2   7991
   200 m^2  17679
   500 m^2   2731
  1000 m^2    831
  2000 m^2    342
  5000 m^2     62
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.
--
b.roof_flat = True
b.roof_separate = False
one texture only
18-19fps

total buildings 50000
written         34564
skipped
  small         15282
  nearby        137
  texture       0
vertices        466414
surfaces        267317
LOD bare        10588 (31)
LOD rough       23976 (69)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2   1361
    50 m^2   2964
   100 m^2   8122
   200 m^2  17686
   500 m^2   2724
  1000 m^2    832
  2000 m^2    342
  5000 m^2     61
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.
---
pitched roofs allowed (untextured), but one texture only
14 fps

total buildings 50000
written         34514
skipped
  small         15334
  nearby        135
  texture       0
vertices        546968
surfaces        307515
LOD bare        10653 (31)
LOD rough       23861 (69)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2   1380
    50 m^2   2891
   100 m^2   8097
   200 m^2  17680
   500 m^2   2732
  1000 m^2    828
  2000 m^2    343
  5000 m^2     62
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0

 
simplify or not
---------------
LOWI benchmark
LOD 3000 7000 20000
threshold 0.00000000001
11-12fps

total buildings 50000
written         33053
skipped
  small         16817
  nearby        116
  texture       0
pitched roof    12593
ground nodes    316079
  simplified    50
vertices        527480
surfaces        296351
LOD bare        10660 (32)
LOD rough       22393 (68)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2      0
    50 m^2   2851
   100 m^2   8108
   200 m^2  17677
   500 m^2   2726
  1000 m^2    827
  2000 m^2    342
  5000 m^2     62
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.

--
threshold 0.1
11-12fps

total buildings 50000
written         32992
skipped
  small         16881
  nearby        111
  texture       0
pitched roof    14957
ground nodes    303204
  simplified    12925
vertices        521838
surfaces        293440
LOD bare        10647 (32)
LOD rough       22345 (68)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2      0
    50 m^2   2854
   100 m^2   8044
   200 m^2  17642
   500 m^2   2728
  1000 m^2    831
  2000 m^2    342
  5000 m^2     62
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.

--
threshold 0.5
11-12fps

total buildings 50000
written         33134
skipped
  small         16737
  nearby        114
  texture       0
pitched roof    15510
ground nodes    296201
  simplified    19928
vertices        515658
surfaces        290488
LOD bare        10600 (32)
LOD rough       22534 (68)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2      0
    50 m^2   2925
   100 m^2   8106
   200 m^2  17655
   500 m^2   2720
  1000 m^2    832
  2000 m^2    342
  5000 m^2     61
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.

---
threshold 1.0
11-12fps

total buildings 50000
written         33201
skipped
  small         16667
  nearby        118
  texture       0
pitched roof    16733
ground nodes    276576
  simplified    39553
vertices        493500
surfaces        279489
LOD bare        10757 (32)
LOD rough       22444 (68)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2      0
    50 m^2   2965
   100 m^2   8163
   200 m^2  17629
   500 m^2   2729
  1000 m^2    829
  2000 m^2    344
  5000 m^2     62
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.
---
threshold 2.0
10-11fps (??)
total buildings 50000
written         32854
skipped
  small         17023
  nearby        107
  texture       0
pitched roof    20142
ground nodes    242729
  simplified    73400
vertices        455698
surfaces        260227
LOD bare        10460 (32)
LOD rough       22394 (68)
LOD detail      0 ( 0)
above
     1 m^2      0
    10 m^2      0
    20 m^2      0
    50 m^2   2983
   100 m^2   7983
   200 m^2  17448
   500 m^2   2714
  1000 m^2    828
  2000 m^2    342
  5000 m^2     62
 10000 m^2     15
 20000 m^2      3
 50000 m^2      0
done.
