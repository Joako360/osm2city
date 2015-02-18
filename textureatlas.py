#!/usr/bin/env python2
#
#
"""generate texture atlas"""

import PIL.Image as Image

class Region(object):
    def __init__(self, x, y, width, height):
        print "  New Region (%i x %i + %i + %i)" % (width, height, x, y)
        self.x = x
        self.y = y        
        self.width_px = width
        self.height_px = height

class Atlas(Region):
    def __init__(self, x, y, width, height):
        super(Atlas, self).__init__(x, y, width, height)
        self.regions = [Region(x, y, width, height)]
        self._textures = []
        
    def write(self, filename, format):
        atlas = Image.new("RGB", (self.width_px, self.height_px))

        for the_texture in self._textures:
            atlas.paste(the_texture.im, (the_texture.x, the_texture.y))

        atlas.save(filename, optimize=True)

    def pack(self, the_texture):
        print "packing %s (%i %i)" % (the_texture.filename, the_texture.width_px, the_texture.height_px)
        for the_region in self.regions:
            if self._pack(the_texture, the_region):
                self._textures.append(the_texture)
                print "  packed at %i %i" % (the_texture.x, the_texture.y)
                return True
        return False
        
    def _pack(self, the_texture, the_region):
        assert(the_texture.height_px > 0)
        assert(the_texture.width_px > 0)
        if the_texture.height_px == the_region.height_px:
            if the_texture.width_px == the_region.width_px:
                print "H split exact fit"
                the_texture.x = the_region.x
                the_texture.y = the_region.y
                self.regions.remove(the_region)
                return True
            elif the_texture.width_px < the_region.width_px:
                print "H split"
                # split horiz
                the_texture.x = the_region.x
                the_texture.y = the_region.y
                the_region.x += the_texture.width_px
                the_region.width_px -= the_texture.width_px
                return True
            else:
                print "H too small (%i < %i), trying next" % (the_region.width_px, the_texture.width_px)
                return False
        elif the_texture.height_px > the_region.height_px:
            print "V too small, trying next"
            return False
        else:
            # check if it fits width
            if the_texture.width_px > the_region.width_px:
                return False
            print "V split"
            # vertical split
            the_texture.x = the_region.x
            the_texture.y = the_region.y
            new_region = Region(the_region.x, the_region.y + the_texture.height_px, the_region.width_px, the_region.height_px - the_texture.height_px)
            the_region.x += the_texture.width_px
            the_region.width_px -= the_texture.width_px
            the_region.height_px = the_texture.height_px
            self.regions.insert(self.regions.index(the_region) + 1, new_region)
            return True
        
class Texture(object):
    """A collection of one or more frames."""

    def __init__(self, filename):
        self.filename   = filename
        self.im = Image.open(filename)
        self.width_px, self.height_px = self.im.size

    @property
    def name(self):
        return self._name


def mk_atlas(filenames_list):
    import glob
    textures = []
    filenames_list = glob.glob("textureatlas/textureatlas-master/samples/*.jpg")
    atlas = Atlas(0, 0, 512, 14000)
    for filename in filenames_list:
        
        # Add frames to texture object list
        textures.append(Texture(filename))

    # Sort textures by perimeter size in non-increasing order
    textures = sorted(textures, key=lambda i:i.height_px, reverse=True)

    for the_texture in textures:
        if atlas.pack(the_texture):
            atlas.write("atlas.png", "RGBA")
            raw_input("Press Enter to continue...")
        else:
            print "no"

    atlas.write("atlast.png", "RGBA")



def main():
    mk_atlas(1)

if __name__ == '__main__':
    main()