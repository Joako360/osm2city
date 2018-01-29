"""
This module allows to read SimGear BTG-files from existing TerraSync scenery files into a Python object model.
IT only reads plain data for specific land-uses. All not needed data is discarded. Writing is not supported.
See http://wiki.flightgear.org/Blender_and_BTG and http://wiki.flightgear.org/BTG_file_format

Partially based on https://sourceforge.net/p/flightgear/fgscenery/tools/ci/master/tree/Blender/import_btg_v7.py
by Lauri Peltonen a.k.a. Zan

Materials actually read (see also http://wiki.flightgear.org/CORINE_to_materials_mapping):
  <name>BuiltUpCover</name>
  <name>Urban</name>

  <name>Construction</name>
  <name>Industrial</name>
  <name>Port</name>

  <name>Town</name>
  <name>SubUrban</name>

Materials for different water types are also saved in order to exclude land-use.

Fans and strips do not seem to be used for the supported materials. Therefore no attempt is done to
save faces of a given fan or stripe in a separate structure instead of together with other triangles.

"""

import gzip
import logging
import math
import struct
from typing import List

import utils.coordinates as coord

WATER_PROXY = 'water'

SUPPORTED_MATERIALS = ['builtupcover', 'urban',
                       'construction', 'industrial', 'port',
                       'town', 'suburban',
                       WATER_PROXY]
WATER_MATERIALS = ['ocean', 'lake', 'pond', 'reservoir', 'stream', 'canal',
                   'lagoon', 'estuary', 'watercourse', 'saline']

OBJECT_TYPE_BOUNDING_SPHERE = 0
OBJECT_TYPE_VERTEX_LIST = 1
OBJECT_TYPE_NORMAL_LIST = 2
OBJECT_TYPE_TEXTURE_COORD_LIST = 3
OBJECT_TYPE_COLOR_LIST = 4

OBJECT_TYPE_POINTS = 9
OBJECT_TYPE_TRIANGLES = 10
OBJECT_TYPE_TRIANGLE_STRIPS = 11
OBJECT_TYPE_TRIANGLE_FANS = 12

INDEX_TYPE_VERTICES = 0x01
INDEX_TYPE_NORMALS = 0x02
INDEX_TYPE_COLORS = 0x04
INDEX_TYPE_TEX_COORDS = 0x08

PROPERTY_TYPE_MATERIAL = 0
PROPERTY_TYPE_INDEX = 1


class BoundingSphere(object):
    """Corresponds kind of to simgear/io/sg_binobj.hxx ->
    SGVec3d gbs_center;
    float gbs_radius;
    """
    __slots__ = ('center', 'radius')

    def __init__(self, x: float, y: float, z: float, radius: float) -> None:
        self.center = coord.Vec3d(x, y, z)
        self.radius = radius


class Face(object):
    __slots__ = ('material', 'vertices')

    def __init__(self, material: bytes, vertices: List[int]) -> None:
        self.material = material.decode(encoding='ascii')
        self.vertices = vertices


class BTGReader(object):
    """Corresponds loosely to SGBinObject in simgear/io/sg_binobj.cxx"""
    __slots__ = ('bounding_sphere', 'faces', 'readers', 'material_name', 'vertex_idx', 'vertices')

    def __init__(self, path: str) -> None:
        self.vertex_idx = None  # The x, y, z vertex indices of the current element
        self.vertices = list()  # corresponds to wgs84_nodes in simgear/io/sg_binobj.hxx
        self.bounding_sphere = None
        self.readers = list()  # list of method names - reader methods are called by introspection
        self.faces = list()
        self.material_name = None  # byte string

        # run the loader
        self.load(path)

    @property
    def gbs_center(self) -> coord.Vec3d:
        return self.bounding_sphere.center

    def create_face(self, n1: int, n2: int, n3: int) -> Face:
        vertices = [0, 0, 0]
        vertices[0] = self.vertex_idx[n1]
        vertices[1] = self.vertex_idx[n2]
        vertices[2] = self.vertex_idx[n3]

        return Face(self.material_name, vertices)

    def add_face(self, face: Face) -> None:
        """Adds a face if it is one of the supported material types"""
        if face.material.lower() in SUPPORTED_MATERIALS:
            self.faces.append(face)

    def read_vertex(self, data: bytes) -> None:
        (vertex,) = struct.unpack("<H", data)
        self.vertex_idx.append(vertex)

    def read_discard(self, data: bytes) -> None:
        """Just reads the data and discards it -> need to read until next"""
        struct.unpack("<H", data)

    def parse_property(self, object_type: int, property_type: int, data: bytes) -> None:
        """Only geometry objects may have properties and they are a sort of triangle type"""
        if object_type in [OBJECT_TYPE_TRIANGLES, OBJECT_TYPE_TRIANGLE_STRIPS, OBJECT_TYPE_TRIANGLE_FANS]:
            if property_type == PROPERTY_TYPE_MATERIAL:
                if data in WATER_MATERIALS:
                    self.material_name = WATER_PROXY
                else:
                    self.material_name = data

            elif property_type == PROPERTY_TYPE_INDEX:
                (idx,) = struct.unpack("B", data[:1])
                self.readers = []
                if idx & INDEX_TYPE_VERTICES:
                    self.readers.append(self.read_vertex)
                if idx & INDEX_TYPE_NORMALS:
                    self.readers.append(self.read_discard)
                if idx & INDEX_TYPE_COLORS:
                    self.readers.append(self.read_discard)
                if idx & INDEX_TYPE_TEX_COORDS:
                    self.readers.append(self.read_discard)

                if len(self.readers) == 0:  # should never happen
                    self.readers = [self.read_vertex, self.read_discard]

    def parse_element(self, object_type: int, number_bytes: int, data: bytes) -> None:
        if object_type == OBJECT_TYPE_BOUNDING_SPHERE:
            (bs_x, bs_y, bs_z, bs_radius) = struct.unpack("<dddf", data[:28])
            # there can be more than one bounding sphere, but only the last one is kept
            self.bounding_sphere = BoundingSphere(bs_x, bs_y, bs_z, bs_radius)

        elif object_type == OBJECT_TYPE_VERTEX_LIST:
            for n in range(0, number_bytes // 12):  # One vertex is 12 bytes (3 * 4 bytes)
                (v_x, v_y, v_z) = struct.unpack("<fff", data[n * 12:(n + 1) * 12])
                self.vertices.append(coord.Vec3d(v_x / 1000, v_y / 1000, v_z / 1000))

        elif object_type == OBJECT_TYPE_NORMAL_LIST:
            for n in range(0, number_bytes // 3):  # One normal is 3 bytes ( 3 * 1 )
                struct.unpack("BBB", data[n * 3:(n + 1) * 3])  # read and discard

        elif object_type == OBJECT_TYPE_TEXTURE_COORD_LIST:
            for n in range(0, number_bytes // 8):  # One texture coord is 8 bytes ( 2 * 4 )
                struct.unpack("<ff", data[n * 8:(n + 1) * 8])  # read and discard

        elif object_type == OBJECT_TYPE_COLOR_LIST:
            for n in range(0, number_bytes // 16):  # Color is 16 bytes ( 4 * 4 )
                struct.unpack("<ffff", data[n * 16:(n + 1) * 16])  # read and discard

        else:  # Geometry objects
            self.vertex_idx = []

            n = 0
            while n < number_bytes:
                for reader in self.readers:
                    reader(data[n:n + 2])
                    n = n + 2

            if object_type == OBJECT_TYPE_TRIANGLES:
                for n in range(0, len(self.vertex_idx) // 3):
                    face = self.create_face(3 * n, 3 * n + 1, 3 * n + 2)
                    self.add_face(face)

            elif object_type == OBJECT_TYPE_TRIANGLE_STRIPS:
                for n in range(0, len(self.vertex_idx) - 2):
                    if n % 2 == 0:
                        face = self.create_face(n, n + 1, n + 2)
                    else:
                        face = self.create_face(n, n + 2, n + 1)
                    self.add_face(face)

            elif object_type == OBJECT_TYPE_TRIANGLE_FANS:
                for n in range(1, len(self.vertex_idx) - 1):
                    face = self.create_face(0, n, n + 1)
                    self.add_face(face)

    def read_objects(self, btg_file, number_objects: int) -> bool:
        """Reads all top level objects"""
        for my_object in range(0, number_objects):
            self.readers = [self.read_vertex, self.read_discard]

            # Object header
            try:
                obj_data = btg_file.read(5)
            except IOError:
                logging.error('Error in file format (object header)')
                return False

            (object_type, object_properties, object_elements) = struct.unpack("<BHH", obj_data)

            # print "Properties", object_properties
            # Read properties
            for a_property in range(0, object_properties):
                try:
                    prop_data = btg_file.read(5)
                except IOError:
                    logging.error('Error in file format (object properties)')
                    return False

                (property_type, data_bytes) = struct.unpack("<BI", prop_data)

                try:
                    data = btg_file.read(data_bytes)
                except IOError:
                    logging.error('Error in file format (property data)')
                    return False

                # Parse property if this is a geometry object
                self.parse_property(object_type, property_type, data)

            # print "Elements", object_elements
            # Read elements
            for element in range(0, object_elements):
                try:
                    elem_data = btg_file.read(4)
                except IOError:
                    logging.error('Error in file format (object elements)')
                    return False

                (databytes,) = struct.unpack("<I", elem_data)

                # Read element data
                try:
                    data = btg_file.read(databytes)
                except IOError:
                    logging.error('Error in file format (element data)')
                    return False

                # Parse element data
                self.parse_element(object_type, databytes, data)
        return True

    def load(self, path: str) -> bool:
        """Loads a btg-files and starts reading up to the point, where objects are read"""
        file_name = path.split('\\')[-1].split('/')[-1]

        # parse the file
        try:
            # Check if the file is gzipped, if so -> use built in gzip
            if file_name[-7:].lower() == ".btg.gz":
                btg_file = gzip.open(path, "rb")
                tile_name = file_name[:-7]
            elif file_name[-4:].lower() == ".btg":
                btg_file = open(path, "rb")
                tile_name = file_name[:-4]
            else:
                logging.error('Not a .btg og .btg.gz file')
                return False  # Not a btg file!
        except IOError:
            logging.error('Cannot open file %s', path)
            return False

        # Read file contents
        btg_file.seek(0)

        # Read and unpack header
        try:
            header = btg_file.read(8)
            number_objects_ushort = btg_file.read(2)
        except IOError:
            logging.error('File in wrong format')
            return False

        (version, magic, creation_time) = struct.unpack("<HHI", header)

        if version < 7:
            logging.error('The BTG version must be 7 or higher')
            return False
        (number_top_level_objects,) = struct.unpack("<h", number_objects_ushort)

        if not magic == 0x5347:
            logging.error("Magic is not correct ('SG'): %s instead of 0x5347", magic)
            return False

        # Read objects
        self.read_objects(btg_file, number_top_level_objects)
        btg_file.close()

        logging.info('Parsed %i vertices and found %i faces.', len(self.vertices), len(self.faces))
        materials_names = set()
        for face in self.faces:
            materials_names.add(face.material)
        for name in materials_names:
            logging.info(name)
        return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    reader = BTGReader('/home/vanosten/bin/terrasync/Terrain/e000n40/e008n47/3088962.btg.gz')
    lon_rad, lat_rad, elev = coord.cart_to_geod(reader.gbs_center)
    quaternion_first = coord.quaternion_from_lon_lat_radian(lon_rad, lat_rad)
    quaternion_other = coord.quaternion_from_euler_radian(0.0, 0.0, math.pi)
    hlOr = coord.Quaternion.multiply(quaternion_first, quaternion_other)
    coord.transform_to_rotated_coordinate_frame(hlOr, reader.vertices)
    logging.info("Done")
