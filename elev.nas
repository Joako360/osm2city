var get_elevation = func {
#TODO read from property or build setup.py
  var in = "C:/Users/keith.paterson/AppData/Roaming/flightgear.org/elev.in";
  var out = "C:/Users/keith.paterson/AppData/Roaming/flightgear.org/Export/";

  var raw_str = io.readfile(in);
  var delimitter = "\r\n";
  print( "Reading File " ~ in);
  if (-1 == find(delimitter, raw_str)) delimitter = "\n";
  var raw_list = split(delimitter, raw_str);
  var allLines = size(raw_list);
  print("Read " ~ allLines ~ " records");
  var file_out = io.open(out ~ "elev.out", "w");
  foreach(var l; raw_list) {
     var l_list = split(" ", l);
     if (size(l_list) == 4) {
        var terrain_elev = geo.elevation(l_list[1], l_list[0]);
        var elev_str = sprintf("%.3f", (terrain_elev));
#        print( l_list[0] ~" "~ l_list[1] ~" "~ l_list[2] ~" "~ l_list[3] ~" "~ elev_str);
        io.write(file_out, l_list[0] ~" "~ l_list[1] ~" "~ l_list[2] ~" "~ l_list[3] ~" "~ elev_str ~"\n");
     } else {
#        print();
        io.write(file_out, l ~"\n");
     }
  }
  io.close(file_out);
  print("Wrote " ~ allLines ~ " records");
}

var get_threaded = func {
  thread.newthread(get_elevation);
}

# Make accessable from Telnet
addcommand("get-elevation", get_threaded);
