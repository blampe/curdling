from __future__ import absolute_import, unicode_literals, print_function
from collections import defaultdict
from distlib.util import parse_requirement
from .service import Service


def getversion(requirement):
    return (
        ''.join(' '.join(x) for x in requirement.constraints or [])
        or None)


class Maestro(object):

    def __init__(self, *args, **kwargs):
        super(Maestro, self).__init__(*args, **kwargs)
        self.mapping = defaultdict(dict)
        self.built = set()
        self.failed = set()

    def file_package(self, package, dependency_of=None):
        # Reading the package description
        requirement = parse_requirement(package)
        version = getversion(requirement)

        # Saving back to the mapping
        self.mapping[requirement.name.lower()].update({
            version: None,
        })

    def _mark(self, attr, package, data):
        pkg = parse_requirement(package)
        name = pkg.name.lower()
        getattr(self, attr).add(name)
        self.mapping[name][getversion(pkg)] = data

    def mark_built(self, package, data):
        self._mark('built', package, data)

    def mark_failed(self, package, data):
        self._mark('failed', package, data)

    def should_queue(self, package):
        pkg = parse_requirement(package)
        return pkg.name.lower() not in self.mapping

    @property
    def pending_packages(self):
        return list(set(self.mapping.keys())
            .difference(self.built)
            .difference(self.failed))
