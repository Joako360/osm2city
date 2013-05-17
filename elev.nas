var path_file = "/home/tom/daten/fgfs/src/fgdata/Nasal/elev.in";
var path_out = "/tmp/elev.xml";

var get = func {
  var raw_str = io.readfile(path_file);
  var raw_list = split("\n", raw_str);
  var file_out = io.open(path_out, "w");
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
  print(size(raw_list));
}
