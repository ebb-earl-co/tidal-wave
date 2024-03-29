[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PyPI - Version](https://img.shields.io/pypi/v/tidal-wave)](https://pypi.org/project/tidal-wave/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/tidal-wave)](https://pypi.org/project/tidal-wave/)
[![Build Python package](https://github.com/ebb-earl-co/tidal-wave/actions/workflows/python-build.yml/badge.svg?branch=trunk&event=release)](https://github.com/ebb-earl-co/tidal-wave/actions/workflows/python-build.yml)
[![Docker Image CI](https://github.com/ebb-earl-co/tidal-wave/actions/workflows/docker-image.yml/badge.svg?branch=trunk)](https://github.com/ebb-earl-co/tidal-wave/actions/workflows/docker-image.yml)

# tidal-wave &#x1F3B6; &#x1F30A;
Waving at the [TIDAL](https://tidal.com) music service with [Python](https://www.python.org/). Runs on (at least) Windows, macOS, and GNU/Linux.

>  TIDAL is an artist-first, fan-centered music streaming platform that delivers over 100 million songs in HiFi sound quality to the global music community. © 2024 TIDAL Music AS

This project is inspired by [`qobuz-dl`](https://github.com/vitiko98/qobuz-dl), and, particularly, is a continuation of [`Tidal-Media-Downloader`](https://github.com/yaronzz/Tidal-Media-Downloader). **This project is intended for private use only: it is not intended for distribution of copyrighted content**.

This software uses libraries from the [FFmpeg](http://ffmpeg.org) project under the [LGPLv2.1](http://www.gnu.org/licenses/old-licenses/lgpl-2.1.html). FFmpeg is a trademark of [Fabrice Bellard](http://www.bellard.org/), originator of the FFmpeg project. 

## Features
* Retrieve [FLAC](https://xiph.org/flac/), [Dolby Atmos](https://www.dolby.com/technologies/dolby-atmos/), [Sony 360 Reality Audio](https://electronics.sony.com/360-reality-audio), or [AAC](https://en.wikipedia.org/wiki/Advanced_Audio_Coding) tracks; [AVC/H.264](https://en.wikipedia.org/wiki/Advanced_Video_Coding) (up to 1920x1080) + [AAC](https://en.wikipedia.org/wiki/Advanced_Audio_Coding) videos
* Either a single track or an entire album can be retrieved
* Album covers are retrieved by default, and embedded into all tracks
* Support for albums with multiple discs
* If available, lyrics are added as metadata to tracks
* If available, album reviews are retrieved as JSON
* If available, album credits are retrieved as JSON
* If available, artist bios are retrieved as JSON
* If available, artist images are retrieved as JPEG
* Playlist retrieval support (video or audio or both)
* Playlist .m3u8 file automatically created
* Mix retrieval support (video or audio)
* Artist's entire works retrieval support (video and audio; albums or albums and EPs and singles)
* Because of the use of the `requests` package, system proxies are respected (HTTP, HTTPs, Socks); or can be specified by typical environment variable
* Also because of the use of `requests`, very simple [`Cache-Control`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control) request caching occurs via `CacheControl`

## Getting Started
A [HiFi Plus](https://tidal.com/pricing) account is **required** in order to retrieve HiRes FLAC, Dolby Atmos, and Sony 360 Reality Audio tracks. Simply a [HiFi](https://tidal.com/pricing) plan is sufficient to retrieve in 16-bit, 44.1 kHz (i.e., lossless) or lower quality as well as videos. More information on sound quality at [TIDAL's site here](https://tidal.com/sound-quality).

### Requirements
 - As resources will be fetched from the World Wide Web, an Internet connection is required
 - The venerable [FFmpeg](http://ffmpeg.org/download.html) is necessary for audio and video data manipulation. This project's [container image](https://github.com/ebb-earl-co/tidal-wave/blob/trunk/Dockerfile) as well as its [`pyinstaller`](https://pyinstaller.org/en/stable/)-created [binary for GNU/Linux](https://github.com/ebb-earl-co/tidal-wave/releases/latest/download/tidal-wave_py311_FFmpeg6.1.1_linux), [binary for Apple Silicon macOS](https://github.com/ebb-earl-co/tidal-wave/releases/latest/download/tidal-wave_py311_FFmpeg6.1.1_macos_arm64), and [binary for x86\_64 macOS](https://github.com/ebb-earl-co/tidal-wave/releases/latest/download/tidal-wave_py311_FFmpeg6.1.1_macos_x86_64) build FFmpeg from source, so separate installation is unnecessary.
   - Static builds of FFmpeg are available from [John Van Sickle](https://www.johnvansickle.com/ffmpeg/) for GNU/Linux, or most package managers feature `ffmpeg`.
   - For macOS, the [FFmpeg download page](http://ffmpeg.org/download.html#build-mac) links to [this download source](https://evermeet.cx/ffmpeg/); or there is always [Homebrew](https://formulae.brew.sh/formula/ffmpeg)
   - For Windows, the [FFmpeg download page](http://ffmpeg.org/download.html#build-windows) lists 2 resources; or [`chocolatey`](https://community.chocolatey.org/packages/ffmpeg) is an option
 - This is a Python package, so **to use it in the default manner** you will need [Python 3](https://www.python.org/downloads/), version 3.8 or newer, on your system.
   - *However*, as of December 2023, an [OCI container image](https://github.com/ebb-earl-co/tidal-wave/pkgs/container/tidal-wave); `pyapp`-compiled binaries; and [`pyinstaller`](https://pyinstaller.org/en/stable/)-created binaries for x86\_64 GNU/Linux, Apple Silicon macOS, and x86\_64 macOS are provided for download and use that *do not require Python to be installed*
 - Only a handful of Python libraries are dependencies:
   - [`backoff`](https://pypi.org/project/backoff/)
   - [`cachecontrol`](https://pypi.org/project/CacheControl/)
   - [`dataclass-wizard`](https://pypi.org/project/dataclass-wizard/)
   - [`ffmpeg-python`](https://pypi.org/project/ffmpeg-python/)
   - [`mutagen`](https://pypi.org/project/mutagen/)
   - [`m3u8`](https://pypi.org/project/m3u8/)
   - [`platformdirs`](https://pypi.org/project/platformdirs/)
   - [`pycryptodome`](https://pypi.org/project/pycryptodome/)
   - [`requests[socks]`](https://pypi.org/project/requests/)
   - [`typer`](https://pypi.org/project/typer/)

## Installation
### `pip` Install from PyPi
Install this project with [`pip`](https://pip.pypa.io/en/stable/): either with a virtual environment (preferred) or any other way you desire:
```bash
# GNU/Linux or macOS or Android (e.g. Termux)
$ python3 -m pip install tidal-wave
```
```powershell
# Windows
PS > python.exe -m pip install tidal-wave
```

Optionally, to get the full `typer` experience when using this utility, add `[all]` to the end of the `pip install command`:
```bash
$ python3 -m pip install tidal-wave[all]
```
```powershell
PS > python.exe -m pip install tidal-wave[all]
```
### `pip` Install from the Repository
Alternatively, you can clone this repository; `cd` into it; and install from there:
```bash
$ git clone --depth=1 https://github.com/ebb-earl-co/tidal-wave.git
$ cd tidal-wave
$ python3 -m venv .venv
$ source .venv/bin/activate
$ (.venv) pip install .  # or, pip install .[all]
```
### `Pyinstaller` executable
This is the preferred release artifact, compiled with [`pyinstaller`](https://pyinstaller.org). It bundles Python 3.11, FFmpeg 6.1.1, and the `tidal-wave` program into one binary, licensed under the terms of FFmpeg: with the [GNU Lesser General Public License (LGPL) version 2.1](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html). Installation is as simple as downloading the correct binary for your platform (currently, GNU/Linux x86\_64; macOS x86\_64; or macOS arm64), giving it execute permissions, and running it.
```bash
$ wget https://github.com/ebb-earl-co/tidal-wave/releases/latest/download/tidal-wave_py311_FFmpeg6.1.1_linux
$ chmod +x ./tidal-wave_py311_FFmpeg6.1.1_linux
# optionally, rename the binary because the name is descriptive, but unwieldy
$ mv ./tidal-wave_py311_FFmpeg6.1.1_linux ./tidal-wave_linux
$ ./tidal-wave_linux --help
```
### `pyapp` executable
Download the Rust-compiled binary from [the Releases](https://github.com/ebb-earl-co/tidal-wave/releases/latest), and, on macOS or GNU/Linux, make it executable
```bash
$ wget https://github.com/ebb-earl-co/tidal-wave/releases/latest/download/tidal-wave_py311.pyapp
$ chmod +x ./tidal-wave_py311.pyapp
$ ./tidal-wave_py311.pyapp --help
```
Or, on Windows, once the .exe file is downloaded, you might have to allow a security exception for an unknown developer, then:
```powershell
PS > Invoke-WebRequest https://github.com/ebb-earl-co/tidal-wave/releases/latest/download/tidal-wave_py311_pyapp.exe
PS > & "tidal-wave_py311_pyapp.exe" --help
```

### Docker
Pull the image from GitHub container repo:
```bash
$ docker pull ghcr.io/ebb-earl-co/tidal-wave:latest
# Or, the main branch of this repository, which will be ahead of `latest`:
$ docker pull ghcr.io/ebb-earl-co/tidal-wave:trunk
```
## Quickstart
Run `python3 tidal-wave --help` to see the options available. Or, if you followed the repository cloning steps above, run `python3 -m tidal_wave --help` from the repository root directory, `tidal-wave`. In either case, you should see something like the following:
```bash
Usage: python -m tidal_wave [OPTIONS] TIDAL_URL [OUTPUT_DIRECTORY]                                                                                                                                                                  
                                                                                                                                                                                                                                     
╭─ Arguments ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    tidal_url             TEXT                The Tidal album or artist or mix or playlist or track or video to download [default: None] [required]                                                                              │
│      output_directory      [OUTPUT_DIRECTORY]  The parent directory under which directory(ies) of files will be written [default: ~/Music]                                                                                        │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --audio-format               [360|Atmos|HiRes|MQA|Lossless|High|Low]  [default: Lossless]                                                                                                                                         │
│ --loglevel                   [DEBUG|INFO|WARNING|ERROR|CRITICAL]      [default: INFO]                                                                                                                                             │
│ --include-eps-singles                                                 No-op unless passing TIDAL artist. Whether to include artist's EPs and singles with albums                                                                  │
│ --no-extra-files                                                      Whether to not even attempt to retrieve artist bio, artist image, album credits, album review, or playlist m3u8                                             │
│ --no-flatten                                                          Whether to treat playlists or mixes as a list of tracks/videos and, as such, retrieve them independently                                                    │
| --transparent                                                         Whether to dump JSON responses from TIDAL API; maximum verbosity                                                                                            | 
│ --install-completion                                                  Install completion for the current shell.                                                                                                                   │
│ --show-completion                                                     Show completion for the current shell, to copy it or customize the installation.                                                                            │
│ --help                                                                Show this message and exit.                                                                                                                                 │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## Usage
Invocation of this tool will store credentials in a particular directory in the user's "home" directory: for Unix-like systems, this will be `/home/${USER}/.config/tidal-wave`: for Windows, it varies: in either OS situation, the exact directory is determined by the `user_config_path()` function of the `platformdirs` package.

Similarly, by default, all media retrieved is placed in subdirectories of the user's default music directory: for Unix-like systems, this probably is `/home/${USER}/Music`; for Windows it is probably `C:\Users\<USER>\Music`. This directory is determined by `platformdirs.user_music_path()`. 
 - If a different path is passed to the second CLI argument, `output_directory`, then all media is written to subdirectories of that directory.

### Which Audio Formats Are Available to Which Clients
Source: [TIDAL](https://tidal.com/supported-devices)
|                | Low                | High               | Lossless           |      MQA           | HiRes FLAC         | Dolby Atmos        | Sony 360 Reality Audio | Video (H.264 + AAC) |
| :---           | :---:              | :---:              |   :---:            |     :---:          |   :---:            |    :---:           |        :---:           |     :---:           |
| Android        | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: |     :x:            |   :heavy_check_mark:   | :heavy_check_mark: |
| Fire TV :large_blue_diamond: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark:        |         :x:        | :heavy_check_mark:     | :x: | :heavy_check_mark: |
| macOS          | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: |         :x:        |       :x:              | :heavy_check_mark: |
| Windows        | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: | :heavy_check_mark: |         :x:        |            :x:         | :heavy_check_mark: |

:large_blue_diamond: This is the default client for `tidal-wave`, a spoofed Amazon Fire TV. It is the one invoked in all situations unless `--audio-format hires` or `--audio-format 360` is passed as a command line flag:
```bash
$ tidal-wave https://listen.tidal.com/album/000000
$ # no --audio-format flag passed will instruct tidal-wave to use the Fire TV client, as it implies --audio-format lossless
$ tidal-wave https://listen.tidal.com/album/000000 --audio-format high
$ # specifying low, high, lossless, or atmos will instruct tidal-wave to use the Fire TV client
$ tidal-wave https://listen.tidal.com/album/000000 --audio-format hires
$ # the above forces tidal-wave to ask for an access token gleaned from an Android, macOS, or Windows device, as laid out in the above table
```
Otherwise, in order to retrieve the desired audio format for a given track, it is **necessary** to have the access token from a compatible device; e.g. an Android device in order to retrieve Sony 360 Reality Audio tracks

### Example
 - First, find the URL of the album/artist/mix/playlist/track/video desired. Then, simply pass it as the first argument to `tidal-wave` with no other arguments in order to: *retrieve the album/artist/mix/playlist/track in Lossless quality to a subdirectory of user's music directory and INFO-level logging* in the case of audio; *retrieve the video in 1080p, H.264+AAC quality to a subdirectory of user's music directory with INFO-level logging* in the case of a video URL.
 ```bash
 (.venv) $ tidal-wave https://tidal.com/browse/track/226092704
 ```
 - By default, the track(s) and/or video(s) are retrieved, and other files are retrieved as well; such as the artist's bio JSON, the artist's TIDAL image, the playlist's .m3u8 file, the album's review JSON, and a few others. In order **not to retrieve any of those**, pass the `--no-extra-files` flag:
 ```bash
 (.venv) $ tidal-wave https://tidal.com/browse/track/226092704 --no-extra-files
 ```
 - To (attempt to) get a Dolby Atmos track, and you desire to see *all* of the log output, the following will do that
 ```bash
 (.venv) $ tidal-wave https://tidal.com/browse/track/... --audio-format atmos --loglevel debug
 ```
 **Keep in mind that an access token from an Android (preferred), Windows, or macOS device will need to be extracted and passed to this tool in order to access HiRes FLAC or Sony 360 Reality Audio tracks**
 - To (attempt to) get a HiRes FLAC version of an album, and you desire to see only warnings and errors, the following will do that:
 ```bash
 $ tidal-wave https://tidal.com/browse/album/... --audio-format hires --loglevel warning
 ```

 - To (attempt to) get a playlist, the following will do that. **N.b.** passing anything to `--audio-format` is a no-op when retrieving videos.
 ```powershell
 PS > C:\Users\User > & tidal-wave_py311_pyapp.exe https://tidal.com/browse/playlist/...
 ```

 - To (attempt to) get a mix, the following will do that. **N.b.** passing anything to `--audio-format` is a no-op when retrieving videos.
 ```bash
 $ ./tidal-wave_py311.pyapp https://tidal.com/browse/mix/...
 ```

 - To (attempt to) get all of an artist's works (albums and videos, **excluding EPs and singles**) in Sony 360 Reality Audio format and verbose logging, the following will do that:
 ```bash
 (.venv) $ python3 -m tidal_wave https://listen.tidal.com/artist/... --audio-format 360 --loglevel debug
 ```

 - To (attempt to) get all of an artist's works (**including EPs and singles**), in HiRes format, the following will do that:
 ```bash
 (.venv) $ tidal-wave https://listen.tidal.com/artist/... --audio-format hires --include-eps-singles
 ```

 - As a throw-everything-at-the-wall-and-see-what-sticks option, there is the `--transparent` flag. In the directory where `tidal-wave` is called, `--transparent` will write the responses from the TIDAL API to .json files
 ```bash
 (.venv) $ tidal-wave https://listen.tidal.com/track/... --audio-format low  --loglevel debug --transparent
 ```

#### Playlists and Mixes
By default, when passed a playlist or mix URL, `tidal-wave` will retrieve all of the tracks and/or videos specified by that URL, and write them to a subdirectory of either `Playlists` or `Mixes`, which itself is a subdirectory of the specified `output_directory`. E.g. `~/Music/Mixes/My Daily Discovery [016dccd302e9ac6132d8334cfbc022]`. In this directory, once all of the tracks and/or videos have been retrieved, they are renamed based on the order in which they appear in the playlist. E.g.
```bash
(.venv) $ tidal-wave https://listen.tidal.com/playlist/1b418bb8-90a7-4f87-901d-707993838346

$ ls ~/Music/Playlists/New Arrivals [1b418bb8-90a7-4f87-901d-707993838346]/
'001 - Dance Alone [CD].flac'
'002 - Kissing Strangers [CD].flac'
'003 - Sunday Service [CD].flac'
```
If this is not the desired behavior, pass the `--no-flatten` flag. This flag instructs `tidal-wave` to leave the tracks and/or videos in the directory where they would be written if they had been passed to `tidal-wave` independently. E.g.
```bash
(.venv) $ tidal-wave https://listen.tidal.com/playlist/1b418bb8-90a7-4f87-901d-707993838346 --no-flatten

$ ls ~/Music/
'Sia/Dance Alone [343225498] [2024]/01 - Dance Alone [CD].flac'
'USHER/COMING HOME [339249017] [2024]/05 - Kissing Strangers [CD].flac'
'Latto/Sunday Service [344275657] [2024]/01 - Sunday Service [CD].flac'
```

#### Docker example
The command line options are the same for the Python invocation, but in order to save configuration and audio data, volumes need to be passed. If they are bind mounts to directories, **they must be created before executing `docker run` to avoid permissions issues**! For example,
```bash
$ mkdir -p ./Music/ ./config/tidal-wave/
$ docker run \
    --rm -it \
    --name tidal-wave \
    --volume ./Music:/home/debian/Music \
    --volume ./config/tidal-wave:/home/debian/.config/tidal-wave \
    ghcr.io/ebb-earl-co/tidal-wave:latest \
    https://tidal.com/browse/track/...
```

Using Docker might be an attractive idea in the event that you want to retrieve all of the videos, albums, EPs, and singles in highest quality possible for a given artist. The following Docker invocation will do that for you:
```bash
$ mkdir -p ./Music/ ./config/tidal-wave/
$ docker run \
    --name tidal-wave \
    --rm -it \
    --volume ./Music:/home/debian/Music \
    --volume ./config/tidal-wave:/home/debian/.config/tidal-wave \
    ghcr.io/ebb-earl-co/tidal-wave:latest \
    https://listen.tidal.com/artist/... \
    --audio-format hires \
    --include-eps-singles
```

Perhaps you don't want a single-shot executable type of Docker invocation, but rather a long-lived container into which one can `docker exec` in order to request media at one's leisure. This is one of the requested features from the GitHub Discussions, in particular for Unraid users. In order to do this, use the following, slightly-modified Docker command:
```bash
$ mkdir -p ./Music/ ./config/tidal-wave/
$ docker run \
    --name tidal-wave \
    -dit \  # is short for: --detach --interactive --tty
    --volume ./Music:/home/debian/Music \
    --volume ./config/tidal-wave:/home/debian/.config/tidal-wave \
    --entrypoint "/bin/bash" \
    ghcr.io/ebb-earl-co/tidal-wave:latest
$ docker exec -it tidal-wave python3 -m tidal_wave https://tidal.com/browse/album/...
$ docker exec -it tidal-wave python3 -m tidal_wave https://tidal.com/browse/mix/...
$ docker exec -it tidal-wave python3 -m tidal_wave https://tidal.com/browse/playlist/...
$ docker exec -it tidal-wave python3 -m tidal_wave https://tidal.com/browse/track/...
```
## Development
The easiest way to start working on development is to fork this project on GitHub, or clone the repository to your local machine and do the pull requesting on GitHub later. In any case, there will need to be some getting from GitHub first, so, roughly, the process is:
  1. Get Python 3.8+ on your system
  2. Use a virtualenv or some other Python environment system (poetry, pipenv, etc.)
  3. Clone the repository: `$ git clone --depth=1 https://github.com/ebb-earl-co/tidal-wave/git`

    * Obviously replace the URL with your forked version if you've followed that strategy
  4. Activate the virtual environment and install the required packages (requirements.txt): `(some-virtual-env) $ python3 -m pip install -r requirements.txt`

    * optional packages to follow the coding style and build process; `pyinstaller`, `black`: `(some-virtual-env) $ python3 -m pip install black pyinstaller`
    * optionally, Rust and cargo in order to build the `pyapp` artifacts
    * optionally, Docker to build the OCI container artifacts
  5. From a Python REPL (or, my preferred method, an iPython session), import all the relevant modules, or the targeted ones for development:
  ```python
  from tidal_wave import album, artist, dash, hls, login, main, media, mix, models, oauth, playlist, requesting, track, utils, video
  from tidal_wave.main import logging, user_music_path, Path
  ```
