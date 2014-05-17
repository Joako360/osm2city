var get_elevation = func {
#Set via setup.py
  setprop("/osm2city/tiles", 0);
  var in = "WILL_BE_SET_BY_SETUP.PY";
  var out = "WILL_BE_SET_BY_SETUP.PY";

  print( "Checking if tile is loaded");
  
  var lat = getprop("/position/latitude-deg");
  var lon = getprop("/position/longitude-deg");
#  var info = geodinfo(lat, lon);
 
  print( "Position " ~ getprop("/position/latitude-deg") ~ " " ~ getprop("/position/longitude-deg") );
  
#  if (info != nil) {
#    print("the terrain under the aircraft is at elevation ", info[0], " m");
#    if (info[1] != nil)
#        print("and it is ", info[1].solid ? "solid ground" : "covered by water");
#  }
#  else {
#    print( "Info is nil! Tile not loaded." );
#  }  
  
  print( "Reading File " ~ in);

  var raw_str = io.readfile(in);
  var delimitter = "\r\n";
  var line = 0;
  print( "Splitting File " ~ in);
  if (-1 == find(delimitter, raw_str)) delimitter = "\n";
  var raw_list = split(delimitter, raw_str);
  raw_str = nil;
  var allLines = size(raw_list);
  print("Read " ~ allLines ~ " records");
  var file_out = io.open(out ~ "elev.out", "w");
  var header = subvec(raw_list, 0, 1);
  print("Writing " ~ allLines ~ " records");
  var record = 0;
  foreach(var l; raw_list) {
     line = line + 1;
     var l_list = split(" ", l);
     setprop("/osm2city/record", record);
     record = record + 1;
     if (size(l_list) == 4) {
        var terrain_elev = geo.elevation(l_list[1], l_list[0]);
        var elev_str = sprintf("%.3f", (terrain_elev));
#        print( l_list[0] ~" "~ l_list[1] ~" "~ l_list[2] ~" "~ l_list[3] ~" "~ elev_str);
        io.write(file_out, l_list[0] ~" "~ l_list[1] ~" "~ l_list[2] ~" "~ l_list[3] ~" "~ elev_str ~"\n");
     } else {
        io.write(file_out, l ~"\n");
     }
  }
#  io.write(file_out, "-- END -- ");
  io.close(file_out);
  print("Wrote " ~ allLines ~ " records");
  
  raw_list = nil;
  setprop("/osm2city/tiles", 1);
  print("Signalled Success");
}

var get_threaded = func {
  
  thread.newthread(get_elevation);
}

# Make accessible from Telnet
addcommand("get-elevation", get_threaded);
