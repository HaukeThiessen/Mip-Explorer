# Mip Explorer
#  Copyright (c) Hauke Thiessen
#
#  ---------------------------------------------------------------------------
#
#  This software is provided 'as-is', without any express or implied
#  warranty. In no event will the authors be held liable for any damages
#  arising from the use of this software.
#
#  Permission is granted to anyone to use this software for any purpose,
#  including commercial applications, and to alter it and redistribute it
#  freely, subject to the following restrictions:
#
#  1. The origin of this software must not be misrepresented; you must not
#     claim that you wrote the original software. If you use this software
#     in a product, an acknowledgment in the documentation is be
#     appreciated but not required.
#
#  2. Altered versions must be plainly marked as such, and must not be
#     misrepresented as being the original software.
#
#  3. This notice may not be removed or altered from any source distribution.
#
#  ---------------------------------------------------------------------------


import cv2
import math
import numpy as np

from enum import Enum


SUPPORTEDFORMATS = {
    "*.bmp",
    "*.dib",
    "*.jpeg",
    "*.jpg",
    "*.jpe",
    "*.jp2",
    "*.png",
    "*.webp",
    "*.pbm",
    "*.pgm",
    "*.ppm",
    "*.pxm",
    "*.pnm",
    "*.sr",
    "*.ras",
    "*.tiff",
    "*.tif",
    "*.tga",
    "*.pic"
}


class TextureType(Enum):
    COLOR = 0
    DATA = 1
    CHANNELS = 2
    NORMAL = 3
    MAX = 4


def normalize_RGB(vec):
    length = np.sqrt(vec[:,:,0]**2 + vec[:,:,1]**2 + vec[:,:,2]**2)
    length = np.clip(length, a_min=0.0001, a_max=10.0)
    vec[:,:,0] = vec[:,:,0] / length
    vec[:,:,1] = vec[:,:,1] / length
    vec[:,:,2] = vec[:,:,2] / length
    return vec

def get_image_from_file(filepath: str) -> np.ndarray:
    image: np.ndarray = np.empty(0)
    try:
        if filepath.endswith(".tga"):
            cap = cv2.VideoCapture(filepath, cv2.CAP_FFMPEG)
            image = cap.read(image)[1]
        else:
            image = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        image = image.astype(float) / 255
        return image
    except:
        print("Failed to open " + filepath)
        pass
    return image


def float_to_uint8(texture):
    texture = texture * 255
    return texture.astype(np.uint8)


def transform_normal_map_to_vectors(image: np.ndarray, normalize: bool = True) -> np.ndarray:
    """
    Since normal maps can only store values in a 0-1 range instead of -1-1, an offset and 2x scale is needed to get a proper normal vector
    """
    image = image[:,:,:3]
    image = image - [0.5, 0.5, 0.5]
    image = image * [2.0, 2.0, 2.0]
    if normalize:
        image = normalize_RGB(image)
    return image

def transform_vectors_to_normal_map(image: np.ndarray) -> np.ndarray:
    """
    Since normal maps can only store values in a 0-1 range instead of -1-1, an offset and 2x scale is needed to get a proper normal vector
    """
    image = image[:,:,:3]
    image = image + [1.0, 1.0, 1.0]
    image = image / [2.0, 2.0, 2.0]
    return image

def resize(texture, scale: float):
    return cv2.resize(texture, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

def calculate_raw_deltas(filepath: str, b_all_mips: bool, is_normal_map: bool = False) -> list[list[float]]:
    """
    Calculates the differences between the mip maps of the texture. Returns a list of the deltas, from Mip0-Mip1 to Mip(last-1) to Mip(last)
    The deltas are per channel (3-4) by default, but are single floats for greyscale textures and normal maps.
    For normal maps, the deltas are not just the differences between the pixel values, but the dot product between the vectors, and mips
    will be normalized on creation.
    The function will fail if the file format is not one of the SUPPORTEDFORMATS.
    Results are mulitplied with 1000 to make the results easier to read. For non-normal textures, think of the values as kilo luminance.
    """
    multiplicator: float = 1000.0 # purely cosmetic
    try:
        current_mip = get_image_from_file(filepath)
        if is_normal_map:
            current_mip = transform_normal_map_to_vectors(current_mip)
        shorter_edge = min(current_mip.shape[0], current_mip.shape[1])
        loops: int = 1
        if b_all_mips:
            loops = int(math.log2(shorter_edge))
        deltas: list[list[float]] = []
        for x in range(loops):
            smaller_mip = current_mip
            smaller_mip = resize(smaller_mip, 0.5)
            if is_normal_map:
                smaller_mip = normalize_RGB(smaller_mip)
            next_mip = smaller_mip
            smaller_mip = resize(smaller_mip, 2.0)
            num_pixels = current_mip.__len__() * current_mip[0].__len__()
            if is_normal_map:
                dot_products = np.sum(current_mip * smaller_mip, axis=-1)
                diff_sum = np.sum(dot_products, axis = (0, 1))
                diff_sum = np.divide(diff_sum, num_pixels)
                diff_sum = 1.0 - diff_sum
                diff_sum = diff_sum * multiplicator
                deltas.append(diff_sum)
            else:
                diff = cv2.absdiff(current_mip, smaller_mip) # nested array with x entries, each containing y pixels with 3-4 channels
                diff_sum = np.sum(diff, axis = (0, 1))
                diff_sum = np.divide(diff_sum, num_pixels)
                diff_sum = diff_sum * multiplicator
                deltas.append(diff_sum.tolist())
            current_mip = next_mip
        return deltas
    except:
        print("Failed to calculate deltas for " + filepath)
        return [[0.0, 0.0, 0.0]]


def interpret_deltas(raw_deltas: list[list[float]], texture_type: TextureType) -> list[list[float]] | list[float]:
    """
    Inteprets the raw deltas based on the texture type. For colors, the luminosity is calculated.
    For data, a simple average is used. For normal maps and channels, the values aren't changed.
    """
    if texture_type == TextureType.CHANNELS or type(raw_deltas[0]) != list:
        return raw_deltas

    has_alpha_channel = raw_deltas[0].__len__() == 4

    if texture_type == TextureType.NORMAL:
        angle_deltas: list[float] = []
        for delta in raw_deltas:
            angle_deltas.append(delta[2])
        return angle_deltas

    if has_alpha_channel:
        channel_weights = (0.165, 0.54, 0.052, 0.243) if texture_type == TextureType.COLOR else (0.25, 0.25, 0.25, 0.25)
    else:
        channel_weights = (0.22, 0.72, 0.07) if texture_type == TextureType.COLOR else (0.333, 0.333, 0.333)

    weighted_deltas: list[float] = []
    for delta in raw_deltas:
        if has_alpha_channel:
            weighted_deltas.append(
                delta[0] * channel_weights[0] +
                delta[1] * channel_weights[1] +
                delta[2] * channel_weights[2] +
                delta[3] * channel_weights[3]  # type: ignore #TODO: exchange with for loop for cleaner structure
            )
        else:
            weighted_deltas.append(
                delta[0] * channel_weights[0] +
                delta[1] * channel_weights[1] +
                delta[2] * channel_weights[2]
            )
    return weighted_deltas


def is_mip_mappable(width: int, height: int) -> bool:
    """
    Returns true if the width and height are powers of two
    """
    if width == 0 or height == 0:
        return False
    return (
        math.log(width, 2).is_integer()
        and math.log(height, 2).is_integer()
        and width > 3
        and height > 3
    )