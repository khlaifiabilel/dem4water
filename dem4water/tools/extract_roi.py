#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract ROI from an image."""
import argparse
import sys
from dataclasses import dataclass
from math import ceil, floor

import rasterio as rio
from rasterio.windows import Window

from dem4water.tools.save_raster import save_image

DTYPE = {
    "uint8": rio.uint8,
    "uint16": rio.uint16,
    "uint32": rio.uint32,
    "float": rio.float32,
}


@dataclass
class ExtractROIParam:
    """Class providing parameters for extract roi functions."""

    mode: str
    mode_radius_cx: int
    mode_radius_cy: int
    mode_radius_r: int = 0
    mode_radius_unitr: str = "phy"
    mode_radius_unitc: str = "phy"
    dtype: str = "float"


def coord_phys_to_pixel(
    in_raster: str,
    extractroi_parameters: ExtractROIParam,
):
    """
    Transform coordinates to index.

    Parameters
    ----------
    in_raster:str
    """
    x_pixel, y_pixel = in_raster.index(
        extractroi_parameters.mode_radius_cx, extractroi_parameters.mode_radius_cy
    )
    return x_pixel, y_pixel


def extract_roi(
    in_raster: rio.io.DatasetReader,
    extractroi_parameters: ExtractROIParam,
):
    """
    Extract ROI from a raster.

    Parameters
    ----------
    in_raster:rio.io.DatasetReader

    ExtractROI_parameters: ExtractROIParam,
    """
    if extractroi_parameters.mode == "radius":
        if (
            extractroi_parameters.mode_radius_unitr == "phy"
            and extractroi_parameters.mode_radius_unitc == "phy"
        ):
            resolution = in_raster.res[0]
            dist_radius = extractroi_parameters.mode_radius_r / resolution

            x_pixel, y_pixel = coord_phys_to_pixel(in_raster, extractroi_parameters)

            width = (dist_radius) * 2 + 1
            height = (dist_radius) * 2 + 1
            if (dist_radius % 2) == 0:
                col_off, row_off = (
                    x_pixel - dist_radius,
                    y_pixel - dist_radius,
                )

            else:
                col_off, row_off = (
                    ceil(x_pixel - dist_radius),
                    floor(y_pixel - dist_radius),
                )

            window = Window(row_off, col_off, width, height)

            data = in_raster.read(window=window)
            transform = rio.windows.transform(window, in_raster.transform)

            profile = in_raster.profile
            profile.update(
                {
                    "height": height,
                    "width": width,
                    "transform": transform,
                    "driver": "GTiff",
                }
            )
            return data, profile


def main():
    """Define parameters."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-in", "--imref", help="Image to be processed", required=True)
    parser.add_argument("-out", "--outim", help="Output Image", required=True)

    parser.add_argument(
        "-mode",
        "--mode",
        help="Extraction mode",
        choices=["standard", "fit", "extent", "radius"],
        required=True,
    )
    parser.add_argument(
        "-mode.radius.r", "--mode_radius_r", help="Radius", type=int, default=0
    )
    parser.add_argument(
        "-mode.radius.unitr",
        "--mode_radius_unitr",
        help="Radius unit",
        choices=["pxl", "phy"],
    )
    parser.add_argument(
        "-mode.radius.cx",
        "--mode_radius_cx",
        help="X coordinate of the center",
        type=int,
        default=0,
    )
    parser.add_argument(
        "-mode.radius.cy",
        "--mode_radius_cy",
        help="Y coordinate of the center",
        type=int,
        default=0,
    )
    parser.add_argument(
        "-mode.radius.unitc",
        "--mode_radius_unitc",
        help="Center unit",
        choices=["pxl", "phy"],
    )
    parser.add_argument(
        "-dtype",
        "--dtype",
        help="Data type of output raster",
        choices=["uint8", "uint16", "uint32", "float"],
        default="uint8",
    )
    args = parser.parse_args()
    params = ExtractROIParam(
        args.mode,
        args.mode_radius_r,
        args.mode_radius_unitr,
        args.mode_radius_cx,
        args.mode_radius_cy,
        args.mode_radius_unitc,
        DTYPE[args.dtype],
    )
    with rio.open(args.imref) as imref:
        data, profile = extract_roi(imref, params)
        save_image(data, profile, args.out)


if __name__ == "__main__":
    sys.exit(main())
