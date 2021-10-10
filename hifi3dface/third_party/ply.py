# original source: https://github.com/daavoo/pyntcloud/blob/master/pyntcloud/io/ply.py
#       HAKUNA MATATA

import sys
import numpy as np
import pandas as pd
from collections import defaultdict

sys_byteorder = (">", "<")[sys.byteorder == "little"]

ply_dtypes = dict(
    [
        (b"int8", "i1"),
        (b"char", "i1"),
        (b"uint8", "u1"),
        (b"uchar", "b1"),
        (b"uchar", "u1"),
        (b"int16", "i2"),
        (b"short", "i2"),
        (b"uint16", "u2"),
        (b"ushort", "u2"),
        (b"int32", "i4"),
        (b"int", "i4"),
        (b"uint32", "u4"),
        (b"uint", "u4"),
        (b"float32", "f4"),
        (b"float", "f4"),
        (b"float64", "f8"),
        (b"double", "f8"),
    ]
)

valid_formats = {"ascii": "", "binary_big_endian": ">", "binary_little_endian": "<"}


def read_ply(filename):
    """Read a .ply (binary or ascii) file and store the elements in pandas DataFrame
    Parameters
    ----------
    filename: str
        Path to the filename
    Returns
    -------
    data: dict
        Elements as pandas DataFrames; comments and ob_info as list of string
    """

    with open(filename, "rb") as ply:

        if b"ply" not in ply.readline():
            raise ValueError("The file does not start whith the word ply")
        # get binary_little/big or ascii
        fmt = ply.readline().split()[1].decode()
        # get extension for building the numpy dtypes
        ext = valid_formats[fmt]

        line = []
        dtypes = defaultdict(list)
        count = 2
        points_size = None
        mesh_size = None
        while b"end_header" not in line and line != b"":
            line = ply.readline()

            if b"element" in line:
                line = line.split()
                name = line[1].decode()
                size = int(line[2])
                if name == "vertex":
                    points_size = size
                elif name == "face":
                    mesh_size = size

            elif b"property" in line:
                line = line.split()
                # element mesh
                if b"list" in line:
                    mesh_names = ["n_points", "v1", "v2", "v3"]

                    if fmt == "ascii":
                        # the first number has different dtype than the list
                        dtypes[name].append((mesh_names[0], ply_dtypes[line[2]]))
                        # rest of the numbers have the same dtype
                        dt = ply_dtypes[line[3]]
                    else:
                        # the first number has different dtype than the list
                        dtypes[name].append((mesh_names[0], ext + ply_dtypes[line[2]]))
                        # rest of the numbers have the same dtype
                        dt = ext + ply_dtypes[line[3]]

                    for j in range(1, 4):
                        dtypes[name].append((mesh_names[j], dt))
                else:
                    if fmt == "ascii":
                        dtypes[name].append((line[2].decode(), ply_dtypes[line[1]]))
                    else:
                        dtypes[name].append(
                            (line[2].decode(), ext + ply_dtypes[line[1]])
                        )
            count += 1

        # for bin
        end_header = ply.tell()

    data = {}

    if fmt == "ascii":
        top = count
        bottom = 0 if mesh_size is None else mesh_size

        names = [x[0] for x in dtypes["vertex"]]

        data["points"] = pd.read_csv(
            filename,
            sep=" ",
            header=None,
            engine="python",
            skiprows=top,
            skipfooter=bottom,
            usecols=names,
            names=names,
        )

        for n, col in enumerate(data["points"].columns):
            data["points"][col] = data["points"][col].astype(dtypes["vertex"][n][1])

        if mesh_size is not None:
            top = count + points_size

            names = [x[0] for x in dtypes["face"]][1:]
            usecols = [1, 2, 3]

            data["mesh"] = pd.read_csv(
                filename,
                sep=" ",
                header=None,
                engine="python",
                skiprows=top,
                usecols=usecols,
                names=names,
            )

            for n, col in enumerate(data["mesh"].columns):
                data["mesh"][col] = data["mesh"][col].astype(dtypes["face"][n + 1][1])

    else:
        with open(filename, "rb") as ply:
            ply.seek(end_header)
            points_np = np.fromfile(ply, dtype=dtypes["vertex"], count=points_size)
            if ext != sys_byteorder:
                points_np = points_np.byteswap().newbyteorder()
            data["points"] = pd.DataFrame(points_np)
            if mesh_size is not None:
                mesh_np = np.fromfile(ply, dtype=dtypes["face"], count=mesh_size)
                if ext != sys_byteorder:
                    mesh_np = mesh_np.byteswap().newbyteorder()
                data["mesh"] = pd.DataFrame(mesh_np)
                data["mesh"].drop("n_points", axis=1, inplace=True)

    return data


def write_ply(filename, points=None, mesh=None, colors=None, as_text=False):
    points = pd.DataFrame(points, columns=["x", "y", "z"])
    mesh = pd.DataFrame(mesh, columns=["v1", "v2", "v3"])
    if colors is not None:
        colors = pd.DataFrame(colors, columns=["red", "green", "blue"])
        points = pd.concat([points, colors], axis=1)
    """

    Parameters
    ----------
    filename: str
        The created file will be named with this
    points: ndarray
    mesh: ndarray
    as_text: boolean
        Set the write mode of the file. Default: binary

    Returns
    -------
    boolean
        True if no problems

    """
    if not filename.endswith("ply"):
        filename += ".ply"

    # open in text mode to write the header
    with open(filename, "w") as ply:
        header = ["ply"]

        if as_text:
            header.append("format ascii 1.0")
        else:
            header.append("format binary_" + sys.byteorder + "_endian 1.0")

        if points is not None:
            header.extend(describe_element("vertex", points))
        if mesh is not None:
            mesh = mesh.copy()
            mesh.insert(loc=0, column="n_points", value=3)
            mesh["n_points"] = mesh["n_points"].astype("u1")
            header.extend(describe_element("face", mesh))

        header.append("end_header")

        for line in header:
            ply.write("%s\n" % line)

    if as_text:
        if points is not None:
            points.to_csv(
                filename, sep=" ", index=False, header=False, mode="a", encoding="ascii"
            )
        if mesh is not None:
            mesh.to_csv(
                filename, sep=" ", index=False, header=False, mode="a", encoding="ascii"
            )

    else:
        # open in binary/append to use tofile
        with open(filename, "ab") as ply:
            if points is not None:
                points.to_records(index=False).tofile(ply)
            if mesh is not None:
                mesh.to_records(index=False).tofile(ply)

    return True


def describe_element(name, df):
    """Takes the columns of the dataframe and builds a ply-like description

    Parameters
    ----------
    name: str
    df: pandas DataFrame

    Returns
    -------
    element: list[str]
    """
    property_formats = {"f": "float", "u": "uchar", "i": "int"}
    element = ["element " + name + " " + str(len(df))]

    if name == "face":
        element.append("property list uchar int vertex_indices")

    else:
        for i in range(len(df.columns)):
            # get first letter of dtype to infer format
            f = property_formats[str(df.dtypes[i])[0]]
            element.append("property " + f + " " + str(df.columns.values[i]))

    return element


def write_obj(obj_path, v_arr, vt_arr, tri_v_arr, tri_t_arr):
    """write mesh data to .obj file.

    Param:
      obj_path: path to .obj file
      v_arr   : N x 3 (x, y, z values for geometry)
      vt_arr  : N x 2 (u, v values for texture)
      f_arr   : M x 3 (mesh faces and their corresponding triplets)

    Returns:
      None
    """
    tri_v_arr = np.copy(tri_v_arr)
    tri_t_arr = np.copy(tri_t_arr)
    if np.amax(vt_arr) > 1 or np.amin(vt_arr) < 0:
        print("Error: the uv values should be ranged between 0 and 1")

    with open(obj_path, "w") as fp:
        fp.write("mtllib test.mtl\n")
        for x, y, z in v_arr:
            fp.write("v %f %f %f\n" % (x, y, z))
        # for u, v in vt_arr:
        #    fp.write('vt %f %f\n' % (v, 1-u))
        for u, v in vt_arr:
            fp.write("vt %f %f\n" % (u, v))

        tri_v_arr += 1
        tri_t_arr += 1
        for (v1, v2, v3), (t1, t2, t3) in zip(tri_v_arr, tri_t_arr):
            fp.write(
                "f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (v1, t1, t1, v2, t2, t2, v3, t3, t3)
            )


def read_obj(obj_path):
    vertices = []

    lines = open(obj_path, "r").readlines()
    for line in lines:
        if line.startswith("v "):
            toks = line.split(" ")[1:]
            vertices.append([float(toks[0]), float(toks[1]), float(toks[2])])
    return np.array(vertices)
