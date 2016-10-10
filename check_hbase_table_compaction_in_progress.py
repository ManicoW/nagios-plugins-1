#!/usr/bin/env python
#  vim:ts=4:sts=4:sw=4:et
#
#  Author: Hari Sekhon
#  Date: 2016-09-16 12:59:08 +0200 (Fri, 16 Sep 2016)
#
#  https://github.com/harisekhon/nagios-plugins
#
#  License: see accompanying Hari Sekhon LICENSE file
#
#  If you're using my code you're welcome to connect with me on LinkedIn
#  and optionally send me feedback to help steer this or other code I publish
#
#  https://www.linkedin.com/in/harisekhon
#

"""

Nagios Plugin to check if a given table is compacting via the HMaster JSP UI

Raises Warning if the given table is compacting (silence warning level during off-peak compaction maintenance window).

Raises Critical if the given table is not found.

See also check_hbase_regionserver_compaction_in_progress.py which checks for compactions on any table compacting on a
RegionServer by RegionServer basis.

Tested on Hortonworks HDP 2.3 (HBase 1.1.2) and Apache HBase 1.0.3, 1.1.6, 1.2.2

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
#from __future__ import unicode_literals

import logging
import os
import sys
import traceback
try:
    from bs4 import BeautifulSoup
    import requests
except ImportError:
    print(traceback.format_exc(), end='')
    sys.exit(4)
srcdir = os.path.abspath(os.path.dirname(__file__))
libdir = os.path.join(srcdir, 'pylib')
sys.path.append(libdir)
try:
    # pylint: disable=wrong-import-position
    from harisekhon.utils import log, qquit, support_msg
    #from harisekhon.utils import CriticalError, UnknownError
    from harisekhon.utils import validate_host, validate_port, validate_database_tablename
    from harisekhon import NagiosPlugin
except ImportError as _:
    print(traceback.format_exc(), end='')
    sys.exit(4)

__author__ = 'Hari Sekhon'
__version__ = '0.2'


class CheckHBaseTableCompacting(NagiosPlugin):

    def __init__(self):
        # Python 2.x
        super(CheckHBaseTableCompacting, self).__init__()
        # Python 3.x
        # super().__init__()
        self.msg = 'msg not defined'
        self.ok()

    def add_options(self):
        self.add_hostoption(name='HBase Master', default_host='localhost', default_port=16010)
        self.add_opt('-T', '--table', help='Table to check if compacting is in progress')

    def run(self):
        self.no_args()
        host = self.get_opt('host')
        port = self.get_opt('port')
        table = self.get_opt('table')
        validate_host(host)
        validate_port(port)
        validate_database_tablename(table)

        # raises 500 error if table doesn't exist
        url = 'http://%(host)s:%(port)s/table.jsp?name=%(table)s' % locals()
        log.debug('GET %s', url)
        try:
            req = requests.get(url)
        except requests.exceptions.RequestException as _:
            qquit('CRITICAL', _)
        log.debug("response: %s %s", req.status_code, req.reason)
        log.debug("content:\n%s\n%s\n%s", '='*80, req.content.strip(), '='*80)
        if req.status_code != 200:
            info = ''
            #if req.status_code == '500' and 'TableNotFoundException' in req.content:
            if 'TableNotFoundException' in req.content:
                info = 'table not found'
            qquit('CRITICAL', "%s %s %s" % (req.status_code, req.reason, info))
        is_table_compacting = self.parse_is_table_compacting(req.content)
        self.msg = 'HBase table \'{0}\' '.format(table)
        if is_table_compacting:
            self.warning()
            self.msg += 'has compaction in progress'
        else:
            self.msg += 'has no compaction in progress'

    @staticmethod
    def parse_is_table_compacting(content):
        soup = BeautifulSoup(content, 'html.parser')
        if log.isEnabledFor(logging.DEBUG):
            log.debug("BeautifulSoup prettified:\n{0}\n{1}".format(soup.prettify(), '='*80))
        try:
            headings = soup.findAll('h2')
            for heading in headings:
                log.debug("checking heading '%s'", heading)
                if heading.get_text() == 'Table Attributes':
                    log.debug('found Table Attributes section header')
                    table = heading.find_next('table')
                    log.debug('checking first following table')
                    if log.isEnabledFor(logging.DEBUG):
                        log.debug('table:\n%s\n%s', table.prettify(), '='*80)
                    rows = table.findChildren('tr')
                    if len(rows) < 3:
                        qquit('UNKNOWN', 'parse error - less than the 3 expected rows in table attributes')
                    col_names = rows[0].findChildren('th')
                    if len(col_names) < 3:
                        qquit('UNKNOWN', 'parse error - less than the 3 expected column headings')
                    first_col = col_names[0].get_text().strip()
                    if first_col != 'Attribute Name':
                        qquit('UNKNOWN',
                              'parse error - expected first column header to be \'{0}\' but got \'\' instead. '\
                              .format('Attribute Name')
                              + support_msg())
                    for row in rows[1:]:
                        cols = row.findChildren('td')
                        if len(cols) < 3:
                            qquit('UNKNOWN', 'parse error - less than the 3 expected columns in table attributes. '
                                  + support_msg())
                        if cols[0].get_text().strip() == 'Compaction':
                            compaction_state = cols[1].get_text().strip()
                            # NONE when enabled, Unknown when disabled
                            if compaction_state in ('NONE', 'Unknown'):
                                return False
                            else:
                                return True
            qquit('UNKNOWN', 'parse error - failed to find Table Attributes section in JSP. ' + support_msg())
        except (AttributeError, TypeError):
            qquit('UNKNOWN', 'failed to parse output. ' + support_msg())


if __name__ == '__main__':
    CheckHBaseTableCompacting().main()
