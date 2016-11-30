#!/usr/bin/env python
"""
Crops scanned pictures.  The scanned picture is larger than the actual picture,
with a mostly-white additional margin to the right and bottom of the picture.

There are multiple approaches to cropping in this script.  The most effective
one tries to identify vertical lines to the right of the photo and horizontal
lines below it that are mostly white.  When a line fails the test for mostly
white, it is considered the edge of the picture.

The other two approaches try to find the transition between margin and picture.
Arbitrarily picking one horizontal and one vertical line to follow to detect the
transition works very well except for photos where the photo color at along a
line is white at the edge.  To account for that, multiple lines can be probed.
When using the maximum point at which an edge appears to be detected, scanner
artifacts can lead to consistently bad crops.  The original scanner this script
was used with produced black artifacts that screwed up both right and bottom
edge detection.  Using the mode rather than the maximum produced better results.

Detecting the transition between scanner background and picture
uses multiple parameters that were chosen by hand based on some observations,
but which could be statistically fit based on more samples.

Ultimately, identifying lines of pixels that are likely to be scanner background
is straightforward and intuitively likely to be accurate with all photos that do
not have a featureless, white background at an edge.
"""

from collections import Counter
import logging
from math import sqrt
from os import listdir
from os.path import basename, isdir, isfile, join, splitext
from sys import exit, stderr

from PIL import Image

# Most of the scanned photos are 6x4.  The canonical scanned sizes are
# specified as "preferred crops".  Empirically determined sizes that are
# "close enough" to these are "rounded".

# 1770x1180 is 3:2 (6"x4" @ 295 dpi)
# 1180x1770 is 2:3 (4"x6" @ 295 dpi)
preferred_crops = [
  (1770, 1180),
  (1180, 1770)
]

def point_distance(point0, point1):
  """Returns the distance between two points specified as (x, y) tuples."""
  return sqrt((point1[0] - point0[0])**2 + (point1[1] - point0[1])**2)

def rgb_brightness(pixel):
  """Returns the brightness of a pixel specified as an (r, g, b) tuple."""
  return sqrt(((pixel[0] * pixel[0]) + (pixel[1] * pixel[1]) + (pixel[2] * pixel[2])) / 3)

def rgb_distance(pixel0, pixel1):
  """Returns the 'distance' between the RGB color of two pixels."""
  return sqrt((pixel1[0] - pixel0[0])**2 + (pixel1[1] - pixel0[1])**2 + (pixel1[2] - pixel0[2])**2)

def rgb_neighbor_distance(image, point, n, do_x, do_after):
  """
  Returns the average RGB color distance between the pixel at a point and its
  'n' nearest neighbors before or after it in the x or y dimension.  When there
  are fewer than 'n' nearest neighbors in the specified direction and dimension,
  only the ones available are averaged.  If there are none (i.e. the point is
  on an edge of the image), 0 is returned.
  """
  rgb = image.getpixel(point)
  x, y = point
  deltas = range(1, n+1, 1) if do_after else range(-1, -(n+1), -1)
  points = 0
  sum = 0
  for delta in deltas:
    try:
      if do_x:
        sum += rgb_distance(rgb, image.getpixel((x + delta, y)))
      else:
        sum += rgb_distance(rgb, image.getpixel((x, y + delta)))
      points += 1
    except IndexError:
      pass

  return sum / points if points > 0 else 0

def rgb_brightness_of_one_line(image, margin, line_index, do_x):
  """
  Returns the average brightness of pixels on a line.  It skips points for a
  specified margin at the start and end of the line.
  """
  brightness = 0
  points = 0
  for position in xrange(margin, image.size[0] - margin if do_x else image.size[1] - margin, 1):
    point = (position, line_index) if do_x else (line_index, position)
    brightness += rgb_brightness(image.getpixel(point))
    points += 1
    
  return brightness / points if points > 0 else 0

def find_edge_using_brightness(image, margin, do_x):
  """
  Returns a photo edge using line brightness to identify lines that are scanner
  background rather than the photo.  It skips points for a specified margin
  at the start and end of each line.
  """
  edge = None
  for line_index in xrange(image.size[0] - 1 if do_x else image.size[1] - 1, -1, -1):
    brightness = rgb_brightness_of_one_line(image, margin, line_index, not do_x)
    logging.debug('do_x: {} line_index: {}, brightness: {}'.format(do_x, line_index, brightness))
    if edge is None:
      if brightness < 240:
        edge = line_index
    else:
      # for debugging, we process extra lines
      if line_index < edge - 16:
        break

  return line_index

def find_edge_of_one_line(image, minimum, line_index, neighbors, threshold, do_x):
  """
  Returns the edge of the photo for one line.  The edge is identified by a
  transition in the color distance of pixels before and after each point when
  moving along a line from the edge of the scan toward the picture.  There are
  several parameters used when detecting the transition.
  """
  passed_threshold = False
  for position in xrange(image.size[0] - 1 if do_x else image.size[1] - 1, minimum-1, -1):
    point = (position, line_index) if do_x else (line_index, position)
    pre = rgb_neighbor_distance(image, point, neighbors, do_x, False)
    post = rgb_neighbor_distance(image, point, neighbors, do_x, True)
    logging.debug('{}: pixel = {} brightness = {} pre = {} post = {}'.format(point, image.getpixel(point), rgb_brightness(image.getpixel(point)), pre, post))
    if not passed_threshold:
      if (pre - post) >= threshold:
        passed_threshold = True
    else:
      if (post - pre) >= threshold:
        return position

  return None

def find_edge(image, minimum, margin, neighbors, threshold, do_x):
  """
  Returns an edge identified by the transition of color distance between
  pixels and their neighbors along a line.  Two calculations are performed
  and thus two values are returned as a tuple.  The first element of the tuple
  is the maximum edge along any probed line.  The scanner on which this script
  was first tested, artifacts present in all scans prevented the maximum from
  being accurate (using the chosen parameterization).  The second element of the
  tuple is the mode of values for all probed lines.  This produces generally
  good results.
  """
  edge = -1
  edge_frequency = Counter()
  for line_index in xrange(margin, image.size[1] - margin if do_x else image.size[0] - margin, neighbors / 2):
    e = find_edge_of_one_line(image, minimum, line_index, neighbors, threshold, do_x)
    if e is not None:
      edge_frequency[e] += 1
      if e > edge:
        edge = e
        logging.info('Updated {} edge to {} at {}={}'.format('x' if do_x else 'y', e, 'y' if do_x else 'x', line_index))

  return (edge if edge >= 0 else -1, edge_frequency.most_common(1)[0][0])

def maybe_conform_crop(crop_point):
  """
  Returns the crop point, possibly changed to conform to one of the preferred
  crop sizes.
  """
  for crop in preferred_crops:
    dist = point_distance(crop, crop_point)
    logging.debug('{}: distance = {}'.format(crop, dist))
    if dist < CONFORM_POINT_DISTANCE_THRESHOLD:
      return crop

  return crop_point

MINIMUM_DIMENSION = 480
EDGE_SEARCH_MARGIN = 20
EDGE_RGB_DISTANCE_NEIGHBORS = 8
EDGE_RGB_DISTANCE_THRESHOLD = 75
CONFORM_POINT_DISTANCE_THRESHOLD = 16

def crop_scan_using_brightness(image_path, crop_dir):
  """
  Crops one scanned image using brightness of lines to identify scanner
  background versus photo.
  """
  image = Image.open(image_path)
  logging.info('{} format: {} size: {} mode: {}'.format(image_path, image.format, image.size, image.mode))
  
  if image.mode != 'RGB':
    print >>stderr, 'Not sure what to do with image mode {}'.format(image.mode)
    exit(1)
  
  edge_x = find_edge_using_brightness(image, EDGE_SEARCH_MARGIN, True)
  edge_y = find_edge_using_brightness(image, EDGE_SEARCH_MARGIN, False)

  logging.info('edge_x: {} edge_y: {}'.format(edge_x, edge_y))
  
  crop = maybe_conform_crop((edge_x, edge_y))

  cropped_path = join(crop_dir, basename(image_path))
  logging.info('crop size: {} path: {}'.format(crop, cropped_path))
  cropped_image = image.crop((0, 0, crop[0], crop[1]))
  cropped_image.save(cropped_path)

def crop_scan(image_path, crop_dir):
  """
  Crops one scanned image using color distance changes to identify the
  transition from background to picture.
  """
  image = Image.open(image_path)
  logging.info('{} format: {} size: {} mode: {}'.format(image_path, image.format, image.size, image.mode))
  
  if image.mode != 'RGB':
    print >>stderr, 'Not sure what to do with image mode {}'.format(image.mode)
    exit(1)
  
  edge_x, mode_x = find_edge(image, MINIMUM_DIMENSION, EDGE_SEARCH_MARGIN, EDGE_RGB_DISTANCE_NEIGHBORS, EDGE_RGB_DISTANCE_THRESHOLD, True)
  edge_y, mode_y = find_edge(image, MINIMUM_DIMENSION, EDGE_SEARCH_MARGIN, EDGE_RGB_DISTANCE_NEIGHBORS, EDGE_RGB_DISTANCE_THRESHOLD, False)
  
  logging.info('edge_x: {} edge_y: {}'.format(edge_x, edge_y))
  
  crop = maybe_conform_crop((edge_x, edge_y))

  cropped_path = join(crop_dir, basename(image_path))
  logging.info('crop size: {} path: {}'.format(crop, cropped_path))
  cropped_image = image.crop((0, 0, crop[0], crop[1]))
  cropped_image.save(cropped_path)

  logging.info('mode_x: {} mode_y: {}'.format(mode_x, mode_y))

  crop = maybe_conform_crop((mode_x, mode_y))

  split_name = splitext(basename(image_path))
  cropped_path = join(crop_dir, split_name[0] + '-mode' + split_name[1])
  logging.info('crop size: {} path: {}'.format(crop, cropped_path))
  cropped_image = image.crop((0, 0, crop[0], crop[1]))
  cropped_image.save(cropped_path)

if __name__ == '__main__':
  import argparse
  
  parser = argparse.ArgumentParser(description='Crop scanned images')
  parser.add_argument('-l', '--log-level', default='INFO', help='Logging level (defalt is INFO)')
  parser.add_argument('-i', '--image-path', help='Path to a single image to crop')
  parser.add_argument('-c', '--crop-directory', required=True, help='Directory to which to write cropped images')
  parser.add_argument('-s', '--scan-directory', help='Directory with scanned images to crop')
  args = parser.parse_args()

  numeric_level = getattr(logging, args.log_level.upper(), None)
  if not isinstance(numeric_level, int):
    raise ValueError('Invalid log level {}'.format(args.log_level))

  logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=numeric_level)

  if (int(args.image_path is not None) + int(args.scan_directory is not None)) != 1:
    print >>stderr, 'Either -i or -s must be specified (and not both)'
    exit(1)

  if not isdir(args.crop_directory):
    print >>stderr, 'Crop directory {} does not exist or is not a directory'.format(args.crop_directory)
    exit(2)

  # N.B. only the margin detection via brightness approach is actually used.
  if args.image_path is not None:
    crop_scan_using_brightness(args.image_path, args.crop_directory)
  else:
    if not isdir(args.scan_directory):
      print >>stderr, 'Scan directory {} does not exist or is not a directory'.format(args.scan_directory)
      exit(3)
    for image_path in filter(isfile, map(lambda f: join(args.scan_directory, f), listdir(args.scan_directory))):
      crop_scan_using_brightness(image_path, args.crop_directory)
