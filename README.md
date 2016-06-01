# Wrocket's Astro-scripts
----
## What is this?
These are any little programs I write for the purpose of processing, organizing, or otherwise managing my modest astrophotos.

----
## align_planet.py
This script is used in the following situation:

1. I have an arbitrary number of photo frames of a bright object (such as a planet) taken at roughly the same settings on the same date
2. The frames aren't aligned, or close to being aligned, since I took them from an untracked mount using a photo camera instead of a video camera.

The script uses a threshold mask to locate the planet in each frame, and then crops the frames so that the planet is aligned perfectly. The resulting images can be then fed into a program like RegiStax or similar.

For example, consider this set of input frames:

Running the command:

    align_planet.py ./output_directory ./input_files/*.jpg

This script produces the following result, with each frame nicely aligned. You're now ready for stacking!

### Requirements
* [Python 3](http://www.python.org/) (I run/test on 3.4.3)
* [ImageMagick](http://www.imagemagick.org/) ( run/test with 6.7.7)
* The [Pillow](http://python-pillow.org/) Python module

### Doesn't RegiStax already do that?
RegiStax is great when you have a set of frames where the target doesn't move much between frames (such as a video), but I've gotten far better (and faster results) using this alignment script.

### Why don't you use a video camera for planetary?
I don't own the requisite hardware, and I'm on a tight budget. It's also fun writing software to do this!