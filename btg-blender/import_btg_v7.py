#!BPY

"""
Name: 'Simgear (.btg) v7...'
Blender: 244
Group: 'Import'
Tooltip: 'Load a Simgear BTG File, Shift: batch import all dir'
"""

__author__= "Lauri Peltonen a.k.a. Zan"
__version__= "0.7"

__bpydoc__ = """\
This script imports a Simgear BTG files to Blender.

Usage:
Run this script from "File->Import" menu and then load the desired BTG file.
Also gzipped BTG files are supported!

To see textures, you need to export FG_ROOT to point at the base directory
(the one which has materials.xml)
Also, you need to enable GLSL materials rendering, under Game -> Blender GLSL materials
"""

import Blender
import bpy
import gzip
import math
import os
import sys
from struct import unpack

HAS_XML = False
try:
  import xml.dom.minidom   # To read materials.xml
  HAS_XML = True
except:
  HAS_XML = False


from Blender.BGL import *
from Blender.Draw import *
from Blender import Texture
from Blender import Material

long_materials = {
  "RWY_WHITE_MEDIUM_LIGHTS":"RWY_WHT_MED_LGHT",
  "RWY_YELLOW_MEDIUM_LIGHTS":"RWY_YEL_MED_LGHT",
  "RWY_YELLOW_LOW_LIGHTS":"RWY_YEL_LOW_LIGHT",
  "RWY_RED_MEDIUM_LIGHTS":"RWY_RED_MED_LGHT",
  "RWY_GREEN_MEDIUM_LIGHTS":"RWY_GRN_MED_LGHT",
  "RWY_GREEN_TAXIWAY_LIGHTS":"RWY_GRN_TXI_LGHT",
  "RWY_BLUE_TAXIWAY_LIGHTS":"RWY_BLU_TXI_LGHT"
   }

BOUNDINGSPHERE = 0
VERTEXLIST = 1
NORMALLIST = 2
TEXTURECOORDLIST = 3
COLORLIST = 4
POINTS = 9
TRIANGLES = 10
TRIANGLESTRIPS = 11
TRIANGLEFANS = 12

MATERIAL = 0
INDEX = 1

VERTICES = 0x01
NORMALS = 0x02
COLORS = 0x04
TEXCOORDS = 0x08

# Textures etc
FG_ROOT = "/usr/local/share/flightgear/"
MaterialList = { }

# Import settings
importPointsVal = True
separateObjectsVal = True
rotateObjectsVal = True

class BTG:
  f = None
  mesh = None
  scn = None

  loadBatch = False

  name = ""
  base = ""
  index = 0

  x = 0
  y = 0
  lat = 0
  lon = 0
  center_lat = 0
  center_lon = 0
  has_coords = False

  boundingspheres = []
  points = []
  vertices = []
  normals = []
  texcoords = []
  colors = []

  faceidx = []
  normalidx = []
  texcoordidx = []
  coloridx = []

  objvertices = []

  nobjects = 0
  objects = []

  readers = []
  materials = []
  material = ""
  materialname = ""
  mesh_materials = 0

  faces = []

  rotateObject = Create(1)
  importPoints = Create(1)
  separateObjects = Create(1)
  wait = True

  def draw(self):
    glClear(GL_COLOR_BUFFER_BIT)

    glRasterPos2d(8, 220)
    Text("BTG file info, write these down for export!")
    glRasterPos2d(8, 205)
    Text("Tile location:")
    glRasterPos2d(8, 190)
    Text("Latitude: " + str(self.center_lat) + "  Longitude: " + str(self.center_lon))

    if len(self.boundingspheres) > 0:
      glRasterPos2d(8, 170)
      Text("Bounding sphere:")
      glRasterPos2d(8, 155)
      Text("X: " + str(self.boundingspheres[-1]["x"]) + " Y: " + str(self.boundingspheres[-1]["y"]) + " Z: " + str(self.boundingspheres[-1]["z"]) + " Radius: " + str(self.boundingspheres[-1]["radius"]))


    glRasterPos2d(8, 120)
    # Text("BTG Import settings")

    glRasterPos2d(8, 100)
    self.rotateObject = Toggle("Rotate object if possible", 1, 10, 55, 210, 25, self.rotateObject.val)
    self.importPoints = Toggle("Import points", 2, 10, 85, 210, 25, self.importPoints.val)
    self.separateObjects = Toggle("Materials as separate meshes", 4, 10, 115, 210, 25, self.separateObjects.val)

    # Button("Import", 3, 10, 10, 80, 18)
    Button("OK", 3, 10, 10, 80, 18)
    # Button("Exit", 4 , 140, 10, 80, 18)


  def event(self, evt, val):
    if (evt== QKEY and not val):
      self.wait = False
      Exit()

  def bevent(self, evt):
    # if evt == 4:
    #   die()
    if evt == 3:
      self.wait = False
      separateObjectsVal = self.separateObjects.val
      importPointsVal = self.importPoints.val
      rotateObjectsVal = self.rotateObject.val

      self.pushtoblender(separateObjectsVal, importPointsVal, rotateObjectsVal)

      Exit()

    return

# Helper functions

  # Returns the tile width in degrees on current latitude
  def span(self, lat):
    lat = abs(lat)
    if lat >= 89: return 360
    elif lat >= 88: return 8
    elif lat >= 86: return 4
    elif lat >= 83: return 2
    elif lat >= 76: return 1
    elif lat >= 62: return 0.5
    elif lat >= 22: return 0.25
    elif lat >= 0: return 0.125
    return 360

  # Convert cartesian coordinates to geoidic
  def cartToGeod(self, x, y, z):
    lon = math.atan2(y, x)
    lat = pi/2 - math.atan2(math.sqrt(x*x+y*y), z)
    rad = math.sqrt(x*x+y*y+z*z)
    return (lon, lat, rad)

  # Convert geoidic coordinates to cartesian
  def geodToCart(self, lon, lat, rad):
    lon = lon / 180.0 * math.pi
    lat = lat / 180.0 * math.pi
    x = math.cos(lon) * math.cos(lat) * rad
    y = math.sin(lon) * math.cos(lat) * rad
    z = math.sin(lat) * rad
    return (x, y, z)


  def read_vertex(self, data):
    (vertex, ) = unpack("<H", data)
    self.faceidx.append(vertex)
    return

  def read_normal(self, data):
    (normal, ) = unpack("<H", data)
    self.normalidx.append(normal)
    return

  def read_color(self, data):
    (color, ) = unpack("<H", data)
    self.coloridx.append(color)
    return

  def read_texcoord(self, data):
    (texcoord, ) = unpack("<H", data)
    self.texcoordidx.append(texcoord)
    return
  

  def parse_property(self, objtype, proptype, data):
    # Only geometry objects may have properties
    # and they have type >= 9 (POINTS)
    if objtype >= POINTS:
      if proptype == MATERIAL:
        # try:
        #   mat = Blender.Material.Get(data)
        # except:
        #  mat = Blender.Material.New(data)
        
        # self.mesh.materials += [mat]

        # Check and replace long names
        if data in long_materials:
          print "Long material name", data, "will be", long_materials[data]
          data = long_materials[data]

        if len(data) >= 21: print "Still too long material", data

        if not data in self.materials:
          self.materials.append(data)

        self.material = self.materials.index(data) + 1  # Make sure material is always > 0
        self.materialname = data

        if objtype <> POINTS: self.mesh_materials = self.mesh_materials + 1

      elif proptype == INDEX:	
        (idx, ) = unpack("B", data[:1])
        self.readers = []
        if idx & VERTICES: self.readers.append(self.read_vertex)
        if idx & NORMALS: self.readers.append(self.read_normal)
        if idx & COLORS: self.readers.append(self.read_color)
        if idx & TEXCOORDS: self.readers.append(self.read_texcoord)

        if objtype == POINTS:
          self.readers = [self.read_vertex]

        if len(self.readers) == 0:
          self.readers = [self.read_vertex, self.read_texcoord]
    return

  def add_face(self, n1, n2, n3):
    face = {}

    f = [0, 0, 0]
    f[0] = self.faceidx[n1]
    f[1] = self.faceidx[n2]
    f[2] = self.faceidx[n3]

    face["verts"] = f

    if self.material:
      face["material"] = [self.material - 1, self.materialname]

    if len(self.texcoordidx)>0:
      face["texcoord"] = [self.texcoordidx[n1], self.texcoordidx[n2], self.texcoordidx[n3]]

    if len(self.normalidx)>0:
      face["normal"] = [self.normalidx[n1], self.normalidx[n2], self.normalidx[n3]]

    if len(self.coloridx)>0:
      face["color"] = [self.coloridx[n1], self.coloridx[n2], self.coloridx[n3]]

    self.faces.append(face)

    return


  def add_blender_face(self, face, single_mesh=True):
    if not single_mesh:
      # If not in single mesh mode, we need to push vertices and materials too!
      # Need to optimize and save meshes vertices!
      v = [0, 0, 0]
      v[0] = self.vertices[face["verts"][0]]
      v[1] = self.vertices[face["verts"][1]]
      v[2] = self.vertices[face["verts"][2]]

      for n, ve in enumerate(v):
#        if not ve in self.objvertices:	# TODO: REMOVED THIS BECAUSE IT CAUSES WRONG VERTEX ORDER
          self.objvertices.append(ve)
          self.mesh.verts.extend([[ve["x"], ve["y"], ve["z"]]])
          face["verts"][n] = len(self.mesh.verts) - 1
#        else: 		# TODO: REMOVED THIS BECAUSE IT CAUSES WRONG VERTEX ORDER
#          face["verts"][n] = self.objvertices.index(ve)

    # Push face into blender, also normals, texture coordinates etc!
    self.mesh.faces.extend([self.mesh.verts[face["verts"][0]], self.mesh.verts[face["verts"][1]], self.mesh.verts[face["verts"][2]]])

    if not face.has_key("material"):
      face["material"] = [0, "Default"]


    # Add material to blender or reuse existing
    try:
      mat = Blender.Material.Get(face["material"][1])

      if not mat in self.mesh.materials:
        print "Adding material", mat
        self.mesh.materials += [mat]
        face["material"][0] = len(self.mesh.materials) - 1
      else:
        face["material"][0] = self.mesh.materials.index(mat)

    except:
      mat = Blender.Material.New(face["material"][1])

      # Add texture to the material
      if MaterialList.has_key(face["material"][1]):
        texturepath = MaterialList[face["material"][1]]
        if texturepath is not None:
          # Load texture
          texture = bpy.data.textures.new(face["material"][1]+"_texture")
          texture.setType('Image')

          try:
            texture.image = Blender.Image.Load(FG_ROOT + "Textures.High/" + texturepath)
          except:
            try:
              texture.image = Blender.Image.Load(FG_ROOT + "Textures/" + texturepath)
            except:
              print "Error loading texture " + texturepath
            else:
              mat.setTexture(0, texture, Texture.TexCo.UV, Texture.MapTo.COL)
          else:
            mat.setTexture(0, texture, Texture.TexCo.UV, Texture.MapTo.COL)


      print "Adding material", mat
      self.mesh.materials += [mat]
      face["material"][0] = len(self.mesh.materials) - 1

    if len(self.mesh.faces) > 0:
      self.mesh.faces[-1].mat = face["material"][0]

    if face.has_key("texcoord") and len(self.mesh.faces) > 0:
      uv1 = Blender.Mathutils.Vector(self.texcoords[face["texcoord"][0]]["x"], 1.0 - self.texcoords[face["texcoord"][0]]["y"])
      uv2 = Blender.Mathutils.Vector(self.texcoords[face["texcoord"][1]]["x"], 1.0 - self.texcoords[face["texcoord"][1]]["y"])
      uv3 = Blender.Mathutils.Vector(self.texcoords[face["texcoord"][2]]["x"], 1.0 - self.texcoords[face["texcoord"][2]]["y"])
      self.mesh.faces[-1].uv  = [uv1, uv2, uv3]

    if face.has_key("normal") and len(self.mesh.faces) > 0:
      no1 = Blender.Mathutils.Vector(self.normals[face["normal"][0]]["x"], self.normals[face["normal"][0]]["y"], self.normals[face["normal"][0]]["z"])
      no2 = Blender.Mathutils.Vector(self.normals[face["normal"][1]]["x"], self.normals[face["normal"][1]]["y"], self.normals[face["normal"][1]]["z"])
      no3 = Blender.Mathutils.Vector(self.normals[face["normal"][2]]["x"], self.normals[face["normal"][2]]["y"], self.normals[face["normal"][2]]["z"])
      # no = (no1 + no2 + no3) / 3.0            # Calculate the mean value of the 3 vectors
      # Set normals to vertexes instead of face?
      self.mesh.verts[face["verts"][0]].no = no1
      self.mesh.verts[face["verts"][1]].no = no2
      self.mesh.verts[face["verts"][2]].no = no3

    if face.has_key("color") and len(self.mesh.faces) > 0:
      co1 = Blender.Mesh.MCol()
      co1.r = self.colors[face["color"][0]]["red"]
      co1.g = self.colors[face["color"][0]]["green"]
      co1.b = self.colors[face["color"][0]]["blue"]
      co1.a = self.colors[face["color"][0]]["alpha"]
      self.mesh.faces[-1].col.extend([co1])

    return


  def parse_element(self, objtype, nbytes, data):
    if objtype == BOUNDINGSPHERE:
      (bs_x, bs_y, bs_z, bs_rad ) = unpack("<dddf", data[:28])
      self.boundingspheres.append({"x":bs_x, "y":bs_y, "z":bs_z, "radius":bs_rad})

    elif objtype == VERTEXLIST:
      for n in range(0, nbytes/12):	# One vertex is 12 bytes (3 * 4 bytes)
        (v_x, v_y, v_z) = unpack("<fff", data[n*12:(n+1)*12])
        self.vertices.append({"x":v_x/1000, "y":v_y/1000, "z":v_z/1000})


    elif objtype == NORMALLIST:
      for n in range(0, nbytes/3):	# One normal is 3 bytes ( 3 * 1 )
        (n_x, n_y, n_z) = unpack("BBB", data[n*3:(n+1)*3])
        self.normals.append({"x":n_x/127.5-1, "y":n_y/127.5-1, "z":n_z/127.5-1})

    elif objtype == TEXTURECOORDLIST:
      for n in range(0, nbytes/8):	# One texture coord is 8 bytes ( 2 * 4 )
        (t_x, t_y) = unpack("<ff", data[n*8:(n+1)*8])
        self.texcoords.append({"x":t_x, "y":1.0 - t_y})

    elif objtype == COLORLIST:
      for n in range(0, nbytes/16):	# Color is 16 bytes ( 4 * 4 )
        (r, g, b, a) = unpack("<ffff", data[n*16:(n+1)*16])
        self.colors.append({"red":r, "green":g, "blue":b, "alpha":a}) 
 
    else:
      # Geometry objects
      self.faceidx = []
      self.normalidx = []
      self.texcoordidx = []
      self.coloridx = []

      n = 0
      while n < nbytes:
        for reader in self.readers:
          reader(data[n:n+2])
          n = n + 2

      if not self.material: self.materialname = "Default"

      if objtype == POINTS:
        for face in self.faceidx:
          self.points.append([self.vertices[face]["x"], self.vertices[face]["y"], self.vertices[face]["z"], self.materialname])
        
      elif objtype == TRIANGLES:
        for n in range(0, len(self.faceidx)/3):
          #self.faces.append(3*n, 3*n+1, 3*n+2)
          self.add_face(3*n, 3*n+1, 3*n+2)

      elif objtype == TRIANGLESTRIPS:
        for n in range(0, len(self.faceidx)-2):
          if n % 2 == 0:
            self.add_face(n, n+1, n+2)
          else:
            self.add_face(n, n+2, n+1)

      elif objtype == TRIANGLEFANS:
        for n in range(1, len(self.faceidx)-1):
          self.add_face(0, n, n+1)

    return


  def read_objects(self, batch):
    self.loadBatch = batch

    for object in range(0, self.nobjects):
      # print "Importing object",object,"/",self.nobjects

      # Create a new mesh
      #print "Loading object", self.name + str(object)

      # Clear all variables for this object
      self.readers = [self.read_vertex, self.read_texcoord] 
      self.material = None
      self.objvertices = []

      # Object header
      try:
        obj_data = self.f.read(5)
      except:
        print "Error in file format (object header)"
        return

      (object_type, object_properties, object_elements) = unpack("<BHH", obj_data)

      # print "Properties", object_properties
      # Read properties
      for property in range(0, object_properties):
        try:
          prop_data = self.f.read(5)
        except:
          print "Error in file format (object properties)"
          return

        (property_type, databytes) = unpack("<BI", prop_data)

        try:
          data = self.f.read(databytes)
        except:
          print "Error in file format (property data)"
          return

        # Parse property if this is a geometry object
        self.parse_property(object_type, property_type, data)


      # print "Elements", object_elements
      # Read elements
      for element in range(0, object_elements):
        try:
          elem_data = self.f.read(4)
        except:
          print "Error in file format (object elements)"
          return

        (databytes, ) = unpack("<I", elem_data)

        # Read element data
        try:
          data = self.f.read(databytes)
        except:
          print "Error in file format (element data)"
          return

        # Parse element data
        self.parse_element(object_type, databytes, data)


    # Show options dialog, and wait until it's finished!
    # Pressing OK pushes objects to blender
    Register(self.draw, self.event, self.bevent) 
    return

  def pushtoblender(self, doImportSeparate, doImportPoints, doRotateObjects):

    self.scn = bpy.data.scenes.active

    if self.mesh_materials < 17 and doImportSeparate == False:
      print "Less than 17 materials, importing as one mesh"

      self.mesh = bpy.data.meshes.new(self.name)

      # Push vertices
      print "Adding vertices", len(self.vertices)
      self.objvertices = self.vertices  # Just to be sure...
      for vert in self.vertices:
        self.mesh.verts.extend([[vert["x"], vert["y"], vert["z"]]])

      # Materials are added in add_blender_face if necessary!

#      print "Adding materials", len(self.materials)
#      for mat in self.materials:
#        self.mesh.materials += [Blender.Material.New(mat)]

      # Push faces
      print "Adding faces", len(self.faces)
      for face in self.faces:
        self.add_blender_face(face)

      # Normals do not currently work from loading
      # So let's recalculate them.
      # self.mesh.calcNormals()

      # Add this object to scene
      ob = self.scn.objects.new(self.mesh, self.name)
      self.rotateobj(ob, doRotateObjects)  # Rotate object to upwards orientation if enabled

      print "All done!"

    else:  # separateObjectsVal = True or mesh_materials > 16
      if doImportSeparate == True: print "Loading materials as separate objects"
      else: print "Over 16 materials, all materials will be individual meshes", self.mesh_materials


      print "Addind faces / objects, this may take a while (be patient)!"
      used_materials = []
      for n, face in enumerate(self.faces):
        # print n, "/", len(self.faces)

        if not face.has_key("material"): face["material"] = [0, "Default"]

        if face["material"][1] in used_materials: continue
        else:
          current_material = face["material"][1]
          used_materials.append(current_material)
          # print current_material, len(used_materials)
          self.objvertices = []
          self.mesh = bpy.data.meshes.new(self.name)

          for f in range(n, len(self.faces)):
            if self.faces[f].has_key("material"):
              if self.faces[f]["material"][1] == current_material:
                self.add_blender_face(self.faces[f], False)

          ob = self.scn.objects.new(self.mesh, self.name)
          self.rotateobj(ob, doRotateObjects)  # Rotate object to upwards orientation if enabled

    # Push points
    if doImportPoints == True:
      print "Adding points", len(self.points)
      for point in self.points:
        # This was WAY too slow so not doing it right now!
        # Add points as "empty"s, this is quite stupid, but what is a better way?
        #ob = Blender.Object.New("Empty")
        #ob.setLocation(point[0], point[1], point[2])
        #ob.setName(point[3])
        #ob = self.scn.objects.new("Empty")
        #self.scn.link(ob)
        #self.rotateobj(ob, doRotateObjects)  # Rotate object to upwards orientation if enabled

        # TODO: Check if point has normal and add it too!

        # Too many lamps make rendering impossible, so just use emptys?
        object = Blender.Object.New('Lamp')
        lamp = Blender.Lamp.New('Lamp', point[3])
        #object.setLocation(point[0], point[1], point[2]) # Handled in rotatelamp
        object.link(lamp)
        self.scn.link(object)

        self.rotatelamp(object, doRotateObjects, [point[0], point[1], point[2]])  # Rotate object to upwards orientation if enabled

        # Need to set the normal for lamp too = lamp direction!


    # Push boundingspheres
    print "Adding bounding spheres", len(self.boundingspheres)
    print "Remember the last one for export!"
    for bs in self.boundingspheres:
      print bs


    # Normals do not currently work from loading
    # So let's recalculate them.
    # self.mesh.calcNormals()

    # Add this object to scene
    # ob = self.scn.objects.new(self.mesh, self.name)

    # If loading batch, rotate and place tiles correctly
#    if loadBatch:
      # self.rotateobj(ob, doRotateObjects, loadBatch)
    return


  def rotateobj(self, ob, doRotate, batch=False):
    # If rotating is enabled, rotate object to correct position
    if doRotate and self.has_coords:
      # print self.center_lon, self.center_lat
      ca = math.cos(self.center_lon/180.0*math.pi)
      sa = math.sin(self.center_lon/180.0*math.pi)
      cb = math.cos(-self.center_lat/180.0*math.pi)
      sb = math.sin(-self.center_lat/180.0*math.pi)

      if not batch:
        self.x = 0
        self.y = 0

      mat = Blender.Mathutils.Matrix([ca*cb, -sa, ca*sb, 0], [sa*cb, ca, sa*sb, 0], [-sb, 0, cb, 0], [0, self.x*22, self.y*14, 0])
      ob.setMatrix(mat)

  def rotatelamp(self, ob, doRotate, location, batch=False):
    # If rotating is enabled, rotate object to correct position
    if doRotate and self.has_coords:
      # print self.center_lon, self.center_lat
      ca = math.cos(self.center_lon/180.0*math.pi)
      sa = math.sin(self.center_lon/180.0*math.pi)
      cb = math.cos(-self.center_lat/180.0*math.pi)
      sb = math.sin(-self.center_lat/180.0*math.pi)

      if not batch:
        self.x = 0
        self.y = 0

      ob.setLocation(ca*cb*location[0]+sa*cb*location[1]-sb*location[2] + self.x*22, 
                     -sa*location[0]+ca*location[1] + self.y*14,
                     ca*sb*location[0]+sa*sb*location[1]+cb*location[2])
    else:
      ob.setLocation(location)


  def load(self, path, batch):
    self.name = path.split('\\')[-1].split('/')[-1]

    # parse the file
    try:
      # Check if the file is gzipped, if so -> use built in gzip
      if self.name[-7:].lower() == ".btg.gz":
        self.f = gzip.open(path, "rb")
        self.base = self.name[:-7]
      elif self.name[-4:].lower() == ".btg":
        self.f = open(path, "rb")
        self.base = self.name[:-4]
      else:
        return  # Not a btg file!
    except:
      print "Cannot open file", path
      return

    # Parse the coordinates from the filename, if possible
    try:
      self.index = int(self.base)
    except:
      print "Could not parse tile location from filename"
      if batch:
        return  # Tile can not be placed properly so discard it
    else:
      self.lon = self.index >> 14
      self.index = self.index - (self.lon << 14)
      self.lon = self.lon - 180

      self.lat = self.index >> 6
      self.index = self.index - (self.lat << 6)
      self.lat = self.lat - 90

      self.y = self.index >> 3
      self.index = self.index - (self.y << 3)
      self.x = self.index

      self.center_lat = self.lat + self.y / 8.0 + 0.0625
      self.center_lon = self.span(self.center_lat)
      if self.center_lon >= 1.0: self.center_lon = self.lon + self.center_lon / 2.0
      else: self.center_lon = self.lon + self.x * self.center_lon * self.center_lon / 2.0

      self.has_coords = True

      print "Tile location:"
      print "  Lat:", self.lat, " Lon:", self.lon
      print "  X:", self.x, " Y:", self.y
      print "  Tile span (width)", self.span(self.lat), " degrees"
      print "  Center:", self.center_lat, self.center_lon


    # Read file contents
    self.f.seek(0)

    # Read and unpack header
    try:
      header = self.f.read(8)
      nobjects_ushort = self.f.read(2)
    except:
      print "File in wrong format"
      return

    (version, magic, creation_time) = unpack("<HHI", header)

    if version >= 7:
      (self.nobjects, ) = unpack("<H", nobjects_ushort)
    else:
      (self.nobjects, ) = unpack("<h", nobjects_ushort)

    if not magic == 0x5347:
      print "Magic is not correct ('SG')"
      return

    # Read objects
    self.read_objects(batch)

    # Now it is loaded! Hoorrah!
    self.f.close()

    # Then just push everything to blender
    print "Done"

    return


  # Main loader
  def __init__(self, path, batch = False):
    Blender.Window.WaitCursor(1)
    editmode = Blender.Window.EditMode()    # are we in edit mode?  If so ...
    if editmode: Blender.Window.EditMode(0) # leave edit mode before getting the mesh

    if batch:
      try:
        files= [ f for f in os.listdir(path) if f.lower().endswith('.btg.gz') or f.lower().endswith('.btg')]
      except:
        Blender.Window.WaitCursor(0)
        Blender.Draw.PupMenu('Error%t|Could not open path ' + path)
        return

      if not files:
        Blender.Window.WaitCursor(0)
        Blender.Draw.PupMenu('Error%t|No files at path ' + path)
        return

      for f in files:
#        self.scn= bpy.data.scenes.new( f )
#        self.scn.makeCurrent()

        self.boundingspheres = []
        self.vertices = []
        self.normals = []
        self.texcoords = []
        self.colors = []

        self.load(path + f, True)

    else:
      self.load(path, False)


    if editmode: Blender.Window.EditMode(1)  # optional, just being nice
    Blender.Window.RedrawAll()

    return


def import_batch(path):
  BTG(path, True)
  return

def import_obj(path):
  BTG(path, False)
  return

if __name__=='__main__':
  # Find FG_ROOT
  fgroot = os.getenv("FG_ROOT")
  if fgroot is not None:
    FG_ROOT = fgroot

  # Find materials node if any
  if FG_ROOT is not None and HAS_XML:
    try:  # Try to load materials.xml
      matxml = xml.dom.minidom.parse(FG_ROOT + "materials.xml")

      proplist = matxml.getElementsByTagName("PropertyList")[0]

      if proplist is not None:
        mlist = matxml.getElementsByTagName("material")

        if mlist is not None:
          # Find the material's texture
          texturepath = None
          for e in mlist:
            for nameNode in e.getElementsByTagName("name"):
              for tname in nameNode.childNodes:
                if tname.nodeType == tname.TEXT_NODE:  # Name was found

                  for texNode in e.getElementsByTagName("texture"):
                    for tpath in texNode.childNodes:
                      if tpath.nodeType == tpath.TEXT_NODE:  # texture was found
                        MaterialList[tname.nodeValue] = tpath.nodeValue  # Store texture path
                   #     break

                  #break  # go for the next texture

    except:
      print "Could not load materials.xml"
      MaterialList = { }


  if Blender.Window.GetKeyQualifiers() & Blender.Window.Qual.SHIFT:
    Blender.Window.FileSelector(import_batch, 'Import BTG Dir', '')
  else:
    Blender.Window.FileSelector(import_obj, 'Import a Simgear BTG or BTG GZ', '*.btg,*.btg.gz')

#Blender.Window.FileSelector(import_obj, 'Import')
#  print "Import done"
