#!/usr/bin/env python3
'''
:author: Aurélien Bricier <aurelien.bricier@csgroup.eu>
:organization: CS Group
:copyright: 2020 CS Group. All rights reserved.
:license: see LICENSE file
:created: 2020
'''

""" cut_contourliness.py
Cut contour lines based on the cutline to estimate the virtual water surface.
"""

import os
import sys
import logging
import argparse
import json
import shapely
import shapely.wkt
from shapely.geometry import shape
from shapely.geometry import Point, Polygon
from shapely.ops import split
from osgeo import ogr
from osgeo import osr
from osgeo import gdal
import numpy as np
import matplotlib.pyplot as plt


def main(arguments):
    '''Entrypoint'''

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-i',
                        '--info',
                        help="daminfo.json file")
    parser.add_argument('-c',
                        '--cut',
                        help="cutline.json file")
    parser.add_argument('-l',
                        '--level',
                        help="contournline.json file")
    parser.add_argument('-d',
                        '--dem',
                        help="Input DEM")
    parser.add_argument('-t',
                        '--tmp',
                        help="Temporary directory")
    parser.add_argument('-o',
                        '--out',
                        help="Output directory")
    parser.add_argument('--debug',
                        action='store_true',
                        help='Activate Debug Mode')
    args = parser.parse_args(arguments)

    logging_format = '%(asctime)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s'
    if (args.debug is True):
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=logging_format)
    else:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=logging_format)
    logging.info("Starting cut_contourlines.py")

    # Silence Mathplotlib related debug messages (font matching)
    logging.getLogger('matplotlib').setLevel(logging.ERROR)

    ds = gdal.Open(args.dem, gdal.GA_ReadOnly);
    carto = osr.SpatialReference(wkt=ds.GetProjection());

    # load GeoJSON file containing info
    with open(args.info) as i:
        jsi = json.load(i)
    damname = ''
    for feature in jsi['features']:
        if feature['properties']['name'] == 'Dam':
            print(feature)
            dam = shape(feature['geometry'])
            damname = feature['properties']['damname']

        if feature['properties']['name'] == 'PDB':
            pdb = shape(feature['geometry'])

    drv = ogr.GetDriverByName( 'GeoJSON' )
    if os.path.exists(os.path.join(args.out, damname + "_vSurfaces.json")):
        os.remove(os.path.join(args.out, damname + "_vSurfaces.json"))
    dst_ds = drv.CreateDataSource( os.path.join(args.out, damname + "_vSurfaces.json"))
    dst_layer = dst_ds.CreateLayer('', srs=carto , \
                                   geom_type=ogr.wkbPolygon )
    field_defn_id=ogr.FieldDefn( 'ID', ogr.OFTString )
    field_defn=ogr.FieldDefn( 'level', ogr.OFTString )
    dst_layer.CreateField( field_defn_id )
    dst_layer.CreateField( field_defn )

    # load GeoJSON file containing cutline
    with open(args.cut) as c:
        jsc = json.load(c)
    for feature in jsc['features']:
        lines = shape(feature['geometry'])
        line = shapely.ops.linemerge(lines)

    # load GeoJSON file containing contour lines
    with open(args.level) as l:
        jsl = json.load(l)

    r_id = 1
    r_elev = []
    r_area = []
    for feature in jsl['features']:
        level = shape(feature['geometry'])
        results = split(level, line)
        found = False
        max_area = -10000
        max_elev = -10000
        for p in results:
            if not p.contains(pdb) and (p.area >= max_area) and p.intersects(line):
                max_area = p.area
                max_elev = float(feature['properties']['ID'])
                found = True
                print("Area: " + str(p.area) + "m2")
                r_feat = ogr.Feature(feature_def=dst_layer.GetLayerDefn())
                r_p = ogr.CreateGeometryFromWkt( p.wkt )
                r_feat.SetGeometryDirectly( r_p )
                r_feat.SetField ( "ID", str(r_id) )
                r_feat.SetField ( "level", feature['properties']['ID'] )

        if found is True:
            dst_layer.CreateFeature( r_feat )
            r_feat.Destroy()
            r_elev.append(max_elev)
            r_area.append(max_area)
            r_id =r_id + 1


    print("index: "+str(r_id))


    fig, ax = plt.subplots()
    ax.plot(r_elev, r_area, '.-r')
    ax.set(xlabel='Virtual Water Surface Elevation (m)',
           ylabel='Virtual Water Surface (m2)')
    plt.title('S(Z_i) ' + damname)
    fig.savefig(os.path.join(args.out, damname + "_SZi.png"))

    data = np.column_stack((r_elev, r_area))
    np.savetxt(os.path.join(args.out, damname + "_SZi.dat"), data)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))