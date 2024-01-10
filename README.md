[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PyPI - Version](https://img.shields.io/pypi/v/tidal-wave)](https://pypi.org/project/tidal-wave/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/tidal-wave)](https://pypi.org/project/tidal-wave/)
![PyPI - Implementation](https://img.shields.io/pypi/implementation/tidal-wave)
![GitHub repo size](https://img.shields.io/github/repo-size/ebb-earl-co/tidal-wave)

# tidal-wave
Waving at the [TIDAL](https://tidal.com) music service. Runs on (at least) Windows, macOS, and GNU/Linux.

This project is inspired by [`qobuz-dl`](https://github.com/vitiko98/qobuz-dl), and, particularly, is a continuation of [`Tidal-Media-Downloader`](https://github.com/yaronzz/Tidal-Media-Downloader). **This project is intended for private use only: it is not intended for distribution of copyrighted content**

## Features
* Download [FLAC](https://xiph.org/flac/), [Dolby Atmos](https://www.dolby.com/technologies/dolby-atmos/), [Sony 360 Reality Audio](https://electronics.sony.com/360-reality-audio), or [AAC](https://en.wikipedia.org/wiki/Advanced_Audio_Coding) tracks; [AVC/H.264](https://en.wikipedia.org/wiki/Advanced_Video_Coding) (up to 1920x1080) + [AAC](https://en.wikipedia.org/wiki/Advanced_Audio_Coding) videos
* Either a single track or an entire album can be downloaded
* Album covers and artist images are downloaded by default
* Support for albums with multiple discs
* If available, lyrics are added as metadata to tracks
* If available, album reviews are downloaded as JSON 
* Video download support
* Playlist download support (video or audio or both)
* Mix download support (video or audio)
* Artist's entire works download support (video and audio; albums or albums and EPs and singles)

## Getting Started
A [HiFi Plus](https://tidal.com/pricing) account is **required** in order to retrieve HiRes FLAC, Dolby Atmos, and Sony 360 Reality Audio tracks. Simply a [HiFi](https://tidal.com/pricing) plan is sufficient to download in 16-bit, 44.1 kHz (i.e. lossless) or lower quality as well as videos.

### Requirements
 - This is a Python tool, so you will need [Python 3](https://www.python.org/downloads/) on your system: this tool supports Python 3.8 or newer.
   - *However*, as of version [2023.12.10](https://github.com/ebb-earl-co/tidal-wave/releases/tag/2023.12.10), a [GitHub container](https://github.com/ebb-earl-co/tidal-wave/pkgs/container/tidal-wave) and `pyapp`-compiled binaries are release artifacts that do not require Python installed
 - As resources will be fetched from the World Wide Web, an Internet connection is required
 - The excellent tool [FFmpeg](http://ffmpeg.org/download.html) is necessary for audio file manipulation. It is available from almost every package manager; or static builds are available from [John Van Sickle](https://www.johnvansickle.com/ffmpeg/).
   - For Windows, the [FFmpeg download page](http://ffmpeg.org/download.html#build-windows) lists 2 resources; or [`chocolatey`](https://community.chocolatey.org/packages/ffmpeg) is an option
   - The Dockerfile [builds FFmpeg](https://github.com/ebb-earl-co/tidal-wave/blob/trunk/Dockerfile#L12) into the image
 - Only a handful of Python libraries are dependencies:
   - [`backoff`](https://pypi.org/project/backoff/)
   - [`dataclass-wizard`](https://pypi.org/project/dataclass-wizard/)
   - [`ffmpeg-python`](https://pypi.org/project/ffmpeg-python/)
   - [`mutagen`](https://pypi.org/project/mutagen/)
   - [`m3u8`](https://pypi.org/project/m3u8/)
   - [`platformdirs`](https://pypi.org/project/platformdirs/)
   - [`requests`](https://pypi.org/project/requests/)
   - [`typer`](https://pypi.org/project/typer/)

## Installation
### `pip` install
Install this project with [`pip`](https://pip.pypa.io/en/stable/): either with a virtual environment (preferred) or any other way you desire:
```bash
$ python3 -m pip install tidal-wave
```

Optionally, to get the full `typer` experience when using this utility, add `[all]` to the end of the `pip install command`:
```bash
$ python3 -m pip install tidal-wave[all]
```
### Local `pip` install
Alternatively, you can clone this repository; `cd` into it; and install from there:
```bash
$ git clone https://github.com/ebb-earl-co/tidal-wave.git
$ cd tidal-wave
$ python3 -m venv .venv
$ source .venv/bin/activate
$ (.venv) pip install .
```
### Shiv executable
As yet another option, if you don't want to mess with `pip`, you can download the `.pyz` artifact in the [releases](https://github.com/ebb-earl-co/tidal-wave/releases) page. It is a binary created using the [`shiv`](https://pypi.org/project/shiv/) project and is used in the following way:
```bash
# download the .pyz file of the latest (or your desired) release
$ wget https://github.com/ebb-earl-co/tidal-wave/releases/download/<VERSION>/tidal-wave_<VERSION>.pyz
$ ./tidal-wave_<VERSION>.pyz --help
```
### `pyapp` executable
Download the Rust-compiled binary from [the Releases](https://github.com/ebb-earl-co/tidal-wave/releases/latest), and, on macOS or GNU/Linux, make it executable
```bash
$ wget https://github.com/ebb-earl-co/tidal-wave/releases/download/<VERSION>/tidal-wave_<VERSION>.pyapp
$ chmod +x ./tidal-wave_<VERSION>.pyapp
```
Or, on Windows, once the .exe file is downloaded, you might have to allow a security exception for an unknown developer.

### Docker
Pull the image from GitHub container repo:
```bash
docker pull ghcr.io/ebb-earl-co/tidal-wave:latest
```
## Quickstart
Run `python3 tidal-wave --help` to see the options available. Or, if you followed the repository cloning steps above, run `python3 -m tidal_wave --help` from the repository root directory, `tidal-wave`. In either case, you should see something like the following:
```bash
Usage: tidal-wave [OPTIONS] TIDAL_URL [OUTPUT_DIRECTORY]                                                                                                                                  
                                                                                                                                                                                            
╭─ Arguments ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *    tidal_url             TEXT                The Tidal album or artist or mix or playlist or track or video to download [default: None] [required]                                     │
│      output_directory      [OUTPUT_DIRECTORY]  The parent directory under which directory(ies) of files will be written [default: /home/${USER}/music/]                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --audio-format               [360|Atmos|HiRes|MQA|Lossless|High|Low]  [default: Lossless]                                                                                                │
│ --loglevel                   [DEBUG|INFO|WARNING|ERROR|CRITICAL]      [default: INFO]                                                                                                    │
│ --include-eps-singles                                                 No-op unless passing TIDAL artist. Whether to include artist's EPs and singles with albums                         │
│ --install-completion                                                  Install completion for the current shell.                                                                          │
│ --show-completion                                                     Show completion for the current shell, to copy it or customize the installation.                                   │
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
 - Even videos are downloaded here (for now) for simplicity

### Example
 - First, find the URL of the album/artist/mix/playlist/track/video desired. Then, simply pass it as the first argument to `tidal-wave` with no other arguments to: *download the album/artist/mix/playlist/track in Lossless quality to a subdirectory of user's music directory and INFO-level logging* in the case of audio; or *download the video in 1080p, H.264+AAC quality to a subdirectory of user's music directory with INFO-level logging* in the case of a video URL.
 ```bash
 (.venv) $ tidal-wave https://tidal.com/browse/track/226092704
 ```
 - To (attempt to) get a Dolby Atmos track, and you desire to see *all* of the log output, the following will do that
 ```bash
 (.venv) $ tidal-wave https://tidal.com/browse/track/... --audio-format atmos --loglevel debug
 ```
 **Keep in mind that authentication from an Android (preferred), iOS, Windows, or macOS device will need to be extracted and passed to this tool in order to access HiRes FLAC and Sony 360 Reality Audio versions of tracks**
 - To (attempt to) get a HiRes FLAC version of an album, and you desire to see only warnings and errors, the following will do that:
 ```bash
 $ ./tidal-wave_<VERSION>.pyz https://tidal.com/browse/album/... --audio-format hires --loglevel warning
 ```

 - To (attempt to) get a video, the following will do that. **N.b.** passing anything to `--audio-format` is a no-op when downloading videos.
 ```bash
 $ ./tidal-wave_<VERSION>.pyz https://tidal.com/browse/video/...
 ```

 - To (attempt to) get a playlist, the following will do that. **N.b.** passing anything to `--audio-format` is a no-op when downloading videos.
 ```bash
 > .\tidal-wave_<VERSION>.pyapp.exe https://tidal.com/browse/playlist/...
 ```

 - To (attempt to) get a mix, the following will do that. **N.b.** passing anything to `--audio-format` is a no-op when downloading videos.
 ```bash
 $ ./tidal-wave_<VERSION>.pyapp https://tidal.com/browse/mix/...
 ```

 - To (attempt to) get all of an artist's works (albums and videos, **excluding EPs and singles**) in Sony 360 Reality Audio format and verbose logging, the following will do that:
 ```bash
 (.venv) $ python3 -m tidal_wave https://listen.tidal.com/artist/... --audio-format 360 --loglevel debug
 ```

 - To (attempt to) get all of an artist's works (**including EPs and singles**), in HiRes format, the following will do that:
 ```bash
 (.venv) $ tidal-wave https://listen.tidal.com/artist/... --audio-format hires --include-eps-singles
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
## Development
The easiest way to start working on development is to fork this project on GitHub, or clone the repository to your local machine and do the pull requesting on GitHub later. In any case, there will need to be some getting from GitHub first, so, roughly, the process is:
  1. Get Python 3.8+ on your system
  2. Use a virtualenv or some other Python environment system (poetry, pipenv, etc.)
  3. Clone the repository: `$ git clone https://github.com/ebb-earl-co/tidal-wave/git`

    * Obviously replace the URL with your forked version if you've followed that strategy
  4. Activate the virtual environment and install the required packages (requirements.txt): `(some-virtual-env) $ python3 -m pip install -r requirements.txt`

    * optional packages to follow the coding style and build process; `shiv`, `black`: `(some-virtual-env) $ python3 -m pip install shiv black`
    * optionally, Rust and cargo in order to build the `pyapp` artifacts
    * optionally, Docker to build the OCI container artifacts
  5. From a Python REPL (or, my preferred method, an iPython session), import all the relevant modules, or the targeted ones for development:
  ```python
  from tidal_wave import album, artist, dash, hls, login, main, media, mix, models, oauth, playlist, requesting, track, utils, video
  from tidal_wave.main import *
  ```
