#!/usr/bin/env python2
#
#
"""generate texture atlas"""

import PIL.Image as Image

class Region(object):
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y        
        self.width_px = width
        self.height_px = height
        print "  New Region " + str(self)

    def __str__(self):
        return "(%i x %i + %i + %i)" % (self.width_px, self.height_px, self.x, self.y)
        

class Atlas(Region):
    def __init__(self, x, y, width, height):
        super(Atlas, self).__init__(x, y, width, height)
        self.regions = [Region(x, y, width, height)]
        self._textures = []
        self.min_width = 1
        self.min_height = 1
        
    def write(self, filename, format):
        atlas = Image.new("RGB", (self.width_px, self.height_px))

        for the_texture in self._textures:
            atlas.paste(the_texture.im, (the_texture._x, the_texture._y))

        atlas.save(filename, optimize=True)

    def pack(self, the_texture):
        print "packing %s (%i %i)" % (the_texture.filename, the_texture.width_px, the_texture.height_px)
        for the_region in self.regions:
            if self._pack(the_texture, the_region):
                self._textures.append(the_texture)
                print "  packed at %i %i" % (the_texture._x, the_texture._y)
                print "now have %i regions" % len(self.regions)
                for the_region in self.regions:
                    print "  - ", the_region
                return True
        return False
        
    def check_regions(self):
        for region1 in self.regions:
            if region1.width_px < self.min_width or region1.height_px < self.min_height:
                self.regions.remove(region1)
            for region2 in self.regions:
                if region2 == region1: continue
                # -- check if we can join two regions
                if region1.x == region2.x and region1.width_px == region2.width_px \
                   and region1.y + region1.height_px == region2.y:
                       region1.height_px += region2.height_px
                       self.regions.remove(region2)
            

    def _pack(self, the_texture, the_region):
        assert(the_texture.height_px > 0)
        assert(the_texture.width_px > 0)
        if the_texture.height_px == the_region.height_px:
            if the_texture.width_px == the_region.width_px:
                print "H split exact fit"
                the_texture._x = the_region.x
                the_texture._y = the_region.y
                self.regions.remove(the_region)
                return True
            elif the_texture.width_px < the_region.width_px:
                print "H split"
                # split horiz
                the_texture._x = the_region.x
                the_texture._y = the_region.y
                the_region.x += the_texture.width_px
                the_region.width_px -= the_texture.width_px
                self.check_regions()
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
            the_texture._x = the_region.x
            the_texture._y = the_region.y
            new_region = Region(the_region.x, the_region.y + the_texture.height_px, the_region.width_px, the_region.height_px - the_texture.height_px)
            the_region.x += the_texture.width_px
            the_region.width_px -= the_texture.width_px
            the_region.height_px = the_texture.height_px
            self.regions.insert(self.regions.index(the_region) + 1, new_region)
            self.check_regions()
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
    atlas = Atlas(0, 0, 256, 14000)
    for filename in filenames_list:
        
        # Add frames to texture object list
        textures.append(Texture(filename))

    # Sort textures by perimeter size in non-increasing order
    textures = sorted(textures, key=lambda i:i.height_px, reverse=True)

    for the_texture in textures:
        if atlas.pack(the_texture):
            atlas.write("atlas.png", "RGBA")
            raw_input("Press Enter to continue...")
            pass
        else:
            print "no"

    atlas.write("atlast.png", "RGBA")



def main():
    mk_atlas(1)

if __name__ == '__main__':
    main()