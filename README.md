# LoraUtils
Small utils that are helpful, at least to me, in the preparation of datasets for Lora Training. There might be similar utils out there but the ones I tried didn't really fit how I like to work so I vibe-coded these that better suit me. Maybe they suit someone out there as well.

Of note, not all buttons/features are thoroughly tested but the key ones are.

This readme is a WORK IN PROGRESS

## VideoClipExtractor.py
Tool to extract video clips from a larger clip/movie file. You can configure the duration to extract, the resolution, crop parts out, etc.. etc..

## TagManager.py
Tool to manage the captions of a given dataset. It works with a current dataset and can also load an additional dataset in addition in case you want to refer to captions you already used in some other Lora training

## FrameEditor.py
Very simple tool that allows you to select and delete frames from a video file, useful for trimming the end of clips for instance
