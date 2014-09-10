from __future__ import absolute_import, print_function, unicode_literals
from ..util import parse_requirement
from .base import Service
from distlib.wheel import Wheel
from distlib.scripts import ScriptMaker

import sys
import os.path


PREFIX = os.path.normpath(sys.prefix)


def get_distribution_paths(name):
    """Return target paths where the package content should be installed"""
    pyver = 'python' + sys.version[:3]

    paths = {
        'prefix' : '{prefix}',
        'data'   : '{prefix}/lib/{pyver}/site-packages',
        'purelib': '{prefix}/lib/{pyver}/site-packages',
        'platlib': '{prefix}/lib/{pyver}/site-packages',
        'headers': '{prefix}/include/{pyver}/{name}',
        'scripts': '{prefix}/bin',
    }

    # pip uses a similar path as an alternative to the system's (read-only)
    # include directory:
    if hasattr(sys, 'real_prefix'):  # virtualenv
        paths['headers'] = os.path.abspath(
            os.path.join(sys.prefix, 'include', 'site', pyver, name))

    # Replacing vars
    for key, val in paths.items():
        paths[key] = val.format(prefix=PREFIX, name=name, pyver=pyver)
    return paths


class ForgivingScriptMaker(ScriptMaker):
    """Assumes scripts are raw binaries if we can't determine an encoding."""

    def _copy_script(self, script, filenames):
        try:
            return super(ForgivingScriptMaker, self)._copy_script(script, filenames)
        except SyntaxError:
            # `distlib` assumed this was a python script and couldn't figure
            # out its encoding. It's likely a raw binary, so just copy it over
            # to `bin` without any modifications.
            from distlib.util import convert_path
            script = os.path.join(self.source_dir, convert_path(script))
            outname = os.path.join(self.target_dir, os.path.basename(script))
            with open(script, 'rb') as f:
                self._fileop.write_binary_file(outname, f.read())
            if self.set_mode:
                self._fileop.set_executable_mode([outname])


class Installer(Service):

    def handle(self, requester, data):
        name = parse_requirement(data['requirement']).name

        maker = ForgivingScriptMaker(None, None)

        wheel = Wheel(data['wheel'])
        wheel.install(get_distribution_paths(name), maker)
        return data
