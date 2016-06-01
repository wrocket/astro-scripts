#!/usr/bin/python3

# The MIT License (MIT)
#
# Copyright (c) 2016 Brian Wray (brian@wrocket.org)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

from PIL import Image
from multiprocessing import Pool
import datetime
import itertools
import os
import os.path
import subprocess
import sys
import tempfile

if len(sys.argv) < 3:
	print('Usage: %s [output_dir] [inputFrame1.jpg] [inputFrame2.jpg] ...' % sys.argv[0])
	quit(-1)


# Processing options class, for now just default values.
class ProcessingOpts:
	def __init__(self, output_dir):
		self.output_dir = output_dir

		# This is the threshold used to create the monochrome image used for centroid detection.
		# Suggested values are [1,10], lower numbers are better on dimmer images
		self.centroid_threshold_pct = 2

		# This is the sample stride sequence for locating the centroid; we'll search with each
		# value until we find a non-black pixel in the monochrome-ed image.
		self.centroid_stride_sequence_px = [64, 32, 16, 8, 4, 2, 1]

		# Once a centroid candidate pxel is found, check within a radius to find more pixels.
		self.centroid_search_radius_px = 150

		# Number of processors in the centroid pool.
		self.centroid_pool_size = 4

		# Crop each image to a size this many times the planet's size.
		# E.g. Frames with a maximum 100x100 planet will be cropped to 300x300 if possible.
		self.crop_ratio = 3.5

		# Process pool size for cropping.
		self.crop_pool_size = 4


# Class describing the image centroid's location and geometry.
class ImageCentroid:
	def __init__(self, center, size_x, size_y):
		self.center = center
		self.size_x = size_x
		self.size_y = size_y


# Given an array of numbers, returns (lowest, highest) if non-empty, else None
def extent(arr):
	if not arr or len(arr) == 0:
		return None
	arr_min = sys.maxsize
	arr_max = -sys.maxsize
	for x in arr:
		if x > arr_max:
			arr_max = x
		if x < arr_min:
			arr_min = x
	return (arr_min, arr_max)


def millis_between(start, end):
	diff = end - start
	return round(diff.total_seconds() * 1000)


# Returns true if a pixel is non-blank in a monochrome image, else false.
def centr_is_pixel_white(pixel):
	return pixel[0] > 10


# Finds a pixel in the centroid of a monochrome image. Returns the pxel if found, else None.
# Stride is the sample size; e.g. 32 means we'll sample along a lattice with a space 32 pixels.
# Lower numbers are slower but more accurate.
def centr_find_pixel(image, stride):
	x_range = range(0, image.size[0], stride)
	y_range = range(0, image.size[1], stride)
	for p in itertools.product(x_range, y_range):
		pixel = image.getpixel(p)
		if centr_is_pixel_white(pixel):
			return p
	return None


# Searches for all pixels in the centroid of a monochrome image centered around a given point and radius.
# Returns a non-None array of points containing the centroid.
def centr_search_pixels(image, radius, center):
	white_pixels = []
	min_x = max(0, center[0] - radius)
	min_y = max(0, center[1] - radius)
	max_x = min(image.size[0], center[0] + radius)
	max_y = min(image.size[1], center[1] + radius)
	for p in itertools.product(range(min_x, max_x), range(min_y, max_y)):
		pixel = image.getpixel(p)
		if centr_is_pixel_white(pixel):
			white_pixels.append(p)
	return white_pixels


def centr_scan_monochrome(mono_image, opts):
	with Image.open(mono_image) as im:
		center = None
		for stride in opts.centroid_stride_sequence_px:
			center = centr_find_pixel(im, stride)
			if center:
				break

		if not center:
			print('Unable to find centroid using search stride sequence of %s' %
				str(_stride_sequence_px), file=sys.stderr)
			return None

		white_pixels = centr_search_pixels(im, opts.centroid_search_radius_px, center)
		if len(white_pixels) == 0:
			print('Unable to find centroid around coordinate %d, %d' %
				center, file=sys.stderr)
			return None

		x_vals = list([p[0] for p in white_pixels])
		y_vals = list([p[1] for p in white_pixels])
		avg_x = sum(x_vals) / float(len(x_vals))
		avg_y = sum(y_vals) / float(len(y_vals))
		center_pt = (round(avg_x), round(avg_y))
		x_extent = extent(x_vals)
		y_extent = extent(y_vals)
		dx = x_extent[1] - x_extent[0]
		dy = y_extent[1] - y_extent[0]
		return ImageCentroid(center_pt, dx, dy)


# Locate and scan the centroid from an image containing a single, obvious centroid.
def find_center(input_image, opts):
	if not os.path.isfile(input_image):
		print('Error opening file %s, exiting' % input_image, file=sys.stderr)
		return None
	input_ext = os.path.splitext(input_image)[-1]
	temp_file = tempfile.mkstemp(suffix=input_ext)[1]
	try:
		cmd = ['convert', input_image, '-threshold', '%d%%' %
			opts.centroid_threshold_pct, temp_file]
		subprocess.check_output(cmd)
		return centr_scan_monochrome(temp_file, opts)
	finally:
		if os.path.isfile(temp_file):
			os.remove(temp_file)


def crop_calculate_size(center_infos, opts):
	size_x = max(i.size_x for i in center_infos)
	size_y = max(i.size_y for i in center_infos)
	return (size_x * opts.crop_ratio, size_y * opts.crop_ratio)


def log(input_image, message):
	fname = os.path.split(input_image)[-1]
	print('%s: %s' % (fname, message.strip()))

# Center and crop single frame.
def get_frame_centroid(input_image, opts):
	start = datetime.datetime.now()
	# Locate the center of the planet in the frame
	cent = find_center(input_image, opts)
	millis = millis_between(start, datetime.datetime.now())
	fname = os.path.split(input_image)[-1]
	if not cent:
		log(input_image, 'No centroid info found! (%ims)' % millis)
		return None
	center_str = '(%i, %i)' % (cent.center[0], cent.center[1])
	log(input_image, 'Found center at %s, size %ix%ipx (%ims)' %
		(center_str, cent.size_x, cent.size_y, millis))
	return (input_image, cent)


def pickle_centroid(args):
	return get_frame_centroid(*args)


def crop_on_center(input_image, center, image_size, opts):
	base_name = os.path.split(input_image)[-1]
	ext = os.path.splitext(base_name)
	out_file = os.path.join(opts.output_dir, '%s_aligned%s' % (ext[0], ext[1]))
	log(input_image, 'Crop to %ix%i, centered on (%i, %i), to file %s' %
		(image_size[0], image_size[1], center.center[0], center.center[1], out_file))
	cx = center.center[0] - round(image_size[0] / 2.0)
	cy = center.center[1] - round(image_size[1] / 2.0)
	args = ['convert', input_image, '-crop', '%dx%d+%d+%d' %
		(image_size[0], image_size[1], cx, cy), out_file]
	subprocess.check_output(args)


def pickle_crop(args):
	crop_on_center(*args)


def initialize(opts):
	if not os.path.exists(opts.output_dir):
		print('Creating output directory: %s' % opts.output_dir)
		os.makedirs(opts.output_dir)


opts = ProcessingOpts(sys.argv[1])
initialize(opts)

# Locate the planets and their pixel sizes in each frame
process_start = datetime.datetime.now()
arg_tuples = [(frame, opts) for frame in sys.argv[2:]]  
with Pool(opts.centroid_pool_size) as centroid_pool:
	crop_info = centroid_pool.map(pickle_centroid, arg_tuples)

filtered_crop_info = list(filter(lambda x: x != None, crop_info))
if len(crop_info) != len(filtered_crop_info):
	print('WARNING: Some frames were dicarded after alignment.')

print('Completed centroid detection step in %ims' %
	millis_between(process_start, datetime.datetime.now()))

# Calculate the frame size of the resulting frames from each frame's dimensions and location
crop_size = crop_calculate_size([x[1] for x in filtered_crop_info], opts)
print('Output frames will be of size %ix%i' % (crop_size[0], crop_size[1]))

# Perform the crop/center operation on each frame.
crop_args = [(c[0], c[1], crop_size, opts) for c in filtered_crop_info]
with Pool(opts.crop_pool_size) as crop_pool:
	crop_pool.map(pickle_crop, crop_args)
