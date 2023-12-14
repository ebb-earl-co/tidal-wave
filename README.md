[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
# tidal-wave
Waving at the [TIDAL](https://tidal.com) music service. Runs on (at least) Windows, macOS, and GNU/Linux.

This project is inspired by [`qobuz-dl`](https://github.com/vitiko98/qobuz-dl), and, particularly, is a continuation of [`Tidal-Media-Downloader`](https://github.com/yaronzz/Tidal-Media-Downloader). **This project is intended for private use only: it is not intended for distribution of copyrighted content**

## Features
* Download [FLAC](https://xiph.org/flac/), [Dolby Atmos](https://www.dolby.com/technologies/dolby-atmos/), [Sony 360 Reality Audio](https://electronics.sony.com/360-reality-audio), or [AAC](https://en.wikipedia.org/wiki/Advanced_Audio_Coding) tracks
* Either a single track or an entire album can be downloaded
* Album covers and artist images are downloaded by default
* Support for albums with multiple discs
* If available, lyrics are added as metadata to tracks
* If available, album reviews are downloaded as JSON 

* _Coming soon_: Video download support
* _Coming soon_: Playlist download support (video and audio)

## Getting Started
A [HiFi Plus](https://tidal.com/pricing) account is **required** in order to retrieve HiRes FLAC, Dolby Atmos, and Sony 360 Reality Audio tracks. Simply a [HiFi](https://tidal.com/pricing) plan is sufficient to download in 16-bit, 44.1 kHz (i.e. lossless) or lower quality.

### Requirements
 - This is a Python tool, so you will need [Python 3](https://www.python.org/downloads/) on your system: this tool supports Python 3.8 or newer. 
 - As resources will be fetched from the World Wide Web, an Internet connection is required
 - The excellent tool [FFmpeg](http://ffmpeg.org/download.html) is necessary for audio file manipulation. It is available from almost every package manager; or static builds are available from [John Van Sickle](https://www.johnvansickle.com/ffmpeg/).
   - For Windows, it's available in the [Microsoft App Store](https://apps.microsoft.com/detail/9NB2FLX7X7WG) or from [`chocolatey`](https://community.chocolatey.org/packages/ffmpeg)
 - Only a handful of Python libraries are dependencies:
   - [`dataclass-wizard`](https://pypi.org/project/dataclass-wizard/)
   - [`ffmpeg-python`](https://pypi.org/project/ffmpeg-python/)
   - [`mutagen`](https://pypi.org/project/mutagen/)
   - [`platformdirs`](https://pypi.org/project/platformdirs/)
   - [`requests`](https://pypi.org/project/requests/)
   - [`typer`](https://pypi.org/project/typer/)

## Installation
Install this project with [`pip`](https://pip.pypa.io/en/stable/): either with a virtual environment (preferred) or any other way you desire:
```bash
$ python3 -m pip install tidal-wave
```

Alternatively, you can clone this repository; `cd` into it; and install from there:
```bash
$ git clone https://github.com/ebb-earl-co/tidal-wave.git
$ cd tidal-wave
$ python3 -m venv .venv
$ source .venv/bin/activate
$ (.venv) pip install .
```

Optionally, to get the full `typer` experience when using this utility, add `[all]` to the end of the `pip install command`:
```bash
$ python3 -m pip install tidal-wave[all]
```

## Quickstart
Run `python3 tidal-wave --help` to see the options available. Or, if you followed the repository cloning steps above, run `python3 -m tidal_wave --help` from the repository root directory, `tidal-wave`. In either case, you should see something like the following:
```bash
Usage: tidal-wave [OPTIONS] TIDAL_URL [OUTPUT_DIRECTORY]                                                                                                                                  
                                                                                                                                                                                            
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    tidal_url             TEXT                The Tidal track or album to download [default: None] [required]                                                                           │
│      output_directory      [OUTPUT_DIRECTORY]  The parent directory under which files will be written; i.e. output_directory/<artist name>/<album name>/ [default: ]                     │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --audio-format        [360|Atmos|HiRes|MQA|Lossless|High|Low]         [default: Lossless]                                                                                                │
│ --loglevel            [DEBUG|INFO|WARNING|ERROR|CRITICAL]             [default: INFO]                                                                                                    │
│ --help                                                                Show this message and exit.                                                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## Usage
> By default, this tool can request (and, if no errors arise, retrieve) all of the audio formats *except* `HiRes` and `360`.

> The [HiRes FLAC](https://tidal.com/supported-devices?filter=hires-flac) format is only available if the credentials from an Android, Windows, iOS, or macOS device can be obtained

> The [Sony 360 Reality Audio](https://tidal.com/supported-devices?filter=sony-360) format is only available if the credentials from an Android or iOS device can be obtained

Invocation of this tool will store credentials in a particular directory in the user's "home" directory: for Unix-like systems, this will be `/home/${USER}/.config/tidal-wave`: for Windows, it varies: in either OS situation, the exact directory is determined by the `user_config_path()` function of the `platformdirs` package.

Similarly, all media retrieved is placed in subdirectories of the user's default Music directory: for Unix-like systems, this probably is `/home/${USER}/Music`; for Windows it is probably `C:\Users\<USER>\Music`. This directory is determined by `platformdirs.user_music_path()`. 
 - If a different path is passed to the second CLI argument, `output_directory`, then all media is written to subdirectories of that directory.

### Example
 - First, find the URL of the track or album ID desired. Then, simmply pass it as the first argument to `tidal-wave` with no other arguments to: *download the track/album in Lossless quality to a subdirectory of user's music directory and INFO-level logging.*
```bash
$ python3 tidal-wave https://tidal.com/browse/track/226092704
```

 - To (attempt to) get a Dolby Atmos track, and you desire to see *all* of the log output, the following will do that
 ```bash
 $ python3 tidal-wave https://tidal.com/browse/track/... --audio-format atmos --loglevel debug
 ```

 - To (attempt to) get a HiRes FLAC version of an album, and you desire to see only warnings and errors, the following will do that:
 ```bash
 $ python3 tidal-wave https://tidal.com/browse/album/... --audio-format hires --loglevel warning
 ```
 **Keep in mind that authentication from an Android (preferred), iOS, Windows, or macOS device will need to be extracted and passed to this tool in order to access HiRes FLAC and Sony 360 Reality Audio versions of tracks**
