# docker-micropython-linux
Docker image that comes loaded with the unix (linux in this case) port of micropython.

#### Why use this? Simple:

* Running automated tests against libraries intended for micropython (you *can* use python3, but there are edge cases).
* Experimenting with micropython without any complexity of building yourself or overhead of buying a board first.
* There wasn't an existing and well-maintained image.

The image is based off the official Debian-slim (stretch) because it's fairly slim (not as slim as alpine, but that can be a headache to build).

#### Getting Started

Providing you have access to Docker, you can run the latest version quite easily by:

    docker run -t mitchins/micropython-linux
    MicroPython v1.9.4-403-g81e320ae on 2018-07-21; linux version
    Use Ctrl-D to exit, Ctrl-E for paste mode
    >>> ^C

Tags are available on the Docker Hub listing

If you check the Dockerfile, you will see it starts up micropython automatically which is stored in /usr/local/bin/micropython

To install something else, you can:

    # micropython -m upip install micropython-unittest
    Installing to: /root/.micropython/lib/
    Warning: pypi.org SSL certificate is not validated
    Installing micropython-unittest 0.3.2 from https://files.pythonhosted.org/packages/9a/42/41057b8da94414a17f7028ee08035c3d945befebddc76d58988067ddaf0f/micropython-unittest-0.3.2.tar.gz

That's about it, the goal is to maintain the latest and stable tagged versions so regressions can be tested as needed, or experimented features accessed.
