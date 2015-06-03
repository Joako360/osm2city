#!BPY

"""
Name: 'Simger BTG'
Blender: 244
Group: 'Export'
Tooltip: 'Simgear BTG exporter'
"""

import Blender
import bpy
import time
from struct import pack

from Blender.BGL import *
from Blender.Draw import *

long_materials = {
  "RWY_WHT_MED_LGHT":"RWY_WHITE_MEDIUM_LIGHTS",
  "RWY_YEL_MED_LGHT":"RWY_YELLOW_MEDIUM_LIGHTS",
  "RWY_YEL_LOW_LIGHT":"RWY_YELLOW_LOW_LIGHTS",
  "RWY_RED_MED_LGHT":"RWY_RED_MEDIUM_LIGHTS",
  "RWY_GRN_MED_LGHT":"RWY_GREEN_MEDIUM_LIGHTS",
  "RWY_GRN_TXI_LGHT":"RWY_GREEN_TAXIWAY_LIGHTS",
  "RWY_BLU_TXI_LGHT":"RWY_BLUE_TAXIWAY_LIGHTS"
   }

path = None

sphereX = Create(0.0)
sphereY = Create(0.0)
sphereZ = Create(0.0)
sphereRad = Create(1.0)

tileLat = Create(0.0)
tileLon = Create(0.0)

def draw():
  global sphereX, sphereY, sphereZ, sphereRad, tileLat, tileLon

  glClear(GL_COLOR_BUFFER_BIT)

  glRasterPos2d(8, 270)
  Text("Export settings")

  glRasterPos2d(8, 250)
  Text("Bounding sphere")

  sphereX = Slider("X: ", 1, 8, 210, 210, 20, sphereX.val, -500000000, 500000000, 0, "Bounding sphere X")
  sphereY = Slider("Y: ", 1, 8, 185, 210, 20, sphereY.val, -500000000, 500000000, 0, "Bounding sphere Y")
  sphereZ = Slider("Z: ", 1, 8, 160, 210, 20, sphereZ.val, -500000000, 500000000, 0, "Bounding sphere Z")
  sphereRad = Slider("Radius: ", 1, 8, 135, 210, 20, sphereRad.val, 1, 500000000, 0, "Bounding sphere radius");

  # tileLat = Slider("Y: ", 1, 8, 185, 210, 20, sphereY.val, 0.0000001, 500000, 0, "Bounding sphere Y")
  # tileLon = Slider("Z: ", 1, 8, 160, 210, 20, sphereZ.val, 0.0000001, 500000, 0, "Bounding sphere Z")

  glRasterPos2d(8, 120)
  # Text("BTG Import settings")

  glRasterPos2d(8, 100)
  # self.rotateObject = Toggle("Rotate object if possible", 1, 10, 55, 210, 25, self.rotateObject.val)
  # self.importPoints = Toggle("Import points", 2, 10, 85, 210, 25, self.importPoints.val)

  Button("Export", 3, 10, 10, 80, 18)
  # Button("Exit", 4 , 140, 10, 80, 18)


def event(evt, val):
  if (evt== QKEY and not val):
    Exit()

def bevent(evt):
  global path

  if evt == 3:
    write_obj(path)
    print "Export done!"
    Exit()

  return


def write_obj(filepath):
  global sphereX, sphereY, sphereZ, sphereRad

  sce = bpy.data.scenes.active
  obs = sce.objects.context

  vertices = []
  texcoords = []
  facegroups = []
  materials = []
  normals = []
  points = {}

  counter = 0
  for ob in obs:
    counter = counter + 1
    print "Optimizing object", counter, "/", len(obs)

    if ob.getType() == "Mesh":
      mesh = ob.getData(mesh=1)
      data = {}

      if len(mesh.materials) > 0:
        mats = mesh.materials
      else: mats = None

#    for vert in mesh.verts:
#      vertices.append({"x":vert.co.x, "y":vert.co.y, "z":vert.co.z})

      faces = []
      uvs = []
      norms = []

      if len(mesh.faces) < 1: continue

      for face in mesh.faces:
        if len(face.v) <> 3: continue

        # Vertices of the face
        verts = []
        for vert in face.v:
          v = {"x":vert.co.x, "y":vert.co.y, "z":vert.co.z}

          # Push vertices if not in list (EXPERIMENTAL!)
          # Pushes only vertices that are in use!
          if not v in vertices:
            vertices.append(v)
            verts.append(len(vertices)-1)
          else:
            verts.append(vertices.index(v))

#          verts.append(vert.index)

        # Texture coordinates
        uv = []
        for u in face.uv:
          coord = { "u":u[0], "v":u[1] }
          if not coord in texcoords:
            texcoords.append(coord)
            uv.append(len(texcoords) - 1)
          else:
            uv.append(texcoords.index(coord))

        # Normals. I'm using face normals currently
        # I think it might give better results than using vertex normals?
        no = {"x":face.no[0], "y":face.no[1], "z":face.no[2]}
        if not no in normals:
          normals.append(no)
          norms.append(len(normals) - 1)
        else:
          norms.append(normals.index(no))

        faces.append(verts)
        uvs.append(uv)

      data["faces"] = faces
      data["uv"] = uvs
      data["normal"] = norms

      if mats:
        # Check the material name and remove all .001 and .002 etc from the end if there is
        matname = mats[0].getName()
        name = "Default"
        try:
          ind = matname.rindex(".")
          try:
            idx = int(matname[ind:])
          except:
            name = matname
          else:
            name = matname[:-4]
        except:
          name = matname

        if long_materials.has_key(name): name = long_materials[name]

        data["material"] = name
      else: data["material"] = "Default"

      facegroups.append(data)


    # Emptys, ie. runway lights ETC
    elif ob.getType() == "Lamp":
      loc = ob.getLocation()
      v = {"x":loc[0], "y":loc[1], "z":loc[2]}
      point = {}

      if not v in vertices:
        vertices.append(v)
        point["vert"] = len(vertices)-1
      else:
        point["vert"] = vertices.index(v)


      lamp = ob.getData()
      name = lamp.name

      try:
        idx = name.rindex(".")
        name = name[:idx]
      except:
        ""

      if long_materials.has_key(name): name = long_materials[name]

      point["name"] = name

      if points.has_key(name):
        points[name].append(point)
      else:
        points[name] = [point]

    else:
      print "Unknown object type", ob.getType(), "discarding..."

  # Bounding sphere, vertices list and triangle list and normal list and points list!
  objects = 4 + len(facegroups) + len(points)
  magic = 0x5347
  version = 7
  creation_time = time.clock()

  header = pack("<HHIH", version, magic, creation_time, objects)

  out = file(filepath, 'wb')
  out.write(header)


  # Bounding sphere!
  object = pack("<BHH", 0, 0, 1)
  out.write(object)
  element = pack("<I", 28)
  out.write(element)

  print "Bounding sphere, X:", sphereX.val, " Y:", sphereY.val, " Z:", sphereZ.val, " Rad:", sphereRad.val
  data = pack("<dddf", sphereX.val, sphereY.val, sphereZ.val, sphereRad.val)
  out.write(data)

  # Vertex List  ( 1 = Vertex List, 0 properties, 1 list of vertices)
  object = pack("<BHH", 1, 0, 1)
  out.write(object)

  element = pack("<I", len(vertices) * 3 * 4)  # 3 floats = 1 vertex
  out.write(element)

  print "verts:", len(vertices)

  for vertex in vertices:
    vertex = pack("<fff", vertex["x"] * 1000, vertex["y"] * 1000, vertex["z"]  *1000)
    out.write(vertex)


  # Normal List  ( 2 = Normal List, 0 properties, 1 list of vertices)
  object = pack("<BHH", 2, 0, 1)
  out.write(object)

  element = pack("<I", len(normals) * 3 * 1)  # 3 bytes = 1 vertex
  out.write(element)

  print "normals:", len(normals)

  for normal in normals:
    vertex = pack("<BBB", (normal["x"]+1)*127.5, (normal["y"]+1)*127.5, (normal["z"]+1)*127.5)
    out.write(vertex)


  # TexCoords List  ( 3 = Coords List, 0 properties, 1 list of vertices)
  object = pack("<BHH", 3, 0, 1)
  out.write(object)

  element = pack("<I", len(texcoords) * 2 * 4)  # 2 floats = 1 vertex
  out.write(element)

  print "texture coords:", len(texcoords)

  for uv in texcoords:
    vertex = pack("<ff", uv["u"], -uv["v"])
    out.write(vertex)


  # Points (1 property (the material), 1 element (list of vertices))
  for pname in points:
    point = points[pname]

    object = pack("<BHH", 9, 1, 1)
    out.write(object)

    print point[0]["name"]
    property = pack("<BI", 0, len(point[0]["name"]))    # Material property, bytes of data
    out.write(property)
    for char in point[0]["name"]:
      out.write(pack("c", char))		# Material name

    element = pack("<I", len(point) * 2)  # 1 short = 1 vertex
    out.write(element)

    for p in point:
      print p["vert"],
      vertex = pack("<H", p["vert"])
      out.write(vertex)

    print

  print "obs:", len(facegroups)

  for faces in facegroups:
    # Write faces as individual triangles (10 = ind. triangles, 2 props (atm), 1 face list (atm))
    object = pack("<BHH", 10, 2, 1)
    out.write(object)

    type = 0x01		# Vertex coords
    size = 2
    if faces.has_key("normal"): 
      type = type + 0x02	# Normal index
      size = size + 2
    if faces.has_key("uv"):
      type = type + 0x08  # texture index
      size = size + 2
    property = pack("<BIB", 1, 1, type)    # Index type property, 1 byte of data
    out.write(property)

    material = faces["material"]
    property = pack("<BI", 0, len(material))    # Material property, bytes of data
    out.write(property)
    for char in material:
      out.write(pack("c", char))		# Material name

    element = pack("<I", len(faces["faces"]) * 3 * size)  # 3 vertices/face, 1 short/vertex index
    out.write(element)

    print "fs:", len(faces["faces"])

    for n in range(0, len(faces["faces"])):
      face = faces["faces"][n]
      if faces.has_key("uv"): uv = faces["uv"][n]
      if faces.has_key("normal"): normal = faces["normal"][n]

      for f in range(0, 3):
        data = ""
        if type & 0x01: data = data + pack("<H", face[f])
        if type & 0x02: data = data + pack("<H", normal)	# Currently only 1 normal / face
        # if type & 0x04: data = data + pack("<H", face[f])
        if type & 0x08: data = data + pack("<H", uv[f])
        out.write(data)

  out.close()
  return


def export(path2):
  global path
  path = path2

  Register(draw, event, bevent)

if __name__=='__main__':
  Blender.Window.FileSelector(export, "Export BTG", '')

