#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""Remove holes in polygons."""

from typing import Union

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon


def remove_interiors(poly):
    """
    Close polygon holes by limitation to the exterior ring.

    Parameters
    ----------
    poly: shapely.geometry.Polygon
        Input shapely Polygon

    Returns
    ---------
    Polygon without any interior holes
    """
    if poly.interiors:
        return Polygon(list(poly.exterior.coords))
    return poly


def pop_largest(geoser):
    """
    Pop the largest polygon off of a GeoSeries.

    Parameters
    ----------
    geoser: geopandas.GeoSeries
        Geoseries of Polygon or MultiPolygon objects

    Returns
    ---------
    Largest Polygon in a Geoseries
    """
    geoms = [g.area for g in geoser]
    return geoser.pop(geoms.index(max(geoms)))


def close_holes(geom: Union[MultiPolygon, Polygon]) -> Union[MultiPolygon, Polygon]:
    """
    Remove holes in a polygon geometry.

    Parameters
    ----------
    geom:
        shapely geometry object

    Returns
    ---------
    Largest Polygon in a Geoseries
    """
    if isinstance(geom, MultiPolygon):
        ser = gpd.GeoSeries([remove_interiors(g) for g in geom])
        big = pop_largest(ser)
        print(big)
        outers = ser.loc[~ser.within(big)].tolist()
        if outers:
            return MultiPolygon([big] + outers)
        return Polygon(big)
    if isinstance(geom, Polygon):
        return remove_interiors(geom)
