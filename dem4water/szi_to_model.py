#!/usr/bin/env python3
"""From Szi compute model."""
import argparse
import json
import logging
import math
import os
import sys
from statistics import median
from time import perf_counter

import numpy as np

from dem4water import compute_model as cm
from dem4water import plot_lib as pl


logger = logging.getLogger("szi_to_model")
log = logging.getLogger()
log.setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("matplotlib").setLevel(logging.ERROR)


def found_mae_first(
    found_first,
    l_mae,
    l_i,
    l_z,
    l_beta,
    l_alpha,
    l_p,
    best_i,
    best_p,
    best,
    best_alpha,
    best_beta,
):
    """Analyze MAE to find the first local minimum."""
    logger.debug("Reanalizing local mae to find the first local minimum.")
    logger.debug(f"len(l_mae): {len(l_mae)}")
    if len(l_i) > 4:
        if l_mae[0] < l_mae[1] and l_mae[0] < l_mae[2]:
            found_first = True
            logger.debug(f"First local minimum found at {l_z[0]} (i= {l_i[0]}).")

            best_i = l_i[0]
            best_p = l_p[0]
            best = l_mae[0]
            best_beta = l_beta[0]
            best_alpha = l_alpha[0]
            logger.debug(

                f"i: {best_i} - alpha= {best_alpha} - "
                f"beta= {best_beta} - mae= {best}"
            )

        elif l_mae[1] < l_mae[0] and l_mae[1] < l_mae[2] and l_mae[1] < l_mae[3]:
            found_first = True
            logger.debug(f"First local minimum found at {l_z[1]} (i= {l_i[1]}).")

            best_i = l_i[1]
            best_p = l_p[1]
            best = l_mae[1]
            best_beta = l_beta[1]
            best_alpha = l_alpha[1]
            logger.debug(
                f"i: {best_i} - alpha= {best_alpha} - "
                f"beta= {best_beta} - mae= {best}"
            )

        else:
            x = range(0, len(l_i) - 1)
            logger.debug(x)

            for j in x[2:-2]:
                if (
                    l_mae[j] < l_mae[j - 2]
                    and l_mae[j] < l_mae[j - 1]
                    and l_mae[j] < l_mae[j + 1]
                    and l_mae[j] < l_mae[j + 2]
                ):
                    found_first = True
                    logger.debug(
                        f"First local minimum found at {l_z[j]} (i= {l_i[j]})."
                    )
                    best_i = l_i[j]
                    best_p = l_p[j]
                    best = l_mae[j]
                    best_beta = l_beta[j]
                    best_alpha = l_alpha[j]
                    logger.debug(
                        f"i: {best_i} - alpha= {best_alpha} - beta= {best_beta} - mae= {best}"
                    )
                    break

            if found_first is False:
                logger.info(
                    "Reanalizing local mae to find the first local minimum --> FAILLED."
                )
                # Exception ?
    else:
        logger.debug("Reanalizing Impossible, not enough local mae data!")
        # Exception ?
    return best_i, best_p, best, best_alpha, best_beta, found_first


def found_mae_hybrid(
    z_i,
    s_zi,
    l_i,
    l_z,
    zmaxoffset,
    zminoffset,
    dslopethresh,
    winsize,
    damname,
    damelev,
    l_p,
    l_mae,
    l_beta,
    l_alpha,
    l_slope,
    best_i,
    best_p,
    best,
    best_alpha,
    best_beta,
):
    """Analyze local mae to find optimal local minimum."""
    logger.debug("Reanalizing local mae to find the optimal local minimum.")
    best = -10000
    x = range(0, len(l_i) - 1)
    for j in x:
        #  logger.debug("j: "+ str(j)
        #  +" - l_z[j]: "+ str(l_z[j]))
        if (
            l_z[j] <= zmaxoffset + float(damelev)
            and l_z[j] >= float(damelev)
            and ((best == -10000) or (l_mae[j] < best))
        ):
            best_j = j
            best_z = l_z[j]
            best_i = l_i[j]
            best_p = l_p[j]
            best = l_mae[j]
            best_beta = l_beta[j]
            best_alpha = l_alpha[j]
            logger.debug(
                f"j: {best_j} - alpha= {best_alpha} - beta= "
                f"{best_beta} - mae= {best}@{best_z}m"
            )
    logger.info(
        f"Hybrid pass #1 => i: {best_i} - alpha= {best_alpha} "
        f"- beta= {best_beta} - mae= {best}@{best_z}m"
    )

    # then refine with a local lmae minima for smaller Zs
    # and until the slope "breaks"
    x = range(0, best_j - 1)
    ds = np.diff(l_slope) / np.diff(l_z)
    for k in x[::-1]:
        if l_z[k] >= float(damelev) - zminoffset and abs(ds[k]) < dslopethresh:
            # and
            #  (l_mae[k] < best)):

            logger.debug(
                "k: %s - lmae[k]: %s - l_z[k]: %s - ds[k]: %s",
                str(k),
                str(l_mae[k]),
                str(l_z[k]),
                str(ds[k]),
            )
            best_z = l_z[k]
            best_i = l_i[k]
            best_p = l_p[k]
            best = l_mae[k]
            best_beta = l_beta[k]
            best_alpha = l_alpha[k]
        else:
            break
    logger.info(
        f"Hybrid pass #2 => i: {best_i} - alpha= {best_alpha} - beta= "
        f"{best_beta} - mae= {best}@{best_z}m"
    )


    logger.info("Model updated using hybrid optimal model selection.")
    logger.info(
        f"alpha= {best_alpha} - beta= {best_beta}"
        f" (Computed on the range [{z_i[best_i]}; {z_i[best_i + winsize]}])"
        f" (i= {best_i})."
    )
    logger.info(
        f"{damname}: S(Z) = {s_zi[0]:.2F} + {best_alpha:.3E} "
        f"* ( Z - {z_i[0]:.2F} ) ^ {best_beta:.3E}"
    )
    return best_i, best_p, best, best_alpha, best_beta


def szi_to_model(
    szi_file,
    database,
    watermap,
    daminfo,
    winsize,
    maemode,
    outfile,
    zmaxoffset,
    zminoffset,
    dslopethresh,
    selection_mode,
    jump_ratio,
    filter_area,
    debug,
):  # noqa: C901  #FIXME: Function is too complex
    """
    Prototype scrip allowing to derive a HSV model from a set of S(Z_i) values.

    The first value of the set should be S_0 = S(Z_0) = 0 with Z_0 the altitude of dam bottom

    The output
    - the list of parameters [alpha;beta]
    - a quality measurment of how well the model fit the S(Z_i) values
    - additionnaly the plot of S(Z) and V(S)
    """
    t1_start = perf_counter()
    logging_format = (
        "%(asctime)s - %(filename)s:%(lineno)s - %(levelname)s - %(message)s"
    )
    if debug is True:
        logging.basicConfig(
            stream=sys.stdout, level=logging.DEBUG, format=logging_format
        )
    else:
        logging.basicConfig(
            stream=sys.stdout, level=logging.INFO, format=logging_format
        )

    logger.info("Starting szi_to_model.py")
    if filter_area not in ["enabled", "disabled"]:
        raise ValueError(
            f"{filter_area} is not a correct value for 'filter_area' parameter"
        )
    # load GeoJSON file containing info
    with open(daminfo, encoding="utf-8") as i:
        jsi = json.load(i)
    for feature in jsi["features"]:
        if feature["properties"]["name"] == "Dam":
            logger.debug(feature)
            damname = feature["properties"]["damname"]
            damelev = feature["properties"]["elev"]
            dam_id = feature["properties"]["ID"]
        # if feature["properties"]["name"] == "PDB":
        #     pdbelev = feature["properties"]["elev"]
    # shp_wmap = wb.create_water_mask(watermap, 0.05)
    # water_body_area = wb.compute_area_from_database_geom(database, damname, shp_wmap)
    # wm_thres = (water_body_area * 15)/100
    if filter_area == "enabled":
        logger.info("Filter small surfaces enabled.")
        z_i, s_zi = cm.filter_szi(szi_file, database, watermap, damname, 100000, 0)
    else:
        z_i = None
        s_zi = None
    z_i, s_zi = cm.remove_jump_szi(szi_file, z_i, s_zi, int(jump_ratio))
    logger.debug(f"Number of S_Zi used for compute model: {len(s_zi)}")
    z_i = z_i[::-1]
    s_zi = s_zi[::-1]
    # find start_i
    start_i = 0
    all_zi = z_i[:]
    all_szi = s_zi[:]
    if selection_mode == "firsts":
        z_i, s_zi = cm.select_lower_szi(z_i, s_zi, damelev, zmaxoffset, winsize)
        start_i = 1
    else:
        for alt in z_i:
            if alt > float(damelev) - zminoffset:
                logger.debug(f"start_i = : {start_i}  - search stopped at Zi = {alt}")
                break
            start_i = start_i + 1

            # TODO: if start_i equals len(Zi) this causes troubles for the rest of algorithm
    logger.info(f"Filtered : {z_i}, {s_zi}")
    logger.debug("z_i: ")
    logger.debug(z_i[:])
    logger.debug("s_zi: ")
    logger.debug(s_zi[:])
    logger.debug(f"Zi_max: {z_i[-1]} - S(Zi_max): {s_zi[-1]}")
    logger.info(f"Z0: {z_i[0]} - S(Z0): {s_zi[0]}")

    i = start_i
    best = -10000
    best_i = i
    best_p = 0
    best_alpha = 0
    best_beta = 0
    l_i = []
    l_z = []
    l_sz = []
    l_p = []
    l_slope = []
    l_mae = []
    l_alpha = []
    l_beta = []

    # Shortcut if just enough data
    data_shortage = False
    # autorise d'avoir un seul point...
    if (i + winsize) >= (len(z_i) - 1):
        data_shortage = True
        logger.warning("Just enough data! Compute unique model.")
        alpha, beta, mae, poly = cm.compute_model(z_i[1:], s_zi[1:], z_i[0], s_zi[0])
        logger.debug(
            f"Zrange [{z_i[0]} ; {z_i[-1]}] --> alpha= {alpha} - "
            f"beta= {beta}  with a local mae of: {mae} m2"
        )
        logger.debug(
            f"i: {i} - Slope= {poly[0]} - z_med= {median(z_i)} -"
            f" Sz_med= {median(s_zi)}"
        )

        # Select MEA to be used:
        best = mae

        best_i = 1

        best_p = poly
        best_alpha = alpha
        best_beta = beta

    # Enough data but not in specified distance to the dam
    # (maybe estimated dam elevation is false, maybe offsets are to strict)
    print(z_i, i, winsize)
    # TODO : mettre un elif
    # Test si z_i[] est pas vide
    if median(z_i[i : i + winsize]) >= zmaxoffset + float(damelev):
        data_shortage = True
        logger.error("zmaxoffset to restrictive, no S(Zi) data within search range.")
        logger.error("Maybe dam elevation estimation is not correct.")
        logger.warning("Computing unique model with the first available S(Zi) dataset.")
        alpha, beta, mae, poly = cm.compute_model(
            z_i[i : i + winsize], s_zi[i : i + winsize], z_i[0], s_zi[0]
        )

        logger.debug(
            f"i: {i} - Zrange [{z_i[i]}; {z_i[i + winsize]}] --> alpha="
            f" {alpha} - beta= {beta} with a local mae of: {mae} m2"
        )
        logger.debug(
            f"i: {i} - Slope= {poly[0]} - z_med= "
            f"{median(z_i[i : i + winsize])} - "
            f"Sz_med= {median(s_zi[i : i + winsize])}"
        )

        best = mae
        best_i = i
        best_p = poly
        best_alpha = alpha
        best_beta = beta

    # Si on est pas dans les deux premiers cas
    while ((i + winsize) < (len(z_i) - 1)) and (
        median(z_i[i : i + winsize]) < zmaxoffset + float(damelev)
    ):
        logger.debug(f"len(z_i[i:i+winsize]): {len(z_i[i : i + winsize])}")
        alpha, beta, loc_mae, poly = cm.compute_model(
            z_i[i : i + winsize], s_zi[i : i + winsize], z_i[0], s_zi[0]
        )
        logger.debug(
            f"i: {i} - Zrange [{z_i[i]}; {z_i[i + winsize]}] --> alpha="
            f" {alpha} - beta= {beta} with a local mae of: {loc_mae} m2"
        )
        logger.debug(
            f"i: {i} - Slope= {poly[0]} - z_med="
            f" {median(z_i[i : i + winsize])} - "
            f"Sz_med= {median(s_zi[i : i + winsize])}"
        )

        # Select MEA to be used:
        #  mae = glo_mae
        mae = loc_mae
        l_i.append(i)
        l_z.append(median(z_i[i : i + winsize]))
        l_sz.append(median(s_zi[i : i + winsize]))
        l_p.append(poly)
        l_slope.append(poly[0])
        l_mae.append(mae)
        l_alpha.append(alpha)
        l_beta.append(beta)

        if (best == -10000) or (mae < best):
            best = mae
            best_i = i
            best_p = poly
            best_alpha = alpha
            best_beta = beta
        i = i + 1

    # For testing
    abs_i = best_i
    # abs_P = best_p
    abs_mae = best
    abs_beta = best_beta
    abs_alpha = best_alpha
    logger.debug("Best Abs")
    logger.debug(f"i: {best_i} - alpha= {best_alpha} - beta= {best_beta} - mae= {best}")
    logger.info(
        f"{damname}: S(Z) = {s_zi[0]:.2F} + {best_alpha:.3E} "
        f"* ( Z - {z_i[0]:.2F} ) ^ {best_beta:.3E}"
    )

    found_first = False
    if maemode == "first" and data_shortage is False:
        best_i, best_p, best, best_alpha, best_beta, found_first = found_mae_first(
            found_first,
            l_mae,
            l_i,
            l_z,
            l_beta,
            l_alpha,
            l_p,
            best_i,
            best_p,
            best,
            best_alpha,
            best_beta,
        )
    elif maemode == "hybrid" and data_shortage is False:
        # first find absolute min at z > damelev > damelev+offset
        best_i, best_p, best, best_alpha, best_beta = found_mae_hybrid(
            z_i,
            s_zi,
            l_i,
            l_z,
            zmaxoffset,
            zminoffset,
            dslopethresh,
            winsize,
            damname,
            damelev,
            l_p,
            l_mae,
            l_beta,
            l_alpha,
            l_slope,
            best_i,
            best_p,
            best,
            best_alpha,
            best_beta,
        )
    if found_first is True:
        logger.info("Model updated using first LMAE minimum.")
        logger.info(
            f"alpha= {best_alpha} - beta= {best_beta}"
            f" (Computed on the range [{z_i[best_i]}; {z_i[best_i + winsize]}])"
            f" (i= {best_i})."
        )
        logger.info(
            f"{damname}: S(Z) = {s_zi[0]:.2F} + {best_alpha:.3E} *"
            f" ( Z - {z_i[0]:.2F}) ^ {best_beta:.3E}"
        )

    model_json = {
        "ID": dam_id,
        "Name": damname,
        "Elevation": damelev,
        "Model": {
            "Z0": z_i[0],
            "S0": s_zi[0],
            "V0": 0.0,
            "alpha": best_alpha,
            "beta": best_beta,
        },
    }

    with open(
        os.path.splitext(outfile)[0] + ".json", "w", encoding="utf-8"
    ) as write_file:
        json.dump(model_json, write_file)

    z = range(int(z_i[0]) + 1, int(z_i[-1]))
    mod_sz = []
    abs_sz = []
    for h in z:
        val_s = s_zi[0] + best_alpha * math.pow((h - z_i[0]), best_beta)
        mod_sz.append(val_s)
        val_s = s_zi[0] + abs_alpha * math.pow((h - z_i[0]), abs_beta)
        abs_sz.append(val_s)

    # Moldel Plot
    pl.plot_model(
        s_zi[best_i : best_i + winsize],
        z_i[best_i : best_i + winsize],
        z_i[0],
        s_zi[0],
        best_alpha,
        best_beta,
        damname,
        outfile,
    )

    # Plot Local MAE
    # TODO : call function plot_slope()
    pl.plot_slope(
        z_i[best_i : best_i + winsize],
        l_mae,
        damelev,
        z_i[abs_i : abs_i + winsize],
        abs_mae,
        best,
        damname,
        l_z,
        l_slope,
        best_p,
        os.path.splitext(outfile)[0] + "_slope.png",
    )

    # Combined Local MAE / model plot
    pl.plot_model_combo(
        all_zi,
        all_szi,
        z_i[best_i : best_i + winsize],
        s_zi[best_i : best_i + winsize],
        damelev,
        data_shortage,
        alpha,
        beta,
        damname,
        z,
        abs_sz,
        mod_sz,
        l_z,
        l_mae,
        abs_mae,
        best,
        os.path.splitext(outfile)[0] + "_combo.png",
    )

    # V(S)
    pl.plot_vs(
        z_i,
        s_zi,
        damelev,
        best_alpha,
        best_beta,
        damname,
        os.path.splitext(outfile)[0] + "_VS.png",
    )

    t1_stop = perf_counter()
    logger.info(f"Elapsed time: {t1_stop}s, {t1_start}s")

    logger.info(f"Elapsed time during the whole program in s :{t1_stop-t1_start}s")


def szi_to_model_parameters():
    """Define szi_to_model parser arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-szi_file", help="Input file")
    parser.add_argument("-daminfo", help="daminfo.json file")
    parser.add_argument("-watermap", help="Water map product")
    parser.add_argument("-database", help="The database geojson file with geometry")
    parser.add_argument(
        "-winsize", type=int, default=11, help="S(Zi) used for model estimation."
    )
    parser.add_argument(
        "-zmaxoffset",
        type=int,
        default=30,
        help="Elevation offset on top of dam elevation used for ending optimal model search",
    )
    parser.add_argument(
        "-zminoffset",
        type=int,
        default=10,
        help="Elevation offset from dam elevation used for starting optimal model search",
    )
    list_of_mode = ["absolute", "first", "hybrid"]
    parser.add_argument("-maemode", default="absolute", choices=list_of_mode)
    parser.add_argument(
        "-dslopethresh",
        default=1000,
        help="Threshold used to identify slope breaks in hybrid model selection",
    )
    parser.add_argument(
        "-selection_mode", type=str, default="best", help="best, firsts"
    )
    parser.add_argument(
        "-jump_ratio", type=str, default=10, help="Ratio between two surface"
    )

    parser.add_argument("-outfile", help="Output file")
    parser.add_argument("-debug", action="store_true", help="Activate Debug Mode")
    parser.add_argument(
        "-filter_area",
        type=str,
        default="disabled",
        help="Enable the filtering of low szi",
        choices=["enabled", "disabled"],
    )
    return parser


def main():
    """Cli for szi_to_model.py."""
    parser = szi_to_model_parameters()
    args = parser.parse_args()
    szi_to_model(
        args.szi_file,
        args.database,
        args.watermap,
        args.daminfo,
        args.winsize,
        args.maemode,
        args.outfile,
        args.zmaxoffset,
        args.zminoffset,
        args.dslopethresh,
        args.selection_mode,
        args.jump_ratio,
        args.filter_area,
        args.debug,
    )


if __name__ == "__main__":
    sys.exit(main())
