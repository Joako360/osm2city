from texture import Texture
import os
def append_facades(tex_prefix, facades):
    """---------------- ADD YOUR FACADE TEXTURES HERE -------------------"""

    facades.append(Texture(tex_prefix + 'tex.src/facade_industrial_red_white_24x18m.jpg',
        23.8, [364, 742, 1086], True,
        18.5, [295, 565, 842], False,
        v_align_bottom = True,
        requires=[],
        provides=['shape:industrial','age:old', 'compat:roof-flat','compat:roof-pitched']))
    #return 
    
    facades.append(Texture(tex_prefix + 'tex.src/DSCF9495_pow2.png',
        14, [585, 873, 1179, 1480, 2048], True,
        19.4, [274, 676, 1114, 1542, 2048], False,
        height_max = 13.,
        v_align_bottom = True,
        requires=['roof:color:black'],
        provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

    facades.append(Texture(tex_prefix + 'tex.src/LZ_old_bright_bc2.png',
        17.9, [345,807,1023,1236,1452,1686,2048], True,
        14.8, [558,1005,1446,2048], False,
        provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_21x42m.jpg',
        43., [40, 79, 115, 156, 196, 235, 273, 312, 351, 389, 428, 468, 507, 545, 584, 624, 662], True,
        88., [667, 597, 530, 460, 391, 322, 254, 185, 117, 48, 736, 804, 873, 943, 1012, 1080, 1151, 1218, 1288, 1350], False,
        v_align_bottom = True, height_min=20.,
        requires=[],
        provides=['age:modern', 'compat:roof-flat', 'shape:terminal']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_black_46x60m.jpg',
        45.9, [167, 345, 521, 700, 873, 944], True,
        60.5, [144, 229, 311, 393, 480, 562, 645, 732, 818, 901, 983, 1067, 1154, 1245], False,
        v_align_bottom = True, height_min=20.,
        requires=[],
        provides=['shape:urban','age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_industrial_white_26x14m.jpg',
        25.7, [165, 368, 575, 781, 987, 1191, 1332], True,
        13.5, [383, 444, 501, 562, 621, 702], False,
        v_align_bottom = True,
        requires=[],
        provides=['shape:industrial','age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_commercial_35x20m.jpg',
        34.6, [105, 210, 312, 417, 519, 622, 726, 829, 933, 1039, 1144, 1245, 1350], True,
        20.4, [177, 331, 489, 651, 796], False,
        v_align_bottom = True,
        requires=[],
        provides=['shape:commercial','age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern36x36_12.png',
        36., [], True,
        36., [158, 234, 312, 388, 465, 542, 619, 697, 773, 870, 1024], False,
        height_min=20,
        provides=['shape:urban','shape:residential','age:modern',
                  'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_residential_26x34m.jpg',
        26.3, [429, 1723, 2142], True,
        33.9, [429, 666, 919, 1167, 1415, 1660, 1905, 2145, 2761], False,
        v_align_bottom = True, height_min=20,
        provides=['shape:urban','shape:residential','age:modern',
                  'compat:roof-flat']))

#    facades.append(Texture(tex_prefix + 'tex.src/DSCF9503_pow2',
#                            12.85, None, True,
#                            17.66, (1168, 1560, 2048), False, True,
#                            requires=['roof:color:black'],
#                            provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

    facades.append(Texture(tex_prefix + 'tex.src/DSCF9503_noroofsec_pow2.png',
        12.85, [360, 708, 1044, 1392, 2048], True,
        17.66, [556,1015,1474,2048], False,
        requires=['roof:color:black'],
        provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

#    facades.append(Texture(tex_prefix + 'tex.src/DSCF9710_pow2',
#                           29.9, (284,556,874,1180,1512,1780,2048), True,
#                           19.8, (173,329,490,645,791,1024), False, True,
#                           provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

    facades.append(Texture(tex_prefix + 'tex.src/DSCF9710.png',
       29.9, [142,278,437,590,756,890,1024], True,
       19.8, [130,216,297,387,512], False,
       provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))


    facades.append(Texture(tex_prefix + 'tex.src/DSCF9678_pow2.png',
       10.4, [97,152,210,299,355,411,512], True,
       15.5, [132,211,310,512], False,
       provides=['shape:residential','shape:commercial','age:modern','compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_residential_25x15m.jpg',
        25.0, [436, 1194, 2121, 2809, 3536], True,
        14.8, [718, 2096], False,
        v_align_bottom = True,
        requires=['roof:color:black'],
        provides=['shape:residential','age:modern','compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_commercial_red_gray_20x14m.jpg',
        20.0, [588, 1169, 1750, 2327, 2911, 3485], True,
        14.1, [755, 1289, 1823, 2453], False,
        v_align_bottom = True,
        requires=['roof:color:black'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_commercial_green_red_27x39m.jpg',
        27.3, [486, 944, 1398, 1765, 2344], True,
        38.9, [338, 582, 839, 1087, 1340, 1593, 1856, 2094, 3340], False,
        v_align_bottom = True,
        requires=['roof:color:black'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_commercial_46x169m.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=True,
        v_size_meters=169.2, v_cuts=[309, 443, 577, 712, 846, 1204, 1383, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    # FIXME:
    facades.append(Texture(tex_prefix + 'tex.src/facade_modern_commercial_90x340m.jpg',
        h_size_meters=90.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=True,
        v_size_meters=340.2, v_cuts=[309, 443, 577, 712, 846, 1204, 1383, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


    facades.append(Texture(tex_prefix + 'tex.src/DSCF9726_noroofsec_pow2.png',
       15.1, [321,703,1024], True,
       9.6, [227,512], False,
       provides=['shape:residential','age:old','compat:roof-flat','compat:roof-pitched']))

    facades.append(Texture(tex_prefix + 'tex.src/wohnheime_petersburger.png',
       15.6, [215, 414, 614, 814, 1024], False,
       15.6, [112, 295, 477, 660, 843, 1024], True,
       height_min = 15.,
       provides=['shape:urban', 'shape:residential', 'age:modern',
                 'compat:roof-flat']))
#                            provides=['shape:urban','shape:residential','age:modern','age:old',
#                                     'compat:roof-flat','compat:roof-pitched']))

    facades.append(Texture(tex_prefix + 'tex.src/castle.jpg',
                           h_size_meters=4, h_cuts=[512, 1024, 1536, 2048], h_can_repeat=True,
                           v_size_meters=4, v_cuts=[512, 1024, 1536, 2048], v_can_repeat=False,
                           height_min=1.,
                           provides=['building:material:stone',
                                     'age:old',
                                     'compat:roof-gabled',
                                     'compat:roof-pitched',
                                     'compat:roof-flat',
                                     'compat:roof-hipped']))


    # debug fallback texture for very large facades.
    #facades.append(Texture(tex_prefix + 'tex.src/facade_modern_black_46x60m.jpg',
        #450.9, [167, 345, 521, 700, 873, 944], True,
        #600.5, [144, 229, 311, 393, 480, 562, 645, 732, 818, 901, 983, 1067, 1154, 1245], False,
        #v_align_bottom = True,
        #requires=[],
        #provides=['shape:urban','age:modern', 'compat:roof-flat']))

def append_facades_test(tex_prefix, facades):
    """---------------- ADD YOUR FACADE TEXTURES HERE -------------------"""

    # -- testing
    facades.append(Texture(tex_prefix + 'tex.src/10storymodernconcrete.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/11storymodernsq.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 1383, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))
    
    facades.append(Texture(tex_prefix + 'tex.src/12storyconcrglassblkwhtmodern.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443,  1204, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/12storygovtmodern.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

    facades.append(Texture(tex_prefix + 'tex.src/14storyconcrwhite.jpg',
        h_size_meters=45.9, h_cuts=[107, 214, 322, 429, 532, 640, 747, 850], h_can_repeat=False,
        v_size_meters=169.2, v_cuts=[309, 443, 577, 712, 846, 1204, 1383, 1567, 1652, 1755, 1845, 1939, 2024, 2113, 2216, 2306, 2396, 3135], v_can_repeat=False,
        v_align_bottom=True, height_min=40,
        requires=['roof:color:brown'],
        provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))

def import_us(tex_prefix, facades):

  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/50storySteelGlassmodern1.jpg',
      h_size_meters=27, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=108, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/45storyglassmodern.jpg',
      h_size_meters=40, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=80, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-OfficeModern-42st.jpg',
      h_size_meters=39, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=156, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/41storyconcrglasswhitemodern2.jpg',
      h_size_meters=20, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=80, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/40storymodern.jpg',
      h_size_meters=40, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=160, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/36storyconcrglassmodern.jpg',
      h_size_meters=32, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=128, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/35storyconcrmodernwhite.jpg',
      h_size_meters=25, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=100, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/30storyconcrbrown4.jpg',
      h_size_meters=29, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=58, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/28storymodern.jpg',
      h_size_meters=29, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=58, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/27storyConcrBrownGlass.jpg',
      h_size_meters=17, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=68, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/25storyBrownWide1.jpg',
      h_size_meters=60, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=60, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/20storybrownconcrmodern.jpg',
      h_size_meters=29, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=58, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/20storygreycncrglassmodern.jpg',
      h_size_meters=27, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=54, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/19storyretromodern.jpg',
      h_size_meters=30, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=120, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/18storyoffice.jpg',
      h_size_meters=28, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=56, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/16storyconcrglassgreymodern4.jpg',
      h_size_meters=14, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=28, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/15storybrownconcr.jpg',
      h_size_meters=38, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=76, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/15storyltbrownconcroffice3.jpg',
      h_size_meters=29, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=58, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/12storygovtmodern.jpg',
      h_size_meters=21, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=21, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/10storymodernconcrete.jpg',
      h_size_meters=27, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=54, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dcofficeconcrwhite8st.jpg',
      h_size_meters=24, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=24, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dchotelDC2_8st.jpg',
      h_size_meters=15, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=30, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dcofficeconcrwhite6-7st.jpg',
      h_size_meters=34, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=17, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/7storymodernsq.jpg',
      h_size_meters=19, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=19, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dcdupontconcr5st.jpg',
      h_size_meters=7, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=14, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/5storywhite.jpg',
      h_size_meters=12, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=12, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dcgovtconcrtan4st.jpg',
      h_size_meters=18, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=9, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/3storystorefronttown.jpg',
      h_size_meters=9, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=9, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/salmon_3_story_0_scale.jpg',
      h_size_meters=8, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=8, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/2stFancyconcrete1.jpg',
      h_size_meters=14, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=7, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dcwhiteconcr2st.jpg',
      h_size_meters=16, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=8, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-dctbrickcomm2st.jpg',
      h_size_meters=21, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=5.25, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/USUAE-4stCommercial.jpg',
      h_size_meters=20, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=10, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-OfficeComm-2st.jpg',
      h_size_meters=15, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=3.75, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-1stCommWarehousewhite1.jpg',
      h_size_meters=15, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=3.75, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-1stCommBrick2.jpg',
      h_size_meters=15, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=3.75, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/commercial/US-1stCommStFront3.jpg',
      h_size_meters=10, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=5, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/residential/tiles/USUAE-8stTile_rep.jpg',
      h_size_meters=15, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=30, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/residential/6storybrickbrown1.jpg',
      h_size_meters=21, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=21, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/residential/5storyCondo_concrglasswhite.jpg',
      h_size_meters=14, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=28, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/residential/US-CityCondo_brick_4st.jpg',
      h_size_meters=16, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=16, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


  facades.append(Texture(tex_prefix + 'tex.src/textures_us/residential/US-CityCondo2st.jpg',
      h_size_meters=11, h_cuts=[0, 500, 1000], h_can_repeat=False,
      v_size_meters=11, v_cuts=[0, 500, 1000], v_can_repeat=False,
      v_align_bottom=True, height_min=10,
      requires=['roof:color:brown'],
      provides=['shape:urban', 'shape:commercial', 'age:modern', 'compat:roof-flat']))


def append_roofs(tex_prefix, roofs):
    """------------ ADD YOUR ROOF TEXTURES HERE -------------------"""

#    roofs.append(Texture(tex_prefix + 'tex.src/roof_tiled_black',
#                         1., [], True, 1., [], False, provides=['color:black']))
#    roofs.append(Texture(tex_prefix + 'tex.src/roof_tiled_red',
#                         1., [], True, 1., [], False, provides=['color:red']))

    roofs.append(Texture(tex_prefix + 'tex.src/roof_red_1.png',
        31.8, [], True, 16.1, [], False, provides=['color:red', 'compat:roof-pitched']))
    roofs.append(Texture(tex_prefix + 'tex.src/roof_black_1.png',
        31.8, [], True, 16.1, [], False, provides=['color:black', 'compat:roof-pitched']))
    roofs.append(Texture(tex_prefix + 'tex.src/roof_black4.jpg',
        6., [], True, 3.5, [], False, provides=['color:black', 'compat:roof-pitched']))
    roofs.append(Texture(tex_prefix + 'tex.src/roof_gen_black_1.png',
        100., [], True, 100., [], False, provides=['color:red', 'compat:roof-flat']))
    roofs.append(Texture(tex_prefix + 'tex.src/roof_gen_black_1.png',
        100., [], True, 100., [], False, provides=['color:black', 'compat:roof-flat']))
    roofs.append(Texture(tex_prefix + 'tex.src/roof_gen_brown_1.png',
        100., [], True, 100., [], False, provides=['color:brown', 'compat:roof-flat']))

#    roofs.append(Texture(tex_prefix + 'tex.src/roof_black2',
#                             1.39, [], True, 0.89, [], True, provides=['color:black']))
#    roofs.append(Texture(tex_prefix + 'tex.src/roof_black3',
#                             0.6, [], True, 0.41, [], True, provides=['color:black']))

#    roofs.append(Texture(tex_prefix + 'tex.src/roof_black3_small_256x128',
#                             0.25, [], True, 0.12, [], True, provides=['color:black']))
