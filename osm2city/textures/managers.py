from dataclasses import dataclass
import enum
import os.path as osp
import random
from typing import Dict, List


PATH_TO_TEXTURES = '/home/vanosten/bin/TerraSync/Models/osm2city'  # FIXME: should be relative once published


@dataclass(frozen=True)
class TexturesFile:
    """The essential data for a physical file on the file system containing a set of textures"""

    name: str  # a descriptive name for the texture file
    file_name: str  # relative to the base directory for osm2city texture files
    width_px: int  # the width in pixels. 0 is left
    height_px: int  # the height in pixels. 0 is top (like in Gimp)
    precision: int = 16  # the number of bits integer used (8 bit = 256 colours, 16 bit = 65536 colours)
    gamma: bool = True  # True if sRGB
    color_profile: str = 'GIMP built-in sRGB'

    @property
    def file_path(self) -> str:
        return osp.join(PATH_TO_TEXTURES, self.file_name)


@enum.unique
class SlopedType(enum.IntEnum):
    flat_only = 1
    sloped_only = 2
    flat_or_sloped = 3


class RoofTexture:
    """A specific texture in a specific texture file representing a specific roof material, colour etc.

    All textures fill the whole width and can be repeated in the x-axis.
    They cannot be repeated in the y-axis, but instead they can be stretched.
    """
    __slots__ = ('textures_file', 'description', 'width_px', 'height_px', 'pixel_size', 'y_min', 'sloped_type')

    def __init__(self, textures_file: TexturesFile, description: str, width: int, height: int,
                 pixel_size: float, y_min: int, sloped_type: SlopedType) -> None:
        self.textures_file = textures_file
        self.description = description
        self.width_px = width  # size of the texture within the physical file in pixels
        self.height_px = height  # in pixels
        self.pixel_size = pixel_size  # how large 1 pixel is in metres in the real world
        # the y coordinate of the lower left corner of this texture within the physical file
        # 0 is at the top of the physical file like in Gimp
        self.y_min = y_min
        self.sloped_type = sloped_type

    @property
    def h_size_meters(self) -> float:  # h means horizontal
        return self.pixel_size * self.width_px

    @property
    def v_size_meters(self) -> float:  # v means vertical
        return self.pixel_size * self.height_px

    @property
    def h_can_repeat(self) -> bool:
        return True

    @property
    def v_can_repeat(self) -> bool:
        return True  # is actually fake, because we scale in method y()

    def x(self, points_x_relative):  # input can be a float or a list of floats - output correspondingly
        """Return the u value of a uv-map for the x-coordinate of a set of points in a face.

        Because this is x-repeatable and x_min is always 0, there is really nothing to do.
        """
        return points_x_relative

    def y(self, points_y_relative):
        """Return the v value of a uv-map for the y-coordinate of a set of points in a face."""
        is_number = False
        if isinstance(points_y_relative, int) or isinstance(points_y_relative, float):
            points_y_relative = [points_y_relative]
            is_number = True
        my_list = list()

        # calculate a scale factor to fake the fact that this is not really repeatable in y-direction
        max_y = 0.
        for point_y_relative in points_y_relative:
            max_y = max(max_y, point_y_relative)
        scale_factor = 1. if max_y <= 1.0 else 1 / max_y

        # calculate the position between 0 and 1 in the vertical direction of the texture
        y_min_relative = self.y_min / self.textures_file.height_px
        y_factor_relative = self.height_px / self.textures_file.height_px
        for point_y_relative in points_y_relative:
            my_list.append(y_min_relative + point_y_relative * y_factor_relative * scale_factor)
        if is_number:
            return my_list[0]
        return my_list


class RoofManager:
    # The atlas of RoofTextures
    # u coordinate is from left to right side of the texture (0.0 - 1.0)
    # v coordinate is from bottom to top of the texture (0.0 - 1.0) - opposite to Gimp, which has 0 at top

    large_flat_roofs = TexturesFile('Textures for large flat roofs', 'large_flat_roofs.png', 256, 8192)

    roof_texture_atlas = [
        # ---- large_flat_roofs
        RoofTexture(large_flat_roofs, 'pink', 256, 1024, 0.1, 7*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'red', 256, 1024, 0.1, 6*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'light green', 256, 1024, 0.1, 5*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'blue', 256, 1024, 0.1, 4*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'yellow', 256, 1024, 0.1, 3*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'orange', 256, 1024, 0.1, 2*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'cyan', 256, 1024, 0.1, 1*1024, SlopedType.flat_or_sloped),
        RoofTexture(large_flat_roofs, 'dark green', 256, 1024, 0.1, 0*1024, SlopedType.flat_or_sloped)
    ]

    __slots__ = '_roof_textures'

    def __init__(self) -> None:
        self._roof_textures = list()  # list of RoofTexture objects
        self._read_texture_atlas()

    def _read_texture_atlas(self) -> None:
        """Reads the global texture atlas and validates the values."""
        for roof_texture in self.roof_texture_atlas:
            self._roof_textures.append(roof_texture)
        if not self._roof_textures:
            raise ValueError('There must be at least 1 validated RoofTexture in roof_texture_atlas')

    def find_matching_roof(self, requires: List[str], max_dimension: float) -> RoofTexture:
        my_texture = random.choice(self._roof_textures)
        return my_texture


class FacadeTexture:
    """A specific texture in a specific texture file representing a specific facade material, colour etc.

    FIXME
    """
    __slots__ = ('textures_file', 'description', 'width_px', 'height_px', 'pixel_size', 'y_min')

    def __init__(self, textures_file: TexturesFile, description: str, width: int, height: int,
                 pixel_size: float, y_min: int) -> None:
        self.textures_file = textures_file
        self.description = description
        self.width_px = width  # size of the texture within the physical file in pixels
        self.height_px = height  # in pixels
        self.pixel_size = pixel_size  # how large 1 pixel is in metres in the real world
        # the y coordinate of the lower left corner of this texture within the physical file
        # 0 is at the top of the physical file like in Gimp
        self.y_min = y_min

    @property
    def h_size_meters(self) -> float:  # h means horizontal
        return self.pixel_size * self.width_px

    @property
    def v_size_meters(self) -> float:  # v means vertical
        return self.pixel_size * self.height_px

    @property
    def h_can_repeat(self) -> bool:
        return True

    @property
    def v_can_repeat(self) -> bool:
        return True  # is actually fake, because we scale in method y()

    def x(self, points_x_relative):  # input can be a float or a list of floats - output correspondingly
        """Return the u value of a uv-map for the x-coordinate of a set of points in a face.

        Because this is x-repeatable and x_min is always 0, there is really nothing to do.
        """
        return points_x_relative

    def y(self, points_y_relative):
        """Return the v value of a uv-map for the y-coordinate of a set of points in a face."""
        is_number = False
        if isinstance(points_y_relative, int) or isinstance(points_y_relative, float):
            points_y_relative = [points_y_relative]
            is_number = True
        my_list = list()

        # calculate a scale factor to fake the fact that this is not really repeatable in y-direction
        max_y = 0.
        for point_y_relative in points_y_relative:
            max_y = max(max_y, point_y_relative)
        scale_factor = 1. if max_y <= 1.0 else 1 / max_y

        # calculate the position between 0 and 1 in the vertical direction of the texture
        y_min_relative = self.y_min / self.textures_file.height_px
        y_factor_relative = self.height_px / self.textures_file.height_px
        for point_y_relative in points_y_relative:
            my_list.append(y_min_relative + point_y_relative * y_factor_relative * scale_factor)
        if is_number:
            return my_list[0]
        return my_list


class FacadeManager:
    # The atlas of RoofTextures
    # u coordinate is from left to right side of the texture (0.0 - 1.0)
    # v coordinate is from bottom to top of the texture (0.0 - 1.0) - opposite to Gimp, which has 0 at top

    fallback_facades = TexturesFile('Texture a fallback for facades', 'fallback_facades.png', 1024, 1024)

    texture_atlas = [
        # ---- large_flat_roofs
        FacadeTexture(fallback_facades, 'light grey', 1024, 1024, 1.0, 0),
    ]

    __slots__ = '_facade_textures'

    def __init__(self) -> None:
        self._facade_textures = list()  # list of RoofTexture objects
        self._read_texture_atlas()

    def _read_texture_atlas(self) -> None:
        """Reads the texture atlas and validates the values."""
        for roof_texture in self.texture_atlas:
            self._facade_textures.append(roof_texture)
        if not self._facade_textures:
            raise ValueError('There must be at least 1 validated RoofTexture in roof_texture_atlas')

    def find_matching_facade(self, requires: List[str], tags: Dict[str, str],
                             height: float, width: float) -> FacadeTexture:
        my_texture = random.choice(self._facade_textures)
        return my_texture
