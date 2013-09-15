from __future__ import absolute_import, unicode_literals, print_function
from distlib import database, metadata, compat, locators
from urlparse import urljoin

from . import util, ReportableError
from .service import Service
from .signal import Signal

import re
import urllib3

# import logging
# logging.basicConfig(level=logging.DEBUG)


def get_locator(component):
    get = component.conf.get
    curds = [CurdlingLocator(u) for u in get('curdling_urls', [])]
    pypi = [PyPiLocator(u) for u in get('pypi_urls', [])]
    return locators.AggregatingLocator(*(curds + pypi), scheme='legacy')


class Pool(urllib3.PoolManager):

    def retrieve(self, url):
        attempts = 5
        headers = {}

        # Authentication
        parsed = compat.urlparse(url)
        if parsed.username:
            auth = '{0}:{1}'.format(parsed.username, parsed.password)
            headers = urllib3.util.make_headers(basic_auth=auth)

        # Params to be passed to request. The `preload_content` must be set to
        # False, otherwise `read()` wont honor `decode_content`.
        params = {'headers': headers, 'preload_content': False}

        # Request the url and ensure we've reached the final location
        response = self.request('GET', url, **params)
        redirect = response.get_redirect_location()
        while redirect:
            response = self.request('GET', redirect, **params)
            redirect = response.get_redirect_location()

            # let's see if there's anyone trying to drive retrieve() crazy by
            # always redirecting to another redirectable url
            attempts -= 1
            if not attempts:
                raise RuntimeError('Maximum redirect attempts reached')

        return response, url


class PyPiLocator(locators.SimpleScrapingLocator):

    def __init__(self, url, **kwargs):
        super(PyPiLocator, self).__init__(url, **kwargs)
        self.opener = Pool()

    def _get_project(self, name):
        return self._fetch(
            urljoin(self.base_url, '%s/' % compat.quote(name)),
            name)

    def _visit_link(self, project_name, link):
        self._seen.add(link)
        locators.logger.debug('_fetch() found link: %s', link)
        info = not self._is_platform_dependent(link) \
            and self.convert_url_to_download_info(link, project_name) \
            or None

        versions = {}
        if info:
            self._update_version_data(versions, info)
            return versions.items()[0]
        return None, None

    def _fetch(self, url, project_name):
        locators.logger.debug('fetch(%s, %s)', url, project_name)
        versions = {}
        page = self.get_page(url)
        for link, rel in (page and page.links or []):
            # Let's not see anything twice, I saw this check on distlib it
            # might be useful.
            if link not in self._seen:
                # Well, here we're ensuring that the first link of a given
                # version will be the one. Even if we find another package for
                # the same version, the first one will be used.
                version, distribution = self._visit_link(project_name, link)
                if version and version not in versions:
                    versions[version] = distribution
        return versions

    def get_page(self, url):
        # http://peak.telecommunity.com/DevCenter/EasyInstall#package-index-api
        scheme, netloc, path, _, _, _ = compat.urlparse(url)
        if scheme == 'file' and os.path.isdir(url2pathname(path)):
            url = urljoin(ensure_slash(url), 'index.html')

        # The `retrieve()` method follows any eventual redirects, so the
        # initial url might be different from the final one
        response, final_url = self.opener.retrieve(url)
        content_type = response.headers.get('content-type', '')
        if locators.HTML_CONTENT_TYPE.match(content_type):
            data = response.data
            encoding = response.headers.get('content-encoding')
            if encoding:
                decoder = self.decoders[encoding]   # fail if not found
                data = decoder(data)
            encoding = 'utf-8'
            m = locators.CHARSET.search(content_type)
            if m:
                encoding = m.group(1)
            try:
                data = data.decode(encoding)
            except UnicodeError:
                data = data.decode('latin-1')    # fallback
            return locators.Page(data, final_url)


class CurdlingLocator(locators.Locator):

    def __init__(self, url, **kwargs):
        super(CurdlingLocator, self).__init__(**kwargs)
        self.original_url = url
        self.url = url
        self.opener = URLOpener()
        self.packages_not_found = []

    def get_distribution_names(self):
        return self.opener.json(urljoin(self.url, 'api'))

    def _get_project(self, name):
        # Retrieve the info
        return {v['version']: self.get_distribution(v) for v in
            self.opener.json(
                urljoin(self.url, 'api/' + name))}

    def _get_distribution(self, version_info):
        # Source url for the package
        source_url = version['urls'][0]  # TODO: prefer whl files

        # Build the metadata
        mdata = metadata.Metadata(scheme=self.scheme)
        mdata.name = version['name']
        mdata.version = version['version']
        mdata.source_url = mdata.download_url = source_url['url']

        # Building the dist and associating the download url
        distribution = database.Distribution(mdata)
        distribution.locator = self
        return distribution


class Downloader(Service):

    def __init__(self, *args, **kwargs):
        super(Downloader, self).__init__(*args, **kwargs)
        self.opener = Pool()
        self.locator = get_locator(self.conf)

    def handle(self, requester, package, sender_data):
        prereleases = self.conf.get('prereleases', True)
        requirement = self.locator.locate(package, prereleases)
        if requirement is None:
            raise ReportableError('Package `{0}\' not found'.format(package))
        return {"path": self.download(requirement.download_url)}

    def get_servers_to_update(self):
        failures = {}
        for locator in self.locator.locators:
            if isinstance(locator, CurdlingLocator) and locator.packages_not_found:
                failures[locator.original_url] = locator.packages_not_found
        return failures

    # -- Private API of the Download service --

    def download(self, url):
        response, _ = self.opener.retrieve(url)

        # Now that we're sure that our request was successful
        header = response.headers.get('content-disposition', '')
        file_name = re.findall(r'filename=([^;]+)', header)
        return self.index.from_data(
            file_name and file_name[0] or url, response.read(
                cache_content=True, decode_content=False))
