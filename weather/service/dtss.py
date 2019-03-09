"""This file contains the Distributed TimeSeries Server (Dtss) host. This is a service that runs as a service and let's
me poll timeseries data either directly from the source (Netatmo API) or from the containers (local cache) available to
the Dtss. This lets gives me local storage of the data that can be queried freely."""

from typing import Dict, Any
from shyft.api import DtsServer, StringVector, TsVector, UtcPeriod, TsInfoVector
from weather.data_collection.netatmo import NetatmoRepository
from weather.interfaces.data_collection_repository import DataCollectionRepository
from weather.test.utilities import MockRepository1, MockRepository2
import logging
import socket
import urllib

ConfigType = Dict[str, object]


_DEFAULT_DATA_COLLECTION_REPO_TYPES = (NetatmoRepository, MockRepository1, MockRepository2)
_DEFAULT_DATA_COLLECTION_REPO_TYPE_LOOKUP = {repo.name: repo for repo in _DEFAULT_DATA_COLLECTION_REPO_TYPES}


class DtssHostConfigurationError(Exception):
    """Exception raised by the DtssHost for configuration errors."""
    pass


class DtssHostError(Exception):
    """Exception raised by the DtssHost for runtime errors."""
    pass


class DtssHost:
    """DtssHost is a data service that accepts queries for TimeSeries data using url identifiers and UtcPeriods.
    The service handles calls both for source systems (i.e. Netatmo api) and data calls directed to a local
    container hosting the same data for faster queries."""

    def __init__(self,
                 dtss_port_num: int,
                 data_collection_repositories: Dict[str, Dict[str, Any]],
                 container_directory: str) -> None:
        """DtssHost constructor needs a port number for the service end point. The data collection repositories are for
        collecting the source data of interest, and the container directory is where the timeseries files are stored for
        the local database.

        Args:
            dtss_port_num: The listening port the DtsServer uses.
            data_collection_repositories: The data collection repositories that we are able to collect data from.
            container_directory: The disk location where we look for and store timeseries.
            data_collection_repos: A sequence of DataCollectionRepository that are available for the DtssHost.
        """
        self.dtss_port_num = dtss_port_num

        # Build a dictionary containing every available repository.
        self.repos: Dict[str, DataCollectionRepository] = {
            name: _DEFAULT_DATA_COLLECTION_REPO_TYPE_LOOKUP[name](**config)
            for name, config in data_collection_repositories.items()
            if name in _DEFAULT_DATA_COLLECTION_REPO_TYPE_LOOKUP
            }

        self.container_directory = container_directory

        # Initialize and configure server:
        self.dtss: DtsServer = None

    def make_server(self) -> DtsServer:
        """Construct and configure our DtsServer."""
        dtss = DtsServer()
        dtss.set_listening_port(self.dtss_port_num)
        dtss.set_auto_cache(True)
        dtss.cb = self.read_callback
        # self.dtss.find_cb = self.dtss_find_callback
        # self.dtss.store_ts_cb = self.dtss_store_callback

        return dtss

    def start(self) -> None:
        """Start the DtsServer service running at port self.dtss_port_num."""
        if self.dtss:
            logging.info('Attempted to start a server that is already running.')
        else:
            self.dtss = self.make_server()
            logging.info(f'DtsServer start at {self.dtss_port_num}.')
            self.dtss.start_async()

    def stop(self) -> None:
        """Stop the DtsServer service running at port self.dtss_port_num."""
        if not self.dtss:
            logging.info('Attempted to stop a server that isn''t running.')
        else:
            logging.info(f'DtsServer stop at port {self.dtss_port_num}.')
            self.dtss.clear()
            del self.dtss
            self.dtss = None

    @property
    def address(self) -> str:
        """Return the full service address of the DtsServer."""
        return f'{socket.gethostname()}:{self.dtss_port_num}'

    def read_callback(self, *, ts_ids: StringVector, read_period: UtcPeriod) -> TsVector:
        """DtssHost.read_callback accepts a set of urls identifying timeseries and a read period and returns bound
        TimeSeries in a TsVector that contain data at least covering the read_period.

        Args:
            ts_ids: A sequence of strings identifying specific timeseries available from the underlying
                    DataCollectionRepository's.
            read_period: A period defined by a utc timestamp for the start and end of the analysis period.

        Returns:
            A TsVector containing the resulting timeseries containing data enough to cover the query period.
        """

        data = dict()  # Group ts_ids by repo.name (scheme).
        for enum, ts_id in enumerate(ts_ids):
            repo_name = self.get_repo_name_from_url(ts_id)
            if repo_name not in data:
                data[repo_name] = []
            data[repo_name].append(dict(enum=enum, ts_id=ts_id, ts=None))

        for repo_name in data:
            tsvec = self.repos[repo_name].read_callback(
                ts_ids=StringVector([ts['ts_id'] for ts in data[repo_name]]),
                read_period=read_period)
            for index, ts in enumerate(tsvec):
                data[repo_name][index]['ts'] = ts

        # Collapse nested lists and sort by initial enumerate:
        transpose_data = []
        for items in data.values():
            transpose_data.extend(items)
        sort = sorted(transpose_data, key=lambda item: item['enum'])

        return TsVector([item['ts'] for item in sort])

    def find_callback(self, *, query: str) -> TsInfoVector:
        """DtssHost.find:callback accepts a query string and returns metadata for any timeseries found."""
        repo_name = self.get_repo_name_from_url(query)
        return self.repos[repo_name].find_callback(query=query)

    def get_repo_name_from_url(self, url: str) -> str:
        """Get the repo name (scheme) from a url, so that we can route it correctly."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in self.repos:
            raise DtssHostError(f'ts_id scheme {parsed.scheme} does not match any '
                                f'that are available for the DtssHost: '
                                f'{", ".join(scheme for scheme in self.repos)}')
        return parsed.scheme


