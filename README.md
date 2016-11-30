Crops scanned pictures.  The scanned image is larger than the actual picture,
with a mostly-white additional margin to the right and bottom of the picture.

There are multiple approaches to cropping in this script.  The most effective
one tries to identify vertical lines to the right of the photo and horizontal
lines below it that are mostly white.  When a line fails the test for mostly
white, it is considered the edge of the picture.

The other two approaches try to find the transition between margin and picture.
Arbitrarily picking one horizontal and one vertical line to follow to detect the
transition works very well except for photos where the photo color along the
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
