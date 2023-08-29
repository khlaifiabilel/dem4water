import os
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely

# from rasterio.mask import mask
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge

from dem4water.tools.compute_grandient_dot_product import compute_gradient_product
from dem4water.tools.polygonize_raster import polygonize
from dem4water.tools.rasterize_vectors import RasterizarionParams, rasterize
from dem4water.tools.remove_holes_in_shapes import close_holes


# ######################################
# Preprocess database
# #######################################
def remove_mutlipolygon(in_vector, epsg, buffer_size=10):
    """Apply a buffer in both sign to close small gap between polygons."""
    gdf = gpd.GeoDataFrame().from_file(in_vector)
    gdf = gdf.to_crs(epsg)
    gdf["geometry"] = gdf.geometry.buffer(buffer_size)
    gdf["geometry"] = gdf.geometry.buffer(-buffer_size)
    gdf = gdf.explode(ignore_index=True)
    return gdf


def preprocess_water_body(in_vector, epsg):
    """."""
    # Fuse multipolygon
    gdf_wb = remove_mutlipolygon(in_vector, epsg, 10)
    # Remove holes
    gdf_wb.geometry = gdf_wb.geometry.apply(lambda p: close_holes(p))
    return gdf_wb


def clear_polygonize(in_vector, epsg):
    """."""
    gdf = gpd.GeoDataFrame().from_file(in_vector)
    gdf = gdf.to_crs(epsg)
    gdf = gdf.loc[gdf["DN"] == 1]
    return gdf


def filter_by_convex_hull(gdf, work_dir, id_col):
    """."""
    gdf_convex_hull = gdf.copy()
    gdf_convex_hull.geometry = gdf_convex_hull.geometry.convex_hull
    gdf_convex_hull["area"] = gdf_convex_hull.geometry.area
    gdf_convex_hull = gdf_convex_hull.sort_values("area", ascending=False)
    gdf_convex_hull = gdf_convex_hull.reset_index(drop=True)

    id_line = list(gdf_convex_hull[id_col])
    view_id = []
    not_to_see = []
    for line in id_line:
        if line not in not_to_see:
            df_work = gdf_convex_hull.loc[gdf_convex_hull[id_col] == line]
            intersect = gpd.sjoin(gdf, df_work, how="inner")
            view_id.append(line)
            not_to_see += list(intersect[f"{id_col}_left"])

            # print(intersect)
            # intersect.to_file(os.path.join(work_dir, "intersect.geojson"))
    gdf_filtered = gdf[gdf[id_col].isin(view_id)]
    # gdf_filtered = gdf_filtered.drop(["area"], axis=1)
    # gdf_filtered.to_file(os.path.join(work_dir, "filtered_poly.geojson"))
    return gdf_filtered


# ##################################################
# Handle points
# ##################################################


def poly_to_points(feature, poly):
    """."""
    return {feature: poly.exterior.coords}


def linestring_to_points(feature, line):
    return {feature: line.coords}


def convert_geodataframe_poly_to_points(
    in_gdf, id_col, out_id_name, ident_gdp=None, suffix=None, type_geom="poly"
):
    """."""
    suffix = suffix if suffix is not None else ""
    # input(suffix)
    if type_geom == "poly":
        in_gdf["points"] = in_gdf.apply(
            lambda p: poly_to_points(p[id_col], p["geometry"]), axis=1
        )
    else:
        in_gdf["points"] = in_gdf.apply(
            lambda p: linestring_to_points(p[id_col], p["geometry"]), axis=1
        )
    list_points = list(in_gdf.points)

    ident = []
    coordx = []
    coordy = []
    fidx = []
    for i, poly in enumerate(list_points):
        for _, points in poly.items():
            for idx, point in enumerate(points[:-1]):
                fidx.append(idx)
                if ident_gdp is None:
                    ident.append(i)
                else:
                    ident.append(ident_gdp)
                coordx.append(point[0])
                coordy.append(point[1])
    df_coords = pd.DataFrame()
    df_coords[f"x{suffix}"] = coordx
    df_coords[f"y{suffix}"] = coordy
    df_coords[id_col] = ident
    df_coords[out_id_name] = fidx  # range(len(df_coords.index))
    gdf = gpd.GeoDataFrame(
        df_coords,
        geometry=gpd.points_from_xy(df_coords[f"x{suffix}"], df_coords[f"y{suffix}"]),
        crs=in_gdf.crs,
    )
    return gdf


def manage_small_subset_of_points(gdf_work, gdf_gdp_poly, gdf_wb_poly, gdp_ident):
    """."""
    # first_point = gdf.iloc[0]
    # last_point = gdf.iloc[-1]
    # print(gdf)
    # print(first_point)
    # print(last_point)
    print(gdf_work)
    print("Too small")
    gdf_gdp_poly.geometry = gdf_gdp_poly.geometry.buffer(30)
    gdf_wb = gdf_wb_poly.copy()
    gdf_wb.geometry = gdf_wb.exterior
    gdf_in = gpd.overlay(gdf_wb, gdf_gdp_poly)
    convert = []
    for line in gdf_in.geometry.values:
        if isinstance(line, MultiLineString):
            convert += [i for i in line.geoms]
        else:
            convert.append(line)
    gdf = gpd.GeoDataFrame(
        {"ident": range(len(convert)), "gdp_unique_id": gdp_ident},
        geometry=convert,
        crs=gdf_in.crs,
    )
    print(gdf)
    gdf = convert_geodataframe_poly_to_points(
        gdf,
        "gdp_unique_id",
        "gdp_point",
        ident_gdp=gdp_ident,
        suffix=None,
        type_geom="line",
    )
    print(gdf)
    # input("wait gdf")
    return gdf


def draw_lines(gdf_wb_points, gdf_gdp_poly, gdf_wb_poly):
    # gdf_temp = gdf_gdp_poly.copy()
    # gdf_temp.geometry = gdf_temp.geometry.buffer(30)
    gdf = gpd.sjoin_nearest(
        gdf_gdp_poly, gdf_wb_points, max_distance=300, distance_col="distance"
    )
    # gdf.to_file(
    #     "/home/btardy/Documents/activites/WATER/GDP/Marne_chain/sjoin_nearest.geojson"
    # )
    list_df = []
    for ident in gdf.gdp_unique_id.unique():
        gdf_work = gdf[gdf.gdp_unique_id == ident]
        if len(gdf_work) == 1:
            print(f"No enought points to start cutline search for gdp n°{ident}")
            continue
        wb_ident = gdf_work.wb_unique_id.unique()
        if len(wb_ident) > 1:
            print("Impossible to match the gdp with a unique water body.")
        else:
            wb_ident = wb_ident[0]
            max_indices_wb = gdf_wb_points[
                gdf_wb_points.wb_unique_id == wb_ident
            ].id_point.max()
        min_indices_gdp = gdf_work.id_point.min()
        max_indices_gdp = gdf_work.id_point.max()
        if min_indices_gdp < 100 and max_indices_gdp > max_indices_wb - 100:
            print("passe par l'origine")
            gdf_points = convert_geodataframe_poly_to_points(
                gdf_work.iloc[[0]], "gdp_unique_id", "gdp_point", ident
            )
            gdf_points_contour = gpd.GeoDataFrame(
                gdf_work[["wb_unique_id", "id_point"]],
                geometry=gpd.points_from_xy(gdf_work.x, gdf_work.y),
                crs=gdf_work.crs,
            )
            inter = gpd.sjoin_nearest(gdf_points_contour, gdf_points)
            # gdf_temp = gdf_work.sort_values(
            #     "gdp_point"
            # )
            gdf_temp = inter.sort_values("gdp_point")
            gdf_work = gdf_temp.reset_index(drop=True)
            gdf_temp = gpd.GeoDataFrame(
                gdf_temp[["gdp_unique_id", "wb_unique_id", "id_point"]],
                geometry=gpd.points_from_xy(gdf_temp.x, gdf_temp.y),
                crs=gdf_work.crs,
            )
            list_df.append(gdf_temp)
        else:
            print("no zero")
            gdf_work = gdf_work.drop_duplicates(["x", "y"])

            print(
                compute_distance(
                    (list(gdf_work.x)[0], list(gdf_work.y)[0]),
                    (list(gdf_work.x)[1], list(gdf_work.y)[1]),
                )
            )

            gdf_work = gdf_work.sort_values("id_point")
            gdf_work = gdf_work.reset_index(drop=True)
            # gdf_work.geometry = gdf_work.simplify(1)

            # if len(gdf_work.index) < 5:
            # print("2 points")
            gdf_poly = gdf_gdp_poly.loc[gdf_gdp_poly.gdp_unique_id == ident]
            radius = gdf_poly.geometry.minimum_bounding_radius().values[0]

            print("radius : ", radius)
            distance = compute_distance(
                (gdf_work.iloc[0].x, gdf_work.iloc[0].y),
                (gdf_work.iloc[1].x, gdf_work.iloc[-1].y),
            )
            print("len of base ", distance)
            if distance < radius * 0.1:
                gdf_temp = manage_small_subset_of_points(
                    gdf_work, gdf_poly, gdf_wb_poly, ident
                )
            else:
                gdf_temp = gpd.GeoDataFrame(
                    gdf_work[["gdp_unique_id", "wb_unique_id", "id_point"]],
                    geometry=gpd.points_from_xy(gdf_work.x, gdf_work.y),
                    crs=gdf_work.crs,
                )
            list_df.append(gdf_temp)
    gdf_n = gpd.GeoDataFrame(pd.concat(list_df, ignore_index=True), crs=list_df[0].crs)
    lines = gdf_n.groupby(["gdp_unique_id"])["geometry"].apply(
        lambda x: LineString(x.tolist())
    )
    lines = gpd.GeoDataFrame(lines, geometry="geometry", crs=gdf.crs)
    # Remove useless points by simplying each line
    lines.geometry = lines.simplify(1)
    lines.reset_index(inplace=True)
    # input("wait")
    return lines


# ##############################################
# Find higher altitude to complete cutline
# ##############################################


# def search_line(init_point, gdf_lines, mnt_raster, buffer_size, alt_max):
#     """."""
#     # print(init_point)
#     max_point = gpd.GeoDataFrame(
#         {"init_point": [1]},
#         geometry=gpd.points_from_xy([init_point[0]], [init_point[1]]),
#         crs=gdf_lines.crs,
#     )
#     coords = []
#     search = True
#     while search:
#         max_point.geometry = max_point.geometry.buffer(buffer_size)
#         geoms = max_point.geometry.values
#         with rasterio.open(mnt_raster) as mnt:
#             out_image, out_transform = mask(mnt, geoms, crop=True)
#             no_data = mnt.nodata
#             data = out_image[0, :, :]
#             row, col = np.where(data != no_data)
#             vals = np.extract(data != no_data, data)
#             x_coords, y_coords = rasterio.transform.xy(
#                 out_transform, row, col, offset="center"
#             )
#             gdf = gpd.GeoDataFrame(
#                 {"row": row, "col": col, "altitude": vals},
#                 geometry=gpd.points_from_xy(x_coords, y_coords),
#                 crs=gdf_lines.crs,
#             )
#             if gdf.altitude.max() <= alt_max:
#                 max_point_c = gdf.iloc[[gdf.altitude.idxmax()]]
#                 point_x = float(max_point_c.iloc[0].geometry.x)
#                 point_y = float(max_point_c.iloc[0].geometry.y)
#                 # print(point_x, ",", point_y)
#                 point = (point_x, point_y)
#                 if point in coords:
#                     # print("stop")
#                     search = False
#                 else:
#                     coords.append(point)
#                     max_point = max_point_c.copy()
#             else:
#                 search = False
#     # print(coords)
#     return coords
#     # input("wait")


def search_point(
    init_point, prev_point, row, direction, mnt_raster, search_radius, alt, alt_max
):
    """."""
    with rasterio.open(mnt_raster) as mnt:
        mnt_array = mnt.read()
        mnt_array = mnt_array[0, :, :]
        # print(mnt_array.shape)
        mnt_transform = mnt.transform
        x_grid, y_grid = np.meshgrid(
            np.arange(mnt_array.shape[0]), np.arange(mnt_array.shape[1]), indexing="ij"
        )
        # print(mnt_array.shape[0], mnt_array.shape[1])
        # print(len(x_grid), len(y_grid))
        # mask = np.zeros(mnt_array.shape[1:], dtype="uint8")
        center_x, center_y = rasterio.transform.rowcol(
            mnt_transform, init_point[0], init_point[1]
        )
        print(center_y, center_x)
        prev_point_x, prev_point_y = rasterio.transform.rowcol(
            mnt_transform, prev_point[0], prev_point[1]
        )
        mask_radius = np.ceil(
            np.sqrt(
                (prev_point_x - center_x) * (prev_point_x - center_x)
                + (prev_point_y - center_y) * (prev_point_y - center_y)
            )
        )
        # convert meters to pixels

        disc_search = (
            (x_grid - center_x) ** 2 + (y_grid - center_y) ** 2
        ) <= search_radius**2
        disc_mask = (
            (x_grid - prev_point_x) ** 2 + (y_grid - prev_point_y) ** 2
        ) >= mask_radius**2
        circle = np.logical_and(disc_search, disc_mask)
        # print(circle)
        # All data outside the search area are set to 0
        # print(circle.shape)
        # input(mnt_array.shape)
        mnt_array[~circle] = 0

        # search maximum in area
        # print(np.amax(mnt_array))
        alt.append(np.amax(mnt_array))

        l_indices = np.where(mnt_array == [np.amax(mnt_array)])
        new_x, new_y = rasterio.transform.xy(mnt_transform, l_indices[0], l_indices[1])
        # print(init_point)
        # print(new_x, new_y)
        stop = False
        if alt[-1] > alt_max:
            stop = True
        if (new_x[0], new_y[0]) in list(row.geometry.coords):
            print("point already found")
            stop = True
        else:
            if len(alt) > 2:
                if alt[-1] <= alt[-2]:
                    stop = True
                    print("Stop")
        if not stop:
            if direction == "left":
                # input(type(row))
                s = shapely.intersection(
                    LineString([(new_x[0], new_y[0]), list(row.geometry.coords)[0]]),
                    row.geometry,
                )
                # If another point than the origin is found as intersection
                if isinstance(s, shapely.geometry.MultiPoint):
                    print("Je croise")
                    stop = True
                    # input(s)
                else:
                    row.geometry = LineString(
                        [(new_x[0], new_y[0])] + list(row.geometry.coords)
                    )
            else:
                s = shapely.intersection(
                    LineString([(new_x[0], new_y[0]), list(row.geometry.coords)[-1]]),
                    row.geometry,
                )
                if isinstance(s, shapely.geometry.MultiPoint):
                    print("Je croise")
                    stop = True
                    # input(s)
                else:
                    row.geometry = LineString(
                        list(row.geometry.coords) + [(new_x[0], new_y[0])]
                    )

        # input(l_indices)

        # profile = mnt.profile

        # # profile.update({"width": mnt_array.shape[0], "height": mnt_array.shape[1]})
        # print(profile)
        # with rasterio.open(
        #     f"/home/btardy/Documents/activites/WATER/GDP/test_chain_3/circle_{direction}_{j}.tif",
        #     "w",
        #     **mnt.profile,
        # ) as out:
        #     out.write(disc_search[None, :, :])
        # with rasterio.open(
        #     f"/home/btardy/Documents/activites/WATER/GDP/test_chain_3/circle_mask_{direction}_{j}.tif",
        #     "w",
        #     **mnt.profile,
        # ) as out:
        #     out.write(disc_mask[None, :, :])
        # with rasterio.open(
        #     f"/home/btardy/Documents/activites/WATER/GDP/test_chain_3/test_mask_{direction}_{j}.tif",
        #     "w",
        #     **mnt.profile,
        # ) as out:
        #     out.write(mnt_array[None, :, :])
        # print(mask_radius)
        # print(center_x, center_y)
        # print(mask.shape)
        # print(dir(mnt))
        return row, stop, alt


def compute_distance(point1, point2, thresholding: Optional[str] = None):
    """."""
    if thresholding == "max":
        dist = np.ceil(
            np.sqrt(
                (point1[0] - point2[0]) * (point1[0] - point2[0])
                + (point1[1] - point2[1]) * (point1[1] - point2[1])
            )
        )
    elif thresholding == "min":
        dist = np.floor(
            np.sqrt(
                (point1[0] - point2[0]) * (point1[0] - point2[0])
                + (point1[1] - point2[1]) * (point1[1] - point2[1])
            )
        )
    else:
        dist = np.sqrt(
            (point1[0] - point2[0]) * (point1[0] - point2[0])
            + (point1[1] - point2[1]) * (point1[1] - point2[1])
        )
    return dist


def fill_cutline(
    gdf_line, mnt_raster, water_body_raster, work_dir, alt_max, resolution=10
):
    """."""
    gdf_out = gdf_line.copy()
    print(gdf_out)
    # Extraire chaque ligne du dataframe
    all_lines = []
    masked_mnt = os.path.join(work_dir, "masked_mnt.tif")
    with rasterio.open(mnt_raster) as mnt:
        with rasterio.open(water_body_raster) as wbr:
            mnt_array = mnt.read()
            wbr_array = wbr.read()
            mnt_array = np.where(wbr_array > 0, 0, mnt_array)
            with rasterio.open(masked_mnt, "w", **mnt.profile) as out:
                out.write(mnt_array)

    for i, row in gdf_line.iterrows():
        # input(row)
        print("process ligne: ", i)
        current_size = np.floor(row.geometry.length / resolution)
        line = list(row.geometry.coords)
        left_point = line[0]
        prev_left_point = line[1]
        right_point = line[-1]
        prev_right_point = line[-2]
        dist_left = compute_distance(prev_left_point, left_point)
        dist_right = compute_distance(prev_left_point, left_point)
        search_distance = min([current_size / 2, dist_left, dist_right])
        # if current_size < search_size:
        #     print("The initial cutline is small. Use the length to found new points")

        # search left
        stop = False
        j = 0
        alt = []
        while not stop:
            # line = list(gdf_line.iloc[i].geometry.coords)
            line = list(row.geometry.coords)
            # print(line)
            # row.geometry = LineString([(1, 1)] + line)
            # input(row)
            # print(len(line))
            # Prendre les 2 points extrème de chaque cotés
            left_point = line[0]
            prev_left_point = line[1]
            right_point = line[-1]
            prev_right_point = line[-2]
            # Chercher dans un radius de N le point le plus haut
            row, stop, alt = search_point(
                left_point,
                prev_left_point,
                row,
                "left",
                masked_mnt,
                search_distance,
                alt,
                alt_max,
            )
            j += 1
        # search right
        stop = False
        j = 0
        alt = []
        while not stop:
            # line = list(gdf_line.iloc[i].geometry.coords)
            # current_size = np.floor(row.geometry.length / resolution)
            # if current_size < search_size:
            #     print(
            #         "The initial cutline is small. Use the length to found new points"
            #     )
            line = list(row.geometry.coords)
            # row.geometry = LineString([(1, 1)] + line)
            # input(row)
            # print(len(line))
            # Prendre les 2 points extrème de chaque cotés
            right_point = line[-1]
            prev_right_point = line[-2]
            # Chercher dans un radius de N le point le plus haut
            row, stop, alt = search_point(
                right_point,
                prev_right_point,
                row,
                "right",
                masked_mnt,
                search_distance,
                alt,
                alt_max,
            )
            j += 1
        all_lines.append(row.geometry)
        print(all_lines)
    # gdf_out.geometry = all_lines
    if len(all_lines) > 1:
        lines_merged = linemerge(all_lines)
        all_lines = list(lines_merged.geoms)

    gdf_final = gpd.GeoDataFrame(
        {"id_cutline": range(len(all_lines))}, geometry=all_lines, crs=gdf_out.crs
    )
    # gdf_out = filter_by_convex_hull(gdf_out, work_dir, "gdp_unique_id")
    #     left_part = search_line(left_point, gdf_line, mnt_raster, buffer_size, alt_max)
    #     left_part.reverse()
    #     right_part = search_line(
    #         right_point, gdf_line, mnt_raster, buffer_size, alt_max
    #     )
    #     line = left_part + line
    #     line += right_part
    #     print(len(line))
    #     all_lines.append(LineString(line))
    #     # gdf_out.iloc[i].geometry = LineString(line)
    #     # Assurer qu'on ne revient pas en arrière
    # gdf_out.geometry = all_lines
    # print(gdf_out)
    return gdf_final


# ##############################################
# Process
# ##############################################
def prepare_inputs(in_vector, mnt_raster, work_dir, gdp_buffer_size, alt_max):
    """."""
    if not os.path.exists(work_dir):
        os.mkdir(work_dir)
    with rasterio.open(mnt_raster) as mnt:
        epsg = mnt.crs.to_epsg()
        # 1 Handle mutlipolygons
        # 2 remove holes
        gdf_bd = preprocess_water_body(in_vector, epsg)
        gdf_bd.to_file(os.path.join(work_dir, "bd_clean.geojson"))
        # 4 Rasterize the waterbody filtered
        params_raster = RasterizarionParams(
            mode="binary",
            binary_foreground_value=1,
            background_value=0,
            column_field=None,
            dtype="uint8",
            nodata=0,
        )
        waterbody_bin = os.path.join(work_dir, "waterbody_bin.tif")

        rasterize(gdf_bd, mnt, params_raster, waterbody_bin)
        # 5 run GDP
        gdp_raster = os.path.join(work_dir, "gdp_raster.tif")
        compute_gradient_product(waterbody_bin, mnt_raster, gdp_raster)
        # 6 Vectorize
        # params_poly = PolygonizeParams(
        #     layer_name="output", field_name="DN", driver="GeoJson", overwrite=True
        # )
        gdp_vector = os.path.join(work_dir, "gdp_vector.geojson")
        polygonize(gdp_raster, gdp_vector)
        gdf_gdp = clear_polygonize(gdp_vector, epsg)
        # 7 Relier les polygones GDP proches
        # TODO compute area w.r.t the waterbody whole area
        gdf_gdp = gdf_gdp.loc[gdf_gdp.geometry.area > 2000]
        # find intersection according the max distance
        gdf_gdp.geometry = gdf_gdp.geometry.buffer(gdp_buffer_size)
        # then fuse
        gdf_gdp = gdf_gdp.dissolve(by="DN")
        # remove the buffer
        gdf_gdp.geometry = gdf_gdp.geometry.buffer(-gdp_buffer_size)
        # then separe into unique object
        gdf_gdp = gdf_gdp.explode(ignore_index=True)
        # dissolve remove the DN column
        gdf_gdp["gdp_unique_id"] = range(len(gdf_gdp.index))
        gdf_gdp.to_file(os.path.join(work_dir, "gdp_fusion_nearest.geojson"))

        gdf_gdp = filter_by_convex_hull(gdf_gdp, work_dir, "gdp_unique_id")
        # 8 Convertir la BD en points
        gdf_bd["wb_unique_id"] = range(len(gdf_bd.index))
        gdf_wb_points = convert_geodataframe_poly_to_points(
            gdf_bd, "wb_unique_id", "id_point"
        )
        gdf_wb_points.to_file(os.path.join(work_dir, "contour_points.geojson"))

        # 9 Draw line
        gdf_gdp_points = convert_geodataframe_poly_to_points(
            gdf_gdp, "gdp_unique_id", "gdp_point", suffix="_gdp"
        )
        gdf_gdp_points.to_file(os.path.join(work_dir, "pdb_contour.geojson"))
        lines = draw_lines(gdf_wb_points, gdf_gdp, gdf_bd)  # _points)
        lines.to_file(os.path.join(work_dir, "cutline_base.geojson"))
        lines = fill_cutline(lines, mnt_raster, waterbody_bin, work_dir, alt_max)
        lines.to_file(os.path.join(work_dir, "cutline.geojson"))


prepare_inputs(
    "/home/btardy/Documents/activites/WATER/GDP/extract/Laparan/laparan_bd.geojson",
    "/home/btardy/Documents/activites/WATER/GDP/extract/Laparan/dem_extract_Laparan.tif",
    "/home/btardy/Documents/activites/WATER/GDP/Laparan_chain",
    100,
    1700,
)

prepare_inputs(
    "/home/btardy/Documents/activites/WATER/GDP/extract/Naussac/naussac_bd.geojson",
    "/home/btardy/Documents/activites/WATER/GDP/extract/Naussac/dem_extract_Naussac.tif",
    "/home/btardy/Documents/activites/WATER/GDP/Naussac_chain",
    100,
    10000,
)
prepare_inputs(
    "/home/btardy/Documents/activites/WATER/GDP/extract/Marne-Giffaumont/extract_marne_inpe_noholes.geojson",
    "/home/btardy/Documents/activites/WATER/GDP/extract/Marne-Giffaumont/dem_extract_Marne-Giffaumont.tif",
    "/home/btardy/Documents/activites/WATER/GDP/Marne_chain",
    100,
    157,
)

prepare_inputs(
    "/home/btardy/Documents/activites/WATER/GDP/extract/Vaufrey/vaufrey_bd.geojson",
    "/home/btardy/Documents/activites/WATER/GDP/extract/Vaufrey/dem_extract_Vaufrey.tif",
    "/home/btardy/Documents/activites/WATER/GDP/Vaufrey_chain",
    100,
    420,
)

# lines = fill_cutline(
#     gpd.GeoDataFrame().from_file(
#         "/home/btardy/Documents/activites/WATER/GDP/Marne_chain/snap_test.geojson"
#     ),
#     "/home/btardy/Documents/activites/WATER/GDP/extract/Marne-Giffaumont/dem_extract_Marne-Giffaumont.tif",
#     "/home/btardy/Documents/activites/WATER/GDP/test_chain_3/waterbody_bin.tif",
#     "/home/btardy/Documents/activites/WATER/GDP/test_chain_3/",
#     alt_max=170,
# )
# lines.to_file(
#     os.path.join(
#         "/home/btardy/Documents/activites/WATER/GDP/test_chain_3/",
#         "cutline_snap.geojson",
#     )
# )
