"""
This module allows to read SimGear BTG-files from existing TerraSync scenery files into a Python object model.
IT only reads plain data for specific land-uses. All not needed data is discarded. Writing is not supported.
See http://wiki.flightgear.org/Blender_and_BTG and http://wiki.flightgear.org/BTG_file_format

Partially based on https://sourceforge.net/p/flightgear/fgscenery/tools/ci/master/tree/Blender/import_btg_v7.py
by Lauri Peltonen a.k.a. Zan
Updated based on information in https://sourceforge.net/projects/xdraconian-fgscenery/
and https://forum.flightgear.org/viewtopic.php?f=5&t=34736,
especially FGBlenderTools/io_scene_flightgear/verticesfg_btg_io.py
Materials interpreted as urban (see also http://wiki.flightgear.org/CORINE_to_materials_mapping):
  <name>BuiltUpCover</name>
  <name>Urban</name>

  <name>Construction</name>
  <name>Industrial</name>
  <name>Port</name>

  <name>Town</name>
  <name>SubUrban</name>

Materials for different water types are saved as a proxy "water" material in order to exclude land-use.

Fans and strips do not seem to be used for the supported materials. Therefore no attempt is done to
save faces of a given fan or stripe in a separate structure instead of together with other triangles.

"""

import gzip
import logging
import math
import struct
from typing import List, Tuple

import utils.calc_tile as ca
import utils.coordinates as coord
from utils.exceptions import MyException

# materials get set to lower in reading BTG files
WATER_PROXY = 'water'

URBAN_MATERIALS = ['builtupcover', 'urban',
                   'construction', 'industrial', 'port',
                   'town', 'suburban']

TRANSPORT_MATERIALS = ['freeway', 'road', 'railroad', 'transport', 'asphalt']

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
        self.material = material.decode(encoding='ascii').lower()
        self.vertices = vertices


class BTGReader(object):
    """Corresponds loosely to SGBinObject in simgear/io/sg_binobj.cxx"""
    __slots__ = ('bounding_sphere', 'faces', 'material_name', 'vertices', 'btg_version')

    def __init__(self, path: str) -> None:
        self.vertices = list()  # corresponds to wgs84_nodes in simgear/io/sg_binobj.hxx. List of Vec3d objects
        self.bounding_sphere = None
        self.faces = dict()  # material: str, list of faces
        self.material_name = None  # byte string

        self.btg_version = 0

        # run the loader
        self._load(path)
        self._clean_data()

    @property
    def is_version_7(self) -> bool:
        return self.btg_version == 7

    @property
    def gbs_center(self) -> coord.Vec3d:
        return self.bounding_sphere.center

    @property
    def gbs_lon_lat(self) -> Tuple[float, float]:
        lon_rad, lat_rad, elev = coord.cart_to_geod(self.gbs_center)
        lon_deg = math.degrees(lon_rad)
        lat_deg = math.degrees(lat_rad)
        return lon_deg, lat_deg

    def add_face(self, face: Face) -> None:
        if face.material not in self.faces:
            self.faces[face.material] = list()
        self.faces[face.material].append(face)

    def parse_element(self, object_type: int, number_bytes: int, data: bytes) -> None:
        if object_type == OBJECT_TYPE_BOUNDING_SPHERE:
            (bs_x, bs_y, bs_z, bs_radius) = struct.unpack("<dddf", data[:28])
            # there can be more than one bounding sphere, but only the last one is kept
            self.bounding_sphere = BoundingSphere(bs_x, bs_y, bs_z, bs_radius)

        elif object_type == OBJECT_TYPE_VERTEX_LIST:
            for n in range(0, number_bytes // 12):  # One vertex is 12 bytes (3 * 4 bytes)
                (v_x, v_y, v_z) = struct.unpack("<fff", data[n * 12:(n + 1) * 12])
                self.vertices.append(coord.Vec3d(v_x, v_y, v_z))  # in import_btg_v7.py all 3 values divided by 1000

        elif object_type == OBJECT_TYPE_NORMAL_LIST:
            for n in range(0, number_bytes // 3):  # One normal is 3 bytes ( 3 * 1 )
                struct.unpack("<BBB", data[n * 3:(n + 1) * 3])  # read and discard

        elif object_type == OBJECT_TYPE_TEXTURE_COORD_LIST:
            for n in range(0, number_bytes // 8):  # One texture coord is 8 bytes ( 2 * 4 )
                struct.unpack("<ff", data[n * 8:(n + 1) * 8])  # read and discard

        elif object_type == OBJECT_TYPE_COLOR_LIST:
            for n in range(0, number_bytes // 16):  # Color is 16 bytes ( 4 * 4 )
                struct.unpack("<ffff", data[n * 16:(n + 1) * 16])  # read and discard

    def parse_geometry(self, object_type: int, number_bytes: int, btg_file,
                       has_vertices: bool, has_normals: bool, has_colors: bool, has_tex_coords: bool) -> None:
        if has_vertices is False:
            has_vertices = True
            if object_type != OBJECT_TYPE_POINTS:
                has_tex_coords = True

        entry_format = '<H' if self.is_version_7 else '<I'
        entry_size = struct.calcsize(entry_format)
        chunck_size = 0
        if has_vertices:
            chunck_size = chunck_size + entry_size
        if has_normals:
            chunck_size = chunck_size + entry_size
        if has_colors:
            chunck_size = chunck_size + entry_size
        if has_tex_coords:
            chunck_size = chunck_size + entry_size

        length = int(number_bytes / chunck_size)

        geom_verts = list()
        remaining_bytes = number_bytes
        while remaining_bytes != 0:
            if has_vertices:
                raw = btg_file.read(entry_size)
                data = struct.unpack(entry_format, raw)
                geom_verts.append(data[0])
                remaining_bytes = remaining_bytes - entry_size

            if has_normals:
                raw = btg_file.read(entry_size)
                _ = struct.unpack(entry_format, raw)
                remaining_bytes = remaining_bytes - entry_size

            if has_colors:
                raw = btg_file.read(entry_size)
                _ = struct.unpack(entry_format, raw)
                remaining_bytes = remaining_bytes - entry_size

            if has_tex_coords:
                raw = btg_file.read(entry_size)
                _ = struct.unpack(entry_format, raw)
                remaining_bytes = remaining_bytes - entry_size

        if object_type == OBJECT_TYPE_TRIANGLES:
            for n in range(0, len(geom_verts) // 3):
                face = Face(self.material_name, [geom_verts[3 * n], geom_verts[3 * n + 1], geom_verts[3 * n + 2]])
                self.add_face(face)
        else:
            logging.warning('Not used object data for type = %i', object_type)

    def read_objects(self, btg_file, number_objects: int, object_fmt: str) -> None:
        """Reads all top level objects"""
        for my_object in range(0, number_objects):
            # Object header
            try:
                obj_data = btg_file.read(struct.calcsize(object_fmt))
            except IOError as e:
                raise MyException('Error in file format (object header)') from e

            (object_type, object_properties, object_elements) = struct.unpack(object_fmt, obj_data)

            # Read properties
            has_vertices = False
            has_normals = False
            has_colors = False
            has_tex_coords = False

            property_fmt = "<BI"
            for a_property in range(0, object_properties):
                try:
                    prop_data = btg_file.read(struct.calcsize(property_fmt))
                except IOError as e:
                    raise MyException('Error in file format (object properties)') from e

                (property_type, data_bytes) = struct.unpack(property_fmt, prop_data)

                try:
                    data = btg_file.read(data_bytes)
                except IOError as e:
                    raise MyException('Error in file format (property data)') from e

                # Materials
                if property_type == PROPERTY_TYPE_MATERIAL:
                    if data in WATER_MATERIALS:
                        self.material_name = WATER_PROXY
                    else:
                        self.material_name = data
                    logging.debug('Material name "%s"', self.material_name)

                elif property_type == PROPERTY_TYPE_INDEX:
                    (_,) = struct.unpack("<B", data[:1])
                    has_vertices = (data[0]) & 1 == 1
                    has_normals = (data[0]) & 2 == 2
                    has_colors = (data[0] & 4) == 4
                    has_tex_coords = (data[0] & 8) == 8

            # Read elements
            element_fmt = '<I'
            for element in range(0, object_elements):
                try:
                    elem_data = btg_file.read(struct.calcsize(element_fmt))
                except IOError as e:
                    raise MyException('Error in file format (object elements)') from e

                (data_bytes,) = struct.unpack(element_fmt, elem_data)

                # Read element data
                try:
                    if object_type in [OBJECT_TYPE_BOUNDING_SPHERE, OBJECT_TYPE_VERTEX_LIST, OBJECT_TYPE_NORMAL_LIST,
                                       OBJECT_TYPE_TEXTURE_COORD_LIST, OBJECT_TYPE_COLOR_LIST]:
                        data = btg_file.read(data_bytes)
                        self.parse_element(object_type, data_bytes, data)
                    else:
                        self.parse_geometry(object_type, data_bytes, btg_file,
                                            has_vertices, has_normals, has_colors, has_tex_coords)
                except IOError as e:
                    raise MyException('Error in file format (element data)') from e

    def _load(self, path: str) -> None:
        """Loads a btg-files and starts reading up to the point, where objects are read"""
        file_name = path.split('\\')[-1].split('/')[-1]

        # parse the file
        try:
            # Check if the file is gzipped, if so -> use built in gzip
            if file_name[-7:].lower() == ".btg.gz":
                btg_file = gzip.open(path, "rb")
                tile_index = int(file_name[:-7])
            elif file_name[-4:].lower() == ".btg":
                btg_file = open(path, "rb")
                tile_index = int(file_name[:-4])
            else:
                raise MyException('Not a .btg or .btg.gz file: %s', file_name)
            ca.log_tile_info(tile_index)
        except IOError as e:
            raise MyException('Cannot open file {}'.format(path)) from e

        # Read file contents
        with btg_file:
            btg_file.seek(0)

            # Read and unpack header
            binary_format = "<HHI"
            try:
                header = btg_file.read(struct.calcsize(binary_format))
            except IOError as e:
                raise MyException('File in wrong format') from e

            (version, magic, creation_time) = struct.unpack(binary_format, header)

            if version < 7:
                raise MyException('The BTG version must be 7 or higher')

            self.btg_version = version
            if self.is_version_7:
                binary_format = "<H"
                object_fmt = "<BHH"
            else:
                binary_format = "<I"
                object_fmt = "<BII"

            number_objects_ushort = btg_file.read(struct.calcsize(binary_format))
            (number_top_level_objects,) = struct.unpack(binary_format, number_objects_ushort)

            if not magic == 0x5347:
                raise MyException("Magic is not correct ('SG'): {} instead of 0x5347".format(magic))

            # Read objects
            self.read_objects(btg_file, number_top_level_objects, object_fmt)

        # translate vertices from cartesian to geodetic coordinates
        # see simgear/scene/tgdb/obj.cxx
        lon_rad, lat_rad, elev = coord.cart_to_geod(self.gbs_center)
        lon_deg = math.degrees(lon_rad)
        lat_deg = math.degrees(lat_rad)
        logging.debug('GBS center: lon = %f, lat = %f', lon_deg, lat_deg)

        logging.debug('Parsed %i vertices and found the following materials:', len(self.vertices))
        for key, faces_list in self.faces.items():
            logging.debug('Material: %s has %i faces', key, len(faces_list))

    def _clean_data(self):
        """Clean up and remove data that is not usable"""
        for material, faces_list in self.faces.items():
            removed = 0
            for face in reversed(faces_list):
                if face.vertices[0] == face.vertices[1] or face.vertices[0] == face.vertices[2] \
                        or face.vertices[1] == face.vertices[2]:
                    removed += 1
                    faces_list.remove(face)
            if removed > 0:
                logging.debug('Removed %i faces for material %s', removed, material)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    btg_reader_7 = BTGReader('/home/vanosten/bin/terrasync/Terrain/e000n40/e008n47/3088961.btg.gz')  # old version
    if not btg_reader_7.is_version_7:
        raise ValueError('BTG file used is not version 7')
    btg_reader_10 = BTGReader('/home/vanosten/bin/terrasync/Terrain/w160n20/w159n21/351207.btg.gz')  # version 10
    if btg_reader_10.is_version_7:
        raise ValueError('BTG file used is version 7 instead of higher')
    logging.info("Done")
